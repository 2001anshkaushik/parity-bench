#!/usr/bin/env python3
"""LlamaIndex-side steady-state load generator. Mirrors a3_load.py. Prints `RATE <req/s>`."""
import asyncio, sys, time
base, conc, tokens, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
DOC = "The quick brown fox jumps over the lazy dog. " * max(1, tokens // 10)

async def go():
    import aiohttp
    cn = aiohttp.TCPConnector(limit=conc, limit_per_host=conc)
    async with aiohttp.ClientSession(connector=cn,
                                     timeout=aiohttp.ClientTimeout(total=600)) as s:
        async with s.post(f"{base}/process", json={"doc_id": "w", "text": DOC}) as r:
            await r.json()
        ok = 0
        stop = time.time() + secs
        t0 = time.time()

        async def w():
            nonlocal ok
            while time.time() < stop:
                try:
                    async with s.post(f"{base}/process", json={"doc_id": "x", "text": DOC}) as r:
                        await r.json()
                    ok += 1
                except Exception:
                    pass
        await asyncio.gather(*(w() for _ in range(conc)))
        print(f"RATE {ok / (time.time() - t0):.3f}")

asyncio.run(go())
