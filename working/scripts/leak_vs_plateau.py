#!/usr/bin/env python3
"""LEAK vs PLATEAU — extend the RocketRide block series on the SAME engine, no restart.

The matched replication gave block medians 2,065 -> 2,674 -> 2,717 MB: deltas of +609 then +43,
a 14:1 deceleration. That is the shape of a plateau, but three points cannot distinguish a plateau
from a leak that happens to be decelerating. This adds blocks 4-6 on the same engine process.

  * median settles near ~2,700  -> steady-state working set; the guidance is sizing
  * median keeps climbing       -> growth in a long-running engine, which is the deployment mode
                                   the cloud product uses, and a product finding in its own right

FIXES A REASONING GAP IN THE PREVIOUS ANALYSIS
----------------------------------------------
"The engine's own RSS after teardown is 192 MB, so it is not a simple engine leak" does not follow.
Teardown RSS is not operating RSS: a parent can be large while a task runs and shrink when the task
exits, and a task forking from a growing parent inherits that growth. So this samples THREE series
separately during every block:

    engine_own_mb   the engine process alone (the parent)
    task_tree_mb    its children only (the task process that does the work)
    driver_mb       this driver process

Only that decomposition can say whether children are forking from a growing parent.
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness.goodput import check_document, GoodputFailure   # noqa: E402
from harness.content_sanity import inspect as content_inspect  # noqa: E402
from harness.resultio import write_result                    # noqa: E402
from weekend_worker import RocketArm, rss_mb                  # noqa: E402

STATE = ROOT / "repl_state"
WARMUP_DOCS = 50
RSS_EVERY = 5
N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
N_BLOCKS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
START_IDX = int(sys.argv[3]) if len(sys.argv) > 3 else 3     # continue numbering after b0..b2


def engine_pid() -> int:
    out = subprocess.run(["lsof", "-nP", "-iTCP:5565", "-sTCP:LISTEN"],
                         capture_output=True, text=True).stdout
    return int([l.split()[1] for l in out.splitlines()[1:] if len(l.split()) > 1][0])


def host_state() -> dict:
    """Host-level memory, so a future excursion is ATTRIBUTABLE rather than merely observed.

    The blocks 2-3 excursion could not be attributed retrospectively because nothing outside the
    process trees was recorded. macOS reclaims and compresses aggressively, so a neighbouring
    process that has already exited can still have left the host in a different state.
    """
    try:
        import psutil
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return {"host_used_mb": round(vm.used / 1e6, 1),
                "host_available_mb": round(vm.available / 1e6, 1),
                "host_percent": vm.percent,
                "swap_used_mb": round(sw.used / 1e6, 1)}
    except Exception:
        return {}


def sample(pid: int) -> tuple[float, float, float]:
    """(engine_own_mb, task_tree_mb, driver_mb) — decomposed, not aggregated."""
    import psutil
    try:
        e = psutil.Process(pid)
        own = e.memory_info().rss / 1e6
        kids = 0.0
        for k in e.children(recursive=True):
            try:
                kids += k.memory_info().rss / 1e6
            except Exception:
                pass
        return own, kids, rss_mb()
    except Exception:
        return 0.0, 0.0, rss_mb()


def prewarm(seconds: float = 25.0):
    import multiprocessing as mp
    from matched_replication import _burn
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


def run_block(bid: str, pdfs, epid: int) -> dict:
    import pypdf
    arm = RocketArm(bid)
    st = {"block": bid, "arm": "rocketride", "next": 0, "goodput": 0, "faults": {},
          "rss": [], "peak_rss_mb": 0.0, "content_suspect": 0,
          "engine_own": [], "task_tree": [], "driver": [], "status": "running"}
    t0 = time.time()
    i = 0
    try:
        while i < N_DOCS:
            f = pdfs[i]
            try:
                rd = pypdf.PdfReader(str(f))
                text = "\n".join((p.extract_text() or "") for p in rd.pages)
            except Exception as e:
                st["faults"][f"parse:{type(e).__name__}"] = \
                    st["faults"].get(f"parse:{type(e).__name__}", 0) + 1
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
            except GoodputFailure as e:
                k = f"goodput:{str(e).split(':')[-1].strip()[:40]}"
                st["faults"][k] = st["faults"].get(k, 0) + 1
            except Exception as e:
                k = f"rocketride:{type(e).__name__}"
                st["faults"][k] = st["faults"].get(k, 0) + 1
            i += 1
            own, tree, drv = sample(epid)
            # ARM TOTAL INCLUDES THE DRIVER — deliberately, after nearly getting this wrong.
            # Excluding it looked right (it is "our" overhead) and moved the ratio 2.01x -> 1.74x.
            # But it is ASYMMETRIC: the LlamaIndex figure is a single process that already contains
            # the same harness work (pypdf, the driver loop) and cannot have it subtracted out.
            # Removing harness from one arm only flatters RocketRide by ~13%. Symmetric options are
            # count-on-both (this, 2.01x) or exclude-from-both (~2.4x, worse for RocketRide), so
            # this is also the conservative choice. The driver series is still recorded separately
            # so its +52 MB growth across blocks stays visible.
            total = own + tree + drv
            st["peak_rss_mb"] = max(st["peak_rss_mb"], total)
            if i % RSS_EVERY == 0:
                st["rss"].append({"n": i, "rss_mb": round(total, 1)})
                st.setdefault("host", []).append({"n": i, **host_state()})
                st["engine_own"].append({"n": i, "mb": round(own, 1)})
                st["task_tree"].append({"n": i, "mb": round(tree, 1)})
                st["driver"].append({"n": i, "mb": round(drv, 1)})
            if i % 500 == 0:
                print(f"    n={i} total={total:.0f} (engine_own={own:.0f} task={tree:.0f} "
                      f"driver={drv:.0f})", flush=True)
    finally:
        try:
            arm.close()
        except Exception:
            pass
    st["next"] = i
    st["elapsed_s"] = time.time() - t0
    st["status"] = "completed"
    post = [x["rss_mb"] for x in st["rss"] if x["n"] > WARMUP_DOCS]
    st["median_rss_post_warmup"] = round(statistics.median(post), 1) if post else None
    h = [x for x in st.get("host", []) if x["n"] > WARMUP_DOCS]
    if h:
        st["median_host_used_mb"] = round(statistics.median([x["host_used_mb"] for x in h]), 1)
        st["median_host_available_mb"] = round(statistics.median([x["host_available_mb"] for x in h]), 1)
        st["max_swap_used_mb"] = round(max(x["swap_used_mb"] for x in h), 1)
    for key in ("engine_own", "task_tree", "driver"):
        v = [x["mb"] for x in st[key] if x["n"] > WARMUP_DOCS]
        st[f"median_{key}"] = round(statistics.median(v), 1) if v else None
    (STATE / f"{bid}.json").write_text(json.dumps(st))
    print(f"  {bid}: median total {st['median_rss_post_warmup']} MB "
          f"(engine_own {st['median_engine_own']}, task {st['median_task_tree']}, "
          f"driver {st['median_driver']})  peak {st['peak_rss_mb']:.0f}  "
          f"goodput {st['goodput']}  {st['elapsed_s']/60:.1f} min", flush=True)
    return st


def main() -> int:
    epid = engine_pid()
    import psutil
    up = (time.time() - psutil.Process(epid).create_time()) / 3600
    print("=" * 92)
    print(f"LEAK vs PLATEAU — engine pid {epid}, uptime {up:.2f} h, NOT restarted")
    print(f"blocks {START_IDX}..{START_IDX+N_BLOCKS-1}, {N_DOCS} docs each, same corpus prefix")
    print("=" * 92)
    pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob("*.pdf"))
    out = []
    for b in range(START_IDX, START_IDX + N_BLOCKS):
        bid = f"b{b}_rocketride"
        if (STATE / f"{bid}.json").exists():
            try:
                d = json.loads((STATE / f"{bid}.json").read_text())
                if d.get("status") == "completed":
                    print(f"  SKIP {bid} (done)")
                    out.append(d)
                    continue
            except Exception:
                pass
        print(f"--- {bid} ---", flush=True)
        prewarm(25)
        out.append(run_block(bid, pdfs, epid))

    # combine with the original three blocks
    allb = []
    for b in range(0, START_IDX + N_BLOCKS):
        f = STATE / f"b{b}_rocketride.json"
        if f.exists():
            d = json.loads(f.read_text())
            if d.get("status") == "completed":
                allb.append(d)
    med = [d["median_rss_post_warmup"] for d in allb]
    print("\n" + "=" * 92)
    print("BLOCK SERIES, RocketRide, same engine throughout")
    print("=" * 92)
    print(f"  medians: {[round(m) for m in med]}")
    deltas = [round(med[i + 1] - med[i]) for i in range(len(med) - 1)]
    print(f"  deltas : {deltas}")
    if len(deltas) >= 3:
        tail = deltas[-2:]
        print(f"  last two deltas: {tail}")
        verdict = ("PLATEAU — later deltas are small relative to the first"
                   if abs(statistics.mean(tail)) < abs(deltas[0]) * 0.25 else
                   "STILL CLIMBING — deltas have not decayed")
        print(f"  VERDICT: {verdict}")
    print("\n  DECOMPOSITION (medians, post-warmup) — is the PARENT growing?")
    print(f"  {'block':16s} {'engine_own':>11s} {'task_tree':>11s} {'driver':>9s} {'total':>9s}")
    for d in allb:
        print(f"  {d['block']:16s} {str(d.get('median_engine_own','-')):>11s} "
              f"{str(d.get('median_task_tree','-')):>11s} {str(d.get('median_driver','-')):>9s} "
              f"{d['median_rss_post_warmup']:>9.0f}")
    p = write_result("leak_vs_plateau", {"blocks": allb, "medians": med, "deltas": deltas,
                                         "engine_pid": epid, "engine_uptime_h": round(up, 2)})
    print(f"\n  written -> {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
