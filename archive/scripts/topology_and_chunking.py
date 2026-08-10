#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

37-61% spreads from per-rep task recreation; superseded by topology_persistent.py

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
# """STEP 2 + STEP 3 — separate topology from framework, and chunk count from token count.

# STEP 2: TOPOLOGY vs FRAMEWORK
#     RocketRide's fixed per-request cost is what makes it lose on short documents. How much of it
#     is the ENGINE and how much is the 4-NODE PIPELINE SHAPE?
#         4-node : webhook -> preprocessor_langchain -> embedding_transformer -> response_documents
#         2-node : webhook -> split_embed -> response_text            (one hop, same work)
#     Measured against each other and against the LlamaIndex service across the crossover region. If
#     the 2-node pipeline moves the crossover substantially, the fixed cost is topology, not engine.

# STEP 3: CHUNK COUNT vs TOKEN COUNT
#     Total embedded tokens held CONSTANT while chunk count varies (by changing chunk_size
#     symmetrically on both sides). Two rival mechanisms make opposite predictions:
#         per-request overhead amortisation -> ratio should NOT move with chunk count
#         per-chunk Python cost             -> ratio SHOULD move with chunk count
#     Chunk size is varied rather than document length precisely so the model does the same total
#     work in every cell — only the number of batched items changes.

# Both services get identical chunk_size settings. On the RocketRide side that is only possible
# because the `split_embed` node reads SE_CHUNK_SIZE — the deployed engine silently drops splitter
# kwargs passed through pipeline config.
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

# OUT = ROOT / "results" / "topology_and_chunking.json"
# WS1_PORT = 8806
# WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
# UNIT = "The quick brown fox jumps over the lazy dog. "
# REPS = 5
# WARMUP = 2
# CONC = 4
# NDRIVERS = 2


# def doc_for(tokens: int) -> str:
#     return UNIT * max(1, tokens // 10)


# # ------------------------------------------------------------------ RocketRide driver
# def _rr(args) -> dict:
#     tag, pipe_rel, doc, n, conc, warm = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         from rocketride import RocketRideClient
#         base = js.loads((ROOT / pipe_rel).read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tc-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"tc_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(js.dumps(base))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         first = await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)
#         # chunk count: 4-node returns `documents`, 2-node returns "N|dims;dims;..."
#         if "documents" in first:
#             nch = len(first["documents"])
#         else:
#             txt = (first.get("text") or [""])[0]
#             nch = int(txt.split("|", 1)[0]) if "|" in txt else 0
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
#                 "errors": errs, "n_chunks": nch, "bytes": rbytes}

#     return asyncio.run(go())


# def _ws1(args) -> dict:
#     tag, _pipe, doc, n, conc, warm = args
#     import asyncio as aio
#     import json as js

#     async def go():
#         import aiohttp
#         conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
#         sem = aio.Semaphore(conc)
#         errs = 0
#         async with aiohttp.ClientSession(connector=conn,
#                                          timeout=aiohttp.ClientTimeout(total=600)) as s:
#             async with s.post(f"{WS1_BASE}/process", json={"doc_id": "f", "text": doc}) as r:
#                 first = await r.json()
#             nch = first.get("n_chunks", 0)
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
#                 "errors": errs, "n_chunks": nch, "bytes": rbytes}

#     return asyncio.run(go())


# ARMS = {
#     "rr_4node": (_rr, "pipes/embed_probe.pipe"),
#     "rr_1node": (_rr, "pipes/single_node.pipe"),
#     "llamaindex": (_ws1, None),
# }


# def run_once(arm: str, doc: str, n: int, tag: str) -> dict:
#     fn, pipe = ARMS[arm]
#     ctx = mp.get_context("spawn")
#     per = max(1, n // NDRIVERS)
#     args = [(f"{tag}_{i}", pipe, doc, per, CONC, 4) for i in range(NDRIVERS)]
#     with ctx.Pool(NDRIVERS) as pool:
#         res = pool.map(fn, args)
#     return {"rate": round(sum(r["rate"] for r in res), 3),
#             "p50": round(statistics.median([r["p50"] for r in res if r["p50"]]), 2),
#             "errors": sum(r["errors"] for r in res),
#             "n_chunks": res[0]["n_chunks"], "bytes": res[0]["bytes"]}


# def start_ws1(chunk_size: int = 4000) -> subprocess.Popen:
#     env = dict(os.environ)
#     env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT),
#                WS1_CHUNK_SIZE=str(chunk_size))
#     p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
#                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#     deadline = time.perf_counter() + 300
#     while time.perf_counter() < deadline:
#         try:
#             with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
#                 m = json.loads(r.read().decode())
#                 if not m.get("resolved_device", "").startswith("cpu"):
#                     raise RuntimeError("device not cpu")
#                 if m.get("chunk_size") != chunk_size:
#                     raise RuntimeError(f"chunk_size {m.get('chunk_size')} != {chunk_size}")
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


# def restart_engine(chunk_size: int) -> None:
#     subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
#     env = dict(os.environ, SE_CHUNK_SIZE=str(chunk_size))
#     subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")], env=env,
#                    capture_output=True, timeout=900)


# def measure_cell(arm: str, doc: str, n: int, tag: str) -> dict:
#     vals = []
#     meta = None
#     for rep in range(REPS + WARMUP):
#         r = run_once(arm, doc, n, f"{tag}r{rep}")
#         if rep >= WARMUP:
#             vals.append(r["rate"])
#         if rep == 0:
#             meta = r
#         time.sleep(1.5)
#     med = statistics.median(vals)
#     sp = (max(vals) - min(vals)) / max(vals) if max(vals) else 0
#     return {"median": med, "rates": vals, "spread": round(sp, 4), "gate": sp <= 0.10,
#             "p50": meta["p50"], "n_chunks": meta["n_chunks"], "bytes": meta["bytes"],
#             "errors": meta["errors"]}


# def main() -> int:
#     OUT.parent.mkdir(parents=True, exist_ok=True)
#     findings: dict = {}

#     # ---------------- STEP 2: topology ----------------------------------
#     print("=" * 96)
#     print("STEP 2 — TOPOLOGY: 4-node vs 1-node RocketRide vs LlamaIndex, across the crossover")
#     print("=" * 96)
#     eo.preflight("topology")
#     restart_engine(4000)
#     ws1 = start_ws1(4000)
#     print("  ws1 up (cpu, chunk_size=4000); engine up with split_embed node\n")
#     topo = []
#     try:
#         levels = [100, 200, 400, 800, 1600]
#         combos = [(t, a) for t in levels for a in ("rr_4node", "rr_1node", "llamaindex")]
#         random.Random(seed_for("topoorder")).shuffle(combos)
#         cells: dict[tuple, dict] = {}
#         for tokens, arm in combos:
#             doc = doc_for(tokens)
#             n = max(24, min(96, int(16000 / tokens) * 4))
#             cells[(tokens, arm)] = measure_cell(arm, doc, n, f"topo{tokens}{arm}")
#             c = cells[(tokens, arm)]
#             print(f"  {tokens:5d}tok {arm:11s} {c['median']:8.3f}/s  sp={c['spread']*100:4.1f}% "
#                   f"{'OK' if c['gate'] else 'GATE'}  chunks={c['n_chunks']}  p50={c['p50']}ms",
#                   flush=True)
#         print(f"\n  {'tokens':>7} | {'4-node':>10} | {'1-node':>10} | {'LlamaIndex':>10} | "
#               f"{'1node/LI':>9} | {'1node/4node':>11}")
#         for t in levels:
#             a, b, c = cells[(t, "rr_4node")], cells[(t, "rr_1node")], cells[(t, "llamaindex")]
#             r_1_li, lo1, hi1 = st.ratio_ci(b["rates"], c["rates"])
#             r_1_4, _, _ = st.ratio_ci(b["rates"], a["rates"])
#             topo.append({"tokens": t, "rr_4node": a, "rr_1node": b, "llamaindex": c,
#                          "ratio_1node_over_li": {"point": r_1_li, "ci95": [lo1, hi1]},
#                          "ratio_1node_over_4node": r_1_4})
#             print(f"  {t:7d} | {a['median']:8.3f}/s | {b['median']:8.3f}/s | {c['median']:8.3f}/s |"
#                   f" {r_1_li:8.3f} | {r_1_4:10.3f}")
#         findings["topology"] = topo
#         OUT.write_text(json.dumps(findings, indent=2))
#     finally:
#         subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)

#     # ---------------- STEP 3: chunk count vs token count -----------------
#     print("\n" + "=" * 96)
#     print("STEP 3 — CHUNK vs TOKEN: total tokens held CONSTANT (~1600), chunk count varied")
#     print("=" * 96)
#     chunk_rows = []
#     TOTAL_TOKENS = 1600
#     doc = doc_for(TOTAL_TOKENS)              # ~7200 chars
#     # chunk_size -> approx chunk count for a ~7200-char document
#     for chunk_size, label in ((8000, "1 chunk"), (3600, "2 chunks"),
#                               (1500, "5 chunks"), (760, "10 chunks")):
#         eo.preflight(f"chunk{chunk_size}")
#         restart_engine(chunk_size)
#         ws1 = start_ws1(chunk_size)
#         try:
#             arms = ["rr_1node", "llamaindex"]
#             random.Random(seed_for("chunkorder", chunk_size)).shuffle(arms)
#             cell: dict[str, dict] = {}
#             for arm in arms:
#                 cell[arm] = measure_cell(arm, doc, 48, f"chk{chunk_size}{arm}")
#             pt, lo, hi = st.ratio_ci(cell["rr_1node"]["rates"], cell["llamaindex"]["rates"])
#             chunk_rows.append({"chunk_size": chunk_size, "label": label,
#                                "total_tokens": TOTAL_TOKENS,
#                                "rr_1node": cell["rr_1node"], "llamaindex": cell["llamaindex"],
#                                "ratio": {"point": pt, "ci95": [lo, hi]}})
#             print(f"  chunk_size={chunk_size:5d} ({label:9s})  "
#                   f"RR1={cell['rr_1node']['median']:7.3f}/s (chunks={cell['rr_1node']['n_chunks']})  "
#                   f"LI={cell['llamaindex']['median']:7.3f}/s (chunks={cell['llamaindex']['n_chunks']})  "
#                   f"ratio={pt:.3f} [{lo:.3f},{hi:.3f}]", flush=True)
#             findings["chunk_vs_token"] = chunk_rows
#             OUT.write_text(json.dumps(findings, indent=2))
#         finally:
#             subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)

#     restart_engine(4000)
#     eo.postflight("topology-chunking")
#     OUT.write_text(json.dumps(findings, indent=2))
#     print(f"\nwritten -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
