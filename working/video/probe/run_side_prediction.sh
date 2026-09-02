#!/usr/bin/env bash
# =============================================================================
# SIDE TEST AS A PREDICTION TEST (2026-09-02, ruled). The size partition is
# perfect (35/35: every film with long edge <= 560px is bit-identical across
# arms; every film above it diverges — 560 is RF-DETR's input edge), and the
# near-threshold split falsified threshold amplification (clean vs diverging
# near01 rates 0.05119 vs 0.04514; adjacent fraction 0.524). This block
# tests the PREDICTION, not a confirmation:
#
#   PRE-REGISTERED PREDICTIONS (printed again before anything runs):
#   P1  small frame (20000LeaguesUndertheSea, 320x240 — the clean class):
#       pre-predict arrays EQUAL and raw scores within <=1e-5 (the measured
#       Leagues float-noise background, ~1e-7).
#   P2  large frame (HouseOnBareMountain, >560px — the diverging class):
#       pre-predict arrays EQUAL (the load paths are equivalent on RGB —
#       census-established) BUT raw scores diverge at %-scale (>=1e-3) or
#       detection counts change: the divergence arises INSIDE predict,
#       where the downscale runs.
#   FALSIFIER: a large-frame delta at 1e-7 scale kills the resize mechanism
#   too and forces a deeper bisect. libs_identity (pillow/torch/torchvision
#   versions + rfdetr detr.py sha per container) rides the verdict: a
#   pillow or wheel-bytes mismatch = the resize class; all-equal libs =
#   deeper bisect.
#
# Also in this ONE bring-up (rr is currently down): the torch BUILD reads
# both containers (version.py incl. git/cuda, wheel tag, torch/lib listing —
# the BLAS bundle question), and the installed rfdetr predict SOURCE dumped
# from both containers and diffed (same version string does not guarantee
# same bytes).
#
# Cost ~8-12 min: rr bring-up ~2-3, two frame extracts ~1, build reads
# ~1, one model load per side ~2-3 each, compares seconds. No leg re-run,
# no gate changed. Committed script + self-printed sha256 (entry 25).
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_side_prediction.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PYF="${PYF:-$HOME/.venv-floor/bin/python3}"
MANIFEST="working/video/films_video_manifest.jsonl"
CORPUS="${CORPUS:-$HOME/films_corpus/subset}"
OUT="${OUT:-$HOME/films_probe/detector_parity}"
LI_IMAGE="${LI_IMAGE:-li:video}"
SMALL_FILM="20000LeaguesUndertheSea.mp4"
LARGE_FILM="HouseOnBareMountain.mp4"
PROBE="working/video/probe/probe_detector_parity.py"
mkdir -p "$OUT"

echo "== PRE-REGISTERED PREDICTIONS =="
echo "P1 small ($SMALL_FILM, 320x240): arrays EQUAL, scores <= 1e-5 (noise floor)"
echo "P2 large ($LARGE_FILM, >560px): arrays EQUAL, scores %-scale (>=1e-3) or counts change"
echo "FALSIFIER: large-frame delta at 1e-7 scale kills the resize mechanism too"

CREATED_RR=0
if [ "$(docker inspect -f '{{.State.Running}}' rr 2>/dev/null)" != "true" ]; then
  echo "rr is down — bringing up a default lifetime"
  docker rm -f rr >/dev/null 2>&1 || true
  docker run -d --name rr --memory 58g --log-opt max-size=200m --network host \
      rr:patched-video >/dev/null
  "$HOME/.venv/bin/python" working/video/probe/wait_ready.py --arm rr --port 5565 \
      --deadline 1800 --container rr
  CREATED_RR=1
fi
cleanup() {
  [ "$CREATED_RR" = "1" ] && docker rm -f rr >/dev/null 2>&1 || true
}
trap cleanup EXIT

EPY="$(docker exec rr sh -c 'for p in /opt/rocketride/engine/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do [ -x "$p" ] && { echo "$p"; break; }; done')"
[ -n "$EPY" ] || { echo "NOT DONE — no python found in rr container"; exit 1; }
echo "engine python: $EPY"

echo "== frame extraction (mid-film, the arms' own ffmpeg) =="
mid() { "$PYF" - "$MANIFEST" "$1" <<'PYMID'
import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get('file') == sys.argv[2]:
        print(r['video_s'] / 2); break
else:
    raise SystemExit(f'NOT DONE — {sys.argv[2]} not in manifest')
PYMID
}
FF="$("$PYF" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
"$FF" -nostdin -loglevel error -y -ss "$(mid "$SMALL_FILM")" -i "$CORPUS/$SMALL_FILM" \
    -frames:v 1 -vcodec png "$OUT/small.png"
"$FF" -nostdin -loglevel error -y -ss "$(mid "$LARGE_FILM")" -i "$CORPUS/$LARGE_FILM" \
    -frames:v 1 -vcodec png "$OUT/large.png"
ls -la "$OUT"/small.png "$OUT"/large.png

echo "== TASK 3: torch BUILD identity, both containers =="
TREAD='import torch, os; d = os.path.dirname(torch.__file__); print(open(os.path.join(d, "version.py")).read()); import glob; print(sorted(os.path.basename(x) for x in glob.glob(os.path.join(d, "lib", "*")))[:24]); w = glob.glob(os.path.join(d, "..", "torch-*.dist-info", "WHEEL")); print(open(w[0]).read() if w else "no WHEEL file")'
echo "-- engine (rr) --";  docker exec rr "$EPY" -c "$TREAD"
echo "-- li ($LI_IMAGE) --"; docker run --rm --entrypoint python "$LI_IMAGE" -c "$TREAD"

echo "== installed rfdetr predict SOURCE, both containers, diffed =="
PREDSRC='import inspect; from rfdetr import RFDETRBase; print(inspect.getsource(inspect.unwrap(RFDETRBase.predict)))'
docker exec rr "$EPY" -c "$PREDSRC" > "$OUT/predict_engine.py.txt" 2>"$OUT/predict_engine.err" || \
  { echo "engine predict-source dump FAILED:"; cat "$OUT/predict_engine.err"; }
docker run --rm --entrypoint python "$LI_IMAGE" -c "$PREDSRC" > "$OUT/predict_li.py.txt" 2>"$OUT/predict_li.err" || \
  { echo "li predict-source dump FAILED:"; cat "$OUT/predict_li.err"; }
if diff -q "$OUT/predict_engine.py.txt" "$OUT/predict_li.py.txt" >/dev/null 2>&1; then
  echo "predict source: IDENTICAL across containers"
else
  echo "predict source: DIFFERS — diff follows"
  diff "$OUT/predict_engine.py.txt" "$OUT/predict_li.py.txt" || true
fi

echo "== side runs (one model load each; stderr to .err files) =="
docker cp "$PROBE" rr:/tmp/probe_detector_parity.py
docker cp "$OUT/small.png" rr:/tmp/small.png
docker cp "$OUT/large.png" rr:/tmp/large.png
docker exec -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 rr "$EPY" \
    /tmp/probe_detector_parity.py --side engine --png /tmp/small.png /tmp/large.png \
    > "$OUT/side_engine.json" 2>"$OUT/side_engine.err"
docker run --rm -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -v "$ROOT/$PROBE:/tmp/probe_detector_parity.py:ro" \
    -v "$OUT:/data" --entrypoint python "$LI_IMAGE" \
    /tmp/probe_detector_parity.py --side li --png /data/small.png /data/large.png \
    > "$OUT/side_li.json" 2>"$OUT/side_li.err"

echo "== VERDICTS (predictions above; libs identity rides them) =="
"$PYF" "$PROBE" --compare "$OUT/side_engine.json" "$OUT/side_li.json"
echo "DONE — artifacts in $OUT (side_*.json, predict_*.py.txt, *.err)."
echo "Bring back the verdict block, the libs_diff, the torch build reads,"
echo "and the predict-source diff line verbatim."
