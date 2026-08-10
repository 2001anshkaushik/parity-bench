#!/usr/bin/env python3
"""NULL CONTROL on my own instrument: does the RSS sampler depress measured throughput?

LlamaIndex read 74.71 /s at 400 tok / c4 in the isolated profile and 90.99 /s at the same point
in the optimal-point run an hour later (+22 %). The profile harness runs a psutil RSS sampler
thread every 250 ms that walks the service's whole process tree; the optimal-point harness does
not. That is the same class of observer effect that biased this project 100x once before.

Predicted difference if the sampler is innocent: zero. Same service, same concurrency, same
document, sampler on vs off, alternated to cancel drift.
"""
import asyncio, json, os, statistics, subprocess, sys, threading, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
PORT = 8861; BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 40   # ~400 tokens


class RSS(threading.Thread):
    def __init__(self, pid):
        super().__init__(daemon=True); self.pid, self.peak, self.stop_flag = pid, 0.0, False

    def run(self):
        import psutil
        while not self.stop_flag:
            try:
                p = psutil.Process(self.pid)
                self.peak = max(self.peak, sum(c.memory_info().rss
                                for c in [p] + p.children(recursive=True)) / 1e6)
            except Exception:
                pass
            time.sleep(0.25)


async def window(conc=4, secs=4.0):
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
            urllib.request.urlopen(f"{BASE}/manifest", timeout=3).read(); time.sleep(3); break
        except Exception:
            time.sleep(3)
    on, off = [], []
    try:
        asyncio.run(window())                       # warm
        for i in range(6):                          # alternate to cancel drift
            if i % 2 == 0:
                s = RSS(p.pid); s.start()
                r = asyncio.run(window()); s.stop_flag = True; s.join(timeout=3); on.append(r)
            else:
                off.append(asyncio.run(window()))
            print(f"  rep {i}: {'sampler ON ' if i % 2 == 0 else 'sampler OFF'} "
                  f"{(on if i % 2 == 0 else off)[-1]:7.2f}/s", flush=True)
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
    mon, moff = statistics.median(on), statistics.median(off)
    print(f"\n  sampler ON  median {mon:7.2f}/s   n={len(on)}")
    print(f"  sampler OFF median {moff:7.2f}/s   n={len(off)}")
    print(f"  effect: {(mon / moff - 1) * 100:+.1f}%  "
          f"({'SAMPLER DEPRESSES THROUGHPUT' if mon < moff * 0.95 else 'no material effect'})")
    json.dump({"on": on, "off": off, "median_on": mon, "median_off": moff},
              open("results/sampler_nullcontrol.json", "w"), indent=1)


main()
