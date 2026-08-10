#!/usr/bin/env python3
"""ITEM A2, part 2 — the symmetric sustained treatment the original never ran.

`burst_vs_sustained.py` applied a 10-burst continuous load to RocketRide ONLY. No LlamaIndex arm
was ever subjected to the same treatment, so "RocketRide decays 31 %" had no control: a host-level
effect would have produced exactly the same reading.

`decay_rootcause.py` PHASE 2 interleaves the arms, which controls the host timeline perfectly but
weakens the sustained condition — each arm rests while the other runs. This script supplies the
missing like-for-like: CONTINUOUS 20-burst sequences, both arms, same document, same concurrency,
same burst size, randomised order, n=3 sequences per arm, cooldown between sequences so each
starts from a comparable host state.

Reading:
  * both arms decay similarly  -> the decay is the HOST, and the engine is exonerated
  * only RocketRide decays     -> the decay is real and engine-specific
  * neither decays             -> the cooldown between sequences is what matters; the original
                                  measured a cold-start transient, not sustained decay
Position-in-session is recorded for every sequence, so a session-drift effect (rule 3 null
control) shows up as decay tracking position rather than arm.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo          # noqa: E402
from harness.seeds import seed_for            # noqa: E402
from scripts.decay_rootcause import (          # noqa: E402
    RRArm, LIArm, decay_of, engine_rss_mb, start_ws1, BURSTS, PER_BURST, CONC,
)

OUT = ROOT / "results" / "decay_symmetric.json"
SEQS_PER_ARM = 3
COOLDOWN = 45.0


async def sequence(arm: str, idx: int, pos: int) -> dict:
    """One continuous 20-burst sequence on a single arm — no cooldown inside."""
    if arm == "rocketride":
        a = RRArm(f"sym{idx}")
        await a.connect()
        await a.new_task()
    else:
        a = LIArm()
        await a.connect()

    rows = []
    for b in range(BURSTS):
        r = await a.burst(n=PER_BURST, conc=CONC)
        rss, _ = engine_rss_mb()
        r.update(burst=b + 1, rss_mb=rss)
        rows.append(r)
    if arm == "rocketride":
        await a.drop_task()
    await a.disconnect()

    rates = [r["rate"] for r in rows]
    out = {"arm": arm, "seq": idx, "session_position": pos, "bursts": rows,
           "decay_pct": decay_of(rates),
           "first3": round(statistics.median(rates[:3]), 2),
           "last3": round(statistics.median(rates[-3:]), 2),
           "fail": sum(r["fail"] for r in rows),
           "rss_start": rows[0]["rss_mb"], "rss_end": rows[-1]["rss_mb"]}
    print(f"    [{pos:2d}] {arm:11s} seq{idx}: {out['first3']:7.2f} -> {out['last3']:7.2f}/s   "
          f"decay {out['decay_pct']:+6.1f}%   fail={out['fail']}   "
          f"rss {out['rss_start']:.0f}->{out['rss_end']:.0f}MB", flush=True)
    return out


async def amain() -> dict:
    plan = [("rocketride", i) for i in range(SEQS_PER_ARM)] + \
           [("llamaindex", i) for i in range(SEQS_PER_ARM)]
    random.Random(seed_for("decaysym")).shuffle(plan)
    print(f"  randomised order: {[a for a, _ in plan]}\n")
    seqs = []
    for pos, (arm, idx) in enumerate(plan):
        seqs.append(await sequence(arm, idx, pos))
        if pos < len(plan) - 1:
            await asyncio.sleep(COOLDOWN)
    return {"sequences": seqs}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    eo.preflight("decay-symmetric")
    print("=" * 96)
    print("ITEM A2 part 2 — SYMMETRIC continuous sustained treatment, both arms, n=3, randomised")
    print("=" * 96)
    ws1 = start_ws1()
    print("  ws1 up (cpu, 8 workers)")
    res = {}
    try:
        res = asyncio.run(amain())
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("decay-symmetric")
        OUT.write_text(json.dumps(res, indent=1))
        print(f"\nwritten -> {OUT}")

    seqs = res.get("sequences", [])
    print("\n" + "=" * 96)
    for arm in ("rocketride", "llamaindex"):
        d = [s["decay_pct"] for s in seqs if s["arm"] == arm]
        f = [s["fail"] for s in seqs if s["arm"] == arm]
        if not d:
            continue
        print(f"  {arm:11s} decay per sequence: {[f'{x:+.1f}%' for x in d]}   "
              f"median {statistics.median(d):+.1f}%   spread {max(d) - min(d):.1f}pp   "
              f"failures {sum(f)}")
    # null control: does decay track session position rather than arm?
    print("\n  null control — decay vs session position "
          "(a position trend with no arm split would mean session drift):")
    for s in sorted(seqs, key=lambda x: x["session_position"]):
        print(f"    pos {s['session_position']}: {s['arm']:11s} {s['decay_pct']:+6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
