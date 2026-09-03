#!/usr/bin/env bash
# =============================================================================
# run_side_prediction_y.sh — RULING Y: the DISCRIMINATING frame (frame 10).
# The LAST probe on the divergence question either way (ruled) — one run,
# BOTH thread conditions, no successor.
#
# RUN 1 (2026-09-02) record: engine side COMPLETED at default thread state
# (doc records intraop 16 / interop 16, six env vars null — the STANDALONE
# default, NOT the campaign's six-vars=2 posture); LI side loaded, ran, and
# failed ONLY at the final write — li:video runs as ws1v (uid 10002) and the
# host-owned /data mount is not writable by it. THIS revision: (i) LI writes
# into a 777 `liout/` subdir, moved up by the wrapper; (ii) artifacts are
# RESUMED, never remade (frame10.png + weights + the completed engine
# default-side doc, each pinned by hash below); (iii) a SECOND CONDITION is
# added per Ruling-Y task 2: both sides re-run with ALL SIX thread vars = 2
# — the exact per-container env mechanism the campaign legs used to pin
# torch to 2 — so the probe covers the campaign's thread state, not only
# the standalone default. Recorded per side per condition by the probe.
#
# == PRE-REGISTERED VERDICTS (restated 2026-09-02 for the two-condition
#    design, BEFORE the re-run; originals below unchanged) ==
#  Condition D  = default env (run 1's state; both sides expected 16/16 —
#                 confirmed like-for-like only by the recorded values).
#  Condition T2 = all six vars = 2, both sides (campaign thread posture).
#  T-1  BOTH conditions bit-equal (arrays + scores)
#       -> STRONGER than the original V-C: the divergence is
#          CONTEXT-dependent AND thread count alone, at matched values
#          (default and campaign), does not reproduce it in isolation.
#          Ticket 6: "reproduces only under campaign execution context;
#          matched thread state in isolation does not reproduce it."
#          CAPS the line.
#  T-2  divergence in exactly ONE condition
#       -> thread-state-CONDITIONAL divergence inside predict; the
#          condition and both sides' recorded values name the mechanism's
#          trigger. (A divergence only at T2 = campaign-relevant directly.)
#  T-3  divergence in BOTH conditions -> the original V-A/V-B apply by
#       layer: arrays differ = preprocessing on diverging content;
#       arrays equal + scores differ = inside predict.
#  T-4  recorded values reveal a CROSS-SIDE thread mismatch within a
#       condition -> that condition is NOT like-for-like; its verdict
#       carries the caveat and the matched condition rules.
#  CONTROL (both conditions): small.png must come back bit-equal.
#
# == ORIGINAL PRE-REGISTERED VERDICTS (run 1, kept verbatim) ==
#  V-A  arrays DIFFER                  -> divergence born in PREPROCESSING
#       on diverging content specifically.
#  V-B  arrays EQUAL, scores differ    -> born INSIDE predict; recorded
#       thread values are the leading candidate.
#  V-C  arrays EQUAL, scores BIT-EQUAL on this KNOWN-DIVERGING frame
#       -> divergence is CONTEXT-dependent, not frame-dependent; Ticket 6
#       answer becomes "reproduces only under campaign execution context".
#
# Frame: HouseOnBareMountain sampled index 10 (t=150 s) — §6's worked
# example (campaign RR 6 detections >=0.3 vs LI 5, per-detection scores
# recorded) — extracted RUN 1 via the arms' own fps=1/15 filter, seek-free.
# Committed script + self-printed sha256 (entry 25).
# Cost this revision: ~12-20 min (rr bring-up if down ~8-12; engine default
# side REUSED; 3 model loads + 6 inferences ~6-9; compares + archive ~1).
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
SMALL_SHA_EXPECT="a82a6b2f32eb57cbf44b1626f5010015743ee2bbd19110a7a17e80d4fbd9a2e8"
FRAME10_SHA_EXPECT="83a02b923d8c1aea116b1b68dbbb2cce0acbb33ef2d58f82b354b051149ed845"
WEIGHTS_MD5_EXPECT="b4d3ce46099eaed50626ede388caf979"
T2ENV=(-e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
       -e VECLIB_MAXIMUM_THREADS=2 -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2)
COMMON=(-e NO_ALBUMENTATIONS_UPDATE=1 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1)
mkdir -p "$OUT"

echo "== control frame: v2's landed small.png, sha-pinned =="
[ -s "$V2OUT/small.png" ] || { echo "REFUSE: $V2OUT/small.png missing"; exit 3; }
[ "$(sha256sum "$V2OUT/small.png" | cut -d' ' -f1)" = "$SMALL_SHA_EXPECT" ] || { echo "REFUSE: small.png sha mismatch"; exit 3; }
cp -f "$V2OUT/small.png" "$OUT/small.png"

echo "== frame10: REUSE (Ruling-Y re-run order: do NOT re-extract) =="
if [ -s "$OUT/frame10.png" ] && [ "$(sha256sum "$OUT/frame10.png" | cut -d' ' -f1)" = "$FRAME10_SHA_EXPECT" ]; then
  echo "  REUSED frame10.png (sha verified $FRAME10_SHA_EXPECT)"
else
  echo "  frame10.png absent or sha-mismatched — extracting via the arms' filter (fallback only)"
  FF="$("$PYF" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
  rm -f "$OUT"/f10_*.png
  "$FF" -nostdin -loglevel error -y -i "$CORPUS/$FILM" -vf fps=1/15 -frames:v 11 "$OUT/f10_%02d.png"
  [ -s "$OUT/f10_11.png" ] || { echo "REFUSE: 11th sampled frame not produced"; exit 3; }
  mv "$OUT/f10_11.png" "$OUT/frame10.png"; rm -f "$OUT"/f10_*.png
  sha256sum "$OUT/frame10.png"
fi

echo "== weights: REUSE if md5-pinned, else extract from the LI image =="
if [ -s "$OUT/rf-detr-base.pth" ] && [ "$(md5sum "$OUT/rf-detr-base.pth" | cut -d' ' -f1)" = "$WEIGHTS_MD5_EXPECT" ]; then
  echo "  REUSED rf-detr-base.pth (md5 $WEIGHTS_MD5_EXPECT)"
else
  WSRC="$(docker run --rm --entrypoint sh "$LI_IMAGE" -c "find / -name 'rf-detr-base.pth' -not -path '/proc/*' 2>/dev/null | head -1")"
  [ -n "$WSRC" ] || { echo "REFUSE: rf-detr-base.pth not found in $LI_IMAGE"; exit 3; }
  CID="$(docker create "$LI_IMAGE")"; docker cp "$CID:$WSRC" "$OUT/rf-detr-base.pth"; docker rm "$CID" >/dev/null
  [ "$(md5sum "$OUT/rf-detr-base.pth" | cut -d' ' -f1)" = "$WEIGHTS_MD5_EXPECT" ] || { echo "REFUSE: extracted weights md5 mismatch"; exit 3; }
fi

echo "== LI write path fix: 777 liout/ subdir (li:video runs as uid 10002) =="
mkdir -p "$OUT/liout"; chmod 777 "$OUT/liout"

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

echo "== engine interpreter by capability =="
SHEBANG="$(docker exec rr sh -c "head -1 $EPREFIX/bin/pip3 2>/dev/null | sed 's/^#!//'" || true)"
EPY=""
for cand in $SHEBANG $EPREFIX/engine $EPREFIX/bin/python3.12 $EPREFIX/bin/python3; do
  [ -n "$cand" ] || continue
  if timeout 90 docker exec rr "$cand" -c 'import torch, rfdetr; print("CAP_OK")' 2>/dev/null | grep -q CAP_OK; then
    EPY="$cand"; echo "  CAPABLE: $cand"; break
  fi
done
[ -n "$EPY" ] || { echo "REFUSE: no capable engine interpreter"; exit 3; }
docker exec rr sh -c "mkdir -p /tmp/ywork"
docker cp "$PROBE" rr:/tmp/ywork/probe_detector_parity.py
docker cp "$OUT/small.png" rr:/tmp/ywork/small.png
docker cp "$OUT/frame10.png" rr:/tmp/ywork/frame10.png
docker cp "$OUT/rf-detr-base.pth" rr:/tmp/ywork/rf-detr-base.pth

run_engine() {  # $1 = out name; extra env after
  local out="$1"; shift
  docker exec -w /tmp/ywork "${COMMON[@]}" "$@" rr "$EPY" \
      /tmp/ywork/probe_detector_parity.py --side engine --png /tmp/ywork/small.png /tmp/ywork/frame10.png \
      --side-out "/tmp/ywork/$out" >"$OUT/${out%.json}.log" 2>"$OUT/${out%.json}.err"
  docker cp "rr:/tmp/ywork/$out" "$OUT/$out"
}
run_li() {      # $1 = out name; extra env after
  local out="$1"; shift
  docker run --rm -w /data "${COMMON[@]}" "$@" \
      -v "$ROOT/$PROBE:/tmp/probe_detector_parity.py:ro" -v "$OUT:/data" --entrypoint python "$LI_IMAGE" \
      /tmp/probe_detector_parity.py --side li --png /data/small.png /data/frame10.png \
      --side-out "/data/liout/$out" >"$OUT/${out%.json}.log" 2>"$OUT/${out%.json}.err"
  mv -f "$OUT/liout/$out" "$OUT/$out"
}

echo "== CONDITION D (default env) =="
if [ -s "$OUT/side_engine_y.json" ] && "$PYF" -c "import json,sys; json.load(open('$OUT/side_engine_y.json'))" 2>/dev/null; then
  echo "  REUSED run-1's completed engine default-side doc (parses clean)"
else
  run_engine side_engine_y.json
fi
run_li side_li_y.json

echo "== CONDITION T2 (all six vars = 2 — the campaign's pinning mechanism) =="
run_engine side_engine_y_t2.json "${T2ENV[@]}"
run_li side_li_y_t2.json "${T2ENV[@]}"

echo "== parse-verify all four side docs (refuse a dirty artifact) =="
"$PYF" - "$OUT/side_engine_y.json" "$OUT/side_li_y.json" "$OUT/side_engine_y_t2.json" "$OUT/side_li_y_t2.json" <<'PYCHK'
import json, sys
for p in sys.argv[1:]:
    json.load(open(p)); print(f'  parse OK: {p}')
PYCHK

echo "== THREAD STATE PER SIDE PER CONDITION (recorded by the probe) =="
"$PYF" - "$OUT" <<'PYTS'
import json, sys, os
out = sys.argv[1]
for name in ('side_engine_y', 'side_li_y', 'side_engine_y_t2', 'side_li_y_t2'):
    d = json.load(open(os.path.join(out, name + '.json')))
    print(f"  {name}: torch_threads={d.get('torch_threads')}  weights_md5={d.get('weights_md5')}")
    print(f"    thread_env={d.get('thread_env')}")
PYTS

echo "== VERDICT, CONDITION D (pre-registered above) =="
"$PYF" "$PROBE" --compare "$OUT/side_engine_y.json" "$OUT/side_li_y.json" | tee "$OUT/compare_y.json"
echo "== VERDICT, CONDITION T2 (pre-registered above) =="
"$PYF" "$PROBE" --compare "$OUT/side_engine_y_t2.json" "$OUT/side_li_y_t2.json" | tee "$OUT/compare_y_t2.json"

echo "== archive (part of the run) =="
( cd "$OUT/.." && find detector_parity_y -type f -not -name 'rf-detr-base.pth' -exec sha256sum {} + | sort -k2 )
aws s3 sync "$OUT" s3://rocketride-benchmark-data/ansh/detector-parity-y-20260902/ --exclude 'rf-detr-base.pth' --exclude 'liout/*'
aws s3 ls s3://rocketride-benchmark-data/ansh/detector-parity-y-20260902/ --recursive
echo "DONE — paste everything above back."
