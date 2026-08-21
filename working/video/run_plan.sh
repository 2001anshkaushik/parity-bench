#!/usr/bin/env bash
# =============================================================================
# Phase 2 run plan — PARAMETERISED SKELETON. Tomorrow is "fill in eight numbers
# and run", not "design the run". Every value the sweep produces is a REQUIRED
# variable below; the script refuses to start with any of them unset, so
# nothing can silently run at a guessed value.
#
#   M_TOKENS       RocketRide parity posture: use() tokens = serving instances
#                  (from probe_concurrency: at the knee, never past it)
#   LI_WORKERS     LlamaIndex uvicorn workers — its own evidence-derived optimum
#                  (Crossroad 17: leaving the default 1 is a real handicap)
#   WARM_N         warm items (>= max(M_TOKENS, LI_WORKERS); manifest re-cut
#                  supplies the split: measured = 60 - WARM_N)
#   RR_THREADS_ENV six BLAS/OMP vars on the RR container — RR's own optimum
#   LI_THREADS_ENV six BLAS/OMP vars on the LI container — LI's own optimum
#                  (Crossroad 17: same sweep matrix both arms, per-arm optimum;
#                  values published beside the full matrix; declared==measured
#                  enforced per arm; cross-arm difference recorded, never failed)
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
# Interpreter contract: driver/smoke import harness (psutil) + rocketride — the
# Phase 1 venv. Probe tooling uses the floor venv. Both overridable.
PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing (Phase 1 venv with psutil+rocketride)"; exit 1; }

cd "$(dirname "$0")/../.."   # repo root

: "${M_TOKENS:?M_TOKENS unset — from probe_concurrency (the knee)}"
: "${LI_WORKERS:?LI_WORKERS unset — the LI-arm optimum (default 1 is a handicap)}"
: "${WARM_N:?WARM_N unset — >= max(M_TOKENS, LI_WORKERS)}"
: "${RR_THREADS_ENV:?RR_THREADS_ENV unset — the RR-arm optimum from the matrix}"
: "${LI_THREADS_ENV:?LI_THREADS_ENV unset — the LI-arm optimum from the matrix}"
if [ "$WARM_N" -lt "$M_TOKENS" ] || [ "$WARM_N" -lt "$LI_WORKERS" ]; then
  echo "NOT DONE — WARM_N=$WARM_N < max(M_TOKENS=$M_TOKENS, LI_WORKERS=$LI_WORKERS): every serving instance must see a warm item"; exit 1
fi
: "${LIVENESS_MIN:?LIVENESS_MIN unset — from probe detections distribution}"
: "${GATE3_RUN_ID:?GATE3_RUN_ID unset — probe run id that confirmed ES2002a agreement}"
: "${BLAST_C:?BLAST_C unset — blast concurrency}"
SEQ_N="${SEQ_N:-5}"
PASSES="${PASSES:-1}"
# DRY_PASS=1: composition proof ONLY — clamps everything to one item, skips the
# PDF fixture and warm-up, writes a THROWAWAY golden. Retires the wiring risk
# in ~minutes; NO number from a dry pass is a measurement.
DRY_PASS="${DRY_PASS:-0}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"   # Crossroad 18: baked image (bake_rr_video.sh)
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
  run docker run -d --name rr --memory 58g $(thread_env_args "$RR_THREADS_ENV") \
      --log-opt max-size=200m -p 5565:5565 "$RR_IMAGE"
  for _ in $(seq 1 360); do
    "$PY" -c "import socket; socket.create_connection(('127.0.0.1',5565),2).close()" 2>/dev/null && return 0
    sleep 5
  done
  echo "rr never listened" | tee -a "$LOG"; exit 1
}

start_li() {
  docker rm -f li_video 2>/dev/null || true
  # shellcheck disable=SC2046
  run docker run -d --name li_video --memory 58g $(thread_env_args "$LI_THREADS_ENV") \
      -e WS1V_WORKERS="$LI_WORKERS" --log-opt max-size=200m -p 8802:8802 "$LI_IMAGE"
  for _ in $(seq 1 120); do
    if curl -sf "http://127.0.0.1:8802/health" >/dev/null 2>&1; then
      # D7 read-back (2026-08-22): the LI image's serving stack is UNPINNED at
      # build (fastapi/uvicorn/llama-index float) — snapshot the resolved
      # versions per run so the measured latency's substrate is on record.
      # Dockerfile pinning is a flagged follow-up ruling, not done here.
      docker exec li_video python -m pip freeze > "$OUT/li_image_freeze.txt" 2>>"$LOG" \
        || echo "li_image_freeze snapshot FAILED (recorded)" | tee -a "$LOG"
      return 0
    fi
    sleep 5
  done
  echo "li_video never became healthy" | tee -a "$LOG"; exit 1
}

stop_arm() { docker logs "$1" > "$OUT/dockerlog_$1_final.txt" 2>&1 || true; docker rm -f "$1" >/dev/null 2>&1 || true; }

DRIVER=("$PY" working/video/driver_video.py
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

# Run-level manifest: all eight numbers + context in ONE machine-readable
# artifact, not only interleaved in run_plan.log. Written before anything
# runs; completion status flipped at the end.
cat > "$OUT/run_manifest.json" <<MANIFEST
{
 "run_dir": "$OUT",
 "started_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "git_sha": "$(git rev-parse HEAD 2>/dev/null || echo unknown)",
 "dry_pass": $([ "$DRY_PASS" = "1" ] && echo true || echo false),
 "numbers": {
  "M_TOKENS": $M_TOKENS,
  "LI_WORKERS": $LI_WORKERS,
  "WARM_N": $WARM_N,
  "RR_THREADS_ENV": $RR_THREADS_ENV,
  "LI_THREADS_ENV": $LI_THREADS_ENV,
  "LIVENESS_MIN": $LIVENESS_MIN,
  "GATE3_RUN_ID": "$GATE3_RUN_ID",
  "BLAST_C": $BLAST_C,
  "SEQ_N": $SEQ_N,
  "PASSES": $PASSES,
  "MEASURED_N": $MEASURED_N
 },
 "images": {"rr": "$RR_IMAGE", "li": "$LI_IMAGE"},
 "completed": false
}
MANIFEST
echo "run manifest: $OUT/run_manifest.json" | tee -a "$LOG"

echo "=== RUN PLAN: M=$M_TOKENS li_workers=$LI_WORKERS warm=$WARM_N \
rr_threads=$RR_THREADS_ENV li_threads=$LI_THREADS_ENV liveness>=$LIVENESS_MIN \
gate3=$GATE3_RUN_ID C=$BLAST_C seq_n=$SEQ_N passes=$PASSES -> $OUT ===" | tee -a "$LOG"

echo "--- 0. manifest re-cut check (re-cut is a REUSE: fetched must be 0) ---" | tee -a "$LOG"
run "$PY" working/video/fetch_ami_video.py --verify

echo "--- 1. LlamaIndex arm (both containers up for smoke read-backs; RR idles) ---" | tee -a "$LOG"
start_rr
start_li
run "$PY" working/video/smoke_video.py --rr-container rr --li-container li_video "${SMOKE_EXTRA[@]}"
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
# D6 fix (2026-08-22): the old `cmd; rc=$?` form was dead code under set -e —
# a failing --cross aborted the script BEFORE rc was read, leaving the manifest
# completed:false and later combos unevaluated. `if ! cmd` is set-e-exempt:
# every combo runs, failures are recorded, and the script exits non-zero at
# the END so the boundary stays fail-closed.
CROSS_FAIL=0
for leg in sequential blast; do
  for posture in default parity; do
    RRJ="$OUT/records_rocketride_video_${posture}_${leg}.jsonl"
    LIJ="$OUT/records_llamaindex_video_workers_${leg}.jsonl"
    if [ -f "$RRJ" ] && [ -f "$LIJ" ]; then
      echo "cross: $posture/$leg" | tee -a "$LOG"
      if "$PY" working/video/driver_video.py --cross "$RRJ" "$LIJ" \
          --gate3-armed "$GATE3_RUN_ID" > "$OUT/cross_${posture}_${leg}.json" 2>>"$LOG"; then
        echo "cross gates PASS: $posture/$leg" | tee -a "$LOG"
      else
        CROSS_FAIL=1
        echo "CROSS GATES FAILED: $posture/$leg" | tee -a "$LOG"
      fi
      cat "$OUT/cross_${posture}_${leg}.json" >> "$LOG"
    fi
  done
done

"$PY" - "$OUT/run_manifest.json" "$CROSS_FAIL" <<'PYDONE'
import json, sys, time
m = json.load(open(sys.argv[1]))
m['completed'] = True
m['cross_gates_failed'] = sys.argv[2] == '1'
m['completed_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
json.dump(m, open(sys.argv[1], 'w'), indent=1)
PYDONE
if [ "$CROSS_FAIL" = "1" ]; then
  echo "=== RUN PLAN COMPLETE — CROSS GATES FAILED (see cross_*.json under $OUT) ===" | tee -a "$LOG"
  exit 1
fi
echo "=== RUN PLAN COMPLETE — everything under $OUT ===" | tee -a "$LOG"
