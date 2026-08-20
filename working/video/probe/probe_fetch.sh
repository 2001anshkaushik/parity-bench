#!/usr/bin/env bash
# Fetch the probe recording, sha-pinned. No mux (audio is out of scope this
# phase; the AVI ships video-only). DONE means verified; any mismatch exits
# non-zero and names the file.
set -euo pipefail

DIR="${PROBE_MEDIA_DIR:-$(dirname "$0")/media}"
mkdir -p "$DIR"

MIRROR="https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
V="ES2002a.Corner.avi"
V_SHA="40fdbfda266ca2ecdc56c214738234aa1ec1e21dbbf4d5a1fdd53f974cc2e730"
# Pinned 2026-08-19 from the mirror (laptop fetch + RIFF parse): single 'vids'
# stream (DIVX, 352x288, 25 fps, 31208 frames = 1248.3 s). No audio stream —
# which is why frame_grabber needs no mux and this phase fetches as-shipped.

if [ ! -f "$DIR/$V" ]; then
  echo "fetching $V ..."
  curl -fL --retry 3 -o "$DIR/$V" "$MIRROR/ES2002a/video/$V"
fi
echo "$V_SHA  $DIR/$V" | sha256sum -c - || { echo "NOT DONE — sha mismatch: $V"; exit 1; }

# Report the stream layout from the container header itself (python RIFF parse,
# no ffprobe dependency): stream types, fourcc, dims, fps, frame count.
python3 - "$DIR/$V" <<'EOF'
import struct, sys
data = open(sys.argv[1], 'rb').read(2_000_000)
assert data[:4] == b'RIFF' and data[8:12] == b'AVI ', 'not an AVI'
def walk(i, end):
    out = []
    while i < end - 8:
        fcc = data[i:i+4]; size = struct.unpack('<I', data[i+4:i+8])[0]
        if fcc == b'LIST' and data[i+8:i+12] in (b'hdrl', b'strl'):
            out += walk(i+12, i+8+size)
        elif fcc == b'avih':
            us, = struct.unpack('<I', data[i+8:i+12])
            tf, = struct.unpack('<I', data[i+24:i+28])
            w, h = struct.unpack('<II', data[i+40:i+48])
            out.append(f'avih: {w}x{h} frames={tf} fps={1e6/us:.3f} dur={tf*us/1e6:.1f}s')
        elif fcc == b'strh':
            st = data[i+8:i+12].decode(); hd = data[i+12:i+16].decode(errors='replace')
            sc, ra = struct.unpack('<II', data[i+28:i+36])
            ln, = struct.unpack('<I', data[i+40:i+44])
            out.append(f'stream: {st} {hd!r} {ra}/{sc} len={ln}')
        i += 8 + size + (size & 1)
    return out
lines = walk(12, len(data))
print('\n'.join(lines))
vids = [l for l in lines if 'vids' in l]
auds = [l for l in lines if 'auds' in l]
assert vids, 'no video stream found'
print(f'stream layout: {len(vids)} video, {len(auds)} audio (expected 1, 0)')
EOF

echo "DONE verified: $V matches pin; layout printed above."
