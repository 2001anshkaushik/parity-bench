#!/usr/bin/env python3
"""STEP 0 + STEP 1 — reproducible seeds, and the COMPLETE fault isolation matrix.

Every framework × every fault class × every rate, one table, one deterministic plan.

Baselines are written the way a competent engineer would write them — per-item try/except,
bounded concurrency, no artificial handicap. If asyncio also scores 0.00 that is the finding.

`alloc` gets extra instrumentation because 512 MB × ~57 concurrent is ~29 GB of churn and it is
the likeliest genuine differentiator: peak RSS of the whole process tree, plus macOS compressor
and swap deltas, so we can tell whether a framework "survived" honestly or whether the OS
absorbed it by compressing and swapping.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import hashlib
import json
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo            # noqa: E402
from harness.collector import read_vm_stat, _page_size  # noqa: E402
from harness.seeds import SEED_NAMESPACE, seed_for      # noqa: E402

OUT = ROOT / "results" / "fault_matrix"
FAULTS = ["raise", "hang", "alloc", "malformed"]
RATES = [0.001, 0.01, 0.05]
N = 1000
DEADLINE = 20.0          # ONE wall-clock deadline, identical for every framework
FILLER = "x" * 64
ALLOC_MB = 512
UID = os.getuid()
PAGE = _page_size()


def digest(item_id: str, filler: str = FILLER) -> str:
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


def plan(n: int, fault: str, rate: float) -> list[tuple[str, str]]:
    rng = random.Random(seed_for("faultplan", fault, rate, n))
    return [(str(i), fault if rng.random() < rate else "ok") for i in range(n)]


def payload(item_id: str, fault: str) -> str:
    return f"FP|{item_id}|{fault}|{FILLER}"


class InjectedFault(Exception):
    pass


def execute_fault(item_id: str, fault: str) -> str:
    """Python twin of the fault_probe engine node. Behaviourally identical."""
    if fault == "raise":
        raise InjectedFault(f"injected exception on item {item_id}")
    if fault == "hang":
        time.sleep(25.0)
    if fault == "alloc":
        blob = bytearray(ALLOC_MB * 1024 * 1024)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        del blob
    if fault == "malformed":
        return 12345 + ""      # type: ignore[operator]
    return digest(item_id)


# --------------------------------------------------------------------- memory watch
class MemWatch:
    """Peak RSS across this process tree + the engine tree, plus macOS compressor/swap deltas."""

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.peak_tree_rss_mb = 0.0
        self.peak_sys_used_pct = 0.0
        self._stop = None
        self._t = None
        self.vm0: dict = {}
        self.vm1: dict = {}

    def __enter__(self):
        import threading
        self.vm0 = read_vm_stat(PAGE)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *e):
        self._stop.set()
        self._t.join(timeout=3)
        self.vm1 = read_vm_stat(PAGE)

    def _loop(self):
        me = os.getpid()
        while not self._stop.is_set():
            rss = 0
            for p in psutil.process_iter(["uids", "cmdline", "memory_info", "pid", "ppid"]):
                try:
                    if not p.info["uids"] or p.info["uids"].real != UID:
                        continue
                    cmd = " ".join(p.info["cmdline"] or ())
                    if (p.info["pid"] == me or p.info["ppid"] == me
                            or "eaas.py" in cmd or "benchmark-A/engine/ai/node.py" in cmd
                            or "spawn_main" in cmd or "resource_tracker" in cmd):
                        if p.info["memory_info"]:
                            rss += p.info["memory_info"].rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self.peak_tree_rss_mb = max(self.peak_tree_rss_mb, rss / 2**20)
            self.peak_sys_used_pct = max(self.peak_sys_used_pct, psutil.virtual_memory().percent)
            self._stop.wait(self.interval)

    def report(self) -> dict:
        g = lambda k: (self.vm1.get(k, 0) - self.vm0.get(k, 0))  # noqa: E731
        return {
            "peak_tree_rss_mb": round(self.peak_tree_rss_mb, 1),
            "peak_system_mem_pct": round(self.peak_sys_used_pct, 1),
            "compressor_delta_mb": round(g("compressor_bytes") / 2**20, 1),
            "swapouts_delta": g("swapouts"),
            "compressions_delta": g("compressions"),
        }


def score(items, results, wall, extra) -> dict:
    injected = [i for i, f in items if f != "ok"]
    clean = [i for i, f in items if f == "ok"]
    failed = missing = wrong = good = 0
    for i in clean:
        r = results.get(i)
        if r is None:
            missing += 1
        elif not r[0]:
            failed += 1
        elif r[1] != digest(i):
            wrong += 1
        else:
            good += 1
    collateral = failed + missing + wrong
    nf = len(injected)
    return {
        "n_items": len(items), "n_injected": nf, "n_clean": len(clean),
        "returned": len(results), "batch_completed": len(results) == len(items),
        "collateral_failed": failed, "collateral_missing": missing,
        "collateral_wrong_output": wrong, "collateral_total": collateral,
        "isolation_ratio": round(collateral / nf, 4) if nf else 0.0,
        "goodput_pct": round(100.0 * good / max(1, len(clean)), 2),
        "wall_s": round(wall, 3), **extra,
    }


# --------------------------------------------------------------------- frameworks
async def run_rocketride(items) -> dict:
    from rocketride import RocketRideClient
    c = RocketRideClient()
    await c.connect(timeout=30000)
    r, err = await eo.guarded(c.use(filepath="pipes/fault_probe.pipe"))
    if r is None:
        await c.disconnect()
        return {"error": f"use failed: {err}"}
    token = r["token"]
    await c.send(token, payload("warm", "ok"), mimetype="text/plain")   # warm, outside timing
    results: dict[str, tuple[bool, str | None]] = {}
    t0 = time.perf_counter()
    dl = t0 + DEADLINE

    async def one(item_id, f):
        rem = dl - time.perf_counter()
        if rem <= 0:
            results[item_id] = (False, None); return
        try:
            resp = await asyncio.wait_for(
                c.send(token, payload(item_id, f), mimetype="text/plain"), timeout=rem)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                results[item_id] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                results[item_id] = (True, txt[0].strip() if isinstance(txt, list) and txt else None)
        except Exception:
            results[item_id] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    wall = time.perf_counter() - t0
    healthy = eo.healthy(15)
    if healthy:
        try:
            await asyncio.wait_for(c.terminate(token), timeout=30)
        except Exception:
            pass
    try:
        await c.disconnect()
    except Exception:
        pass
    return score(items, results, wall, {"engine_healthy_after": healthy})


async def run_asyncio(items) -> dict:
    """Bounded concurrency + per-item try/except — the shape asyncio's own docs recommend."""
    results: dict[str, tuple[bool, str | None]] = {}
    sem = asyncio.Semaphore(64)
    t0 = time.perf_counter()
    dl = t0 + DEADLINE

    async def one(item_id, f):
        async with sem:
            rem = dl - time.perf_counter()
            if rem <= 0:
                results[item_id] = (False, None); return
            try:
                v = await asyncio.wait_for(asyncio.to_thread(execute_fault, item_id, f),
                                           timeout=rem)
                results[item_id] = (True, v)
            except Exception:
                results[item_id] = (False, None)

    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    return score(items, results, time.perf_counter() - t0, {"concurrency_limit": 64})


async def run_threadpool(items) -> dict:
    results: dict[str, tuple[bool, str | None]] = {}
    t0 = time.perf_counter()
    dl = t0 + DEADLINE
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(64)
    with cf.ThreadPoolExecutor(max_workers=64) as ex:
        async def one(item_id, f):
            async with sem:
                rem = dl - time.perf_counter()
                if rem <= 0:
                    results[item_id] = (False, None); return
                try:
                    v = await asyncio.wait_for(
                        loop.run_in_executor(ex, execute_fault, item_id, f), timeout=rem)
                    results[item_id] = (True, v)
                except Exception:
                    results[item_id] = (False, None)
        await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
        wall = time.perf_counter() - t0
        ex.shutdown(wait=False, cancel_futures=True)
    return score(items, results, wall, {"max_workers": 64})


def _pp(arg):
    item_id, f = arg
    try:
        return (item_id, True, execute_fault(item_id, f))
    except Exception:
        return (item_id, False, None)


def run_processpool(items) -> dict:
    results: dict[str, tuple[bool, str | None]] = {}
    ctx = mp.get_context("spawn")
    broken = False
    t0 = time.perf_counter()
    dl = t0 + DEADLINE
    with cf.ProcessPoolExecutor(max_workers=14, mp_context=ctx) as ex:
        futs = {ex.submit(_pp, it): it[0] for it in items}
        try:
            for fut in cf.as_completed(futs, timeout=max(0.01, dl - time.perf_counter())):
                iid = futs[fut]
                try:
                    item_id, ok, val = fut.result()
                    results[item_id] = (ok, val)
                except Exception as e:
                    results[iid] = (False, None)
                    if "BrokenProcessPool" in type(e).__name__:
                        broken = True
        except cf.TimeoutError:
            pass                      # outstanding at the deadline = lost, same as async paths
        for f in futs:
            f.cancel()
        wall = time.perf_counter() - t0
        ex.shutdown(wait=False, cancel_futures=True)
    return score(items, results, wall, {"max_workers": 14, "pool_broken": broken})


# --------------------------------------------------------------------- driver
async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    rows: list[dict] = []

    # ---- STEP 0 determinism proof ------------------------------------
    print("=" * 78)
    print("STEP 0 — SEED DETERMINISM PROOF")
    print("=" * 78)
    proof = {"seed_namespace": SEED_NAMESPACE, "checks": []}
    ok_all = True
    for fault in FAULTS:
        for rate in RATES:
            a = plan(N, fault, rate)
            b = plan(N, fault, rate)
            same_plan = a == b
            inj_a = sum(1 for _, f in a if f != "ok")
            inj_b = sum(1 for _, f in b if f != "ok")
            fp = hashlib.sha256(json.dumps(a).encode()).hexdigest()[:16]
            proof["checks"].append({"fault": fault, "rate": rate, "seed": seed_for(
                "faultplan", fault, rate, N), "injected": inj_a,
                "identical_plan": same_plan, "plan_fingerprint": fp})
            ok_all &= same_plan and inj_a == inj_b
    print(f"  in-process repeat: {'ALL IDENTICAL' if ok_all else 'MISMATCH'}")
    for c in proof["checks"]:
        print(f"    {c['fault']:10s} r={c['rate']:<6} seed={c['seed']:<12} "
              f"injected={c['injected']:<4} fp={c['plan_fingerprint']}")
    proof["in_process_identical"] = ok_all
    (OUT / "seed_proof.json").write_text(json.dumps(proof, indent=2))

    # ---- STEP 1 matrix ------------------------------------------------
    print("\n" + "=" * 78)
    print("STEP 1 — COMPLETE FAULT ISOLATION MATRIX")
    print("=" * 78)

    def record(fw, fault, rate, res, mem):
        row = {"framework": fw, "fault": fault, "rate": rate,
               "seed": seed_for("faultplan", fault, rate, N), **res, **mem}
        rows.append(row)
        (OUT / "fault_matrix.json").write_text(json.dumps(rows, indent=2, default=str))
        print(f"  {fw:14s} {fault:10s} r={rate:<6} inj={res.get('n_injected'):<3} "
              f"ret={res.get('returned'):<5} collat={res.get('collateral_total'):<4} "
              f"ratio={str(res.get('isolation_ratio')):<8} good={res.get('goodput_pct')}% "
              f"peakRSS={mem.get('peak_tree_rss_mb')}MB "
              f"cmpr={mem.get('compressor_delta_mb')}MB swap={mem.get('swapouts_delta')} "
              f"{res.get('wall_s')}s", flush=True)

    for fault in FAULTS:
        for rate in RATES:
            items = plan(N, fault, rate)
            # RocketRide
            eo.preflight(f"{fault}/{rate}")
            with MemWatch() as m:
                res = await run_rocketride(items)
            record("rocketride", fault, rate, res, m.report())
            eo.postflight(f"{fault}/{rate}")
            # asyncio
            with MemWatch() as m:
                res = await run_asyncio(items)
            record("asyncio", fault, rate, res, m.report())
            # threadpool
            with MemWatch() as m:
                res = await run_threadpool(items)
            record("threadpool", fault, rate, res, m.report())
            # processpool
            with MemWatch() as m:
                res = run_processpool(items)
            record("processpool", fault, rate, res, m.report())

            if time.perf_counter() - t_start > 3300:
                print("  BUDGET GUARD: stopping matrix early", flush=True)
                break

    (OUT / "fault_matrix.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nelapsed {time.perf_counter()-t_start:.0f}s -> {OUT/'fault_matrix.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
