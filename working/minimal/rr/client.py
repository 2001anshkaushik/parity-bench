"""Minimal RocketRide client: PDF bytes in, (chunks, vectors) out.

The same layer as ../li/client.py — the minimum code to send a document and read the result back.
`weekend_worker.RocketArm` additionally carries listening-socket engine discovery, container-pid
resolution and process-tree RSS; none of that is code a developer writes to use the engine. See
../REMOVED.md.

The unique project_id is NOT scaffolding and stays: the engine allows one live task per
project_id, so a fixed id makes two concurrent pipelines collide.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent


class RocketClient:
    def __init__(self, pipe: Path = HERE / "pipeline.pipe", timeout: float = 1800.0):
        from rocketride import RocketRideClient

        self.timeout = timeout
        self.loop = asyncio.new_event_loop()
        cfg = json.loads(pipe.read_text())
        cfg["project_id"] = str(uuid.uuid5(
            uuid.NAMESPACE_DNS, f"min-{os.getpid()}-{time.time()}"))
        self.path = pipe.parent / f"generated_{os.getpid()}.pipe"
        self.path.write_text(json.dumps(cfg))
        self.c = RocketRideClient()
        self.loop.run_until_complete(self.c.connect(timeout=60000))
        self.tok = self.loop.run_until_complete(
            self.c.use(filepath=str(self.path)))["token"]

    def process(self, pdf_bytes: bytes):
        out = self.loop.run_until_complete(asyncio.wait_for(
            self.c.send(self.tok, pdf_bytes, mimetype="application/pdf"),
            timeout=self.timeout))
        docs = out.get("documents") or []
        return ([d.get("page_content", "") for d in docs],
                [d.get("embedding") or [] for d in docs])

    def close(self) -> None:
        try:
            self.loop.run_until_complete(asyncio.wait_for(self.c.terminate(self.tok), timeout=60))
            self.loop.run_until_complete(self.c.disconnect())
        except Exception:
            pass
