"""Adapter protocol.

Every framework under test implements this and nothing else. The runner, collector and workload
know nothing framework-specific — that separation is what lets an outside reviewer swap in their
own adapter and re-run our exact numbers, which is the whole basis for the results being credible.

Adapter authoring rule (non-negotiable for publication)
------------------------------------------------------
Each adapter must be implemented the way *that framework's own documentation* recommends —
async where the framework is async-native, its own pool abstraction where it has one. Beating a
deliberately naive baseline proves nothing. Before publication every adapter should be reviewed
by someone who actually likes that framework, or posted publicly for correction.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from ..workload import WorkItem


@dataclass
class ItemResult:
    item_id: int
    ok: bool
    value: str | None = None
    error: str | None = None
    error_type: str | None = None
    submit_ns: int = 0
    start_ns: int = 0
    end_ns: int = 0

    @property
    def latency_ms(self) -> float:
        """Time from submission to completion — includes queueing under open-loop load."""
        return (self.end_ns - self.submit_ns) / 1e6

    @property
    def service_ms(self) -> float:
        """Time actually spent executing, excluding queue wait. Only meaningful closed-loop."""
        return (self.end_ns - self.start_ns) / 1e6


@dataclass
class AdapterInfo:
    """Provenance for the results file. Every field lands in the published record."""

    name: str
    version: str | None = None
    execution_model: str = "unknown"      # e.g. "asyncio", "process_pool", "external_engine"
    is_local: bool = True                 # False => calls a hosted API; not comparable in Track A
    extra: dict[str, Any] = field(default_factory=dict)


class Adapter(abc.ABC):
    """Base class for a framework under test."""

    #: Set False for adapters that call a hosted service — they belong in Track B only.
    is_local: bool = True

    @abc.abstractmethod
    def info(self) -> AdapterInfo:
        ...

    def pids(self) -> list[int]:
        """PIDs of processes doing this adapter's work, *excluding* the harness process.

        In-process frameworks return []. External engines (RocketRide) return the engine roots so
        the collector can walk their trees. Getting this wrong is the single easiest way to
        produce an invalid memory comparison — see collector.py note 1.
        """
        return []

    async def setup(self) -> None:
        """One-time cost: build the graph, start the pool, connect the client. Not timed."""

    async def teardown(self) -> None:
        ...

    @abc.abstractmethod
    async def run_batch(self, items: list[WorkItem], concurrency: int) -> list[ItemResult]:
        """Execute every item, honouring `concurrency` as the max in-flight limit.

        Must return one ItemResult per input item, including failures. Swallowing a failure and
        returning a short list is the bug this signature exists to prevent.
        """
