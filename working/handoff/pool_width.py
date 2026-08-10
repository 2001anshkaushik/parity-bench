"""Effective concurrency width measurement — WITH A GUARD AGAINST ITS OWN WORST FAILURE MODE.

Method: hold each item for a known duration T, offer far more work than the pool can run at once,
measure steady-state throughput X. For a pool of width W serving holds of length T, X = W / T
exactly, so W = X * T.

THE FAILURE MODE THIS GUARDS
----------------------------
If the OFFERED concurrency is below the true width, the estimator returns the offered value —
not the width — and it does so with near-zero run-to-run spread. Calibrated against a known
16-wide pool:

    offered=4   -> estimate 3.97   (-75.2% error)   spread 0.0%
    offered=8   -> estimate 7.94   (-50.4% error)   spread 0.1%
    offered=16  -> estimate 15.86  ( -0.9% error)
    offered=64  -> estimate 15.87  ( -0.8% error)

A confidently wrong number that looks precise is worse than a noisy one, because nothing about the
output signals a problem. Documenting it is not enough when the whole team will run the tool.

So `measure_width()` ESCALATES offered concurrency until the estimate stops tracking it, and
HARD-FAILS if it cannot escape the tracking regime. You cannot get a silently-truncated answer out
of this function.

Secondary guard: holds shorter than ~0.25 s under-read (measured -19.1% at T=0.01 s) because
dispatch overhead becomes a significant fraction of the hold. Short holds are rejected.

    from pool_width import measure_width
    r = measure_width(submit_fn, hold_s=0.5)
    r["width"], r["confidence"], r["escalation"]
"""

from __future__ import annotations

import statistics
import time
from typing import Callable

MIN_HOLD_S = 0.25
TRACKING_TOLERANCE = 0.15     # estimate within 15% of offered => probably tracking, not measuring
MAX_OFFERED = 4096


class WidthMeasurementError(RuntimeError):
    """Raised when a trustworthy width could not be established. Never returns a guess."""


def _estimate(submit_fn: Callable[[int, float], float], offered: int, hold_s: float) -> float:
    """submit_fn(offered, hold_s) -> observed throughput (items/sec) at steady state."""
    thr = submit_fn(offered, hold_s)
    return thr * hold_s


def measure_width(submit_fn: Callable[[int, float], float], hold_s: float = 0.5,
                  start_offered: int = 8, reps: int = 3,
                  max_offered: int = MAX_OFFERED) -> dict:
    """Measure effective width, escalating offered concurrency until the estimate plateaus.

    Returns a dict with `width`, `confidence`, and the full escalation trace. Raises
    WidthMeasurementError rather than returning a number it cannot stand behind.
    """
    if hold_s < MIN_HOLD_S:
        raise WidthMeasurementError(
            f"hold_s={hold_s} is below the {MIN_HOLD_S}s floor. Short holds under-read width "
            f"(measured -19.1% at 0.01s) because dispatch overhead becomes a large fraction of "
            f"the hold. Use hold_s >= {MIN_HOLD_S}.")

    trace: list[dict] = []
    offered = max(2, start_offered)
    prev_est: float | None = None

    while offered <= max_offered:
        ests = [_estimate(submit_fn, offered, hold_s) for _ in range(reps)]
        est = statistics.median(ests)
        spread = (max(ests) - min(ests)) / max(ests) if max(ests) else 0.0
        # "Tracking" = the estimate is pinned near the offered concurrency, which means we are
        # measuring what we offered rather than what the pool can do.
        tracking = abs(est - offered) / offered <= TRACKING_TOLERANCE
        trace.append({"offered": offered, "estimates": [round(e, 2) for e in ests],
                      "median_estimate": round(est, 2), "spread_frac": round(spread, 3),
                      "tracking_offered": tracking})
        if not tracking:
            # Escaped the tracking regime: the pool refused to go faster, so this is the width.
            # Confirm with one more doubling — if the estimate is stable, we are done.
            confirm_offered = min(offered * 2, max_offered)
            cests = [_estimate(submit_fn, confirm_offered, hold_s) for _ in range(reps)]
            cest = statistics.median(cests)
            drift = abs(cest - est) / max(est, 1e-9)
            trace.append({"offered": confirm_offered, "estimates": [round(e, 2) for e in cests],
                          "median_estimate": round(cest, 2), "confirmation": True,
                          "drift_vs_previous": round(drift, 3)})
            if drift > 0.15:
                # Still climbing: not a plateau. Keep escalating.
                offered = confirm_offered
                prev_est = cest
                continue
            width = statistics.median([est, cest])
            return {"width": round(width, 2), "hold_s": hold_s, "reps": reps,
                    "confidence": "VERIFIED (escaped tracking regime, confirmed by doubling)",
                    "offered_at_measurement": offered, "escalation": trace,
                    "spread_frac": round(spread, 3)}
        prev_est = est
        offered *= 2

    raise WidthMeasurementError(
        f"Estimate tracked offered concurrency all the way to {max_offered} without plateauing. "
        f"Either the true width exceeds {max_offered}, or the system under test has no fixed "
        f"width (e.g. it spawns unbounded workers). Refusing to report a number: the value would "
        f"be the offered concurrency, not the width. Trace: {trace[-3:]}")
