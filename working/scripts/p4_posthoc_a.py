#!/usr/bin/env python3
"""P4-A POST-HOC observations (NOT pre-registered; written after the data; reported beside the readings, never replacing
them), computed from analysis_p4a.json (itself computed from the raw legs).

    p4_posthoc_a.py <campaign_dir>  -> analysis_p4a_posthoc.json

1. Drift between the ABAB rounds: per cell, F(run 2) / F(run 1) - 1 and frames/s likewise.
2. The pre-registered quantities per ROUND (run 1 cells only, run 2 cells only): D_RR / D_LI - 1 and the closure c.
3. ACTIVE's cost: CPU-s per frame and service cores against RR K=16 (cell means).
4. Cores busy in the forward, K=1 against K=16, per arm (cell means).
5. The within-session K=16 gap: LI frames/s / RR frames/s - 1 (cell means).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

camp = Path(sys.argv[1])
A = json.loads((camp / "analysis_p4a.json").read_text())
L, C = A["legs"], A["cells"]
CELLS = {"rr_k1": ("p4a_rr1_1", "p4a_rr1_2"), "rr_k16": ("p4a_rr16_1", "p4a_rr16_2"), "li_k1": ("p4a_li1_1", "p4a_li1_2"),
         "li_k16": ("p4a_li16_1", "p4a_li16_2"), "rr_k16_active": ("p4a_act_1", "p4a_act_2")}
drift = {c: {"F_run2_over_run1_minus_1": L[b]["F_s"] / L[a]["F_s"] - 1,
             "fps_run2_over_run1_minus_1": L[b]["frames_per_s"] / L[a]["frames_per_s"] - 1} for c, (a, b) in CELLS.items()}
per_round = {}
for r in (0, 1):
    F = {c: L[v[r]]["F_s"] for c, v in CELLS.items()}
    d_rr, d_li = F["rr_k16"] / F["rr_k1"], F["li_k16"] / F["li_k1"]
    per_round[f"round_{r + 1}"] = {"D_RR": d_rr, "D_LI": d_li, "D_RR_over_D_LI_minus_1": d_rr / d_li - 1,
                                   "closure": (F["rr_k16"] - F["rr_k16_active"]) / (F["rr_k16"] - F["rr_k1"]),
                                   "active_F_over_rr16_F_minus_1": F["rr_k16_active"] / F["rr_k16"] - 1}
m = lambda c, k: C[c][k]["mean"]  # noqa: E731
out = {"label": "P4-A POST-HOC observations (not pre-registered; beside the readings, never replacing them)",
       "round_drift": drift,
       "every_cell_slower_in_round_2": all(v["F_run2_over_run1_minus_1"] > 0 for v in drift.values()),
       "per_round_readings": per_round,
       "active_cost": {"cpu_s_per_frame_active_over_rr16_minus_1": m("rr_k16_active", "cpu_s_per_frame") / m("rr_k16", "cpu_s_per_frame") - 1,
                       "service_cores_active": m("rr_k16_active", "engine_cores"), "service_cores_rr16": m("rr_k16", "engine_cores")},
       "cores_in_forward": {"rr_k1": m("rr_k1", "cores_in_forward"), "rr_k16": m("rr_k16", "cores_in_forward"),
                            "li_k1": m("li_k1", "cores_in_forward"), "li_k16": m("li_k16", "cores_in_forward"),
                            "rr_k16_active": m("rr_k16_active", "cores_in_forward")},
       "k16_gap_li_over_rr_fps_minus_1": m("li_k16", "frames_per_s") / m("rr_k16", "frames_per_s") - 1,
       "k1_lock_duty": {"rr_k1": m("rr_k1", "lock_duty"), "li_k1": m("li_k1", "lock_duty")}}
(camp / "analysis_p4a_posthoc.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
