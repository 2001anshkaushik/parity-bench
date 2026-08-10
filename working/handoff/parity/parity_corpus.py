#!/usr/bin/env python3
"""STEP 2b/2c — parity on the REAL mt10k distribution, plus a controlled chunk-count sweep.

Two experiments, one session, interleaved and randomised:

  B. REAL DISTRIBUTION — documents drawn from the verified mt10k corpus in their natural
     proportions (93.2% single-chunk, median 1,186 bytes, tail to 22 chunks). Answers: does the
     parity result hold on the workload WS-1 actually specifies?

  C. CHUNK SWEEP — synthetic documents at exactly 1, 2, 5, 10, 20 chunks. Answers: does the gap
     narrow as model work grows relative to per-request overhead? That is the mechanism proposed
     to explain the 1-chunk result, and it makes a falsifiable prediction (Rule 6): if per-request
     overhead amortisation is the explanation, the ratio must move monotonically toward 1.0 as
     chunk count rises. If the ratio stays flat, overhead amortisation is REFUTED and the
     difference is per-chunk work, not per-request cost.

Rule 5 in reverse: this arm is unfavourable to RocketRide, so structural costs the engine pays and
this service does not are measured and reported, not absorbed — node-hop count, first-request
latency, response bytes.
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

OUT = ROOT / "results" / "parity_corpus.json"
WS1_PORT = 8803
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
REPS = 5
WARMUP_REQS = 20
N_PER_RUN = 200
PINNED_CONC = 8
NDRIVERS = 2
CONC_PER_DRIVER = PINNED_CONC // NDRIVERS
COOLDOWN_S = 3.0

# One chunk ~= 4000 chars under the contract splitter. Build documents that land on exact counts.
_UNIT = "The quick brown fox jumps over the lazy dog. "


def synth_doc(n_chunks: int) -> str:
    """Approximately n_chunks chunks at chunk_size=4000, overlap=200 (stride ~3800)."""
    target = 3800 * n_chunks - 200 if n_chunks > 1 else 2000
    return (_UNIT * (target // len(_UNIT) + 1))[:target]


def load_corpus_docs(n: int, seed_tag: str) -> list[str]:
    data = json.loads((ROOT / "data" / "mt10k" / "mt10k_sample.json").read_text())
    rng = random.Random(seed_for("corpussample", seed_tag))
    # Natural proportions: uniform sample of the corpus, no stratification.
    return [rng.choice(data)["text"] for _ in range(n)]


# ------------------------------------------------------------------ drivers
def _rr(args) -> dict:
    tag, docs, conc, warm = args
    import asyncio as aio
    import json as js

    async def go():
        from rocketride import RocketRideClient
        base = js.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pc-{tag}"))
        p = ROOT / "pipes" / "generated" / f"pc_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(js.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]

        t_first = time.perf_counter()
        first = await aio.wait_for(c.send(tok, docs[0], mimetype="text/plain"), timeout=300)
        first_ms = (time.perf_counter() - t_first) * 1000
        rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())
        nch = len(first.get("documents", []))

        sem = aio.Semaphore(conc)

        async def one(d, collect):
            async with sem:
                t0 = time.perf_counter()
                try:
                    await aio.wait_for(c.send(tok, d, mimetype="text/plain"), timeout=180)
                    return (time.perf_counter() - t0) * 1000 if collect else True
                except Exception:
                    return None

        await aio.gather(*(one(docs[i % len(docs)], False) for i in range(warm)),
                         return_exceptions=True)
        t0 = time.perf_counter()
        res = await aio.gather(*(one(docs[i % len(docs)], True) for i in range(len(docs))),
                               return_exceptions=True)
        wall = time.perf_counter() - t0
        try:
            await aio.wait_for(c.terminate(tok), timeout=60)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        lat = sorted(x for x in res if isinstance(x, float))
        return {"ok": len(lat), "wall": wall, "rate": len(lat) / wall if wall else 0,
                "p50": lat[len(lat) // 2] if lat else None,
                "first_ms": round(first_ms, 2), "bytes": rbytes, "n_chunks_first": nch}

    return asyncio.run(go())


def _ws1(args) -> dict:
    tag, docs, conc, warm = args
    import asyncio as aio
    import json as js

    async def go():
        import aiohttp
        conn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        sem = aio.Semaphore(conc)
        async with aiohttp.ClientSession(connector=conn) as s:
            t_first = time.perf_counter()
            async with s.post(f"{WS1_BASE}/process",
                              json={"doc_id": "first", "text": docs[0]}) as r:
                first = await r.json()
            first_ms = (time.perf_counter() - t_first) * 1000
            rbytes = len(js.dumps(first, separators=(",", ":"), ensure_ascii=False).encode())
            nch = first.get("n_chunks", 0)

            async def one(i, d, collect):
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        async with s.post(f"{WS1_BASE}/process",
                                          json={"doc_id": str(i), "text": d}) as r:
                            await r.json()
                            return (time.perf_counter() - t0) * 1000 if collect else True
                    except Exception:
                        return None

            await aio.gather(*(one(i, docs[i % len(docs)], False) for i in range(warm)),
                             return_exceptions=True)
            t0 = time.perf_counter()
            res = await aio.gather(*(one(i, docs[i % len(docs)], True)
                                     for i in range(len(docs))), return_exceptions=True)
            wall = time.perf_counter() - t0
        lat = sorted(x for x in res if isinstance(x, float))
        return {"ok": len(lat), "wall": wall, "rate": len(lat) / wall if wall else 0,
                "p50": lat[len(lat) // 2] if lat else None,
                "first_ms": round(first_ms, 2), "bytes": rbytes, "n_chunks_first": nch}

    return asyncio.run(go())


DRIVERS = {"rocketride": _rr, "llamaindex": _ws1}


def run_once(service: str, docs: list[str], tag: str) -> dict:
    ctx = mp.get_context("spawn")
    per = max(1, len(docs) // NDRIVERS)
    args = [(f"{tag}_{i}", docs[i * per:(i + 1) * per] or docs[:per],
             CONC_PER_DRIVER, WARMUP_REQS) for i in range(NDRIVERS)]
    with ctx.Pool(NDRIVERS) as pool:
        res = pool.map(DRIVERS[service], args)
    return {"rate": round(sum(r["rate"] for r in res), 2),
            "p50": round(statistics.median([r["p50"] for r in res if r["p50"]]), 2),
            "first_ms": round(max(r["first_ms"] for r in res), 2),
            "bytes": res[0]["bytes"], "n_chunks_first": res[0]["n_chunks_first"]}


def start_ws1(workers: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS=str(workers), WS1_PORT=str(WS1_PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.perf_counter() + 300
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                m = json.loads(r.read().decode())
                if not m.get("resolved_device", "").startswith("cpu"):
                    raise RuntimeError(f"resolved_device={m.get('resolved_device')}")
                time.sleep(3)
                return p
        except RuntimeError:
            raise
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died on startup")
        time.sleep(3)
    p.kill()
    raise RuntimeError("ws1 not ready")


def summarise(rows: list[dict]) -> dict:
    rates = [r["rate"] for r in rows]
    med = statistics.median(rates)
    spread = (max(rates) - min(rates)) / max(rates) if max(rates) else 0
    lo, hi = st.bootstrap_ci(rates)
    return {"median_rate": med, "rates": rates, "spread_frac": round(spread, 4),
            "ci95": [lo, hi], "passes_gate": spread <= 0.10,
            "p50_ms": statistics.median(r["p50"] for r in rows),
            "bytes": rows[0]["bytes"], "first_ms": max(r["first_ms"] for r in rows),
            "n_chunks_first": rows[0]["n_chunks_first"]}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    findings: dict = {}
    eo.preflight("parity-corpus")
    ws1 = start_ws1(workers=8)
    print("  ws1 up (device=cpu asserted)\n")

    try:
        # ---------------- B: real mt10k distribution --------------------
        print("=" * 78)
        print("B — REAL mt10k DISTRIBUTION (natural proportions, 93.2% single-chunk)")
        print("=" * 78)
        corpus = load_corpus_docs(N_PER_RUN, "B")
        order = [(s, r) for s in ("rocketride", "llamaindex") for r in range(REPS)]
        random.Random(seed_for("corpusorder")).shuffle(order)
        raw: dict[str, list[dict]] = {"rocketride": [], "llamaindex": []}
        for svc, rep in order:
            row = run_once(svc, corpus, f"B{svc}{rep}")
            raw[svc].append(row)
            print(f"  {svc:11s} rep{rep}  {row['rate']:8.2f}/s  p50={row['p50']:7.2f}ms  "
                  f"bytes={row['bytes']:7d}", flush=True)
            time.sleep(COOLDOWN_S)
        findings["real_distribution"] = {k: summarise(v) for k, v in raw.items()}
        rr, ws = raw["rocketride"], raw["llamaindex"]
        pt, lo, hi = st.ratio_ci([r["rate"] for r in rr], [r["rate"] for r in ws])
        findings["real_distribution"]["ratio_rr_over_ws"] = {"point": pt, "ci95": [lo, hi]}
        print(f"\n  ratio RR/WS1 = {pt} [CI95 {lo}, {hi}]  "
              f"-> {'LlamaIndex faster by %.2fx' % (1/pt) if pt < 1 else 'RocketRide faster'}")

        # ---------------- C: chunk-count sweep ---------------------------
        print("\n" + "=" * 78)
        print("C — CHUNK SWEEP: does the gap narrow as model work grows? (Rule 6 test)")
        print("=" * 78)
        sweep = []
        combos = [(n, s) for n in (1, 2, 5, 10, 20) for s in ("rocketride", "llamaindex")]
        random.Random(seed_for("sweeporder")).shuffle(combos)
        by: dict[tuple, list[float]] = {}
        for nchunks, svc in combos:
            docs = [synth_doc(nchunks)] * max(40, N_PER_RUN // max(1, nchunks))
            reps = []
            for rep in range(3):
                r = run_once(svc, docs, f"C{nchunks}{svc}{rep}")
                if rep >= 1:
                    reps.append(r["rate"])
                if rep == 0:
                    actual = r["n_chunks_first"]
            by[(nchunks, svc)] = reps
            print(f"  chunks={nchunks:2d} {svc:11s} median={statistics.median(reps):8.2f}/s  "
                  f"(actual chunks in response: {actual})", flush=True)
            time.sleep(COOLDOWN_S)
        for n in (1, 2, 5, 10, 20):
            r_rr = by[(n, "rocketride")]
            r_ws = by[(n, "llamaindex")]
            pt, lo, hi = st.ratio_ci(r_rr, r_ws)
            sweep.append({"target_chunks": n,
                          "rocketride_median": statistics.median(r_rr),
                          "llamaindex_median": statistics.median(r_ws),
                          "ratio_rr_over_ws": pt, "ci95": [lo, hi]})
            print(f"  chunks={n:2d}: RR={statistics.median(r_rr):7.2f}/s  "
                  f"WS1={statistics.median(r_ws):7.2f}/s  ratio={pt:.3f} [{lo:.3f},{hi:.3f}]")
        findings["chunk_sweep"] = sweep
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("parity-corpus")

    OUT.write_text(json.dumps(findings, indent=2))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
