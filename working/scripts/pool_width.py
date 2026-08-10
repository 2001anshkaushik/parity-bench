#!/usr/bin/env python3
"""STEP 3 — measure the task's TRUE effective concurrency width.

The engine reports 24 OS threads; task config reportedly defaults to threadCount 64. Neither
tells us how many items a task actually executes at once, and without that number the hang
isolation ratio (~9) cannot be interpreted: it may be a pool-width artefact rather than a
property of the engine.

Method: hold each item for a known duration T inside the node (`sleep:T`), submit far more items
than any plausible width, and measure steady-state throughput X. For a pool of width W serving
holds of length T, X = W / T exactly. So W = X * T — read off, not guessed. Repeated at several
T so the answer must be consistent rather than a coincidence of one timing.
"""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
from harness import engine_ops as eo

OUT = ROOT / "results" / "pool_width"

async def measure(T: float, n: int, client_conc: int) -> dict:
    from rocketride import RocketRideClient
    c = RocketRideClient(); await c.connect(timeout=30000)
    r = await c.use(filepath="pipes/fault_probe.pipe"); tok = r["token"]
    await c.send(tok, f"FP|warm|ok|x", mimetype="text/plain")
    sem = asyncio.Semaphore(client_conc)
    done = 0
    async def one(i):
        nonlocal done
        async with sem:
            try:
                await asyncio.wait_for(
                    c.send(tok, f"FP|{i}|sleep:{T}|x", mimetype="text/plain"), timeout=180)
                done += 1
            except Exception: pass
    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
    wall = time.perf_counter() - t0
    try: await asyncio.wait_for(c.terminate(tok), timeout=30)
    except Exception: pass
    try: await c.disconnect()
    except Exception: pass
    thr = done / wall if wall else 0
    return {"hold_s": T, "n": n, "client_concurrency": client_conc, "completed": done,
            "wall_s": round(wall, 3), "throughput_per_s": round(thr, 2),
            "implied_width": round(thr * T, 1)}

async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("STEP 3 — effective pool width  (W = throughput x hold)")
    # n chosen so each config runs ~10-20 s: n = width_guess * (wall/T)
    for T, n in ((0.25, 600), (0.5, 400), (1.0, 200)):
        eo.preflight(f"width T={T}")
        r = await measure(T, n, client_conc=512)
        rows.append(r)
        print(f"  hold={T}s n={n}  completed={r['completed']} wall={r['wall_s']}s "
              f"thr={r['throughput_per_s']}/s  -> implied width = {r['implied_width']}", flush=True)
        (OUT / "pool_width.json").write_text(json.dumps(rows, indent=2))
        eo.postflight(f"width T={T}")
    widths = [r["implied_width"] for r in rows if r["completed"] > 0]
    if widths:
        print(f"\n  implied widths: {widths}  spread={max(widths)-min(widths):.1f}")
    print(f"written -> {OUT/'pool_width.json'}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
