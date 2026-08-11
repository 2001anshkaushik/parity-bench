#!/usr/bin/env python3
"""Matched-layer replication — both arms as client -> network -> service -> worker.

See publishable/MATCHED_LAYERS.md. The existing matched_replication.py compares an IN-PROCESS
LlamaIndex against a client-server RocketRide; this runs LlamaIndex through ws1/service.py over HTTP
so the shapes match.

Every result row carries the topology that produced it. A bare ratio is what let 2.0x and 22.8x
coexist in this repo.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from weekend_worker import LlamaHttpArm, RocketArm, rss_mb, engine_tree_rss_mb  # noqa: E402
from harness import ws1_service as ws                                          # noqa: E402
from harness.resultio import write_result                                      # noqa: E402

CORPUS = ROOT / "corpus" / "govdocs1" / "pdfs"
WARMUP = 50          # discarded before any statistic, per BENCHMARK_SETUP.md section 4
THREADS = 10         # RocketRide's unpinned intra-op count, measured. Both arms must report this.


def say(m):
    print(m, flush=True)


def engine_pid():
    return RocketArm._engine_pid()


def rr_threads() -> int:
    import subprocess
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
                        str(ROOT / "working" / "scripts" / "probe_env.py"), f"ml{int(time.time())}"],
                       capture_output=True, text=True, cwd=str(ROOT))
    return json.loads(p.stdout)["torch_num_threads"]


def run_block(arm, pdfs, n_docs, label, sample_every=5):
    """One block. Returns rss series (post-warmup), elapsed, goodput, faults."""
    import pypdf
    from harness.goodput import check_document, GoodputFailure
    rss, faults, good, chunks = [], {}, 0, 0
    t0 = time.time()
    for i in range(n_docs):
        f = pdfs[i]
        try:
            rd = pypdf.PdfReader(str(f))
            text = "\n".join((p.extract_text() or "") for p in rd.pages)
        except Exception as e:
            faults[f"parse:{type(e).__name__}"] = faults.get(f"parse:{type(e).__name__}", 0) + 1
            continue
        if not text.strip():
            faults["empty_extraction"] = faults.get("empty_extraction", 0) + 1
            continue
        try:
            ch, em = arm.process(text)
            check_document(f.name, ch, em)
            good += 1
            chunks += len(ch)
        except GoodputFailure as e:
            faults[f"goodput:{e}"] = faults.get(f"goodput:{e}", 0) + 1
        except Exception as e:
            faults[f"err:{type(e).__name__}"] = faults.get(f"err:{type(e).__name__}", 0) + 1
        if i >= WARMUP and i % sample_every == 0:
            rss.append(arm.rss())
    return {"label": label, "rss": rss, "elapsed_s": time.time() - t0, "goodput": good,
            "chunks": chunks, "faults": faults,
            "median_rss_mb": round(st.median(rss), 1) if rss else None,
            "peak_rss_mb": round(max(rss), 1) if rss else None}


def ci95(v):
    """Median with a 95% CI. n is small, so use the order-statistic CI, not a normal approximation."""
    if len(v) < 2:
        return (st.median(v) if v else None, None, None)
    s = sorted(v)
    return (st.median(s), s[0], s[-1])


def spread_pct(v):
    return (max(v) - min(v)) / st.median(v) * 100 if v and st.median(v) else float("inf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=2000)
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pdfs = sorted(CORPUS.glob("*.pdf"))
    if len(pdfs) < a.docs:
        say(f"FATAL: corpus has {len(pdfs)} pdfs, need {a.docs}")
        return 2
    say(f"corpus: {len(pdfs)} pdfs, using first {a.docs}")

    ep = engine_pid()
    if ep is None:
        say("FATAL: no engine on :5565 — start it first")
        return 2

    h = ws.start(workers=a.workers, port=a.port, threads=THREADS)
    try:
        ws.wait_warm(h, timeout=900)
    except ws.Ws1NotWarm as e:
        say(f"FATAL: {e}")
        ws.stop(h)
        return 2
    thr = sorted(set(h.measured_threads.values()))
    say(f"service: {len(h.warm_pids)}/{a.workers} workers warm, torch(intra,interop)={thr}")

    # ---- CONFIG GATE: both arms must report the same in-process thread count -------------------
    et = rr_threads()
    lt = thr[0][0] if thr else -1
    say(f"CONFIG GATE  engine task process torch threads = {et} | ws1 worker torch threads = {lt}")
    if et != lt or len(thr) != 1:
        say(f"CONFIG GATE FAILED — REFUSING TO RUN. arms not matched ({et} vs {thr})")
        ws.stop(h)
        return 3
    say(f"CONFIG GATE PASSED — both arms at {et} intra-op threads")

    plan = []
    for b in range(a.blocks):
        pair = ["rocketride", "llamaindex_http"]
        random.Random(a.seed + b).shuffle(pair)
        plan += [(p, b) for p in pair]
    say(f"plan: {' '.join(f'{p}/b{b}' for p, b in plan)}")

    out = {"topology": {
               "rocketride": "driver -> WebSocket+DAP -> engine parent -> 1 task process",
               "llamaindex_http": f"driver -> HTTP/1.1 -> uvicorn parent -> {a.workers} worker(s)"},
           "workers": a.workers, "concurrency": 1, "docs_per_block": a.docs,
           "threads_intra": et, "engine_pid": ep, "blocks": []}

    for arm_name, b in plan:
        say(f"--- {arm_name} block {b} ---")
        if arm_name == "rocketride":
            arm = RocketArm(f"ml{b}")
            arm.rss = lambda: engine_tree_rss_mb(ep) + rss_mb()
        else:
            arm = LlamaHttpArm(port=a.port)
        r = run_block(arm, pdfs, a.docs, f"{arm_name}_b{b}")
        r["arm"] = arm_name
        r["topology"] = out["topology"][arm_name]
        r["workers"] = a.workers if arm_name == "llamaindex_http" else 1
        arm.close()
        out["blocks"].append(r)
        say(f"    goodput={r['goodput']} median_rss={r['median_rss_mb']} MB "
            f"peak={r['peak_rss_mb']} MB elapsed={r['elapsed_s']:.1f}s faults={sum(r['faults'].values())}")

    ws.stop(h)

    for name in ("rocketride", "llamaindex_http"):
        bl = [x for x in out["blocks"] if x["arm"] == name]
        med = [x["median_rss_mb"] for x in bl if x["median_rss_mb"]]
        el = [x["elapsed_s"] for x in bl]
        if med:
            m, lo, hi = ci95(med)
            out[f"{name}_memory"] = {"median_mb": m, "lo": lo, "hi": hi, "n": len(med),
                                     "spread_pct": round(spread_pct(med), 1),
                                     "gate": "PASS" if spread_pct(med) <= 10 else "FAIL"}
            m2, lo2, hi2 = ci95(el)
            out[f"{name}_wall"] = {"median_s": round(m2, 1), "lo": round(lo2, 1), "hi": round(hi2, 1),
                                   "n": len(el), "spread_pct": round(spread_pct(el), 1),
                                   "gate": "PASS" if spread_pct(el) <= 10 else "FAIL"}

    rm = out.get("rocketride_memory", {}).get("median_mb")
    lm = out.get("llamaindex_http_memory", {}).get("median_mb")
    if rm and lm:
        out["memory_ratio_rr_over_li"] = round(rm / lm, 3)
        say(f"\nMATCHED MEMORY  RocketRide {rm} MB / LlamaIndex-HTTP {lm} MB = {rm/lm:.2f}x "
            f"at {a.workers} worker(s), concurrency 1")
    rw = out.get("rocketride_wall", {}).get("median_s")
    lw = out.get("llamaindex_http_wall", {}).get("median_s")
    if rw and lw:
        out["wall_ratio_rr_over_li"] = round(rw / lw, 3)
        say(f"MATCHED WALL    RocketRide {rw}s / LlamaIndex-HTTP {lw}s = {rw/lw:.2f}x")

    if not a.dry_run:
        p = write_result("matched_layers", out)
        say(f"written -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
