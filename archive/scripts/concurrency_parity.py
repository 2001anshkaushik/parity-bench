#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

per-rep burst boundaries across unsynchronised drivers (12-58% spreads); superseded by barrier-synchronised windows

Archived 2026-08-09. Preserved because the correction history is an asset: this script is the
evidence for how the corresponding number was produced and why it was withdrawn. It is NOT a
working instrument and its output must not be used.

Replacement, if you need this measurement: see publishable/STATE.md and publishable/README.md.
"""
import sys

sys.stderr.write(__doc__ + "\n")
sys.stderr.write("REFUSING TO RUN: this harness is deprecated and its results were withdrawn.\n")
sys.exit(2)

# ----------------------------------------------------------------------------------
# ORIGINAL SOURCE PRESERVED BELOW THIS LINE, UNREACHABLE. Do not remove the guard above.
# ----------------------------------------------------------------------------------

# #!/usr/bin/env python3
# """STEP 2 — re-measure parity under a configuration that is actually defensible.

# Step 1 refuted the 31 % decay, which removes the only reason we had for preferring the
# persistent harness's direction over the fresh-task harness's. That leaves the real problem
# exposed: THE TWO SWEEPS DISAGREED BECAUSE OF HOW THEY WERE CONFIGURED, NOT BECAUSE OF THE
# FRAMEWORKS.

# At 800 tokens the same nominal workload has produced three different answers:
#     fresh-task sweep   (8 in flight)  RR/LI = 1.488
#     persistent sweep   (8 in flight)  RR/LI = 0.823
#     interleaved today  (4 in flight)  RR/LI = 1.03

# Measured widths: RocketRide's effective pool width is ~17; the LlamaIndex service's is 8. Both
# sweeps offered 8 concurrent requests. That SATURATES LlamaIndex and UNDER-DRIVES RocketRide by
# roughly half. A single fixed concurrency cannot compare two services with different widths, and
# the one we picked happened to penalise RocketRide.

# So: sweep the concurrency axis and report the whole curve, plus each arm's own peak. That is the
# comparison that does not depend on picking a number.

# TWO INSTRUMENT FIXES:
#   1. AGGREGATION. Driver processes desynchronise, so per-burst-index alignment is unreliable —
#      that is what produced the fake U-shaped "decay" in decay_rootcause PHASE 5. The first fix
#      attempted here was wall-clock union (total ok / union window); THAT WAS WRONG IN THE OTHER
#      DIRECTION and depressed every cell, because the union spans time in which an early-finishing
#      driver has already started its next rep. The correct estimator sums each driver's own rate
#      over its own contiguous window; `whole_window` is retained as a conservative cross-check.
#   2. DRIVER COUNT SCALES WITH CONCURRENCY. The engine is known not to scale with more connections
#      inside one process but to scale ~linearly with more driver processes, so offered concurrency
#      is spread across up to 4 processes on BOTH arms, keeping the client off the critical path.
# """
# from __future__ import annotations

# import asyncio
# import json
# import multiprocessing as mp
# import os
# import random
# import statistics
# import subprocess
# import sys
# import time
# import urllib.request
# import uuid
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(ROOT))
# os.chdir(ROOT)

# from harness import engine_ops as eo       # noqa: E402
# from harness import stats as st            # noqa: E402
# from harness.seeds import seed_for         # noqa: E402

# OUT = ROOT / "results" / "concurrency_parity.json"
# WS1_PORT = 8813
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "

# TOKENS = [400, 800, 1600]
# CONCS = [2, 4, 8, 16, 32]
# REPS = 5
# WARMUP = 2
# MAXDRV = 4


# def doc_for(t: int) -> str:
#     return UNIT * max(1, t // 10)


# def layout(conc: int) -> tuple[int, int]:
#     """Spread offered concurrency across processes on BOTH arms, identically."""
#     drivers = min(MAXDRV, conc)
#     return drivers, max(1, conc // drivers)


# def _rr_driver(args) -> dict:
#     tag, doc, per_burst, conc, reps, warm = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         from rocketride import RocketRideClient
#         base = js.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"cp-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"cp_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(js.dumps(base))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#         sem = aio.Semaphore(conc)

#         async def burst(n):
#             async def one(_i):
#                 async with sem:
#                     try:
#                         await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#                         return True
#                     except Exception:
#                         return False
#             t0 = time.time()
#             res = await aio.gather(*(one(i) for i in range(n)), return_exceptions=True)
#             t1 = time.time()
#             return {"ok": sum(1 for x in res if x is True), "n": n, "start": t0, "end": t1}

#         out = []
#         for rep in range(reps + warm):
#             b = await burst(per_burst)
#             if rep >= warm:
#                 out.append(b)
#         try:
#             await aio.wait_for(c.terminate(tok), timeout=120)
#         except Exception:
#             pass
#         try:
#             await c.disconnect()
#         except Exception:
#             pass
#         return {"bursts": out}

#     return asyncio.run(go())


# def _li_driver(args) -> dict:
#     tag, doc, per_burst, conc, reps, warm = args
#     import asyncio as aio

#     async def go():
#         import aiohttp
#         cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         async with aiohttp.ClientSession(connector=cn,
#                                          timeout=aiohttp.ClientTimeout(total=600)) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": doc}) as r:
#                 await r.json()
#             sem = aio.Semaphore(conc)

#             async def burst(n):
#                 async def one(i):
#                     async with sem:
#                         try:
#                             async with s.post(f"{WS1_BASE}/process",
#                                               json={"doc_id": str(i), "text": doc}) as r:
#                                 await r.json()
#                             return True
#                         except Exception:
#                             return False
#                 t0 = time.time()
#                 res = await aio.gather(*(one(i) for i in range(n)), return_exceptions=True)
#                 t1 = time.time()
#                 return {"ok": sum(1 for x in res if x is True), "n": n, "start": t0, "end": t1}

#             out = []
#             for rep in range(reps + warm):
#                 b = await burst(per_burst)
#                 if rep >= warm:
#                     out.append(b)
#         return {"bursts": out}

#     return asyncio.run(go())


# ARMS = {"rocketride": _rr_driver, "llamaindex": _li_driver}


# def measure(arm: str, tokens: int, conc: int, tag: str) -> dict:
#     """Aggregate by summing per-driver rates; see the note below on why not union."""
#     drivers, per_drv_conc = layout(conc)
#     doc = doc_for(tokens)
#     per_burst = max(8, int(24000 / tokens) * per_drv_conc)
#     args = [(f"{tag}_{i}", doc, per_burst, per_drv_conc, REPS, WARMUP) for i in range(drivers)]
#     ctx = mp.get_context("spawn")
#     with ctx.Pool(drivers) as pool:
#         res = pool.map(ARMS[arm], args)

#     # Aggregate by SUMMING EACH DRIVER'S OWN RATE over its OWN contiguous window.
#     # The wall-clock-union alternative (total ok / union window) is WRONG here: when drivers
#     # stagger, the union spans time in which the early-finishing driver has already moved on to
#     # its next rep, so its work is counted against a window it no longer occupies. That inflates
#     # the denominator and depresses every cell. Per-driver rates are each measured over a window
#     # that driver actually occupied, and the drivers run concurrently, so the sum is the system
#     # rate. `whole_window` below is the conservative cross-check.
#     rates, fails = [], 0
#     for rep in range(REPS):
#         n = sum(r["bursts"][rep]["n"] for r in res)
#         ok = sum(r["bursts"][rep]["ok"] for r in res)
#         fails += n - ok
#         per = 0.0
#         for r in res:
#             b = r["bursts"][rep]
#             d = b["end"] - b["start"]
#             per += (b["ok"] / d) if d > 0 else 0.0
#         rates.append(round(per, 3))
#     tot_ok = sum(b["ok"] for r in res for b in r["bursts"])
#     w0 = min(b["start"] for r in res for b in r["bursts"])
#     w1 = max(b["end"] for r in res for b in r["bursts"])
#     whole_window = round(tot_ok / (w1 - w0), 3) if w1 > w0 else 0.0
#     med = statistics.median(rates)
#     sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0.0
#     return {"median": med, "rates": rates, "spread": round(sp, 4), "gate": sp <= 0.10,
#             "drivers": drivers, "conc_per_driver": per_drv_conc, "fails": fails,
#             "whole_window": whole_window}


# def start_ws1() -> subprocess.Popen:
#     env = dict(os.environ)
#     env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
#     p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
#                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#     dl = time.perf_counter() + 300
#     while time.perf_counter() < dl:
#         try:
#             with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
#                 m = json.loads(r.read().decode())
#                 if not m.get("resolved_device", "").startswith("cpu"):
#                     raise RuntimeError("ws1 resolved_device is not cpu")
#                 time.sleep(3)
#                 return p
#         except RuntimeError:
#             raise
#         except Exception:
#             pass
#         if p.poll() is not None:
#             raise RuntimeError("ws1 died during startup")
#         time.sleep(3)
#     p.kill()
#     raise RuntimeError("ws1 not ready in 300s")


# def main() -> int:
#     OUT.parent.mkdir(parents=True, exist_ok=True)
#     eo.preflight("concurrency-parity")
#     print("=" * 100)
#     print("STEP 2 — CONCURRENCY SWEEP, both arms, wall-clock-union aggregation")
#     print("=" * 100)
#     ws1 = start_ws1()
#     print("  ws1 up (cpu, 8 workers)\n")
#     combos = [(t, c, a) for t in TOKENS for c in CONCS for a in ("rocketride", "llamaindex")]
#     random.Random(seed_for("concparity")).shuffle(combos)
#     cells: dict[tuple, dict] = {}
#     try:
#         for i, (t, c, a) in enumerate(combos):
#             cell = measure(a, t, c, f"c{t}_{c}_{a[:2]}")
#             cells[(t, c, a)] = cell
#             print(f"  [{i + 1:2d}/{len(combos)}] {t:5d}tok conc={c:2d} {a:11s} "
#                   f"{cell['median']:8.2f}/s  sp={cell['spread'] * 100:5.1f}% "
#                   f"{'OK  ' if cell['gate'] else 'GATE'} "
#                   f"({cell['drivers']}drv x {cell['conc_per_driver']})  "
#                   f"ww={cell['whole_window']:.1f}/s  fails={cell['fails']}",
#                   flush=True)
#             time.sleep(1)
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("concurrency-parity")

#     rows = []
#     print("\n" + "=" * 100)
#     print("CONCURRENCY CURVES")
#     print("=" * 100)
#     for t in TOKENS:
#         print(f"\n  {t} tokens/doc")
#         print(f"    {'conc':>5} | {'RocketRide':>22} | {'LlamaIndex':>22} | {'ratio RR/LI':>22}")
#         for c in CONCS:
#             A, B = cells[(t, c, "rocketride")], cells[(t, c, "llamaindex")]
#             pt, lo, hi = st.ratio_ci(A["rates"], B["rates"])
#             rows.append({"tokens": t, "conc": c, "rocketride": A, "llamaindex": B,
#                          "ratio": {"point": pt, "ci95": [lo, hi]},
#                          "both_gate": A["gate"] and B["gate"]})
#             print(f"    {c:5d} | {A['median']:9.2f}/s sp={A['spread'] * 100:5.1f}% "
#                   f"{'OK ' if A['gate'] else 'GT '} | {B['median']:9.2f}/s "
#                   f"sp={B['spread'] * 100:5.1f}% {'OK ' if B['gate'] else 'GT '} | "
#                   f"{pt:6.3f} [{lo:.3f},{hi:.3f}]")
#         ra = [(cells[(t, c, 'rocketride')]['median'], c) for c in CONCS]
#         rb = [(cells[(t, c, 'llamaindex')]['median'], c) for c in CONCS]
#         pa, pb = max(ra), max(rb)
#         print(f"    PEAK: RocketRide {pa[0]:.2f}/s @conc {pa[1]}   "
#               f"LlamaIndex {pb[0]:.2f}/s @conc {pb[1]}   peak ratio {pa[0] / pb[0]:.3f}")

#     OUT.write_text(json.dumps(rows, indent=1))
#     print(f"\nwritten -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
