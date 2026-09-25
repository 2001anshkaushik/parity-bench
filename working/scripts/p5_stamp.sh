#!/usr/bin/env bash
# p5_stamp.sh — install / collect the P5 stamped detect copy (IInstance.py + infer_worker.py) in a RUNNING rr:p5-infer
# container (its writable layer; the image is never touched). The P1 twin is p1_stamp.sh (stock RR and LI legs).
#
#   bash working/scripts/p5_stamp.sh install <container>
#   bash working/scripts/p5_stamp.sh collect <container> <leg_dir>
#
# install refuses unless the container's IGlobal.py, IInstance.py and infer_worker.py carry the md5s of the clean P5
# source in this worktree (working/nodes/p5_infer_src) — the files the stamped copies derive from. The caller
# restarts the container so the copy is imported.
set -uo pipefail
OP="$1"; C="$2"
cd "$(dirname "$0")/../.." || exit 2
NODE=/opt/rocketride/engine/nodes/detect; SRC=working/nodes/p5_infer_src; ST=working/nodes/p5_infer_stamped
case "$OP" in
  install)
    for f in IGlobal.py IInstance.py infer_worker.py; do
      WANT="$(md5sum "$SRC/$f" | cut -d' ' -f1)"
      HAVE="$(docker exec "$C" md5sum "$NODE/$f" 2>/dev/null | cut -d' ' -f1)"
      [ "$HAVE" = "$WANT" ] || { echo "REFUSED: $C:$NODE/$f md5 ${HAVE:-ABSENT} != $WANT (the clean P5 file)" >&2; exit 6; }
    done
    docker cp "$ST/IInstance.py" "$C:$NODE/IInstance.py" || exit 6
    docker cp "$ST/infer_worker.py" "$C:$NODE/infer_worker.py" || exit 6
    echo "P5 stamps installed in $C (IInstance $(md5sum "$ST/IInstance.py" | cut -c1-12), infer_worker $(md5sum "$ST/infer_worker.py" | cut -c1-12))"
    ;;
  collect)
    L="$3"
    docker cp "$C:/tmp/p5_stamps.jsonl" "$L/p5_stamps.jsonl" && echo "P5 stamps collected: $(wc -l < "$L/p5_stamps.jsonl") records" || echo "!! no P5 stamp file came out of $C"
    docker cp "$C:/tmp/p5_readback.json" "$L/p5_readback.json" && echo "P5 read-back collected" || echo "!! no P5 read-back came out of $C"
    ;;
  *) echo "unknown op $OP" >&2; exit 2 ;;
esac
