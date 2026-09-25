#!/usr/bin/env python3
"""P6 analysis (preregistration.json), from raw leg files only; imported by p6_gates.py smoke (G_smoke_P6B decides from
exactly this code). Per-leg metrics are P5's (p5_analyse_a.leg: frames/s, the forward D1 set, inference duty, cores busy in
the forward, CPU-s/frame, queue depth, memory, session facts).

    p6_analyse.py <campaign_dir>  -> analysis_p6.json   (sections P6_A, P6_B, P6_C)

P6-A: correctness per round (P5 vs stock, 16/16), Q1 = P5 f/s / LI f/s >= 0.95 and Q2 = P5 f/s / stock f/s >= 1.20, per
round and pooled (FIXED tolerances); DESCRIPTIVE only: the P5 forward at K=16 over P5's committed K=1 forward reference
(parity_p5 p5a_p5k1_1/2), mean and the p50/p99 split. P6-B: per block and arm, per-arm totals, the ratio against 0.95, the
per-block ratio distribution, errors, D0, warm checks, the paused arm's CPU, correctness per video against P1-D. P6-C: the
out-of-box thread count (T=16): correctness against the out-of-box reference (P0 V1 v1_rr_def_a), the P5 T=16 forward over
the P5 T=4 forward of P6-A (<= 0.95 = faster by at least 5%), and P5 T=16 f/s / LI T=16 f/s against 0.95.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import identity, load  # noqa: E402
from p5_analyse_a import canary_leg, leg, spread0  # noqa: E402

RES = Path(__file__).resolve().parents[2] / "working" / "results"
P5C = RES / "parity_p5_20260925T141647Z"
P1D = RES / "parity_p1_20260923T184000Z" / "v1full_rr_t4"
P0DEF = RES / "parity_p0_20260923T083031Z" / "v1_rr_def_a"
Q1_BAR, Q2_BAR, T16_BAR = 0.95, 1.20, 0.95
A_CELLS = {"stock_k16": ("p6a_stock16_1", "p6a_stock16_2", "stock"), "p5_k16": ("p6a_p5k16_1", "p6a_p5k16_2", "p5"),
           "li_k16": ("p6a_li16_1", "p6a_li16_2", "li")}
C_CELLS = {"p5_t16": ("p6c_p5t16_1", "p6c_p5t16_2", "p5"), "li_t16": ("p6c_lit16_1", "p6c_lit16_2", "li")}


def gated(camp: Path, done: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    p = camp / done
    if p.exists():
        for x in json.loads(p.read_text()).get("legs", []):
            d, _, st = x.partition(":")
            if st in ("rc=0", "DEGRADED_all_rows"):
                out.setdefault(d[:-3] if d[-3:] in ("_r1", "_r2") else d, d)
    return out


def first_attempt(camp: Path, name: str) -> Optional[str]:
    for suf in ("", "_r1", "_r2"):
        if list((camp / f"{name}{suf}").glob("export_*.json")):
            return f"{name}{suf}"
    return None


def cells_of(camp: Path, spec, gl) -> Dict[str, Any]:
    legs: Dict[str, Any] = {}
    for c, (a, b, fl) in spec.items():
        for n in (a, b):
            d = gl.get(n) or first_attempt(camp, n)
            legs[n] = leg(camp, d, fl) if d else None
    cells = {}
    for c, (a, b, fl) in spec.items():
        L = [legs[a], legs[b]]

        def pv(k, sub=None):
            v = [(x.get(k) if sub is None else (x.get(k) or {}).get(sub)) if x else None for x in L]
            full = None not in v
            return {"round_1": v[0], "round_2": v[1], "mean": statistics.mean(v) if full else None, "spread": spread0(*v) if full else None}
        cells[c] = {"legs": [x["dir"] if x else None for x in L], "complete": None not in L, "frames_per_s": pv("frames_per_s"), "F_s": pv("F_s"),
                    "duty": pv("duty"), "cores_in_forward": pv("cores_in_forward"), "cpu_s_per_frame": pv("cpu_s_per_frame"),
                    "memory_peak_total_bytes": pv("memory_peak_total_bytes"), "forward_p50": pv("forward_D1", "p50"),
                    "forward_p99": pv("forward_D1", "p99"), "engine_cores": pv("engine_cores")}
    return {"legs": legs, "cells": cells}


def ident(x, y, n=16):
    if not x or not y:
        return None
    i = identity({"dir": x["dir"], "by_video": x["_by_video"]}, {"dir": y["dir"], "by_video": y["_by_video"]})
    i["videos_eq_n"] = i["videos_compared"] == n
    return i


def strip(legs):
    for x in legs.values():
        if x and isinstance(x.get("_by_video"), dict):
            x["_by_video"] = f"{len(x['_by_video'])} videos (records file)"


def analyse_a(camp: Path) -> Dict[str, Any]:
    gl = gated(camp, "chain_p6_a_done.json")
    got = cells_of(camp, A_CELLS, gl)
    legs, C = got["legs"], got["cells"]
    pairs = [ident(legs[f"p6a_p5k16_{r}"], legs[f"p6a_stock16_{r}"]) for r in (1, 2)]
    pairs = [p for p in pairs if p]
    gate = (len(pairs) == 2 and all(p["identical"] and p["videos_eq_n"] for p in pairs)) if pairs else None
    if pairs and any(not (p["identical"] and p["videos_eq_n"]) for p in pairs):
        gate = False
    beside = {"stock_run_to_run": ident(legs["p6a_stock16_1"], legs["p6a_stock16_2"]), "p5_run_to_run": ident(legs["p6a_p5k16_1"], legs["p6a_p5k16_2"]),
              "li_run_to_run": ident(legs["p6a_li16_1"], legs["p6a_li16_2"])}
    rd: Dict[str, Any] = {}
    if all(C[c]["complete"] for c in A_CELLS):
        def q(num, den, bar, key):
            r = C[num]["frames_per_s"][key] / C[den]["frames_per_s"][key]
            return {"ratio": r, "bar": bar, "holds": r >= bar}
        rd["Q1"] = {k: q("p5_k16", "li_k16", Q1_BAR, k2) for k, k2 in (("round_1", "round_1"), ("round_2", "round_2"), ("pooled", "mean"))}
        rd["Q2"] = {k: q("p5_k16", "stock_k16", Q2_BAR, k2) for k, k2 in (("round_1", "round_1"), ("round_2", "round_2"), ("pooled", "mean"))}
        for s in ("Q1", "Q2"):
            rd[s]["verdict"] = ("HOLDS" if rd[s]["pooled"]["holds"] else "DOES NOT HOLD") + " (pooled); round 1 " + (
                "holds" if rd[s]["round_1"]["holds"] else "does not") + ", round 2 " + ("holds" if rd[s]["round_2"]["holds"] else "does not")
    else:
        rd["Q1"] = rd["Q2"] = {"verdict": "NOT EVALUABLE", "missing_cells": [c for c in A_CELLS if not C[c]["complete"]]}
    # DESCRIPTIVE ONLY: the P5 forward at K=16 over P5's committed K=1 forward (parity_p5 p5a_p5k1_1/2)
    ref = [leg(P5C, n, "p5") for n in ("p5a_p5k1_1", "p5a_p5k1_2")]
    desc = None
    if all(ref) and C["p5_k16"]["complete"]:
        rF = statistics.mean(x["F_s"] for x in ref)
        r50 = statistics.mean(x["forward_D1"]["p50"] for x in ref)
        r99 = statistics.mean(x["forward_D1"]["p99"] for x in ref)
        desc = {"label": "DESCRIPTIVE ONLY — never gated; the K=1 reference is P5's committed session (cross-session)",
                "reference_legs": ["parity_p5_20260925T141647Z/p5a_p5k1_1", "parity_p5_20260925T141647Z/p5a_p5k1_2"],
                "ref_F_s": rF, "ref_p50": r50, "ref_p99": r99,
                "F_over_ref_minus_1": C["p5_k16"]["F_s"]["mean"] / rF - 1,
                "p50_over_ref_minus_1": C["p5_k16"]["forward_p50"]["mean"] / r50 - 1,
                "p99_over_ref_minus_1": C["p5_k16"]["forward_p99"]["mean"] / r99 - 1}
    strip(legs)
    return {"gated_legs": gl, "legs": legs, "cells": C,
            "correctness": {"pairs": pairs, "gate_pass": gate, "beside": beside,
                            "rule": "P5 K=16 output identical to stock K=16 on 16/16 videos in each round (hard)"},
            "readings": rd, "descriptive_forward_degradation": desc,
            "canary": {n: canary_leg(camp, n) for n in ("p6c_can_a1", "p6c_can_a2")}}


def analyse_b(camp: Path) -> Optional[Dict[str, Any]]:
    names = [f"p6b_{arm}_b{b:02d}" for b in range(1, 12) for arm in ("rr", "li")]
    if not any((camp / n).is_dir() for n in names):
        return None
    blocks: Dict[str, Any] = {}
    for n in names:
        d = camp / n
        g = load(d) if d.is_dir() else None
        if not g:
            blocks[n] = None
            continue
        oc = json.loads((d / "other_container_cpu.json").read_text()) if (d / "other_container_cpu.json").exists() else {}
        try:
            other = (int(oc["cpu_usage_usec_after"]) - int(oc["cpu_usage_usec_before"])) / 1e6
        except (KeyError, ValueError, TypeError):
            other = None
        gate = lambda k: (json.loads((camp / "gates" / f"{k}_{n}.json").read_text()).get("outcome")  # noqa: E731
                          if (camp / "gates" / f"{k}_{n}.json").exists() else None)
        blocks[n] = {"dir": n, "videos": g["videos"], "errors": g["errors"], "frames": g["frames"], "span_s": g["span_s"],
                     "frames_per_s": g["frames_per_s"], "d0": gate("G_d0"), "cell": gate("G_cell"), "warm": gate("G_warm"),
                     "other_container": oc.get("other"), "other_container_cpu_s_during_block": other,
                     "other_container_state_at_start": (d / "other_container_state.txt").read_text().strip() if (d / "other_container_state.txt").exists() else None,
                     "_by_video": g["by_video"]}
    per_arm = {}
    for arm in ("rr", "li"):
        xs = [x for n, x in blocks.items() if x and n.startswith(f"p6b_{arm}_")]
        fr, sp = sum(x["frames"] for x in xs), sum(x["span_s"] for x in xs)
        per_arm[arm] = {"blocks": len(xs), "videos": sum(x["videos"] for x in xs), "errors": sum(x["errors"] for x in xs),
                        "frames": fr, "span_s": sp, "total_frames_per_s": fr / sp if sp else None}
    both = [b for b in range(1, 12) if blocks.get(f"p6b_rr_b{b:02d}") and blocks.get(f"p6b_li_b{b:02d}")]
    # beside the pre-registered totals (each arm over the blocks IT ran): the same over the blocks BOTH arms ran, so an
    # incomplete stage (the budget) still compares the same videos on both arms
    paired = {}
    for arm in ("rr", "li"):
        xs = [blocks[f"p6b_{arm}_b{b:02d}"] for b in both]
        fr, sp = sum(x["frames"] for x in xs), sum(x["span_s"] for x in xs)
        paired[arm] = {"blocks": len(xs), "videos": sum(x["videos"] for x in xs), "frames": fr, "span_s": sp,
                       "total_frames_per_s": fr / sp if sp else None}
    paired_ratio = (paired["rr"]["total_frames_per_s"] / paired["li"]["total_frames_per_s"]) if paired["rr"]["total_frames_per_s"] and paired["li"]["total_frames_per_s"] else None
    ratios = {str(b): blocks[f"p6b_rr_b{b:02d}"]["frames_per_s"] / blocks[f"p6b_li_b{b:02d}"]["frames_per_s"] for b in both}
    rv = sorted(ratios.values())
    tot = (per_arm["rr"]["total_frames_per_s"] / per_arm["li"]["total_frames_per_s"]) if per_arm["rr"]["total_frames_per_s"] and per_arm["li"]["total_frames_per_s"] else None
    ref = load(P1D)
    mine: Dict[str, Any] = {}
    for n, x in blocks.items():
        if x and n.startswith("p6b_rr_"):
            mine.update(x["_by_video"])
    differ, same = [], 0
    for v, o in sorted(mine.items()):
        r = (ref or {}).get("by_video", {}).get(v)
        if r is None or r["chunk_sha256"] != o["chunk_sha256"] or r["frame_scores"] != o["frame_scores"]:
            differ.append({"video": v, "absent_from_reference": r is None,
                           "chunk_hash_differs": bool(r) and r["chunk_sha256"] != o["chunk_sha256"],
                           "frame_scores_differ": bool(r) and r["frame_scores"] != o["frame_scores"]})
        else:
            same += 1
    strip(blocks)
    return {"blocks": blocks, "per_arm": per_arm, "ratio_rr_over_li_totals": tot, "q1_bar": Q1_BAR,
            "paired_blocks": {"blocks": both, "per_arm": paired, "ratio_rr_over_li": paired_ratio,
                              "meets_q1_bar": (paired_ratio >= Q1_BAR) if paired_ratio is not None else None,
                              "note": "beside the pre-registered totals: the same arithmetic over the blocks BOTH arms ran"},
            "complete_168": per_arm["rr"]["videos"] == 168 and per_arm["li"]["videos"] == 168,
            "ratio_meets_q1_bar": (tot >= Q1_BAR) if tot is not None else None,
            "per_block_ratio_distribution": {"blocks": len(rv), "min": rv[0] if rv else None, "p50": statistics.median(rv) if rv else None,
                                             "max": rv[-1] if rv else None, "per_block": ratios},
            "correctness_vs_p1d": {"reference": "parity_p1_20260923T184000Z/v1full_rr_t4", "videos_compared": len(mine), "identical": same,
                                   "differ": differ, "pass": bool(mine) and not differ and len(mine) == 168,
                                   "all_compared_identical": bool(mine) and not differ},
            "blocks_not_run": [n for n, x in blocks.items() if x is None],
            "start_warm": {n: (json.loads((camp / "gates" / f"G_warm_{n}.json").read_text()).get("outcome") if (camp / "gates" / f"G_warm_{n}.json").exists() else None)
                           for n in ("p6b_rr_startwarm", "p6b_li_startwarm")},
            "canary": {n: canary_leg(camp, n) for n in ("p6c_can_b0", "p6c_can_bmid")}}


def analyse_c(camp: Path, a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not any((camp / n).is_dir() for c in C_CELLS.values() for n in c[:2]):
        return None
    got = cells_of(camp, C_CELLS, gated(camp, "chain_p6_c_done.json"))
    legs, C = got["legs"], got["cells"]
    ref = load(P0DEF)
    refx = {"dir": "P0 v1_rr_def_a (out of box, committed)", "_by_video": ref["by_video"]} if ref else None
    pairs = [x for x in (ident(legs["p6c_p5t16_1"], refx), ident(legs["p6c_p5t16_2"], refx)) if x]
    gate = (bool(pairs) and all(p["identical"] and p["videos_eq_n"] for p in pairs)) if pairs else None
    rd: Dict[str, Any] = {}
    aC = a["cells"]
    for key, k2 in (("round_1", "round_1"), ("round_2", "round_2"), ("pooled", "mean")):
        f16, f4 = C["p5_t16"]["F_s"].get(k2), aC["p5_k16"]["F_s"].get(k2)
        s16, l16 = C["p5_t16"]["frames_per_s"].get(k2), C["li_t16"]["frames_per_s"].get(k2)
        rd[key] = {"F_t16_over_F_t4": (f16 / f4) if (f16 and f4) else None,
                   "faster_by_at_least_5pct": (f16 / f4 <= T16_BAR) if (f16 and f4) else None,
                   "fps_p5_t16_over_li_t16": (s16 / l16) if (s16 and l16) else None}
    if rd["pooled"]["F_t16_over_F_t4"] is not None:
        rd["verdict_forward"] = ("T=16 IS faster by at least 5%" if rd["pooled"]["faster_by_at_least_5pct"] else "T=16 is NOT faster by at least 5%") + " (pooled)"
    strip(legs)
    return {"legs": legs, "cells": C, "correctness": {"pairs": pairs, "gate_pass": gate,
            "rule": "P5 at T=16 identical to the committed out-of-box output (P0 V1 v1_rr_def_a) on 16/16 videos"},
            "readings": rd, "not_interleaved_note": "P6-A's T=4 legs and P6-C's T=16 legs are in different stages of the session (not ABAB); the canary per round is reported beside",
            "canary": {n: canary_leg(camp, n) for n in ("p6c_can_c1", "p6c_can_c2")}}


def drift(camp: Path, a: Dict[str, Any]) -> Dict[str, Any]:
    """preregistration_addendum_1.json: P5's rule on P6-A's rounds; the other canaries beside, in time order."""
    order = ("p6c_can_a1", "p6c_can_a2", "p6c_can_b0", "p6c_can_bmid", "p6c_can_c1", "p6c_can_c2")
    can = {n: (canary_leg(camp, n) or {}).get("F_s") for n in order}
    c1, c2 = can["p6c_can_a1"], can["p6c_can_a2"]
    cells = {c: v["F_s"]["round_2"] / v["F_s"]["round_1"] - 1 for c, v in a["cells"].items() if v["F_s"]["round_1"] and v["F_s"]["round_2"]}
    med = statistics.median(cells.values()) if cells else None
    out = {"canary_F_s_in_time_order": can, "canary_change_a2_over_a1": (c2 / c1 - 1) if (c1 and c2) else None,
           "p6a_cells_F_change_round2_over_round1": cells, "p6a_cells_median_change": med, "floor": 0.0082,
           "canary_vs_first": {n: (v / c1 - 1) if (v and c1) else None for n, v in can.items()}}
    ch = out["canary_change_a2_over_a1"]
    if ch is None or med is None:
        out["reading"] = "NOT EVALUABLE"
    else:
        moved = abs(ch) > 0.0082
        out.update({"canary_moved": moved, "moved_with_the_cells": moved and med != 0 and (ch > 0) == (med > 0),
                    "reading": ("the canary MOVED WITH the cells" if (moved and med != 0 and (ch > 0) == (med > 0)) else
                                "the canary moved AGAINST the cells" if moved else "the canary did NOT move (within the 0.82% floor)")})
    return out


def main() -> int:
    camp = Path(sys.argv[1])
    a = analyse_a(camp)
    out = {"label": "P6 analysis (preregistration.json)", "P6_A": a, "P6_B": analyse_b(camp), "P6_C": analyse_c(camp, a), "drift": drift(camp, a)}
    (camp / "analysis_p6.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p6.json: A correctness {a['correctness']['gate_pass']}; Q1 {a['readings']['Q1'].get('verdict')}; Q2 {a['readings']['Q2'].get('verdict')}; "
          f"B {'present' if out['P6_B'] else 'absent'}; C {'present' if out['P6_C'] else 'absent'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
