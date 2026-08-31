#!/usr/bin/env bash
# =============================================================================
# High-C reissue on the MEASURED batch (2026-08-31): ONLY the four points the
# 9-film heads batch could not saturate — rr_M16xT2 and li_N16xT2 at C=16
# and C=32. The heads batch caps in-flight at 9, so the heads C=16/32 points
# were the same experiment twice (inflight max 9 at both) and their marginal
# rows were arithmetic on concurrency that never happened; the summarizer
# now refuses those (MARG NOT MEASURED / knee NOT DETERMINED) instead of
# printing them. The heads C=1..8 points are SOUND and are NOT re-run.
#
# METHODOLOGY, recorded: heads (9 films / 12.59 h) and measured (35 films /
# 49.33 h) are DIFFERENT WORKLOADS — one marginal chain must never span
# both (a cross-batch step confounds delta-C with delta-content), and
# summarize now groups chains by (label, batch) structurally. These four
# points form their own measured-batch chains with one marginal step each
# (16->32). Bonus evidence: their C=32 rows pair with the posture sweep's
# measured-batch C=32 points at the same postures (rr 8.65 / li 10.071 f/s)
# — the first same-corpus repeatability pairs at the ruled postures.
#
# OUT_DIR defaults to ~/films_probe/curve_hi_out — SEPARATE from curve_out
# so no heads-era artifact or memwatch file is moved aside or overwritten
# (entry 7: the quotable command must not clobber evidence).
# Committed script + self-printed sha256 per register entry 25.
# Expected wall ~1.5-2 h (est.: 11,841 frames per point at near-peak rates
# ~8-10 f/s => ~20-26 min/point, + two bring-ups).
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_films_curve_highc.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PY:-$HOME/.venv-floor/bin/python3}"
MANIFEST="${MANIFEST:-working/video/films_video_manifest.jsonl}"
OUT_DIR="${OUT_DIR:-$HOME/films_probe/curve_hi_out}"
mkdir -p "$OUT_DIR"
[ -f "$MANIFEST" ] || { echo "NOT DONE — subset manifest missing: $MANIFEST (run the build first)"; exit 1; }

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

teardown() {
  docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
  touch "$OUT_DIR/memwatch.stop" 2>/dev/null || true
}
trap teardown EXIT

point() { # $1=probe-args $2=C $3=containers $4=label
  echo "---- point $4 C=$2 (measured batch) ----"
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

echo "== rr M16xT2, measured batch, C in {16, 32} =="
docker rm -f rr >/dev/null 2>&1 || true
# shellcheck disable=SC2086
docker run -d --name rr --memory 58g $(envargs 2) --log-opt max-size=200m \
    --network host rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
for c in 16 32; do
  point "--arm rr --tokens 16 --threads-env 2 --batch measured" "$c" rr rr_M16xT2 \
    || echo "POINT rr C=$c FAILED (rc=$?) — recorded; sweep continues"
done
docker rm -f rr >/dev/null 2>&1 || true

echo "== li N16xT2, measured batch, C in {16, 32} =="
NAMES=""
for i in $(seq 0 15); do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory 3g $(envargs 2) \
      -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  NAMES="$NAMES,li_bal_$i"
done
NAMES="${NAMES#,}"
for i in $(seq 0 15); do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done
for c in 16 32; do
  point "--arm li --instances 16 --threads-env 2 --batch measured" "$c" "$NAMES" li_N16xT2 \
    || echo "POINT li C=$c FAILED (rc=$?) — recorded; sweep continues"
done
for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done

echo "== high-C chains (measured batch) =="
"$PY" working/video/probe/probe_films_curve.py --summarize "$OUT_DIR"
echo "DONE — artifacts in $OUT_DIR (heads-era curve_out untouched)."
echo "Entry 26: STOP-AND-LAND — bundle before anything else pushes."
