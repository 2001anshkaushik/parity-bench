#!/usr/bin/env python3
"""How far does Model B scale — and does it degrade cleanly?

Model B (one pipeline, N concurrent in-flight `send()` calls) showed *zero* process growth from
n=1 to n=1000: the engine's work-stealing pool absorbs concurrency without forking. RLIMIT_NPROC
therefore does not bound Model B at all, and the real ceiling is whatever the engine's queueing,
memory and WebSocket transport impose.

That makes this the probe that sets the sweep range. It pushes to 10,000 and beyond, and — more
importantly than the maximum — records *how* behaviour changes on the way: whether latency grows
smoothly (clean backpressure), throughput collapses, or the engine stops serving.

Health is checked after every level so a livelock is caught immediately rather than after 27
minutes, which is how the Model A failure was first discovered.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo  # noqa: E402

UID = os.getuid()
URI = "http://127.0.0.1:5565"
OUT = ROOT / "results" / "process_scaling"
LEVELS = [100, 500, 1000, 2000, 5000, 10000, 20000]


def engine_healthy(timeout: float = 8.0) -> bool:
    try:
        with urllib.request.urlopen(f"{URI}/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def snapshot() -> dict:
    total = node = 0
    eng_rss = 0
    eng_threads = 0
    for p in psutil.process_iter(["uids", "cmdline", "memory_info", "num_threads"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            total += 1
            cmd = " ".join(p.info["cmdline"] or ())
            if eo.NODE_MARK in cmd:
                node += 1
            if "eaas.py" in cmd and "5565" in cmd:
                eng_rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
                eng_threads = p.info["num_threads"] or 0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"uid_procs": total, "node_procs": node,
            "engine_rss_mb": round(eng_rss / 2**20, 1), "engine_threads": eng_threads}


async def level(client, token: str, n: int) -> dict:
    lat: list[float] = []
    errs: list[str] = []

    async def one(i: int):
        t0 = time.perf_counter()
        try:
            await client.send(token, f"item-{i}", mimetype="text/plain")
            lat.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            errs.append(f"{type(e).__name__}: {e}"[:120])

    before = snapshot()
    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
    wall = time.perf_counter() - t0
    after = snapshot()

    lat.sort()
    def pct(q):
        return round(lat[min(len(lat) - 1, int(q * len(lat)))], 2) if lat else None

    return {
        "concurrency": n, "wall_s": round(wall, 3),
        "ok": len(lat), "errors": len(errs),
        "error_sample": errs[0] if errs else None,
        "throughput_per_s": round(len(lat) / wall, 1) if wall else None,
        "lat_p50_ms": pct(0.50), "lat_p95_ms": pct(0.95), "lat_p99_ms": pct(0.99),
        "lat_max_ms": round(lat[-1], 2) if lat else None,
        "before": before, "after": after,
    }


async def main() -> int:
    from rocketride import RocketRideClient

    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print("Model B ceiling — one pipeline, N concurrent sends")
    print("=" * 74)
    if not engine_healthy():
        print("engine not healthy; run scripts/start_engine.sh first")
        return 1

    c = RocketRideClient()
    await c.connect(timeout=30000)
    r = await c.use(filepath="pipes/probe_minimal.pipe")
    token = r["token"]
    await c.send(token, "warm", mimetype="text/plain")
    print(f"task ready; baseline {snapshot()}\n")

    rows = []
    broke_at = None
    try:
        for n in LEVELS:
            row = await level(c, token, n)
            rows.append(row)
            print(f"n={n:6d}  ok={row['ok']:6d} err={row['errors']:5d}  "
                  f"{row['wall_s']:7.2f}s  {str(row['throughput_per_s']):>8}/s  "
                  f"p50={row['lat_p50_ms']} p99={row['lat_p99_ms']} max={row['lat_max_ms']}  "
                  f"procs={row['after']['uid_procs']} node={row['after']['node_procs']} "
                  f"engine_rss={row['after']['engine_rss_mb']}MB "
                  f"thr={row['after']['engine_threads']}")
            await asyncio.sleep(1.0)
            if not engine_healthy():
                broke_at = n
                print(f"\n*** ENGINE STOPPED SERVING after n={n} ***")
                break
            if row["errors"] > row["ok"] * 0.5 and row["errors"] > 10:
                broke_at = n
                print(f"\n*** MAJORITY ERRORS at n={n} — stopping ***")
                break
    finally:
        try:
            await asyncio.wait_for(c.terminate(token), timeout=15)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass

    result = {"levels": LEVELS, "rows": rows, "broke_at": broke_at,
              "engine_healthy_at_end": engine_healthy()}
    (OUT / "model_b_ceiling.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"\nbroke_at = {broke_at}   healthy_at_end = {result['engine_healthy_at_end']}")
    print(f"written -> {OUT / 'model_b_ceiling.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
