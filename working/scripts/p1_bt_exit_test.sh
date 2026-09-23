#!/usr/bin/env bash
# p1_bt_exit_test.sh — TOOLING ONLY: kill stray tooling bpftraces by pid, then time bpftrace's exit on
# SIGINT with and without a large BPFTRACE_MAP_KEYS_MAX, with a scheduler-tracepoint per-CPU map.
set -uo pipefail
echo "p1_bt_exit_test.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
for p in "$@"; do [ "$(cat /proc/$p/comm 2>/dev/null)" = bpftrace ] && sudo -n kill -9 "$p" && echo "killed stray bpftrace $p"; done
O=$(mktemp -d)
for keys in 4000000 200000 default; do
  if [ "$keys" = default ]; then sudo -n bpftrace -f json -o "$O/$keys.json" -e 'tracepoint:sched:sched_switch { @c[args->next_pid] = count(); @s[args->prev_pid] = sum(1); }' > "$O/$keys.log" 2>&1 &
  else sudo -n env BPFTRACE_MAP_KEYS_MAX=$keys bpftrace -f json -o "$O/$keys.json" -e 'tracepoint:sched:sched_switch { @c[args->next_pid] = count(); @s[args->prev_pid] = sum(1); }' > "$O/$keys.log" 2>&1 &
  fi
  sleep 6
  P=$(pgrep -f "$O/$keys.json" | while read x; do [ "$(cat /proc/$x/comm)" = bpftrace ] && echo $x; done | head -1)
  t0=$(date +%s.%N); sudo -n kill -INT "$P"
  for i in $(seq 1 600); do kill -0 "$P" 2>/dev/null || [ -d /proc/$P ] || break; sleep 0.5; done
  t1=$(date +%s.%N)
  echo "keys=$keys pid=$P exit_after_s=$(python3 -c "print(round($t1-$t0,1))") alive=$([ -d /proc/$P ] && echo yes || echo no) out_bytes=$(sudo -n wc -c < "$O/$keys.json")"
  [ -d /proc/$P ] && sudo -n kill -9 "$P"
  sleep 1
done
sudo -n rm -rf "$O"
echo "CHAIN_DONE bt_exit"
