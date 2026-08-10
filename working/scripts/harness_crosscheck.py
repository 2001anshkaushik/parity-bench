#!/usr/bin/env python3
"""Which harness is telling the truth at concurrency 8 — 198/s or 106/s?

The single-process background-load harness read 198 /s at c8; the multiprocess profile harness
read 106 /s at the same nominal point. Both cannot be right, and every saturation point rests on
this. Two independent checks:

  1. VERIFY THE WORK. Inspect a response body and confirm the service actually returned chunks
     and embedding vectors. A fast path that returns an error body with HTTP 200 would inflate a
     success count, since both harnesses only count non-exceptions.
  2. COUNT SERVER-SIDE. Compare the client's completed-request count against the number of
     documents the service reports processing, so the rate does not depend on client bookkeeping.

Then measure the same offered concurrency both ways back to back in one process-lifetime.
"""
import asyncio, json, multiprocessing as mp, os, statistics, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
PORT = 8875; BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 40
WINDOW = 4.0


async def single_proc(conc, secs=WINDOW):
    import aiohttp
    cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
    async with aiohttp.ClientSession(connector=cn,
                                     timeout=aiohttp.ClientTimeout(total=600)) as s:
        async with s.post(f"{BASE}/process", json={"doc_id": "w", "text": DOC}) as r:
            body = await r.json()
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
        return ok / (time.time() - t0), body


def _drv(args):
    conc, secs = args

    async def go():
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
                        async with s.post(f"{BASE}/process",
                                          json={"doc_id": "x", "text": DOC}) as r:
                            await r.json()
                        ok += 1
                    except Exception:
                        pass
            await asyncio.gather(*(w() for _ in range(conc)))
            return ok, time.time() - t0
    return asyncio.run(go())


def multi_proc(total_conc, drivers=4, secs=WINDOW):
    per = max(1, total_conc // drivers)
    ctx = mp.get_context("spawn")
    with ctx.Pool(drivers) as pool:
        res = pool.map(_drv, [(per, secs)] * drivers)
    ok = sum(r[0] for r in res)
    el = max(r[1] for r in res)
    return ok / el


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
        rate, body = asyncio.run(single_proc(1))
        print("  CHECK 1 — response body keys:", sorted(body.keys())[:8])
        print(f"    n_chunks={body.get('n_chunks')}  "
              f"embedding dims={len(body.get('embeddings', [[]])[0]) if body.get('embeddings') else 'ABSENT'}")
        print(f"    doc_id={body.get('doc_id')}  error={body.get('error')}")
        print("\n  CHECK 2 — same offered concurrency, both harnesses, alternated (n=3):")
        sp, mpr = [], []
        for i in range(3):
            r1, _ = asyncio.run(single_proc(8)); sp.append(r1)
            r2 = multi_proc(8); mpr.append(r2)
            print(f"    rep {i}: single-process {r1:8.2f}/s   multiprocess(4x2) {r2:8.2f}/s",
                  flush=True)
        print(f"\n    single-process median   {statistics.median(sp):8.2f}/s")
        print(f"    multiprocess  median   {statistics.median(mpr):8.2f}/s")
        print(f"    ratio single/multi      {statistics.median(sp)/statistics.median(mpr):6.3f}x")
        Path("results/harness_crosscheck.json").write_text(json.dumps(
            {"single": sp, "multi": mpr, "body_keys": sorted(body.keys())}, indent=1))
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)


if __name__ == "__main__":
    main()
