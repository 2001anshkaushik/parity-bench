#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

fresh-task-per-rep; the burst-mode framing it supports was withdrawn in session 6

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
# """STEP 1 — extend the token sweep into the long-form regime: 400 → 6400 tokens/doc.

# The existing sweep stops at ~400 tokens, which is exactly where RocketRide starts winning. The
# question leadership cares about is whether that advantage keeps growing with document weight or
# plateaus, because long-form work is the next target.

# RULE 5 (direction of bias): this regime FAVOURS RocketRide, so the hunt is for artifacts that
# would unfairly penalise LlamaIndex as documents grow. Each is measured, not argued:

#   P1 memory pressure on the LlamaIndex service — 8 workers each holding a model plus large
#      activations. Peak RSS of the whole process tree is sampled per level; if it climbs toward the
#      48 GiB ceiling, throughput loss is a memory artifact, not a framework property.
#   P2 chunk batching differences — a long document becomes many chunks, and both sides claim ONE
#      batched encode per document. Verified per level: the response chunk count is recorded from
#      both services and must match.
#   P3 token-cap truncation — MiniLM caps at 512 tokens/chunk. If one side truncates and the other
#      does not, they are not doing the same work. Chunk counts and total embedded tokens are
#      reported so truncation is visible.
#   P4 request timeout — long documents take longer; a timeout tuned for short docs would silently
#      drop LlamaIndex requests. Timeouts are generous and error counts are reported per level.

# Protocol: both arms, one session, interleaved, randomised (fixed seed), warmup discarded, n>=5,
# variance gate applied per arm.
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

# import psutil  # noqa: E402

# from harness import engine_ops as eo    # noqa: E402
# from harness import stats as st         # noqa: E402
# from harness.seeds import seed_for      # noqa: E402

# OUT = ROOT / "results" / "token_sweep_extended.json"
# WS1_PORT = 8805
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "     # ~10 tokens per repetition
# TOKEN_LEVELS = [400, 800, 1600, 3200, 6400]
# REPS = 5
# WARMUP_REQS = 8
# CONC_PER_DRIVER = 4
# NDRIVERS = 2
# UID = os.getuid()


# def doc_for(tokens: int) -> str:
#     return UNIT * max(1, tokens // 10)


# def n_requests_for(tokens: int) -> int:
#     """Fewer requests at heavier levels so each run stays ~10-25 s rather than minutes."""
#     return max(24, min(120, int(24000 / tokens) * 4))


# # ------------------------------------------------------------------ memory probe (P1)
# def tree_rss_mb(match: str) -> float:
#     total = 0
#     for p in psutil.process_iter(["uids", "cmdline", "memory_info"]):
#         try:
#             if not p.info["uids"] or p.info["uids"].real != UID:
#                 continue
#             cmd = " ".join(p.info["cmdline"] or ())
#             if match in cmd:
#                 if p.info["memory_info"]:
#                     total += p.info["memory_info"].rss
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#     return round(total / 2**20, 1)


# def ws1_tree_rss_mb() -> float:
#     """Walk the tree from the uvicorn master — cmdline grep alone undercounts workers 173x."""
#     master = None
#     for p in psutil.process_iter(["cmdline", "pid"]):
#         try:
#             if "uvicorn" in " ".join(p.info["cmdline"] or ()) and "ws1.service" in " ".join(p.info["cmdline"] or ()):
#                 master = psutil.Process(p.info["pid"])
#                 break
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#     if master is None:
#         return 0.0
#     try:
#         procs = [master] + master.children(recursive=True)
#         return round(sum(x.memory_info().rss for x in procs) / 2**20, 1)
#     except (psutil.NoSuchProcess, psutil.AccessDenied):
#         return 0.0


# # ------------------------------------------------------------------ drivers
# def _rr(args) -> dict:
#     tag, doc, n, conc, warm = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         from rocketride import RocketRideClient
#         base = js.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tse-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"tse_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(js.dumps(base))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         first = await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#         nchunks = len(first.get("documents", []))
#         rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())

#         sem = aio.Semaphore(conc)
#         errs = 0

#         async def one(i, collect):
#             nonlocal errs
#             async with sem:
#                 t0 = time.perf_counter()
#                 try:
#                     await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#                     return (time.perf_counter() - t0) * 1000 if collect else True
#                 except Exception:
#                     errs += 1
#                     return None

#         await aio.gather(*(one(i, False) for i in range(warm)), return_exceptions=True)
#         t0 = time.perf_counter()
#         res = await aio.gather(*(one(i, True) for i in range(n)), return_exceptions=True)
#         wall = time.perf_counter() - t0
#         try:
#             await aio.wait_for(c.terminate(tok), timeout=120)
#         except Exception:
#             pass
#         try:
#             await c.disconnect()
#         except Exception:
#             pass
#         lat = sorted(x for x in res if isinstance(x, float))
#         return {"rate": len(lat) / wall if wall else 0, "p50": lat[len(lat) // 2] if lat else None,
#                 "errors": errs, "n_chunks": nchunks, "bytes": rbytes}

#     return asyncio.run(go())


# def _ws1(args) -> dict:
#     tag, doc, n, conc, warm = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         import aiohttp
#         conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         sem = aio.Semaphore(conc)
#         timeout = aiohttp.ClientTimeout(total=600)
#         errs = 0
#         async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "f", "text": doc}) as r:
#                 first = await r.json()
#             nchunks = first.get("n_chunks", 0)
#             rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())

#             async def one(i, collect):
#                 nonlocal errs
#                 async with sem:
#                     t0 = time.perf_counter()
#                     try:
#                         async with s.post(f"{WS1_BASE}/process",
#                                           json={"doc_id": str(i), "text": doc}) as r:
#                             await r.json()
#                             return (time.perf_counter() - t0) * 1000 if collect else True
#                     except Exception:
#                         errs += 1
#                         return None

#             await aio.gather(*(one(i, False) for i in range(warm)), return_exceptions=True)
#             t0 = time.perf_counter()
#             res = await aio.gather(*(one(i, True) for i in range(n)), return_exceptions=True)
#             wall = time.perf_counter() - t0
#         lat = sorted(x for x in res if isinstance(x, float))
#         return {"rate": len(lat) / wall if wall else 0, "p50": lat[len(lat) // 2] if lat else None,
#                 "errors": errs, "n_chunks": nchunks, "bytes": rbytes}

#     return asyncio.run(go())


# DRIVERS = {"rocketride": _rr, "llamaindex": _ws1}


# def run_once(service: str, doc: str, n: int, tag: str) -> dict:
#     ctx = mp.get_context("spawn")
#     per = max(1, n // NDRIVERS)
#     args = [(f"{tag}_{i}", doc, per, CONC_PER_DRIVER, WARMUP_REQS) for i in range(NDRIVERS)]
#     t0 = time.perf_counter()
#     with ctx.Pool(NDRIVERS) as pool:
#         res = pool.map(DRIVERS[service], args)
#     peak_rss = ws1_tree_rss_mb() if service == "llamaindex" else tree_rss_mb("eaas.py")
#     return {"rate": round(sum(r["rate"] for r in res), 3),
#             "p50": round(statistics.median([r["p50"] for r in res if r["p50"]]), 2),
#             "errors": sum(r["errors"] for r in res),
#             "n_chunks": res[0]["n_chunks"], "bytes": res[0]["bytes"],
#             "service_rss_mb": peak_rss}


# def start_ws1(workers: int = 8) -> subprocess.Popen:
#     env = dict(os.environ)
#     env.update(WS1_DEVICE="cpu", WS1_WORKERS=str(workers), WS1_PORT=str(WS1_PORT))
#     p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
#                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#     deadline = time.perf_counter() + 300
#     while time.perf_counter() < deadline:
#         try:
#             with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
#                 m = json.loads(r.read().decode())
#                 if not m.get("resolved_device", "").startswith("cpu"):
#                     raise RuntimeError(f"resolved_device={m.get('resolved_device')}")
#                 time.sleep(3)
#                 return p
#         except RuntimeError:
#             raise
#         except Exception:
#             pass
#         if p.poll() is not None:
#             raise RuntimeError("ws1 died on startup")
#         time.sleep(3)
#     p.kill()
#     raise RuntimeError("ws1 not ready")


# def main() -> int:
#     OUT.parent.mkdir(parents=True, exist_ok=True)
#     eo.preflight("token-sweep-extended")
#     ws1 = start_ws1()
#     print("  ws1 up (device=cpu asserted)\n")
#     print("=" * 92)
#     print("STEP 1 — EXTENDED TOKEN SWEEP: 400 -> 6400 tokens/doc, long-form regime")
#     print("=" * 92)

#     combos = [(t, s) for t in TOKEN_LEVELS for s in ("rocketride", "llamaindex")
#               for _ in range(REPS + 2)]
#     random.Random(seed_for("tokensweepext")).shuffle(combos)
#     seen: dict[tuple, int] = {}
#     raw: dict[tuple, list[dict]] = {}

#     try:
#         for tokens, svc in combos:
#             key = (tokens, svc)
#             idx = seen.get(key, 0)
#             seen[key] = idx + 1
#             doc = doc_for(tokens)
#             n = n_requests_for(tokens)
#             row = run_once(svc, doc, n, f"t{tokens}{svc}{idx}")
#             if idx >= 2:                      # discard 2 warmup runs per cell
#                 raw.setdefault(key, []).append(row)
#             kind = "warm" if idx < 2 else "meas"
#             print(f"  {tokens:5d}tok {svc:11s} r{idx} {kind}  {row['rate']:8.3f}/s  "
#                   f"p50={row['p50']:8.1f}ms  chunks={row['n_chunks']:3d}  "
#                   f"errs={row['errors']}  rss={row['service_rss_mb']:8.1f}MB", flush=True)
#             time.sleep(2)
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
#         eo.postflight("token-sweep-extended")

#     print("\n" + "=" * 92)
#     print(f"{'tokens':>7} | {'RocketRide':>22} | {'LlamaIndex':>22} | {'ratio RR/LI':>20}")
#     print("=" * 92)
#     rows = []
#     for t in TOKEN_LEVELS:
#         rr = [r["rate"] for r in raw.get((t, "rocketride"), [])]
#         ws = [r["rate"] for r in raw.get((t, "llamaindex"), [])]
#         if not rr or not ws:
#             continue
#         rr_med, ws_med = statistics.median(rr), statistics.median(ws)
#         rr_sp = (max(rr) - min(rr)) / max(rr) if max(rr) else 0
#         ws_sp = (max(ws) - min(ws)) / max(ws) if max(ws) else 0
#         pt, lo, hi = st.ratio_ci(rr, ws)
#         rr_meta = raw[(t, "rocketride")][0]
#         ws_meta = raw[(t, "llamaindex")][0]
#         rows.append({
#             "tokens": t, "chars": len(doc_for(t)),
#             "rocketride": {"median": rr_med, "rates": rr, "spread": round(rr_sp, 4),
#                            "gate": rr_sp <= 0.10, "p50": rr_meta["p50"],
#                            "n_chunks": rr_meta["n_chunks"], "bytes": rr_meta["bytes"],
#                            "rss_mb": rr_meta["service_rss_mb"],
#                            "errors": sum(r["errors"] for r in raw[(t, "rocketride")])},
#             "llamaindex": {"median": ws_med, "rates": ws, "spread": round(ws_sp, 4),
#                            "gate": ws_sp <= 0.10, "p50": ws_meta["p50"],
#                            "n_chunks": ws_meta["n_chunks"], "bytes": ws_meta["bytes"],
#                            "rss_mb": ws_meta["service_rss_mb"],
#                            "errors": sum(r["errors"] for r in raw[(t, "llamaindex")])},
#             "ratio_rr_over_li": {"point": pt, "ci95": [lo, hi]},
#         })
#         print(f"{t:7d} | {rr_med:9.3f}/s sp={rr_sp*100:4.1f}% {'OK' if rr_sp<=.10 else 'GATE'} | "
#               f"{ws_med:9.3f}/s sp={ws_sp*100:4.1f}% {'OK' if ws_sp<=.10 else 'GATE'} | "
#               f"{pt:6.3f} [{lo:.3f},{hi:.3f}]")

#     # throughput retention relative to the 400-token level
#     if rows:
#         base = rows[0]
#         print("\n  throughput retention vs 400 tokens (16x more work at 6400):")
#         for r in rows:
#             print(f"    {r['tokens']:5d}tok  RR {r['rocketride']['median']/base['rocketride']['median']:6.3f}x   "
#                   f"LI {r['llamaindex']['median']/base['llamaindex']['median']:6.3f}x   "
#                   f"chunks RR={r['rocketride']['n_chunks']} LI={r['llamaindex']['n_chunks']}   "
#                   f"RSS RR={r['rocketride']['rss_mb']:.0f}MB LI={r['llamaindex']['rss_mb']:.0f}MB")

#     OUT.write_text(json.dumps(rows, indent=2))
#     print(f"\nwritten -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
