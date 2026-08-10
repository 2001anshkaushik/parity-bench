#!/usr/bin/env bash
# Start the RocketRide engine natively on 127.0.0.1:5565 for benchmark-A.
#
# Differences from rocketride-bench (Krish)/scripts/start_engine.sh, each deliberate:
#   * binds 127.0.0.1, never 0.0.0.0 — no reason to expose a benchmark engine to the LAN
#   * passes --port explicitly. Krish's ROCKETRIDE_PORT only reaches the health-check URL and
#     never the engine, so setting it polls one port while the engine listens on another
#   * idempotent: refuses to start a second instance on an occupied port
#   * does not copy benchmark nodes into the engine bundle — we measure the shipped engine
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE_DIR="${ENGINE_DIR:-$ROOT/engine}"
HOST=127.0.0.1
PORT="${RR_PORT:-5565}"
LOG="$ROOT/logs/engine.log"
PIDFILE="$ROOT/logs/engine.pid"

export ROCKETRIDE_URI="http://${HOST}:${PORT}"
export ROCKETRIDE_APIKEY="${ROCKETRIDE_APIKEY:-MYAPIKEY}"
# Fault-probe node knobs. Hang must outlast any client timeout we use, but not so long that
# a 5%-hang batch pins task processes for the rest of the session.
export FP_HANG_SECONDS="${FP_HANG_SECONDS:-25}"
export FP_ALLOC_MB="${FP_ALLOC_MB:-512}"
# split_embed node knobs (STEP 2/3: topology and chunk-vs-token experiments)
export SE_CHUNK_SIZE="${SE_CHUNK_SIZE:-4000}"
export SE_CHUNK_OVERLAP="${SE_CHUNK_OVERLAP:-200}"

if [ ! -x "$ENGINE_DIR/engine" ]; then
  echo "engine binary not found at $ENGINE_DIR/engine" >&2
  echo "  provision it first (see ENVIRONMENT.md for the pinned version and SHA256)" >&2
  exit 1
fi

# Idempotency. Starting a second engine on a busy port yields a process that dies or silently
# binds elsewhere, and a benchmark that unknowingly measures whichever one answered.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  existing="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t | head -1)"
  echo "port $PORT already has a listener (pid $existing) — not starting a second instance"
  ps -p "$existing" -o pid=,command= 2>/dev/null | sed 's/^/  /'
  exit 0
fi

mkdir -p "$ROOT/logs"
{
  echo "==============================================================="
  echo "start $(date -u +%Y-%m-%dT%H:%M:%SZ)  host=$HOST port=$PORT"
  echo "engine_dir=$ENGINE_DIR"
  echo "==============================================================="
} >>"$LOG"

# cwd must be the bundle root: `ai/eaas.py` is resolved relative to it.
cd "$ENGINE_DIR"
nohup ./engine ai/eaas.py --host="$HOST" --port="$PORT" >>"$LOG" 2>&1 &
ENGINE_PID=$!
echo "$ENGINE_PID" >"$PIDFILE"
echo "started pid $ENGINE_PID -> $LOG"

# Readiness uses /version, not /ping. /ping requires auth and answers 401, which proves only that
# *something* is bound to the port; /version is unauthenticated, returns 200, and carries the
# running build's version and hash — so readiness and identity are established in one call.
#
# The obvious spelling of this check is wrong, and wrong in the dangerous direction. With
# `curl ... -w '%{http_code}' || echo 000`, a refused connection makes curl print `000` *and*
# exit 7, so the `||` fires and appends a second `000` — the variable holds `000000`, compares
# unequal to `000`, and the script reports a healthy engine that is not listening at all. Assign
# the fallback instead of appending it.
#
# First launch is slow: the engine bootstraps its embedded Python (pip, wheel, setuptools, uv,
# constraint compilation) before it binds. Observed well past the 60 s a warm start needs, so the
# default deadline is generous and progress is printed rather than leaving the caller guessing.
DEADLINE="${RR_START_TIMEOUT:-900}"
started_at=$(date +%s)
last_note=0
while :; do
  now=$(date +%s); elapsed=$((now - started_at))
  if [ "$elapsed" -ge "$DEADLINE" ]; then
    echo "engine did not answer on ${HOST}:${PORT} within ${DEADLINE}s; see $LOG" >&2
    exit 1
  fi
  if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "engine process exited during startup; last log lines:" >&2
    tail -20 "$LOG" >&2
    rm -f "$PIDFILE"
    exit 1
  fi
  code="$(curl -s -o /tmp/rr_version_probe.$$ -w '%{http_code}' "http://${HOST}:${PORT}/version" 2>/dev/null)" || code="000"
  if [ "$code" = "200" ]; then
    echo "engine healthy on ${HOST}:${PORT} (HTTP $code, pid $ENGINE_PID, ${elapsed}s)"
    echo "  running: $(cat /tmp/rr_version_probe.$$ 2>/dev/null)"
    rm -f /tmp/rr_version_probe.$$
    ./engine --version 2>&1 | head -1
    exit 0
  fi
  rm -f /tmp/rr_version_probe.$$
  if [ $((elapsed - last_note)) -ge 30 ]; then
    last_note=$elapsed
    echo "  ... still bootstrapping (${elapsed}s): $(tail -1 "$LOG" 2>/dev/null | tr -d '\r')"
  fi
  sleep 1
done
