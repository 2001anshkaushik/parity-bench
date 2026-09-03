#!/usr/bin/env bash
# =============================================================================
# run_side_prediction_y.sh — RULING Y (2026-09-02): the DISCRIMINATING frame.
# The LAST probe on the divergence question either way (ruled).
#
# v2's result (landed + READ, FILMS_LANDING.md §2a): BOTH probe frames came
# back bit-equal across containers — but the large frame mapped onto a
# campaign-AGREEING frame (sampled idx 123; 113/248 of the film's frames
# diverged). This run points the SAME instrument at the ANATOMY FRAME:
# HouseOnBareMountain sampled index 10 (t=150 s) — the DEFINITIVE §6 worked
# example, where campaign RR found 6 detections >=0.3 [bottle .946/.935,
# chair .856/.449/.385, person .318] against LI's 5 [bottle .953/.934,
# chair .863/.490, person .433]. Frame choice over idx 124, with reasoning:
# a COUNT divergence with per-detection scores already recorded (so the
# probe's output joins against BOTH campaign sides, not just across probe
# sides), and an EXACT-PIPELINE extraction — the arms sample with ffmpeg
# fps=1/15, so frame 10 is reproduced by running the SAME filter from t=0
# and taking the 11th output (seek-free, byte-faithful to the arms'
# sampling; idx 124 would decode 31 min through the filter for a
# score-only divergence with no recorded per-detection values).
#
# == PRE-REGISTERED VERDICTS (Ruling Y, recorded before running) ==
#  V-A  arrays DIFFER                  -> the divergence is born in
#       PREPROCESSING on diverging content specifically.
#  V-B  arrays EQUAL, scores differ    -> born INSIDE predict; the recorded
#       torch thread values are then the leading candidate — reported
#       beside the delta.
#  V-C  arrays EQUAL, scores BIT-EQUAL on this KNOWN-DIVERGING frame
#       -> the divergence is CONTEXT-dependent, not frame-dependent: it
#       does not reproduce in single-inference isolation, and Ticket 6's
#       answer becomes "reproduces only under campaign execution context".
#       A finding, not a failure — and it CAPS this line of investigation.
#  CONTROL: small.png (v2's landed clean frame, sha-pinned below) must come
#  back bit-equal AGAIN in the same run — the instrument's own null.
#
# Fixes over v2 (both owned in the record):
#  * torch.get_num_threads()/get_num_interop_threads() + the six BLAS/OMP
#    env vars recorded per side (the v2 omission).
#  * NO FETCH POSSIBLE: the canonical rf-detr-base.pth is extracted ONCE
#    from the LI image (where it is baked; v2's li side used it,
#    MD5-correct), md5-printed, and placed in BOTH sides' working dirs;
#    the probe now REFUSES if it is absent from cwd and records
#    weights_md5 — both sides provably run the same bytes.
#  * PARSE-VERIFIED artifacts: v2's landed side files carried a stdout
#    prefix despite the file contract; whatever the mechanism, a non-JSON
#    side doc now refuses at the wrapper instead of landing dirty. Engine
#    exec stdout goes to a .log, never near the .json.
#  * Own OUT dir (detector_parity_y) — v2's landed artifacts untouched —
#    and the run ARCHIVES ITSELF to S3 at the end (the 09-02 lesson: the
#    archive step is part of the run, not a later paste).
# Committed script + self-printed sha256 (entry 25).
# Cost: ~15-25 min (rr bring-up ~8-12 if down; extraction <1 min; two
# model loads + four inferences ~4-6 min; compare + archive ~1 min).
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$ROOT"
echo "run_side_prediction_y.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PYF="${PYF:-$HOME/.venv-floor/bin/python3}"
CORPUS="${CORPUS:-$HOME/films_corpus/subset}"
V2OUT="$HOME/films_probe/detector_parity"
OUT="${OUT:-$HOME/films_probe/detector_parity_y}"
LI_IMAGE="${LI_IMAGE:-li:video}"
PROBE="working/video/probe/probe_detector_parity.py"
EPREFIX="/opt/rocketride/engine"
FILM="HouseOnBareMountain.mp4"
mkdir -p "$OUT"

echo "== control frame: v2's landed small.png, sha-pinned =="
SMALL_SHA_EXPECT="a82a6b2f32eb57cbf44b1626f5010015743ee2bbd19110a7a17e80d4fbd9a2e8"
[ -s "$V2OUT/small.png" ] || { echo "REFUSE: $V2OUT/small.png missing"; exit 3; }
SMALL_SHA="$(sha256sum "$V2OUT/small.png" | cut -d' ' -f1)"
[ "$SMALL_SHA" = "$SMALL_SHA_EXPECT" ] || { echo "REFUSE: small.png sha $SMALL_SHA != landed $SMALL_SHA_EXPECT"; exit 3; }
cp "$V2OUT/small.png" "$OUT/small.png"

echo "== rr bring-up (only if down) =="
CREATED_RR=0
if [ "$(docker inspect -f '{{.State.Running}}' rr 2>/dev/null)" != "true" ]; then
  docker rm -f rr >/dev/null 2>&1 || true
  docker run -d --name rr --memory 58g --log-opt max-size=200m --network host rr:patched-video >/dev/null
  "$HOME/.venv/bin/python" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  CREATED_RR=1
fi
cleanup() { [ "$CREATED_RR" = "1" ] && docker rm -f rr >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== frame 10 extraction — the arms' own filter, seek-free =="
FF="$("$PYF" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
rm -f "$OUT"/f10_*.png
"$FF" -nostdin -loglevel error -y -i "$CORPUS/$FILM" -vf fps=1/15 -frames:v 11 "$OUT/f10_%02d.png"
[ -s "$OUT/f10_11.png" ] || { echo "REFUSE: 11th sampled frame not produced"; exit 3; }
mv "$OUT/f10_11.png" "$OUT/frame10.png"; rm -f "$OUT"/f10_*.png
sha256sum "$OUT/frame10.png"

echo "== canonical weights: extracted ONCE from the LI image, shared to both sides =="
WSRC="$(docker run --rm --entrypoint sh "$LI_IMAGE" -c "find / -name 'rf-detr-base.pth' -not -path '/proc/*' 2>/dev/null | head -1")"
[ -n "$WSRC" ] || { echo "REFUSE: rf-detr-base.pth not found in $LI_IMAGE"; exit 3; }
CID="$(docker create "$LI_IMAGE")"; docker cp "$CID:$WSRC" "$OUT/rf-detr-base.pth"; docker rm "$CID" >/dev/null
echo "weights md5: $(md5sum "$OUT/rf-detr-base.pth" | cut -d' ' -f1)  (v2's li side validated this file against rf-detr's canonical MD5)"

echo "== engine interpreter by capability (v2 method) =="
SHEBANG="$(docker exec rr sh -c "head -1 $EPREFIX/bin/pip3 2>/dev/null | sed 's/^#!//'" || true)"
EPY=""
for cand in $SHEBANG $EPREFIX/engine $EPREFIX/bin/python3.12 $EPREFIX/bin/python3; do
  [ -n "$cand" ] || continue
  if timeout 90 docker exec rr "$cand" -c 'import torch, rfdetr; print("CAP_OK")' 2>/dev/null | grep -q CAP_OK; then
    EPY="$cand"; echo "  CAPABLE: $cand"; break
  fi
done
[ -n "$EPY" ] || { echo "REFUSE: no capable engine interpreter — report and stop (scope ruling)"; exit 3; }

echo "== side runs (one model load each; cwd holds the weights; no fetch possible) =="
docker exec rr sh -c "mkdir -p /tmp/ywork"
docker cp "$PROBE" rr:/tmp/ywork/probe_detector_parity.py
docker cp "$OUT/small.png" rr:/tmp/ywork/small.png
docker cp "$OUT/frame10.png" rr:/tmp/ywork/frame10.png
docker cp "$OUT/rf-detr-base.pth" rr:/tmp/ywork/rf-detr-base.pth
docker exec -w /tmp/ywork -e NO_ALBUMENTATIONS_UPDATE=1 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 rr "$EPY" \
    /tmp/ywork/probe_detector_parity.py --side engine --png /tmp/ywork/small.png /tmp/ywork/frame10.png \
    --side-out /tmp/ywork/side_engine_y.json >"$OUT/side_engine_y.log" 2>"$OUT/side_engine_y.err"
docker cp rr:/tmp/ywork/side_engine_y.json "$OUT/side_engine_y.json"
docker run --rm -w /data -e NO_ALBUMENTATIONS_UPDATE=1 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -v "$ROOT/$PROBE:/tmp/probe_detector_parity.py:ro" -v "$OUT:/data" --entrypoint python "$LI_IMAGE" \
    /tmp/probe_detector_parity.py --side li --png /data/small.png /data/frame10.png \
    --side-out /data/side_li_y.json >"$OUT/side_li_y.log" 2>"$OUT/side_li_y.err"

echo "== parse-verify both side docs (refuse a dirty artifact) =="
"$PYF" - "$OUT/side_engine_y.json" "$OUT/side_li_y.json" <<'PYCHK'
import json, sys
for p in sys.argv[1:]:
    json.load(open(p)); print(f'  parse OK: {p}')
PYCHK

echo "== VERDICT (pre-registered above; committed comparator) =="
"$PYF" "$PROBE" --compare "$OUT/side_engine_y.json" "$OUT/side_li_y.json" | tee "$OUT/compare_y.json"

echo "== archive (part of the run, not a later paste) =="
( cd "$OUT/.." && find detector_parity_y -type f -not -name 'rf-detr-base.pth' -exec sha256sum {} + | sort -k2 )
aws s3 sync "$OUT" s3://rocketride-benchmark-data/ansh/detector-parity-y-20260902/ --exclude 'rf-detr-base.pth'
aws s3 ls s3://rocketride-benchmark-data/ansh/detector-parity-y-20260902/ --recursive
echo "DONE — paste everything above back."
