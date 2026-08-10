#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

ASCENDING cold concurrency sweep: measures the machine in a low-power state and under-reports by up to 2.2x (session 11). Use scripts/isolated_profile_prewarm.py

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
# """PHASE 1 — ISOLATED SATURATION PROFILE. One framework at a time. No comparison.

# Every head-to-head number this project has produced was taken at a concurrency level someone
# picked: 8 because it looked reasonable, 2 because the anchor used it. That is backwards. A service
# has a knee and a saturation point, and comparing two services at a concurrency that saturates one
# and starves the other is not a framework comparison — it is a configuration accident. Session 8
# showed exactly that: the engine's advantage at concurrency 2 inverts by concurrency 8.

# So this harness characterises ONE service standing alone and reports where its own limits are.
# The output determines which concurrency levels are meaningful in any later head-to-head.

# Reported per concurrency level:
#   * throughput (req/s), barrier-synchronised fixed-duration windows, n>=5, spread + 10% gate
#   * latency P50 / P95 / P99 / P99.9  -- tail latency is where saturation shows up first
#   * peak RSS, sampled continuously from OUTSIDE the driver
#   * error rate

# Derived:
#   * KNEE           — last concurrency where doubling still buys >= KNEE_GAIN more throughput.
#                      Below the knee you are latency-bound; above it you are queueing.
#   * SATURATION     — first concurrency where throughput stops rising (within noise) while P99
#                      keeps climbing. Past this, offered load only buys latency.

# DELIBERATELY NOT A COMPARISON. No second arm, no ratios. Mixing the two is how we got here.
# """
# from __future__ import annotations

# import asyncio
# import json
# import multiprocessing as mp
# import os
# import statistics
# import subprocess
# import sys
# import threading
# import time
# import urllib.request
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(ROOT))
# os.chdir(ROOT)

# from harness import engine_ops as eo   # noqa: E402

# WS1_PORT = 8841
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "
# CONCS = [1, 2, 4, 8, 16, 32, 64]
# WINDOW = 4.0
# REPS = 5
# WARMUP = 1
# MAXDRV = 4
# KNEE_GAIN = 0.15          # doubling concurrency must buy >=15% throughput to still be "before the knee"

# _BARRIER = None


# def _init(b):
#     global _BARRIER
#     _BARRIER = b


# def layout(conc):
#     d = min(MAXDRV, conc)
#     return d, max(1, conc // d)


# def _driver(args):
#     tag, doc, conc = args
#     barrier = _BARRIER

#     async def go():
#         import aiohttp
#         cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         async with aiohttp.ClientSession(connector=cn,
#                                          timeout=aiohttp.ClientTimeout(total=600)) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": doc}) as r:
#                 await r.json()
#             out = []
#             for w in range(REPS + WARMUP):
#                 try:
#                     barrier.wait(timeout=180)
#                 except Exception:
#                     pass
#                 ok = fail = 0
#                 lat = []
#                 stop = time.time() + WINDOW
#                 t0 = time.time()

#                 async def worker():
#                     nonlocal ok, fail
#                     while time.time() < stop:
#                         st = time.perf_counter()
#                         try:
#                             async with s.post(f"{WS1_BASE}/process",
#                                               json={"doc_id": "x", "text": doc}) as r:
#                                 await r.json()
#                             lat.append(time.perf_counter() - st)
#                             ok += 1
#                         except Exception:
#                             fail += 1
#                 await asyncio.gather(*(worker() for _ in range(conc)))
#                 if w >= WARMUP:
#                     out.append({"ok": ok, "fail": fail,
#                                 "elapsed": time.time() - t0, "lat": lat})
#             return out
#     return asyncio.run(go())


# def pct(vals, q):
#     if not vals:
#         return None
#     v = sorted(vals)
#     i = min(len(v) - 1, int(len(v) * q))
#     return round(v[i] * 1000, 2)


# class RSS(threading.Thread):
#     def __init__(self, pid):
#         super().__init__(daemon=True)
#         self.pid, self.peak, self.stop_flag = pid, 0.0, False

#     def run(self):
#         import psutil
#         while not self.stop_flag:
#             try:
#                 p = psutil.Process(self.pid)
#                 self.peak = max(self.peak, sum(c.memory_info().rss
#                                                for c in [p] + p.children(recursive=True)) / 1e6)
#             except Exception:
#                 pass
#             time.sleep(0.25)


# def profile(tokens: int, ws1_pid: int) -> list[dict]:
#     doc = UNIT * max(1, tokens // 10)
#     rows = []
#     for conc in CONCS:
#         d, per = layout(conc)
#         ctx = mp.get_context("spawn")
#         barrier = ctx.Barrier(d)
#         sampler = RSS(ws1_pid)
#         sampler.start()
#         with ctx.Pool(d, initializer=_init, initargs=(barrier,)) as pool:
#             res = pool.map(_driver, [(f"p{conc}_{i}", doc, per) for i in range(d)])
#         sampler.stop_flag = True
#         sampler.join(timeout=5)

#         rates, all_lat, fails, total = [], [], 0, 0
#         for w in range(REPS):
#             ok = sum(r[w]["ok"] for r in res)
#             f = sum(r[w]["fail"] for r in res)
#             el = max(r[w]["elapsed"] for r in res)
#             rates.append(ok / el if el else 0.0)
#             fails += f
#             total += ok + f
#             for r in res:
#                 all_lat += r[w]["lat"]
#         med = statistics.median(rates)
#         sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0
#         row = {"conc": conc, "throughput": round(med, 2), "spread": round(sp, 4),
#                "gate": sp <= 0.10, "p50": pct(all_lat, 0.50), "p95": pct(all_lat, 0.95),
#                "p99": pct(all_lat, 0.99), "p999": pct(all_lat, 0.999),
#                "peak_rss_mb": round(sampler.peak, 1),
#                "error_rate": round(fails / total, 5) if total else 0.0,
#                "samples": len(all_lat)}
#         rows.append(row)
#         print(f"    c={conc:3d} {row['throughput']:8.2f}/s sp={sp * 100:5.1f}% "
#               f"{'OK  ' if row['gate'] else 'GATE'} P50={row['p50']:8.2f} P95={row['p95']:8.2f} "
#               f"P99={row['p99']:9.2f} P99.9={row['p999']:9.2f} rss={row['peak_rss_mb']:7.1f}MB "
#               f"err={row['error_rate']:.4f}", flush=True)
#     return rows


# def derive(rows: list[dict]) -> dict:
#     knee, sat = None, None
#     for i in range(len(rows) - 1):
#         gain = rows[i + 1]["throughput"] / rows[i]["throughput"] - 1 if rows[i]["throughput"] else 0
#         if gain >= KNEE_GAIN:
#             knee = rows[i + 1]["conc"]
#     best = max(r["throughput"] for r in rows)
#     for r in rows:
#         if r["throughput"] >= best * 0.95:
#             sat = r["conc"]
#             break
#     return {"knee": knee, "saturation": sat, "peak_throughput": best,
#             "knee_rule": f"last concurrency whose doubling still bought >= {KNEE_GAIN:.0%}",
#             "saturation_rule": "lowest concurrency reaching 95% of peak throughput"}


# def start_ws1():
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
#                     raise RuntimeError("device is not cpu")
#                 time.sleep(3)
#                 return p
#         except RuntimeError:
#             raise
#         except Exception:
#             pass
#         if p.poll() is not None:
#             raise RuntimeError("ws1 died")
#         time.sleep(3)
#     raise RuntimeError("ws1 not ready")


# def main() -> int:
#     eo.preflight("isolated-profile")
#     ws1 = start_ws1()
#     print("=" * 116)
#     print("PHASE 1 — ISOLATED SATURATION PROFILE: LlamaIndex FastAPI service (8 workers, cpu)")
#     print("  NO COMPARISON. This characterises one service standing alone.")
#     print("=" * 116)
#     out = {"service": "llamaindex-fastapi", "workers": 8, "device": "cpu", "profiles": {}}
#     try:
#         for tokens in (400, 1600):
#             print(f"\n  {tokens} tokens/doc")
#             rows = profile(tokens, ws1.pid)
#             out["profiles"][str(tokens)] = {"rows": rows, "derived": derive(rows)}
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("isolated-profile")
#         (ROOT / "results" / "isolated_profile_llamaindex.json").write_text(json.dumps(out, indent=1))

#     print("\n" + "=" * 116)
#     print("DERIVED OPERATING POINTS — these determine which concurrency levels a head-to-head may use")
#     print("=" * 116)
#     for tok, prof in out["profiles"].items():
#         d = prof["derived"]
#         print(f"  {tok:>5} tok:  KNEE=c{d['knee']}   SATURATION=c{d['saturation']}   "
#               f"peak {d['peak_throughput']:.2f}/s")
#     print("\n  written -> results/isolated_profile_llamaindex.json")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
