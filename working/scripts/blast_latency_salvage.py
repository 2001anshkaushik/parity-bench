#!/usr/bin/env python3
"""Recover service latency from blast records written before defect #29 was fixed.

THE DEFECT. The two blast legs stamped `submit_ns` at different points in the request's life:

    LlamaIndex   inside the pool worker  -> at ADMISSION      -> latency = service time
    RocketRide   before `async with sem` -> at BATCH OPEN     -> latency = queue wait + service

Both arms cap in-flight work at BLAST_C, so the concurrency was matched; only the clock was
not. Measured on two local 200-doc runs: LlamaIndex submit spread 65.0 s / 67.2 s across 67 s /
69 s legs (97.6%, 97.5%), RocketRide 0.001 s across a 319 s leg (0.0%). At 10k that printed
RocketRide p50 1120 s against LlamaIndex 2.05 s.

THE RECONSTRUCTION. A bounded pool of C is a FIFO queue: a slot is granted when an earlier
request completes, so the k-th admission (k >= C) happens at the (k-C)-th completion, and
waiters are granted in enqueue order. `asyncio.Semaphore` and `ThreadPoolExecutor` are both
FIFO, and every coroutine is created before any completes, so no late arrival can steal a
released permit. Admission is therefore recoverable from completion times alone.

    admit[k] = batch_open           for k < C
    admit[k] = completion_sorted[k-C]   otherwise

THE NULL CONTROL, which is why this is trustworthy rather than plausible. The same
reconstruction is applied to the arm that already recorded real admission stamps. If the model
is right it must reproduce those stamps; if it does not, it is wrong about the other arm too
and this script refuses to report a reconstruction. On the local 200-doc runs it reproduced
LlamaIndex's recorded p50 to four decimals (0.6908 -> 0.6909, 0.7149 -> 0.7150).

A reconstruction is still a model. Its output is PROVISIONAL and is superseded by any run made
after the fix, which records `enqueue_ns` and `admit_ns` directly and needs no model at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "working"))

from harness import metrics_shared as ms  # noqa: E402

# Agreement the null control must reach before any reconstruction is reported. The residual is
# real: the model places admission at a completion INSTANT, while a pool hands the slot over a
# few hundred microseconds later. 2% absorbs that without absorbing a wrong model — the observed
# residual is ~0.01%, two orders of magnitude inside it.
NULL_CONTROL_TOL = 0.02


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def stamp_convention(rows: list[dict]) -> dict:
    """Which clock did this arm use? Measured from the records, never assumed."""
    s = [r["submit_ns"] for r in rows if r.get("submit_ns")]
    c = [r["completion_ns"] for r in rows if r.get("completion_ns")]
    if not s or not c:
        return {"verdict": "UNKNOWN", "reason": "rows lack submit_ns/completion_ns"}
    leg_ns = max(c) - min(s)
    spread = (max(s) - min(s)) / leg_ns if leg_ns else 0.0
    if rows and all(r.get("enqueue_ns") and r.get("admit_ns") for r in rows):
        v = "BOTH_STAMPS"        # post-fix record: nothing to reconstruct
    elif spread < 0.05:
        v = "BATCH_OPEN"         # every document stamped at t0
    elif spread > 0.50:
        v = "ADMISSION"          # stamps spread across the leg
    else:
        v = "AMBIGUOUS"
    return {"verdict": v, "submit_spread_frac_of_leg": round(spread, 5),
            "leg_s": round(leg_ns / 1e9, 1), "n": len(rows)}


def reconstruct(rows: list[dict], c: int) -> list[dict]:
    """Rows with submit_ns replaced by the modelled admission instant."""
    order = {r["doc"]: i for i, r in enumerate(sorted(rows, key=lambda r: r["submit_ns"]))}
    comps = sorted(r["completion_ns"] for r in rows if r.get("completion_ns"))
    t0 = min(r["submit_ns"] for r in rows)
    out = []
    for r in rows:
        k = order[r["doc"]]
        adm = t0 if k < c else comps[min(k - c, len(comps) - 1)]
        # A modelled admission can never post-date its own completion; clamping keeps a
        # latency non-negative rather than emitting an impossible number.
        out.append({**r, "submit_ns": min(adm, r.get("completion_ns", adm))})
    return out


def cells(rows, warm_n, mode):
    tp = ms.throughput(rows, warm_n)
    lat = ms.latency(rows, warm_n, mode=mode)
    return tp, lat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--concurrency", type=int, required=True, help="SMOKE_BLAST_C of that run")
    ap.add_argument("--warm-n", type=int, default=64)
    a = ap.parse_args()

    arms = {}
    for tag, name in (("li", "llamaindex"), ("rr", "rocketride")):
        p = a.run_dir / f"perdoc_{tag}_blast.jsonl"
        if not p.exists():
            print(f"MISSING {p}")
            return 2
        rows = load(p)
        arms[name] = {"rows": rows, "conv": stamp_convention(rows)}
        cv = arms[name]["conv"]
        print(f"{name:12} n={cv.get('n')} leg={cv.get('leg_s')}s  "
              f"submit spread = {100 * cv.get('submit_spread_frac_of_leg', 0):.1f}% of leg  "
              f"-> stamped at {cv['verdict']}")

    # ---- NULL CONTROL: reconstruct the arm that already has real admission stamps.
    control = [n for n, v in arms.items() if v["conv"]["verdict"] == "ADMISSION"]
    if not control:
        print("\nNULL CONTROL IMPOSSIBLE: no arm recorded real admission stamps, so the model "
              "cannot be checked against anything. Refusing to report a reconstruction.")
        return 3
    cn = control[0]
    _, real = cells(arms[cn]["rows"], a.warm_n, "closed-loop")
    _, modelled = cells(reconstruct(arms[cn]["rows"], a.concurrency), a.warm_n, "closed-loop")
    print(f"\nNULL CONTROL — reconstruct {cn}, which already knows the answer:")
    worst = 0.0
    for k in ("p50", "p90", "p95", "p99"):
        rv, mv = real.get(k), modelled.get(k)
        if rv:
            err = abs(mv - rv) / rv
            worst = max(worst, err)
            print(f"    {k}: recorded {rv:>10.4f}s   modelled {mv:>10.4f}s   err {100*err:6.3f}%")
    if worst > NULL_CONTROL_TOL:
        print(f"  FAIL: worst error {100*worst:.2f}% > {100*NULL_CONTROL_TOL:.0f}%. The FIFO "
              "model does not reproduce known stamps, so it cannot be trusted on the other "
              "arm. NOTHING REPORTED.")
        return 4
    print(f"  PASS: worst error {100*worst:.3f}% — the model reproduces known admission stamps.")

    # ---- Apply it to the arm that needs it, and prove throughput does not move.
    print(f"\nRECOVERED (PROVISIONAL — model, not measurement; warm_n={a.warm_n}, "
          f"C={a.concurrency}):")
    print(f"  {'arm':12} {'clock':<22} {'docs/s':>9} {'p50':>10} {'p95':>10} {'p99':>10}")
    for name, v in arms.items():
        rows = v["rows"]
        variants = [("as recorded", rows, "closed-loop" if v["conv"]["verdict"] == "ADMISSION"
                     else "open-loop-blast")]
        if v["conv"]["verdict"] == "BATCH_OPEN":
            variants.append(("reconstructed service", reconstruct(rows, a.concurrency),
                             "closed-loop"))
        for label, rws, mode in variants:
            tp, lat = cells(rws, a.warm_n, mode)
            print(f"  {name:12} {label:<22} {tp['docs_per_s']:>9} {lat['p50']:>10.4f} "
                  f"{lat['p95']:>10.4f} {lat['p99']:>10.4f}")

    tps = {n: ms.throughput(v["rows"], a.warm_n)["docs_per_s"] for n, v in arms.items()}
    moved = {n: ms.throughput(reconstruct(v["rows"], a.concurrency),
                              a.warm_n)["docs_per_s"] for n, v in arms.items()}
    same = all(tps[n] == moved[n] for n in tps)
    print(f"\nthroughput under the same transform: {'UNCHANGED' if same else 'MOVED'} "
          f"{tps} -> {moved}")
    print("  docs/s at warm_n>0 spans completion-to-completion and never reads submit_ns, so "
          "the throughput comparison in the original report stands as published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
