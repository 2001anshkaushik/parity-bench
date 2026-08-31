#!/usr/bin/env bash
# =============================================================================
# FILMS MAIN RUN — Rulings P/Q/R/S/T (2026-08-31). Unlike the AMI skeleton
# (run_plan.sh, kept as the AMI-era artifact), every number here is RULED and
# BAKED — there are no posture/concurrency env knobs, because an env var on a
# paste line is how ruled campaigns stop being the ruled campaign (entry 25).
#
#   Cells (RULING P): LI N16xT2 -> RR default -> RR M16xT2; sequential leg +
#   2 blast passes each; BLAST_C=16 everywhere (RULING O); DEFAULT_N=35
#   (full measured set); SEQ_N=5; corpus = films manifest 54186c24 (35
#   measured + 2 warm, RULING J), splitter 4000/0 both arms (RULING L).
#   The RR default cell is an RR-internal out-of-box ratio (Crossroad 27) —
#   its cross files say so; LI's out-of-box is measured-pathological
#   (LI_SERVING_SKEW) and gets a report line, not a cell.
#
#   GATE3_RUN_ID and LIVENESS_MIN are READ FROM the staging artifact
#   (arming.json — Rulings Q/R), never typed: run_films_staging.sh produces
#   it and this script refuses to start without it or with armed:false.
#
#   Warm-up: driver-side per leg, WARM_N=2 manifest warm rows re-sent in
#   waves of 2x workers (RULING S: kept, not halved — warmth gates on
#   markers and the extra wave is the margin that passes legs).
#
# Helpers run()/container_provenance/stop_arm are deliberate copies of
# run_plan.sh's proven forms (:166-208) — the AMI skeleton stays untouched
# as the artifact its campaign ran on.
#
# PREFLIGHT_ONLY=1: bring up each cell's containers and run the driver's
# full --preflight-only per cell (incl. the Ruling-L chunk read-back), then
# stop — the minute-zero plan check (~15 min), no measurement.
#
# Committed script + self-printed sha256 per register entry 25.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../.."   # repo root
echo "run_plan_films.sh sha256: $(sha256sum "working/video/run_plan_films.sh" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing (venv with psutil+rocketride)"; exit 1; }

# ---- RULED NUMBERS (P/O/L/J) — baked, not knobs -----------------------------
M_TOKENS=16; RR_TENV=2; LI_INSTANCES=16; LI_TENV=2
BLAST_C=16; DEFAULT_N=35; SEQ_N=5; PASSES=2
VIDEO_MANIFEST="working/video/films_video_manifest.jsonl"   # T item 6: hard-pinned
GOLDEN="working/video/golden_films_record.json"
ARMING="${ARMING:-$HOME/films_probe/gate3_films/arming.json}"
PDF_CORPUS="${PDF_CORPUS:-$PWD/corpus/govdocs1/pdfs}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"
LI_IMAGE="${LI_IMAGE:-li:video}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-0}"

[ -f "$VIDEO_MANIFEST" ] || { echo "NOT DONE — films manifest missing: $VIDEO_MANIFEST"; exit 1; }
[ -f "$GOLDEN" ] || { echo "NOT DONE — films golden missing: $GOLDEN (run_films_staging.sh writes it once)"; exit 1; }
[ -f "$ARMING" ] || { echo "NOT DONE — arming artifact missing: $ARMING (run_films_staging.sh, Rulings Q/R)"; exit 1; }
[ -d "$PDF_CORPUS" ] || { echo "NOT DONE — PDF_CORPUS=$PDF_CORPUS is not a directory"; exit 1; }

# Arming values read, validated, echoed — never transcribed by hand.
ARM_OUT="$("$PY" - "$ARMING" <<'PYARM'
import json, sys
a = json.load(open(sys.argv[1]))
if a.get('armed') is not True:
    raise SystemExit(f"NOT DONE — arming.json says armed={a.get('armed')!r}; "
                     "gate-3 staging did not pass; the campaign cannot start")
lm = a['liveness']['liveness_min']
if lm is not None and not (0.0 < float(lm) <= 1.0):
    raise SystemExit(f'NOT DONE — liveness_min={lm!r} out of (0,1]')
print(a['gate3_run_id'])
print('NOT_RUN' if lm is None else lm)
PYARM
)" || { echo "$ARM_OUT"; exit 1; }
GATE3_RUN_ID="${ARM_OUT%%$'\n'*}"
LIVENESS_MIN="${ARM_OUT#*$'\n'}"
echo "armed: gate3=$GATE3_RUN_ID liveness_min=$LIVENESS_MIN (from $ARMING)"

# Corpus dir via the ONE locator (two lines: path, then source).
if ! LOC_OUT="$("$PY" working/video/corpus_locator.py --manifest "$VIDEO_MANIFEST" --tool run_plan_films)"; then
  echo "$LOC_OUT"; echo "NOT DONE — corpus_dir could not be resolved (above)"; exit 1
fi
CORPUS_DIR="${LOC_OUT%%$'\n'*}"; CORPUS_SRC="${LOC_OUT#*$'\n'}"
[ -d "$CORPUS_DIR" ] || { echo "NOT DONE — CORPUS_DIR=$CORPUS_DIR is not a directory"; exit 1; }

OUT="working/video/results/films_mainrun_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
LOG="$OUT/run_plan_films.log"
echo "corpus: manifest=$VIDEO_MANIFEST corpus_dir=$CORPUS_DIR [$CORPUS_SRC]" | tee -a "$LOG"

run() {  # run_plan.sh:166-172 form — ${PIPESTATUS[0]}, never $?
  echo "+ $*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  [ "$rc" = "0" ] || { echo "STEP FAILED rc=$rc: $*" | tee -a "$LOG"; exit "$rc"; }
}

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

container_provenance() {   # run_plan.sh:186-208 form
  local name="$1" tag="${2:-}" id created age
  id="$(docker inspect -f '{{.Id}}' "$name" 2>/dev/null | cut -c1-12)"
  created="$(docker inspect -f '{{.Created}}' "$name" 2>/dev/null)"
  age="$("$PY" -c "
import sys, time, datetime
try:
    t = datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))
    print(int(time.time() - t.timestamp()))
except Exception:
    print(-1)
" "$created" 2>/dev/null || echo -1)"
  echo "container $name${tag:+ [$tag]}: id=$id created=$created age=${age}s" | tee -a "$LOG"
  if [ "$age" -lt 0 ] 2>/dev/null || [ "$age" -gt 600 ]; then
    echo "NOT DONE — $name container state unknown or pre-existing (age=${age}s); a campaign" | tee -a "$LOG"
    echo "starts from a KNOWN container state. Remove it by hand and relaunch." | tee -a "$LOG"; exit 1
  fi
}

stop_arm() {  # $2 = lifetime tag
  docker logs "$1" > "$OUT/dockerlog_$1${2:+_$2}_final.txt" 2>&1 || true
  docker rm -f "$1" >/dev/null 2>&1 || true
}

LI_PORTS="8802-8817"
LI_CONTAINERS=""
for i in $(seq 0 15); do LI_CONTAINERS="$LI_CONTAINERS,li_bal_$i"; done
LI_CONTAINERS="${LI_CONTAINERS#,}"

start_rr() {  # $1 = 'unset' (default posture) or thread int (ruled posture)
  local t="$1" env_args=""
  docker rm -f rr 2>/dev/null || true
  [ "$t" = "unset" ] || env_args="$(envargs "$t")"
  # shellcheck disable=SC2086
  run docker run -d --name rr --memory 58g $env_args \
      --log-opt max-size=200m --network host "$RR_IMAGE"
  run "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  container_provenance rr "$t"
}

start_li_balanced() {  # RULED shape: 16 x single-worker, 3g, T=2, ports 8802-8817
  local i
  for i in $(seq 0 15); do
    docker rm -f "li_bal_$i" 2>/dev/null || true
    # shellcheck disable=SC2086
    run docker run -d --name "li_bal_$i" --memory 3g $(envargs "$LI_TENV") \
        -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$LI_IMAGE" -c \
        "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30"
  done
  for i in $(seq 0 15); do
    run "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
        --workers 1 --container "li_bal_$i" --deadline 1200
    container_provenance "li_bal_$i" "N16xT${LI_TENV}"
  done
}

stop_li_balanced() {
  local i; for i in $(seq 0 15); do stop_arm "li_bal_$i"; done
}

# Image lineage — VERBATIM into provenance (Crossroad 33).
RR_IMAGE_LINEAGE="Crossroad 33 (2026-08-22): rr:patched-video = a docker/Dockerfile.rocketride build PLUS one documented derived layer replacing working/nodes/env_probe (the instrument node; absent from the measured pipe, and carrying no requirements.txt so the engine constraints-cache key cannot move). A full rebuild was deliberately DEFERRED: it would re-resolve the floating ubuntu:22.04 base, the unpinned apt libc++/libunwind the engine ELF links, and the bootcheck constraints cache COPYed into the image, replacing the image that every RR probe number and the gate-3 arming run were measured on. PATH B re-baseline scheduled post-campaign with before/after fingerprints."
# T item 2 (2026-08-31): the AMI-era 'serving stack UNPINNED' text is FALSE
# since b295dea — corrected here so films exports carry true provenance.
LI_IMAGE_LINEAGE="docker/Dockerfile.llamaindex-video at the Ruling-L config (4000/0): FULL 149-pin freeze install from li_video/li_image_freeze.txt with a fail-closed build-time read-back (pip freeze == freeze file; b295dea), streaming reader (spool -> frames-on-disk -> k=1), chunk config read back per leg from every worker's /health by the driver preflight (Ruling T item 3)."

# Cross-file disclosures ride the cross label into EVERY cross file (Ruling T):
DISCLOSURES="DISCLOSURES: char_conservation verdict at the Phase-1 +/-2 pct default is band-cutting DATA for the films band (Ruling L equivalence note), not a calibrated headline; the gate-3 boundary-exclusion drift cap (0.5 pct/video) is LIVE and UNSIZED for films content (H16 open — do not read its verdict as calibrated)."

DRIVER=("$PY" working/video/driver_video.py --out-dir "$OUT" \
        --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR")
LIVE_ARGS=()
[ "$LIVENESS_MIN" = "NOT_RUN" ] || LIVE_ARGS=(--liveness-min-fraction "$LIVENESS_MIN")

# Run-level manifest: the ruled numbers + arming, machine-readable, before
# anything runs; completed flipped at the end (run_plan.sh pattern).
"$PY" - "$OUT/run_manifest.json" "$ARMING" <<PYMAN
import json, subprocess, sys, time
arm = json.load(open(sys.argv[2]))
m = {
 'run_dir': '$OUT', 'campaign': 'films_mainrun',
 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
 'git_sha': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                           text=True).stdout.strip(),
 'preflight_only': '$PREFLIGHT_ONLY' == '1',
 'ruled_numbers': {
  'rulings': 'P (cells/passes/seq), O (C=16 both arms), M (16x2 postures), L (4000/0), J (warm split), S (warm waves kept 2x)',
  'M_TOKENS': $M_TOKENS, 'RR_THREADS_ENV': $RR_TENV,
  'RR_DEFAULT_THREADS_ENV': 'unset (engine default — what a user gets)',
  'LI_INSTANCES': $LI_INSTANCES, 'LI_THREADS_ENV': $LI_TENV,
  'BLAST_C': $BLAST_C, 'DEFAULT_N': $DEFAULT_N, 'SEQ_N': $SEQ_N,
  'PASSES': $PASSES, 'WARM_N': 2,
 },
 'arming': arm,
 'corpus': {'manifest': '$VIDEO_MANIFEST', 'corpus_dir': '$CORPUS_DIR',
            'manifest_sha256_expected': '54186c24a25df594ffd14c9a270281863208ef23dfec2b00814372ed125d4b54'},
 'disclosures': '''$DISCLOSURES''',
 'completed': False,
}
json.dump(m, open(sys.argv[1], 'w'), indent=1)
print('run manifest:', sys.argv[1])
PYMAN

echo "=== FILMS RUN: LI N${LI_INSTANCES}xT${LI_TENV} -> RR default -> RR M${M_TOKENS}xT${RR_TENV}; C=$BLAST_C; passes=$PASSES; seq_n=$SEQ_N; gate3=$GATE3_RUN_ID; liveness=$LIVENESS_MIN -> $OUT ===" | tee -a "$LOG"

echo "--- 0. corpus verify (read-only, full sha256) ---" | tee -a "$LOG"
run "$PY" working/video/fetch_ami_video.py --verify --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR"

echo "--- 1. LlamaIndex N16xT2 (one lifetime for the LI block; warm-up per leg) ---" | tee -a "$LOG"
start_rr unset   # both arms up for the smoke's cross read-backs; rr idles at default
start_li_balanced
run "$PY" working/video/smoke_video.py --rr-container rr --li-container li_bal_0 \
    --rr-threads-env unset --pdf-corpus "$PDF_CORPUS" \
    --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR" --golden "$GOLDEN"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  run "${DRIVER[@]}" --arm llamaindex --leg sequential --n 1 --preflight-only \
      --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
      --image-lineage "$LI_IMAGE_LINEAGE"
else
  run "${DRIVER[@]}" --arm llamaindex --leg sequential --n "$SEQ_N" \
      --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
      --image-lineage "$LI_IMAGE_LINEAGE"
  for pass in $(seq 1 "$PASSES"); do
    echo "--- LI blast pass $pass/$PASSES ---" | tee -a "$LOG"
    run "${DRIVER[@]}" --arm llamaindex --leg blast --n "$DEFAULT_N" \
        --blast-concurrency "$BLAST_C" --pass "$pass" \
        --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
        --image-lineage "$LI_IMAGE_LINEAGE"
  done
fi
stop_li_balanced

echo "--- 2. RocketRide DEFAULT posture (out-of-box: 1 token, env unset; Crossroad 27 framing) ---" | tee -a "$LOG"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  run "${DRIVER[@]}" --arm rocketride --posture default --leg sequential --n 1 \
      --rr-threads-env unset --preflight-only "${LIVE_ARGS[@]}" \
      --image-lineage "$RR_IMAGE_LINEAGE"
else
  run "${DRIVER[@]}" --arm rocketride --posture default --leg sequential --n "$SEQ_N" \
      --rr-threads-env unset "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
  for pass in $(seq 1 "$PASSES"); do
    run "${DRIVER[@]}" --arm rocketride --posture default --leg blast --n "$DEFAULT_N" \
        --blast-concurrency "$BLAST_C" --rr-threads-env unset --pass "$pass" \
        "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
  done
fi
stop_arm rr default

echo "--- 3. RocketRide M16xT2 (ruled posture, fresh rr lifetime) ---" | tee -a "$LOG"
start_rr "$RR_TENV"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n 1 \
      --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" --preflight-only \
      "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
  stop_arm rr parity
  echo "=== PREFLIGHT_ONLY COMPLETE — wiring + read-backs proven, nothing measured ===" | tee -a "$LOG"
  exit 0
fi
run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n "$SEQ_N" \
    --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" "${LIVE_ARGS[@]}" \
    --image-lineage "$RR_IMAGE_LINEAGE"
for pass in $(seq 1 "$PASSES"); do
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n "$DEFAULT_N" \
      --blast-concurrency "$BLAST_C" --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" \
      --pass "$pass" "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
done
stop_arm rr parity

echo "--- 4. cross-arm gates (gate 3 armed by $GATE3_RUN_ID) ---" | tee -a "$LOG"
CROSS_FAIL=0
for leg in sequential blast; do
  for posture in default parity; do
    for RRJ in "$OUT/records_rocketride_video_${posture}_${leg}.jsonl" \
               "$OUT"/records_rocketride_video_${posture}_${leg}_p*.jsonl; do
      [ -f "$RRJ" ] || continue
      sfx="${RRJ##*/records_rocketride_video_${posture}_${leg}}"; sfx="${sfx%.jsonl}"
      LIJ="$OUT/records_llamaindex_video_workers_${leg}${sfx}.jsonl"
      [ -f "$LIJ" ] || { echo "cross: $posture/$leg$sfx — no LI counterpart; skipped" | tee -a "$LOG"; continue; }
      if [ "$posture" = "default" ]; then
        CROSS_LABEL="equal-work gates ONLY — the RR default (out-of-box) posture is an RR-internal ratio (Crossroad 27), not a cross-arm performance comparison | $DISCLOSURES"
      else
        CROSS_LABEL="ruled 16x2-vs-16x2 posture (Rulings M/O) — cross-arm comparison | $DISCLOSURES"
      fi
      echo "cross: $posture/$leg$sfx" | tee -a "$LOG"
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
echo "=== FILMS RUN COMPLETE (cross_fail=$CROSS_FAIL) — everything under $OUT ===" | tee -a "$LOG"
echo "ENTRY 26 STOP-AND-LAND: the results are IN-REPO. The box commits $OUT and" | tee -a "$LOG"
echo "bundles; NO laptop work pushes onto this base until ls-remote confirms the" | tee -a "$LOG"
echo "landing. (Cut, uploaded, downloaded, verified are not landed.)" | tee -a "$LOG"
[ "$CROSS_FAIL" = "1" ] && exit 1
exit 0
