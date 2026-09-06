#!/usr/bin/env bash
# =============================================================================
# FILMS-500 LIFETIME-CONTROLLED PASSES (ruling 2026-09-06). THROUGHPUT ONLY —
# no cross gates, no partition (settled: 433 predicted, 433 measured).
#
# WHY: the campaign's two passes per arm ran consecutively inside ONE
# container lifetime and drifted in arm-specific directions (RR p2 slower,
# LI p2 faster), a spread the size of the +5.9% effect. The free
# position-in-leg fit on the landed records (FILMS500_RESULTS.md, drift
# finding) showed the SHAPE: a FIRST-PASS TRANSIENT that settles into a
# PLATEAU which pass 2 inherits flat —
#   RR p1 first20%->last20% +4.8% (Q1..Q4 4.98 4.92 5.09 5.26 s/foot-min),
#      p2 flat +0.4% AT p1's end level;
#   LI p1 -8.5% (5.07 5.16 5.12 4.82), p2 flat -0.4% at p1's end level.
# So PASS 2 IS THE SETTLED STATE and pass 1 the transient. The ruling's
# one-pass-per-fresh-lifetime form would measure four transients and never
# the plateau; contested WITH that measurement, this script bakes the
# data-supported design instead (Ansh rules; a one-line constant change +
# new sha reproduces the one-pass form if he so rules):
#
#   DESIGN: two FRESH container lifetimes, ARMS ALTERNATED against the
#   campaign's order (RR first here, LI second — any box-level time trend
#   lands on both arms across the two campaigns), TWO passes per lifetime
#   (transient + plateau, each reproduced), container AGE AT LEG START and
#   pass-in-lifetime recorded in every export (provenance_video.
#   container_lifetime). Passes numbered 3 and 4 to continue the
#   campaign's numbering.
#
# PRE-REGISTERED READINGS (before it runs):
#   CONFIRMS the lifetime-drift account: RR pass 3 drifts +3..6% first->last
#     20% and pass 4 sits flat at pass 3's end level; LI pass 3 drifts
#     -6..-9% and pass 4 sits flat at ITS end level — directions and
#     magnitudes reproduce on fresh lifetimes.
#   REFUTES it: fresh lifetimes show FLAT first passes (the campaign's drift
#     was a one-off or a box-time artifact); or the drifts reverse sign; or
#     pass 4 keeps drifting instead of plateauing (continuous degradation —
#     a different finding, worse for RR).
#   WHAT n=4 WITH LIFETIME CONTROLLED CLAIMS THAT n=2 CANNOT: a
#     steady-state (plateau) LI-vs-RR comparison at n=2 per side — the
#     production-relevant number — separated from a first-hours transient
#     also at n=2 per side; and the arm-order alternation across the two
#     campaigns removes box time as a confound. n=2 could only average a
#     transient with a plateau and call it a mean.
#
# Everything else = run_plan_films500.sh's proven forms (lock shared —
# cannot overlap a plan; FAST step 0; helpers copied; mirror self-launched).
# Committed script + self-printed sha256 (entry 25).
# PROJECTED WALL: RR 2 x ~3.7 h + LI 2 x ~3.5 h + 2 bring-ups + 4 warm-ups
# ≈ 15.5 h. Idle watchdog: legs are CPU-heavy, step 0 is seconds — no
# keepalive needed (sequence-doc ruling).
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE/../.."
echo "run_films500_lifetimes.sh sha256: $(sha256sum "working/video/run_films500_lifetimes.sh" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"
PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing"; exit 1; }

# ---- RULED/BAKED ---------------------------------------------------------
M_TOKENS=16; RR_TENV=2; LI_TENV=2; BLAST_C=16; N_MEASURED=498
PASSES_PER_LIFETIME=2          # data-supported (transient + plateau); 1 = the ruling's original form
FIRST_PASS_NO=3                # continues the campaign's p1/p2 numbering
VIDEO_MANIFEST="working/video/films500_video_manifest.jsonl"
GOLDEN="working/video/golden_films_record.json"
ARMING="${ARMING:-$HOME/films_probe/gate3_films500/arming.json}"
PDF_CORPUS="${PDF_CORPUS:-$PWD/corpus/govdocs1/pdfs}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"; LI_IMAGE="${LI_IMAGE:-li:video}"
for f in "$VIDEO_MANIFEST" "$GOLDEN" "$ARMING"; do [ -f "$f" ] || { echo "NOT DONE — missing $f"; exit 1; }; done
[ -d "$PDF_CORPUS" ] || { echo "NOT DONE — PDF_CORPUS=$PDF_CORPUS"; exit 1; }

LIVENESS_MIN="$("$PY" -c "
import json; a=json.load(open('$ARMING')); assert a.get('armed') is True
lm=a['liveness']['liveness_min']; print('NOT_RUN' if lm is None else lm)")"
if ! LOC_OUT="$("$PY" working/video/corpus_locator.py --manifest "$VIDEO_MANIFEST" --tool run_films500_lifetimes)"; then
  echo "$LOC_OUT"; exit 1; fi
CORPUS_DIR="${LOC_OUT%%$'\n'*}"; CORPUS_SRC="${LOC_OUT#*$'\n'}"
[ -d "$CORPUS_DIR" ] || { echo "NOT DONE — CORPUS_DIR=$CORPUS_DIR"; exit 1; }

# shared plan lock — a lifetime run can never overlap a plan (or vice versa)
exec 9>"$HOME/.films500_plan.lock"
if ! flock -n 9; then
  echo "NOT DONE — another films500 plan/lifetime run is ALIVE:"; pgrep -af 'run_plan_films500|run_films500_lifetimes' | grep -v "^$$ " | sed 's/^/  /'
  [ -f "$HOME/.films500_plan.current" ] && echo "  its run dir: $(cut -d' ' -f2- "$HOME/.films500_plan.current")"; exit 1
fi
OUT="working/video/results/films500_lifetimes_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"; echo "$$ $OUT" > "$HOME/.films500_plan.current"
LOG="$OUT/run_films500_lifetimes.log"
echo "plan lock held (pid $$); run dir $OUT; corpus $CORPUS_DIR [$CORPUS_SRC]" | tee -a "$LOG"
nohup bash working/video/probe/mirror_films500.sh "$PWD/$OUT" > "$OUT/mirror.log" 2>&1 &
echo "MIRROR self-launched (pid $!) -> ansh/films500-live-$(basename "$OUT")/" | tee -a "$LOG"

run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; local rc=${PIPESTATUS[0]}
  [ "$rc" = "0" ] || { echo "STEP FAILED rc=$rc: $*" | tee -a "$LOG"; exit "$rc"; }; }
envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n -e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }
container_age_s() {  # $1 container -> seconds since Created
  local created; created="$(docker inspect -f '{{.Created}}' "$1" 2>/dev/null)"
  "$PY" -c "
import sys, time, datetime
t = datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')); print(int(time.time()-t.timestamp()))" "$created"
}
lifetime_json() {  # $1 container  $2 lifetime_id  $3 pass_in_lifetime
  "$PY" -c "
import json, sys, subprocess
c, lid, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
created = subprocess.run(['docker','inspect','-f','{{.Created}}',c],capture_output=True,text=True).stdout.strip()
print(json.dumps({'container': c, 'lifetime_id': lid, 'created': created,
                  'age_at_leg_start_s': int(sys.argv[4]), 'pass_in_lifetime': k,
                  'design': 'fresh lifetime per arm, arms alternated vs the campaign (RR first), '
                            f'{sys.argv[5]} passes per lifetime; pass 1 of a lifetime = transient, pass 2 = plateau (pre-registered)'}))" \
    "$1" "$2" "$3" "$(container_age_s "$1")" "$PASSES_PER_LIFETIME"
}
stop_arm() { docker logs "$1" > "$OUT/dockerlog_$1${2:+_$2}_final.txt" 2>&1 || true; docker rm -f "$1" >/dev/null 2>&1 || true; }
LI_PORTS="8802-8817"; LI_CONTAINERS=""; for i in $(seq 0 15); do LI_CONTAINERS="$LI_CONTAINERS,li_bal_$i"; done; LI_CONTAINERS="${LI_CONTAINERS#,}"
start_rr() { docker rm -f rr 2>/dev/null || true
  # shellcheck disable=SC2086
  run docker run -d --name rr --memory 58g $(envargs "$RR_TENV") --log-opt max-size=200m --network host "$RR_IMAGE"
  run "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr; }
start_li() { local i; for i in $(seq 0 15); do docker rm -f "li_bal_$i" 2>/dev/null || true
    # shellcheck disable=SC2086
    run docker run -d --name "li_bal_$i" --memory 3g $(envargs "$LI_TENV") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$LI_IMAGE" -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30"; done
  for i in $(seq 0 15); do run "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) --workers 1 --container "li_bal_$i" --deadline 1200; done; }
stop_li() { local i; for i in $(seq 0 15); do stop_arm "li_bal_$i"; done; }
RR_IMAGE_LINEAGE="Crossroad 33 (2026-08-22): rr:patched-video = a docker/Dockerfile.rocketride build PLUS one documented derived layer replacing working/nodes/env_probe; full rebuild deliberately DEFERRED (floating base); the image every RR number was measured on."
LI_IMAGE_LINEAGE="docker/Dockerfile.llamaindex-video at the Ruling-L config (4000/0): FULL 149-pin freeze install with fail-closed read-back (b295dea), streaming reader (spool -> frames-on-disk -> k=1)."
DRIVER=("$PY" working/video/driver_video.py --out-dir "$OUT" --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR")
LIVE_ARGS=(); [ "$LIVENESS_MIN" = "NOT_RUN" ] || LIVE_ARGS=(--liveness-min-fraction "$LIVENESS_MIN")

"$PY" - "$OUT/run_manifest.json" <<PYMAN
import json, subprocess, time
json.dump({'run_dir': '$OUT', 'campaign': 'films500_lifetimes', 'throughput_only': True,
 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
 'git_sha': subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip(),
 'design': {'lifetimes': ['RR fresh (passes 3,4)', 'LI fresh (passes 3,4)'], 'arm_order': 'RR first (reversed vs campaign LI-first)',
            'passes_per_lifetime': $PASSES_PER_LIFETIME, 'first_pass_no': $FIRST_PASS_NO, 'C': $BLAST_C, 'N_measured': $N_MEASURED,
            'why': 'campaign passes drifted within one lifetime: RR p1 +4.8pct first->last20pct then p2 flat; LI p1 -8.5pct then p2 flat (position fit on landed records)'},
 'pre_registered': {'confirms': 'RR p3 +3..6pct drift, p4 flat at p3 end; LI p3 -6..-9pct, p4 flat at its end',
                    'refutes': 'flat first passes; reversed signs; or p4 still drifting (continuous degradation)',
                    'n4_claims': 'plateau LI-vs-RR at n=2/side separated from transient n=2/side; arm-order alternation removes box time'},
 'no_cross_gates': 'partition settled: 433 predicted, 433 measured, 0 violations',
 'completed': False}, open('$OUT/run_manifest.json','w'), indent=1)
PYMAN

echo "=== LIFETIME PASSES: RR fresh (p3,p4) -> LI fresh (p3,p4); C=$BLAST_C; N=$N_MEASURED; liveness=$LIVENESS_MIN; THROUGHPUT ONLY ===" | tee -a "$LOG"
echo "=== PRE-REGISTERED: confirms = RR p3 drifts +3..6% & p4 flat at p3's end, LI p3 -6..-9% & p4 flat; refutes = flat p3s / reversed signs / p4 still drifting ===" | tee -a "$LOG"

echo "--- 0. corpus check: FAST mode (stat census + 5-film sha spot; stamp via locator) ---" | tee -a "$LOG"
run "$PY" - "$VIDEO_MANIFEST" "$CORPUS_DIR" <<'PYV'
import json, sys, os, hashlib
rows=[json.loads(l) for l in open(sys.argv[1]) if '"file"' in l]; corpus=sys.argv[2]; bad=[]
for r in rows:
    p=os.path.join(corpus,r['file'])
    if not os.path.exists(p) or os.path.getsize(p)!=r['bytes']: bad.append(r['file'])
if bad: print('NOT DONE — census:', bad[:5]); raise SystemExit(1)
srt=sorted(rows,key=lambda r:r['file'])
for r in [srt[i] for i in (0,len(srt)//4,len(srt)//2,3*len(srt)//4,len(srt)-1)]:
    h=hashlib.sha256(); f=open(os.path.join(corpus,r['file']),'rb')
    for c in iter(lambda: f.read(1<<22), b''): h.update(c)
    if h.hexdigest()!=r['sha256']: print('NOT DONE — spot sha', r['file']); raise SystemExit(1)
print(f'corpus check FAST PASS: {len(rows)}/{len(rows)} census + 5 spot shas')
PYV

echo "--- 1. RR M16xT2, FRESH lifetime, passes $FIRST_PASS_NO..$((FIRST_PASS_NO+PASSES_PER_LIFETIME-1)) ---" | tee -a "$LOG"
start_rr
for k in $(seq 1 "$PASSES_PER_LIFETIME"); do
  P=$((FIRST_PASS_NO+k-1)); LT="$(lifetime_json rr rr-L2 "$k")"
  echo "RR pass $P: $LT" | tee -a "$LOG"
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n "$N_MEASURED" --blast-concurrency "$BLAST_C" \
      --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" --pass "$P" "${LIVE_ARGS[@]}" \
      --image-lineage "$RR_IMAGE_LINEAGE" --container-lifetime "$LT"
done
stop_arm rr L2

echo "--- 2. LI N16xT2, FRESH lifetime, passes $FIRST_PASS_NO..$((FIRST_PASS_NO+PASSES_PER_LIFETIME-1)) ---" | tee -a "$LOG"
start_li
for k in $(seq 1 "$PASSES_PER_LIFETIME"); do
  P=$((FIRST_PASS_NO+k-1)); LT="$(lifetime_json li_bal_0 li-L2 "$k")"
  echo "LI pass $P: $LT" | tee -a "$LOG"
  run "${DRIVER[@]}" --arm llamaindex --leg blast --n "$N_MEASURED" --blast-concurrency "$BLAST_C" --pass "$P" \
      --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
      --image-lineage "$LI_IMAGE_LINEAGE" --container-lifetime "$LT"
done
stop_li

"$PY" - "$OUT/run_manifest.json" <<'PYDONE'
import json, sys, time
m=json.load(open(sys.argv[1])); m['completed']=True; m['completed_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
json.dump(m, open(sys.argv[1],'w'), indent=1)
PYDONE
touch "$OUT/MIRROR_STOP"
echo "=== LIFETIME PASSES COMPLETE — $OUT (mirror stops after its final sync). Entry-26 STOP-AND-LAND next. ===" | tee -a "$LOG"
