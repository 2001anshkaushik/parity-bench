#!/usr/bin/env bash
# p1_stamp.sh — install / collect the P1 E2 per-frame stamps + one-time in-process read-back in a
# RUNNING container (its writable layer; the image is never touched).
#
#   bash working/scripts/p1_stamp.sh rr|li install <container>
#   bash working/scripts/p1_stamp.sh rr|li collect <container> <leg_dir>
#
# install refuses unless the container's original file has the md5 the stamped copy derives from
# (the same bases as P0's V2 copies). The caller restarts the container so the copy is imported.
set -uo pipefail
ARM="$1"; OP="$2"; C="$3"
cd "$(dirname "$0")/../.." || exit 2
if [ "$ARM" = "rr" ]; then
  DST=/opt/rocketride/engine/nodes/detect/IInstance.py; SRC=working/nodes/p1_detect_stamped/IInstance.py
  BASE=984d80e45e885b5ae21e987664850b4c
else
  DST=/app/li_video/pipeline.py; SRC=working/video/li_video/p1/pipeline_stamped.py
  BASE=2eff189a5bdba7e353194f1b9ef8d1e7
fi
case "$OP" in
  install)
    HAVE="$(docker exec "$C" md5sum "$DST" 2>/dev/null | cut -d' ' -f1)"
    [ "$HAVE" = "$BASE" ] || { echo "REFUSED: $C:$DST md5 ${HAVE:-ABSENT} != $BASE (the stamped copy's base)" >&2; exit 6; }
    docker cp "$SRC" "$C:$DST" || exit 6
    echo "P1 stamps installed in $C:$DST (base md5 $BASE; stamped md5 $(md5sum "$SRC" | cut -d' ' -f1))"
    ;;
  collect)
    L="$4"
    docker cp "$C:/tmp/p1_stamps.jsonl" "$L/p1_stamps.jsonl" && echo "P1 stamps collected: $(wc -l < "$L/p1_stamps.jsonl") records" || echo "!! no P1 stamp file came out of $C"
    docker cp "$C:/tmp/p1_readback.json" "$L/p1_readback.json" && echo "P1 read-back collected" || echo "!! no P1 read-back came out of $C"
    ;;
  *) echo "unknown op $OP" >&2; exit 2 ;;
esac
