#!/usr/bin/env python3
"""Analyse a docs batch-size sweep: rank K per arm, and refuse to call a winner the data cannot
support.

    batchsize_analyse.py <campaign_dir> [--out report.json]

<campaign_dir> holds one sub-directory per launch (rr_pass1, li_pass1, rr_rev, ...), each with
leg_<arm>_<leg>.json + perdoc_<arm>_<leg>.jsonl as exp_batchsize_sweep.py wrote them.

A ranking is a claim, so it is checked from angles whose failure modes differ (register entry 2:
self-consistency is not evidence — a check must cross an independence boundary):

  A. CLOCK        docs/s recomputed from the per-document records' wall-clock stamps (time_ns)
                  against the export's monotonic span (perf_counter). Two clocks, one leg.
  B. CPU SOURCE   effective cores from the arm's cgroup against busy cores from host /proc/stat
                  over the same cpuset. Two kernels' worth of accounting; a gap is foreign load
                  or work the cgroup does not own (docker-proxy), and it is printed, not hidden.
  C. CONTENT      every document's chunk-hash list must be IDENTICAL across all K within an
                  arm — batch size may change when work happens, never what comes out. NULL
                  CONTROL: the same comparator run ACROSS arms must report differences (Tika vs
                  pypdf extract different text); if it reports none, it cannot see anything.
  E. TAIL         docs/s up to the 90th-percentile completion, beside the span figure. On a
                  short slice ONE slow document sets the span of every fast leg (first read:
                  two LlamaIndex continuous passes 19% apart on span, 1% apart to 90% — the whole
                  gap was when a 791-page PDF finished). A K ranking that changes between the
                  two metrics is a ranking of where the slow document landed, not of K. On the
                  engine's batched legs completion stamps are per BATCH, so this figure is
                  coarse at large K and mechanical (0.9x span) when one batch holds everything.
  D. NOISE FLOOR  legs that ran twice (a replicate launch) give the spread of the instrument.
                  A best K whose lead over the runner-up is inside that spread is a TIE, and
                  is reported as one. No replicate -> the floor is UNKNOWN and says so.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DOCUMENT_OUTCOMES = {"no_documents", "empty_extraction", "parse_failed"}


def load_campaign(d: Path) -> List[Dict[str, Any]]:
    """Shakedown launches (shake_*) are wiring checks on a DIFFERENT, 16-document slice. Pooling
    them with the measured slice once read a corpus difference as run-to-run noise (a 30% 'noise
    floor' from two legs that never shared a document), so they are excluded, and so is any leg
    whose document count differs from the campaign's — a replicate is the same work twice."""
    legs = []
    for lj in sorted(d.glob("*/leg_*.json")):
        if lj.parent.name.startswith("shake"):
            continue
        leg = json.loads(lj.read_text())
        leg["_launch"] = lj.parent.name
        # The verdict is DERIVED here from the recorded reasons, never edited in the artifact:
        # parser-level document outcomes are content, not lost work (see exp_batchsize_sweep.py).
        reasons = set((leg.get("documents") or {}).get("hard_failure_reasons") or [])
        leg["verdict_export"] = leg.get("verdict")
        if leg.get("verdict") == "DEGRADED" and reasons and reasons <= DOCUMENT_OUTCOMES \
                and leg["documents"]["recorded"] == leg["documents"]["submitted"]:
            leg["verdict"] = "OK"
            leg["verdict_note"] = f"export said DEGRADED over document outcomes only: {sorted(reasons)}"
        pd = lj.parent / lj.name.replace("leg_", "perdoc_").replace(".json", ".jsonl")
        leg["_perdoc"] = ([json.loads(x) for x in pd.read_text().splitlines() if x.strip()]
                          if pd.exists() else None)
        legs.append(leg)
    sizes = {g["documents"]["submitted"] for g in legs if g.get("documents")}
    if len(sizes) > 1:
        raise SystemExit(f"REFUSED: legs with different document counts {sorted(sizes)} in one "
                         "campaign — they are not comparable and are not replicates")
    return legs


def check_clock(leg: Dict[str, Any], tol: float = 0.02) -> Dict[str, Any]:
    rows = leg.get("_perdoc")
    if not rows:
        return {"verdict": "NOT RUN", "reason": "no per-document records"}
    span = (max(r["completion_ns"] for r in rows) - min(r["submit_ns"] for r in rows)) / 1e9
    ok = sum(1 for r in rows if r.get("ok"))
    mine, theirs = ok / span, leg["throughput"]["docs_per_s"]
    rel = abs(mine - theirs) / theirs if theirs else None
    return {"verdict": "PASS" if rel is not None and rel <= tol else "FAIL",
            "docs_per_s_from_records": round(mine, 4), "docs_per_s_export": theirs,
            "relative_gap": round(rel, 5) if rel is not None else None, "tolerance": tol}


def check_cpu(leg: Dict[str, Any], tol_cores: float = 1.5) -> Dict[str, Any]:
    cg = leg["cost"].get("effective_cores")
    host = (leg.get("percore_host") or {}).get("mean_busy_cores")
    if cg is None or host is None:
        return {"verdict": "NOT RUN", "reason": "a source is missing"}
    gap = host - cg
    return {"verdict": "PASS" if abs(gap) <= tol_cores else "FAIL", "cgroup_effective_cores": cg,
            "host_busy_cores_on_cpuset": host, "host_minus_cgroup": round(gap, 3),
            "tolerance_cores": tol_cores,
            "reading": "host > cgroup is work on the arm's cores the arm's cgroup does not own"}


def _hashes(leg: Dict[str, Any]) -> Dict[str, str]:
    return {r["doc"]: hashlib.sha256("|".join(r.get("chunk_sha256") or []).encode()).hexdigest()
            for r in (leg.get("_perdoc") or []) if r.get("ok")}


def compare_content(a: Dict[str, str], b: Dict[str, str]) -> Tuple[int, int, List[str]]:
    common = sorted(set(a) & set(b))
    diff = [d for d in common if a[d] != b[d]]
    return len(common), len(diff), diff[:8]


def check_content(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for g in legs:
        if g.get("_perdoc"):
            by_arm.setdefault(g["arm"], []).append(g)
    for arm, gs in by_arm.items():
        base, worst = _hashes(gs[0]), []
        for g in gs[1:]:
            n, nd, ex = compare_content(base, _hashes(g))
            worst.append({"leg": f"{g['_launch']}/{g['leg']}", "common": n, "differing": nd,
                          "examples": ex})
        out[arm] = {"reference": f"{gs[0]['_launch']}/{gs[0]['leg']}", "comparisons": worst,
                    "verdict": ("PASS" if worst and all(w["differing"] == 0 and w["common"] > 0
                                                        for w in worst)
                                else "NOT RUN" if not worst else "FAIL")}
    if len(by_arm) == 2:
        (a1, g1), (a2, g2) = list(by_arm.items())
        n, nd, _ = compare_content(_hashes(g1[0]), _hashes(g2[0]))
        out["null_control_cross_arm"] = {
            "common": n, "differing": nd,
            "verdict": "FIRED" if nd > 0 else "DID NOT FIRE",
            "meaning": ("the comparator sees differences where they must exist (different "
                        "parsers)" if nd > 0 else
                        "the comparator reported two different parsers as identical — the "
                        "within-arm PASS above proves nothing")}
    else:
        out["null_control_cross_arm"] = {"verdict": "NOT RUN", "reason": "needs both arms"}
    return out


def check_tail(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_leg: Dict[str, Any] = {}
    by_arm: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}
    for g in legs:
        rows = g.get("_perdoc")
        if g.get("verdict") != "OK" or not rows:
            continue
        ok = sorted((r for r in rows if r.get("ok")), key=lambda r: r["completion_ns"])
        t0 = min(r["submit_ns"] for r in rows)
        k90 = int(0.9 * len(ok))
        t90 = (ok[k90 - 1]["completion_ns"] - t0) / 1e9
        span = (max(r["completion_ns"] for r in rows) - t0) / 1e9
        a, b = len(ok) / span, k90 / t90
        per_leg[f"{g['_launch']}/{g['leg']}"] = {
            "docs_per_s_span": round(a, 4), "docs_per_s_to_p90": round(b, 4),
            "p90_over_span": round(b / a, 3), "t90_s": round(t90, 1), "span_s": round(span, 1)}
        key = f"k{g['k']}" if g.get("k") else f"refc{g['reference_c']}"
        by_arm.setdefault(g["arm"], {}).setdefault(key, []).append((a, b))
    ranks: Dict[str, Any] = {}
    for arm, m in by_arm.items():
        mean = lambda v, i: sum(x[i] for x in v) / len(v)      # noqa: E731
        grid = [k for k in m if k.startswith("k")]
        r_span = sorted(grid, key=lambda k: -mean(m[k], 0))
        r_p90 = sorted(grid, key=lambda k: -mean(m[k], 1))
        ranks[arm] = {"rank_by_span": r_span, "rank_by_to_p90": r_p90,
                      "verdict": "PASS — K ranking identical under both metrics"
                      if r_span == r_p90 else "DIFFERS — read both rankings",
                      "to_p90_replicate_spread": {
                          k: round((max(x[1] for x in v) - min(x[1] for x in v)) / mean(v, 1), 4)
                          for k, v in m.items() if len(v) > 1}}
    return {"per_leg": per_leg, "by_arm": ranks}


def noise_floor(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for arm in sorted({g["arm"] for g in legs}):
        seen: Dict[Any, List[float]] = {}
        for g in legs:
            if g["arm"] == arm and g.get("verdict") == "OK" and g["throughput"]["docs_per_s"]:
                seen.setdefault(g["k"] or f"refc{g['reference_c']}", []).append(
                    g["throughput"]["docs_per_s"])
        reps = {k: v for k, v in seen.items() if len(v) > 1}
        spreads = {str(k): round((max(v) - min(v)) / (sum(v) / len(v)), 4) for k, v in reps.items()}
        out[arm] = {"replicated": {str(k): v for k, v in reps.items()}, "relative_spread": spreads,
                    "floor": max(spreads.values()) if spreads else None}
    return out


def rank(legs: List[Dict[str, Any]], floors: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for arm in sorted({g["arm"] for g in legs}):
        per_k: Dict[int, List[Dict[str, Any]]] = {}
        ref = []
        for g in legs:
            if g["arm"] != arm or g.get("verdict") != "OK":
                continue
            (per_k.setdefault(g["k"], []) if g["k"] else ref).append(g)
        table = []
        for k, gs in sorted(per_k.items()):
            v = [g["throughput"]["docs_per_s"] for g in gs]
            table.append({
                "k": k, "runs": len(gs), "docs_per_s_mean": round(sum(v) / len(v), 4),
                "docs_per_s_all": v,
                "effective_cores": round(sum(g["cost"]["effective_cores"] for g in gs) / len(gs), 3),
                "cpu_utilization": round(sum(g["cost"]["cpu_utilization"] for g in gs) / len(gs), 4),
                "idle_core_count_mean": round(sum(g["percore_host"]["idle_core_count_mean"]
                                                  for g in gs) / len(gs), 2),
                "idle_core_equivalents": round(sum(g["percore_host"]["idle_core_equivalents"]
                                                   for g in gs) / len(gs), 3),
                "cpu_s_per_doc": round(sum(g["cost"]["cpu_s_per_doc"] for g in gs) / len(gs), 4),
                "batch_wall_s_max": max((g["batches"] or {}).get("wall_s_max", 0) for g in gs)})
        ordered = sorted(table, key=lambda r: r["docs_per_s_mean"], reverse=True)
        floor = floors.get(arm, {}).get("floor")
        call: Dict[str, Any] = {"best_k": ordered[0]["k"] if ordered else None}
        if len(ordered) > 1:
            lead = (ordered[0]["docs_per_s_mean"] - ordered[1]["docs_per_s_mean"]) / ordered[1]["docs_per_s_mean"]
            call.update(runner_up_k=ordered[1]["k"], lead_over_runner_up=round(lead, 4),
                        noise_floor=floor,
                        verdict=("UNRESOLVED — no replicate, noise floor unknown" if floor is None
                                 else "TIE — lead is inside the noise floor" if lead <= floor
                                 else "RESOLVED — lead exceeds the noise floor"))
        refs = [{"reference_c": g["reference_c"], "docs_per_s": g["throughput"]["docs_per_s"],
                 "effective_cores": g["cost"]["effective_cores"],
                 "cpu_utilization": g["cost"]["cpu_utilization"],
                 "idle_core_count_mean": g["percore_host"]["idle_core_count_mean"],
                 "launch": g["_launch"]} for g in ref]
        if refs and ordered:
            best_ref = max(r["docs_per_s"] for r in refs)
            call["batching_vs_continuous"] = {
                "best_batched_docs_per_s": ordered[0]["docs_per_s_mean"],
                "continuous_docs_per_s": best_ref,
                "batched_over_continuous": round(ordered[0]["docs_per_s_mean"] / best_ref, 4)}
        out[arm] = {"by_k": table, "call": call, "continuous_reference": refs}
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    d = Path(sys.argv[1])
    legs = load_campaign(d)
    if not legs:
        print(f"REFUSED: no leg_*.json under {d}/*/")
        return 3
    floors = noise_floor(legs)
    rep = {
        "campaign_dir": str(d),
        "legs_seen": [f"{g['_launch']}/{g['arm']}/{g['leg']}:{g.get('verdict')}" for g in legs],
        "ranking": rank(legs, floors),
        "noise_floor": floors,
        "check_A_clock": {f"{g['_launch']}/{g['leg']}": check_clock(g) for g in legs
                          if g.get("verdict") == "OK"},
        "check_B_cpu_source": {f"{g['_launch']}/{g['leg']}": check_cpu(g) for g in legs
                               if g.get("verdict") == "OK"},
        "check_C_content": check_content(legs),
        "check_E_tail": check_tail(legs),
    }
    for g in legs:
        g.pop("_perdoc", None)
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only")
            return 3
        p.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
