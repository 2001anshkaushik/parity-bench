#!/usr/bin/env bash
# =============================================================================
# FILMS-500 STAGING (scope ruling 2026-09-03 + the §10.4 arming lesson).
# Runs ONCE before run_plan_films500.sh and produces the arming artifact the
# campaign refuses to start without.
#
# WHAT CHANGED FROM THE 35-CAMPAIGN STAGING (and why, recorded):
#   * The staged same-frames set SPANS THE 560px BOUNDARY — the 35 campaign
#     staged one sub-560px film, which structurally could not exhibit the
#     divergence (§10.4 lesson). Staged set, both with COMMITTED byte-parity
#     proofs that the arms decode identical frames:
#       - 20000LeaguesUndertheSea.mp4 (320x240, <=560): the STRICT-AGREEMENT
#         CONTROL — gate-3 disagreement HERE means the instrument is broken
#         and nothing arms.
#       - HouseOnBareMountain.mp4 (714x480, >560): divergence EXPECTED per
#         Ruling U — recorded in the arming artifact as expected, NEVER an
#         arming failure. Its liveness rides into LIVENESS_MIN.
#   * LIVENESS_MIN (Ruling R, unchanged formula): 0.5 x the measured MINIMUM
#     non-empty-frame fraction — now the minimum ACROSS BOTH staged films;
#     the arming artifact states the basis is multi-film and spans the
#     resolution boundary, unlike the 35 campaign's single sub-560px film.
#   * The films GOLDEN is REUSED in COMPARE mode (write-once honored): the
#     golden film is in this corpus byte-identically (subset hardlinked into
#     full500), so the smoke compares instead of rewriting.
#
# Prereqs: fetch_films500.sh census clean; films500_video_manifest.jsonl
# landed at repo HEAD (built by build_films500_manifest.sh, null control
# passed); repo pulled on the box.
# Cost ~45-75 min (bring-ups ~10, verify+stamp ~15, smoke-compare ~5, staged
# legs 643 frames/arm at ~0.6-1.2 f/s single-lane ~10-18/arm, derive s).
# Committed script + self-printed sha256 (entry 25).
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$ROOT"
echo "run_films500_staging.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PYBIN:-$HOME/.venv/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing"; exit 1; }
MANIFEST="working/video/films500_video_manifest.jsonl"
STAGING_MANIFEST="working/video/films500_staging_manifest.jsonl"
GOLDEN="working/video/golden_films_record.json"
OUT="${OUT:-$HOME/films_probe/gate3_films500}"
PDF_CORPUS="${PDF_CORPUS:-$PWD/corpus/govdocs1/pdfs}"
RR_IMAGE="${RR_IMAGE:-rr:patched-video}"
LI_IMAGE="${LI_IMAGE:-li:video}"
CORPUS_DIR="$HOME/films_corpus/full500"
CONTROL="20000LeaguesUndertheSea.mp4"     # <=560 strict control
EXPECTED_DIVERGER="HouseOnBareMountain.mp4"  # >560, divergence EXPECTED (Ruling U)
mkdir -p "$OUT"
[ -f "$MANIFEST" ] || { echo "NOT DONE — $MANIFEST missing (build + land it first)"; exit 1; }
[ -f "$GOLDEN" ] || { echo "NOT DONE — $GOLDEN missing (the 35-campaign wrote it once; it is reused here)"; exit 1; }
[ -d "$PDF_CORPUS" ] || { echo "NOT DONE — PDF_CORPUS=$PDF_CORPUS not a directory"; exit 1; }
[ -d "$CORPUS_DIR" ] || { echo "NOT DONE — $CORPUS_DIR missing (fetch_films500.sh first)"; exit 1; }

echo "== 0a. full sha256 verify + corpus_dir stamp on the 500 manifest (T item 5 form) =="
"$PY" working/video/fetch_ami_video.py --stamp-corpus-dir --corpus-dir "$CORPUS_DIR" --manifest "$MANIFEST"

echo "== 0b. staged 2-row manifest (verbatim rows from the 500 manifest; span check fail-closed) =="
"$PY" - "$MANIFEST" "$STAGING_MANIFEST" "$CONTROL" "$EXPECTED_DIVERGER" <<'PYSM'
import json, sys
src, dst, control, diverger = sys.argv[1:5]
lines = [json.loads(l) for l in open(src)]
meta = next(l['_meta'] for l in lines if '_meta' in l)
rows = {r['file']: r for r in lines if 'file' in r}
sel = []
for name, kind in ((control, 'control'), (diverger, 'expected-diverger')):
    r = rows.get(name)
    if r is None:
        print(f'REFUSE — staged film not in the 500 manifest: {name}'); raise SystemExit(3)
    long_edge = max(r['detector_width'], r['detector_height'])
    if kind == 'control' and long_edge > 560:
        print(f'REFUSE — control {name} long edge {long_edge} > 560'); raise SystemExit(3)
    if kind == 'expected-diverger' and long_edge <= 560:
        print(f'REFUSE — expected-diverger {name} long edge {long_edge} <= 560'); raise SystemExit(3)
    r = dict(r); r['role'] = 'measured'; r['staging_kind'] = kind
    sel.append(r)
smeta = {'_meta': {**meta, 'staging_of': src,
                   'staging_basis': 'multi-film, spans the 560px boundary '
                                    '(§10.4 lesson): control <=560 + expected-diverger >560'}}
with open(dst, 'w') as f:
    f.write(json.dumps(smeta) + '\n')
    for r in sel: f.write(json.dumps(r) + '\n')
print(f'staging manifest: {dst} — ' + '; '.join(
    f"{r['file']} {r['detector_width']}x{r['detector_height']} ({r['staging_kind']})" for r in sel))
PYSM
"$PY" working/video/fetch_ami_video.py --verify --manifest "$STAGING_MANIFEST" --corpus-dir "$CORPUS_DIR"

LI_PORTS="8802-8817"; LI_CONTAINERS=""
for i in $(seq 0 15); do LI_CONTAINERS="$LI_CONTAINERS,li_bal_$i"; done
LI_CONTAINERS="${LI_CONTAINERS#,}"
teardown() { docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in $(seq 0 15); do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done; }
trap teardown EXIT
envargs() { local n="$1"; echo "-e OMP_NUM_THREADS=$n -e MKL_NUM_THREADS=$n \
-e OPENBLAS_NUM_THREADS=$n -e VECLIB_MAXIMUM_THREADS=$n -e NUMEXPR_NUM_THREADS=$n -e TORCH_NUM_THREADS=$n"; }

echo "== 1a. rr default lifetime =="
docker rm -f rr >/dev/null 2>&1 || true
docker run -d --name rr --memory 58g --log-opt max-size=200m --network host "$RR_IMAGE" >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr

echo "== 1b. LI balanced 16x1 at 3g (ruled shape) =="
for i in $(seq 0 15); do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory 3g $(envargs 2) \
      -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$LI_IMAGE" -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
done
for i in $(seq 0 15); do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done

echo "== 2. smoke, GOLDEN COMPARE mode (write-once honored; golden film byte-identical in full500) =="
"$PY" working/video/smoke_video.py --rr-container rr --li-container li_bal_0 \
    --rr-threads-env unset --pdf-corpus "$PDF_CORPUS" \
    --manifest "$MANIFEST" --corpus-dir "$CORPUS_DIR" --golden "$GOLDEN"

echo "== 3a. staged leg: RR default, BOTH staged films, sequential (--skip-warmup) =="
"$PY" working/video/driver_video.py --arm rocketride --posture default --leg sequential \
    --n 2 --rr-threads-env unset --skip-warmup \
    --manifest "$STAGING_MANIFEST" --corpus-dir "$CORPUS_DIR" --out-dir "$OUT" \
    --image-lineage "films500 staging leg — lineage recorded fully by run_plan_films500"

echo "== 3b. staged leg: LI balanced 16x1, BOTH staged films, sequential =="
"$PY" working/video/driver_video.py --arm llamaindex --leg sequential \
    --n 2 --skip-warmup --li-ports "$LI_PORTS" --li-containers "$LI_CONTAINERS" \
    --manifest "$STAGING_MANIFEST" --corpus-dir "$CORPUS_DIR" --out-dir "$OUT" \
    --image-lineage "films500 staging leg — lineage recorded fully by run_plan_films500"

echo "== 4a. CONTROL arming: the proven deriver judges the <=560 film alone =="
"$PY" - "$OUT" "$CONTROL" <<'PYF'
import json, sys, os
out, control = sys.argv[1], sys.argv[2]
for stem in ('rocketride_video_default_sequential', 'llamaindex_video_workers_sequential'):
    src = os.path.join(out, f'records_{stem}.jsonl')
    dst = os.path.join(out, f'records_{stem}.control.jsonl')
    with open(dst, 'w') as f:
        for line in open(src):
            if json.loads(line).get('video') == control:
                f.write(line)
    n = sum(1 for _ in open(dst))
    if n != 1:
        print(f'REFUSE — control filter wrote {n} rows from {src}'); raise SystemExit(3)
print('control-only record files written')
PYF
"$PY" working/video/probe/derive_gate3_arming.py \
    --rr-records "$OUT/records_rocketride_video_default_sequential.control.jsonl" \
    --li-records "$OUT/records_llamaindex_video_workers_sequential.control.jsonl" \
    --out "$OUT/arming_control.json"

echo "== 4b. COMPOSE the multi-film arming artifact (span basis + expected divergence recorded) =="
"$PY" - "$OUT" "$CONTROL" "$EXPECTED_DIVERGER" <<'PYC'
import json, sys, os, time, subprocess
out, control, diverger = sys.argv[1], sys.argv[2], sys.argv[3]
ac = json.load(open(os.path.join(out, 'arming_control.json')))
if ac.get('armed') is not True:
    print(f"NOT ARMED — the <=560 CONTROL disagreed (armed={ac.get('armed')!r}): the "
          "instrument is broken; this is a STOP finding, not an expected divergence.")
    raise SystemExit(3)
recs = {}
for stem, arm in (('rocketride_video_default_sequential', 'rr'),
                  ('llamaindex_video_workers_sequential', 'li')):
    for line in open(os.path.join(out, f'records_{stem}.jsonl')):
        r = json.loads(line)
        recs[(arm, r['video'])] = r
def nonempty_frac(r):
    m = r['frame_label_multisets']
    return sum(1 for fr in m if fr) / len(m)
fracs = {k: nonempty_frac(r) for k, r in recs.items()}
lm = 0.5 * min(fracs.values())
d_rr = recs[('rr', diverger)]['frame_label_multisets']
d_li = recs[('li', diverger)]['frame_label_multisets']
div = [i for i, (a, b) in enumerate(zip(d_rr, d_li)) if a != b]
sha = subprocess.run(['git', 'rev-parse', '--short=8', 'HEAD'],
                     capture_output=True, text=True).stdout.strip()
stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
arming = {
 'armed': True,
 'gate3_run_id': f'films500-staging-{stamp}-{sha}',
 'basis': ('MULTI-FILM, SPANS THE 560px RESOLUTION BOUNDARY (scope ruling '
           '2026-09-03; unlike the 35-film campaign, whose staged set was a '
           f'single sub-560px film — §10.4 lesson): control {control} '
           f'(<=560, strict agreement REQUIRED and measured) + '
           f'{diverger} (>560, divergence EXPECTED per Ruling U and measured).'),
 'control': {'film': control, 'arming': ac},
 'expected_diverger': {'film': diverger,
                       'n_frames': len(d_rr),
                       'n_diverging': len(div),
                       'diverged_as_expected': len(div) > 0,
                       'note': ('divergence here is the RULED expectation (Ruling U); '
                                'ZERO divergence on this >560px film would itself be a '
                                'finding to flag, not a pass to celebrate')},
 'liveness': {'liveness_min': lm,
              'formula': '0.5 x min non-empty-frame fraction across BOTH staged films (Ruling R, multi-film basis)',
              'per_film_fracs': {f'{a}:{v}': fracs[(a, v)] for (a, v) in fracs}},
 'staged_utc': stamp,
}
json.dump(arming, open(os.path.join(out, 'arming.json'), 'w'), indent=1)
print(json.dumps({'armed': True, 'gate3_run_id': arming['gate3_run_id'],
                  'liveness_min': lm,
                  'diverger_frames_diverging': f'{len(div)}/{len(d_rr)}',
                  'control_armed': True}, indent=1))
if len(div) == 0:
    print('NOTE — the >560px staged film did NOT diverge in staging: flag to Ansh '
          'before the campaign (it contradicts the Ruling-U expectation at n=1).')
PYC
echo "STAGING COMPLETE — read $OUT/arming.json (span basis, control verdict,"
echo "expected-diverger census, multi-film liveness) BEFORE run_plan_films500.sh."