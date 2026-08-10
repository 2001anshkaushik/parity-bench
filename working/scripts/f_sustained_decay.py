#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
OPEN ITEM F / A13 — does LlamaIndex throughput decay under MINUTES of sustained load?

Today's readings for the same nominal point (400 tok, concurrency 8) span 2.6x:
    session-9 profile      74.7 /s      (7-cell sequential run, c8 measured 4th)
    today's profile re-run 106.5 /s     (same harness, same structure)
    background-load test   198.2 /s     (short bursts, fresh service)
    harness cross-check    186-188 /s   (both harness designs agree, short bursts)

Within-run spreads are 1.6-3 %, so this is not noise. The pattern that fits: SHORT measurements
read ~190; measurements taken after minutes of prior load read ~100.

Session 6 tested exactly this shape on RocketRide over 10 bursts of 60 requests (~10 s) and
correctly found no decay. This tests a much longer horizon on the OTHER arm: continuous load at
fixed concurrency for 5 minutes, throughput reported per 10 s window.

  decay to a plateau  -> sustained capacity is ~half of burst capacity, the profile numbers are
                         the sustained ones, and every short measurement in this project overstates
  flat                -> the decay hypothesis fails and the 2.6x spread is still unexplained

RULE 5 note: this arm is LlamaIndex, so a decay finding here works AGAINST the direction the last
few sessions have been pointing. It gets the same scrutiny either way.
"""
import asyncio, json, os, statistics, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
PORT = 8877; BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 40
CONC = 8
TOTAL_S = 300.0
BUCKET_S = 10.0


async def run():
    import aiohttp
    cn = aiohttp.TCPConnector(limit=CONC, limit_per_host=CONC)
    buckets = []
    async with aiohttp.ClientSession(connector=cn,
                                     timeout=aiohttp.ClientTimeout(total=600)) as s:
        async with s.post(f"{BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
            await r.json()
        t0 = time.time(); stop = t0 + TOTAL_S
        counts = {}

        async def w():
            while time.time() < stop:
                try:
                    async with s.post(f"{BASE}/process", json={"doc_id": "x", "text": DOC}) as r:
                        await r.json()
                    b = int((time.time() - t0) // BUCKET_S)
                    counts[b] = counts.get(b, 0) + 1
                except Exception:
                    pass
        await asyncio.gather(*(w() for _ in range(CONC)))
        for b in sorted(counts):
            buckets.append(round(counts[b] / BUCKET_S, 2))
    return buckets


def main():
    env = dict(os.environ); env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.time() + 300
    while time.time() < dl:
        try:
            urllib.request.urlopen(f"{BASE}/manifest", timeout=3).read(); time.sleep(4); break
        except Exception:
            time.sleep(3)
    try:
        b = asyncio.run(run())
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
    print(f"  throughput per {BUCKET_S:.0f}s window over {TOTAL_S:.0f}s at c={CONC}:")
    for i in range(0, len(b), 6):
        print("    " + "  ".join(f"{x:7.1f}" for x in b[i:i + 6]))
    first, last = statistics.median(b[:3]), statistics.median(b[-3:])
    print(f"\n  first 3 windows median {first:7.2f}/s")
    print(f"  last  3 windows median {last:7.2f}/s")
    print(f"  decay {(1 - last / first) * 100:+.1f}%")
    v = ("SUSTAINED DECAY CONFIRMED" if last < first * 0.85 else
         "NO SUSTAINED DECAY — the 2.6x spread is NOT explained by load duration")
    print(f"  VERDICT: {v}")
    Path("results/f_sustained_decay.json").write_text(json.dumps(
        {"buckets": b, "first3": first, "last3": last, "verdict": v}, indent=1))


if __name__ == "__main__":
    main()
