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

## Throughput (banked, re-read) — **DRAFT: n=2, spread ≈ effect size, pending the lifetime-controlled passes (ruling 2026-09-06)**

> Every throughput clause below is held at DRAFT. The pass spreads (RR
> 5.1%, LI 5.7%) equal the +5.9% effect, and the pairs overlap (RR's
> faster pass 12.198 vs LI's slower pass 12.249). The partition section
> above is FINAL and untouched by this.

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

## WITHIN-LIFETIME DRIFT — a FINDING (from the landed records; n=1 lifetime per arm)

Per-film wall normalized to footage (s per footage-minute) against
position in the leg (admit order), both arms, both passes — the cheapest
measurement, free from records already held:

| leg | Q1 · Q2 · Q3 · Q4 | first 20% → last 20% | slope (s/foot-min per position) |
|---|---|---|---|
| RR pass 1 | 4.98 · 4.92 · 5.09 · **5.26** | 5.10 → 5.34 = **+4.8%** | +0.00073 |
| RR pass 2 | 5.30 · 5.33 · 5.37 · 5.33 | 5.38 → 5.40 = **+0.4% (flat)** | +0.00004 |
| LI pass 1 | 5.07 · 5.16 · 5.12 · **4.82** | 5.19 → 4.75 = **−8.5%** | −0.00072 |
| LI pass 2 | 4.66 · 4.74 · 4.85 · 4.80 | 4.79 → 4.77 = **−0.4% (flat)** | +0.00026 |

**Shape: a first-pass TRANSIENT that settles into a PLATEAU which pass 2
inherits flat.** RR's per-film cost rises through pass 1 (4.98 → 5.26)
and then holds at that worse level for all of pass 2 (5.30–5.37); LI's
falls through pass 1 (5.07 → 4.82, most of it in the last quarter) and
holds at the better level (4.66–4.85). Neither continues drifting in
pass 2. So the campaign's two passes are **not** two samples of one
state — pass 1 is the transient, pass 2 the settled state — and the
"5% spread" is the transient-to-plateau step, arm-specific in sign.
RR's degradation-to-plateau was first read as §6's residual candidate
#3 (accumulated process state in the engine's serving context); the
campaign's own collector streams narrow that reading — see "what the
collector streams add" below. LI's improvement is consistent with
cache warmth taking hours at 16-lane pace. **n=1 lifetime per arm; the
lifetime-controlled passes reproduce or refute it.**

**Design consequence, contested with this measurement — contest
ACCEPTED 2026-09-06**: a fresh-container-per-pass design would measure
four transients and never the plateau; the design that runs is two
passes per fresh lifetime, arms alternated, RR first
(`run_films500_lifetimes.sh`) — the alternation also balances
box-time-of-day across the two campaigns.

**Same films, same order — content excluded (Ansh's check, verified
from the records).** Both passes submit in the SAME manifest order:
enqueue order equals the manifest order in pass 1 AND pass 2, 498/498
positions identical, both arms (admit order differs only by C=16
admission jitter: 452/498 RR, 456/498 LI). If the slowdown were content
— heavier films later — both passes would show the same within-pass
shape. RR pass 1 rises and RR pass 2 is flat on the same films in the
same order. That is state, not content.

**Basis note.** The table above normalizes by manifest `video_s`; the
pre-registered reading tool (`probe/lifetimes_reading.py`) uses measured
frames (footage = frames × 15 s, which keeps `TheSheik.mp4`, whose
manifest `video_s` is 0.0). Same shape on the frames basis: RR p1 +3.6%
→ p2 −0.2% (levels 5.094 → 5.375, +5.5%); LI p1 −9.8% → p2 −1.8% (5.091
→ 4.804, −5.6%). Paired per-film log-ratio SE: 0.62% RR, 0.39% LI
(n=498) — whole-pass levels resolve to well under 1%.

**What the campaign's collector streams add (held data; service role,
0.5 s ticks).** RR's service tree climbs **27 → 54 GiB RSS (cgroup anon
20 → 47 GiB) across pass 1 — then resets to 27 GiB and climbs
identically across pass 2 (27 → 53; anon 20 → 46)**: the per-token
processes end with the ttl=0 tokens between passes, so the growth is per
pass, ~+27 GiB per 498 films (~54 MB per film across 16 tokens). LI is
flat at ~22 GiB throughout (anon 0.9 GiB). The cost plateau carried into
RR pass 2 does **not** track that memory: pass 2 climbs the same way
while its cost is flat. So per-token memory growth (allocator/arena/
retained state in the task processes) is **excluded as the carrier** of
the pass-1→pass-2 step. Whatever carries it persists across the token
reset — the engine SERVER process (a bounded structure filling, then
steady, is the textbook plateau shape), the container's filesystem view,
the host filesystem, or the clock. The memory growth is a finding in its
own right (at this rate a token reaches the 58 GiB cgroup limit in
roughly 1,100 films) and is pre-registered to reproduce in p3/p4.

**Two mechanisms, instrumented before the launch (TASK 1).** Ansh's
alternative to process state: both arms spool every video to the
container's `/tmp` and delete it (RR `engine/ai/common/avi/reader.py:425`
`/tmp/media_*`, removed in `Reader.__del__`; LI `li_video/service.py:164`
`/tmp/ws1v_spool_*`) — ~500 GB of write-and-delete churn per campaign on
the overlay writable layer, i.e. the host filesystem under the docker
root. Free-space scattering there is a monotone slowdown that PERSISTS
into the next pass and is indistinguishable from process state from
outside. The held data leans without deciding: LI improved under the same
churn, and RR pass 2 stayed flat under 250 GB more of it — a filesystem
mechanism has to saturate exactly at pass 1's end. **The lifetimes run
discriminates**: a FRESH container on the SAME dirty filesystem starts
slow if it is the filesystem, fast if it is process state. Every
lifetimes export records, at leg start and leg end
(`export.lifetime_state`, `working/video/lifetime_state.py`): the spool
path's df/du/file count inside each container (a non-zero count at leg
end is a spool leak), cgroup memory, every process's RSS/RssAnon/VmData
with the top processes named (server vs token processes separable), the
writable-layer size, host free space, the ext4 free-space fragmentation
proxy (`/proc/fs/ext4/<dev>/mb_groups`: free fragments, average free
extent, share of free space in ≥4 MiB extents; `e2freefrag` best-effort),
`/proc/diskstats` (leg delta = churn volume) and a 5 s statvfs stream
under the leg — spool high-water at the filesystem level. (The campaign
never collected a per-film spool figure; the nearest held instrument was
mem_watch's 5 s df in the sweep, not run in the campaign.)
**Pre-registered read**: RR p3's opening quartile against the campaign
p1's opening quartile (5.03 s/foot-min, frames basis): **≤ 5.13 =
process side; ≥ 5.20 (near the p2 plateau 5.375) = filesystem side**;
between = indeterminate at n=1; corroborated by the fragmentation proxy's
direction across legs and by LI p3's opening quartile vs LI p1's (5.14 —
a filesystem penalty adds on top of LI's cold start).

**The +11.6% plateau pair is HYPOTHESIS, not finding (ruling
2026-09-06).** The campaign's pass-2 pair — LI 12.953 vs RR 11.609 —
rests on n=1 lifetime per arm and is LARGER than the +5.9% it would
replace; a bigger claim on thinner evidence gets more suspicion, not
less. It is the thing the lifetimes run tests; it does not lead until
n=2 per side. The pass-1 transient pair (12.249 vs 12.198 = +0.4%) is the
overlap the ruling names: two transients crossing in opposite directions.

**Pre-registered, extended (TASK 2): is the plateau reproducible at
all?** p4's level against the campaign p2's level (paired per film,
log-ratio, frames basis; p2: RR 5.375, LI 4.804): **|Δ| ≤ 2% = same
level** — a reproducible steady state at n=2 lifetimes per arm, and the
plateau pair becomes quotable (still n=2); **|Δ| ≥ 3% = different
level** — the plateau is lifetime-specific, neither pass is a stable
production number, a finding in its own right that changes what this
campaign can claim (no steady-state headline; per-lifetime ranges
instead); 2–3% = not resolvable at one pair of lifetimes, no plateau
claim either way. Drift bands (frames basis): RR p3 first→last-20% in
+1..+6% and p4 flat (|Δ| ≤ 2.5%) at p3's end level; LI p3 in −6..−13%
and p4 flat; refutes = flat p3 (<1%), reversed sign, or p4 still
drifting in the same direction (continuous degradation — a different and
worse finding for RR). The reading is computed by
`probe/lifetimes_reading.py`, committed before the run; its null control
reproduces the campaign p1/p2 figures above.

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
pass 2 is consistent with cache warmth (its memory is flat at ~22 GiB
across both passes). RR getting slower was first read as accumulated
process state — allocator arenas, fragmentation, §6's residual candidate
#3 — but the campaign's collector streams show RR's per-token memory
RESETS between passes (27 → 54 GiB in each pass) while the cost plateau
carries over, so per-token process memory is excluded as the carrier
(drift section above); the open candidates are the engine server
process, the host filesystem's spool churn (Ansh's alternative,
instrumented for the lifetimes run) and the clock. The spread is real,
it is not symmetric noise, and its RR half is an open mechanism.
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

## Draft headline — HELD (n=2, spread ≈ effect size; pending the lifetime-controlled passes; the partition clause is final)

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
