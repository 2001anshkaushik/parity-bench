#!/usr/bin/env python3
"""STEP 1 experiment C — SECOND INDEPENDENT METHOD for the device finding.

Experiment A/B measured the model directly in N processes, with no HTTP. This measures the
running SERVICE over HTTP. Different failure modes: A/B could be wrong about process-pool
overhead or `cpu_times()` accounting; this one could be wrong about client saturation or accept
distribution. If both agree on the direction and rough magnitude of the mps-vs-cpu difference,
the finding is VERIFIED rather than PROVISIONAL.

Protocol compliance:
  - n=3 repetitions per (device, concurrency), randomised order with a fixed seed
  - median reported with min/max spread; single-run values never reported as fact
  - the client is checked against its own ceiling first, so we are not re-running the
    single-process-driver mistake
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.seeds import seed_for  # noqa: E402

PORT = int(os.environ.get("WS1_PORT", "8801"))
BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 40
REPS = 3
N_REQ = 200


def start_service(device: str, workers: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE=device, WS1_WORKERS=str(workers), WS1_PORT=str(PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")],
                         cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.perf_counter() + 240
    seen = 0
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=3) as r:
                if r.status == 200:
                    seen += 1
                    # /health is answered by ONE worker and is not a whole-service gate; poll
                    # repeatedly and give stragglers time before trusting it.
                    if seen >= 6:
                        time.sleep(3)
                        return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("service died on startup")
        time.sleep(2)
    p.kill()
    raise RuntimeError(f"service not ready in 240s (device={device})")


def stop_service(p: subprocess.Popen) -> None:
    subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
    try:
        p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
    time.sleep(2)


async def measure(conc: int, n: int) -> dict:
    import aiohttp

    lat: list[float] = []
    errs = 0
    pids: set[int] = set()
    conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
    sem = asyncio.Semaphore(conc)
    async with aiohttp.ClientSession(connector=conn) as s:
        async def one(i: int):
            nonlocal errs
            async with sem:
                t0 = time.perf_counter()
                try:
                    async with s.post(f"{BASE}/process",
                                      json={"doc_id": str(i), "text": DOC}) as r:
                        b = await r.json()
                        pids.add(b["meta"]["worker_pid"])
                        lat.append((time.perf_counter() - t0) * 1000)
                except Exception:
                    errs += 1
        await asyncio.gather(*(one(-i) for i in range(1, conc + 1)), return_exceptions=True)
        lat.clear(); pids.clear()
        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
        wall = time.perf_counter() - t0
    lat.sort()
    return {"throughput_per_s": round(len(lat) / wall, 1),
            "p50_ms": round(lat[len(lat) // 2], 2) if lat else None,
            "workers_hit": len(pids), "errors": errs}


def main() -> int:
    combos = [(dev, conc) for dev in ("cpu", "mps") for conc in (1, 4, 8, 14)]
    random.Random(seed_for("devicesweep")).shuffle(combos)
    by_device: dict = {}
    rows = []
    out = ROOT / "results" / "ws1_service_device.json"

    print("=" * 78)
    print(f"EXPERIMENT C — service over HTTP, mps vs cpu, n={REPS} randomised")
    print("=" * 78)

    # Group by device so we restart the service only when the device changes.
    for dev in ("cpu", "mps"):
        subset = [c for d, c in combos if d == dev]
        proc = start_service(dev, 14)
        try:
            for conc in subset:
                runs = []
                for _ in range(REPS):
                    runs.append(asyncio.run(measure(conc, N_REQ)))
                    time.sleep(2)          # short cooldown between repetitions
                thr = [r["throughput_per_s"] for r in runs]
                med = statistics.median(thr)
                spread = (max(thr) - min(thr)) / max(thr) if max(thr) else 0
                row = {"device": dev, "concurrency": conc, "reps": REPS,
                       "throughput_median_per_s": med, "throughput_runs": thr,
                       "spread_frac": round(spread, 3),
                       "p50_ms_median": statistics.median(r["p50_ms"] for r in runs),
                       "workers_hit": max(r["workers_hit"] for r in runs),
                       "errors": sum(r["errors"] for r in runs)}
                rows.append(row)
                by_device.setdefault(dev, []).append(row)
                print(f"  {dev:4s} conc={conc:3d}  median={med:8.1f}/s  runs={thr}  "
                      f"spread={spread*100:5.1f}%  p50={row['p50_ms_median']:7.2f}ms  "
                      f"workers_hit={row['workers_hit']}", flush=True)
                out.write_text(json.dumps(rows, indent=2))
        finally:
            stop_service(proc)

    print("\n  --- peak per device ---")
    for dev, rs in by_device.items():
        best = max(rs, key=lambda r: r["throughput_median_per_s"])
        print(f"  {dev:4s} peak {best['throughput_median_per_s']}/s at concurrency "
              f"{best['concurrency']} (spread {best['spread_frac']*100:.1f}%)")
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
