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
#   WARM_N         warm items; the manifest re-cut supplies the split
#                  (measured = 60 - WARM_N). Crossroad 32 (2026-08-21): need
#                  NOT exceed the instance count — warm rows may be re-sent;
#                  the driver gates every instance observed serving.
#   RR_THREADS_ENV six BLAS/OMP vars on the RR container for the PARITY
#                  posture ONLY — the measured optimum, set WITH M_TOKENS by
#                  the M x T refine (Crossroads 29/30: the winning product sets
#                  both). RULING 2026-08-21: the DEFAULT posture runs the
#                  engine default — nothing declared — because the out-of-box
#                  posture must reflect what a user actually gets, and the
#                  M=1 thread curve only ever measured 1/8/32. The rr
#                  container is therefore started TWICE: unset for steps 1-2,
#                  RR_THREADS_ENV for step 3; every leg states its expectation
#                  (--rr-threads-env) and the driver reads it back declared +
#                  in-process, fail-closed.
#   LI_THREADS_ENV six BLAS/OMP vars on the LI container — LI's own optimum
#                  (Crossroad 17: same sweep matrix both arms, per-arm optimum;
#                  values published beside the full matrix; declared==measured
#                  enforced per arm; cross-arm difference recorded, never failed)
#   DEFAULT_N      Crossroad 27: videos in the DEFAULT-posture blast leg.
#                  At today's 44-corpus scale set it to MEASURED_N (full set).
#                  Above ~1000 videos the default posture runs a STATED
#                  SUBSET (RULED 2026-08-21: >=500, manifest-order prefix,
#                  stated in the export; or the full set when smaller) —
#                  the out-of-box finding is a RATIO and does not need 5000
#                  samples; 5000 videos at 1 token is ~36 h re-proving what
#                  500 show. Parity always runs the full measured set.
#                  cross_gates pairs on the video-name INTERSECTION and
#                  reports n_paired, so a subset compares honestly.
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
#                  thin-window alternative). RULED 2 for the 44-video campaign
#                  at C=16 (Crossroad 32) — export PASSES=2 on the real run.
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
DRY_PASS="${DRY_PASS:-0}"
# LIVENESS_MIN (gate 5) is probe-derived and has NO default. A DRY pass may
# omit it — the driver then records gate 5 as NOT RUN (first-class verdict,
# never PASS) and nothing from a dry pass is a measurement anyway. A real run
# refuses without it.
if [ "$DRY_PASS" != "1" ]; then
  # No quotes or parentheses inside a :? message — bash 3.2 treats a quote in
  # the word as opening one and the parse error surfaces lines later.
  : "${LIVENESS_MIN:?LIVENESS_MIN unset — gate 5 threshold from the measured detections distribution; only DRY_PASS=1 may omit it}"
fi
LIVENESS_MIN="${LIVENESS_MIN:-}"
: "${GATE3_RUN_ID:?GATE3_RUN_ID unset — probe run id that confirmed ES2002a agreement}"
: "${BLAST_C:?BLAST_C unset — blast concurrency}"
: "${DEFAULT_N:?DEFAULT_N unset — Crossroad 27: default-posture blast size (full set at 44-scale; stated subset >=500 above ~1000)}"
SEQ_N="${SEQ_N:-5}"
PASSES="${PASSES:-1}"
# Register entry 8 (2026-08-21): presence is not plausibility. The :? checks
# above prove the eight EXIST; these prove they are NUMBERS in range before a
# single container starts. A guard that checks presence rather than
# plausibility cannot fail for the case it was built for.
require_pos_int() {
  case "$2" in ''|*[!0-9]*)
    echo "NOT DONE — $1='$2' is not a positive integer (missing space in the command?)"; exit 1;;
  esac
  [ "$2" -ge 1 ] || { echo "NOT DONE — $1=$2 must be >= 1"; exit 1; }
}
require_pos_int M_TOKENS "$M_TOKENS";   require_pos_int LI_WORKERS "$LI_WORKERS"
require_pos_int WARM_N "$WARM_N";       require_pos_int RR_THREADS_ENV "$RR_THREADS_ENV"
require_pos_int LI_THREADS_ENV "$LI_THREADS_ENV"; require_pos_int BLAST_C "$BLAST_C"
require_pos_int SEQ_N "$SEQ_N";         require_pos_int PASSES "$PASSES"
require_pos_int DEFAULT_N "$DEFAULT_N"
if [ -n "$LIVENESS_MIN" ]; then
"$PY" - "$LIVENESS_MIN" <<'EOF' || exit 1
import sys
raw = sys.argv[1]
try:
    v = float(raw)
except ValueError:
    raise SystemExit(f'NOT DONE — LIVENESS_MIN={raw!r} is not a number')
if not (0.0 < v <= 1.0):
    raise SystemExit(f'NOT DONE — LIVENESS_MIN={v} must be a fraction in (0, 1]')
EOF
fi
case "$GATE3_RUN_ID" in
  -*|*--*) echo "NOT DONE — GATE3_RUN_ID='$GATE3_RUN_ID' looks like a flag or a missing-space typo, not a probe run id"; exit 1;;
esac
# Crossroad 32 (2026-08-21): WARM_N need not exceed the instance count — a
# warm row MAY be re-sent to cover more than one token; the disjointness that
# matters is warm-vs-MEASURED (the manifest split), not warm-vs-warm; a token
# warmed twice is no less warm. The driver GATES on every instance observed
# serving during warm-up. Recorded here, never refused.
if [ "$WARM_N" -lt "$M_TOKENS" ] || [ "$WARM_N" -lt "$LI_WORKERS" ]; then
  echo "note — WARM_N=$WARM_N < max(M_TOKENS=$M_TOKENS, LI_WORKERS=$LI_WORKERS): warm rows will be re-sent until every instance has served (Crossroad 32; the driver gates coverage)"
fi
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

start_rr() {  # $1 = thread env for THIS lifetime: 'unset' (default posture) or N (parity)
  local t="$1"
  case "$t" in unset) ;; ''|*[!0-9]*) echo "NOT DONE — start_rr needs 'unset' or a positive int, got '$t'"; exit 1;; esac
  docker rm -f rr 2>/dev/null || true
  # Crossroad 22: --network host both arms (Phase 1 section C parity; no
  # docker-proxy hop in measured latency; TCP-check trap = instance seven).
  # Ruling 2026-08-21: per-posture thread env — 'unset' passes NO -e (the
  # engine default is what a user gets); N passes the six. Read back below.
  local env_args=""
  [ "$t" = "unset" ] || env_args="$(thread_env_args "$t")"
  # shellcheck disable=SC2046,SC2086
  run docker run -d --name rr --memory 58g $env_args \
      --log-opt max-size=200m --network host "$RR_IMAGE"
  # Read-back of the DECLARED env on the container this lifetime (the
  # in-process read-back is the driver's per-leg preflight).
  echo "rr declared thread env (expected $t): $(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' rr | grep -E '^(OMP|MKL|OPENBLAS|VECLIB|NUMEXPR|TORCH)_' | tr '\n' ' ' || true)" | tee -a "$LOG"
  # Readiness = a real SDK connect (one helper everywhere); asserts host mode
  # and records it in the log via run().
  run "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
}

start_li() {
  docker rm -f li_video 2>/dev/null || true
  # Crossroad 22: --network host (see start_rr).
  # shellcheck disable=SC2046
  run docker run -d --name li_video --memory 58g $(thread_env_args "$LI_THREADS_ENV") \
      -e WS1V_WORKERS="$LI_WORKERS" --log-opt max-size=200m --network host "$LI_IMAGE"
  # Readiness = /health 200 + warm_workers == LI_WORKERS (the real predicate,
  # not liveness); asserts host mode; deadline covers W model loads.
  run "$PY" working/video/probe/wait_ready.py --arm li --port 8802 \
      --deadline 900 --workers "$LI_WORKERS" --container li_video
  # D7 read-back (2026-08-21): the LI image's serving stack is UNPINNED at
  # build (fastapi/uvicorn/llama-index float) — snapshot the resolved
  # versions per run so the measured latency's substrate is on record.
  # Dockerfile pinning is a flagged follow-up ruling, not done here.
  docker exec li_video python -m pip freeze > "$OUT/li_image_freeze.txt" 2>>"$LOG" \
    || echo "li_image_freeze snapshot FAILED (recorded)" | tee -a "$LOG"
}

stop_arm() {  # $2 = optional lifetime tag (rr now has two lifetimes — logs must not overwrite)
  docker logs "$1" > "$OUT/dockerlog_$1${2:+_$2}_final.txt" 2>&1 || true
  docker rm -f "$1" >/dev/null 2>&1 || true
}

# Crossroad 33 (2026-08-22): the image lineage rides in every export's
# provenance, verbatim — a tag is not an identity, and rr:patched-video is no
# longer "what the Dockerfile builds".
# NOT written as "${VAR:-long default}": inside a ${…:-word} expansion bash
# parses quotes in the word, so ONE apostrophe (gate 3's) opens a quote and the
# parse error surfaces lines later at an unrelated paren — the same 3.2 quirk
# that bit the LIVENESS_MIN :? message this morning, walked into twice in one
# day. The if-form takes an ordinary double-quoted string, where ' is literal.
if [ -z "${RR_IMAGE_LINEAGE:-}" ]; then
  RR_IMAGE_LINEAGE="Crossroad 33 (2026-08-22): rr:patched-video = a docker/Dockerfile.rocketride build PLUS one documented derived layer replacing working/nodes/env_probe (the instrument node; absent from the measured pipe, and carrying no requirements.txt so the engine constraints-cache key cannot move). A full rebuild was deliberately DEFERRED: it would re-resolve the floating ubuntu:22.04 base, the unpinned apt libc++/libunwind the engine ELF links, and the bootcheck constraints cache COPYed into the image, replacing the image that every RR probe number and the gate-3 arming run were measured on. PATH B re-baseline scheduled post-campaign with before/after fingerprints."
fi
if [ -z "${LI_IMAGE_LINEAGE:-}" ]; then
  LI_IMAGE_LINEAGE="docker/Dockerfile.llamaindex-video, unmodified build, no derived layers; serving stack UNPINNED at build (per-run pip freeze snapshot in li_image_freeze.txt)."
fi
DRIVER=("$PY" working/video/driver_video.py --out-dir "$OUT")
if [ -n "$LIVENESS_MIN" ]; then
  DRIVER+=(--liveness-min-fraction "$LIVENESS_MIN")
else
  echo "gate 5 (detection_liveness): LIVENESS_MIN not supplied — NOT RUN on every leg (dry pass only)" | tee -a "$LOG"
fi
MEASURED_N=$((60 - WARM_N))
[ "$DEFAULT_N" -le "$MEASURED_N" ] || {
  echo "NOT DONE — DEFAULT_N=$DEFAULT_N > MEASURED_N=$MEASURED_N (Crossroad 27: the default"
  echo "posture runs a subset of the measured set, never more than it)"; exit 1; }
SMOKE_EXTRA=()
if [ "$DRY_PASS" = "1" ]; then
  echo "=== DRY PASS — wiring only; every knob clamped; nothing here is a measurement ===" | tee -a "$LOG"
  # PASSES=2 here on purpose (2026-08-21): a dry pass that clamps PASSES to 1
  # was green while the second pass was a no-op resume — the composition
  # must prove the pass mechanism, not skip it.
  SEQ_N=1; PASSES=2; MEASURED_N=1; BLAST_C=1; DEFAULT_N=1
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
  "RR_THREADS_ENV_applies_to": "parity posture only — rr restarted between postures (ruling 2026-08-21)",
  "RR_DEFAULT_THREADS_ENV": "unset (engine default: what a user gets; read back in-process per leg)",
  "LI_THREADS_ENV": $LI_THREADS_ENV,
  "LIVENESS_MIN": ${LIVENESS_MIN:-null},
  "GATE3_RUN_ID": "$GATE3_RUN_ID",
  "BLAST_C": $BLAST_C,
  "DEFAULT_N": $DEFAULT_N,
  "SEQ_N": $SEQ_N,
  "PASSES": $PASSES,
  "MEASURED_N": $MEASURED_N
 },
 "images": {"rr": "$RR_IMAGE", "li": "$LI_IMAGE"},
 "decisions": {
  "ruled_values": "Crossroads 31/32 (2026-08-21): M_TOKENS=16, RR_THREADS_ENV=2 (parity; default posture unset), LI_WORKERS=8, LI_THREADS_ENV=1, WARM_N=16, BLAST_C=16, DEFAULT_N=44, PASSES=2 — if the numbers above differ, this run is NOT the ruled campaign",
  "M_TOKENS_rationale": "working/video/RR_PARITY_CURVE.md — the full M x T curve including the faster M=32 we DECLINED (+3.3% throughput for 31% of the box idle and 32 model stacks); idle burden is reported beside every parity number, never subtracted",
  "WARM_N_rationale": "Crossroad 32: warm rows may be re-sent across instances; warm-vs-measured disjointness is the invariant; the driver gates every instance observed serving"
 },
 "completed": false
}
MANIFEST
echo "run manifest: $OUT/run_manifest.json" | tee -a "$LOG"

echo "=== RUN PLAN: M=$M_TOKENS li_workers=$LI_WORKERS warm=$WARM_N \
rr_threads(parity)=$RR_THREADS_ENV rr_threads(default)=unset li_threads=$LI_THREADS_ENV \
liveness>=${LIVENESS_MIN:-NOT_RUN} gate3=$GATE3_RUN_ID C=$BLAST_C seq_n=$SEQ_N passes=$PASSES -> $OUT ===" | tee -a "$LOG"

echo "--- 0. manifest re-cut check (re-cut is a REUSE: fetched must be 0) ---" | tee -a "$LOG"
# NOTE (2026-08-22): --verify sha256s the WHOLE corpus — roughly one core for
# tens of seconds. It is OURS, and it used to show up in the next quiet-box
# check as "foreign load" because that gate read load1 (a ~60 s lagging
# average) and subtracted only containers. The gate is now instantaneous
# (/proc/stat busy − our containers − our own process tree), so this
# verification's tail no longer inflates it and no leg systematically settles
# because of it. If a quiet-box check DOES settle now, something is burning
# CPU at that moment — read the trend: DECAYING is a transient, SUSTAINED is a hog.
run "$PY" working/video/fetch_ami_video.py --verify

echo "--- 1. LlamaIndex arm (both containers up for smoke read-backs; RR idles at the DEFAULT config) ---" | tee -a "$LOG"
start_rr unset
start_li
run "$PY" working/video/smoke_video.py --rr-container rr --li-container li_video \
    --rr-threads-env unset "${SMOKE_EXTRA[@]}"
run "${DRIVER[@]}" --arm llamaindex --leg sequential --n "$SEQ_N" \
    --image-lineage "$LI_IMAGE_LINEAGE"
for pass in $(seq 1 "$PASSES"); do
  echo "--- LI blast pass $pass/$PASSES ---" | tee -a "$LOG"
  run "${DRIVER[@]}" --arm llamaindex --leg blast --n "$MEASURED_N" --blast-concurrency "$BLAST_C" \
      --pass "$pass" --image-lineage "$LI_IMAGE_LINEAGE"
done
stop_arm li_video

echo "--- 2. RocketRide DEFAULT posture (1 token, use(threads=) unset = engine 64, six-var env UNSET = engine default) ---" | tee -a "$LOG"
# The full smoke ran once in step 1 with BOTH containers live; per-leg
# re-verification (flags, pins, identity, quiet box) is the driver's own
# fail-closed preflight — no || true anywhere in this file. Every RR leg
# states its expected thread env; the driver reads it back (ruling 2026-08-21).
run "${DRIVER[@]}" --arm rocketride --posture default --leg sequential --n "$SEQ_N" \
    --rr-threads-env unset --image-lineage "$RR_IMAGE_LINEAGE"
for pass in $(seq 1 "$PASSES"); do
  # Crossroad 27: the default-posture blast runs DEFAULT_N (a stated subset at
  # scale — the out-of-box finding is a ratio); parity runs the full set.
  run "${DRIVER[@]}" --arm rocketride --posture default --leg blast --n "$DEFAULT_N" \
      --blast-concurrency "$BLAST_C" --rr-threads-env unset --pass "$pass" \
      --image-lineage "$RR_IMAGE_LINEAGE"
done
stop_arm rr default

echo "--- 3. RocketRide PARITY posture (M=$M_TOKENS tokens, six-var env = $RR_THREADS_ENV; fresh rr lifetime) ---" | tee -a "$LOG"
start_rr "$RR_THREADS_ENV"
run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n "$SEQ_N" --tokens "$M_TOKENS" \
    --rr-threads-env "$RR_THREADS_ENV" --image-lineage "$RR_IMAGE_LINEAGE"
for pass in $(seq 1 "$PASSES"); do
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n "$MEASURED_N" \
      --blast-concurrency "$BLAST_C" --tokens "$M_TOKENS" --rr-threads-env "$RR_THREADS_ENV" \
      --pass "$pass" --image-lineage "$RR_IMAGE_LINEAGE"
done
stop_arm rr parity

echo "--- 4. cross-arm gates (gate 3 armed by $GATE3_RUN_ID, then char conservation) ---" | tee -a "$LOG"
# D6 fix (2026-08-21): the old `cmd; rc=$?` form was dead code under set -e —
# a failing --cross aborted the script BEFORE rc was read, leaving the manifest
# completed:false and later combos unevaluated. `if ! cmd` is set-e-exempt:
# every combo runs, failures are recorded, and the script exits non-zero at
# the END so the boundary stays fail-closed.
CROSS_FAIL=0
# Pass-aware (2026-08-21): pass 1 files carry the bare name, pass N>1 carry
# _pN; each RR pass file pairs with the LI file of the SAME pass suffix.
for leg in sequential blast; do
  for posture in default parity; do
    for RRJ in "$OUT/records_rocketride_video_${posture}_${leg}.jsonl" \
               "$OUT"/records_rocketride_video_${posture}_${leg}_p*.jsonl; do
      [ -f "$RRJ" ] || continue
      sfx="${RRJ##*/records_rocketride_video_${posture}_${leg}}"; sfx="${sfx%.jsonl}"
      LIJ="$OUT/records_llamaindex_video_workers_${leg}${sfx}.jsonl"
      [ -f "$LIJ" ] || { echo "cross: $posture/$leg$sfx — no LI counterpart ($LIJ); skipped" | tee -a "$LOG"; continue; }
      echo "cross: $posture/$leg$sfx" | tee -a "$LOG"
      # Ruling 2026-08-21: the DEFAULT posture is an RR-internal out-of-box
      # ratio (Crossroad 27), so its cross file is equal-work gates ONLY —
      # NOT a cross-arm performance comparison. Stamp the basis into the file.
      if [ "$posture" = "default" ]; then
        CROSS_LABEL="equal-work gates ONLY — the RR default (out-of-box) posture is an RR-internal ratio (Crossroad 27), not a cross-arm performance comparison"
      else
        CROSS_LABEL="parity posture — cross-arm comparison (matched instances)"
      fi
      if "$PY" working/video/driver_video.py --cross "$RRJ" "$LIJ" \
          --gate3-armed "$GATE3_RUN_ID" --cross-label "$CROSS_LABEL" \
          > "$OUT/cross_${posture}_${leg}${sfx}.json" 2>>"$LOG"; then
        echo "cross gates PASS: $posture/$leg$sfx" | tee -a "$LOG"
      else
        CROSS_FAIL=1
        echo "CROSS GATES FAILED: $posture/$leg$sfx" | tee -a "$LOG"
      fi
      cat "$OUT/cross_${posture}_${leg}${sfx}.json" >> "$LOG"
    done
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
