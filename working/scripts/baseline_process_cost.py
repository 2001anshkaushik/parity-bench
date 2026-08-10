#!/usr/bin/env python3
"""Process cost per unit of concurrency for the Python baselines.

Completes the Step 0 picture: RLIMIT_NPROC only binds an adapter that actually forks per unit of
work. Establishing that per-unit cost for each Track A baseline says which of them (if any) the
8,000-process ceiling constrains.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import json
import multiprocessing as mp
import os
import sys
import threading
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "process_scaling"
UID = os.getuid()


def count() -> int:
    n = 0
    for p in psutil.process_iter(["uids"]):
        try:
            if p.info["uids"] and p.info["uids"].real == UID:
                n += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return n


class Peak:
    def __init__(self, interval=0.1):
        self.interval, self.peak = interval, 0
        self._stop = threading.Event()

    def __enter__(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *e):
        self._stop.set()
        self._t.join(timeout=3)

    def _loop(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, count())
            self._stop.wait(self.interval)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    base = count()
    print(f"baseline uid procs: {base}\n")
    rows = []

    async def _aio(n):
        await asyncio.gather(*(asyncio.sleep(0.5) for _ in range(n)))

    for n in (100, 1000, 10000):
        with Peak() as pk:
            asyncio.run(_aio(n))
        d = pk.peak - base
        rows.append({"adapter": "asyncio", "concurrency": n, "peak": pk.peak,
                     "delta": d, "procs_per_unit": round(d / n, 5)})
        print(f"asyncio      n={n:6d}  peak={pk.peak:5d}  delta={d:+4d}  per_unit={d/n:.5f}")

    for n in (100, 1000):
        workers = min(n, 512)   # macOS thread ceiling; 10k OS threads is not a real design
        with Peak() as pk:
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(lambda _: time.sleep(0.3), range(n)))
        d = pk.peak - base
        rows.append({"adapter": "threadpool", "concurrency": n, "workers": workers,
                     "peak": pk.peak, "delta": d, "procs_per_unit": round(d / n, 5)})
        print(f"threadpool   n={n:6d}  workers={workers:4d} peak={pk.peak:5d}  delta={d:+4d}  "
              f"per_unit={d/n:.5f}")

    for w in (4, 10, 14, 28, 56):
        with Peak() as pk:
            ctx = mp.get_context("spawn")
            with cf.ProcessPoolExecutor(max_workers=w, mp_context=ctx) as ex:
                list(ex.map(time.sleep, [0.4] * w))
                time.sleep(0.3)
        d = pk.peak - base
        rows.append({"adapter": "processpool", "workers": w, "peak": pk.peak,
                     "delta": d, "procs_per_worker": round(d / w, 3)})
        print(f"processpool  workers={w:4d}  peak={pk.peak:5d}  delta={d:+4d}  "
              f"per_worker={d/w:.2f}")

    (OUT / "baseline_process_cost.json").write_text(
        json.dumps({"baseline": base, "rows": rows}, indent=2))
    print(f"\nwritten -> {OUT / 'baseline_process_cost.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
