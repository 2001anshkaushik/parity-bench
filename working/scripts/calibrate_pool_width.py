#!/usr/bin/env python3
"""STEP 3 — calibrate the pool-width instrument against systems of KNOWN width.

`pool_width.py` produced the "~17" figure that the whole team is about to rely on for the
concurrency-pinning field. Nobody has ever checked whether the instrument is accurate. Given this
project's record — a collector that biased results 100x, an IPC cost wrong by 115x, a driver that
understated throughput 4.8x — an uncalibrated instrument is exactly the shape of the next mistake.

Method: build pools whose width is known *by construction* (`ThreadPoolExecutor(max_workers=W)`),
run the same `W = throughput x hold` estimator against them, and report the error.

Also probes the failure modes that matter in practice:
  - hold duration too short relative to dispatch overhead
  - offered concurrency below the true width (estimator cannot see width it never exercises)
  - a pool whose width exceeds the core count (threads that are not CPU-bound)
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "pool_width_calibration.json"
REPS = 3


def _hold(seconds: float) -> float:
    """Sleep-based hold: releases the GIL, so a thread pool's width is genuinely exercised.
    Using a CPU-bound hold instead would measure core count, not pool width — a distinction the
    estimator depends on and a real failure mode worth stating."""
    time.sleep(seconds)
    return seconds


def estimate_width(pool: cf.ThreadPoolExecutor, hold_s: float, offered: int,
                   n_items: int) -> dict:
    """W = X * T, where X is steady-state throughput and T the per-item hold."""
    sem_items = list(range(n_items))
    t0 = time.perf_counter()
    futs = [pool.submit(_hold, hold_s) for _ in sem_items[:offered]]
    done = 0
    pending = set(futs)
    remaining = n_items - offered
    while pending:
        finished, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
        done += len(finished)
        for _ in finished:
            if remaining > 0:
                pending.add(pool.submit(_hold, hold_s))
                remaining -= 1
    wall = time.perf_counter() - t0
    thr = done / wall if wall else 0.0
    return {"throughput_per_s": round(thr, 2), "implied_width": round(thr * hold_s, 2),
            "wall_s": round(wall, 3), "completed": done}


def run_case(true_width: int, hold_s: float, offered: int, n_items: int) -> dict:
    est = []
    for _ in range(REPS):
        with cf.ThreadPoolExecutor(max_workers=true_width) as ex:
            ex.map(int, range(true_width))            # pre-spawn outside the measurement
            est.append(estimate_width(ex, hold_s, offered, n_items)["implied_width"])
    med = statistics.median(est)
    err = (med - true_width) / true_width
    return {"true_width": true_width, "hold_s": hold_s, "offered_concurrency": offered,
            "estimates": est, "median_estimate": med,
            "error_pct": round(err * 100, 1),
            "spread_pct": round((max(est) - min(est)) / max(est) * 100, 1) if max(est) else 0}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    print("=" * 78)
    print("POOL-WIDTH INSTRUMENT CALIBRATION — against KNOWN widths")
    print("=" * 78)

    print("\n[A] accuracy at known widths (hold 0.5 s, offered = 4x width)")
    for w in (4, 8, 16, 64):
        r = run_case(w, 0.5, offered=w * 4, n_items=w * 12)
        r["case"] = "accuracy"
        rows.append(r)
        print(f"  true={w:3d}  estimated={r['median_estimate']:7.2f}  error={r['error_pct']:+6.1f}%  "
              f"spread={r['spread_pct']:4.1f}%  runs={r['estimates']}", flush=True)

    print("\n[B] FAILURE MODE: hold too short (width 16, offered 64)")
    for hold in (0.01, 0.05, 0.25, 1.0):
        r = run_case(16, hold, offered=64, n_items=16 * 12)
        r["case"] = "short_hold"
        rows.append(r)
        print(f"  hold={hold:5.2f}s  estimated={r['median_estimate']:7.2f}  "
              f"error={r['error_pct']:+7.1f}%", flush=True)

    print("\n[C] FAILURE MODE: offered concurrency below true width (width 16, hold 0.5 s)")
    for off in (4, 8, 16, 32, 64):
        r = run_case(16, 0.5, offered=off, n_items=16 * 10)
        r["case"] = "under_offered"
        rows.append(r)
        print(f"  offered={off:3d}  estimated={r['median_estimate']:7.2f}  "
              f"error={r['error_pct']:+7.1f}%", flush=True)

    OUT.write_text(json.dumps(rows, indent=2))

    acc = [r for r in rows if r["case"] == "accuracy"]
    worst = max(abs(r["error_pct"]) for r in acc)
    print(f"\n  ACCURACY VERDICT: worst error across known widths = {worst:.1f}%")
    print(f"  written -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
