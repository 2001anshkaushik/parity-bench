#!/usr/bin/env bash
# WS-1 LlamaIndex service launcher. Tuning follows uvicorn's own deployment docs; a hobbled
# baseline is the strawman failure mode and this is OUR framework in the parity study, so any
# shortcut here biases the result against LlamaIndex.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${WS1_PORT:-8801}"
WORKERS="${WS1_WORKERS:-14}"     # one per logical core (14 on M4 Pro), per uvicorn deployment docs
# ROOT is working/, so the venv — which lives one level ABOVE the clone (PROVISIONING.md §4) — is
# $ROOT/../../.venv, not $ROOT/../.venv. The latter was correct when ws1/ sat at the clone root and
# silently stopped resolving when the tree was restructured into working/; the service then died at
# launch with "No such file or directory" for every caller, since nothing sets WS1_PYTHON.
PY="${WS1_PYTHON:-$ROOT/../../.venv/bin/python}"
[ -x "$PY" ] || { echo "run_service.sh: interpreter not found at $PY (set WS1_PYTHON to override)" >&2; exit 127; }
export WS1_DEVICE="${WS1_DEVICE:-cpu}"

cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export WS1_WORKERS="$WORKERS"
export TOKENIZERS_PARALLELISM=false
# Each worker is its own process; letting torch/BLAS start one thread per core INSIDE each of 14
# workers would create ~200 threads and measure thread thrash rather than the service.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"

exec "$PY" -m uvicorn ws1.service:app \
  --host 127.0.0.1 --port "$PORT" \
  --workers "$WORKERS" \
  --loop uvloop \
  --http httptools \
  --no-access-log \
  --log-level warning \
  --timeout-keep-alive 30
