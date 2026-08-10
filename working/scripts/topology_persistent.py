#!/usr/bin/env python3
"""STEP 2 + STEP 3 (persistent-connection rewrite).

FIRST ATTEMPT DISCARDED. `topology_and_chunking.py` recreated the RocketRide task and the client
pool on every repetition and produced spreads of 37-61 % on both arms — unreportable under the
variance gate. Preserved as `logs/topo_chunk_INVALID.out`. This version reuses ONE task and ONE
client per cell across all repetitions, mirroring how the LlamaIndex service persists. Same fix
that rescued the token sweep.

STEP 2 — TOPOLOGY vs FRAMEWORK
    How much of RocketRide's fixed per-request cost is the ENGINE, and how much is the 4-NODE
    PIPELINE SHAPE?
        4-node : webhook -> preprocessor_langchain -> embedding_transformer -> response_documents
        1-node : webhook -> split_embed -> response_text          (same work, one hop)
    If the 1-node pipeline moves the crossover materially, the fixed cost is topology, not engine.

STEP 3 — CHUNK COUNT vs TOKEN COUNT
    Total embedded tokens held CONSTANT while chunk_size is varied symmetrically on both sides.
        per-request overhead amortisation -> ratio should NOT move with chunk count
        per-chunk Python cost             -> ratio SHOULD move with chunk count
    chunk_size is only variable on the RocketRide side because `split_embed` reads SE_CHUNK_SIZE;
    the deployed engine silently drops splitter kwargs from pipeline config.
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

from harness import engine_ops as eo    # noqa: E402
from harness import stats as st         # noqa: E402
from harness.seeds import seed_for      # noqa: E402

OUT = ROOT / "results" / "topology_persistent.json"
WS1_PORT = 8808
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
UNIT = "The quick brown fox jumps over the lazy dog. "
REPS = 5
WARMUP_REPS = 2
CONC = 4
NDRIVERS = 2


def doc_for(t: int) -> str:
    return UNIT * max(1, t // 10)


def _rr(args) -> dict:
    """ONE task, many repetitions."""
    tag, pipe_rel, doc, n, conc, reps, warm = args
    import asyncio as aio
    import json as js

    async def go():
        from rocketride import RocketRideClient
        base = js.loads((ROOT / pipe_rel).read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tp-{tag}"))
        p = ROOT / "pipes" / "generated" / f"tp_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(js.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        first = await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=900)
        if "documents" in first:
            nch = len(first["documents"])
        else:
            txt = (first.get("text") or [""])[0]
            nch = int(str(txt).split("|", 1)[0]) if "|" in str(txt) else 0
        rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())
        sem = aio.Semaphore(conc)

        async def burst(count):
            async def one(i):
                async with sem:
                    try:
                        await aio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=900)
                        return True
                    except Exception:
                        return None
            t0 = time.perf_counter()
            res = await aio.gather(*(one(i) for i in range(count)), return_exceptions=True)
            wall = time.perf_counter() - t0
            return sum(1 for x in res if x is True) / wall if wall else 0.0

        rates = []
        for rep in range(reps + warm):
            rt = await burst(n)
            if rep >= warm:
                rates.append(rt)
            await aio.sleep(0.4)
        try:
            await aio.wait_for(c.terminate(tok), timeout=180)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return {"rates": rates, "n_chunks": nch, "bytes": rbytes}

    return asyncio.run(go())


def _ws1(args) -> dict:
    tag, _pipe, doc, n, conc, reps, warm = args
    import asyncio as aio
    import json as js

    async def go():
        import aiohttp
        conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        sem = aio.Semaphore(conc)
        async with aiohttp.ClientSession(connector=conn,
                                         timeout=aiohttp.ClientTimeout(total=900)) as s:
            async with s.post(f"{WS1_BASE}/process", json={"doc_id": "f", "text": doc}) as r:
                first = await r.json()
            nch = first.get("n_chunks", 0)
            rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())

            async def burst(count):
                async def one(i):
                    async with sem:
                        try:
                            async with s.post(f"{WS1_BASE}/process",
                                              json={"doc_id": str(i), "text": doc}) as r:
                                await r.json()
                                return True
                        except Exception:
                            return None
                t0 = time.perf_counter()
                res = await aio.gather(*(one(i) for i in range(count)), return_exceptions=True)
                wall = time.perf_counter() - t0
                return sum(1 for x in res if x is True) / wall if wall else 0.0

            rates = []
            for rep in range(reps + warm):
                rt = await burst(n)
                if rep >= warm:
                    rates.append(rt)
                await aio.sleep(0.4)
        return {"rates": rates, "n_chunks": nch, "bytes": rbytes}

    return asyncio.run(go())


ARMS = {"rr_4node": (_rr, "pipes/embed_probe.pipe"),
        "rr_1node": (_rr, "pipes/single_node.pipe"),
        "llamaindex": (_ws1, None)}


def measure_cell(arm: str, doc: str, n: int, tag: str) -> dict:
    fn, pipe = ARMS[arm]
    ctx = mp.get_context("spawn")
    per = max(8, n // NDRIVERS)
    args = [(f"{tag}_{i}", pipe, doc, per, CONC, REPS, WARMUP_REPS) for i in range(NDRIVERS)]
    with ctx.Pool(NDRIVERS) as pool:
        res = pool.map(fn, args)
    agg = [round(sum(r["rates"][i] for r in res), 3) for i in range(REPS)]
    med = statistics.median(agg)
    sp = (max(agg) - min(agg)) / max(agg) if max(agg) else 0
    return {"median": med, "rates": agg, "spread": round(sp, 4), "gate": sp <= 0.10,
            "n_chunks": res[0]["n_chunks"], "bytes": res[0]["bytes"]}


def start_ws1(chunk_size: int = 4000) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT),
               WS1_CHUNK_SIZE=str(chunk_size))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                m = json.loads(r.read().decode())
                if not m.get("resolved_device", "").startswith("cpu"):
                    raise RuntimeError("device not cpu")
                if m.get("chunk_size") != chunk_size:
                    raise RuntimeError(f"chunk_size {m.get('chunk_size')} != {chunk_size}")
                time.sleep(3)
                return p
        except RuntimeError:
            raise
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(3)
    p.kill()
    raise RuntimeError("ws1 not ready")


def restart_engine(chunk_size: int) -> None:
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
    env = dict(os.environ, SE_CHUNK_SIZE=str(chunk_size))
    subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")], env=env,
                   capture_output=True, timeout=900)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    findings: dict = {}

    print("=" * 96)
    print("STEP 2 — TOPOLOGY (persistent connections): 4-node vs 1-node vs LlamaIndex")
    print("=" * 96)
    eo.preflight("topology-persistent")
    restart_engine(4000)
    start_ws1(4000)
    print("  ws1 up (cpu, chunk 4000); engine up with split_embed\n")
    levels = [100, 200, 400, 800, 1600]
    cells: dict[tuple, dict] = {}
    try:
        combos = [(t, a) for t in levels for a in ARMS]
        random.Random(seed_for("topopersist")).shuffle(combos)
        for tokens, arm in combos:
            doc = doc_for(tokens)
            n = max(32, min(96, int(16000 / tokens) * 4))
            c = measure_cell(arm, doc, n, f"tp{tokens}{arm}")
            cells[(tokens, arm)] = c
            print(f"  {tokens:5d}tok {arm:11s} {c['median']:9.3f}/s  sp={c['spread']*100:5.1f}% "
                  f"{'OK  ' if c['gate'] else 'GATE'}  chunks={c['n_chunks']}", flush=True)
            time.sleep(1.5)
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)

    topo = []
    print(f"\n  {'tokens':>7} | {'4-node':>12} | {'1-node':>12} | {'LlamaIndex':>12} | "
          f"{'1n/LI':>7} | {'1n/4n':>7} | gates")
    for t in levels:
        a, b, c = cells[(t, "rr_4node")], cells[(t, "rr_1node")], cells[(t, "llamaindex")]
        r1li, lo1, hi1 = st.ratio_ci(b["rates"], c["rates"])
        r4li, lo4, hi4 = st.ratio_ci(a["rates"], c["rates"])
        r1n4, _, _ = st.ratio_ci(b["rates"], a["rates"])
        topo.append({"tokens": t, "rr_4node": a, "rr_1node": b, "llamaindex": c,
                     "ratio_1node_over_li": {"point": r1li, "ci95": [lo1, hi1]},
                     "ratio_4node_over_li": {"point": r4li, "ci95": [lo4, hi4]},
                     "ratio_1node_over_4node": r1n4,
                     "all_gates_pass": a["gate"] and b["gate"] and c["gate"]})
        g = "".join("Y" if x["gate"] else "n" for x in (a, b, c))
        print(f"  {t:7d} | {a['median']:10.3f}/s | {b['median']:10.3f}/s | {c['median']:10.3f}/s |"
              f" {r1li:6.3f} | {r1n4:6.3f} | {g}")
    findings["topology"] = topo
    OUT.write_text(json.dumps(findings, indent=2))

    print("\n" + "=" * 96)
    print("STEP 3 — CHUNK vs TOKEN: ~1600 total tokens held constant, chunk_size varied")
    print("=" * 96)
    rows = []
    doc = doc_for(1600)
    for chunk_size, label in ((8000, "1 chunk"), (3600, "2 chunks"),
                              (1500, "5 chunks"), (760, "10 chunks")):
        eo.preflight(f"chunk{chunk_size}")
        restart_engine(chunk_size)
        start_ws1(chunk_size)
        try:
            arms = ["rr_1node", "llamaindex"]
            random.Random(seed_for("chunkpersist", chunk_size)).shuffle(arms)
            cell = {a: measure_cell(a, doc, 48, f"ck{chunk_size}{a}") for a in arms}
            pt, lo, hi = st.ratio_ci(cell["rr_1node"]["rates"], cell["llamaindex"]["rates"])
            rows.append({"chunk_size": chunk_size, "label": label, "total_tokens": 1600,
                         "rr_1node": cell["rr_1node"], "llamaindex": cell["llamaindex"],
                         "ratio": {"point": pt, "ci95": [lo, hi]},
                         "gates_pass": cell["rr_1node"]["gate"] and cell["llamaindex"]["gate"]})
            print(f"  chunk_size={chunk_size:5d} ({label:9s})  "
                  f"RR1={cell['rr_1node']['median']:8.3f}/s(ch={cell['rr_1node']['n_chunks']},"
                  f"sp={cell['rr_1node']['spread']*100:.0f}%)  "
                  f"LI={cell['llamaindex']['median']:8.3f}/s(ch={cell['llamaindex']['n_chunks']},"
                  f"sp={cell['llamaindex']['spread']*100:.0f}%)  "
                  f"ratio={pt:.3f} [{lo:.3f},{hi:.3f}]", flush=True)
            findings["chunk_vs_token"] = rows
            OUT.write_text(json.dumps(findings, indent=2))
        finally:
            subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)

    restart_engine(4000)
    eo.postflight("topology-persistent")
    OUT.write_text(json.dumps(findings, indent=2))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
