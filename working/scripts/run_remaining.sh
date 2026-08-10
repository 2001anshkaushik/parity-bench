#!/usr/bin/env bash
# Chain steps 2-4 after the fault probe finishes. Each step is independent; a failure in one
# is logged and the chain continues, so a single bad step cannot silently drop the rest.
set -u
cd $REPO/benchmark-A
PY=../.venv/bin/python

echo "[chain] waiting for fault probe ..."
while pgrep -f fault_isolation_probe >/dev/null 2>&1; do sleep 10; done
echo "[chain] fault probe done at $(date +%H:%M:%S)"

echo "[chain] === STEP 2 deployment parity ==="
$PY -u scripts/deployment_parity.py > logs/parity.out 2>&1
echo "[chain] step2 exit=$?"

echo "[chain] === STEP 3 ceiling ==="
$PY -u scripts/ceiling_probe.py > logs/ceiling.out 2>&1
echo "[chain] step3 exit=$?"

echo "[chain] === STEP 4 operational complexity ==="
$PY -u scripts/operational_complexity.py > logs/operational.out 2>&1
echo "[chain] step4 exit=$?"

echo "[chain] ALL STEPS COMPLETE at $(date +%H:%M:%S)"
