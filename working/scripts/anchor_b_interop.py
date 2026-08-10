#!/usr/bin/env python3
"""STEP 1 — close fairness asymmetry 2 (inter-op threads) and re-measure Anchor B.

`TORCH_NUM_THREADS=1` pins torch's INTRA-op pool but leaves INTER-op at the core count, because no
environment variable reaches it. Verified inside the task process: intra 1, inter 14. The only
lever is `torch.set_num_interop_threads()` called before torch starts parallel work, which is now
wired into `nodes/split_embed` behind `SE_INTEROP_THREADS` and reports whether it actually took.

Three engine configurations, measured in one session so drift cannot masquerade as a config effect:

    A  intra=1, inter=1      fully pinned          (the new option)
    B  intra=1, inter=14     the session-8 "tuned" (partial pin)
    C  default               untuned

Two cells: 1600 tok at concurrency 2 (Anchor B itself, a LOW-concurrency cell where intra-op
pinning is known to HURT) and at concurrency 8 (where inter-op parallelism has something to do).
Reporting only conc 2 would answer the anchor question but not the mechanism question.

RULE 5 — a further RocketRide-favourable knob, so the artifact hunt is aimed at it:
  * `interop_set` is read back FROM THE TASK PROCESS each block; a block whose report is not "ok"
    with the expected value is void rather than quietly counted.
  * LlamaIndex is measured in every block. It cannot be affected by the engine's thread settings,
    so its movement across blocks is the drift null control — the session-8 run showed that
    control does NOT fully hold (+3.4 % median, up to +19.5 %), so any RocketRide delta smaller
    than about 5 % is not reportable.
  * payload is left identical to previous runs (SE_REPORT_THREADS off during measurement).
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

OUT = ROOT / "results" / "anchor_b_interop.json"
WS1_PORT = 8831
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
UNIT = "The quick brown fox jumps over the lazy dog. "
DOC = UNIT * 160                      # ~1600 tokens
CELLS = [2, 8]
WINDOW = 4.0
REPS = 5
WARMUP = 1
MAXDRV = 4
THREAD_KEYS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]

CONFIGS = {
    "A_intra1_inter1": {"intra": True, "interop": "1"},
    "B_intra1_inter14": {"intra": True, "interop": None},
    "C_untuned": {"intra": False, "interop": None},
}

_BARRIER = None


def _init(b):
    global _BARRIER
    _BARRIER = b


def layout(conc: int) -> tuple[int, int]:
    d = min(MAXDRV, conc)
    return d, max(1, conc // d)


def restart_engine(cfg: dict) -> dict:
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
    time.sleep(3)
    env = dict(os.environ)
    env["CPU_PROBE_ITERS"] = "235000"
    for k in THREAD_KEYS:
        env.pop(k, None)
    env.pop("SE_INTEROP_THREADS", None)
    if cfg["intra"]:
        for k in THREAD_KEYS:
            env[k] = "1"
    if cfg["interop"]:
        env["SE_INTEROP_THREADS"] = cfg["interop"]
    env["SE_REPORT_THREADS"] = "1"
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout:
        raise RuntimeError(f"engine did not start: {r.stdout[-300:]}")
    time.sleep(2)
    rep = _read_threads()
    print(f"    [task process reports] {rep}", flush=True)
    # gate: the configuration we asked for must be the configuration the node got
    want_inter = int(cfg["interop"]) if cfg["interop"] else 14
    if rep.get("inter_after") != want_inter:
        raise RuntimeError(f"interop mismatch: wanted {want_inter}, node reports {rep}")
    want_intra = 1 if cfg["intra"] else 10
    if rep.get("intra_after") != want_intra:
        raise RuntimeError(f"intra mismatch: wanted {want_intra}, node reports {rep}")
    # measurement runs with the report OFF so the payload matches previous runs
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
    time.sleep(2)
    env["SE_REPORT_THREADS"] = "0"
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout:
        raise RuntimeError("engine did not restart for measurement")
    time.sleep(2)
    return rep


def _read_threads() -> dict:
    code = (
        "import asyncio,json,sys,uuid\n"
        "from pathlib import Path\n"
        "ROOT=Path.cwd(); sys.path.insert(0,str(ROOT))\n"
        "async def go():\n"
        "    from rocketride import RocketRideClient\n"
        "    b=json.loads((ROOT/'pipes'/'single_node.pipe').read_text())\n"
        "    b['project_id']=str(uuid.uuid5(uuid.NAMESPACE_DNS,'ibthr'))\n"
        "    p=ROOT/'pipes'/'generated'/'ibthr.pipe'; p.parent.mkdir(parents=True,exist_ok=True)\n"
        "    p.write_text(json.dumps(b))\n"
        "    c=RocketRideClient(); await c.connect(timeout=30000)\n"
        "    r=await c.use(filepath=str(p.relative_to(ROOT))); t=r['token']\n"
        "    o=await asyncio.wait_for(c.send(t,'x '*50,mimetype='text/plain'),timeout=300)\n"
        "    print(''.join(o.get('text',[])))\n"
        "    await c.disconnect()\n"
        "asyncio.run(go())\n")
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"), "-c", code],
                       capture_output=True, text=True, cwd=str(ROOT))
    for ln in p.stdout.splitlines():
        if ln.startswith("THREADS "):
            return json.loads(ln[8:])
    return {"error": p.stdout[-200:] + p.stderr[-200:]}


async def _windows(fire, conc, barrier):
    out = []
    for w in range(REPS + WARMUP):
        try:
            barrier.wait(timeout=180)
        except Exception:
            pass
        ok = fail = 0
        stop = time.time() + WINDOW
        t0 = time.time()

        async def worker():
            nonlocal ok, fail
            while time.time() < stop:
                try:
                    await fire()
                    ok += 1
                except Exception:
                    fail += 1
        await asyncio.gather(*(worker() for _ in range(conc)))
        if w >= WARMUP:
            out.append({"ok": ok, "fail": fail, "elapsed": time.time() - t0})
    return out


def _rr(args):
    tag, conc = args
    barrier = _BARRIER

    async def go():
        from rocketride import RocketRideClient
        b = json.loads((ROOT / "pipes" / "single_node.pipe").read_text())
        b["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ib-{tag}"))
        p = ROOT / "pipes" / "generated" / f"ib_{tag}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(b))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(p.relative_to(ROOT)))
        tok = r["token"]
        await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)

        async def fire():
            await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
        res = await _windows(fire, conc, barrier)
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        await c.disconnect()
        return res
    return asyncio.run(go())


def _li(args):
    tag, conc = args
    barrier = _BARRIER

    async def go():
        import aiohttp
        cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
        async with aiohttp.ClientSession(connector=cn,
                                         timeout=aiohttp.ClientTimeout(total=600)) as s:
            async with s.post(f"{WS1_BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
                await r.json()

            async def fire():
                async with s.post(f"{WS1_BASE}/process", json={"doc_id": "x", "text": DOC}) as r:
                    await r.json()
            return await _windows(fire, conc, barrier)
    return asyncio.run(go())


ARMS = {"rocketride": _rr, "llamaindex": _li}


def measure(arm, conc, tag):
    d, per = layout(conc)
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(d)
    with ctx.Pool(d, initializer=_init, initargs=(barrier,)) as pool:
        res = pool.map(ARMS[arm], [(f"{tag}_{i}", per) for i in range(d)])
    rates, fails = [], 0
    for w in range(REPS):
        ok = sum(r[w]["ok"] for r in res)
        fails += sum(r[w]["fail"] for r in res)
        el = max(r[w]["elapsed"] for r in res)
        rates.append(round(ok / el, 2) if el else 0.0)
    med = statistics.median(rates)
    sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0
    return {"median": med, "rates": rates, "spread": round(sp, 4),
            "gate": sp <= 0.10, "fails": fails}


def start_ws1():
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                json.loads(r.read().decode())
                time.sleep(3)
                return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(3)
    raise RuntimeError("ws1 not ready")


def main() -> int:
    eo.preflight("anchor-b-interop")
    ws1 = start_ws1()
    print("=" * 100)
    print("STEP 1 — ANCHOR B across three engine thread configurations (1600 tok)")
    print("=" * 100)
    res = {}
    try:
        for name, cfg in CONFIGS.items():
            print(f"\n### {name}")
            rep = restart_engine(cfg)
            cells = {}
            combos = [(c, a) for c in CELLS for a in ("rocketride", "llamaindex")]
            random.Random(seed_for(f"ib{name}")).shuffle(combos)
            for conc, arm in combos:
                cell = measure(arm, conc, f"{name[:3]}{conc}{arm[:2]}")
                cells[f"{conc}|{arm}"] = cell
                print(f"    c={conc:2d} {arm:11s} {cell['median']:8.2f}/s "
                      f"sp={cell['spread'] * 100:5.1f}% {'OK  ' if cell['gate'] else 'GATE'} "
                      f"fails={cell['fails']}", flush=True)
            res[name] = {"threads": rep, "cells": cells}
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("anchor-b-interop")
        OUT.write_text(json.dumps(res, indent=1))

    print("\n" + "=" * 100)
    print("ANCHOR B — 1600 tok (reference: 1.190x untuned, session-8 reproduced 1.201)")
    print("=" * 100)
    for conc in CELLS:
        print(f"\n  concurrency {conc}")
        for name in CONFIGS:
            rr = res[name]["cells"][f"{conc}|rocketride"]
            li = res[name]["cells"][f"{conc}|llamaindex"]
            pt, lo, hi = st.ratio_ci(rr["rates"], li["rates"])
            print(f"    {name:17s} RR {rr['median']:7.2f}/s {'OK ' if rr['gate'] else 'GT '}"
                  f"| LI {li['median']:7.2f}/s {'OK ' if li['gate'] else 'GT '}"
                  f"| ratio {pt:6.3f} [{lo:.3f},{hi:.3f}]")
    print("\n  INTEROP EFFECT (A vs B, RocketRide only — same intra pin, inter 1 vs 14):")
    for conc in CELLS:
        a = res["A_intra1_inter1"]["cells"][f"{conc}|rocketride"]["median"]
        b = res["B_intra1_inter14"]["cells"][f"{conc}|rocketride"]["median"]
        print(f"    c={conc:2d}  inter=1 {a:7.2f}/s vs inter=14 {b:7.2f}/s  -> {a / b:5.3f}x")
    print("\n  DRIFT NULL CONTROL (LlamaIndex across blocks — cannot be affected by engine threads):")
    for conc in CELLS:
        vals = [res[n]["cells"][f"{conc}|llamaindex"]["median"] for n in CONFIGS]
        print(f"    c={conc:2d}  {[f'{v:.2f}' for v in vals]}  "
              f"spread {(max(vals) - min(vals)) / max(vals) * 100:.1f}%")
    print(f"\n  written -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
