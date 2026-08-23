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

# Heredoc pythons are fed on STDIN, where sys.path[0] is '' (cwd) — which is this
# directory, so `import artifact_identity` resolves. That default is off under
# PYTHONSAFEPATH/-P, and the floor venv is not ours to assume: state the path
# rather than depend on an interpreter default. Verified safe under bash 3.2 + set -u.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# Overridable (Crossroad 37): the gate-3 staging must be re-done on the corpus
# actually being run — an arming id from a Corner video does not arm a Closeup1 run.
VIDEO="${VIDEO:-media/ES2002a.Corner.avi}"
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

preserve() {  # Evidence is never overwritten (register entry 7: the Crossroad 24
  # recheck ran as PROBE_MATRIX=32 and clobbered the original t32 JSON — the
  # disqualified form of a command stays quotable, so the script itself must
  # make it safe). Existing outputs move aside; *.prev_<ts> matches no *.json
  # glob, so the summarizer and gates never read a superseded run as current.
  if [ -f "$1" ]; then
    local dest="$1.prev_$(date +%Y%m%dT%H%M%S)"
    mv "$1" "$dest"
    echo "preserved existing $1 -> $dest" | tee -a "$LOG"
  fi
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
preserve probe_frame_identity_early.json
start_rr 8
"$PY" probe_frame_identity.py --video "$VIDEO" --no-floor-ok \
  --out probe_frame_identity_early.json 2>&1 | tee -a "$LOG"
IDENT_RC=${PIPESTATUS[0]}
stop_rr "identity"
[ "$IDENT_RC" = "0" ] || { echo "verification pipe FAILED to load/serve (rc=$IDENT_RC) — gates 2c and 4 stand on it; investigate before spending the probe window" | tee -a "$LOG"; exit "$IDENT_RC"; }

for N in $MATRIX; do
  echo "== RR arm, threads=$N ==" | tee -a "$LOG"
  preserve "probe_rr_t${N}.json"
  start_rr "$N"
  "$PY" probe_rr.py --video "$VIDEO" --sends 2 \
    --out "probe_rr_t${N}.json" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  stop_rr "$N"
  [ "$RC" = "0" ] || { echo "RR probe failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }

  echo "== LI floor, threads=$N ==" | tee -a "$LOG"
  preserve "probe_li_floor_t${N}.json"
  env OMP_NUM_THREADS="$N" MKL_NUM_THREADS="$N" OPENBLAS_NUM_THREADS="$N" \
      VECLIB_MAXIMUM_THREADS="$N" NUMEXPR_NUM_THREADS="$N" TORCH_NUM_THREADS="$N" \
      PROBE_THREADS="$N" \
      "$PY" probe_li_floor.py --video "$VIDEO" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  [ "$RC" = "0" ] || { echo "LI floor failed at threads=$N (rc=$RC)" | tee -a "$LOG"; exit "$RC"; }
done

echo "== token-topology census: $CENSUS_TOKENS tokens, threads=8, concurrent sends ==" | tee -a "$LOG"
preserve "probe_rr_census_m${CENSUS_TOKENS}.json"
start_rr 8
"$PY" probe_rr.py --video "$VIDEO" --tokens "$CENSUS_TOKENS" \
  --out "probe_rr_census_m${CENSUS_TOKENS}.json" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
stop_rr "census"
[ "$RC" = "0" ] || echo "census flagged rc=$RC — read probe_rr_census_m${CENSUS_TOKENS}.json before any comparative run" | tee -a "$LOG"


# The matrix point THIS run produced — never a glob. `sorted(glob("probe_rr_t*"))[-1]`
# is LEXICOGRAPHIC, so with t1/t2/t32/t8 on disk it returns t8, and a Closeup1
# re-stage silently compared stale Corner artifacts (2026-08-23). Both files are
# now named from the matrix point AND asserted to carry this run's video sha.
LAST_T="$(echo $MATRIX | awk '{print $NF}')"

# GATE 4 — THE ONE COMPARATOR (2026-08-23). There were TWO: this one, and a twin
# ~30 lines upstream that selected its floor with sorted(glob(...))[-1] and, from
# a two-day-old Corner floor, printed a REAL-DIFFERENCE verdict on a correct
# decode. The twin is deleted. Selection AND verdict language now come from
# artifact_identity.py so a future site cannot re-invent either (register 14).
# The early identity step runs before any floor for this video exists, so it can
# only save the engine hashes; gate 4 is finished HERE, with no resend.
echo "== GATE 4: engine vs LI floor, post-matrix, no resend ==" | tee -a "$LOG"
"$PY" - "$VIDEO" "$LAST_T" <<'EOF4' | tee -a "$LOG"
import json, sys
from pathlib import Path
from artifact_identity import (video_sha16, select_by_video, require_same_video,
                               cannot_compare, real_difference, passed,
                               RC_PASS, RC_REAL_DIFFERENCE, RC_CANNOT_COMPARE)
GATE = 'gate 4'
video, last_t = Path(sys.argv[1]), sys.argv[2]
want = video_sha16(video)

early_p = 'probe_frame_identity_early.json'
if not Path(early_p).exists():
    print(cannot_compare(GATE, f'{early_p} missing — it holds the engine hashes this step '
                               'compares, so gate 4 stays NOT RUN'))
    sys.exit(RC_CANNOT_COMPARE)
early = json.load(open(early_p))

# Prefer this run's last matrix point; accept any floor from THIS video; never
# one from another video, whatever its name happens to sort to.
sel = select_by_video(want, [f'probe_li_floor_t{last_t}.json', 'probe_li_floor_t*.json'])
if not sel.ok:
    print(cannot_compare(GATE, sel.why_not(video.name) +
                         ' — gate 4 DEFERS: produce an LI floor on this video, then re-run'))
    sys.exit(RC_CANNOT_COMPARE)
floor_name = Path(sel.path).name
# ALWAYS name the artifact compared against — a selection nobody can see in the
# log is how a stale comparator survived two probe windows.
print(f'{GATE}: floor selected by identity: {floor_name}'
      + (f'; rejected {sel.rejected}' if sel.rejected
         else " (this run's matrix point, matched directly)"))

why = require_same_video(want, {'engine/early': early, f'li_floor ({floor_name})': sel.doc})
if why:
    print(cannot_compare(GATE, f'{why} ({video.name})'))
    sys.exit(RC_CANNOT_COMPARE)

a = early.get('engine_frame_png_sha16') or []
b = sel.doc.get('frame_png_sha16') or []
if not a or not b:
    print(cannot_compare(GATE, f'absent hashes on one side (engine={len(a)} li={len(b)}) — '
                               'absence fails first'))
    sys.exit(RC_CANNOT_COMPARE)

# Past this line, and ONLY past this line, same-input is proven: both sides
# recorded video_sha16 == want. A difference here is a difference in the ARMS.
bad = None
if len(a) != len(b):
    print(real_difference(GATE, f'FRAME COUNT DIFFERS engine={len(a)} li={len(b)}', want))
    rc = RC_REAL_DIFFERENCE
else:
    bad = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    print(passed(GATE, f'{len(a)} frames byte-identical across arms', want) if not bad
          else real_difference(GATE, f'{len(bad)} of {len(a)} frames differ, first {bad[:10]}', want))
    rc = RC_PASS if not bad else RC_REAL_DIFFERENCE

json.dump({'gate4_decode_identity': {
    'PASS': rc == RC_PASS, 'verdict': 'PASS' if rc == RC_PASS else 'REAL DIFFERENCE',
    'n_engine': len(a), 'n_li': len(b), 'mismatched_frames': (bad or None) and bad[:20],
    'video': video.name, 'video_sha16': want, 'floor_json': floor_name,
    'floor_rejected': sel.rejected_json(), 'same_input_proven': True,
    'compared_without_resend': True}}, open('probe_frame_identity_final.json', 'w'), indent=1)
sys.exit(rc)
EOF4
GATE4_RC=${PIPESTATUS[0]}
case "$GATE4_RC" in
  0) : ;;
  2) echo "gate 4 CANNOT COMPARE — an EVIDENCE fault, NOT a finding about the arms. Do not report it as a decode difference; fix the evidence and re-run this step." | tee -a "$LOG" ;;
  *) echo "gate 4 REAL DIFFERENCE (rc=$GATE4_RC) — same input was PROVEN on both sides. Investigate decode path/ffmpeg build before any measured run; read probe_frame_identity_final.json." | tee -a "$LOG" ;;
esac

echo "== GATE-3 STAGED CONFIRMATION: cross-arm label multisets on $(basename "$VIDEO") (t=$LAST_T) ==" | tee -a "$LOG"
"$PY" - "$VIDEO" "$LAST_T" <<'EOF3' | tee -a "$LOG"
import json, sys
from pathlib import Path
from artifact_identity import (video_sha16, require_same_video, cannot_compare,
                               real_difference, RC_PASS, RC_REAL_DIFFERENCE,
                               RC_CANNOT_COMPARE)
GATE = 'gate-3 staging'
video, last_t = Path(sys.argv[1]), sys.argv[2]
want_sha = video_sha16(video)
rr_path, fl_path = f'probe_rr_t{last_t}.json', f'probe_li_floor_t{last_t}.json'
for pth in (rr_path, fl_path):
    if not Path(pth).exists():
        print(cannot_compare(GATE, f'{pth} missing — this run\'s matrix point produced no '
                                   'such artifact, and no other file substitutes for it'))
        sys.exit(RC_CANNOT_COMPARE)
rr = json.load(open(rr_path))
fl = json.load(open(fl_path))
# ABSENCE FAILS FIRST, and so does a stale artifact: both sides must record the
# SAME video, and it must be the one this run was pointed at. One implementation,
# shared with gate 4 and the frame-agreement check (artifact_identity).
why = require_same_video(want_sha, {'rr': rr, 'li_floor': fl})
if why:
    print(cannot_compare(GATE, f'{why} = {video.name}. An arming id from this comparison '
                               'would assert agreement on the wrong corpus'))
    sys.exit(RC_CANNOT_COMPARE)
print(f'gate-3 staging: both arms confirmed on {video.name} (sha16 {want_sha}, t={last_t})')
sends = [s for s in rr.get('sends', []) if 'documents' in s]
if not sends:
    print(cannot_compare(GATE, 'no RR send analysis in the artifact'))
    sys.exit(RC_CANNOT_COMPARE)
a = sends[-1]['documents'].get('frame_label_multisets')
b = fl.get('frame_label_multisets')
if a is None or b is None:
    print(cannot_compare(GATE, 'absent label multisets (rawdecode failed?) — absence fails first'))
    sys.exit(RC_CANNOT_COMPARE)
if len(a) != len(b):
    print(real_difference(GATE, f'FRAME COUNT DIFFERS rr={len(a)} li={len(b)} '
                          '(model swap / resize path / version drift)', want_sha))
    sys.exit(RC_REAL_DIFFERENCE)
div = [i for i, (x, y) in enumerate(zip(a, b)) if sorted(x) != sorted(y)]
if div:
    ra = sends[-1]['documents'].get('frame_scores') or []
    rb = fl.get('frame_scores') or []
    deltas = [abs(p - q) for fa, fb in zip(ra, rb) if len(fa) == len(fb)
              for p, q in zip(sorted(fa), sorted(fb))]
    print(real_difference(GATE, f'DIVERGES on {len(div)}/{len(a)} frames '
                          f'(first: {div[:5]}) — model swap, resize path, version drift',
                          want_sha))
    print('CHECK RECORDED VALUES IN THIS ORDER: interpreter versions per arm (the engine')
    print('embeds its own CPython, distinct from the container PATH python), then')
    print('rfdetr/torch versions, then checkpoint md5, then PNG byte identity (gate 4).')
    print(f'score triage (diagnostic only): max paired delta = {max(deltas) if deltas else None}')
    print('Gate 3 stays UNARMED. Only a human downgrades, in writing, with the reason.')
    sys.exit(RC_REAL_DIFFERENCE)
print(f'gate-3 staging: EXACT agreement on {len(a)} frames — arm the gate with '
      f'--gate3-armed <this probe run id> in the driver')
EOF3
GATE3_RC=${PIPESTATUS[0]}
case "$GATE3_RC" in
  0) : ;;
  2) echo "gate-3 staging CANNOT COMPARE — an EVIDENCE fault, NOT arm disagreement. Nothing is armed; fix the evidence and re-run." | tee -a "$LOG" ;;
  *) echo "gate-3 staging REAL DIFFERENCE (rc=$GATE3_RC) — same input PROVEN on both arms. Investigate BEFORE any measured run." | tee -a "$LOG" ;;
esac

echo "== frame-count cross-method agreement (Crossroad 23: measured vs measured, no formula) ==" | tee -a "$LOG"
"$PY" - "$VIDEO" <<'EOF' | tee -a "$LOG"
import sys
from pathlib import Path
from artifact_identity import (video_sha16, select_all_by_video, cannot_compare,
                               real_difference, passed,
                               RC_PASS, RC_REAL_DIFFERENCE, RC_CANNOT_COMPARE)
# The old check asserted li_frames == {84} — a formula's product. It fired on
# the probe (ffmpeg emits 83: the final slot never opens) and Crossroad 23
# deleted the formula. The check's real job survives: every MEASURED count —
# LI extractor, RR rawdecode, RR overlap-stripped bracket — must be ONE value.
#
# 2026-08-23: it pooled every probe_*_t*.json on disk regardless of which video
# produced it, so one stale Corner floor made {83, 93} and the check reported
# "the methods disagree" — a fabricated finding, in the block whose rc is this
# script's exit code. Pooling now takes only artifacts from THIS video.
GATE = 'frame agreement'
video = Path(sys.argv[1])
want = video_sha16(video)
li, li_rej = select_all_by_video(want, ['probe_li_floor_t*.json'])
rr, rr_rej = select_all_by_video(want, ['probe_rr_t*.json'])
for label, rej in (('LI floor', li_rej), ('RR', rr_rej)):
    if rej:
        print(f'{GATE}: {label} artifacts from other videos EXCLUDED: {rej}')
if not li or not rr:
    print(cannot_compare(GATE, f'no {"LI floor" if not li else "RR"} artifact from this video '
                               f'(sha16 {want} = {video.name}) — nothing to pool'))
    sys.exit(RC_CANNOT_COMPARE)

li_frames = {doc['n_frames'] for _, doc in li}
rr_counts = set()
for _, doc in rr:
    for snd in doc.get('sends', []):
        d = snd.get('documents') or {}
        rr_counts |= {d.get('frames_rawdecode'), d.get('frames_from_chunks')}
rr_counts.discard(None)
print(f'{GATE}: LI-floor extractor counts {sorted(li_frames)} '
      f'from {[Path(f).name for f, _ in li]}')
print(f'{GATE}: RR chunk-derived counts (rawdecode + bracket) {sorted(rr_counts)} '
      f'from {[Path(f).name for f, _ in rr]}')
if not rr_counts:
    print(cannot_compare(GATE, 'RR artifacts carry no frame counts (rawdecode failed?) — '
                               'absence fails first'))
    sys.exit(RC_CANNOT_COMPARE)
# Same-input proven for every pooled artifact by construction above.
if len(li_frames) == 1 and li_frames == rr_counts:
    print(passed(GATE, f'one value, all methods: {sorted(li_frames)}', want))
    sys.exit(RC_PASS)
print(real_difference(GATE, f'methods disagree — LI {sorted(li_frames)} vs RR {sorted(rr_counts)}',
                      want))
sys.exit(RC_REAL_DIFFERENCE)
EOF
RC=${PIPESTATUS[0]}
case "$RC" in
  2) echo "frame agreement CANNOT COMPARE — an EVIDENCE fault, not a finding about the arms." | tee -a "$LOG" ;;
esac
echo "probe complete — log: $LOG (rc=$RC)"
exit "$RC"
