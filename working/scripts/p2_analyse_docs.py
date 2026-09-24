#!/usr/bin/env python3
"""P2-A and P2-C docs analysis (preregistration.json P2_A_docs_headline, P2_C_parser_rerun), from raw leg files only.

    p2_analyse_docs.py <campaign_dir> [--texts-dir <dir>]  -> analysis_p2docs.json (+ p2c_correctness_<label>.jsonl)

Per leg, P0/P1's loaders and definitions unchanged (p0_analyse_docs, p1_analyse_docs.leg_summary): span docs/s over
the measured rows; the excluded-straggler view; the D1 stage set on stamped RocketRide legs (parse share); engine
cores, utilisation (engine cores / 32), idle cores (32 - host busy cores, percore sampler), idle spin (measured,
never added back), CPU-s/doc; the SAMPLED memory peak inside the leg's window; lost documents; steal, MHz, CPU model,
boot id. Gates are recomputed here from the same raw files by the pre-registered rules and compared with the
records the chain decided from (gates/*.json); a disagreement is reported, never resolved silently.
Full-run texts (texts.jsonl.gz) are too large for the repository: pass --texts-dir holding <leg>/texts.jsonl.gz
(S3 copies); the 384-slice texts are in the legs themselves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import load_leg, spread as _spread  # noqa: E402
import p1_analyse_docs as P1  # noqa: E402
from p2_gates import ELEVEN, p50_parse_eleven, texts_of  # noqa: E402

FLOOR = {"rr": 0.0082, "li": 0.0987}
A_THRESHOLD = 0.85
LITTLE = 1 / (1 - 0.0551) - 1          # P2-C verdict bar (preregistration.json P2_C verdict)
VARIANTS = (("hyb", "hybrid"), ("pure", "pure"))


def spread(a: float, b: float) -> Optional[float]:
    """P0's spread; None when both runs are zero (a leg that answered nothing has no spread to report)."""
    return _spread(a, b) if (a + b) else None


def leg_dir(camp: Path, name: str) -> Optional[Path]:
    return P1.leg_dir(camp, name)


def summary(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    d = leg_dir(camp, name)
    if d is None:
        return None
    s = P1.leg_summary(d)
    g = s["_g"]
    leg = json.loads(next(d.glob("leg_*.json")).read_text())
    cost = leg.get("cost") or {}
    ph = leg.get("percore_host") or {}
    s["utilisation"] = cost.get("cpu_utilization")
    s["host_busy_cores"] = ph.get("mean_busy_cores")
    s["idle_cores"] = ph.get("idle_core_equivalents")
    s["verdict"] = leg.get("verdict")
    s["documents"] = leg.get("documents")
    rows = g["rows"]
    s["empty_docs"] = sorted(r["doc"] for r in rows if not r.get("ok") or not r.get("n_chunks"))
    s["attempt"] = d.name
    return s


def public(s: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if s is None:
        return None
    out = {k: v for k, v in s.items() if k not in ("_g", "chunks", "empty_docs")}
    out["empty_documents"] = {"n": len(s["empty_docs"]), "docs": s["empty_docs"][:200]}
    return out


def dps(s: Dict[str, Any]) -> float:
    return s["span"]["docs_per_s"]


def abab(a: List[Dict[str, Any]], b: List[Dict[str, Any]], floor: float) -> Dict[str, Any]:
    """Cell b vs cell a, two runs each: readable iff |delta| > max(floor, both spreads)."""
    va, vb = [dps(x) for x in a], [dps(x) for x in b]
    ma, mb = statistics.mean(va), statistics.mean(vb)
    sa, sb = spread(*va), spread(*vb)
    d = (mb / ma - 1) if ma else None
    thr = max(floor, sa or 0.0, sb or 0.0)
    return {"a_legs": [x["attempt"] for x in a], "b_legs": [x["attempt"] for x in b], "a_docs_per_s": va, "b_docs_per_s": vb,
            "a_mean": ma, "b_mean": mb, "a_spread": sa, "b_spread": sb, "delta_b_vs_a": d, "threshold": thr,
            "readable": (abs(d) > thr) if d is not None else False}


def correctness_texts(camp: Path, ref: Path, cand: Path, label: str) -> Dict[str, Any]:
    """P1-C's correctness definitions unchanged (preregistration.json P2_C full_run.correctness_first)."""
    tr, tc = texts_of(ref), texts_of(cand)
    gr, gc = load_leg(ref), load_leg(cand)
    docs = sorted({r["doc"] for r in gr["rows"]} | {r["doc"] for r in gc["rows"]})
    ok_r = {r["doc"] for r in gr["rows"] if r.get("ok") and r.get("n_chunks")}
    ok_c = {r["doc"] for r in gc["rows"] if r.get("ok") and r.get("n_chunks")}
    empty_r = {d for d in docs if d not in ok_r or not tr.get(d, "").strip()}
    empty_c = {d for d in docs if d not in ok_c or not tc.get(d, "").strip()}
    per = []
    for d in docs:
        ca, cb = " ".join(tr.get(d, "").split()), " ".join(tc.get(d, "").split())
        per.append({"doc": d, "ref_empty": d in empty_r, "cand_empty": d in empty_c, "ref_chars": len(ca), "cand_chars": len(cb),
                    "char_ratio": (len(cb) / len(ca)) if ca else None, "dice": P1.dice(ca, cb) if (ca or cb) else None})
    out_f = camp / f"p2c_correctness_{label}.jsonl"
    if not out_f.exists():
        out_f.write_text("".join(json.dumps(x) + "\n" for x in per))
    loses = sorted(empty_c - empty_r)
    fr, fc = ref / "texts.jsonl.gz", cand / "texts.jsonl.gz"
    return {"reference": ref.name, "candidate": cand.name, "documents": len(docs),
            "texts_sha256": {ref.name: hashlib.sha256(fr.read_bytes()).hexdigest(), cand.name: hashlib.sha256(fc.read_bytes()).hexdigest()},
            "empty": {"reference": len(empty_r), "candidate": len(empty_c)},
            "candidate_empty_where_reference_recovers": loses, "n_loses": len(loses),
            "candidate_recovers_where_reference_empty": sorted(empty_r - empty_c),
            "char_ratio": P1.dist([x["char_ratio"] for x in per if x["char_ratio"] is not None]),
            "dice": P1.dist([x["dice"] for x in per if x["dice"] is not None]),
            "failures": sorted(d for d in docs if d not in {r["doc"] for r in gc["rows"] if r.get("ok")})[:200],
            "adoptable": not loses, "per_document_file": out_f.name}


def gate_record(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    f = camp / "gates" / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


# ------------------------------------------------------------------ P2-A
def p2a(camp: Path, L: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    rr = [L[n] for n in ("p2a_rr_a", "p2a_rr_b") if L.get(n)]
    li = [L[n] for n in ("p2a_li_a", "p2a_li_b") if L.get(n)]
    if len(rr) == 2 and len(li) == 2:
        vr, vl = [dps(x) for x in rr], [dps(x) for x in li]
        ratio = statistics.mean(vr) / statistics.mean(vl)
        rec = gate_record(camp, "G_smoke_A")
        out["smoke_gate"] = {"threshold": A_THRESHOLD, "rr_docs_per_s": vr, "li_docs_per_s": vl, "rr_mean": statistics.mean(vr),
                             "li_mean": statistics.mean(vl), "ratio_rr_over_li": ratio, "fired": ratio >= A_THRESHOLD,
                             "spreads": {"rr": spread(*vr), "li": spread(*vl)}, "floors": FLOOR,
                             "known_bias": "none of the eleven is in the 384 slice; P1-B +12.6% on the 384 slice vs +128% full: the gate understates RocketRide",
                             "chain_record": ({"outcome": rec.get("outcome"), "ratio": rec.get("ratio_rr_over_li")} if rec else None),
                             "agrees_with_chain_record": bool(rec) and (rec.get("outcome") == ("FIRED" if ratio >= A_THRESHOLD else "NOT FIRED"))
                             and abs(rec.get("ratio_rr_over_li", -1) - ratio) < 1e-12}
        out["smoke_side_by_side"] = {"rr": {x["attempt"]: {"cpu_s_per_doc": x["cpu_s_per_doc"], "engine_cores": x["engine_cores"],
                                                          "utilisation": x["utilisation"], "idle_cores": x["idle_cores"],
                                                          "idle_spin_cores": x["idle_spin_cores"], "memory": x["memory"]} for x in rr},
                                     "li": {x["attempt"]: {"cpu_s_per_doc": x["cpu_s_per_doc"], "engine_cores": x["engine_cores"],
                                                          "utilisation": x["utilisation"], "idle_cores": x["idle_cores"],
                                                          "idle_spin_cores": x["idle_spin_cores"], "memory": x["memory"]} for x in li}}
        out["rr_within_session_determinism"] = P1.correctness_identity(rr[0], rr[1])
    else:
        out["smoke_gate"] = {"status": "NOT EVALUABLE", "have": [x["attempt"] for x in rr + li]}
    an_rr = [L[n] for n in ("p2a_an_rr_a", "p2a_an_rr_b") if L.get(n)]
    an_li = [L[n] for n in ("p2a_an_li_a", "p2a_an_li_b") if L.get(n)]
    if len(an_rr) == 2 and len(an_li) == 2:
        c = abab(an_li, an_rr, FLOOR["li"])
        out["anchor_96_c8"] = {"rr_one_token_vs_li_one_worker": c, "ratio_rr_over_li": c["b_mean"] / c["a_mean"],
                               "rule": "ratio reported beside max(9.87%, the four spreads); no gate",
                               "cpu_s_per_doc": {x["attempt"]: x["cpu_s_per_doc"] for x in an_rr + an_li}}
    else:
        out["anchor_96_c8"] = {"status": "NOT EVALUABLE"}
    fr, fl = L.get("p2a_rr_full"), L.get("p2a_li_full")
    if fr and fl:
        d = dps(fr) / dps(fl) - 1
        bar = FLOOR["li"]
        verdict = "EXCEEDS" if d > bar else ("FALLS SHORT" if d < -bar else "MATCHES WITHIN NOISE")
        er, el = set(fr["empty_docs"]), set(fl["empty_docs"])
        out["full"] = {
            "rr": fr["attempt"], "li": fl["attempt"], "rr_docs_per_s": dps(fr), "li_docs_per_s": dps(fl), "delta_rr_vs_li": d,
            "bar": bar, "verdict": verdict, "one_token_matches_24_worker_optimum_at_full_scale": "YES" if d >= -bar else "NO",
            "excluded_straggler": {"rr": fr["excluded_straggler"]["docs_per_s"], "li": fl["excluded_straggler"]["docs_per_s"],
                                   "delta_rr_vs_li": fr["excluded_straggler"]["docs_per_s"] / fl["excluded_straggler"]["docs_per_s"] - 1},
            "per_arm": {arm: {"cpu_s_per_doc": x["cpu_s_per_doc"], "engine_cores": x["engine_cores"], "utilisation": x["utilisation"],
                              "host_busy_cores": x["host_busy_cores"], "idle_cores": x["idle_cores"], "idle_spin_cores": x["idle_spin_cores"],
                              "memory": x["memory"], "lost_documents": x["lost_documents"], "verdict": x["verdict"]}
                        for arm, x in (("rr", fr), ("li", fl))},
            "empty_documents": {"rr": len(er), "li": len(el), "rr_only": sorted(er - el), "li_only": sorted(el - er)},
            "rule": "one run each; EXCEEDS iff delta > +9.87%, MATCHES WITHIN NOISE iff |delta| <= 9.87%, FALLS SHORT iff delta < -9.87%"}
    else:
        out["full"] = {"status": "NOT RUN", "reason": "see master_gates.jsonl (A_FULL)"}
    return out


# ------------------------------------------------------------------ P2-C
def p2c(camp: Path, L: Dict[str, Any], texts_dir: Optional[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    b = camp / "p2c_build.json"
    out["build"] = json.loads(b.read_text()) if b.exists() else {"status": "no build record"}
    out["node_gates"] = {v: gate_record(camp, f"G_node_C_{v}") for v in ("hybrid", "pure")}
    # (a) SPEED on the eleven, recomputed
    ev: Dict[str, List[Dict[str, Any]]] = {}
    for arm in ("fix", "hyb", "pure"):
        ev[arm] = [p50_parse_eleven(d) for d in (leg_dir(camp, f"p2c_s_{arm}_{r}") for r in ("a", "b")) if d is not None]
    per: Dict[str, Any] = {}
    if all(len(ev[a]) == 2 for a in ev) and all(x["documents"] >= 6 for a in ev for x in ev[a]):
        T = [x["p50_s"] for x in ev["fix"]]
        tm, st = statistics.mean(T), spread(*T)
        for v, name in VARIANTS:
            vm = statistics.mean(x["p50_s"] for x in ev[v])
            per[name] = {"a": {"T_legs_p50_s": T, "T_mean_s": tm, "spread_T": st, "V_legs_p50_s": [x["p50_s"] for x in ev[v]],
                               "V_mean_s": vm, "relative_reduction": (tm - vm) / tm, "holds": (tm - vm) / tm > st}}
    else:
        for _, name in VARIANTS:
            per[name] = {"a": {"holds": False, "status": "NOT EVALUABLE"}}
    out["eleven_detail"] = {a: [{k: x[k] for k in ("leg", "documents", "p50_s", "not_ok", "incomplete_stamps", "parse_bracket_s")} for x in ev[a]] for a in ev}
    # (b) COVERAGE on the 384 slice, recomputed
    fix = [leg_dir(camp, f"p2c_fix_{r}") for r in ("a", "b")]
    if None not in fix and all((d / "texts.jsonl.gz").exists() for d in fix):
        measured = {r["doc"] for r in load_leg(fix[0])["rows"]}
        tika_text = set()
        for d in fix:
            tika_text |= {k for k, s in texts_of(d).items() if k in measured and s.strip()}
        for v, name in VARIANTS:
            vd = [leg_dir(camp, f"p2c_{v}_{r}") for r in ("a", "b")]
            if None in vd or not all((d / "texts.jsonl.gz").exists() for d in vd):
                per[name]["b"] = {"holds": False, "status": "NOT EVALUABLE (legs or texts absent)"}
                continue
            empty_v = set()
            for d in vd:
                rows = {r["doc"]: r for r in load_leg(d)["rows"]}
                t = texts_of(d)
                empty_v |= {doc for doc in measured if not rows.get(doc, {}).get("ok") or not rows.get(doc, {}).get("n_chunks")
                            or not t.get(doc, "").strip()}
            Lv = sorted(tika_text & empty_v)
            per[name]["b"] = {"tika_extracts": len(tika_text), "variant_empty_any_run": len(empty_v), "L_V": Lv, "holds": not Lv}
    else:
        for _, name in VARIANTS:
            per[name]["b"] = {"holds": False, "status": "NOT EVALUABLE"}
    rec = gate_record(camp, "G_smoke_C")
    for _, name in VARIANTS:
        per[name]["fired"] = bool(per[name]["a"].get("holds") and per[name]["b"].get("holds"))
    fired = [n for _, n in VARIANTS if per[n]["fired"]]
    out["smoke_gate"] = {"per_variant": per, "fired_variants": fired,
                         "chain_record_fired": rec.get("fired_variants") if rec else None,
                         "agrees_with_chain_record": bool(rec) and rec.get("fired_variants") == fired,
                         "known_bias": "(a) ranks the parse bracket on the eleven tail documents at C=1; HYBRID pays PDFium and Tika on "
                                       "every fallback; (b) is decided on the 384 slice, which holds none of the eleven"}
    # correctness first on the 384 slice (context for the smoke; per run, variant vs fixed Tika of the same pair)
    corr: Dict[str, Any] = {}
    for v, name in VARIANTS:
        for r in ("a", "b"):
            ref, cand = leg_dir(camp, f"p2c_fix_{r}"), leg_dir(camp, f"p2c_{v}_{r}")
            if ref and cand and (ref / "texts.jsonl.gz").exists() and (cand / "texts.jsonl.gz").exists():
                corr[f"{name}_{r}"] = correctness_texts(camp, ref, cand, f"384_{name}_{r}")
    out["correctness_384"] = corr
    # speed on the 384 slice (typical documents; ungated), ABAB
    fixs = [L.get(f"p2c_fix_{r}") for r in ("a", "b")]
    spd: Dict[str, Any] = {}
    for v, name in VARIANTS:
        vs = [L.get(f"p2c_{v}_{r}") for r in ("a", "b")]
        if all(fixs) and all(vs):
            spd[name] = abab(fixs, vs, FLOOR["rr"])
            spd[name]["parse_share"] = {"fix": [x["parse_share"] for x in fixs], name: [x["parse_share"] for x in vs]}
            spd[name]["memory_peak_bytes"] = {x["attempt"]: (x["memory"] or {}).get("peak_bytes") for x in fixs + vs}
    out["speed_384"] = spd
    # full runs
    full: Dict[str, Any] = {}
    comp = None
    for n in ("p2a_rr_full", "p2c_fix_full"):
        if L.get(n):
            comp = n
            break
    for v, name in VARIANTS:
        c = L.get(f"p2c_{v}_full")
        if not c:
            full[name] = {"status": "NOT RUN", "reason": "see master_gates.jsonl (C_FULL)"}
            continue
        rec_c: Dict[str, Any] = {"comparator": comp}
        if comp and texts_dir:
            ref_d, cand_d = texts_dir / L[comp]["attempt"], texts_dir / c["attempt"]
            if (ref_d / "texts.jsonl.gz").exists() and (cand_d / "texts.jsonl.gz").exists():
                # the texts live in S3; the leg records are in the campaign dir: stage both into the texts dir view
                rec_c["correctness"] = correctness_texts_split(camp, leg_dir(camp, comp), ref_d, leg_dir(camp, f"p2c_{v}_full"), cand_d, f"full_{name}")
            else:
                rec_c["correctness"] = {"status": "texts absent in --texts-dir"}
        else:
            rec_c["correctness"] = {"status": "no comparator or no --texts-dir"}
        if comp:
            d = dps(c) / dps(L[comp]) - 1
            rec_c["speed"] = {"comparator_docs_per_s": dps(L[comp]), "variant_docs_per_s": dps(c), "delta": d,
                              "readable": abs(d) > FLOOR["rr"], "floor": FLOOR["rr"],
                              "excluded_straggler_delta": c["excluded_straggler"]["docs_per_s"] / L[comp]["excluded_straggler"]["docs_per_s"] - 1,
                              "exceeds_little_bar": d > LITTLE, "little_bar": LITTLE}
        rec_c["memory"] = {"variant": c["memory"], "comparator": L[comp]["memory"] if comp else None}
        rec_c["parse_share"] = {"variant": c["parse_share"], "comparator": L[comp]["parse_share"] if comp else None}
        full[name] = rec_c
    out["full"] = full
    adoptable_faster = [n for n in full if isinstance(full[n].get("speed"), dict) and full[n]["speed"]["exceeds_little_bar"]
                        and full[n]["speed"]["readable"] and (full[n].get("correctness") or {}).get("adoptable") is True]
    if not out["build"].get("gate_G_build_C_pass"):
        status = "NOT RUN (G_build_C: the image or its in-image check failed or never ran)"
    elif any((g or {}).get("outcome", "").startswith("FAIL") for g in out["node_gates"].values()) or not all(out["node_gates"].values()):
        status = "NOT RUN (G_node_C: the prototype node did not produce text, or its gate never ran)"
    elif all(per[n]["a"].get("status") or per[n]["b"].get("status") for _, n in VARIANTS):
        status = "NOT EVALUABLE (the smoke gate could not be evaluated for either variant)"
    else:
        status = "NOT SUPPORTED" if adoptable_faster else "SUPPORTED"
    out["verdict"] = {"little_bar": LITTLE, "variants_adoptable_and_faster_than_bar": adoptable_faster,
                      "hypothesis_gains_little": status,
                      "rule": "SUPPORTED iff no variant is both ADOPTABLE and faster than fixed Tika at full scale by more than 5.83% "
                              "(readable beyond 0.82%), including the case where no variant's smoke gate fires"}
    return out


def correctness_texts_split(camp: Path, ref_leg: Path, ref_texts: Path, cand_leg: Path, cand_texts: Path, label: str) -> Dict[str, Any]:
    """correctness_texts with the leg records from the campaign dir and the texts from the S3 copy."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        r, c = Path(t) / ref_leg.name, Path(t) / cand_leg.name
        shutil.copytree(ref_leg, r)
        shutil.copytree(cand_leg, c)
        for src, dst in ((ref_texts, r), (cand_texts, c)):
            if not (dst / "texts.jsonl.gz").exists():
                shutil.copy(src / "texts.jsonl.gz", dst / "texts.jsonl.gz")
        return correctness_texts(camp, r, c, label)


LEGS = ["p2a_rr_a", "p2a_li_a", "p2a_rr_b", "p2a_li_b", "p2a_an_rr_a", "p2a_an_li_a", "p2a_an_rr_b", "p2a_an_li_b",
        "p2c_s_fix_a", "p2c_s_hyb_a", "p2c_s_pure_a", "p2c_s_fix_b", "p2c_s_hyb_b", "p2c_s_pure_b",
        "p2c_fix_a", "p2c_hyb_a", "p2c_pure_a", "p2c_fix_b", "p2c_hyb_b", "p2c_pure_b",
        "p2a_rr_full", "p2a_li_full", "p2c_fix_full", "p2c_hyb_full", "p2c_pure_full"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--texts-dir", type=Path, default=None)
    a = ap.parse_args()
    L = {n: summary(a.camp, n) for n in LEGS}
    boots = sorted({x["boot_id"] for x in L.values() if x and x.get("boot_id")})
    out = {"label": "P2 docs analysis (P2-A, P2-C), from raw leg files; gates recomputed and compared with the chain's records",
           "session": {"boot_ids": boots, "one_session": len(boots) == 1},
           "legs": {n: public(x) for n, x in L.items() if x}, "legs_absent": [n for n, x in L.items() if not x],
           "P2_A": p2a(a.camp, L), "P2_C": p2c(a.camp, L, a.texts_dir)}
    f = a.camp / "analysis_p2docs.json"
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
