#!/usr/bin/env python3
"""Null control for the blast leg: two arms, one synthetic service, no difference allowed.

DEFECT #29 (2026-08-16). The two blast legs used different concurrency primitives — a
ThreadPoolExecutor on LlamaIndex, an asyncio.Semaphore on RocketRide — and stamped `submit_ns`
at different points in the request's life. Both capped in-flight work at BLAST_C, so the
concurrency was matched; the clock was not. LlamaIndex stamped at admission (service latency),
RocketRide stamped before the semaphore (queue wait + service). At 10k that printed RocketRide
p50 1120 s against LlamaIndex 2.05 s — a ~550x artifact, biased AGAINST RocketRide.

The defect was invisible to every existing test because each arm was self-consistent. Only a
test that runs BOTH patterns against the SAME synthetic service can see it: any difference in
the reported latency is then instrument, because there is nothing else left for it to be.

The last case deliberately reintroduces the bug and requires the control to fail. A null
control that cannot fail proves nothing.
"""
from __future__ import annotations

import asyncio
import concurrent.futures as cf
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness import metrics_shared as ms  # noqa: E402

N = 48
C = 4
SERVICE_S = 0.02
DRIVER = Path(__file__).resolve().parent.parent / "scripts" / "smoke50_parser_in.py"

_fails: list[str] = []


def check(name, cond, got=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name:52} {got}")
    if not cond:
        _fails.append(name)


def service(_i):
    time.sleep(SERVICE_S)


def pool_arm() -> list[dict]:
    """The LlamaIndex pattern: N items, C threads, stamp where the worker picks the item up."""
    enq = time.time_ns()
    rows = []

    def one(i):
        admit = time.time_ns()
        service(i)
        return {"doc": f"d{i}", "enqueue_ns": enq, "admit_ns": admit, "submit_ns": admit,
                "completion_ns": time.time_ns(), "ok": True, "n_chunks": 1}
    with cf.ThreadPoolExecutor(max_workers=C) as ex:
        rows.extend(ex.map(one, range(N)))
    return rows


def sem_arm(stamp_before_gate: bool) -> list[dict]:
    """The RocketRide pattern: N coroutines, a semaphore of C, stamp inside or outside it."""
    async def go():
        enq = time.time_ns()
        sem = asyncio.Semaphore(C)
        rows = []

        async def one(i):
            row = {"doc": f"d{i}", "enqueue_ns": enq, "ok": True, "n_chunks": 1}
            if stamp_before_gate:
                row["submit_ns"] = time.time_ns()      # the bug: stamped at batch open
            async with sem:
                if not stamp_before_gate:
                    row["admit_ns"] = row["submit_ns"] = time.time_ns()
                await asyncio.sleep(SERVICE_S)
            row["completion_ns"] = time.time_ns()
            rows.append(row)
        await asyncio.gather(*(one(i) for i in range(N)))
        return rows
    return asyncio.run(go())


def p50(rows) -> float:
    return ms.latency(rows, warm_n=0, mode="closed-loop")["p50"]


def main() -> int:
    print("blast symmetry — both arms, one synthetic service, warm_n=0")
    pool, sem = pool_arm(), sem_arm(stamp_before_gate=False)

    # Both patterns serve the identical workload, so both must land near the service time.
    for nm, rows in (("thread pool (LlamaIndex pattern)", pool),
                     ("semaphore (RocketRide pattern)", sem)):
        m = p50(rows)
        check(f"{nm} p50 ~ service time", SERVICE_S <= m < SERVICE_S * 3, f"p50={m:.4f}s")

    # THE NULL CONTROL. Same service, same C, same N — the two must agree.
    a, b = p50(pool), p50(sem)
    check("two arms agree within 50%", abs(a - b) / max(a, b) < 0.5,
          f"pool={a:.4f}s sem={b:.4f}s ratio={max(a,b)/min(a,b):.2f}x")

    # THE CONTROL MUST BE ABLE TO FAIL. Reintroduce the bug; the gap has to reappear.
    broken = p50(sem_arm(stamp_before_gate=True))
    check("stamping before the gate is DETECTED", broken > a * 3,
          f"broken={broken:.4f}s vs pool={a:.4f}s ({broken/a:.1f}x)")

    # Throughput must not notice any of this: its window is completion-to-completion.
    tp_ok = (ms.throughput(sem, 8)["docs_per_s"]
             == ms.throughput([{**r, "submit_ns": r["enqueue_ns"]} for r in sem], 8)["docs_per_s"])
    check("throughput unmoved by the stamp choice (warm_n>0)", tp_ok)

    # Source guard, so the driver cannot drift back while this test keeps passing on its own
    # replicas of the two patterns.
    src = DRIVER.read_text()
    rr = src[src.index("def blast_rocket("):src.index("for arm_name, runner in")]
    check("blast_rocket stamps AFTER `async with sem`",
          rr.index("async with sem") < rr.index("admit_ns"))
    check("blast_rocket sets submit_ns only from admit_ns",
          re.search(r'row\["admit_ns"\]\s*=\s*row\["submit_ns"\]', rr) is not None)
    li = src[src.index("def blast_llama("):src.index("def blast_rocket(")]
    check("blast_llama stamps admit inside the worker",
          "admit = time.time_ns()" in li and '"submit_ns": admit' in li)
    for nm, body in (("blast_llama", li), ("blast_rocket", rr)):
        check(f"{nm} records enqueue_ns too", "enqueue_ns" in body)

    print("\n" + ("ALL PASS" if not _fails else f"{len(_fails)} FAILED: {_fails}"))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
