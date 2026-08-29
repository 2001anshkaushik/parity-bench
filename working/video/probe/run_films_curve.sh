#!/usr/bin/env bash
# =============================================================================
# Films concurrency sweep (RULING I, 2026-08-28). Committed script +
# self-printed sha256 per register entry 25.
#
# Points: rr-8x4 and li-8x4 at C in {1,2,4,8} (the headline cells get the
# full sweep); rr-default at C in {1,2} only (M=1 by definition — C above 1
# measures queueing at the single reader lock, worth a control, not four
# points). Every point runs the SAME 9-film batch (strata-cell heads from
# OUR subset manifest's meta — fixed workload, variable C) with the FIXED
# mem_watch beside it; posture env read-backs fail closed inside the probe.
#
# Ends with probe_films_curve.py --summarize: the curve table, marginal
# efficiency per step ([T(C)/T(prev)]/[C/prev], knee < 0.7 — the
# probe_concurrency rule verbatim), and marginal GB per active lane.
# C IS NOT PICKED HERE — Ansh rules from the printed curve.
#
# Estimated cost (stated before the run; single-lane realtime factors
# measured 44.6/31.8/34.7 on grapes): batch footage ~12.5 h -> rr-8x4
# ~50-65 min over 4 points, li-8x4 ~45-60 min, rr-default ~35 min over 2,
# bring-ups ~15 min => ~2.5-3.5 h wall. Disk: no new fetches (subset on
# disk); transient rr /tmp spool up to ~5-7 GB at C=8.
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
mkdir -p "$OUT_DIR"
[ -f "$MANIFEST" ] || { echo "NOT DONE — subset manifest missing: $MANIFEST (run the build first)"; exit 1; }

ENVARGS4="-e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 \
-e VECLIB_MAXIMUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TORCH_NUM_THREADS=4"

teardown() {
  docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in 0 1 2 3 4 5 6 7; do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
  touch "$OUT_DIR/memwatch.stop" 2>/dev/null || true
}
trap teardown EXIT

point() { # $1=cell $2=C $3=containers-csv
  local cell="$1" c="$2" containers="$3"
  echo "---- point $cell C=$c ----"
  rm -f "$OUT_DIR/memwatch.stop"
  "$PY" working/video/probe/mem_watch.py --containers "$containers" \
      --spool-path /tmp --duration-s 14400 \
      --stop-file "$OUT_DIR/memwatch.stop" \
      --out "$OUT_DIR/memwatch_${cell}_C${c}" &
  local mw=$!
  local rc=0
  "$PY" working/video/probe/probe_films_curve.py --cell "$cell" \
      --concurrency "$c" --manifest "$MANIFEST" \
      --containers "$containers" --out-dir "$OUT_DIR" || rc=$?
  touch "$OUT_DIR/memwatch.stop"
  wait "$mw" || true
  return "$rc"
}

echo "== posture rr-default (control: C measures queueing on M=1) =="
docker rm -f rr >/dev/null 2>&1 || true
docker run -d --name rr --memory 58g --log-opt max-size=200m --network host \
    rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
for c in 1 2; do point rr-default "$c" rr; done
docker rm -f rr >/dev/null 2>&1 || true

echo "== posture rr-8x4 (full sweep) =="
# shellcheck disable=SC2086
docker run -d --name rr --memory 58g $ENVARGS4 --log-opt max-size=200m \
    --network host rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
for c in 1 2 4 8; do point rr-8x4 "$c" rr; done
docker rm -f rr >/dev/null 2>&1 || true

echo "== posture li-8x4 (full sweep) =="
NAMES=""
for i in 0 1 2 3 4 5 6 7; do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory 7g $ENVARGS4 -e WS1V_WORKERS=1 \
      --log-opt max-size=200m --network host --entrypoint sh li:video -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  NAMES="$NAMES,li_bal_$i"
done
NAMES="${NAMES#,}"
for i in 0 1 2 3 4 5 6 7; do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done
for c in 1 2 4 8; do point li-8x4 "$c" "$NAMES"; done
for i in 0 1 2 3 4 5 6 7; do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done

echo "== curve =="
"$PY" working/video/probe/probe_films_curve.py --summarize "$OUT_DIR"
echo "DONE — artifacts in $OUT_DIR. Bundle them; entry 26: STOP-AND-LAND —"
echo "nothing else pushes until the bundle is fetched and ls-remote confirms."
