#!/usr/bin/env python3
"""STEP 2 — what actually causes the run-to-run variance?

Observed so far: the same nominal load measured 446/s and 165/s on this service (2.7x), and the
RocketRide engine showed +/-35%. It was labelled "a host property", which is a hypothesis, not a
finding.

First real evidence arrived from the device sweep: **cpu runs spread 3-4%, mps runs spread
43-53%** on identical work. That points at accelerator contention rather than anything host-wide.

This experiment applies RULE 3 (null control): find the condition under which the variance
DISAPPEARS. Four candidate causes, each with a condition that should suppress it if it is the
cause:

    device contention   -> pin device=cpu               (predicted: variance collapses)
    load carryover      -> cooldown to quiet load avg   (predicted: variance collapses)
    page cache / warmup -> discard first N iterations    (predicted: variance collapses)
    thermal             -> long idle before the run      (predicted: variance collapses)

If variance persists under all four, none of them is the cause and the protocol must simply
require more repetitions rather than claim an explanation.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
DOC = "The quick brown fox jumps over the lazy dog. " * 40
N_DOCS = 80
REPS = 5


def _bench(args) -> float:
    """One in-process measurement: returns docs/s. Model warmed outside the timed region."""
    device, n_docs = args
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS"):
        os.environ[k] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    emb = HuggingFaceEmbedding(model_name=MODEL, device=device)
    emb.get_text_embedding_batch(["warm"])
    t0 = time.perf_counter()
    for _ in range(n_docs):
        emb.get_text_embedding_batch([DOC])
    return n_docs / (time.perf_counter() - t0)


def series(device: str, reps: int, cooldown_s: float, discard_first: int) -> dict:
    """Run `reps` measurements in ONE process (model loaded once), with optional cooldown."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    vals = []
    with ctx.Pool(1) as pool:
        for i in range(reps + discard_first):
            v = pool.apply(_bench, ((device, N_DOCS),))
            if i >= discard_first:
                vals.append(v)
            if cooldown_s:
                time.sleep(cooldown_s)
    med = statistics.median(vals)
    spread = (max(vals) - min(vals)) / max(vals) if max(vals) else 0
    return {"device": device, "reps": reps, "cooldown_s": cooldown_s,
            "discard_first": discard_first,
            "values": [round(v, 1) for v in vals],
            "median": round(med, 1), "spread_frac": round(spread, 3),
            "load_avg_at_end": round(os.getloadavg()[0], 2)}


def busy_host(seconds: float) -> None:
    """Deliberately raise the load average, to test the carryover hypothesis."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_spin, args=(seconds,)) for _ in range(12)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


def _spin(seconds: float) -> None:
    end = time.perf_counter() + seconds
    x = 0
    while time.perf_counter() < end:
        x = (x * 31 + 7) & 0xFFFFFFFF


def main() -> int:
    out = ROOT / "results" / "ws1_variance_cause.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    print("=" * 78)
    print(f"STEP 2 — VARIANCE CAUSE. n={REPS} per condition. RULE 3: find where it disappears.")
    print("=" * 78)

    conds = [
        ("mps  baseline (no cooldown)",      dict(device="mps", reps=REPS, cooldown_s=0,  discard_first=0)),
        ("cpu  baseline (no cooldown)",      dict(device="cpu", reps=REPS, cooldown_s=0,  discard_first=0)),
        ("mps  + 5s cooldown",               dict(device="mps", reps=REPS, cooldown_s=5,  discard_first=0)),
        ("cpu  + 5s cooldown",               dict(device="cpu", reps=REPS, cooldown_s=5,  discard_first=0)),
        ("mps  + discard first 2 warmups",   dict(device="mps", reps=REPS, cooldown_s=0,  discard_first=2)),
        ("cpu  + discard first 2 warmups",   dict(device="cpu", reps=REPS, cooldown_s=0,  discard_first=2)),
    ]
    for label, kw in conds:
        r = series(**kw)
        r["condition"] = label
        rows.append(r)
        print(f"  {label:32s} median={r['median']:7.1f}/s  spread={r['spread_frac']*100:5.1f}%  "
              f"values={r['values']}", flush=True)
        out.write_text(json.dumps(rows, indent=2))

    print("\n  [load carryover test] raising load average with 12 spinners for 20s ...")
    busy_host(20)
    la = os.getloadavg()
    print(f"  load avg immediately after: {la[0]:.2f}")
    r = series(device="cpu", reps=REPS, cooldown_s=0, discard_first=0)
    r["condition"] = "cpu  immediately after heavy load (no cooldown)"
    rows.append(r)
    print(f"  {r['condition']:32s} median={r['median']:7.1f}/s  spread={r['spread_frac']*100:5.1f}%  "
          f"values={r['values']}", flush=True)
    out.write_text(json.dumps(rows, indent=2))

    print("\n  --- spread by device ---")
    for dev in ("mps", "cpu"):
        sp = [r["spread_frac"] for r in rows if r["device"] == dev]
        print(f"  {dev}: spreads {[round(s*100,1) for s in sp]}%  median {statistics.median(sp)*100:.1f}%")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
