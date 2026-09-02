#!/usr/bin/env bash
# =============================================================================
# SIDE TEST AS A PREDICTION TEST — v2 (2026-09-02). v1 died on interpreter
# resolution: the engine does NOT use the container's system python — its
# console-script shebangs point at /opt/rocketride/engine/engine (the engine
# executable EMBEDS CPython and is the venv's registered interpreter;
# engine/bin/pip3 shebang, laptop extract). v1's fallback reached for
# /usr/bin/python3 — the ~/.venv-vs-~/.venv-floor trap one layer in. v2:
#   * interpreter resolved by CAPABILITY, never by name: every candidate
#     must `import torch, rfdetr` inside 90 s or is rejected; NO system
#     fallback exists; none-found = fail closed with the tried list.
#   * RESUMABLE: frames already on disk are REUSED (small.png 25,519 B /
#     large.png 400,575 B extracted by v1 — never re-extracted); the rr
#     bring-up is skipped when rr runs.
#   * EVIDENCE IN LAYERS, python-free first: the torch build reads, the
#     package-version scrape and the rfdetr detr.py byte-diff need only
#     sh/find/cat in each container — they CANNOT die on an interpreter and
#     they likely name the differing library on their own. The predict run
#     (scores) is the LAST layer; if the embedded interpreter cannot run it
#     standalone, the script REPORTS AND STOPS (exit 3) with everything the
#     earlier layers yielded — per Ansh's scope ruling: the mechanism is
#     already pinned by the 35/35 size partition; this is one clean
#     confirmation run naming WHICH library differs (upstream-ticket
#     evidence), never a blocker for ruling gate 3.
#
# PRE-REGISTERED PREDICTIONS (unchanged from v1):
#   P1 small (20000Leagues, 320x240): arrays EQUAL, scores <= 1e-5 (the
#      measured Leagues noise floor).
#   P2 large (HouseOnBareMountain, >560px): arrays EQUAL, scores %-scale
#      (>= 1e-3) or counts change — the divergence lives INSIDE predict,
#      where the downscale runs.
#   FALSIFIER: a large-frame delta at 1e-7 scale kills the resize mechanism
#   too and forces a deeper bisect.
#
# Weights note (Task-2 risk, stated): the engine-side predict runs with
# -w /opt/rocketride/engine/cache — the WORKDIR mechanism the LI image's
# own bake-proof uses for offline checkpoint resolution; HF_HUB_OFFLINE/
# TRANSFORMERS_OFFLINE are set and any fetch attempt surfaces as a failure,
# never a silent download.
# Committed script + self-printed sha256 (entry 25). Cost ~6-10 min from
# the resumed state (no extraction, bring-up only if rr is down).
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
EPREFIX="/opt/rocketride/engine"
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

echo "== frames (RESUME: reuse if present — v1's extracts are good) =="
if [ -s "$OUT/small.png" ] && [ -s "$OUT/large.png" ]; then
  echo "reusing existing frames:"; ls -la "$OUT"/small.png "$OUT"/large.png
else
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
fi

echo "== LAYER 1 (python-free, cannot die on an interpreter) =="
echo "-- engine (rr): torch build --"
docker exec rr sh -c "SP=$EPREFIX/lib/python3.12/site-packages; \
  cat \$SP/torch/version.py 2>/dev/null || echo 'torch/version.py NOT FOUND'; \
  echo '--- torch/lib ---'; ls \$SP/torch/lib 2>/dev/null | head -24; \
  echo '--- WHEEL ---'; cat \$SP/torch-*.dist-info/WHEEL 2>/dev/null"
echo "-- li ($LI_IMAGE): torch build --"
docker run --rm --entrypoint sh "$LI_IMAGE" -c "VP=\$(find /usr/local/lib /usr/lib -maxdepth 4 -type d -name site-packages 2>/dev/null | head -1); \
  cat \$VP/torch/version.py 2>/dev/null; echo '--- torch/lib ---'; \
  ls \$VP/torch/lib 2>/dev/null | head -24; echo '--- WHEEL ---'; \
  cat \$VP/torch-*.dist-info/WHEEL 2>/dev/null"
echo "-- package versions, both (dist-info scrape) --"
docker exec rr sh -c "ls $EPREFIX/lib/python3.12/site-packages | grep -iE '^(pillow|torch|torchvision|rfdetr|numpy).*dist-info' | sort" | sed 's/^/  engine  /'
docker run --rm --entrypoint sh "$LI_IMAGE" -c "VP=\$(find /usr/local/lib /usr/lib -maxdepth 4 -type d -name site-packages 2>/dev/null | head -1); \
  ls \$VP | grep -iE '^(pillow|torch|torchvision|rfdetr|numpy).*dist-info' | sort" | sed 's/^/  li      /'
echo "-- rfdetr detr.py byte identity (same version string != same bytes) --"
docker exec rr sh -c "cat \$(find $EPREFIX -path '*rfdetr/detr.py' 2>/dev/null | head -1)" \
    > "$OUT/detr_engine.py" 2>/dev/null || echo "engine detr.py NOT FOUND under $EPREFIX"
docker run --rm --entrypoint sh "$LI_IMAGE" -c "cat \$(find /usr/local/lib /usr/lib -path '*rfdetr/detr.py' 2>/dev/null | head -1)" \
    > "$OUT/detr_li.py" 2>/dev/null || echo "li detr.py NOT FOUND"
if [ -s "$OUT/detr_engine.py" ] && [ -s "$OUT/detr_li.py" ]; then
  sha256sum "$OUT/detr_engine.py" "$OUT/detr_li.py"
  if diff -q "$OUT/detr_engine.py" "$OUT/detr_li.py" >/dev/null; then
    echo "detr.py: BYTE-IDENTICAL across containers"
  else
    echo "detr.py: DIFFERS — first 40 diff lines:"; diff "$OUT/detr_engine.py" "$OUT/detr_li.py" | head -40
  fi
fi

echo "== LAYER 2: engine interpreter by CAPABILITY (import torch, rfdetr in 90s) =="
SHEBANG="$(docker exec rr sh -c "head -1 $EPREFIX/bin/pip3 2>/dev/null | sed 's/^#!//'" || true)"
CANDIDATES="$SHEBANG $EPREFIX/engine $EPREFIX/bin/python3.12 $EPREFIX/bin/python3 \
$(docker exec rr sh -c "find $EPREFIX -maxdepth 3 -type f -name 'python3*' 2>/dev/null" | tr '\n' ' ')"
EPY=""
for cand in $CANDIDATES; do
  [ -n "$cand" ] || continue
  echo "  trying: $cand"
  if timeout 90 docker exec rr "$cand" -c 'import torch, rfdetr; print("CAP_OK")' 2>/dev/null | grep -q CAP_OK; then
    EPY="$cand"; echo "  CAPABLE: $cand"; break
  fi
done
if [ -z "$EPY" ]; then
  echo "ENGINE-SIDE PREDICT NOT OBTAINABLE STANDALONE — no candidate imported"
  echo "torch+rfdetr (tried: $CANDIDATES). Per Ansh's scope ruling: REPORT AND"
  echo "STOP — Layer 1 above carries the build identity and the detr.py diff,"
  echo "which likely name the differing library already; gate 3 rules on the"
  echo "35/35 size partition. LI side follows for its half of the record."
  docker run --rm -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
      -v "$ROOT/$PROBE:/tmp/probe_detector_parity.py:ro" \
      -v "$OUT:/data" --entrypoint python "$LI_IMAGE" \
      /tmp/probe_detector_parity.py --side li --png /data/small.png /data/large.png \
      > "$OUT/side_li.json" 2>"$OUT/side_li.err" || true
  echo "LI side written to $OUT/side_li.json (engine side ABSENT)."
  exit 3
fi

echo "== LAYER 3: side runs (one model load each) =="
docker cp "$PROBE" rr:/tmp/probe_detector_parity.py
docker cp "$OUT/small.png" rr:/tmp/small.png
docker cp "$OUT/large.png" rr:/tmp/large.png
# --side-out (2026-09-02, the Layer-3 lesson): the side doc travels as a
# FILE — the engine's embedded interpreter prints its own banner to stdout,
# which corrupted the v2 stdout capture into non-JSON.
docker exec -w "$EPREFIX/cache" -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 rr "$EPY" \
    /tmp/probe_detector_parity.py --side engine --png /tmp/small.png /tmp/large.png \
    --side-out /tmp/side_engine.json 2>"$OUT/side_engine.err"
docker cp rr:/tmp/side_engine.json "$OUT/side_engine.json"
docker run --rm -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -v "$ROOT/$PROBE:/tmp/probe_detector_parity.py:ro" \
    -v "$OUT:/data" --entrypoint python "$LI_IMAGE" \
    /tmp/probe_detector_parity.py --side li --png /data/small.png /data/large.png \
    --side-out /data/side_li.json 2>"$OUT/side_li.err"

echo "== VERDICTS (predictions above; libs identity rides them) =="
"$PYF" "$PROBE" --compare "$OUT/side_engine.json" "$OUT/side_li.json"
echo "DONE — artifacts in $OUT. Bring back: both frame verdicts with"
echo "max_sorted_delta, libs_diff, the Layer-1 build reads and the detr.py"
echo "identity line, verbatim."
