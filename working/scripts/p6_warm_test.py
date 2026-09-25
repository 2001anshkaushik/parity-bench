#!/usr/bin/env python3
"""P6 laptop test of the driver's opt-in warm symmetry (--warm-sends N --warm-concurrency C), with the fakes of
working/video/test_warmup_distribution.py: on BOTH arms exactly N sends, at most C concurrently, the declared values in
the ledger, the per-arm coverage gates still applied; without the flags the Crossroad 40 policies are unchanged (null
control: a default run must NOT carry the P6 policy).

    p6_warm_test.py  -> exit 0 iff every check passes
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

VID = Path(__file__).resolve().parents[2] / "working" / "video"
sys.path.insert(0, str(VID))
import driver_video as drv  # noqa: E402
import test_warmup_distribution as T  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if not ok else ""))


class Conc:
    """Wraps a fake arm and records the peak number of sends in flight."""
    def __init__(self, arm):
        self.arm, self.now, self.peak = arm, 0, 0
        self.name, self.declared_workers = arm.name, arm.declared_workers

    async def health(self):
        return await self.arm.health()

    async def process(self, blob, name):
        self.now += 1
        self.peak = max(self.peak, self.now)
        try:
            await asyncio.sleep(0.003)
            return await self.arm.process(blob, name)
        finally:
            self.now -= 1


def run(arm, posture, warm, corpus, d, **kw):
    args = SimpleNamespace(skip_warmup=False, corpus_dir=str(corpus), arm=arm.name, leg="blast", blast_concurrency=16, **kw)
    pf = T.pf_for(arm.arm if isinstance(arm, Conc) else arm)
    asyncio.run(drv.run_warmup(args, arm, posture, warm, pf, d, "teststem"))
    return json.loads((d / "warmup_teststem.json").read_text())


def main() -> int:
    for label, mk, posture in (("LlamaIndex, one worker", lambda: T.FakeLIArm(workers=1), drv.Posture("workers", 1, None)),
                               ("RocketRide, one token", lambda: T.FakeRRArm(tokens=1), drv.Posture("parity", 1, None))):
        for n, c in ((2, 2), (16, 16)):
            with tempfile.TemporaryDirectory() as t:
                d = Path(t)
                corpus, warm = T.setup(d, warm_n=2)
                arm = Conc(mk())
                doc = run(arm, posture, warm, corpus, d, warm_sends=n, warm_concurrency=c)
                check(f"{label}, --warm-sends {n} --warm-concurrency {c}: exactly {n} sends", len(doc["sends"]) == n, str(len(doc["sends"])))
                check(f"{label}: at most {c} in flight, and {min(n, c)} reached", arm.peak == min(n, c), f"peak {arm.peak}")
                check(f"{label}: the ledger declares the policy", doc["warm_sends_declared"] == n and doc["warm_concurrency_declared"] == c
                      and "P6 warm symmetry" in doc["policy"], doc["policy"])
                check(f"{label}: every warm row re-sent in turn", [e["row"] for e in doc["sends"]] == [warm[k % 2]["file"] for k in range(n)])
    print("null control: without the flags the Crossroad 40 policy is unchanged")
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = T.setup(d, warm_n=2)
        doc = run(T.FakeLIArm(workers=1), drv.Posture("workers", 1, None), warm, corpus, d)
        check("default LlamaIndex K=16 run: 16 sends, Crossroad 40 policy, no P6 declaration",
              len(doc["sends"]) == 16 and "Crossroad 40" in doc["policy"] and doc.get("warm_sends_declared") is None, doc["policy"])
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = T.setup(d, warm_n=2)
        try:
            run(T.FakeLIArm(workers=2, warm_markers=1), drv.Posture("workers", 2, None), warm, corpus, d, warm_sends=2, warm_concurrency=2)
            raised = False
        except SystemExit:
            raised = True
        check("the LlamaIndex warm-marker gate still applies under the P6 policy (1 of 2 markers -> NOT DONE)", raised)
    print(f"\nP6 warm symmetry: {'PASS' if not FAILS else 'FAIL'} ({len(FAILS)} failing)")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
