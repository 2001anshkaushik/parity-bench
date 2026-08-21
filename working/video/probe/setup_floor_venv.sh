#!/usr/bin/env bash
# =============================================================================
# FLOOR VENV — a SEPARATE environment at ~/.venv-floor, pinned to the rr
# image's own constraint resolutions. Why separate, not additive:
#
#   * The engine's constraints pin torch 2.10.0 (the version read back from
#     Phase 1 task processes); the host ~/.venv carries torch 2.13.0+cpu and
#     llama_index for Phase 1 work. An additive install under the engine pins
#     would DOWNGRADE ~/.venv's torch — exactly the silent movement we must
#     not make. A separate venv satisfies both constraints at once:
#     ~/.venv untouched, floor bit-matched to the container arm.
#   * The floor's comparability claim IS the pin set: rfdetr / torch /
#     torchvision / transformers / supervision / timm / imageio-ffmpeg /
#     sentence-transformers at the versions the engine resolved at image
#     build — never what PyPI resolves today.
#
# Prereq: working/video/li_video/engine_pins.txt exists (extract_engine_pins.sh
# against the built rr:patched). This script REFUSES to run without it.
# Adds on top of the pins: rocketride==1.3.0 (the image's own SDK pin) and
# psutil pinned to ~/.venv's version (collector parity with Phase 1 sampling).
#
# Read-backs at the end prove: floor versions == pins; ~/.venv torch UNMOVED.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root

PINS="working/video/li_video/engine_pins.txt"
FLOOR="${FLOOR_VENV:-$HOME/.venv-floor}"
BASE="${BASE_VENV:-$HOME/.venv}"

[ -f "$PINS" ] || { echo "NOT DONE — $PINS missing. Run: bash working/video/li_video/extract_engine_pins.sh rr:patched"; exit 1; }
[ -x "$BASE/bin/python" ] || { echo "NOT DONE — $BASE not found (needed only to read its psutil/torch versions)"; exit 1; }

BASE_TORCH_BEFORE=$("$BASE/bin/python" -c "import torch; print(torch.__version__)")
PSUTIL_PIN=$("$BASE/bin/python" -c "import psutil; print(psutil.__version__)")
echo "base venv before: torch=$BASE_TORCH_BEFORE psutil=$PSUTIL_PIN (must be unchanged after)"

python3 -m venv "$FLOOR"
"$FLOOR/bin/pip" install --quiet --upgrade pip
echo "installing engine pins (expect a multi-GB torch wheel; this is the point):"
grep -v '^#' "$PINS"
"$FLOOR/bin/pip" install -r "$PINS"
"$FLOOR/bin/pip" install "rocketride==1.3.0" "psutil==$PSUTIL_PIN" "langchain-text-splitters"

echo "== read-back: floor venv versions vs pins =="
"$FLOOR/bin/python" - "$PINS" <<'EOF'
import sys
from importlib.metadata import version, PackageNotFoundError
pins = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith('#') and '==' in line:
        name, ver = line.split('==')
        pins[name.strip().lower()] = ver.strip()
bad = []
for name, want in pins.items():
    try:
        got = version(name)
    except PackageNotFoundError:
        got = None
    status = 'OK' if got == want else 'MISMATCH'
    if got != want:
        bad.append(name)
    print(f'  {name}: pinned {want} installed {got} {status}')
for extra in ('rocketride', 'psutil', 'langchain-text-splitters'):
    print(f'  {extra}: {version(extra)}')
assert sys.prefix != sys.base_prefix, 'not running inside a venv?'
print(f'  interpreter: {sys.executable} (venv=True)')
raise SystemExit(1 if bad else 0)
EOF

echo "== read-back: base venv UNMOVED =="
BASE_TORCH_AFTER=$("$BASE/bin/python" -c "import torch; print(torch.__version__)")
"$BASE/bin/python" -c "import llama_index" 2>/dev/null && echo "  llama_index importable: yes"
if [ "$BASE_TORCH_BEFORE" != "$BASE_TORCH_AFTER" ]; then
  echo "NOT DONE — base venv torch MOVED: $BASE_TORCH_BEFORE -> $BASE_TORCH_AFTER"; exit 1
fi
echo "  torch: $BASE_TORCH_AFTER (unchanged)"
echo "DONE — floor venv at $FLOOR, pinned to the engine's resolutions; base venv untouched."
