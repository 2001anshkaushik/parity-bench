#!/usr/bin/env python3
"""STEP 2 (corrected instrument) — barrier-synchronised, fixed-duration measurement windows.

`concurrency_parity.py` still failed the 10 % variance gate on almost every cell (12-58 %). The
cause is visible in its own cross-check: where the per-driver-sum and the whole-window estimator
diverge most (33.3 vs 21.7 /s), the driver processes have drifted furthest apart.

Mechanism of the noise: drivers run REPS as discrete bursts and immediately start the next one.
They desynchronise, so during any one driver's burst the others may be between bursts. That driver
therefore sees less contention and reports a higher rate, and the sum over-states system
throughput by an amount that varies run to run. Per-burst boundaries are the defect, not the load.

Fix, which removes the failure mode rather than averaging over it:
  * a multiprocessing BARRIER synchronises every driver at the start of each measurement window,
    so all drivers are loading the system over the SAME wall-clock interval
  * inside a window each driver issues requests CONTINUOUSLY at its concurrency (no burst
    boundaries, no gaps) until the window expires
  * aggregate throughput = total completions across drivers / window duration — one number, one
    clock, immune to desynchronisation

Both arms use the identical harness; only the request function differs.
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import random
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo       # noqa: E402
from harness import stats as st            # noqa: E402
from harness.seeds import seed_for         # noqa: E402

OUT = ROOT / "results" / "concurrency_barrier.json"
WS1_PORT = 8815
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
UNIT = "The quick brown fox jumps over the lazy dog. "

TOKENS = [400, 1600]
CONCS = [2, 4, 8, 16, 32]
WINDOW = 4.0
REPS = 5
WARMUP = 1
MAXDRV = 4


def doc_for(t: int) -> str:
    return UNIT * max(1, t // 10)


def layout(conc: int) -> tuple[int, int]:
    drivers = min(MAXDRV, conc)
    return drivers, max(1, conc // drivers)


async def _run_windows(fire, conc: int, barrier, reps: int, warm: int) -> list[dict]:
    """Continuously issue `fire()` at `conc` for WINDOW seconds, once per synchronised window."""
    out = []
    for w in range(reps + warm):
        try:
            barrier.wait(timeout=120)
        except Exception:
            pass
        ok = fail = 0
        stop = time.time() + WINDOW
        t0 = time.time()

        async def worker():
            nonlocal ok, fail
            while time.time() < stop:
                try:
                    await fire()
                    ok += 1
                except Exception:
                    fail += 1

        await asyncio.gather(*(worker() for _ in range(conc)))
        el = time.time() - t0
        if w >= warm:
            out.append({"ok": ok, "fail": fail, "elapsed": el})
    return out


_BARRIER = None


def _init(b):
    global _BARRIER
    _BARRIER = b


def _rr_driver(args) -> list[dict]:
    tag, doc, conc, reps, warm = args
    barrier = _BARRIER

    async def go():
        from rocketride import RocketRideClient
        base = json.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"cb-{tag}"))
        p = ROOT / "pipes" / "generated" / f"cb_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

        async def fire():
            await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

        res = await _run_windows(fire, conc, barrier, reps, warm)
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return res

    return asyncio.run(go())


def _li_driver(args) -> list[dict]:
    tag, doc, conc, reps, warm = args
    barrier = _BARRIER

    async def go():
        import aiohttp
        cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        async with aiohttp.ClientSession(connector=cn,
                                         timeout=aiohttp.ClientTimeout(total=600)) as s:
            async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": doc}) as r:
                await r.json()

            async def fire():
                async with s.post(f"{WS1_BASE}/process",
                                  json={"doc_id": "x", "text": doc}) as r:
                    await r.json()

            return await _run_windows(fire, conc, barrier, reps, warm)

    return asyncio.run(go())


ARMS = {"rocketride": _rr_driver, "llamaindex": _li_driver}


def measure(arm: str, tokens: int, conc: int, tag: str) -> dict:
    drivers, per = layout(conc)
    doc = doc_for(tokens)
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(drivers)
    args = [(f"{tag}_{i}", doc, per, REPS, WARMUP) for i in range(drivers)]
    with ctx.Pool(drivers, initializer=_init, initargs=(barrier,)) as pool:
        res = pool.map(ARMS[arm], args)

    rates, fails = [], 0
    for w in range(REPS):
        ok = sum(r[w]["ok"] for r in res)
        fails += sum(r[w]["fail"] for r in res)
        el = max(r[w]["elapsed"] for r in res)
        rates.append(round(ok / el, 3) if el > 0 else 0.0)
    med = statistics.median(rates)
    sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0.0
    return {"median": med, "rates": rates, "spread": round(sp, 4), "gate": sp <= 0.10,
            "drivers": drivers, "conc_per_driver": per, "fails": fails}


def start_ws1() -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                m = json.loads(r.read().decode())
                if not m.get("resolved_device", "").startswith("cpu"):
                    raise RuntimeError("ws1 resolved_device is not cpu")
                time.sleep(3)
                return p
        except RuntimeError:
            raise
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died during startup")
        time.sleep(3)
    p.kill()
    raise RuntimeError("ws1 not ready in 300s")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    eo.preflight("concurrency-barrier")
    print("=" * 100)
    print("STEP 2 — BARRIER-SYNCHRONISED concurrency sweep (variance fix)")
    print("=" * 100)
    ws1 = start_ws1()
    print("  ws1 up (cpu, 8 workers)\n")
    combos = [(t, c, a) for t in TOKENS for c in CONCS for a in ("rocketride", "llamaindex")]
    random.Random(seed_for("concbarrier")).shuffle(combos)
    cells: dict[tuple, dict] = {}
    try:
        for i, (t, c, a) in enumerate(combos):
            cell = measure(a, t, c, f"b{t}_{c}_{a[:2]}")
            cells[(t, c, a)] = cell
            print(f"  [{i + 1:2d}/{len(combos)}] {t:5d}tok conc={c:2d} {a:11s} "
                  f"{cell['median']:8.2f}/s  sp={cell['spread'] * 100:5.1f}% "
                  f"{'OK  ' if cell['gate'] else 'GATE'} "
                  f"({cell['drivers']}drv x {cell['conc_per_driver']})  fails={cell['fails']}",
                  flush=True)
            time.sleep(1)
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("concurrency-barrier")

    rows = []
    print("\n" + "=" * 100)
    for t in TOKENS:
        print(f"\n  {t} tokens/doc")
        print(f"    {'conc':>5} | {'RocketRide':>24} | {'LlamaIndex':>24} | {'ratio RR/LI':>22}")
        for c in CONCS:
            A, B = cells[(t, c, "rocketride")], cells[(t, c, "llamaindex")]
            pt, lo, hi = st.ratio_ci(A["rates"], B["rates"])
            rows.append({"tokens": t, "conc": c, "rocketride": A, "llamaindex": B,
                         "ratio": {"point": pt, "ci95": [lo, hi]},
                         "both_gate": A["gate"] and B["gate"]})
            print(f"    {c:5d} | {A['median']:9.2f}/s sp={A['spread'] * 100:5.1f}% "
                  f"{'OK ' if A['gate'] else 'GT '} | {B['median']:9.2f}/s "
                  f"sp={B['spread'] * 100:5.1f}% {'OK ' if B['gate'] else 'GT '} | "
                  f"{pt:6.3f} [{lo:.3f},{hi:.3f}]")
        pa = max((cells[(t, c, 'rocketride')]['median'], c) for c in CONCS)
        pb = max((cells[(t, c, 'llamaindex')]['median'], c) for c in CONCS)
        print(f"    PEAK: RocketRide {pa[0]:.2f}/s @conc {pa[1]}   "
              f"LlamaIndex {pb[0]:.2f}/s @conc {pb[1]}   peak ratio {pa[0] / pb[0]:.3f}")

    ngate = sum(1 for r in rows if r["both_gate"])
    print(f"\n  cells where BOTH arms pass the 10% gate: {ngate}/{len(rows)}")
    OUT.write_text(json.dumps(rows, indent=1))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
