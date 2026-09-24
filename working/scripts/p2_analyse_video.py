#!/usr/bin/env python3
"""P2-B video analysis (preregistration.json P2_B + amendment 1), from raw leg files only.

    p2_analyse_video.py <campaign_dir> [--p1 <p1_campaign_dir>]  -> analysis_p2b.json

Per leg (P0/P1 loaders unchanged): frames/s = export total_frames / total_span_s (p0_analyse_video.load; amendment 1),
the records' own rate beside it; per-video outputs (chunk hashes, frame scores); the P1 stamped copy's forward
block over the measured frames (p1_analyse_e2: the last N frame stamps by wall time); the in-process read-back
(debugger, malloc environment, OS threads); memory; session facts. Then the correctness gate (COMBINED vs baseline,
16/16 in both pairs), the reading on the PRIMARY metric, and the same closure on F beside it (mechanism).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import FLOOR, cell, identity, load, spread  # noqa: E402
from p1_analyse_e2 import forward_block, measured_frames  # noqa: E402

CELLS = {"rr_base": ["p2b_rr_base_a", "p2b_rr_base_b"], "rr_comb": ["p2b_rr_comb_a", "p2b_rr_comb_b"],
         "li_ref": ["p2b_li_a", "p2b_li_b"]}


def leg_dir(camp: Path, name: str) -> Optional[Path]:
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and list(d.glob("export_*.json")) and list(d.glob("records_*.jsonl")):
            return d
    return None


def readback(d: Path) -> Dict[str, Any]:
    rb = json.loads((d / "p1_readback.json").read_text()) if (d / "p1_readback.json").exists() else {}
    pf = sorted(d.glob("preflight_*.json"))
    p0 = (json.loads(pf[0].read_text()).get("p0") or {}) if pf else {}
    tr = {k: ((p0.get(k) or {}).get("trace") or {}) for k in ("d0_pre", "d0_post") if p0.get(k)}
    return {"pydevd_loaded": {k: v.get("pydevd_loaded") for k, v in tr.items()},
            "debugpy_loaded": {k: v.get("debugpy_loaded") for k, v in tr.items()},
            "sys_monitoring_tools_env_probe": {k: v.get("sys_monitoring_tools") for k, v in tr.items()},
            "monitoring_tools_detector": rb.get("monitoring_tools"), "gettrace_detector": rb.get("gettrace"),
            "malloc_env_detector": {k: v for k, v in (rb.get("env") or {}).items() if k.startswith("MALLOC_")},
            "os_threads_detector": len(rb.get("os_threads") or []),
            "proc_threads_env_probe": {k: (p0.get(k) or {}).get("proc_threads") for k in ("d0_pre", "d0_post") if p0.get(k)},
            "python_threads_detector": len(rb.get("python_threads") or []),
            "torch": {k: (rb.get("torch") or {}).get(k) for k in ("num_threads", "num_interop_threads", "cpu_capability")}
            if isinstance(rb.get("torch"), dict) else rb.get("torch"),
            "env_detector": rb.get("env"), "python_thread_names": rb.get("python_threads"),
            "thread_name_counts": _counts([t[1] for t in (rb.get("os_threads") or [])])}


def _counts(names: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for n in names:
        out[n] = out.get(n, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def leg(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    d = leg_dir(camp, name)
    if d is None:
        return None
    g = load(d)
    fr = measured_frames(d, g["frames"]) if (d / "p1_stamps.jsonl").exists() else []
    ms = d / "memstat.jsonl.summary.json"
    return {"name": name, "dir": d.name, "summary": g, "frames_per_s": g["frames_per_s"],
            "records_frames_per_s": g["records_frames_per_s"], "errors": g["errors"], "videos": g["videos"],
            "frames_match_export": g["frames_match_export"], "forward": forward_block(fr) if fr else None,
            "readback": readback(d), "memstat": json.loads(ms.read_text()) if ms.exists() else None,
            "session": g["session"], "boot_id": g["boot_id"]}


def closure(base: float, comb: float, li: float) -> Optional[float]:
    gap = li - base
    return (comb - base) / gap if gap else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--p1", type=Path, default=None, help="P1 campaign dir (cross-session determinism, context only)")
    a = ap.parse_args()
    L = {n: leg(a.camp, n) for ns in CELLS.values() for n in ns}
    out: Dict[str, Any] = {"label": "P2-B video configuration suspects, untraced (preregistration.json P2_B + amendment 1)",
                           "legs": {n: ({k: v for k, v in x.items() if k != "summary"} | {"summary": {k: v for k, v in x["summary"].items() if k != "by_video"}})
                                    if x else None for n, x in L.items()},
                           "boot_ids": sorted({x["boot_id"] for x in L.values() if x and x.get("boot_id")})}
    have = {c: [L[n] for n in ns if L.get(n)] for c, ns in CELLS.items()}
    # correctness gate: COMBINED vs baseline, same pair, 16/16
    pairs = []
    for r in ("a", "b"):
        b, c = L.get(f"p2b_rr_base_{r}"), L.get(f"p2b_rr_comb_{r}")
        if b and c:
            idn = identity(b["summary"], c["summary"])
            idn["sixteen_of_sixteen"] = idn["identical"] and idn["videos_compared"] == 16 and b["errors"] == 0 and c["errors"] == 0
            pairs.append(idn)
    cg = {"pairs": pairs, "rule": "COMBINED chunk-identical to baseline (chunk hashes AND frame scores) on 16/16 videos in BOTH pairs",
          "pass": len(pairs) == 2 and all(p["sixteen_of_sixteen"] for p in pairs)}
    cg["outcome"] = "PASS" if cg["pass"] else ("NOT EVALUABLE (a pair is missing)" if len(pairs) < 2 else "FAIL — OUTPUT-CHANGING: no speed verdict")
    out["correctness_gate"] = cg
    ctx = {}
    for x, y in (("p2b_rr_base_a", "p2b_rr_base_b"), ("p2b_li_a", "p2b_li_b")):
        if L.get(x) and L.get(y):
            ctx[f"{x}_vs_{y}"] = identity(L[x]["summary"], L[y]["summary"])
    if a.p1:
        for x, y in (("p2b_rr_base_a", "e2_rr_off_a"), ("p2b_li_a", "e2_li_off_a")):
            dp = leg_dir(a.p1, y)
            if L.get(x) and dp:
                ctx[f"{x}_vs_P1_{y}"] = identity(L[x]["summary"], load(dp))
    out["determinism_context"] = ctx
    # cells and the reading
    C = {c: cell([x["summary"] for x in have[c]]) for c in CELLS if len(have[c]) == 2}
    out["cells"] = C
    Fm: Dict[str, Any] = {}
    for c in CELLS:
        fw = [x["forward"]["forward_mean_s"] for x in have[c] if x.get("forward") and x["forward"].get("forward_mean_s")]
        cr = [x["forward"]["caller_cpu_ratio"] for x in have[c] if x.get("forward") and x["forward"].get("caller_cpu_ratio") is not None]
        Fm[c] = {"F_legs_s": fw, "F_mean_s": statistics.mean(fw) if fw else None, "F_spread": spread(*fw) if len(fw) == 2 else None,
                 "caller_cpu_ratio_legs": cr, "caller_cpu_ratio_mean": statistics.mean(cr) if cr else None}
    out["forward_mechanism"] = Fm
    rd: Dict[str, Any] = {"floor": FLOOR}
    if len(C) == 3:
        base, comb, li = C["rr_base"]["mean"], C["rr_comb"]["mean"], C["li_ref"]["mean"]
        gap_rel = li / base - 1
        gthr = max(FLOOR, C["li_ref"]["spread"], C["rr_base"]["spread"])
        rd["gap"] = {"li_minus_base_frames_per_s": li - base, "li_over_base_minus_1": gap_rel, "threshold": gthr,
                     "reproduced_in_session": gap_rel > gthr}
        ch = comb / base - 1
        cthr = max(FLOOR, C["rr_base"]["spread"], C["rr_comb"]["spread"])
        cl = closure(base, comb, li)
        rd["combined"] = {"comb_over_base_minus_1": ch, "threshold": cthr, "beyond_spread": ch > cthr, "closure": cl}
        if not cg["pass"]:
            rd["verdict"] = "OUTPUT-CHANGING — no speed verdict" if len(pairs) == 2 else "NOT EVALUABLE"
        elif not rd["gap"]["reproduced_in_session"]:
            rd["verdict"] = "THE GAP DID NOT REPRODUCE IN SESSION — no reading"
        elif cl is not None and cl >= 0.5 and ch > cthr:
            rd["verdict"] = "CONFIGURATION EXPLAINS THE GAP"
        else:
            rd["verdict"] = "CONFIGURATION DOES NOT EXPLAIN THE GAP (at this strength: the debugger and MALLOC_ARENA_MAX jointly ruled out as the main cause)"
        if all(Fm[c]["F_mean_s"] for c in CELLS):
            fb, fc, fl = Fm["rr_base"]["F_mean_s"], Fm["rr_comb"]["F_mean_s"], Fm["li_ref"]["F_mean_s"]
            rd["secondary_F"] = {"label": "mechanism, reported beside; the verdict follows the PRIMARY metric",
                                 "F_base_s": fb, "F_comb_s": fc, "F_li_s": fl, "closure_on_F": closure(fb, fc, fl),
                                 "comb_over_base_minus_1": fc / fb - 1,
                                 "threshold": max(FLOOR, Fm["rr_base"]["F_spread"] or 0, Fm["rr_comb"]["F_spread"] or 0)}
    else:
        rd["verdict"] = "NOT EVALUABLE (a cell lacks two legs)"
    out["reading"] = rd
    # read-back differences COMBINED vs LlamaIndex (for the next suspects)
    rc, rl = (have["rr_comb"][0]["readback"] if have["rr_comb"] else None), (have["li_ref"][0]["readback"] if have["li_ref"] else None)
    if rc and rl:
        diff = {}
        for k in ("malloc_env_detector", "monitoring_tools_detector", "gettrace_detector", "os_threads_detector",
                  "python_threads_detector", "torch"):
            if rc.get(k) != rl.get(k):
                diff[k] = {"rr_comb": rc.get(k), "li": rl.get(k)}
        ea, eb = rc.get("env_detector") or {}, rl.get("env_detector") or {}
        envd = {k: {"rr_comb": ea.get(k), "li": eb.get(k)} for k in sorted(set(ea) | set(eb)) if ea.get(k) != eb.get(k)}
        if envd:
            diff["env_detector"] = envd
        diff["thread_name_counts"] = {"rr_comb": rc.get("thread_name_counts"), "li": rl.get("thread_name_counts")}
        out["readback_differences_comb_vs_li"] = diff
    f = a.camp / "analysis_p2b.json"
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote {f}: {rd.get('verdict')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
