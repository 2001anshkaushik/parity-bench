#!/usr/bin/env python3
"""Why a 200-document run and a 10,000-document run report different docs/s for the SAME engine.

THE PUZZLE. Our 10k RocketRide blast reported 4.03 docs/s. Our own 200-doc blast on the same
box, same C=32, same corpus family, reported 0.52-0.67 — and Leela's 200-doc RocketRide blast
reports 0.68-0.74, agreeing with our 200 and not our 10k.

NOT THE CORPUS. The first 200 documents of our manifest average 616.4 KB against 616.2 KB for
all 10,000, and are LIGHTER by pages (22.9 vs 29.6 mean). If document weight drove it, the
200-doc run would be the faster one.

NOT A WARM-UP RAMP EITHER, and the obvious test for one is broken. Slicing a run into deciles
BY COMPLETION RANK always shows a decaying rate, because completion rank sorts documents by
duration: the fast ones finish first by construction. That profile measures the size
distribution, not the engine.

THE ACTUAL MECHANISM — heavy tail plus a finite number of waves. With C servers, throughput is
(n - warm) / span, and span is set by when the LAST document finishes. At n=200 with C=32 there
are only ~6 waves of work, so the span is governed by the slowest document in each wave — a
maximum, not a mean. At n=10,000 there are ~300 waves and the same distribution converges to
C / mean_service_time. GovDocs1 is severely heavy-tailed (median 201 KB, p90 1.8 MB), so the
gap between "governed by maxima" and "governed by the mean" is large. A 200-document throughput
number is therefore biased LOW against a 10,000-document one for a fixed engine, and the two
were never measuring the same thing.

THE TEST. Take per-document SERVICE times — the one quantity that should be invariant to run
length — and replay them through a C-server FIFO queue at both scales. If the simulation
reproduces both reported figures from one service-time distribution, the engine never changed
speed and the difference is entirely scale.

Service time is read from `admit_ns` where records carry it, and otherwise reconstructed with
the FIFO admission model (blast_latency_salvage.py, null-controlled to 0.014%).
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path


def load(p: Path) -> list[dict]:
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("completion_ns") and r.get("submit_ns"):
            rows.append(r)
    return rows


def service_times(rows, c: int) -> tuple[list[float], str]:
    """Per-document service seconds, and where they came from."""
    if all(r.get("admit_ns") for r in rows):
        return ([(r["completion_ns"] - r["admit_ns"]) / 1e9 for r in rows],
                "measured (admit_ns present)")
    spread = (max(r["submit_ns"] for r in rows) - min(r["submit_ns"] for r in rows))
    leg = max(r["completion_ns"] for r in rows) - min(r["submit_ns"] for r in rows)
    if leg and spread / leg > 0.5:
        return ([(r["completion_ns"] - r["submit_ns"]) / 1e9 for r in rows],
                "measured (submit_ns is an admission stamp)")
    order = {r["doc"]: i for i, r in enumerate(sorted(rows, key=lambda r: r["submit_ns"]))}
    comps = sorted(r["completion_ns"] for r in rows)
    t0 = min(r["submit_ns"] for r in rows)
    out = []
    for r in rows:
        k = order[r["doc"]]
        adm = t0 if k < c else comps[min(k - c, len(comps) - 1)]
        out.append(max((r["completion_ns"] - min(adm, r["completion_ns"])) / 1e9, 0.0))
    return out, "RECONSTRUCTED via the FIFO admission model (defect #29 records)"


def simulate(svc: list[float], n: int, c: int, warm: int, seed: int = 1) -> float:
    """docs/s for n documents through c FIFO servers, drawing service times from `svc`.

    Deterministic LCG rather than `random`: the same inputs must give the same answer in a
    report someone else re-runs. Sampling with replacement when n > len(svc) assumes the
    distribution, not the sequence, is what carries over — which is the claim under test.
    """
    x = seed
    draw = []
    for _ in range(n):
        x = (1103515245 * x + 12345) % (1 << 31)
        draw.append(svc[x % len(svc)])
    free = [0.0] * c                       # next-free time per server
    completions = []
    for d in draw:
        i = min(range(c), key=lambda j: free[j])
        free[i] += d
        completions.append(free[i])
    completions.sort()
    if len(completions) <= warm:
        return 0.0
    span = completions[-1] - completions[warm - 1]
    return (len(completions) - warm) / span if span > 0 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("perdoc", type=Path)
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--warm-n", type=int, default=64)
    ap.add_argument("--scales", type=int, nargs="+", default=[200, 1000, 10000])
    a = ap.parse_args()

    rows = load(a.perdoc)
    if len(rows) < a.warm_n + 5:
        print(f"{len(rows)} usable records — too few")
        return 2
    svc, how = service_times(rows, a.concurrency)
    svc = [s for s in svc if s > 0]

    obs_rows = sorted(rows, key=lambda r: r["completion_ns"])
    span = (obs_rows[-1]["completion_ns"] - obs_rows[a.warm_n - 1]["completion_ns"]) / 1e9
    observed = (len(obs_rows) - a.warm_n) / span if span > 0 else 0.0

    print(f"{a.perdoc.name}: {len(rows)} records, C={a.concurrency}, warm_n={a.warm_n}")
    print(f"  service time source: {how}")
    print(f"  service seconds   mean={st.mean(svc):8.3f}  median={st.median(svc):8.3f}  "
          f"p95={sorted(svc)[int(len(svc) * .95)]:8.3f}  max={max(svc):8.3f}")
    print(f"  tail weight       the slowest 1% carry "
          f"{100 * sum(sorted(svc)[-max(len(svc) // 100, 1):]) / sum(svc):.1f}% of all "
          f"service seconds")
    print(f"\n  OBSERVED at n={len(rows)}: {observed:.3f} docs/s")
    print(f"  ceiling C/mean   = {a.concurrency / st.mean(svc):.3f} docs/s "
          "(what an infinitely long run converges to)\n")
    print(f"  {'n':>8}  {'simulated docs/s':>17}  {'% of ceiling':>13}")
    ceil = a.concurrency / st.mean(svc)
    for n in a.scales:
        # Three seeds: one draw of a heavy-tailed distribution is not a measurement.
        rs = [simulate(svc, n, a.concurrency, a.warm_n, seed=s) for s in (1, 7, 99)]
        print(f"  {n:>8}  {st.mean(rs):>10.3f} +/-{(max(rs) - min(rs)) / 2:<5.3f}  "
              f"{100 * st.mean(rs) / ceil:>12.0f}%")
    print("\n  If the simulated small-n figure lands near the observed small-n figure and the")
    print("  simulated large-n figure near the large-n one, ONE service-time distribution")
    print("  explains both, and the engine never changed speed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
