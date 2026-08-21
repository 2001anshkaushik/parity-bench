#!/usr/bin/env bash
# Orchestrates the single-video probe: disk numbers, RR arm (thread matrix,
# 2 sends each), LI floor (same matrix), then the token-topology census.
# Arms strictly ONE AT A TIME. No cpuset on either arm (Phase 2 environment);
# the six thread variables are exported the SAME on both arms per matrix point.
set -euo pipefail
# Interpreter contract (box trap: system "$PY" lacks psutil/rfdetr/imageio_ffmpeg):
# every python here is the FLOOR venv. Override with PYBIN.
PY="${PYBIN:-$HOME/.venv-floor/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing; run working/video/probe/setup_floor_venv.sh first"; exit 1; }

cd "$(dirname "$0")"

VIDEO="media/ES2002a.Corner.avi"
[ -f "$VIDEO" ] || { echo "run ./probe_fetch.sh first"; exit 1; }
IMAGE="${RR_IMAGE:-rr:patched-video}"   # Crossroad 18: the BAKED image; rr:patched would reinstall 3-4.5GB per container
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
  # Crossroad 22: --network host (Phase 1 section C parity; docker-proxy both
  # adds a userspace hop to latency and defeats TCP readiness — instance seven).
  # shellcheck disable=SC2046
  docker run -d --name rrprobe --memory 58g $(thread_env_args "$1") --network host "$IMAGE" >/dev/null
  # First boot with the baked constraints cache is minutes; 10-30 min at
  # near-zero CPU on a cache miss is NORMAL, not a hang (carryover section C).
  # Readiness = a real SDK connect (wait_ready prints the log tail on failure).
  "$PY" wait_ready.py --arm rr --port 5565 --deadline 1800 --container rrprobe || return 1
}

stop_rr() {
  docker logs rrprobe > "rrprobe_threads$1.dockerlog" 2>&1 || true
  docker rm -f rrprobe >/dev/null 2>&1 || true
}

echo "== disk numbers first (they need the quietest machine) ==" | tee -a "$LOG"
./probe_disk.sh "$VIDEO" 2>&1 | tee -a "$LOG"

echo "== VERIFICATION PIPE LOAD-PROOF (gates 2c/4 pipe; two minutes, fail cheap) ==" | tee -a "$LOG"
start_rr 8
"$PY" probe_frame_identity.py --video "$VIDEO" --no-floor-ok \
  --out probe_frame_identity_early.json 2>&1 | tee -a "$LOG"
IDENT_RC=${PIPESTATUS[0]}
stop_rr "identity"
[ "$IDENT_RC" = "0" ] || { echo "verification pipe FAILED to load/serve (rc=$IDENT_RC) — gates 2c and 4 stand on it; investigate before spending the probe window" | tee -a "$LOG"; exit "$IDENT_RC"; }

for N in $MATRIX; do
  echo "== RR arm, threads=$N ==" | tee -a "$LOG"
  start_rr "$N"
  "$PY" probe_rr.py --video "$VIDEO" --sends 2 \
    --out "probe_rr_t${N}.json" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  stop_rr "$N"
  [ "$RC" = "0" ] || { echo "RR probe failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }

  echo "== LI floor, threads=$N ==" | tee -a "$LOG"
  env OMP_NUM_THREADS="$N" MKL_NUM_THREADS="$N" OPENBLAS_NUM_THREADS="$N" \
      VECLIB_MAXIMUM_THREADS="$N" NUMEXPR_NUM_THREADS="$N" TORCH_NUM_THREADS="$N" \
      PROBE_THREADS="$N" \
      "$PY" probe_li_floor.py --video "$VIDEO" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  [ "$RC" = "0" ] || { echo "LI floor failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }
done

echo "== token-topology census: $CENSUS_TOKENS tokens, threads=8, concurrent sends ==" | tee -a "$LOG"
start_rr 8
"$PY" probe_rr.py --video "$VIDEO" --tokens "$CENSUS_TOKENS" \
  --out "probe_rr_census_m${CENSUS_TOKENS}.json" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
stop_rr "census"
[ "$RC" = "0" ] || echo "census flagged rc=$RC — read probe_rr_census_m${CENSUS_TOKENS}.json before any comparative run" | tee -a "$LOG"

echo "== GATE 4: engine-vs-floor PNG hashes (from the early identity run, no resend) ==" | tee -a "$LOG"
"$PY" - <<'EOF4' | tee -a "$LOG"
import glob, json, sys
try:
    ident = json.load(open('probe_frame_identity_early.json'))
except FileNotFoundError:
    print('gate 4: early identity output missing'); sys.exit(1)
floors = sorted(glob.glob('probe_li_floor_t*.json'))
if not floors:
    print('gate 4: no floor json produced by the matrix'); sys.exit(1)
li = json.load(open(floors[-1])).get('frame_png_sha16') or []
eng = ident.get('engine_frame_png_sha16') or []
if not eng or not li:
    print(f'gate 4: absent hashes (engine={len(eng)} li={len(li)}) — absence fails first'); sys.exit(1)
if eng == li:
    print(f'gate 4 PASS: {len(eng)} frames byte-identical across arms'); sys.exit(0)
mism = [i for i, (a, b) in enumerate(zip(eng, li)) if a != b]
print(f'gate 4 FAIL: n_engine={len(eng)} n_li={len(li)} first mismatches {mism[:5]} — '
      'decode paths differ; REAL-DIFFERENCE hypothesis first'); sys.exit(1)
EOF4
G4_RC=${PIPESTATUS[0]}
[ "$G4_RC" = "0" ] || echo "gate 4 failed (rc=$G4_RC) — investigate before any measured run" | tee -a "$LOG"

echo "== GATE-3 STAGED CONFIRMATION: cross-arm label multisets on ES2002a ==" | tee -a "$LOG"
"$PY" - <<'EOF3' | tee -a "$LOG"
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
    print('CHECK RECORDED VALUES IN THIS ORDER: interpreter versions per arm (the engine')
    print('embeds its own CPython, distinct from the container PATH python), then')
    print('rfdetr/torch versions, then checkpoint md5, then PNG byte identity (gate 4).')
    print(f'score triage (diagnostic only): max paired delta = {max(deltas) if deltas else None}')
    print('Gate 3 stays UNARMED. Only a human downgrades, in writing, with the reason.')
    sys.exit(1)
print(f'gate-3 staging: EXACT agreement on {len(a)} frames — arm the gate with '
      f'--gate3-armed <this probe run id> in the driver')
EOF3
GATE3_RC=${PIPESTATUS[0]}
[ "$GATE3_RC" = "0" ] || echo "gate-3 staging failed (rc=$GATE3_RC) — investigate BEFORE any measured run" | tee -a "$LOG"

echo "== frame-count cross-method agreement (Crossroad 23: measured vs measured, no formula) ==" | tee -a "$LOG"
"$PY" - <<'EOF' | tee -a "$LOG"
import glob, json
# The old check asserted li_frames == {84} — a formula's product. It fired on
# the probe (ffmpeg emits 83: the final slot never opens) and Crossroad 23
# deleted the formula. The check's real job survives: every MEASURED count —
# LI extractor, RR rawdecode, RR overlap-stripped bracket — must be ONE value.
li = sorted(glob.glob('probe_li_floor_t*.json'))
rr = sorted(glob.glob('probe_rr_t*.json'))
li_frames = {json.load(open(f))['n_frames'] for f in li}
rr_counts = set()
for f in rr:
    for s in json.load(open(f)).get('sends', []):
        d = s.get('documents') or {}
        rr_counts |= {d.get('frames_rawdecode'), d.get('frames_from_chunks')}
rr_counts.discard(None)
print(f'LI-floor extractor counts: {sorted(li_frames)}')
print(f'RR chunk-derived counts (rawdecode + bracket): {sorted(rr_counts)}')
ok = len(li_frames) == 1 and li_frames == rr_counts
print('FRAME AGREEMENT:', (f'CONFIRMED — one value, all methods: {sorted(li_frames)}' if ok
      else 'NOT CONFIRMED — methods disagree; investigate before trusting any count'))
raise SystemExit(0 if ok else 1)
EOF
RC=${PIPESTATUS[0]}
echo "probe complete — log: $LOG (rc=$RC)"
exit "$RC"
