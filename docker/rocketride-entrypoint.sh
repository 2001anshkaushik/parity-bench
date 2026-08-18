#!/bin/sh
# serve    -> boot the engine in the foreground (default)
# <other>  -> exec verbatim, for in-container debugging
set -eu
case "${1:-serve}" in
  serve)
    # --host is EXPLICIT. Without it the engine binds its default interface, which inside a
    # container is not reachable through Docker's published-port proxy — the "WebSocket upgrade
    # rejected through the published-port proxy" symptom Leela recorded, root-caused as this
    # missing flag and not a product defect. Her proven entrypoint carries it (and credits our
    # own runbook-era image for it); this file closes the loop back into our recipe.
    echo "[entrypoint] RocketRide engine on ${RR_HOST:-0.0.0.0}:${RR_PORT:-5565}"
    # exec from the engine's own directory so $ORIGIN RUNPATHs resolve; exec keeps the engine
    # as PID 1 so SIGTERM reaches it and `docker stop` is clean, not a 10 s kill.
    cd /opt/rocketride/engine
    exec ./engine ai/eaas.py --host="${RR_HOST:-0.0.0.0}" --port="${RR_PORT:-5565}"
    ;;
  *)
    exec "$@"
    ;;
esac
