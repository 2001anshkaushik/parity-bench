#!/usr/bin/env bash
# =============================================================================
# run_wrapper_resize_parity.sh — V-D (2026-09-06; v2 2026-09-07): the engine
# facade's LANCZOS pre-downscale to infer_edge=560 vs the campaign RR output on
# the Ruling-Y diverging frame. Pre-registered in probe_wrapper_resize_parity.py.
#
# v2 (after the v1 refusal "no python with torch+rfdetr+PIL inside rr"): the
# interpreter discovery, the offline weights and the cleanup trap are the Ruling-Y
# runner's, reused verbatim (run_side_prediction_y.sh:71-137): the engine image's
# capable interpreter is found by CAPABILITY among the pip3 shebang, the `engine`
# launcher and the venv pythons; RFDETRBase() runs OFFLINE and resolves
# ./rf-detr-base.pth from the cwd, so the checkpoint is extracted from the LI image
# (the same bytes both arms measured with) and md5-pinned against the LANDED Y
# artifact's weights_md5; an EXIT trap removes the rr container this script starts.
#
# DO NOT RUN WHILE A MEASURED LEG IS LIVE. Refuses if the films500 plan lock is
# held. Starts rr ONLY if none is running (six vars = 2 = the campaign condition)
# and removes it on exit ONLY if it started it. ~3-5 min. One SSM session.
# Committed script + self-printed sha256 (entry 25).
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE/../../.."
echo "run_wrapper_resize_parity.sh sha256: $(sha256sum "working/video/probe/run_wrapper_resize_parity.sh" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"
exec 9>"$HOME/.films500_plan.lock"
flock -n 9 || { echo "NOT DONE — a films500 plan/lifetime run is ALIVE (plan lock held); this probe waits for the landing"; exit 1; }
PY="${PYBIN:-$HOME/.venv/bin/python}"
FRAME="working/video/results/detector-parity-y-20260902/frame10.png"
YJSON="working/video/results/detector-parity-y-20260902/side_engine_y.json"
[ -f "$FRAME" ] || { echo "NOT DONE — $FRAME missing"; exit 1; }
[ -f "$YJSON" ] || { echo "NOT DONE — $YJSON missing (the weights md5 pin)"; exit 1; }
echo "frame sha256: $(sha256sum "$FRAME" | cut -c1-16) (pinned 83a02b923d8c1aea)"
WEIGHTS_MD5_EXPECT="$("$PY" -c "import json;print(json.load(open('$YJSON'))['weights_md5'])")"
echo "weights md5 pin (landed Y artifact): $WEIGHTS_MD5_EXPECT"
EPREFIX="/opt/rocketride/engine"
LI_IMAGE="${LI_IMAGE:-li:video}"
COMMON=(-e NO_ALBUMENTATIONS_UPDATE=1 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1
        -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e VECLIB_MAXIMUM_THREADS=2
        -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2)
OUT="working/video/results/wrapper-resize-parity-$(date -u +%Y%m%d)"; mkdir -p "$OUT"

echo "== weights: REUSE if md5-pinned, else extract from $LI_IMAGE (the Y runner's method) =="
if [ -s "$OUT/rf-detr-base.pth" ] && [ "$(md5sum "$OUT/rf-detr-base.pth" | cut -d' ' -f1)" = "$WEIGHTS_MD5_EXPECT" ]; then
  echo "  REUSED rf-detr-base.pth (md5 $WEIGHTS_MD5_EXPECT)"
else
  WSRC="$(docker run --rm --entrypoint sh "$LI_IMAGE" -c "find / -name 'rf-detr-base.pth' -not -path '/proc/*' 2>/dev/null | head -1")"
  [ -n "$WSRC" ] || { echo "NOT DONE — rf-detr-base.pth not found in $LI_IMAGE"; exit 3; }
  CID="$(docker create "$LI_IMAGE")"; docker cp "$CID:$WSRC" "$OUT/rf-detr-base.pth"; docker rm "$CID" >/dev/null
  GOT="$(md5sum "$OUT/rf-detr-base.pth" | cut -d' ' -f1)"
  [ "$GOT" = "$WEIGHTS_MD5_EXPECT" ] || { echo "NOT DONE — extracted weights md5 $GOT != pinned $WEIGHTS_MD5_EXPECT"; exit 3; }
  echo "  EXTRACTED rf-detr-base.pth from $LI_IMAGE:$WSRC (md5 $GOT == pin)"
fi

echo "== rr bring-up (only if down) =="
STARTED=0
if [ "$(docker inspect -f '{{.State.Running}}' rr 2>/dev/null)" != "true" ]; then
  docker rm -f rr >/dev/null 2>&1 || true
  echo "  starting rr:patched-video with the six vars = 2 (campaign condition)"
  docker run -d --name rr --memory 58g -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
    -e VECLIB_MAXIMUM_THREADS=2 -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2 --log-opt max-size=200m --network host rr:patched-video >/dev/null
  STARTED=1
  "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
fi
cleanup() { [ "$STARTED" = "1" ] && docker rm -f rr >/dev/null 2>&1 && echo "rr (started by this probe) removed" || true; }
trap cleanup EXIT

echo "== engine interpreter by CAPABILITY (Y runner's method) =="
SHEBANG="$(docker exec rr sh -c "head -1 $EPREFIX/bin/pip3 2>/dev/null | sed 's/^#!//'" || true)"
EPY=""
for cand in $SHEBANG $EPREFIX/engine $EPREFIX/bin/python3.12 $EPREFIX/bin/python3; do
  [ -n "$cand" ] || continue
  if timeout 90 docker exec "${COMMON[@]}" rr "$cand" -c 'import torch, rfdetr, PIL; print("CAP_OK")' 2>/dev/null | grep -q CAP_OK; then
    EPY="$cand"; echo "  CAPABLE: $cand"; break
  fi
done
[ -n "$EPY" ] || { echo "NOT DONE — no capable engine interpreter among: $SHEBANG $EPREFIX/engine $EPREFIX/bin/python3.12 $EPREFIX/bin/python3"; exit 3; }

docker exec rr sh -c 'mkdir -p /tmp/vd'
docker cp "$FRAME" rr:/tmp/vd/frame10.png
docker cp working/video/probe/probe_wrapper_resize_parity.py rr:/tmp/vd/probe.py
docker cp "$OUT/rf-detr-base.pth" rr:/tmp/vd/rf-detr-base.pth
echo "== side (inside rr, cwd /tmp/vd, six vars = 2) =="
docker exec -w /tmp/vd "${COMMON[@]}" rr "$EPY" /tmp/vd/probe.py --side --frame /tmp/vd/frame10.png --out /tmp/vd/side_vd.json 2>&1 | tee "$OUT/side_vd.log"
docker cp rr:/tmp/vd/side_vd.json "$OUT/side_vd.json"
echo "== compare =="
"$PY" working/video/probe/probe_wrapper_resize_parity.py --compare "$OUT/side_vd.json" --weights-md5 "$WEIGHTS_MD5_EXPECT" | tee "$OUT/verdict.txt"
( cd "$OUT" && sha256sum side_vd.json side_vd.log verdict.txt )
echo "=== V-D DONE — $OUT (rf-detr-base.pth is NOT landed: md5-pinned, reproducible from $LI_IMAGE) ==="
