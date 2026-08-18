#!/usr/bin/env python3
"""upload_time classification and cpuset parsing — the two paths that broke on the N=1000 probe.

Defect #34: cpu_utilization divided by the DRIVER's taskset affinity (8) instead of the service
container's cpuset (24) — printed 1.58 INVALID for a true 52.8%. Defect #35: sum(upload_time)/
wall assumed durations; upload_time is a completion OFFSET (Leela derives completion_ns = t0 +
upload_time), and the formula printed an impossible engine_side_concurrency of 281.266 against
threads_requested=24.

The first test REPRODUCES the 281 on synthetic offset data and requires the classifier to refuse
duration semantics for it — a control that cannot fail proves nothing.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# exp_batched_blast imports the collector chain, which imports psutil; absent on this laptop.
if "psutil" not in sys.modules:
    stub = types.ModuleType("psutil")
    for n in ("NoSuchProcess", "ZombieProcess", "AccessDenied", "Error", "TimeoutExpired"):
        setattr(stub, n, type(n, (Exception,), {}))
    stub.Process = object
    stub.process_iter = lambda *a, **k: []
    stub.virtual_memory = stub.swap_memory = lambda: None
    sys.modules["psutil"] = stub

spec = importlib.util.spec_from_file_location(
    "ebb", Path(__file__).resolve().parent.parent / "scripts" / "exp_batched_blast.py")
ebb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ebb)
from harness.memory_sources import parse_cpuset  # noqa: E402

_fails: list[str] = []


def check(name, cond, got=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name:58} {got}")
    if not cond:
        _fails.append(name)


def main() -> int:
    print("upload_time semantics")
    # 1. The N=1000 probe shape: completion OFFSETS skewed early across a 350 s wall.
    wall, n, threads = 350.0, 988, 24
    offsets = [wall * ((i + 1) / n) ** 1.4 for i in range(n)]
    naive = sum(offsets) / wall
    check("the defect reproduces: naive sum/wall is impossible", naive > threads,
          f"naive={naive:.1f} > threads={threads}")
    c = ebb.classify_upload_time(offsets, wall, threads)
    check("classifier refuses duration semantics for offsets", c["semantics"] == "offset",
          f"semantics={c['semantics']}")
    check("offset reason names max ~= wall", "max" in c["reason"], c["reason"][:60])

    # 2. Genuine per-file durations in seconds must classify as duration, bounded by the pool.
    durs = [2.0 + (i % 5) * 0.1 for i in range(100)]
    c2 = ebb.classify_upload_time(durs, 10.0, threads)
    check("real durations classify as duration", c2["semantics"] == "duration",
          c2["semantics"])
    conc = sum(x * c2["scale"] for x in durs) / 10.0
    check("derived concurrency respects the pool ceiling", conc <= threads * 1.1,
          f"{conc:.1f} <= {threads}")

    # 3. Millisecond durations: rejected at seconds, accepted at ms, flagged as contradicting
    #    the SDK docstring.
    ms_vals = [500.0 + (i % 7) for i in range(100)]
    c3 = ebb.classify_upload_time(ms_vals, 10.0, threads)
    check("ms-only data classifies at ms", c3["semantics"] == "duration"
          and c3["scale"] == 1e-3, f"{c3['semantics']}@{c3['scale']}")
    check("ms classification is flagged as contradicting the docstring",
          "CONTRADICTS" in c3["reason"] or "CONTRADICTS" in str(c3.get("evidence", "")),
          c3["reason"][:60])

    # 4. Ambiguity refuses to pick. Both hypotheses fit: few values near the wall.
    c4 = ebb.classify_upload_time([9.0, 8.0, 7.0, 6.0, 5.0], 10.0, threads)
    check("ambiguous data refuses classification", c4["semantics"] == "ambiguous",
          c4["semantics"])
    check("empty input is unclassifiable, not a crash",
          ebb.classify_upload_time([], 10.0, threads)["semantics"] == "unclassifiable")

    print("cpuset parsing")
    for spec_, want in (("0-23", 24), ("0-3,8-11", 8), ("0", 1), ("0-23\n", 24),
                        ("", None), ("junk", None), (None, None), ("1,3,5", 3)):
        check(f"parse_cpuset({spec_!r}) == {want}", parse_cpuset(spec_) == want,
              f"got {parse_cpuset(spec_)}")

    print("\n" + ("ALL PASS" if not _fails else f"{len(_fails)} FAILED: {_fails}"))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
