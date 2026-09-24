#!/usr/bin/env python3
"""P2 gates, computed exactly as preregistration.json states them; the chains and the master decide from
these exit codes and records, never from a figure typed by hand.

    p2_gates.py memstat  <campaign_dir> <leg>             G_memstat: the leg's memstat.jsonl has >= 1 row
    p2_gates.py a_smoke  <campaign_dir>                   G_smoke_A (P2_A_docs_headline.SMOKE_GATE_P2_A)
    p2_gates.py node_c   <campaign_dir> <leg> <variant>   G_node_C: the prototype node's counters show docs >= 1, text >= 1
    p2_gates.py c_smoke  <campaign_dir>                   G_smoke_C per variant ((a) SPEED and (b) COVERAGE)
    p2_gates.py manip_b  <campaign_dir> <leg> base|comb   G_manip_B: the in-process read-back shows the cell

Exit 0 = PASS / FIRED, 1 = FAIL / NOT FIRED, 2 = evidence missing or not evaluable. Each call writes ONE record,
gates/<gate>.json, create-only (a gate is decided once; a second decision on the same name refuses).
c_smoke exits 0 when it evaluated (its record lists fired_variants, possibly empty) and 2 when it could not.
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_docs import load_leg, rr_stage_rows, spread  # noqa: E402

ELEVEN = {"011_011464.pdf", "039_039660.pdf", "008_008871.pdf", "011_011730.pdf", "014_014261.pdf",
          "000_000344.pdf", "031_031239.pdf", "002_002489.pdf", "034_034697.pdf", "033_033172.pdf",
          "014_014969.pdf"}
FLOOR = {"rr": 0.0082, "li": 0.0987}
A_THRESHOLD = 0.85
VARIANTS = ("hyb", "pure")
VARIANT_NAME = {"hyb": "hybrid", "pure": "pure"}


def leg_dir(camp: Path, name: str) -> Optional[Path]:
    """The pre-registered leg: its first attempt that has a leg record, else a retry (<leg>_r1, <leg>_r2)."""
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and list(d.glob("leg_*.json")) and (list(d.glob("perdoc_*.jsonl")) or list(d.glob("perdoc_*.jsonl.gz"))):
            return d
    return None


def record(camp: Path, gate: str, out: Dict[str, Any]) -> None:
    g = camp / "gates"
    g.mkdir(exist_ok=True)
    out = {"gate": gate, "decided_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **out}
    with open(g / f"{gate}.json", "x") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else "…") for k, v in out.items()}))


# ------------------------------------------------------------------ G_memstat
def memstat(camp: Path, leg: str) -> int:
    d = camp / leg
    f = d / "memstat.jsonl"
    n = sum(1 for x in f.read_text().splitlines() if x.strip()) if f.exists() else 0
    ok = n >= 1
    record(camp, f"G_memstat_{leg}", {"leg": leg, "file": "memstat.jsonl", "exists": f.exists(), "rows": n,
                                      "rule": "the first leg's memstat.jsonl has >= 1 row (register 55)",
                                      "outcome": "PASS" if ok else "FAIL"})
    return 0 if ok else 1


# ------------------------------------------------------------------ G_smoke_A
def a_smoke(camp: Path) -> int:
    v: Dict[str, List[float]] = {"rr": [], "li": []}
    legs: Dict[str, List[str]] = {"rr": [], "li": []}
    for arm in ("rr", "li"):
        for r in ("a", "b"):
            d = leg_dir(camp, f"p2a_{arm}_{r}")
            if d is None:
                record(camp, "G_smoke_A", {"outcome": "NOT EVALUABLE", "missing": f"p2a_{arm}_{r}"})
                return 2
            g = load_leg(d)
            v[arm].append(g["span"]["docs_per_s"])
            legs[arm].append(d.name)
    mr, ml = statistics.mean(v["rr"]), statistics.mean(v["li"])
    ratio = mr / ml
    fired = ratio >= A_THRESHOLD
    record(camp, "G_smoke_A", {
        "rule": "FIRES iff mean(RR span docs/s, p2a_rr_a/b) >= 0.85 x mean(LI span docs/s, p2a_li_a/b)",
        "threshold": A_THRESHOLD, "legs": legs, "rr_docs_per_s": v["rr"], "li_docs_per_s": v["li"],
        "rr_mean": mr, "li_mean": ml, "ratio_rr_over_li": ratio,
        "spreads": {"rr": spread(*v["rr"]), "li": spread(*v["li"])}, "floors": FLOOR,
        "known_bias": "none of the eleven pathological PDFs is in the 384 slice; P1-B gained +12.6% on the 384 slice vs "
                      "+128% on the full corpus, so this gate understates RocketRide (recorded; the gate stands as written)",
        "outcome": "FIRED" if fired else "NOT FIRED"})
    return 0 if fired else 1


# ------------------------------------------------------------------ G_node_C
def node_c(camp: Path, leg: str, variant: str) -> int:
    f = camp / leg / f"p1_pdfium_{variant}.json"
    c = json.loads(f.read_text()) if f.exists() else None
    ok = bool(c and c.get("docs", 0) >= 1 and c.get("text", 0) >= 1)
    record(camp, f"G_node_C_{variant}", {"leg": leg, "counters_file": f.name, "counters": c,
                                         "rule": "the prototype node's own counters show docs >= 1 and text >= 1",
                                         "outcome": "PASS" if ok else "FAIL — the prototype did not run (P1's failure mode); P2-C stops"})
    return 0 if ok else 1


# ------------------------------------------------------------------ G_smoke_C
def p50_parse_eleven(d: Path) -> Dict[str, Any]:
    g = load_leg(d)
    ok_rows = [r for r in g["rows"] if r.get("ok")]
    sr, incomplete = rr_stage_rows(dict(g, rows=ok_rows))
    pb = {x["doc"]: x["parse_bracket"] for x in sr if x["doc"] in ELEVEN}
    return {"leg": d.name, "documents": len(pb), "not_ok": sorted(r["doc"] for r in g["rows"] if not r.get("ok")),
            "incomplete_stamps": incomplete, "parse_bracket_s": pb,
            "p50_s": statistics.median(pb.values()) if pb else None}


def texts_of(d: Path) -> Dict[str, str]:
    f = d / "texts.jsonl.gz"
    if not f.exists():
        raise FileNotFoundError(f"{d.name}/texts.jsonl.gz")
    out: Dict[str, str] = {}
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for line in fh:
            j = json.loads(line)
            out[j["doc"]] = "".join(j["texts"])
    return out


def c_smoke(camp: Path) -> int:
    # (a) SPEED, the eleven at C=1
    a: Dict[str, Any] = {}
    for arm in ("fix",) + VARIANTS:
        a[arm] = []
        for r in ("a", "b"):
            d = leg_dir(camp, f"p2c_s_{arm}_{r}")
            if d is None:
                record(camp, "G_smoke_C", {"outcome": "NOT EVALUABLE", "missing": f"p2c_s_{arm}_{r}"})
                return 2
            a[arm].append(p50_parse_eleven(d))
    degenerate = [x["leg"] for arm in a for x in a[arm] if x["documents"] < 6]
    T = [x["p50_s"] for x in a["fix"]]
    per: Dict[str, Any] = {}
    evaluable_a = not degenerate and all(x["p50_s"] is not None for arm in a for x in a[arm])
    tm = statistics.mean(T) if evaluable_a else None
    st = spread(*T) if evaluable_a else None
    for v in VARIANTS:
        if evaluable_a:
            vm = statistics.mean(x["p50_s"] for x in a[v])
            rel = (tm - vm) / tm
            per[v] = {"a": {"T_mean_s": tm, "T_legs_p50_s": T, "spread_T": st, "V_mean_s": vm,
                            "V_legs_p50_s": [x["p50_s"] for x in a[v]], "relative_reduction": rel,
                            "holds": rel > st}}
        else:
            per[v] = {"a": {"holds": False, "status": f"NOT EVALUABLE (fewer than 6 of the eleven stamped in {degenerate})"}}
    # (b) COVERAGE on the 384 slice
    try:
        fixd = [leg_dir(camp, f"p2c_fix_{r}") for r in ("a", "b")]
        if None in fixd:
            raise FileNotFoundError("p2c_fix_a/b")
        measured = {r["doc"] for r in load_leg(fixd[0])["rows"]}
        tika_text = set()
        for d in fixd:
            t = texts_of(d)
            tika_text |= {k for k, s in t.items() if k in measured and s.strip()}
        for v in VARIANTS:
            vd = [leg_dir(camp, f"p2c_{v}_{r}") for r in ("a", "b")]
            if None in vd:
                raise FileNotFoundError(f"p2c_{v}_a/b")
            empty_v = set()
            for d in vd:
                rows = {r["doc"]: r for r in load_leg(d)["rows"]}
                t = texts_of(d)
                for doc in measured:
                    r = rows.get(doc)
                    if r is None or not r.get("ok") or not r.get("n_chunks") or not t.get(doc, "").strip():
                        empty_v.add(doc)
            L = sorted(tika_text & empty_v)
            per[v]["b"] = {"tika_extracts": len(tika_text), "variant_empty_any_run": len(empty_v),
                           "L_V": L, "holds": not L}
    except FileNotFoundError as e:
        for v in VARIANTS:
            per[v].setdefault("b", {"holds": False, "status": f"NOT EVALUABLE ({e})"})
    fired = [VARIANT_NAME[v] for v in VARIANTS if per[v]["a"].get("holds") and per[v].get("b", {}).get("holds")]
    for v in VARIANTS:
        per[v]["fired"] = VARIANT_NAME[v] in fired
    record(camp, "G_smoke_C", {
        "rule": "per variant, FIRES iff (a) (T - V)/T > spread_T on the p50 parse bracket over the eleven at C=1 AND "
                "(b) L_V is empty on the 384 slice (preregistration.json P2_C_parser_rerun.SMOKE_GATE_P2_C)",
        "per_variant": per, "legs_a": {arm: [x["leg"] for x in a[arm]] for arm in a},
        "eleven_detail": a, "fired_variants": fired,
        "known_bias": "(a) ranks the parse bracket on the eleven tail documents at C=1, where P1-B already removed the "
                      "pathology; HYBRID pays PDFium and Tika on every fallback document; (b) is decided on the 384 slice, "
                      "which holds none of the eleven (recorded; the gate stands as written)",
        "outcome": "EVALUATED"})
    return 0


# ------------------------------------------------------------------ G_manip_B
def manip_b(camp: Path, leg: str, kind: str) -> int:
    d = camp / leg
    rb = json.loads((d / "p1_readback.json").read_text()) if (d / "p1_readback.json").exists() else None
    pf = sorted(d.glob("preflight_*.json"))
    p0 = (json.loads(pf[0].read_text()).get("p0") or {}) if pf else {}
    traces = {k: ((p0.get(k) or {}).get("trace") or {}) for k in ("d0_pre", "d0_post")}
    env = (rb or {}).get("env") or {}
    mon = (rb or {}).get("monitoring_tools") or {}
    dbg_env_probe = [t.get("pydevd_loaded") for t in traces.values() if t]
    mon_probe = [t.get("sys_monitoring_tools") for t in traces.values() if t]
    debugger = {"env_probe_pydevd_loaded": dbg_env_probe, "env_probe_sys_monitoring_tools": mon_probe,
                "readback_monitoring_tools": mon, "readback_gettrace": (rb or {}).get("gettrace")}
    has_dbg = any(x is True for x in dbg_env_probe) or "pydevd" in json.dumps(mon) or any("pydevd" in json.dumps(m or {}) for m in mon_probe)
    no_dbg = (bool(dbg_env_probe) and all(x is False for x in dbg_env_probe) and "pydevd" not in json.dumps(mon)
              and not any("pydevd" in json.dumps(m or {}) for m in mon_probe))
    malloc = env.get("MALLOC_ARENA_MAX")
    threads = len((rb or {}).get("os_threads") or [])
    if rb is None or not pf:
        ok, why = False, f"read-back missing (p1_readback.json {'present' if rb else 'ABSENT'}, preflight {'present' if pf else 'ABSENT'})"
    elif kind == "base":
        ok = has_dbg and malloc is None
        why = "baseline must show the debugger loaded and no MALLOC_ARENA_MAX"
    else:
        ok = no_dbg and malloc == "2"
        why = "COMBINED must show no debugger (pydevd_loaded false, no sys.monitoring tool) and MALLOC_ARENA_MAX=2"
    record(camp, f"G_manip_B_{leg}", {"leg": leg, "cell": kind, "rule": why, "debugger": debugger,
                                      "debugger_loaded": has_dbg, "debugger_absent": no_dbg,
                                      "malloc_arena_max_in_detector_process": malloc,
                                      "detector_process_os_threads": threads,
                                      "outcome": "PASS" if ok else "FAIL — the cell is not the cell described; P2-B stops"})
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, camp = sys.argv[1], Path(sys.argv[2])
    try:
        if cmd == "memstat":
            return memstat(camp, sys.argv[3])
        if cmd == "a_smoke":
            return a_smoke(camp)
        if cmd == "node_c":
            return node_c(camp, sys.argv[3], sys.argv[4])
        if cmd == "c_smoke":
            return c_smoke(camp)
        if cmd == "manip_b":
            return manip_b(camp, sys.argv[3], sys.argv[4])
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
