#!/usr/bin/env bash
# FINAL APPLES-TO-APPLES SESSION (Task 5, 2026-08-25 — runs only after Ansh
# approves). Six legs, n=168, C=16, fresh containers per leg:
#   1. RR  8x4  p1      4. LI-bal 8x4  p2
#   2. LI-bal 8x4 p1    5. LI-bal 16x2 p1
#   3. RR  8x4  p2      6. LI-bal 16x2 p2
# ORDER RATIONALE: the head-to-head cell (8x4) is INTERLEAVED across arms so
# slow drift (thermal, cache, time-of-day) lands on both arms equally; the LI
# 16x2 pair runs as a block at the end because its RR counterpart (16x2) is
# BANKED from an earlier session — flagged in the report as a cross-session
# comparison. Fresh containers per leg make interleaving cost nothing extra.
# Continues past a failed leg; wrapper flock + the driver's per-arm flock.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/parity-bench-video")"
PY="${PYBIN:-$HOME/.venv/bin/python}"
LOCK="${TMPDIR:-/tmp}/overnight_apples.lock"; exec 9>"$LOCK"
flock -n 9 || { echo "NOT DONE — another apples session holds $LOCK"; exit 1; }
grep -q "resolve_service_containers" working/video/driver_video.py || {
  echo "NOT DONE — driver predates the multi-instance collector fix; pull first"; exit 1; }
OUT="working/video/results/apples_$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
LOG="$OUT/session.log"
LIN_RR="$( "$PY" - working/video/results <<'EOF'
import glob, json, sys
def walk(n):
    if isinstance(n, dict):
        if 'lineage_declared' in n: yield n['lineage_declared']
        for v in n.values(): yield from walk(v)
    elif isinstance(n, list):
        for v in n: yield from walk(v)
vals = {v for f in glob.glob(sys.argv[1] + '/mainrun_*/export_rocketride_*.json')
        for v in walk(json.load(open(f))) if v}
print(sorted(vals)[-1] if vals else 'UNKNOWN — no banked RR export on this box')
EOF
)"
LIN_LI="docker/Dockerfile.llamaindex-video REBUILT 2026-08-25 (device-only stage stamps); N single-worker instances, driver round-robin (LI-balanced posture)"
echo "RR lineage: ${LIN_RR:0:60}..." | tee -a "$LOG"

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

rr_leg() { # $1=M $2=T $3=pass
  local M="$1" T="$2" P="$3" tag="rr_${1}x${2}_p$3"
  echo "=== $tag: fresh rr, M=$M six-vars=$T ===" | tee -a "$LOG"
  docker rm -f rr >/dev/null 2>&1 || true
  # shellcheck disable=SC2046
  docker run -d --name rr --memory 58g $(envargs "$T") --log-opt max-size=200m \
      --network host rr:patched-video >/dev/null
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr 2>&1 | tee -a "$LOG" || { R+=("$tag: NOT READY"); docker rm -f rr >/dev/null 2>&1; return; }
  "$PY" working/video/driver_video.py --arm rocketride --posture parity --leg blast \
      --n 168 --blast-concurrency 16 --tokens "$M" --rr-threads-env "$T" --pass "$P" \
      --image-lineage "$LIN_RR" --out-dir "$OUT" 2>&1 | tee -a "$LOG"
  R+=("$tag: rc=${PIPESTATUS[0]}"); docker logs rr > "$OUT/dockerlog_$tag.txt" 2>&1 || true
  docker rm -f rr >/dev/null 2>&1 || true
}

li_leg() { # $1=N instances $2=T $3=pass
  local N="$1" T="$2" P="$3" tag="li_${1}x${2}_p$3" MEM PORTS="" NAMES=""
  MEM=$([ "$N" -ge 16 ] && echo 3g || echo 7g)
  echo "=== $tag: $N fresh single-worker instances, torch=$T, ${MEM}/instance ===" | tee -a "$LOG"
  for i in $(seq 0 $((N-1))); do
    local PT=$((8802+i)); PORTS="$PORTS,$PT"; NAMES="$NAMES,li_bal_$i"
    docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
    # shellcheck disable=SC2046
    docker run -d --name "li_bal_$i" --memory "$MEM" $(envargs "$T") -e WS1V_WORKERS=1 \
        --log-opt max-size=200m --network host --entrypoint sh li:video -c \
        "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $PT --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  done
  PORTS="${PORTS#,}"; NAMES="${NAMES#,}"
  for i in $(seq 0 $((N-1))); do
    "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) --workers 1 \
        --container "li_bal_$i" --deadline 1200 2>&1 | tee -a "$LOG" \
      || { R+=("$tag: instance $i NOT READY"); return; }
  done
  "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n 168 \
      --blast-concurrency 16 --li-ports "$PORTS" --li-containers "$NAMES" --pass "$P" \
      --image-lineage "$LIN_LI" --out-dir "$OUT" 2>&1 | tee -a "$LOG"
  R+=("$tag: rc=${PIPESTATUS[0]}")
  for i in $(seq 0 $((N-1))); do
    docker logs "li_bal_$i" > "$OUT/dockerlog_${tag}_i$i.txt" 2>&1 || true
    docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  done
}

declare -a R=()
rr_leg 8 4 1
li_leg 8 4 1
rr_leg 8 4 2
li_leg 8 4 2
li_leg 16 2 1
li_leg 16 2 2

echo "=== APPLES SESSION SUMMARY ===" | tee -a "$LOG"
BAD=0; for r in "${R[@]}"; do echo "  $r" | tee -a "$LOG"; case "$r" in *rc=0) ;; *) BAD=1;; esac; done
echo "results in $OUT — cross-gates next; RR 16x2 counterpart is BANKED (cross-session, flagged)" | tee -a "$LOG"
exit "$BAD"
