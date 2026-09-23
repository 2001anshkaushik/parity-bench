#!/usr/bin/env bash
# p1_tooling_test.sh — TOOLING ONLY (no measurement): attach P1-A's tracer for a few seconds to an
# idle LlamaIndex worker and to the RocketRide engine server, and the memory sampler to both, to prove
# the bpftrace script parses and resolves its symbols on each arm. Writes under <out_dir>.
#   bash working/scripts/p1_tooling_test.sh <out_dir_abs>
set -uo pipefail
echo "p1_tooling_test.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
O="$1"; mkdir -p "$O"; cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"
for c in rr li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: $c present"; exit 3; }; done
trap 'docker rm -f rr li_bal_0 >/dev/null 2>&1' EXIT
docker run -d --name li_bal_0 --memory 7g --network host --entrypoint sh li:video -c "exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --log-level warning" >/dev/null
docker run -d --name rr --memory 58g --network host rr:patched-video >/dev/null
sleep 25
for arm in li rr; do
  C=li_bal_0; [ "$arm" = rr ] && C=rr
  L="$O/$arm"; mkdir -p "$L"
  PID=$(docker inspect -f '{{.State.Pid}}' "$C")
  "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
  MP=$!
  touch "$L/.warm_done"
  "$PY" working/harness/p1_tracer.py --arm "$arm" --container "$C" --leg-dir "$L" --leg "tool_$arm" --pid "$PID" > "$L/tracer_stdout.txt" 2>&1 &
  TP=$!
  for i in $(seq 1 120); do [ -f "$L/.tracer_ready" ] && break; sleep 1; done
  echo "$arm ready after ${i}s: $(cat "$L/.tracer_ready" 2>/dev/null | head -c 80)"
  sleep 8; touch "$L/.window_closed"; wait "$TP"; echo "$arm tracer rc=$?"; touch "$L/.leg_done"; wait "$MP"
  cat "$L/tracer_stdout.txt"; tail -c 400 "$L"/e2trace_*.log; echo; ls -la "$L"; head -c 300 "$L/memstat.jsonl.summary.json"; echo
done
echo "CHAIN_DONE tooling"
