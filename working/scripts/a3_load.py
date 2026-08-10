#!/usr/bin/env python3
"""Steady-state load generator for a3_threads.py. Prints `RATE <req/s>` on stdout.

Deliberately a separate process: sampling engine CPU from inside the driver would put the
sampler on the same interpreter as the load, and an in-process collector has already biased
this project's results by 100x once.
"""
import asyncio, json, sys, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pipe_rel, conc, tag, seconds = sys.argv[1], int(sys.argv[2]), sys.argv[3], float(sys.argv[4])
# Token count is an OPTIONAL 5th arg. It was previously hardcoded to ~400 tokens, which silently
# made every "token level" in memory_ceiling.py identical on the RocketRide side.
TOKENS = int(sys.argv[5]) if len(sys.argv) > 5 else 400
DOC = "The quick brown fox jumps over the lazy dog. " * max(1, TOKENS // 10)


async def go():
    from rocketride import RocketRideClient
    base = json.loads((ROOT / pipe_rel).read_text())
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"a3load-{tag}"))
    p = ROOT / "pipes" / "generated" / f"a3load_{tag}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base))
    c = RocketRideClient()
    await c.connect(timeout=30000)
    r = await c.use(filepath=str(p.relative_to(ROOT)))
    tok = r["token"]
    await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
    ok = 0
    stop = time.time() + seconds
    t0 = time.time()

    async def w():
        nonlocal ok
        while time.time() < stop:
            try:
                await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
                ok += 1
            except Exception:
                pass
    await asyncio.gather(*(w() for _ in range(conc)))
    el = time.time() - t0
    print(f"RATE {ok / el:.3f}")
    try:
        await asyncio.wait_for(c.terminate(tok), timeout=120)
    except Exception:
        pass
    await c.disconnect()

asyncio.run(go())
