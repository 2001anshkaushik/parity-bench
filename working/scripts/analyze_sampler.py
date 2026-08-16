#!/usr/bin/env python3
"""What the existing sampler streams already know about a leg's process fan-out and memory.

WHY. The 10k blast reported RocketRide summed RSS 84,960.6 MB against LlamaIndex 36,427.1 MB,
inverting the sequential-leg ordering (RR 3.0 GB anon vs LI 20.8 GB anon at 200 docs). The
summed figure over-counts shared pages once per process, so the question is entirely about
process fan-out: at C=32 the same arm peaked at 9,209 MB over 200 documents and 84,960 MB over
10,000. Concurrency was identical, so either the pool grows with cumulative documents, or the
pool is bounded by C and 200 documents was too short to saturate it, or the processes
themselves grow. `sampler_<arm>_<leg>.jsonl` records n_procs, rss, threads and fds every 0.5 s
and can tell these apart with no new run.

WHAT IT CANNOT ANSWER. Streams written before cgroup sampling landed carry no `cg_anon`, so
there is no deduplicated memory figure in them and none can be reconstructed — summed RSS
cannot be divided by a sharing factor that was never measured. That part needs the re-run.

READ THE THREE VERDICTS AS A SET:
  bounded-by-concurrency   n_procs saturates early and holds -> the 200-doc figure was
                           pre-saturation, and summed RSS is flat in document count
  grows-with-documents     n_procs still climbing at leg end -> processes are not being
                           reaped; summed RSS grows without bound and so does real memory
  per-process growth       n_procs flat but rss/n_procs climbing -> a leak inside the workers
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def ticks(p: Path, role: str = "service") -> list[dict]:
    out = []
    for line in p.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue                       # torn last line of a killed run
        if r.get("kind") == "role_tick" and r.get("role") == role:
            out.append(r)
    return out


def slope(xs, ys) -> float:
    """Least-squares slope. Plain arithmetic — no numpy in the harness."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def quartile_profile(rows, key):
    """Value at each quarter of the leg — enough to see saturation vs a ramp that never ends."""
    if not rows:
        return []
    return [rows[min(int(len(rows) * f), len(rows) - 1)].get(key) for f in (0, .25, .5, .75, .99)]


def report(path: Path) -> dict:
    t = ticks(path)
    if len(t) < 4:
        print(f"{path.name}: {len(t)} ticks — too few to characterise")
        return {}
    span = t[-1]["t"] - t[0]["t"]
    procs = [r["n_procs"] for r in t]
    rss_mb = [r["rss"] / 2**20 for r in t]
    per_proc = [r / max(p, 1) for r, p in zip(rss_mb, procs)]
    times = [r["t"] for r in t]
    peak_i = max(range(len(t)), key=lambda i: rss_mb[i])

    # Saturation: has the process count stopped rising by the last quarter of the leg?
    tail = procs[int(len(procs) * 0.75):]
    tail_slope = slope(times[int(len(times) * 0.75):], tail)
    still_climbing = tail_slope > 0.05          # >1 process per 20 s at leg end

    print(f"\n=== {path.name}   {len(t)} ticks over {span:.0f}s")
    print(f"  n_procs      min {min(procs):5d}  peak {max(procs):5d}  final {procs[-1]:5d}   "
          f"quartiles {quartile_profile(t, 'n_procs')}")
    print(f"  threads      peak {max(r.get('threads') or 0 for r in t):5d}   "
          f"(cgroup pids.current counts THESE, not processes)")
    print(f"  summed RSS   peak {max(rss_mb):9.1f} MB at t={times[peak_i]:.0f}s "
          f"({100 * times[peak_i] / span:.0f}% through the leg)   final {rss_mb[-1]:9.1f} MB")
    print(f"  RSS/process  first {per_proc[0]:8.1f} MB  at peak {per_proc[peak_i]:8.1f} MB  "
          f"last {per_proc[-1]:8.1f} MB")
    cg = [r.get("cg_anon") for r in t if r.get("cg_anon")]
    print(f"  cgroup anon  {'peak %.1f MB (%d samples)' % (max(cg) / 2**20, len(cg)) if cg else 'ABSENT — stream predates cgroup sampling; no deduplicated figure exists'}")

    # A cgroup charges a shared page once, so the per-cgroup total cannot fall below the summed
    # figure divided by the number of processes — that floor is reached only if every resident
    # page is mapped by every process. Approximate against `anon` specifically, since RSS also
    # counts file-backed pages, but it is a hard sanity bound on how far the over-count can go.
    print(f"  anon floor   >= {max(rss_mb) / max(max(procs), 1):9.1f} MB "
          f"(= peak summed RSS / {max(procs)} procs; the most sharing can possibly explain)")

    # Leak vs warm-up: measure per-process growth over the SECOND HALF only. Comparing against
    # tick 0 flags every model load as a leak — locally it called a 197 MB -> 1,788 MB torch
    # import "a leak inside the workers", which it plainly is not.
    h = len(times) // 2
    late_slope_mb_min = slope(times[h:], per_proc[h:]) * 60
    if still_climbing:
        v = ("GROWS-WITH-DOCUMENTS — the process count was still rising at leg end "
             f"({tail_slope * 60:.1f} procs/min). Not bounded by C; summed RSS and real "
             "memory both grow with corpus size.")
    elif late_slope_mb_min > 1.0:
        v = ("PER-PROCESS GROWTH — process count saturated but each process still gained "
             f"{late_slope_mb_min:.1f} MB/min through the second half. A leak, not warm-up.")
    else:
        v = ("BOUNDED-BY-CONCURRENCY — process count saturated and per-process memory was flat "
             f"after warm-up ({late_slope_mb_min:+.1f} MB/min). A smaller run that peaked lower "
             "simply never saturated.")
    print(f"  VERDICT: {v}")
    return {"peak_procs": max(procs), "peak_rss_mb": round(max(rss_mb), 1),
            "tail_slope_procs_per_min": round(tail_slope * 60, 2), "verdict": v.split(" —")[0],
            "has_cgroup_anon": bool(cg)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args()
    found = sorted(a.run_dir.glob("sampler_*.jsonl"))
    if not found:
        print(f"no sampler_*.jsonl in {a.run_dir}")
        return 2
    out = {p.name: report(p) for p in found}
    # The summary sidecars carry peak_process_count and distinct_pids_seen directly, and
    # distinct_pids_seen is the one number that separates a live pool from a churn of
    # short-lived processes: 33 concurrent with 10,000 distinct means one process per document.
    print("\n=== summary sidecars (cumulative distinct pids is the churn tell)")
    for s in sorted(a.run_dir.glob("sampler_*.summary.json")):
        try:
            r = (json.loads(s.read_text()).get("roles", {}).get("service", {}) or {})
        except Exception as e:
            print(f"  {s.name}: unreadable ({type(e).__name__})")
            continue
        print(f"  {s.name:34} peak_procs={r.get('peak_process_count')} "
              f"distinct_pids_seen={r.get('distinct_pids_seen')} "
              f"peak_threads={r.get('peak_thread_count')} "
              f"peak_pss_mb={r.get('peak_pss_mb')} "
              f"peak_cgroup_anon_mb={r.get('peak_cgroup_anon_mb')}")
    print("\npeak_pss_mb is the deduplicated cross-check. If it is None the sampler could not "
          "read smaps_rollup\n(different uid, no CAP_SYS_PTRACE) and summed RSS has nothing to "
          "be checked against in this run.")
    return 0 if out else 2


if __name__ == "__main__":
    raise SystemExit(main())
