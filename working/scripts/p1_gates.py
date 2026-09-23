#!/usr/bin/env python3
"""P1-B gates, computed exactly as preregistration.json P1_B states (the chain decides from these files).

    p1_gates.py correctness <campaign_dir> <base_leg> <fix_leg>   -> p1b_correctness.json
    p1_gates.py smoke <campaign_dir> <base_subdir> <fix_subdir>    -> p1b_smoke_gate.json
Exit 0 = PASS / FIRED, 1 = FAIL / NOT FIRED, 2 = evidence missing.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def perdoc(leg: Path):
    f = sorted(leg.glob("perdoc_*.jsonl"))
    if not f:
        raise SystemExit(2)
    rows = [json.loads(x) for x in f[0].read_text().splitlines() if x.strip()]
    return {r["doc"]: r for r in rows}


def correctness(d: Path, base: str, fix: str) -> int:
    b, f = perdoc(d / base), perdoc(d / fix)
    both = sorted(k for k in b if b[k].get("ok") and f.get(k, {}).get("ok"))
    differ = [k for k in both if b[k]["chunk_sha256"] != f[k]["chunk_sha256"]]
    lost = sorted(k for k in b if b[k].get("ok") and not f.get(k, {}).get("ok"))
    gained = sorted(k for k in f if f[k].get("ok") and not b.get(k, {}).get("ok"))
    ok = not differ and not lost
    out = {"gate": "P1-B correctness (preregistration.json P1_B.correctness_gate)", "base_leg": base, "fix_leg": fix,
           "documents_ok_in_both": len(both), "chunk_lists_differ": differ, "lost_by_fix": lost,
           "gained_by_fix": gained, "outcome": "PASS" if ok else "FAIL — OUTPUT-CHANGING"}
    (d / "p1b_correctness.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v if not isinstance(v, list) else len(v) for k, v in out.items()}))
    return 0 if ok else 1


def census_total(p: Path) -> int:
    tot = 0
    for line in p.read_text().splitlines():
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") == "map":
            tot += sum((j.get("data") or {}).get("@exec", {}).values())
    return tot


def smoke(d: Path, base: str, fix: str) -> int:
    rows = {}
    for lab, sub in (("base", base), ("fix", fix)):
        r = [json.loads(x) for x in (d / sub / "results_e1.jsonl").read_text().splitlines() if x.strip()]
        rows[lab] = r
    p50 = {lab: statistics.median(x["wall_s"] for x in r) for lab, r in rows.items()}
    cen = {lab: census_total(d / sub / "exec_census.json") for lab, sub in (("base", base), ("fix", fix))}
    ratio = p50["base"] / p50["fix"] if p50["fix"] else None
    drop = 1 - cen["fix"] / cen["base"] if cen["base"] else None
    fired = bool(ratio is not None and ratio >= 10 and drop is not None and drop >= 0.90)
    out = {"gate": "P1-B smoke (preregistration.json P1_B.smoke_gate)", "base": base, "fix": fix,
           "p50_wall_s": p50, "speed_ratio_base_over_fix": ratio, "exec_census_total": cen,
           "exec_census_drop": drop, "threshold": "ratio >= 10 AND drop >= 90%",
           "rc_nonzero": {lab: [x["doc"] for x in r if x.get("rc") != 0] for lab, r in rows.items()},
           "fired": fired}
    (d / "p1b_smoke_gate.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out))
    return 0 if fired else 1


if __name__ == "__main__":
    mode, d, a, b = sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4]
    raise SystemExit(correctness(d, a, b) if mode == "correctness" else smoke(d, a, b))
