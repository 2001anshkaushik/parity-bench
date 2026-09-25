#!/usr/bin/env python3
"""P3 gates, computed exactly as preregistration.json states them; the chains and the master decide from these exit
codes and records. Every gate here has a positive and a null control run WHOLE on the box before launch
(p3_gate_controls.sh; the GATE CONTROLS rule).

    p3_gates.py memstat   <camp> <leg>                         G_memstat: the leg's memstat.jsonl has >= 1 row
    p3_gates.py mandate   <leg_dir>                            docs D0: exit 1 iff a leg_*.json records a mandate violation
    p3_gates.py mandate_v <leg_dir>                            video D0: exit 1 iff MANDATE_VIOLATION.json exists
    p3_gates.py alone                                          exit 1 iff any container exists (P3-B: every cell alone)
    p3_gates.py health_a  <camp> <ref_leg_dir> [<ref_leg_dir>] G_health_A (P3-A health smoke)
    p3_gates.py smoke_c   <camp>                               G_smoke_C (P3-C thread shapes: correctness, then speed)
    p3_gates.py node_d    <camp> <leg> <variant>               G_node_D (the prototype node's counters: docs >= 1, text >= 1)
    p3_gates.py smoke_d   <camp>                               G_smoke_D (P3-D: P2-C's per-variant speed-and-coverage gate)

Exit 0 = PASS / FIRED / clean, 1 = FAIL / NOT FIRED / violation, 2 = evidence missing or not evaluable. Gate records
go to <camp>/gates/<gate>.json, create-only. smoke_c and smoke_d exit 0 when they evaluated (the record names the
fired shape / variants, possibly none) and 2 when they could not.
"""
from __future__ import annotations

import base64
import gzip
import json
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import load_leg, rr_stage_rows, spread  # noqa: E402
from p2_gates import ELEVEN, leg_dir, p50_parse_eleven, texts_of  # noqa: E402
import p2_gates  # noqa: E402

FLOOR_RR = 0.0082
SHAPES = (1, 2, 4)
D_VARIANTS = ("hyb", "pure")
D_NAME = {"hyb": "hybrid", "pure": "pure"}


def record(camp: Path, gate: str, out: Dict[str, Any]) -> None:
    g = camp / "gates"
    g.mkdir(exist_ok=True)
    out = {"gate": gate, "decided_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **out}
    with open(g / f"{gate}.json", "x") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else "…") for k, v in out.items()}))


# ------------------------------------------------------------------ small gates
def mandate(d: Path) -> int:
    legs = list(d.glob("leg_*.json"))
    if not legs:
        print(f"no leg record in {d}")
        return 2
    for f in legs:
        m = ((json.loads(f.read_text()).get("p0") or {}).get("mandate") or {})
        if m.get("mandate_violation"):
            print(f"MANDATE VIOLATION in {f}: {m.get('violations')}")
            return 1
    print(f"D0 clean: {d.name}")
    return 0


def mandate_v(d: Path) -> int:
    if (d / "MANDATE_VIOLATION.json").exists():
        print(f"MANDATE VIOLATION in {d}")
        return 1
    print(f"D0 clean: {d.name}")
    return 0


def alone() -> int:
    out = subprocess.run(["docker", "ps", "-aq"], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"docker ps failed: {out.stderr.strip()}")
        return 2
    n = len([x for x in out.stdout.split() if x.strip()])
    print(f"containers present: {n}")
    return 0 if n == 0 else 1


# ------------------------------------------------------------------ G_health_A
def leg_health(d: Path) -> Dict[str, Any]:
    leg = json.loads(next(d.glob("leg_*.json")).read_text())
    docs = leg.get("documents") or {}
    v = leg.get("verdict")
    rows_all = docs.get("submitted") is not None and docs.get("recorded") == docs.get("submitted")
    ms = d / "memstat.jsonl"
    n_ms = sum(1 for x in ms.read_text().splitlines() if x.strip()) if ms.exists() else 0
    m = ((leg.get("p0") or {}).get("mandate") or {})
    return {"leg": d.name, "arm": leg.get("arm"), "verdict": v, "documents": docs,
            "verdict_ok": v == "OK" or (v == "DEGRADED" and rows_all), "memstat_rows": n_ms,
            "d0_clean": not m.get("mandate_violation"), "violations": m.get("violations")}


def chunks_ok(d: Path) -> Dict[str, List[str]]:
    return {r["doc"]: r.get("chunk_sha256") for r in load_leg(d)["rows"] if r.get("ok")}


def health_a(camp: Path, refs: List[Path]) -> int:
    rr, li = leg_dir(camp, "p3a_rr_h"), leg_dir(camp, "p3a_li_h")
    if rr is None or li is None or not all(r.is_dir() for r in refs):
        record(camp, "G_health_A", {"outcome": "NOT EVALUABLE", "missing": [n for n, x in (("p3a_rr_h", rr), ("p3a_li_h", li)) if x is None]})
        return 2
    h = {"rr": leg_health(rr), "li": leg_health(li)}
    ours = chunks_ok(rr)
    ident = []
    for ref in refs:
        theirs = chunks_ok(ref)
        shared = sorted(set(ours) & set(theirs))
        differ = [k for k in shared if ours[k] != theirs[k]]
        ident.append({"reference": f"{ref.parent.name}/{ref.name}", "shared_ok_documents": len(shared), "chunk_lists_differ": differ,
                      "ok_in_reference_not_here": sorted(set(theirs) - set(ours)), "identical": not differ and len(shared) > 0})
    conds = {"both_verdicts_ok_or_degraded_with_all_rows": h["rr"]["verdict_ok"] and h["li"]["verdict_ok"],
             "d0_clean": h["rr"]["d0_clean"] and h["li"]["d0_clean"],
             "memory_sampler_non_empty": h["rr"]["memstat_rows"] >= 1 and h["li"]["memstat_rows"] >= 1,
             "rr_chunks_identical_to_p2a_on_shared_documents": all(x["identical"] for x in ident)}
    fired = all(conds.values())
    record(camp, "G_health_A", {"rule": "HEALTH gate (Ansh's ruling: not a performance proxy): FIRES iff both legs are verdict OK or "
                                         "DEGRADED with every row, D0 is clean, the memory sampler is non-empty on both, and the RR "
                                         "leg's chunk lists equal P2-A's committed rr:p1-tikafix legs on every shared ok document",
                                "legs": h, "identity": ident, "conditions": conds, "outcome": "FIRED" if fired else "NOT FIRED"})
    return 0 if fired else 1


# ------------------------------------------------------------------ G_smoke_C (thread shapes)
def vecs_of(d: Path) -> Optional[Dict[str, List[Optional[List[float]]]]]:
    f = d / "vecs.jsonl.gz"
    if not f.exists():
        return None
    out: Dict[str, List[Optional[List[float]]]] = {}
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for line in fh:
            j = json.loads(line)
            out[j["doc"]] = [list(struct.unpack(f"<{len(base64.b64decode(v)) // 4}f", base64.b64decode(v))) if v else None
                             for v in j["vecs"]]
    return out


def vec_delta(a: Path, b: Path, measured: set) -> Dict[str, Any]:
    va, vb = vecs_of(a), vecs_of(b)
    if va is None or vb is None:
        return {"status": f"vectors absent ({a.name}: {va is not None}, {b.name}: {vb is not None})"}
    mx, n_chunks, n_docs, skipped = 0.0, 0, 0, []
    for doc in sorted(measured & set(va) & set(vb)):
        xa, xb = va[doc], vb[doc]
        if len(xa) != len(xb):
            skipped.append(doc)
            continue
        n_docs += 1
        for u, w in zip(xa, xb):
            if u is None or w is None or len(u) != len(w):
                continue
            n_chunks += 1
            mx = max(mx, max(abs(p - q) for p, q in zip(u, w)))
    return {"a": a.name, "b": b.name, "documents_compared": n_docs, "chunks_compared": n_chunks,
            "max_abs_delta": mx if n_chunks else None, "skipped_chunk_count_differs": skipped}


def smoke_c(camp: Path) -> int:
    L = {s: [leg_dir(camp, f"p3c_t{s}_{r}") for r in ("a", "b")] for s in SHAPES}
    if any(x is None for s in SHAPES for x in L[s]):
        record(camp, "G_smoke_C", {"outcome": "NOT EVALUABLE", "missing": [f"p3c_t{s}_{r}" for s in SHAPES for r, x in zip("ab", L[s]) if x is None]})
        return 2
    G = {s: [load_leg(x) for x in L[s]] for s in SHAPES}
    dps = {s: [g["span"]["docs_per_s"] for g in G[s]] for s in SHAPES}
    chunks = {s: [{r["doc"]: r.get("chunk_sha256") for r in g["rows"] if r.get("ok")} for g in G[s]] for s in SHAPES}
    measured = {r["doc"] for r in G[1][0]["rows"]}
    m1, s1 = statistics.mean(dps[1]), spread(*dps[1])
    per: Dict[str, Any] = {}
    for s in SHAPES[1:]:
        corr = []
        for i, r in enumerate("ab"):
            for j, r1 in enumerate("ab"):
                ca, cb = chunks[1][j], chunks[s][i]
                shared = sorted(set(ca) & set(cb))
                corr.append({"shape_leg": L[s][i].name, "vars1_leg": L[1][j].name, "shared_ok": len(shared),
                             "chunk_lists_differ": [k for k in shared if ca[k] != cb[k]],
                             "ok_in_vars1_not_here": sorted(set(ca) - set(cb))})
        correct = all(not x["chunk_lists_differ"] and not x["ok_in_vars1_not_here"] and x["shared_ok"] > 0 for x in corr)
        ms_, ss = statistics.mean(dps[s]), spread(*dps[s])
        d = ms_ / m1 - 1
        thr = max(FLOOR_RR, s1, ss)
        per[str(s)] = {"docs_per_s": dps[s], "mean": ms_, "spread": ss, "delta_vs_vars1": d, "threshold": thr,
                       "beats_vars1": d > thr, "correctness": {"text_chunks_identical_to_vars1": correct, "pairs": corr},
                       "vector_max_abs_delta_vs_vars1": [vec_delta(L[1][i], L[s][i], measured) for i in (0, 1)],
                       "fired": correct and d > thr}
    fired = [s for s in per if per[s]["fired"]]
    winner = max(fired, key=lambda s: per[s]["delta_vs_vars1"]) if fired else None
    record(camp, "G_smoke_C", {
        "rule": "correctness first: a shape counts only if its text chunks equal vars=1's on every shared ok document (both runs "
                "against both vars=1 runs) and it loses none; then it FIRES iff mean(shape)/mean(vars=1) - 1 > max(0.82%, spread "
                "vars=1, spread shape); the winner is the fired shape with the largest gain",
        "vars1": {"docs_per_s": dps[1], "mean": m1, "spread": s1,
                  "vector_max_abs_delta_run_a_vs_b": vec_delta(L[1][0], L[1][1], measured)},
        "per_shape": per, "fired_shapes": fired, "winner": winner, "outcome": "EVALUATED"})
    return 0


# ------------------------------------------------------------------ G_node_D, G_smoke_D (P2-C's gates, P3-D names)
def node_d(camp: Path, leg: str, variant: str) -> int:
    f = camp / leg / f"p1_pdfium_{variant}.json"
    c = json.loads(f.read_text()) if f.exists() else None
    ok = bool(c and c.get("docs", 0) >= 1 and c.get("text", 0) >= 1)
    record(camp, f"G_node_D_{variant}", {"leg": leg, "counters_file": f.name, "counters": c,
                                         "rule": "the prototype node's own counters show docs >= 1 and text >= 1",
                                         "outcome": "PASS" if ok else "FAIL — the prototype did not run; P3-D stops"})
    return 0 if ok else 1


def smoke_d(camp: Path) -> int:
    a: Dict[str, Any] = {}
    for arm in ("fix",) + D_VARIANTS:
        a[arm] = []
        for r in ("a", "b"):
            d = leg_dir(camp, f"p3d_s_{arm}_{r}")
            if d is None:
                record(camp, "G_smoke_D", {"outcome": "NOT EVALUABLE", "missing": f"p3d_s_{arm}_{r}"})
                return 2
            a[arm].append(p50_parse_eleven(d))
    degenerate = [x["leg"] for arm in a for x in a[arm] if x["documents"] < 6]
    evaluable_a = not degenerate and all(x["p50_s"] is not None for arm in a for x in a[arm])
    T = [x["p50_s"] for x in a["fix"]]
    tm = statistics.mean(T) if evaluable_a else None
    st = spread(*T) if evaluable_a else None
    per: Dict[str, Any] = {}
    for v in D_VARIANTS:
        if evaluable_a:
            vm = statistics.mean(x["p50_s"] for x in a[v])
            rel = (tm - vm) / tm
            per[v] = {"a": {"T_mean_s": tm, "T_legs_p50_s": T, "spread_T": st, "V_mean_s": vm,
                            "V_legs_p50_s": [x["p50_s"] for x in a[v]], "relative_reduction": rel, "holds": rel > st}}
        else:
            per[v] = {"a": {"holds": False, "status": f"NOT EVALUABLE (fewer than 6 of the eleven stamped in {degenerate})"}}
    try:
        fixd = [leg_dir(camp, f"p3d_fix_{r}") for r in ("a", "b")]
        if None in fixd:
            raise FileNotFoundError("p3d_fix_a/b")
        measured = {r["doc"] for r in load_leg(fixd[0])["rows"]}
        tika_text = set()
        for d in fixd:
            tika_text |= {k for k, s in texts_of(d).items() if k in measured and s.strip()}
        for v in D_VARIANTS:
            vd = [leg_dir(camp, f"p3d_{v}_{r}") for r in ("a", "b")]
            if None in vd:
                raise FileNotFoundError(f"p3d_{v}_a/b")
            empty_v = set()
            for d in vd:
                rows = {r["doc"]: r for r in load_leg(d)["rows"]}
                t = texts_of(d)
                for doc in measured:
                    r = rows.get(doc)
                    if r is None or not r.get("ok") or not r.get("n_chunks") or not t.get(doc, "").strip():
                        empty_v.add(doc)
            Lv = sorted(tika_text & empty_v)
            per[v]["b"] = {"tika_extracts": len(tika_text), "variant_empty_any_run": len(empty_v), "L_V": Lv, "holds": not Lv}
    except FileNotFoundError as e:
        for v in D_VARIANTS:
            per[v].setdefault("b", {"holds": False, "status": f"NOT EVALUABLE ({e})"})
    fired = [D_NAME[v] for v in D_VARIANTS if per[v]["a"].get("holds") and per[v].get("b", {}).get("holds")]
    for v in D_VARIANTS:
        per[v]["fired"] = D_NAME[v] in fired
    record(camp, "G_smoke_D", {
        "rule": "P2-C's gate unchanged (preregistration.json P3_D): per variant, FIRES iff (a) (T - V)/T > spread_T on the p50 parse "
                "bracket over the eleven at C=1 AND (b) L_V is empty on the 384 slice",
        "per_variant": per, "eleven_detail": a, "fired_variants": fired,
        "known_bias": "(a) ranks the parse bracket on the eleven tail documents at C=1; HYBRID pays PDFium and Tika on every fallback; "
                      "(b) is decided on the 384 slice, which holds none of the eleven",
        "outcome": "EVALUATED"})
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    try:
        if cmd == "memstat":
            return p2_gates.memstat(Path(sys.argv[2]), sys.argv[3])
        if cmd == "mandate":
            return mandate(Path(sys.argv[2]))
        if cmd == "mandate_v":
            return mandate_v(Path(sys.argv[2]))
        if cmd == "alone":
            return alone()
        if cmd == "health_a":
            return health_a(Path(sys.argv[2]), [Path(x) for x in sys.argv[3:]])
        if cmd == "smoke_c":
            return smoke_c(Path(sys.argv[2]))
        if cmd == "node_d":
            return node_d(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        if cmd == "smoke_d":
            return smoke_d(Path(sys.argv[2]))
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
