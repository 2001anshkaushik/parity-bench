#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
STEP 3 — where does the ~2,600 items/s ceiling come from?

Model B saturated at ~2,600/s and stayed there from n=100 to n=20,000. Before that number is
published as "RocketRide's throughput", it has to be attributed. Four candidate causes, each
varied INDEPENDENTLY so the answer is evidence rather than a hypothesis:

  1. client driver        -> vary DRIVER PROCESSES (1, 2, 4). If throughput scales with driver
                             processes, the ceiling was our own single Python client's GIL and
                             every number so far UNDERSTATES RocketRide.
  2. WebSocket multiplex  -> vary CLIENT CONNECTIONS within one driver (1, 2, 4, 8). If it scales
                             with connections but not beyond, the single multiplexed socket is
                             the bottleneck, not the engine.
  3. transport/serialize  -> vary PAYLOAD SIZE (64 B .. 64 KB). If items/s is flat while MB/s
                             rises, we are latency/round-trip bound, not bandwidth bound.
  4. engine scheduler     -> vary PIPELINE NODE COUNT (1, 2, 4 pass-through nodes). If per-item
                             cost rises linearly with node count, per-node scheduling dominates.

Only if throughput stays pinned at ~2,600/s across 1-3 is the engine itself the ceiling.
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo  # noqa: E402

OUT = ROOT / "results" / "ceiling"
N_ITEMS = 3000
CONCURRENCY = 500


def make_passthrough_pipe(n_nodes: int, tag: str) -> str:
    """Pipeline with n_nodes fault_probe nodes chained (each a pass-through for 'ok' items)."""
    comps = [{"id": "input", "provider": "webhook", "config": {}, "ui": {}}]
    prev = "input"
    for i in range(n_nodes):
        nid = f"n{i}"
        comps.append({"id": nid, "provider": "fault_probe", "config": {}, "ui": {},
                      "input": [{"lane": "text", "from": prev}]})
        prev = nid
    comps.append({"id": "output", "provider": "response_text", "config": {}, "ui": {},
                  "input": [{"lane": "text", "from": prev}]})
    spec = {"components": comps, "source": "input",
            "project_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ceiling-{tag}-{n_nodes}")),
            "viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1}
    p = ROOT / "pipes" / "generated" / f"ceiling_{tag}_{n_nodes}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec, indent=1))
    return str(p.relative_to(ROOT))


async def run_one_client(pipe: str, n: int, conc: int, payload_bytes: int,
                         n_conns: int) -> dict:
    """n_conns separate RocketRideClient connections inside ONE driver process."""
    from rocketride import RocketRideClient

    filler = "y" * max(0, payload_bytes - 16)
    # One live task per project_id: N connections each need their OWN pipeline file, or the
    # 2nd..Nth use() returns "Pipeline is already running." (found the hard way).
    import json as _json, uuid as _uuid
    base = _json.loads((ROOT / pipe).read_text())
    clients, tokens = [], []
    for k in range(n_conns):
        spec = dict(base)
        spec["project_id"] = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"{pipe}-conn{k}"))
        pk = ROOT / "pipes" / "generated" / f"conn_{Path(pipe).stem}_{k}.pipe"
        pk.parent.mkdir(parents=True, exist_ok=True)
        pk.write_text(_json.dumps(spec, indent=1))
        c = RocketRideClient()
        await c.connect(timeout=30000)
        r = await c.use(filepath=str(pk.relative_to(ROOT)))
        clients.append(c)
        tokens.append(r["token"])
    # warm each connection
    await asyncio.gather(*(c.send(t, f"FP|w|ok|{filler}", mimetype="text/plain")
                           for c, t in zip(clients, tokens)), return_exceptions=True)

    sem = asyncio.Semaphore(conc)
    ok = 0
    errs = 0

    async def one(i: int):
        nonlocal ok, errs
        c = clients[i % n_conns]
        t = tokens[i % n_conns]
        async with sem:
            try:
                await asyncio.wait_for(
                    c.send(t, f"FP|{i}|ok|{filler}", mimetype="text/plain"), timeout=60)
                ok += 1
            except Exception:
                errs += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
    wall = time.perf_counter() - t0

    for c, t in zip(clients, tokens):
        try:
            await asyncio.wait_for(c.terminate(t), timeout=30)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass

    mb = (n * payload_bytes) / 2**20
    return {"ok": ok, "errors": errs, "wall_s": round(wall, 3),
            "throughput_per_s": round(ok / wall, 1) if wall else None,
            "mb_per_s": round(mb / wall, 3) if wall else None}


def _driver_worker(args):
    pipe, n, conc, payload_bytes, n_conns = args
    return asyncio.run(run_one_client(pipe, n, conc, payload_bytes, n_conns))


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    findings: dict = {}
    eo.preflight("ceiling")

    pipe1 = make_passthrough_pipe(1, "base")

    # --- 2. client connections within one driver ------------------------
    print("\n[2] client CONNECTIONS (one driver process)")
    conn_rows = []
    for nc in (1, 2, 4, 8):
        eo.preflight(f"conns{nc}")
        r = await run_one_client(pipe1, N_ITEMS, CONCURRENCY, 128, nc)
        r["connections"] = nc
        conn_rows.append(r)
        print(f"  conns={nc}  {r['throughput_per_s']}/s  errs={r['errors']}  {r['wall_s']}s",
              flush=True)
        eo.postflight(f"conns{nc}")
    findings["connections"] = conn_rows

    # --- 1. driver processes --------------------------------------------
    print("\n[1] DRIVER PROCESSES (independent OS processes, 1 conn each)")
    proc_rows = []
    for nprocs in (1, 2, 4):
        eo.preflight(f"drivers{nprocs}")
        per = N_ITEMS // nprocs
        ctx = mp.get_context("spawn")
        t0 = time.perf_counter()
        with ctx.Pool(nprocs) as pool:
            res = pool.map(_driver_worker,
                           [(pipe1, per, CONCURRENCY // nprocs, 128, 1)] * nprocs)
        wall = time.perf_counter() - t0
        total_ok = sum(r["ok"] for r in res)
        row = {"driver_processes": nprocs, "total_ok": total_ok,
               "wall_s": round(wall, 3),
               "aggregate_throughput_per_s": round(total_ok / wall, 1) if wall else None,
               "per_driver": [r["throughput_per_s"] for r in res]}
        proc_rows.append(row)
        print(f"  drivers={nprocs}  aggregate={row['aggregate_throughput_per_s']}/s  "
              f"per_driver={row['per_driver']}", flush=True)
        eo.postflight(f"drivers{nprocs}")
    findings["driver_processes"] = proc_rows

    # --- 3. payload size -------------------------------------------------
    print("\n[3] PAYLOAD SIZE (1 driver, 1 conn)")
    pay_rows = []
    for size in (64, 1024, 8192, 65536):
        eo.preflight(f"payload{size}")
        r = await run_one_client(pipe1, 1500, CONCURRENCY, size, 1)
        r["payload_bytes"] = size
        pay_rows.append(r)
        print(f"  payload={size:6d}B  {r['throughput_per_s']}/s  {r['mb_per_s']} MB/s",
              flush=True)
        eo.postflight(f"payload{size}")
    findings["payload_size"] = pay_rows

    # --- 4. pipeline node count -------------------------------------------
    print("\n[4] PIPELINE NODE COUNT")
    node_rows = []
    for nn in (1, 2, 4):
        eo.preflight(f"nodes{nn}")
        p = make_passthrough_pipe(nn, "chain")
        r = await run_one_client(p, 1500, CONCURRENCY, 128, 1)
        r["nodes"] = nn
        r["per_item_ms"] = round(1000.0 / r["throughput_per_s"], 4) if r["throughput_per_s"] else None
        node_rows.append(r)
        print(f"  nodes={nn}  {r['throughput_per_s']}/s  per_item={r['per_item_ms']}ms",
              flush=True)
        eo.postflight(f"nodes{nn}")
    findings["node_count"] = node_rows

    (OUT / "ceiling.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nwritten -> {OUT/'ceiling.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
