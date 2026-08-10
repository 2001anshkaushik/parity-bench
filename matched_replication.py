#!/usr/bin/env python3
"""MATCHED REPLICATION — both arms, matched configuration, interleaved, n>=3.

WHAT THIS RUN IS FOR
--------------------
The 10,000-document endurance comparison had two defects: the arms ran with different thread
counts (RocketRide 1, LlamaIndex 10) and the runs were two days apart. This replaces it with a
design that can actually support a ratio claim.

DESIGN
  * 2,000 documents per block (still ~8x the ingestion work of 10,000 mt10k documents by volume)
  * n>=3 blocks per arm, INTERLEAVED A-B-A-B-A-B — not all-A-then-all-B, so any session drift
    lands on both arms rather than on one
  * block order randomised within the interleave (seeded, reproducible)
  * the machine is PRE-WARMED before every block (open item A13: ascending/cold measurement on
    this host under-reports by up to 2.2x)
  * the first WARMUP_DOCS documents of each block are measured but reported separately, and the
    RSS series drops them before any slope or median
  * both arms gated at 10 % spread across blocks; a gate-failing arm yields DIRECTION ONLY,
    never a point estimate

MATCHED CONFIGURATION — chosen on measurement, see publishable/FAIRNESS_BASIS.md
  Both arms run UNPINNED (torch default = 10 intra-op threads) at concurrency 1 sequential.
  Measured on this corpus: unpinned beats pinned by 3.07x for RocketRide and 3.26x for LlamaIndex,
  so unpinned is each arm's own best setting and the two happen to coincide.

THE ASSERTION THAT MATTERS
  Before any measurement, the in-process thread count is read from BOTH arms — the engine's task
  process via nodes/env_probe, the LlamaIndex process directly — and the run REFUSES TO START if
  they differ. Declared != measured: two configuration fixes in this project silently failed, and
  the mismatch this run exists to correct was invisible for a full 10,000-document run.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness.goodput import check_document, GoodputFailure     # noqa: E402
from harness.content_sanity import inspect as content_inspect  # noqa: E402
from harness.resultio import write_result                      # noqa: E402
from harness.seeds import seed_for                             # noqa: E402
from weekend_worker import LlamaArm, RocketArm, rss_mb, engine_tree_rss_mb  # noqa: E402

STATE = ROOT / "repl_state"
STATUS = ROOT / "repl_status.txt"
LOGS = ROOT / "repl_logs"
WARMUP_DOCS = 50
RSS_EVERY = 5
CKPT_EVERY = 100
HEARTBEAT = 60.0
THREAD_KEYS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]


def say(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "replication.log", "a") as f:
        f.write(line + "\n")


def heartbeat(**kw):
    STATUS.write_text(" ".join(f"{k}={v}" for k, v in kw.items()) +
                      f" pid={os.getpid()} updated={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")


# ---------------------------------------------------------------- configuration gate
def engine_threads() -> int:
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
                        str(ROOT / "working" / "scripts" / "probe_env.py"), f"mr{int(time.time())}"],
                       capture_output=True, text=True, cwd=str(ROOT))
    return json.loads(p.stdout)["torch_num_threads"]


def llama_threads() -> int:
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"), "-c",
                        "import torch;print(torch.get_num_threads())"],
                       capture_output=True, text=True, env=clean_env(), cwd=str(ROOT))
    return int(p.stdout.strip())


def clean_env() -> dict:
    """The matched setting: UNPINNED. Remove every thread variable rather than setting it."""
    e = dict(os.environ)
    for k in THREAD_KEYS:
        e.pop(k, None)
    return e


def assert_matched() -> int:
    """Refuse to run unless BOTH arms measure the same in-process thread count."""
    et, lt = engine_threads(), llama_threads()
    say(f"CONFIG GATE  engine task process torch threads = {et} | "
        f"LlamaIndex process torch threads = {lt}")
    if et != lt:
        raise SystemExit(
            f"REFUSING TO RUN: thread counts differ (engine {et}, llamaindex {lt}). "
            f"This is the exact defect the replication exists to correct; running anyway would "
            f"reproduce it. Restart the engine without thread env vars and retry.")
    if et == 1:
        raise SystemExit(
            f"REFUSING TO RUN: both arms are PINNED to 1 thread. Matched, but not each arm's best "
            f"setting at concurrency 1 (unpinned is 3.07x/3.26x better — FAIRNESS_BASIS.md). "
            f"Restart the engine without thread env vars.")
    say(f"CONFIG GATE PASSED — both arms matched at {et} intra-op threads, unpinned")
    return et


def restart_engine_unpinned():
    subprocess.run(["bash", str(ROOT / "working" / "scripts" / "stop_engine.sh")],
                   capture_output=True)
    time.sleep(3)
    env = clean_env()
    env["CPU_PROBE_ITERS"] = "235000"
    r = subprocess.run(["bash", str(ROOT / "working" / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout and "already has a listener" not in r.stdout:
        raise RuntimeError(f"engine did not start: {r.stdout[-300:]}")
    time.sleep(2)


# ---------------------------------------------------------------- pre-warm
def _burn(stop):
    """Module-level so multiprocessing's spawn start method can pickle it.

    A nested function here raised `Can't get local object 'prewarm.<locals>.burn'` on macOS, where
    spawn (not fork) is the default. Caught by the dry run.
    """
    x = 0
    while not stop.is_set():
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF


def prewarm(seconds: float = 25.0):
    """Drive the machine to a high-power state before measuring.

    Open item A13: an ascending/cold measurement on this host under-reports by up to 2.2x, and
    pre-warming reproduces the descending-order result. This is not optional.
    """
    say(f"pre-warm {seconds:.0f}s")
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    stop = ctx.Event()
    ps = [ctx.Process(target=_burn, args=(stop,)) for _ in range(8)]
    for p in ps:
        p.start()
    time.sleep(seconds)
    stop.set()
    for p in ps:
        p.join(timeout=5)
        if p.is_alive():
            p.terminate()


# ---------------------------------------------------------------- one block
def run_block(arm_name: str, block_id: str, pdfs, n_docs: int, engine_pid: int | None) -> dict:
    import pypdf
    arm = RocketArm(block_id) if arm_name == "rocketride" else LlamaArm()
    ck = STATE / f"{block_id}.json"
    st = {"arm": arm_name, "block": block_id, "next": 0, "goodput": 0, "faults": {},
          "rss": [], "peak_rss_mb": 0.0, "chunks": 0, "elapsed_s": 0.0,
          "content_suspect": 0, "status": "running"}
    if ck.exists():
        try:
            st = json.loads(ck.read_text())
            say(f"  resume {block_id} at {st['next']}")
        except Exception:
            pass

    def rss():
        return (engine_tree_rss_mb(engine_pid) + rss_mb()) if arm_name == "rocketride" else rss_mb()

    t0 = time.time()
    prior = st["elapsed_s"]
    last_hb = 0.0
    i = st["next"]
    try:
        while i < n_docs:
            f = pdfs[i]
            if time.time() - last_hb >= HEARTBEAT:
                heartbeat(block=block_id, arm=arm_name, doc=f"{i}/{n_docs}",
                          elapsed=f"{time.time()-t0:.0f}s", rss=f"{rss():.0f}MB",
                          goodput=st["goodput"])
                last_hb = time.time()
            try:
                rd = pypdf.PdfReader(str(f))
                text = "\n".join((p.extract_text() or "") for p in rd.pages)
            except Exception as e:
                k = f"parse:{type(e).__name__}"
                st["faults"][k] = st["faults"].get(k, 0) + 1
                i += 1
                continue
            if not text.strip():
                st["faults"]["empty_extraction"] = st["faults"].get("empty_extraction", 0) + 1
                i += 1
                continue
            if content_inspect(text)["suspect"]:
                st["content_suspect"] += 1
            try:
                chunks, vecs = arm.process(text)
                check_document(f.name, chunks, vecs)
                st["goodput"] += 1
                st["chunks"] += len(chunks)
            except GoodputFailure as e:
                k = f"goodput:{str(e).split(':')[-1].strip()[:40]}"
                st["faults"][k] = st["faults"].get(k, 0) + 1
            except Exception as e:
                k = f"{arm_name}:{type(e).__name__}"
                st["faults"][k] = st["faults"].get(k, 0) + 1
            i += 1
            r = rss()
            st["peak_rss_mb"] = max(st["peak_rss_mb"], r)
            if i % RSS_EVERY == 0:
                st["rss"].append({"n": i, "t": round(time.time() - t0, 1), "rss_mb": round(r, 1)})
            if i % CKPT_EVERY == 0:
                st["next"] = i
                st["elapsed_s"] = prior + time.time() - t0
                ck.write_text(json.dumps(st))
    finally:
        try:
            arm.close()
        except Exception:
            pass
    st["next"] = i
    st["elapsed_s"] = prior + time.time() - t0
    st["status"] = "completed"
    # WARMUP EXCLUSION: measured, but never included in a median or a slope
    post = [x for x in st["rss"] if x["n"] > WARMUP_DOCS]
    st["median_rss_post_warmup"] = round(statistics.median([x["rss_mb"] for x in post]), 1) if post else None
    st["docs_per_s_RUN_COST_ONLY"] = round(i / st["elapsed_s"], 3) if st["elapsed_s"] else None
    ck.write_text(json.dumps(st))
    say(f"  {block_id} done: {i} docs, goodput {st['goodput']}, "
        f"median RSS {st['median_rss_post_warmup']} MB, peak {st['peak_rss_mb']:.0f} MB, "
        f"{st['elapsed_s']/60:.1f} min")
    return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=2000)
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--prewarm", type=float, default=25.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    say("=" * 90)
    say(f"MATCHED REPLICATION  docs/block={a.docs}  blocks/arm={a.blocks}  "
        f"{'DRY RUN' if a.dry_run else 'REAL RUN'}")
    say("=" * 90)

    restart_engine_unpinned()
    threads = assert_matched()

    import subprocess as sp
    out = sp.run(["lsof", "-nP", "-iTCP:5565", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    engine_pid = int([l.split()[1] for l in out.splitlines()[1:] if len(l.split()) > 1][0])
    say(f"engine pid {engine_pid} (by listening socket)")

    pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob("*.pdf"))
    n = min(a.docs, len(pdfs))

    # INTERLEAVED A-B-A-B-A-B with the pair order randomised per round
    rng = random.Random(seed_for("matchedrepl"))
    plan = []
    for b in range(a.blocks):
        pair = ["rocketride", "llamaindex"]
        rng.shuffle(pair)
        for arm in pair:
            plan.append((arm, f"b{b}_{arm}"))
    say("plan: " + " -> ".join(x[0][:2].upper() for x in plan))

    results = []
    for idx, (arm, bid) in enumerate(plan):
        if (STATE / f"{bid}.json").exists():
            try:
                if json.loads((STATE / f"{bid}.json").read_text()).get("status") == "completed":
                    say(f"SKIP {bid} (already completed)")
                    results.append(json.loads((STATE / f"{bid}.json").read_text()))
                    continue
            except Exception:
                pass
        say(f"--- block {idx+1}/{len(plan)}: {bid} ---")
        prewarm(a.prewarm)
        results.append(run_block(arm, bid, pdfs, n, engine_pid))

    # ------------------------------------------------------------ analysis
    say("=" * 90)
    summary = {"threads_matched": threads, "docs_per_block": n, "blocks": a.blocks,
               "plan": [p[1] for p in plan], "blocks_detail": results}
    for arm in ("rocketride", "llamaindex"):
        rows = [r for r in results if r["arm"] == arm and r.get("median_rss_post_warmup")]
        if not rows:
            continue
        med = [r["median_rss_post_warmup"] for r in rows]
        peak = [r["peak_rss_mb"] for r in rows]
        gp = [r["goodput"] for r in rows]
        spread = (max(med) - min(med)) / max(med) if max(med) else 0
        # A spread over ONE block is identically 0 and would pass the gate trivially. A gate that
        # cannot fail is worse than no gate — require n>=3 before a pass means anything.
        gate = (len(med) >= 3) and (spread <= 0.10)
        summary[arm] = {"n_blocks": len(rows), "median_rss": med,
                        "median_of_medians": statistics.median(med),
                        "spread": round(spread, 4), "gate": gate,
                        "gate_note": ("insufficient blocks for a spread (n<3)" if len(med) < 3
                                      else ("pass" if spread <= 0.10 else "spread exceeds 10%")),
                        "peaks": peak, "goodput": gp,
                        "faults": [sum(r["faults"].values()) for r in rows],
                        "content_suspect": [r["content_suspect"] for r in rows]}
        say(f"{arm:11s} n={len(rows)} median RSS {med} -> {statistics.median(med):.0f} MB  "
            f"spread {spread*100:.1f}%  "
            f"{'GATE OK' if gate else 'GATE FAIL (' + summary[arm]['gate_note'] + ')'}")
    if "rocketride" in summary and "llamaindex" in summary:
        r, l = summary["rocketride"], summary["llamaindex"]
        ratio = r["median_of_medians"] / l["median_of_medians"]
        both = r["gate"] and l["gate"]
        summary["memory_ratio"] = {"point": round(ratio, 3), "both_gates_pass": both}
        say(f"MATCHED MEMORY RATIO RocketRide/LlamaIndex = {ratio:.2f}x  "
            f"{'QUOTABLE' if both else 'DIRECTION ONLY (a gate failed)'}")
    p = write_result("matched_replication", summary)
    say(f"written -> {p.name}")
    heartbeat(block="finished", arm="-", doc="-", elapsed="-", rss="-", goodput="-")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
