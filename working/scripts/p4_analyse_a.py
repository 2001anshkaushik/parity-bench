#!/usr/bin/env python3
"""P4-A video concurrency analysis (preregistration.json P4_A_video_concurrency), from raw leg files only.

    p4_analyse_a.py <campaign_dir>  -> analysis_p4a.json

Per leg: frames/s (export total_frames / total_span_s), measured frames (the LAST measured record per video without error),
the forward pass per frame over the measured stamp rows (the last N frame rows of p1_stamps.jsonl by t_wall) with the full
D1 metric set, every stamped component's D1 set, lock duty (P0 V2's duty cycle on the P1 stamp file), cores busy during
the forward, caller on-CPU share, CPU-s/frame, caller switch rate (consecutive forwards by fw0_mono run by a different
tid), session facts, the sampled memory peak, the gate records. Per cell: mean and replicate spread. Then correctness
(before speed) and the pre-registered readings R1, R2/R3.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import identity, load, metric_set, spread  # noqa: E402
from p1_analyse_e2 import forward_block, measured_frames  # noqa: E402

FLOOR = 0.0082
CELLS = {"rr_k1": ("p4a_rr1_1", "p4a_rr1_2"), "rr_k16": ("p4a_rr16_1", "p4a_rr16_2"),
         "li_k1": ("p4a_li1_1", "p4a_li1_2"), "li_k16": ("p4a_li16_1", "p4a_li16_2"),
         "rr_k16_active": ("p4a_act_1", "p4a_act_2")}
ARM = {"rr_k1": "rr", "rr_k16": "rr", "rr_k16_active": "rr", "li_k1": "li", "li_k16": "li"}


def rows(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def gated_legs(camp: Path) -> Dict[str, str]:
    """The pre-registered leg name -> the attempt the chain gated (chain_p4a_run_done.json's legs list: '<dir>:rc=0' or
    '<dir>:DEGRADED_all_rows'); only attempts that returned a result."""
    f = camp / "chain_p4a_run_done.json"
    out: Dict[str, str] = {}
    if not f.exists():
        return out
    for x in json.loads(f.read_text()).get("legs", []):
        d, _, st = x.partition(":")
        if st in ("rc=0", "DEGRADED_all_rows") and d.startswith("p4a_"):
            base = d[:-3] if d[-3:] in ("_r1", "_r2") else d
            out.setdefault(base, d)
    return out


def components(fr: List[Dict[str, Any]], arm: str, st_all: List[Dict[str, Any]]) -> Dict[str, Any]:
    """P0 V2's v2_components on the P1 stamp rows (the same definitions; measured frames passed in)."""
    if not fr:
        return {"status": "NO STAMPS"}
    t_first = fr[0]["t_wall"]
    if arm == "rr":
        comps = ("decode", "lock_wait", "resize", "preprocess", "predict_pre", "forward", "predict_post", "dict_build",
                 "loader_post", "rescale", "inside_other", "lock_held", "emit")
        per = [sum(x or 0 for x in (r.get("decode"), r.get("lock_wait"), r.get("lock_held"), r.get("emit"))) for r in fr]
        run_total = sum(per)
        t0 = min(r["t_wall"] for r in fr)
        t1 = max(r["t_wall"] + tot for r, tot in zip(fr, per))
        held = sum(r.get("lock_held") or 0 for r in fr)
        return {"frames": len(fr), "run_total_s": run_total, "window_s": t1 - t0,
                "lock_duty": held / (t1 - t0) if t1 > t0 else None,
                "components": {c: metric_set([r.get(c) for r in fr], run_total) for c in comps}}
    vids = [r for r in st_all if r.get("kind") == "video" and r["t_wall_release"] >= t_first]
    comps = ("load_decode", "predict_pre", "forward", "predict_post", "dict_build", "format", "lock_held")
    run_total = sum(r.get("lock_held") or 0 for r in fr) + sum(r.get("lock_wait") or 0 for r in vids)
    t0 = min(r["t_wall"] for r in fr)
    t1 = max(r["t_wall_release"] for r in vids) if vids else None
    held = sum(r.get("lock_held") or 0 for r in vids)
    return {"frames": len(fr), "videos_in_window": len(vids), "run_total_s": run_total,
            "window_s": (t1 - t0) if t1 else None, "lock_duty": (held / (t1 - t0)) if (t1 and t1 > t0) else None,
            "components": {c: metric_set([r.get(c) for r in fr], run_total) for c in comps},
            "per_video": {"lock_wait": metric_set([r.get("lock_wait") for r in vids]),
                          "lock_held": metric_set([r.get("lock_held") for r in vids])},
            "lock_scope_note": "the LlamaIndex lock is taken once per VIDEO around the whole frame loop"}


def switch_rate(fr: List[Dict[str, Any]]) -> Dict[str, Any]:
    s = sorted((r for r in fr if r.get("fw0_mono") is not None and r.get("tid") is not None), key=lambda r: r["fw0_mono"])
    n = len(s)
    sw = sum(1 for a, b in zip(s, s[1:]) if a["tid"] != b["tid"])
    return {"frames_ordered": n, "switches": sw, "rate": sw / (n - 1) if n > 1 else None,
            "caller_threads": len({r["tid"] for r in s})}


def mem_peak(d: Path) -> Optional[int]:
    v = [r.get("total") for r in rows(d / "memstat.jsonl") if r.get("total") is not None]
    return max(v) if v else None


def gate_rec(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    f = camp / "gates" / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


def leg(camp: Path, name: str, arm: str) -> Optional[Dict[str, Any]]:
    d = camp / name
    g = load(d) if d.is_dir() else None
    if not g:
        return None
    st_all = rows(d / "p1_stamps.jsonl")
    fr = measured_frames(d, g["frames"])
    fb = forward_block(fr) if fr else {}
    rb = json.loads((d / "p1_readback.json").read_text()) if (d / "p1_readback.json").exists() else {}
    comp = components(fr, arm, st_all)
    out = {k: g[k] for k in ("dir", "videos", "errors", "frames", "frames_match_export", "span_s", "frames_per_s",
                             "records_frames_per_s", "cpu_s_per_frame", "engine_cores", "service_cpu_s", "boot_id", "session")}
    out.update({"arm": arm, "stamp_frames_measured": len(fr), "F_s": fb.get("forward_mean_s"), "forward_D1": fb.get("forward"),
                "cores_in_forward": fb.get("cores_in_forward"), "caller_cpu_ratio": fb.get("caller_cpu_ratio"),
                "lock_duty": comp.get("lock_duty"), "components": comp, "caller_switch": switch_rate(fr),
                "memory_peak_total_bytes": mem_peak(d),
                "readback": {"torch_num_threads": (rb.get("torch") or {}).get("num_threads") if isinstance(rb.get("torch"), dict) else None,
                             "OMP_WAIT_POLICY": (rb.get("env") or {}).get("OMP_WAIT_POLICY", "ABSENT"),
                             "OMP_NUM_THREADS": (rb.get("env") or {}).get("OMP_NUM_THREADS"),
                             "os_threads": len(rb.get("os_threads") or []), "pid": rb.get("pid")},
                "gates": {"G_d0": (gate_rec(camp, f"G_d0_{name}") or {}).get("outcome"),
                          "G_cell": (gate_rec(camp, f"G_cell_{name}") or {}).get("outcome")},
                "_by_video": g["by_video"]})
    return out


def mean(v: List[float]) -> Optional[float]:
    v = [x for x in v if x is not None]
    return statistics.mean(v) if v else None


def cell_of(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    def pair(k):
        v = [x[k] for x in legs]
        return {"per_leg": v, "mean": mean(v), "spread": spread(*v) if len(v) == 2 and None not in v else None}
    return {"legs": [x["dir"] for x in legs], "n_legs": len(legs), "F_s": pair("F_s"), "frames_per_s": pair("frames_per_s"),
            "lock_duty": pair("lock_duty"), "cores_in_forward": pair("cores_in_forward"), "cpu_s_per_frame": pair("cpu_s_per_frame"),
            "caller_switch_rate": pair_v([x["caller_switch"]["rate"] for x in legs]),
            "caller_threads": [x["caller_switch"]["caller_threads"] for x in legs],
            "caller_cpu_ratio": pair("caller_cpu_ratio"), "engine_cores": pair("engine_cores"),
            "memory_peak_total_bytes": [x["memory_peak_total_bytes"] for x in legs],
            "forward_p50": pair_v([(x["forward_D1"] or {}).get("p50") for x in legs]),
            "forward_p95": pair_v([(x["forward_D1"] or {}).get("p95") for x in legs])}


def pair_v(v: List[Optional[float]]) -> Dict[str, Any]:
    return {"per_leg": v, "mean": mean(v), "spread": spread(*v) if len(v) == 2 and None not in v else None}


def main() -> int:
    camp = Path(sys.argv[1])
    gl = gated_legs(camp)
    legs: Dict[str, Any] = {}
    for c, names in CELLS.items():
        for n in names:
            d = gl.get(n)
            legs[n] = leg(camp, d, ARM[c]) if d else None
    cells = {c: cell_of([legs[n] for n in names if legs.get(n)]) for c, names in CELLS.items()
             if any(legs.get(n) for n in names)}
    complete = {c: cells.get(c, {}).get("n_legs") == 2 for c in CELLS}

    # ---------------- correctness before speed
    def ident(a: str, b: str) -> Optional[Dict[str, Any]]:
        la, lb = legs.get(a), legs.get(b)
        if not la or not lb:
            return None
        x = identity({"dir": la["dir"], "by_video": la["_by_video"]}, {"dir": lb["dir"], "by_video": lb["_by_video"]})
        x["videos_eq_16"] = x["videos_compared"] == 16
        return x
    act_pairs = [ident(a, b) for a in CELLS["rr_k16_active"] for b in CELLS["rr_k16"]]
    act_pairs = [x for x in act_pairs if x]
    gate_active = {"pairs": act_pairs, "pass": bool(act_pairs) and all(x["identical"] and x["videos_eq_16"] for x in act_pairs),
                   "rule": "every (ACTIVE, RR K=16) pair identical (chunk sha256 AND frame scores) on 16/16 videos",
                   "chain_record": (gate_rec(camp, "G_correct_active") or {}).get("outcome")}
    beside = {"rr_k16_run_to_run": ident(*CELLS["rr_k16"]), "rr_k1_run_to_run": ident(*CELLS["rr_k1"]),
              "rr_k1_vs_rr_k16": [x for x in (ident(a, b) for a in CELLS["rr_k1"] for b in CELLS["rr_k16"]) if x],
              "li_k16_run_to_run": ident(*CELLS["li_k16"]), "li_k1_run_to_run": ident(*CELLS["li_k1"]),
              "li_k1_vs_li_k16": [x for x in (ident(a, b) for a in CELLS["li_k1"] for b in CELLS["li_k16"]) if x],
              "active_run_to_run": ident(*CELLS["rr_k16_active"])}

    # ---------------- readings
    F = {c: cells[c]["F_s"]["mean"] for c in cells}
    SF = {c: cells[c]["F_s"]["spread"] for c in cells}
    FPS = {c: cells[c]["frames_per_s"]["mean"] for c in cells}
    rd: Dict[str, Any] = {}
    need1 = ("rr_k1", "rr_k16", "li_k1", "li_k16")
    if all(complete[c] for c in need1):
        d_rr, d_li = F["rr_k16"] / F["rr_k1"], F["li_k16"] / F["li_k1"]
        s1 = max(SF[c] for c in need1)
        excess = d_rr / d_li - 1
        c1, c2 = excess > s1, FPS["rr_k1"] >= FPS["li_k1"]
        rd["R1"] = {"D_RR": d_rr, "D_LI": d_li, "D_RR_over_D_LI_minus_1": excess, "S1": s1,
                    "clause_degradation_beyond": c1, "clause_rr_k1_fps_ge_li_k1": c2,
                    "rr_k1_fps": FPS["rr_k1"], "li_k1_fps": FPS["li_k1"], "rr_k1_over_li_k1_fps_minus_1": FPS["rr_k1"] / FPS["li_k1"] - 1,
                    "k1_spread_max_fps": max(cells["rr_k1"]["frames_per_s"]["spread"], cells["li_k1"]["frames_per_s"]["spread"]),
                    "sum_of_four_F_spreads_context": sum(SF[c] for c in need1),
                    "verdict": "SUPPORTED" if (c1 and c2) else "NOT SUPPORTED",
                    "failed_clauses": [n for n, ok in (("RR's degradation does not exceed LI's beyond S1", c1),
                                                       ("RR K=1 f/s < LI K=1 f/s", c2)) if not ok]}
    else:
        rd["R1"] = {"verdict": "NOT EVALUABLE", "missing_cells": [c for c in need1 if not complete[c]]}
    need2 = ("rr_k1", "rr_k16", "rr_k16_active")
    if all(complete[c] for c in need2):
        deg = F["rr_k16"] / F["rr_k1"] - 1
        pre_deg = deg > max(SF["rr_k1"], SF["rr_k16"])
        s2 = max(SF["rr_k16"], SF["rr_k16_active"])
        closure = (F["rr_k16"] - F["rr_k16_active"]) / (F["rr_k16"] - F["rr_k1"]) if F["rr_k16"] != F["rr_k1"] else None
        red = F["rr_k16"] / F["rr_k16_active"] - 1
        base = {"rr_degradation_minus_1": deg, "degradation_threshold": max(SF["rr_k1"], SF["rr_k16"]),
                "precondition_degradation_beyond": pre_deg, "precondition_correctness": gate_active["pass"],
                "closure": closure, "active_reduction_F16_over_Factive_minus_1": red, "S2": s2,
                "active_fps_vs_rr_k16_minus_1": FPS["rr_k16_active"] / FPS["rr_k16"] - 1}
        if not gate_active["pass"]:
            base["verdict"] = "OUTPUT-CHANGING: no speed reading (the ACTIVE cell is not output-identical to RR K=16 on 16/16)"
        elif not pre_deg:
            base["verdict"] = "NOT EVALUABLE: RR's forward does not degrade from K=1 to K=16 beyond its spreads"
        elif closure is not None and closure >= 0.5 and red > s2:
            base["verdict"] = "R2 POOL WAKE-UP (the fix is CONFIG)"
        else:
            base["verdict"] = "R3 NOT WAKE-UP (caller interleaving or shared contention; P5 candidate: a single inference thread)"
        rd["R2_R3"] = base
    else:
        rd["R2_R3"] = {"verdict": "NOT EVALUABLE", "missing_cells": [c for c in need2 if not complete[c]]}

    for x in legs.values():
        if x:
            x["_by_video"] = f"{len(x['_by_video'])} videos (chunk hashes, frame scores; records file)"
    out = {"label": "P4-A video concurrency (preregistration.json P4_A_video_concurrency)", "gated_legs": gl,
           "cells_complete": complete, "legs": legs, "cells": cells,
           "correctness": {"G_correct_active": gate_active, "beside": beside}, "readings": rd,
           "sessions": sorted({x["boot_id"] for x in legs.values() if x and x.get("boot_id")})}
    (camp / "analysis_p4a.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p4a.json: R1 {rd['R1'].get('verdict')}; R2/R3 {rd['R2_R3'].get('verdict')}; correctness {gate_active['pass']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
