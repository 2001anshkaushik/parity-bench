#!/usr/bin/env python3
"""Do the committed Stage 3b analyses contain ONLY launched legs? (R7, 2026-09-22)

    batchsize_provenance_check.py [--out report.json]

A launch that failed early on 2026-09-20 filed a copy of the SMOKE campaign's shake_rr export under
the Stage 3b S3 prefix (register 44). This checks, on the committed tree, that neither Stage 3b
analysis used it or anything else not launched in Stage 3b:

  1. every leg an analysis lists (legs_seen) is a launch directory under the Stage 3b campaign
     directory holding that leg's file — and no shake* launch appears;
  2. every service-arm launch's worker count came from an export whose run_dir names THIS campaign
     and THIS launch — the analyser's own matching, replayed;
  3. the misfiled copy's own run_dir names the smoke campaign, so that rule cannot match it.

NULL CONTROL: the same matching is run on a synthetic campaign holding one launch and a planted
export named for that launch but carrying ANOTHER campaign's run_dir; it must be rejected.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import batchsize_analyse as ba  # noqa: E402

S3B = ROOT / "working/results/batchsize_s3b_20260920T203139Z"
MISFILED = "exp_batchsize_sweep_rr__20260920T113718Z__8cd562347f86.json"


def main() -> int:
    rep: Dict[str, Any] = {"campaign": str(S3B.relative_to(ROOT))}
    launch_dirs = sorted(p.name for p in S3B.iterdir() if p.is_dir() and list(p.glob("leg_*.json")))
    units = ba._units_by_run_dir(S3B)
    checks = {}
    for f in ("analysis_docs_384.json", "analysis_docs_anchor96.json"):
        a = json.loads((S3B / f).read_text())
        seen = [x.split("/")[0] for x in a["legs_seen"]]
        bad = sorted({s for s in seen if s not in launch_dirs or s.startswith("shake")})
        li = sorted({x.split("/")[0] for x in a["legs_seen"] if x.split("/")[1] == "li"})
        checks[f] = {"launches_listed": sorted(set(seen)), "listed_but_not_a_stage3b_launch": bad,
                     "service_arm_exports": {l: (units.get(l) or {}).get("export") for l in li},
                     "service_arm_launch_without_matching_export": [l for l in li if not units.get(l)]}
    rep["analyses"] = checks
    root_copy = ROOT / "working/results" / MISFILED
    rd = json.loads(root_copy.read_text())["data"]["run_dir"] if root_copy.exists() else None
    rep["misfiled_copy"] = {"file": MISFILED, "run_dir_it_names": rd,
                            "matchable_by_stage3b": bool(rd) and rd.rstrip("/").split("/")[-2:-1] == [S3B.name],
                            "matched_for_any_launch": any((u or {}).get("export") == MISFILED for u in units.values())}
    # NULL CONTROL: a planted export named for a real launch but carrying another campaign's run_dir
    with tempfile.TemporaryDirectory() as t:
        root = Path(t) / "working" / "results"; camp = root / S3B.name
        (camp / "li_w16").mkdir(parents=True)
        (root / "exp_batchsize_sweep_li__20990101T000000Z__x.json").write_text(json.dumps(
            {"data": {"run_dir": "working/results/batchsize_OTHER/li_w16", "posture": {"ws1_workers": 99}}}))
        planted = ba._units_by_run_dir(camp)
    rep["null_control"] = {"planted_export_for_another_campaign_rejected": "li_w16" not in planted}
    ok = (all(not c["listed_but_not_a_stage3b_launch"] and not c["service_arm_launch_without_matching_export"]
              for c in checks.values())
          and not rep["misfiled_copy"]["matched_for_any_launch"] and rep["null_control"]["planted_export_for_another_campaign_rejected"])
    rep["verdict"] = ("PASS — both Stage 3b analyses contain only Stage 3b launches; the misfiled copy matches no launch"
                      if ok else "FAIL — see the fields above")
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only")
            return 3
        p.write_text(text)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
