"""Framework-agnostic benchmark runner.

Load models
-----------
**closed_loop** — a bounded number of items in flight; a new one is admitted only as one
completes. Measures *service latency*: how long the system takes to do one unit of work. This is
the mode for latency claims.

**open_loop** — items are submitted on a schedule regardless of whether the system is keeping up.
Measures what happens under backpressure: queues grow, latency becomes dominated by queue wait.
Per-item latency here is **batch-position latency, not service latency** — Leela's team already
published a run where this distinction had to be added as a limitation after the fact
(`findings/limitations.md` #3). The runner labels the mode in every result row so the two can
never be silently mixed in analysis.
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

from . import stats
from .adapters.base import Adapter, ItemResult
from .collector_proc import ProcessCollector
from .env_capture import capture as capture_env, thermal_state
from .workload import FaultKind, WorkItem, WorkloadSpec, generate, reference_results

LoadMode = Literal["closed_loop", "open_loop"]


@dataclass
class RunConfig:
    run_id: str
    adapter_name: str
    concurrency: int
    workload: WorkloadSpec
    load_mode: LoadMode = "closed_loop"
    open_loop_rate_per_s: float | None = None
    repetitions: int = 1
    rss_ceiling_bytes: int | None = None
    enforce_ceiling: bool = False
    verify_correctness: bool = True
    collector_interval_s: float = 0.10
    warmup_items: int = 0
    out_dir: Path = Path("results")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["workload"] = {**asdict(self.workload), "kernel": self.workload.kernel.value}
        d["out_dir"] = str(self.out_dir)
        return d


@dataclass
class RunResult:
    run_id: str
    adapter: dict
    config: dict
    env: dict
    wall_seconds: float
    setup_seconds: float
    counts: dict
    latency_ms: dict
    throughput: dict
    resources: dict
    faults: dict
    cost: dict
    errors_by_type: dict
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Runner:
    def __init__(self, adapter: Adapter, config: RunConfig):
        self.adapter = adapter
        self.config = config

    async def run(self) -> RunResult:
        cfg = self.config
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []

        items = generate(cfg.workload)
        expected = reference_results(items) if cfg.verify_correctness else {}

        info = self.adapter.info()
        if not info.is_local:
            notes.append(
                "Adapter calls a hosted service: Track A (execution substrate) comparison is "
                "INVALID for this run — network latency and remote hardware dominate."
            )

        env = capture_env()
        gc.collect()

        t_setup = time.perf_counter()
        await self.adapter.setup()
        setup_s = time.perf_counter() - t_setup

        if cfg.warmup_items:
            warm = items[: cfg.warmup_items]
            try:
                await self.adapter.run_batch(warm, min(cfg.concurrency, len(warm)))
            except Exception as e:
                notes.append(f"warmup raised {type(e).__name__}: {e}")

        # Roles are resolved *after* setup: before it, a pool has no workers and an engine client
        # has no connection, so the spec would be empty. Declarative form (pids / cmdline pattern)
        # so it survives the process boundary into the out-of-process collector.
        roles_spec: dict = {"harness": {"pids": [os.getpid()]}}
        ext = [p for p in self.adapter.pids() if p != os.getpid()]
        if ext:
            roles_spec["adapter_external"] = {"pids": ext}
        if info.extra.get("process_pattern"):
            roles_spec["engine"] = {"pattern": info.extra["process_pattern"]}

        collector = ProcessCollector(
            out_path=cfg.out_dir / f"{cfg.run_id}_samples.jsonl",
            roles_spec=roles_spec,
            interval_s=cfg.collector_interval_s,
            rss_ceiling_bytes=cfg.rss_ceiling_bytes,
            enforce_ceiling=cfg.enforce_ceiling,
        )

        crashed = False
        crash_error = None
        results: list[ItemResult] = []

        collector.start()
        t0 = time.perf_counter()
        try:
            if cfg.load_mode == "open_loop" and cfg.open_loop_rate_per_s:
                results = await self._run_open_loop(items, cfg)
            else:
                results = await self.adapter.run_batch(items, cfg.concurrency)
        except BaseException as e:
            # A hard failure of the whole batch IS the finding for priority #1/#2 — record it as
            # data rather than letting the harness die with it.
            crashed = True
            crash_error = f"{type(e).__name__}: {e}\n{traceback.format_exc()[:2000]}"
            notes.append("ADAPTER CRASHED — whole-batch failure recorded, not retried.")
        wall = time.perf_counter() - t0
        collector.stop()

        try:
            await self.adapter.teardown()
        except Exception as e:
            notes.append(f"teardown raised {type(e).__name__}: {e}")

        env["thermal_after"] = thermal_state()

        summary = self._summarise(
            items, results, expected, wall, setup_s, collector, cfg, info, env,
            crashed, crash_error, notes,
        )

        with (cfg.out_dir / f"{cfg.run_id}_result.json").open("w") as f:
            json.dump(summary.to_dict(), f, indent=2, default=str)
        with (cfg.out_dir / f"{cfg.run_id}_items.jsonl").open("w") as f:
            for r in results:
                f.write(json.dumps({
                    "item_id": r.item_id, "ok": r.ok, "error_type": r.error_type,
                    "latency_ms": round(r.latency_ms, 4), "service_ms": round(r.service_ms, 4),
                }, separators=(",", ":")) + "\n")
        return summary

    async def _run_open_loop(self, items: list[WorkItem], cfg: RunConfig) -> list[ItemResult]:
        """Submit at a fixed arrival rate irrespective of completion. Backpressure test."""
        interval = 1.0 / cfg.open_loop_rate_per_s
        tasks: list[asyncio.Task] = []
        sem = asyncio.Semaphore(cfg.concurrency)

        async def _submit(item: WorkItem):
            async with sem:
                out = await self.adapter.run_batch([item], 1)
                return out[0] if out else ItemResult(item.item_id, False, error="no result")

        start = time.perf_counter()
        for idx, item in enumerate(items):
            target = start + idx * interval
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(_submit(item)))
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        return [g if not isinstance(g, BaseException)
                else ItemResult(-1, False, error=repr(g)[:300], error_type=type(g).__name__)
                for g in gathered]

    def _summarise(self, items, results, expected, wall, setup_s, collector, cfg, info, env,
                   crashed, crash_error, notes) -> RunResult:
        by_id = {r.item_id: r for r in results if r.item_id >= 0}
        faulted_ids = {i.item_id for i in items if i.fault is not FaultKind.NONE}
        clean_ids = {i.item_id for i in items} - faulted_ids

        returned = len(by_id)
        missing = len(items) - returned
        ok = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]

        # Goodput: correct AND verified, restricted to items that were never meant to fail.
        correct = 0
        wrong = 0
        for iid in clean_ids:
            r = by_id.get(iid)
            if r is None or not r.ok:
                continue
            if expected:
                if r.value == expected.get(iid):
                    correct += 1
                else:
                    wrong += 1
            else:
                correct += 1

        # Fault isolation: clean items that died anyway. This is the collateral-damage number,
        # and it is the sharpest single measure of whether failures cascade.
        collateral = sum(1 for iid in clean_ids if (r := by_id.get(iid)) is not None and not r.ok)
        collateral += sum(1 for iid in clean_ids if iid not in by_id)
        n_faults = len(faulted_ids)
        isolation_ratio = (collateral / n_faults) if n_faults else 0.0

        lat = [r.latency_ms for r in results if r.ok]
        svc = [r.service_ms for r in results if r.ok]
        col = collector.summary()

        total_rss = sum(v["peak_rss_bytes"] for v in col["roles"].values())
        total_cpu = sum(v["total_cpu_seconds"] for v in col["roles"].values())
        n_done = max(1, correct)

        errors_by_type: dict[str, int] = {}
        for r in failed:
            errors_by_type[r.error_type or "unknown"] = errors_by_type.get(r.error_type or "unknown", 0) + 1

        if cfg.load_mode == "open_loop":
            notes.append("OPEN LOOP: latency values are batch-position latency (queue wait "
                         "included), NOT service latency. Do not compare against closed-loop runs.")

        return RunResult(
            run_id=cfg.run_id,
            adapter={"name": info.name, "version": info.version,
                     "execution_model": info.execution_model,
                     "is_local": info.is_local, "extra": info.extra},
            config=cfg.to_dict(),
            env=env,
            wall_seconds=round(wall, 4),
            setup_seconds=round(setup_s, 4),
            counts={
                "submitted": len(items), "returned": returned, "missing": missing,
                "succeeded": len(ok), "failed": len(failed),
                "injected_faults": n_faults,
                "verified_correct": correct, "verified_wrong": wrong,
                "crashed": crashed, "crash_error": crash_error,
            },
            latency_ms={
                "mode": cfg.load_mode,
                "end_to_end": stats.describe(lat).to_dict(),
                "service": stats.describe(svc).to_dict(),
            },
            throughput={
                "items_per_s": round(len(ok) / wall, 3) if wall else None,
                "goodput_per_s": round(correct / wall, 3) if wall else None,
                "wall_seconds": round(wall, 4),
            },
            resources=col,
            faults={
                "injected": n_faults,
                "collateral_failures": collateral,
                "isolation_ratio_collateral_per_fault": round(isolation_ratio, 4),
                "cascade_detected": collateral > 0,
            },
            cost={
                "peak_rss_all_roles_bytes": total_rss,
                "peak_rss_all_roles_mb": round(total_rss / 2**20, 2),
                "total_cpu_seconds_all_roles": round(total_cpu, 4),
                "cpu_seconds_per_1k_items": round(total_cpu / n_done * 1000, 4),
                "peak_rss_mb_per_1k_items": round(total_rss / 2**20 / n_done * 1000, 4),
            },
            errors_by_type=errors_by_type,
            notes=notes,
        )
