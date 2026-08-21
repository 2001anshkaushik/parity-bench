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

echo "== GATE-3 STAGED CONFIRMATION: cross-arm label multisets on ES2002a ==" | tee -a "$LOG"
python3 - <<'EOF3' | tee -a "$LOG"
import glob, json, sys
# Latest RR probe steady-state send vs LI floor, same video, same threads point.
rr_files = sorted(glob.glob('probe_rr_t*.json'))
fl_files = sorted(glob.glob('probe_li_floor_t*.json'))
if not rr_files or not fl_files:
    print('gate-3 staging: missing probe outputs — cannot confirm'); sys.exit(1)
rr = json.load(open(rr_files[-1]))
fl = json.load(open(fl_files[-1]))
sends = [s for s in rr.get('sends', []) if 'documents' in s]
if not sends:
    print('gate-3 staging: no RR send analysis'); sys.exit(1)
a = sends[-1]['documents'].get('frame_label_multisets')
b = fl.get('frame_label_multisets')
if a is None or b is None:
    print('gate-3 staging: absent label multisets (rawdecode failed?) — absence fails first'); sys.exit(1)
if len(a) != len(b):
    print(f'gate-3 staging: FRAME COUNT DIFFERS rr={len(a)} li={len(b)} — REAL-DIFFERENCE '
          'hypothesis first (model swap / resize path / version drift), never tolerance'); sys.exit(1)
div = [i for i, (x, y) in enumerate(zip(a, b)) if sorted(x) != sorted(y)]
if div:
    ra = sends[-1]['documents'].get('frame_scores') or []
    rb = fl.get('frame_scores') or []
    deltas = [abs(p - q) for fa, fb in zip(ra, rb) if len(fa) == len(fb)
              for p, q in zip(sorted(fa), sorted(fb))]
    print(f'gate-3 staging: DIVERGES on {len(div)}/{len(a)} frames (first: {div[:5]}).')
    print('FIRST HYPOTHESIS IS A REAL DIFFERENCE — model swap, resize path, version drift.')
    print(f'score triage (diagnostic only): max paired delta = {max(deltas) if deltas else None}')
    print('Gate 3 stays UNARMED. Only a human downgrades, in writing, with the reason.')
    sys.exit(1)
print(f'gate-3 staging: EXACT agreement on {len(a)} frames — arm the gate with '
      f'--gate3-armed <this probe run id> in the driver')
EOF3
GATE3_RC=${PIPESTATUS[0]}
[ "$GATE3_RC" = "0" ] || echo "gate-3 staging failed (rc=$GATE3_RC) — investigate BEFORE any measured run" | tee -a "$LOG"

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
