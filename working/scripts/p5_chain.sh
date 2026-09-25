#!/usr/bin/env bash
# p5_chain.sh — P5 on the box (preregistration.json), one workload at a time. Leg mechanics are P4's (p4_video_chain.sh):
# stamped detect copies, the percore and 1 Hz memory samplers per leg, session facts, append-only S3 uploads.
#
#   bash working/scripts/p5_chain.sh <campaign_dir_abs> <expect_head> build     rr:p5-infer + G_build_A (p5_infer_build.sh)
#   bash working/scripts/p5_chain.sh <campaign_dir_abs> <expect_head> control   gate-control targets (not measured legs), each K=2, 2 videos,
#                                                                               stamped: p5ctl_p5 (rr:p5-infer), p5ctl_stock (rr:patched-video),
#                                                                               p5ctl_li (li:video); and p5ctl_canary (the canary once)
#   bash working/scripts/p5_chain.sh <campaign_dir_abs> <expect_head> run       refuses unless the latest gate_controls record says all_pass.
#       P5-A smoke, two ABAB rounds, each preceded by the canary:
#         p5c_can_r  p5a_stock16_r  p5a_p5k16_r  p5a_p5k1_r  p5a_li16_r        (r = 1, 2)
#       after every leg G_d0 (exit 9) and G_cell (exit 11); after the canary G_canary (exit 11); G_memstat after the first leg (exit 10);
#       after round 1's p5a_p5k1_1: G_correct_A1 (HARD: output-changing -> exit 13, P5-A and P5-B stop);
#       after round 2: G_correct_A (all pairs, recorded) and G_smoke_P5B (S1 AND S2 pooled); if it fires, P5-B follows:
#       168 videos in 11 blocks (10 x 16 + 8), arms alternating block by block (odd blocks RR first, even blocks LI first), one
#       container per arm for the whole stage, the idle arm's container PAUSED (docker pause: frozen, no CPU); the canary (both
#       paused) before the first block and after block 6.
#       Budget: P5_DEADLINE_EPOCH = the run stage's first leg + 27,000 s; a leg or block not started by then is NOT RUN.
set -uo pipefail
echo "p5_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head> build|control|run" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
TREE="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$TREE" || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: worktree at $HAVE, caller expects $H" >&2; exit 2; }
PY="$HOME/.venv/bin/python"
"$PY" -c 'import psutil' || { echo "REFUSED: $PY cannot import psutil" >&2; exit 2; }
VMAN="$HOME/parity-bench-video/working/video/ami_video_manifest.jsonl"
[ -f "$VMAN" ] || { echo "REFUSED: AMI manifest $VMAN absent" >&2; exit 2; }
FR="$HOME/p3b_frames_parity_p3_20260925T035027Z"; FMAN="$TREE/working/results/parity_p3_20260925T035027Z/p3b_frames_manifest.json"
CANV=v00_EN2001a; RRW=/opt/rocketride/engine/cache/models/rfdetr
S3="s3://rocketride-benchmark-data/ansh/parity-p5/$REL"
T=4
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  manifest $(sha256sum "$VMAN" | cut -c1-16)"
for img in rr:patched rr:patched-video li:video rr:p5-infer; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
R=(); LAST=""; FIRSTDONE=0
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
up() { local dest="$S3/$1/"; aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists — not uploading over it"; return 1; }; aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"; }
up1() { aws s3 ls "$S3/$1" >/dev/null 2>&1 || aws s3 cp "$D/$1" "$S3/$1" --only-show-errors; }
upgates() { for f in "$D"/gates/*.json; do [ -f "$f" ] && up1 "gates/$(basename "$f")"; done; }
past() { [ -n "${P5_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P5_DEADLINE_EPOCH" ]; }
g() { "$PY" working/scripts/p5_gates.py "$@"; }
imgid() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null; }
sess_open() { cat /proc/stat | head -1 > "$1/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$1/boot_id.txt"; grep -m1 "model name" /proc/cpuinfo > "$1/cpu_model.txt"; grep MHz /proc/cpuinfo > "$1/mhz_open.txt"; }
sess_close() { cat /proc/stat | head -1 > "$1/procstat_close.txt"; grep MHz /proc/cpuinfo > "$1/mhz_close.txt"; }

if [ "$STAGE" = run ]; then   # the GATE CONTROLS rule: checked before anything is recorded
  CTL="$(ls "$D"/gate_controls.json "$D"/gate_controls_run*.json 2>/dev/null | sort -V | tail -1)"
  [ -n "$CTL" ] || { echo "REFUSED: no gate_controls record in $D (the GATE CONTROLS rule)"; exit 12; }
  "$PY" -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("all_pass") is True else 1)' "$CTL" || { echo "REFUSED: $CTL does not say all_pass"; exit 12; }
  echo "gate controls: $(basename "$CTL") all_pass"
fi
"$PY" - "$D/chain_p5_${STAGE}_start.json" "$HAVE" <<'PYSTART' || { echo "REFUSED: chain_p5_${STAGE}_start.json exists (one run per stage)"; exit 3; }
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video", "rr:p5-infer")}
json.dump({"stage_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "head": sys.argv[2],
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(), "image_ids_at_start": ids},
          open(sys.argv[1], "x"), indent=1)
PYSTART
up1 "chain_p5_${STAGE}_start.json"

finish() {
  for img in rr:patched rr:patched-video li:video rr:p5-infer; do echo "image $img $(imgid "$img")"; done
  "$PY" - "$D/chain_p5_${STAGE}_done.json" "$1" "${R[*]}" "${P5_DEADLINE_EPOCH:-}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video", "rr:p5-infer")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "deadline_epoch": sys.argv[4] or None,
           "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  up1 "chain_p5_${STAGE}_done.json"; upgates
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE p5 $STAGE $1"
}

# ---------------------------------------------------------------- the canary (P3-B bare microbenchmark, rr:patched-video)
canary() {  # canary <name> [allow_paused]
  local name="$1" allowp="${2:-0}" try L C=p5_canary MPID rc
  past && { echo "!! $name NOT RUN: budget"; R+=("${name}:NOT_RUN_budget"); return 1; }
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"; [ -e "$L" ] && continue
    if [ "$allowp" = 1 ]; then
      [ "$(docker ps -q --filter status=running | wc -l)" = 0 ] || { R+=("${name}${try}:NOT_ALONE"); return 1; }
    else g alone || { R+=("${name}${try}:NOT_ALONE"); return 1; }; fi
    mkdir -p "$L"; chmod 0777 "$L"
    echo "===== CANARY ${name}${try} $(date -u +%H:%M:%SZ) (paused containers allowed: $allowp) ====="
    docker ps -a --format '{{.Names}} {{.Status}}' > "$L/containers_at_start.txt"
    sess_open "$L"
    docker run -d --name "$C" --network none --memory 16g $(envargs "$T") -v "$FR/$CANV:/frames/$CANV:ro" -v "$TREE/working/video/p3b:/x:ro" -v "$L:/out" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine rr:patched-video /x/p3b_bench.py --frames /frames --weights-dir "$RRW" --out /out/bench.json >/dev/null || { R+=("${name}${try}:rc=4"); continue; }
    "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
    MPID=$!
    rc="$(docker wait "$C")"
    touch "$L/.leg_done"; wait "$MPID" 2>/dev/null
    docker logs "$C" > "$L/container_log.txt" 2>&1; docker rm "$C" >/dev/null 2>&1
    sess_close "$L"
    grep '^P3B_BENCH ' "$L/container_log.txt" | tail -1
    up "${name}${try}"
    if [ "$rc" = 0 ] && [ -f "$L/bench.json" ]; then
      g canary "$D" "${name}${try}" "$FMAN" "$CANV"; local cg=$?; upgates
      [ "$cg" = 0 ] || { R+=("G_canary_${name}${try}:FAIL"); finish "STOPPED: the canary did not run on the manifest's frames"; exit 11; }
      R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times"; return 1
}

# ---------------------------------------------------------------- a smoke / control leg (fresh container)
# leg <name> <stock|p5|li> <K> <n>
leg() {
  local name="$1" fl="$2" K="$3" n="$4" try L rc C SPID MPID IMG
  LAST=""
  if past; then echo "!! $name NOT RUN: the P5 budget has passed"; R+=("${name}:NOT_RUN_budget"); return 1; fi
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"
    [ -e "$L" ] && { echo "REFUSED: $L exists (append-only)"; continue; }
    g alone || { R+=("${name}${try}:NOT_ALONE"); docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'; return 1; }
    mkdir -p "$L"; rc=0
    echo "===== LEG ${name}${try} ($fl K=$K n=$n T=$T) $(date -u +%H:%M:%SZ) ====="
    if [ "$fl" = li ]; then
      C=li_bal_0; IMG=li:video
      docker run -d --name li_bal_0 --memory 7g $(envargs "$T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null || rc=4
      [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh li install li_bal_0 || rc=6; }
      [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
    else
      C=rr; IMG=$([ "$fl" = p5 ] && echo rr:p5-infer || echo rr:patched-video)
      docker run -d --name rr --memory 58g $(envargs "$T") --log-opt max-size=200m --network host "$IMG" >/dev/null || rc=4
      [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
      if [ "$fl" = p5 ]; then [ "$rc" = 0 ] && { bash working/scripts/p5_stamp.sh install rr || rc=6; }
      else [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh rr install rr || rc=6; }; fi
      [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
    fi
    if [ "$rc" = 0 ]; then
      docker inspect -f '{{.Image}}' "$C" > "$L/container_image_id.txt"
      sess_open "$L"
      PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
      SPID=$!
      "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
      MPID=$!
      unset P1_SYNC_DIR
      if [ "$fl" = li ]; then
        "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency "$K" --li-ports 8802 --li-containers li_bal_0 --manifest "$VMAN" --image-lineage "li:video sha256:0a52afcb (P5 $name, ONE instance, K=$K, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
      else
        P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency "$K" --rr-threads-env "$T" --manifest "$VMAN" --image-lineage "$IMG $(imgid "$IMG" | cut -c1-19) (P5 $name, 1 token, K=$K, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
      fi
      rc=$?
      sess_close "$L"
      touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
      if [ "$fl" = p5 ]; then bash working/scripts/p5_stamp.sh collect "$C" "$L"; else bash working/scripts/p1_stamp.sh "$([ "$fl" = li ] && echo li || echo rr)" collect "$C" "$L"; fi
      docker logs "$C" > "$L/dockerlog_$C.txt" 2>&1
    fi
    tail -3 "$L/driver.log" 2>/dev/null
    docker stop "$C" >/dev/null 2>&1; docker rm "$C" >/dev/null 2>&1
    up "${name}${try}"
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    if [ "$rc" != 0 ]; then
      local nrec
      nrec="$("$PY" -c 'import json,glob,sys; f=sorted(glob.glob(sys.argv[1]+"/records_*.jsonl")); e=glob.glob(sys.argv[1]+"/export_*.json"); print(len({json.loads(x)["video"] for x in open(f[0]) if x.strip() and json.loads(x).get("role")=="measured"}) if f and e else 0)' "$L" 2>/dev/null || echo 0)"
      if [ "$nrec" = "$n" ]; then echo "leg ${name}${try}: driver rc=$rc but all $n videos recorded -> DEGRADED-with-all-rows, KEPT"; rc=0; R+=("${name}${try}:DEGRADED_all_rows"); fi
    fi
    if [ "$rc" = 0 ]; then
      case " ${R[*]} " in *" ${name}${try}:DEGRADED_all_rows "*) ;; *) R+=("${name}${try}:rc=0");; esac
      LAST="${name}${try}"; return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED, chain continues"; return 1
}

after() {  # after <leg> <stock|p5|li> <K> <n>
  local L="$1" fl="$2" K="$3" n="$4" IMG
  IMG=$(imgid "$([ "$fl" = p5 ] && echo rr:p5-infer || ([ "$fl" = li ] && echo li:video || echo rr:patched-video))")
  g d0 "$D" "$L" "$([ "$fl" = li ] && echo li || echo rr)"; local d=$?
  g cell "$D" "$L" "$fl" "$K" "$T" "$n" "$IMG"; local c=$?
  upgates
  [ "$d" = 0 ] || { R+=("G_d0_${L}:FAIL(rc=$d)"); finish "STOPPED: G_d0 failed on $L"; exit 9; }
  [ "$c" = 0 ] || { R+=("G_cell_${L}:FAIL(rc=$c)"); finish "STOPPED: G_cell failed on $L"; exit 11; }
  if [ "$FIRSTDONE" = 0 ]; then
    FIRSTDONE=1
    g memstat "$D" "$L" || { upgates; R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10; }
    upgates
  fi
}
cellrun() { leg "$1" "$2" "$3" 16 && after "$LAST" "$2" "$3" 16; }

# ---------------------------------------------------------------- P5-B: block-interleaved 168 videos
blockman() {  # blockman <b> -> writes $D/p5b_manifests/block_<b>.jsonl (meta + warm rows + block b's measured rows)
  mkdir -p "$D/p5b_manifests"
  "$PY" - "$VMAN" "$1" "$D/p5b_manifests/block_$(printf %02d "$1").jsonl" <<'PYMAN'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
meta = [r for r in rows if "_meta" in r]
warm = [r for r in rows if r.get("role") == "warm"]
meas = [r for r in rows if r.get("role") == "measured"][:168]
b = int(sys.argv[2]); blk = meas[(b - 1) * 16: b * 16]
with open(sys.argv[3], "x") as f:
    for r in meta + warm + blk:
        f.write(json.dumps(r) + "\n")
print(len(blk))
PYMAN
}
cg_usage() { local id; id="$(docker inspect -f '{{.Id}}' "$1" 2>/dev/null)"; awk '/^usage_usec/ {print $2}' "/sys/fs/cgroup/system.slice/docker-$id.scope/cpu.stat" 2>/dev/null || echo NA; }
blockleg() {  # blockleg <name> <rr|li> <n> <manifest> <warm 1|0> <other_container>
  local name="$1" arm="$2" n="$3" man="$4" warm="$5" other="$6" L C rc=0 SPID MPID u0 u1 IMG
  if past; then echo "!! $name NOT RUN: the P5 budget has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1; fi
  L="$D/$name"; [ -e "$L" ] && { echo "REFUSED: $L exists"; LAST=""; return 1; }
  mkdir -p "$L"; C=$([ "$arm" = rr ] && echo rr || echo li_bal_0)
  echo "===== BLOCK $name ($arm n=$n warm=$warm; $other paused) $(date -u +%H:%M:%SZ) ====="
  docker unpause "$C" >/dev/null 2>&1
  if [ "$arm" = li ]; then "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 600 > "$L/wait_ready.txt" 2>&1 || rc=5
  else "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 600 --container rr > "$L/wait_ready.txt" 2>&1 || rc=5; fi
  docker inspect -f '{{.State.Paused}} {{.State.Status}}' "$other" > "$L/other_container_state.txt" 2>&1
  u0="$(cg_usage "$other")"
  docker inspect -f '{{.Image}}' "$C" > "$L/container_image_id.txt"; cp "$man" "$L/block_manifest.jsonl"
  if [ "$rc" = 0 ]; then
    sess_open "$L"
    PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
    SPID=$!
    "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
    MPID=$!
    if [ "$arm" = li ]; then
      "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency 16 --li-ports 8802 --li-containers li_bal_0 --manifest "$man" $([ "$warm" = 0 ] && echo --skip-warmup) --image-lineage "li:video sha256:0a52afcb (P5-B $name, ONE instance, K=16, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
    else
      P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency 16 --rr-threads-env "$T" --manifest "$man" --image-lineage "rr:p5-infer $(imgid rr:p5-infer | cut -c1-19) (P5-B $name, 1 token, K=16, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
    fi
    rc=$?
    sess_close "$L"
    touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
    if [ "$arm" = rr ]; then bash working/scripts/p5_stamp.sh collect rr "$L"; else bash working/scripts/p1_stamp.sh li collect li_bal_0 "$L"; fi
  fi
  u1="$(cg_usage "$other")"
  echo "{\"other\": \"$other\", \"cpu_usage_usec_before\": \"$u0\", \"cpu_usage_usec_after\": \"$u1\"}" > "$L/other_container_cpu.json"
  docker pause "$C" >/dev/null 2>&1
  tail -3 "$L/driver.log" 2>/dev/null
  up "$name"
  if [ -f "$L/MANDATE_VIOLATION.json" ]; then R+=("${name}:MANDATE_VIOLATION"); docker unpause rr li_bal_0 >/dev/null 2>&1; docker rm -f rr li_bal_0 >/dev/null 2>&1; finish "STOPPED: mandate violation in $name"; exit 9; fi
  [ "$rc" = 0 ] && { R+=("${name}:rc=0"); LAST="$name"; return 0; }
  R+=("${name}:rc=$rc"); LAST=""; return 1
}
p5b() {
  local b nb first second ok=1
  echo "===== P5-B: block-interleaved 168 videos $(date -u +%H:%M:%SZ) ====="
  g alone || { R+=("P5B:NOT_ALONE"); return 1; }
  # one container per arm for the whole stage, each stamped and ready, then paused
  docker run -d --name rr --memory 58g $(envargs "$T") --log-opt max-size=200m --network host rr:p5-infer >/dev/null \
    && docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ && bash working/scripts/p5_stamp.sh install rr && docker restart rr >/dev/null \
    && "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || ok=0
  [ "$ok" = 1 ] && docker pause rr >/dev/null
  [ "$ok" = 1 ] && docker run -d --name li_bal_0 --memory 7g $(envargs "$T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null \
    && bash working/scripts/p1_stamp.sh li install li_bal_0 && docker restart li_bal_0 >/dev/null \
    && "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || ok=0
  [ "$ok" = 1 ] && docker pause li_bal_0 >/dev/null
  [ "$ok" = 1 ] || { R+=("P5B:SETUP_FAILED"); docker unpause rr li_bal_0 >/dev/null 2>&1; docker rm -f rr li_bal_0 >/dev/null 2>&1; return 1; }
  canary p5c_can_b0 1
  local liwarm=1
  for b in $(seq 1 11); do
    nb="$(blockman "$b")" || { R+=("P5B:MANIFEST_FAILED_b$b"); break; }
    if [ $((b % 2)) = 1 ]; then first=rr; second=li; else first=li; second=rr; fi
    for arm in $first $second; do
      local nm="p5b_${arm}_b$(printf %02d "$b")" other w=1
      other=$([ "$arm" = rr ] && echo li_bal_0 || echo rr)
      [ "$arm" = li ] && { w=$liwarm; }
      blockleg "$nm" "$arm" "$nb" "$D/p5b_manifests/block_$(printf %02d "$b").jsonl" "$w" "$other"
      if [ -n "$LAST" ]; then
        [ "$arm" = li ] && liwarm=0
        g d0 "$D" "$LAST" "$arm"; local dd=$?
        g cell "$D" "$LAST" "$([ "$arm" = rr ] && echo p5 || echo li)" 16 "$T" "$nb" "$(imgid "$([ "$arm" = rr ] && echo rr:p5-infer || echo li:video)")"; local cc=$?
        upgates
        [ "$dd" = 0 ] || { R+=("G_d0_${LAST}:FAIL"); docker unpause rr li_bal_0 >/dev/null 2>&1; docker rm -f rr li_bal_0 >/dev/null 2>&1; finish "STOPPED: G_d0 failed on $LAST"; exit 9; }
        [ "$cc" = 0 ] || { R+=("G_cell_${LAST}:FAIL"); docker unpause rr li_bal_0 >/dev/null 2>&1; docker rm -f rr li_bal_0 >/dev/null 2>&1; finish "STOPPED: G_cell failed on $LAST"; exit 11; }
      fi
    done
    [ "$b" = 6 ] && canary p5c_can_bmid 1
  done
  for c in rr li_bal_0; do docker unpause "$c" >/dev/null 2>&1; docker logs "$c" > "$D/p5b_dockerlog_$c.txt" 2>&1; docker stop "$c" >/dev/null 2>&1; docker rm "$c" >/dev/null 2>&1; done
  up1 p5b_dockerlog_rr.txt; up1 p5b_dockerlog_li_bal_0.txt
  aws s3 ls "$S3/p5b_manifests/" >/dev/null 2>&1 || aws s3 cp "$D/p5b_manifests" "$S3/p5b_manifests/" --recursive --only-show-errors
}

case "$STAGE" in
  build)
    bash working/scripts/p5_infer_build.sh "$D"; rc=$?
    up1 p5a_build.json
    R+=("build:rc=$rc"); finish "$([ "$rc" = 0 ] && echo 'build complete, G_build_A PASS' || echo "build FAILED rc=$rc")"; exit "$rc"
    ;;
  control)
    leg p5ctl_p5 p5 2 2 || { finish "control leg p5ctl_p5 FAILED"; exit 4; }
    leg p5ctl_stock stock 2 2 || { finish "control leg p5ctl_stock FAILED"; exit 4; }
    leg p5ctl_li li 2 2 || { finish "control leg p5ctl_li FAILED"; exit 4; }
    canary p5ctl_canary || { finish "control canary FAILED"; exit 4; }
    finish "control targets complete (gate-control targets, not measured legs)"
    ;;
  run)
    export P5_DEADLINE_EPOCH="$(( $(date +%s) + 27000 ))"
    echo "first leg starts $(date -u +%H:%M:%SZ); deadline $(date -u -d "@$P5_DEADLINE_EPOCH" +%H:%M:%SZ) (epoch $P5_DEADLINE_EPOCH)"
    for r in 1 2; do
      canary "p5c_can_$r"
      cellrun "p5a_stock16_$r" stock 16
      cellrun "p5a_p5k16_$r" p5 16
      cellrun "p5a_p5k1_$r" p5 1
      if [ "$r" = 1 ]; then
        S16="$(ls -d "$D"/p5a_stock16_1* 2>/dev/null | head -1)"; P16="$(ls -d "$D"/p5a_p5k16_1* 2>/dev/null | head -1)"; P1="$(ls -d "$D"/p5a_p5k1_1* 2>/dev/null | head -1)"
        g correct "$D" G_correct_A1 "$(basename "$P16")" "$(basename "$S16")" "$(basename "$P1")" "$(basename "$S16")" "$(basename "$P1")" "$TREE/working/results/parity_p4_20260925T092942Z/p4a_rr1_1"; cr=$?
        upgates
        [ "$cr" = 0 ] || { R+=("G_correct_A1:FAIL(rc=$cr)"); finish "STOPPED: OUTPUT-CHANGING — rr:p5-infer is not output-identical to stock (P5-A and P5-B stop; no speed reading)"; exit 13; }
        R+=("G_correct_A1:PASS")
      fi
      cellrun "p5a_li16_$r" li 16
    done
    # (the smoke done record lists the legs so the analyser reads the gated attempts)
    "$PY" -c 'import json,sys; json.dump({"legs": sys.argv[2].split()}, open(sys.argv[1], "x"), indent=1)' "$D/chain_p5_smoke_done.json" "${R[*]}"; up1 chain_p5_smoke_done.json
    PAIRS=()
    for r in 1 2; do for c in p5k16 p5k1; do
      a="$(ls -d "$D"/p5a_${c}_$r* 2>/dev/null | head -1)"; s="$(ls -d "$D"/p5a_stock16_$r* 2>/dev/null | head -1)"
      [ -n "$a" ] && [ -n "$s" ] && PAIRS+=("$(basename "$a")" "$(basename "$s")")
    done; done
    [ "${#PAIRS[@]}" -ge 2 ] && { g correct "$D" G_correct_A "${PAIRS[@]}"; R+=("G_correct_A:rc=$?"); }
    g smoke "$D"; sg=$?; upgates
    R+=("G_smoke_P5B:rc=$sg")
    if [ "$sg" = 0 ]; then p5b; else echo "P5-B NOT RUN: G_smoke_P5B did not fire (rc=$sg)"; R+=("P5B:NOT_RUN_gate"); fi
    finish "complete"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
