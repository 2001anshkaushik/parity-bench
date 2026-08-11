#!/usr/bin/env bash
# Waits for the primary matched-layer run to finish, then runs the full sweep.
# They must NOT overlap: CPU contention would corrupt both arms of both runs.
cd "$(dirname "$0")"
echo "[chain] waiting for primary to finish..."
while pgrep -f 'matched_layers_run.py' >/dev/null; do sleep 30; done
echo "[chain] primary done at $(date '+%H:%M:%S'); settling 60s before the sweep"
sleep 60
echo "[chain] starting sweep C=1,2,4,8,16 docs=500 reps=3"
exec ../.venv/bin/python matched_layers_sweep.py --docs 500 --reps 3 --conc 1,2,4,8,16 --port 8802
