#!/usr/bin/env bash
# =============================================================================
# Films POSTURE sweep (RULING K, 2026-08-28): M x thread-env for RocketRide,
# N x thread-env for LlamaIndex, C >= lanes at every point — the sweep that
# finds each arm's configuration on Films, run BEFORE the C sweep (M x
# threads sets the posture; C then saturates it; sweeping C first risks
# finding the knee for a posture we abandon). Committed script +
# self-printed sha256 per register entry 25.
#
# Batch: the FULL measured 35 (49.33 h footage) — a 9-film batch cannot
# saturate M>=16 lanes. C per point = min(2 x lanes, 35): C >= M ruled
# (single-lane points were exactly the artifact that made rr-8x4 look
# slower than rr-default); 2x keeps lanes fed through stragglers; capped by
# item count. Every point: posture env read-back fail-closed in the probe,
# fixed mem_watch beside it (per-instance peak anon + memory.peak — the
# 8.10 GB single-lane figure is still unextrapolated), warm rows
# structurally excluded.
#
# RR grid (M x T, spend = M*T vs 32 vCPU), each point's reason:
#   8x4   full-spend — the AMI headline shape; the cross-regime anchor
#   16x2  full-spend — AMI's FASTER measured point (12.73 vs 11.63); the
#         first question is whether that ordering survives 1080p decode
#   32x1  full-spend, max lanes — Crossroad 30's AMI direction; also the
#         memory-envelope stress point (M x 0.94 GB baseline)
#   4x8   full-spend, threads-heavy — AMI measured it losing (0.1179 vs
#         0.1417); films' heavier per-item decode re-asks the question
#   8x2   UNDER-spend (16 of 32) — prices the spend: if ~= 8x4, the extra
#         threads were contention, not work
#   16x4  OVER-subscribe (64 of 32) — measures how much oversubscription
#         costs on films; one point, cut first on budget
# LI grid (N single-worker instances x T; W stays 1 — the W dimension was
# measured pathological at AMI (kernel-accept skew, LI_SERVING_SKEW ruling)
# and balanced mode superseded it; re-sweeping a known-bad axis buys nothing):
#   8x4 full-spend (AMI headline) | 16x2 full-spend, instance-heavy |
#   4x8 full-spend, threads-heavy | 8x2 under-spend | 8x8 over-subscribe
#   (cut first on budget)
#
# Budget lever: SKIP_OVERSUB=1 skips 16x4 and 8x8 (grid points, never
# passes — Ansh's preference). Est. total ~4.5-5.5 h with them, ~4 h
# without; disk: no new fetches; rr /tmp transient spool up to ~28 GB at
# C=35 (all in flight), LI spool spread across instances.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_films_posture.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PY:-$HOME/.venv-floor/bin/python3}"
MANIFEST="${MANIFEST:-working/video/films_video_manifest.jsonl}"
OUT_DIR="${OUT_DIR:-$HOME/films_probe/posture_out}"
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

point() { # $1=arm $2=lanes-flag+value $3=T $4=C $5=containers $6=label
  echo "---- point $6 C=$4 ----"
  rm -f "$OUT_DIR/memwatch.stop"
  "$PY" working/video/probe/mem_watch.py --containers "$5" \
      --spool-path /tmp --duration-s 14400 \
      --stop-file "$OUT_DIR/memwatch.stop" \
      --out "$OUT_DIR/memwatch_$6_C$4" &
  local mw=$!
  local rc=0
  # shellcheck disable=SC2086
  "$PY" working/video/probe/probe_films_curve.py --arm "$1" $2 \
      --threads-env "$3" --batch measured --concurrency "$4" \
      --manifest "$MANIFEST" --containers "$5" --out-dir "$OUT_DIR" || rc=$?
  touch "$OUT_DIR/memwatch.stop"
  wait "$mw" || true
  return "$rc"
}

rr_point() { # $1=M $2=T $3=C
  docker rm -f rr >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name rr --memory 58g $(envargs "$2") --log-opt max-size=200m \
      --network host rr:patched-video >/dev/null
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  point rr "--tokens $1" "$2" "$3" rr "rr_M$1xT$2"
  docker rm -f rr >/dev/null 2>&1 || true
}

li_point() { # $1=N $2=T $3=C
  local n="$1" mem names="" i
  mem=$([ "$n" -ge 16 ] && echo 3g || echo 7g)   # overnight_apples MEM rule
  for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
  for i in $(seq 0 $((n - 1))); do
    # shellcheck disable=SC2086
    docker run -d --name "li_bal_$i" --memory "$mem" $(envargs "$2") \
        -e WS1V_WORKERS=1 --log-opt max-size=200m --network host \
        --entrypoint sh li:video -c \
        "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
    names="$names,li_bal_$i"
  done
  names="${names#,}"
  for i in $(seq 0 $((n - 1))); do
    "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
        --workers 1 --container "li_bal_$i" --deadline 1200
  done
  point li "--instances $n" "$2" "$3" "$names" "li_N$1xT$2"
  for i in $(seq 0 $((n - 1))); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
}

# A failed point is RECORDED AND THE SWEEP CONTINUES (2026-08-30 fix): the
# probe writes a FAILED artifact with the exception chain and the OOM state
# (docker OOMKilled + cgroup memory.events oom_kill delta), mem_watch's last
# ticks carry the anon at failure, and earlier points are already on disk —
# an OOM at the 32x1 stress point is a FINDING, never a crashed sweep.
echo "== RocketRide posture grid (M x T, C = min(2M, 35)) =="
rr_point 8 4 16   || echo "POINT rr_M8xT4 FAILED (rc=$?) — recorded; sweep continues"
rr_point 16 2 32  || echo "POINT rr_M16xT2 FAILED (rc=$?) — recorded; sweep continues"
rr_point 32 1 35  || echo "POINT rr_M32xT1 FAILED (rc=$?) — recorded; sweep continues"
rr_point 4 8 8    || echo "POINT rr_M4xT8 FAILED (rc=$?) — recorded; sweep continues"
rr_point 8 2 16   || echo "POINT rr_M8xT2 FAILED (rc=$?) — recorded; sweep continues"
if [ "${SKIP_OVERSUB:-0}" != "1" ]; then
  rr_point 16 4 32 || echo "POINT rr_M16xT4 FAILED (rc=$?) — recorded; sweep continues"
else echo "SKIP rr 16x4 (SKIP_OVERSUB=1)"; fi

echo "== LlamaIndex posture grid (N x T, W=1, C = min(2N, 35)) =="
li_point 8 4 16   || echo "POINT li_N8xT4 FAILED (rc=$?) — recorded; sweep continues"
li_point 16 2 32  || echo "POINT li_N16xT2 FAILED (rc=$?) — recorded; sweep continues"
li_point 4 8 8    || echo "POINT li_N4xT8 FAILED (rc=$?) — recorded; sweep continues"
li_point 8 2 16   || echo "POINT li_N8xT2 FAILED (rc=$?) — recorded; sweep continues"
if [ "${SKIP_OVERSUB:-0}" != "1" ]; then
  li_point 8 8 16 || echo "POINT li_N8xT8 FAILED (rc=$?) — recorded; sweep continues"
else echo "SKIP li 8x8 (SKIP_OVERSUB=1)"; fi

echo "== posture matrix =="
"$PY" working/video/probe/probe_films_curve.py --summarize "$OUT_DIR"
echo "DONE — artifacts in $OUT_DIR. Bundle them; entry 26: STOP-AND-LAND —"
echo "nothing else pushes until the bundle is fetched and ls-remote confirms."
echo "The C sweep (run_films_curve.sh) runs AFTER Ansh rules the postures"
echo "from this matrix, with RR_TOKENS/RR_TENV/LI_INSTANCES/LI_TENV set."
