#!/usr/bin/env bash
# OVERNIGHT: the four missing RR blast legs at n=168 C=16, chunked write path.
#   nohup bash working/video/overnight_rr.sh working/video/results/mainrun_20260824T025550Z > .../console.log 2>&1 &
# Order: parity p1, parity p2, default p1, default p2. Fresh container per LEG.
# CONTINUES past a failed leg (records the rc, moves on) — the driver-level
# per-arm flock plus this wrapper's own lock make a second concurrent run
# impossible. Lineage is inherited from the banked RR export's provenance,
# verbatim; corpus dir derives from the stamped manifest. nohup/tmux safe.
set -uo pipefail   # NOT -e: a failed leg must not kill the remaining legs
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/parity-bench-video")"
OUT="${1:?usage: overnight_rr.sh <mainrun dir>}"
PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing"; exit 1; }
[ -d "$OUT" ] || { echo "NOT DONE — $OUT is not a directory"; exit 1; }
LOCK="${TMPDIR:-/tmp}/overnight_rr.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "NOT DONE — another overnight_rr holds $LOCK"; exit 1; }
LOG="$OUT/overnight_rr_$(date -u +%Y%m%dT%H%M%SZ).log"

grep -q "chunked-1MiB" working/video/driver_video.py || {
  echo "NOT DONE — driver lacks the chunked write path; pull first (a whole-frame blast dies at every C tried)" | tee -a "$LOG"; exit 1; }

LINEAGE="$("$PY" - "$OUT" <<'EOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
def walk(n):
    if isinstance(n, dict):
        if 'lineage_declared' in n:
            yield n['lineage_declared']
        for v in n.values(): yield from walk(v)
    elif isinstance(n, list):
        for v in n: yield from walk(v)
vals = {v for c in sorted(out.glob('export_rocketride_*.json'))
        for v in walk(json.loads(c.read_text())) if v}
if len(vals) != 1:
    print(f'NOT DONE — {len(vals)} distinct lineage_declared values in banked exports; refusing',
          file=sys.stderr); raise SystemExit(1)
print(vals.pop())
EOF
)" || { echo "lineage extraction failed (above)" | tee -a "$LOG"; exit 1; }
echo "lineage (banked export, verbatim): ${LINEAGE:0:70}..." | tee -a "$LOG"

thread_env_args() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

echo "=== resume state per leg (errored rows are RE-RUN, never counted done) ===" | tee -a "$LOG"
for f in "$OUT"/records_rocketride_video_*blast*.jsonl; do
  [ -f "$f" ] || continue
  T=$(grep -c . "$f" 2>/dev/null || echo 0); E=$(grep -c '"error"' "$f" 2>/dev/null || echo 0)
  echo "  $(basename "$f"): $T rows, $E errored" | tee -a "$LOG"
done

declare -a RESULTS=()
run_leg() {  # $1 posture, $2 env('unset'|N), $3 pass, extra args...
  local posture="$1" env="$2" pass="$3"; shift 3
  local tag="${posture}_p${pass}"
  echo "=== LEG $tag: fresh container (env=$env), chunked writes, n=168 C=16 ===" | tee -a "$LOG"
  docker rm -f rr >/dev/null 2>&1 || true
  local env_args=""; [ "$env" = "unset" ] || env_args="$(thread_env_args "$env")"
  # shellcheck disable=SC2086
  docker run -d --name rr --memory 58g $env_args --log-opt max-size=200m \
      --network host rr:patched-video >/dev/null
  if ! "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr 2>&1 | tee -a "$LOG"; then
    RESULTS+=("$tag: NOT READY — leg skipped"); docker rm -f rr >/dev/null 2>&1 || true; return
  fi
  "$PY" working/video/driver_video.py --arm rocketride --posture "$posture" --leg blast \
      --n 168 --blast-concurrency 16 --pass "$pass" --image-lineage "$LINEAGE" "$@" \
      --out-dir "$OUT" 2>&1 | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  docker logs rr > "$OUT/dockerlog_rr_${tag}_overnight.txt" 2>&1 || true
  docker rm -f rr >/dev/null 2>&1 || true
  RESULTS+=("$tag: rc=$rc")
  echo "=== LEG $tag done rc=$rc (continuing regardless) ===" | tee -a "$LOG"
}

run_leg parity 2 1 --tokens 16 --rr-threads-env 2
run_leg parity 2 2 --tokens 16 --rr-threads-env 2
run_leg default unset 1 --rr-threads-env unset
run_leg default unset 2 --rr-threads-env unset

echo "=== OVERNIGHT SUMMARY ===" | tee -a "$LOG"
FAILED=0
for r in "${RESULTS[@]}"; do echo "  $r" | tee -a "$LOG"; case "$r" in *rc=0) ;; *) FAILED=1;; esac; done
echo "next (after ALL four are rc=0): cross-gates —" | tee -a "$LOG"
echo "  $PY working/video/driver_video.py --cross <RR records> <LI records> --gate3-armed <GATE3_RUN_ID>" | tee -a "$LOG"
echo "log: $LOG"
exit "$FAILED"
