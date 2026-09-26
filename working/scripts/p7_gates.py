#!/usr/bin/env python3
"""P7 gates, computed exactly as preregistration.json states them; the chain decides from these exit codes. Every gate has a
positive and a null control run WHOLE on the box before launch (p7_gate_controls.py). P6's gates are reused unchanged
(alone, memstat, d0, cell incl. the out-of-box form, warm, canary, correct); P7 adds:

    p7_gates.py detcap <camp> <leg>
        G_detcap: the leg's detections_*.jsonl exists and, for EVERY measured ok video of the records (the LAST row per
        video), holds a measured capture row (the LAST per video) with as many frames as the record's frame_scores, whose
        per-frame scores equal the record's frame_scores exactly (in order) and whose sorted labels equal
        frame_label_multisets, and every detection carries a box (x1, y1, x2, y2)
    p7_gates.py tier <camp> [<s1> <s2> <p1> <p2> <frames v:i,v:i> <control> <ref_abs>]
        G_tier2: fires iff the Tier 1 reading (p7_analyse.tier1, the same code the report uses) is CONDITION-DEPENDENT.
        The optional arguments exist for the gate controls only; the chain passes none.

Exit 0 = pass / fired, 1 = fail / not fired, 2 = evidence missing / not evaluable. Records go to <camp>/gates/<gate>.json,
create-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p6_gates  # noqa: E402
from p4_gates import record  # noqa: E402


def detcap(camp: Path, leg: str) -> int:
    from p0_analyse_video import load  # noqa: E402
    d = camp / leg
    g = load(d) if d.is_dir() else None
    caps = sorted(d.glob("detections_*.jsonl")) if d.is_dir() else []
    if g is None or not caps:
        record(camp, f"G_detcap_{leg}", {"leg": leg, "records": g is not None, "capture_file": bool(caps), "outcome": "EVIDENCE MISSING"})
        return 2
    cap = {}
    for line in caps[0].read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("role") == "measured":
                cap[r["video"]] = r["frames"]
    bad = {}
    for v, x in g["by_video"].items():
        fr = cap.get(v)
        why = None
        if fr is None:
            why = "no capture row"
        elif len(fr) != len(x["frame_scores"] or []):
            why = f"frames {len(fr)} vs record {len(x['frame_scores'] or [])}"
        else:
            for i, (f, s, lab) in enumerate(zip(fr, x["frame_scores"], x["labels"] or [])):
                if [float(dd.get("score", 0.0)) for dd in f] != s:
                    why = f"frame {i}: scores differ from the record"
                    break
                if sorted(str(dd.get("label")) for dd in f) != lab:
                    why = f"frame {i}: labels differ from the record"
                    break
                if any(not all(k in (dd.get("box") or {}) for k in ("x1", "y1", "x2", "y2")) for dd in f):
                    why = f"frame {i}: a detection without a box"
                    break
        if why:
            bad[v] = why
    ok = bool(g["by_video"]) and not bad
    record(camp, f"G_detcap_{leg}", {"leg": leg, "capture_file": caps[0].name, "videos_in_records": len(g["by_video"]),
                                     "videos_captured": len(cap), "failures": bad,
                                     "rule": "preregistration.json gates.G_detcap", "outcome": "PASS" if ok else "FAIL"})
    return 0 if ok else 1


def tier(camp: Path, a: list) -> int:
    from p7_analyse import tier1  # noqa: E402  (the same code the report uses)
    kw = {}
    if a:
        s1, s2, p1, p2, fr, ctl, ref = a
        kw = {"legs": {"stock": (s1, s2), "p5": (p1, p2)}, "frames": {x.split(":")[0]: int(x.split(":")[1]) for x in fr.split(",")},
              "control": ctl, "ref": Path(ref)}
    t = tier1(camp, **kw)
    rd = t["reading"]
    record(camp, "G_tier2", {"rule": "fires iff the Tier 1 reading is CONDITION-DEPENDENT (preregistration.json P7_B)",
                             "reading": rd, "pattern": t.get("pattern"), "control_identical": t.get("control_identical"),
                             "missing": t.get("missing"), "arguments": a or "the preregistered legs, frames, control and reference",
                             "outcome": "FIRED" if rd == "CONDITION-DEPENDENT" else ("NOT EVALUABLE" if rd == "NOT EVALUABLE" else "NOT FIRED")})
    return 0 if rd == "CONDITION-DEPENDENT" else (2 if rd == "NOT EVALUABLE" else 1)


def main() -> int:
    a = sys.argv[1:]
    try:
        if a[0] == "detcap":
            return detcap(Path(a[1]), a[2])
        if a[0] == "tier":
            return tier(Path(a[1]), a[2:])
        if a[0] in ("alone", "memstat", "d0", "canary", "correct", "cell", "warm"):
            sys.argv = [sys.argv[0]] + a
            return p6_gates.main()
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    except (IndexError, ValueError):
        pass
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
