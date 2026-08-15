#!/usr/bin/env python3
"""Unit tests for metrics_shared — exact expected values, no benchmark needed.

Run:  ../.venv/bin/python working/harness/test_metrics_shared.py
Every case is arithmetic a reviewer can check by hand (Shashi's test_metrics.py discipline).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import metrics_shared as m  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name:44} got={got!r}" + ("" if ok else f"  want={want!r}"))
    if not ok:
        FAILED.append(name)


def rows(*triples):
    """(submit_s, completion_s, ok[, n_chunks]) -> row dicts with epoch-ns timestamps."""
    out = []
    for i, t in enumerate(triples):
        s, c, ok = t[0], t[1], t[2]
        r = {"doc": f"d{i}", "submit_ns": int(s * 1e9), "completion_ns": int(c * 1e9), "ok": ok}
        if len(t) > 3:
            r["n_chunks"] = t[3]
        out.append(r)
    return out


print("percentile — nearest-rank, integer ceil (Shashi metrics.py:84-93)")
v = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
check("p50 of 1..10 -> rank ceil(5)=5 -> 5", m.percentile(v, 50), 5)
check("p95 of 1..10 -> rank ceil(9.5)=10 -> 10", m.percentile(v, 95), 10)
check("p0 -> min", m.percentile(v, 0), 1)
check("p100 -> max", m.percentile(v, 100), 10)
check("p50 of [10,20,30] -> rank ceil(1.5)=2 -> 20", m.percentile([30, 10, 20], 50), 20)
check("p99 of 2 vals -> rank ceil(1.98)=2 -> hi", m.percentile([7, 3], 99), 7)
check("None entries ignored", m.percentile([None, 4, None, 2], 50), 2)
check("empty -> None", m.percentile([], 50), None)
check("p out of range -> None", m.percentile(v, 101), None)

print("scalar guards — unavailable => None, never 0/inf (Shashi metrics.py:6-7)")
check("docs_per_s zero wall -> None", m.docs_per_s(10, 0), None)
check("docs_per_s None docs -> None", m.docs_per_s(None, 5.0), None)
check("docs_per_s 10/4 -> 2.5", m.docs_per_s(10, 4.0), 2.5)
check("chunks_per_s 30/4 -> 7.5", m.chunks_per_s(30, 4.0), 7.5)
check("cpu_s_per_doc 8/4 -> 2", m.cpu_s_per_doc(8.0, 4), 2.0)
check("cpu_s_per_chunk 8/16 -> 0.5", m.cpu_s_per_chunk(8.0, 16), 0.5)
check("effective_cores 12/4 -> 3", m.effective_cores(12.0, 4.0), 3.0)
check("negative wall -> None", m.docs_per_s(10, -1), None)

print("cpu_utilization — >1.0 flagged INVALID, never clamped (Leela m7_resources.py:131-135)")
u = m.cpu_utilization(28.0, 10.0, 14)
check("util 28/(10*14) -> 0.2", u["cpu_utilization"], 0.2)
check("util 0.2 valid", u["cpu_utilization_valid"], True)
u = m.cpu_utilization(200.0, 10.0, 14)
check("util 200/(140) -> 1.4286 NOT clamped", u["cpu_utilization"], 1.4286)
check("util 1.4286 -> valid False", u["cpu_utilization_valid"], False)
check("util 1.4286 -> error present", "cpu_utilization_error" in u, True)
u = m.cpu_utilization(None, 10.0, 14)
check("util None cpu -> None", u["cpu_utilization"], None)

print("perf_window — completion rank, Leela m1_m2_perf.py:8-28")
r5 = rows((0, 1, True, 2), (0, 2, True, 2), (0, 3, True, 2), (0, 4, True, 2), (0, 5, True, 2))
w = m.perf_window(r5, warm_n=2)
check("warm_n=2 window has 3 docs", len(w["window"]), 3)
check("boundary at 2nd completion (2s)", w["boundary_ns"], int(2e9))
check("span = 5-2 = 3s", w["span_s"], 3.0)
w = m.perf_window(r5, warm_n=0)
check("warm_n=0 span = 5-0 = 5s", w["span_s"], 5.0)
check("warm_n >= completions -> error", "error" in m.perf_window(r5, warm_n=5), True)
check("warm_n > completions -> error", "error" in m.perf_window(r5, warm_n=64), True)

print("throughput — docs/s AND chunks/s over the window (Leela m1_m2_perf.py:31-62)")
t = m.throughput(r5, warm_n=2)
check("successful_in_window 3", t["successful_in_window"], 3)
check("chunks 6", t["successful_chunks"], 6)
check("docs_per_s 3/3 -> 1.0", t["docs_per_s"], 1.0)
check("chunks_per_s 6/3 -> 2.0", t["chunks_per_s"], 2.0)
check("window_t0 = boundary", t["window_t0_ns"], int(2e9))
check("window_t1 = last completion", t["window_t1_ns"], int(5e9))
r_fail = rows((0, 1, True, 2), (0, 2, False), (0, 3, True, 2))
t = m.throughput(r_fail, warm_n=0)
check("failed doc excluded from ok count", t["successful_in_window"], 2)
check("failed doc still in window_docs", t["window_docs"], 3)

print("latency — mode labels (Leela m1_m2_perf.py:103-122), nearest-rank percentiles")
lat = m.latency(rows((0, 1, True), (1, 3, True), (2, 5, True)), warm_n=0)
check("n=3", lat["n"], 3)
check("p50 of [1,2,3] -> 2", lat["p50"], 2.0)
check("max 3", lat["max"], 3.0)
check("mean 2", lat["mean"], 2.0)
check("closed-loop label", lat["label"], "true service latency")
lat = m.latency(rows((0, 1, True)), warm_n=0, mode="open-loop-blast")
check("blast label", lat["label"], "batch-position latency — includes queue wait")
check("no ok docs -> error", "error" in m.latency(rows((0, 1, False)), warm_n=0), True)

print("cost_window — anchor at-or-before t0 (Shashi cstats.py:250, Leela m7_resources.py:81)")
series = [(0.0, 0.0, 100.0), (1.0, 2.0, 110.0), (2.0, 4.0, 400.0), (3.0, 6.0, 120.0),
          (4.0, 8.0, 130.0)]
c = m.cost_window(series, 1.0, 3.0)
check("cpu delta anchors at ts=1.0 sample -> 6-2=4", c["cpu_s"], 4.0)
check("peak RSS from INSIDE only -> 400", c["peak_rss_mb"], 400.0)
check("samples inside (1,3] -> 2", c["samples_in_window"], 2)
c = m.cost_window(series, 0.5, 3.5)
check("t0 between samples anchors before -> 6-0=6", c["cpu_s"], 6.0)
check("empty window -> None", m.cost_window(series, 10.0, 11.0), None)
check("inverted window -> None", m.cost_window(series, 3.0, 1.0), None)
check("no series -> None", m.cost_window([], 0.0, 1.0), None)

print("cost sources — pluggable, identical downstream")
ticks = "\n".join([
    json.dumps({"kind": "role_tick", "t": 0.0, "role": "service", "rss": 104857600, "cpu_s": 1.0}),
    json.dumps({"kind": "role_tick", "t": 1.0, "role": "service", "rss": 209715200, "cpu_s": 3.0}),
    json.dumps({"kind": "role_tick", "t": 1.0, "role": "other", "rss": 999, "cpu_s": 99.0}),
    json.dumps({"kind": "system_tick", "t": 1.5}),
])
s = m.series_from_role_ticks(ticks, "service", epoch_anchor_s=1000.0)
check("role_ticks: 2 rows for role", len(s), 2)
check("role_ticks: epoch anchor applied", s[0][0], 1000.0)
check("role_ticks: rss bytes -> MB", s[0][2], 100.0)
check("role_ticks: other role excluded", all(x[1] != 99.0 for x in s), True)
cg = "\n".join([json.dumps({"ts": 5.0, "cpu_total_s": 1.5, "rss_mb_sum": 640.0}),
                json.dumps({"ts": 5.5, "cpu_total_s": 2.5, "rss_mb_sum": 650.0}),
                "not json"])
s = m.series_from_cgroup_jsonl(cg)
check("cgroup: 2 rows parsed, garbage skipped", len(s), 2)
check("cgroup: ts passthrough (already epoch)", s[0][0], 5.0)
check("cgroup: same tuple shape as psutil source", len(s[0]), 3)

print("derive_side — assembly, None-propagation")
d = m.derive_side(r5, series, warm_n=2, available_cpus=14, mode="closed-loop")
check("derive: docs_per_s 1.0", d["docs_per_s"], 1.0)
check("derive: cpu window (2,5] anchored -> 8-4=4", d["cpu_s"], 4.0)
check("derive: effective_cores 4/3", d["effective_cores"], 1.333)
check("derive: latency mode", d["latency"]["mode"], "closed-loop")
d = m.derive_side(r5, None, warm_n=2, available_cpus=14, mode="closed-loop")
check("derive: no sampler -> cpu_s None not 0", d["cpu_s"], None)
check("derive: no sampler -> util None", d["cpu_utilization"], None)
d = m.derive_side(r5, series, warm_n=64, available_cpus=14, mode="closed-loop")
check("derive: warm_n too large -> error dict", "error" in d, True)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("ALL PASS")
