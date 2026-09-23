#!/usr/bin/env bash
# p0_v2_stamp.sh — install / collect the P0 V2 per-frame stamps in a RUNNING container.
#
#   bash working/scripts/p0_v2_stamp.sh rr install <container>
#   bash working/scripts/p0_v2_stamp.sh li install <container>
#   bash working/scripts/p0_v2_stamp.sh rr|li collect <container> <leg_dir>
#
# install copies the stamped copy over the container's own file (its writable layer — the image is
# never touched) ONLY if the container's original has the md5 the stamped copy was derived from;
# anything else refuses, because a stamped copy of a different file would measure a different arm.
# The caller restarts the container afterwards so the stamped module is what gets imported.
set -uo pipefail
ARM="$1"; OP="$2"; C="$3"
cd "$(dirname "$0")/../.." || exit 2
if [ "$ARM" = "rr" ]; then
  DST=/opt/rocketride/engine/nodes/detect/IInstance.py; SRC=working/nodes/p0_detect_stamped/IInstance.py
  BASE=984d80e45e885b5ae21e987664850b4c
else
  DST=/app/li_video/pipeline.py; SRC=working/video/li_video/p0/pipeline_stamped.py
  BASE=2eff189a5bdba7e353194f1b9ef8d1e7
fi
case "$OP" in
  install)
    HAVE="$(docker exec "$C" md5sum "$DST" 2>/dev/null | cut -d' ' -f1)"
    [ "$HAVE" = "$BASE" ] || { echo "REFUSED: $C:$DST md5 ${HAVE:-ABSENT} != $BASE (the stamped copy's base)" >&2; exit 6; }
    docker cp "$SRC" "$C:$DST" || exit 6
    echo "V2 stamps installed in $C:$DST (base md5 $BASE; stamped md5 $(md5sum "$SRC" | cut -d' ' -f1))"
    ;;
  collect)
    L="$4"
    docker cp "$C:/tmp/p0_v2_stamps.jsonl" "$L/p0_v2_stamps.jsonl" && echo "V2 stamps collected: $(wc -l < "$L/p0_v2_stamps.jsonl") records" || echo "!! no V2 stamp file came out of $C"
    ;;
  *) echo "unknown op $OP" >&2; exit 2 ;;
esac
