#!/usr/bin/env python3
"""P7-A (laptop, committed exports only): where do the two frames sit? For IN1002.avi frame 58 and TS3010a.avi frame 56,
the prototype's P6-B output (parity_p6 p6b_rr_b06 / p6b_rr_b10, the LAST measured ok row per video) against the banked
stock output (parity_p1 v1full_rr_t4). preregistration.json P7_A states the definitions and the reading; nothing here is
tuned to the data.

    p7_frames.py <p7_campaign_dir>  -> p7a_frames.json

WHAT THE COMMITTED RECORDS HOLD: per frame, frame_scores (the detections' scores in the node's order) and
frame_label_multisets (the labels SORTED, so not paired with scores); per video, chunk_sha256 per chunk. They hold NO box.
So: detections are paired by RANK (each frame's scores sorted descending); a DIFFERING DETECTION is a rank pair whose scores
differ, or a detection with no partner (the counts differ); its label is recoverable only for an unpaired detection whose
frame's label-multiset difference names exactly that many labels; its box is not recorded.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

RES = Path(__file__).resolve().parents[2] / "working" / "results"
P6 = RES / "parity_p6_20260925T175225Z"
P1D = RES / "parity_p1_20260923T184000Z" / "v1full_rr_t4"
FRAMES = {"IN1002.avi": (58, "p6b_rr_b06"), "TS3010a.avi": (56, "p6b_rr_b10")}
THR, BAND, MAX_SCORE, MAX_BOX = 0.3, 0.001, 1e-5, 1e-3


def last_rows(d: Path) -> Dict[str, Dict[str, Any]]:
    out = {}
    for f in sorted(d.glob("records_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("role") == "measured" and "error" not in r:
                    out[r["video"]] = r
    return out


def session(d: Path) -> Dict[str, Any]:
    def mhz(f):
        v = [float(x) for x in re.findall(r"cpu MHz\s*:\s*([0-9.]+)", f.read_text())] if f.exists() else []
        return round(sum(v) / len(v), 1) if v else None
    txt = " ".join(p.read_text(errors="replace") for p in d.glob("*.txt"))
    mc = re.findall(r"microcode\s*:\s*(\S+)", txt)
    return {"leg": str(d.relative_to(RES)), "cpu_model": (d / "cpu_model.txt").read_text().strip() if (d / "cpu_model.txt").exists() else None,
            "microcode": sorted(set(mc)) or "not recorded (no leg file carries /proc/cpuinfo's microcode line)",
            "mhz_mean_open": mhz(d / "mhz_open.txt"), "mhz_mean_close": mhz(d / "mhz_close.txt"),
            "boot_id": (d / "boot_id.txt").read_text().strip()[:8] if (d / "boot_id.txt").exists() else None}


def frame_diff(a_scores: List[float], b_scores: List[float], a_lab: List[str], b_lab: List[str]) -> Dict[str, Any]:
    a, b = sorted(a_scores, reverse=True), sorted(b_scores, reverse=True)
    extra = Counter(b_lab) - Counter(a_lab)
    missing = Counter(a_lab) - Counter(b_lab)
    dets = []
    for k in range(max(len(a), len(b))):
        sa, sb = (a[k] if k < len(a) else None), (b[k] if k < len(b) else None)
        if sa == sb:
            continue
        unpaired = sa is None or sb is None
        lab = "not recoverable (the records keep labels sorted, unpaired with scores)"
        if unpaired:
            side = extra if sa is None else missing
            n_unp = abs(len(a) - len(b))
            if sum(side.values()) == n_unp and len(side) == 1:
                lab = next(iter(side))
        dets.append({"rank": k, "score_banked_stock": sa, "score_prototype": sb, "unpaired": unpaired, "label": lab,
                     "box": "not recorded in any committed export",
                     "distance_from_threshold": {"banked_stock": None if sa is None else abs(sa - THR), "prototype": None if sb is None else abs(sb - THR)},
                     "within_band_in_either_run": any(x is not None and abs(x - THR) <= BAND for x in (sa, sb))})
    return {"n_detections": {"banked_stock": len(a), "prototype": len(b)},
            "label_multiset_difference": {"only_in_prototype": dict(extra), "only_in_banked_stock": dict(missing)},
            "max_rank_paired_score_delta": max((abs(x - y) for x, y in zip(a, b)), default=0.0),
            "differing_detections": dets}


def main() -> int:
    camp = Path(sys.argv[1])
    ref = last_rows(P1D)
    out: Dict[str, Any] = {"frames": {}, "other_frames": {}, "sessions": {}}
    c1 = True
    other_max, other_bad = 0.0, []
    for v, (i, blk) in FRAMES.items():
        a, b = ref[v], last_rows(P6 / blk)[v]
        fd = frame_diff(a["frame_scores"][i], b["frame_scores"][i], a["frame_label_multisets"][i], b["frame_label_multisets"][i])
        fd["chunks"] = {"n": [a["n_chunks"], b["n_chunks"]],
                        "differing_chunk_indexes": [k for k, (x, y) in enumerate(zip(a["chunk_sha256"], b["chunk_sha256"])) if x != y],
                        "note": "every other chunk's text (so every score and box inside it) is byte-identical; a frame sharing a differing chunk with the named frame cannot be excluded"}
        fd["prototype_leg"], fd["frame"] = f"parity_p6_20260925T175225Z/{blk}", i
        out["frames"][f"{v}#{i}"] = fd
        c1 = c1 and bool(fd["differing_detections"]) and all(x["within_band_in_either_run"] for x in fd["differing_detections"])
        n = len(a["frame_scores"])
        vmax, vbad = 0.0, []
        for j in range(n):
            if j == i:
                continue
            sa, sb = sorted(a["frame_scores"][j], reverse=True), sorted(b["frame_scores"][j], reverse=True)
            if len(sa) != len(sb) or a["frame_label_multisets"][j] != b["frame_label_multisets"][j]:
                vbad.append(j)
                continue
            vmax = max([vmax] + [abs(x - y) for x, y in zip(sa, sb)])
        out["other_frames"][v] = {"frames_compared": n - 1, "max_score_delta": vmax, "frames_with_count_or_label_difference": vbad,
                                  "max_box_delta_px": "NOT EVALUABLE — no committed export records boxes"}
        other_max = max(other_max, vmax)
        other_bad += [f"{v}#{j}" for j in vbad]
        out["sessions"][v] = {"banked_stock_P1D": session(P1D), "prototype_P6B": session(P6 / blk)}
    c2 = other_max <= MAX_SCORE and not other_bad
    clauses = {"C1 every differing detection's score, in either run, within +/-0.001 of 0.3": c1,
               "C2 every other frame of both videos: max score delta <= 1e-5 (and the same count and labels)": c2,
               "C3 every other frame of both videos: box delta <= 1e-3 px": None}
    boundary = c1 and c2 and clauses["C3 every other frame of both videos: box delta <= 1e-3 px"] is True
    failed = [k for k, x in clauses.items() if x is False]
    unev = [k for k, x in clauses.items() if x is None]
    out["reading"] = {"clauses": clauses, "failed": failed, "not_evaluable": unev,
                      "reading": "BOUNDARY" if boundary else "NOT BOUNDARY",
                      "why": "every clause holds" if boundary else "; ".join([f"FAILED: {k}" for k in failed] + [f"NOT EVALUABLE from committed exports: {k}" for k in unev])}
    out["august_artifact"] = {
        "claim": "the August ami_full campaign recorded IN1002.avi frame 58 as its single cross_detection_agreement failure, a detection scoring 0.3004 against 0.3",
        "committed_mention": "working/video/WS1_Phase2_Video_Benchmark_DEFINITIVE.md section 5.1 (commit 21990572, a byte-for-byte copy of a received report)",
        "committed_artifact": None,
        "search": "the 26 Aug result directories committed (working/video/results/apples_20260826T041510Z, apples_20260826T052915Z) hold the RocketRide exports and collector summaries only — no LlamaIndex records and no cross_detection_agreement output; no committed file other than the report carries the 0.3004 figure for IN1002",
        "used": False, "status": "NOT COMMITTED — the figure is not used"}
    out["s5b_artifact"] = {"claim": "S5-B's one label-set change: a score moving 0.3011 -> 0.3008 across the band edge (EN2001a.avi frame 97, tv)",
                           "committed_artifact": "working/results/batchsize_s5_20260921T205917Z/analysis_output_shift.json s5b_tier2_label_set_failures_explained.2.label_set_failures[0].detections_crossing_the_band_edge[0] (score_B1, score_B2)",
                           "used": True}
    (camp / "p7a_frames.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"P7-A: {out['reading']['reading']} — {out['reading']['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
