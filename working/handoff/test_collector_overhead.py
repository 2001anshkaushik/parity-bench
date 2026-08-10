"""Regression test: the collector must not perturb what it measures.

This test exists because the first version of the collector slowed the measured system 100x
(5,412 -> 58 items/s) and did it ASYMMETRICALLY — throttling in-process frameworks while leaving
an external engine untouched. That is not noise, it is a fabricated result.

It also asserts its own noise floor (T2). An earlier version of this test used a 30 ms workload
and swung +/-43% between repeats: it would have "passed" while being blind to any real regression.
A tolerance is only meaningful if the measurement is quieter than the tolerance.

Run:  python test_collector_overhead.py     (needs psutil; ~30 s)
"""
from __future__ import annotations
import concurrent.futures as cf
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tree_collector import ProcessCollector          # noqa: E402

N = 1500
REPS = 3
TOLERANCE = 0.15


def _work(i: int) -> int:
    acc = 0
    for k in range(9000):          # ~1 ms of GIL-holding work per item
        acc = (acc * 31 + k) & 0xFFFFFFFF
    return acc


def _run_once(with_collector: bool, tmp: Path) -> float:
    ctx = mp.get_context("spawn")
    with cf.ProcessPoolExecutor(max_workers=10, mp_context=ctx) as ex:
        list(ex.map(int, range(10)))                 # pre-spawn OUTSIDE the timed region
        col = None
        if with_collector:
            import os
            col = ProcessCollector(tmp / "s.jsonl", {"h": {"pids": [os.getpid()]}},
                                   interval_s=0.10)
            col.start()
        t0 = time.perf_counter()
        list(ex.map(_work, range(N), chunksize=25))
        d = time.perf_counter() - t0
        if col:
            col.stop()
    return N / d


def main() -> int:
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="colltest-"))
    off = sorted(_run_once(False, tmp) for _ in range(REPS))[REPS // 2]
    offs = [_run_once(False, tmp) for _ in range(REPS)]
    on = sorted(_run_once(True, tmp) for _ in range(REPS))[REPS // 2]
    noise = (max(offs) - min(offs)) / max(offs)
    overhead = (off - on) / off

    print(f"  collector OFF : {off:8.1f} items/s   (run-to-run spread {noise*100:.1f}%)")
    print(f"  collector ON  : {on:8.1f} items/s")
    print(f"  overhead      : {overhead*100:+.1f}%")

    fails = []
    if overhead >= TOLERANCE:
        fails.append(f"T1 overhead {overhead*100:.1f}% >= {TOLERANCE*100:.0f}%")
    if noise >= TOLERANCE:
        fails.append(f"T2 baseline noise {noise*100:.1f}% >= tolerance — measurement too noisy "
                     f"for the tolerance to mean anything")
    print("  RESULT:", "PASS" if not fails else "FAIL " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
