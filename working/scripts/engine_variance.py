#!/usr/bin/env python3
"""STEP 3 — does RocketRide's +/-35% survive the full variance protocol?

The engine's variance was measured BEFORE the protocol existed: no warmup discard, n=1 per
configuration, sequential order. On the LlamaIndex service, discarding the first two iterations
took spread from 17.7% to 1.7% — so the obvious hypothesis is that the engine's variance is the
same artefact.

This re-measures it properly:
  * 2 warmup iterations discarded per configuration
  * n=5 measured repetitions
  * randomised order across driver counts (fixed seed)
  * cooldown between repetitions
  * spread reported and gated at 10%

Either answer is useful. If the spread collapses, every earlier engine number needs a correction
banner. If it survives, the variance is real and unexplained, and that is worth knowing before
anyone publishes an engine throughput figure.

Deliberately uses the SAME trivial pipeline (`probe_minimal.pipe`, webhook -> response_text) and
the SAME multi-process driver as the original measurements, so the only thing that changed is the
protocol.
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo    # noqa: E402
from harness.seeds import seed_for      # noqa: E402

OUT = ROOT / "results" / "engine_variance.json"
N_PER_DRIVER = 1200
CONC = 250
DRIVER_COUNTS = [1, 2, 4]
REPS = 5
WARMUP = 2
COOLDOWN_S = 4.0
GATE = 0.10


def _drive(args) -> dict:
    tag, n, conc = args
    import asyncio as aio
    import json as js

    async def go():
        from rocketride import RocketRideClient
        base = js.loads((ROOT / "pipes" / "probe_minimal.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"evar-{tag}"))
        p = ROOT / "pipes" / "generated" / f"evar_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(js.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        await c.send(tok, "warm", mimetype="text/plain")
        sem = aio.Semaphore(conc)
        ok = 0

        async def one(i):
            nonlocal ok
            async with sem:
                try:
                    await aio.wait_for(c.send(tok, f"i{i}", mimetype="text/plain"), timeout=60)
                    ok += 1
                except Exception:
                    pass

        t0 = time.perf_counter()
        await aio.gather(*(one(i) for i in range(n)), return_exceptions=True)
        wall = time.perf_counter() - t0
        try:
            await aio.wait_for(c.terminate(tok), timeout=30)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return {"ok": ok, "wall": wall, "rate": ok / wall if wall else 0.0}

    return asyncio.run(go())


def one_measurement(ndrivers: int, rep_tag: str) -> float:
    """Aggregate throughput = sum of per-driver rates (their windows overlap)."""
    ctx = mp.get_context("spawn")
    args = [(f"{rep_tag}_{i}", N_PER_DRIVER, CONC) for i in range(ndrivers)]
    with ctx.Pool(ndrivers) as pool:
        res = pool.map(_drive, args)
    return round(sum(r["rate"] for r in res), 1)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    order = [(d, r) for d in DRIVER_COUNTS for r in range(REPS + WARMUP)]
    random.Random(seed_for("enginevariance")).shuffle(order)

    print("=" * 78)
    print(f"STEP 3 — RocketRide variance under the FULL protocol")
    print(f"  n={REPS} measured (+{WARMUP} warmup discarded), randomised order, "
          f"cooldown {COOLDOWN_S}s, gate {GATE*100:.0f}%")
    print("=" * 78)

    # Track which repetition index each driver-count is on, so the first WARMUP measurements for
    # each configuration are discarded regardless of where they land in the shuffled order.
    seen: dict[int, int] = {d: 0 for d in DRIVER_COUNTS}
    raw: dict[int, list[float]] = {d: [] for d in DRIVER_COUNTS}

    eo.preflight("engine-variance")
    for ndrv, _ in order:
        idx = seen[ndrv]
        seen[ndrv] += 1
        val = one_measurement(ndrv, f"d{ndrv}r{idx}")
        raw[ndrv].append(val)
        kind = "warmup " if idx < WARMUP else "measured"
        print(f"  drivers={ndrv}  rep{idx}  {kind}  {val:8.1f}/s", flush=True)
        time.sleep(COOLDOWN_S)
    eo.postflight("engine-variance")

    rows = []
    print("\n  --- results ---")
    for d in DRIVER_COUNTS:
        allv = raw[d]
        warm = allv[:WARMUP]
        kept = allv[WARMUP:]
        med = statistics.median(kept)
        spread = (max(kept) - min(kept)) / max(kept) if max(kept) else 0.0
        spread_all = ((max(allv) - min(allv)) / max(allv)) if max(allv) else 0.0
        rows.append({"drivers": d, "warmup_discarded": warm, "measured": kept,
                     "median": med, "spread_frac": round(spread, 4),
                     "spread_frac_if_warmup_included": round(spread_all, 4),
                     "passes_gate": spread <= GATE})
        print(f"  drivers={d}  median={med:8.1f}/s  spread={spread*100:5.1f}%  "
              f"(with warmup included: {spread_all*100:5.1f}%)  "
              f"gate={'PASS' if spread <= GATE else 'FAIL'}")
        print(f"      warmup discarded: {warm}")
        print(f"      measured        : {kept}")

    worst = max(r["spread_frac"] for r in rows)
    worst_incl = max(r["spread_frac_if_warmup_included"] for r in rows)
    verdict = ("COLLAPSED — the +/-35% was largely the same warmup artefact"
               if worst <= GATE else
               "SURVIVES — variance is real and NOT explained by warmup")
    print(f"\n  worst spread (protocol applied) : {worst*100:.1f}%")
    print(f"  worst spread (warmup included)  : {worst_incl*100:.1f}%")
    print(f"  VERDICT: {verdict}")

    OUT.write_text(json.dumps({"rows": rows, "worst_spread": worst,
                               "worst_spread_with_warmup": worst_incl,
                               "gate": GATE, "verdict": verdict}, indent=2))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
