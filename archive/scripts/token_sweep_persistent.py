#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

the sustained token curve it produced was invalidated in session 6

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
# """STEP 1 re-run — fix the asymmetry that made the RocketRide arm fail the variance gate.

# In `token_sweep_extended.py` every repetition created a fresh RocketRide client, called `use()`
# (which spawns a NEW task process that must load MiniLM), measured, then `terminate()`d it. The
# LlamaIndex service, by contrast, was started ONCE and persisted across all repetitions.

# That asymmetry does two things, both bad:
#   * it injects per-rep variance into the RocketRide arm only — which is exactly what we saw
#     (spread 17.9-28.3 % on RR at every level, while LlamaIndex mostly passed the 10 % gate)
#   * it PENALISES RocketRide, because a freshly-spawned task process has a cold allocator and cold
#     page cache for the first requests of every repetition

# Fix: the RocketRide task is created ONCE per cell and reused across all repetitions, exactly
# mirroring how the LlamaIndex service persists. Now both sides are warm-and-persistent.

# This is a direct application of rule 5: the noisy arm was the one favouring RocketRide, so the
# artifact hunt had to be aimed at the measurement rather than at the conclusion.
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

# from harness import engine_ops as eo    # noqa: E402
# from harness import stats as st         # noqa: E402
# from harness.seeds import seed_for      # noqa: E402

# OUT = ROOT / "results" / "token_sweep_persistent.json"
# WS1_PORT = 8807
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "
# TOKEN_LEVELS = [400, 800, 1600, 3200, 6400]
# REPS = 5
# WARMUP_REPS = 2
# CONC = 4
# NDRIVERS = 2


# def doc_for(t: int) -> str:
#     return UNIT * max(1, t // 10)


# def n_req(t: int) -> int:
#     return max(32, min(120, int(32000 / t) * 4))


# def _rr_persistent(args) -> dict:
#     """ONE task, many repetitions — mirrors the persistent LlamaIndex service."""
#     tag, doc, n, conc, reps, warm_reps = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         from rocketride import RocketRideClient
#         base = js.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tsp-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"tsp_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(js.dumps(base))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         first = await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#         nch = len(first.get("documents", []))
#         sem = aio.Semaphore(conc)

#         async def burst(count):
#             async def one(i):
#                 async with sem:
#                     try:
#                         await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#                         return True
#                     except Exception:
#                         return None
#             t0 = time.perf_counter()
#             res = await aio.gather(*(one(i) for i in range(count)), return_exceptions=True)
#             wall = time.perf_counter() - t0
#             ok = sum(1 for x in res if x is True)
#             return ok / wall if wall else 0.0

#         rates = []
#         for rep in range(reps + warm_reps):
#             rt = await burst(n)
#             if rep >= warm_reps:
#                 rates.append(rt)
#             await aio.sleep(0.5)
#         try:
#             await aio.wait_for(c.terminate(tok), timeout=120)
#         except Exception:
#             pass
#         try:
#             await c.disconnect()
#         except Exception:
#             pass
#         return {"rates": rates, "n_chunks": nch}

#     return asyncio.run(go())


# def _ws1_persistent(args) -> dict:
#     tag, doc, n, conc, reps, warm_reps = args
#     import asyncio as aio

#     async def go():
#         import aiohttp
#         conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         sem = aio.Semaphore(conc)
#         async with aiohttp.ClientSession(connector=conn,
#                                          timeout=aiohttp.ClientTimeout(total=600)) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "f", "text": doc}) as r:
#                 nch = (await r.json()).get("n_chunks", 0)

#             async def burst(count):
#                 async def one(i):
#                     async with sem:
#                         try:
#                             async with s.post(f"{WS1_BASE}/process",
#                                               json={"doc_id": str(i), "text": doc}) as r:
#                                 await r.json()
#                                 return True
#                         except Exception:
#                             return None
#                 t0 = time.perf_counter()
#                 res = await aio.gather(*(one(i) for i in range(count)), return_exceptions=True)
#                 wall = time.perf_counter() - t0
#                 ok = sum(1 for x in res if x is True)
#                 return ok / wall if wall else 0.0

#             rates = []
#             for rep in range(reps + warm_reps):
#                 rt = await burst(n)
#                 if rep >= warm_reps:
#                     rates.append(rt)
#                 await aio.sleep(0.5)
#         return {"rates": rates, "n_chunks": nch}

#     return asyncio.run(go())


# ARMS = {"rocketride": _rr_persistent, "llamaindex": _ws1_persistent}


# def measure_cell(arm: str, tokens: int, tag: str) -> dict:
#     doc, n = doc_for(tokens), n_req(tokens)
#     ctx = mp.get_context("spawn")
#     per = max(8, n // NDRIVERS)
#     args = [(f"{tag}_{i}", doc, per, CONC, REPS, WARMUP_REPS) for i in range(NDRIVERS)]
#     with ctx.Pool(NDRIVERS) as pool:
#         res = pool.map(ARMS[arm], args)
#     # aggregate per repetition across drivers
#     agg = [round(sum(r["rates"][i] for r in res), 3) for i in range(REPS)]
#     med = statistics.median(agg)
#     sp = (max(agg) - min(agg)) / max(agg) if max(agg) else 0
#     return {"median": med, "rates": agg, "spread": round(sp, 4), "gate": sp <= 0.10,
#             "n_chunks": res[0]["n_chunks"]}


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
#                     raise RuntimeError("device not cpu")
#                 time.sleep(3)
#                 return p
#         except RuntimeError:
#             raise
#         except Exception:
#             pass
#         if p.poll() is not None:
#             raise RuntimeError("ws1 died")
#         time.sleep(3)
#     p.kill()
#     raise RuntimeError("ws1 not ready")


# def main() -> int:
#     OUT.parent.mkdir(parents=True, exist_ok=True)
#     eo.preflight("token-sweep-persistent")
#     ws1 = start_ws1()
#     print("  ws1 up (cpu). RocketRide task now PERSISTENT across reps — the fix.\n")
#     print("=" * 92)
#     print("STEP 1 RE-RUN — persistent task on both sides (variance-gate fix)")
#     print("=" * 92)
#     combos = [(t, a) for t in TOKEN_LEVELS for a in ("rocketride", "llamaindex")]
#     random.Random(seed_for("tokenpersist")).shuffle(combos)
#     cells: dict[tuple, dict] = {}
#     try:
#         for tokens, arm in combos:
#             c = measure_cell(arm, tokens, f"p{tokens}{arm}")
#             cells[(tokens, arm)] = c
#             print(f"  {tokens:5d}tok {arm:11s} {c['median']:9.3f}/s  sp={c['spread']*100:5.1f}% "
#                   f"{'OK  ' if c['gate'] else 'GATE'}  chunks={c['n_chunks']}  "
#                   f"rates={[round(x,1) for x in c['rates']]}", flush=True)
#             time.sleep(2)
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("token-sweep-persistent")

#     print("\n" + "=" * 92)
#     print(f"{'tokens':>7} | {'RocketRide':>24} | {'LlamaIndex':>24} | {'ratio RR/LI':>22}")
#     print("=" * 92)
#     rows = []
#     for t in TOKEN_LEVELS:
#         a, b = cells[(t, "rocketride")], cells[(t, "llamaindex")]
#         pt, lo, hi = st.ratio_ci(a["rates"], b["rates"])
#         rows.append({"tokens": t, "rocketride": a, "llamaindex": b,
#                      "ratio_rr_over_li": {"point": pt, "ci95": [lo, hi]},
#                      "both_pass_gate": a["gate"] and b["gate"]})
#         print(f"{t:7d} | {a['median']:9.3f}/s sp={a['spread']*100:5.1f}% "
#               f"{'OK ' if a['gate'] else 'GATE'} | {b['median']:9.3f}/s sp={b['spread']*100:5.1f}% "
#               f"{'OK ' if b['gate'] else 'GATE'} | {pt:6.3f} [{lo:.3f},{hi:.3f}]")
#     base = rows[0]
#     print("\n  throughput retention vs 400 tokens:")
#     for r in rows:
#         print(f"    {r['tokens']:5d}tok  RR {r['rocketride']['median']/base['rocketride']['median']:6.3f}x  "
#               f"LI {r['llamaindex']['median']/base['llamaindex']['median']:6.3f}x  "
#               f"chunks={r['rocketride']['n_chunks']}")
#     OUT.write_text(json.dumps(rows, indent=2))
#     print(f"\nwritten -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
