#!/usr/bin/env python3
"""STEP 1 — fault isolation probe. Decides whether the headline claim survives.

The earlier inference — "Model B keeps one process, therefore no blast-radius containment" —
conflated *process* isolation with *fault* isolation. A dataflow lane can catch a per-item error
and keep the batch alive without any process boundary at all. This probe tests that directly
instead of reasoning from process counts.

Identical work unit and identical fault hooks on both sides: the `fault_probe` engine node and
the Python `execute_fault()` below implement the same five behaviours, and both return the same
sha256 digest for clean items, so goodput is verified rather than assumed.

FAULT ISOLATION RATIO = collateral damage per injected fault
    collateral = clean items that failed, went missing, or returned a WRONG digest
    ratio 0.0  -> perfect isolation
    ratio >0   -> faults spill onto innocent work; >1 means each fault costs more than itself
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo  # noqa: E402

OUT = ROOT / "results" / "fault_isolation"
FAULTS = ["raise", "hang", "alloc", "malformed"]
RATES = [0.001, 0.01, 0.05]
N_MODEL_B = 1000
N_MODEL_A = 100
ITEM_TIMEOUT = 20.0      # per-item client timeout; FP_HANG_SECONDS=25 so hangs exceed it
FILLER = "x" * 64


def digest(item_id: str, filler: str) -> str:
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


def plan(n: int, fault: str, rate: float, seed: int) -> list[tuple[str, str]]:
    """Deterministic (item_id, fault) plan. Same plan for every framework."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        f = fault if rng.random() < rate else "ok"
        out.append((str(i), f))
    return out


def payload(item_id: str, fault: str) -> str:
    return f"FP|{item_id}|{fault}|{FILLER}"


# --------------------------------------------------------------------- python side
class InjectedFault(Exception):
    pass


def execute_fault(item_id: str, fault: str, filler: str = FILLER) -> str:
    """Python-side twin of the fault_probe node. Must stay behaviourally identical."""
    if fault == "raise":
        raise InjectedFault(f"injected exception on item {item_id}")
    if fault == "hang":
        time.sleep(25.0)
    if fault == "alloc":
        blob = bytearray(512 * 1024 * 1024)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        del blob
    if fault == "malformed":
        # Twin of handing the engine a wrongly-typed lane value: a type error raised by the
        # runtime's own contract rather than by us.
        return 12345 + ""      # type: ignore[operator]
    return digest(item_id, filler)


def score(items: list[tuple[str, str]], results: dict[str, tuple[bool, str | None]],
          wall: float, extra: dict) -> dict:
    """results: item_id -> (ok, value_or_None)."""
    injected = [i for i, f in items if f != "ok"]
    clean = [i for i, f in items if f == "ok"]

    collateral_failed = collateral_missing = collateral_wrong = 0
    good = 0
    for i in clean:
        r = results.get(i)
        if r is None:
            collateral_missing += 1
        elif not r[0]:
            collateral_failed += 1
        elif r[1] != digest(i, FILLER):
            collateral_wrong += 1
        else:
            good += 1
    collateral = collateral_failed + collateral_missing + collateral_wrong
    n_f = len(injected)
    faults_caught = sum(1 for i in injected if i in results and not results[i][0])

    return {
        "n_items": len(items), "n_injected": n_f, "n_clean": len(clean),
        "returned": len(results),
        "batch_completed": len(results) == len(items),
        "good_items_correct": good,
        "collateral_failed": collateral_failed,
        "collateral_missing": collateral_missing,
        "collateral_wrong_output": collateral_wrong,
        "collateral_total": collateral,
        "isolation_ratio": round(collateral / n_f, 4) if n_f else 0.0,
        "faults_reported_as_errors": faults_caught,
        "goodput_pct": round(100.0 * good / max(1, len(clean)), 2),
        "wall_s": round(wall, 3),
        **extra,
    }


# --------------------------------------------------------------------- RocketRide
async def rr_model_b(fault: str, rate: float, n: int, seed: int) -> dict:
    from rocketride import RocketRideClient

    items = plan(n, fault, rate, seed)
    c = RocketRideClient()
    await c.connect(timeout=30000)
    r, err = await eo.guarded(c.use(filepath="pipes/fault_probe.pipe"))
    if r is None:
        await c.disconnect()
        return {"error": f"use() failed: {err}"}
    token = r["token"]
    results: dict[str, tuple[bool, str | None]] = {}
    livelock = None

    async def one(item_id: str, f: str):
        try:
            resp = await asyncio.wait_for(
                c.send(token, payload(item_id, f), mimetype="text/plain"),
                timeout=ITEM_TIMEOUT)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                results[item_id] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                val = txt[0].strip() if isinstance(txt, list) and txt else None
                results[item_id] = (True, val)
        except Exception:
            results[item_id] = (False, None)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    wall = time.perf_counter() - t0

    t_rec = time.perf_counter()
    ok_after = eo.healthy(15)
    recovery = round(time.perf_counter() - t_rec, 2)
    if not ok_after:
        livelock = eo.capture_livelock(f"model_b/{fault}/{rate}").__dict__
    else:
        try:
            await asyncio.wait_for(c.terminate(token), timeout=30)
        except Exception:
            pass
    try:
        await c.disconnect()
    except Exception:
        pass
    return score(items, results, wall,
                 {"engine_healthy_after": ok_after, "health_check_s": recovery,
                  "livelock": livelock})


async def rr_model_a(fault: str, rate: float, n: int, seed: int) -> dict:
    """N concurrent pipelines, one item each — genuine per-task process isolation."""
    from rocketride import RocketRideClient

    items = plan(n, fault, rate, seed)
    base = json.loads((ROOT / "pipes" / "fault_probe.pipe").read_text())
    gen = ROOT / "pipes" / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, _ in items:
        spec = dict(base)
        spec["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fault-a-{fault}-{rate}-{i}"))
        p = gen / f"fa_{fault}_{int(rate*1000)}_{i}.pipe"
        p.write_text(json.dumps(spec))
        paths.append(str(p.relative_to(ROOT)))

    c = RocketRideClient()
    await c.connect(timeout=30000)
    results: dict[str, tuple[bool, str | None]] = {}
    t0 = time.perf_counter()
    used, err = await eo.guarded(
        asyncio.gather(*(c.use(filepath=p) for p in paths), return_exceptions=True),
        timeout=eo.WATCHDOG_S)
    if used is None:
        ev = eo.capture_livelock(f"model_a/{fault}/{rate}")
        return {"error": f"use() watchdog: {err}", "livelock": ev.__dict__,
                "n_items": len(items)}
    tokens = {}
    for (item_id, f), u in zip(items, used):
        if isinstance(u, dict) and "token" in u:
            tokens[item_id] = u["token"]
        else:
            results[item_id] = (False, None)

    async def one(item_id: str, f: str, tok: str):
        try:
            resp = await asyncio.wait_for(
                c.send(tok, payload(item_id, f), mimetype="text/plain"), timeout=ITEM_TIMEOUT)
            if isinstance(resp, dict) and "error" in resp and "text" not in resp:
                results[item_id] = (False, None)
            else:
                txt = resp.get("text") if isinstance(resp, dict) else None
                val = txt[0].strip() if isinstance(txt, list) and txt else None
                results[item_id] = (True, val)
        except Exception:
            results[item_id] = (False, None)

    fmap = dict(items)
    await asyncio.gather(*(one(i, fmap[i], t) for i, t in tokens.items()),
                         return_exceptions=True)
    wall = time.perf_counter() - t0

    ok_after = eo.healthy(15)
    livelock = None
    if not ok_after:
        livelock = eo.capture_livelock(f"model_a/{fault}/{rate}").__dict__
    else:
        await asyncio.gather(*(asyncio.wait_for(c.terminate(t), timeout=30)
                               for t in tokens.values()), return_exceptions=True)
    try:
        await c.disconnect()
    except Exception:
        pass
    return score(items, results, wall,
                 {"engine_healthy_after": ok_after, "tasks_created": len(tokens),
                  "livelock": livelock})


# --------------------------------------------------------------------- baselines
async def baseline_asyncio(fault: str, rate: float, n: int, seed: int) -> dict:
    items = plan(n, fault, rate, seed)
    results: dict[str, tuple[bool, str | None]] = {}
    sem = asyncio.Semaphore(64)

    async def one(item_id: str, f: str):
        async with sem:
            try:
                v = await asyncio.wait_for(asyncio.to_thread(execute_fault, item_id, f),
                                           timeout=ITEM_TIMEOUT)
                results[item_id] = (True, v)
            except Exception:
                results[item_id] = (False, None)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i, f) for i, f in items), return_exceptions=True)
    return score(items, results, time.perf_counter() - t0, {"engine_healthy_after": None})


def _pp_task(arg):
    item_id, f = arg
    try:
        return (item_id, True, execute_fault(item_id, f))
    except Exception:
        return (item_id, False, None)


async def baseline_processpool(fault: str, rate: float, n: int, seed: int) -> dict:
    import concurrent.futures as cf
    import multiprocessing as mp

    items = plan(n, fault, rate, seed)
    results: dict[str, tuple[bool, str | None]] = {}
    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    pool_died = False
    with cf.ProcessPoolExecutor(max_workers=14, mp_context=ctx) as ex:
        futs = {ex.submit(_pp_task, it): it[0] for it in items}
        for fut in cf.as_completed(futs, timeout=None):
            iid = futs[fut]
            try:
                item_id, ok, val = fut.result(timeout=ITEM_TIMEOUT)
                results[item_id] = (ok, val)
            except Exception as e:
                results[iid] = (False, None)
                if "BrokenProcessPool" in type(e).__name__:
                    pool_died = True
    return score(items, results, time.perf_counter() - t0,
                 {"engine_healthy_after": None, "pool_broken": pool_died})


# --------------------------------------------------------------------- driver
async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    budget_start = time.perf_counter()
    rows: list[dict] = []

    def record(scope, framework, fault, rate, res):
        row = {"scope": scope, "framework": framework, "fault": fault, "rate": rate, **res}
        rows.append(row)
        (OUT / "fault_isolation.json").write_text(json.dumps(rows, indent=2, default=str))
        print(f"  {framework:14s} {fault:10s} r={rate:<6} "
              f"inj={res.get('n_injected'):<4} ret={res.get('returned'):<5} "
              f"collat={res.get('collateral_total')} "
              f"ratio={res.get('isolation_ratio')} "
              f"good={res.get('goodput_pct')}% "
              f"healthy={res.get('engine_healthy_after')} "
              f"{res.get('wall_s')}s", flush=True)

    print("=" * 78)
    print("STEP 1 — FAULT ISOLATION PROBE")
    print("=" * 78)

    # --- Model B --------------------------------------------------------
    print(f"\n[Model B] one pipeline, n={N_MODEL_B}")
    for fault in FAULTS:
        for rate in RATES:
            tag = f"B/{fault}/{rate}"
            eo.preflight(tag)
            res = await rr_model_b(fault, rate, N_MODEL_B, seed=hash((fault, rate)) % 10**6)
            record("model_b", "rocketride", fault, rate, res)
            eo.postflight(tag)

    # --- baselines, identical injection ---------------------------------
    print(f"\n[baselines] identical plan, n={N_MODEL_B}")
    for fault in FAULTS:
        for rate in RATES:
            seed = hash((fault, rate)) % 10**6
            res = await baseline_asyncio(fault, rate, N_MODEL_B, seed)
            record("in_process", "asyncio", fault, rate, res)
            res = await baseline_processpool(fault, rate, N_MODEL_B, seed)
            record("in_process", "processpool", fault, rate, res)

    # --- Model A, downscaled ---------------------------------------------
    # Model A costs ~50 s of pipeline setup at n=100 plus teardown, so the full 4x3 grid would
    # be ~40 min of the 3 h budget for a model that livelocks at 150 anyway. Downscaled to the
    # highest rate only, which is where isolation differences are largest. Stated, not dropped.
    print(f"\n[Model A] n={N_MODEL_A}, rate=0.05 only (downscaled — see note in report)")
    for fault in FAULTS:
        tag = f"A/{fault}/0.05"
        eo.preflight(tag)
        elapsed = time.perf_counter() - budget_start
        if elapsed > 3600:
            print(f"  SKIPPED {tag}: budget guard ({elapsed:.0f}s elapsed)", flush=True)
            rows.append({"scope": "model_a", "framework": "rocketride", "fault": fault,
                         "rate": 0.05, "skipped": "budget guard"})
            continue
        res = await rr_model_a(fault, 0.05, N_MODEL_A, seed=hash((fault, 0.05)) % 10**6)
        record("model_a", "rocketride", fault, 0.05, res)
        eo.postflight(tag)

    (OUT / "fault_isolation.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nelapsed {time.perf_counter()-budget_start:.0f}s -> {OUT/'fault_isolation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
