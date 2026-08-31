#!/usr/bin/env bash
# =============================================================================
# RULING N reissue on the MEASURED batch (2026-08-31): rr_M16xT2 and
# li_N16xT2 at C in {8, 16, 32} — three points per arm. The heads batch
# (9 films) caps in-flight at 9, so its C=16/32 points were the same
# experiment twice and their marginal rows were arithmetic on concurrency
# that never happened; the summarizer now refuses that class. The heads
# C=1..8 points are SOUND and are NOT re-run.
#
# RULING N, recorded: option 1 over the full measured chain — option 2's
# 10-14 h is dominated by C=1 re-measuring single-lane throughput already
# held; this run costs ~2.5-3 h and additionally yields the first
# same-corpus repeatability pairs at the ruled postures (its C=32 reruns
# vs the posture sweep's measured-batch C=32: rr 8.65 / li 10.071 f/s).
# The knee region is already bracketed from BELOW by honest saturated
# steps (heads marg-eff RR 0.805/0.725/0.598, LI 0.846/0.736/0.627 at
# C=2/4/8 — both cross 0.7 between C=4 and C=8); this run brackets it
# from above. THE C=8 ADDITION prices the batch change directly:
# measured-C=8 vs heads-C=8 at the same posture (heads: RR 5.435, LI
# 6.349 f/s — CORRECTED 2026-08-31 post-run: the ruling relay had 6.636
# here, which is the heads-C=16 figure; the box artifacts adjudicated;
# the measured result was RR 8.21 / LI 9.569 = the ~34% batch finding)
# — without it the measured chain would share no C with the
# heads chain and the batch difference would stay unmeasured. FLAGGED IN
# ADVANCE (Ansh): the 9 heads are the largest-bytes film per stratum and
# may be systematically slower per frame than the full 35 — measured-C=8
# landing well above heads-C=8 is a BATCH-COMPOSITION finding for the
# report, not noise.
#
# METHODOLOGY, recorded: heads (9 films / 12.59 h) and measured (35 films
# / 49.33 h) are DIFFERENT WORKLOADS — one marginal chain must never span
# both (a cross-batch step confounds delta-C with delta-content); the
# summarizer groups chains by (label, batch) structurally. These six
# points form measured-batch chains with two marginal steps (8->16->32).
#
# OUT_DIR defaults to ~/films_probe/curve_hi_out — SEPARATE from curve_out
# so no heads-era artifact or memwatch file is moved aside or overwritten
# (entry 7: the quotable command must not clobber evidence).
# Committed script + self-printed sha256 per register entry 25.
# Expected wall ~2.5-3 h (11,841 frames per point; C=16/32 at ~8-10 f/s =>
# ~20-26 min/point, C=8 at ~6-8 f/s => ~25-33 min/point, + two bring-ups).
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

echo "== rr M16xT2, measured batch, C in {8, 16, 32} =="
docker rm -f rr >/dev/null 2>&1 || true
# shellcheck disable=SC2086
docker run -d --name rr --memory 58g $(envargs 2) --log-opt max-size=200m \
    --network host rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
for c in 8 16 32; do
  point "--arm rr --tokens 16 --threads-env 2 --batch measured" "$c" rr rr_M16xT2 \
    || echo "POINT rr C=$c FAILED (rc=$?) — recorded; sweep continues"
done
docker rm -f rr >/dev/null 2>&1 || true

echo "== li N16xT2, measured batch, C in {8, 16, 32} =="
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
for c in 8 16 32; do
  point "--arm li --instances 16 --threads-env 2 --batch measured" "$c" "$NAMES" li_N16xT2 \
    || echo "POINT li C=$c FAILED (rc=$?) — recorded; sweep continues"
done
for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done

echo "== high-C chains (measured batch) =="
"$PY" working/video/probe/probe_films_curve.py --summarize "$OUT_DIR"
echo "DONE — artifacts in $OUT_DIR (heads-era curve_out untouched)."
echo "Entry 26: STOP-AND-LAND — bundle before anything else pushes."
