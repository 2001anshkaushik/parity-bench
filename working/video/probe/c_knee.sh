#!/usr/bin/env bash
# RR DEFAULT-POSTURE CONCURRENCY KNEE (2026-08-24) — the real driver path, one
# wave per point, fresh container per point, bisect order. Identifies the C at
# which one-token whole-frame blast survives, or rules concurrency out (a PASS
# at C=16 moves suspicion off concurrency entirely).
#
#   POINTS="16 8 4" bash working/video/probe/c_knee.sh        # default, ~45-55 min
#   POINTS="12 6" ... to refine between a failing 16 and a passing 8, etc.
#
# Each point: n = C (exactly one wave — every failure so far died in wave one),
# the largest-payload rows first come from the manifest order as-is. Failure
# points cost ~2-3 min; passing points ~C x ~45-60s inference + warm-up.
#
# LOCKED: two drivers against one engine container voided a probe tonight.
# flock + a pgrep refusal make that structurally impossible, not remembered.
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/parity-bench-video")"
PY="${PYBIN:-$HOME/.venv/bin/python}"
LOCK="${TMPDIR:-/tmp}/rr_video_driver.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "NOT DONE — another run holds $LOCK; two drivers on one container voided a probe already"; exit 1; }
if pgrep -f "driver_video.py.*--arm rocketride" >/dev/null 2>&1; then
  echo "NOT DONE — a rocketride driver is already running (pgrep); refusing a second"; exit 1
fi
POINTS="${POINTS:-16 8 4}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="working/video/results/cknee_$STAMP"
mkdir -p "$BASE"
echo "knee sweep: POINTS=[$POINTS] -> $BASE (lock $LOCK held)"

for C in $POINTS; do
  OUT="$BASE/C$C"
  mkdir -p "$OUT"
  echo "=== POINT C=$C (n=$C, one wave, fresh container) ==="
  docker rm -f rr >/dev/null 2>&1 || true
  docker run -d --name rr --memory 58g --log-opt max-size=200m --network host rr:patched-video >/dev/null
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  RC=0
  "$PY" working/video/driver_video.py --arm rocketride --posture default --leg blast \
      --n "$C" --blast-concurrency "$C" --rr-threads-env unset \
      --out-dir "$OUT" --image-lineage "c_knee probe $STAMP — NOT a campaign leg, discard from any comparison" \
      2>&1 | tee "$OUT/console.log" || RC=$?
  docker logs rr > "$OUT/dockerlog.txt" 2>&1 || true
  docker rm -f rr >/dev/null 2>&1 || true
  echo "point C=$C driver rc=${RC}"
done

echo; echo "=== KNEE SUMMARY (read this back verbatim) ==="
"$PY" - "$BASE" <<'EOF'
import glob, json, sys
from pathlib import Path
base = Path(sys.argv[1])
for d in sorted(base.glob('C*'), key=lambda p: int(p.name[1:]), reverse=True):
    recs = [json.loads(l) for f in glob.glob(str(d / 'records_*.jsonl'))
            for l in open(f) if l.strip()]
    errs = [r for r in recs if 'error' in r]
    reads = sorted(r['read_s'] for r in recs if r.get('read_s') is not None)
    resid = None
    for line in (d / 'console.log').read_text().splitlines():
        if 'blob residency' in line:
            resid = line.strip()
    first_err = errs[0]['error'][:90] if errs else None
    print(f"C={d.name[1:]:>3}: records {len(recs)} errors {len(errs)} "
          f"read_s {reads[:1]}..{reads[-1:] if reads else []} | {resid}")
    if first_err:
        print(f"        first error: {first_err}")
print('PASS at a C = that wave survives whole-frame sends; FAIL = the knee is above it.')
print('A PASS at C=16 rules concurrency out at this payload — suspicion moves to state/load.')
EOF
