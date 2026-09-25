#!/usr/bin/env python3
"""P4-B laptop items (1) and (2), from COMMITTED leg files only (preregistration.json P4_B_laptop).

    p4_analyse_b.py <p4_campaign_dir>  -> analysis_p4b.json

(1) POST-HOC VALIDATION of steady-phase docs/s as a smoke metric: P0's definition (p0_analyse_docs.drain on the leg's
    measured rows) on the 384-slice legs of P2-A, P3-A health and P3-C smoke; check 1 (per-session RR/LI ratio agrees with
    P3-A's full-scale ratio within 8.19%, both sessions) and check 2 (vars=4 slower than vars=1 on the slice).
(2) PARSER CLOSE-OUT: HYBRID (p3d_hyb_full) against fixed Tika (p3a_rr_full): docs/s, chunks, chunks/s, CPU-s per chunk,
    chunks per ok document, and the log decomposition of HYBRID's docs/s gain into fewer chunks and chunk throughput.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import drain, load_leg, spread  # noqa: E402  (gzip-aware: rows_of)

RES = Path(__file__).resolve().parents[2] / "working" / "results"
P2 = RES / "parity_p2_20260924T160106Z"
P3 = RES / "parity_p3_20260925T035027Z"
AGREE = 0.0819
FLOOR = 0.0082


def steady(d: Path) -> Dict[str, Any]:
    g = load_leg(d)
    dr = drain(g["rows"])
    return {"leg": d.name, "rows": len(g["rows"]), "ok": sum(1 for r in g["rows"] if r.get("ok")),
            "span_docs_per_s": g["span"]["docs_per_s"], "steady_docs_per_s": dr["steady_docs_per_s"],
            "last_submit_s": dr["last_submit_s"], "span_s": dr["span_s"], "drain_share_of_span": dr["drain_share_of_span"],
            "completed_ok_by_last_submit": round(dr["steady_docs_per_s"] * dr["last_submit_s"]) if dr["steady_docs_per_s"] else None}


def item1(r_full: float) -> Dict[str, Any]:
    legs = {n: steady(P2 / n) for n in ("p2a_rr_a", "p2a_rr_b", "p2a_li_a", "p2a_li_b")}
    legs.update({n: steady(P3 / n) for n in ("p3a_rr_h", "p3a_li_h", "p3c_t1_a", "p3c_t1_b", "p3c_t2_a", "p3c_t2_b",
                                             "p3c_t4_a", "p3c_t4_b")})
    s = {k: v["steady_docs_per_s"] for k, v in legs.items()}
    sp = {k: v["span_docs_per_s"] for k, v in legs.items()}
    p2_ratio = statistics.mean([s["p2a_rr_a"], s["p2a_rr_b"]]) / statistics.mean([s["p2a_li_a"], s["p2a_li_b"]])
    p3_ratio = s["p3a_rr_h"] / s["p3a_li_h"]
    sess = {"P2-A": {"steady_ratio": p2_ratio, "rel_to_full_minus_1": p2_ratio / r_full - 1},
            "P3-A health": {"steady_ratio": p3_ratio, "rel_to_full_minus_1": p3_ratio / r_full - 1}}
    for v in sess.values():
        v["agrees"] = abs(v["rel_to_full_minus_1"]) <= AGREE
    sess["P2-A"]["span_ratio_beside"] = statistics.mean([sp["p2a_rr_a"], sp["p2a_rr_b"]]) / statistics.mean([sp["p2a_li_a"], sp["p2a_li_b"]])
    sess["P3-A health"]["span_ratio_beside"] = sp["p3a_rr_h"] / sp["p3a_li_h"]
    check1 = all(v["agrees"] for v in sess.values())
    shapes = {}
    for t in (1, 2, 4):
        v = [s[f"p3c_t{t}_a"], s[f"p3c_t{t}_b"]]
        w = [sp[f"p3c_t{t}_a"], sp[f"p3c_t{t}_b"]]
        shapes[f"vars={t}"] = {"steady_mean": statistics.mean(v), "steady_spread": spread(*v),
                               "span_mean_beside": statistics.mean(w), "span_spread_beside": spread(*w)}
    d4 = shapes["vars=4"]["steady_mean"] / shapes["vars=1"]["steady_mean"] - 1
    thr = max(FLOOR, shapes["vars=1"]["steady_spread"], shapes["vars=4"]["steady_spread"])
    check2 = shapes["vars=4"]["steady_mean"] < shapes["vars=1"]["steady_mean"]
    fails = [n for n, ok in (("check 1 (the per-session steady RR/LI ratio agrees with the full-scale ratio within 8.19%)", check1),
                             ("check 2 (vars=4 slower than vars=1 on the slice's steady phase)", check2)) if not ok]
    return {"label": "POST-HOC VALIDATION (committed legs; the rule was fixed in preregistration.json before these figures were computed)",
            "definition": "P0 steady-phase docs/s = ok documents completed by the last submission / (last submission - first submission)",
            "full_scale_ratio": r_full, "agree_bound": AGREE, "legs": legs,
            "check_1": {"sessions": sess, "pass": check1},
            "check_2": {"shapes": shapes, "vars4_vs_vars1_steady_minus_1": d4, "threshold_beside": thr,
                        "beyond_threshold_beside": abs(d4) > thr, "pass": check2,
                        "full_scale_sign": "vars=4 slower (P3-C full: -4.56%)"},
            "verdict": "VALIDATES" if not fails else "DOES NOT VALIDATE", "failed_checks": fails}


def item2() -> Dict[str, Any]:
    out = {}
    for tag, d in (("FIX", P3 / "p3a_rr_full"), ("HYB", P3 / "p3d_hyb_full")):
        g = load_leg(d)
        leg = json.loads(next(d.glob("leg_*.json")).read_text())
        ok = [r for r in g["rows"] if r.get("ok")]
        chunks = sum(r.get("n_chunks") or 0 for r in ok)
        span = g["span"]["span_s"]
        cpu = leg["cost"]["cpu_s"]
        out[tag] = {"leg": d.name, "rows": len(g["rows"]), "ok": len(ok), "span_s": span, "docs_per_s": g["span"]["docs_per_s"],
                    "chunks": chunks, "chunks_per_s": chunks / span, "cpu_s": cpu, "cpu_s_per_chunk": cpu / chunks,
                    "cpu_s_per_doc": leg["cost"]["cpu_s_per_doc"], "chunks_per_ok_doc": chunks / len(ok),
                    "boot_id": g.get("boot_id")}
    f, h = out["FIX"], out["HYB"]
    r_docs = h["docs_per_s"] / f["docs_per_s"]
    r_cpd = h["chunks_per_ok_doc"] / f["chunks_per_ok_doc"]
    r_chunks = h["chunks_per_s"] / f["chunks_per_s"]
    return {"label": "P4-B (2) parser close-out, from P3's committed full legs (same session)", "legs": out,
            "R_docs": r_docs, "R_chunks_per_ok_doc": r_cpd, "R_chunks_per_s": r_chunks,
            "R_cpu_s_per_chunk": h["cpu_s_per_chunk"] / f["cpu_s_per_chunk"],
            "identity_check_R_docs_eq_R_chunks_over_R_cpd": r_chunks / r_cpd,
            "docs_gain": r_docs - 1, "chunks_fewer": 1 - h["chunks"] / f["chunks"],
            "share_of_gain_from_fewer_chunks": math.log(1 / r_cpd) / math.log(r_docs),
            "share_of_gain_from_chunk_throughput": math.log(r_chunks) / math.log(r_docs)}


def main() -> int:
    camp = Path(sys.argv[1])
    a = json.loads((P3 / "analysis_p3docs.json").read_text())
    r_full = a["P3_A"]["full"]["ratio_rr_over_li"]
    out = {"item1_steady_phase": item1(r_full), "item2_parser_close_out": item2()}
    (camp / "analysis_p4b.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    i1, i2 = out["item1_steady_phase"], out["item2_parser_close_out"]
    print(f"(1) {i1['verdict']} {i1['failed_checks']}; (2) docs +{i2['docs_gain']:.4f}, fewer-chunks share {i2['share_of_gain_from_fewer_chunks']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
