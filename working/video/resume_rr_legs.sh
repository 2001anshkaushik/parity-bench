#!/usr/bin/env bash
# CROSSROAD 42/43 RESUME — the four missing RR blast legs, nothing else.
#   usage:  bash working/video/resume_rr_legs.sh working/video/results/mainrun_<stamp>
#
# Banked and NOT re-run: LI sequential, LI blast p1/p2, RR default sequential
# (5 legs incl. the smoke). Missing: RR default blast p1/p2, RR parity blast
# p1/p2. Cross-gates (leg 9) run AFTER; this script prints the invocation.
#
# Provenance CANNOT drift: RR_IMAGE_LINEAGE is read from the banked RR
# sequential export's own provenance (lineage_declared) — not from env, not
# from run_plan.log, not retyped. The corpus dir derives from the stamped
# manifest via corpus_locator. The driver must carry Crossroad 43 (ttl=0);
# this refuses to launch a 5-hour resume on a pre-43 driver.
set -euo pipefail
OUT="${1:?usage: resume_rr_legs.sh <mainrun dir>}"
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/parity-bench-video")"
PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing"; exit 1; }
[ -d "$OUT" ] || { echo "NOT DONE — $OUT is not a directory"; exit 1; }
LOG="$OUT/resume_rr_$(date -u +%Y%m%dT%H%M%SZ).log"

# -- guard: the driver on THIS box is post-Crossroad-43 --------------------
grep -q "ttl=0)" working/video/driver_video.py || {
  echo "NOT DONE — driver_video.py still carries a finite ttl; pull first. A resume on the" | tee -a "$LOG"
  echo "old driver dies at the same 2h cliff (Crossroad 43)." | tee -a "$LOG"; exit 1; }

# -- guard: the errored default-blast records are moved aside --------------
if [ -f "$OUT/records_rocketride_video_default_blast.jsonl" ]; then
  if grep -q '"error"' "$OUT/records_rocketride_video_default_blast.jsonl"; then
    echo "NOT DONE — $OUT/records_rocketride_video_default_blast.jsonl still holds errored" | tee -a "$LOG"
    echo "rows. The driver now re-runs errored keys, but the ruling was move-aside; do that" | tee -a "$LOG"
    echo "first:  mv $OUT/records_rocketride_video_default_blast.jsonl{,.errored_$(date -u +%H%M%SZ)}" | tee -a "$LOG"
    exit 1
  fi
fi

# -- lineage from the banked export's own provenance -----------------------
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
# any banked ROCKETRIDE export carries it; the sequential one is banked by ruling
cands = sorted(out.glob('export_rocketride_*.json'))
vals = {v for c in cands for v in walk(json.loads(c.read_text())) if v}
if not vals:
    print('NOT DONE — no banked rocketride export under ' + str(out) +
          ' carries lineage_declared; cannot inherit provenance', file=sys.stderr)
    raise SystemExit(1)
if len(vals) > 1:
    print('NOT DONE — banked exports DISAGREE on lineage_declared; refusing to pick',
          file=sys.stderr)
    raise SystemExit(1)
print(vals.pop())
EOF
)" || { echo "lineage extraction failed (above)"; exit 1; }
echo "lineage (from banked export, verbatim): ${LINEAGE:0:80}..." | tee -a "$LOG"

VIDEO_MANIFEST=working/video/ami_video_manifest.jsonl
CORPUS_DIR="$("$PY" working/video/corpus_locator.py --manifest "$VIDEO_MANIFEST" --tool resume | head -1)" \
  || { echo "NOT DONE — corpus_dir unresolved (stamp missing?)"; exit 1; }
echo "corpus_dir=$CORPUS_DIR [manifest meta]" | tee -a "$LOG"

DRIVER=("$PY" working/video/driver_video.py --out-dir "$OUT"
        --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR")

thread_env_args() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

start_rr() { # $1 = 'unset' | N   (same shape as run_plan)
  docker rm -f rr >/dev/null 2>&1 || true
  local env_args=""; [ "$1" = "unset" ] || env_args="$(thread_env_args "$1")"
  # shellcheck disable=SC2086
  docker run -d --name rr --memory 58g $env_args --log-opt max-size=200m \
      --network host rr:patched-video >/dev/null
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  echo "container rr [$1]: created=$(docker inspect -f '{{.Created}}' rr) (fresh lifetime)" | tee -a "$LOG"
}
run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"
        local rc=${PIPESTATUS[0]}
        [ "$rc" = "0" ] || { echo "STEP FAILED rc=$rc: $*" | tee -a "$LOG"; exit "$rc"; }; }

echo "=== RESUME: RR default blast p1/p2 (posture default, env unset, ttl=0) ===" | tee -a "$LOG"
start_rr unset
for p in 1 2; do
  run "${DRIVER[@]}" --arm rocketride --posture default --leg blast --n 168 \
      --blast-concurrency 16 --rr-threads-env unset --pass "$p" --image-lineage "$LINEAGE"
done
docker logs rr > "$OUT/dockerlog_rr_default_resume.txt" 2>&1 || true

echo "=== RESUME: RR parity blast p1/p2 (M=16, six-var env=2, ttl=0) ===" | tee -a "$LOG"
start_rr 2
for p in 1 2; do
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n 168 \
      --blast-concurrency 16 --tokens 16 --rr-threads-env 2 --pass "$p" --image-lineage "$LINEAGE"
done
docker logs rr > "$OUT/dockerlog_rr_parity_resume.txt" 2>&1 || true
docker rm -f rr >/dev/null 2>&1 || true

echo "=== RESUME COMPLETE — four legs. Cross-gates (leg 9) next: ===" | tee -a "$LOG"
echo "  $PY working/video/driver_video.py --cross \\" | tee -a "$LOG"
echo "      $OUT/records_rocketride_video_parity_blast.jsonl \\" | tee -a "$LOG"
echo "      $OUT/records_llamaindex_video_workers_blast.jsonl \\" | tee -a "$LOG"
echo "      --gate3-armed <GATE3_RUN_ID from run_manifest.json>   # exact record names: ls $OUT/records_*.jsonl" | tee -a "$LOG"
echo "log: $LOG"
