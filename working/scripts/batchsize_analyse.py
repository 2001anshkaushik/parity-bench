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


GRID = {1, 8, 16, 32, 64, 128}          # the batch sizes the campaign was asked to test
DOCUMENT_OUTCOMES = {"no_documents", "empty_extraction", "parse_failed"}


def _units_by_run_dir(d: Path) -> Dict[str, Any]:
    """Each launch's per-arm export records the shape the arm was started with. Read it rather
    than parsing launch directory names: the name is a label, the export is the read-back."""
    out: Dict[str, Any] = {}
    for f in sorted(d.glob("exp_batchsize_sweep_*.json")):
        try:
            data = json.loads(f.read_text()).get("data", {})
        except (OSError, json.JSONDecodeError):
            continue
        rd = (data.get("run_dir") or "").rstrip("/").split("/")[-1]
        p_ = data.get("posture") or {}
        if rd:
            out[rd] = {"ws1_workers": p_.get("ws1_workers"),
                       "thread_env": p_.get("thread_env_expected"),
                       "rr_threads": data.get("posture", {}).get("rr_threads_requested")}
    return out


def load_campaign(d: Path) -> List[Dict[str, Any]]:
    """Shakedown launches (shake_*) are wiring checks on a DIFFERENT, 16-document slice. Pooling
    them with the measured slice once read a corpus difference as run-to-run noise (a 30% 'noise
    floor' from two legs that never shared a document), so they are excluded, and so is any leg
    whose document count differs from the campaign's — a replicate is the same work twice."""
    legs = []
    units = _units_by_run_dir(d)
    for lj in sorted(d.glob("*/leg_*.json")):
        if lj.parent.name.startswith("shake"):
            continue
        leg = json.loads(lj.read_text())
        leg["_launch"] = lj.parent.name
        pd = lj.parent / lj.name.replace("leg_", "perdoc_").replace(".json", ".jsonl")
        leg["_perdoc"] = ([json.loads(x) for x in pd.read_text().splitlines() if x.strip()]
                          if pd.exists() else None)
        # The verdict is DERIVED here from the recorded reasons, never edited in the artifact:
        # parser-level document outcomes are content, not lost work (see exp_batchsize_sweep.py).
        reasons = set((leg.get("documents") or {}).get("hard_failure_reasons") or [])
        # A COLD-CACHE LEG IS A CONDITION, NOT A REPLICATE (2026-09-20). Pooling one with the
        # warm legs at the same K reported the cache effect as instrument noise and tripled the
        # service arm's floor (27.7% against a true warm spread of ~10%), which then made every
        # "within noise" verdict meaningless. Same class as pooling the shakedown slice.
        leg["condition"] = "cold" if (leg.get("page_cache") or {}).get("attempted") else "warm"
        # THE ARM'S SHAPE IS PART OF THE CONDITION TOO (2026-09-20). Continuous C=32 legs at 16,
        # 24 and 32 service workers are three configurations, and pooling them as repeats put a
        # worker-count effect into the noise floor — the same error as pooling a cold leg with
        # warm ones, one level up. A replicate is the same work under the same conditions.
        u = units.get(lj.parent.name) or {}
        leg["arm_units"] = u.get("ws1_workers") if leg["arm"] == "li" else 1
        leg["cell"] = f"{leg['condition']}/units={leg['arm_units']}"
        leg["verdict_export"] = leg.get("verdict")
        # A TimeoutError is OUR client deadline firing — the engine did not error, the driver
        # stopped waiting. It is a HARNESS loss, never a product failure (DOCS_HANDOFF §3.6 bans
        # quoting the 1800 s PipeExceptions as reliability), but it is still a lost document. So
        # a leg whose only hard failures are deadline losses is ANALYSABLE and CARRIES THEM:
        # throughput is computed on completed documents only, and every lost document is named
        # with how long it was held. Any other hard failure keeps the leg DEGRADED.
        deadline = {r for r in reasons if r.endswith("TimeoutError")}
        rest = reasons - deadline - DOCUMENT_OUTCOMES
        if leg.get("verdict") == "DEGRADED" and reasons and not rest \
                and leg["documents"]["recorded"] == leg["documents"]["submitted"]:
            leg["verdict"] = "OK"
            lost = [{"doc": r["doc"], "reason": r["reason"],
                     "held_s": round((r["completion_ns"] - r["submit_ns"]) / 1e9, 1)}
                    for r in (leg.get("_perdoc") or [])
                    if str(r.get("reason", "")).endswith("TimeoutError")]
            if lost:
                leg["deadline_losses"] = {
                    "n": len(lost), "documents": lost[:50],
                    "fraction_of_submitted": round(len(lost) / leg["documents"]["submitted"], 5),
                    "attribution": "the driver's own deadline firing — not an engine error"}
            leg["verdict_note"] = (f"export said DEGRADED over {sorted(reasons)}: document "
                                   f"outcomes and {len(lost)} client-deadline loss(es) only — "
                                   "analysable, losses carried")
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
        # p99 too (2026-09-21): at full scale p90 discards a thousand documents; p99 discards the
        # stragglers. The first 10k leg spent its last 28 minutes on ONE document
        # (039_039660.pdf — 39 pages, 1722 s on the engine arm, 67 s on the service arm in the
        # banked run) while the host idled at 2.3 cores, so span throughput there measures that
        # document's parse, not the pipeline. The straggler that set the span is NAMED, below.
        k99 = int(0.99 * len(ok))
        t99 = (ok[k99 - 1]["completion_ns"] - t0) / 1e9
        span = (max(r["completion_ns"] for r in rows) - t0) / 1e9
        last = max(rows, key=lambda r: r["completion_ns"])
        a, b, c99 = len(ok) / span, k90 / t90, k99 / t99
        per_leg[f"{g['_launch']}/{g['leg']}"] = {
            "docs_per_s_span": round(a, 4), "docs_per_s_to_p90": round(b, 4),
            "docs_per_s_to_p99": round(c99, 4), "p99_over_span": round(c99 / a, 3),
            "p90_over_span": round(b / a, 3), "t90_s": round(t90, 1), "t99_s": round(t99, 1),
            "span_s": round(span, 1),
            "span_set_by": {"doc": last["doc"], "held_s": round((last["completion_ns"]
                                                                  - last["submit_ns"]) / 1e9, 1),
                            "seconds_after_p99": round(span - t99, 1)}}
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
            if (g["arm"] == arm and g.get("verdict") == "OK" and g.get("condition") == "warm"
                    and g["throughput"]["docs_per_s"]):
                seen.setdefault((g["k"] or f"refc{g['reference_c']}", g.get("arm_units")),
                                []).append(g["throughput"]["docs_per_s"])
        reps = {k: v for k, v in seen.items() if len(v) > 1}
        spreads = {f"{k[0]}@units={k[1]}": round((max(v) - min(v)) / (sum(v) / len(v)), 4)
                   for k, v in reps.items()}
        out[arm] = {"replicated": {f"{k[0]}@units={k[1]}": v for k, v in reps.items()},
                    "relative_spread": spreads,
                    "floor": max(spreads.values()) if spreads else None}
    return out


def _mean(gs: List[Dict[str, Any]], f) -> Optional[float]:
    v = [f(g) for g in gs if f(g) is not None]
    return round(sum(v) / len(v), 3) if v else None


def unit_sweep(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """G3(b): the service arm's worker count, swept at one C, against its own replicate noise.
    24 was inherited from a 24-core cpuset that Ruling A removed, so it has to be re-earned."""
    out: Dict[str, Any] = {}
    for arm in sorted({g["arm"] for g in legs}):
        cells: Dict[Any, Dict[Any, List[float]]] = {}
        for g in legs:
            if g["arm"] != arm or g.get("verdict") != "OK" or g.get("condition") != "warm":
                continue
            key = f"K={g['k']}" if g.get("k") else f"C={g['reference_c']}"
            cells.setdefault(key, {}).setdefault(g.get("arm_units"), []).append(
                g["throughput"]["docs_per_s"])
        rows = {k: {str(u): [round(x, 4) for x in v] for u, v in byu.items()}
                for k, byu in cells.items() if len(byu) > 1}
        if rows:
            out[arm] = rows
    return out


def cache_effect(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """G5(a): cold against warm at the SAME configuration, so the ordering hypothesis is tested
    rather than absorbed. A cold leg's own cost numbers travel with it: a cold arm that also
    burns fewer cores was waiting on disk, which is the mechanism, not just the magnitude."""
    out: Dict[str, Any] = {}
    for arm in sorted({g["arm"] for g in legs}):
        cells: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for g in legs:
            if g["arm"] != arm or g.get("verdict") != "OK":
                continue
            key = f"K={g['k']}" if g.get("k") else f"C={g['reference_c']}"
            cells.setdefault(key, {}).setdefault(g["condition"], []).append(g)
        rows = {}
        for key, byc in cells.items():
            if "cold" not in byc or "warm" not in byc:
                continue
            w = [x["throughput"]["docs_per_s"] for x in byc["warm"]]
            c = [x["throughput"]["docs_per_s"] for x in byc["cold"]]
            wm, cm = sum(w) / len(w), sum(c) / len(c)
            rows[key] = {
                "warm_runs": w, "cold_runs": c, "warm_mean": round(wm, 4), "cold_mean": round(cm, 4),
                "cold_over_warm": round(cm / wm, 4), "delta_pct": round((cm / wm - 1) * 100, 1),
                "warm_engine_cores": round(sum(x["cost"]["engine_container_cores"] for x in byc["warm"]) / len(w), 3),
                "cold_engine_cores": round(sum(x["cost"]["engine_container_cores"] for x in byc["cold"]) / len(c), 3)}
        out[arm] = rows
    return out


def rank(legs: List[Dict[str, Any]], floors: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # The K grid and the continuous curve are read at ONE arm shape — the one most of the
    # campaign ran — so a worker-count sweep cannot leak into a batch-size ranking.
    ref_units: Dict[str, Any] = {}
    for arm in sorted({g["arm"] for g in legs}):
        counts: Dict[Any, int] = {}
        for g in legs:
            if g["arm"] == arm and g.get("condition") == "warm":
                counts[g.get("arm_units")] = counts.get(g.get("arm_units"), 0) + 1
        ref_units[arm] = max(counts, key=lambda u: counts[u]) if counts else None
    for arm in sorted({g["arm"] for g in legs}):
        per_k: Dict[int, List[Dict[str, Any]]] = {}
        ref = []
        for g in legs:
            if g["arm"] != arm or g.get("verdict") != "OK" or g.get("condition") != "warm":
                continue
            if g.get("arm_units") != ref_units.get(arm):
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
                "batch_wall_s_max": max((g["batches"] or {}).get("wall_s_max", 0) for g in gs),
                # Ruling A's three sources, carried into the table rather than left in the legs.
                "engine_cores": _mean(gs, lambda g: g["cost"].get("engine_container_cores")),
                "driver_cores": _mean(gs, lambda g: g["cost"].get("driver_cores")),
                "host_cores": _mean(gs, lambda g: g["cost"].get("host_total_cores")),
                "unattributed_cores": _mean(gs, lambda g: g["cost"].get("unattributed_cores")),
                "idle_spin_cores": _mean(gs, lambda g: (g["cost"].get("idle_spin_measured") or {}).get("cores")),
                "idle_core_equivalents_net_of_spin":
                    _mean(gs, lambda g: g["percore_host"].get("idle_core_equivalents_net_of_spin")),
                "available_cpus": gs[0]["cost"].get("available_cpus")})
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
        # THE REQUESTED GRID, called separately: edge probes beyond it (K=256, K=384) describe
        # the trend and must not decide the answer to "which of the requested sizes is best".
        # Non-overlap is the sturdier test on a noisy arm: the best K's WORST run against the
        # runner-up's BEST run. It needs replicates on both; without them it says so.
        in_grid = [r for r in ordered if r["k"] in GRID]
        if len(in_grid) > 1:
            b, u = in_grid[0], in_grid[1]
            call["in_requested_grid"] = {
                "grid": sorted(GRID), "best_k": b["k"], "runner_up_k": u["k"],
                "lead_over_runner_up": round(b["docs_per_s_mean"] / u["docs_per_s_mean"] - 1, 4),
                "best_worst_run": min(b["docs_per_s_all"]), "runner_up_best_run": max(u["docs_per_s_all"]),
                "ranges_non_overlapping": (min(b["docs_per_s_all"]) > max(u["docs_per_s_all"])
                                           if b["runs"] > 1 and u["runs"] > 1 else None),
                "monotonic_in_k": all(x["docs_per_s_mean"] < y["docs_per_s_mean"] for x, y in
                                      zip(sorted(in_grid, key=lambda r: r["k"]),
                                          sorted(in_grid, key=lambda r: r["k"])[1:])),
                "best_is_grid_edge": b["k"] == max(GRID)}
        refs = [{"reference_c": g["reference_c"], "docs_per_s": g["throughput"]["docs_per_s"],
                 "effective_cores": g["cost"]["effective_cores"],
                 "cpu_utilization": g["cost"]["cpu_utilization"],
                 "idle_core_count_mean": g["percore_host"]["idle_core_count_mean"],
                 "idle_core_equivalents_net_of_spin":
                     g["percore_host"].get("idle_core_equivalents_net_of_spin"),
                 "idle_spin_cores": (g["cost"].get("idle_spin_measured") or {}).get("cores"),
                 "engine_cores": g["cost"].get("engine_container_cores"),
                 "driver_cores": g["cost"].get("driver_cores"),
                 "host_cores": g["cost"].get("host_total_cores"),
                 "unattributed_cores": g["cost"].get("unattributed_cores"),
                 "available_cpus": g["cost"].get("available_cpus"),
                 "launch": g["_launch"]} for g in ref]
        # THE KNEE (G3a), by a rule fixed before the curve was seen: the SMALLEST C whose mean
        # throughput is within the arm's own replicate noise of the best C. "Within noise of the
        # best" is the only definition that does not reward buying concurrency that bought
        # nothing; where there is no replicate the noise is unknown and the knee says so.
        by_c: Dict[int, List[float]] = {}
        for r in refs:
            by_c.setdefault(r["reference_c"], []).append(r["docs_per_s"])
        if by_c:
            means = {c: sum(v) / len(v) for c, v in by_c.items()}
            best_c = max(means, key=lambda c: means[c])
            tol = floors.get(arm, {}).get("floor")
            within = ([c for c in sorted(means) if means[c] >= means[best_c] * (1 - tol)]
                      if tol is not None else [])
            call["continuous_knee"] = {
                "curve": {str(c): round(means[c], 4) for c in sorted(means)},
                "best_c": best_c, "best_docs_per_s": round(means[best_c], 4),
                "noise_floor_used": tol,
                "knee_c": (within[0] if within else None),
                "rule": "smallest C within the arm's replicate noise floor of the best C",
                "verdict": ("UNRESOLVED — no replicate on this arm, so 'within noise' has no "
                            "value" if tol is None else
                            f"knee at C={within[0]}" if within else "no C qualifies")}
        if refs and ordered:
            best_ref = max(r["docs_per_s"] for r in refs)
            call["batching_vs_continuous"] = {
                "best_batched_docs_per_s": ordered[0]["docs_per_s_mean"],
                "continuous_docs_per_s": best_ref,
                "batched_over_continuous": round(ordered[0]["docs_per_s_mean"] / best_ref, 4)}
        out[arm] = {"by_k": table, "call": call, "continuous_reference": refs,
                    "arm_units_ranked": ref_units[arm],
                    "arm_units_note": "the K grid and continuous curve are read at this arm "
                                      "shape only; other shapes are in unit_sweep"}
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
        "check_G5a_cache_effect": cache_effect(legs),
        "check_G3b_unit_sweep": unit_sweep(legs),
        "deadline_losses_per_leg": {f"{g['_launch']}/{g['leg']}": g["deadline_losses"]
                                    for g in legs if g.get("deadline_losses")},
        "box_hygiene_per_leg": {f"{g['_launch']}/{g['leg']}": {
            k: v for k, v in (g.get("box_hygiene") or {}).items() if k != "ruling"}
            for g in legs if g.get("box_hygiene")},
        "page_cache_per_leg": {f"{g['_launch']}/{g['leg']}": g.get("page_cache")
                               for g in legs if (g.get("page_cache") or {}).get("attempted")},
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
