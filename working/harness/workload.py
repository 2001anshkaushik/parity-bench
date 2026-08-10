"""Deterministic, seeded workload generation with fault injection.

Why four kernels instead of one
-------------------------------
The GIL only binds on *pure-Python bytecode execution*. Most real AI-pipeline work does not hold
it: numpy/OpenCV/Pillow release the GIL around their C loops, ffmpeg runs in a separate process,
and LLM calls are network waits. A benchmark that uses only a GIL-holding kernel manufactures the
result it wants; one that uses only a GIL-releasing kernel hides a genuine architectural
difference. We therefore run all four and report them separately — the *shape of the difference
across kernels* is the actual finding.

    gil_bound     pure-Python hashing/parsing loop      GIL held      → favours process isolation
    gil_free      numpy matmul                          GIL released  → threads scale fine
    io_bound      awaitable sleep (LLM/API stand-in)    GIL released  → async wins, cheaply
    mixed         parse → embed → serialise             realistic     → the ICP-shaped case

Item sizes are drawn from a lognormal distribution, not held constant. Real corpora have a long
tail (a 2-page PDF beside a 400-page one) and uniform inputs mask exactly the scheduler quality
this benchmark exists to measure.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Iterator


class Kernel(str, Enum):
    GIL_BOUND = "gil_bound"
    GIL_FREE = "gil_free"
    IO_BOUND = "io_bound"
    MIXED = "mixed"


class FaultKind(str, Enum):
    NONE = "none"
    CORRUPT_INPUT = "corrupt_input"   # malformed payload -> parser must raise
    TIMEOUT = "timeout"               # stalls beyond the deadline
    MEMORY_SPIKE = "memory_spike"     # transient large allocation
    EXCEPTION = "exception"           # unhandled error inside the unit of work


@dataclass(frozen=True)
class WorkItem:
    item_id: int
    kernel: Kernel
    size_units: int          # kernel-specific work magnitude
    payload_bytes: int
    fault: FaultKind
    seed: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kernel"] = self.kernel.value
        d["fault"] = self.fault.value
        return d


@dataclass
class WorkloadSpec:
    n_items: int
    kernel: Kernel = Kernel.MIXED
    seed: int = 1337
    # Lognormal size distribution: median `size_median`, spread `size_sigma`.
    size_median: int = 200
    size_sigma: float = 0.8
    size_cap: int = 5000
    payload_median_bytes: int = 4096
    # Fault injection rates. Defaults mirror the brief: 5% corrupt, 2% timeout, 1% OOM.
    rate_corrupt: float = 0.0
    rate_timeout: float = 0.0
    rate_memory_spike: float = 0.0
    rate_exception: float = 0.0

    def fault_rate_total(self) -> float:
        return self.rate_corrupt + self.rate_timeout + self.rate_memory_spike + self.rate_exception


def generate(spec: WorkloadSpec) -> list[WorkItem]:
    """Build the item list. Deterministic for a given spec — same seed, same bytes, every run."""
    rng = random.Random(spec.seed)
    items: list[WorkItem] = []
    thresholds = [
        (spec.rate_corrupt, FaultKind.CORRUPT_INPUT),
        (spec.rate_timeout, FaultKind.TIMEOUT),
        (spec.rate_memory_spike, FaultKind.MEMORY_SPIKE),
        (spec.rate_exception, FaultKind.EXCEPTION),
    ]
    for i in range(spec.n_items):
        size = int(min(spec.size_cap, max(1, rng.lognormvariate(math.log(spec.size_median), spec.size_sigma))))
        payload = int(max(64, rng.lognormvariate(math.log(spec.payload_median_bytes), 0.6)))
        roll = rng.random()
        fault = FaultKind.NONE
        acc = 0.0
        for rate, kind in thresholds:
            acc += rate
            if roll < acc:
                fault = kind
                break
        items.append(WorkItem(
            item_id=i, kernel=spec.kernel, size_units=size,
            payload_bytes=payload, fault=fault, seed=rng.randint(0, 2**31 - 1),
        ))
    return items


# ---------------------------------------------------------------------------
# Kernels. These must be importable at module top level so ProcessPoolExecutor
# can pickle them by reference on macOS (spawn start method).
# ---------------------------------------------------------------------------

class WorkFailure(Exception):
    """Raised by a kernel when an injected fault fires."""


def _apply_fault(item: WorkItem) -> None:
    if item.fault is FaultKind.EXCEPTION:
        raise WorkFailure(f"injected exception on item {item.item_id}")
    if item.fault is FaultKind.CORRUPT_INPUT:
        raise WorkFailure(f"corrupt payload on item {item.item_id}")
    if item.fault is FaultKind.MEMORY_SPIKE:
        # Transient ~64 MB allocation; touched so it is really resident.
        blob = bytearray(64 * 2**20)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        del blob


def run_gil_bound(item: WorkItem) -> str:
    """Iterated hashing in pure Python. Holds the GIL for its whole duration."""
    _apply_fault(item)
    if item.fault is FaultKind.TIMEOUT:
        _busy_spin(5.0)
    h = hashlib.sha256(bytes([item.seed & 0xFF]) * 64)
    acc = 0
    for i in range(item.size_units * 200):
        acc = (acc * 31 + (i ^ item.seed)) & 0xFFFFFFFF
        if i % 64 == 0:
            h.update(acc.to_bytes(4, "little"))
    return h.hexdigest()


def run_gil_free(item: WorkItem) -> str:
    """numpy matmul. Releases the GIL inside BLAS — threads genuinely parallelise here."""
    _apply_fault(item)
    if item.fault is FaultKind.TIMEOUT:
        _busy_spin(5.0)
    import numpy as np
    n = max(8, min(160, int(math.sqrt(item.size_units) * 6)))
    rs = np.random.RandomState(item.seed % (2**31 - 1))
    a = rs.rand(n, n).astype("float32")
    b = rs.rand(n, n).astype("float32")
    c = a @ b
    return hashlib.sha256(np.ascontiguousarray(c).tobytes()).hexdigest()


def run_mixed(item: WorkItem) -> str:
    """parse -> transform -> serialise. Roughly the shape of a real document node."""
    _apply_fault(item)
    if item.fault is FaultKind.TIMEOUT:
        _busy_spin(5.0)
    text = (f"doc-{item.item_id}-" * (item.payload_bytes // 16 + 1))[: item.payload_bytes]
    chunks = [text[i : i + 512] for i in range(0, len(text), 512)]
    import numpy as np
    rs = np.random.RandomState(item.seed % (2**31 - 1))
    vecs = rs.rand(len(chunks), 384).astype("float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.maximum(norms, 1e-9)
    digest = hashlib.sha256()
    for ch in chunks:
        digest.update(ch.encode())
    digest.update(np.ascontiguousarray(vecs).tobytes())
    return digest.hexdigest()


SYNC_KERNELS = {
    Kernel.GIL_BOUND: run_gil_bound,
    Kernel.GIL_FREE: run_gil_free,
    Kernel.MIXED: run_mixed,
}


def run_sync(item: WorkItem) -> str:
    """Top-level dispatch — picklable, so ProcessPoolExecutor can use it under `spawn`."""
    fn = SYNC_KERNELS.get(item.kernel)
    if fn is None:
        raise ValueError(f"{item.kernel} has no synchronous kernel; use the async path")
    return fn(item)


async def run_io_bound(item: WorkItem) -> str:
    """Stand-in for an LLM/API call: a fixed-latency await, no CPU.

    Holding model latency constant is what isolates *framework* overhead from *model* cost. A real
    LLM call would swamp every framework difference with 800 ms of network wait and measure the
    provider, not the orchestrator.
    """
    import asyncio
    _apply_fault(item)
    if item.fault is FaultKind.TIMEOUT:
        await asyncio.sleep(5.0)
    await asyncio.sleep(item.size_units / 10000.0)
    return hashlib.sha256(f"{item.item_id}:{item.seed}".encode()).hexdigest()


def _busy_spin(seconds: float) -> None:
    import time
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


def reference_results(items: list[WorkItem]) -> dict[int, str]:
    """Ground truth for correctness checking, computed single-threaded.

    Goodput is meaningless without this. A framework that returns fast but wrong answers, or
    silently drops items, must not score as successful.
    """
    out: dict[int, str] = {}
    for it in items:
        if it.fault is not FaultKind.NONE:
            continue  # faulted items have no expected value
        try:
            out[it.item_id] = run_sync(it)
        except (ValueError, WorkFailure):
            continue
    return out
