#!/usr/bin/env python3
"""ITEM A3, part 2 — WHY is only the embedding arm flat, and can it be fixed from outside?

The ladder (a3_serialization.py) showed the engine is not the bottleneck: the request path scales
3.69x, Python-node dispatch 3.45x, and ~15 ms of PURE-PYTHON CPU inside a node 3.59x. Only the
MiniLM arm is flat (1.46x). So the serialisation is specific to the model / native stack.

STRONGEST ALTERNATIVE (rule 6), and the reason this script exists:

  (a) TORCH INTRA-OP SATURATION — not serialisation at all. torch defaults its intra-op thread
      pool to the core count, so ONE forward pass already spreads across ~all cores. Concurrency
      then cannot help: the machine is saturated at c=1. Prior evidence: finding 7 measured
      `cores_busy 9.29` for a single engine embed. Our LlamaIndex service, by contrast, pins
      OMP_NUM_THREADS=1 and gets its parallelism from 8 worker processes — which is exactly why
      it scales and the engine does not.

  (b) A LOCK in the model or native stack serialising forward passes.

These predict opposite things and are cheaply separated:

  MEASUREMENT 1 — CPU occupancy of the engine tree at c=1 vs c=8 on the embed arm.
      (a) predicts occupancy is already near the core count at c=1 and barely rises.
      (b) predicts low occupancy at c=1 (one core) that stays low as concurrency rises.

  MEASUREMENT 2 — THE INTERVENTION. Restart the engine with the thread-limit environment
      variables set to 1 and re-run the embed concurrency sweep.
      (a) predicts the arm STARTS SCALING (each request now uses one core, so N requests use N).
      (b) predicts no change.

Measurement 2 is also the actionable half: if a documented environment variable converts a flat
service into a scaling one, that is a product finding with a fix attached, not just a benchmark
observation.

RULE 5: a mechanism that exonerates the engine ("it's just torch defaults") is the
RocketRide-favourable reading, so it is not accepted on argument. The intervention has to
actually move the number, and the null control below has to stay put.

RULE 3 NULL CONTROL: the cpu_probe arm is re-run under the same thread-limited engine. It is
pure Python and uses no BLAS, so thread limits MUST NOT change it. If it moves, the intervention
changed something other than what we think and neither reading is safe.
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
os.chdir(ROOT)

OUT = ROOT / "results" / "a3_threads.json"


def engine_cpu_percent(seconds: float = 3.0) -> dict:
    """Total CPU% across the engine process tree, sampled over a wall-clock interval."""
    import psutil
    roots = [p for p in psutil.process_iter(["pid", "name"])
             if (p.info["name"] or "").lower() == "engine"]
    procs = []
    for r in roots:
        try:
            procs += [r] + r.children(recursive=True)
        except Exception:
            pass
    seen, uniq = set(), []
    for p in procs:
        if p.pid not in seen:
            seen.add(p.pid)
            uniq.append(p)
    for p in uniq:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(seconds)
    tot = 0.0
    for p in uniq:
        try:
            tot += p.cpu_percent(None)
        except Exception:
            pass
    return {"cpu_percent": round(tot, 1), "cores_busy": round(tot / 100.0, 2),
            "procs": len(uniq)}


def load_and_sample(pipe_rel: str, conc: int, tag: str, seconds: float = 6.0) -> dict:
    """Drive `conc` concurrent requests in a background process and sample engine CPU."""
    drv = subprocess.Popen(
        [str(ROOT.parent / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "a3_load.py"),
         pipe_rel, str(conc), tag, str(seconds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT))
    time.sleep(2.5)                      # let the load reach steady state
    occ = engine_cpu_percent(3.0)
    out, _ = drv.communicate(timeout=180)
    txt = out.decode()
    rate = None
    for ln in txt.splitlines():
        if ln.startswith("RATE "):
            rate = float(ln.split()[1])
    occ["rate"] = rate
    if rate is None:
        occ["driver_output"] = txt[-400:]
    return occ


def restart_engine(threads: str | None) -> None:
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")],
                   capture_output=True)
    time.sleep(3)
    env = dict(os.environ)
    env["CPU_PROBE_ITERS"] = "235000"
    keys = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]
    if threads:
        for k in keys:
            env[k] = threads
    else:
        for k in keys:
            env.pop(k, None)
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout:
        raise RuntimeError(f"engine did not come up: {r.stdout[-400:]} {r.stderr[-200:]}")
    time.sleep(2)


def main() -> int:
    res: dict = {}
    print("=" * 100)
    print("A3 part 2 — torch intra-op saturation vs a lock, and whether it is fixable")
    print("=" * 100)

    for label, threads in (("default", None), ("threads=1", "1")):
        print(f"\n### engine with thread env: {label}")
        restart_engine(threads)
        block: dict = {}
        for arm, pipe in (("embed", "pipes/single_node.pipe"),
                          ("cpu", "pipes/a3_cpu.pipe")):
            block[arm] = {}
            for conc in (1, 8):
                s = load_and_sample(pipe, conc, f"{label}_{arm}_{conc}")
                block[arm][conc] = s
                print(f"  {arm:5s} conc={conc:2d}  rate={s['rate']}"
                      f"  cores_busy={s['cores_busy']:5.2f}  procs={s['procs']}", flush=True)
        res[label] = block

    OUT.write_text(json.dumps(res, indent=1))
    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    for arm in ("embed", "cpu"):
        d1 = res["default"][arm][1]
        d8 = res["default"][arm][8]
        t1 = res["threads=1"][arm][1]
        t8 = res["threads=1"][arm][8]
        sd = (d8["rate"] / d1["rate"]) if d1["rate"] else 0
        st = (t8["rate"] / t1["rate"]) if t1["rate"] else 0
        print(f"  {arm:5s}  default   c1={d1['rate']:8.2f}/s ({d1['cores_busy']:5.2f} cores)  "
              f"c8={d8['rate']:8.2f}/s ({d8['cores_busy']:5.2f} cores)  scaling {sd:.2f}x")
        print(f"  {arm:5s}  threads=1 c1={t1['rate']:8.2f}/s ({t1['cores_busy']:5.2f} cores)  "
              f"c8={t8['rate']:8.2f}/s ({t8['cores_busy']:5.2f} cores)  scaling {st:.2f}x")
    print(f"\n  written -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
