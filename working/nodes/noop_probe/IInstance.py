# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# ARM 2 of the A3 concurrency-serialization ladder. Consumes the text lane and emits a constant.
# It does no useful work on purpose: the difference between this arm and `probe_minimal` (which
# has no Python node at all) is the cost of DISPATCHING INTO A PYTHON NODE, isolated from
# anything the node computes.
from rocketlib import IInstanceBase


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        # Hold the lane and emit once in closing(), matching every other benchmark node so the
        # lane-handling pattern is not itself a variable between arms.
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        self.instance.writeText("ok")

    def close(self):
        self.buf = ""
