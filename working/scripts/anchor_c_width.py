#!/usr/bin/env python3
"""ANCHOR C — effective pool width, both arms, guarded instrument.

Gated in REBASELINE_PLAN.md and never run. Width is a STRUCTURAL property: how many items the
service can have in flight at once, independent of how fast each one is. It matters here for two
reasons — it tells us whether a container CPU quota is actually being enforced (the re-baseline
gate), and it sets the concurrency levels at which a head-to-head comparison is even meaningful.

Method: hold each item for a known duration T with no CPU cost (a sleep), offer far more work than
the pool can run at once, and measure steady-state throughput X. For a pool of width W serving
holds of length T, X = W / T exactly, so W = X * T.

Both arms already ship a symmetric hold: `fault_probe`'s `hang` (FP_HANG_SECONDS) and the WS-1
service's `FAULT:hang` (WS1_FAULT_HANG_S). Same directive-in-payload design on both sides, so the
work unit is identical and neither side gets a bespoke code path.

USES THE GUARDED INSTRUMENT (`handoff/pool_width.py`) rather than hand-rolled arithmetic. Its
failure mode is the dangerous kind: if offered concurrency is below the true width it returns the
OFFERED value at near-zero spread — confidently wrong, and precise-looking. The guarded version
escalates until the estimate stops tracking the offer and raises rather than returning a guess.
Calibrated to ~1 % against known widths of 4/8/16/64 (finding 17).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "handoff"))

from harness import engine_ops as eo          # noqa: E402
from pool_width import measure_width, WidthMeasurementError   # noqa: E402

OUT = ROOT / "results" / "anchor_c_width.json"
WS1_PORT = 8833
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
HOLD_S = 0.5


def rr_submit(offered: int, hold_s: float) -> float:
    """Offer `offered` concurrent holds through the engine; return steady-state throughput."""
    async def go():
        from rocketride import RocketRideClient
        base = json.loads((ROOT / "pipes" / "fault_probe.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"acw-{offered}"))
        p = ROOT / "pipes" / "generated" / f"acw_{offered}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        payload = f"FP|w|hang|{'x' * 200}"
        sem = asyncio.Semaphore(offered)
        done = 0
        stop = time.time() + max(6.0, hold_s * 12)

        async def one():
            nonlocal done
            while time.time() < stop:
                async with sem:
                    try:
                        await asyncio.wait_for(
                            c.send(tok, payload, mimetype="text/plain"), timeout=120)
                        done += 1
                    except Exception:
                        pass
        t0 = time.time()
        await asyncio.gather(*(one() for _ in range(offered)))
        el = time.time() - t0
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return done / el if el else 0.0
    return asyncio.run(go())


def li_submit(offered: int, hold_s: float) -> float:
    async def go():
        import aiohttp
        cn = aiohttp.TCPConnector(limit=offered, limit_per_host=offered)
        async with aiohttp.ClientSession(connector=cn,
                                         timeout=aiohttp.ClientTimeout(total=120)) as s:
            done = 0
            stop = time.time() + max(6.0, hold_s * 12)

            async def one():
                nonlocal done
                while time.time() < stop:
                    try:
                        async with s.post(f"{WS1_BASE}/process",
                                          json={"doc_id": "w",
                                                "text": f"FAULT:hang|{'x' * 200}"}) as r:
                            await r.read()
                        done += 1
                    except Exception:
                        pass
            t0 = time.time()
            await asyncio.gather(*(one() for _ in range(offered)))
            el = time.time() - t0
            return done / el if el else 0.0
    return asyncio.run(go())


def start_ws1() -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT),
               WS1_FAULT_HANG_S=str(HOLD_S))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                json.loads(r.read().decode())
                time.sleep(3)
                return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(3)
    raise RuntimeError("ws1 not ready")


def main() -> int:
    eo.preflight("anchor-c-width")
    # engine restarted with a SHORT hold; the default 25 s would pin task processes for the run
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
    time.sleep(3)
    env = dict(os.environ)
    env.update(FP_HANG_SECONDS=str(HOLD_S), CPU_PROBE_ITERS="235000")
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"):
        env[k] = "1"
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout:
        raise RuntimeError("engine did not start")
    time.sleep(2)
    ws1 = start_ws1()
    print("=" * 96)
    print(f"ANCHOR C — effective pool width, guarded instrument, hold={HOLD_S}s")
    print("=" * 96)
    res = {}
    try:
        for arm, fn in (("rocketride", rr_submit), ("llamaindex", li_submit)):
            try:
                w = measure_width(fn, hold_s=HOLD_S, start_offered=8, reps=3, max_offered=96)
                res[arm] = w
                print(f"\n  {arm}: width={w['width']:.2f}  confidence={w['confidence']}")
                for step in w.get("escalation", []):
                    print(f"      offered={step.get('offered'):5d} -> estimate "
                          f"{step.get('estimate', 0):7.2f}  spread={step.get('spread', 0) * 100:.1f}%")
            except WidthMeasurementError as e:
                res[arm] = {"error": str(e)}
                print(f"\n  {arm}: MEASUREMENT REFUSED — {e}")
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("anchor-c-width")
        OUT.write_text(json.dumps(res, indent=1))

    print("\n" + "=" * 96)
    print("  reference (native, session <=5):  RocketRide ~17 (finding 8)   LlamaIndex 8 (finding 9)")
    for arm in ("rocketride", "llamaindex"):
        v = res.get(arm, {})
        print(f"  {arm:11s} {('width %.2f' % v['width']) if 'width' in v else v.get('error', '?')}")
    print(f"\n  written -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
