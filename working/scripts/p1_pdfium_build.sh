#!/usr/bin/env bash
# p1_pdfium_build.sh — build rr:p1-pdfium FROM rr:p1-tikafix (P1-C). Neither base is modified.
#
#   bash working/scripts/p1_pdfium_build.sh <campaign_dir_abs>
#
# Adds: the two prototype parse nodes generated from working/nodes/p1_pdfium_src (pdfium_pure,
# pdfium_hybrid), and pypdfium2 5.13.0 + pypdfium2_raw copied from ~/p0venv (the wheel H6 used; no
# download) into the engine's own site-packages. Checks inside the built image with the engine's
# Python: import, version, one corpus PDF parsed, both node modules import with the right variant.
set -uo pipefail
echo "p1_pdfium_build.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
D="$1"; cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"; PV="$HOME/p0venv/lib/python3.12/site-packages"
docker image inspect rr:p1-pdfium >/dev/null 2>&1 && { echo "REFUSED: rr:p1-pdfium exists (never overwritten)"; exit 3; }
docker image inspect rr:p1-tikafix >/dev/null 2>&1 || { echo "REFUSED: rr:p1-tikafix absent"; exit 3; }
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix; do echo "$i $(docker image inspect -f '{{.Id}}' "$i")"; done; }
BEFORE="$(ids)"; echo "images before:"; echo "$BEFORE"
SITE="$(docker run --rm --entrypoint sh rr:p1-tikafix -c 'ls -d /opt/rocketride/engine/lib/python3.12/site-packages')" || exit 4
echo "engine site-packages: $SITE"
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
mkdir -p "$B/nodes" "$B/site"
"$PY" working/nodes/p1_pdfium_src/gen.py "$B/nodes" || exit 5
cp -R "$PV/pypdfium2" "$PV/pypdfium2_raw" "$B/site/" || exit 5
cp -R "$PV"/pypdfium2-5.13.0.dist-info "$B/site/" 2>/dev/null || { echo "REFUSED: pypdfium2 5.13.0 dist-info absent in ~/p0venv"; exit 5; }
cp -R "$PV"/pypdfium2_raw-*.dist-info "$B/site/" 2>/dev/null || true
cp working/nodes/p1_pdfium_src/check_in_image.py "$B/"
printf 'FROM rr:p1-tikafix\nCOPY nodes/pdfium_pure /opt/rocketride/engine/nodes/pdfium_pure\nCOPY nodes/pdfium_hybrid /opt/rocketride/engine/nodes/pdfium_hybrid\nCOPY site/ %s/\nCOPY check_in_image.py /opt/rocketride/p1_check_in_image.py\n' "$SITE" > "$B/Dockerfile"
docker build -q -t rr:p1-pdfium "$B" || exit 6
AFTER="$(ids)"; echo "images after:"; echo "$AFTER"
[ "$BEFORE" = "$AFTER" ] || { echo "!! A BASE IMAGE ID CHANGED"; exit 7; }
CORPUS="$HOME/parity-bench/corpus/govdocs1/pdfs"
CHECK="$(docker run --rm -v "$CORPUS:/corpus:ro" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine rr:p1-pdfium /opt/rocketride/p1_check_in_image.py /corpus/002_002489.pdf 2>&1 | grep P1_PDFIUM_CHECK)"
echo "$CHECK"
[ -n "$CHECK" ] || { echo "!! in-image check produced nothing"; exit 8; }
"$PY" - "$D/p1c_build.json" "$(docker image inspect -f '{{.Id}}' rr:p1-pdfium)" "$BEFORE" "$CHECK" "$SITE" <<'PYREC'
import json, sys, time
json.dump({"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "image": "rr:p1-pdfium",
           "image_id": sys.argv[2], "from": "rr:p1-tikafix", "base_ids_before_and_after": sys.argv[3].splitlines(),
           "engine_site_packages": sys.argv[5],
           "in_image_check": json.loads(sys.argv[4].split("P1_PDFIUM_CHECK ", 1)[1])}, open(sys.argv[1], "x"), indent=1)
print(open(sys.argv[1]).read())
PYREC
echo "CHAIN_DONE pdfium_build"
