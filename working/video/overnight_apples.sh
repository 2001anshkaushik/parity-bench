#!/usr/bin/env bash
# FINAL APPLES-TO-APPLES SESSION (2026-08-25, executive ruling — SIX legs),
# n=168, C=16, fresh containers per leg. HEADLINE = 8x4 both arms (cross-team
# consensus: 8 instances, with Leela and Shashi), n=2, interleaved across arms.
# 16x2 legs are CEILING PROOFS, n=1, supporting data only, blocked at the end;
# the queue-depth asymmetry at 8x4 (LI 2-deep at C=16, RR 1-deep) is a STATED
# CAVEAT quantified by the ceiling cells. Collector fix (7c1cd81) and hashing
# locus fix (00b86e1) required — this refuses a driver without them.
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
grep -q "hashing_locus" working/video/driver_video.py || {
  echo "NOT DONE — driver predates the hashing-locus fix (00b86e1); pull first"; exit 1; }
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

li_set() { # $1=N -> sets PORTS and NAMES (the ONE source; bring-up, driver argv
  # and plan_check all read these, so they cannot disagree — 2026-08-25)
  PORTS=""; NAMES=""
  local i; for i in $(seq 0 $(( $1 - 1 ))); do
    PORTS="$PORTS,$((8802+i))"; NAMES="$NAMES,li_bal_$i"
  done
  PORTS="${PORTS#,}"; NAMES="${NAMES#,}"
}

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

start_rr_set() { # $1=T — ONE bring-up used by legs AND the dry preflight
  docker rm -f rr >/dev/null 2>&1 || true
  # shellcheck disable=SC2046
  docker run -d --name rr --memory 58g $(envargs "$1") --log-opt max-size=200m \
      --network host rr:patched-video >/dev/null
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
}
stop_rr_set() { docker rm -f rr >/dev/null 2>&1 || true; }

start_li_set() { # $1=N $2=T — ONE bring-up used by legs AND the dry preflight
  li_set "$1"
  local MEM; MEM=$([ "$1" -ge 16 ] && echo 3g || echo 7g)
  local i
  for i in $(seq 0 $(( $1 - 1 ))); do
    docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
    # shellcheck disable=SC2046
    docker run -d --name "li_bal_$i" --memory "$MEM" $(envargs "$2") -e WS1V_WORKERS=1 \
        --log-opt max-size=200m --network host --entrypoint sh li:video -c \
        "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  done
  for i in $(seq 0 $(( $1 - 1 ))); do
    "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) --workers 1 \
        --container "li_bal_$i" --deadline 1200 || return 1
  done
}
stop_li_set() { local i; for i in $(seq 0 $(( $1 - 1 ))); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done; }

rr_leg() { # $1=M $2=T $3=pass
  local M="$1" T="$2" P="$3" tag="rr_${1}x${2}_p$3"
  case " ${SKIP:-} " in *" $tag "*) echo "=== $tag SKIPPED (banked) ===" | tee -a "$LOG"; R+=("$tag: SKIPPED (banked)"); return;; esac
  echo "=== $tag: fresh rr, M=$M six-vars=$T ===" | tee -a "$LOG"
  start_rr_set "$T" 2>&1 | tee -a "$LOG" || { R+=("$tag: NOT READY"); stop_rr_set; return; }
  "$PY" working/video/driver_video.py --arm rocketride --posture parity --leg blast \
      --n 168 --blast-concurrency 16 --tokens "$M" --rr-threads-env "$T" --pass "$P" \
      --image-lineage "$LIN_RR" --out-dir "$OUT" 2>&1 | tee -a "$LOG"
  R+=("$tag: rc=${PIPESTATUS[0]}"); docker logs rr > "$OUT/dockerlog_$tag.txt" 2>&1 || true
  stop_rr_set
}

li_leg() { # $1=N instances $2=T $3=pass
  local N="$1" T="$2" P="$3" tag="li_${1}x${2}_p$3" MEM
  case " ${SKIP:-} " in *" $tag "*) echo "=== $tag SKIPPED (banked) ===" | tee -a "$LOG"; R+=("$tag: SKIPPED (banked)"); return;; esac
  echo "=== $tag: $N fresh single-worker instances, torch=$T ===" | tee -a "$LOG"
  start_li_set "$N" "$T" 2>&1 | tee -a "$LOG" || { R+=("$tag: instance NOT READY"); stop_li_set "$N"; return; }
  li_set "$N"
  "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n 168 \
      --blast-concurrency 16 --li-ports "$PORTS" --li-containers "$NAMES" --pass "$P" \
      --image-lineage "$LIN_LI" --out-dir "$OUT" 2>&1 | tee -a "$LOG"
  R+=("$tag: rc=${PIPESTATUS[0]}")
  local i; for i in $(seq 0 $((N-1))); do
    docker logs "li_bal_$i" > "$OUT/dockerlog_${tag}_i$i.txt" 2>&1 || true
  done
  stop_li_set "$N"
}

echo "=== LEG ORDER (verify the interleave BEFORE it runs) ===" | tee -a "$LOG"
cat <<'ORDER' | tee -a "$LOG"
  1. RR     8x4  p1   <- HEADLINE cell (executive ruling), interleaved across arms
  2. LI-bal  8x4 p1
  3. RR     8x4  p2
  4. LI-bal  8x4 p2
  5. RR    16x2  p1   <- CEILING PROOF, n=1, supporting data only (blocked)
  6. LI-bal 16x2 p1
ORDER
echo "=== PLAN CHECK (minute zero — every leg validated before any leg runs) ===" | tee -a "$LOG"
PLAN_FAIL=0
for spec in "rr:8:4:1" "li:8:4:1" "rr:8:4:2" "li:8:4:2" "rr:16:2:1" "li:16:2:1"; do
  IFS=: read -r A_ARM A_N A_T A_P <<EOF2
$spec
EOF2
  tag="${A_ARM}_${A_N}x${A_T}_p${A_P}"
  case " ${SKIP:-} " in *" $tag "*) echo "  $tag: SKIP (banked)" | tee -a "$LOG"; continue;; esac
  if [ "$A_ARM" = "li" ]; then
    li_set "$A_N"
    NP=$(echo "$PORTS" | tr ',' '\n' | grep -c .); NN=$(echo "$NAMES" | tr ',' '\n' | grep -c .)
    if [ "$NP" != "$A_N" ] || [ "$NN" != "$A_N" ] || [ "$NP" != "$NN" ]; then
      echo "  $tag: FAIL — ports($NP)/containers($NN) disagree with N=$A_N" | tee -a "$LOG"; PLAN_FAIL=1
    else
      echo "  $tag: ok — $A_N ports + $A_N containers, --li-ports/--li-containers both present" | tee -a "$LOG"
    fi
  else
    echo "  $tag: ok — tokens=$A_N env=$A_T" | tee -a "$LOG"
  fi
done
docker image inspect rr:patched-video >/dev/null 2>&1 || { echo "  FAIL — image rr:patched-video missing" | tee -a "$LOG"; PLAN_FAIL=1; }
"$PY" working/video/corpus_locator.py --manifest working/video/ami_video_manifest.jsonl --tool plan_check >/dev/null || { echo "  FAIL — corpus_dir unresolved" | tee -a "$LOG"; PLAN_FAIL=1; }
"$PY" -c "
import sys; sys.path.insert(0,'working'); sys.path.insert(0,'working/video')
import driver_video as d
d.resolve_service_containers('llamaindex','rr','li_video', ','.join(f'li_bal_{i}' for i in range(8)), 8)
d.resolve_service_containers('llamaindex','rr','li_video', ','.join(f'li_bal_{i}' for i in range(16)), 16)
try:
    d.resolve_service_containers('llamaindex','rr','li_video', None, 8); sys.exit(1)
except SystemExit as e:
    sys.exit(0 if 'NOT DONE' in str(e) else 1)
" || { echo "  FAIL — driver service-set resolution not behaving" | tee -a "$LOG"; PLAN_FAIL=1; }
[ "$PLAN_FAIL" = 0 ] || { echo "PLAN CHECK FAILED — refusing to start (fail at minute zero, not forty)" | tee -a "$LOG"; exit 1; }
echo "shape checks passed — now the REAL preflights (2026-08-26: both failures passed the"
echo "old plan check and died at minute 40 in a preflight it never exercised)" | tee -a "$LOG"
dry_pf() { # $1=arm $2=N $3=T  — bring up via the SAME functions the legs use,
  # run the driver's ACTUAL preflight (--preflight-only), tear down.
  if [ "$1" = rr ]; then
    start_rr_set "$3" >>"$LOG" 2>&1 || { echo "  dry-preflight rr: BRING-UP FAILED" | tee -a "$LOG"; return 1; }
    "$PY" working/video/driver_video.py --arm rocketride --posture parity --leg blast \
        --n 168 --blast-concurrency 16 --tokens "$2" --rr-threads-env "$3" --pass 1 \
        --image-lineage "dry preflight" --out-dir "$OUT/dry_pf" --preflight-only 2>&1 | tail -3 | tee -a "$LOG"
    local rc=${PIPESTATUS[0]}; stop_rr_set; return "$rc"
  else
    start_li_set "$2" "$3" >>"$LOG" 2>&1 || { echo "  dry-preflight li($2): BRING-UP FAILED" | tee -a "$LOG"; stop_li_set "$2"; return 1; }
    li_set "$2"
    "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n 168 \
        --blast-concurrency 16 --li-ports "$PORTS" --li-containers "$NAMES" --pass 1 \
        --image-lineage "dry preflight" --out-dir "$OUT/dry_pf" --preflight-only 2>&1 | tail -3 | tee -a "$LOG"
    local rc=${PIPESTATUS[0]}; stop_li_set "$2"; return "$rc"
  fi
}
for shape in "rr:8:4" "li:8:4" "rr:16:2" "li:16:2"; do
  IFS=: read -r D_ARM D_N D_T <<EOF3
$shape
EOF3
  case " ${SKIP:-} " in
    *" ${D_ARM}_${D_N}x${D_T}_p1 "*) [ "${D_ARM}" = rr ] && echo "  dry-preflight $shape: leg skipped; still exercising shape" | tee -a "$LOG";;
  esac
  echo "  dry-preflight $shape ..." | tee -a "$LOG"
  dry_pf "$D_ARM" "$D_N" "$D_T" || { echo "PLAN CHECK FAILED at REAL preflight for $shape — refusing the session" | tee -a "$LOG"; exit 1; }
done
echo "PLAN CHECK PASSED — argv shapes AND real preflights, all legs validated" | tee -a "$LOG"

echo "rebuilding li:video (hashing-locus change is baked into the image)" | tee -a "$LOG"
docker build -q -t li:video -f docker/Dockerfile.llamaindex-video . | tee -a "$LOG"

declare -a R=()
rr_leg 8 4 1
li_leg 8 4 1
rr_leg 8 4 2
li_leg 8 4 2
rr_leg 16 2 1
li_leg 16 2 1

echo "=== APPLES SESSION SUMMARY ===" | tee -a "$LOG"
BAD=0; for r in "${R[@]}"; do echo "  $r" | tee -a "$LOG"; case "$r" in *rc=0) ;; *) BAD=1;; esac; done
echo "results in $OUT — headline 8x4 n=2 interleaved; 16x2 = ceiling proofs n=1. Cross-gates next." | tee -a "$LOG"
exit "$BAD"
