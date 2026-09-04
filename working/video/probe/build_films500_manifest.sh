#!/usr/bin/env bash
# build_films500_manifest.sh v2 — BOX-SIDE. Cut expected_frames_measured for
# all 500 films through OUR sha-pinned ffmpeg at fps=1/15 (Crossroad 23:
# measured at manifest build, NEVER derived from duration, NEVER her
# frames_counted).
#
# v2 (2026-09-04) after run 1 failed 500/500 on a TOOL THAT DOES NOT EXIST:
# v1 called ffprobe beside the bundled ffmpeg — imageio_ffmpeg ships NO
# ffprobe (box binaries dir holds ffmpeg-linux-x86_64-v7.0.2 alone), a fact
# already on the campaign record (every decode path resolves the bundled
# binary precisely because the box has no host ffmpeg/ffprobe) and not
# applied when the dimension feature was added — register entry 31. Fixes:
#   * DIMENSIONS + DURATION from the PINNED ffmpeg itself:
#     imageio_ffmpeg.read_frames() yields the header-parsed meta dict first
#     (_io.py:301-302 `meta = parse_ffmpeg_header(...); yield meta`), with
#     meta['size'] (_parsing.py:180) and meta['duration'] (:199-205) — same
#     bundled binary, no new tool. PROVEN against the committed census on
#     three knowns before adoption: Leagues (320,240), House (714,480),
#     JailBait (560,380) — exact matches, 2026-09-04.
#   * FAIL-FAST STARTUP CHECK: the mechanism runs on the first corpus file
#     before any worker spawns; a missing/broken tool refuses ONCE with the
#     tool named, never 500 times per-item.
#   * KNOWNS_ONLY=1 mode: runs the 35 subset knowns alone and executes the
#     NULL CONTROL (counts must reproduce the committed subset manifest
#     EXACTLY or refuse) — the control had never executed, masked by the
#     ffprobe failure. Writes *.nullcheck.jsonl, NEVER the real manifest;
#     its per-film parts are REUSED by the full run (shared parts dir).
#
# Parallel (P=12) and RESUMABLE (parts present are skipped). Detach:
#   box.sh launch manifest500 'bash ~/parity-bench-video/working/video/probe/build_films500_manifest.sh'
# Null-control pre-run (ruled, must pass BEFORE the 500):
#   box.sh launch nullcheck500 'cd ~/parity-bench-video && KNOWNS_ONLY=1 bash working/video/probe/build_films500_manifest.sh'
# Committed script + self-printed sha256 (entry 25). No keepalive: P=12
# ffmpeg decode pegs 12 cores throughout (sequence-doc ruling).
set -euo pipefail
echo "build_films500_manifest.sh sha256: $(sha256sum "$0" | awk '{print $1}')"
cd ~/parity-bench-video

CORPUS="$HOME/films_corpus/full500"
OUT="working/video/films500_video_manifest.jsonl"
PARTS="$OUT.parts"
SUBSET_MANIFEST="working/video/films_video_manifest.jsonl"
FFMPEG_SHA_EXPECT="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
P="${MANIFEST_P:-12}"
PYF="$HOME/.venv-floor/bin/python3"
MODE="full"
[ "${KNOWNS_ONLY:-0}" = "1" ] && { MODE="nullcheck"; OUT="$OUT.nullcheck.jsonl"; }

FF=$("$PYF" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')
GOT=$(sha256sum "$FF" | awk '{print $1}')
[ "$GOT" = "$FFMPEG_SHA_EXPECT" ] || { echo "REFUSE: ffmpeg sha $GOT != pinned $FFMPEG_SHA_EXPECT"; exit 3; }
echo "ffmpeg: $FF (sha OK)"
[ -s "$CORPUS/corpus_manifest.json" ] || { echo "REFUSE: run fetch_films500.sh first"; exit 3; }

"$PYF" - "$CORPUS/corpus_manifest.json" <<'PYL' > /tmp/films500.names
import json, sys
m = json.load(open(sys.argv[1]))
for name in sorted((m.get('sha256') or m.get('files') or {})): print(name)
PYL

if [ "$MODE" = "nullcheck" ]; then
  "$PYF" -c "import json,sys
[print(json.loads(l)['file']) for l in open('$SUBSET_MANIFEST') if '\"file\"' in l]" > /tmp/films500.knowns
  grep -Fx -f /tmp/films500.knowns /tmp/films500.names > /tmp/films500.names.k
  mv /tmp/films500.names.k /tmp/films500.names
  echo "KNOWNS_ONLY: $(wc -l < /tmp/films500.names | tr -d ' ') subset films; output -> $OUT (the real manifest is NOT written in this mode)"
fi

echo "== startup prereq: BOTH dimension mechanisms, ONCE, before any worker =="
# Two bases, both carried and labelled (2026-09-04 ruling): CONTAINER
# (header meta — the coded stream size) and DETECTOR (PIL .size of a
# decoded frame — what actually reaches RF-DETR, the basis Ruling U's
# 560px edge is defined on; the committed census measured this basis).
# On the 35 knowns the two coincide on every film (reconciled 2026-09-04,
# zero disagreements); they CAN differ on SAR/anamorphic sources, and the
# 465 unknowns are unmeasured — so both are measured per film, the
# partition uses DETECTOR, and any container!=detector film is flagged.
FIRST=$(head -1 /tmp/films500.names)
"$PYF" - "$CORPUS/$FIRST" "$FF" <<'PYCHK' || { echo "REFUSE: dimension mechanisms unavailable — imageio_ffmpeg.read_frames header meta AND/OR PIL-on-decoded-frame (tool named above; a prerequisite that cannot succeed refuses at startup, never per-item 500 times)"; exit 3; }
import sys, subprocess, tempfile, os
from imageio_ffmpeg import read_frames
from PIL import Image
g = read_frames(sys.argv[1]); m = next(g); g.close()
assert m.get('size') and m.get('duration') is not None, f'meta lacks size/duration: {sorted(m)}'
t = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
t.close()
subprocess.run([sys.argv[2], '-nostdin', '-loglevel', 'error', '-y', '-i', sys.argv[1],
                '-frames:v', '1', '-vcodec', 'png', t.name], check=True)
im = Image.open(t.name); dsz = im.size; im.close(); os.unlink(t.name)
print(f"  mechanisms OK on {sys.argv[1].rsplit('/', 1)[-1]}: container={m['size']} detector={dsz} duration={m['duration']:.1f}s")
PYCHK

count_one() {  # $1 = filename; writes one JSON part; prints timing
  local name="$1" f t0 t1 frames dims sha bytes
  f="$CORPUS/$name"
  t0=$(date +%s)
  # frame count via the null muxer's final counter on stderr (the arms' filter):
  frames=$("$FF" -nostdin -hide_banner -i "$f" -vf fps=1/15 -f null - 2>&1 \
           | grep -o 'frame=[[:space:]]*[0-9]*' | tail -1 | grep -o '[0-9]*')
  # BOTH dimension bases + duration: container from read_frames header
  # meta; detector from PIL .size of one decoded PNG (the arms' encode
  # path — the census basis, the one RF-DETR's 560px edge is defined on).
  dims=$("$PYF" - "$f" "$FF" <<'PYD'
import sys, subprocess, tempfile, os
from imageio_ffmpeg import read_frames
from PIL import Image
g = read_frames(sys.argv[1]); m = next(g); g.close()
cw, ch = m['size']
t = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
t.close()
subprocess.run([sys.argv[2], '-nostdin', '-loglevel', 'error', '-y', '-i', sys.argv[1],
                '-frames:v', '1', '-vcodec', 'png', t.name], check=True)
im = Image.open(t.name); dw, dh = im.size; im.close(); os.unlink(t.name)
print(m.get('duration', ''), cw, ch, dw, dh)
PYD
)
  local dur cw ch dw dh
  dur=$(echo "$dims" | awk '{print $1}'); cw=$(echo "$dims" | awk '{print $2}')
  ch=$(echo "$dims" | awk '{print $3}'); dw=$(echo "$dims" | awk '{print $4}')
  dh=$(echo "$dims" | awk '{print $5}')
  sha=$(sha256sum "$f" | awk '{print $1}')
  bytes=$(stat -c %s "$f")
  t1=$(date +%s)
  [ -n "$frames" ] || { echo "COUNT FAILED: $name" >&2; return 1; }
  [ -n "$dw" ] && [ -n "$dh" ] && [ -n "$cw" ] && [ -n "$ch" ] || { echo "DIMENSIONS FAILED: $name" >&2; return 1; }
  "$PYF" -c "
import json,sys
print(json.dumps({'file': sys.argv[1], 'sha256': sys.argv[2], 'bytes': int(sys.argv[3]),
                  'video_s': (float(sys.argv[4]) if sys.argv[4] else None),
                  'expected_frames_measured': int(sys.argv[5]),
                  'container_width': int(sys.argv[6]), 'container_height': int(sys.argv[7]),
                  'detector_width': int(sys.argv[8]), 'detector_height': int(sys.argv[9])}))" \
    "$name" "$sha" "$bytes" "$dur" "$frames" "$cw" "$ch" "$dw" "$dh" > "$PARTS/$name.json"
  echo "  $name: frames=$frames container=${cw}x${ch} detector=${dw}x${dh} wall=$((t1-t0))s" >&2
}
export -f count_one; export CORPUS PARTS FF PYF

mkdir -p "$PARTS"
TODO=0
: > /tmp/films500.todo
while read -r NAME; do
  # resume only on parts that carry the v3 dual-dimension fields —
  # v2-era parts (single unlabelled width) are stale and re-counted
  if [ -s "$PARTS/$NAME.json" ] && grep -q detector_width "$PARTS/$NAME.json"; then continue; fi
  echo "$NAME" >> /tmp/films500.todo; TODO=$((TODO+1))
done < /tmp/films500.names
echo "to count: $TODO of $(wc -l < /tmp/films500.names | tr -d ' ') (rest resumed from parts)"
xargs -a /tmp/films500.todo -I{} -P "$P" bash -c 'count_one "$@"' _ {}

echo "== assemble + census ($MODE) =="
"$PYF" - "$OUT" "$SUBSET_MANIFEST" "$MODE" /tmp/films500.names "$PARTS" <<'PYA'
import json, sys, os
out, subset_path, mode, names_path, parts = sys.argv[1:6]
names = [l.strip() for l in open(names_path) if l.strip()]
rows = []
for n in names:
    p = os.path.join(parts, n + '.json')
    if os.path.exists(p): rows.append(json.loads(open(p).read()))
if len(rows) != len(names):
    missing = [n for n in names if not os.path.exists(os.path.join(parts, n + '.json'))]
    print(f'REFUSE — {len(missing)} film(s) uncounted: {missing[:5]}'); raise SystemExit(3)
subset = {}
for line in open(subset_path):
    r = json.loads(line)
    if 'file' in r: subset[r['file']] = r
# NULL CONTROL (runs in BOTH modes): the knowns must reproduce exactly.
mism = []
for name, s in subset.items():
    mine = next((r for r in rows if r['file'] == name), None)
    if mine is None:
        if mode == 'full': mism.append((name, 'MISSING', None))
        continue
    if mine['expected_frames_measured'] != s.get('expected_frames_measured'):
        mism.append((name, mine['expected_frames_measured'], s.get('expected_frames_measured')))
    if mine['sha256'] != s.get('sha256'):
        mism.append((name, 'SHA', 'DIFFERS'))
if mism:
    print('REFUSE — NULL CONTROL FAILED on the knowns:', mism[:5]); raise SystemExit(3)
n_known = sum(1 for n in subset if any(r['file'] == n for r in rows))
print(f'NULL CONTROL: {n_known}/{len(subset)} known subset films reproduce the committed manifest EXACTLY')
# THIRD NULL CONTROL (2026-09-04): the knowns' DETECTOR dimensions must
# equal the committed census (the basis Ruling U's 560px edge is defined
# on — PIL on the decoded frame). Reconciled once by hand: 35/35 agree.
census_path = 'working/video/results/detector-parity-20260902/census_20260902T080135Z.json'
census = {r['film']: tuple(r['size']) for r in json.load(open(census_path))['per_film']}
dmism = []
for r in rows:
    exp = census.get(r['file'])
    if exp and (r['detector_width'], r['detector_height']) != exp:
        dmism.append((r['file'], (r['detector_width'], r['detector_height']), exp))
if dmism:
    print('REFUSE — DIMENSION CONTROL FAILED vs the committed census:', dmism[:5]); raise SystemExit(3)
n_dim = sum(1 for r in rows if r['file'] in census)
print(f'DIMENSION CONTROL: {n_dim} censused knowns match the committed census (detector basis) EXACTLY')
sar = [r['file'] for r in rows
       if (r['container_width'], r['container_height']) != (r['detector_width'], r['detector_height'])]
if sar:
    print(f'NOTE — container != detector dimensions on {len(sar)} film(s) (SAR/anamorphic sources; '
          f'partition uses DETECTOR): {sar[:10]}')
if mode == 'nullcheck':
    with open(out, 'w') as f:
        f.write(json.dumps({'_meta': {'nullcheck_mode': True, 'n_files': len(rows)}}) + '\n')
        for r in rows: f.write(json.dumps(r) + '\n')
    print(f'nullcheck manifest: {out} (the real manifest was NOT written)')
    raise SystemExit(0)
# WARM PAIR DERIVED, NEVER BAKED (v4, 2026-09-04, after the baked-name
# refuse): warm = (this corpus's 500) MINUS (her measured 498, mirrored
# from her committed per_doc at pin 3967d9f4 into
# films500_her_measured_set.txt). The v3 bake took the set file's
# title column and the wrong two films besides (her convention is
# sorted-last-two, not queue-tail); deriving from her run's own records
# makes our measured 498 equal hers BY CONSTRUCTION (verified: diff=0).
her_path = 'working/video/films500_her_measured_set.txt'
her = {l.strip() for l in open(her_path) if l.strip() and not l.startswith('#')}
if len(her) != 498:
    print(f'REFUSE — her measured mirror has {len(her)} names, expected 498 ({her_path})'); raise SystemExit(3)
files = {r['file'] for r in rows}
not_in_corpus = her - files
if not_in_corpus:
    print(f'REFUSE — her measured set names {len(not_in_corpus)} film(s) not in this corpus: {sorted(not_in_corpus)[:5]}'); raise SystemExit(3)
WARM = files - her
if len(WARM) != 2:
    print(f'REFUSE — corpus minus her measured = {len(WARM)} film(s), expected exactly 2: {sorted(WARM)[:5]}'); raise SystemExit(3)
print(f'warm pair DERIVED (corpus - her measured): {sorted(WARM)}')
for r in rows:
    r['role'] = 'warm' if r['file'] in WARM else 'measured'
rows.sort(key=lambda r: (r['role'] == 'warm', r['file']))
n_meas = sum(1 for r in rows if r['role'] == 'measured')
above = [r for r in rows if max(r['detector_width'], r['detector_height']) > 560]
meta = {'_meta': {'corpus_manifest_sha256':
        'bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1',
        'ffmpeg_sha256': 'e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99',
        'dimensions_source': ('TWO bases per film, labelled (2026-09-04 ruling): container_* = '
                              'coded stream size (read_frames header meta); detector_* = PIL '
                              '.size of one decoded PNG via the arms\' encode path — the basis '
                              'the committed census used and the one RF-DETR\'s 560px edge is '
                              'defined on. The PARTITION uses detector_*. Knowns verified '
                              'against the census by the dimension control.'),
        'interval_s': 15, 'n_files': len(rows), 'n_measured': n_meas, 'n_warm': len(WARM),
        'warm_rule': ('DERIVED at build: corpus 500 minus her measured 498 (her committed films500 per_doc @3967d9f4, mirrored as films500_her_measured_set.txt) — our measured set equals hers by construction'),
        'warm_films': sorted(WARM),
        'total_frames': sum(r['expected_frames_measured'] for r in rows),
        'total_video_s': sum(r['video_s'] or 0 for r in rows),
        'n_above_560px_detector_basis': len(above),
        'n_container_detector_mismatch': len(sar),
        'note_560px': 'the corpus-wide >560px fraction (detector basis) is derivable from THIS artifact'}}
with open(out, 'w') as f:
    f.write(json.dumps(meta) + '\n')
    for r in rows: f.write(json.dumps(r) + '\n')
m = meta['_meta']
print(f"census: n={m['n_files']} ({m['n_measured']} measured + {m['n_warm']} warm)  "
      f"total_frames={m['total_frames']}  footage={m['total_video_s']/3600:.2f} h  "
      f">560px(detector): {m['n_above_560px_detector_basis']}/{m['n_files']}  container!=detector: {m['n_container_detector_mismatch']}")
print(f"manifest: {out}")
PYA
echo "DONE ($MODE)."
