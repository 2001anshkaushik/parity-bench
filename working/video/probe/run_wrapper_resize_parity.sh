#!/usr/bin/env bash
# =============================================================================
# run_wrapper_resize_parity.sh — V-D (2026-09-06): the engine facade's LANCZOS
# pre-downscale to infer_edge=560 vs the campaign RR output on the Ruling-Y
# diverging frame. Pre-registered in probe_wrapper_resize_parity.py.
#
# DO NOT RUN WHILE A MEASURED LEG IS LIVE. Refuses if the films500 plan lock is
# held. Needs a LIVE rr container (rr:patched-video) at the campaign thread
# condition — this script starts one ONLY if none is running, with the six
# vars = 2, and removes it afterwards ONLY if it started it. ~3 min.
# Committed script + self-printed sha256 (entry 25). One SSM session.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE/../../.."
echo "run_wrapper_resize_parity.sh sha256: $(sha256sum "working/video/probe/run_wrapper_resize_parity.sh" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"
exec 9>"$HOME/.films500_plan.lock"
flock -n 9 || { echo "NOT DONE — a films500 plan/lifetime run is ALIVE (plan lock held); this probe waits for the landing"; exit 1; }
FRAME="working/video/results/detector-parity-y-20260902/frame10.png"
[ -f "$FRAME" ] || { echo "NOT DONE — $FRAME missing"; exit 1; }
echo "frame sha256: $(sha256sum "$FRAME" | cut -c1-16) (pinned 83a02b923d8c1aea)"
OUT="working/video/results/wrapper-resize-parity-$(date -u +%Y%m%d)"; mkdir -p "$OUT"
STARTED=0
if ! docker inspect rr >/dev/null 2>&1; then
  echo "no rr container: starting rr:patched-video with the six vars = 2 (campaign condition)"
  docker run -d --name rr --memory 58g -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
    -e VECLIB_MAXIMUM_THREADS=2 -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2 --network host rr:patched-video >/dev/null
  STARTED=1
  "$HOME/.venv/bin/python" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
fi
docker exec rr sh -c 'mkdir -p /tmp/vd'
docker cp "$FRAME" rr:/tmp/vd/frame10.png
docker cp working/video/probe/probe_wrapper_resize_parity.py rr:/tmp/vd/probe.py
EPY=""
for c in /opt/rocketride/engine/bin/python3 /opt/rocketride/engine/bin/python python3; do
  if docker exec rr "$c" -c 'import torch, rfdetr, PIL; print("CAP_OK")' 2>/dev/null | grep -q CAP_OK; then EPY="$c"; break; fi
done
[ -n "$EPY" ] || { echo "NOT DONE — no python with torch+rfdetr+PIL inside rr"; exit 1; }
echo "engine python: $EPY"
# the six vars = 2 on the exec (the container's env is the campaign's; stated explicitly anyway)
docker exec -w /tmp/vd -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e VECLIB_MAXIMUM_THREADS=2 \
  -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 rr \
  "$EPY" /tmp/vd/probe.py --side --frame /tmp/vd/frame10.png --out /tmp/vd/side_vd.json 2>&1 | tee "$OUT/side_vd.log"
docker cp rr:/tmp/vd/side_vd.json "$OUT/side_vd.json"
"$HOME/.venv/bin/python" working/video/probe/probe_wrapper_resize_parity.py --compare "$OUT/side_vd.json" | tee "$OUT/verdict.txt"
if [ "$STARTED" = "1" ]; then docker rm -f rr >/dev/null; echo "rr (started by this probe) removed"; fi
sha256sum "$OUT"/* | cut -c1-80
echo "=== V-D DONE — $OUT (entry-26 landing next) ==="
