#!/usr/bin/env bash
# Read the RESOLVED dependency pins out of the built rr image's constraints
# cache and write the subset the LlamaIndex arm must match. The engine's
# requirements are unpinned for rfdetr/torch/etc — resolution freezes at image
# build (bootcheck constraints compile), so the image is the only truth.
# Current-PyPI hazard this guards: rfdetr>=1.9 requires transformers>=5.1
# while the engine pins transformers==4.53.3 — the compile must have
# backtracked rfdetr, and WHICH version it chose is unknowable from source.
#
# Run AFTER `docker build ... -t rr:patched .` and BEFORE building the LI
# video image. Exits non-zero if any required pin is absent.
set -euo pipefail

IMAGE="${1:-rr:patched}"
OUT="${2:-$(dirname "$0")/engine_pins.txt}"
CONSTRAINTS_PATH=/opt/rocketride/engine/cache/constraints.txt

# The entrypoint execs non-"serve" argv verbatim (rocketride-entrypoint.sh).
if ! docker run --rm "$IMAGE" cat "$CONSTRAINTS_PATH" > /tmp/rr_constraints.txt 2>/dev/null; then
  echo "NOT DONE — cannot read $CONSTRAINTS_PATH from $IMAGE."
  echo "Either the image is not built, or it was built with RR_BOOT_CHECK=0 (empty cache)."
  exit 1
fi

REQUIRED="rfdetr torch torchvision transformers supervision timm pillow numpy imageio-ffmpeg sentence-transformers"
{
  echo "# Resolved pins read from $IMAGE:$CONSTRAINTS_PATH on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# by extract_engine_pins.sh — the LlamaIndex video image installs exactly these."
} > "$OUT"

MISSING=""
for pkg in $REQUIRED; do
  # constraints.txt lines look like 'name==version' (uv compile output).
  line=$(grep -i -E "^${pkg}==" /tmp/rr_constraints.txt | head -1 || true)
  if [ -n "$line" ]; then
    echo "$line" >> "$OUT"
  else
    MISSING="$MISSING $pkg"
  fi
done
rm -f /tmp/rr_constraints.txt

if [ -n "$MISSING" ]; then
  echo "NOT DONE — pins absent from the image's constraints:$MISSING"
  echo "(a package the engine never references, e.g. sentence-transformers IS referenced"
  echo " via requirements_sentence_transformers.txt — absence means the compile changed shape;"
  echo " read the full constraints file before proceeding)"
  exit 1
fi

echo "DONE — pins written to $OUT:"
cat "$OUT"
