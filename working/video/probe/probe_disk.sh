#!/usr/bin/env bash
# Disk read throughput during decode — the storage-decision number.
# Cold-cache runs need sudo for drop_caches; without sudo the script SAYS SO,
# labels those rows cache=warm-only, and still produces the O_DIRECT ceiling.
set -uo pipefail
cd "$(dirname "$0")"

VIDEO="${1:-media/ES2002a.Corner.avi}"
[ -f "$VIDEO" ] || { echo "run ./probe_fetch.sh first ($VIDEO missing)"; exit 1; }
BYTES=$(stat -c %s "$VIDEO" 2>/dev/null || stat -f %z "$VIDEO")
LOG="probe_disk_$(date +%Y%m%d_%H%M%S).log"
echo "video=$VIDEO bytes=$BYTES -> $LOG"

FFMPEG=$(python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || command -v ffmpeg)
[ -n "$FFMPEG" ] || { echo "NOT DONE — no ffmpeg (pip install imageio-ffmpeg)"; exit 1; }

HAVE_SUDO=0
if sudo -n true 2>/dev/null; then HAVE_SUDO=1; fi
drop_caches() {
  if [ "$HAVE_SUDO" = "1" ]; then
    sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; echo cold
  else
    echo warm-only
  fi
}
[ "$HAVE_SUDO" = "1" ] || echo "WARNING: no passwordless sudo — cold-cache rows will read cache=warm-only" | tee -a "$LOG"

disk_read_bytes() { awk '{ if ($3 !~ /loop|ram/) s += $6 * 512 } END { print s }' /proc/diskstats 2>/dev/null || echo 0; }

run_timed() { # label cmd...
  local label="$1"; shift
  local cache; cache=$(drop_caches)
  local r0 t0 t1 r1
  r0=$(disk_read_bytes); t0=$(date +%s.%N)
  "$@" >/dev/null 2>>"$LOG"
  local rc=$?
  t1=$(date +%s.%N); r1=$(disk_read_bytes)
  python3 - "$label" "$cache" "$t0" "$t1" "$r0" "$r1" "$BYTES" "$rc" <<'EOF' | tee -a "$LOG"
import sys
label, cache, t0, t1, r0, r1, size, rc = sys.argv[1:9]
wall = float(t1) - float(t0); rb = int(r1) - int(r0)
print(f'{label}: cache={cache} wall={wall:.2f}s device_read={rb/1e6:.1f}MB '
      f'({rb/wall/1e6:.1f} MB/s) file={int(size)/1e6:.1f}MB rc={rc}')
EOF
  return $rc
}

echo "== 1. cold raw sequential read ==" | tee -a "$LOG"
run_timed raw_read cat "$VIDEO"

echo "== 2. cold decode (the measured pipeline's filter) ==" | tee -a "$LOG"
run_timed cold_decode "$FFMPEG" -nostdin -loglevel error -i "$VIDEO" \
  -vf fps=1/15 -f image2pipe -fps_mode passthrough -vcodec png -

echo "== 3. warm decode (contrast) ==" | tee -a "$LOG"
HAVE_SUDO=0 run_timed warm_decode "$FFMPEG" -nostdin -loglevel error -i "$VIDEO" \
  -vf fps=1/15 -f image2pipe -fps_mode passthrough -vcodec png -

echo "== 4. O_DIRECT 8-way parallel read ceiling (no sudo needed) ==" | tee -a "$LOG"
CHUNK=$(( BYTES / 8 / 1048576 ))
t0=$(date +%s.%N)
for i in 0 1 2 3 4 5 6 7; do
  dd if="$VIDEO" of=/dev/null iflag=direct bs=1M skip=$(( i * CHUNK )) count="$CHUNK" 2>/dev/null &
done
wait
t1=$(date +%s.%N)
python3 -c "
w=float('$t1')-float('$t0'); total=8*$CHUNK*1048576
print(f'parallel_direct: wall={w:.2f}s aggregate={total/1e6:.0f}MB ({total/w/1e6:.0f} MB/s device ceiling estimate)')" | tee -a "$LOG"

echo "== 5. blast extrapolation ==" | tee -a "$LOG"
python3 -c "
print('at C=32 cold starts, aggregate demand ~= 32 x file_size over the decode window;')
print('compare row 4 ceiling vs (32 x row-1 single-stream rate needed). Decision rule:')
print('ceiling > demand -> storage is NOT the bottleneck; no upgrade on assumption.')" | tee -a "$LOG"

echo "DONE — $LOG"
