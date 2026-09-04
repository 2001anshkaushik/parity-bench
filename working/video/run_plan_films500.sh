#!/usr/bin/env bash
# =============================================================================
# FILMS-500 MAIN RUN — built to Ansh's SCOPE RULING (2026-09-03). Every number
# BAKED (entry 25: env knobs are how ruled campaigns stop being ruled).
#
#   CELLS (ruled): RR M16xT2 and LI N16xT2 ONLY, 498 measured films, TWO
#   blast passes each, BLAST_C=16 (Ruling O), splitter 4000/0 (Ruling L).
#   THE RR DEFAULT CELL IS SKIPPED — ruled reasoning, recorded: a default
#   pass at 500 costs ~19 h (161,940 frames / 2.35 f/s measured) — as much
#   as both headline cells at two passes — to answer a question already
#   answered twice at n=2 (films-35 spread 0.77%; AMI-168 spread 0.77%).
#   The out-of-box finding ships from those measurements at their own N,
#   with the N stated wherever it appears; Leela's runbook defines no
#   default-RocketRide cell, so nothing cross-team depends on one.
#
#   SEQUENTIAL LEGS: n=5 per cell, EXPLICITLY NOT SCALED with the corpus
#   (ruled): they exist for gate 8 (determinism repeat), uncontended
#   per-film latency, and the speedup divisor — none of which scale with N.
#
#   WARM SPLIT: 498 measured + 2 warm (manifest role rows). The warm
#   pair is DERIVED at manifest build as corpus minus her measured 498
#   (her committed per_doc @3967d9f4, mirrored in
#   films500_her_measured_set.txt): yanks_are_coming + zontar — so our
#   measured set equals hers BY CONSTRUCTION (diff=0), for cross-team
#   joins. (The earlier "last 2 of queue order" reading was wrong —
#   her convention is sorted order, and only her records are ground
#   truth; builder v4.)
#
#   ARMING: read from run_films500_staging.sh's arming.json — a MULTI-FILM
#   basis SPANNING the 560px boundary (§10.4 lesson): <=560 control must
#   agree strictly; >560 divergence expected. LIVENESS_MIN = Ruling-R
#   formula over both staged films. Never typed.
#
#   CROSS-GATE EXPECTATION, STATED BEFORE THE RUN (ruled, so nobody reads
#   it as a failure): gate 3 WILL FAIL on ~433 of the 498 measured films
#   — the landed manifest counts 435/500 above the 560px edge (detector
#   basis; both warm films are above it too) and the partition predicts
#   every one of them diverges. That is
#   the expected, already-ruled outcome (Ruling U), NOT a stop condition,
#   and this plan does not treat it as one. The check that matters is the
#   PARTITION ITSELF: if films above 560px PASS, or films below it FAIL,
#   that is a finding that changes Ruling U — flagged LOUDLY by the
#   partition check below (exit 2), never buried in a count.
#
#   $/1k FOOTAGE-HOUR (ruled): published as a results row in this
#   campaign's report. Every export already computes
#   efficiency.usd_per_1k_footage_hours (basis in-export: $1.428/h /
#   x_realtime x 1000) — the run_manifest records the publication ruling.
#
# Helpers are the proven run_plan_films.sh forms, copied. Committed script,
# self-printed sha256 (entry 25).
#
# PROJECTED WALL (from measured films-35 rates; assumptions in
# FILMS500_SEQUENCE.md): LI ~4.4 h/pass, RR ~4.7 h/pass, x2 passes each
# + seq/warm/cross overhead ~2 h => ~20-22 h total. Mirror runs beside it.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../.."   # repo root
echo "run_plan_films500.sh sha256: $(sha256sum "working/video/run_plan_films500.sh" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing (venv with psutil+rocketride)"; exit 1; }

# ---- RULED NUMBERS (scope ruling 2026-09-03) — baked, not knobs -------------
M_TOKENS=16; RR_TENV=2; LI_INSTANCES=16; LI_TENV=2
BLAST_C=16; N_MEASURED=498; SEQ_N=5; PASSES=2
VIDEO_MANIFEST="working/video/films500_video_manifest.jsonl"
GOLDEN="working/video/golden_films_record.json"
ARMING="${ARMING:-$HOME/films_probe/gate3_films500/arming.json}"
PDF_CORPUS="${PDF_CORPUS:-$PWD/corpus/govdocs1/pdfs}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"
LI_IMAGE="${LI_IMAGE:-li:video}"
PREFLIGHT_ONLY="${PREFLIGHT_ONLY:-0}"

[ -f "$VIDEO_MANIFEST" ] || { echo "NOT DONE — 500 manifest missing: $VIDEO_MANIFEST"; exit 1; }
[ -f "$GOLDEN" ] || { echo "NOT DONE — golden missing: $GOLDEN"; exit 1; }
[ -f "$ARMING" ] || { echo "NOT DONE — arming missing: $ARMING (run_films500_staging.sh)"; exit 1; }
[ -d "$PDF_CORPUS" ] || { echo "NOT DONE — PDF_CORPUS=$PDF_CORPUS is not a directory"; exit 1; }

# Manifest sanity: her frozen source pin + the measured/warm split, from meta.
"$PY" - "$VIDEO_MANIFEST" <<'PYMF'
import json, sys
meta = next(json.loads(l)['_meta'] for l in open(sys.argv[1]) if '"_meta"' in l)
assert meta['corpus_manifest_sha256'].startswith('bd0c915e'), \
    f"NOT DONE — manifest source pin {meta['corpus_manifest_sha256'][:8]} != bd0c915e"
assert meta['n_measured'] == 498 and meta['n_warm'] == 2, \
    f"NOT DONE — split {meta['n_measured']}+{meta['n_warm']} != 498+2"
print(f"manifest meta OK: n={meta['n_files']} ({meta['n_measured']}+{meta['n_warm']}), "
      f"frames={meta['total_frames']}, >560px(detector) "
      f"{meta['n_above_560px_detector_basis']}/{meta['n_files']}, "
      f"container!=detector: {meta['n_container_detector_mismatch']}")
PYMF

ARM_OUT="$("$PY" - "$ARMING" <<'PYARM'
import json, sys
a = json.load(open(sys.argv[1]))
if a.get('armed') is not True:
    raise SystemExit(f"NOT DONE — arming.json says armed={a.get('armed')!r}")
if 'SPANS THE 560px' not in a.get('basis', ''):
    raise SystemExit('NOT DONE — arming basis does not state the 560px span '
                     '(scope ruling: the staged set must span the boundary)')
lm = a['liveness']['liveness_min']
if lm is not None and not (0.0 < float(lm) <= 1.0):
    raise SystemExit(f'NOT DONE — liveness_min={lm!r} out of (0,1]')
print(a['gate3_run_id'])
print('NOT_RUN' if lm is None else lm)
PYARM
)" || { echo "$ARM_OUT"; exit 1; }
GATE3_RUN_ID="${ARM_OUT%%$'\n'*}"
LIVENESS_MIN="${ARM_OUT#*$'\n'}"
echo "armed: gate3=$GATE3_RUN_ID liveness_min=$LIVENESS_MIN (multi-film span basis, from $ARMING)"

if ! LOC_OUT="$("$PY" working/video/corpus_locator.py --manifest "$VIDEO_MANIFEST" --tool run_plan_films500)"; then
  echo "$LOC_OUT"; echo "NOT DONE — corpus_dir could not be resolved (above)"; exit 1
fi
CORPUS_DIR="${LOC_OUT%%$'\n'*}"; CORPUS_SRC="${LOC_OUT#*$'\n'}"
[ -d "$CORPUS_DIR" ] || { echo "NOT DONE — CORPUS_DIR=$CORPUS_DIR is not a directory"; exit 1; }

OUT="working/video/results/films500_mainrun_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
LOG="$OUT/run_plan_films500.log"
echo "corpus: manifest=$VIDEO_MANIFEST corpus_dir=$CORPUS_DIR [$CORPUS_SRC]" | tee -a "$LOG"
echo "MIRROR: launch beside this run —" | tee -a "$LOG"
echo "  box.sh launch mirror500 'bash ~/parity-bench-video/working/video/probe/mirror_films500.sh $PWD/$OUT'" | tee -a "$LOG"

run() {  # run_plan.sh:166-172 form — ${PIPESTATUS[0]}, never $?
  echo "+ $*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  [ "$rc" = "0" ] || { echo "STEP FAILED rc=$rc: $*" | tee -a "$LOG"; exit "$rc"; }
}

envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

container_provenance() {   # run_plan.sh:186-208 form
  local name="$1" tag="${2:-}" id created age
  id="$(docker inspect -f '{{.Id}}' "$name" 2>/dev/null | cut -c1-12)"
  created="$(docker inspect -f '{{.Created}}' "$name" 2>/dev/null)"
  age="$("$PY" -c "
import sys, time, datetime
try:
    t = datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))
    print(int(time.time() - t.timestamp()))
except Exception:
    print(-1)
" "$created" 2>/dev/null || echo -1)"
  echo "container $name${tag:+ [$tag]}: id=$id created=$created age=${age}s" | tee -a "$LOG"
  if [ "$age" -lt 0 ] 2>/dev/null || [ "$age" -gt 600 ]; then
    echo "NOT DONE — $name container state unknown or pre-existing (age=${age}s)." | tee -a "$LOG"; exit 1
  fi
}

stop_arm() {
  docker logs "$1" > "$OUT/dockerlog_$1${2:+_$2}_final.txt" 2>&1 || true
  docker rm -f "$1" >/dev/null 2>&1 || true
}

LI_PORTS="8802-8817"; LI_CONTAINERS=""
for i in $(seq 0 15); do LI_CONTAINERS="$LI_CONTAINERS,li_bal_$i"; done
LI_CONTAINERS="${LI_CONTAINERS#,}"

start_rr() {
  local t="$1" env_args=""
  docker rm -f rr 2>/dev/null || true
  [ "$t" = "unset" ] || env_args="$(envargs "$t")"
  # shellcheck disable=SC2086
  run docker run -d --name rr --memory 58g $env_args \
      --log-opt max-size=200m --network host "$RR_IMAGE"
  run "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  container_provenance rr "$t"
}

start_li_balanced() {
  local i
  for i in $(seq 0 15); do
    docker rm -f "li_bal_$i" 2>/dev/null || true
    # shellcheck disable=SC2086
    run docker run -d --name "li_bal_$i" --memory 3g $(envargs "$LI_TENV") \
        -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$LI_IMAGE" -c \
        "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30"
  done
  for i in $(seq 0 15); do
    run "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
        --workers 1 --container "li_bal_$i" --deadline 1200
    container_provenance "li_bal_$i" "N16xT${LI_TENV}"
  done
}

stop_li_balanced() { local i; for i in $(seq 0 15); do stop_arm "li_bal_$i"; done; }

RR_IMAGE_LINEAGE="Crossroad 33 (2026-08-22): rr:patched-video = a docker/Dockerfile.rocketride build PLUS one documented derived layer replacing working/nodes/env_probe (the instrument node; absent from the measured pipe, and carrying no requirements.txt so the engine constraints-cache key cannot move). A full rebuild was deliberately DEFERRED: it would re-resolve the floating ubuntu:22.04 base, the unpinned apt libc++/libunwind the engine ELF links, and the bootcheck constraints cache COPYed into the image, replacing the image that every RR probe number and the gate-3 arming run were measured on. PATH B re-baseline scheduled post-campaign with before/after fingerprints."
LI_IMAGE_LINEAGE="docker/Dockerfile.llamaindex-video at the Ruling-L config (4000/0): FULL 149-pin freeze install from li_video/li_image_freeze.txt with a fail-closed build-time read-back (pip freeze == freeze file; b295dea), streaming reader (spool -> frames-on-disk -> k=1), chunk config read back per leg from every worker's /health by the driver preflight."

DISCLOSURES="DISCLOSURES: gate-3 strict FAILURES on >560px films are the RULED EXPECTATION (Ruling U; the partition check is the finding surface, not the failure count); char_conservation at the Phase-1 +/-2 pct default is band-cutting DATA (Ruling W deferral stands); the boundary-exclusion drift cap (0.5 pct/video) is LIVE and UNSIZED for films content (H16 open)."

DRIVER=("$PY" working/video/driver_video.py --out-dir "$OUT" \
        --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR")
LIVE_ARGS=()
[ "$LIVENESS_MIN" = "NOT_RUN" ] || LIVE_ARGS=(--liveness-min-fraction "$LIVENESS_MIN")

"$PY" - "$OUT/run_manifest.json" "$ARMING" <<PYMAN
import json, subprocess, sys, time
arm = json.load(open(sys.argv[2]))
m = {
 'run_dir': '$OUT', 'campaign': 'films500_mainrun',
 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
 'git_sha': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                           text=True).stdout.strip(),
 'preflight_only': '$PREFLIGHT_ONLY' == '1',
 'ruled_numbers': {
  'scope_ruling': ('2026-09-03: RR M16xT2 + LI N16xT2 ONLY at 500 films, 2 blast passes each. '
                   'RR DEFAULT SKIPPED — ~19 h/pass to re-answer a question answered twice at '
                   'n=2 (films-35 0.77 pct spread; AMI-168 0.77 pct); the out-of-box finding '
                   'ships from those runs at their own N, N stated wherever it appears; her '
                   'runbook defines no default-RocketRide cell. SEQ_N=5 NOT scaled with the '
                   'corpus (gate 8 / uncontended latency / speedup divisor do not scale with N).'),
  'M_TOKENS': $M_TOKENS, 'RR_THREADS_ENV': $RR_TENV,
  'LI_INSTANCES': $LI_INSTANCES, 'LI_THREADS_ENV': $LI_TENV,
  'BLAST_C': $BLAST_C, 'N_MEASURED': $N_MEASURED, 'SEQ_N': $SEQ_N,
  'PASSES': $PASSES, 'WARM_N': 2,
  'usd_per_1k_footage_hours': ('PUBLISHED as a results row (ruled 2026-09-03): every export '
                               'computes efficiency.usd_per_1k_footage_hours, basis in-export '
                               '(1.428 USD/h / x_realtime x 1000)'),
 },
 'cross_gate_expectation': ('STATED BEFORE THE RUN (ruled): gate 3 will FAIL on ~433 of the '
                            '498 measured films (landed manifest: 435/500 above the 560px edge, '
                            'detector basis) — every >560px film is expected to diverge (Ruling U). '
                            'Expected outcome, NOT a stop condition; the finding surface is the '
                            'PARTITION CHECK (>560 diverging, <=560 clean) — a violation in '
                            'EITHER direction changes Ruling U and exits loudly.'),
 'arming': arm,
 'corpus': {'manifest': '$VIDEO_MANIFEST', 'corpus_dir': '$CORPUS_DIR',
            'source_manifest_sha256_expected': 'bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1'},
 'disclosures': '''$DISCLOSURES''',
 'completed': False,
}
json.dump(m, open(sys.argv[1], 'w'), indent=1)
print('run manifest:', sys.argv[1])
PYMAN

echo "=== FILMS-500 RUN: LI N${LI_INSTANCES}xT${LI_TENV} -> RR M${M_TOKENS}xT${RR_TENV}; C=$BLAST_C; N=$N_MEASURED; passes=$PASSES; seq_n=$SEQ_N; gate3=$GATE3_RUN_ID; liveness=$LIVENESS_MIN -> $OUT ===" | tee -a "$LOG"
echo "=== EXPECTATION (ruled, stated before the run): gate 3 FAILS on ~433 of 498 measured films (landed manifest: 435/500 above the 560px edge, detector basis) — every >560px film is expected to diverge (Ruling U). The failing list will be LONG. Not a stop condition. The partition check at the end is the finding surface. ===" | tee -a "$LOG"

echo "--- 0. corpus verify (read-only, full sha256) ---" | tee -a "$LOG"
run "$PY" working/video/fetch_ami_video.py --verify --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR"

echo "--- 1. LlamaIndex N16xT2 ---" | tee -a "$LOG"
start_rr unset
start_li_balanced
run "$PY" working/video/smoke_video.py --rr-container rr --li-container li_bal_0 \
    --rr-threads-env unset --pdf-corpus "$PDF_CORPUS" \
    --manifest "$VIDEO_MANIFEST" --corpus-dir "$CORPUS_DIR" --golden "$GOLDEN"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  run "${DRIVER[@]}" --arm llamaindex --leg sequential --n 1 --preflight-only \
      --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
      --image-lineage "$LI_IMAGE_LINEAGE"
else
  run "${DRIVER[@]}" --arm llamaindex --leg sequential --n "$SEQ_N" \
      --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
      --image-lineage "$LI_IMAGE_LINEAGE"
  for pass in $(seq 1 "$PASSES"); do
    echo "--- LI blast pass $pass/$PASSES ---" | tee -a "$LOG"
    run "${DRIVER[@]}" --arm llamaindex --leg blast --n "$N_MEASURED" \
        --blast-concurrency "$BLAST_C" --pass "$pass" \
        --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" "${LIVE_ARGS[@]}" \
        --image-lineage "$LI_IMAGE_LINEAGE"
  done
fi
stop_li_balanced
stop_arm rr idle

echo "--- 2. RocketRide M16xT2 (ruled posture; NO default cell — scope ruling) ---" | tee -a "$LOG"
start_rr "$RR_TENV"
if [ "$PREFLIGHT_ONLY" = "1" ]; then
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n 1 \
      --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" --preflight-only \
      "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
  stop_arm rr parity
  echo "=== PREFLIGHT_ONLY COMPLETE ===" | tee -a "$LOG"
  exit 0
fi
run "${DRIVER[@]}" --arm rocketride --posture parity --leg sequential --n "$SEQ_N" \
    --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" "${LIVE_ARGS[@]}" \
    --image-lineage "$RR_IMAGE_LINEAGE"
for pass in $(seq 1 "$PASSES"); do
  run "${DRIVER[@]}" --arm rocketride --posture parity --leg blast --n "$N_MEASURED" \
      --blast-concurrency "$BLAST_C" --tokens "$M_TOKENS" --rr-threads-env "$RR_TENV" \
      --pass "$pass" "${LIVE_ARGS[@]}" --image-lineage "$RR_IMAGE_LINEAGE"
done
stop_arm rr parity

echo "--- 3. cross-arm gates (gate 3 armed by $GATE3_RUN_ID; failures EXPECTED on >560px) ---" | tee -a "$LOG"
CROSS_FAIL=0
CROSS_LABEL="ruled 16x2-vs-16x2 posture at 500 films — cross-arm comparison | $DISCLOSURES"
for leg in sequential blast; do
  for RRJ in "$OUT/records_rocketride_video_parity_${leg}.jsonl" \
             "$OUT"/records_rocketride_video_parity_${leg}_p*.jsonl; do
    [ -f "$RRJ" ] || continue
    sfx="${RRJ##*/records_rocketride_video_parity_${leg}}"; sfx="${sfx%.jsonl}"
    LIJ="$OUT/records_llamaindex_video_workers_${leg}${sfx}.jsonl"
    [ -f "$LIJ" ] || { echo "cross: parity/$leg$sfx — no LI counterpart; skipped" | tee -a "$LOG"; continue; }
    echo "cross: parity/$leg$sfx" | tee -a "$LOG"
    if "$PY" working/video/driver_video.py --cross "$RRJ" "$LIJ" \
        --gate3-armed "$GATE3_RUN_ID" --cross-label "$CROSS_LABEL" \
        > "$OUT/cross_parity_${leg}${sfx}.json" 2>>"$LOG"; then
      echo "cross gates PASS: parity/$leg$sfx" | tee -a "$LOG"
    else
      CROSS_FAIL=1
      echo "cross gates read FAIL: parity/$leg$sfx (EXPECTED on this corpus — see partition check)" | tee -a "$LOG"
    fi
  done
done

echo "--- 4. PARTITION CHECK (the finding surface — Ruling U's 560px prediction at 500) ---" | tee -a "$LOG"
"$PY" - "$OUT" "$VIDEO_MANIFEST" > "$OUT/partition_check.json" <<'PYPART'
import json, sys, glob, os
out, manifest = sys.argv[1], sys.argv[2]
dims = {}
for line in open(manifest):
    r = json.loads(line)
    if 'file' in r:
        dims[r['file']] = max(r['detector_width'], r['detector_height'])
checks = []
for cp in sorted(glob.glob(os.path.join(out, 'cross_parity_blast*.json'))):
    c = json.load(open(cp))
    pv = c.get('cross_detection_agreement', {}).get('per_video') or {}
    above_pass, below_fail, missing = [], [], []
    n_above_div = n_below_clean = 0
    for film, v in pv.items():
        edge = dims.get(film)
        if edge is None:
            missing.append(film); continue
        if edge > 560:
            if v.get('PASS'): above_pass.append(film)
            else: n_above_div += 1
        else:
            if v.get('PASS'): n_below_clean += 1
            else: below_fail.append(film)
    checks.append({'cross_file': os.path.basename(cp),
                   'n_above_diverging': n_above_div,
                   'n_below_clean': n_below_clean,
                   'ABOVE_560_PASSING': above_pass,
                   'BELOW_560_FAILING': below_fail,
                   'missing_dimensions': missing})
holds = all(not c['ABOVE_560_PASSING'] and not c['BELOW_560_FAILING']
            and not c['missing_dimensions'] for c in checks) and bool(checks)
doc = {'partition_holds': holds, 'edge_px': 560, 'checks': checks,
       'ruling': ('HOLDS: the 560px partition reproduced at 500 — Ruling U stands, '
                  'gate-3 failures above the edge are the ruled expectation.'
                  if holds else
                  'VIOLATION: films crossed the partition — THIS CHANGES RULING U. '
                  'Flag loudly; do not report a count as if it were the finding.')}
json.dump(doc, sys.stdout, indent=1)
PYPART
PARTITION_RC=0
"$PY" - "$OUT/partition_check.json" <<'PYSAY' 2>&1 | tee -a "$LOG" || PARTITION_RC=${PIPESTATUS[0]}
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({k: d[k] for k in ('partition_holds', 'ruling')}, indent=1))
for c in d['checks']:
    print(f"  {c['cross_file']}: above-diverging={c['n_above_diverging']} "
          f"below-clean={c['n_below_clean']} "
          f"VIOLATIONS above-passing={len(c['ABOVE_560_PASSING'])} "
          f"below-failing={len(c['BELOW_560_FAILING'])} "
          f"missing-dims={len(c['missing_dimensions'])}")
if not d['partition_holds']:
    print('*** PARTITION VIOLATION — THIS CHANGES RULING U — STOP AND REPORT ***')
    raise SystemExit(2)
PYSAY

"$PY" - "$OUT/run_manifest.json" "$CROSS_FAIL" "$PARTITION_RC" <<'PYDONE'
import json, sys, time
m = json.load(open(sys.argv[1]))
m['completed'] = True
m['cross_gates_failed'] = sys.argv[2] == '1'
m['cross_gates_failed_note'] = ('EXPECTED per the pre-run ruling (Ruling U at 500): '
                                'gate-3 failures above 560px are the ruled outcome, '
                                'not a defect — the partition check is the verdict surface')
m['partition_check_rc'] = int(sys.argv[3])
m['completed_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
json.dump(m, open(sys.argv[1], 'w'), indent=1)
PYDONE

echo "=== FILMS-500 RUN COMPLETE (cross_fail=$CROSS_FAIL [expected], partition_rc=$PARTITION_RC) — $OUT ===" | tee -a "$LOG"
echo "Touch $OUT/MIRROR_STOP to end the mirror after the final sync." | tee -a "$LOG"
echo "ENTRY 26 STOP-AND-LAND: the box commits $OUT and bundles; no laptop push onto this base until ls-remote confirms." | tee -a "$LOG"
if [ "$PARTITION_RC" != "0" ]; then
  echo "*** PARTITION VIOLATION (rc=$PARTITION_RC) — THIS CHANGES RULING U ***" | tee -a "$LOG"
  exit 2
fi
exit 0
