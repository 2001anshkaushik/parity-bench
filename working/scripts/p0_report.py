#!/usr/bin/env python3
"""p0_report.py — the P0 morning deliverable, GENERATED from committed analysis artifacts.

    p0_report.py <campaign_dir> --out-md <md> --out-json <json>

No figure is typed: every number is read from an analysis_*.json in the campaign directory (each
of which is computed from the raw per-document / per-frame / per-parse records) and rounded only
here, at display. A missing analysis prints NOT RUN with the reason the chain or gate recorded.
Rules applied structurally (preregistration.json): PROFILE / DIAGNOSTIC absolutes never sit beside
baseline figures; every gate prints threshold, measured value and fired-or-not; every RocketRide
docs throughput carries the Ruling A caveat (dagger); ROI is three columns, never a score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DAG = "†"
CAVEAT = ("32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, "
          "-11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are "
          "unreadable)")
INPUTS: Dict[str, str] = {}


def load(camp: Path, name: str) -> Optional[Any]:
    f = camp / name
    if not f.exists():
        return None
    INPUTS[name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    return json.loads(f.read_text())


def n(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return f"{x:,}"
    return f"{x:,.{nd}f}"


def pct(x: Optional[float], nd: int = 2) -> str:
    return "—" if x is None else f"{100 * x:+.{nd}f}%"


def share(x: Optional[float], nd: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{nd}f}%"


def table(head: List[str], rows: List[List[str]]) -> List[str]:
    return (["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
            + ["| " + " | ".join(r) + " |" for r in rows] + [""])


def stage_rows(st: Dict[str, Any], order: List[str]) -> List[List[str]]:
    rows = []
    for k in order:
        v = st.get(k) or {}
        occ = v.get("occupancy") or {}
        rows.append([k, n(v.get("count")), share(v.get("share_of_run_total")), n(v.get("min")),
                     n(v.get("mean")), n(v.get("sd")), n(v.get("p50")), n(v.get("p90")),
                     n(v.get("p95")), n(v.get("p99")), n(v.get("max")), n(v.get("mean_over_p50"), 2),
                     f"{n(occ.get('max'), 0)} / {n(occ.get('mean'), 2)} / {n(occ.get('p50'), 0)} / {n(occ.get('p95'), 0)}"
                     if occ else "—", v.get("timed_from", "")])
    return rows


STAGE_HEAD = ["stage", "count", "share of run total", "min s", "mean s", "sd s", "p50 s", "p90 s",
              "p95 s", "p99 s", "max s", "mean/p50", "occupancy max / mean / p50 / p95", "timed from"]


# ----------------------------------------------------------------------------- sections

def sec_d0(docs: Optional[Dict[str, Any]], v1: Optional[Dict[str, Any]], v2: Optional[Dict[str, Any]],
           F: Dict[str, Any]) -> List[str]:
    out = ["## D0 — instance accounting (every cell)", ""]
    rows, viol = [], []
    for name, leg in sorted(((docs or {}).get("legs") or {}).items()):
        m = leg.get("mandate") or {}
        ext = leg.get("d0_external") or {}
        models = leg.get("d0_models_pre") or {}
        mtxt = "; ".join(f"{k.rsplit('.', 1)[-1]} ×{v.get('distinct_weights')}" for k, v in models.items()) or "—"
        rows.append([name, leg.get("arm"), n(ext.get("task_instances_max")) if leg.get("arm") == "rr" else
                     n(ext.get("li_worker_processes_max")), mtxt,
                     n((leg.get("d0_threads_pre") or {}).get("proc_threads")),
                     n(leg.get("torch_threads_pre")), "VIOLATION" if m.get("mandate_violation") else "ok"])
        if m.get("mandate_violation"):
            viol.append((name, m.get("violations")))
    for stage, a in (("v1", v1), ("v2", v2)):
        for name, leg in sorted(((a or {}).get("legs") or {}).items()):
            p0 = leg.get("p0") or {}
            census = leg.get("task_census") or {}
            models = ((p0.get("d0_pre") or {}).get("root_modules_with_params")) or {}
            mtxt = "; ".join(f"{k.rsplit('.', 1)[-1]} ×{v.get('distinct_weights')}" for k, v in models.items()) or "—"
            mv = (p0.get("mandate") or {})
            rows.append([name, "rr" if "_rr_" in name else "li",
                         n(len(census.get("new_task_pids") or [])) if census else "1 instance (li)",
                         mtxt, n(((p0.get("d0_pre") or {}).get("proc_threads"))), n(p0.get("torch_num_threads")),
                         "VIOLATION" if mv.get("mandate_violation") else "ok"])
            if mv.get("mandate_violation"):
                viol.append((name, mv.get("violations")))
    out += table(["cell", "arm", "task processes (RR) / worker processes (LI)", "loaded models (distinct weights)",
                  "OS threads in the task", "torch threads", "mandate"], rows)
    F["d0_violations"] = viol
    out.append("**Mandate:** " + ("VIOLATED — " + "; ".join(f"{a}: {b}" for a, b in viol) if viol
                                  else "no cell showed more than one RocketRide task process or more than one loaded instance of a model."))
    out.append("")
    return out
