# RocketRide parity posture — the full M × T curve, and the faster configuration we declined

Published so the choice of M_TOKENS is not taken on faith (Crossroad 31, 2026-08-21).

**Conditions.** 32-vCPU box (c7i.8xlarge class), engine 3.3.1 patched (`rr:patched-video`),
`--network host`, fresh container per point, one video per token per point
(ES2002a.Corner.avi → 83 frames / 2,154 detections / 166 chunks, byte-identical work at every
point), each token warmed once before the timed batch (steady state). M = `use()` tokens
(census-verified as M distinct task processes), T = the six BLAS/OMP variables on the container
(`use(threads=)` unset throughout). Idle = container cgroup CPU over a 6 s quiet window after
`use()` × M, before any work. **Values as relayed from the box; the JSONs on the box
(`probe_concurrency_T8.json` and the T=4 / T=2 / T=1 refine outputs) are authoritative.**

## 1. Tokens alone, T = 8 (the first sweep)

| M | videos/s | batch wall | cpu util (of 32) | idle cores (before work) | marginal efficiency |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.0688 | 14.5 s | 0.262 | 1.28 | — |
| 2 | 0.1006 | 19.9 s | 0.477 | 1.54 | 0.73 |
| 4 | 0.1179 | 33.9 s | 0.853 | 2.02 | 0.59 |
| 8 | 0.0246 | 325.6 s | 0.976 | 3.04 | **collapse 4.8×** — 64 threads on 32 cores, CPU pegged |
| 16 | 0.0187 | 856.8 s | 0.985 | 5.25 | 0.38 |

Read at T=8 alone this says M=4. It was the wrong axis to hold fixed (Crossroad 29).

## 2. The M × T refine — the budget line M × T = 32, plus the T = 1 floor

| M × T | videos/s | cpu util | idle cores | idle share of 32 | note |
|---:|---:|---:|---:|---:|---|
| 4 × 8 | 0.1179 | 0.853 | 2.02 | 6.3% | |
| 8 × 4 | 0.1417 | 0.863 | (not relayed) | | +20% over 4×8 |
| **16 × 2** | **0.1551** | 0.867 | 5.24 | 16.4% | **chosen** — +9.5% over 8×4 |
| 16 × 1 | 0.1345 | (not relayed) | | | −13% vs 16×2: T=1 is past the useful floor |
| 32 × 1 | 0.1602 | 0.875 | 10.04 | 31.4% | fastest measured — **declined** |

Along the budget line throughput is monotonic in tokens (tokens parallelize where intra-op
threads queue behind the detect device lock) and flattening: 16 → 32 buys **+3.3%** for double the
tokens, double the idle (+4.8 cores), and 32 model stacks in memory.

## 3. The choice — Crossroad 31

**M_TOKENS = 16, T = 2 for the parity posture.** (The default posture runs the engine default —
the six variables undeclared — because the out-of-box posture must reflect what a user gets.)

**M = 32 is measurably faster, and we declined it.** 3.3% more throughput does not justify 31% of
the box burning idle and 32 model stacks. That is a judgement, so the full curve is above; anyone
who weighs the trade differently can see exactly what they would gain and what it costs. The idle
burden is reported beside every parity number in the exports (`efficiency.idle_burden`, and the
`at_a_glance` line that opens each export) — reported, never subtracted: a configuration that wins
on throughput while idling a third of the box is still the honest production answer if that is
what the engine does; concealing the cost would be the dishonest part.

## 4. The idle burden along the curve (Ticket 4)

~1.0 core of server spin plus ~0.26 cores per live token (least-squares over M = 1…16 at T=8:
slope 0.264, intercept 0.99 — the intercept *is* the independently measured 1.002-core idle
engine). Independent of T (5.24 at T=2 vs 5.25 at T=8 for M=16). Measured 10.04 at M=32 against
the fit's 9.4: the marginal over 16 → 32 is 0.30 cores/token, slightly above the 0.26 — the fit is
a fit, the measurement stands.

## 5. Why this page exists

Stopping at the last point that happened to be tested is the error the refine caught twice
(Crossroads 29 and 30). The curve is here, end to end, including the configuration that beat the
chosen one.
