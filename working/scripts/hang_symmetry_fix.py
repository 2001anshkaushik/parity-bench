#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
Re-run the hang@5% cell with a SYMMETRIC deadline across all three frameworks.

Why this exists
---------------
The first pass applied a real 20 s per-item deadline to RocketRide and asyncio
(`asyncio.wait_for`), but not to ProcessPoolExecutor: that path called
`fut.result(timeout=...)` inside `as_completed()`, which only ever sees futures that have
ALREADY completed, so the timeout never fired. processpool was allowed to run to 100 s and
scored a perfect 0.0 isolation ratio, while RocketRide's items were killed at 20 s and scored
13.82. That is not a framework difference, it is a harness bug — and it happened to flatter the
Python baseline and penalise RocketRide.

Fix: one wall-clock deadline enforced identically for every framework. Items not finished by the
deadline are counted lost for everyone. Also reported is the deadline-free completion time, so
the distinction between "lost work" and "slow work" stays visible instead of being collapsed.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo  # noqa: E402
from scripts.fault_isolation_probe import (  # noqa: E402
    FILLER, ITEM_TIMEOUT, digest, execute_fault, payload, plan, score,
)

OUT = ROOT / "results" / "fault_isolation"
N = 1000
RATE = 0.05
FAULT = "hang"
SEED = hash((FAULT, RATE)) % 10**6


def _task(arg):
    item_id, f = arg
    try:
        return (item_id, True, execute_fault(item_id, f))
    except Exception:
        return (item_id, False, None)


def processpool_symmetric() -> dict:
    """Same deadline semantics as the async paths: unfinished at the deadline = lost."""
    items = plan(N, FAULT, RATE, SEED)
    results: dict[str, tuple[bool, str | None]] = {}
    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    deadline = t0 + ITEM_TIMEOUT
    with cf.ProcessPoolExecutor(max_workers=14, mp_context=ctx) as ex:
        futs = {ex.submit(_task, it): it[0] for it in items}
        try:
            for fut in cf.as_completed(futs, timeout=max(0.01, deadline - time.perf_counter())):
                iid = futs[fut]
                try:
                    item_id, ok, val = fut.result()
                    results[item_id] = (ok, val)
                except Exception:
                    results[iid] = (False, None)
        except cf.TimeoutError:
            pass  # everything still outstanding is lost, exactly as for the async paths
        for f in futs:
            f.cancel()
        wall = time.perf_counter() - t0
        ex.shutdown(wait=False, cancel_futures=True)
    return score(items, results, wall, {"deadline_s": ITEM_TIMEOUT, "workers": 14})


async def asyncio_symmetric() -> dict:
    items = plan(N, FAULT, RATE, SEED)
    results: dict[str, tuple[bool, str | None]] = {}
    sem = asyncio.Semaphore(64)
    t0 = time.perf_counter()
    deadline = t0 + ITEM_TIMEOUT

    async def one(item_id: str, f: str):
        async with sem:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                results[item_id] = (False, None)
                return
            try:
                v = await asyncio.wait_for(asyncio.to_thread(execute_fault, item_id, f),
                                           timeout=remaining)
                results[item_id] = (True, v)
            except Exception:
                results[item_id] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    return score(items, results, time.perf_counter() - t0,
                 {"deadline_s": ITEM_TIMEOUT, "semaphore": 64})


async def rocketride_symmetric() -> dict:
    from rocketride import RocketRideClient

    items = plan(N, FAULT, RATE, SEED)
    c = RocketRideClient()
    await c.connect(timeout=30000)
    r, err = await eo.guarded(c.use(filepath="pipes/fault_probe.pipe"))
    if r is None:
        await c.disconnect()
        return {"error": f"use failed: {err}"}
    token = r["token"]
    results: dict[str, tuple[bool, str | None]] = {}
    t0 = time.perf_counter()
    deadline = t0 + ITEM_TIMEOUT

    async def one(item_id: str, f: str):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            results[item_id] = (False, None)
            return
        try:
            resp = await asyncio.wait_for(
                c.send(token, payload(item_id, f), mimetype="text/plain"), timeout=remaining)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                results[item_id] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                results[item_id] = (True, txt[0].strip() if isinstance(txt, list) and txt else None)
        except Exception:
            results[item_id] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    wall = time.perf_counter() - t0
    ok_after = eo.healthy(15)
    if ok_after:
        try:
            await asyncio.wait_for(c.terminate(token), timeout=30)
        except Exception:
            pass
    try:
        await c.disconnect()
    except Exception:
        pass
    return score(items, results, wall,
                 {"deadline_s": ITEM_TIMEOUT, "engine_healthy_after": ok_after})


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print(f"SYMMETRIC-DEADLINE RE-RUN: {FAULT} @ {RATE}, deadline {ITEM_TIMEOUT}s for ALL")
    print("=" * 74)
    rows = []

    eo.preflight("hangfix/rocketride")
    rr = await rocketride_symmetric()
    rows.append({"framework": "rocketride_model_b", **rr})
    print(f"  rocketride   ratio={rr.get('isolation_ratio')} collat={rr.get('collateral_total')} "
          f"good={rr.get('goodput_pct')}% wall={rr.get('wall_s')}s")
    eo.postflight("hangfix/rocketride")

    a = await asyncio_symmetric()
    rows.append({"framework": "asyncio", **a})
    print(f"  asyncio      ratio={a.get('isolation_ratio')} collat={a.get('collateral_total')} "
          f"good={a.get('goodput_pct')}% wall={a.get('wall_s')}s")

    p = processpool_symmetric()
    rows.append({"framework": "processpool", **p})
    print(f"  processpool  ratio={p.get('isolation_ratio')} collat={p.get('collateral_total')} "
          f"good={p.get('goodput_pct')}% wall={p.get('wall_s')}s")

    (OUT / "hang_symmetric.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nwritten -> {OUT/'hang_symmetric.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
