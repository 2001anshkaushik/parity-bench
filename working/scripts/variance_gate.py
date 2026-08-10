#!/usr/bin/env python3
"""Runnable variance gate — exits non-zero when a measurement is too noisy to report.

A run that fails this gate is not a slow result, it is an INVALID measurement. The point is to
make that failure loud and automatable rather than a judgement call someone makes after seeing
the numbers.

Defaults come from measured evidence (see VARIANCE_PROTOCOL.md):
  --discard 2   the first iterations are a warmup artefact; discarding them took observed spread
                from 17.7% to 1.7% on identical work
  --reps 5      n=3 detects gross problems, n=5 gives a usable spread estimate
  --cooldown 5  independently worth ~13 points of spread
  --threshold 0.10   roughly 2x the worst well-behaved case (0.7-4.4%)

Usage:
    # gate a shell command that prints a single number (the metric) on stdout
    python variance_gate.py --cmd "./bench.sh" --reps 5

    # or gate a Python callable
    from variance_gate import gate
    result = gate(lambda: measure_throughput(), reps=5)
    if not result["passed"]: raise SystemExit("variance gate failed")
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def preconditions() -> dict:
    """Check what we can, and be explicit about what we cannot.

    Deliberately does NOT gate on load average: we tested that hypothesis directly and refuted it
    (measuring immediately after driving load to 7.88 gave the LOWEST spread observed, 0.7%).
    Recording it as context, not as a pass/fail criterion.
    """
    checks: dict = {}
    checks["thread_env"] = {k: os.environ.get(k) for k in
                            ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                             "VECLIB_MAXIMUM_THREADS", "TOKENIZERS_PARALLELISM")}
    checks["thread_env_pinned"] = all(
        checks["thread_env"].get(k) == "1"
        for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"))
    checks["load_avg"] = [round(x, 2) for x in os.getloadavg()]   # context only, not a gate

    # torch device is the single biggest lever (2-3x throughput, 10x spread). Report if reachable.
    checks["torch_device_default"] = "UNVERIFIED (torch not importable here)"
    try:
        import torch  # noqa: F401
        checks["torch_num_threads"] = __import__("torch").get_num_threads()
        checks["mps_available"] = __import__("torch").backends.mps.is_available()
        checks["torch_device_default"] = (
            "mps would be auto-selected by sentence-transformers"
            if checks["mps_available"] else "cpu")
    except Exception:
        pass

    if shutil.which("pmset"):
        try:
            out = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True,
                                 timeout=5).stdout
            checks["thermal_warning"] = "No thermal warning" not in out
        except Exception:
            checks["thermal_warning"] = "UNVERIFIED"
    return checks


def _extract_metric(stdout: str, pattern: str | None) -> float | None:
    if pattern:
        m = re.search(pattern, stdout)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                return None
        return None
    nums = _NUM.findall(stdout.strip().splitlines()[-1]) if stdout.strip() else []
    return float(nums[-1]) if nums else None


def gate(fn, reps: int = 5, discard: int = 2, cooldown: float = 5.0,
         threshold: float = 0.10, label: str = "measurement") -> dict:
    """Run `fn` (reps + discard) times, discard warmup, return a verdict dict."""
    raw: list[float] = []
    for i in range(reps + discard):
        v = fn()
        raw.append(v)
        if cooldown and i < reps + discard - 1:
            time.sleep(cooldown)
    kept = raw[discard:]
    kept_clean = [v for v in kept if v is not None]
    if len(kept_clean) < 2:
        return {"passed": False, "reason": "fewer than 2 usable measurements",
                "raw": raw, "label": label}
    med = statistics.median(kept_clean)
    spread = (max(kept_clean) - min(kept_clean)) / max(kept_clean)
    passed = spread <= threshold
    return {
        "label": label, "passed": passed,
        "median": round(med, 4), "spread_frac": round(spread, 4),
        "threshold": threshold,
        "values_kept": [round(v, 4) for v in kept_clean],
        "values_discarded_as_warmup": [round(v, 4) for v in raw[:discard] if v is not None],
        "reps": reps, "discard": discard, "cooldown_s": cooldown,
        "preconditions": preconditions(),
        "verdict": ("REPORTABLE" if passed else
                    "INVALID MEASUREMENT — fix preconditions and re-run, do not report the median"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True, help="shell command; its metric is read from stdout")
    ap.add_argument("--metric-regex", default=None,
                    help=r"regex with one capture group, e.g. 'throughput=([0-9.]+)'. "
                         "Default: last number on the last stdout line.")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--discard", type=int, default=2)
    ap.add_argument("--cooldown", type=float, default=5.0)
    ap.add_argument("--threshold", type=float, default=0.10)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    def run_once() -> float | None:
        r = subprocess.run(args.cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  [warn] command exited {r.returncode}: {(r.stderr or '')[-200:]}",
                  file=sys.stderr)
        return _extract_metric(r.stdout, args.metric_regex)

    print(f"variance gate: {args.reps} reps (+{args.discard} discarded), "
          f"cooldown {args.cooldown}s, threshold {args.threshold*100:.0f}%")
    res = gate(run_once, reps=args.reps, discard=args.discard,
               cooldown=args.cooldown, threshold=args.threshold, label=args.cmd)

    print(f"  discarded warmup : {res.get('values_discarded_as_warmup')}")
    print(f"  measured         : {res.get('values_kept')}")
    print(f"  median           : {res.get('median')}")
    print(f"  spread           : {res.get('spread_frac', 0)*100:.1f}%  "
          f"(threshold {args.threshold*100:.0f}%)")
    pc = res.get("preconditions", {})
    if not pc.get("thread_env_pinned"):
        print("  [precondition] thread env NOT pinned — set OMP/MKL/OPENBLAS_NUM_THREADS=1")
    if pc.get("mps_available"):
        print("  [precondition] mps is available: sentence-transformers will auto-select the GPU "
              "unless device is pinned. GPU spread was 14-25% vs CPU 0.7-4.4%.")
    print(f"  VERDICT: {res['verdict']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
