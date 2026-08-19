#!/usr/bin/env python3
"""Leela's "connection acceptance ceiling": the mechanism is in the engine source, and every
number he reported falls out of one constant. This probe exists to CONFIRM OR REFUTE that
reading on a live engine — the predictions below are falsifiable and stated before any run.

THE SOURCE (rocketride-server, verified at tag server-v3.3.1, constants.py:69,
task_server.py — identical at HEAD):

    CONST_MAX_UNAUTHED_CONNS_PER_IP = 10
    ...
    # Accept WebSocket without auth on upgrade; first DAP message must be auth
    if client_ip and current_unauthed >= CONST_MAX_UNAUTHED_CONNS_PER_IP:
        await websocket.close(code=1008)   # Policy Violation
        return

Auth happens on the FIRST DAP MESSAGE, not the upgrade, so every connection holds an
"unauthenticated slot" from upgrade until its auth message; the slot frees on successful auth
(release_unauthed_slot) or disconnect. It is an anti-DoS cap, per client IP — and behind
docker-proxy or a bench-client container, EVERYTHING shares one IP.

WHY THIS REPRODUCES LEELA'S NUMBERS EXACTLY. His pool builder connects a main client (which
authenticates, freeing its slot), then gathers pool_size-1 extra connects SIMULTANEOUSLY:
  offered 12  -> 11 extras burst -> 10 admitted + 1 refused -> "pool: 11 clients (1 failed)"
  offered 128 -> 127 extras burst -> 10 admitted, 117 refused -> "accepted 11, refused 117"
  offered 200 -> same 11.  Independent of threads/cores — it is a security constant.

PREDICTIONS this probe tests (any failure kills the hypothesis):
  P1  bare sockets, SEQUENTIAL, never authenticating: exactly 10 hold; the 11th is refused
      even opened slowly — unauthenticated slots never free.
  P2  bare sockets, BURST: same 10.
  P3  SDK clients (which authenticate), SEQUENTIAL: NO ceiling at 11 — 32 and 64 all hold,
      because each auth frees its slot before the next connect.
  P4  SDK clients, BURST, no retry: ~11 (10 + however many auth mid-burst).
  P5  SDK clients, BURST, WITH RETRY: reaches N — proving this is burst admission plus a
      non-retrying pool builder, NOT a ceiling on concurrent authenticated connections.
  P6  refusal layer: TCP connect SUCCEEDS; the rejection is the upgrade answered without a
      101 (Starlette close-before-accept surfaces as HTTP 403) or a 1008 close — never a
      TCP-level refusal. The probe records which.

    SMOKE_EXTERNAL=1 python3 working/scripts/probe_ws_ceiling.py            # all phases
    python3 working/scripts/probe_ws_ceiling.py --host 127.0.0.1 --port 5565 --n 8 11 12 16 32 64
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import experiment_common as ec          # noqa: E402
from harness.resultio import write_result            # noqa: E402

say = ec.say


def bare_open(host: str, port: int, timeout: float = 10.0) -> dict:
    """One raw WebSocket upgrade, held open, never authenticated. Classifies the exact layer
    of any refusal — that is Leela's question 2 and prediction P6."""
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
    except OSError as e:
        s.close()
        return {"layer": "tcp_connect_refused", "detail": str(e)[:80], "sock": None}
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET /task/service HTTP/1.1\r\nHost: {host}:{port}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    try:
        s.sendall(req.encode())
        head = s.recv(4096)
    except OSError as e:
        s.close()
        return {"layer": "reset_during_upgrade", "detail": str(e)[:80], "sock": None}
    line = head.split(b"\r\n", 1)[0].decode(errors="replace")
    if b" 101 " in head.split(b"\r\n", 1)[0]:
        # Upgrade accepted. A 1008 close frame may still arrive; peek briefly.
        s.settimeout(1.5)
        try:
            frame = s.recv(64)
            if frame and (frame[0] & 0x0F) == 0x8:          # close opcode
                code = int.from_bytes(frame[2:4], "big") if len(frame) >= 4 else None
                s.close()
                return {"layer": f"ws_close_{code}", "detail": "closed after 101",
                        "sock": None}
        except socket.timeout:
            pass                                             # no close: genuinely held
        return {"layer": "held", "detail": line, "sock": s}
    s.close()
    return {"layer": f"upgrade_rejected ({line})", "detail": line, "sock": None}


def phase_bare(host, port, n, burst: bool) -> dict:
    held, refused = [], {}
    socks = []
    if burst:
        # As simultaneous as a single thread gets: connect all TCP first, then upgrade.
        results = [bare_open(host, port) for _ in range(n)]
    else:
        results = []
        for _ in range(n):
            results.append(bare_open(host, port))
            time.sleep(0.2)                                  # deliberately staggered
    for r in results:
        if r["sock"] is not None:
            socks.append(r["sock"])
            held.append(r["layer"])
        else:
            refused[r["layer"]] = refused.get(r["layer"], 0) + 1
    out = {"offered": n, "held": len(socks), "refused": sum(refused.values()),
           "refusal_layers": refused}
    for s in socks:
        try:
            s.close()
        except OSError:
            pass
    return out


def phase_sdk(n: int, burst: bool, retry: int) -> dict:
    """N real SDK clients, which AUTHENTICATE — each success frees its unauth slot."""
    import asyncio

    from rocketride import RocketRideClient

    async def go():
        clients, failures = [], {}

        async def one(i):
            for attempt in range(retry + 1):
                c = RocketRideClient()
                try:
                    await asyncio.wait_for(c.connect(timeout=15000), timeout=20)
                    clients.append(c)
                    return
                except Exception as e:
                    key = f"{type(e).__name__}: {str(e)[:60]}"
                    if attempt == retry:
                        failures[key] = failures.get(key, 0) + 1
                    else:
                        await asyncio.sleep(0.3 * (attempt + 1))

        if burst:
            await asyncio.gather(*(one(i) for i in range(n)))
        else:
            for i in range(n):
                await one(i)
        held = len(clients)
        for c in clients:
            try:
                await c.disconnect()
            except Exception:
                pass
        return {"offered": n, "held": held, "refused": sum(failures.values()),
                "failures": failures, "retries_allowed": retry}
    return asyncio.run(go())


def engine_env(host: str, port: int) -> dict:
    """Leela's question 3: listen backlog and fd limits, to rule out an environment cap."""
    import subprocess
    out: dict = {}
    try:
        r = subprocess.run(["ss", "-ltn", f"sport = :{port}"], capture_output=True,
                           text=True, timeout=10)
        out["ss_ltn"] = r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        out["ss_ltn"] = f"unavailable: {type(e).__name__}"
    pid = ec._container_root_pid(ec.RR_CONTAINER) if ec.EXTERNAL else None
    if pid:
        try:
            lim = Path(f"/proc/{pid}/limits").read_text()
            out["engine_fd_limit"] = next((l for l in lim.splitlines()
                                           if "open files" in l), "not found")
            out["engine_pid"] = pid
        except OSError as e:
            out["engine_fd_limit"] = f"unreadable: {type(e).__name__}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("SMOKE_RR_PORT", "5565")))
    ap.add_argument("--n", type=int, nargs="+", default=[8, 11, 12, 16, 32, 64])
    a = ap.parse_args()

    say("WS ceiling probe — hypothesis: CONST_MAX_UNAUTHED_CONNS_PER_IP=10, per client IP, "
        "slot freed on auth")
    out = {"experiment": "probe_ws_ceiling", "host": a.host, "port": a.port,
           "hypothesis": "unauth-burst cap of 10 per IP (server-v3.3.1 constants.py:69), "
                         "NOT a ceiling on concurrent authenticated connections",
           "engine_env": engine_env(a.host, a.port), "phases": {}}
    say(f"  env: {out['engine_env']}")

    verdicts = []
    for n in a.n:
        r = phase_bare(a.host, a.port, n, burst=False)
        out["phases"][f"bare_seq_{n}"] = r
        say(f"  bare seq   N={n:<3} held={r['held']:<3} refused={r['refused']:<3} "
            f"{r['refusal_layers']}")
        if n > 10:
            verdicts.append(("P1", n, r["held"] == 10))
    r = phase_bare(a.host, a.port, max(a.n), burst=True)
    out["phases"]["bare_burst"] = r
    say(f"  bare burst N={max(a.n):<3} held={r['held']:<3} refused={r['refused']}")
    verdicts.append(("P2", max(a.n), r["held"] == 10))

    for n in a.n:
        r = phase_sdk(n, burst=False, retry=0)
        out["phases"][f"sdk_seq_{n}"] = r
        say(f"  sdk  seq   N={n:<3} held={r['held']:<3} refused={r['refused']} "
            f"{r['failures']}")
        if n >= 16:
            verdicts.append(("P3", n, r["held"] == n))
    for label, retry in (("sdk_burst_noretry", 0), ("sdk_burst_retry", 4)):
        r = phase_sdk(max(a.n), burst=True, retry=retry)
        out["phases"][label] = r
        say(f"  {label:<18} N={max(a.n):<3} held={r['held']:<3} refused={r['refused']} "
            f"{r['failures']}")
        if retry:
            verdicts.append(("P5", max(a.n), r["held"] == max(a.n)))

    out["predictions"] = [{"id": p, "n": n, "held_as_predicted": ok} for p, n, ok in verdicts]
    failed = [v for v in verdicts if not v[2]]
    out["hypothesis_survives"] = not failed
    say(f"\n  predictions: {sum(1 for v in verdicts if v[2])}/{len(verdicts)} held"
        + (f"  — FAILED: {[(p, n) for p, n, ok in failed]}  THE HYPOTHESIS IS WRONG; "
           "report the raw table, not the story" if failed else
           "  — consistent with the unauth-burst cap; NOT a connection ceiling"))
    p = write_result("probe_ws_ceiling", out)
    say(f"written -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
