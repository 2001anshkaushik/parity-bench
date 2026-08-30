#!/usr/bin/env bash
# =============================================================================
# RULING L box application (2026-08-30): rebuild li:video at the 4000/0
# splitter config and PROVE it took effect — read-backs, never assertions
# (register entry 1: a chunk config was once accepted and silently discarded
# downstream of everything traced; entry 12: a value that sets a run
# parameter has a read-back before it is quotable).
#
# Run AFTER `git pull --ff-only` (its own command, never chained — standing
# rule) and BEFORE run_films_posture.sh (Ansh: the splitter change lands
# before the posture sweep, never between passes — chunk config changes the
# workload, so every posture number must be measured on the config the legs
# will use).
#
# What it does:
#   1. guards: clean tracked tree (the build context bakes li_video source),
#      Dockerfile at this HEAD carries WS1V_CHUNK_OVERLAP=0;
#   2. docker build li:video (SESSION_STATE.md:1342 form; freeze-pin layers
#      stay cached — only the COPY of li_video, the offline-proof RUN and
#      the metadata layers rebuild);
#   3. read-back 1: image Config.Env carries WS1V_CHUNK_OVERLAP=0 and no 200;
#   4. read-back 2: verify_li_chunk_config.py INSIDE the image (--network
#      none): env parse + realized zero-seam split + overlap-200 null control.
# li:video-anchor is DELIBERATELY untouched (banked-comparable, 4000/200 era).
# The sweep probe additionally refuses any LI point whose /health does not
# read back 4000/0/chars, so a stale image cannot measure a posture.
#
# Committed script + self-printed sha256 per register entry 25. No git writes
# happen here — nothing to bundle; entry 26 does not trigger.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_ruling_l_box.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"
# STOP: the operator compares BOTH lines against the laptop-printed values
# before anything below runs (entry 26 addendum: a stale HEAD is a different
# instrument wearing the same command line).

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --porcelain --untracked-files=no
  echo "NOT DONE — tracked files are modified on the box; the build context"
  echo "would bake unreviewed bytes into li:video."
  exit 1
fi
if ! grep -q 'WS1V_CHUNK_OVERLAP=0' docker/Dockerfile.llamaindex-video; then
  echo "NOT DONE — Dockerfile at this HEAD does not carry WS1V_CHUNK_OVERLAP=0"
  echo "(stale HEAD? git pull --ff-only first, as its own command)."
  exit 1
fi

echo "== building li:video (freeze-pin layers cached; COPY+proof+meta rebuild) =="
docker build -f docker/Dockerfile.llamaindex-video -t li:video .

echo "== read-back 1: image Config.Env =="
ENVJSON="$(docker inspect --format '{{json .Config.Env}}' li:video)"
echo "$ENVJSON"
if ! printf '%s' "$ENVJSON" | grep -q '"WS1V_CHUNK_OVERLAP=0"'; then
  echo "NOT DONE — image env lacks WS1V_CHUNK_OVERLAP=0."
  exit 1
fi
if printf '%s' "$ENVJSON" | grep -q 'WS1V_CHUNK_OVERLAP=200'; then
  echo "NOT DONE — image env still carries WS1V_CHUNK_OVERLAP=200."
  exit 1
fi
echo "read-back 1 OK: Config.Env carries WS1V_CHUNK_OVERLAP=0 (and no 200)"

echo "== read-back 2: in-container parse + realization + null control =="
docker run --rm --network none \
  -v "$ROOT/working/video/probe/verify_li_chunk_config.py:/tmp/verify_li_chunk_config.py:ro" \
  --entrypoint python li:video /tmp/verify_li_chunk_config.py

echo "RULING L APPLIED AND READ BACK on this box."
echo "li:video-anchor untouched (4000/200 era, banked-comparable)."
echo "Next: run_films_posture.sh — its probe refuses any LI point whose"
echo "/health does not read back 4000/0/chars, so this rebuild is load-bearing."
