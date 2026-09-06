# Films-500 — results, read from the landed artifacts (2026-09-06)

Campaign `films500_mainrun_20260904T204852Z`, landed at box commit
`cc98ca6b`, bundle sha `1882c0d4…`, ff-merged to `origin/video-bench`.
Six legs, 498 measured films each, 0 errors, every per-leg gate PASS or
NOT RUN. **NOT the sizing report** — the 35-film DEFINITIVE stays as
written; re-scoping is Ansh's separate ruling. Every figure below is
re-read from the landed exports/records, not the run log.

## Partition (the finding surface) — HELD exactly

`partition_check.json`, both parity cross files, verbatim:
`partition_holds: true`, `above_diverging=433`, `below_clean=65`,
`ABOVE_560_PASSING=[]`, `BELOW_560_FAILING=[]`, `missing_dimensions=[]`,
`partition_rc=0`. Both cross files: `PASS=False, n_videos=498,
failing=433`. **Ruling U predicted 433 of 498 before the run; the run
produced exactly 433, no exceptions across 498 films, both passes.**
The 87% edge fraction measured at manifest build (435/500, 433 measured)
reproduced as the failing count to the film.

## Throughput (banked, re-read)

| cell | blast f/s p1/p2 | window f/s (n=482) | cores | util | idle |
|---|---|---|---|---|---|
| LI N16×T2 | 12.249 / 12.953 | 12.212 / 12.957 | 28.604 / 28.45 | 89.4 / 88.9% | 0.071 / 0.067 |
| RR M16×T2 | 12.198 / 11.609 | 12.254 / 11.613 | 31.013 / 31.084 | 96.9 / 97.1% | 4.689 / 4.656 |
| sequential (n=5) | LI 1.834 · RR 2.081 | — | 1.88 · 6.95 | 5.9 / 21.7% | — |

cross_fail=1 (expected). Pass means: **LI 12.601 f/s, RR 11.904** —
LI +5.9% span.

## (a) Why both arms are faster at 500 than at 35 — ramp/drain geometry, confirmed

Pass means: LI 12.601 vs 10.134 (+24%), RR 11.904 vs 9.512 (+25%). The
mechanism is exactly the sizing report's ramp/drain geometry, and the
span-vs-window figures prove it:

| | span f/s | window f/s | gap |
|---|---|---|---|
| **500** LI | 12.601 | 12.585 | **+0.1%** |
| **500** RR | 11.904 | 11.933 | **−0.3%** |
| 35 LI | 10.134 | 8.439 | +20.1% |
| 35 RR | 9.512 | 8.261 | +15.2% |

At 35 films the steady window ran far above the span — half the
completions landed in ramp/drain where 16 lanes could not stay fed, so
the whole-batch rate was dragged well below the saturated rate. **At 500
the window and span nearly coincide** (LI 12.601 vs 12.585; RR 11.904 vs
11.933): 498 items keep all 16 lanes saturated for essentially the whole
leg, ramp and drain are a negligible fraction, and the whole-batch rate
rises to meet the saturated rate. **The 500 numbers ARE the sizing
report's window numbers, arrived at as span.** LI's window barely moved
(8.439→12.585 is mostly the corpus, but the saturated rate itself is
higher at 500 — different film mix); the load-bearing fact is the gap
collapse, and it holds for both arms.

## (b) Per-core, both ways — the effective-core gap crossed zero

| | per MEASURED core | per EFFECTIVE core (idle removed) |
|---|---|---|
| **500** | LI 0.4417 · RR 0.3834 → **LI +15.2%** | LI 0.4428 · RR 0.4513 → **RR +1.9%** |
| 35 | LI 0.4724 · RR 0.3727 → LI +26.7% | LI 0.4739 · RR 0.4562 → LI +3.9% |

(effective cores: RR minus 4.67 idle, LI minus 0.07.) Two things moved,
both toward RR:

1. **The measured-core gap narrowed 26.7% → 15.2%.** RR is now
   saturating the box (97.0% util vs 79.8% at 35) — its idle 4.67 cores
   are a smaller fraction of a fuller box, so the same idle tax costs
   less in per-measured-core terms.
2. **The effective-core comparison INVERTED**: LI +3.9% at 35 became
   **RR +1.9% at 500.** With each arm's own idle spin removed, RocketRide
   now does marginally MORE frames per effective core than LlamaIndex on
   this corpus. Within ±5% pass spread (see (c)) this is a statistical
   tie — but the direction flipped, and the honest reading is: **at
   scale, on the work itself, the two engines are at parity per effective
   core, with RR fractionally ahead.** The 35-film pairing (+26.7% / +3.9%)
   overstated both halves because RR was under-fed there.

The idle burden is unchanged and still the whole story of the measured-
core gap: 4.67 cores standing still, 15% of the box, reported beside
every RR figure and never subtracted.

## (c) Pass spreads are 5% — and they are a directional within-lifetime trend, not noise

RR 12.198 / 11.609 = **5.1%**; LI 12.249 / 12.953 = **5.7%** (vs 2.08% /
0.22% at 35). This needs an account before any headline fixes, and the
records give one: **the spread is directional and arm-specific, because
the two passes are consecutive within ONE container lifetime, not
independent replicates** (log: LI p1→p2 on the same 16 containers created
20:49; RR p1→p2 on the same rr created 05:04). Per-film wall medians:

| | pass 1 | pass 2 | direction |
|---|---|---|---|
| RR | median 381.9 s, sum 206,221 s | median 397.5 s, sum 217,577 s | **p2 SLOWER (+4%)** |
| LI | median 379.9 s, sum 206,098 s | median 354.7 s, sum 194,474 s | **p2 FASTER (−6%)** |

**RR degrades across its lifetime; LI warms up.** Nothing in the measured
environment differs to cause it — util is flat (96.9/97.1), cores flat
(31.01/31.08), preleg load low both (3.59/4.58). LI getting faster on
pass 2 is page-cache warmth (frames-on-disk reader re-reading a warm FS)
and JIT/allocator settling. **RR getting slower on pass 2 over a ~7.4-hour
leg is accumulated process state** — allocator arenas, fragmentation —
which is precisely §6's residual-candidate #3 (the engine's serving
context degrading over a long run) showing up in throughput, not just in
detection scores. The spread is real, it is not symmetric noise, and its
RR half points at the same open mechanism the detection divergence does.
**Consequence for the headline: quote pass means with the spread stated,
and do not fix a sub-5% cross-arm claim without n>2 — the within-lifetime
trend is the same size as the effect.**

## (d) $/1k footage-hour, per cell per pass (exports' own values)

| | pass 1 | pass 2 |
|---|---|---|
| LI N16×T2 | $7.79 | $7.36 |
| RR M16×T2 | $7.82 | $8.22 |

Means: LI $7.58, RR $8.02 — RR +5.8% $/1k, tracking the span throughput
gap (same basis $1.428/h ÷ x_realtime × 1000). Both an order below the
sizing report's default-cell $38–40 and near Leela's films500 SIZING
LG $9.24 / RR-default $40.79 (different corpus, not a join).

## Draft headline (NOT final — for the re-scoping ruling)

> At the ruled 16×2-vs-16×2 posture, C=16, on the full 498-measured-film
> Archive Films corpus (675.7 h footage, RF-DETR base), two passes:
> **LlamaIndex delivered +5.9% span throughput** (12.601 vs 11.904 f/s
> pass means, ±5% pass spread); **+15.2% per measured core** (idle
> included — the cost a user pays); and **−1.9% per effective core** —
> i.e. **RocketRide is fractionally ahead on the work itself once each
> arm's idle spin leaves its own denominator**, a statistical tie at this
> spread. RocketRide saturates the box (97% util) and spends 4.67 cores
> (15%) idle holding 16 tokens; that idle burden is the entire
> measured-core gap.

Figures behind each clause: posture/C/corpus/N/footage from the run
manifest + landed 500 manifest (498 measured, 675.73 h); +5.9% from pass
means 12.601/11.904; +15.2% and −1.9% from (b); 97% util and 4.67 idle
from the RR export; ±5% from (c). Every clause is scoped to THIS run's
one configuration, as the 35-film headline was — and (c)'s spread caveat
rides the throughput clause because the effect and the noise are the same
size.
