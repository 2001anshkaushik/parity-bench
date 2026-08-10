#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
OPEN ITEM A13 — why did the isolated profile read 74.7 /s where later runs read 89-91 /s?

The RSS sampler was already exonerated by null control (-0.4 %). The remaining specific hypothesis
is the one the project has already been burned by once:

    `isolated_profile.py::start_ws1` gates readiness on GET /manifest, then sleeps 3 s.
    `ws1/service.py:128` answers /manifest from ONE worker and even reports os.getpid().
    The documented correct gate is counting 8 `warm in` lines, one per worker.

So the profile may have begun measuring while most of the 8 workers had never loaded the model.
74.7 / 90 = 83 %, which is what you would see with roughly 6-7 of 8 workers warm.

A/B, alternated to cancel drift, n=3 each:

    COLD-GATE  start, poll /manifest, sleep 3, measure immediately   (what the profile did)
    WARM-GATE  start, wait for 8 `warm in` lines, then measure       (what it should have done)

Same service, same concurrency (4), same document (~400 tokens), same measurement window. If
COLD reads ~75 and WARM ~90, A13 is explained and the fix is a one-line gate change. If both read
~90, the hypothesis is refuted and the drift is something else.

RULE 3: the prediction if the hypothesis is FALSE is zero difference. That is the null this test
is built to be able to return.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

PORT = 8871
BASE = f"http://127.0.0.1:{PORT}"
LOG = ROOT / "logs" / "a13_ws1.out"
DOC = "The quick brown fox jumps over the lazy dog. " * 40      # ~400 tokens
CONC = 4
WINDOW = 4.0
WORKERS = 8


def launch():
    LOG.write_text("")
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS=str(WORKERS), WS1_PORT=str(PORT))
    f = open(LOG, "w")
    return subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT),
                            env=env, stdout=f, stderr=subprocess.STDOUT)


def gate_manifest(p):
    """The profile's gate: one worker answers, then sleep 3."""
    dl = time.time() + 300
    while time.time() < dl:
        try:
            with urllib.request.urlopen(f"{BASE}/manifest", timeout=3) as r:
                json.loads(r.read().decode())
            time.sleep(3)
            return
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(1)
    raise RuntimeError("manifest gate timed out")


def gate_warm(p):
    """The documented gate: every worker has logged that it finished loading the model."""
    dl = time.time() + 400
    while time.time() < dl:
        try:
            n = LOG.read_text(errors="ignore").count("warm in")
        except Exception:
            n = 0
        if n >= WORKERS:
            time.sleep(2)
            return n
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(1)
    raise RuntimeError(f"only {LOG.read_text(errors='ignore').count('warm in')} workers warm")


def warm_count() -> int:
    try:
        return LOG.read_text(errors="ignore").count("warm in")
    except Exception:
        return 0


async def measure():
    import aiohttp
    cn = aiohttp.TCPConnector(limit=CONC, limit_per_host=CONC)
    async with aiohttp.ClientSession(connector=cn,
                                     timeout=aiohttp.ClientTimeout(total=600)) as s:
        async with s.post(f"{BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
            await r.json()
        ok = 0
        stop = time.time() + WINDOW
        t0 = time.time()

        async def w():
            nonlocal ok
            while time.time() < stop:
                try:
                    async with s.post(f"{BASE}/process", json={"doc_id": "x", "text": DOC}) as r:
                        await r.json()
                    ok += 1
                except Exception:
                    pass
        await asyncio.gather(*(w() for _ in range(CONC)))
        return ok / (time.time() - t0)


def trial(kind: str) -> dict:
    p = launch()
    try:
        if kind == "cold":
            gate_manifest(p)
        else:
            gate_warm(p)
        warm_at_start = warm_count()
        rate = asyncio.run(measure())
        warm_at_end = warm_count()
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        time.sleep(4)
    return {"kind": kind, "rate": round(rate, 2),
            "workers_warm_at_start": warm_at_start, "workers_warm_at_end": warm_at_end}


def main() -> int:
    print("=" * 92)
    print("A13 — does the readiness gate explain 74.7 vs 90 /s?  (LlamaIndex, 400 tok, c=4)")
    print("=" * 92)
    res = []
    for i in range(6):
        kind = "cold" if i % 2 == 0 else "warm"
        t = trial(kind)
        res.append(t)
        print(f"  trial {i}  {kind.upper():4s}-gate  {t['rate']:7.2f}/s   "
              f"workers warm at start={t['workers_warm_at_start']}/{WORKERS} "
              f"at end={t['workers_warm_at_end']}/{WORKERS}", flush=True)

    cold = [r["rate"] for r in res if r["kind"] == "cold"]
    warm = [r["rate"] for r in res if r["kind"] == "warm"]
    mc, mw = statistics.median(cold), statistics.median(warm)
    print("\n" + "=" * 92)
    print(f"  COLD-gate (profile's method) median {mc:7.2f}/s   n={len(cold)}  {cold}")
    print(f"  WARM-gate (correct method)   median {mw:7.2f}/s   n={len(warm)}  {warm}")
    print(f"  effect: cold reads {mc / mw * 100:.1f}% of warm  ({(mc / mw - 1) * 100:+.1f}%)")
    verdict = ("CONFIRMED — the readiness gate explains A13" if mc < mw * 0.93 else
               "REFUTED — the gate is not the cause; A13 remains open")
    print(f"  VERDICT: {verdict}")
    (ROOT / "results" / "a13_warmgate.json").write_text(json.dumps(
        {"trials": res, "median_cold": mc, "median_warm": mw, "verdict": verdict}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
