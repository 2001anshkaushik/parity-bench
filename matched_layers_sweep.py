#!/usr/bin/env python3
"""Matched-layer concurrency sweep — the curve, with the mechanism, not just the total.

Tests the prediction registered in publishable/PREREGISTRATION.md. Read that first: it states what
counts as confirmed, falsified, and VOID, and it was committed before this file reached its final
form.

Matching rule: concurrent in-flight documents.
  LlamaIndex  -> C uvicorn workers, C concurrent POSTs
  RocketRide  -> ONE pipeline, C concurrent send() calls   <- Model B's shape

Driving RocketRide as C separate pipelines would force C task processes BY CONSTRUCTION and would
falsify the flatness prediction through this harness's design rather than the engine's behaviour.
Both arms are asyncio with an identical concurrent-worker loop, so the driver is common-mode.

ACHIEVED concurrency is measured, never assumed. A flat curve obtained by not actually being
concurrent would confirm the prediction for the wrong reason.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics as st
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

import psutil                                                    # noqa: E402
from weekend_worker import RocketArm, rss_mb                     # noqa: E402
from harness import ws1_service as ws                            # noqa: E402
from harness.resultio import write_result                        # noqa: E402

CORPUS = ROOT / "corpus" / "govdocs1" / "pdfs"
STATE = ROOT / "sweep_state"
WARMUP = 50
THREADS = 10
HEARTBEAT = ROOT / "sweep_status.txt"


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def beat(**kw):
    HEARTBEAT.write_text(
        f"{' '.join(f'{k}={v}' for k, v in kw.items())} "
        f"updated={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")


def load_texts(n):
    """Parse once, outside every timed region — parsing is common-mode to both arms."""
    import pypdf
    out = []
    for f in sorted(CORPUS.glob("*.pdf")):
        if len(out) >= n:
            break
        try:
            rd = pypdf.PdfReader(str(f))
            t = "\n".join((p.extract_text() or "") for p in rd.pages)
            if t.strip():
                out.append(t)
        except Exception:
            continue
    return out


class Inflight:
    """Achieved concurrency. Incremented immediately before the await, decremented after."""

    def __init__(self):
        self.n = 0
        self.lock = threading.Lock()

    def __enter__(self):
        with self.lock:
            self.n += 1
        return self

    def __exit__(self, *a):
        with self.lock:
            self.n -= 1


class Decomposer(threading.Thread):
    """Samples the FULL decomposition continuously — counts as well as totals.

    A total alone cannot distinguish 'flat because it pools' from 'flat because the workload never
    created pressure'. The counts are what test the prediction.
    """

    def __init__(self, kind, inflight, engine_pid=None, port=None, interval=0.25):
        super().__init__(daemon=True)
        self.kind, self.inflight, self.engine_pid, self.port = kind, inflight, engine_pid, port
        self.interval, self.rows, self._stop = interval, [], threading.Event()

    def _rocket(self):
        eng = psutil.Process(self.engine_pid)
        kids = eng.children(recursive=True)
        parent_mb = eng.memory_info().rss / 1e6
        tree_mb, n = 0.0, 0
        for k in kids:
            try:
                tree_mb += k.memory_info().rss / 1e6
                n += 1
            except psutil.NoSuchProcess:
                pass
        return {"parent_mb": round(parent_mb, 1), "tree_mb": round(tree_mb, 1),
                "task_procs": n, "driver_mb": round(rss_mb(), 1),
                "total_mb": round(parent_mb + tree_mb + rss_mb(), 1)}

    def _llama(self):
        parent, workers = ws.serving_pids(self.port)
        if parent is None:
            return None
        pm, wm, n, per = 0.0, 0.0, 0, []
        try:
            pm = psutil.Process(parent).memory_info().rss / 1e6
        except psutil.NoSuchProcess:
            pass
        for pid in workers:
            try:
                v = psutil.Process(pid).memory_info().rss / 1e6
                wm += v
                per.append(round(v, 1))
                n += 1
            except psutil.NoSuchProcess:
                pass
        return {"parent_mb": round(pm, 1), "workers_mb": round(wm, 1), "worker_count": n,
                "per_worker_mb": per, "driver_mb": round(rss_mb(), 1),
                "total_mb": round(pm + wm + rss_mb(), 1)}

    def run(self):
        while not self._stop.is_set():
            try:
                r = self._rocket() if self.kind == "rocketride" else self._llama()
                if r:
                    r["inflight"] = self.inflight.n
                    self.rows.append(r)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=3)


def summarise(rows, key="total_mb"):
    if not rows:
        return {}
    tot = [r[key] for r in rows if r.get(key) is not None]
    infl = [r["inflight"] for r in rows if r.get("inflight") is not None]
    busy = [r for r in rows if r.get("inflight", 0) > 0]
    out = {"samples": len(rows),
           "median_mb": round(st.median(tot), 1) if tot else None,
           "peak_mb": round(max(tot), 1) if tot else None,
           "inflight_max": max(infl) if infl else 0,
           "inflight_median_busy": round(st.median([r["inflight"] for r in busy]), 2) if busy else 0}
    for k in ("task_procs", "worker_count"):
        v = [r[k] for r in busy if k in r]
        if v:
            out[f"{k}_min"], out[f"{k}_max"] = min(v), max(v)
            out[f"{k}_median"] = round(st.median(v), 1)
    for k in ("parent_mb", "tree_mb", "workers_mb", "driver_mb"):
        v = [r[k] for r in busy if k in r]
        if v:
            out[f"{k}_median"] = round(st.median(v), 1)
    return out


# ---------------------------------------------------------------- RocketRide: 1 pipeline, C sends
async def cell_rocket(texts, C, engine_pid, docs):
    from rocketride import RocketRideClient
    base = json.loads((ROOT / "working" / "pipes" / "embed_probe.pipe").read_text())
    uniq = f"sweep-rr-{C}-{os.getpid()}-{int(time.time())}"
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, uniq))
    p = ROOT / "working" / "pipes" / "generated" / f"sweep_rr_{C}_{os.getpid()}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base))

    c = RocketRideClient()
    await c.connect(timeout=60000)
    r = await c.use(filepath=str(p.relative_to(ROOT)))
    tok = r["token"]

    infl = Inflight()
    dec = Decomposer("rocketride", infl, engine_pid=engine_pid)
    idx = {"i": 0, "done": 0}
    lock = asyncio.Lock()
    ok = {"n": 0}

    async def worker():
        while True:
            async with lock:
                i = idx["i"]
                idx["i"] += 1
            if i >= docs:
                return
            try:
                with infl:
                    out = await asyncio.wait_for(
                        c.send(tok, texts[i % len(texts)], mimetype="text/plain"), timeout=1800)
                if out.get("documents"):
                    ok["n"] += 1
            except Exception:
                pass
            idx["done"] += 1
            if idx["done"] == WARMUP:
                dec.rows.clear()

    dec.start()
    t0 = time.time()
    await asyncio.gather(*(worker() for _ in range(C)))
    el = time.time() - t0
    dec.stop()
    try:
        await asyncio.wait_for(c.terminate(tok), timeout=120)
        await c.disconnect()
    except Exception:
        pass
    return dec.rows, el, ok["n"]


# ---------------------------------------------------------------- LlamaIndex: C workers, C POSTs
async def cell_llama(texts, C, port, docs):
    import aiohttp
    infl = Inflight()
    dec = Decomposer("llamaindex_http", infl, port=port)
    idx = {"i": 0, "done": 0}
    lock = asyncio.Lock()
    ok = {"n": 0}
    base = f"http://127.0.0.1:{port}/process"

    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=max(C, 8))) as sess:

        async def worker():
            while True:
                async with lock:
                    i = idx["i"]
                    idx["i"] += 1
                if i >= docs:
                    return
                try:
                    with infl:
                        async with sess.post(base, json={"doc_id": f"d{i}",
                                                         "text": texts[i % len(texts)]},
                                             timeout=aiohttp.ClientTimeout(total=1800)) as r:
                            out = await r.json()
                    if out.get("ok"):
                        ok["n"] += 1
                except Exception:
                    pass
                idx["done"] += 1
                if idx["done"] == WARMUP:
                    dec.rows.clear()

        dec.start()
        t0 = time.time()
        await asyncio.gather(*(worker() for _ in range(C)))
        el = time.time() - t0
        dec.stop()
    return dec.rows, el, ok["n"]


async def amain(a):
    CS = [int(x) for x in a.conc.split(",")]
    STATE.mkdir(exist_ok=True)
    say(f"loading {a.docs} documents")
    texts = load_texts(a.docs)
    say(f"  {len(texts)} texts ready")

    ep = RocketArm._engine_pid()
    if ep is None:
        say("FATAL: no engine on :5565")
        return 2

    rng = random.Random(a.seed)
    levels = list(CS)
    rng.shuffle(levels)
    order = []
    for C in levels:
        reps = list(range(a.reps))
        rng.shuffle(reps)
        order += [(C, r) for r in reps]
    say(f"order: {' '.join(f'C{c}r{r}' for c, r in order)}")

    svc = {"h": None, "C": None}

    async def ensure(C):
        if svc["C"] == C:
            return
        if svc["h"]:
            ws.stop(svc["h"])
            await asyncio.sleep(2)
        h = ws.start(workers=C, port=a.port, threads=THREADS)
        await asyncio.get_event_loop().run_in_executor(None, lambda: ws.wait_warm(h, 900))
        thr = sorted(set(h.measured_threads.values()))
        assert len(thr) == 1 and thr[0][0] == THREADS, f"thread mismatch C={C}: {thr}"
        svc["h"], svc["C"] = h, C
        say(f"  service: {len(h.warm_pids)}/{C} workers warm, torch={thr}")

    cells = []
    try:
        for n, (C, r) in enumerate(order, 1):
            ck = STATE / f"C{C}_r{r}.json"
            if ck.exists():
                cells.append(json.loads(ck.read_text()))
                say(f"  resume: C={C} r{r} already done")
                continue
            await ensure(C)
            beat(cell=f"{n}/{len(order)}", C=C, rep=r, phase="llamaindex")
            lrows, lel, lok = await cell_llama(texts, C, a.port, a.docs)
            beat(cell=f"{n}/{len(order)}", C=C, rep=r, phase="rocketride")
            rrows, rel, rok = await cell_rocket(texts, C, ep, a.docs)
            ls, rs = summarise(lrows), summarise(rrows)
            cell = {"concurrency": C, "rep": r, "docs": a.docs,
                    "llamaindex_http": {**ls, "workers_declared": C, "goodput": lok,
                                        "elapsed_s": round(lel, 1),
                                        "throughput_per_s": round(a.docs / lel, 2),
                                        "topology": f"driver -> HTTP/1.1 -> uvicorn parent -> {C} worker(s)"},
                    "rocketride": {**rs, "pipelines": 1, "goodput": rok,
                                   "elapsed_s": round(rel, 1),
                                   "throughput_per_s": round(a.docs / rel, 2),
                                   "topology": f"driver -> WebSocket+DAP -> engine parent -> task tree, {C} in-flight"}}
            lm, rm = ls.get("median_mb"), rs.get("median_mb")
            cell["ratio_rr_over_li"] = round(rm / lm, 3) if (lm and rm) else None
            # VOID if achieved concurrency did not reach offered (PREREGISTRATION section 4)
            cell["achieved_ok"] = (ls.get("inflight_max", 0) >= C and rs.get("inflight_max", 0) >= C)
            cells.append(cell)
            ck.write_text(json.dumps(cell))
            say(f"  C={C:2d} r{r}: LI {lm} MB ({ls.get('worker_count_median')}w, "
                f"infl {ls.get('inflight_max')}) | RR {rm} MB "
                f"({rs.get('task_procs_median')} task, infl {rs.get('inflight_max')}) | "
                f"ratio {cell['ratio_rr_over_li']} | achieved={'OK' if cell['achieved_ok'] else 'SHORT'}")
    finally:
        if svc["h"]:
            ws.stop(svc["h"])

    curve = []
    for C in CS:
        g = [c for c in cells if c["concurrency"] == C]
        if not g:
            continue
        lm = [c["llamaindex_http"]["median_mb"] for c in g if c["llamaindex_http"].get("median_mb")]
        rm = [c["rocketride"]["median_mb"] for c in g if c["rocketride"].get("median_mb")]
        rt = [c["rocketride"].get("task_procs_median") for c in g if c["rocketride"].get("task_procs_median")]
        rtree = [c["rocketride"].get("tree_mb_median") for c in g if c["rocketride"].get("tree_mb_median")]
        if not lm or not rm:
            continue
        sp = lambda v: round((max(v) - min(v)) / st.median(v) * 100, 1) if st.median(v) else 999
        curve.append({
            "concurrency": C, "n": len(g),
            "llamaindex_median_mb": round(st.median(lm), 1), "llamaindex_spread_pct": sp(lm),
            "llamaindex_gate": "PASS" if sp(lm) <= 10 else "FAIL",
            "rocketride_median_mb": round(st.median(rm), 1), "rocketride_spread_pct": sp(rm),
            "rocketride_gate": "PASS" if sp(rm) <= 10 else "FAIL",
            "rocketride_task_procs": round(st.median(rt), 1) if rt else None,
            "rocketride_tree_mb": round(st.median(rtree), 1) if rtree else None,
            "ratio_rr_over_li": round(st.median(rm) / st.median(lm), 3),
            "all_cells_achieved": all(c["achieved_ok"] for c in g),
        })

    out = {"preregistration": "publishable/PREREGISTRATION.md",
           "matching_rule": "concurrent in-flight documents; LlamaIndex workers=C, "
                            "RocketRide ONE pipeline with C in-flight sends (Model B shape)",
           "threads_intra": THREADS, "docs_per_cell": a.docs, "reps": a.reps,
           "engine_pid": ep, "cells": cells, "curve": curve}

    say("\n=== CURVE ===")
    say(f"  {'C':>3} {'LI MB':>8} {'gate':>5} {'RR MB':>8} {'gate':>5} {'RR task':>8} "
        f"{'RR tree':>8} {'RR/LI':>7} {'achieved':>9}")
    for c in curve:
        say(f"  {c['concurrency']:>3} {c['llamaindex_median_mb']:>8} {c['llamaindex_gate']:>5} "
            f"{c['rocketride_median_mb']:>8} {c['rocketride_gate']:>5} "
            f"{str(c['rocketride_task_procs']):>8} {str(c['rocketride_tree_mb']):>8} "
            f"{c['ratio_rr_over_li']:>7} {'OK' if c['all_cells_achieved'] else 'SHORT':>9}")
    cross = [c for c in curve if c["ratio_rr_over_li"] < 1.0]
    say(f"\n  CROSSOVER at C={cross[0]['concurrency']}" if cross else
        "\n  NO crossover in the measured range")
    tp = [c["rocketride_task_procs"] for c in curve if c["rocketride_task_procs"]]
    tr = [c["rocketride_tree_mb"] for c in curve if c["rocketride_tree_mb"]]
    if tp:
        say(f"  RocketRide task processes across C: {tp}  ({'FLAT' if max(tp)-min(tp) <= 1 else 'GROWS'})")
    if tr:
        gr = (max(tr) - min(tr)) / min(tr) * 100
        say(f"  RocketRide task-tree MB across C: {tr}  (range {gr:.0f}% -> "
            f"{'FLAT, prediction holds' if gr <= 25 else 'GROWS, PREDICTION FALSIFIED'})")
    say(f"written -> {write_result('matched_layers_sweep', out)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=500)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conc", type=str, default="1,2,4,8,16")
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--seed", type=int, default=23)
    a = ap.parse_args()
    return asyncio.run(amain(a))


if __name__ == "__main__":
    raise SystemExit(main())
