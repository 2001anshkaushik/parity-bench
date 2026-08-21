#!/usr/bin/env bash
# =============================================================================
# Phase 2 run plan — PARAMETERISED SKELETON. Tomorrow is "fill in six numbers
# and run", not "design the run". Every value the sweep produces is a REQUIRED
# variable below; the script refuses to start with any of them unset, so
# nothing can silently run at a guessed value.
#
#   M_TOKENS       RocketRide parity posture: use() tokens = serving instances
#                  (from probe_concurrency: at the knee, never past it)
#   WARM_N         warm items (>= serving instances; manifest re-cut supplies
#                  the split: measured = 60 - WARM_N)
#   THREADS_ENV    the six BLAS/OMP variables, SAME value both arms
#                  (from the probe's thread matrix)
#   LIVENESS_MIN   gate-5 minimum non-empty-frame fraction (from the probe's
#                  measured Corner-view distribution)
#   GATE3_RUN_ID   the probe run whose ES2002a comparison confirmed strict
#                  cross-arm agreement (arms gate 3; unarmed = NOT RUN)
#   BLAST_C        blast concurrency (wave arithmetic decided WITH the sweep)
#
# Optional (defaults are decisions already made, not guesses):
#   SEQ_N=5        sequential leg size (uncontended latency + determinism +
#                  speedup divisor)
#   PASSES=1       2 = run the measured set twice in the blast legs (the
#                  thin-window alternative — decide from the sweep numbers)
#
# Standing rules enforced by structure: arms run ONE AT A TIME (this script is
# strictly sequential); submission order is manifest-seq on both arms (driver
# behaviour + recorded in every export); page cache evicted per arm (driver);
# quiet-box gate before every leg (driver); ${PIPESTATUS[0]} never $?.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

: "${M_TOKENS:?M_TOKENS unset — from probe_concurrency (the knee)}"
: "${WARM_N:?WARM_N unset — >= serving instances}"
: "${THREADS_ENV:?THREADS_ENV unset — six BLAS vars, same both arms}"
: "${LIVENESS_MIN:?LIVENESS_MIN unset — from probe detections distribution}"
: "${GATE3_RUN_ID:?GATE3_RUN_ID unset — probe run id that confirmed ES2002a agreement}"
: "${BLAST_C:?BLAST_C unset — blast concurrency}"
SEQ_N="${SEQ_N:-5}"
PASSES="${PASSES:-1}"
# DRY_PASS=1: composition proof ONLY — clamps everything to one item, skips the
# PDF fixture and warm-up, writes a THROWAWAY golden. Retires the wiring risk
# in ~minutes; NO number from a dry pass is a measurement.
DRY_PASS="${DRY_PASS:-0}"
RR_IMAGE="${RR_IMAGE:-rr:patched}"
LI_IMAGE="${LI_IMAGE:-li:video}"
OUT="working/video/results/mainrun_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
LOG="$OUT/run_plan.log"

run() {  # log + fail-closed wrapper
  echo "+ $*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  [ "$rc" = "0" ] || { echo "STEP FAILED rc=$rc: $*" | tee -a "$LOG"; exit "$rc"; }
}

thread_env_args() {
  local n="$1"
  echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n -e OPENBLAS_NUM_THREADS=$n \
       -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"
}

start_rr() {
  docker rm -f rr 2>/dev/null || true
  # shellcheck disable=SC2046
  run docker run -d --name rr --memory 58g $(thread_env_args "$THREADS_ENV") \
      --log-opt max-size=200m -p 5565:5565 "$RR_IMAGE"
  for _ in $(seq 1 360); do
    python3 -c "import socket; socket.create_connection(('127.0.0.1',5565),2).close()" 2>/dev/null && return 0
    sleep 5
  done
  echo "rr never listened" | tee -a "$LOG"; exit 1
}

start_li() {
  docker rm -f li_video 2>/dev/null || true
  # shellcheck disable=SC2046
  run docker run -d --name li_video --memory 58g $(thread_env_args "$THREADS_ENV") \
      -e WS1V_WORKERS="$M_TOKENS" --log-opt max-size=200m -p 8802:8802 "$LI_IMAGE"
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:8802/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  echo "li_video never became healthy" | tee -a "$LOG"; exit 1
}

stop_arm() { docker logs "$1" > "$OUT/dockerlog_$1_final.txt" 2>&1 || true; docker rm -f "$1" >/dev/null 2>&1 || true; }

DRIVER=(python3 working/video/driver_video.py
        --liveness-min-fraction "$LIVENESS_MIN"
        --out-dir "$OUT")
MEASURED_N=$((60 - WARM_N))
SMOKE_EXTRA=()
if [ "$DRY_PASS" = "1" ]; then
  echo "=== DRY PASS — wiring only; every knob clamped; nothing here is a measurement ===" | tee -a "$LOG"
  SEQ_N=1; PASSES=1; MEASURED_N=1; BLAST_C=1
  DRIVER+=(--skip-warmup)
  SMOKE_EXTRA=(--skip-fixture --write-golden --golden "$OUT/dry_golden.json")
fi

echo "=== RUN PLAN: M=$M_TOKENS warm=$WARM_N threads=$THREADS_ENV liveness>=$LIVENESS_MIN \
gate3=$GATE3_RUN_ID C=$BLAST_C seq_n=$SEQ_N passes=$PASSES -> $OUT ===" | tee -a "$LOG"

echo "--- 0. manifest re-cut check (re-cut is a REUSE: fetched must be 0) ---" | tee -a "$LOG"
run python3 working/video/fetch_ami_video.py --verify

echo "--- 1. LlamaIndex arm (both containers up for smoke read-backs; RR idles) ---" | tee -a "$LOG"
start_rr
start_li
run python3 working/video/smoke_video.py --rr-container rr --li-container li_video "${SMOKE_EXTRA[@]}"
run "${DRIVER[@]}" --arm llamaindex --leg sequential --n "$SEQ_N"
for pass in $(seq 1 "$PASSES"); do
  echo "--- LI blast pass $pass/$PASSES ---" | tee -a "$LOG"
  run "${DRIVER[@]}" --arm llamaindex --leg blast --n "$MEASURED_N" --blast-concurrency "$BLAST_C"
done
stop_arm li_video

echo "--- 2. RocketRide DEFAULT posture (1 token, threads unset = engine 64) ---" | tee -a "$LOG"
# The full smoke ran once in step 1 with BOTH containers live; per-leg
# re-verification (flags, pins, identity, quiet box) is the driver's own
# fail-closed preflight — no || true anywhere in this file.
run "${DRIVER[@]}" --arm rocketride --posture default --leg sequential --n "$SEQ_N"
for pass in $(seq 1 "$PASSES"); do
  run "${DRIVER[@]}" --arm rocketride --posture default --leg blast --n "$MEASURED_N" \
      --blast-concurrency "$BLAST_C"
done

echo "--- 3. RocketRide PARITY posture (M=$M_TOKENS tokens) ---" | tee -a "$LOG"
run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n "$SEQ_N" --tokens "$M_TOKENS"
for pass in $(seq 1 "$PASSES"); do
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n "$MEASURED_N" \
      --blast-concurrency "$BLAST_C" --tokens "$M_TOKENS"
done
stop_arm rr

echo "--- 4. cross-arm gates (gate 3 armed by $GATE3_RUN_ID, then char conservation) ---" | tee -a "$LOG"
for leg in sequential blast; do
  for posture in default parity; do
    RRJ="$OUT/records_rocketride_video_${posture}_${leg}.jsonl"
    LIJ="$OUT/records_llamaindex_video_workers_${leg}.jsonl"
    if [ -f "$RRJ" ] && [ -f "$LIJ" ]; then
      echo "cross: $posture/$leg" | tee -a "$LOG"
      python3 working/video/driver_video.py --cross "$RRJ" "$LIJ" \
        --gate3-armed "$GATE3_RUN_ID" > "$OUT/cross_${posture}_${leg}.json" 2>>"$LOG"
      rc=$?
      cat "$OUT/cross_${posture}_${leg}.json" >> "$LOG"
      [ "$rc" = "0" ] || echo "CROSS GATES FAILED: $posture/$leg (rc=$rc)" | tee -a "$LOG"
    fi
  done
done

echo "=== RUN PLAN COMPLETE — everything under $OUT ===" | tee -a "$LOG"
