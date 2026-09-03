#!/usr/bin/env bash
# mirror_films500.sh — BOX-SIDE mid-run S3 mirror, adopting Leela's form
# (her films_v2.sh:43 syncs results DURING a run; we have only archived
# after — at day-long scale a box death preserved nothing but disk).
# Syncs the RUN DIRECTORY only — records, exports, consoles, manifests as
# they land — NEVER the corpora. Read-only on disk; writes only its S3
# prefix. Stops when <run_dir>/MIRROR_STOP exists or the dir vanishes.
# Launch it beside the campaign:
#   box.sh launch mirror500 'bash ~/parity-bench-video/working/video/probe/mirror_films500.sh <run_dir_abs_path>'
# Stop it:
#   box.sh run 'touch <run_dir_abs_path>/MIRROR_STOP'
# Committed script + self-printed sha256 (entry 25).
set -euo pipefail
echo "mirror_films500.sh sha256: $(sha256sum "$0" | awk '{print $1}')"

RUN_DIR="${1:?usage: mirror_films500.sh <run_dir_abs_path>}"
[ -d "$RUN_DIR" ] || { echo "REFUSE: $RUN_DIR is not a directory"; exit 3; }
STAMP="$(basename "$RUN_DIR")"
DST="s3://rocketride-benchmark-data/ansh/films500-live-$STAMP/"
INTERVAL="${MIRROR_INTERVAL_S:-300}"

echo "mirroring $RUN_DIR -> $DST every ${INTERVAL}s (corpora never; stop: touch $RUN_DIR/MIRROR_STOP)"
CYCLE=0
while :; do
  [ -e "$RUN_DIR/MIRROR_STOP" ] && { echo "MIRROR_STOP seen — final sync, then exit"; }
  aws s3 sync "$RUN_DIR" "$DST" --exclude '*.tmp' --exclude 'MIRROR_STOP' --quiet || \
    echo "cycle $CYCLE: sync returned nonzero (transient S3/API error tolerated; next cycle retries)"
  CYCLE=$((CYCLE+1))
  echo "cycle $CYCLE synced at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [ -e "$RUN_DIR/MIRROR_STOP" ] && break
  [ -d "$RUN_DIR" ] || { echo "run dir vanished — exiting"; break; }
  sleep "$INTERVAL"
done
echo "DONE — $CYCLE cycles."
