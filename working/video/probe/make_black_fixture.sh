#!/usr/bin/env bash
# Gate 5's NULL CONTROL: a synthetic black clip that MUST produce ~all-empty
# detections and therefore MUST FAIL the detection-liveness gate. A liveness
# gate that passes on this fixture is broken.
#
# Scope note (settled decision 3): that decision banned a synthetic
# DUPLICATION fixture. This is a detector null control — mandated by the
# discipline ("every detector ships with a null control that must fire") —
# and it never feeds a measured leg.
#
# Matches corpus geometry (352x288 @ 25fps, mpeg4-family codec in AVI) so the
# decode path is exercised like real corpus items. sha256 recorded at
# creation into a sidecar; the fixture is generated, not fetched, so the
# sidecar records what THIS box produced (ffmpeg version noted alongside).
set -euo pipefail
PY="${PYBIN:-$HOME/.venv-floor/bin/python}"
[ -x "$PY" ] || { echo "NOT DONE — $PY missing; run setup_floor_venv.sh first"; exit 1; }

DIR="$(dirname "$0")/media"
mkdir -p "$DIR"
OUT="$DIR/black_60s_352x288.avi"

FFMPEG=$("$PY" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || command -v ffmpeg)
[ -n "$FFMPEG" ] || { echo "NOT DONE — no ffmpeg (pip install imageio-ffmpeg)"; exit 1; }

"$FFMPEG" -y -nostdin -loglevel error \
  -f lavfi -i "color=c=black:s=352x288:r=25:d=60" \
  -c:v mpeg4 -q:v 5 "$OUT"

SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
{
  echo "file: $(basename "$OUT")"
  echo "sha256: $SHA"
  echo "created_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "ffmpeg: $("$FFMPEG" -version | head -1)"
  echo "purpose: gate-5 null control — MUST fail detection_liveness at any sane threshold"
  echo "usage: PROBE_THREADS=8 $PY probe_li_floor.py --video $OUT  # expect ~0 nonempty frames"
} > "$OUT.sha256.txt"
cat "$OUT.sha256.txt"
echo "DONE — fixture generated (expected frames at fps=1/15 over 60s: 4)"
