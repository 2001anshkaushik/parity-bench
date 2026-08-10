#!/usr/bin/env python3
"""STEP 1 experiment A — which LAYER owns the concurrency-4 ceiling?

The service caps at ~4 effective concurrency despite 14 workers. Candidate causes span two
layers, and reasoning cannot separate them:

    ABOVE the model : uvicorn accept distribution, keep-alive connection pinning, Starlette
                      threadpool, HTTP/serialization
    AT/BELOW        : torch intra-op threads, memory bandwidth, P-core vs E-core scheduling,
                      sentence-transformers internal batching

This experiment removes the entire HTTP layer. N independent OS processes each load the model
once and embed in a loop — no uvicorn, no sockets, no Starlette, no JSON. If aggregate throughput
still caps near 4x, the ceiling is at or below the model and nothing about the web stack matters.
If it scales toward 14x, the ceiling is in the web layer.

This is the NULL CONTROL for the whole investigation: it is the variant where, if the web stack
were innocent, we would predict no ceiling.

CPU accounting is done by differencing `cpu_times()` per process (CPU-seconds consumed), not by
sampling `cpu_percent()`. Snapshot sampling was giving ~2.7 cores busy and that reading is itself
suspect — a rate estimated from two instants, on a machine whose scheduler we are trying to
characterise. CPU-seconds over the whole window is a count, not an estimate.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
DOC = "The quick brown fox jumps over the lazy dog. " * 40   # ~1.8 KB, single chunk
N_DOCS = 120


def _worker(args) -> dict:
    """Load model, warm, then embed N_DOCS. Returns wall time and CPU-seconds consumed."""
    idx, n_docs, pin, device = args
    if pin:
        for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                  "VECLIB_MAXIMUM_THREADS"):
            os.environ[k] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    import psutil
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    import torch

    emb = HuggingFaceEmbedding(model_name=MODEL, device=device)
    emb.get_text_embedding_batch(["warm"])           # warm OUTSIDE the timed region

    me = psutil.Process()
    c0 = me.cpu_times()
    t0 = time.perf_counter()
    for _ in range(n_docs):
        emb.get_text_embedding_batch([DOC])
    wall = time.perf_counter() - t0
    c1 = me.cpu_times()

    return {
        "idx": idx, "wall_s": wall, "docs": n_docs,
        "throughput_per_s": n_docs / wall,
        "cpu_s": (c1.user - c0.user) + (c1.system - c0.system),
        "torch_threads": torch.get_num_threads(),
        "device": device,
        "pid": os.getpid(),
    }


def run_level(nprocs: int, n_docs: int, pin: bool, device: str) -> dict:
    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    with ctx.Pool(nprocs) as pool:
        res = pool.map(_worker, [(i, n_docs, pin, device) for i in range(nprocs)])
    outer = time.perf_counter() - t0
    agg = sum(r["throughput_per_s"] for r in res)
    cpu = sum(r["cpu_s"] for r in res)
    span = max(r["wall_s"] for r in res)
    return {
        "processes": nprocs, "pinned": pin, "device": device,
        "aggregate_throughput_per_s": round(agg, 1),
        "per_proc_throughput": [round(r["throughput_per_s"], 1) for r in res],
        "total_cpu_seconds": round(cpu, 2),
        "max_worker_wall_s": round(span, 2),
        # CPU-seconds consumed divided by the longest worker's wall time = cores genuinely busy.
        # This is a count over a window, not a two-instant rate estimate.
        "cores_busy": round(cpu / span, 2),
        "outer_wall_s": round(outer, 2),
        "torch_threads_per_worker": res[0]["torch_threads"],
    }


def main() -> int:
    out = ROOT / "results" / f"ws1_layer_isolation_{os.environ.get('EXP_DEVICE','cpu')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    print("=" * 78)
    print("EXPERIMENT A — NULL CONTROL: model-only, NO HTTP layer at all")
    print(f"  {N_DOCS} docs per process, model loaded and warmed outside the timed region")
    print("=" * 78)
    device = os.environ.get("EXP_DEVICE", "cpu")
    print(f"  DEVICE = {device}")
    base = None
    for nprocs in (1, 2, 4, 8, 14):
        r = run_level(nprocs, N_DOCS, True, device)
        rows.append(r)
        if base is None:
            base = r["aggregate_throughput_per_s"]
        print(f"  procs={nprocs:3d} dev={device:4s} agg={r['aggregate_throughput_per_s']:8.1f}/s  "
              f"scaling={r['aggregate_throughput_per_s']/base:5.2f}x  "
              f"cores_busy={r['cores_busy']:5.2f}  torch_thr={r['torch_threads_per_worker']}",
              flush=True)
        out.write_text(json.dumps(rows, indent=2))
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
