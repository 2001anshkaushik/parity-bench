#!/usr/bin/env python3
"""P0 docs analysis: D0 per leg, D1 (overhead, null control, stage tables both arms), the
same-session single-instance parity cell, and H1 — all from the raw per-document records.

    p0_analyse_docs.py <campaign_dir> [--out analysis_docs_p0.json]

Every figure is computed here from the committed raw files of each leg directory:
perdoc_<arm>_<leg>.jsonl (client submit/completion, chunk hashes, LlamaIndex service stamps),
stamp_probe.jsonl (RocketRide engine stamps, PROFILE legs), leg_<arm>_<leg>.json (window, cost,
the P0 session and D0 blocks). Definitions are the pre-registration's (preregistration.json):
quantiles nearest-rank on sorted values, the median the true median, shares of run total over the
documents with a complete stamp set, occupancy time-weighted over the measured window.
Nothing is rounded before it is used; the output rounds only for display.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLOOR = {"rr": 0.0082, "li": 0.0987}
PARSE_RR = ("admission", "parse_bracket", "split", "embed", "return")
TIMED_FROM = {"admission": "OUTSIDE (client submit -> engine pipe open)",
              "parse_bracket": "OUTSIDE (pipe open -> parse's last text): upload, executor-thread "
                               "wait, Tika and engine glue; parse is native C++",
              "split": "INSIDE at node boundaries (LangChain splitter, Python)",
              "embed": "INSIDE at node boundaries (MiniLM, Python/torch; node's buffered flush)",
              "return": "OUTSIDE (embed's last documents -> client completion)",
              "extract": "INSIDE the service (pypdf)", "svc_split": "INSIDE the service",
              "svc_embed": "INSIDE the service", "queue": "OUTSIDE (client latency - service total)"}


# ------------------------------------------------------------------ statistics

def q_nearest(v: List[float], q: float) -> float:
    s = sorted(v)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def metric_set(v: List[float], run_total: float) -> Dict[str, Any]:
    if not v:
        return {"count": 0}
    mean = sum(v) / len(v)
    med = statistics.median(v)
    return {"count": len(v), "sum": sum(v), "share_of_run_total": sum(v) / run_total if run_total else None,
            "min": min(v), "mean": mean, "sd": statistics.pstdev(v) if len(v) > 1 else 0.0,
            "p50": med, "p90": q_nearest(v, 0.90), "p95": q_nearest(v, 0.95),
            "p99": q_nearest(v, 0.99), "max": max(v),
            "mean_over_p50": (mean / med) if med else None}


def occupancy(intervals: List[Tuple[float, float]], t0: float, t1: float) -> Dict[str, Any]:
    """Time-weighted distribution of how many intervals are open, over [t0, t1]."""
    ev = []
    for a, b in intervals:
        a, b = max(a, t0), min(b, t1)
        if b > a:
            ev += [(a, 1), (b, -1)]
    ev.sort()
    level, last, dur = 0, t0, {}
    for t, d in ev:
        if t > last:
            dur[level] = dur.get(level, 0.0) + (t - last)
            last = t
        level += d
    if t1 > last:
        dur[level] = dur.get(level, 0.0) + (t1 - last)
    tot = sum(dur.values())
    if not tot:
        return {"max": 0}
    levels = sorted(dur)
    def tq(q):
        acc = 0.0
        for lv in levels:
            acc += dur[lv]
            if acc >= q * tot:
                return lv
        return levels[-1]
    return {"max": max(lv for lv in levels if dur[lv] > 0), "mean": sum(lv * d for lv, d in dur.items()) / tot,
            "p50": tq(0.5), "p95": tq(0.95), "window_s": tot}


def spread(a: float, b: float) -> float:
    return abs(a - b) / ((a + b) / 2)


# ------------------------------------------------------------------ loading

def leg_files(d: Path) -> Optional[Dict[str, Path]]:
    lj = sorted(d.glob("leg_*.json"))
    pd = sorted(d.glob("perdoc_*.jsonl"))
    if not lj or not pd:
        return None
    return {"leg": lj[0], "perdoc": pd[0], "stamps": d / "stamp_probe.jsonl"}


def rows_of(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def span_raw(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    t0 = min(r["submit_ns"] for r in rows)
    t1 = max(r["completion_ns"] for r in rows)
    ok = sum(1 for r in rows if r.get("ok"))
    span = (t1 - t0) / 1e9
    return {"span_s": span, "ok": ok, "n": len(rows), "docs_per_s": ok / span}


def load_leg(d: Path) -> Optional[Dict[str, Any]]:
    f = leg_files(d)
    if not f:
        return None
    leg = json.loads(f["leg"].read_text())
    rows = rows_of(f["perdoc"])
    p0 = leg.get("p0") or {}
    out = {"dir": d.name, "arm": leg["arm"], "leg": leg["leg"], "rows": rows,
           "window": leg.get("window"), "span": span_raw(rows),
           "stamped": bool(leg.get("instrumented_s5d_stamps")),
           "li_timed": any(isinstance(r.get("svc_timing_ms"), dict) and "extract" in r["svc_timing_ms"]
                           for r in rows),
           "boot_id": (p0.get("session") or {}).get("boot_id"),
           "session": p0.get("session"), "mandate": p0.get("mandate"),
           "d0_in": p0.get("d0_in_process"), "cost": leg.get("cost"),
           "percore_host": leg.get("percore_host"), "verdict": leg.get("verdict"),
           "pyspy": p0.get("pyspy")}
    out["stamps"] = rows_of(f["stamps"]) if f["stamps"].exists() else []
    return out


# ------------------------------------------------------------------ RocketRide stages

def rr_stage_rows(leg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    by_doc: Dict[str, Dict[str, Any]] = {}
    names = {r["doc"] for r in leg["rows"]}
    for s in leg["stamps"]:
        if s.get("doc") in names:
            by_doc.setdefault(s["doc"], {"recs": []})["recs"].append(s)
    out, incomplete = [], 0
    for r in leg["rows"]:
        g = by_doc.get(r["doc"])
        if not g:
            incomplete += 1
            continue
        st = {x["stage"]: x for x in g["recs"] if x.get("stage")}
        if not all(k in st for k in ("after_parse", "after_split", "after_embed")):
            incomplete += 1
            continue
        sub, comp = r["submit_ns"] / 1e9, r["completion_ns"] / 1e9
        opn = min(x["open_t"] for x in g["recs"])
        pl, sl, el = st["after_parse"]["last_t"], st["after_split"]["last_t"], st["after_embed"]["last_t"]
        out.append({"doc": r["doc"], "submit": sub, "open": opn, "parse_first": st["after_parse"]["first_t"],
                    "parse_last": pl, "split_last": sl, "embed_last": el, "completion": comp,
                    "embed_close": st["after_embed"]["close_t"],
                    "close_max": max(x["close_t"] for x in g["recs"]),
                    "tname": st["after_embed"].get("tname"), "native_id": st["after_embed"].get("native_id"),
                    "admission": opn - sub, "parse_bracket": pl - opn, "split": sl - pl,
                    "embed": el - sl, "return": comp - el, "end_to_end": comp - sub})
    return out, incomplete


def rr_d1(leg: Dict[str, Any]) -> Dict[str, Any]:
    sr, incomplete = rr_stage_rows(leg)
    run_total = sum(x["end_to_end"] for x in sr)
    t0, t1 = leg["window"]["t0_ns"] / 1e9, leg["window"]["t1_ns"] / 1e9
    iv = {"admission": ("submit", "open"), "parse_bracket": ("open", "parse_last"),
          "split": ("parse_last", "split_last"), "embed": ("split_last", "embed_last"),
          "return": ("embed_last", "completion")}
    stages = {}
    for k in PARSE_RR:
        stages[k] = {**metric_set([x[k] for x in sr], run_total), "timed_from": TIMED_FROM[k],
                     "occupancy": occupancy([(x[iv[k][0]], x[iv[k][1]]) for x in sr], t0, t1)}
    return {"docs_with_complete_stamps": len(sr), "docs_incomplete_stamps": incomplete,
            "run_total_s": run_total, "stages": stages,
            "end_to_end": metric_set([x["end_to_end"] for x in sr], run_total)}


def li_d1(leg: Dict[str, Any]) -> Dict[str, Any]:
    rows = [r for r in leg["rows"] if isinstance(r.get("svc_timing_ms"), dict)
            and "extract" in r["svc_timing_ms"]]
    per = []
    for r in rows:
        tm = r["svc_timing_ms"]
        lat = (r["completion_ns"] - r["submit_ns"]) / 1e9
        per.append({"extract": tm["extract"] / 1e3, "svc_split": tm["split"] / 1e3,
                    "svc_embed": tm["embed"] / 1e3,
                    "queue": lat - tm["total"] / 1e3, "end_to_end": lat,
                    "t_ex0": tm["t0_wall"], "submit": r["submit_ns"] / 1e9,
                    "completion": r["completion_ns"] / 1e9})
    run_total = sum(x["end_to_end"] for x in per)
    t0, t1 = leg["window"]["t0_ns"] / 1e9, leg["window"]["t1_ns"] / 1e9
    stages = {}
    for k in ("queue", "extract", "svc_split", "svc_embed"):
        stages[k] = {**metric_set([x[k] for x in per], run_total), "timed_from": TIMED_FROM[k]}
    stages["extract"]["occupancy"] = occupancy([(x["t_ex0"], x["t_ex0"] + x["extract"]) for x in per], t0, t1)
    stages["svc_split"]["occupancy"] = occupancy(
        [(x["t_ex0"] + x["extract"], x["t_ex0"] + x["extract"] + x["svc_split"]) for x in per], t0, t1)
    stages["svc_embed"]["occupancy"] = occupancy(
        [(x["t_ex0"] + x["extract"] + x["svc_split"],
          x["t_ex0"] + x["extract"] + x["svc_split"] + x["svc_embed"]) for x in per], t0, t1)
    return {"docs_with_service_stamps": len(per), "docs_without": len(leg["rows"]) - len(per),
            "run_total_s": run_total, "stages": stages,
            "note": "only documents the service answered ok carry stage stamps (an error class "
                    "returns before the stamps are added)"}


# ------------------------------------------------------------------ comparisons

def pair_compare(a: List[Dict[str, Any]], b: List[Dict[str, Any]], floor: float) -> Dict[str, Any]:
    """a = baseline cell legs (e.g. unstamped), b = the other cell; span docs/s."""
    va = [x["span"]["docs_per_s"] for x in a]
    vb = [x["span"]["docs_per_s"] for x in b]
    ma, mb = sum(va) / len(va), sum(vb) / len(vb)
    sa = spread(*va) if len(va) == 2 else None
    sb = spread(*vb) if len(vb) == 2 else None
    thr = max([floor] + [s for s in (sa, sb) if s is not None])
    delta = (mb - ma) / ma
    return {"cell_a": [x["dir"] for x in a], "cell_b": [x["dir"] for x in b],
            "a_docs_per_s": va, "b_docs_per_s": vb, "a_mean": ma, "b_mean": mb,
            "a_spread": sa, "b_spread": sb, "floor": floor, "threshold": thr,
            "delta_b_vs_a": delta, "readable": abs(delta) > thr,
            "same_session": len({x["boot_id"] for x in a + b}) == 1}


def chunk_identity(a: Dict[str, Any], b: Dict[str, Any], u_ref: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ha = {r["doc"]: r.get("chunk_sha256") for r in a["rows"] if r.get("ok")}
    hb = {r["doc"]: r.get("chunk_sha256") for r in b["rows"] if r.get("ok")}
    both = sorted(set(ha) & set(hb))
    diff = [d for d in both if ha[d] != hb[d]]
    nondet, attributable = [], []
    if u_ref is not None:
        hu = {r["doc"]: r.get("chunk_sha256") for r in u_ref["rows"] if r.get("ok")}
        for d in diff:
            (nondet if (d in hu and hu[d] != ha[d]) else attributable).append(d)
    return {"a": a["dir"], "b": b["dir"], "compared": len(both), "identical": len(both) - len(diff),
            "differing": diff[:50], "n_differing": len(diff),
            "differing_where_unstamped_legs_also_disagree": nondet,
            "differing_attributable_to_instrument": attributable if u_ref is not None else diff,
            "only_in_a": sorted(set(ha) - set(hb))[:20], "only_in_b": sorted(set(hb) - set(ha))[:20]}


def h1(legs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for name in ("h1_c32_a", "h1_c64_a", "h1_c32_b", "h1_c64_b"):
        g = legs.get(name)
        if not g or not g["stamps"]:
            out[name] = {"status": "NOT RUN or no stamps"}
            continue
        sr, _ = rr_stage_rows(g)
        t0, t1 = g["window"]["t0_ns"] / 1e9, g["window"]["t1_ns"] / 1e9
        names = {r["doc"] for r in g["rows"]}
        recs = [s for s in g["stamps"] if s.get("doc") in names]
        tnames = sorted({s.get("tname") for s in recs if s.get("tname")})
        idx = sorted(int(t.split("_", 1)[1]) for t in tnames
                     if t.startswith("asyncio_") and t.split("_", 1)[1].isdigit())
        # The engine's executor threads are all NAMED 'External' (tooling leg, 2026-09-23), so the
        # width is counted by the OS thread id each document's close() ran on, not by name.
        nids = {s.get("native_id") for s in recs if s.get("native_id")}
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for s in recs:
            by_doc.setdefault(s["doc"], []).append(s)
        opn = [(min(x["open_t"] for x in v), max(x["close_t"] for x in v)) for v in by_doc.values()]
        out[name] = {"span": g["span"], "boot_id": g["boot_id"],
                     "executor_threads_seen": len(nids), "thread_names_seen": tnames[:6],
                     "asyncio_executor_max_index": idx[-1] if idx else None,

                     "executing_concurrency": occupancy([(x["parse_first"], x["embed_close"]) for x in sr
                                                         if x["parse_first"]], t0, t1),
                     "engine_open_concurrency": occupancy(opn, t0, t1)}
    c64 = [out[n] for n in ("h1_c64_a", "h1_c64_b") if "span" in out.get(n, {})]
    c32 = [out[n] for n in ("h1_c32_a", "h1_c32_b") if "span" in out.get(n, {})]
    verdict = None
    if c64:
        width_ok = all(x["executor_threads_seen"] <= 32 for x in c64)
        exec_ok = all(x["executing_concurrency"]["max"] <= 32 for x in c64)
        verdict = "HOLDS" if (width_ok and exec_ok) else "REFUTED"
    thr = None
    if len(c64) == 2 and len(c32) == 2:
        a = [legs["h1_c32_a"], legs["h1_c32_b"]]
        b = [legs["h1_c64_a"], legs["h1_c64_b"]]
        thr = pair_compare(a, b, FLOOR["rr"])
    out["verdict"] = {"h1": verdict, "rule": "HOLDS if at C=64 the executor width seen is <= 32 "
                      "and the executing concurrency never exceeds 32; REFUTED if any C=64 leg "
                      "shows more than 32 executing at once", "c64_vs_c32_throughput": thr}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out", default="analysis_docs_p0.json")
    a = ap.parse_args()
    legs: Dict[str, Dict[str, Any]] = {}
    for d in sorted(a.campaign.iterdir()):
        if d.is_dir():
            g = load_leg(d)
            if g:
                legs[d.name] = g
    res: Dict[str, Any] = {"campaign": a.campaign.name, "legs": {}}
    for n, g in legs.items():
        res["legs"][n] = {"arm": g["arm"], "leg": g["leg"], "verdict": g["verdict"],
                          "span": g["span"], "stamped_profile": g["stamped"],
                          "li_timed_profile": g["li_timed"], "boot_id": g["boot_id"],
                          "steal": (g["session"] or {}).get("steal"),
                          "mhz": (g["session"] or {}).get("mhz_over_window"),
                          "cpu_model": ((g["session"] or {}).get("cpu_open") or {}).get("model"),
                          "d0_external": (g["session"] or {}).get("d0_external"),
                          "d0_models_pre": (((g["d0_in"] or {}).get("pre") or {}).get("d0") or {}).get("root_modules_with_params"),
                          "d0_threads_pre": {k: (((g["d0_in"] or {}).get("pre") or {}).get("d0") or {}).get(k)
                                             for k in ("proc_threads", "python_threads",
                                                       "asyncio_executor_threads_alive")},
                          "torch_threads_pre": ((g["d0_in"] or {}).get("pre") or {}).get("torch_num_threads"),
                          "mandate": g["mandate"],
                          "engine_cores": (g["cost"] or {}).get("engine_container_cores"),
                          "cpu_s_per_doc": (g["cost"] or {}).get("cpu_s_per_doc"),
                          "host_busy_cores": (g["percore_host"] or {}).get("mean_busy_cores")}
    res["sessions"] = sorted({g["boot_id"] for g in legs.values() if g["boot_id"]})
    # ---- D1 overhead
    ov = {}
    def have(*ns):
        return all(n in legs for n in ns)
    if have("d1_rr_s1", "d1_rr_u1", "d1_rr_s2", "d1_rr_u2"):
        ov["rr_384_c32"] = pair_compare([legs["d1_rr_u1"], legs["d1_rr_u2"]],
                                        [legs["d1_rr_s1"], legs["d1_rr_s2"]], FLOOR["rr"])
        ov["rr_384_c32"]["overhead"] = -ov["rr_384_c32"]["delta_b_vs_a"]
    if have("an_rr_s1", "an_rr_u1", "an_rr_s2", "an_rr_u2"):
        ov["rr_96_c8"] = pair_compare([legs["an_rr_u1"], legs["an_rr_u2"]],
                                      [legs["an_rr_s1"], legs["an_rr_s2"]], FLOOR["rr"])
        ov["rr_96_c8"]["overhead"] = -ov["rr_96_c8"]["delta_b_vs_a"]
    if have("an_li_t1", "an_li_u1", "an_li_t2", "an_li_u2"):
        ov["li_96_c8_one_worker"] = pair_compare([legs["an_li_u1"], legs["an_li_u2"]],
                                                 [legs["an_li_t1"], legs["an_li_t2"]], FLOOR["li"])
        ov["li_96_c8_one_worker"]["overhead"] = -ov["li_96_c8_one_worker"]["delta_b_vs_a"]
    res["d1_overhead"] = ov
    # ---- null control: stamped vs unstamped chunk identity
    nc = []
    for kind, s_, u, u2 in (("instrument", "d1_rr_s1", "d1_rr_u1", "d1_rr_u2"),
                            ("instrument", "d1_rr_s2", "d1_rr_u2", "d1_rr_u1"),
                            ("instrument", "an_rr_s1", "an_rr_u1", "an_rr_u2"),
                            ("instrument", "an_rr_s2", "an_rr_u2", "an_rr_u1"),
                            ("instrument", "an_li_t1", "an_li_u1", "an_li_u2"),
                            ("instrument", "an_li_t2", "an_li_u2", "an_li_u1"),
                            ("determinism", "d1_rr_u2", "d1_rr_u1", None),
                            ("determinism", "an_rr_u2", "an_rr_u1", None),
                            ("determinism", "an_li_u2", "an_li_u1", None)):
        if s_ in legs and u in legs:
            nc.append({"kind": kind, **chunk_identity(legs[u], legs[s_], legs.get(u2) if u2 else None)})
    inst = [x for x in nc if x["kind"] == "instrument"]
    res["d1_null_control_chunk_identity"] = {
        "pairs": nc,
        "pass": (all(not x["differing_attributable_to_instrument"] for x in inst) if inst else None),
        "rule": "stamped (timed) output equals unstamped (untimed) output chunk for chunk on every "
                "document both completed; a difference on a document whose two unstamped legs "
                "agree is attributed to the instrument (a correctness failure). Determinism pairs "
                "(unstamped vs unstamped) say whether the arm's own output is reproducible"}
    # ---- D1 stage tables (PROFILE)
    res["d1_stages"] = {n: {"arm": "rr", **rr_d1(legs[n])} for n in
                        ("d1_rr_s1", "d1_rr_s2", "an_rr_s1", "an_rr_s2", "h1_c32_a", "h1_c32_b",
                         "h1_c64_a", "h1_c64_b") if n in legs and legs[n]["stamps"]}
    res["d1_stages"].update({n: {"arm": "li", **li_d1(legs[n])} for n in ("an_li_t1", "an_li_t2")
                             if n in legs and legs[n]["li_timed"]})
    res["d1_labels"] = {"profile": "every stage table is from a PROFILE leg: shares, rankings and "
                                   "distributions only; its absolute times never sit beside a "
                                   "baseline figure", "timed_from": TIMED_FROM}
    # ---- same-session single-instance parity cell (unstamped / untimed)
    if have("an_rr_u1", "an_rr_u2", "an_li_u1", "an_li_u2"):
        pc = pair_compare([legs["an_li_u1"], legs["an_li_u2"]], [legs["an_rr_u1"], legs["an_rr_u2"]],
                          max(FLOOR["rr"], FLOOR["li"]))
        pc["reading"] = ("delta_b_vs_a = RocketRide one token / LlamaIndex one worker - 1, span "
                         "docs/s, 96-document anchor slice, C=8, six thread vars = 1 on both; the "
                         "floor is the larger of the two arms' (9.87%)")
        res["parity_anchor_same_session"] = pc
    res["h1"] = h1(legs)
    out = a.campaign / a.out
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
