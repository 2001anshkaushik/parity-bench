#!/usr/bin/env bash
# build_films500_manifest.sh — BOX-SIDE. Cut expected_frames_measured for
# all 500 films through OUR sha-pinned ffmpeg at fps=1/15 (Crossroad 23:
# measured at manifest build, NEVER derived from duration, and NEVER her
# frames_counted — her own bracket counter carries the 416 artifact).
#
# BUILT-IN NULL CONTROL: the 35 films of our committed subset manifest are
# in this corpus; this builder's counts for them must REPRODUCE
# working/video/films_video_manifest.jsonl EXACTLY, or it REFUSES — the
# counting method's equivalence to the arms' sampling is thereby measured
# on 35 knowns, not asserted.
#
# Parallel (-P below; decode is per-file independent, CPU-bound, box has 32
# cores and no legs running) and RESUMABLE (films already in the output are
# skipped). Wall projection: one measured anchor (HouseOnBareMountain,
# 3,719 s of footage decoded through this filter in 26.75 s = ~139x
# realtime, single process, SD MPEG-4) puts 674.75 h at ~4.9 h single-lane,
# ~25-40 min at P=12; 1080p prints decode slower, so the honest envelope is
# ~0.5-2.5 h. The script prints per-film timing — the first few films
# calibrate the estimate. Detach it:
#   box.sh launch manifest500 'bash ~/parity-bench-video/working/video/probe/build_films500_manifest.sh'
# Committed script + self-printed sha256 (entry 25).
set -euo pipefail
echo "build_films500_manifest.sh sha256: $(sha256sum "$0" | awk '{print $1}')"
cd ~/parity-bench-video

CORPUS="$HOME/films_corpus/full500"
OUT="working/video/films500_video_manifest.jsonl"
SUBSET_MANIFEST="working/video/films_video_manifest.jsonl"
FFMPEG_SHA_EXPECT="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
P="${MANIFEST_P:-12}"

FF="$("$HOME/.venv-floor/bin/python3" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
GOT=$(sha256sum "$FF" | awk '{print $1}')
[ "$GOT" = "$FFMPEG_SHA_EXPECT" ] || { echo "REFUSE: ffmpeg sha $GOT != pinned $FFMPEG_SHA_EXPECT"; exit 3; }
echo "ffmpeg: $FF (sha OK)"
[ -s "$CORPUS/corpus_manifest.json" ] || { echo "REFUSE: run fetch_films500.sh first"; exit 3; }

count_one() {  # $1 = filename; appends one JSON line; prints timing
  local name="$1" f t0 t1 frames dur sha bytes
  f="$CORPUS/$name"
  t0=$(date +%s)
  # frame count via the null muxer's own final counter on stderr:
  frames=$("$FF" -nostdin -hide_banner -i "$f" -vf fps=1/15 -f null - 2>&1 \
           | grep -o 'frame=[[:space:]]*[0-9]*' | tail -1 | grep -o '[0-9]*')
  # duration + WIDTH/HEIGHT in one ffprobe call — resolution feeds the
  # 500-run's 560px partition check (and makes the corpus-wide >560px
  # fraction derivable from OUR OWN artifact for the first time).
  dwh=$("$HOME/.venv-floor/bin/python3" - "$f" <<'PYD'
import subprocess, sys, json, os
import imageio_ffmpeg
ff = imageio_ffmpeg.get_ffmpeg_exe()
probe = os.path.join(os.path.dirname(ff), 'ffprobe')
if os.path.exists(probe):
    out = subprocess.run([probe, '-v', 'error',
                          '-select_streams', 'v:0',
                          '-show_entries', 'stream=width,height:format=duration',
                          '-of', 'json', sys.argv[1]], capture_output=True, text=True)
    j = json.loads(out.stdout)
    st = (j.get('streams') or [{}])[0]
    print(j.get('format', {}).get('duration', ''), st.get('width', ''), st.get('height', ''))
else:
    print('  ')
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
  "$HOME/.venv-floor/bin/python3" -c "
import json,sys
print(json.dumps({'file': sys.argv[1], 'sha256': sys.argv[2], 'bytes': int(sys.argv[3]),
                  'video_s': (float(sys.argv[4]) if sys.argv[4] else None),
                  'expected_frames_measured': int(sys.argv[5]),
                  'width': int(sys.argv[6]), 'height': int(sys.argv[7])}))" \
    "$name" "$sha" "$bytes" "$dur" "$frames" "$w" "$h" >> "$OUT.parts/$name.json"
  echo "  $name: frames=$frames ${w}x${h} wall=$((t1-t0))s" >&2
}
export -f count_one; export CORPUS OUT FF HOME

mkdir -p "$OUT.parts"
python3 - "$CORPUS/corpus_manifest.json" <<'PYL' > /tmp/films500.names
import json, sys
m = json.load(open(sys.argv[1]))
for name in sorted((m.get('sha256') or m.get('files') or {})): print(name)
PYL

TODO=0
: > /tmp/films500.todo
while read -r NAME; do
  [ -s "$OUT.parts/$NAME.json" ] && continue
  echo "$NAME" >> /tmp/films500.todo; TODO=$((TODO+1))
done < /tmp/films500.names
echo "to count: $TODO of $(wc -l < /tmp/films500.names | tr -d ' ') (rest resumed from parts)"
xargs -a /tmp/films500.todo -I{} -P "$P" bash -c 'count_one "$@"' _ {}

echo "== assemble + census =="
"$HOME/.venv-floor/bin/python3" - "$OUT" "$SUBSET_MANIFEST" <<'PYA'
import json, sys, glob, os
out, subset_path = sys.argv[1], sys.argv[2]
rows = []
for p in sorted(glob.glob(out + '.parts/*.json')):
    rows.append(json.loads(open(p).read()))
subset = {}
for line in open(subset_path):
    r = json.loads(line)
    if 'file' in r: subset[r['file']] = r
# NULL CONTROL: our 35 knowns must reproduce exactly.
mism = []
for name, s in subset.items():
    mine = next((r for r in rows if r['file'] == name), None)
    if mine is None: mism.append((name, 'MISSING', None)); continue
    if mine['expected_frames_measured'] != s.get('expected_frames_measured'):
        mism.append((name, mine['expected_frames_measured'], s.get('expected_frames_measured')))
    if mine['sha256'] != s.get('sha256'):
        mism.append((name, 'SHA', 'DIFFERS'))
if mism:
    print('REFUSE — null control failed on the 35 knowns:', mism[:5]); raise SystemExit(3)
print(f'null control: 35/35 subset films reproduce the committed manifest exactly')
# Warm split — HER driver convention, adopted for cross-team join identity:
# the frozen set's LAST TWO in queue order are warm (her ami30h.txt:5 states
# the convention; her films500 README runs 498 measured + 2 warm; the tail
# of archive_films_500.txt @3967d9f4 names them). Measured = the other 498,
# matching her measured set exactly.
WARM = {'submarine_alert.mp4', 'DominiqueIsDead1978.mp4'}
missing_warm = WARM - {r['file'] for r in rows}
if missing_warm:
    print(f'REFUSE — designated warm films not in corpus: {missing_warm}'); raise SystemExit(3)
for r in rows:
    r['role'] = 'warm' if r['file'] in WARM else 'measured'
rows.sort(key=lambda r: (r['role'] == 'warm', r['file']))  # measured first, warm last
n_meas = sum(1 for r in rows if r['role'] == 'measured')
above = [r for r in rows if max(r['width'], r['height']) > 560]
meta = {'_meta': {'corpus_manifest_sha256':
        'bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1',
        'ffmpeg_sha256': 'e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99',
        'interval_s': 15, 'n_files': len(rows), 'n_measured': n_meas, 'n_warm': len(WARM),
        'warm_rule': 'last 2 of the frozen queue order (her driver convention; matches her 498+2 split)',
        'total_frames': sum(r['expected_frames_measured'] for r in rows),
        'total_video_s': sum(r['video_s'] or 0 for r in rows),
        'n_above_560px': len(above),
        'note_560px': 'width/height measured per film via the pinned ffprobe; '
                      'the corpus-wide >560px fraction is derivable from THIS '
                      'artifact (it was not derivable from any held artifact before)'}}
with open(out, 'w') as f:
    f.write(json.dumps(meta) + '\n')
    for r in rows: f.write(json.dumps(r) + '\n')
m = meta['_meta']
print(f"census: n={m['n_files']} ({m['n_measured']} measured + {m['n_warm']} warm)  "
      f"total_frames={m['total_frames']}  footage={m['total_video_s']/3600:.2f} h  "
      f">560px: {m['n_above_560px']}/{m['n_files']}")
print(f"manifest: {out}")
PYA
echo "DONE — commit the manifest from the box (entry-26 landing) or read it back."
