#!/usr/bin/env python3
"""OPEN ITEM F / A13 — is CONCURRENT background CPU load the drift mechanism?

The session-9-vs-today divergence is not a flat session offset. At concurrency 1-2 the two
sessions agree within 4 %; at concurrency >= 4 today is 18-74 % faster. A uniform "slow session"
cannot do that. Something that only bites when the service is competing for cores can.

Hypothesis: BACKGROUND CPU LOAD DURING THE RUN. At c1-2 the service uses 1-2 cores of 14 and
competing work is invisible. At c>=8 it wants most of the machine, and anything else running
takes directly from it.

Note this is NOT what finding 12 refuted. Finding 12 drove load up BEFORE a run and found no
carryover effect. This is load DURING the run, which is a different mechanism.

Test: LlamaIndex at 400 tok, concurrency 8 (where the divergence is largest), with 0 / 2 / 4
competing CPU hogs. n=3 each, interleaved. If throughput falls with background load while a
concurrency-1 control does not, the mechanism is identified.
"""
import asyncio, json, multiprocessing as mp, os, statistics, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
PORT = 8873; BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 40


def hog(stop):
    x = 0
    while not stop.is_set():
        x = (x * 31 + 7) & 0xFFFFFFFF


async def measure(conc, secs=4.0):
    import aiohttp
    cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
    async with aiohttp.ClientSession(connector=cn,
                                     timeout=aiohttp.ClientTimeout(total=600)) as s:
        async with s.post(f"{BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
            await r.json()
        ok = 0; stop = time.time() + secs; t0 = time.time()

        async def w():
            nonlocal ok
            while time.time() < stop:
                try:
                    async with s.post(f"{BASE}/process", json={"doc_id": "x", "text": DOC}) as r:
                        await r.json()
                    ok += 1
                except Exception:
                    pass
        await asyncio.gather(*(w() for _ in range(conc)))
        return ok / (time.time() - t0)


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
    out = {}
    try:
        asyncio.run(measure(8))     # warm
        for nhog in (0, 2, 4):
            stop = mp.Event()
            procs = [mp.Process(target=hog, args=(stop,)) for _ in range(nhog)]
            for q in procs:
                q.start()
            time.sleep(2)
            c8 = [asyncio.run(measure(8)) for _ in range(3)]
            c1 = [asyncio.run(measure(1)) for _ in range(3)]
            stop.set()
            for q in procs:
                q.join(timeout=5)
            out[nhog] = {"c8": [round(x, 2) for x in c8], "c1": [round(x, 2) for x in c1],
                         "c8_med": round(statistics.median(c8), 2),
                         "c1_med": round(statistics.median(c1), 2)}
            print(f"  hogs={nhog}:  c8 median {out[nhog]['c8_med']:7.2f}/s   "
                  f"c1 median {out[nhog]['c1_med']:6.2f}/s", flush=True)
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
    b8, b1 = out[0]["c8_med"], out[0]["c1_med"]
    print("\n  effect of background load, relative to zero hogs:")
    for n in (0, 2, 4):
        print(f"    hogs={n}:  c8 {out[n]['c8_med'] / b8 * 100:6.1f}%   "
              f"c1 {out[n]['c1_med'] / b1 * 100:6.1f}%   <- c1 is the control")
    Path("results/f_background_load.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
