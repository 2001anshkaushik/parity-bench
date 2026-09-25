#!/usr/bin/env python3
"""P3-A, P3-C and P3-D docs analysis (preregistration.json P3_A, P3_C, P3_D), from raw leg files only.

    p3_analyse_docs.py <campaign_dir> [--texts-dir <dir>] [--vecs-dir <dir>]  -> analysis_p3docs.json

Per leg, P0/P1/P2's loaders and definitions unchanged (p2_analyse_docs.summary: span docs/s, the excluded-straggler view,
stage shares on stamped legs, CPU-s/doc, utilisation, idle cores, idle spin, the sampled memory peak, lost and empty
documents, steal, MHz, CPU model, boot id). Every gate is recomputed from the same raw files by the pre-registered rule and
compared with the record the chain decided from (gates/*.json). Full-run texts and the P3-C vectors are large and live in
S3: pass --texts-dir / --vecs-dir holding <leg>/texts.jsonl.gz / <leg>/vecs.jsonl.gz.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import load_leg  # noqa: E402
import p2_analyse_docs as P2  # noqa: E402
from p2_gates import p50_parse_eleven, texts_of  # noqa: E402
import p3_gates as G  # noqa: E402

FLOOR = {"rr": 0.0082, "li": 0.0987}
LI_SMOKE_SPREAD = 0.0819            # P2-A's LlamaIndex 384 replicate spread (preregistration.json P3_A ratio_rule)
BAR = 0.85
LITTLE = 1 / (1 - 0.0551) - 1
P2_CAMP = Path(__file__).resolve().parents[2] / "working" / "results" / "parity_p2_20260924T160106Z"


def spread(a: float, b: float) -> Optional[float]:
    return P2.spread(a, b)


def with_s3(camp: Path, name: str, extra: Optional[Path], fname: str) -> Optional[Path]:
    """The leg's directory, with fname taken from --texts-dir/--vecs-dir when the committed leg lacks it."""
    d = P2.leg_dir(camp, name)
    if d is None or (d / fname).exists() or extra is None or not (extra / d.name / fname).exists():
        return d
    import shutil
    import tempfile
    t = Path(tempfile.mkdtemp()) / d.name
    shutil.copytree(d, t)
    shutil.copy(extra / d.name / fname, t / fname)
    return t


def rec(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    return P2.gate_record(camp, name)


# ------------------------------------------------------------------ P3-A
def p3a(camp: Path, L: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    rr, li = P2.leg_dir(camp, "p3a_rr_h"), P2.leg_dir(camp, "p3a_li_h")
    if rr and li:
        h = {"rr": G.leg_health(rr), "li": G.leg_health(li)}
        ours = G.chunks_ok(rr)
        ident = []
        for ref in (P2_CAMP / "p2a_rr_a", P2_CAMP / "p2a_rr_b"):
            theirs = G.chunks_ok(ref)
            shared = sorted(set(ours) & set(theirs))
            differ = [k for k in shared if ours[k] != theirs[k]]
            ident.append({"reference": ref.name, "shared_ok_documents": len(shared), "chunk_lists_differ": differ,
                          "ok_in_reference_not_here": sorted(set(theirs) - set(ours)), "identical": not differ and len(shared) > 0})
        conds = {"both_verdicts_ok_or_degraded_with_all_rows": h["rr"]["verdict_ok"] and h["li"]["verdict_ok"],
                 "d0_clean": h["rr"]["d0_clean"] and h["li"]["d0_clean"],
                 "memory_sampler_non_empty": h["rr"]["memstat_rows"] >= 1 and h["li"]["memstat_rows"] >= 1,
                 "rr_chunks_identical_to_p2a_on_shared_documents": all(x["identical"] for x in ident)}
        fired = all(conds.values())
        r = rec(camp, "G_health_A")
        out["health_gate"] = {"legs": h, "identity": ident, "conditions": conds, "fired": fired,
                              "health_legs_docs_per_s": {"rr": L["p3a_rr_h"]["span"]["docs_per_s"] if L.get("p3a_rr_h") else None,
                                                         "li": L["p3a_li_h"]["span"]["docs_per_s"] if L.get("p3a_li_h") else None},
                              "note": "a HEALTH gate (Ansh's ruling): its docs/s are reported, never read as performance",
                              "agrees_with_chain_record": bool(r) and r.get("outcome") == ("FIRED" if fired else "NOT FIRED")}
    else:
        out["health_gate"] = {"status": "NOT EVALUABLE"}
    fr, fl = L.get("p3a_rr_full"), L.get("p3a_li_full")
    if fr and fl:
        r = P2.dps(fr) / P2.dps(fl)
        hi, lo = BAR * (1 + LI_SMOKE_SPREAD), BAR * (1 - LI_SMOKE_SPREAD)
        verdict = "SUPPORTED" if r >= hi else ("NOT SUPPORTED" if r < lo else "UNREADABLE AT n=1 (at the bar within LlamaIndex's replicate spread)")
        er, el = set(fr["empty_docs"]), set(fl["empty_docs"])
        out["full"] = {"rr": fr["attempt"], "li": fl["attempt"], "rr_docs_per_s": P2.dps(fr), "li_docs_per_s": P2.dps(fl),
                       "ratio_rr_over_li": r, "n_per_arm": 1, "bar": BAR, "readable_band": [lo, hi], "li_smoke_spread_bound": LI_SMOKE_SPREAD,
                       "verdict": verdict,
                       "excluded_straggler": {"rr": fr["excluded_straggler"]["docs_per_s"], "li": fl["excluded_straggler"]["docs_per_s"],
                                              "ratio_rr_over_li": fr["excluded_straggler"]["docs_per_s"] / fl["excluded_straggler"]["docs_per_s"]},
                       "per_arm": {arm: {"cpu_s_per_doc": x["cpu_s_per_doc"], "engine_cores": x["engine_cores"], "utilisation": x["utilisation"],
                                         "host_busy_cores": x["host_busy_cores"], "idle_cores": x["idle_cores"], "idle_spin_cores": x["idle_spin_cores"],
                                         "memory": x["memory"], "lost_documents": x["lost_documents"], "verdict": x["verdict"], "parse_share": x.get("parse_share")}
                                   for arm, x in (("rr", fr), ("li", fl))},
                       "empty_documents": {"rr": len(er), "li": len(el), "rr_only": sorted(er - el), "li_only": sorted(el - er)},
                       "rule": "r = RR/LI span docs/s, n=1 per arm; SUPPORTED iff r >= 0.85 x 1.0819; NOT SUPPORTED iff r < 0.85 x 0.9181; else UNREADABLE at n=1"}
    else:
        out["full"] = {"status": "NOT RUN", "reason": "see master_done.json (A_FULL)"}
    return out


# ------------------------------------------------------------------ P3-C
def p3c(camp: Path, L: Dict[str, Any], vecs_dir: Optional[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    names = {s: [f"p3c_t{s}_{r}" for r in ("a", "b")] for s in G.SHAPES}
    if not all(L.get(n) for s in names for n in names[s]):
        out["smoke_gate"] = {"status": "NOT EVALUABLE", "have": [n for s in names for n in names[s] if L.get(n)]}
        return out
    dps = {s: [P2.dps(L[n]) for n in names[s]] for s in G.SHAPES}
    chunks = {s: [L[n]["chunks"] for n in names[s]] for s in G.SHAPES}
    measured = {r["doc"] for r in L[names[1][0]]["_g"]["rows"]}
    m1, s1 = statistics.mean(dps[1]), spread(*dps[1])
    per: Dict[str, Any] = {}
    for s in G.SHAPES[1:]:
        corr = []
        for i in (0, 1):
            for j in (0, 1):
                ca, cb = chunks[1][j], chunks[s][i]
                shared = sorted(set(ca) & set(cb))
                corr.append({"shape_leg": names[s][i], "vars1_leg": names[1][j], "shared_ok": len(shared),
                             "chunk_lists_differ": [k for k in shared if ca[k] != cb[k]], "ok_in_vars1_not_here": sorted(set(ca) - set(cb))})
        correct = all(not x["chunk_lists_differ"] and not x["ok_in_vars1_not_here"] and x["shared_ok"] > 0 for x in corr)
        ms_, ss = statistics.mean(dps[s]), spread(*dps[s])
        d = ms_ / m1 - 1
        thr = max(FLOOR["rr"], s1, ss)
        vd = []
        for i in (0, 1):
            a = with_s3(camp, names[1][i], vecs_dir, "vecs.jsonl.gz")
            b = with_s3(camp, names[s][i], vecs_dir, "vecs.jsonl.gz")
            vd.append(G.vec_delta(a, b, measured) if a and b else {"status": "leg absent"})
        per[str(s)] = {"docs_per_s": dps[s], "mean": ms_, "spread": ss, "delta_vs_vars1": d, "threshold": thr, "beats_vars1": d > thr,
                       "correctness": {"text_chunks_identical_to_vars1": correct, "pairs": corr}, "vector_max_abs_delta_vs_vars1": vd,
                       "fired": correct and d > thr,
                       "embed_share": [L[n].get("d1", {}).get("stages", {}).get("embed", {}).get("share_of_run_total") if L[n].get("d1") else None for n in names[s]],
                       "cpu_s_per_doc": [L[n]["cpu_s_per_doc"] for n in names[s]], "engine_cores": [L[n]["engine_cores"] for n in names[s]],
                       "memory_peak_bytes": [(L[n]["memory"] or {}).get("peak_bytes") for n in names[s]]}
    fired = [s for s in per if per[s]["fired"]]
    winner = max(fired, key=lambda s: per[s]["delta_vs_vars1"]) if fired else None
    a1 = with_s3(camp, names[1][0], vecs_dir, "vecs.jsonl.gz"); b1 = with_s3(camp, names[1][1], vecs_dir, "vecs.jsonl.gz")
    r = rec(camp, "G_smoke_C")
    out["smoke_gate"] = {"vars1": {"docs_per_s": dps[1], "mean": m1, "spread": s1,
                                   "embed_share": [L[n].get("d1", {}).get("stages", {}).get("embed", {}).get("share_of_run_total") if L[n].get("d1") else None for n in names[1]],
                                   "cpu_s_per_doc": [L[n]["cpu_s_per_doc"] for n in names[1]], "engine_cores": [L[n]["engine_cores"] for n in names[1]],
                                   "vector_max_abs_delta_run_a_vs_b": G.vec_delta(a1, b1, measured) if a1 and b1 else None},
                         "per_shape": per, "fired_shapes": fired, "winner": winner,
                         "chain_record": {"fired_shapes": r.get("fired_shapes"), "winner": r.get("winner")} if r else None,
                         "agrees_with_chain_record": bool(r) and r.get("fired_shapes") == fired and r.get("winner") == winner}
    if winner:
        w = L.get(f"p3c_t{winner}_full")
        comp = L.get("p3a_rr_full") or L.get("p3c_t1_full")
        if w and comp:
            d = P2.dps(w) / P2.dps(comp) - 1
            out["full"] = {"winner": winner, "leg": w["attempt"], "comparator": comp["attempt"], "winner_docs_per_s": P2.dps(w),
                           "comparator_docs_per_s": P2.dps(comp), "delta": d, "readable": abs(d) > FLOOR["rr"],
                           "chunk_identity_vs_comparator": P2.P1.correctness_identity(comp, w),
                           "excluded_straggler_delta": w["excluded_straggler"]["docs_per_s"] / comp["excluded_straggler"]["docs_per_s"] - 1,
                           "cpu_s_per_doc": {"winner": w["cpu_s_per_doc"], "comparator": comp["cpu_s_per_doc"]},
                           "memory": {"winner": w["memory"], "comparator": comp["memory"]}}
        else:
            out["full"] = {"status": "NOT RUN", "reason": "see master_done.json (C_FULL)"}
    else:
        out["full"] = {"status": "NOT RUN", "reason": "no shape fired"}
    return out


# ------------------------------------------------------------------ P3-D (P2-C's analysis, P3 names)
def p3d(camp: Path, L: Dict[str, Any], texts_dir: Optional[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    b = camp / "p3d_build.json"
    out["build"] = json.loads(b.read_text()) if b.exists() else {"status": "no build record"}
    out["node_gates"] = {v: rec(camp, f"G_node_D_{v}") for v in ("hybrid", "pure")}
    ev: Dict[str, List[Dict[str, Any]]] = {}
    for arm in ("fix", "hyb", "pure"):
        ev[arm] = [p50_parse_eleven(d) for d in (P2.leg_dir(camp, f"p3d_s_{arm}_{r}") for r in ("a", "b")) if d is not None]
    per: Dict[str, Any] = {}
    VAR = (("hyb", "hybrid"), ("pure", "pure"))
    if all(len(ev[a]) == 2 for a in ev) and all(x["documents"] >= 6 for a in ev for x in ev[a]):
        T = [x["p50_s"] for x in ev["fix"]]
        tm, st = statistics.mean(T), spread(*T)
        for v, name in VAR:
            vm = statistics.mean(x["p50_s"] for x in ev[v])
            per[name] = {"a": {"T_legs_p50_s": T, "T_mean_s": tm, "spread_T": st, "V_legs_p50_s": [x["p50_s"] for x in ev[v]],
                               "V_mean_s": vm, "relative_reduction": (tm - vm) / tm, "holds": (tm - vm) / tm > st}}
    else:
        for _, name in VAR:
            per[name] = {"a": {"holds": False, "status": "NOT EVALUABLE"}}
    out["eleven_detail"] = {a: [{k: x[k] for k in ("leg", "documents", "p50_s", "not_ok", "incomplete_stamps", "parse_bracket_s")} for x in ev[a]] for a in ev}
    fix = [with_s3(camp, f"p3d_fix_{r}", texts_dir, "texts.jsonl.gz") for r in ("a", "b")]
    if None not in fix and all((d / "texts.jsonl.gz").exists() for d in fix):
        measured = {r["doc"] for r in load_leg(fix[0])["rows"]}
        tika_text = set()
        for d in fix:
            tika_text |= {k for k, s in texts_of(d).items() if k in measured and s.strip()}
        for v, name in VAR:
            vd = [with_s3(camp, f"p3d_{v}_{r}", texts_dir, "texts.jsonl.gz") for r in ("a", "b")]
            if None in vd or not all((d / "texts.jsonl.gz").exists() for d in vd):
                per[name]["b"] = {"holds": False, "status": "NOT EVALUABLE (legs or texts absent)"}
                continue
            empty_v = set()
            for d in vd:
                rows = {r["doc"]: r for r in load_leg(d)["rows"]}
                t = texts_of(d)
                empty_v |= {doc for doc in measured if not rows.get(doc, {}).get("ok") or not rows.get(doc, {}).get("n_chunks") or not t.get(doc, "").strip()}
            Lv = sorted(tika_text & empty_v)
            per[name]["b"] = {"tika_extracts": len(tika_text), "variant_empty_any_run": len(empty_v), "L_V": Lv, "holds": not Lv}
    else:
        for _, name in VAR:
            per[name]["b"] = {"holds": False, "status": "NOT EVALUABLE"}
    for _, name in VAR:
        per[name]["fired"] = bool(per[name]["a"].get("holds") and per[name]["b"].get("holds"))
    fired = [n for _, n in VAR if per[n]["fired"]]
    r = rec(camp, "G_smoke_D")
    out["smoke_gate"] = {"per_variant": per, "fired_variants": fired, "chain_record_fired": r.get("fired_variants") if r else None,
                         "agrees_with_chain_record": bool(r) and r.get("fired_variants") == fired}
    corr: Dict[str, Any] = {}
    for v, name in VAR:
        for rr_ in ("a", "b"):
            ref, cand = with_s3(camp, f"p3d_fix_{rr_}", texts_dir, "texts.jsonl.gz"), with_s3(camp, f"p3d_{v}_{rr_}", texts_dir, "texts.jsonl.gz")
            if ref and cand and (ref / "texts.jsonl.gz").exists() and (cand / "texts.jsonl.gz").exists():
                corr[f"{name}_{rr_}"] = P2.correctness_texts(camp, ref, cand, f"p3d_384_{name}_{rr_}")
    out["correctness_384"] = corr
    fixs = [L.get(f"p3d_fix_{r}") for r in ("a", "b")]
    spd: Dict[str, Any] = {}
    for v, name in VAR:
        vs = [L.get(f"p3d_{v}_{r}") for r in ("a", "b")]
        if all(fixs) and all(vs):
            spd[name] = P2.abab(fixs, vs, FLOOR["rr"])
            spd[name]["parse_share"] = {"fix": [x["parse_share"] for x in fixs], name: [x["parse_share"] for x in vs]}
    out["speed_384"] = spd
    full: Dict[str, Any] = {}
    comp = next((n for n in ("p3a_rr_full", "p3d_fix_full") if L.get(n)), None)
    for v, name in VAR:
        c = L.get(f"p3d_{v}_full")
        if not c:
            full[name] = {"status": "NOT RUN", "reason": "see master_done.json (D_FULL)"}
            continue
        rc: Dict[str, Any] = {"comparator": comp}
        if comp:
            ref_d = with_s3(camp, comp, texts_dir, "texts.jsonl.gz")
            cand_d = with_s3(camp, f"p3d_{v}_full", texts_dir, "texts.jsonl.gz")
            rc["correctness"] = (P2.correctness_texts(camp, ref_d, cand_d, f"p3d_full_{name}")
                                 if (ref_d / "texts.jsonl.gz").exists() and (cand_d / "texts.jsonl.gz").exists() else {"status": "texts absent"})
            d = P2.dps(c) / P2.dps(L[comp]) - 1
            rc["speed"] = {"comparator_docs_per_s": P2.dps(L[comp]), "variant_docs_per_s": P2.dps(c), "delta": d, "readable": abs(d) > FLOOR["rr"],
                           "excluded_straggler_delta": c["excluded_straggler"]["docs_per_s"] / L[comp]["excluded_straggler"]["docs_per_s"] - 1,
                           "exceeds_little_bar": d > LITTLE, "little_bar": LITTLE}
        rc["memory"] = {"variant": c["memory"], "comparator": L[comp]["memory"] if comp else None}
        rc["parse_share"] = {"variant": c["parse_share"], "comparator": L[comp]["parse_share"] if comp else None}
        full[name] = rc
    out["full"] = full
    adopt_fast = [n for n in full if isinstance(full[n].get("speed"), dict) and full[n]["speed"]["exceeds_little_bar"] and full[n]["speed"]["readable"]
                  and (full[n].get("correctness") or {}).get("adoptable") is True]
    if not out["build"].get("gate_G_build_C_pass"):
        status = "NOT RUN (G_build_D: the image or its in-image check failed or never ran)"
    elif any((g or {}).get("outcome", "").startswith("FAIL") for g in out["node_gates"].values()) or not all(out["node_gates"].values()):
        status = "NOT RUN (G_node_D: the prototype produced no text, or its gate never ran)"
    elif all(per[n]["a"].get("status") or per[n]["b"].get("status") for _, n in VAR):
        status = "NOT EVALUABLE (the smoke gate could not be evaluated for either variant)"
    else:
        status = "NOT SUPPORTED" if adopt_fast else "SUPPORTED"
    out["verdict"] = {"little_bar": LITTLE, "variants_adoptable_and_faster_than_bar": adopt_fast, "hypothesis_gains_little": status}
    return out


LEGS = ["p3c_t1_a", "p3c_t2_a", "p3c_t4_a", "p3c_t1_b", "p3c_t2_b", "p3c_t4_b", "p3a_rr_h", "p3a_li_h", "p3a_rr_full", "p3a_li_full",
        "p3d_s_fix_a", "p3d_s_hyb_a", "p3d_s_pure_a", "p3d_s_fix_b", "p3d_s_hyb_b", "p3d_s_pure_b",
        "p3d_fix_a", "p3d_hyb_a", "p3d_pure_a", "p3d_fix_b", "p3d_hyb_b", "p3d_pure_b",
        "p3c_t1_full", "p3c_t2_full", "p3c_t4_full", "p3d_fix_full", "p3d_hyb_full", "p3d_pure_full"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--texts-dir", type=Path, default=None)
    ap.add_argument("--vecs-dir", type=Path, default=None)
    a = ap.parse_args()
    L = {n: P2.summary(a.camp, n) for n in LEGS}
    boots = sorted({x["boot_id"] for x in L.values() if x and x.get("boot_id")})
    out = {"label": "P3 docs analysis (P3-A, P3-C, P3-D), from raw leg files; gates recomputed and compared with the chain's records",
           "session": {"boot_ids": boots, "one_session": len(boots) == 1},
           "legs": {n: P2.public(x) for n, x in L.items() if x}, "legs_absent": [n for n, x in L.items() if not x],
           "P3_A": p3a(a.camp, L), "P3_C": p3c(a.camp, L, a.vecs_dir), "P3_D": p3d(a.camp, L, a.texts_dir)}
    f = a.camp / "analysis_p3docs.json"
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
