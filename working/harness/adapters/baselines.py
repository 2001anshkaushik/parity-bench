"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
Reference baselines: the Python execution substrates a competent engineer would actually use.

These are Track A's control group. If RocketRide cannot beat an expert-tuned `ProcessPoolExecutor`
on CPU-bound fan-out, the architectural claim does not hold — and we need to know that internally
before a customer discovers it. They also serve as the harness's own test fixture: they need no
external server, so Phase 1 can be validated end-to-end before any framework is installed.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import multiprocessing as mp
import os
import sys
import time
import traceback

from ..workload import Kernel, WorkItem, run_io_bound, run_sync
from .base import Adapter, AdapterInfo, ItemResult


def _now() -> int:
    return time.perf_counter_ns()


def _warm_worker(hold_s: float) -> int:
    """Occupy one pool worker for `hold_s`. Top-level so `spawn` can pickle it by reference."""
    time.sleep(hold_s)
    return os.getpid()


async def _gather_bounded(coros, concurrency: int):
    sem = asyncio.Semaphore(concurrency)

    async def _wrap(c):
        async with sem:
            return await c

    return await asyncio.gather(*(_wrap(c) for c in coros), return_exceptions=True)


class AsyncioAdapter(Adapter):
    """Single-process asyncio with a bounded semaphore.

    The correct choice for I/O-bound work and the honest baseline for it. On CPU-bound kernels it
    is deliberately the *worst* case — one core, GIL-serialised — and we report it as such rather
    than pretending it is what a Python engineer would ship.
    """

    def info(self) -> AdapterInfo:
        return AdapterInfo(name="asyncio", version=sys.version.split()[0], execution_model="asyncio")

    async def run_batch(self, items: list[WorkItem], concurrency: int) -> list[ItemResult]:
        results: list[ItemResult] = []
        sem = asyncio.Semaphore(concurrency)
        batch_submit = _now()

        async def _one(item: WorkItem) -> ItemResult:
            submit = batch_submit
            async with sem:
                start = _now()
                try:
                    if item.kernel is Kernel.IO_BOUND:
                        val = await run_io_bound(item)
                    else:
                        val = run_sync(item)
                    return ItemResult(item.item_id, True, value=val,
                                      submit_ns=submit, start_ns=start, end_ns=_now())
                except Exception as e:
                    return ItemResult(item.item_id, False, error=str(e)[:300],
                                      error_type=type(e).__name__,
                                      submit_ns=submit, start_ns=start, end_ns=_now())

        gathered = await asyncio.gather(*(_one(i) for i in items), return_exceptions=True)
        for item, r in zip(items, gathered):
            if isinstance(r, BaseException):
                results.append(ItemResult(item.item_id, False, error=repr(r)[:300],
                                          error_type=type(r).__name__))
            else:
                results.append(r)
        return results


class ThreadPoolAdapter(Adapter):
    """Thread pool. Scales on GIL-releasing kernels (numpy), flat on GIL-bound ones."""

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers
        self._pool: cf.ThreadPoolExecutor | None = None

    def info(self) -> AdapterInfo:
        return AdapterInfo(name="threadpool", version=sys.version.split()[0],
                           execution_model="thread_pool",
                           extra={"max_workers": self.max_workers})

    async def setup(self) -> None:
        self._pool = cf.ThreadPoolExecutor(max_workers=self.max_workers)

    async def teardown(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    async def run_batch(self, items: list[WorkItem], concurrency: int) -> list[ItemResult]:
        if self._pool is None:
            self._pool = cf.ThreadPoolExecutor(max_workers=self.max_workers or concurrency)
        loop = asyncio.get_running_loop()
        batch_submit = _now()
        sem = asyncio.Semaphore(concurrency)

        async def _one(item: WorkItem) -> ItemResult:
            async with sem:
                start = _now()
                try:
                    val = await loop.run_in_executor(self._pool, run_sync, item)
                    return ItemResult(item.item_id, True, value=val,
                                      submit_ns=batch_submit, start_ns=start, end_ns=_now())
                except Exception as e:
                    return ItemResult(item.item_id, False, error=str(e)[:300],
                                      error_type=type(e).__name__,
                                      submit_ns=batch_submit, start_ns=start, end_ns=_now())

        out = await asyncio.gather(*(_one(i) for i in items), return_exceptions=True)
        return [r if not isinstance(r, BaseException)
                else ItemResult(-1, False, error=repr(r)[:300], error_type=type(r).__name__)
                for r in out]


class ProcessPoolAdapter(Adapter):
    """Process pool — the honest Python answer to CPU-bound fan-out, and the real competitor.

    Uses `spawn` explicitly. macOS defaults to spawn on Python 3.8+, but stating it removes any
    ambiguity about fork-vs-spawn memory accounting: under spawn each worker is a fresh
    interpreter, so worker RSS is genuinely additive rather than copy-on-write shared. That is the
    memory cost RocketRide claims to avoid, and it must be measured, not assumed.

    `max_workers` is capped at core count by default. Oversubscribing processes to match a
    10,000-item concurrency target would be a strawman: no competent engineer spawns 10k
    processes, and doing so to manufacture an OOM would be the exact methodological failure this
    suite exists to avoid.
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or os.cpu_count() or 8
        self._pool: cf.ProcessPoolExecutor | None = None

    def info(self) -> AdapterInfo:
        return AdapterInfo(name="processpool", version=sys.version.split()[0],
                           execution_model="process_pool",
                           extra={"max_workers": self.max_workers, "start_method": "spawn"})

    def pids(self) -> list[int]:
        if self._pool is None:
            return []
        return [p.pid for p in getattr(self._pool, "_processes", {}).values()]

    async def setup(self) -> None:
        ctx = mp.get_context("spawn")
        self._pool = cf.ProcessPoolExecutor(max_workers=self.max_workers, mp_context=ctx)
        # Every worker must actually be spawned before the timed region starts. `spawn` costs
        # ~150 ms of fresh-interpreter startup per worker on macOS; an inadequate warm-up leaks
        # that into the measurement and understates Python by ~100x. (Found exactly that way:
        # the harness reported a 155 ms per-task floor against a pool that really does >17k
        # tasks/s.) A short blocking task per worker forces genuine concurrent occupancy —
        # `map` over a few cheap items does not, since one worker can serve them all.
        futs = [self._pool.submit(_warm_worker, 0.25) for _ in range(self.max_workers)]
        for f in futs:
            f.result(timeout=60)

    async def teardown(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    async def run_batch(self, items: list[WorkItem], concurrency: int) -> list[ItemResult]:
        if self._pool is None:
            await self.setup()
        loop = asyncio.get_running_loop()
        batch_submit = _now()
        sem = asyncio.Semaphore(concurrency)

        async def _one(item: WorkItem) -> ItemResult:
            async with sem:
                start = _now()
                try:
                    val = await loop.run_in_executor(self._pool, run_sync, item)
                    return ItemResult(item.item_id, True, value=val,
                                      submit_ns=batch_submit, start_ns=start, end_ns=_now())
                except Exception as e:
                    # A BrokenProcessPool here is a genuine finding: a worker died and took
                    # unrelated in-flight items with it. That is precisely the fault-isolation
                    # failure mode priority #2 is about, so it is recorded, never retried.
                    return ItemResult(item.item_id, False, error=str(e)[:300],
                                      error_type=type(e).__name__,
                                      submit_ns=batch_submit, start_ns=start, end_ns=_now())

        out = await asyncio.gather(*(_one(i) for i in items), return_exceptions=True)
        return [r if not isinstance(r, BaseException)
                else ItemResult(-1, False, error=repr(r)[:300], error_type=type(r).__name__)
                for r in out]


def _run_chunk(items: list[WorkItem]) -> list[tuple[int, bool, str]]:
    """Execute a batch inside one worker. Top-level for picklability under `spawn`."""
    out: list[tuple[int, bool, str]] = []
    for it in items:
        try:
            out.append((it.item_id, True, run_sync(it)))
        except Exception as e:
            out.append((it.item_id, False, f"{type(e).__name__}: {e}"[:300]))
    return out


class ChunkedProcessPoolAdapter(Adapter):
    """Process pool with per-worker batching — the configuration a competent engineer ships.

    One IPC round-trip per *chunk* rather than per item. At 10,000 items the difference is the
    whole result: per-item dispatch pays 10,000 pickle/pipe round-trips, chunked pays 50. Omitting
    this adapter and reporting only per-item dispatch would be the single easiest way to
    manufacture a RocketRide win, so it is a required member of the baseline set.

    Note the trade-off, which belongs in the report: chunking amortises IPC but *weakens fault
    isolation* — an interpreter crash mid-chunk takes the whole chunk with it, not one item. That
    is a genuine axis on which an engine with per-item isolation can legitimately claim an
    advantage, and it is measurable with our injected faults rather than asserted.
    """

    def __init__(self, max_workers: int | None = None, chunk_size: int = 0):
        self.max_workers = max_workers or os.cpu_count() or 8
        self.chunk_size = chunk_size  # 0 => derive from batch size at run time
        self._pool: cf.ProcessPoolExecutor | None = None

    def info(self) -> AdapterInfo:
        return AdapterInfo(name="processpool_chunked", version=sys.version.split()[0],
                           execution_model="process_pool_chunked",
                           extra={"max_workers": self.max_workers,
                                  "chunk_size": self.chunk_size or "auto",
                                  "start_method": "spawn"})

    def pids(self) -> list[int]:
        if self._pool is None:
            return []
        return [p.pid for p in getattr(self._pool, "_processes", {}).values()]

    async def setup(self) -> None:
        ctx = mp.get_context("spawn")
        self._pool = cf.ProcessPoolExecutor(max_workers=self.max_workers, mp_context=ctx)
        futs = [self._pool.submit(_warm_worker, 0.25) for _ in range(self.max_workers)]
        for f in futs:
            f.result(timeout=60)

    async def teardown(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    async def run_batch(self, items: list[WorkItem], concurrency: int) -> list[ItemResult]:
        if self._pool is None:
            await self.setup()
        loop = asyncio.get_running_loop()
        cs = self.chunk_size or max(1, len(items) // (self.max_workers * 4))
        chunks = [items[i : i + cs] for i in range(0, len(items), cs)]
        batch_submit = _now()

        async def _one(chunk: list[WorkItem]) -> list[ItemResult]:
            start = _now()
            try:
                triples = await loop.run_in_executor(self._pool, _run_chunk, chunk)
                end = _now()
                return [ItemResult(iid, ok, value=v if ok else None,
                                   error=None if ok else v,
                                   error_type=None if ok else v.split(":")[0],
                                   submit_ns=batch_submit, start_ns=start, end_ns=end)
                        for iid, ok, v in triples]
            except Exception as e:
                end = _now()
                # Whole-chunk loss — the isolation cost of batching, recorded honestly.
                return [ItemResult(it.item_id, False, error=str(e)[:300],
                                   error_type=type(e).__name__,
                                   submit_ns=batch_submit, start_ns=start, end_ns=end)
                        for it in chunk]

        gathered = await asyncio.gather(*(_one(c) for c in chunks), return_exceptions=True)
        out: list[ItemResult] = []
        for g in gathered:
            if isinstance(g, BaseException):
                out.append(ItemResult(-1, False, error=repr(g)[:300], error_type=type(g).__name__))
            else:
                out.extend(g)
        return out


BASELINES = {
    "asyncio": AsyncioAdapter,
    "threadpool": ThreadPoolAdapter,
    "processpool": ProcessPoolAdapter,
    "processpool_chunked": ChunkedProcessPoolAdapter,
}
