#!/usr/bin/env bash
# =============================================================================
# FILMS MAIN-RUN STAGING (Rulings Q, R, T items 4+5; 2026-08-31). Runs ONCE
# before run_plan_films.sh and produces everything the campaign refuses to
# start without:
#
#   0. step-0 verify — fetch_ami_video --verify against the FILMS manifest
#      (T item 5: the verify op is manifest-generic — rows' file/sha256/bytes;
#      this invocation IS the 30-second confirmation; read-only, never fetches);
#   1. bring-ups at the RULED shapes: rr default lifetime (no thread env) +
#      LI balanced 16x1 at 3g, ports 8802-8817 (T item 1's shape, exercised
#      here before the campaign);
#   2. FILMS SMOKE GOLDEN, write-once (T item 4): full smoke in --write-golden
#      mode at the default rr lifetime; golden video = shortest corpus item
#      (smoke default); golden path golden_films_record.json — NEVER the AMI
#      golden's path (entry 7: evidence is not clobbered);
#   3. STAGED GATE-3 (Ruling Q): one film, BOTH arms, through the LEG DRIVER
#      itself (real preflights — including the new Ruling-L chunk read-back,
#      live for the first time — real records; --skip-warmup: labels do not
#      depend on warmth, and staging measures agreement, not latency; stated
#      here). Film = first measured manifest row (20000LeaguesUndertheSea):
#      deterministic, and the film whose frames are proven byte-identical
#      A==B==C in the committed parity artifact — the same-frames
#      precondition is strongest exactly there.
#   4. ARMING + LIVENESS_MIN (Ruling R): derive_gate3_arming.py runs the
#      committed strict gate on the staged records and cuts LIVENESS_MIN from
#      the measured minimum with a stated 2x margin — writes arming.json,
#      which run_plan_films.sh READS (no transcription). Gate-3 disagreement
#      = STOP finding, nothing armed, campaign cannot start.
#
# Committed script + self-printed sha256 per register entry 25.
# Expected wall ~45-70 min (bring-ups ~10, golden ~3-5, smoke ~5, staged legs
# ~8-15/arm at ~0.6-1.2 f/s single-lane on 395 frames, derive seconds).
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_films_staging.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PYBIN:-$HOME/.venv/bin/python}"          # driver/smoke interpreter (Phase 1 venv)
[ -x "$PY" ] || { echo "NOT DONE — $PY missing (venv with psutil+rocketride)"; exit 1; }
MANIFEST="working/video/films_video_manifest.jsonl"
GOLDEN="working/video/golden_films_record.json"
OUT="${OUT:-$HOME/films_probe/gate3_films}"
PDF_CORPUS="${PDF_CORPUS:-$PWD/corpus/govdocs1/pdfs}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"
LI_IMAGE="${LI_IMAGE:-li:video}"
mkdir -p "$OUT"
[ -f "$MANIFEST" ] || { echo "NOT DONE — films manifest missing: $MANIFEST"; exit 1; }
if [ ! -d "$PDF_CORPUS" ]; then
  echo "NOT DONE — PDF_CORPUS=$PDF_CORPUS is not a directory (smoke section A measures"
  echo "the duplication patch; a label is not a measurement). Point PDF_CORPUS at GovDocs1."
  exit 1
fi
if [ -f "$GOLDEN" ]; then
  echo "NOT DONE — $GOLDEN already exists. The films golden is WRITE-ONCE; delete it"
  echo "by hand only if Ansh ruled a re-write (image or thread config changed)."
  exit 1
fi

# Resolve corpus dir through the ONE locator (entry 15). It prints TWO
# lines — path, then source — the run_plan parse form, copied exactly.
if ! LOC_OUT="$("$PY" working/video/corpus_locator.py --manifest "$MANIFEST" --tool films_staging)"; then
  echo "$LOC_OUT"; echo "NOT DONE — corpus_dir could not be resolved (above)"; exit 1
fi
CORPUS_DIR="${LOC_OUT%%$'\n'*}"
CORPUS_SRC="${LOC_OUT#*$'\n'}"
[ -d "$CORPUS_DIR" ] || { echo "NOT DONE — resolved CORPUS_DIR=$CORPUS_DIR is not a directory"; exit 1; }
echo "corpus: manifest=$MANIFEST corpus_dir=$CORPUS_DIR [$CORPUS_SRC]"

echo "== 0. step-0 verify (T item 5: manifest-generic --verify on the films manifest; read-only) =="
"$PY" working/video/fetch_ami_video.py --verify --manifest "$MANIFEST" --corpus-dir "$CORPUS_DIR"

LI_PORTS="8802-8817"
LI_CONTAINERS=""
for i in $(seq 0 15); do LI_CONTAINERS="$LI_CONTAINERS,li_bal_$i"; done
LI_CONTAINERS="${LI_CONTAINERS#,}"

teardown() {
  docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
}
trap teardown EXIT

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

echo "== 1a. rr default lifetime (no thread env — the out-of-box posture) =="
docker rm -f rr >/dev/null 2>&1 || true
docker run -d --name rr --memory 58g --log-opt max-size=200m --network host "$RR_IMAGE" >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr

echo "== 1b. LI balanced 16x1 at 3g (the ruled N16xT2 shape; T item 1) =="
for i in $(seq 0 15); do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory 3g $(envargs 2) \
      -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$LI_IMAGE" -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
done
for i in $(seq 0 15); do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done

echo "== 2. films smoke golden, WRITE-ONCE + full smoke sections (T item 4) =="
# --li-container li_bal_0: instance 0 by the stated convention (entry 21's
# per-site semantics); the driver's own leg preflight checks EVERY instance.
"$PY" working/video/smoke_video.py --rr-container rr --li-container li_bal_0 \
    --rr-threads-env unset --pdf-corpus "$PDF_CORPUS" \
    --manifest "$MANIFEST" --corpus-dir "$CORPUS_DIR" \
    --write-golden --golden "$GOLDEN"
echo "golden written: $GOLDEN (write-once; campaign smokes COMPARE against it)"

echo "== 3a. staged leg: RR default, 1 film, sequential (--skip-warmup: staging measures agreement, not latency) =="
"$PY" working/video/driver_video.py --arm rocketride --posture default --leg sequential \
    --n 1 --rr-threads-env unset --skip-warmup \
    --manifest "$MANIFEST" --corpus-dir "$CORPUS_DIR" --out-dir "$OUT" \
    --image-lineage "staging leg — lineage recorded fully by run_plan_films"

echo "== 3b. staged leg: LI balanced 16x1, 1 film, sequential =="
"$PY" working/video/driver_video.py --arm llamaindex --leg sequential \
    --n 1 --skip-warmup --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" \
    --manifest "$MANIFEST" --corpus-dir "$CORPUS_DIR" --out-dir "$OUT" \
    --image-lineage "staging leg — lineage recorded fully by run_plan_films"

echo "== 4. arming + LIVENESS_MIN derivation (Rulings Q + R) =="
"$PY" working/video/probe/derive_gate3_arming.py \
    --rr-records "$OUT/records_rocketride_video_default_sequential.jsonl" \
    --li-records "$OUT/records_llamaindex_video_workers_sequential.jsonl" \
    --out "$OUT/arming.json"

echo "STAGING COMPLETE. Read $OUT/arming.json (agreement verdict, liveness"
echo "derivation) BEFORE launching run_plan_films.sh — gate-3 disagreement is"
echo "a STOP finding. Golden at $GOLDEN. Containers torn down by trap."
