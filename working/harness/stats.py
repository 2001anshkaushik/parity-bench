"""Statistics helpers.

Point estimates from a single run are not evidence. Everything user-facing reports a
distribution: percentiles for latency (means hide the tail, and the tail is what pages the ICP's
on-call at 3am) and bootstrap confidence intervals for cross-run comparisons.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile. `sorted_vals` must already be sorted."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


@dataclass
class Distribution:
    n: int
    mean: float
    p50: float
    p90: float
    p95: float
    p99: float
    p999: float
    min: float
    max: float
    stdev: float

    def to_dict(self) -> dict:
        return {k: (None if isinstance(v, float) and math.isnan(v) else v)
                for k, v in self.__dict__.items()}


def describe(vals: list[float]) -> Distribution:
    if not vals:
        nan = float("nan")
        return Distribution(0, nan, nan, nan, nan, nan, nan, nan, nan, nan)
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    var = sum((v - mean) ** 2 for v in s) / n if n > 1 else 0.0
    return Distribution(
        n=n, mean=round(mean, 4),
        p50=round(percentile(s, 0.50), 4), p90=round(percentile(s, 0.90), 4),
        p95=round(percentile(s, 0.95), 4), p99=round(percentile(s, 0.99), 4),
        p999=round(percentile(s, 0.999), 4),
        min=round(s[0], 4), max=round(s[-1], 4), stdev=round(math.sqrt(var), 4),
    )


def bootstrap_ci(vals: list[float], statistic=None, n_boot: int = 2000,
                 alpha: float = 0.05, seed: int = 7) -> tuple[float, float]:
    """Percentile-bootstrap CI. Distribution-free, which matters because latency is nowhere
    near normal — it is heavy-tailed and often multi-modal under contention."""
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    stat = statistic or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    n = len(vals)
    boots = []
    for _ in range(n_boot):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        boots.append(stat(sample))
    boots.sort()
    return (round(percentile(boots, alpha / 2), 4), round(percentile(boots, 1 - alpha / 2), 4))


def ratio_ci(a: list[float], b: list[float], n_boot: int = 2000,
             alpha: float = 0.05, seed: int = 11) -> tuple[float, float, float]:
    """Bootstrap CI for mean(a)/mean(b) — the 'N× faster' claim, with honest error bars.

    Returns (point, lo, hi). If the interval spans 1.0 there is no demonstrated difference, and
    the number must not be published as a win.
    """
    if not a or not b:
        return (float("nan"),) * 3
    rng = random.Random(seed)
    point = (sum(a) / len(a)) / (sum(b) / len(b)) if sum(b) else float("nan")
    boots = []
    for _ in range(n_boot):
        sa = [a[rng.randrange(len(a))] for _ in range(len(a))]
        sb = [b[rng.randrange(len(b))] for _ in range(len(b))]
        mb = sum(sb) / len(sb)
        if mb:
            boots.append((sum(sa) / len(sa)) / mb)
    if not boots:
        return (point, float("nan"), float("nan"))
    boots.sort()
    return (round(point, 4), round(percentile(boots, alpha / 2), 4),
            round(percentile(boots, 1 - alpha / 2), 4))
