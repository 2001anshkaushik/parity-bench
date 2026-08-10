#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

PHASE 5 summed per-burst-index rates across desynchronised driver processes, manufacturing a U-shaped curve

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
# """ITEM A2 — root-cause the 31 % sustained decay.

# The sustained-vs-burst direction reversal rests ENTIRELY on this decay, so it gets the full
# protocol. `burst_vs_sustained.py` measured it with ONE process, ONE connection, ONE task, no
# cooldown, no warmup discard, and NO LlamaIndex arm. Every one of those is a candidate artifact.

# Rivals, and the phase that separates each:

#   (a) CLIENT CONNECTION FUNNELING — the engine is known not to scale with more connections in one
#       process but to scale ~linearly with more driver processes. If sustained load funnels through
#       one connection, the "decay" is the client saturating, not the engine slowing.
#         -> PHASE 5 (N independent driver processes, each own connection + own task)
#         -> PHASE 4b (fresh connection per burst, same process)

#   (b) PIPELINE ACCUMULATION — the task retains state across sends; decay-then-plateau fits a
#       bounded buffer filling.
#         -> PHASE 4a (fresh task per burst, SAME connection) isolates task state from connection
#         -> PHASE 3 (recovery after idle) separates resettable from cumulative
#         -> RSS sampled between bursts throughout

#   (c) THERMAL / HOST — the host slows down over the sequence, and the LlamaIndex arm was never
#       given the same treatment, so the comparison was asymmetric.
#         -> PHASE 2 INTERLEAVED is the decisive control: alternate RR burst / LI burst inside ONE
#            sequence. Both arms then share an identical host timeline. If RR decays while LI stays
#            flat in the same sequence, host/thermal is refuted outright. If both decay together,
#            it is the host and the engine is exonerated.

#   (d) SILENT FAILURES — the original harness did `except Exception: return None` and divided the
#       SUCCESS count by wall time without ever recording failures. A rising error rate would look
#       exactly like throughput decay. Every phase here records ok/fail per burst.

# Nothing is concluded from argument; each rival gets an experiment.
# """
# from __future__ import annotations

# import asyncio
# import json
# import multiprocessing as mp
# import os
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

# from harness import engine_ops as eo  # noqa: E402

# OUT = ROOT / "results" / "decay_rootcause.json"
# WS1_PORT = 8811
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"

# UNIT = "The quick brown fox jumps over the lazy dog. "
# DOC = UNIT * 80          # ~800 tokens — same document as burst_vs_sustained.py
# BURSTS = 20
# PER_BURST = 60
# CONC = 4
# RECOVER_IDLE = 60.0
# RECOVER_BURSTS = 5


# # ---------------------------------------------------------------- host sampling
# def engine_rss_mb() -> tuple[float, int]:
#     """Total RSS of the engine process tree, in MB, plus process count.

#     Sampled ONLY BETWEEN bursts and with a single process-table scan. An in-loop collector that
#     rescanned per tick previously biased this project's results 100x; that mistake is not repeated.
#     """
#     try:
#         import psutil
#     except Exception:
#         return (0.0, 0)
#     roots = [p for p in psutil.process_iter(["pid", "name"])
#              if (p.info["name"] or "").lower() == "engine"]
#     if not roots:
#         return (0.0, 0)
#     seen, total = set(), 0.0
#     for r in roots:
#         try:
#             procs = [r] + r.children(recursive=True)
#         except Exception:
#             continue
#         for p in procs:
#             if p.pid in seen:
#                 continue
#             seen.add(p.pid)
#             try:
#                 total += p.memory_info().rss / 1e6
#             except Exception:
#                 pass
#     return (round(total, 1), len(seen))


# # ---------------------------------------------------------------- arm primitives
# class RRArm:
#     """RocketRide over one client. Task/connection lifecycle is controllable per phase."""

#     def __init__(self, tag: str):
#         self.tag = tag
#         self.c = None
#         self.tok = None
#         self._n = 0

#     async def _pipe(self, suffix: str) -> str:
#         base = json.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"decay-{self.tag}-{suffix}"))
#         p = ROOT / "pipes" / "generated" / f"decay_{self.tag}_{suffix}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(json.dumps(base))
#         return str(p.relative_to(ROOT))

#     async def connect(self):
#         from rocketride import RocketRideClient
#         self.c = RocketRideClient()
#         await self.c.connect(timeout=30000)

#     async def new_task(self) -> float:
#         """Create a task; returns creation seconds (measured, not assumed)."""
#         fp = await self._pipe(str(self._n))
#         self._n += 1
#         t0 = time.perf_counter()
#         r = await self.c.use(filepath=fp)
#         self.tok = r["token"]
#         await asyncio.wait_for(self.c.send(self.tok, DOC, mimetype="text/plain"), timeout=600)
#         return time.perf_counter() - t0

#     async def drop_task(self):
#         if self.tok:
#             try:
#                 await asyncio.wait_for(self.c.terminate(self.tok), timeout=120)
#             except Exception:
#                 pass
#             self.tok = None

#     async def disconnect(self):
#         try:
#             await self.c.disconnect()
#         except Exception:
#             pass
#         self.c = None

#     async def burst(self, n: int = PER_BURST, conc: int = CONC) -> dict:
#         sem = asyncio.Semaphore(conc)
#         lat: list[float] = []

#         async def one(_i):
#             async with sem:
#                 s = time.perf_counter()
#                 try:
#                     await asyncio.wait_for(self.c.send(self.tok, DOC, mimetype="text/plain"),
#                                            timeout=600)
#                     lat.append(time.perf_counter() - s)
#                     return True
#                 except Exception:
#                     return False

#         t0 = time.perf_counter()
#         res = await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
#         wall = time.perf_counter() - t0
#         ok = sum(1 for x in res if x is True)
#         return _mk(ok, n - ok, wall, lat)


# class LIArm:
#     """LlamaIndex over one aiohttp session — structurally mirrored to RRArm."""

#     def __init__(self, conc: int = CONC):
#         self.s = None
#         self.conc = conc

#     async def connect(self):
#         import aiohttp
#         conn = aiohttp.TCPConnector(limit=self.conc, limit_per_host=self.conc)
#         self.s = aiohttp.ClientSession(connector=conn,
#                                        timeout=aiohttp.ClientTimeout(total=600))
#         async with self.s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
#             await r.json()

#     async def disconnect(self):
#         try:
#             await self.s.close()
#         except Exception:
#             pass
#         self.s = None

#     async def burst(self, n: int = PER_BURST, conc: int | None = None) -> dict:
#         sem = asyncio.Semaphore(conc or self.conc)
#         lat: list[float] = []

#         async def one(i):
#             async with sem:
#                 s = time.perf_counter()
#                 try:
#                     async with self.s.post(f"{WS1_BASE}/process",
#                                            json={"doc_id": str(i), "text": DOC}) as r:
#                         await r.json()
#                     lat.append(time.perf_counter() - s)
#                     return True
#                 except Exception:
#                     return False

#         t0 = time.perf_counter()
#         res = await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
#         wall = time.perf_counter() - t0
#         ok = sum(1 for x in res if x is True)
#         return _mk(ok, n - ok, wall, lat)


# def _mk(ok: int, fail: int, wall: float, lat: list[float]) -> dict:
#     lat = sorted(lat)
#     return {"rate": round(ok / wall, 3) if wall else 0.0,
#             "ok": ok, "fail": fail, "wall": round(wall, 4),
#             "p50": round(lat[len(lat) // 2] * 1000, 2) if lat else None,
#             "p95": round(lat[int(len(lat) * 0.95)] * 1000, 2) if lat else None}


# def decay_of(rates: list[float]) -> float:
#     """Percent decay, first-3 median vs last-3 median. Same statistic as the original."""
#     if len(rates) < 6:
#         return 0.0
#     f, l = statistics.median(rates[:3]), statistics.median(rates[-3:])
#     return round((1 - l / f) * 100, 1) if f else 0.0


# # ---------------------------------------------------------------- ws1 lifecycle
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


# # ---------------------------------------------------------------- phases
# async def phase1_replicate() -> dict:
#     """Instrumented replication of the original: 1 proc, 1 conn, 1 task, no cooldown.

#     Adds what the original never recorded: ok/fail per burst (rival d) and engine-tree RSS
#     between bursts (rival b).
#     """
#     print("\nPHASE 1 — instrumented replication (1 proc / 1 conn / 1 task, no cooldown)")
#     a = RRArm("p1")
#     await a.connect()
#     tcreate = await a.new_task()
#     print(f"    task creation measured at {tcreate:.2f}s")
#     rows = []
#     for b in range(BURSTS):
#         r = await a.burst()
#         rss, nproc = engine_rss_mb()
#         r.update(burst=b + 1, rss_mb=rss, nproc=nproc)
#         rows.append(r)
#         print(f"    burst {b + 1:2d}: {r['rate']:7.2f}/s  ok={r['ok']:2d} fail={r['fail']:2d}  "
#               f"p50={r['p50']}ms p95={r['p95']}ms  rss={rss:.0f}MB/{nproc}p", flush=True)

#     print(f"\n    idling {RECOVER_IDLE:.0f}s -> PHASE 3 recovery on the SAME task/connection")
#     await asyncio.sleep(RECOVER_IDLE)
#     rec = []
#     for b in range(RECOVER_BURSTS):
#         r = await a.burst()
#         rss, nproc = engine_rss_mb()
#         r.update(burst=b + 1, rss_mb=rss, nproc=nproc)
#         rec.append(r)
#         print(f"    recover {b + 1}: {r['rate']:7.2f}/s  ok={r['ok']:2d} fail={r['fail']:2d}  "
#               f"rss={rss:.0f}MB", flush=True)
#     await a.drop_task()
#     await a.disconnect()

#     rates = [r["rate"] for r in rows]
#     rr = [r["rate"] for r in rec]
#     out = {"bursts": rows, "recovery": rec, "task_create_s": round(tcreate, 2),
#            "decay_pct": decay_of(rates),
#            "recovered_to_pct": round(statistics.median(rr) / statistics.median(rates[:3]) * 100, 1),
#            "total_fail": sum(r["fail"] for r in rows)}
#     print(f"    => decay {out['decay_pct']:+.1f}%   failures {out['total_fail']}   "
#           f"recovery reaches {out['recovered_to_pct']:.0f}% of opening rate")
#     return out


# async def phase2_interleaved() -> dict:
#     """THE DECISIVE THERMAL CONTROL — alternate RR and LI bursts in ONE sequence.

#     Both arms experience the same host timeline, the same thermal state, the same background
#     load. If RocketRide decays while LlamaIndex stays flat here, rival (c) is refuted. If both
#     decay together, the host is responsible and the engine is exonerated.
#     """
#     print("\nPHASE 2 — INTERLEAVED RR/LI, one sequence, identical host timeline (thermal control)")
#     rr = RRArm("p2")
#     await rr.connect()
#     await rr.new_task()
#     li = LIArm()
#     await li.connect()
#     rows = []
#     for b in range(BURSTS):
#         a = await rr.burst()
#         c = await li.burst()
#         rss, _ = engine_rss_mb()
#         rows.append({"burst": b + 1, "rr": a, "li": c, "rss_mb": rss})
#         print(f"    burst {b + 1:2d}:  RR {a['rate']:7.2f}/s (f={a['fail']})   "
#               f"LI {c['rate']:7.2f}/s (f={c['fail']})   ratio={a['rate'] / c['rate']:.3f}"
#               if c["rate"] else "", flush=True)
#     await rr.drop_task()
#     await rr.disconnect()
#     await li.disconnect()

#     rrr = [r["rr"]["rate"] for r in rows]
#     lir = [r["li"]["rate"] for r in rows]
#     out = {"bursts": rows, "rr_decay_pct": decay_of(rrr), "li_decay_pct": decay_of(lir)}
#     print(f"    => RR decay {out['rr_decay_pct']:+.1f}%   LI decay {out['li_decay_pct']:+.1f}%")
#     return out


# async def phase4_lifecycle() -> dict:
#     """Separate task state from connection state, both inside one process.

#     4a: fresh TASK every burst, connection reused  -> if decay dies, it is task state (rival b)
#     4b: fresh CONNECTION+task every burst          -> if decay dies only here, it is connection
#     """
#     print("\nPHASE 4a — fresh TASK per burst, connection reused")
#     a = RRArm("p4a")
#     await a.connect()
#     rows_a, creates = [], []
#     for b in range(10):
#         await a.drop_task()
#         creates.append(await a.new_task())
#         r = await a.burst()
#         r["burst"] = b + 1
#         rows_a.append(r)
#         print(f"    burst {b + 1:2d}: {r['rate']:7.2f}/s  ok={r['ok']:2d} fail={r['fail']:2d} "
#               f"(task created in {creates[-1]:.2f}s)", flush=True)
#     await a.drop_task()
#     await a.disconnect()

#     print("\nPHASE 4b — fresh CONNECTION + task per burst")
#     rows_b = []
#     for b in range(10):
#         c = RRArm(f"p4b{b}")
#         await c.connect()
#         await c.new_task()
#         r = await c.burst()
#         r["burst"] = b + 1
#         rows_b.append(r)
#         await c.drop_task()
#         await c.disconnect()
#         print(f"    burst {b + 1:2d}: {r['rate']:7.2f}/s  ok={r['ok']:2d} fail={r['fail']:2d}",
#               flush=True)

#     ra = [r["rate"] for r in rows_a]
#     rb = [r["rate"] for r in rows_b]
#     out = {"fresh_task": rows_a, "fresh_conn": rows_b,
#            "fresh_task_decay_pct": decay_of(ra), "fresh_conn_decay_pct": decay_of(rb),
#            "task_create_s": round(statistics.median(creates), 2)}
#     print(f"    => fresh-task decay {out['fresh_task_decay_pct']:+.1f}%   "
#           f"fresh-conn decay {out['fresh_conn_decay_pct']:+.1f}%")
#     return out


# def _driver(args) -> list[dict]:
#     """One independent driver process: own connection, own task, own burst sequence."""
#     tag, nb = args

#     async def go():
#         a = RRArm(tag)
#         await a.connect()
#         await a.new_task()
#         out = []
#         for _ in range(nb):
#             out.append(await a.burst(n=PER_BURST, conc=CONC))
#         await a.drop_task()
#         await a.disconnect()
#         return out

#     return asyncio.run(go())


# def phase5_multiproc(ndrivers: int = 4) -> dict:
#     """Rival (a): does the decay survive N independent processes/connections/tasks?

#     The engine is known to scale with driver processes but not with connections inside one
#     process. If the aggregate is flat here while phase 1 decays, the decay is client funneling.
#     """
#     print(f"\nPHASE 5 — {ndrivers} INDEPENDENT driver processes (own conn + own task each)")
#     ctx = mp.get_context("spawn")
#     with ctx.Pool(ndrivers) as pool:
#         res = pool.map(_driver, [(f"p5_{i}", BURSTS) for i in range(ndrivers)])
#     agg = []
#     for i in range(BURSTS):
#         rate = sum(r[i]["rate"] for r in res)
#         fail = sum(r[i]["fail"] for r in res)
#         agg.append({"burst": i + 1, "rate": round(rate, 3), "fail": fail})
#         print(f"    burst {i + 1:2d}: {rate:8.2f}/s aggregate (fail={fail})", flush=True)
#     rates = [a["rate"] for a in agg]
#     out = {"ndrivers": ndrivers, "aggregate": agg, "decay_pct": decay_of(rates),
#            "per_driver": res}
#     print(f"    => aggregate decay {out['decay_pct']:+.1f}%")
#     return out


# # ---------------------------------------------------------------- main
# async def amain() -> dict:
#     res = {}
#     res["phase1_replicate"] = await phase1_replicate()
#     res["phase2_interleaved"] = await phase2_interleaved()
#     res["phase4_lifecycle"] = await phase4_lifecycle()
#     return res


# def main() -> int:
#     OUT.parent.mkdir(parents=True, exist_ok=True)
#     eo.preflight("decay-rootcause")
#     print("=" * 96)
#     print("ITEM A2 — ROOT-CAUSING THE 31% SUSTAINED DECAY")
#     print("=" * 96)
#     ws1 = start_ws1()
#     print("  ws1 up (cpu, 8 workers)")
#     res = {}
#     try:
#         res = asyncio.run(amain())
#         res["phase5_multiproc"] = phase5_multiproc()
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("decay-rootcause")
#         OUT.write_text(json.dumps(res, indent=1))
#         print(f"\nwritten -> {OUT}")

#     print("\n" + "=" * 96)
#     print("VERDICT TABLE")
#     print("=" * 96)
#     p1 = res.get("phase1_replicate", {})
#     p2 = res.get("phase2_interleaved", {})
#     p4 = res.get("phase4_lifecycle", {})
#     p5 = res.get("phase5_multiproc", {})
#     print(f"  phase 1  1proc/1conn/1task ...... decay {p1.get('decay_pct'):+.1f}%  "
#           f"failures={p1.get('total_fail')}  recovery={p1.get('recovered_to_pct')}%")
#     print(f"  phase 2  RR interleaved ......... decay {p2.get('rr_decay_pct'):+.1f}%")
#     print(f"  phase 2  LI interleaved ......... decay {p2.get('li_decay_pct'):+.1f}%  "
#           f"<- if similar to RR, it is the HOST")
#     print(f"  phase 4a fresh task/burst ....... decay {p4.get('fresh_task_decay_pct'):+.1f}%")
#     print(f"  phase 4b fresh conn/burst ....... decay {p4.get('fresh_conn_decay_pct'):+.1f}%")
#     print(f"  phase 5  {p5.get('ndrivers')} driver processes ..... decay {p5.get('decay_pct'):+.1f}%"
#           f"  <- if flat, phase 1 was client funneling")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
