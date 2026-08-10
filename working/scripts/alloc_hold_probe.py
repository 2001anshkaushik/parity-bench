#!/usr/bin/env python3
"""alloc_hold — make the memory fault actually test sustained concurrent pressure.

The `alloc` cell in the matrix scored 0.00 for everyone and looked like a non-differentiator. It
was a weak test: each allocation freed immediately (~0.3 s), so peak RSS implied only ~3-6
allocations resident at once. "Survived 27 GB of churn" really meant "survived ~3 GB, 54 times in
a row" — sequential churn, not concurrent pressure.

`alloc_hold:T` allocates and HOLDS for T seconds, so concurrent allocations genuinely overlap and
peak footprint becomes `min(pool_width, n_faults) x block_size`. That is where the architectures
should diverge: a 14-worker process pool and a 64-wide thread pool hold very different amounts of
memory for the same offered load.

Sized deliberately: 256 MB x up to 54 concurrent = ~13.8 GB worst case on a 48 GiB host, which
leaves ample headroom. This must not be the experiment that swaps the user's desktop.

Order is randomised with a fixed seed (audit finding A5), every framework gets an identical
warm-up (A1), and the process pool is pre-spawned outside the timed region (A2).
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import json
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo                       # noqa: E402
from harness.seeds import seed_for                         # noqa: E402
from scripts.fault_matrix import (                         # noqa: E402
    DEADLINE, FILLER, MemWatch, digest, payload, plan, score,
)

OUT = ROOT / "results" / "alloc_hold"
N = 1000
RATE = 0.05
HOLD_S = 2.0
BLOCK_MB = 256
FAULT = f"alloc_hold:{HOLD_S}"


def execute_hold(item_id: str, fault: str) -> str:
    if fault.startswith("alloc_hold:"):
        blob = bytearray(BLOCK_MB * 1024 * 1024)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        time.sleep(float(fault.split(":", 1)[1]))
        v = digest(item_id)
        del blob
        return v
    return digest(item_id)


def _pp(arg):
    item_id, f = arg
    try:
        return (item_id, True, execute_hold(item_id, f))
    except Exception:
        return (item_id, False, None)


def _warm(_):
    return 1


async def rr(items) -> dict:
    from rocketride import RocketRideClient
    c = RocketRideClient()
    await c.connect(timeout=30000)
    r, err = await eo.guarded(c.use(filepath="pipes/fault_probe.pipe"))
    if r is None:
        await c.disconnect(); return {"error": err}
    tok = r["token"]
    await c.send(tok, payload("warm", "ok"), mimetype="text/plain")
    res: dict = {}
    t0 = time.perf_counter(); dl = t0 + DEADLINE

    async def one(i, f):
        rem = dl - time.perf_counter()
        if rem <= 0:
            res[i] = (False, None); return
        try:
            resp = await asyncio.wait_for(
                c.send(tok, payload(i, f), mimetype="text/plain"), timeout=rem)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                res[i] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                res[i] = (True, txt[0].strip() if isinstance(txt, list) and txt else None)
        except Exception:
            res[i] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    wall = time.perf_counter() - t0
    h = eo.healthy(15)
    if h:
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=30)
        except Exception:
            pass
    try:
        await c.disconnect()
    except Exception:
        pass
    return score(items, res, wall, {"engine_healthy_after": h})


async def aio(items) -> dict:
    res: dict = {}
    sem = asyncio.Semaphore(64)
    await asyncio.to_thread(_warm, 0)          # identical warm-up (audit A1)
    t0 = time.perf_counter(); dl = t0 + DEADLINE

    async def one(i, f):
        async with sem:
            rem = dl - time.perf_counter()
            if rem <= 0:
                res[i] = (False, None); return
            try:
                res[i] = (True, await asyncio.wait_for(
                    asyncio.to_thread(execute_hold, i, f), timeout=rem))
            except Exception:
                res[i] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    return score(items, res, time.perf_counter() - t0, {"effective_width": 18})


async def tp(items) -> dict:
    res: dict = {}
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(64)
    with cf.ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_warm, range(64)))         # pre-warm outside timing
        t0 = time.perf_counter(); dl = t0 + DEADLINE

        async def one(i, f):
            async with sem:
                rem = dl - time.perf_counter()
                if rem <= 0:
                    res[i] = (False, None); return
                try:
                    res[i] = (True, await asyncio.wait_for(
                        loop.run_in_executor(ex, execute_hold, i, f), timeout=rem))
                except Exception:
                    res[i] = (False, None)

        await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
        wall = time.perf_counter() - t0
        ex.shutdown(wait=False, cancel_futures=True)
    return score(items, res, wall, {"effective_width": 64})


def pp(items) -> dict:
    res: dict = {}
    ctx = mp.get_context("spawn")
    ex = cf.ProcessPoolExecutor(max_workers=14, mp_context=ctx)
    list(ex.map(_warm, range(14)))             # pre-spawn outside timing (audit A2)
    t0 = time.perf_counter(); dl = t0 + DEADLINE
    futs = {ex.submit(_pp, it): it[0] for it in items}
    try:
        for fut in cf.as_completed(futs, timeout=max(0.01, dl - time.perf_counter())):
            iid = futs[fut]
            try:
                item_id, ok, val = fut.result()
                res[item_id] = (ok, val)
            except Exception:
                res[iid] = (False, None)
    except cf.TimeoutError:
        pass
    for f in futs:
        f.cancel()
    wall = time.perf_counter() - t0
    ex.shutdown(wait=False, cancel_futures=True)
    return score(items, res, wall, {"effective_width": 14})


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = plan(N, FAULT, RATE)
    injected = sum(1 for _, f in items if f != "ok")
    print("=" * 78)
    print(f"alloc_hold — {BLOCK_MB} MB held {HOLD_S}s, n={N}, rate={RATE}, injected={injected}")
    print(f"  worst-case concurrent footprint = min(width, {injected}) x {BLOCK_MB} MB")
    print("=" * 78)

    order = [("rocketride", rr), ("asyncio", aio), ("threadpool", tp), ("processpool", pp)]
    random.Random(seed_for("allocholdorder")).shuffle(order)
    print(f"  randomised order: {[n for n, _ in order]}\n")

    rows = []
    for name, fn in order:
        eo.preflight(f"allochold/{name}")      # identical hygiene for all (audit A4)
        with MemWatch() as m:
            r = await fn(items) if asyncio.iscoroutinefunction(fn) else fn(items)
        mem = m.report()
        rows.append({"framework": name, "block_mb": BLOCK_MB, "hold_s": HOLD_S, **r, **mem})
        print(f"  {name:13s} ratio={str(r.get('isolation_ratio')):<8} "
              f"good={r.get('goodput_pct')}% collat={r.get('collateral_total'):<4} "
              f"peakRSS={mem['peak_tree_rss_mb']}MB sysmem={mem['peak_system_mem_pct']}% "
              f"cmpr={mem['compressor_delta_mb']}MB swap={mem['swapouts_delta']} "
              f"{r.get('wall_s')}s", flush=True)
        (OUT / "alloc_hold.json").write_text(json.dumps(rows, indent=2, default=str))
        eo.postflight(f"allochold/{name}")

    print(f"\nwritten -> {OUT/'alloc_hold.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
