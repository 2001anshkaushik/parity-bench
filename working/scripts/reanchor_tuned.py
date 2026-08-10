#!/usr/bin/env python3
"""STEP 1 — re-anchor natively with the engine thread-pinned, tuned vs untuned side by side.

Every anchor in REBASELINE_PLAN.md was measured against an UNTUNED engine. The A3 finding showed
that costs the engine ~19 % throughput and most of its concurrency scaling. Containerising against
that reference would bake the error in permanently, so the anchors are re-measured natively first.

DESIGN — ABA, because the tuned/untuned comparison spans engine restarts:

    block 1   engine TUNED    (thread env = 1)     full grid
    block 2   engine UNTUNED  (default threads)    full grid
    block 3   engine TUNED    again                key cells only

Between-session drift is an open, unexplained problem in this project (item F), and an engine
restart is the kind of boundary it hides at. Block 3 is the drift control: if block 3 does not
reproduce block 1, the tuned-vs-untuned delta is confounded and must not be reported.

SECOND, INDEPENDENT DRIFT CONTROL: the LlamaIndex arm is measured in every block even though the
engine's thread setting cannot possibly affect it. Any movement in the LlamaIndex numbers across
blocks is pure drift, measured directly rather than assumed absent. This is the rule-3 null
control — predicted difference is zero.

RULE 5 — this change favours RocketRide, so the artifact hunt is aimed at it:
  * the pin is verified INSIDE the task process by `nodes/env_probe` (torch.get_num_threads()),
    not merely exported at engine start. torch caches its thread count at import, so an exported
    variable is a DECLARED value until the node confirms it. Gate: block 1 and 3 must report 1,
    block 2 must report >1, or the run is void.
  * the LlamaIndex arm is left exactly as it has always been configured. Tuning one side while
    re-measuring is the obvious way to manufacture a favourable result, so it is not done here;
    the fairness question is handled separately in FAIRNESS_BASIS.md.
  * peak RSS is sampled per cell for STEP 3, from outside the driver.

Anchor A = the concurrency grid. Anchor B (1600 tok / conc 2) is a CELL of that grid, so it is
measured under identical conditions rather than as a separate run. Anchor C (pool width) is a
different instrument and runs separately.
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

from harness import engine_ops as eo       # noqa: E402
from harness import stats as st            # noqa: E402
from harness.seeds import seed_for         # noqa: E402

OUT = ROOT / "results" / "reanchor_tuned.json"
WS1_PORT = 8821
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
UNIT = "The quick brown fox jumps over the lazy dog. "

TOKENS = [400, 1600]
CONCS = [1, 2, 4, 8, 16, 32]
KEY_CELLS = [(1600, 2), (400, 8), (1600, 8)]      # block 3 drift control
WINDOW = 4.0
REPS = 5
WARMUP = 1
MAXDRV = 4

THREAD_KEYS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]

_BARRIER = None


def _init(b):
    global _BARRIER
    _BARRIER = b


def doc_for(t: int) -> str:
    return UNIT * max(1, t // 10)


def layout(conc: int) -> tuple[int, int]:
    drivers = min(MAXDRV, conc)
    return drivers, max(1, conc // drivers)


# ------------------------------------------------------------------ engine lifecycle
def restart_engine(tuned: bool) -> dict:
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
    time.sleep(3)
    env = dict(os.environ)
    env["CPU_PROBE_ITERS"] = "235000"
    for k in THREAD_KEYS:
        env.pop(k, None)
    if tuned:
        for k in THREAD_KEYS:
            env[k] = "1"
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout:
        raise RuntimeError(f"engine did not start: {r.stdout[-300:]}")
    time.sleep(2)
    # DECLARED != MEASURED: ask the task process what it actually got.
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
                        str(ROOT / "scripts" / "probe_env.py"),
                        f"blk{'T' if tuned else 'U'}{int(time.time())}"],
                       capture_output=True, text=True, cwd=str(ROOT))
    try:
        info = json.loads(p.stdout)
    except Exception:
        raise RuntimeError(f"env probe failed: {p.stdout[-300:]} {p.stderr[-200:]}")
    got = info.get("torch_num_threads")
    if tuned and got != 1:
        raise RuntimeError(f"TUNED requested but task process reports torch threads={got}")
    if not tuned and (got is None or got <= 1):
        raise RuntimeError(f"UNTUNED requested but task process reports torch threads={got}")
    print(f"    [env verified] torch_num_threads={got} interop={info.get('torch_num_interop_threads')}"
          f" OMP={info['env'].get('OMP_NUM_THREADS')}", flush=True)
    return info


def peak_rss_mb() -> float:
    """Engine-tree RSS, sampled between cells. Cheap single scan, never inside a window."""
    try:
        import psutil
    except Exception:
        return 0.0
    tot, seen = 0.0, set()
    for r in psutil.process_iter(["pid", "name"]):
        if (r.info["name"] or "").lower() != "engine":
            continue
        try:
            for p in [r] + r.children(recursive=True):
                if p.pid in seen:
                    continue
                seen.add(p.pid)
                tot += p.memory_info().rss / 1e6
        except Exception:
            pass
    return round(tot, 1)


def ws1_rss_mb(root_pid: int) -> float:
    try:
        import psutil
        p = psutil.Process(root_pid)
        return round(sum(c.memory_info().rss for c in [p] + p.children(recursive=True)) / 1e6, 1)
    except Exception:
        return 0.0


# ------------------------------------------------------------------ arms
async def _run_windows(fire, conc: int, barrier, reps: int, warm: int) -> list[dict]:
    out = []
    for w in range(reps + warm):
        try:
            barrier.wait(timeout=180)
        except Exception:
            pass
        ok = fail = 0
        lat: list[float] = []
        stop = time.time() + WINDOW
        t0 = time.time()

        async def worker():
            nonlocal ok, fail
            while time.time() < stop:
                s = time.perf_counter()
                try:
                    await fire()
                    lat.append(time.perf_counter() - s)
                    ok += 1
                except Exception:
                    fail += 1

        await asyncio.gather(*(worker() for _ in range(conc)))
        el = time.time() - t0
        if w >= warm:
            ls = sorted(lat)
            out.append({"ok": ok, "fail": fail, "elapsed": el,
                        "p50_ms": round(ls[len(ls) // 2] * 1000, 2) if ls else None})
    return out


def _rr_driver(args) -> list[dict]:
    tag, doc, conc, reps, warm = args
    barrier = _BARRIER

    async def go():
        from rocketride import RocketRideClient
        base = json.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ra-{tag}"))
        p = ROOT / "pipes" / "generated" / f"ra_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

        async def fire():
            await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

        res = await _run_windows(fire, conc, barrier, reps, warm)
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
        return res

    return asyncio.run(go())


def _li_driver(args) -> list[dict]:
    tag, doc, conc, reps, warm = args
    barrier = _BARRIER

    async def go():
        import aiohttp
        cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        async with aiohttp.ClientSession(connector=cn,
                                         timeout=aiohttp.ClientTimeout(total=600)) as s:
            async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": doc}) as r:
                await r.json()

            async def fire():
                async with s.post(f"{WS1_BASE}/process", json={"doc_id": "x", "text": doc}) as r:
                    await r.json()

            return await _run_windows(fire, conc, barrier, reps, warm)

    return asyncio.run(go())


ARMS = {"rocketride": _rr_driver, "llamaindex": _li_driver}


def measure(arm: str, tokens: int, conc: int, tag: str, ws1_pid: int) -> dict:
    drivers, per = layout(conc)
    doc = doc_for(tokens)
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(drivers)
    args = [(f"{tag}_{i}", doc, per, REPS, WARMUP) for i in range(drivers)]
    with ctx.Pool(drivers, initializer=_init, initargs=(barrier,)) as pool:
        res = pool.map(ARMS[arm], args)
    rss = peak_rss_mb() if arm == "rocketride" else ws1_rss_mb(ws1_pid)

    rates, fails, p50s = [], 0, []
    for w in range(REPS):
        ok = sum(r[w]["ok"] for r in res)
        fails += sum(r[w]["fail"] for r in res)
        el = max(r[w]["elapsed"] for r in res)
        rates.append(round(ok / el, 2) if el > 0 else 0.0)
        p50s += [r[w]["p50_ms"] for r in res if r[w]["p50_ms"]]
    med = statistics.median(rates)
    sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0.0
    return {"median": med, "rates": rates, "spread": round(sp, 4), "gate": sp <= 0.10,
            "drivers": drivers, "conc_per_driver": per, "fails": fails,
            "p50_ms": round(statistics.median(p50s), 2) if p50s else None,
            "rss_mb": rss}


def start_ws1() -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                m = json.loads(r.read().decode())
                if not m.get("resolved_device", "").startswith("cpu"):
                    raise RuntimeError("ws1 resolved_device is not cpu")
                time.sleep(3)
                return p
        except RuntimeError:
            raise
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died during startup")
        time.sleep(3)
    p.kill()
    raise RuntimeError("ws1 not ready")


def run_block(name: str, tuned: bool, cells: list[tuple], ws1_pid: int, seedtag: str) -> dict:
    print(f"\n{'=' * 100}\nBLOCK {name}  — engine {'TUNED (threads=1)' if tuned else 'UNTUNED (default)'}\n{'=' * 100}")
    envinfo = restart_engine(tuned)
    combos = [(t, c, a) for (t, c) in cells for a in ("rocketride", "llamaindex")]
    random.Random(seed_for(seedtag)).shuffle(combos)
    out = {}
    for i, (t, c, a) in enumerate(combos):
        cell = measure(a, t, c, f"{name}{t}_{c}_{a[:2]}", ws1_pid)
        out[f"{t}|{c}|{a}"] = cell
        print(f"  [{i + 1:2d}/{len(combos)}] {t:5d}tok c={c:2d} {a:11s} "
              f"{cell['median']:9.2f}/s sp={cell['spread'] * 100:5.1f}% "
              f"{'OK  ' if cell['gate'] else 'GATE'} p50={cell['p50_ms']}ms "
              f"rss={cell['rss_mb']:.0f}MB fails={cell['fails']}", flush=True)
    return {"tuned": tuned, "env": envinfo, "cells": out}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    eo.preflight("reanchor")
    print("=" * 100)
    print("STEP 1 — RE-ANCHOR NATIVELY, engine thread-pinned, ABA design")
    print("=" * 100)
    ws1 = start_ws1()
    print(f"  ws1 up (cpu, 8 workers) pid={ws1.pid}")
    full = [(t, c) for t in TOKENS for c in CONCS]
    res = {}
    try:
        res["block1_tuned"] = run_block("1T", True, full, ws1.pid, "ra1")
        res["block2_untuned"] = run_block("2U", False, full, ws1.pid, "ra2")
        res["block3_tuned"] = run_block("3T", True, KEY_CELLS, ws1.pid, "ra3")
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("reanchor")
        OUT.write_text(json.dumps(res, indent=1))
        print(f"\nwritten -> {OUT}")

    b1, b2, b3 = res["block1_tuned"]["cells"], res["block2_untuned"]["cells"], res["block3_tuned"]["cells"]

    print("\n" + "=" * 100)
    print("ANCHOR A — CONCURRENCY CURVE, TUNED vs UNTUNED (RocketRide)")
    print("=" * 100)
    for t in TOKENS:
        print(f"\n  {t} tokens/doc")
        print(f"    {'conc':>5} | {'RR tuned':>18} | {'RR untuned':>18} | {'gain':>7} | {'LlamaIndex':>18} | {'ratio tuned':>20}")
        for c in CONCS:
            rt, ru = b1[f"{t}|{c}|rocketride"], b2[f"{t}|{c}|rocketride"]
            lt = b1[f"{t}|{c}|llamaindex"]
            gain = rt["median"] / ru["median"] if ru["median"] else 0
            pt, lo, hi = st.ratio_ci(rt["rates"], lt["rates"])
            print(f"    {c:5d} | {rt['median']:9.2f}/s {'OK ' if rt['gate'] else 'GT '}"
                  f"{rt['spread'] * 100:4.1f}% | {ru['median']:9.2f}/s "
                  f"{'OK ' if ru['gate'] else 'GT '}{ru['spread'] * 100:4.1f}% | "
                  f"{gain:6.2f}x | {lt['median']:9.2f}/s {'OK ' if lt['gate'] else 'GT '}"
                  f"{lt['spread'] * 100:4.1f}% | {pt:6.3f} [{lo:.3f},{hi:.3f}]")
        for lbl, blk in (("tuned  ", b1), ("untuned", b2)):
            v = [blk[f"{t}|{c}|rocketride"]["median"] for c in CONCS]
            print(f"    RR {lbl} scaling c1->c32: {max(v) / v[0]:.2f}x")

    print("\n" + "=" * 100)
    print("ANCHOR B — 1600 tok / conc 2   (native reference was RR 1.190x [1.184,1.196])")
    print("=" * 100)
    for lbl, blk in (("TUNED", b1), ("UNTUNED", b2)):
        rr, li = blk["1600|2|rocketride"], blk["1600|2|llamaindex"]
        pt, lo, hi = st.ratio_ci(rr["rates"], li["rates"])
        print(f"  {lbl:8s} RR {rr['median']:8.2f}/s sp={rr['spread'] * 100:4.1f}% "
              f"{'OK' if rr['gate'] else 'GATE'} | LI {li['median']:8.2f}/s "
              f"sp={li['spread'] * 100:4.1f}% {'OK' if li['gate'] else 'GATE'} | "
              f"ratio {pt:.3f} [{lo:.3f},{hi:.3f}]")

    print("\n" + "=" * 100)
    print("DRIFT CONTROLS")
    print("=" * 100)
    print("  (a) block1 vs block3, same TUNED config — a real delta here voids the comparison")
    for (t, c) in KEY_CELLS:
        for a in ("rocketride", "llamaindex"):
            k = f"{t}|{c}|{a}"
            d = (b3[k]["median"] / b1[k]["median"] - 1) * 100 if b1[k]["median"] else 0
            print(f"    {t:5d}tok c={c:2d} {a:11s} b1={b1[k]['median']:8.2f} "
                  f"b3={b3[k]['median']:8.2f}  {d:+6.1f}%")
    print("\n  (b) NULL CONTROL — LlamaIndex cannot be affected by the engine's thread setting;")
    print("      any block1-vs-block2 movement here is pure drift, not tuning")
    diffs = []
    for t in TOKENS:
        for c in CONCS:
            k = f"{t}|{c}|llamaindex"
            d = (b2[k]["median"] / b1[k]["median"] - 1) * 100 if b1[k]["median"] else 0
            diffs.append(d)
    print(f"      LI block2/block1 across {len(diffs)} cells: median {statistics.median(diffs):+.1f}%  "
          f"range [{min(diffs):+.1f}%, {max(diffs):+.1f}%]")

    print("\n  peak RSS observed (for STEP 3 memory ceiling):")
    for a in ("rocketride", "llamaindex"):
        vals = [(blk[k]["rss_mb"], k) for blk in (b1, b2) for k in blk if k.endswith(a)]
        mx = max(vals)
        print(f"    {a:11s} peak {mx[0]:9.1f} MB  at {mx[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
