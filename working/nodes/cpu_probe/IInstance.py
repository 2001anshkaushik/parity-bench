# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# ARM 3 of the A3 concurrency-serialization ladder. Burns a fixed amount of PURE-PYTHON CPU with
# no model, no torch, and no native library that could release the GIL on its own schedule.
#
# Why pure Python specifically: sentence-transformers runs its matmuls in native code, which may
# release the GIL. If the embedding arm is flat but this arm scales, the serialization is not
# generic Python-in-a-node; if BOTH are flat, the node execution model serializes regardless of
# what the node computes. That is the distinction this arm exists to draw, so it must not
# accidentally call into a library that behaves like the model does.
#
# CPU_PROBE_ITERS is calibrated so one call costs roughly what one 400-token embed costs
# (~15 ms), keeping the per-request work comparable across arms.
import os

from rocketlib import IInstanceBase

ITERS = int(os.environ.get("CPU_PROBE_ITERS", "120000"))


def burn(n: int) -> int:
    # Integer arithmetic in a tight loop: stays in the interpreter, holds the GIL, allocates
    # almost nothing, and cannot be optimized away because the result is emitted.
    acc = 0
    for i in range(n):
        acc = (acc * 31 + i) & 0xFFFFFFFF
    return acc


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        self.instance.writeText(str(burn(ITERS)))

    def close(self):
        self.buf = ""
