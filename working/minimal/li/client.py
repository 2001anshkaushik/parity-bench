"""Minimal LlamaIndex client: PDF bytes in, (chunks, vectors) out.

The `client_harness` layer is "the minimum code to send a document and read the result back" —
not our measuring apparatus. `weekend_worker.LlamaHttpArm` additionally carries process-tree RSS
sampling, listening-socket discovery and container-pid resolution; none of that is code a
developer writes to use the service. See ../REMOVED.md.
"""
from __future__ import annotations

import json
import urllib.request


class LlamaClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8801, timeout: float = 1800.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self.n = 0

    def process(self, pdf_bytes: bytes):
        self.n += 1
        req = urllib.request.Request(
            f"{self.base}/process_pdf", data=pdf_bytes,
            headers={"Content-Type": "application/pdf", "X-Doc-Id": f"d{self.n}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode())
        if not out.get("ok"):
            return [], []
        return ([c["text"] for c in out["chunks"]],
                [c["embedding"] for c in out["chunks"]])

    def close(self) -> None:
        pass
