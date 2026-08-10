#!/usr/bin/env python3
"""ITEM A3 — locate what serialises RocketRide under concurrency, before we containerise.

Established (session 6): RocketRide's throughput is FLAT in offered concurrency 2->32
(56-65 /s at 400 tokens) while the LlamaIndex service scales to a plateau. Something serialises
the workload regardless of how much load is offered. This run localises it.

A LADDER OF FOUR ARMS, each adding exactly one layer to the one below:

  1. minimal   webhook -> response_text            NO Python node at all. Pure engine request
                                                   path: WebSocket + DAP + dispatch + response.
  2. noop      webhook -> noop_probe -> response   Adds DISPATCH INTO A PYTHON NODE. The node
                                                   consumes the lane and emits a constant.
  3. cpu       webhook -> cpu_probe  -> response   Adds ~15 ms of PURE-PYTHON CPU. No model, no
                                                   torch, no native library that might release
                                                   the GIL on its own schedule.
  4. embed     webhook -> split_embed -> response  Adds the MiniLM forward pass (native code).

Readings, decided in advance:
  * arm 1 flat                      -> the engine's request path serialises. Nothing above it
                                       can be blamed and no node change can help.
  * arm 1 scales, arm 2 flat        -> Python-node dispatch serialises.
  * arms 1-2 scale, arm 3 flat      -> executing Python in a node serialises (one interpreter
                                       holding one GIL for all concurrent work).
  * arms 1-3 scale, arm 4 flat      -> the serialisation is specific to the model/native stack,
                                       not to the engine.

RULE 3 NULL CONTROL. Arm 1 is the control: finding 10 already puts the engine at 12,313 /s on
this exact pipeline with 4 drivers, so arm 1 MUST reach thousands/s. If it reads ~60 /s the
instrument is broken, not the engine, and nothing else in this run may be believed.

RULE 5. A flat arm 1 would be the most damaging possible result for RocketRide, so the client
ceiling is measured explicitly rather than assumed: per-driver rates are reported alongside the
aggregate, and a client-bound arm shows a per-driver rate that falls as drivers are added while
the total stays pinned.

Same document on every arm so payload is not a variable. Barrier-synchronised fixed-duration
windows (the session-6 fix): all drivers load the engine over the SAME wall-clock interval, with
no per-burst boundaries inside it.
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo       # noqa: E402
from harness.seeds import seed_for         # noqa: E402

OUT = ROOT / "results" / "a3_serialization.json"
UNIT = "The quick brown fox jumps over the lazy dog. "
DOC = UNIT * 40                 # ~400 tokens, identical on every arm
CONCS = [1, 2, 4, 8, 16, 32]
WINDOW = 4.0
REPS = 3
WARMUP = 1
MAXDRV = 4

ARMS = {
    "1_minimal": "pipes/probe_minimal.pipe",
    "2_noop":    "pipes/a3_noop.pipe",
    "3_cpu":     "pipes/a3_cpu.pipe",
    "4_embed":   "pipes/single_node.pipe",
}

_BARRIER = None


def _init(b):
    global _BARRIER
    _BARRIER = b


def layout(conc: int) -> tuple[int, int]:
    drivers = min(MAXDRV, conc)
    return drivers, max(1, conc // drivers)


def _driver(args) -> list[dict]:
    tag, pipe_rel, conc, reps, warm = args
    barrier = _BARRIER

    async def go():
        from rocketride import RocketRideClient
        base = json.loads((ROOT / pipe_rel).read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"a3-{tag}"))
        p = ROOT / "pipes" / "generated" / f"a3_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(base))

        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        # one warm send outside every measured window; also our latency reference
        t0 = time.perf_counter()
        await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
        warm_ms = (time.perf_counter() - t0) * 1000

        out = []
        for w in range(reps + warm):
            try:
                barrier.wait(timeout=180)
            except Exception:
                pass
            ok = fail = 0
            lat: list[float] = []
            stop = time.time() + WINDOW
            start = time.time()

            async def worker():
                nonlocal ok, fail
                while time.time() < stop:
                    s = time.perf_counter()
                    try:
                        await asyncio.wait_for(
                            c.send(tok, DOC, mimetype="text/plain"), timeout=600)
                        lat.append(time.perf_counter() - s)
                        ok += 1
                    except Exception:
                        fail += 1

            await asyncio.gather(*(worker() for _ in range(conc)))
            el = time.time() - start
            if w >= warm:
                ls = sorted(lat)
                out.append({"ok": ok, "fail": fail, "elapsed": el,
                            "p50_ms": round(ls[len(ls) // 2] * 1000, 2) if ls else None,
                            "warm_ms": round(warm_ms, 2)})
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return out

    return asyncio.run(go())


def measure(arm: str, conc: int) -> dict:
    drivers, per = layout(conc)
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(drivers)
    args = [(f"{arm}_{conc}_{i}", ARMS[arm], per, REPS, WARMUP) for i in range(drivers)]
    with ctx.Pool(drivers, initializer=_init, initargs=(barrier,)) as pool:
        res = pool.map(_driver, args)

    rates, per_driver, fails, p50s = [], [], 0, []
    for w in range(REPS):
        ok = sum(r[w]["ok"] for r in res)
        fails += sum(r[w]["fail"] for r in res)
        el = max(r[w]["elapsed"] for r in res)
        rates.append(round(ok / el, 2) if el > 0 else 0.0)
        per_driver.append(round(statistics.median(
            [r[w]["ok"] / r[w]["elapsed"] for r in res]), 2))
        p50s += [r[w]["p50_ms"] for r in res if r[w]["p50_ms"]]
    med = statistics.median(rates)
    sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0.0
    return {"median": med, "rates": rates, "spread": round(sp, 4), "gate": sp <= 0.10,
            "drivers": drivers, "conc_per_driver": per, "fails": fails,
            "per_driver_median": statistics.median(per_driver),
            "p50_ms": round(statistics.median(p50s), 2) if p50s else None,
            "warm_ms": round(statistics.median([r[0]["warm_ms"] for r in res]), 2)}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    eo.preflight("a3-serialization")
    print("=" * 104)
    print("ITEM A3 — WHERE DOES ROCKETRIDE SERIALISE?  ladder: minimal -> noop -> cpu -> embed")
    print("=" * 104)
    combos = [(a, c) for a in ARMS for c in CONCS]
    random.Random(seed_for("a3ladder")).shuffle(combos)
    cells: dict[tuple, dict] = {}
    try:
        for i, (a, c) in enumerate(combos):
            cell = measure(a, c)
            cells[(a, c)] = cell
            print(f"  [{i + 1:2d}/{len(combos)}] {a:10s} conc={c:2d} "
                  f"{cell['median']:9.2f}/s  sp={cell['spread'] * 100:5.1f}% "
                  f"{'OK  ' if cell['gate'] else 'GATE'} "
                  f"({cell['drivers']}drv x {cell['conc_per_driver']}) "
                  f"per-drv={cell['per_driver_median']:8.2f}/s  p50={cell['p50_ms']}ms  "
                  f"fails={cell['fails']}", flush=True)
    finally:
        eo.postflight("a3-serialization")

    print("\n" + "=" * 104)
    print("SCALING LADDER — throughput vs offered concurrency")
    print("=" * 104)
    print(f"  {'arm':10s} " + "".join(f"{('c=' + str(c)):>12s}" for c in CONCS) + "   scaling")
    rows = []
    for a in ARMS:
        vals = [cells[(a, c)]["median"] for c in CONCS]
        scal = max(vals) / vals[0] if vals[0] else 0
        rows.append({"arm": a, "pipe": ARMS[a],
                     "cells": {str(c): cells[(a, c)] for c in CONCS},
                     "scaling_factor": round(scal, 2)})
        print(f"  {a:10s} " + "".join(f"{v:12.1f}" for v in vals) + f"   {scal:5.2f}x")
    print(f"\n  {'arm':10s} {'p50 @c=1':>10s} {'p50 @c=32':>10s}   latency inflation")
    for a in ARMS:
        l1, l32 = cells[(a, 1)]["p50_ms"], cells[(a, 32)]["p50_ms"]
        print(f"  {a:10s} {l1:10.2f} {l32:10.2f}   {(l32 / l1 if l1 else 0):5.1f}x")

    OUT.write_text(json.dumps(rows, indent=1))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
