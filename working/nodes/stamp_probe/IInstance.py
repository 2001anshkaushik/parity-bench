# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# A PASS-THROUGH STAGE STAMP for S5-D (the admission funnel). Placed at a stage boundary of the
# docs pipeline, it forwards every event UNCHANGED — the lane methods return without calling
# preventDefault(), so the engine forwards the original event — and records, per document:
#   open_t     when this document's pipeline instance opened at this node (engine-side ADMIT:
#              the pipe slot is already held, so this is inside the admission bound)
#   first_t    when the first event crossed this boundary (the stage upstream began emitting)
#   last_t     when the last event crossed it (the stage upstream finished)
#   closing_t  when the document closed at this node
# The position is DERIVED from what the node sees, so one type serves every boundary with no
# config: text = after parse; documents without embeddings = after the splitter; documents WITH
# embeddings = after the embedding node.
#
# Clocks: time.time() inside the container is the host's CLOCK_REALTIME, the clock the driver's
# time.time_ns() stamps use, so engine stamps and client stamps share one timeline.
import json
import os
import threading
import time

from rocketlib import IInstanceBase

_OUT = os.environ.get("STAMP_PROBE_OUT", "/tmp/stamp_probe.jsonl")
_WRITE_LOCK = threading.Lock()


def _has_embedding(docs) -> bool:
    for d in docs or []:
        e = getattr(d, "embedding", None)
        if e is None and isinstance(d, dict):
            e = d.get("embedding")
        if e is not None and len(e):
            return True
    return False


class IInstance(IInstanceBase):
    def open(self, obj):
        self._doc = (obj.name if getattr(obj, "hasName", False) else None)
        self._open_t = time.time()
        self._first_t = self._last_t = None
        self._n = 0
        self._stage = None

    def _stamp(self, stage):
        now = time.time()
        if self._first_t is None:
            self._first_t, self._stage = now, stage
        self._last_t = now
        self._n += 1

    def writeText(self, text):
        self._stamp("after_parse")            # pass-through: no preventDefault

    def writeDocuments(self, documents):
        self._stamp("after_embed" if _has_embedding(documents) else "after_split")

    def closing(self):
        self._closing_t = time.time()

    def close(self):
        # WRITTEN IN close(), NOT closing() (laptop test, 2026-09-21): the embedding node buffers
        # and flushes its documents from its own close(), after every closing(), so a record
        # written at closing() missed them — stage None, n=0 — while the events were still
        # forwarded (chunk hashes stayed identical). close() is the last call per document.
        rec = {"doc": self._doc, "stage": self._stage, "open_t": self._open_t,
               "first_t": self._first_t, "last_t": self._last_t,
               "closing_t": getattr(self, "_closing_t", None), "close_t": time.time(),
               "n_events": self._n, "pid": os.getpid(), "tid": threading.get_ident(),
               # P0 (2026-09-23): the executing thread's NAME. asyncio's default executor names
               # its workers asyncio_0..asyncio_N-1, so the highest index seen is the pool width
               # that actually ran pipelines (H1), read from the engine rather than inferred.
               "tname": threading.current_thread().name, "native_id": threading.get_native_id()}
        with _WRITE_LOCK:
            with open(_OUT, "a") as f:
                f.write(json.dumps(rec) + "\n")
