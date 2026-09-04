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

echo "== startup prereq: the dimension/duration mechanism, ONCE, before any worker =="
FIRST=$(head -1 /tmp/films500.names)
"$PYF" - "$CORPUS/$FIRST" <<'PYCHK' || { echo "REFUSE: dimension mechanism unavailable — imageio_ffmpeg.read_frames header meta (the bundled package ships NO ffprobe; a prerequisite that cannot succeed refuses at startup with the tool named, never per-item 500 times)"; exit 3; }
import sys
from imageio_ffmpeg import read_frames
g = read_frames(sys.argv[1]); m = next(g); g.close()
assert m.get('size') and m.get('duration') is not None, f'meta lacks size/duration: {sorted(m)}'
print(f"  mechanism OK on {sys.argv[1].rsplit('/', 1)[-1]}: size={m['size']} duration={m['duration']:.1f}s")
PYCHK

count_one() {  # $1 = filename; writes one JSON part; prints timing
  local name="$1" f t0 t1 frames dwh dur w h sha bytes
  f="$CORPUS/$name"
  t0=$(date +%s)
  # frame count via the null muxer's final counter on stderr (the arms' filter):
  frames=$("$FF" -nostdin -hide_banner -i "$f" -vf fps=1/15 -f null - 2>&1 \
           | grep -o 'frame=[[:space:]]*[0-9]*' | tail -1 | grep -o '[0-9]*')
  # duration + WIDTH/HEIGHT from the SAME pinned binary via read_frames'
  # header meta (proven vs the committed census on three knowns, 2026-09-04):
  dwh=$("$PYF" - "$f" <<'PYD'
import sys
from imageio_ffmpeg import read_frames
g = read_frames(sys.argv[1]); m = next(g); g.close()
w, h = m['size']
print(m.get('duration', ''), w, h)
PYD
)
  dur=$(echo "$dwh" | awk '{print $1}')
  w=$(echo "$dwh" | awk '{print $2}')
  h=$(echo "$dwh" | awk '{print $3}')
  sha=$(sha256sum "$f" | awk '{print $1}')
  bytes=$(stat -c %s "$f")
  t1=$(date +%s)
  [ -n "$frames" ] || { echo "COUNT FAILED: $name" >&2; return 1; }
  [ -n "$w" ] && [ -n "$h" ] || { echo "DIMENSIONS FAILED: $name" >&2; return 1; }
  "$PYF" -c "
import json,sys
print(json.dumps({'file': sys.argv[1], 'sha256': sys.argv[2], 'bytes': int(sys.argv[3]),
                  'video_s': (float(sys.argv[4]) if sys.argv[4] else None),
                  'expected_frames_measured': int(sys.argv[5]),
                  'width': int(sys.argv[6]), 'height': int(sys.argv[7])}))" \
    "$name" "$sha" "$bytes" "$dur" "$frames" "$w" "$h" > "$PARTS/$name.json"
  echo "  $name: frames=$frames ${w}x${h} wall=$((t1-t0))s" >&2
}
export -f count_one; export CORPUS PARTS FF PYF

mkdir -p "$PARTS"
TODO=0
: > /tmp/films500.todo
while read -r NAME; do
  [ -s "$PARTS/$NAME.json" ] && continue
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
if mode == 'nullcheck':
    with open(out, 'w') as f:
        f.write(json.dumps({'_meta': {'nullcheck_mode': True, 'n_files': len(rows)}}) + '\n')
        for r in rows: f.write(json.dumps(r) + '\n')
    print(f'nullcheck manifest: {out} (the real manifest was NOT written)')
    raise SystemExit(0)
WARM = {'submarine_alert.mp4', 'DominiqueIsDead1978.mp4'}
missing_warm = WARM - {r['file'] for r in rows}
if missing_warm:
    print(f'REFUSE — designated warm films not in corpus: {missing_warm}'); raise SystemExit(3)
for r in rows:
    r['role'] = 'warm' if r['file'] in WARM else 'measured'
rows.sort(key=lambda r: (r['role'] == 'warm', r['file']))
n_meas = sum(1 for r in rows if r['role'] == 'measured')
above = [r for r in rows if max(r['width'], r['height']) > 560]
meta = {'_meta': {'corpus_manifest_sha256':
        'bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1',
        'ffmpeg_sha256': 'e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99',
        'dimensions_source': 'imageio_ffmpeg.read_frames header meta (same pinned binary; '
                             'proven vs the committed census on 3 knowns 2026-09-04)',
        'interval_s': 15, 'n_files': len(rows), 'n_measured': n_meas, 'n_warm': len(WARM),
        'warm_rule': 'last 2 of the frozen queue order (her driver convention; matches her 498+2 split)',
        'total_frames': sum(r['expected_frames_measured'] for r in rows),
        'total_video_s': sum(r['video_s'] or 0 for r in rows),
        'n_above_560px': len(above),
        'note_560px': 'width/height measured per film via the pinned decoder; the corpus-wide '
                      '>560px fraction is derivable from THIS artifact'}}
with open(out, 'w') as f:
    f.write(json.dumps(meta) + '\n')
    for r in rows: f.write(json.dumps(r) + '\n')
m = meta['_meta']
print(f"census: n={m['n_files']} ({m['n_measured']} measured + {m['n_warm']} warm)  "
      f"total_frames={m['total_frames']}  footage={m['total_video_s']/3600:.2f} h  "
      f">560px: {m['n_above_560px']}/{m['n_files']}")
print(f"manifest: {out}")
PYA
echo "DONE ($MODE)."
