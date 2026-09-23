#!/usr/bin/env python3
"""P0 V1 (matched single instance) and V2 (duty cycle, per-frame decomposition), from raw records.

    p0_analyse_video.py <campaign_dir> v1|v1full|v2  -> analysis_<stage>.json

Per leg directory: records_*.jsonl (one row per video: role, frames_observed, admit_ns/done_ns on
CLOCK_MONOTONIC, chunk_sha256, frame_scores, frame_label_multisets, error), export_*.json (the
driver's export: efficiency.service_cpu_s / effective_cores, p0 block), p0_v2_stamps.jsonl (V2).
  frames/s   = export total_frames / total_span_s (the driver's leg wall; checked equal to the sum
               of frames_observed over measured rows without error); the records' admit->done
               span is reported beside it
  CPU-s/frame = export efficiency.service_cpu_s / those frames; engine cores = effective_cores
  V1 gap = mean(li_t4 f/s) / mean(rr_t4 f/s) - 1; gate: gap - max(0.82%, spread rr_t4,
           spread li_t4) >= 10 percentage points (preregistration.json V1)
  V2 duty cycle = sum of lock-held time / (last frame end - first frame start); the D1 metric set
           per component; null control = RocketRide stamped vs unstamped frames/s within
           max(0.82%, both spreads) AND identical per-video chunk hashes and frame scores.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

FLOOR = 0.0082


def rows(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def q_nearest(v: List[float], q: float) -> float:
    s = sorted(v)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def metric_set(v: List[float], run_total: Optional[float] = None) -> Dict[str, Any]:
    v = [x for x in v if x is not None]
    if not v:
        return {"count": 0}
    mean, med = sum(v) / len(v), statistics.median(v)
    return {"count": len(v), "sum": sum(v),
            "share_of_run_total": (sum(v) / run_total) if run_total else None,
            "min": min(v), "mean": mean, "sd": statistics.pstdev(v) if len(v) > 1 else 0.0,
            "p50": med, "p90": q_nearest(v, .9), "p95": q_nearest(v, .95), "p99": q_nearest(v, .99),
            "max": max(v), "mean_over_p50": mean / med if med else None}


def spread(a: float, b: float) -> float:
    return abs(a - b) / ((a + b) / 2)


def load(d: Path) -> Optional[Dict[str, Any]]:
    rec = sorted(d.glob("records_*.jsonl"))
    exp = sorted(d.glob("export_*.json"))
    if not rec or not exp:
        return None
    rs = [r for r in rows(rec[0]) if r.get("role") == "measured"]
    last = {}
    for r in rs:                                  # the driver's rule: the LAST record per video
        last[r["video"]] = r
    rs = list(last.values())
    ok = [r for r in rs if "error" not in r]
    frames = sum(r.get("frames_observed") or 0 for r in ok)
    t0 = min(r["admit_ns"] for r in rs if r.get("admit_ns"))
    t1 = max(r["done_ns"] for r in rs if r.get("done_ns"))
    span = (t1 - t0) / 1e9
    e = json.loads(exp[0].read_text())
    eff = e.get("efficiency") or {}
    cpu_s = eff.get("service_cpu_s")
    th = e.get("throughput") or {}
    # PRIMARY frames/s = the export's total_frames / total_span_s (the driver's leg wall) — the
    # definition every banked video figure used (S5-A's 2.233, G4's 3.068). The records' own
    # admit->done span is reported beside it, never substituted.
    return {"dir": d.name, "videos": len(rs), "errors": len(rs) - len(ok), "frames": frames,
            "frames_match_export": frames == th.get("total_frames"),
            "span_s": th.get("total_span_s"),
            "frames_per_s": (th["total_frames"] / th["total_span_s"]) if th.get("total_span_s") else None,
            "records_span_s": span, "records_frames_per_s": frames / span if span else None,
            "export_frames_per_s": th.get("total_frames_per_s"),
            "export_total_frames": th.get("total_frames"),
            "cpu_s_per_frame": (cpu_s / frames) if (cpu_s and frames) else None,
            "engine_cores": eff.get("effective_cores"), "service_cpu_s": cpu_s,
            "boot_id": (d / "boot_id.txt").read_text().strip() if (d / "boot_id.txt").exists() else None,
            "p0": e.get("p0") or (e.get("provenance_video") or {}).get("p0"),
            "task_census": e.get("task_census") or (e.get("provenance_video") or {}).get("task_census"),
            "session": session_facts(d),
            "thread_pins": (e.get("thread_pins_by_arm") or {}).get("cross_arm_values"),
            "by_video": {r["video"]: {"chunk_sha256": r.get("chunk_sha256"),
                                      "frame_scores": r.get("frame_scores"),
                                      "labels": r.get("frame_label_multisets")} for r in ok}}


def session_facts(d: Path) -> Dict[str, Any]:
    """The leg's own records: boot id, steal over the leg (aggregate /proc/stat at open and close),
    mean core MHz at open and close, CPU model."""
    out: Dict[str, Any] = {}
    try:
        a = [int(x) for x in (d / "procstat_open.txt").read_text().split()[1:]]
        b = [int(x) for x in (d / "procstat_close.txt").read_text().split()[1:]]
        dl = [y - x for x, y in zip(a, b)]
        total = sum(dl[:8])
        out["steal_share"] = dl[7] / total if total else None
    except (OSError, ValueError, IndexError):
        out["steal_share"] = None
    for tag in ("open", "close"):
        try:
            v = [float(l.split(":")[1]) for l in (d / f"mhz_{tag}.txt").read_text().splitlines() if ":" in l]
            out[f"mhz_{tag}_mean"] = sum(v) / len(v) if v else None
        except OSError:
            out[f"mhz_{tag}_mean"] = None
    try:
        out["cpu_model"] = (d / "cpu_model.txt").read_text().split(":", 1)[1].strip()
    except (OSError, IndexError):
        out["cpu_model"] = None
    return out


def cell(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    v = [g["frames_per_s"] for g in legs]
    return {"legs": [g["dir"] for g in legs], "frames_per_s": v, "mean": sum(v) / len(v),
            "spread": spread(*v) if len(v) == 2 else None,
            "cpu_s_per_frame": [g["cpu_s_per_frame"] for g in legs],
            "engine_cores": [g["engine_cores"] for g in legs]}


def identity(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    both = sorted(set(a["by_video"]) & set(b["by_video"]))
    chunk_diff = [v for v in both if a["by_video"][v]["chunk_sha256"] != b["by_video"][v]["chunk_sha256"]]
    score_diff = [v for v in both if a["by_video"][v]["frame_scores"] != b["by_video"][v]["frame_scores"]]
    return {"a": a["dir"], "b": b["dir"], "videos_compared": len(both),
            "chunk_hash_differs": chunk_diff, "frame_scores_differ": score_diff,
            "identical": not chunk_diff and not score_diff}


def v2_components(d: Path, arm: str) -> Dict[str, Any]:
    st = rows(d / "p0_v2_stamps.jsonl")
    if not st:
        return {"status": "NO STAMPS"}
    if arm == "rr":
        fr = st
        comps = ("decode", "lock_wait", "resize", "preprocess", "predict_pre", "forward",
                 "predict_post", "dict_build", "loader_post", "rescale", "inside_other",
                 "lock_held", "emit")
        per_frame_total = [sum(x or 0 for x in (r.get("decode"), r.get("lock_wait"),
                                                  r.get("lock_held"), r.get("emit"))) for r in fr]
        run_total = sum(per_frame_total)
        t0 = min(r["t_wall"] for r in fr)
        t1 = max(r["t_wall"] + tot for r, tot in zip(fr, per_frame_total))
        held = sum(r.get("lock_held") or 0 for r in fr)
        out = {"frames": len(fr), "run_total_s": run_total, "window_s": t1 - t0,
               "duty_cycle": held / (t1 - t0) if t1 > t0 else None,
               "components": {c: metric_set([r.get(c) for r in fr], run_total) for c in comps},
               "forward_hooks_fired": sum(1 for r in fr if r.get("forward") is not None),
               "inside_lock_not_forward_s": sum((r.get("lock_held") or 0) - (r.get("forward") or 0) for r in fr)}
        return out
    fr = [r for r in st if r.get("kind") == "frame"]
    vids = [r for r in st if r.get("kind") == "video"]
    comps = ("load_decode", "predict_pre", "forward", "predict_post", "dict_build", "format", "lock_held")
    run_total = sum(r.get("lock_held") or 0 for r in fr) + sum(r.get("lock_wait") or 0 for r in vids)
    t0 = min(r["t_wall"] for r in fr) if fr else None
    t1 = max(r["t_wall_release"] for r in vids) if vids else None
    held = sum(r.get("lock_held") or 0 for r in vids)
    return {"frames": len(fr), "videos": len(vids), "run_total_s_in_detect": run_total,
            "window_s": (t1 - t0) if (t0 and t1) else None,
            "duty_cycle": (held / (t1 - t0)) if (t0 and t1 and t1 > t0) else None,
            "components": {c: metric_set([r.get(c) for r in fr], run_total) for c in comps},
            "per_video": {"lock_wait": metric_set([r.get("lock_wait") for r in vids]),
                          "lock_held": metric_set([r.get("lock_held") for r in vids]),
                          "extract_outside_lock": metric_set([r.get("extract_outside_lock") for r in vids])},
            "forward_hooks_fired": sum(1 for r in fr if r.get("forward") is not None),
            "lock_scope_note": "the LlamaIndex lock is taken once per VIDEO around the whole frame loop"}


def main() -> int:
    camp, stage = Path(sys.argv[1]), sys.argv[2]
    legs = {d.name: load(d) for d in sorted(camp.iterdir()) if d.is_dir() and d.name.startswith(stage + "_")}
    legs = {k: v for k, v in legs.items() if v}
    base = lambda n: n.rsplit("_r", 1)[0] if n.rsplit("_r", 1)[-1].isdigit() else n  # noqa: E731
    res: Dict[str, Any] = {"legs": {k: {x: v[x] for x in v if x != "by_video"} for k, v in legs.items()},
                           "sessions": sorted({v["boot_id"] for v in legs.values() if v["boot_id"]})}
    def pick(prefix):
        return [v for k, v in sorted(legs.items()) if base(k).startswith(prefix)]
    if stage in ("v1", "v1full"):
        rr4, li4, rrd = pick(f"{stage}_rr_t4"), pick(f"{stage}_li_t4"), pick(f"{stage}_rr_def")
        res["cells"] = {"rr_t4": cell(rr4) if rr4 else None, "li_t4": cell(li4) if li4 else None,
                        "rr_default": cell(rrd) if rrd else None}
        if rr4 and li4:
            gap = res["cells"]["li_t4"]["mean"] / res["cells"]["rr_t4"]["mean"] - 1
            thr = max([FLOOR] + [c["spread"] for c in (res["cells"]["rr_t4"], res["cells"]["li_t4"])
                                 if c["spread"] is not None])
            res["gap"] = {"li_over_rr_minus_1": gap, "threshold": thr, "margin_pp": gap - thr,
                          "gate_fired": (stage == "v1" and len(rr4) == 2 and len(li4) == 2
                                         and gap - thr >= 0.10),
                          "rule": "gap - max(0.82%, spread rr_t4, spread li_t4) >= 10 percentage points"}
        if len(rr4) == 2:
            res["rr_t4_determinism"] = identity(rr4[0], rr4[1])
        if len(rrd) == 2:
            res["rr_default_determinism"] = identity(rrd[0], rrd[1])
        if rr4 and rrd:
            res["rr_t4_vs_default_output"] = identity(rrd[0], rr4[0])
    else:
        rs, ru, ls = pick("v2_rr_s"), pick("v2_rr_u"), pick("v2_li_s")
        res["null_control"] = None
        if len(rs) == 2 and len(ru) == 2:
            cs, cu = cell(rs), cell(ru)
            d = cs["mean"] / cu["mean"] - 1
            thr = max(FLOOR, cs["spread"], cu["spread"])
            ids = [identity(ru[0], rs[0]), identity(ru[1], rs[1])]
            det = identity(ru[0], ru[1])
            res["null_control"] = {"stamped": cs, "unstamped": cu, "delta": d, "threshold": thr,
                                   "throughput_within": abs(d) <= thr, "output_identity": ids,
                                   "unstamped_determinism": det,
                                   "pass": abs(d) <= thr and all(x["identical"] for x in ids)}
        res["rr_components"] = {g["dir"]: v2_components(camp / g["dir"], "rr") for g in rs}
        res["li_components"] = {g["dir"]: v2_components(camp / g["dir"], "li") for g in ls}
    out = camp / f"analysis_{stage}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
