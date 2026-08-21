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

# -----------------------------------------------------------------------------
# VENV CREATOR RESOLUTION — the creator is a RECORDED CHOICE, not an implicit
# default. The box's system python3 is 3.10 with ensurepip stripped (Debian
# packaging), so bare `python3 -m venv` fails there; "the venv creator" was an
# unbound environment assumption, the same class as "the interpreter". Order:
#   1. uv            — what the engine itself uses; no ensurepip; can pin 3.12
#   2. ~/.venv's own base interpreter (pyvenv.cfg) — 3.12 by construction,
#      if it still exists and carries ensurepip
#   3. virtualenv    — bundles pip, no ensurepip needed
#   4. apt           — printed as an INSTRUCTION for the operator, never run here
# Python-version preference: 3.12, matching BOTH arms (engine bundles 3.12,
# the LI image pins 3.12-slim). A floor on a different minor is tolerated but
# DECLARED — recorded below and in every floor output via sys.version.
# -----------------------------------------------------------------------------
if [ -e "$FLOOR" ]; then
  echo "note: $FLOOR exists (possibly a half-made venv from a failed run) — recreating"
  rm -rf "$FLOOR"
fi

CREATOR=""
CREATOR_DETAIL=""
if command -v uv >/dev/null 2>&1; then
  if uv venv --seed --python 3.12 "$FLOOR" 2>/tmp/uv_err; then
    CREATOR="uv"; CREATOR_DETAIL="uv $(uv --version 2>/dev/null | head -1), --python 3.12 --seed"
  elif uv venv --seed "$FLOOR" 2>>/tmp/uv_err; then
    CREATOR="uv"; CREATOR_DETAIL="uv $(uv --version 2>/dev/null | head -1), default interpreter (3.12 fetch unavailable: $(tail -1 /tmp/uv_err))"
  fi
fi
if [ -z "$CREATOR" ] && [ -f "$BASE/pyvenv.cfg" ]; then
  BASE_INTERP=$(awk -F' = ' '/^executable/ {print $2}' "$BASE/pyvenv.cfg")
  [ -n "$BASE_INTERP" ] || BASE_INTERP="$(awk -F' = ' '/^home/ {print $2}' "$BASE/pyvenv.cfg")/python3"
  if [ -x "$BASE_INTERP" ] && "$BASE_INTERP" -c "import ensurepip" 2>/dev/null; then
    "$BASE_INTERP" -m venv "$FLOOR"
    CREATOR="base-interpreter"; CREATOR_DETAIL="$BASE_INTERP ($("$BASE_INTERP" -c 'import sys; print(sys.version.split()[0])'))"
  fi
fi
if [ -z "$CREATOR" ] && command -v virtualenv >/dev/null 2>&1; then
  VENV_PY=""
  command -v python3.12 >/dev/null 2>&1 && VENV_PY="-p python3.12"
  # shellcheck disable=SC2086
  virtualenv $VENV_PY "$FLOOR"
  CREATOR="virtualenv"; CREATOR_DETAIL="virtualenv $(virtualenv --version 2>/dev/null | head -1)${VENV_PY:+ with $VENV_PY}"
fi
if [ -z "$CREATOR" ]; then
  echo "NOT DONE — no venv creator available: uv absent, $BASE/pyvenv.cfg interpreter"
  echo "missing or without ensurepip, virtualenv absent. OPERATOR INSTRUCTION"
  echo "(last resort, not executed by this script):"
  echo "    sudo apt install python3.12-venv    # or python3.10-venv for the system 3.10"
  echo "then re-run this script."
  exit 1
fi
echo "venv creator: $CREATOR ($CREATOR_DETAIL)"

# Guarantee pip regardless of creator (uv --seed and virtualenv provide it;
# a bare venv from route 2 provides it via ensurepip having been verified).
if ! [ -x "$FLOOR/bin/pip" ]; then
  "$FLOOR/bin/python" -m ensurepip --upgrade 2>/dev/null || {
    echo "NOT DONE — venv created by $CREATOR has no pip and ensurepip failed"; exit 1; }
fi
"$FLOOR/bin/pip" install --quiet --upgrade pip
FLOOR_PYVER=$("$FLOOR/bin/python" -c "import sys; print(sys.version.split()[0])")
echo "floor python: $FLOOR_PYVER (arms are both 3.12; a differing floor minor is tolerated but declared)"
echo "installing engine pins (expect a multi-GB torch wheel; this is the point):"
grep -v '^#' "$PINS"
# torch/torchvision pin LOCAL versions (+cu128) which plain PyPI does not host;
# the PyTorch CUDA index supplies them and --extra-index-url lets everything
# else resolve from PyPI at the same pinned versions in one pass.
"$FLOOR/bin/pip" install -r "$PINS" --extra-index-url https://download.pytorch.org/whl/cu128
"$FLOOR/bin/pip" install "rocketride==1.3.0" "psutil==$PSUTIL_PIN"
# langchain-text-splitters normally arrives pinned via engine_pins.txt; if an
# older pins file predates its addition to the REQUIRED list, install the
# box-extracted pin (1.1.2, 2026-08-21) rather than whatever PyPI resolves.
"$FLOOR/bin/python" -c "import langchain_text_splitters" 2>/dev/null || \
  "$FLOOR/bin/pip" install "langchain-text-splitters==1.1.2"

echo "== read-back: floor venv versions vs pins =="
"$FLOOR/bin/python" - "$PINS" "$CREATOR" "$CREATOR_DETAIL" <<'EOF'
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
print(f'  interpreter: {sys.executable} (venv=True, python {sys.version.split()[0]})')
print(f'  venv_creator: {sys.argv[2]} ({sys.argv[3]})')
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
