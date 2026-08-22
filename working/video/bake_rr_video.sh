#!/usr/bin/env bash
# =============================================================================
# CROSSROAD 18 (2026-08-21): bake the vision deps into rr:patched-video.
#
# Why: the engine installs node requirements at FIRST PIPELINE LOAD into the
# container's WRITABLE LAYER, which `docker rm` destroys. probe_run.sh
# recreates the container per thread point and probe_concurrency per M —
# ~8 fresh containers each re-pulling 3-4.5 GB of wheels plus rf-detr-base.pth
# and miniLM weights. One load, one `docker commit`, and every downstream
# container starts warm.
#
# The bake is VERIFIED, not trusted: four read-backs below, and the smoke's
# image-identity section still MEASURES the duplication patch through the PDF
# fixture on every run.
#
# Usage (box):   bash working/video/bake_rr_video.sh
# Produces:      rr:patched-video  (+ bake_readback.json next to this script)
# =============================================================================
set -euo pipefail
PY="${PYBIN:-$HOME/.venv/bin/python}"          # rocketride SDK lives in the Phase 1 venv
[ -x "$PY" ] || { echo "NOT DONE — $PY missing (needs rocketride SDK)"; exit 1; }
cd "$(dirname "$0")/../.."

SRC_IMAGE="${SRC_IMAGE:-rr:patched}"
OUT_IMAGE="${OUT_IMAGE:-rr:patched-video}"
PINS="working/video/li_video/engine_pins.txt"
FIXTURE="working/video/probe/media/black_60s_352x288.avi"
RFDETR_MD5_EXPECTED="b4d3ce46099eaed50626ede388caf979"   # rfdetr 1.5.2 assets/model_weights.py:192-196 (rf-detr-base-coco.pth)
C=rrbake
# A failed bake must not leave a half-booted container for the next attempt to
# inherit (2026-08-21). Idempotent: on success both are already removed.
cleanup() { docker rm -f "$C" "${C}2" >/dev/null 2>&1 || true; }
trap cleanup EXIT

[ -f "$PINS" ] || { echo "NOT DONE — $PINS missing (extract_engine_pins.sh first)"; exit 1; }
[ -f "$FIXTURE" ] || { echo "NOT DONE — $FIXTURE missing (make_black_fixture.sh first; it exercises the full path in seconds)"; exit 1; }

echo "== 0. SDK identity (instance six): entry points vs the INSTALLED wheel, then the static scan =="
"$PY" working/video/sdk_identity.py --json | tee working/video/bake_sdk_identity.json || {
  echo "NOT DONE — SDK identity read-back failed (names/params vs installed rocketride)"; exit 1; }
"$PY" working/video/sdk_identity.py --scan working/video >/dev/null || {
  echo "NOT DONE — static SDK scan found an import/call outside the verified surface"; exit 1; }

echo "== 1. fresh container from $SRC_IMAGE; ONE pipe load pulls deps + weights =="
docker rm -f "$C" 2>/dev/null || true
# Crossroad 22: --network host, matching Phase 1 section C — docker-proxy adds
# a userspace hop AND binds the published port before the engine listens,
# which is exactly what broke the old TCP readiness check (instance seven).
docker run -d --name "$C" --memory 58g --network host "$SRC_IMAGE" >/dev/null
# Readiness = a real SDK connect (one helper, everywhere); asserts host
# networking first and prints the log tail on failure. Engine first boot
# installs deps via uv — minutes at low CPU is normal.
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container "$C" || {
  echo "NOT DONE — engine never became SDK-connectable (see log tail above)"; exit 1; }

T0=$(date +%s)
"$PY" - "$FIXTURE" <<'EOF'
import asyncio, os, sys, time
os.environ.setdefault('ROCKETRIDE_URI', 'http://127.0.0.1:5565')
os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
from rocketride import RocketRideClient
async def main():
    # The RAW measured pipe, fixed project_id and all — the ONLY use() in the
    # tree allowed to skip a fresh project_id: sequential, in a fresh container,
    # nothing concurrent to collide with, and 'the exact measured pipe loads
    # and installs its deps' is the property being baked.
    client = RocketRideClient()
    await client.connect(timeout=60000)
    t0 = time.monotonic()
    tok = (await client.use(filepath='working/video/benchmark_video_detect.pipe', ttl=3600))['token']
    print(f'use() [installs deps + downloads weights]: {time.monotonic()-t0:.0f}s')
    try:
        t0 = time.monotonic()
        r = await client.send(tok, open(sys.argv[1],'rb').read(), objinfo={'name':'bake.avi'},
                              mimetype='video/x-msvideo')
        docs = (r or {}).get('documents')
        print(f'send(black fixture): {time.monotonic()-t0:.0f}s, documents={"present" if docs is not None else "ABSENT"}')
    finally:
        # terminate BEFORE the commit: the baked image must not carry a live task
        await asyncio.wait_for(client.terminate(tok), timeout=120)
        await client.disconnect()
asyncio.run(main())
EOF
echo "bake load total: $(( $(date +%s) - T0 ))s"

echo "== 2. commit =="
docker commit "$C" "$OUT_IMAGE" >/dev/null
docker rm -f "$C" >/dev/null

echo "== 3. read-backs on the BAKED image =="
RB="working/video/bake_readback.json"

# (a) labels preserved through commit
L1=$(docker inspect -f '{{index .Config.Labels "benchmark.rocketride.duplication_patch_applied"}}' "$OUT_IMAGE")
L2=$(docker inspect -f '{{index .Config.Labels "benchmark.rocketride.duplication_patch_id"}}' "$OUT_IMAGE")
L3=$(docker inspect -f '{{index .Config.Labels "benchmark.rocketride.engine_version"}}' "$OUT_IMAGE")
[ "$L1" = "1" ] || { echo "NOT DONE — baked image lost duplication_patch_applied ($L1)"; exit 1; }
echo "labels: patch=$L1 id=$L2 engine=$L3"

# (b) pinned vision packages INSIDE the baked image, versions vs engine_pins.txt
# (c) weights present in the engine cache, rf-detr md5 vs the package registry
# No embedded-python execution: the engine ships NO python binary FILE — the
# interpreter is inside the ELF (CPython 3.12.13, confirmed from the pinned
# binary AND the box's own find). Versions come from the dist-info directory
# names in site-packages, which is pure filesystem truth and needs no
# interpreter at all (the first bake attempt's find for bin/python3* could
# never have worked here).
docker run --rm "$OUT_IMAGE" sh -c '
  SP=$(find /opt/rocketride/engine -maxdepth 4 -type d -name site-packages 2>/dev/null | head -1)
  echo "site_packages=$SP"
  [ -n "$SP" ] && ls "$SP" | grep -E "\.dist-info$" | sed "s/\.dist-info$//"
  find /opt/rocketride/engine/cache -name "*.pth" -exec md5sum {} \; 2>/dev/null
  find /opt/rocketride/engine/cache -iname "*minilm*" -maxdepth 6 -type d 2>/dev/null | head -3
  ls /root/.cache/huggingface 2>/dev/null | head -3 || true
' | tee /tmp/bake_inside.txt

"$PY" - "$PINS" /tmp/bake_inside.txt "$RFDETR_MD5_EXPECTED" "$RB" <<'EOF'
import json, sys
pins = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith('#') and '==' in line:
        n, v = line.split('==')
        pins[n.strip().lower().replace('_', '-')] = v.strip()
inside, pth = {}, {}
for line in open(sys.argv[2]):
    line = line.strip()
    if line.endswith('.pth') and len(line.split()) == 2:
        h, path = line.split(); pth[path] = h
    elif ('-' in line and ' ' not in line
          and not line.startswith(('site_packages=', '/'))):
        # dist-info stem: {name}-{version}; wheel-normalized names use '_',
        # local versions use '+' (never '-'), so the LAST hyphen splits them.
        n, _, v = line.rpartition('-')
        if n and v[:1].isdigit():
            inside[n.lower().replace('_', '-')] = v
bad = {n: (pins.get(n), inside.get(n)) for n in pins
       if n in inside and inside[n] != pins[n]}
absent = [n for n in ('rfdetr', 'torch', 'transformers', 'supervision', 'timm')
          if inside.get(n) in (None, 'ABSENT')]
rf = {p: h for p, h in pth.items() if 'rf-detr-base' in p}
rf_ok = any(h == sys.argv[3] for h in rf.values())
report = {'pins_mismatch': bad or None, 'pins_absent': absent or None,
          'pth_files': pth, 'rfdetr_base_md5_expected': sys.argv[3],
          'rfdetr_base_md5_ok': rf_ok, 'packages_inside': inside}
json.dump(report, open(sys.argv[4], 'w'), indent=1)
print(json.dumps({k: report[k] for k in ('pins_mismatch','pins_absent','rfdetr_base_md5_ok')}, indent=1))
if bad or absent or not rf_ok:
    print('NOT DONE — baked image fails pin/weight read-back'); raise SystemExit(1)
print('read-back (b)+(c) PASS: packages at pinned versions, rf-detr-base md5 matches the 1.5.2 registry')
EOF

# (d) the env_probe node INSIDE the image must be byte-identical to the repo
# (2026-08-22). The bake commits whatever rr:patched was built with; a stale
# node there rides silently into rr:patched-video and reports an old field
# set, which the driver used to read as None. Compare image-vs-repo md5 —
# self-updating, no constant to drift. The runtime assert (assert_envprobe_
# complete) is the second net; this refuses to ship the bad image at all.
NODE_REPO="working/nodes/env_probe/IInstance.py"
NODE_IN_IMG="/opt/rocketride/engine/nodes/env_probe/IInstance.py"
REPO_MD5=$(md5sum "$NODE_REPO" 2>/dev/null | awk '{print $1}' || md5 -q "$NODE_REPO")
IMG_MD5=$(docker run --rm "$OUT_IMAGE" sh -c "md5sum '$NODE_IN_IMG' 2>/dev/null | awk '{print \$1}'")
echo "env_probe node md5: repo=$REPO_MD5 image=$IMG_MD5"
if [ -z "$IMG_MD5" ]; then
  echo "NOT DONE — env_probe node ABSENT inside $OUT_IMAGE ($NODE_IN_IMG): the base image never got it (docker/Dockerfile.rocketride COPYs it into rr:patched)."; exit 1
fi
if [ "$REPO_MD5" != "$IMG_MD5" ]; then
  echo "NOT DONE — env_probe node inside $OUT_IMAGE ($IMG_MD5) != repo ($REPO_MD5): a STALE node emitting an old field set. Rebuild rr:patched from the current repo, then re-bake."; exit 1
fi
echo "read-back (d) PASS: env_probe node inside the image is byte-identical to the repo (schema current)"

echo "== 4. no-install proof: fresh container from the bake must be ready FAST and pull NOTHING =="
docker rm -f "${C}2" 2>/dev/null || true
docker run -d --name "${C}2" --memory 58g --network host "$OUT_IMAGE" >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 600 --container "${C}2" || {
  echo "NOT DONE — baked image never became SDK-connectable"; exit 1; }
T0=$(date +%s)
"$PY" - <<'EOF'
import asyncio, os, time
os.environ.setdefault('ROCKETRIDE_URI', 'http://127.0.0.1:5565')
os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
from rocketride import RocketRideClient
async def main():
    client = RocketRideClient()
    await client.connect(timeout=60000)
    t0 = time.monotonic()
    tok = (await client.use(filepath='working/video/benchmark_video_detect.pipe', ttl=600))['token']
    print(f'use() on the BAKED image: {time.monotonic()-t0:.0f}s')
    await asyncio.wait_for(client.terminate(tok), timeout=60)
    await client.disconnect()
asyncio.run(main())
EOF
READY=$(( $(date +%s) - T0 ))
DLLINES=$(docker logs "${C}2" 2>&1 | grep -ci "downloading\|installing" || true)
docker rm -f "${C}2" >/dev/null
echo "no-install proof: use()=${READY}s, download/install log lines=${DLLINES}"
if [ "$READY" -gt 180 ] || [ "$DLLINES" -gt 0 ]; then
  echo "NOT DONE — baked image still installs at load (ready=${READY}s, dl_lines=${DLLINES})"; exit 1
fi
echo "DONE — $OUT_IMAGE baked and verified (SDK identity, labels, pins, weights md5, no-install)."
echo "Read-backs: $RB + working/video/bake_sdk_identity.json"
