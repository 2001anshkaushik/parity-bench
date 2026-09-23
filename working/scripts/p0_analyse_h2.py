#!/usr/bin/env python3
"""P0 H2 analysis — the interpreter lock, from the raw tracer, sampler and profiler files.

    p0_analyse_h2.py <campaign_dir> [--out analysis_h2.json]

Per H2 leg directory (tool_gil, h2_null_c1, h2_c32_a, h2_c32_b, h2_full_c32 when run):
  giltrace_<leg>.json      bpftrace -f json maps: per-thread wait_ns / hold_ns / takes, tracer
                           start/end (amendment 1)
  threadstate_<leg>.jsonl  5 Hz /proc samples: [tid, comm, state, cumulative ticks] per thread
  pyspy_gil_<leg>.txt      py-spy raw, GIL holder only: "thread (tid): name;frame;...;frame count"
Definitions (preregistration.json H2 + preregistration_amendment_1.json):
  python threads = threads that entered take_gil; T = tracer window; denominator n_py x T
  waiting = sum(wait) / (n_py x T); holding = sum(hold) / (n_py x T); occupancy = sum(hold) / T
  native = share of Python-thread /proc samples in state R, minus holding (floored at 0)
  idle = 1 - waiting - holding - native
  gate: mean waiting of h2_c32_a and h2_c32_b >= 15%; null control: h2_null_c1 waiting < 2%.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

GATE = 0.15
NULL_MAX = 0.02
STAGE_OF = (("embedding_transformer", "embed"), ("sentence_transformers", "embed"),
            ("transformers/", "embed"), ("torch/", "embed"), ("tokenizers", "embed"),
            ("preprocessor_langchain", "split"), ("langchain", "split"),
            ("nodes/response", "response"), ("stamp_probe", "stamp_probe"),
            ("env_probe", "env_probe"), ("data_conn", "engine glue (data_conn)"))


def bpf_maps(p: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") in ("map", "hist") and isinstance(j.get("data"), dict):
            out.update(j["data"])
    return out


def as_int_map(m: Any) -> Dict[str, int]:
    return {str(k): int(v) for k, v in (m or {}).items()} if isinstance(m, dict) else {}


def gil_shares(d: Path, leg: str) -> Dict[str, Any]:
    m = bpf_maps(d / f"giltrace_{leg}.json")
    if not m:
        return {"status": "NO TRACE", "file": f"giltrace_{leg}.json"}
    wait, hold, takes = as_int_map(m.get("@wait_ns")), as_int_map(m.get("@hold_ns")), as_int_map(m.get("@takes"))
    t_start, t_end = m.get("@start_ns"), m.get("@end_ns")
    if not (isinstance(t_start, int) and isinstance(t_end, int)) or t_end <= t_start:
        return {"status": "NO WINDOW", "maps": sorted(m)}
    T = (t_end - t_start) / 1e9
    py = sorted(takes)
    n = len(py)
    tw, th = sum(wait.values()) / 1e9, sum(hold.values()) / 1e9
    # /proc states for the Python threads
    r_share = None
    ts = d / f"threadstate_{leg}.jsonl"
    if ts.exists() and n:
        pys = set(int(t) for t in py)
        tot = run = 0
        for line in ts.read_text().splitlines():
            if not line.strip():
                continue
            for tid, comm, state, ticks in json.loads(line)["th"]:
                if tid in pys:
                    tot += 1
                    run += state == "R"
        r_share = run / tot if tot else None
    waiting = tw / (n * T) if n else None
    holding = th / (n * T) if n else None
    native = max(0.0, r_share - holding) if (r_share is not None and holding is not None) else None
    idle = (1 - waiting - holding - native) if native is not None else None
    per_s_w = {int(k): v / 1e9 for k, v in as_int_map(m.get("@wait_by_s")).items()}
    return {"status": "OK", "tracer_window_s": T, "python_threads": n,
            "gil_takes": sum(takes.values()), "wait_s_total": tw, "hold_s_total": th,
            "waiting_on_gil": waiting, "holding_gil": holding, "native": native, "idle": idle,
            "python_thread_R_state_share": r_share,
            "gil_occupancy": th / T, "occupancy_le_1": th / T <= 1.0,
            "wait_s_per_second_max": max(per_s_w.values()) if per_s_w else None,
            "top_waiting_threads_s": sorted(((k, v / 1e9) for k, v in wait.items()),
                                            key=lambda x: -x[1])[:5]}


LINE = re.compile(r"^(?P<stack>.*) (?P<n>\d+)$")


def pyspy_gil(d: Path, leg: str, rate: float, window_s: Optional[float]) -> Dict[str, Any]:
    f = d / f"pyspy_gil_{leg}.txt"
    if not f.exists() or not f.stat().st_size:
        return {"status": "NO FILE"}
    fn, stage, total = Counter(), Counter(), 0
    for line in f.read_text().splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        n = int(m.group("n"))
        frames = m.group("stack").split(";")
        inner = frames[-1]
        key = re.sub(r":\d+\)$", ")", inner)            # function + file, line number dropped
        fn[key] += n
        total += n
        joined = ";".join(frames)
        st = next((s for pat, s in STAGE_OF if pat in joined), "other")
        stage[st] += n
    return {"status": "OK", "samples": total,
            "occupancy_from_ticks": (total / (rate * window_s)) if window_s else None,
            "top10": [{"function": k, "samples": v, "share": v / total} for k, v in fn.most_common(10)],
            "by_stage": {k: {"samples": v, "share": v / total} for k, v in stage.most_common()},
            "stage_rule": "a sample is attributed to the first node/library pattern found in its "
                          "stack: " + ", ".join(f"{p}->{s}" for p, s in STAGE_OF)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out", default="analysis_h2.json")
    a = ap.parse_args()
    res: Dict[str, Any] = {"legs": {}}
    for name in ("tool_gil", "h2_null_c1", "h2_c32_a", "h2_c32_b", "h2_full_c32"):
        d = a.campaign / name
        lj = sorted(d.glob("leg_*.json")) if d.is_dir() else []
        if not lj:
            res["legs"][name] = {"status": "NOT RUN"}
            continue
        leg = json.loads(lj[0].read_text())
        tag = f"{leg['arm']}_{leg['leg']}"
        py = (leg.get("p0") or {}).get("pyspy") or {}
        win = leg.get("window") or {}
        wsec = (win["t1_ns"] - win["t0_ns"]) / 1e9 if win else None
        res["legs"][name] = {
            "leg": leg["leg"], "boot_id": ((leg.get("p0") or {}).get("session") or {}).get("boot_id"),
            "mandate": ((leg.get("p0") or {}).get("mandate") or {}).get("mandate_violation"),
            "docs_per_s_DIAGNOSTIC": (leg.get("throughput") or {}).get("docs_per_s"),
            "engine_cores": (leg.get("cost") or {}).get("engine_container_cores"),
            "host_busy_cores": (leg.get("percore_host") or {}).get("mean_busy_cores"),
            "recorders": {k: {"rc": v.get("rc"), "bytes": v.get("bytes"), "log_tail": v.get("log_tail")}
                          for k, v in py.items() if isinstance(v, dict) and "rc" in v},
            "gil": gil_shares(d, tag),
            "pyspy_gil": pyspy_gil(d, tag, 100.0, wsec),
            "recorder_n_native": ("NOT RUN — py-spy --native aborts on the engine binary "
                                  "(UNW_EBADREG), tooling leg 08:36Z; amendment 1")}
    null = res["legs"].get("h2_null_c1", {}).get("gil", {})
    smoke = [res["legs"].get(n, {}).get("gil", {}) for n in ("h2_c32_a", "h2_c32_b")]
    null_ok = null.get("status") == "OK" and null.get("waiting_on_gil") is not None \
        and null["waiting_on_gil"] < NULL_MAX
    vals = [s["waiting_on_gil"] for s in smoke if s.get("status") == "OK" and s.get("waiting_on_gil") is not None]
    mean_w = sum(vals) / len(vals) if len(vals) == 2 else None
    res["null_control"] = {"leg": "h2_null_c1", "waiting_on_gil": null.get("waiting_on_gil"),
                           "threshold": NULL_MAX, "pass": null_ok}
    res["gate"] = {"threshold": GATE, "metric": "mean waiting_on_gil of h2_c32_a and h2_c32_b",
                   "measured": mean_w, "values": vals,
                   "fired": (mean_w is not None and null_ok and mean_w >= GATE),
                   "evaluable": mean_w is not None and null_ok,
                   "note": ("UNREADABLE: the null control failed or is missing, so no gate decision"
                            if not null_ok else None),
                   "amendment": "instrument per preregistration_amendment_1.json (bpftrace on "
                                "take_gil/drop_gil); recorder N NOT RUN (UNW_EBADREG)"}
    out = a.campaign / a.out
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"wrote {out}")
    print(json.dumps({"null": res["null_control"], "gate": res["gate"]}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
