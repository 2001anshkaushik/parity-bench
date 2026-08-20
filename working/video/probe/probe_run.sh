#!/usr/bin/env bash
# Orchestrates the single-video probe: disk numbers, RR arm (thread matrix,
# 2 sends each), LI floor (same matrix), then the token-topology census.
# Arms strictly ONE AT A TIME. No cpuset on either arm (Phase 2 environment);
# the six thread variables are exported the SAME on both arms per matrix point.
set -euo pipefail
cd "$(dirname "$0")"

VIDEO="media/ES2002a.Corner.avi"
[ -f "$VIDEO" ] || { echo "run ./probe_fetch.sh first"; exit 1; }
IMAGE="${RR_IMAGE:-rr:patched}"
MATRIX="${PROBE_MATRIX:-1 8 32}"
CENSUS_TOKENS="${PROBE_TOKENS:-2}"
LOG="probe_$(date +%Y%m%d_%H%M%S).log"
echo "image=$IMAGE matrix=[$MATRIX] census_tokens=$CENSUS_TOKENS -> $LOG"

thread_env_args() {
  local n="$1"
  echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n -e OPENBLAS_NUM_THREADS=$n \
       -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"
}

start_rr() { # threads
  docker rm -f rrprobe >/dev/null 2>&1 || true
  # shellcheck disable=SC2046
  docker run -d --name rrprobe --memory 58g $(thread_env_args "$1") -p 5565:5565 "$IMAGE" >/dev/null
  # First boot with the baked constraints cache is minutes; 10-30 min at
  # near-zero CPU on a cache miss is NORMAL, not a hang (carryover section C).
  for _ in $(seq 1 360); do
    if python3 -c "import socket; socket.create_connection(('127.0.0.1',5565),2).close()" 2>/dev/null; then return 0; fi
    sleep 5
  done
  echo "engine never listened on 5565"; docker logs rrprobe | tail -40; return 1
}

stop_rr() {
  docker logs rrprobe > "rrprobe_threads$1.dockerlog" 2>&1 || true
  docker rm -f rrprobe >/dev/null 2>&1 || true
}

echo "== disk numbers first (they need the quietest machine) ==" | tee -a "$LOG"
./probe_disk.sh "$VIDEO" 2>&1 | tee -a "$LOG"

for N in $MATRIX; do
  echo "== RR arm, threads=$N ==" | tee -a "$LOG"
  start_rr "$N"
  python3 probe_rr.py --video "$VIDEO" --sends 2 \
    --out "probe_rr_t${N}.json" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  stop_rr "$N"
  [ "$RC" = "0" ] || { echo "RR probe failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }

  echo "== LI floor, threads=$N ==" | tee -a "$LOG"
  env OMP_NUM_THREADS="$N" MKL_NUM_THREADS="$N" OPENBLAS_NUM_THREADS="$N" \
      VECLIB_MAXIMUM_THREADS="$N" NUMEXPR_NUM_THREADS="$N" TORCH_NUM_THREADS="$N" \
      PROBE_THREADS="$N" \
      python3 probe_li_floor.py --video "$VIDEO" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  [ "$RC" = "0" ] || { echo "LI floor failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }
done

echo "== token-topology census: $CENSUS_TOKENS tokens, threads=8, concurrent sends ==" | tee -a "$LOG"
start_rr 8
python3 probe_rr.py --video "$VIDEO" --tokens "$CENSUS_TOKENS" \
  --out "probe_rr_census_m${CENSUS_TOKENS}.json" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
stop_rr "census"
[ "$RC" = "0" ] || echo "census flagged rc=$RC — read probe_rr_census_m${CENSUS_TOKENS}.json before any comparative run" | tee -a "$LOG"

echo "== frame-count agreement (settled decision 2 verification) ==" | tee -a "$LOG"
python3 - <<'EOF' | tee -a "$LOG"
import glob, json
li = sorted(glob.glob('probe_li_floor_t*.json'))
rr = sorted(glob.glob('probe_rr_t*.json'))
li_frames = {json.load(open(f))['n_frames'] for f in li}
rr_lines = {json.load(open(f))['sends'][-1]['frames'].get('frame_debug_lines') for f in rr if json.load(open(f)).get('sends')}
print(f'LI-floor frame counts (independent ffmpeg count): {sorted(li_frames)} — expected {{84}}')
print(f'RR detect debug-line counts (None = log level hid them): {sorted(rr_lines, key=str)}')
ok = li_frames == {84}
print('INTERVAL SEMANTICS:', 'CONFIRMED (84 frames at fps=1/15 on 1248.3s)' if ok else f'NOT CONFIRMED — got {li_frames}, investigate before trusting any number')
raise SystemExit(0 if ok else 1)
EOF
RC=${PIPESTATUS[0]}
echo "probe complete — log: $LOG (rc=$RC)"
exit "$RC"
