"""Arm-agnostic metrics — pure functions, adopted from the teammates' code, not invented.

Provenance of every definition (ADOPT LIST 2026-08-14; settled decisions in the same message):
  perf_window / throughput      Leela  metrics/m1_m2_perf.py:8-62   (warm-up excluded METRIC-SIDE,
                                by completion rank — NOT driver-side spans)
  latency shape + mode label    Leela  metrics/m1_m2_perf.py:103-122
  percentile                    Shashi metrics.py:84-93  (nearest-rank, integer ceil,
                                NO interpolation — settled; stats.py's linear interp is NOT used)
  docs_per_s / chunks_per_s     both   (Shashi metrics.py:24-29, Leela m1_m2_perf.py:57-58)
  cpu_s_per_doc / per_chunk     both   (Shashi metrics.py:32-37, Leela m7_resources.py:118-124)
  effective_cores               Leela  m7_resources.py:26 == Shashi's achieved_parallelism
                                (metrics.py:40-44); same formula, Leela's name
  cpu_utilization + valid flag  Leela  m7_resources.py:127-135 — >1.0 is flagged INVALID,
                                never clamped
  cost window slicing           both   (Shashi cstats.py:237-272, Leela m7_resources.py:56-100):
                                anchor on the last sample AT OR BEFORE t0, delta the cumulative
                                CPU counter, peak RSS from inside the window only
  unavailable => None           Shashi metrics.py:6-7 ("never 0, never inf — a failed run can't
                                masquerade as a fast one")

Nothing here is a new metric. Where the two teammates disagree (warm-up placement, percentile
method) the choice was settled by the team and is recorded above, not re-litigated here.

Row contract (per-doc JSONL, one dict per document):
  doc            str
  submit_ns      int   epoch nanoseconds (time.time_ns()) at submission
  completion_ns  int   epoch nanoseconds at response
  ok             bool
  n_chunks       int   (present when ok)

Cost-series contract (pluggable sampler — the metric functions never know the source):
  list of (ts_epoch_s, cpu_total_s_cumulative, rss_mb) tuples, one per sample.
    - psutil tree source (this laptop, native): series_from_role_ticks()
    - cgroup source (Docker on the box, Leela's aws_run/box/cgroup_sampler.py schema):
      series_from_cgroup_jsonl()
"""
from __future__ import annotations

import json
from typing import Any, Optional


def _pos(*vals) -> bool:
    """True when every value is a positive number. Shashi metrics.py:19-21, verbatim logic."""
    return all(isinstance(v, (int, float)) and v > 0 for v in vals)


# ---------------------------------------------------------------- scalar metrics (both teammates)

def docs_per_s(docs, wall_s) -> Optional[float]:
    return docs / wall_s if _pos(docs, wall_s) else None


def chunks_per_s(chunks, wall_s) -> Optional[float]:
    return chunks / wall_s if _pos(chunks, wall_s) else None


def cpu_s_per_doc(cpu_s, docs) -> Optional[float]:
    return cpu_s / docs if _pos(cpu_s, docs) else None


def cpu_s_per_chunk(cpu_s, chunks) -> Optional[float]:
    return cpu_s / chunks if _pos(cpu_s, chunks) else None


def effective_cores(cpu_s, wall_s) -> Optional[float]:
    """Average cores busy across the span. Leela's name; Shashi calls the identical formula
    achieved_parallelism."""
    return cpu_s / wall_s if _pos(cpu_s, wall_s) else None


def cpu_utilization(cpu_s, wall_s, cpus) -> dict:
    """Fraction of the CPU allocation actually used. >1.0 means cost was attributed outside
    the window or outside the tree — the run is INVALID there; flagged, never clamped
    (Leela m7_resources.py:131-135)."""
    if not _pos(cpu_s, wall_s, cpus):
        return {"cpu_utilization": None, "cpu_utilization_valid": None}
    util = cpu_s / (wall_s * cpus)
    out = {"cpu_utilization": round(util, 4), "cpu_utilization_valid": util <= 1.0,
           "available_cpus": cpus}
    if util > 1.0:
        out["cpu_utilization_error"] = (
            "utilization > 1.0 — CPU attributed outside the measured window or outside "
            "this service tree; the cost numbers of this cell are INVALID")
    return out


def percentile(values, p) -> Optional[float]:
    """Nearest-rank, deterministic, no interpolation — Shashi metrics.py:84-93 exactly.
    Ignores None entries (failed items are counted elsewhere, never as latency)."""
    vals = sorted(v for v in (values or []) if isinstance(v, (int, float)))
    if not vals or not isinstance(p, (int, float)) or not 0 <= p <= 100:
        return None
    if p == 0:
        return vals[0]
    rank = max(1, -(-len(vals) * p // 100))  # ceil(n*p/100), integer math
    return vals[int(rank) - 1]


# ---------------------------------------------------------------- window (Leela, metric-side)

def ok_records(rows) -> list[dict]:
    return [r for r in (rows or []) if r.get("ok")]


def by_completion(rows) -> list[dict]:
    return sorted((r for r in (rows or []) if r.get("completion_ns") is not None),
                  key=lambda r: r["completion_ns"])


def perf_window(rows, warm_n: int = 0) -> dict:
    """Slice a run into (warmup, window) by COMPLETION order — Leela m1_m2_perf.py:8-28.

    warm_n=0 -> whole run is the window, span from first submit to last completion.
    warm_n=N -> the first N completions are excluded; the window spans from the Nth
    completion to the last. Too few completions is an error dict, never a silent pass.
    """
    done = by_completion(rows)
    if len(done) <= warm_n:
        return {"error": f"{len(done)} completions <= warm_n={warm_n}"}
    if warm_n:
        boundary_ns = done[warm_n - 1]["completion_ns"]
        window = [r for r in done if r["completion_ns"] > boundary_ns]
        span_s = (done[-1]["completion_ns"] - boundary_ns) / 1e9
    else:
        boundary_ns = None
        window = done
        submits = [r["submit_ns"] for r in rows if r.get("submit_ns") is not None]
        if not submits:
            return {"error": "warm_n=0 needs submit_ns on at least one row"}
        span_s = (done[-1]["completion_ns"] - min(submits)) / 1e9
    return {"window": window, "span_s": span_s, "warm_n": warm_n,
            "boundary_ns": boundary_ns}


def throughput(rows, warm_n: int = 0) -> dict:
    """M1 — docs/s AND chunks/s, never one alone (Leela m1_m2_perf.py:31-62).
    window_t0_ns/t1_ns are returned so the cost sampler is sliced to the IDENTICAL span."""
    w = perf_window(rows, warm_n)
    if "error" in w:
        return w
    ok = ok_records(w["window"])
    chunks = sum(r.get("n_chunks") or 0 for r in ok)
    span = w["span_s"]
    t1 = max((r["completion_ns"] for r in w["window"]), default=None)
    if w["boundary_ns"] is not None:
        t0 = w["boundary_ns"]
    else:
        t0 = min((r["submit_ns"] for r in rows if r.get("submit_ns") is not None),
                 default=None)
    return {
        "successful_in_window": len(ok),
        "window_docs": len(w["window"]),
        "window_span_s": round(span, 3),
        "successful_chunks": chunks,
        "docs_per_s": round(len(ok) / span, 4) if span > 0 else None,
        "chunks_per_s": round(chunks / span, 4) if span > 0 else None,
        "warm_n": warm_n,
        "window_t0_ns": t0,
        "window_t1_ns": t1,
    }


def latency(rows, warm_n: int = 0, mode: str = "closed-loop") -> dict:
    """Leela's shape and labels (m1_m2_perf.py:103-122); percentile method is the settled
    nearest-rank. mode is a LABEL: 'closed-loop' => true service latency; 'open-loop-blast'
    => batch-position latency (includes queue wait). The two must never share a table row."""
    w = perf_window(rows, warm_n)
    if "error" in w:
        return w
    ok = ok_records(w["window"])
    lats = [(r["completion_ns"] - r["submit_ns"]) / 1e9 for r in ok
            if r.get("submit_ns") is not None]
    if not lats:
        return {"error": "no successful docs in window"}
    out = {"n": len(lats)}
    for p in (50, 90, 95, 99):
        out[f"p{p}"] = round(percentile(lats, p), 4)
    out["max"] = round(max(lats), 4)
    out["mean"] = round(sum(lats) / len(lats), 4)
    out["failed_items"] = len(w["window"]) - len(ok)
    out["label"] = ("true service latency" if mode == "closed-loop"
                    else "batch-position latency — includes queue wait")
    out["mode"] = mode
    out["warm_n"] = warm_n
    return out


# ---------------------------------------------------------------- cost sources (pluggable)

def series_from_role_ticks(jsonl_text: str, role: str, epoch_anchor_s: float) -> list[tuple]:
    """Normalize our psutil TreeCollector JSONL (role_tick rows, collector.py:394-398).

    The collector's `t` is seconds since ITS start; `epoch_anchor_s` is the epoch time the
    parent observed at collector readiness. Anchor error is bounded by the readiness
    handshake (<0.1 s), well under the 0.5 s sampling interval that already bounds edge
    attribution. cpu_s is cumulative and includes retired (dead-PID) CPU — the roll-forward
    is why this source is trustworthy for the engine's per-task children.
    """
    out = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") != "role_tick" or r.get("role") != role:
            continue
        out.append((epoch_anchor_s + r["t"], r["cpu_s"], r["rss"] / 1048576))
    return out


def series_from_cgroup_jsonl(jsonl_text: str) -> list[tuple]:
    """Normalize Leela's in-container cgroup sampler JSONL (aws_run/box/cgroup_sampler.py:
    {ts, cpu_total_s, rss_mb_sum, ...}, ts already epoch). The Docker-mode source."""
    out = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "ts" not in r or "cpu_total_s" not in r:
            continue
        out.append((r["ts"], r["cpu_total_s"], r.get("rss_mb_sum")))
    return out


def cost_window(series, t0_s, t1_s) -> Optional[dict]:
    """Cost attributed to [t0, t1] only — the throughput window. Anchor on the last sample
    at or before t0 (the cumulative counter's value ENTERING the window), peak RSS from
    inside only. Both teammates' math (Shashi cstats.py:250-272, Leela m7_resources.py:77-99).
    Returns None rather than guessing when the window cannot be resolved."""
    if not series or t0_s is None or t1_s is None or t1_s <= t0_s:
        return None
    before = [s for s in series if s[0] <= t0_s]
    inside = [s for s in series if t0_s < s[0] <= t1_s]
    if not inside:
        return None
    pts = ([before[-1]] if before else []) + inside
    cpus = [c for _, c, _ in pts if c is not None]
    if len(cpus) < 2:
        return None
    rsss = [r for _, _, r in inside if r is not None]
    return {
        "cpu_s": round(cpus[-1] - cpus[0], 3),
        "peak_rss_mb": round(max(rsss), 1) if rsss else None,
        "samples_in_window": len(inside),
        "window_s": round(t1_s - t0_s, 3),
    }


# ---------------------------------------------------------------- assembly

def derive_side(rows, cost_series, warm_n: int, available_cpus, mode: str) -> dict:
    """One arm, one send mode, one warm_n: throughput + latency + cost over the SAME window.
    cost_series may be None/empty — every cost field is then None, never 0 (a missing
    sampler must not masquerade as a free run)."""
    tp = throughput(rows, warm_n)
    if "error" in tp:
        return {"error": tp["error"], "warm_n": warm_n, "mode": mode}
    lat = latency(rows, warm_n, mode=mode)
    d = {"mode": mode, "warm_n": warm_n, **tp, "latency": lat}
    cw = cost_window(cost_series,
                     tp["window_t0_ns"] / 1e9 if tp.get("window_t0_ns") else None,
                     tp["window_t1_ns"] / 1e9 if tp.get("window_t1_ns") else None)
    if cw:
        cpu = cw["cpu_s"]
        d.update({
            "cpu_s": cpu,
            "cpu_s_per_doc": round(cpu_s_per_doc(cpu, tp["successful_in_window"]), 4)
            if cpu_s_per_doc(cpu, tp["successful_in_window"]) is not None else None,
            "cpu_s_per_chunk": round(cpu_s_per_chunk(cpu, tp["successful_chunks"]), 5)
            if cpu_s_per_chunk(cpu, tp["successful_chunks"]) is not None else None,
            "effective_cores": round(effective_cores(cpu, cw["window_s"]), 3)
            if effective_cores(cpu, cw["window_s"]) is not None else None,
            "peak_rss_mb": cw["peak_rss_mb"],
            "cost_samples_in_window": cw["samples_in_window"],
            **cpu_utilization(cpu, cw["window_s"], available_cpus),
        })
    else:
        d.update({"cpu_s": None, "cpu_s_per_doc": None, "cpu_s_per_chunk": None,
                  "effective_cores": None, "peak_rss_mb": None,
                  "cpu_utilization": None, "cpu_utilization_valid": None,
                  "cost_note": "no cost samples resolved to this window"})
    return d
