#!/usr/bin/env bash
# p3_video_chain.sh — P3-B, the video discriminator (preregistration.json P3_B), on the box, one workload at a time.
#
#   bash working/scripts/p3_video_chain.sh <campaign_dir_abs> <expect_head>
#
# 0. The fixed frame set: the first NV=3 measured rows of the AMI manifest, extracted once with li:video's
#    imageio-ffmpeg binary and the engine-mirror argv (fps=1/15, passthrough, png) into ~/p3b_frames_<campaign>
#    (outside the repository: ~hundreds of MB); p3b_frames_manifest.json (name, bytes, sha256 per frame) is the record.
# 1. ABAB, two runs each, every cell ALONE (no other container exists at its start; exactly one model instance):
#      p3b_a_1 p3b_b_1 p3b_c_1 p3b_a_2 p3b_b_2 p3b_c_2
#    (a) rr:patched-video's embedded Python, bare script (working/video/p3b/p3b_bench.py), T=4, one caller thread
#    (b) li:video's Python, the same bare script, T=4, one caller thread
#    (c) the RR engine task process: rr:patched-video, one token, the P1 stamped detect copy, K=1 (one video in flight)
#        on the SAME three videos, T=4; P0_ONTOKEN D0; the (1) inspection of the task process's maps at warm-up end
# 2. p3b_d_1: ONE LlamaIndex service leg (li:video, one instance, stamped, K=1, same videos, T=4) whose purpose is
#    the (1) inspection of LlamaIndex's detector process during a leg; its figures are context, not a reading.
# Per leg: steal (/proc/stat), CPU model, MHz, boot id, the 1 Hz memory sampler on the cell's container (started
# after the leg directory exists; G_memstat after the first leg: exit 10), and the budget check (P3_DEADLINE_EPOCH).
set -uo pipefail
echo "p3_video_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head>" >&2; exit 2; }
D="$1"; H="$2"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
TREE="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$TREE" || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
PY="$HOME/.venv/bin/python"
VMAN="$HOME/parity-bench-video/working/video/ami_video_manifest.jsonl"
VDIR="$HOME/parity-bench-video/corpus/ami/full"
[ -f "$VMAN" ] && [ -d "$VDIR" ] || { echo "REFUSED: AMI manifest or corpus absent" >&2; exit 2; }
S3="s3://rocketride-benchmark-data/ansh/parity-p3/$REL"
NV=3
FR="$HOME/p3b_frames_$(basename "$D")"
RRW="${P3B_RR_WEIGHTS:?P3B_RR_WEIGHTS (the rf-detr-base.pth directory inside rr:patched-video) must be set by the caller}"
LIW="${P3B_LI_WEIGHTS:?P3B_LI_WEIGHTS (the rf-detr-base.pth directory inside li:video) must be set by the caller}"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  head $HAVE  deadline ${P3_DEADLINE_EPOCH:-unset}  weights rr=$RRW li=$LIW"
for img in rr:patched rr:patched-video li:video; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
R=(); LAST=""
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
alone() { local n; n="$(docker ps -aq | wc -l)"; [ "$n" = 0 ] || { echo "REFUSED: $n container(s) exist — every P3-B cell runs ALONE"; docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'; return 1; }; }
up() { local dest="$S3/$1/"; aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists — not uploading over it"; return 1; }; aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"; }
up1() { aws s3 ls "$S3/$1" >/dev/null 2>&1 || aws s3 cp "$D/$1" "$S3/$1" --only-show-errors; }
sess_open() { cat /proc/stat | head -1 > "$1/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$1/boot_id.txt"; grep -m1 "model name" /proc/cpuinfo > "$1/cpu_model.txt"; grep MHz /proc/cpuinfo > "$1/mhz_open.txt"; }
sess_close() { cat /proc/stat | head -1 > "$1/procstat_close.txt"; grep MHz /proc/cpuinfo > "$1/mhz_close.txt"; }
# the (1) inspection: every process in container $1 that has libtorch mapped -> its OpenMP/BLAS/threading runtimes
inspect() {
  docker exec "$1" sh -c 'for p in /proc/[0-9]*; do if grep -q libtorch_cpu "$p/maps" 2>/dev/null; then echo "PID ${p#/proc/} $(cat $p/comm) $(tr "\0" " " < $p/cmdline | cut -c1-160)"; awk "{print \$6}" "$p/maps" | grep -E "libgomp|libiomp|libomp|libmkl|libopenblas|libblas|liblapack|libtbb|libgfortran|libtorch|libc10|libnuma|_multiarray_umath|libcblas|libflexiblas" | sort -u; fi; done' > "$2" 2>&1
  echo "inspection $1 -> $2 ($(grep -c '^PID' "$2") torch process(es))"
}
past() { [ -n "${P3_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P3_DEADLINE_EPOCH" ]; }
FIRSTDONE=0
memgate() {
  [ "$FIRSTDONE" = 1 ] && return 0
  FIRSTDONE=1
  "$PY" working/scripts/p3_gates.py memstat "$D" "$1"; local g=$?
  [ -f "$D/gates/G_memstat_$1.json" ] && up1 "gates/G_memstat_$1.json"
  [ "$g" = 0 ] || { R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10; }
}
finish() {
  "$PY" - "$D/chain_p3b_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  up1 chain_p3b_done.json
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE p3b $1"
}

# ---------------------------------------------------------------- 0. the frame set
alone || exit 3
if [ ! -f "$D/p3b_frames_manifest.json" ]; then
  [ -e "$FR" ] && { echo "REFUSED: $FR exists without a manifest (append-only)"; exit 3; }
  mkdir -p "$FR"; chmod 0777 "$FR"      # li:video runs as uid 10002 (ws1v); the extraction writes here
  mapfile -t VIDS < <("$PY" -c 'import json,sys; rows=[json.loads(x) for x in open(sys.argv[1]) if x.strip() and not x.startswith("#")]; rows=[r for r in rows if isinstance(r,dict) and r.get("role")=="measured"][:int(sys.argv[2])]; print("\n".join(r["file"] for r in rows))' "$VMAN" "$NV")
  [ "${#VIDS[@]}" = "$NV" ] || { echo "REFUSED: could not read $NV measured rows from the manifest (${#VIDS[@]})"; exit 2; }
  echo "frame videos: ${VIDS[*]}"
  docker run --rm --name p3b_frames --network none -v "$VDIR:/v:ro" -v "$FR:/frames" -v "$TREE/working/video/p3b:/x:ro" --entrypoint python li:video /x/p3b_frames.py --out /frames $(printf '/v/%s ' "${VIDS[@]}") || { echo "REFUSED: frame extraction failed"; exit 4; }
  "$PY" - "$FR" "$D/p3b_frames_manifest.json" "${VIDS[@]}" <<'PYM'
import hashlib, json, os, sys
fr, out, vids = sys.argv[1], sys.argv[2], sys.argv[3:]
rows = []
for dp, _, fs in sorted(os.walk(fr)):
    for f in sorted(fs):
        if f.endswith(".png"):
            p = os.path.join(dp, f); b = open(p, "rb").read()
            rows.append({"frame": os.path.relpath(p, fr), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
rows.sort(key=lambda r: r["frame"])
json.dump({"videos": vids, "argv": "fps=1/15 -fps_mode passthrough -vcodec png (li:video imageio-ffmpeg)", "n_frames": len(rows),
           "set_sha256": hashlib.sha256("".join(r["sha256"] for r in rows).encode()).hexdigest(), "frames": rows},
          open(out, "x"), indent=1)
print("frames", len(rows))
PYM
  up1 p3b_frames_manifest.json
fi

# ---------------------------------------------------------------- 1. the cells
# bare <name> <a|b>
bare() {
  local name="$1" cell="$2" try L rc C MPID
  past && { echo "!! $name NOT RUN: the P3 7-hour budget has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1; }
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"; [ -e "$L" ] && continue
    alone || { R+=("${name}${try}:NOT_ALONE"); return 1; }
    mkdir -p "$L"; chmod 0777 "$L"; C="p3b_${cell}"   # (b) runs as li:video's uid 10002 and writes bench.json here
    echo "===== LEG ${name}${try} (bare $cell) $(date -u +%H:%M:%SZ) ====="
    sess_open "$L"
    if [ "$cell" = a ]; then
      docker run -d --name "$C" --network none --memory 16g $(envargs 4) -v "$FR:/frames:ro" -v "$TREE/working/video/p3b:/x:ro" -v "$L:/out" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine rr:patched-video /x/p3b_bench.py --frames /frames --weights-dir "$RRW" --out /out/bench.json >/dev/null || { rc=4; R+=("${name}${try}:rc=$rc"); continue; }
    else
      docker run -d --name "$C" --network none --memory 16g $(envargs 4) -v "$FR:/frames:ro" -v "$TREE/working/video/p3b:/x:ro" -v "$L:/out" --entrypoint python li:video /x/p3b_bench.py --frames /frames --weights-dir "$LIW" --out /out/bench.json >/dev/null || { rc=4; R+=("${name}${try}:rc=$rc"); continue; }
    fi
    "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
    MPID=$!
    rc="$(docker wait "$C")"
    touch "$L/.leg_done"; wait "$MPID" 2>/dev/null
    docker logs "$C" > "$L/container_log.txt" 2>&1; docker rm "$C" >/dev/null 2>&1
    sess_close "$L"
    grep '^P3B_BENCH ' "$L/container_log.txt" | tail -1
    up "${name}${try}"
    if [ "$rc" = 0 ] && [ -f "$L/bench.json" ]; then R+=("${name}${try}:rc=0"); LAST="${name}${try}"; memgate "${name}${try}"; return 0; fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED"; LAST=""; return 1
}
# svc <name> <rr|li> : a service leg, K=1, stamped, the (1) inspection at warm-up end (driver P1_SYNC_DIR hook)
svc() {
  local name="$1" arm="$2" try L rc C SPID MPID WPID
  past && { echo "!! $name NOT RUN: the P3 7-hour budget has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1; }
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"; [ -e "$L" ] && continue
    alone || { R+=("${name}${try}:NOT_ALONE"); return 1; }
    mkdir -p "$L"; rc=0
    echo "===== LEG ${name}${try} ($arm service, K=1, stamped) $(date -u +%H:%M:%SZ) ====="
    if [ "$arm" = rr ]; then
      C=rr
      docker run -d --name rr --memory 58g $(envargs 4) --log-opt max-size=200m --network host rr:patched-video >/dev/null || rc=4
      [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
      [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh rr install rr || rc=6; }
      [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
    else
      C=li_bal_0
      docker run -d --name li_bal_0 --memory 7g $(envargs 4) -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null || rc=4
      [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh li install li_bal_0 || rc=6; }
      [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
    fi
    if [ "$rc" = 0 ]; then
      sess_open "$L"
      PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
      SPID=$!
      "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
      MPID=$!
      ( for i in $(seq 1 1200); do [ -f "$L/.warm_done" ] && break; sleep 1; done
        inspect "$C" "$L/runtime_maps.txt"; touch "$L/.tracer_ready" ) &
      WPID=$!
      export P1_SYNC_DIR="$L"
      if [ "$arm" = rr ]; then
        P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$NV" --blast-concurrency 1 --rr-threads-env 4 --manifest "$VMAN" --image-lineage "rr:patched-video sha256:b7f51acc (P3 $name, 1 token, K=1, six vars=4)" --out-dir "$L" > "$L/driver.log" 2>&1
      else
        "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$NV" --blast-concurrency 1 --li-ports 8802 --li-containers li_bal_0 --manifest "$VMAN" --image-lineage "li:video sha256:0a52afcb (P3 $name, ONE instance, K=1, six vars=4)" --out-dir "$L" > "$L/driver.log" 2>&1
      fi
      rc=$?
      unset P1_SYNC_DIR
      kill "$WPID" 2>/dev/null; wait "$WPID" 2>/dev/null
      sess_close "$L"
      touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
      bash working/scripts/p1_stamp.sh "$arm" collect "$C" "$L"
      docker logs "$C" > "$L/dockerlog.txt" 2>&1
    fi
    tail -3 "$L/driver.log" 2>/dev/null
    docker stop "$C" >/dev/null 2>&1; docker rm "$C" >/dev/null 2>&1
    up "${name}${try}"
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    if [ "$rc" = 0 ]; then R+=("${name}${try}:rc=0"); LAST="${name}${try}"; memgate "${name}${try}"; return 0; fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED"; LAST=""; return 1
}
bare p3b_a_1 a
bare p3b_b_1 b
svc  p3b_c_1 rr
bare p3b_a_2 a
bare p3b_b_2 b
svc  p3b_c_2 rr
svc  p3b_d_1 li
finish complete
