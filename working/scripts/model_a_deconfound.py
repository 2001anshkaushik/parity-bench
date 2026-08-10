#!/usr/bin/env python3
"""STEP 4 — Model A fault isolation, deconfounded.

The previous Model A cells were unusable: ~50 s of pipeline setup sat INSIDE the timed region, so
a 20 s per-item deadline fired while the engine was still launching pipelines. Essentially every
clean item timed out regardless of any injected fault, producing meaningless ratios of 32 and 49.
The tell was `collateral_wrong_output = 0` everywhere — nothing corrupted, everything just late.

Fixed here:
  * all `use()` calls complete, and the engine is confirmed healthy and quiet, BEFORE timing
  * a settle window lets task trees finish spawning
  * the deadline starts at FIRST SEND, not at setup
  * a control run with zero injected faults establishes the floor: if the control already loses
    clean items, Model A cannot be measured on this host and is reported as unmeasurable rather
    than as a fault-isolation number.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo   # noqa: E402
from harness.seeds import seed_for     # noqa: E402

OUT = ROOT / "results" / "model_a"
# DOWNSCALED from n=100 to n=50, stated not dropped. A zero-fault control at n=100 scored 0 %
# goodput inside a 20 s deadline even with setup fully excluded: the engine's per-send latency
# grows steeply with the number of LIVE task trees (measured control walls: n=5 -> 0.01 s,
# n=20 -> 2.17 s, n=50 -> 12.78 s, n=100 -> >20 s). n=50 is the largest size where a zero-fault
# control passes, so it is the largest size at which fault isolation can be attributed to faults
# rather than to load. Deadline widened to 45 s to leave headroom above the 12.8 s control.
N = 50
RATE = 0.05
DEADLINE = 45.0
FILLER = "x" * 64
SETTLE_S = 5.0


def digest(i: str) -> str:
    return hashlib.sha256(f"{i}|{FILLER}".encode()).hexdigest()


def plan(fault: str, rate: float):
    import random
    rng = random.Random(seed_for("modelA", fault, rate, N))
    return [(str(i), fault if rng.random() < rate else "ok") for i in range(N)]


async def run(fault: str, rate: float) -> dict:
    from rocketride import RocketRideClient

    items = plan(fault, rate)
    base = json.loads((ROOT / "pipes" / "fault_probe.pipe").read_text())
    gen = ROOT / "pipes" / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, _ in items:
        spec = dict(base)
        spec["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mA-dec-{fault}-{rate}-{i}"))
        p = gen / f"mAd_{fault}_{int(rate*1000)}_{i}.pipe"
        p.write_text(json.dumps(spec))
        paths.append(str(p.relative_to(ROOT)))

    c = RocketRideClient()
    await c.connect(timeout=30000)

    # ---------- SETUP: entirely outside the timed region ----------
    t_setup = time.perf_counter()
    used = await asyncio.gather(*(c.use(filepath=p) for p in paths), return_exceptions=True)
    setup_s = time.perf_counter() - t_setup
    tokens = {}
    for (iid, _), u in zip(items, used):
        if isinstance(u, dict) and "token" in u:
            tokens[iid] = u["token"]
    await asyncio.sleep(SETTLE_S)              # let task trees finish spawning
    healthy_before = eo.healthy(20)
    quiet = eo.counts()

    results: dict[str, tuple[bool, str | None]] = {}
    fmap = dict(items)

    # ---------- TIMED REGION starts at first send ----------
    t0 = time.perf_counter()
    dl = t0 + DEADLINE

    async def one(iid: str, tok: str):
        rem = dl - time.perf_counter()
        if rem <= 0:
            results[iid] = (False, None); return
        try:
            resp = await asyncio.wait_for(
                c.send(tok, f"FP|{iid}|{fmap[iid]}|{FILLER}", mimetype="text/plain"), timeout=rem)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                results[iid] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                results[iid] = (True, txt[0].strip() if isinstance(txt, list) and txt else None)
        except Exception:
            results[iid] = (False, None)

    await asyncio.gather(*(one(i, t) for i, t in tokens.items()), return_exceptions=True)
    wall = time.perf_counter() - t0
    # ---------- TIMED REGION ends ----------

    healthy_after = eo.healthy(20)
    if healthy_after:
        await asyncio.gather(*(asyncio.wait_for(c.terminate(t), timeout=30)
                               for t in tokens.values()), return_exceptions=True)
    try:
        await c.disconnect()
    except Exception:
        pass

    injected = [i for i, f in items if f != "ok"]
    clean = [i for i, f in items if f == "ok"]
    failed = missing = wrong = good = 0
    for i in clean:
        r = results.get(i)
        if r is None:
            missing += 1
        elif not r[0]:
            failed += 1
        elif r[1] != digest(i):
            wrong += 1
        else:
            good += 1
    collateral = failed + missing + wrong
    return {
        "fault": fault, "rate": rate, "tasks_created": len(tokens),
        "setup_s_excluded": round(setup_s, 2), "settle_s": SETTLE_S,
        "healthy_before_timing": healthy_before,
        "node_procs_at_start": quiet["node_procs"],
        "n_injected": len(injected), "n_clean": len(clean), "returned": len(results),
        "collateral_failed": failed, "collateral_missing": missing,
        "collateral_wrong_output": wrong, "collateral_total": collateral,
        "isolation_ratio": round(collateral / len(injected), 4) if injected else None,
        "goodput_pct": round(100.0 * good / max(1, len(clean)), 2),
        "timed_wall_s": round(wall, 3), "engine_healthy_after": healthy_after,
    }


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("=" * 74)
    print("STEP 4 — MODEL A DECONFOUNDED (setup excluded, deadline starts at first send)")
    print("=" * 74)

    # Control first: zero faults. If clean items already die here, Model A is unmeasurable.
    eo.preflight("modelA control")
    ctrl = await run("raise", 0.0)
    rows.append({"cell": "control_no_faults", **ctrl})
    print(f"  CONTROL (0 faults): tasks={ctrl['tasks_created']} setup={ctrl['setup_s_excluded']}s "
          f"timed={ctrl['timed_wall_s']}s goodput={ctrl['goodput_pct']}% "
          f"collateral={ctrl['collateral_total']}", flush=True)
    eo.postflight("modelA control")

    if ctrl["goodput_pct"] < 95.0:
        print(f"\n  *** CONTROL FAILED ({ctrl['goodput_pct']}% goodput with ZERO faults) ***")
        print("  Model A is UNMEASURABLE on this host: clean items are lost without any fault.")
        rows.append({"verdict": "UNMEASURABLE",
                     "reason": f"control goodput {ctrl['goodput_pct']}% with zero injected faults"})
        (OUT / "model_a_deconfounded.json").write_text(json.dumps(rows, indent=2, default=str))
        return 0

    for fault in ("raise", "hang", "alloc", "malformed"):
        eo.preflight(f"modelA {fault}")
        r = await run(fault, RATE)
        rows.append({"cell": fault, **r})
        print(f"  {fault:10s} inj={r['n_injected']} ret={r['returned']} "
              f"collat={r['collateral_total']} ratio={r['isolation_ratio']} "
              f"good={r['goodput_pct']}% timed={r['timed_wall_s']}s", flush=True)
        (OUT / "model_a_deconfounded.json").write_text(json.dumps(rows, indent=2, default=str))
        eo.postflight(f"modelA {fault}")

    (OUT / "model_a_deconfounded.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nwritten -> {OUT/'model_a_deconfounded.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
