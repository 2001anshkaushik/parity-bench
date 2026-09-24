#!/usr/bin/env bash
# p2_video_chain.sh — P2-B video legs (preregistration.json P2_B), on the box, one workload at a time, a fresh
# container lifetime per leg. Derived from p1_video_chain.sh (same leg mechanics, stamps, samplers, uploads).
#
#   bash working/scripts/p2_video_chain.sh <campaign_dir_abs> <expect_head> b
#
#   b   16 videos, K=16, T=4, the P1 stamped detect copies on every leg, NO tracer, ABAB two runs each:
#       p2b_rr_base_a p2b_rr_comb_a p2b_li_a p2b_rr_base_b p2b_rr_comb_b p2b_li_b
#       rr_base = rr:patched-video, one token (exactly P1-A's untraced RocketRide leg)
#       rr_comb = the same + noDebug on the execute call (driver P2_NODEBUG=1, the H7 method) AND
#                 MALLOC_ARENA_MAX=2 in the container's environment
#       li      = li:video, ONE instance, one worker
#   G_manip_B after the first base and the first COMBINED leg (p2_gates.py manip_b): a failure stops P2-B (exit 11).
#   G_memstat after the first leg (exit 10).
#
# Single instance on BOTH arms (the mandate). Every leg: steal (/proc/stat open/close), CPU model, MHz, boot id,
# the percore sampler and the 1 Hz memory sampler on the service container, both started after the leg dir exists.
set -uo pipefail
echo "p2_video_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head> b" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
TREE="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$TREE" || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; WANT="$(echo "$H" | cut -c1-12)"
[ "$HAVE" = "$WANT" ] || { echo "REFUSED: worktree at $HAVE, caller expects $WANT" >&2; exit 2; }
PY="$HOME/.venv/bin/python"
VMAN="${P0_VIDEO_MANIFEST:-$HOME/parity-bench-video/working/video/ami_video_manifest.jsonl}"
[ -f "$VMAN" ] || { echo "REFUSED: AMI manifest $VMAN absent" >&2; exit 2; }
S3="s3://rocketride-benchmark-data/ansh/parity-p2/$REL"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  manifest $(sha256sum "$VMAN" | cut -c1-16)"
for img in rr:patched rr:patched-video; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
R=()
ours=()
cleanup() { for c in "${ours[@]:-}"; do [ -n "$c" ] && { docker stop "$c" >/dev/null 2>&1; docker rm "$c" >/dev/null 2>&1; }; done; ours=(); }
trap cleanup EXIT
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
refuse_existing() { for c in "$@"; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' exists — not ours" >&2; return 1; }; done; return 0; }

# leg <name> <arm rr|li> <T> <n> <stamped 0|1> <traced 0|1> [comb 0|1]
leg() {
  local name="$1" arm="$2" T="$3" n="$4" stamped="$5" traced="$6" comb="${7:-0}" try L rc C TPID MA=""
  LAST=""
  [ "$comb" = 1 ] && MA="-e MALLOC_ARENA_MAX=2"
  if [ -n "${P2_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P2_DEADLINE_EPOCH" ]; then
    echo "!! $name NOT RUN: the P2 8-hour budget (preregistration.json budget_and_order) has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1
  fi
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"
    [ -e "$L" ] && { echo "REFUSED: $L exists (append-only)"; continue; }
    mkdir -p "$L"
    echo "===== LEG ${name}${try} ($arm T=$T n=$n stamped=$stamped traced=$traced comb=$comb) $(date -u +%H:%M:%SZ) ====="
    rc=0
    if [ "$arm" = "rr" ]; then
      C=rr; refuse_existing rr || return 1
      ours+=("$(docker run -d --name rr --memory 58g $(envargs "$T") $MA --log-opt max-size=200m --network host rr:patched-video)") || rc=4
      [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
      [ "$rc" = 0 ] && [ "$stamped" = 1 ] && { bash working/scripts/p1_stamp.sh rr install rr || rc=6; }
      [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
    else
      C=li_bal_0; refuse_existing li_bal_0 || return 1
      ours+=("$(docker run -d --name li_bal_0 --memory 7g $(envargs "$T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30")") || rc=4
      if [ "$rc" = 0 ] && [ "$stamped" = 1 ]; then
        bash working/scripts/p1_stamp.sh li install li_bal_0 || rc=6
        [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
      fi
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
    fi
    if [ "$rc" = 0 ]; then
      PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
      local SPID=$!
      "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
      local MPID=$!
      cat /proc/stat | head -1 > "$L/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$L/boot_id.txt"
      grep -m1 "model name" /proc/cpuinfo > "$L/cpu_model.txt"; grep MHz /proc/cpuinfo > "$L/mhz_open.txt"
      TPID=""
      if [ "$traced" = 1 ]; then
        "$PY" working/harness/p1_tracer.py --arm "$arm" --container "$C" --leg-dir "$L" --leg "$name" > "$L/tracer_stdout.txt" 2>&1 &
        TPID=$!
        export P1_SYNC_DIR="$L"
      else
        unset P1_SYNC_DIR
      fi
      if [ "$arm" = "rr" ]; then
        P2_NODEBUG="$comb" P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency 16 --rr-threads-env "$T" --manifest "$VMAN" --image-lineage "rr:patched-video sha256:b7f51acc (P2 $name, 1 token, six vars=$T, $([ "$comb" = 1 ] && echo 'COMBINED noDebug + MALLOC_ARENA_MAX=2' || echo baseline))" --out-dir "$L" > "$L/driver.log" 2>&1
      else
        "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency 16 --li-ports 8802 --li-containers li_bal_0 --manifest "$VMAN" --image-lineage "li:video sha256:0a52afcb (P2 $name, ONE instance, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
      fi
      rc=$?
      unset P1_SYNC_DIR
      cat /proc/stat | head -1 > "$L/procstat_close.txt"; grep MHz /proc/cpuinfo > "$L/mhz_close.txt"
      [ -n "$TPID" ] && { [ -f "$L/.window_closed" ] || echo "driver ended without closing the window" > "$L/.window_closed"; wait "$TPID"; echo "tracer rc=$?"; }
      touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
      [ "$stamped" = 1 ] && bash working/scripts/p1_stamp.sh "$arm" collect "$C" "$L"
      for c in "${ours[@]:-}"; do [ -n "$c" ] && docker logs "$c" > "$L/dockerlog_${c:0:12}.txt" 2>&1; done
      [ "$arm" = "rr" ] && docker image inspect -f '{{.Id}}' rr:patched-video > "$L/engine_image_id.txt" 2>/dev/null
    fi
    tail -3 "$L/driver.log" 2>/dev/null
    cleanup
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then
      R+=("${name}${try}:MANDATE_VIOLATION"); upload "${name}${try}"; finish "STOPPED: mandate violation in ${name}${try}"; exit 9
    fi
    upload "${name}${try}"
    [ "$rc" -eq 0 ] && { R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0; }
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED, chain continues"; return 1
}

upload() {
  local dest="$S3/$1/"
  if aws s3 ls "$dest" >/dev/null 2>&1; then echo "!! $dest exists — not uploading over it"; return 1; fi
  aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"
}

finish() {
  for img in rr:patched rr:patched-video; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
  "$PY" - "$D/chain_video_${STAGE}_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "protected_image_ids_at_end": ids},
          open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_video_${STAGE}_done.json" "$S3/chain_video_${STAGE}_done.json" --only-show-errors
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE $1"
}

for c in rr li li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' present — one workload at a time" >&2; exit 3; }; done
gate() {  # gate <p2_gates args...> ; records and uploads gates/<name>.json
  "$PY" working/scripts/p2_gates.py "$@"; local g=$?
  for f in "$D"/gates/*.json; do [ -f "$f" ] && ! aws s3 ls "$S3/gates/$(basename "$f")" >/dev/null 2>&1 && aws s3 cp "$f" "$S3/gates/$(basename "$f")" --only-show-errors; done
  return $g
}
case "$STAGE" in
  b)
    leg p2b_rr_base_a rr 4 16 1 0 0
    FIRST="$LAST"
    if [ -z "$FIRST" ] || ! gate memstat "$D" "$FIRST"; then R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first video leg's memory sampler wrote nothing)"; exit 10; fi
    gate manip_b "$D" "$FIRST" base || { R+=("G_manip_B:FAIL(base)"); finish "STOPPED: G_manip_B (baseline read-back is not the cell described)"; exit 11; }
    leg p2b_rr_comb_a rr 4 16 1 0 1
    if [ -z "$LAST" ] || ! gate manip_b "$D" "$LAST" comb; then R+=("G_manip_B:FAIL(comb)"); finish "STOPPED: G_manip_B (COMBINED read-back is not the cell described)"; exit 11; fi
    leg p2b_li_a li 4 16 1 0
    leg p2b_rr_base_b rr 4 16 1 0 0
    leg p2b_rr_comb_b rr 4 16 1 0 1
    leg p2b_li_b li 4 16 1 0
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
