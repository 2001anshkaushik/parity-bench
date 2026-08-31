#!/usr/bin/env bash
# =============================================================================
# Films C sweep (RULING I, re-ordered by RULING K: this runs AFTER the
# posture sweep and Ansh's posture ruling — M x threads sets the posture, C
# then saturates it; sweeping C first risks finding the knee for a posture
# we abandon). Committed script + self-printed sha256 per register entry 25.
#
# Set the RULED winners before running (defaults are the AMI shapes and are
# NOT a ruling): RR_TOKENS, RR_TENV, LI_INSTANCES, LI_TENV.
#
# Points: the winning RR and LI postures at C_GRID (default "1 2 4 8" —
# the RULING I grid, sized when the assumed winners had 8 lanes; at the
# RULING M 16-lane winners C=8 under-saturates and the knee cannot appear
# below C=16 — extending the grid is Ansh's ruling, and C_GRID is the
# lever, e.g. C_GRID="1 2 4 8 16 32"); rr-default at C in {1,2} only
# (M=1 by definition — C above 1 measures queueing at the single
# per-instance reader lock; one control point verifies queued-item
# survival at films timescale, not four). Every point runs the SAME 9-film
# strata-heads batch (fixed workload, variable C — content-controlled
# curve) with the fixed mem_watch beside it; posture env read-backs fail
# closed; warm rows structurally excluded.
#
# --summarize prints the curve, marginal efficiency per step
# ([T(C)/T(prev)]/[C/prev], knee < 0.7 — probe_concurrency.py:15-17
# verbatim) and marginal GB per active lane. C IS NOT PICKED HERE.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_films_curve.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PY:-$HOME/.venv-floor/bin/python3}"
MANIFEST="${MANIFEST:-working/video/films_video_manifest.jsonl}"
OUT_DIR="${OUT_DIR:-$HOME/films_probe/curve_out}"
RR_TOKENS="${RR_TOKENS:-8}"
RR_TENV="${RR_TENV:-4}"
LI_INSTANCES="${LI_INSTANCES:-8}"
LI_TENV="${LI_TENV:-4}"
C_GRID="${C_GRID:-1 2 4 8}"
mkdir -p "$OUT_DIR"
[ -f "$MANIFEST" ] || { echo "NOT DONE — subset manifest missing: $MANIFEST (run the build first)"; exit 1; }
echo "winners in use (from the posture ruling): RR M=${RR_TOKENS} T=${RR_TENV}; LI N=${LI_INSTANCES} T=${LI_TENV}; C grid: ${C_GRID}"

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

teardown() {
  docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
  touch "$OUT_DIR/memwatch.stop" 2>/dev/null || true
}
trap teardown EXIT

point() { # $1=probe-args $2=C $3=containers $4=label
  echo "---- point $4 C=$2 ----"
  rm -f "$OUT_DIR/memwatch.stop"
  "$PY" working/video/probe/mem_watch.py --containers "$3" \
      --spool-path /tmp --duration-s 14400 \
      --stop-file "$OUT_DIR/memwatch.stop" \
      --out "$OUT_DIR/memwatch_$4_C$2" &
  local mw=$!
  local rc=0
  # shellcheck disable=SC2086
  "$PY" working/video/probe/probe_films_curve.py $1 --concurrency "$2" \
      --manifest "$MANIFEST" --containers "$3" --out-dir "$OUT_DIR" || rc=$?
  touch "$OUT_DIR/memwatch.stop"
  wait "$mw" || true
  return "$rc"
}

echo "== posture rr-default (control: C measures queueing on M=1) =="
docker rm -f rr >/dev/null 2>&1 || true
docker run -d --name rr --memory 58g --log-opt max-size=200m --network host \
    rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
for c in 1 2; do
  point "--cell rr-default" "$c" rr rr-default \
    || echo "POINT rr-default C=$c FAILED (rc=$?) — recorded; sweep continues"
done
docker rm -f rr >/dev/null 2>&1 || true

echo "== ruled RR posture (M=${RR_TOKENS} x T=${RR_TENV}), full C sweep =="
# shellcheck disable=SC2086
docker run -d --name rr --memory 58g $(envargs "$RR_TENV") --log-opt max-size=200m \
    --network host rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
# shellcheck disable=SC2086
for c in $C_GRID; do
  point "--arm rr --tokens $RR_TOKENS --threads-env $RR_TENV --batch heads" \
      "$c" rr "rr_M${RR_TOKENS}xT${RR_TENV}" \
    || echo "POINT rr C=$c FAILED (rc=$?) — recorded; sweep continues"
done
docker rm -f rr >/dev/null 2>&1 || true

echo "== ruled LI posture (N=${LI_INSTANCES} x T=${LI_TENV}), full C sweep =="
NAMES=""
MEM=$([ "$LI_INSTANCES" -ge 16 ] && echo 3g || echo 7g)
for i in $(seq 0 $((LI_INSTANCES - 1))); do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory "$MEM" $(envargs "$LI_TENV") \
      -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  NAMES="$NAMES,li_bal_$i"
done
NAMES="${NAMES#,}"
for i in $(seq 0 $((LI_INSTANCES - 1))); do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done
# shellcheck disable=SC2086
for c in $C_GRID; do
  point "--arm li --instances $LI_INSTANCES --threads-env $LI_TENV --batch heads" \
      "$c" "$NAMES" "li_N${LI_INSTANCES}xT${LI_TENV}" \
    || echo "POINT li C=$c FAILED (rc=$?) — recorded; sweep continues"
done
for i in $(seq 0 $((LI_INSTANCES - 1))); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done

echo "== curve =="
"$PY" working/video/probe/probe_films_curve.py --summarize "$OUT_DIR"
echo "DONE — artifacts in $OUT_DIR. Bundle them; entry 26: STOP-AND-LAND —"
echo "nothing else pushes until the bundle is fetched and ls-remote confirms."
