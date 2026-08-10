#!/usr/bin/env python3
"""Phase 1 gate — proves the harness measures what it claims to measure.

Calibrating the instrument before trusting it is not optional. Every check below is a specific
way this harness could silently lie in a published chart:

  T1 collector sees a child process's memory      -> otherwise external engines read as ~0 MB
  T2 CPU seconds survive process death            -> otherwise process-per-task engines read as free
  T3 workload generation is deterministic         -> otherwise runs are not comparable
  T4 fault injection fires at the configured rate -> otherwise "0 crashes" is meaningless
  T5 correctness verification catches wrong output-> otherwise fast-and-wrong scores as a win
  T6 adapters return one result per item          -> otherwise dropped items read as successes
  T7 fault isolation is measured, not assumed     -> the priority-2 claim
  T8 GIL signature is visible across kernels      -> the whole Track A premise

Exit code 0 only if every check passes.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import stats  # noqa: E402
from harness.adapters.baselines import AsyncioAdapter, ProcessPoolAdapter, ThreadPoolAdapter  # noqa: E402
from harness.collector import TreeCollector, self_pid_source  # noqa: E402
from harness.runner import RunConfig, Runner  # noqa: E402
from harness.workload import (  # noqa: E402
    FaultKind, Kernel, WorkloadSpec, generate, reference_results, run_sync,
)

RESULTS = Path(__file__).resolve().parent.parent / "results" / "selftest"
PASS, FAIL = "PASS", "FAIL"
_checks: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _checks.append((name, PASS if ok else FAIL, detail))
    print(f"  [{PASS if ok else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return ok


# --------------------------------------------------------------------------- T1/T2
def test_collector_tree_accounting() -> None:
    """Spawn a child that allocates a known amount, confirm the collector attributes it."""
    print("\nT1/T2 collector: process-tree memory + retired CPU")
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    target_mb = 200
    proc = ctx.Process(target=_child_burn, args=(target_mb, 2.5))
    proc.start()
    time.sleep(0.7)  # let the child import Python and start allocating

    col = TreeCollector(out_path=RESULTS / "collector_probe.jsonl",
                        roles={"child": lambda: [proc.pid] if proc.is_alive() else []},
                        interval_s=0.05)
    col.start()
    proc.join(timeout=15)
    time.sleep(0.3)
    col.stop()

    s = col.summary()["roles"]["child"]
    peak_mb = s["peak_rss_mb"]
    check("T1 child RSS attributed to tree",
          peak_mb >= target_mb * 0.5,
          f"peak {peak_mb} MB for a ~{target_mb} MB child")
    check("T2 CPU seconds retained after child exit",
          s["total_cpu_seconds"] > 0.05,
          f"{s['total_cpu_seconds']}s CPU, {s['distinct_pids_seen']} pid(s) seen")
    check("T2b thread count observed", s["peak_thread_count"] >= 1,
          f"peak {s['peak_thread_count']} threads")


def _child_burn(mb: int, seconds: float) -> None:
    blob = bytearray(mb * 2**20)
    for off in range(0, len(blob), 4096):
        blob[off] = 1
    end = time.perf_counter() + seconds
    x = 0
    while time.perf_counter() < end:
        x = (x * 31 + 7) & 0xFFFFFFFF
    del blob


# --------------------------------------------------------------------------- T3
def test_determinism() -> None:
    print("\nT3 workload determinism")
    spec = WorkloadSpec(n_items=500, kernel=Kernel.MIXED, seed=42,
                        rate_corrupt=0.05, rate_timeout=0.02, rate_exception=0.01)
    a, b = generate(spec), generate(spec)
    check("T3 identical items for identical spec",
          [x.to_dict() for x in a] == [x.to_dict() for x in b], f"{len(a)} items")
    c = generate(WorkloadSpec(n_items=500, kernel=Kernel.MIXED, seed=43))
    check("T3b different seed -> different workload",
          [x.to_dict() for x in a] != [x.to_dict() for x in c])
    sizes = [x.size_units for x in a]
    check("T3c sizes are heterogeneous (long tail present)",
          max(sizes) > 3 * (sorted(sizes)[len(sizes) // 2]),
          f"median {sorted(sizes)[len(sizes)//2]}, max {max(sizes)}")


# --------------------------------------------------------------------------- T4
def test_fault_rates() -> None:
    print("\nT4 fault injection rate accuracy")
    n = 20000
    spec = WorkloadSpec(n_items=n, kernel=Kernel.MIXED, seed=7,
                        rate_corrupt=0.05, rate_timeout=0.02, rate_memory_spike=0.01,
                        rate_exception=0.01)
    items = generate(spec)
    counts = {k: sum(1 for i in items if i.fault is k) for k in FaultKind}
    for kind, want in [(FaultKind.CORRUPT_INPUT, 0.05), (FaultKind.TIMEOUT, 0.02),
                       (FaultKind.MEMORY_SPIKE, 0.01), (FaultKind.EXCEPTION, 0.01)]:
        got = counts[kind] / n
        check(f"T4 {kind.value} ~{want:.0%}", abs(got - want) < 0.005, f"observed {got:.3%}")


# --------------------------------------------------------------------------- T5
def test_correctness_detection() -> None:
    print("\nT5 correctness verification")
    items = generate(WorkloadSpec(n_items=50, kernel=Kernel.MIXED, seed=3))
    ref = reference_results(items)
    check("T5 reference computed for all clean items", len(ref) == 50, f"{len(ref)}/50")
    same = run_sync(items[0]) == ref[items[0].item_id]
    check("T5b kernel is reproducible across calls", same)
    tampered = dict(ref)
    tampered[items[0].item_id] = "deadbeef"
    check("T5c a wrong value is distinguishable",
          tampered[items[0].item_id] != run_sync(items[0]))


# --------------------------------------------------------------------------- T6/T7/T8
async def test_adapters_and_isolation() -> dict:
    print("\nT6/T7 adapters: completeness + fault isolation")
    spec = WorkloadSpec(n_items=300, kernel=Kernel.MIXED, seed=11,
                        size_median=60, size_sigma=0.5,
                        rate_corrupt=0.05, rate_exception=0.02)
    n_faults = sum(1 for i in generate(spec) if i.fault is not FaultKind.NONE)

    out = {}
    for name, adapter in [("asyncio", AsyncioAdapter()),
                          ("threadpool", ThreadPoolAdapter(max_workers=8)),
                          ("processpool", ProcessPoolAdapter(max_workers=6))]:
        cfg = RunConfig(run_id=f"selftest_{name}", adapter_name=name, concurrency=32,
                        workload=spec, out_dir=RESULTS, verify_correctness=True)
        res = await Runner(adapter, cfg).run()
        c = res.counts
        check(f"T6 {name}: one result per submitted item",
              c["returned"] == c["submitted"] and c["missing"] == 0,
              f"{c['returned']}/{c['submitted']} returned")
        check(f"T6b {name}: injected faults actually failed",
              c["failed"] >= n_faults * 0.9,
              f"{c['failed']} failed vs {n_faults} injected")
        check(f"T6c {name}: no wrong values among successes",
              c["verified_wrong"] == 0,
              f"{c['verified_correct']} verified correct")
        check(f"T7 {name}: fault isolation measured",
              res.faults["collateral_failures"] == 0,
              f"cascade={res.faults['cascade_detected']}, "
              f"ratio={res.faults['isolation_ratio_collateral_per_fault']}")
        check(f"T7b {name}: resources captured for all roles",
              res.cost["peak_rss_all_roles_mb"] > 0 and res.cost["total_cpu_seconds_all_roles"] > 0,
              f"peak {res.cost['peak_rss_all_roles_mb']} MB, "
              f"{res.cost['total_cpu_seconds_all_roles']}s CPU")
        out[name] = res
    return out


async def test_gil_signature() -> dict:
    """The premise of Track A: GIL-bound work must scale differently than GIL-releasing work.

    The first draft of this test asserted "processes always beat threads on GIL-bound work" and
    failed — process pools lost by 14x. The cause is real and important: every task crossing a
    process boundary pays a fixed pickle + pipe + unpickle cost, and below some per-item work size
    that overhead dominates completely. So the honest test is not "processes win", it is
    "the process/thread advantage grows with per-item work and crosses 1.0 somewhere".

    That crossover is a calibration constant this suite needs anyway. RocketRide spawns a process
    tree per task, so it pays a structurally similar per-task cost — and any workload sized below
    the crossover will make *any* process-isolated engine look bad regardless of its scheduler.
    Choosing item sizes without knowing this number is how a benchmark accidentally decides its
    own outcome.
    """
    print("\nT8 GIL signature + process-boundary crossover")
    results: dict = {}
    sizes = [(90, "small"), (1200, "medium"), (4000, "large")]

    for kernel in (Kernel.GIL_BOUND, Kernel.GIL_FREE):
        for size_median, label in sizes:
            n = 120 if size_median < 1000 else 48
            spec = WorkloadSpec(n_items=n, kernel=kernel, seed=5,
                                size_median=size_median, size_sigma=0.15, size_cap=6000)
            for name, adapter in [("threadpool", ThreadPoolAdapter(max_workers=10)),
                                  ("processpool", ProcessPoolAdapter(max_workers=10))]:
                cfg = RunConfig(run_id=f"gil_{kernel.value}_{label}_{name}", adapter_name=name,
                                concurrency=10, workload=spec, out_dir=RESULTS,
                                verify_correctness=False)
                res = await Runner(adapter, cfg).run()
                results[(kernel, label, name)] = res.throughput["items_per_s"] or 0.0
            tp = results[(kernel, label, "threadpool")]
            pp = results[(kernel, label, "processpool")]
            ratio = pp / max(tp, 1e-9)
            print(f"      {kernel.value:10s} {label:7s} thread={tp:8.1f}/s  "
                  f"process={pp:7.1f}/s  ratio={ratio:5.2f}x")

    gb = {lbl: results[(Kernel.GIL_BOUND, lbl, "processpool")]
          / max(results[(Kernel.GIL_BOUND, lbl, "threadpool")], 1e-9) for _, lbl in sizes}
    gf = {lbl: results[(Kernel.GIL_FREE, lbl, "processpool")]
          / max(results[(Kernel.GIL_FREE, lbl, "threadpool")], 1e-9) for _, lbl in sizes}

    check("T8 process advantage grows with per-item work (GIL-bound)",
          gb["large"] > gb["small"],
          f"small {gb['small']:.2f}x -> large {gb['large']:.2f}x")
    check("T8b processes overtake threads at large items (GIL-bound)",
          gb["large"] > 1.0,
          f"ratio {gb['large']:.2f}x — crossover is below the 'large' size")
    check("T8c GIL-free work gains less from processes than GIL-bound",
          gf["large"] < gb["large"],
          f"gil_free {gf['large']:.2f}x < gil_bound {gb['large']:.2f}x "
          "(numpy already releases the GIL, so threads keep up)")
    return {"gil_bound_ratios": gb, "gil_free_ratios": gf}


async def test_observer_effect() -> float:
    """The instrument must not change the measurement — and must not change it *unevenly*.

    The first collector ran as a thread in the harness and called `children(recursive=True)` per
    root per tick; on macOS that rescans the whole process table while holding the GIL. Measured
    cost: 5,412 -> 58 items/s, a 100x slowdown. The bias direction is what makes it dangerous:
    in-process frameworks (LangGraph, CrewAI) execute inside the harness and would eat that
    penalty, while an external engine like RocketRide would not — an entirely fabricated win.

    Fixed by one process-table scan per decimated discovery cycle, plus running the sampler in a
    separate process. This test fails the build if either regresses.
    """
    print("\nT10 observer effect (collector must not perturb the measurement)")
    from harness.collector_proc import ProcessCollector

    # The batch must run long enough for the result to mean something. A first version used 200
    # near-zero items (~30 ms) and swung +/-43% between repeats — it would have "passed" while
    # being blind to any real regression. Sized here for ~1.5 s per repeat, median of 3, and the
    # run-to-run spread is reported so the tolerance can be judged against actual noise.
    N = 1500

    async def _timed(with_collector: bool) -> float:
        spec = WorkloadSpec(n_items=N, kernel=Kernel.GIL_BOUND, seed=9,
                            size_median=45, size_sigma=0.1, size_cap=80)
        items = generate(spec)
        a = ProcessPoolAdapter(max_workers=10)
        await a.setup()
        col = None
        if with_collector:
            col = ProcessCollector(RESULTS / "observer" / "s.jsonl",
                                   {"h": {"pids": [os.getpid()]}}, interval_s=0.10)
            col.start()
        t = time.perf_counter()
        await a.run_batch(items, 10)
        d = time.perf_counter() - t
        if col:
            col.stop()
        await a.teardown()
        return N / d

    reps = 3
    off_runs = [await _timed(False) for _ in range(reps)]
    on_runs = [await _timed(True) for _ in range(reps)]
    off, on = sorted(off_runs)[reps // 2], sorted(on_runs)[reps // 2]
    overhead = (off - on) / off
    noise = (max(off_runs) - min(off_runs)) / off
    print(f"      collector off: {off:8.1f} items/s (spread {noise*100:.1f}%)"
          f"   on: {on:8.1f} items/s")
    check("T10 out-of-process collector overhead under 15%", overhead < 0.15,
          f"{overhead * 100:+.1f}% throughput change (median of {reps})")
    check("T10b baseline noise low enough for that tolerance to be meaningful", noise < 0.15,
          f"off-run spread {noise * 100:.1f}% — must stay below the 15% tolerance")
    return overhead


async def measure_ipc_floor() -> float:
    """Per-task process-boundary cost, measured directly. Used to size real workloads."""
    print("\nT9 process-boundary overhead floor")
    spec = WorkloadSpec(n_items=200, kernel=Kernel.GIL_BOUND, seed=9, size_median=1,
                        size_sigma=0.01, size_cap=2)
    adapter = ProcessPoolAdapter(max_workers=10)
    cfg = RunConfig(run_id="ipc_floor", adapter_name="processpool", concurrency=10,
                    workload=spec, out_dir=RESULTS, verify_correctness=False)
    res = await Runner(adapter, cfg).run()
    per_task_ms = res.latency_ms["service"]["p50"]
    print(f"      near-zero-work task p50 service time: {per_task_ms:.2f} ms")
    check("T9 process-boundary floor measured", per_task_ms > 0,
          f"{per_task_ms:.2f} ms per task — workloads must be sized well above this")
    return per_task_ms


# --------------------------------------------------------------------------- main
async def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    # Pin BLAS threading: without this each pool worker starts one BLAS thread per core and the
    # run measures thread thrash rather than the execution model.
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(k, "1")

    print("=" * 74)
    print("benchmark-A Phase 1 self-test")
    print("=" * 74)

    test_collector_tree_accounting()
    test_determinism()
    test_fault_rates()
    test_correctness_detection()
    await test_adapters_and_isolation()
    ratios = await test_gil_signature()
    overhead = await test_observer_effect()
    floor_ms = await measure_ipc_floor()

    calib = RESULTS / "calibration.json"
    calib.write_text(json.dumps({
        "collector_observer_overhead_fraction": round(overhead, 4),
        "process_boundary_floor_ms_p50": round(floor_ms, 4),
        "gil_bound_process_over_thread_ratio": {k: round(v, 4) for k, v in ratios["gil_bound_ratios"].items()},
        "gil_free_process_over_thread_ratio": {k: round(v, 4) for k, v in ratios["gil_free_ratios"].items()},
        "note": "Workload item sizes for real runs must sit well above the process-boundary "
                "floor, or any process-isolated engine (including RocketRide) is measured on "
                "IPC overhead rather than on its scheduler.",
    }, indent=2))
    print(f"\n[calibration] written -> {calib}")

    print("\n" + "=" * 74)
    failed = [c for c in _checks if c[1] == FAIL]
    print(f"{len(_checks) - len(failed)}/{len(_checks)} checks passed")
    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name} — {detail}")
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
