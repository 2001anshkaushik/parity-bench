#!/usr/bin/env python3
"""P0 H5 (Tika config tail) and H6 (parser bake-off), from the raw per-parse records.

    p0_analyse_parse.py <campaign_dir> h5       -> analysis_h5.json
    p0_analyse_parse.py <campaign_dir> h6smoke  -> analysis_h6smoke.json
    p0_analyse_parse.py <campaign_dir> h6full   -> analysis_h6full.json

Records: <campaign>/<stage>/results_<label>.jsonl, one row per parse: doc, wall_s and cpu_s of
the parse call (measured inside the worker), chars and stripped_chars (read back from the text by
the orchestrator), error / timeout. Rules are preregistration.json H5 / H6 verbatim:
  H5 gate: some single feature has variant <= 0.5 x shipped-mean time on >= 6 of the 11, with
           text length within 5% of shipped on each of those documents.
  H6 gate: some candidate has p50(tika_shipped) / p50(candidate) >= 2 on the 11 AND returns
           empty on no 384-slice document tika_shipped extracts text from.
  EMPTY = raised, timed out, or whitespace-stripped length 0.
Timeouts enter a time statistic at the timeout value and are flagged as lower bounds.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
ELEVEN = ["011_011464.pdf", "039_039660.pdf", "008_008871.pdf", "011_011730.pdf", "014_014261.pdf",
          "000_000344.pdf", "031_031239.pdf", "002_002489.pdf", "034_034697.pdf", "033_033172.pdf",
          "014_014969.pdf"]
FEATURES = {"h5_no_sortByPosition": "sortByPosition", "h5_no_acroform": "extractAcroFormContent",
            "h5_no_annotations": "extractAnnotationText", "h5_no_bookmarks": "extractBookmarksText"}


def rows(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def q_nearest(v: List[float], q: float) -> float:
    s = sorted(v)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def metric_set(v: List[float]) -> Dict[str, Any]:
    if not v:
        return {"count": 0}
    mean = sum(v) / len(v)
    med = statistics.median(v)
    return {"count": len(v), "sum": sum(v), "min": min(v), "mean": mean,
            "sd": statistics.pstdev(v) if len(v) > 1 else 0.0, "p50": med,
            "p90": q_nearest(v, .9), "p95": q_nearest(v, .95), "p99": q_nearest(v, .99),
            "max": max(v), "mean_over_p50": mean / med if med else None}


def t_of(r: Dict[str, Any]) -> Optional[float]:
    if r.get("timeout"):
        return float(r.get("timeout_s"))
    if r.get("error") or r.get("wall_s") is None:
        return None
    return float(r["wall_s"])


def empty(r: Optional[Dict[str, Any]]) -> bool:
    return r is None or bool(r.get("timeout") or r.get("error")) or not r.get("stripped_chars")


def in_engine_holds() -> Dict[str, float]:
    """S5-D in-engine parse bracket (context only): after_parse.last_t - open_t."""
    f = ROOT / "working/results/batchsize_s5_20260921T205917Z/s5d/rr_stamped/stamp_probe.jsonl"
    out: Dict[str, float] = {}
    for r in rows(f):
        if r.get("stage") == "after_parse" and r.get("doc") in ELEVEN and r.get("last_t"):
            out[r["doc"]] = r["last_t"] - r["open_t"]
    return out


def h5(camp: Path) -> Dict[str, Any]:
    rs = rows(camp / "h5" / "results_h5.jsonl")
    by = {(r["doc"], r["label"]): r for r in rs}
    holds = in_engine_holds()
    per_doc, feat = {}, {f: {"docs_passing": [], "rows": {}} for f in FEATURES}
    for d in ELEVEN:
        s1, s2 = by.get((d, "h5_shipped_r1")), by.get((d, "h5_shipped_r2"))
        t1, t2 = (t_of(s1) if s1 else None), (t_of(s2) if s2 else None)
        ts = [t for t in (t1, t2) if t is not None]
        sm = sum(ts) / len(ts) if ts else None
        shipped_timeout = bool((s1 or {}).get("timeout") or (s2 or {}).get("timeout"))
        len_ref = (s1 or {}).get("chars") if not empty(s1) else (s2 or {}).get("chars")
        per_doc[d] = {"shipped_r1_s": t1, "shipped_r2_s": t2, "shipped_mean_s": sm,
                      "shipped_timeout": shipped_timeout,
                      "replicate_spread": (abs(t1 - t2) / ((t1 + t2) / 2)) if (t1 and t2) else None,
                      "shipped_chars_r1": (s1 or {}).get("chars"), "shipped_chars_r2": (s2 or {}).get("chars"),
                      "shipped_cpu_r1_s": (s1 or {}).get("cpu_s"),
                      "in_engine_hold_s_S5D_context": holds.get(d),
                      "in_engine_over_isolated": (holds[d] / sm) if (d in holds and sm) else None}
        for lab, fname in FEATURES.items():
            v = by.get((d, lab))
            tv = t_of(v) if v else None
            lc = ((v["chars"] / len_ref - 1) if (v and not empty(v) and len_ref) else None)
            passes = (tv is not None and sm is not None and not (v or {}).get("timeout")
                      and tv <= 0.5 * sm and lc is not None and abs(lc) <= 0.05)
            feat[lab]["rows"][d] = {"variant_s": tv, "variant_timeout": bool((v or {}).get("timeout")),
                                    "time_change": (tv / sm - 1) if (tv is not None and sm) else None,
                                    "chars": (v or {}).get("chars"), "length_change": lc,
                                    "passes": passes}
            if passes:
                feat[lab]["docs_passing"].append(d)
    for lab, f in feat.items():
        red = [1 - x["variant_s"] / per_doc[d]["shipped_mean_s"] for d, x in f["rows"].items()
               if x["variant_s"] is not None and per_doc[d]["shipped_mean_s"]]
        f["n_passing"] = len(f["docs_passing"])
        f["median_time_reduction"] = statistics.median(red) if red else None
        f["param"] = FEATURES[lab]
    passing = [lab for lab, f in feat.items() if f["n_passing"] >= 6]
    best = max(passing, key=lambda l: feat[l]["median_time_reduction"] or -1) if passing else None
    return {"per_document": per_doc, "per_feature": feat,
            "gate": {"threshold": ">= 50% time removed on >= 6 of the 11 with text length within 5%",
                     "fired": bool(passing), "features_passing": passing,
                     "best_config": (best.replace("h5_", "") + ".xml") if best else None,
                     "n_passing_by_feature": {l: f["n_passing"] for l, f in feat.items()}},
            "records": len(rs)}


def h6(camp: Path, stage: str) -> Dict[str, Any]:
    d = camp / stage
    tail_prefix, big_prefix = ("h6_tail_", "h6_384_") if stage == "h6smoke" else (None, f"{stage}_")
    out: Dict[str, Any] = {"parsers": {}}
    labels = sorted(p.stem.replace("results_", "") for p in d.glob("results_*.jsonl"))
    tail = {l.replace(tail_prefix, ""): {r["doc"]: r for r in rows(d / f"results_{l}.jsonl")}
            for l in labels if tail_prefix and l.startswith(tail_prefix)}
    big = {l.replace(big_prefix, ""): {r["doc"]: r for r in rows(d / f"results_{l}.jsonl")}
           for l in labels if l.startswith(big_prefix)}
    if stage != "h6smoke":           # the full corpus contains the 11: restrict to them for (a)
        tail = {p: {k: v for k, v in rr.items() if k in ELEVEN} for p, rr in big.items()}
    ref = "tika_shipped"
    t_ref = [t_of(r) for r in tail.get(ref, {}).values() if t_of(r) is not None]
    p50_ref = statistics.median(t_ref) if t_ref else None
    tika_text = {k for k, r in big.get(ref, {}).items() if not empty(r)}
    for p in sorted(set(tail) | set(big)):
        tt = [t_of(r) for r in tail.get(p, {}).values() if t_of(r) is not None]
        p50 = statistics.median(tt) if tt else None
        bigr = big.get(p, {})
        emp = sorted(k for k, r in bigr.items() if empty(r))
        loss = sorted(set(emp) & tika_text)
        gain = sorted({k for k, r in bigr.items() if not empty(r)} - tika_text) if p != ref else []
        out["parsers"][p] = {
            "tail_11": {"p50_s": p50, "timeouts": sorted(k for k, r in tail.get(p, {}).items() if r.get("timeout")),
                        "metric_set_s": metric_set(tt),
                        "speed_ratio_vs_tika_shipped": (p50_ref / p50) if (p50 and p50_ref) else None},
            "corpus": {"n": len(bigr), "empty": len(emp), "empty_docs": emp[:200],
                       "loses_where_tika_extracts": loss, "n_loses": len(loss),
                       "extracts_where_tika_empty": gain, "n_gains": len(gain),
                       "metric_set_s": metric_set([t_of(r) for r in bigr.values() if t_of(r) is not None]),
                       "timeouts": sorted(k for k, r in bigr.items() if r.get("timeout")),
                       "errors": {k: r["error"] for k, r in bigr.items() if r.get("error")}}}
    cands = [p for p in out["parsers"] if p != ref and p != "tika_best"] + \
            (["tika_best"] if "tika_best" in out["parsers"] else [])
    speed_pass = [p for p in cands if (out["parsers"][p]["tail_11"]["speed_ratio_vs_tika_shipped"] or 0) >= 2]
    full_pass = [p for p in speed_pass if out["parsers"][p]["corpus"]["n_loses"] == 0]
    out["gate" if stage == "h6smoke" else "verdict"] = {
        "rule": ("p50(tika_shipped)/p50(candidate) >= 2 on the 11 AND no empty on a document "
                 "tika_shipped extracts"),
        "speed_pass": speed_pass, "speed_and_coverage_pass": full_pass,
        "fired": bool(full_pass) if stage == "h6smoke" else None,
        "hybrid_branch": (bool(speed_pass) and not full_pass) if stage == "h6smoke" else None,
        "candidates": full_pass if stage != "h6smoke" else None}
    fid = d / ("fidelity_384.jsonl" if stage == "h6smoke" else "fidelity_9975.jsonl")
    if fid.exists():
        fr = rows(fid)
        fd = {}
        for c in sorted({r["cand"] for r in fr}):
            xs = [r for r in fr if r["cand"] == c and "missing" not in r]
            ratio = [r["char_ratio"] for r in xs if r.get("char_ratio") is not None]
            dice = [r["dice"] for r in xs if r.get("dice") is not None]
            def dist(v):
                return ({"n": len(v), "min": min(v), "p5": q_nearest(v, .05), "p25": q_nearest(v, .25),
                         "p50": statistics.median(v), "p75": q_nearest(v, .75), "p95": q_nearest(v, .95)}
                        if v else {"n": 0})
            fd[c] = {"char_ratio": dist(ratio), "dice": dist(dice),
                     "missing": sum(1 for r in fr if r["cand"] == c and "missing" in r)}
        out["fidelity_vs_tika_shipped"] = fd
    return out


def main() -> int:
    camp, stage = Path(sys.argv[1]), sys.argv[2]
    res = h5(camp) if stage == "h5" else h6(camp, stage)
    out = camp / f"analysis_{stage}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"wrote {out}")
    print(json.dumps(res.get("gate") or res.get("verdict"), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
