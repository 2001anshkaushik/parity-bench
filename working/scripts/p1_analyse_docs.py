#!/usr/bin/env python3
"""P1-B and P1-C docs analysis (preregistration.json P1_B, P1_C), from raw leg files only.

    p1_analyse_docs.py <campaign_dir> [--texts-dir <dir>]  -> analysis_p1docs.json (+ p1c_correctness_<v>.jsonl)

Per leg (P0's loader and stage rules): span docs/s over all rows; the excluded-straggler view (the
same, over the documents that are not the eleven); the D1 metric set per stage (stamped PROFILE);
engine cores and idle spin (the driver's cost block); the sampled memory peak from memstat.jsonl
INSIDE the measured window [min submit, max completion]; lost documents (rows not ok).
P1-C correctness needs each full run's texts.jsonl.gz (kept in S3, too large for the repository):
pass the directory holding <leg>/texts.jsonl.gz; the per-document comparison is written beside the
analysis and is the committed evidence (with the texts' sha256)."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import load_leg, metric_set, pair_compare, rr_d1, span_raw  # noqa: E402
from p1_gates import census_total  # noqa: E402

FLOOR = 0.0082
ELEVEN = {"011_011464.pdf", "039_039660.pdf", "008_008871.pdf", "011_011730.pdf", "014_014261.pdf",
          "000_000344.pdf", "031_031239.pdf", "002_002489.pdf", "034_034697.pdf", "033_033172.pdf",
          "014_014969.pdf"}


def leg_dir(camp: Path, name: str) -> Optional[Path]:
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and list(d.glob("leg_*.json")) and list(d.glob("perdoc_*.jsonl")):
            return d
    return None


def mem_peak(d: Path, t0: float, t1: float) -> Dict[str, Any]:
    f = d / "memstat.jsonl"
    if not f.exists():
        return {"status": "NO FILE"}
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    win = [r for r in rows if t0 <= r["t"] <= t1]
    if not win:
        return {"status": "NO SAMPLES IN WINDOW", "samples_total": len(rows)}
    return {"samples_in_window": len(win), "hz": 1.0,
            "peak_bytes": {k: max(r[k] for r in win) for k in ("anon", "file", "total")},
            "peak_anon_plus_file_bytes": max(r["anon"] + r["file"] for r in win)}


def leg_summary(d: Path) -> Dict[str, Any]:
    g = load_leg(d)
    rows = g["rows"]
    t0 = min(r["submit_ns"] for r in rows) / 1e9
    t1 = max(r["completion_ns"] for r in rows) / 1e9
    rest = [r for r in rows if r["doc"] not in ELEVEN]
    s = (g.get("session") or {})
    d1 = rr_d1(g) if g["stamps"] else None
    lost = sorted(r["doc"] for r in rows if not r.get("ok"))
    return {"dir": d.name, "n": len(rows), "span": g["span"], "excluded_straggler": span_raw(rest),
            "boot_id": g["boot_id"], "steal_share": (s.get("steal") or {}).get("share"),
            "mhz_mean": (s.get("mhz_over_window") or {}).get("mean_of_samples"),
            "cpu_model": ((s.get("cpu_open") or {}).get("model") or [None])[0],
            "mandate": g.get("mandate"),
            "engine_cores": (g.get("cost") or {}).get("engine_container_cores"),
            "idle_spin_cores": ((g.get("cost") or {}).get("idle_spin_measured") or {}).get("cores"),
            "cpu_s_per_doc": (g.get("cost") or {}).get("cpu_s_per_doc"),
            "memory": mem_peak(d, t0, t1), "lost_documents": {"n": len(lost), "docs": lost[:100]},
            "d1": d1, "parse_share": ((d1 or {}).get("stages") or {}).get("parse_bracket", {}).get("share_of_run_total"),
            "chunks": {r["doc"]: r.get("chunk_sha256") for r in rows if r.get("ok")},
            "_g": g}


def one_vs_one(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    va, vb = a["span"]["docs_per_s"], b["span"]["docs_per_s"]
    d = vb / va - 1
    return {"a": a["dir"], "b": b["dir"], "a_docs_per_s": va, "b_docs_per_s": vb, "delta_b_vs_a": d,
            "threshold": FLOOR, "readable": abs(d) > FLOOR,
            "excluded_straggler": {"a": a["excluded_straggler"]["docs_per_s"], "b": b["excluded_straggler"]["docs_per_s"],
                                   "delta_b_vs_a": b["excluded_straggler"]["docs_per_s"] / a["excluded_straggler"]["docs_per_s"] - 1}}


def correctness_identity(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    ca, cb = a["chunks"], b["chunks"]
    both = sorted(set(ca) & set(cb))
    return {"a": a["dir"], "b": b["dir"], "documents_ok_in_both": len(both),
            "chunk_lists_differ": [k for k in both if ca[k] != cb[k]],
            "lost_by_b": sorted(set(ca) - set(cb)), "gained_by_b": sorted(set(cb) - set(ca)),
            "pass": all(ca[k] == cb[k] for k in both) and not (set(ca) - set(cb))}


def texts(p: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            out[j["doc"]] = "".join(j["texts"])
    return out


def dice(a: str, b: str) -> float:
    ta, tb = Counter(a.split()), Counter(b.split())
    n = sum(ta.values()) + sum(tb.values())
    return (2 * sum((ta & tb).values()) / n) if n else 1.0


def dist(v: List[float]) -> Dict[str, Any]:
    if not v:
        return {"n": 0}
    s = sorted(v)
    q = lambda f: s[max(0, math.ceil(f * len(s)) - 1)]  # noqa: E731  nearest rank
    return {"n": len(s), "min": s[0], "p5": q(.05), "p25": q(.25), "p50": statistics.median(s),
            "p75": q(.75), "p95": q(.95)}


def p1c_correctness(camp: Path, tdir: Path, ref_leg: str, cand_leg: str, label: str,
                    ref_rows: Dict[str, Any], cand_rows: Dict[str, Any]) -> Dict[str, Any]:
    fr, fc = tdir / ref_leg / "texts.jsonl.gz", tdir / cand_leg / "texts.jsonl.gz"
    if not (fr.exists() and fc.exists()):
        return {"status": f"texts absent ({fr.exists()}, {fc.exists()})"}
    tr, tc = texts(fr), texts(fc)
    docs = sorted({r["doc"] for r in ref_rows["_g"]["rows"]} | {r["doc"] for r in cand_rows["_g"]["rows"]})
    ok_r = {r["doc"] for r in ref_rows["_g"]["rows"] if r.get("ok")}
    ok_c = {r["doc"] for r in cand_rows["_g"]["rows"] if r.get("ok")}
    empty_r = {d for d in docs if d not in ok_r or not tr.get(d, "").strip()}
    empty_c = {d for d in docs if d not in ok_c or not tc.get(d, "").strip()}
    per = []
    for d in docs:
        a, b = tr.get(d, ""), tc.get(d, "")
        ca, cb = " ".join(a.split()), " ".join(b.split())
        per.append({"doc": d, "ref_empty": d in empty_r, "cand_empty": d in empty_c, "ref_chars": len(ca),
                    "cand_chars": len(cb), "char_ratio": (len(cb) / len(ca)) if ca else None,
                    "dice": dice(ca, cb) if (ca or cb) else None})
    out_f = camp / f"p1c_correctness_{label}.jsonl"
    out_f.write_text("".join(json.dumps(x) + "\n" for x in per))
    loses = sorted(empty_c - empty_r)
    return {"reference": ref_leg, "candidate": cand_leg, "documents": len(docs),
            "texts_sha256": {ref_leg: hashlib.sha256(fr.read_bytes()).hexdigest(), cand_leg: hashlib.sha256(fc.read_bytes()).hexdigest()},
            "texts_location": "S3 only (s3://rocketride-benchmark-data/ansh/parity-p1/<campaign>/<leg>/texts.jsonl.gz)",
            "empty": {"reference": len(empty_r), "candidate": len(empty_c)},
            "candidate_empty_where_reference_recovers": loses, "n_loses": len(loses),
            "candidate_recovers_where_reference_empty": sorted(empty_r - empty_c),
            "char_ratio": dist([x["char_ratio"] for x in per if x["char_ratio"] is not None]),
            "dice": dist([x["dice"] for x in per if x["dice"] is not None]),
            "failures": sorted(d for d in docs if d not in ok_c)[:200],
            "adoptable": len(loses) == 0, "per_document_file": out_f.name}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--texts-dir", type=Path, default=None)
    a = ap.parse_args()
    camp = a.campaign
    names = ["p1b_base_a", "p1b_fix_a", "p1b_base_b", "p1b_fix_b", "p1b_base_full", "p1b_fix_full",
             "p1c_hyb_full", "p1c_pure_full", "p1c_fix_a", "p1c_hyb_a", "p1c_pure_a", "p1c_fix_b", "p1c_hyb_b", "p1c_pure_b"]
    L = {n: leg_summary(d) for n in names if (d := leg_dir(camp, n))}
    out: Dict[str, Any] = {"legs": {n: {k: v for k, v in x.items() if k not in ("_g", "chunks")} for n, x in L.items()},
                           "sessions": sorted({x["boot_id"] for x in L.values()})}
    b: Dict[str, Any] = {}
    if "p1b_base_a" in L and "p1b_fix_a" in L:
        b["correctness"] = correctness_identity(L["p1b_base_a"], L["p1b_fix_a"])
    sm = {}
    for lab, sub in (("base", "p1b_smoke_base"), ("fix", "p1b_smoke_fix")):
        f = camp / sub / "results_e1.jsonl"
        if f.exists():
            r = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
            sm[lab] = {"p50_wall_s": statistics.median(x["wall_s"] for x in r), "per_doc": {x["doc"]: x["wall_s"] for x in r},
                       "rc_nonzero": [x["doc"] for x in r if x.get("rc") != 0],
                       "exec_census_total": census_total(camp / sub / "exec_census.json")}
    if len(sm) == 2:
        ratio = sm["base"]["p50_wall_s"] / sm["fix"]["p50_wall_s"]
        drop = 1 - sm["fix"]["exec_census_total"] / sm["base"]["exec_census_total"] if sm["base"]["exec_census_total"] else None
        b["smoke"] = {**sm, "speed_ratio": ratio, "exec_census_drop": drop,
                      "fired": ratio >= 10 and drop is not None and drop >= 0.90}
    if all(n in L for n in ("p1b_base_a", "p1b_base_b", "p1b_fix_a", "p1b_fix_b")):
        b["speed_384"] = pair_compare([L["p1b_base_a"]["_g"], L["p1b_base_b"]["_g"]],
                                      [L["p1b_fix_a"]["_g"], L["p1b_fix_b"]["_g"]], FLOOR)
    if "p1b_base_full" in L and "p1b_fix_full" in L:
        b["full"] = one_vs_one(L["p1b_base_full"], L["p1b_fix_full"])
    if b.get("correctness") and b.get("smoke"):
        b["verdict"] = ("SUPPORTED" if b["correctness"]["pass"] and b["smoke"]["fired"] else
                        "NOT SUPPORTED" if b["correctness"]["pass"] else "OUTPUT-CHANGING")
    out["p1b"] = b
    c: Dict[str, Any] = {}
    if a.texts_dir and "p1b_fix_full" in L:
        for lab, n in (("hybrid", "p1c_hyb_full"), ("pure", "p1c_pure_full")):
            if n in L:
                c[f"correctness_{lab}"] = p1c_correctness(camp, a.texts_dir, L["p1b_fix_full"]["dir"], L[n]["dir"], lab,
                                                          L["p1b_fix_full"], L[n])
    cells = {k: [L[f"p1c_{k}_{s}"]["_g"] for s in ("a", "b") if f"p1c_{k}_{s}" in L] for k in ("fix", "hyb", "pure")}
    if all(len(v) == 2 for v in cells.values()):
        c["speed_384"] = {"hybrid_vs_fix": pair_compare(cells["fix"], cells["hyb"], FLOOR),
                          "pure_vs_fix": pair_compare(cells["fix"], cells["pure"], FLOOR)}
    if "p1b_fix_full" in L:
        for lab, n in (("hybrid", "p1c_hyb_full"), ("pure", "p1c_pure_full")):
            if n in L:
                c[f"full_{lab}_vs_fix"] = one_vs_one(L["p1b_fix_full"], L[n])
    ch = c.get("correctness_hybrid") or {}
    if ch.get("adoptable") is not None:
        sp = (c.get("speed_384") or {}).get("hybrid_vs_fix") or {}
        if not ch["adoptable"]:
            v = "P1-B OPTIMAL (HYBRID not adoptable)"
        elif sp and sp["readable"] and sp["delta_b_vs_a"] > 0:
            v = "HYBRID OPTIMAL"
        elif sp and sp["readable"] and sp["delta_b_vs_a"] < 0:
            v = "P1-B OPTIMAL (HYBRID readably slower)"
        else:
            v = "TIE within the floor" if sp else None
        c["verdict"] = v
    out["p1c"] = c
    (camp / "analysis_p1docs.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"p1b": {k: v for k, v in b.items() if k in ("verdict",)}, "p1c": c.get("verdict"),
                      "legs": list(L)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
