#!/usr/bin/env python3
"""Ask the task process what its thread configuration actually is."""
import asyncio, json, sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

async def go():
    from rocketride import RocketRideClient
    base = json.loads((ROOT / "working" / "pipes" / "a3_env.pipe").read_text())
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"envq-{sys.argv[1]}"))
    p = ROOT / "working" / "pipes" / "generated" / f"envq_{sys.argv[1]}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(base))
    c = RocketRideClient(); await c.connect(timeout=30000)
    r = await c.use(filepath=str(p.relative_to(ROOT))); tok = r["token"]
    out = await asyncio.wait_for(c.send(tok, "probe", mimetype="text/plain"), timeout=300)
    txt = "".join(out.get("text", []))
    print(json.dumps(json.loads(txt.strip()), indent=1))
    try: await asyncio.wait_for(c.terminate(tok), timeout=60)
    except Exception: pass
    await c.disconnect()
asyncio.run(go())
