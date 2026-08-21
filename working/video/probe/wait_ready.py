#!/usr/bin/env python3
"""Container readiness — ONE helper for every container start (Crossroad 22 /
instance seven, 2026-08-21).

THE INCIDENT: the bake's wait loops used socket.create_connection to 5565.
That predicate was MEASURED meaningful in Phase 1 — under --network host,
where a TCP accept could only come from the engine. The video tree started
containers with -p 5565:5565, where docker-proxy binds the published port the
instant `docker run` returns: the same line kept passing while measuring the
FORWARDER's readiness, not the engine's ("stream ends after 0 bytes, before
end of line"). A measurement is bound to the conditions it was taken under;
when the condition (network mode) moved, it silently became an assumption
again. Register entry 3.

Rules shipped here:

* Readiness is measured on the THING NEEDED, never a proxy (ruling
  2026-08-21): RR = a real SDK connect() in a retry loop with a deadline;
  LI = /health returning 200 + parseable JSON (optionally warm_workers == W).
  Each RR attempt is bounded by asyncio.wait_for in seconds WE control — the
  SDK timeout argument's unit is unmeasured (Phase 1 passed 60000 and only
  ever exercised the success path), so it must not be the deadline mechanism.

* Crossroad 22: both arms run --network host (docker-proxy inserts a
  userspace hop into every message and latency is a measured quantity; and a
  silent deviation from Phase 1 section C's configuration breaks cross-phase
  comparability for no gain). assert_host_network() reads the mode back and
  refuses anything else — the mode is a recorded value, never an implicit
  flag. Arms run one at a time, so host networking cannot collide ports.

Used by: bake_rr_video.sh, run_plan.sh, probe_run.sh (CLI), and
probe_concurrency.py, probe_li_workers.py (import). Importing this module
needs stdlib only; rocketride loads lazily inside wait_rr_ready (both venv
contracts pin 1.3.0).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request


def _docker(args: list, timeout: int = 30) -> str:
    try:
        return subprocess.run(['docker', *args], capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception as exc:  # noqa: BLE001 — reported, never masks
        return f'<failed: {exc!r}>'


def _log_tail(container: str, n: int = 40) -> str:
    try:
        r = subprocess.run(['docker', 'logs', '--tail', str(n), container],
                           capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr)[-4000:]
    except Exception as exc:  # noqa: BLE001
        return f'<docker logs failed: {exc!r}>'


def assert_host_network(container: str) -> str:
    """Read back the container's network mode; refuse anything but host."""
    mode = _docker(['inspect', '-f', '{{.HostConfig.NetworkMode}}', container])
    if mode != 'host':
        raise RuntimeError(
            f"NOT DONE — {container}: NetworkMode={mode!r}, not 'host'. Crossroad 22 "
            "rules --network host on both arms: docker-proxy adds a userspace hop to "
            "measured latency, and it silently invalidates TCP readiness checks "
            "(instance seven).")
    return mode


async def wait_rr_ready(port: int = 5565, deadline_s: float = 1800,
                        interval_s: float = 5.0, attempt_timeout_s: float = 20.0,
                        container: str | None = None) -> dict:
    """Real SDK connect() in a retry loop — readiness for SDK traffic, measured
    as SDK traffic. Raises RuntimeError (with a container log tail when the
    name is given) if the deadline passes."""
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    try:
        from rocketride import RocketRideClient
    except ImportError as exc:
        raise RuntimeError(
            f'NOT DONE — wait_ready --arm rr needs the rocketride SDK, not importable '
            f'in this interpreter ({sys.executable}). Run under a venv with '
            f'rocketride==1.3.0 (~/.venv or ~/.venv-floor).') from exc
    t0 = time.monotonic()
    attempts, last = 0, None
    while time.monotonic() - t0 < deadline_s:
        attempts += 1
        client = RocketRideClient()
        try:
            await asyncio.wait_for(client.connect(timeout=60000),
                                   timeout=attempt_timeout_s)
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 — readiness proven by the connect
                pass
            return {'ready': True, 'arm': 'rr', 'port': port,
                    'wall_s': round(time.monotonic() - t0, 1), 'attempts': attempts}
        except Exception as exc:  # noqa: BLE001 — retried until deadline
            last = repr(exc)
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(interval_s)
    tail = _log_tail(container) if container else None
    raise RuntimeError(
        f'NOT DONE — engine never became SDK-connectable on 127.0.0.1:{port} within '
        f'{deadline_s:.0f}s ({attempts} attempts; last: {last})'
        + (f'\ncontainer log tail ({container}):\n{tail}' if tail else ''))


def wait_li_ready(port: int = 8802, deadline_s: float = 600, interval_s: float = 5.0,
                  workers: int | None = None, container: str | None = None) -> dict:
    """/health returning 200 + JSON; with workers=N, additionally requires
    warm_workers == N and warm (probe_li_workers' original predicate, kept)."""
    t0 = time.monotonic()
    attempts, last = 0, None
    while time.monotonic() - t0 < deadline_s:
        attempts += 1
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',
                                        timeout=10) as resp:
                h = json.load(resp)
            if workers is None or (h.get('warm_workers') == workers and h.get('warm')):
                return {'ready': True, 'arm': 'li', 'port': port,
                        'wall_s': round(time.monotonic() - t0, 1),
                        'attempts': attempts,
                        'warm_workers': h.get('warm_workers'), 'pid': h.get('pid')}
            last = f'health up but warm_workers={h.get("warm_workers")} != {workers}'
        except Exception as exc:  # noqa: BLE001 — retried until deadline
            last = repr(exc)
        time.sleep(interval_s)
    tail = _log_tail(container) if container else None
    raise RuntimeError(
        f'NOT DONE — LI service never became ready on 127.0.0.1:{port} within '
        f'{deadline_s:.0f}s ({attempts} attempts; last: {last})'
        + (f'\ncontainer log tail ({container}):\n{tail}' if tail else ''))


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Readiness = the real predicate (SDK connect / health JSON), '
                    'never TCP. With --container, first read back NetworkMode and '
                    'refuse anything but host (Crossroad 22).')
    ap.add_argument('--arm', choices=['rr', 'li'], required=True)
    ap.add_argument('--port', type=int, default=None,
                    help='default: 5565 (rr) / 8802 (li)')
    ap.add_argument('--deadline', type=float, default=None,
                    help='seconds; default: 1800 (rr) / 600 (li)')
    ap.add_argument('--workers', type=int, default=None,
                    help='li only: require warm_workers == N (not just liveness)')
    ap.add_argument('--container', default=None,
                    help='enables the host-network read-back and a log tail on failure')
    args = ap.parse_args()
    out: dict = {}
    try:
        if args.container:
            out['network_mode'] = assert_host_network(args.container)
        if args.arm == 'rr':
            out |= asyncio.run(wait_rr_ready(
                port=args.port or 5565, deadline_s=args.deadline or 1800,
                container=args.container))
        else:
            out |= wait_li_ready(
                port=args.port or 8802, deadline_s=args.deadline or 600,
                workers=args.workers, container=args.container)
    except RuntimeError as exc:
        print(exc)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
