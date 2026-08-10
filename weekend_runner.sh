#!/usr/bin/env bash
# =====================================================================================
# WEEKEND RUNNER — unattended, deadline-driven, resumable. No agent alive during execution.
#
# Every phase has a HARD wall-clock cap. On expiry the worker checkpoints and the runner
# ADVANCES; a phase that runs long can never eat the phases behind it.
#
# BOTH ARMS RUN NATIVELY, and that is a deliberate deviation from DOCKER_ARCHITECTURE.md.
# server-v3.3.1 ships darwin-arm64, linux-x64 and win64 — there is NO linux-arm64 build, and
# the repo's own Docker workflow targets linux/amd64 only. Containerising RocketRide on this
# arm64 host would require x86 emulation, which the architecture doc forbids precisely because
# emulation would silently corrupt every number. Running one arm containerised and one native
# would be asymmetric, which is worse than neither. So: both native, symmetric, no emulation.
# The LlamaIndex container demo is a separate, already-delivered artifact.
#
# Consequence to disclose with any result: there is no cgroup enforcing the memory ceiling.
# The worker enforces a SOFT ceiling and records a breach as a result. A soft ceiling detects
# the breach; it does not prove the process would have died at that point under a hard limit.
# =====================================================================================
set -uo pipefail          # NOT -e: a failing phase must advance, not abort the weekend

cd "$(dirname "$0")" || exit 1
ROOT="$PWD"
PY="$ROOT/../.venv/bin/python"
LOG_DIR="$ROOT/weekend_logs"; mkdir -p "$LOG_DIR"
STATE="$ROOT/weekend_state"; mkdir -p "$STATE"
STATUS="$ROOT/status.txt"
CORPUS="$ROOT/corpus/govdocs1/pdfs"
LIMIT_MB="${LIMIT_MB:-12000}"
PHASE_LOG="$LOG_DIR/runner.log"

# caps in seconds; overridable for the dry run
CAP_P0="${CAP_P0:-5400}"     # 90 min  insurance: 200 docs, both arms
CAP_P1="${CAP_P1:-21600}"    #  6 h    corpus top-up
CAP_P2="${CAP_P2:-57600}"    # 16 h    LlamaIndex, full corpus
CAP_P3="${CAP_P3:-57600}"    # 16 h    RocketRide, full corpus (SEQUENTIAL, never with P2)
CAP_P4="${CAP_P4:-3600}"     # 60 min  simultaneous both-arms envelope proof
N_P0="${N_P0:-200}"
N_FULL="${N_FULL:-10000}"

say() { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*" | tee -a "$PHASE_LOG"; }

hb() {  # heartbeat while the runner itself is between phases
  echo "phase=$1 arm=- doc=- elapsed=- rss=- pid=$$ updated=$(date '+%Y-%m-%dT%H:%M:%S') $2" \
    > "$STATUS"
}

phase_done() { [ -f "$STATE/$1.done" ]; }
mark_done()  { touch "$STATE/$1.done"; }

engine_up() { curl -s --max-time 5 http://127.0.0.1:5565/version >/dev/null 2>&1; }

start_engine() {
  # ~60 s cold start. This MUST be outside any measured region.
  if engine_up; then say "engine already up"; return 0; fi
  say "starting engine (cold start ~60s, outside every measured region)"
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 TORCH_NUM_THREADS=1 CPU_PROBE_ITERS=235000 \
    bash "$ROOT/working/scripts/start_engine.sh" >> "$LOG_DIR/engine.log" 2>&1
  for _ in $(seq 1 60); do
    if engine_up; then say "engine READY"; return 0; fi
    sleep 5
  done
  say "ENGINE FAILED TO BECOME READY"; return 1
}

run_phase() {   # name arm cap target
  local name="$1" arm="$2" cap="$3" target="$4"
  if phase_done "$name"; then say "SKIP $name (already done)"; return 0; fi
  say "PHASE $name arm=$arm cap=${cap}s target=$target limit=${LIMIT_MB}MB"
  hb "$name" "starting"
  # log to a FILE, never a pipe: the descending-order run's data is gone forever because its
  # stdout went to grep.
  "$PY" "$ROOT/weekend_worker.py" --phase "$name" --arm "$arm" --cap-seconds "$cap" \
        --limit-mb "$LIMIT_MB" --target "$target" --corpus "$CORPUS" \
        >> "$LOG_DIR/${name}_${arm}.log" 2>&1
  local rc=$?
  case $rc in
    0)  say "PHASE $name/$arm COMPLETED";        mark_done "$name" ;;
    10) say "PHASE $name/$arm CAP REACHED — checkpointed, advancing" ;;
    11) say "PHASE $name/$arm MEMORY LIMIT EXCEEDED — curve recorded, advancing" ; mark_done "$name" ;;
    *)  say "PHASE $name/$arm FAILED rc=$rc — advancing (see ${name}_${arm}.log)" ;;
  esac
  return 0
}

say "================ WEEKEND RUN START pid=$$ ================"
say "corpus=$(ls "$CORPUS" 2>/dev/null | wc -l | tr -d ' ') distinct PDFs; free disk: $(df -h "$ROOT" | tail -1 | awk '{print $4}')"
say "caps: P0=${CAP_P0}s P1=${CAP_P1}s P2=${CAP_P2}s P3=${CAP_P3}s P4=${CAP_P4}s"

# ---- PHASE 0 — insurance deliverable: both arms, small, fast ----------------------
run_phase p0_insurance llamaindex "$CAP_P0" "$N_P0"
start_engine && run_phase p0_insurance_rr rocketride "$CAP_P0" "$N_P0"

# ---- PHASE 1 — corpus top-up (skips instantly if already at target) ---------------
if ! phase_done p1_fetch; then
  have=$(ls "$CORPUS" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$have" -ge "$N_FULL" ]; then
    say "PHASE p1_fetch SKIPPED — corpus already has $have >= $N_FULL"; mark_done p1_fetch
  else
    say "PHASE p1_fetch: $have -> $N_FULL, cap ${CAP_P1}s, stop if free disk < 10GB"
    hb p1_fetch "fetching"
    ( "$PY" "$ROOT/working/scripts/fetch_govdocs.py" "$N_FULL" 10 >> "$LOG_DIR/fetch.log" 2>&1 ) &
    fpid=$!
    fstart=$(date +%s)
    while kill -0 $fpid 2>/dev/null; do
      free_gb=$(df -g "$ROOT" | tail -1 | awk '{print $4}')
      if [ "${free_gb:-999}" -lt 10 ]; then say "FREE DISK < 10GB — stopping fetch"; kill $fpid; break; fi
      [ $(( $(date +%s) - fstart )) -ge "$CAP_P1" ] && { say "fetch cap reached"; kill $fpid; break; }
      hb p1_fetch "pdfs=$(ls "$CORPUS" | wc -l | tr -d ' ') free=${free_gb}GB"
      sleep 60
    done
    mark_done p1_fetch
  fi
fi

# ---- PHASE 2 — LlamaIndex, full corpus -------------------------------------------
run_phase p2_llamaindex llamaindex "$CAP_P2" "$N_FULL"

# ---- PHASE 3 — RocketRide, full corpus. SEQUENTIAL: never concurrent with phase 2 --
start_engine && run_phase p3_rocketride rocketride "$CAP_P3" "$N_FULL"

# ---- PHASE 4 — simultaneous both arms: the shared-envelope proof -------------------
if ! phase_done p4_simultaneous; then
  say "PHASE p4_simultaneous cap=${CAP_P4}s — BOTH arms at once (throughput here is void)"
  hb p4_simultaneous "both arms"
  start_engine
  "$PY" "$ROOT/weekend_worker.py" --phase p4_sim --arm llamaindex --cap-seconds "$CAP_P4" \
      --limit-mb "$LIMIT_MB" --target "$N_FULL" --corpus "$CORPUS" \
      >> "$LOG_DIR/p4_llamaindex.log" 2>&1 &
  a=$!
  "$PY" "$ROOT/weekend_worker.py" --phase p4_sim --arm rocketride --cap-seconds "$CAP_P4" \
      --limit-mb "$LIMIT_MB" --target "$N_FULL" --corpus "$CORPUS" \
      >> "$LOG_DIR/p4_rocketride.log" 2>&1 &
  b=$!
  wait $a; wait $b
  say "PHASE p4_simultaneous done"; mark_done p4_simultaneous
fi

# ---- PHASE 5 — rolling summary from every checkpoint ------------------------------
say "PHASE p5_summary"
"$PY" "$ROOT/weekend_summarise.py" >> "$LOG_DIR/summary.log" 2>&1
say "summary written to publishable/WEEKEND_RESULTS.md"

hb finished "all phases complete"
say "================ WEEKEND RUN COMPLETE ================"
