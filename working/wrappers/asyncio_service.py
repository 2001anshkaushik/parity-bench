"""Tier 2 reference wrapper: the asyncio baseline behind FastAPI + uvicorn.

Why this exists
---------------
Every RocketRide number collected so far includes a WebSocket round trip to a separate process.
Every in-process Python number does not. Comparing them directly understates RocketRide by
whatever the transport costs, and no reviewer would accept it. Tier 2 puts each Python framework
behind the same shape of boundary — HTTP/socket, separate process, real serialization — so the
comparison is like-for-like.

Tuning follows uvicorn's own deployment guidance rather than defaults, because a hobbled FastAPI
baseline is exactly the strawman this suite exists to avoid:
  * `--workers N` — uvicorn runs single-process by default; production deployments run one worker
    per core. Set explicitly by the launcher.
  * `--loop uvloop` — uvloop is uvicorn's recommended loop and materially faster than asyncio's.
  * `--http httptools` — the C HTTP parser, recommended over the pure-Python `h11` fallback.
  * `--no-access-log` — per-request logging is a well-known throughput tax and is off in
    production deployments.
  * `--limit-concurrency` left unset so backpressure behaviour is the server's own, not a cap we
    imposed for the benchmark.

The work unit is byte-identical to the RocketRide `fault_probe` node and to
`fault_isolation_probe.execute_fault`, so results are directly comparable.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time

from fastapi import FastAPI, Response
from pydantic import BaseModel

FILLER_DIGEST_SALT = ""
HANG_SECONDS = float(os.environ.get("FP_HANG_SECONDS", "25"))
ALLOC_MB = int(os.environ.get("FP_ALLOC_MB", "512"))

app = FastAPI(title="benchmark-A asyncio tier2 wrapper")


class Item(BaseModel):
    item_id: str
    fault: str = "ok"
    filler: str = ""


def digest(item_id: str, filler: str) -> str:
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


def _work(item_id: str, fault: str, filler: str) -> str:
    if fault == "raise":
        raise RuntimeError(f"injected exception on item {item_id}")
    if fault == "alloc":
        blob = bytearray(ALLOC_MB * 1024 * 1024)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        del blob
    if fault == "malformed":
        return 12345 + ""  # type: ignore[operator]
    return digest(item_id, filler)


@app.get("/health")
async def health():
    return {"status": "ok", "pid": os.getpid()}


@app.post("/process")
async def process(item: Item, response: Response):
    """One work unit. Faults are returned as per-item errors, never 500s that kill the worker.

    Returning 200-with-error mirrors how RocketRide reports a node exception (a per-item `error`
    key on an otherwise successful response). Making one side raise a transport-level error and
    the other return a payload error would measure the error convention, not fault isolation.
    """
    if item.fault == "hang":
        await asyncio.sleep(HANG_SECONDS)
    try:
        # CPU-ish work goes to a thread so one bad item cannot stall the event loop for
        # everyone — the async-correct shape, and what the framework's docs would have you do.
        value = await asyncio.to_thread(_work, item.item_id, item.fault, item.filler)
        return {"item_id": item.item_id, "ok": True, "value": value}
    except Exception as e:  # noqa: BLE001 - deliberate: per-item containment
        return {"item_id": item.item_id, "ok": False,
                "error": f"{type(e).__name__}: {e}"[:200]}
