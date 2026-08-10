#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
Decisive test for the ~2,600/s ceiling: does throughput scale with DRIVER PROCESSES?

If aggregate throughput rises roughly linearly with independent client processes, the ceiling
was our own single Python driver (its GIL / event loop), and every RocketRide throughput number
collected so far UNDERSTATES the engine. If it stays pinned near ~2,600/s no matter how many
independent clients push, the engine is the ceiling.

Each driver gets its OWN pipeline file: the engine allows one live task per project_id, so
sharing one file makes every driver after the first fail with "Pipeline is already running."
"""
from __future__ import annotations
import asyncio, json, multiprocessing as mp, os, sys, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
from harness import engine_ops as eo

N_PER_DRIVER = 1500
CONC = 250

def _pipe_for(tag: str) -> str:
    base = json.loads((ROOT / "pipes" / "probe_minimal.pipe").read_text())
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"driverscale-{tag}"))
    p = ROOT / "pipes" / "generated" / f"drv_{tag}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(base))
    return str(p.relative_to(ROOT))

async def _drive(tag: str, n: int, conc: int) -> dict:
    from rocketride import RocketRideClient
    c = RocketRideClient(); await c.connect(timeout=30000)
    r = await c.use(filepath=_pipe_for(tag)); tok = r["token"]
    await c.send(tok, "warm", mimetype="text/plain")
    sem = asyncio.Semaphore(conc); ok = 0
    async def one(i):
        nonlocal ok
        async with sem:
            try:
                await asyncio.wait_for(c.send(tok, f"x{i}", mimetype="text/plain"), timeout=60); ok += 1
            except Exception: pass
    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
    wall = time.perf_counter() - t0
    try: await asyncio.wait_for(c.terminate(tok), timeout=30)
    except Exception: pass
    try: await c.disconnect()
    except Exception: pass
    return {"tag": tag, "ok": ok, "wall_s": round(wall, 3),
            "throughput_per_s": round(ok / wall, 1) if wall else None}

def _worker(args):
    tag, n, conc = args
    return asyncio.run(_drive(tag, n, conc))

if __name__ == "__main__":
    OUT = ROOT / "results" / "ceiling"; OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("DRIVER PROCESS SCALING (each driver = own process, own connection, own pipeline)")
    for nprocs in (1, 2, 4, 8):
        eo.preflight(f"drv{nprocs}")
        ctx = mp.get_context("spawn")
        args = [(f"n{nprocs}_i{i}", N_PER_DRIVER, CONC) for i in range(nprocs)]
        t0 = time.perf_counter()
        with ctx.Pool(nprocs) as pool:
            res = pool.map(_worker, args)
        wall = time.perf_counter() - t0
        tot = sum(r["ok"] for r in res)
        # per-driver windows overlap; sum of per-driver rates is the aggregate the ENGINE saw
        agg = round(sum(r["throughput_per_s"] or 0 for r in res), 1)
        row = {"driver_processes": nprocs, "total_ok": tot, "wall_s": round(wall, 3),
               "sum_of_driver_rates_per_s": agg,
               "per_driver": [r["throughput_per_s"] for r in res]}
        rows.append(row)
        print(f"  drivers={nprocs}  sum_rate={agg}/s  per_driver={row['per_driver']}", flush=True)
        (OUT / "driver_scaling.json").write_text(json.dumps(rows, indent=2))
        eo.postflight(f"drv{nprocs}")
    print(f"written -> {OUT/'driver_scaling.json'}")
