#!/usr/bin/env python3
"""S5-C analysis: is RocketRide's 32-vCPU cost a hyperthreading effect, and is it RocketRide's?

    batchsize_analyse_smt.py <s5c_campaign_dir> [--out report.json]

Cells (one launch dir each, continuous C=32 on the 384 slice): rr_a1, rr_a2 (unconstrained, the
null-control pair), rr_b (cpuset 0-23), rr_c (one vCPU per physical core, from lscpu), and li_a,
li_b, li_c the same three on LlamaIndex.

  NULL CONTROL  rr_a1 vs rr_a2 must agree within the arm's 0.82% floor on docs/s. If not, no
                between-cell difference means anything and the report says so before anything else.
  DISCRIMINATOR CPU-s per document. Fewer CPUs slow ANY arm; only a sibling effect makes the SAME
                work CHEAPER when siblings are removed. The hypothesis predicts RocketRide's
                CPU-s/doc falls from (a) to (c) beyond the floor, and LlamaIndex's does not.
  MECHANISM     the per-process thread counts snapshotted 30 s into each leg: which process's pool
                (if any) follows the cpuset — the task process (Python default executor, sized from
                os.cpu_count(), which ignores cpusets), the JVM (sizes from availableProcessors(),
                which honours them), or neither (the task pool is a fixed threadCount of 64).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

FLOOR_RR = 0.0082
CELLS = ("rr_a1", "rr_a2", "rr_b", "rr_c", "li_a", "li_b", "li_c")


def cell(d: Path) -> Optional[Dict[str, Any]]:
    legs = sorted(d.glob("leg_*_refc32_*.json"))
    if not legs:
        return None
    g = json.loads(legs[0].read_text())
    c, pc, docs = g["cost"], g.get("percore_host") or {}, g["documents"]
    snap = ((g.get("process_readback") or {}).get("thirty_s_into_window") or {})
    procs = snap.get("processes") or []
    def threads_of(pred):
        return sum(p["threads"] for p in procs if pred(p))
    return {
        "verdict": g.get("verdict"), "declared_cpuset": g.get("cpuset_declared_for_s5c"),
        "docs_per_s": g["throughput"]["docs_per_s"], "span_s": g["throughput"]["span_s"],
        "ok_documents": docs["ok"],
        "engine_cores": c.get("engine_container_cores"), "cpu_s_per_doc": c.get("cpu_s_per_doc"),
        "util_of_cpuset": c.get("cpu_utilization_of_cpuset"), "util_of_32": c.get("cpu_utilization"),
        "cpuset_cpus": c.get("cpuset_cpus"), "host_cores": c.get("host_total_cores"),
        "idle_core_equivalents_of_32": pc.get("idle_core_equivalents"),
        "idle_spin_burned_cores": (c.get("idle_spin_measured") or {}).get("cores"),
        "threads_total": snap.get("total_threads"),
        "threads_task_node_py": threads_of(lambda p: "node.py" in p.get("cmd", "")),
        "threads_java": threads_of(lambda p: "java" in (p.get("name", "") + p.get("cmd", "")).lower()),
        "threads_serving": threads_of(lambda p: "eaas.py" in p.get("cmd", "")),
        "processes_top": [{k: p[k] for k in ("name", "threads", "cpus_allowed")} for p in procs[:5]],
    }


def rel(a, b):
    return round(a / b - 1, 4) if a is not None and b else None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 2
    d = Path(sys.argv[1])
    cells = {n: cell(d / n) for n in CELLS if (d / n).is_dir()}
    missing = [n for n in CELLS if not cells.get(n)]
    rep: Dict[str, Any] = {"campaign_dir": str(d), "cells": cells, "missing_cells": missing,
                           "lscpu_cells": json.loads((d / "cells.json").read_text()) if (d / "cells.json").exists() else None}
    a1, a2 = cells.get("rr_a1"), cells.get("rr_a2")
    if not (a1 and a2):
        rep["verdict"] = "NOT RUN — the null-control pair is incomplete"
        print(json.dumps(rep, indent=1)); return 3
    spread = abs(a1["docs_per_s"] - a2["docs_per_s"]) / ((a1["docs_per_s"] + a2["docs_per_s"]) / 2)
    rep["null_control"] = {"rr_a1": a1["docs_per_s"], "rr_a2": a2["docs_per_s"], "spread": round(spread, 4),
                           "floor": FLOOR_RR, "PASS": spread <= FLOOR_RR}
    if spread > FLOOR_RR:
        rep["verdict"] = ("NULL CONTROL FAILED — two runs of the same unconstrained cell differ by more than "
                          "the floor; no between-cell difference below that spread is interpretable")
    a_cpd = (a1["cpu_s_per_doc"] + a2["cpu_s_per_doc"]) / 2
    a_dps = (a1["docs_per_s"] + a2["docs_per_s"]) / 2
    tol = max(FLOOR_RR, spread)
    def compare(arm, base_cpd, base_dps, b, c):
        out = {}
        for name, x in (("b_0-23", b), ("c_one_per_core", c)):
            if x:
                out[name] = {"cpu_s_per_doc_vs_a": rel(x["cpu_s_per_doc"], base_cpd),
                             "docs_per_s_vs_a": rel(x["docs_per_s"], base_dps),
                             "engine_cores": x["engine_cores"], "cpuset_cpus": x["cpuset_cpus"]}
        return out
    rep["rocketride"] = compare("rr", a_cpd, a_dps, cells.get("rr_b"), cells.get("rr_c"))
    la = cells.get("li_a")
    rep["llamaindex"] = compare("li", la["cpu_s_per_doc"], la["docs_per_s"], cells.get("li_b"), cells.get("li_c")) if la else {}
    rr_c = rep["rocketride"].get("c_one_per_core", {}).get("cpu_s_per_doc_vs_a")
    li_c = rep["llamaindex"].get("c_one_per_core", {}).get("cpu_s_per_doc_vs_a")
    rep["hypothesis_test"] = {
        "tolerance_used": round(tol, 4),
        "rr_cheaper_without_siblings": (rr_c is not None and rr_c < -tol),
        "li_cheaper_without_siblings": (li_c is not None and li_c < -tol),
        "reading": (None if rr_c is None or li_c is None else
                    "SUPPORTED — RocketRide's work gets cheaper without hyperthread siblings and LlamaIndex's does not"
                    if rr_c < -tol and not li_c < -tol else
                    "BOX PROPERTY — both arms get cheaper without siblings; not RocketRide-specific"
                    if rr_c < -tol and li_c < -tol else
                    "NOT SUPPORTED — RocketRide's CPU-s/doc does not fall beyond the tolerance without siblings")}
    rep["pool_readback"] = {n: {k: c[k] for k in ("declared_cpuset", "threads_total", "threads_task_node_py",
                                                   "threads_java", "threads_serving")}
                            for n, c in cells.items() if c}
    rep.setdefault("verdict", rep["hypothesis_test"]["reading"])
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only"); return 3
        p.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
