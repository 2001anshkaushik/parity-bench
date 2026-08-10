#!/usr/bin/env bash
# Stop only the engine this suite started, identified by pidfile.
#
# PID reuse is a real hazard on a long-lived dev machine: a stale pidfile plus an unlucky wrap
# means `kill $(cat pidfile)` terminates an unrelated process. So the recorded PID is verified to
# still *be* the engine before any signal is sent. Nothing is killed by port or by name — a
# developer's own engine on 5565 is not ours to stop.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIDFILE="$ROOT/logs/engine.pid"
LOG="$ROOT/logs/engine.log"

if [ ! -f "$PIDFILE" ]; then
  echo "no pidfile at $PIDFILE — nothing started by this suite is running"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if ! kill -0 "$PID" 2>/dev/null; then
  echo "pid $PID is not alive; removing stale pidfile"
  rm -f "$PIDFILE"
  exit 0
fi

CMD="$(ps -p "$PID" -o command= 2>/dev/null || true)"
case "$CMD" in
  *engine*eaas.py*)
    ;;
  *)
    echo "pid $PID is alive but does not look like our engine — refusing to kill it." >&2
    echo "  command: $CMD" >&2
    echo "  (PID reuse: remove $PIDFILE by hand if you are sure)" >&2
    exit 1
    ;;
esac

# Per-task node.py children are reparented on the engine's exit; report any that outlive it
# rather than killing processes we did not directly start.
CHILDREN="$(pgrep -P "$PID" 2>/dev/null | tr '\n' ' ' || true)"

echo "stopping engine pid $PID"
kill -TERM "$PID" 2>/dev/null || true
for _ in $(seq 1 40); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.25
done

if kill -0 "$PID" 2>/dev/null; then
  echo "did not exit on SIGTERM after 10s; sending SIGKILL"
  kill -KILL "$PID" 2>/dev/null || true
  sleep 0.5
fi

rm -f "$PIDFILE"
echo "stopped. log: $LOG"

if [ -n "${CHILDREN// /}" ]; then
  for c in $CHILDREN; do
    if kill -0 "$c" 2>/dev/null; then
      echo "NOTE: child pid $c outlived the engine: $(ps -p "$c" -o command= 2>/dev/null)"
    fi
  done
fi
