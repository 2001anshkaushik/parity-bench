"""Fault injection with CORRECT accounting — drop-in, stdlib only.

The accounting is the point. Most poison-run harnesses report "it survived" without separating
the faults they injected from the damage those faults caused, and without checking that the
survivors are actually correct. Both omissions flatter the system under test.

    injected                    faults deliberately introduced
    collateral_failed           CLEAN items that returned an error
    collateral_missing          CLEAN items that never returned
    collateral_wrong_output     CLEAN items that returned the WRONG value   <-- usually omitted
    isolation_ratio             collateral_total / injected                 <-- the headline
    goodput_pct                 verified-correct clean items / clean items

`collateral_wrong_output` is the one people leave out and the one that matters most: a framework
that stays up while silently corrupting survivors would otherwise score as perfectly isolating.

TWO METHODOLOGY TRAPS THIS MODULE EXISTS TO PREVENT (both produced false verdicts for us):

1. ONE wall-clock deadline from batch start, enforced identically for every framework.
   We had `ProcessPoolExecutor` calling `fut.result(timeout=...)` inside `as_completed()`, which
   only sees ALREADY-COMPLETED futures — the deadline never fired, it ran to 100 s against a 20 s
   budget for everyone else, and scored a fictitious perfect 0.00. Separately an asyncio path
   started its timer on semaphore acquisition rather than batch start, granting it a longer
   effective deadline. Both differences vanished once the deadline was made symmetric.

2. ALWAYS run a zero-fault control. Ours reported isolation ratios of 32 and 49 that were pure
   artefact: setup cost sat inside the timed region, so clean items timed out with no fault
   involved. A control with zero injected faults scores 0% goodput in that situation and catches
   it immediately. If the control does not pass at ~100%, the configuration cannot measure
   isolation at all and the numbers must be discarded.

Seeding uses seeds.py (sha256), not hash() — see that module for why.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field

from seeds import seed_for

FAULT_CLASSES = ("raise", "hang", "alloc", "alloc_hold", "malformed")


@dataclass
class Plan:
    items: list[tuple[str, str]]          # (item_id, fault) — "ok" for clean
    seed: int
    injected: int
    fingerprint: str


def make_plan(n: int, fault: str, rate: float, tag: str = "default") -> Plan:
    """Deterministic fault plan. Same (n, fault, rate, tag) -> same plan, on any machine."""
    seed = seed_for("faultplan", tag, fault, rate, n)
    rng = random.Random(seed)
    items = [(str(i), fault if rng.random() < rate else "ok") for i in range(n)]
    fp = hashlib.sha256(repr(items).encode()).hexdigest()[:16]
    return Plan(items=items, seed=seed, injected=sum(1 for _, f in items if f != "ok"),
                fingerprint=fp)


def reference(item_id: str, filler: str = "") -> str:
    """Ground truth for goodput verification. Replace with your workload's real reference
    (for mt10k: the offline reference vectors)."""
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


@dataclass
class Deadline:
    """ONE wall-clock deadline from batch start. Ask it for `remaining()` per item."""
    seconds: float
    _t0: float = field(default_factory=time.perf_counter)

    def remaining(self) -> float:
        return self.seconds - (time.perf_counter() - self._t0)

    def expired(self) -> bool:
        return self.remaining() <= 0

    def elapsed(self) -> float:
        return time.perf_counter() - self._t0


def score(plan: Plan, results: dict[str, tuple[bool, str | None]], wall: float,
          reference_fn=reference, extra: dict | None = None) -> dict:
    """results: item_id -> (ok, value_or_None). Every submitted item must appear or be absent;
    absence is counted as `collateral_missing`, never silently ignored."""
    clean = [i for i, f in plan.items if f == "ok"]
    failed = missing = wrong = good = 0
    for i in clean:
        r = results.get(i)
        if r is None:
            missing += 1
        elif not r[0]:
            failed += 1
        elif r[1] != reference_fn(i):
            wrong += 1
        else:
            good += 1
    collateral = failed + missing + wrong
    return {
        "seed": plan.seed, "plan_fingerprint": plan.fingerprint,
        "n_items": len(plan.items), "n_injected": plan.injected, "n_clean": len(clean),
        "returned": len(results), "batch_completed": len(results) == len(plan.items),
        "collateral_failed": failed, "collateral_missing": missing,
        "collateral_wrong_output": wrong, "collateral_total": collateral,
        "isolation_ratio": round(collateral / plan.injected, 4) if plan.injected else 0.0,
        "goodput_pct": round(100.0 * good / max(1, len(clean)), 2),
        "wall_s": round(wall, 3), **(extra or {}),
    }


def control_passed(control_result: dict, threshold: float = 95.0) -> bool:
    """Gate: a zero-fault control MUST pass before any fault cell is believable."""
    return control_result.get("goodput_pct", 0.0) >= threshold
