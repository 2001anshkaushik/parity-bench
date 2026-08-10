#!/usr/bin/env python3
"""STEP 2 — settle Tier 2: RocketRide vs FastAPI+uvicorn, driven IDENTICALLY.

The previous Tier 2 result was not usable: FastAPI's 16,827/s came from a single-process aiohttp
driver, which is the exact flaw that understated RocketRide by 4.8x. A single Python client
saturates around 3,400 req/s regardless of what it is talking to, so both numbers were measuring
the driver.

Here both sides get the same multi-process driver, the same driver-count sweep, the same payload,
the same per-driver concurrency, on the same machine in the same session. Order is randomised
(fixed seed) so thermal drift and any warm-up advantage cannot systematically favour whichever
side happens to run first.

uvicorn workers are swept too — its own deployment docs call for one worker per core, and the
knee has to be found rather than assumed.
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo      # noqa: E402
from harness.seeds import seed_for        # noqa: E402

OUT = ROOT / "results" / "tier2"
PORT = int(os.environ.get("T2_PORT", "8793"))
BASE = f"http://127.0.0.1:{PORT}"
N_PER_DRIVER = 1500
CONC_PER_DRIVER = 250
DRIVER_COUNTS = [1, 2, 4, 8]
UVICORN_WORKERS = [4, 14]
UID = os.getuid()


# --------------------------------------------------------------------- resource census
def census(match_any: list[str]) -> dict:
    procs = 0
    threads = 0
    rss = 0.0
    for p in psutil.process_iter(["uids", "cmdline", "memory_info", "num_threads"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            cmd = " ".join(p.info["cmdline"] or ())
            if any(m in cmd for m in match_any):
                procs += 1
                threads += p.info["num_threads"] or 0
                if p.info["memory_info"]:
                    rss += p.info["memory_info"].rss / 2**20
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"processes": procs, "threads": threads, "rss_mb": round(rss, 1)}


RR_MATCH = ["eaas.py", "benchmark-A/engine/ai/node.py"]
FA_MATCH = ["uvicorn", "asyncio_service"]


# --------------------------------------------------------------------- workers
def _rr_worker(args) -> dict:
    tag, n, conc = args
    import asyncio as aio
    import json as js
    import uuid as uu

    async def go():
        from rocketride import RocketRideClient
        base = js.loads((ROOT / "pipes" / "probe_minimal.pipe").read_text())
        base["project_id"] = str(uu.uuid5(uu.NAMESPACE_DNS, f"tier2-{tag}"))
        p = ROOT / "pipes" / "generated" / f"t2_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(js.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        await c.send(tok, "warm", mimetype="text/plain")
        sem = aio.Semaphore(conc)
        lat: list[float] = []
        errs = 0

        async def one(i):
            nonlocal errs
            async with sem:
                t0 = time.perf_counter()
                try:
                    await aio.wait_for(c.send(tok, f"item-{i}", mimetype="text/plain"),
                                       timeout=60)
                    lat.append((time.perf_counter() - t0) * 1000)
                except Exception:
                    errs += 1

        t0 = time.perf_counter()
        await aio.gather(*(one(i) for i in range(n)), return_exceptions=True)
        wall = time.perf_counter() - t0
        try:
            await aio.wait_for(c.terminate(tok), timeout=30)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return {"ok": len(lat), "errors": errs, "wall_s": wall, "lat": lat}

    return asyncio.run(go())


def _fa_worker(args) -> dict:
    tag, n, conc = args
    import asyncio as aio

    async def go():
        import aiohttp
        lat: list[float] = []
        errs = 0
        sem = aio.Semaphore(conc)
        connector = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        async with aiohttp.ClientSession(connector=connector) as s:
            async def one(i):
                nonlocal errs
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        async with s.post(f"{BASE}/process",
                                          json={"item_id": f"{tag}-{i}", "fault": "ok",
                                                "filler": ""}) as r:
                            await r.json()
                            lat.append((time.perf_counter() - t0) * 1000)
                    except Exception:
                        errs += 1
            # warm
            try:
                async with s.get(f"{BASE}/health") as r:
                    await r.json()
            except Exception:
                pass
            t0 = time.perf_counter()
            await aio.gather(*(one(i) for i in range(n)), return_exceptions=True)
            wall = time.perf_counter() - t0
        return {"ok": len(lat), "errors": errs, "wall_s": wall, "lat": lat}

    return asyncio.run(go())


# --------------------------------------------------------------------- uvicorn control
def start_uvicorn(workers: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "uvicorn", "wrappers.asyncio_service:app",
           "--host", "127.0.0.1", "--port", str(PORT), "--workers", str(workers),
           "--loop", "uvloop", "--http", "httptools", "--no-access-log",
           "--log-level", "warning"]
    p = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.perf_counter() + 60
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    time.sleep(1.0)      # let all workers finish binding
                    return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError(f"uvicorn died: {(p.stderr.read() or b'').decode()[-500:]}")
        time.sleep(0.3)
    p.kill()
    raise RuntimeError("uvicorn not healthy in 60s")


def stop_uvicorn(p: subprocess.Popen) -> None:
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=5)


def summarise(res: list[dict], wall: float, label: str, extra: dict) -> dict:
    lat = sorted(x for r in res for x in r["lat"])
    ok = sum(r["ok"] for r in res)
    errs = sum(r["errors"] for r in res)
    agg = round(sum(r["ok"] / r["wall_s"] for r in res if r["wall_s"]), 1)

    def pct(q):
        return round(lat[min(len(lat) - 1, int(q * len(lat)))], 3) if lat else None

    return {"target": label, "total_ok": ok, "errors": errs,
            "outer_wall_s": round(wall, 3),
            "aggregate_throughput_per_s": agg,
            "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
            "per_driver_rates": [round(r["ok"] / r["wall_s"], 1) if r["wall_s"] else None
                                 for r in res], **extra}


def run_drivers(fn, nprocs: int, tag_prefix: str) -> tuple[list[dict], float]:
    ctx = mp.get_context("spawn")
    args = [(f"{tag_prefix}_{i}", N_PER_DRIVER, CONC_PER_DRIVER) for i in range(nprocs)]
    t0 = time.perf_counter()
    with ctx.Pool(nprocs) as pool:
        res = pool.map(fn, args)
    return res, time.perf_counter() - t0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    t_start = time.perf_counter()

    combos: list[tuple] = []
    for d in DRIVER_COUNTS:
        combos.append(("rocketride", d, None))
    for w in UVICORN_WORKERS:
        for d in DRIVER_COUNTS:
            combos.append(("fastapi", d, w))
    random.Random(seed_for("tier2order")).shuffle(combos)

    print("=" * 78)
    print("STEP 2 — TIER 2, both sides driven identically (randomised order)")
    print(f"  {N_PER_DRIVER} items/driver, concurrency {CONC_PER_DRIVER}/driver")
    print("=" * 78)

    uv_proc = None
    uv_workers_running = None
    try:
        for target, ndrv, workers in combos:
            if time.perf_counter() - t_start > 2400:
                print("  BUDGET GUARD: stopping Tier 2 sweep early", flush=True)
                rows.append({"skipped": f"{target}/{ndrv}/{workers}", "reason": "budget guard"})
                continue
            if target == "rocketride":
                if uv_proc:
                    stop_uvicorn(uv_proc); uv_proc = None; uv_workers_running = None
                eo.preflight(f"rr-d{ndrv}")
                res, wall = run_drivers(_rr_worker, ndrv, f"rr{ndrv}")
                c = census(RR_MATCH)
                row = summarise(res, wall, "rocketride",
                                {"drivers": ndrv, "uvicorn_workers": None, **c})
                eo.postflight(f"rr-d{ndrv}")
            else:
                if uv_workers_running != workers:
                    if uv_proc:
                        stop_uvicorn(uv_proc)
                    uv_proc = start_uvicorn(workers)
                    uv_workers_running = workers
                res, wall = run_drivers(_fa_worker, ndrv, f"fa{ndrv}w{workers}")
                c = census(FA_MATCH)
                row = summarise(res, wall, "fastapi",
                                {"drivers": ndrv, "uvicorn_workers": workers, **c})
            rows.append(row)
            (OUT / "tier2.json").write_text(json.dumps(rows, indent=2, default=str))
            print(f"  {row['target']:11s} drivers={ndrv} workers={workers} -> "
                  f"{row['aggregate_throughput_per_s']}/s  p50={row['p50_ms']}ms "
                  f"p99={row['p99_ms']}ms  procs={row['processes']} thr={row['threads']} "
                  f"rss={row['rss_mb']}MB errs={row['errors']}", flush=True)
    finally:
        if uv_proc:
            stop_uvicorn(uv_proc)

    (OUT / "tier2.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nelapsed {time.perf_counter()-t_start:.0f}s -> {OUT/'tier2.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
