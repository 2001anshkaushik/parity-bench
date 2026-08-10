#!/usr/bin/env python3
"""STEP 2 — deployment parity: measure what the service boundary actually costs.

Every RocketRide number so far includes a WebSocket round trip to a separate process; every
in-process Python number does not. That gap is not a rounding error and it runs against
RocketRide, so the honest structure is two tiers:

  Tier 1 (in-process)  asyncio, ProcessPoolExecutor, ThreadPoolExecutor, langgraph, crewai.
                       RocketRide has NO entry — it cannot run in-process. Stated limitation.
  Tier 2 (service)     RocketRide engine vs each framework behind FastAPI+uvicorn. Same client,
                       same driver, same hop, same serialization. THE headline comparison.

This script measures the wrapper's own overhead — the thing that has to be subtracted (or at
least disclosed) before any Tier 1 number is compared to a Tier 2 one. Measured, not estimated:
the same work unit is run in-process and through the wrapper, and the delta is reported at p50
and p99 along with the wrapper's process and memory cost.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OUT = ROOT / "results" / "deployment_parity"
PORT = int(os.environ.get("T2_PORT", "8791"))
BASE = f"http://127.0.0.1:{PORT}"
FILLER = "x" * 64
UID = os.getuid()


def digest(item_id: str, filler: str) -> str:
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


def wrapper_procs() -> tuple[int, float]:
    """(process count, summed RSS MB) for the uvicorn master + workers."""
    n, rss = 0, 0.0
    for p in psutil.process_iter(["uids", "cmdline", "memory_info"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            cmd = " ".join(p.info["cmdline"] or ())
            if "uvicorn" in cmd and "asyncio_service" in cmd:
                n += 1
                if p.info["memory_info"]:
                    rss += p.info["memory_info"].rss / 2**20
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return n, round(rss, 1)


def start_wrapper(workers: int) -> subprocess.Popen:
    """Launch uvicorn tuned per its own deployment docs, not defaults."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable, "-m", "uvicorn", "wrappers.asyncio_service:app",
        "--host", "127.0.0.1", "--port", str(PORT),
        "--workers", str(workers),
        "--loop", "uvloop",          # uvicorn's recommended loop, not the asyncio default
        "--http", "httptools",       # C parser, not the pure-Python h11 fallback
        "--no-access-log",           # per-request logging is a known throughput tax
        "--log-level", "warning",
    ]
    p = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    import urllib.request
    deadline = time.perf_counter() + 60
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    return p
        except Exception:
            pass
        if p.poll() is not None:
            err = (p.stderr.read() or b"").decode()[-800:]
            raise RuntimeError(f"uvicorn died on startup: {err}")
        time.sleep(0.3)
    p.kill()
    raise RuntimeError("uvicorn did not become healthy in 60s")


def stop_wrapper(p: subprocess.Popen) -> None:
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=5)


async def drive_http(n: int, concurrency: int) -> dict:
    import aiohttp

    lat: list[float] = []
    errs = 0
    sem = asyncio.Semaphore(concurrency)
    conn = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)

    async with aiohttp.ClientSession(connector=conn) as sess:
        async def one(i: int):
            nonlocal errs
            async with sem:
                t0 = time.perf_counter()
                try:
                    async with sess.post(f"{BASE}/process",
                                         json={"item_id": str(i), "fault": "ok",
                                               "filler": FILLER}) as r:
                        body = await r.json()
                        if body.get("value") != digest(str(i), FILLER):
                            errs += 1
                        else:
                            lat.append((time.perf_counter() - t0) * 1000)
                except Exception:
                    errs += 1

        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
        wall = time.perf_counter() - t0

    lat.sort()
    def pct(q):
        return round(lat[min(len(lat) - 1, int(q * len(lat)))], 3) if lat else None
    return {"n": n, "concurrency": concurrency, "ok": len(lat), "errors": errs,
            "wall_s": round(wall, 3),
            "throughput_per_s": round(len(lat) / wall, 1) if wall else None,
            "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99)}


async def drive_inprocess(n: int, concurrency: int) -> dict:
    """Identical work unit with no boundary at all — the subtrahend."""
    lat: list[float] = []
    sem = asyncio.Semaphore(concurrency)

    def work(i):
        return digest(str(i), FILLER)

    async def one(i: int):
        async with sem:
            t0 = time.perf_counter()
            await asyncio.to_thread(work, i)
            lat.append((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
    wall = time.perf_counter() - t0
    lat.sort()
    def pct(q):
        return round(lat[min(len(lat) - 1, int(q * len(lat)))], 3) if lat else None
    return {"n": n, "concurrency": concurrency, "ok": len(lat), "errors": 0,
            "wall_s": round(wall, 3),
            "throughput_per_s": round(len(lat) / wall, 1) if wall else None,
            "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": pct(0.99)}


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    findings: dict = {}
    N = 2000
    CONC = 200

    print("=" * 74)
    print("STEP 2 — DEPLOYMENT PARITY: wrapper overhead, measured")
    print("=" * 74)

    print("\n[tier 1] in-process, no boundary")
    t1 = await drive_inprocess(N, CONC)
    findings["tier1_in_process"] = t1
    print(f"  {t1['throughput_per_s']}/s  p50={t1['p50_ms']}ms p99={t1['p99_ms']}ms")

    for workers in (1, 4, 14):
        print(f"\n[tier 2] FastAPI+uvicorn, workers={workers} (uvloop, httptools, no access log)")
        p = start_wrapper(workers)
        try:
            await drive_http(200, 50)                 # warm
            nproc, rss = wrapper_procs()
            res = await drive_http(N, CONC)
            res.update(wrapper_processes=nproc, wrapper_rss_mb=rss, workers=workers)
            findings[f"tier2_workers_{workers}"] = res
            print(f"  {res['throughput_per_s']}/s  p50={res['p50_ms']}ms p99={res['p99_ms']}ms "
                  f"procs={nproc} rss={rss}MB errors={res['errors']}")
            if t1["p50_ms"] is not None and res["p50_ms"] is not None:
                print(f"  overhead vs in-process: p50 +{res['p50_ms']-t1['p50_ms']:.3f}ms  "
                      f"p99 +{res['p99_ms']-t1['p99_ms']:.3f}ms  "
                      f"throughput x{res['throughput_per_s']/max(1e-9,t1['throughput_per_s']):.3f}")
        finally:
            stop_wrapper(p)
            time.sleep(1.0)

    (OUT / "deployment_parity.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nwritten -> {OUT/'deployment_parity.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
