#!/usr/bin/env python3
"""The output shift of every Stage 5 knob, by ONE comparator, from the driver's own records.

    batchsize_output_shift.py <s5_dir> [--out report.json]

S5-B stopped on its pre-registered Tier 2 criterion (1e-5 score, 1e-3 px). To read that stop as a
measurement and not a verdict on batching alone, this puts it beside the shift another knob already
produces: S5-A's intra-op width changes scores with every label kept. Both are computed here by
batchsize_analyse_threads.frame_compare on the records (per-frame label multisets and scores; scores
paired in sorted order, a lower bound). S5-A is measured against the out-of-the-box default cell; S5-B
against its own patched B=1, which is chunk-identical to stock. The tap-based Tier 2 figures S5-B
was judged on are carried beside, from analysis_s5b.json, because the taps also pair boxes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batchsize_analyse_threads as bat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT = ROOT / "working/results/batchsize_smoke_20260920T113000Z/video_n16/rr_k16"
DEFAULT_REP = ROOT / "working/results/batchsize_s3b_20260920T203139Z/video/rep/rr_k16_rep"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    s5 = Path(sys.argv[1])
    base = bat.recs(DEFAULT)
    b1 = bat.recs(s5 / "s5b" / "rr_k16_B1")
    rep: Dict[str, Any] = {
        "comparator": "batchsize_analyse_threads.frame_compare — label multisets and sorted-paired scores per frame (lower bound)",
        "null_control_default_vs_its_replicate": bat.frame_compare(base, bat.recs(DEFAULT_REP)),
        "null_control_patched_B1_vs_default": bat.frame_compare(base, b1),
        "s5a_thread_width_vs_default": {T: bat.frame_compare(base, bat.recs(s5 / "s5a" / f"rr_k16_T{T}")) for T in (1, 2, 4, 8, 16)},
        "s5b_batch_vs_patched_B1": {B: bat.frame_compare(b1, bat.recs(s5 / "s5b" / f"rr_k16_B{B}")) for B in (2, 4, 8)},
    }
    s5b = json.loads((s5 / "analysis_s5b.json").read_text())
    rep["s5b_tier2_from_taps"] = {B: {k: r.get(k) for k in ("tier2_failing_frames", "frames_compared", "max_score_delta",
                                                         "max_box_delta_px", "tier")}
                                  for B, r in (s5b.get("correctness_by_b") or {}).items()}
    # What the taps' "label multiset or count differs outside the band" failures ARE, frame by frame
    # (2026-09-22): the rule filters EACH side by its own scores, so a detection whose score crosses the
    # band's edge (outside on one side, inside on the other) reads as a count change although every
    # label is still there. Reported so the stop is read as what was measured, not as a label change.
    import batchsize_analyse_s5b as s5bmod  # noqa: E402
    t1 = s5bmod.taps(s5 / "s5b" / "rr_k16_B1")
    measured = set(b1)
    detail: Dict[str, Any] = {}
    for B in (2, 4, 8):
        tb = s5bmod.taps(s5 / "s5b" / f"rr_k16_B{B}")
        rows, fail_measured, fail_warm = [], 0, 0
        for k in sorted(set(t1) & set(tb)):
            r = s5bmod.tier2_frame(t1[k], tb[k])
            if not r["ok"]:
                if k[0] in measured:
                    fail_measured += 1
                else:
                    fail_warm += 1
            if "why" in r:
                la, lb = sorted(d["label"] for d in t1[k]), sorted(d["label"] for d in tb[k])
                near = lambda s: abs(s - s5bmod.THR) <= s5bmod.BAND  # noqa: E731
                crossed = [{"label": x["label"], "score_B1": round(x["score"], 4), f"score_B{B}": round(y["score"], 4)}
                           for x, y in zip(sorted(t1[k], key=lambda d: (d["label"], d["score"])),
                                           sorted(tb[k], key=lambda d: (d["label"], d["score"])))
                           if x["label"] == y["label"] and near(x["score"]) != near(y["score"])]
                rows.append({"video": k[0], "frame": k[1], "measured_video": k[0] in measured,
                             "labels_B1": la, f"labels_B{B}": lb, "any_label_or_count_changed": la != lb,
                             "detections_crossing_the_band_edge": crossed})
        detail[str(B)] = {"tier2_failing_frames_on_measured_videos": fail_measured,
                          "tier2_failing_frames_on_warm_up_videos": fail_warm,
                          "label_set_failures": rows}
    rep["s5b_tier2_label_set_failures_explained"] = detail
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only")
            return 3
        p.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
