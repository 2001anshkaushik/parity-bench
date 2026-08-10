# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# Deterministic per-item fault injection on the text lane, so RocketRide and the Python
# baselines receive an IDENTICAL work unit and IDENTICAL fault hooks. Without this the
# comparison is not apples-to-apples: you would be injecting faults into the driver for one
# side and into the runtime for the other.
#
# The directive travels IN THE PAYLOAD rather than in config, because faults must vary per item
# within one batch — that is the whole point of a partial-failure test. Wire format:
#
#     FP|<item_id>|<fault>|<filler...>
#
# fault ∈ ok | raise | hang | alloc | malformed
#
#   ok         -> echo a deterministic digest, the correctness reference for goodput
#   raise      -> raise a Python exception inside the node
#   hang       -> sleep past any sane client timeout
#   alloc      -> touch a large allocation (real RSS, not just reserved)
#   malformed  -> hand the engine a value of the wrong type, to exercise its own validation
#                 rather than a Python exception we raised ourselves
#
# The digest for `ok` items is sha256(item_id|filler) so the driver can verify that good items
# produced CORRECT output, not merely that they returned. A framework that stays up but
# silently corrupts survivors must not score as isolating faults well.
import hashlib
import os
import sys
import time

from rocketlib import IInstanceBase

HANG_SECONDS = float(os.environ.get("FP_HANG_SECONDS", "120"))
ALLOC_MB = int(os.environ.get("FP_ALLOC_MB", "512"))
# Held allocations overlap, so this is sized smaller than the fire-and-forget variant:
# a 64-wide pool holding 54 of these must stay well inside 48 GiB.
ALLOC_HOLD_MB = int(os.environ.get("FP_ALLOC_HOLD_MB", "256"))


def digest(item_id: str, filler: str) -> str:
    return hashlib.sha256(f"{item_id}|{filler}".encode()).hexdigest()


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        # Hold the lane; we emit once in closing(), matching the anonymize node's pattern.
        self.preventDefault()

    def closing(self):
        raw = self.buf
        fault = "ok"
        item_id = "?"
        filler = ""
        try:
            if raw.startswith("FP|"):
                parts = raw.split("|", 3)
                item_id, fault = parts[1], parts[2]
                filler = parts[3] if len(parts) > 3 else ""
        except Exception:
            fault = "ok"

        sys.stderr.write(f"FPROBE\tid={item_id}\tfault={fault}\tpid={os.getpid()}\n")
        sys.stderr.flush()

        if fault == "raise":
            raise RuntimeError(f"fault_probe injected exception on item {item_id}")

        if fault == "hang":
            time.sleep(HANG_SECONDS)

        # sleep:<seconds> — a calibrated occupancy hold, used to measure the task's effective
        # concurrency width. With a hold of T seconds and a width of W, steady-state throughput
        # is exactly W/T, so W falls out of a throughput measurement with no guessing.
        if fault.startswith("sleep:"):
            try:
                time.sleep(float(fault.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass
            self.instance.writeText(digest(item_id, filler))
            return

        # alloc_hold:<seconds> — allocate AND HOLD, so concurrent allocations actually overlap.
        # Plain `alloc` frees immediately (~0.3 s), so at most ~3-6 allocations were ever resident
        # at once and "survived 29 GB of churn" was really "survived 3 GB, 54 times in a row".
        # Holding turns it into genuine sustained concurrent pressure bounded by pool width.
        if fault.startswith("alloc_hold:"):
            try:
                hold = float(fault.split(":", 1)[1])
            except (ValueError, IndexError):
                hold = 1.0
            blob = bytearray(ALLOC_HOLD_MB * 1024 * 1024)
            for off in range(0, len(blob), 4096):
                blob[off] = 1
            time.sleep(hold)
            self.instance.writeText(digest(item_id, filler))
            del blob
            return

        if fault == "alloc":
            blob = bytearray(ALLOC_MB * 1024 * 1024)
            for off in range(0, len(blob), 4096):
                blob[off] = 1
            self.instance.writeText(digest(item_id, filler))
            del blob
            return

        if fault == "malformed":
            # Deliberately violate the lane's contract: writeText is typed `str`. Passing an
            # int exercises the ENGINE's validation path rather than an exception we chose to
            # raise, which is a different failure class and worth measuring separately.
            self.instance.writeText(12345)  # type: ignore[arg-type]
            return

        self.instance.writeText(digest(item_id, filler))

    def close(self):
        self.buf = ""
