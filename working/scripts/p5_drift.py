#!/usr/bin/env python3
"""P5-C (2) DRIFT NOTE (preregistration.json P5_C_laptop (2)): the canary per round beside P4's round-to-round drift, and
whether the canary moved with the P5-A cells. The rule was fixed before the data: the canary MOVED iff
|F(canary round 2) / F(canary round 1) - 1| > 0.82% (the RR floor); it moved WITH the cells iff it moved in the same
direction as the median of the P5-A cells' round-2 / round-1 forward changes. No figure is adjusted.

    p5_drift.py <p5_campaign_dir>  -> analysis_p5_drift.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P4 = ROOT / "working" / "results" / "parity_p4_20260925T092942Z"
FLOOR = 0.0082


def main() -> int:
    camp = Path(sys.argv[1])
    a = json.loads((camp / "analysis_p5a.json").read_text())
    p4 = json.loads((P4 / "analysis_p4a_posthoc.json").read_text())
    can = a.get("canary") or {}
    c1, c2 = (can.get("p5c_can_1") or {}).get("F_s"), (can.get("p5c_can_2") or {}).get("F_s")
    cells = {c: (v["F_s"]["round_2"] / v["F_s"]["round_1"] - 1) for c, v in a["cells"].items()
             if v["F_s"]["round_1"] and v["F_s"]["round_2"]}
    med = statistics.median(cells.values()) if cells else None
    out = {"label": "P5-C (2) drift note (rule fixed in the pre-registration; no figure adjusted)",
           "canary_F_s": {"round_1": c1, "round_2": c2}, "canary_change": (c2 / c1 - 1) if (c1 and c2) else None,
           "p5_cells_F_change_round2_over_round1": cells, "p5_cells_median_change": med,
           "p4_round_drift_F_change": {k: v["F_run2_over_run1_minus_1"] for k, v in p4["round_drift"].items()},
           "p4_every_cell_slower_in_round_2": p4["every_cell_slower_in_round_2"], "floor": FLOOR}
    ch = out["canary_change"]
    if ch is None or med is None:
        out["reading"] = "NOT EVALUABLE (a canary round or a cell is missing)"
    else:
        moved = abs(ch) > FLOOR
        with_cells = moved and ((ch > 0) == (med > 0)) and med != 0
        out.update({"canary_moved": moved, "moved_with_the_cells": with_cells,
                    "reading": ("the canary MOVED WITH the cells" if with_cells else
                                "the canary moved AGAINST the cells" if moved else
                                "the canary did NOT move (within the 0.82% floor)")})
    (camp / "analysis_p5_drift.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote analysis_p5_drift.json: {out['reading']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
