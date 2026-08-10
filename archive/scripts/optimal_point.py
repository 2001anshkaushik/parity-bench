#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

its operating points came from saturation figures that were later withdrawn

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
# """STEP 2 — the first comparison in this project with BOTH arms in their serving regime.

# Every previous head-to-head picked one concurrency and applied it to both arms. Sessions 6-8 used
# 8, 16 and 32 — all past LlamaIndex's saturation point of 4, so those numbers describe how a
# queue behaves, not how a service serves.

# Now both isolated profiles exist, so each arm can be run at ITS OWN saturation concurrency:

#     LlamaIndex        c4 at both token levels (plateau 67.4 /s @400, 29.0 /s @1600)
#     RocketRide untuned c16 @400, c4 @1600
#     RocketRide tuned   c4  @400, c32 @1600

# HYPOTHESIS UNDER TEST, not assumed: at their own operating points the two are near parity, with
# RocketRide slightly ahead at 1600 tokens. Arithmetic across previous sessions suggested that, but
# those numbers came from different sessions AND different pipeline topologies, so they are not a
# result. This measures it in one interleaved session.

# RULE 5, BOTH DIRECTIONS. The hypothesis favours RocketRide at 1600 tokens, so:
#   * LlamaIndex is measured in BOTH engine-config blocks. It cannot be affected by the engine's
#     thread setting, so its movement across blocks is the drift null control — session 8 showed
#     that control does NOT always hold (+3.4 % median, up to +19.5 %), so any difference smaller
#     than ~5 % is not reportable.
#   * the 4-node `embed_probe.pipe` is used, which returns the FULL embedding payload, matching what
#     the LlamaIndex service returns. The 1-node variant returns a 159-byte summary and would hand
#     RocketRide a payload advantage.
#   * both arms must pass the 10 % gate in a cell for that cell's ratio to be quoted.
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

# OUT = ROOT / "results" / "optimal_point.json"
# WS1_PORT = 8851
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "
# WINDOW = 4.0
# REPS = 5
# WARMUP = 1
# MAXDRV = 4
# THREAD_KEYS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
#                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]

# # operating points taken from the isolated profiles (plateau-median rule)
# PLAN = {
#     "untuned": [(400, "llamaindex", 4), (400, "rocketride", 16),
#                 (1600, "llamaindex", 4), (1600, "rocketride", 4)],
#     "tuned":   [(400, "llamaindex", 4), (400, "rocketride", 4),
#                 (1600, "llamaindex", 4), (1600, "rocketride", 32)],
# }

# _BARRIER = None


# def _init(b):
#     global _BARRIER
#     _BARRIER = b


# def layout(conc):
#     d = min(MAXDRV, conc)
#     return d, max(1, conc // d)


# async def _windows(fire, conc, barrier):
#     out = []
#     for w in range(REPS + WARMUP):
#         try:
#             barrier.wait(timeout=240)
#         except Exception:
#             pass
#         ok = fail = 0
#         lat = []
#         stop = time.time() + WINDOW
#         t0 = time.time()

#         async def worker():
#             nonlocal ok, fail
#             while time.time() < stop:
#                 s = time.perf_counter()
#                 try:
#                     await fire()
#                     lat.append(time.perf_counter() - s)
#                     ok += 1
#                 except Exception:
#                     fail += 1
#         await asyncio.gather(*(worker() for _ in range(conc)))
#         if w >= WARMUP:
#             out.append({"ok": ok, "fail": fail, "elapsed": time.time() - t0, "lat": lat})
#     return out


# def _rr(args):
#     tag, doc, conc = args
#     barrier = _BARRIER

#     async def go():
#         from rocketride import RocketRideClient
#         b = json.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         b["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"op-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"op_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(json.dumps(b))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

#         async def fire():
#             await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#         res = await _windows(fire, conc, barrier)
#         try:
#             await asyncio.wait_for(c.terminate(tok), timeout=120)
#         except Exception:
#             pass
#         try:
#             await c.disconnect()
#         except Exception:
#             pass
#         return res
#     return asyncio.run(go())


# def _li(args):
#     tag, doc, conc = args
#     barrier = _BARRIER

#     async def go():
#         import aiohttp
#         cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         async with aiohttp.ClientSession(connector=cn,
#                                          timeout=aiohttp.ClientTimeout(total=600)) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": doc}) as r:
#                 await r.json()

#             async def fire():
#                 async with s.post(f"{WS1_BASE}/process", json={"doc_id": "x", "text": doc}) as r:
#                     await r.json()
#             return await _windows(fire, conc, barrier)
#     return asyncio.run(go())


# ARMS = {"rocketride": _rr, "llamaindex": _li}


# def pct(v, q):
#     if not v:
#         return None
#     s = sorted(v)
#     return round(s[min(len(s) - 1, int(len(s) * q))] * 1000, 2)


# def measure(arm, tokens, conc, tag):
#     doc = UNIT * max(1, tokens // 10)
#     d, per = layout(conc)
#     ctx = mp.get_context("spawn")
#     barrier = ctx.Barrier(d)
#     with ctx.Pool(d, initializer=_init, initargs=(barrier,)) as pool:
#         res = pool.map(ARMS[arm], [(f"{tag}_{i}", doc, per) for i in range(d)])
#     rates, lat, fails, total = [], [], 0, 0
#     for w in range(REPS):
#         ok = sum(r[w]["ok"] for r in res)
#         f = sum(r[w]["fail"] for r in res)
#         el = max(r[w]["elapsed"] for r in res)
#         rates.append(ok / el if el else 0.0)
#         fails += f
#         total += ok + f
#         for r in res:
#             lat += r[w]["lat"]
#     med = statistics.median(rates)
#     sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0
#     return {"median": round(med, 2), "rates": [round(x, 2) for x in rates],
#             "spread": round(sp, 4), "gate": sp <= 0.10, "conc": conc,
#             "p50": pct(lat, .50), "p99": pct(lat, .99),
#             "error_rate": round(fails / total, 5) if total else 0.0}


# def restart(tuned: bool):
#     subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
#     time.sleep(3)
#     env = dict(os.environ)
#     env["CPU_PROBE_ITERS"] = "235000"
#     env["SE_REPORT_THREADS"] = "0"
#     env.pop("SE_INTEROP_THREADS", None)
#     for k in THREAD_KEYS:
#         env.pop(k, None)
#     if tuned:
#         for k in THREAD_KEYS:
#             env[k] = "1"
#     r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
#                        capture_output=True, env=env, text=True)
#     if "healthy" not in r.stdout:
#         raise RuntimeError("engine did not start")
#     time.sleep(2)
#     p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
#                         str(ROOT / "scripts" / "probe_env.py"), f"op{int(time.time())}"],
#                        capture_output=True, text=True, cwd=str(ROOT))
#     got = json.loads(p.stdout).get("torch_num_threads")
#     want = 1 if tuned else 10
#     if got != want:
#         raise RuntimeError(f"thread gate failed: wanted {want}, got {got}")
#     print(f"    [env verified] torch_num_threads={got}", flush=True)


# def start_ws1():
#     env = dict(os.environ)
#     env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
#     p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
#                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#     dl = time.perf_counter() + 300
#     while time.perf_counter() < dl:
#         try:
#             with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
#                 json.loads(r.read().decode())
#                 time.sleep(3)
#                 return p
#         except Exception:
#             pass
#         if p.poll() is not None:
#             raise RuntimeError("ws1 died")
#         time.sleep(3)
#     raise RuntimeError("ws1 not ready")


# def main() -> int:
#     eo.preflight("optimal-point")
#     ws1 = start_ws1()
#     print("=" * 104)
#     print("STEP 2 — OPTIMAL OPERATING POINT: each arm at ITS OWN saturation concurrency")
#     print("=" * 104)
#     res = {}
#     try:
#         for cfg in ("untuned", "tuned"):
#             print(f"\n### engine {cfg.upper()}")
#             restart(cfg == "tuned")
#             cells = {}
#             plan = list(PLAN[cfg])
#             random.Random(seed_for(f"op{cfg}")).shuffle(plan)
#             for tokens, arm, conc in plan:
#                 c = measure(arm, tokens, conc, f"{cfg[:2]}{tokens}{arm[:2]}{conc}")
#                 cells[f"{tokens}|{arm}"] = c
#                 print(f"    {tokens:5d}tok {arm:11s} @c{conc:<3d} {c['median']:8.2f}/s "
#                       f"sp={c['spread'] * 100:5.1f}% {'OK  ' if c['gate'] else 'GATE'} "
#                       f"P50={c['p50']:8.2f} P99={c['p99']:9.2f} err={c['error_rate']:.4f}",
#                       flush=True)
#             res[cfg] = cells
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("optimal-point")
#         OUT.write_text(json.dumps(res, indent=1))

#     print("\n" + "=" * 104)
#     print("OPTIMAL-POINT COMPARISON  (each arm at its own saturation; ratio = RR / LI)")
#     print("=" * 104)
#     for cfg in ("untuned", "tuned"):
#         print(f"\n  engine {cfg}")
#         for tokens in (400, 1600):
#             rr = res[cfg][f"{tokens}|rocketride"]
#             li = res[cfg][f"{tokens}|llamaindex"]
#             pt, lo, hi = st.ratio_ci(rr["rates"], li["rates"])
#             both = rr["gate"] and li["gate"]
#             print(f"    {tokens:5d}tok  RR {rr['median']:7.2f}/s @c{rr['conc']:<3d}"
#                   f"{'OK ' if rr['gate'] else 'GT '} | LI {li['median']:7.2f}/s @c{li['conc']:<3d}"
#                   f"{'OK ' if li['gate'] else 'GT '} | ratio {pt:6.3f} [{lo:.3f},{hi:.3f}]"
#                   f"  {'QUOTABLE' if both else 'gate-failed, direction only'}")
#     print("\n  DRIFT NULL CONTROL — LlamaIndex across the two engine-config blocks:")
#     for tokens in (400, 1600):
#         a = res["untuned"][f"{tokens}|llamaindex"]["median"]
#         b = res["tuned"][f"{tokens}|llamaindex"]["median"]
#         print(f"    {tokens:5d}tok  untuned-block {a:7.2f}/s  tuned-block {b:7.2f}/s  "
#               f"delta {(b / a - 1) * 100:+.1f}%")
#     print(f"\n  written -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
