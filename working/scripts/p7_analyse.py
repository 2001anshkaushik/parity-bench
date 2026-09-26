#!/usr/bin/env python3
"""P7 analysis (preregistration.json), from raw leg files only; imported by p7_gates.py (G_tier2 decides from exactly this
code) and by the report.

    p7_analyse.py <campaign_dir>  -> analysis_p7.json   (sections P7_B_tier1, P7_B_tier2, P7_C, canaries)

P7-B TIER 1: IN1002.avi frame 58, TS3010a.avi frame 56 and the control IN1009.avi, K=3, T=4; stock (rr:patched-video) and
the prototype (rr:p5-infer), ABAB, two runs each. A run's FRAME is its record's frame_scores[i] and
frame_label_multisets[i] and, when the run captured detections (--keep-detections), its detection list (label, score and
box x1,y1,x2,y2, in the node's order). Two runs AGREE on a frame iff the scores and label multisets are equal and, where
BOTH captured, the detection lists are equal. A VIDEO is identical in two runs iff chunk_sha256 AND frame_scores are equal
(the P6 identity) and, where both captured, every frame's detection list is equal.
Readings, in this order: UNREADABLE (the control video not identical across all four runs) -> STOCK VARIES (the two stock
runs disagree on either named frame) -> PROTOTYPE SHIFTS (stock stable on both frames AND stock identical to the banked
P1-D output on both videos; the prototype stable on both frames and disagreeing with stock on BOTH frames) -> PROTOTYPE
SHIFTS ON ONE FRAME (the same, disagreeing on exactly one) -> CONDITION-DEPENDENT (all four runs agree on both frames)
-> UNCLASSIFIED (the pattern named). Deltas against S5-B's Tier 2 tolerances use batchsize_analyse_s5b.tier2_frame
unchanged (labels outside +/-0.001 of 0.3, score <= 1e-5, box <= 1e-3 px).
P7-B TIER 2 (only if Tier 1 reads CONDITION-DEPENDENT): the P6-B blocks 06 (IN1002, and the control IN1009) and 10
(TS3010a), both cells, K=16, one run each. Per named video: STOCK VARIES (the Tier 2 stock run disagrees on the frame with
either Tier 1 stock run or with P1-D) -> PROTOTYPE SHIFTS (it agrees; the Tier 2 prototype run disagrees with it) -> NOT
REPRODUCED (all agree). UNREADABLE if the control is not identical across the Tier 1 runs and both block-06 runs.
P7-C: P6-C's cells, round 2; P6-C's pooled reading exactly as P6's preregistration states it, over P6-C round 1 and this
round (CROSS-SESSION: the two rounds are in different box sessions).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import load  # noqa: E402
from p5_analyse_a import canary_leg, leg, spread0  # noqa: E402
from batchsize_analyse_s5b import tier2_frame, THR, BAND, MAX_SCORE, MAX_BOX  # noqa: E402

RES = Path(__file__).resolve().parents[2] / "working" / "results"
P6C = RES / "parity_p6_20260925T175225Z"
P1D = RES / "parity_p1_20260923T184000Z" / "v1full_rr_t4"
P0DEF = RES / "parity_p0_20260923T083031Z" / "v1_rr_def_a"
FRAMES = {"IN1002.avi": 58, "TS3010a.avi": 56}
CONTROL = "IN1009.avi"
BLOCK_OF = {"IN1002.avi": "b06", "TS3010a.avi": "b10", CONTROL: "b06"}
P6B_BLOCK = {"b06": "p6b_rr_b06", "b10": "p6b_rr_b10"}
T1 = {"stock": ("p7b_stock_1", "p7b_stock_2"), "p5": ("p7b_p5_1", "p7b_p5_2")}
T2 = {"b06": ("p7t2_stock_b06", "p7t2_p5_b06"), "b10": ("p7t2_stock_b10", "p7t2_p5_b10")}
T16_BAR = 0.95


def run_of(d: Path) -> Optional[Dict[str, Any]]:
    """Records (LAST measured ok row per video, via P0's load) and, if present, the capture (LAST measured row per video)."""
    g = load(d) if d.is_dir() else None
    if not g:
        return None
    cap: Dict[str, List[list]] = {}
    for f in sorted(d.glob("detections_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("role") == "measured":
                    cap[r["video"]] = r["frames"]
    return {"dir": d.name, "by_video": g["by_video"], "cap": cap or None}


def frame(run: Dict[str, Any], video: str, i: int) -> Optional[Dict[str, Any]]:
    v = run["by_video"].get(video)
    if not v or v.get("frame_scores") is None or i >= len(v["frame_scores"]):
        return None
    dets = (run.get("cap") or {}).get(video)
    return {"scores": v["frame_scores"][i], "labels": (v.get("labels") or [None] * (i + 1))[i],
            "dets": dets[i] if dets is not None and i < len(dets) else None}


def _dkey(d):
    b = d.get("box") or {}
    return (str(d.get("label")), d.get("score"), b.get("x1"), b.get("y1"), b.get("x2"), b.get("y2"))


def agree(x: Optional[Dict[str, Any]], y: Optional[Dict[str, Any]]) -> Optional[bool]:
    if x is None or y is None:
        return None
    if x["scores"] != y["scores"] or x["labels"] != y["labels"]:
        return False
    if x["dets"] is not None and y["dets"] is not None:
        return [_dkey(d) for d in x["dets"]] == [_dkey(d) for d in y["dets"]]
    return True


def video_identical(a: Dict[str, Any], b: Dict[str, Any], video: str) -> Optional[bool]:
    va, vb = a["by_video"].get(video), b["by_video"].get(video)
    if not va or not vb:
        return None
    if va["chunk_sha256"] != vb["chunk_sha256"] or va["frame_scores"] != vb["frame_scores"]:
        return False
    ca, cb = (a.get("cap") or {}).get(video), (b.get("cap") or {}).get(video)
    if ca is not None and cb is not None:
        return [[_dkey(d) for d in f] for f in ca] == [[_dkey(d) for d in f] for f in cb]
    return True


def deltas(x: Optional[Dict[str, Any]], y: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Descriptive, for a disagreeing pair: rank-paired score deltas from the records, and S5-B's Tier 2 test on the captures."""
    if x is None or y is None:
        return {"evaluable": False}
    a, b = sorted(x["scores"], reverse=True), sorted(y["scores"], reverse=True)
    out: Dict[str, Any] = {"n_detections": [len(a), len(b)], "labels_equal": x["labels"] == y["labels"],
                           "max_rank_paired_score_delta": max((abs(p - q) for p, q in zip(a, b)), default=0.0),
                           "unpaired_scores": (a[len(b):] or b[len(a):]),
                           "scores_within_band_of_threshold": sorted({round(s, 6) for s in x["scores"] + y["scores"] if abs(s - THR) <= BAND})}
    if x["dets"] is not None and y["dets"] is not None:
        try:
            t = tier2_frame(x["dets"], y["dets"])
        except (ValueError, KeyError) as e:          # min() over an empty pool: a label present on one side only, inside no band
            t = {"ok": False, "why": f"unpairable ({e.__class__.__name__})"}
        out["s5b_tier2"] = {**t, "tolerances": {"band": BAND, "score": MAX_SCORE, "box_px": MAX_BOX}}
    return out


def tier1(camp: Path, legs: Optional[Dict[str, tuple]] = None, frames: Optional[Dict[str, int]] = None,
          control: Optional[str] = None, ref: Optional[Path] = None, banked_p5: Optional[Dict[str, Path]] = None) -> Dict[str, Any]:
    legs, frames, control, ref = legs or T1, frames or FRAMES, control or CONTROL, ref or P1D
    runs = {k: [run_of(camp / n) for n in v] for k, v in legs.items()}
    missing = [n for k, v in legs.items() for n, r in zip(v, runs[k]) if r is None]
    if missing:
        return {"reading": "NOT EVALUABLE", "missing": missing}
    R = run_of(ref)
    s1, s2 = runs["stock"]; p1, p2 = runs["p5"]
    four = [s1, s2, p1, p2]
    ctl = {f"{a['dir']} vs {b['dir']}": video_identical(a, b, control) for i, a in enumerate(four) for b in four[i + 1:]}
    per: Dict[str, Any] = {}
    for v, i in frames.items():
        F = {r["dir"]: frame(r, v, i) for r in four}
        fs = [F[r["dir"]] for r in four]
        per[f"{v}#{i}"] = {
            "stock_stable": agree(fs[0], fs[1]), "p5_stable": agree(fs[2], fs[3]),
            "p5_vs_stock_round": [agree(fs[2], fs[0]), agree(fs[3], fs[1])],
            "all_four_agree": all(agree(fs[a], fs[b]) for a in range(4) for b in range(a + 1, 4)),
            "stock_video_identical_to_ref": [video_identical(s1, R, v), video_identical(s2, R, v)] if R else None,
            "vs_banked": {"P1-D stock": [agree(f, frame(R, v, i)) if R else None for f in fs]},
            "deltas_p5_vs_stock": deltas(fs[2], fs[0]), "deltas_stock_vs_stock": deltas(fs[0], fs[1]),
            "frames_captured": [f is not None and f["dets"] is not None for f in fs],
            "n_detections": [len(f["scores"]) if f else None for f in fs]}
        bp = (banked_p5 or {}).get(v)
        if bp is not None:
            B = run_of(bp)
            per[f"{v}#{i}"]["vs_banked"]["P6-B prototype"] = [agree(f, frame(B, v, i)) if B else None for f in fs]
    # every OTHER frame of the named videos and the control: where the prototype disagrees with stock (descriptive)
    other: Dict[str, Any] = {}
    for v in list(frames) + [control]:
        n = len((s1["by_video"].get(v) or {}).get("frame_scores") or [])
        dis = [j for j in range(n) if not (v in frames and j == frames[v]) and not agree(frame(p1, v, j), frame(s1, v, j))]
        other[v] = {"frames": n, "other_frames_where_p5_round1_disagrees_with_stock_round1": dis}
    cf = list(per.values())
    stock_stable = all(x["stock_stable"] for x in cf)
    p5_stable = all(x["p5_stable"] for x in cf)
    ref_ok = all(all(x["stock_video_identical_to_ref"] or [False]) for x in cf)
    shifted = [k for k, x in per.items() if x["p5_vs_stock_round"][0] is False]
    if not all(ctl.values()):
        reading = "UNREADABLE"
    elif not stock_stable:
        reading = "STOCK VARIES"
    elif ref_ok and p5_stable and len(shifted) == len(cf):
        reading = "PROTOTYPE SHIFTS"
    elif ref_ok and p5_stable and len(shifted) == 1:
        reading = "PROTOTYPE SHIFTS ON ONE FRAME"
    elif all(x["all_four_agree"] for x in cf):
        reading = "CONDITION-DEPENDENT"
    else:
        reading = "UNCLASSIFIED"
    return {"reading": reading, "legs": {k: list(v) for k, v in legs.items()}, "frames": frames, "control": control,
            "reference": str(ref.relative_to(RES)) if str(ref).startswith(str(RES)) else str(ref),
            "control_identical": ctl, "per_frame": per, "other_frames": other,
            "pattern": {"stock_stable_both_frames": stock_stable, "p5_stable_both_frames": p5_stable,
                        "stock_identical_to_reference_both_videos": ref_ok, "frames_where_p5_disagrees_with_stock": shifted}}


def tier2(camp: Path) -> Optional[Dict[str, Any]]:
    if not any((camp / n).is_dir() for v in T2.values() for n in v):
        return None
    s = {b: (run_of(camp / a), run_of(camp / p)) for b, (a, p) in T2.items()}
    t1 = {k: [run_of(camp / n) for n in v] for k, v in T1.items()}
    R = run_of(P1D)
    ctl_runs = [x for x in t1["stock"] + t1["p5"] + list(s["b06"]) if x]
    ctl = all(video_identical(ctl_runs[0], x, CONTROL) for x in ctl_runs[1:]) if len(ctl_runs) == 6 else None
    per: Dict[str, Any] = {}
    for v, i in FRAMES.items():
        st, p5 = s[BLOCK_OF[v]]
        if st is None or p5 is None:
            per[v] = {"reading": "NOT RUN / absent"}
            continue
        fst, fp5 = frame(st, v, i), frame(p5, v, i)
        vs_t1 = [agree(fst, frame(x, v, i)) for x in t1["stock"] if x]
        vs_ref = agree(fst, frame(R, v, i)) if R else None
        B = run_of(P6C / P6B_BLOCK[BLOCK_OF[v]])
        rd = ("STOCK VARIES" if (False in vs_t1 or vs_ref is False) else
              "PROTOTYPE SHIFTS" if agree(fp5, fst) is False else "NOT REPRODUCED")
        per[v] = {"frame": i, "reading": rd, "stock_t2_vs_stock_t1": vs_t1, "stock_t2_vs_P1D": vs_ref,
                  "p5_t2_vs_stock_t2": agree(fp5, fst), "p5_t2_vs_banked_P6B": agree(fp5, frame(B, v, i)) if B else None,
                  "deltas_p5_vs_stock": deltas(fp5, fst)}
    rds = {x.get("reading") for x in per.values()}
    overall = ("UNREADABLE" if ctl is False else next(iter(rds)) if len(rds) == 1 else
               "MIXED: " + "; ".join(f"{v} {x.get('reading')}" for v, x in per.items()))
    return {"reading": overall, "control_identical_across_tier1_and_block06": ctl, "per_video": per,
            "legs": {b: list(v) for b, v in T2.items()}}


def p7c(camp: Path) -> Optional[Dict[str, Any]]:
    if not any((camp / n).is_dir() for n in ("p7c_p5t16_2", "p7c_lit16_2")):
        return None
    L = {"p6c_p5t16_1": leg(P6C, "p6c_p5t16_1", "p5"), "p7c_p5t16_2": leg(camp, "p7c_p5t16_2", "p5"),
         "p6c_lit16_1": leg(P6C, "p6c_lit16_1", "li"), "p7c_lit16_2": leg(camp, "p7c_lit16_2", "li"),
         "p6a_p5k16_1": leg(P6C, "p6a_p5k16_1", "p5"), "p6a_p5k16_2": leg(P6C, "p6a_p5k16_2", "p5")}

    def m(a, b, k):
        return statistics.mean([L[a][k], L[b][k]]) if L[a] and L[b] else None
    rd: Dict[str, Any] = {}
    for key, (t16, t4, l16) in (("round_1", ("p6c_p5t16_1", "p6a_p5k16_1", "p6c_lit16_1")), ("round_2", ("p7c_p5t16_2", "p6a_p5k16_2", "p7c_lit16_2"))):
        f16, f4 = (L[t16] or {}).get("F_s"), (L[t4] or {}).get("F_s")
        s16, l = (L[t16] or {}).get("frames_per_s"), (L[l16] or {}).get("frames_per_s")
        rd[key] = {"F_t16_over_F_t4": f16 / f4 if f16 and f4 else None, "faster_by_at_least_5pct": (f16 / f4 <= T16_BAR) if f16 and f4 else None,
                   "fps_p5_t16_over_li_t16": s16 / l if s16 and l else None, "legs": [t16, t4, l16]}
    F16, F4 = m("p6c_p5t16_1", "p7c_p5t16_2", "F_s"), m("p6a_p5k16_1", "p6a_p5k16_2", "F_s")
    S16, LI16 = m("p6c_p5t16_1", "p7c_p5t16_2", "frames_per_s"), m("p6c_lit16_1", "p7c_lit16_2", "frames_per_s")
    rd["pooled"] = {"F_t16_mean": F16, "F_t4_mean": F4, "F_t16_over_F_t4": F16 / F4 if F16 and F4 else None,
                    "faster_by_at_least_5pct": (F16 / F4 <= T16_BAR) if F16 and F4 else None,
                    "fps_p5_t16_mean": S16, "fps_li_t16_mean": LI16, "fps_p5_t16_over_li_t16": S16 / LI16 if S16 and LI16 else None,
                    "spread_F_t16": spread0(L["p6c_p5t16_1"]["F_s"], L["p7c_p5t16_2"]["F_s"]) if L["p6c_p5t16_1"] and L["p7c_p5t16_2"] else None}
    if rd["pooled"]["F_t16_over_F_t4"] is not None:
        rd["verdict_forward"] = ("T=16 IS faster by at least 5%" if rd["pooled"]["faster_by_at_least_5pct"] else "T=16 is NOT faster by at least 5%") + " (pooled)"
    corr = None
    if L["p7c_p5t16_2"]:
        from p0_analyse_video import identity  # noqa: E402
        a, b = load(camp / "p7c_p5t16_2"), load(P0DEF)
        if a and b:
            corr = identity({"dir": "p7c_p5t16_2", "by_video": a["by_video"]}, {"dir": "P0 v1_rr_def_a", "by_video": b["by_video"]})
            corr["pass"] = corr["identical"] and corr["videos_compared"] == 16
    strip = {k: ({kk: vv for kk, vv in v.items() if kk != "_by_video"} if v else None) for k, v in L.items()}
    return {"legs": strip, "readings": rd, "correctness_C2": corr,
            "cross_session": "P6-C round 1 and P6-A (the T=4 reference) are in P6's box session; P7-C round 2 is in P7's. P6's pooled rule is applied as written; the canaries of both sessions are reported beside and adjust nothing."}


def canaries(camp: Path) -> Dict[str, Any]:
    out = {n: canary_leg(camp, n) for n in sorted(p.name for p in camp.glob("p7*_can_*") if p.is_dir())}
    out.update({f"P6 {n}": canary_leg(P6C, n) for n in ("p6c_can_a1", "p6c_can_a2", "p6c_can_c1")})
    return {k: ({"F_s": v["F_s"], "frames": v["frames"]} if v else None) for k, v in out.items()}


def main() -> int:
    camp = Path(sys.argv[1])
    t1 = tier1(camp, banked_p5={v: P6C / P6B_BLOCK[BLOCK_OF[v]] for v in FRAMES})
    out = {"label": "P7 analysis (preregistration.json)", "P7_B_tier1": t1, "P7_B_tier2": tier2(camp), "P7_C": p7c(camp),
           "canaries": canaries(camp)}
    (camp / "analysis_p7.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p7.json: tier 1 {t1['reading']}; tier 2 {(out['P7_B_tier2'] or {}).get('reading', 'absent')}; "
          f"P7-C {'present' if out['P7_C'] else 'absent'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
