#!/usr/bin/env bash
# p4_video_chain.sh — P4-A video concurrency (preregistration.json P4_A_video_concurrency), on the box, one workload at a
# time, a fresh container per leg, every leg ALONE. Leg mechanics are P2-B's (p2_video_chain.sh): the P1 stamped detect
# copies on both arms, the percore sampler and the 1 Hz memory sampler per leg, session facts, append-only S3 uploads.
#
#   bash working/scripts/p4_video_chain.sh <campaign_dir_abs> <expect_head> control
#       the gate-control target p4ctl_active: RR, OMP_WAIT_POLICY=ACTIVE, T=4, K=2, 2 videos, stamped, P0_ONTOKEN.
#       Not a measured leg. p4_gate_controls.py runs after it.
#   bash working/scripts/p4_video_chain.sh <campaign_dir_abs> <expect_head> run
#       refuses unless the highest-numbered gate_controls record says all_pass. 16 videos, T=4, ABAB two runs each:
#       p4a_rr16_1 p4a_li16_1 p4a_rr1_1 p4a_li1_1 p4a_act_1 p4a_rr16_2 p4a_li16_2 p4a_rr1_2 p4a_li1_2 p4a_act_2
#       after EVERY leg: G_d0 (exit 9), G_cell (exit 11); after the FIRST leg: G_memstat (exit 10).
#       Budget: P4_DEADLINE_EPOCH = the first leg's start + 18,000 s; a leg not started by then is NOT RUN.
#       At the end: G_correct_active (recorded, not a stop), protected image ids, chain_p4a_done.json.
set -uo pipefail
echo "p4_video_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head> control|run" >&2; exit 2; }
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
S3="s3://rocketride-benchmark-data/ansh/parity-p4/$REL"
T=4
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  manifest $(sha256sum "$VMAN" | cut -c1-16)"
for img in rr:patched rr:patched-video li:video; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
R=(); LAST=""; FIRSTDONE=0
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
up() { local dest="$S3/$1/"; aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists — not uploading over it"; return 1; }; aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"; }
up1() { aws s3 ls "$S3/$1" >/dev/null 2>&1 || aws s3 cp "$D/$1" "$S3/$1" --only-show-errors; }
upgates() { for f in "$D"/gates/*.json; do [ -f "$f" ] && up1 "gates/$(basename "$f")"; done; }
past() { [ -n "${P4_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P4_DEADLINE_EPOCH" ]; }
g() { "$PY" working/scripts/p4_gates.py "$@"; }
if [ "$STAGE" = run ]; then   # the GATE CONTROLS rule: checked before anything is recorded
  CTL="$(ls "$D"/gate_controls.json "$D"/gate_controls_run*.json 2>/dev/null | sort -V | tail -1)"
  [ -n "$CTL" ] || { echo "REFUSED: no gate_controls record in $D (the GATE CONTROLS rule)"; exit 12; }
  "$PY" -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("all_pass") is True else 1)' "$CTL" || { echo "REFUSED: $CTL does not say all_pass"; exit 12; }
  echo "gate controls: $(basename "$CTL") all_pass"
fi
"$PY" - "$D/chain_p4a_${STAGE}_start.json" "$HAVE" <<'PYSTART' || { echo "REFUSED: chain_p4a_${STAGE}_start.json exists (one run per stage)"; exit 3; }
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video")}
json.dump({"stage_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "head": sys.argv[2],
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(), "image_ids_at_start": ids},
          open(sys.argv[1], "x"), indent=1)
PYSTART
up1 "chain_p4a_${STAGE}_start.json"

finish() {
  for img in rr:patched rr:patched-video li:video; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
  "$PY" - "$D/chain_p4a_${STAGE}_done.json" "$1" "${R[*]}" "${P4_DEADLINE_EPOCH:-}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "deadline_epoch": sys.argv[4] or None,
           "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  up1 "chain_p4a_${STAGE}_done.json"; upgates
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE p4a $STAGE $1"
}

# leg <name> <arm rr|li> <K> <n> <ACTIVE|unset>
leg() {
  local name="$1" arm="$2" K="$3" n="$4" omp="$5" try L rc C SPID MPID WP="" nrec
  LAST=""
  if past; then echo "!! $name NOT RUN: the P4 5-hour budget (preregistration.json budget) has passed"; R+=("${name}:NOT_RUN_budget"); return 1; fi
  [ "$omp" = ACTIVE ] && WP="-e OMP_WAIT_POLICY=ACTIVE"
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"
    [ -e "$L" ] && { echo "REFUSED: $L exists (append-only)"; continue; }
    g alone || { R+=("${name}${try}:NOT_ALONE"); docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'; return 1; }
    mkdir -p "$L"; rc=0
    echo "===== LEG ${name}${try} ($arm K=$K n=$n T=$T OMP_WAIT_POLICY=$omp) $(date -u +%H:%M:%SZ) ====="
    if [ "$arm" = rr ]; then
      C=rr
      docker run -d --name rr --memory 58g $(envargs "$T") $WP --log-opt max-size=200m --network host rr:patched-video >/dev/null || rc=4
      [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
      [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh rr install rr || rc=6; }
      [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
    else
      C=li_bal_0
      docker run -d --name li_bal_0 --memory 7g $(envargs "$T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null || rc=4
      [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh li install li_bal_0 || rc=6; }
      [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
    fi
    if [ "$rc" = 0 ]; then
      cat /proc/stat | head -1 > "$L/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$L/boot_id.txt"
      grep -m1 "model name" /proc/cpuinfo > "$L/cpu_model.txt"; grep MHz /proc/cpuinfo > "$L/mhz_open.txt"
      PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
      SPID=$!
      "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
      MPID=$!
      unset P1_SYNC_DIR
      if [ "$arm" = rr ]; then
        P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency "$K" --rr-threads-env "$T" --manifest "$VMAN" --image-lineage "rr:patched-video sha256:b7f51acc (P4 $name, 1 token, K=$K, six vars=$T, OMP_WAIT_POLICY=$omp)" --out-dir "$L" > "$L/driver.log" 2>&1
      else
        "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency "$K" --li-ports 8802 --li-containers li_bal_0 --manifest "$VMAN" --image-lineage "li:video sha256:0a52afcb (P4 $name, ONE instance, K=$K, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
      fi
      rc=$?
      cat /proc/stat | head -1 > "$L/procstat_close.txt"; grep MHz /proc/cpuinfo > "$L/mhz_close.txt"
      touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
      bash working/scripts/p1_stamp.sh "$arm" collect "$C" "$L"
      docker logs "$C" > "$L/dockerlog_$C.txt" 2>&1
      [ "$arm" = rr ] && docker image inspect -f '{{.Id}}' rr:patched-video > "$L/engine_image_id.txt" 2>/dev/null
    fi
    tail -3 "$L/driver.log" 2>/dev/null
    docker stop "$C" >/dev/null 2>&1; docker rm "$C" >/dev/null 2>&1
    up "${name}${try}"
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    if [ "$rc" != 0 ]; then
      # DEGRADED-with-all-rows: the driver exited non-zero but its records hold a measured row for every video -> KEPT
      nrec="$("$PY" -c 'import json,glob,sys; f=sorted(glob.glob(sys.argv[1]+"/records_*.jsonl")); e=glob.glob(sys.argv[1]+"/export_*.json"); print(len({json.loads(x)["video"] for x in open(f[0]) if x.strip() and json.loads(x).get("role")=="measured"}) if f and e else 0)' "$L" 2>/dev/null || echo 0)"
      if [ "$nrec" = "$n" ]; then echo "leg ${name}${try}: driver rc=$rc but all $n videos recorded -> DEGRADED-with-all-rows, KEPT"; rc=0; R+=("${name}${try}:DEGRADED_all_rows"); fi
    fi
    if [ "$rc" = 0 ]; then
      case " ${R[*]} " in *" ${name}${try}:DEGRADED_all_rows "*) ;; *) R+=("${name}${try}:rc=0");; esac
      LAST="${name}${try}"
      return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED, chain continues"; return 1
}

# after-leg gates: <leg> <arm> <K> <n> <omp>
after() {
  local L="$1" arm="$2" K="$3" n="$4" omp="$5"
  g d0 "$D" "$L" "$arm"; local d=$?
  g cell "$D" "$L" "$arm" "$K" "$T" "$omp" "$n"; local c=$?
  upgates
  [ "$d" = 0 ] || { R+=("G_d0_${L}:FAIL(rc=$d)"); finish "STOPPED: G_d0 failed on $L"; exit 9; }
  [ "$c" = 0 ] || { R+=("G_cell_${L}:FAIL(rc=$c)"); finish "STOPPED: G_cell failed on $L (the harness is not measuring the cell it names)"; exit 11; }
  if [ "$FIRSTDONE" = 0 ]; then
    FIRSTDONE=1
    g memstat "$D" "$L" || { upgates; R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10; }
    upgates
  fi
}
ACT_OK=(); RR16_OK=()
cellrun() {  # cellrun <name> <arm> <K> <omp> ; the gated leg (first attempt that returned a result) joins its cell's list
  leg "$1" "$2" "$3" 16 "$4" || return 1
  after "$LAST" "$2" "$3" 16 "$4"
  case "$1" in p4a_act_*) ACT_OK+=("$LAST");; p4a_rr16_*) RR16_OK+=("$LAST");; esac
}

case "$STAGE" in
  control)
    leg p4ctl_active rr 2 2 ACTIVE || { finish "control leg FAILED"; exit 4; }
    finish "control leg complete (a gate-control target, not a measured leg)"
    ;;
  run)
    export P4_DEADLINE_EPOCH="$(( $(date +%s) + 18000 ))"
    echo "first leg starts $(date -u +%H:%M:%SZ); deadline $(date -u -d "@$P4_DEADLINE_EPOCH" +%H:%M:%SZ) (epoch $P4_DEADLINE_EPOCH)"
    for r in 1 2; do
      cellrun "p4a_rr16_$r" rr 16 unset
      cellrun "p4a_li16_$r" li 16 unset
      cellrun "p4a_rr1_$r"  rr 1  unset
      cellrun "p4a_li1_$r"  li 1  unset
      cellrun "p4a_act_$r"  rr 16 ACTIVE
    done
    # the correctness gate: every available (ACTIVE, RR K=16) pair; recorded, not a stop
    PAIRS=()
    for a in "${ACT_OK[@]:-}"; do for b in "${RR16_OK[@]:-}"; do [ -n "$a" ] && [ -n "$b" ] && PAIRS+=("$a" "$b"); done; done
    if [ "${#PAIRS[@]}" -ge 2 ]; then g correct "$D" G_correct_active "${PAIRS[@]}"; R+=("G_correct_active:rc=$?"); else R+=("G_correct_active:NOT_EVALUABLE"); fi
    upgates
    finish "complete"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
