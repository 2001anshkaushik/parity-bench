"""Deterministic seeding.

`hash()` on str/tuple is salted per interpreter (PEP 456), so `hash((fault, rate))` produced a
different seed in every process. Within one run all frameworks shared a plan and stayed
comparable, but the same nominal config injected 44 hangs in one run and 66 in the next — so no
result was reproducible across runs, and nothing could be pre-registered against it.

Seeds here derive from a stable digest of the config string. Same config, same seed, forever,
on any machine and any interpreter.
"""

from __future__ import annotations

import hashlib

# Bump only to deliberately re-randomise an entire study. Recorded in every result file.
SEED_NAMESPACE = "benchmark-A/v1"


def seed_for(*parts: object) -> int:
    """Stable 32-bit seed for a config tuple. Deterministic across processes and machines."""
    key = f"{SEED_NAMESPACE}|" + "|".join(str(p) for p in parts)
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
