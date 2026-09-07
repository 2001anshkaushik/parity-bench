# Films-500 — results, read from the landed artifacts (2026-09-06)

Campaign `films500_mainrun_20260904T204852Z`, landed at box commit
`cc98ca6b`, bundle sha `1882c0d4…`, ff-merged to `origin/video-bench`.
Six legs, 498 measured films each, 0 errors, every per-leg gate PASS or
NOT RUN. **Lifetimes run** `films500_lifetimes_20260906T090339Z` (four
legs, landed 2026-09-07 at box commit 405d3c6, bundle `dbe874bb…`) and
**V-D** (`wrapper-resize-parity-20260907`, box commit 844a990) landed
the same way. **NOT the sizing report** — the 35-film DEFINITIVE stays
as written; re-scoping is Ansh's separate ruling. Every figure below is
re-read from the landed exports/records, not the run log.

*Manifest provenance, recorded (2026-09-07).* Every export from both runs
carries `manifest_sha256 = c5a09a34…` while the committed
`films500_video_manifest.jsonl` hashes `075fc35b…`: the box's working
copy differs from the committed file by its `_meta` line only (`git diff`
on the box: 1 line; the corpus locator's `--stamp-corpus-dir` writes
`_meta.corpus_dir` there, `corpus_locator.py:19-35`). The measured rows
the runs used are byte-identical to the committed ones: every record's
`expected_frames`, `video_s_manifest`, `bytes` and `submitted_sha256`
match the committed manifest row for its film, 498/498 on all eight
blast legs. The driver hashes the file, not the rows; a canonical row
hash (or committing the stamped file) is a follow-up, not a change now.

## Partition (the finding surface) — HELD exactly

`partition_check.json`, both parity cross files, verbatim:
`partition_holds: true`, `above_diverging=433`, `below_clean=65`,
`ABOVE_560_PASSING=[]`, `BELOW_560_FAILING=[]`, `missing_dimensions=[]`,
`partition_rc=0`. Both cross files: `PASS=False, n_videos=498,
failing=433`. **Ruling U predicted 433 of 498 before the run; the run
produced exactly 433, no exceptions across 498 films, both passes.**
The 87% edge fraction measured at manifest build (435/500, 433 measured)
reproduced as the failing count to the film.

## Throughput — LIFETIME-CONTROLLED (landed 2026-09-07; n=2 fresh lifetimes per arm) — pending Ansh's FINAL ruling on the headline

The lifetimes run (`results/films500_lifetimes_20260906T090339Z`, box
commit 405d3c6, bundle `dbe874bb…`, ff-merged; two FRESH container
lifetimes, RR first then LI, two passes each, 498 films, 0 errors, every
gate PASS or NOT RUN) replaces the campaign's one-lifetime pair as the
throughput basis. Every figure below is the landed export's own field.

| leg | span f/s | window f/s (n=482) | cores | util | idle cores | CPU-s/frame | $/1k fh | container age at driver start |
|---|---|---|---|---|---|---|---|---|
| RR p3 (fresh) | **11.665** | 11.677 | 31.171 | 97.4% | 4.653 | 2.672 | 8.18 | 6 s |
| RR p4 | **11.560** | 11.620 | 31.038 | 97.0% | 4.640 | 2.685 | 8.25 | 16,530 s |
| LI p3 (fresh) | **12.791** | 12.772 | 29.044 | 90.8% | 0.063 | 2.271 | 7.46 | 24 s |
| LI p4 | **12.809** | 12.794 | 28.994 | 90.6% | 0.062 | 2.264 | 7.45 | 13,563 s |
| campaign RR p1 / p2 (one lifetime) | 12.198 / 11.609 | 12.254 / 11.613 | 31.013 / 31.084 | 96.9 / 97.1% | 4.689 / 4.656 | 2.543 / 2.678 | 7.82 / 8.22 | — |
| campaign LI p1 / p2 (one lifetime) | 12.249 / 12.953 | 12.212 / 12.957 | 28.604 / 28.450 | 89.4 / 88.9% | 0.071 / 0.067 | 2.335 / 2.196 | 7.79 / 7.36 | — |
| sequential (campaign, n=5) | LI 1.834 · RR 2.081 | — | 1.88 · 6.95 | 5.9 / 21.7% | — | — | — | — |

**Pass spreads collapsed to AMI class: RR 0.91%, LI 0.14%** (campaign:
5.1% / 5.7%). The campaign's 5% spreads were a property of THAT run, not
of either framework.

**Headline arithmetic (p3+p4 means; effective cores = measured cores
minus each arm's own idle burden, RR 4.647, LI 0.063):**

| basis | LI | RR | LI vs RR | campaign (p1+p2) | settled set (p2+p3+p4) |
|---|---|---|---|---|---|
| span f/s | **12.800** | **11.613** | **LI +10.2%** | +5.9% | +10.7% |
| f/s per MEASURED core | 0.4411 | 0.3733 | **LI +18.1%** | +15.2% | +19.4% |
| f/s per EFFECTIVE core | 0.4420 | 0.4389 | **LI +0.7%** (tie) | RR +1.9% | LI +1.8% |
| CPU-s per frame (engine cgroup) | 2.268 | 2.679 | RR +18.1% | RR +8.9%… (p1-skewed) | — |
| $/1k footage-hour | 7.46 / 7.45 | 8.18 / 8.25 | RR +10.3% | RR +5.8% | — |

Per-pass effective-core pairs (LI vs RR): p1 0.4293 vs 0.4634 (RR
+7.9%), p2 0.4564 vs 0.4393 (LI +3.9%), p3 0.4414 vs 0.4399 (LI +0.3%),
p4 0.4427 vs 0.4379 (LI +1.1%). **The effective-core inversion at 500
(RR +1.9%) was entirely the campaign's pass-1 pair**; on fresh lifetimes
it is a tie with LI marginally ahead in both pairings. The number a
product reader will use moved by 2.6 points toward LI and lands at
parity. Per measured core — the cost a user pays — LI +18%: the idle
burden (4.65 cores, 14.5% of the box, holding 16 tokens) is, as before,
the whole of that gap. cross_fail=1 was expected and is unchanged.

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

## THE LIFETIMES RUN'S PRE-REGISTERED READING (landed 2026-09-07) — the transient-plateau account is WITHDRAWN

`probe/lifetimes_reading.py --lifetimes results/films500_lifetimes_20260906T090339Z`
(null control reproduced the campaign p1/p2 figures first; frames basis,
enqueue order = manifest order in all four legs):

| leg | Q1 · Q2 · Q3 · Q4 (s/foot-min) | first 20% → last 20% | level |
|---|---|---|---|
| RR p3 (fresh) | 5.372 · 5.287 · 5.405 · 5.356 | 5.501 → 5.374 = **−2.3%** | 5.354 |
| RR p4 | 5.401 · 5.297 · 5.444 · 5.351 | 5.506 → 5.362 = −2.6% | 5.372 |
| LI p3 (fresh) | 4.875 · 4.888 · 4.827 · 4.913 | 5.025 → 4.869 = **−3.1%** | 4.876 |
| LI p4 | 4.875 · 4.883 · 4.789 · 4.902 | 5.007 → 4.863 = −2.9% | 4.862 |

Verdicts, by the bands written before the run: **RR p3 REFUTES**
(reversed sign: −2.3% against the pre-registered +1..+6%); **LI p3 does
not confirm** (−3.1%, outside −6..−13%); both p4s reproduce their p3's
own within-pass profile at the same level (|Δdrift| < 1%, level within
0.1%) — a **repeatable pass-start shape**, not lifetime drift: the first
20% of every pass runs ~2.5–3% slower than the last 20% on both arms,
fresh container or aged (the sixteen cold starts; the campaign's `read_s`
Q1 effect), and nothing rises after it. **Plateau level: p4 vs campaign
p2 = RR −0.04% (paired SE 0.57%), LI +1.32% (SE 0.77%) — SAME LEVEL on
both arms.** So the campaign's pass 2 and both lifetimes passes are one
steady state — RR 5.35–5.38 s/foot-min (11.56–11.67 f/s), LI 4.80–4.88
(12.79–12.95 f/s) — and **the campaign's pass-1 pair is the anomaly**
(RR p1 5.09, +5% fast; LI p1 5.09, −5% slow and improving through the
pass). The transient-plateau reading below is withdrawn: pass 1 was not
a transient settling into pass 2's level; pass 2 was the norm and pass 1
was off it.

**The mechanism read is VOID, its premise having failed.** By its rule
(RR p3 opening quartile 5.372 ≥ 5.20) it fires "filesystem side" — but
the rule took the campaign's pass-1 opening quartile (5.03) as the normal
fresh start, and that is the quantity the run showed to be anomalous:
the fresh container opened at the steady level. The three mechanisms
have nothing to carry. Filesystem: the ext4 free-space proxy is flat
across the whole run (avg free extent 43,608 → 43,082 KiB, ≥4 MiB share
0.9936 → 0.9933, free fragments 14,510 → 14,684 after ~1 TB of spool
churn; docker-root free 603.5 → 603.3 GiB; `lifetime_state_prerun/
postrun.json`). Process memory: the per-token climb reproduced in every
pass — RR RSS 26.7 → 52.5 GiB (p3) and 26.5 → 49.2 (p4), cgroup anon
19.2 → 44.8 and 19.0 → 41.6, the token processes at 3.4–3.6 GiB each at
leg end, the server small — with flat cost; **that growth is a confirmed
finding at n=4 and is not the carrier of anything**. Page cache: the next
section. Spool: rr `/tmp` at leg end held 18 files / 76 KiB (16 webhooks
+ 2 locks, zero `media_*`) both passes — no leak; LI 3 files / 32 KiB per
instance; the fs stream's spool high-water was 12.0 GiB (RR) / 13.9 GiB
(LI) above the leg-start level. One recorded absence: `/proc/diskstats`
(the `/dev/root` name), so churn volume is not captured.

**Page cache (TASK 4, from the sampler started beside the run).**
`probe/cachewatch_join.py`: 938 rows parsed (1 unrecognised line — the
`nohup` banner), 2026-09-06 11:11:54Z → 09-07 02:49:05Z, iowait read as
the cumulative `/proc/stat` counter and differenced to percent-of-box.
Coverage: RR p3 from 62% in (147 rows), RR p4 / LI p3 / LI p4 fully (233
/ 211 / 211). iowait quartiles: RR p3 – / 0.07 / 0.06 / 0.08 %; RR p4
0.22 / 0.08 / 0.04 / 0.11; LI p3 1.39 / 0.52 / 0.57 / 0.63; LI p4 1.36 /
0.50 / 0.55 / 0.69 — never above ~1.4% of the box (the LI leg-start
sixteen-way cold burst), flat after it. Cached: 30 → 18.7 GiB through
each RR pass (the anon climb squeezing host cache, as in the campaign),
38 → 44 GiB through LI; Dirty 300–370 MiB (RR), 100–260 (LI). ρ(cost,
iowait) −0.12 / −0.11 / −0.08 / −0.03; ρ(cost, position) −0.13 / −0.09 /
−0.02 / −0.02: nothing moved and nothing correlated. **Page cache is
exonerated for this run.** The sampler cannot speak to the campaign's
legs (it started 22 h after they ended).

**The remaining outlier — the campaign's RR pass 1 (12.198 f/s).** No
fresh-lifetime RR pass reaches it (11.665, 11.560); it is now the only
RR pass off the steady state. From held records: every provenance scalar
is identical across the four RR passes (image `b7f51acc`, thread env 2
read back, task census 16 → 16, host networking, driver CPU share 0.2%);
pre-leg load1 3.59 / 4.58 / 0.52 / 5.8 shows no pattern; container age
is the same at p1 and p3 (fresh). Two held facts place the anomaly
outside the pass: **(i) it predates the pass** — RR p1's sixteen
warm-up sends ran at a median 152 s against 159 / 164 / 163 s for p2 /
p3 / p4 (−5 to −7%), before any pass-1 state could exist; **(ii) it is
CPU speed, not scheduling** — the pass did the same work in 5% fewer
engine-cgroup CPU-seconds (2.543 vs 2.672–2.685 CPU-s/frame at the same
97% util). LI's campaign pass 1 is the mirror image: warm-up sends at a
median 834 s against 757 / 791 / 782 s (+6–10% slow) and a within-pass
improvement. Both campaign pass-1 windows were anomalous from their
first warm send, in opposite directions: an environmental effect on the
box (CPU frequency / turbo headroom or host contention — HYPOTHESIS;
nothing in our exports measures it, and the sampler did not exist then).
**Unexplained beyond that; not smoothed; not reproduced on n=2 fresh
lifetimes per arm.**

## WITHIN-LIFETIME DRIFT — the campaign's reading (2026-09-06), WITHDRAWN by the lifetimes run (see above; kept as the record of what was pre-registered)

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

**Third mechanism — PAGE CACHE — pre-registered 2026-09-06 with pass 3 in
flight (the commit time is the timestamp; no pass-3 record had been read).**
Source: Shashi's films50 run (relayed; his doc is not held): his RR
rep1→rep2 fell 187.8× → 159.7× with byte-identical output, probed live at
11% iowait, six processes blocked on I/O, ~80% of his corpus resident, a
gp3 root volume at its 125 MB/s ceiling; his mitigation is prewarm plus
`cache_resident_gb_before/after` per cell. What our design already fixes
and what the exports already record:
- **Every leg starts corpus-COLD by construction, with proof**:
  `posix_fadvise(DONTNEED)` over every corpus file and a read-back that
  refuses if a sampled file still reads hot (`driver_video.py:2299-2310`,
  `probe/drop_cache_fadvise.py`; in every leg since 2026-08-20, before
  the AMI runs). A fresh container does not reset the host cache — our leg
  start does, for the corpus.
- The 263 GB corpus can never be resident in 61 GiB; each film is read
  from disk once per pass by the driver's sha pass, recorded per film as
  **`read_s`** (outside `wall_s`, inside the leg span). `read_s` per
  footage-minute is **flat by position in all four campaign legs** (Q2–Q4
  0.052–0.076 s/foot-min; Q1 ≈0.14 = sixteen cold starts at once) while
  RR p1's cost rose: the corpus-side reads do not carry the drift.
- The container's own page cache is in every collector stream
  (`cg_current − cg_anon`): RR 7.15 → 5.98 GiB across p1 and 7.38 → 6.39
  across p2 — squeezed by anon growth under the 58 GiB limit while ~8.9
  GiB of spools are in flight, so some spool pages are evicted and
  re-read during decode; host `mem_available` 34 → 15 GiB in both passes,
  never under global pressure. **iowait, Dirty and Writeback are recorded
  nowhere in our exports** — Ansh's once-a-minute `/proc/meminfo` sampler
  supplies them; `probe/cachewatch_join.py` joins it (clock anchor = each
  leg's `fsstream` row 0 `utc − t`, the leg start within ~1 s; leg end =
  anchor + `leg_wall_s`; per-film windows from the monotonic stamps;
  collector rows from the `.ready` mtime).
- **Distinguishing prediction.** Page cache ⇒ within RR p3 the per-film
  cost tracks iowait and the Cached/Dirty churn in time (cost correlates
  with iowait, ρ ≥ 0.3, and iowait itself moves through the leg,
  ρ(iowait, position) ≥ 0.3 — where both co-trend with position the
  detrended residual correlation splits them; iowait moves only in the
  rising legs), the cgroup file cache shrinks as it
  did, and p4 shows the same — the campaign's flat p2 under an identical
  cache squeeze already argues against it as the carrier. Process /
  filesystem ⇒ cost rises with position while iowait and Cached are flat.
  The p3 opening-quartile read does NOT separate page cache from process
  state (both reset at leg start by design); the cachewatch join and the
  cgroup file-cache trajectory do. Prewarm is not adopted: warm-start
  (his) and cold-start-with-proof (ours) are different bases, stated
  wherever the two are put side by side.
- **Result (landed 2026-09-07)**: the prediction had nothing to act on —
  cost flat, iowait flat and ≤1.4% of the box, no correlation (the
  lifetimes reading section carries the join figures). Exonerated for
  this run; silent on the campaign's legs.

## (c) Pass spreads are 5% — and they are a directional within-lifetime trend, not noise — WITHDRAWN 2026-09-07 (the fresh lifetimes reproduced pass 2, not pass 1; spreads 0.91% / 0.14%; the campaign's pass-1 windows were environmental outliers — see the lifetimes reading above)

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

## Headline — lifetime-controlled (landed 2026-09-07; pending Ansh's FINAL ruling; the partition clause is final)

> At the ruled 16×2-vs-16×2 posture, C=16, on the full 498-measured-film
> Archive Films corpus (675.7 h footage, RF-DETR base), on two FRESH
> container lifetimes per arm with two passes each (spreads 0.9% RR,
> 0.1% LI): **LlamaIndex delivered +10.2% span throughput** (12.800 vs
> 11.613 f/s); **+18.1% per measured core** (idle included — the cost a
> user pays); and **+0.7% per effective core** — a statistical tie on the
> work itself once each arm's idle spin leaves its own denominator.
> RocketRide saturates the box (97% util) and spends 4.65 cores (14.5%)
> idle holding 16 tokens; that idle burden is the whole of the
> measured-core gap. RocketRide costs $8.22 per 1,000 footage-hours to
> LlamaIndex's $7.46 (+10%). Above 560px the arms differ in
> preprocessing only — the engine's own pre-downscale, confirmed by V-D —
> and the model does the same work per frame on both.

Figures behind each clause: posture/C/corpus/N/footage from the run
manifests and the landed 500 manifest (498 measured, 675.73 h); +10.2%,
+18.1%, +0.7% and $/1k from the lifetimes exports (table above); 97% util
and 4.65 idle from the RR exports; spreads from p3/p4. The campaign's
one-lifetime draft (+5.9% / +15.2% / −1.9%) is superseded: its pass-1
pair was an environmental outlier in both arms. Every clause is scoped
to THIS configuration, as the 35-film headline was.

## The 560px mechanism — located in the engine source (2026-09-06) and CONFIRMED by V-D (2026-09-07)

Shashi's determinism table (relayed via the operator, DATA; his document
is not held) reports both his arms deterministic at a fixed thread count
and every per-film digest changing across thread counts with totals
moving ≤3 — BLAS reduction order in the last bits, a handful crossing 0.3.
Assessed against everything we hold:

- **Within-arm reproducibility under 16-lane load is total.** The
  campaign's two passes per arm — same lifetime, same load, same order —
  are bit-identical film by film: labels, full-precision scores,
  detection counts and chunk shas, **498/498 RR and 498/498 LI, including
  all 433 films above 560px**. The proposed "same frame, same arm, twice
  under load" test is answered at 996 repeats: there is no run-to-run
  variance to find. The divergence is deterministic and between arms
  (433 both passes).
- **The thread-count effect exists and is four orders of magnitude too
  small.** Our own Ruling-Y artifacts show intraop 16 vs 2 moving the 7th
  decimal (0.953240275 vs 0.953240395, both sides identically); the
  campaign's frame-10 deltas are 10⁻²–10⁻¹ on the same objects (person
  0.953 → 0.946, chair 0.490 → 0.449, bottle 0.433 → 0.385, plus a chair
  at 0.318 crossing the threshold). Percent-level shifts are what a
  different resampling of the input produces, not what reduction order
  produces.
- **The mechanism is in the engine's serving path, named from source.**
  The detect node builds the engine's `Detector` facade
  (`engine/nodes/detect/IGlobal.py:38-75`) and calls its `detect` on the
  PNG-decoded frame (`IInstance.py:103-107`; lossless load,
  `ai/common/image/image.py:13-27`). That facade downscales first:
  `ai/common/models/vision/detection.py:60` declares the rfdetr backend
  with `infer_edge=560`, `:466` stores it, and `Detector.detect`
  (`:512-518`) runs `resize_for_inference(image, 560)` —
  `dense_resize.py`: a strict no-op when the long edge is ≤ 560,
  otherwise `Image.LANCZOS` to `floor(w·s) × floor(h·s)`, `s = 560/max(w,h)`
  — and hands the downscaled image to the backend, mapping boxes back
  afterwards. The source comment calls the downscale "lossless (boxes
  mapped back)": lossless for coordinates, not for pixels or scores.
  LlamaIndex (`li_video/pipeline.py:215`) hands RF-DETR the raw frame,
  and RF-DETR applies its own resize. Two resampling pipelines above 560,
  one below.
- **It predicts every held fact.** Boundary exactly at 560 on the long
  edge, inclusive: the one corpus film at exactly 560 (JailBait, 560×380)
  is clean, 64 below are clean, 433 measured above diverge — the helper's
  `<=` reproduced to the pixel; the 624×480 films Ansh cites are
  downscaled to 560×430; the 381 films at 640×480 to 560×420.
  Deterministic (no variance). Context-dependent in exactly the sense
  measured: the Ruling-Y probe (`probe_detector_parity.py:36-75`) called
  `RFDETRBase().predict` on the raw frame — it replicated the backend's
  `detect` (`detection.py:172`, "passes the image untouched", the line
  its own header cites) and never entered the facade's `detect` that the
  node calls. Isolation was bit-equal to LI because it ran LI's path.
  Register entry 33.
- **Shashi's cross-arm caveat does not transfer.** His HS returns
  1.4–3.6% fewer detections with a hypothesised YUV→RGB matrix difference
  (BT.709 vs BT.601) and a height-based boundary (576/720). Our arms share
  one pinned ffmpeg binary (`e7e7fb30…`), frames on failing films are
  proven byte-identical (`probe_frame_parity` A==C EXACT), and our
  boundary is a 560px long-edge rule that puts 624×480 films on the
  diverging side — which the engine constant predicts and a colour matrix
  would not. Not adopted.
- **Confirmation, pre-registered (V-D), the cheapest possible, after the
  lifetimes run lands and on Ansh's ruling**:
  `probe/probe_wrapper_resize_parity.py` + `run_wrapper_resize_parity.sh`
  (refuses while the plan lock is held), inside the rr container at the
  campaign thread condition — frame 10 of HouseOnBareMountain (714×480,
  sha 83a02b92…) through `resize_for_inference(·, 560)` → 560×376 →
  `RFDETRBase().predict`. **CONFIRMS** if it reproduces the campaign RR
  output for that frame (labels {bottle×2, chair×3, person}, scores
  0.9464733 0.935210288 0.856113911 0.449365526 0.384643406 0.318114191 at
  9 dp) while the raw frame reproduces the campaign LI output (5
  detections, 0.953240395 …); the ≤560 control must be a no-op both ways;
  every predict run twice; a thread condition other than 2 or a raw frame
  that fails the LI baseline is CANNOT COMPARE, not a verdict. **REFUTES**
  if the resized frame does not reproduce RR. About three minutes of box
  time, one session, no engine change. If confirmed it replaces
  "accumulated serving-context state" with a named code path, and Ticket
  6's ask becomes concrete: make the facade's pre-downscale match the
  model's own preprocessing, or document the deviation. The 35-film
  DEFINITIVE §6 is FINAL and not edited here; its residual-candidate list
  gets a one-paragraph addendum only on Ansh's ruling after V-D.

**V-D RESULT (run 2026-09-07 03:23Z inside `rr:patched-video`, intraop 2,
weights md5 `b4d3ce46…` pinned to the Ruling-Y artifact; landed at
`results/wrapper-resize-parity-20260907/`, box commit 844a990):
CONFIRMED.** The frame through the engine's own
`resize_for_inference(·, 560)` — the engine helper imported by path
agrees with the port pixel-for-pixel, 714×480 → 560×376 — then
`RFDETRBase().predict` reproduces the campaign RR output **bit-equal at
9 dp**: person 0.946473300, chair 0.935210288, bottle 0.856113911, chair
0.449365526, bottle 0.384643406, chair 0.318114191 (six detections); the
raw frame reproduces the campaign LI output bit-equal (five detections,
0.953240395 …); the ≤560 control is a no-op both ways; every predict was
run twice and matched itself. The engine facade's LANCZOS pre-downscale
to `infer_edge=560` is the mechanism of the 560px partition, named in
source and reproduced outside the serving context.

## Workload above 560px — sized from source and held records (2026-09-06; TASK 1) and the facade's configurability (TASK 2)

**The premise to check first: does the facade's downscale reduce the
detector's work?** From the held RF-DETR 1.5.2 source (the Ruling-Y
probe captured `detr.py` from BOTH containers; `detr_li.py` and
`detr_engine.py` are byte-identical): `predict` converts each input with
`F.to_tensor` → `F.normalize` → **`F.resize(img_tensor, (self.model.
resolution, self.model.resolution))`** (`detr.py:379`) before inference —
every input, whatever its size, becomes a 560×560 tensor for RFDETRBase.
So the facade changes the pixels RF-DETR's own resize *starts from* (hence
the scores), not the tensor the model consumes. Model work per frame is
the same on both arms for every frame. What differs above 560 is
preprocessing only: RR does LANCZOS(source → 560 long edge) *and then*
RF-DETR's resize to 560²; LI does RF-DETR's resize from the source
directly. RR pays an extra pass — a few milliseconds of PIL LANCZOS per
frame against ~0.84 s of detection (estimate until V-D times it; it is a
cost on RR's side, not a saving).

**The quantity the premise points at, sized anyway.** Pixels handed to
`rfdetr.predict`: per film the facade's area ratio runs 0.154–0.978
(640×480 → 560×420 = 0.766, 381 films; 720×480 → 560×373 = 0.604;
624×480 → 560×430 = 0.804), frames-weighted mean **0.750**; over the
corpus RR hands RF-DETR 35.0 Gpx where LI hands 46.6 Gpx. That number is
the input to RF-DETR's fixed-output resize, not the model's input; the
model consumes 313,600 px per frame on both arms (50.8 Gpx over the
corpus each).

**Held measurements agree with the symmetric reading — the free
within-campaign test.**

| test (pass 2 unless stated) | result |
|---|---|
| LI `detect` stage, s per frame, by source resolution | 320×240 0.839 · 540×360 0.831 · **624×480 0.83 · 640×480 0.84 · 720×480 0.85** — flat across the edge (≤560 median 0.836, >560 0.839) |
| LI `extract` stage (ffmpeg decode + PNG to disk), s per frame | ≤560 0.132 · >560 0.249 — the stage that scales with source pixels |
| RR/LI per-film s-per-frame ratio, comparable resolutions across the edge | 540×360 (below) **1.106** · 640×480 (above) **1.114** · 720×480 (above) **1.113** — flat |
| RR/LI ratio by class | p2: ≤560 1.168 (n=65) vs >560 1.121 (n=433); p1: 1.014 vs 0.989 |
| where the class difference comes from | the 320×240 films (31 of the 65): RR/LI **1.214** — LI's extract stage is disproportionately cheap on tiny frames (LI 0.98 s/frame vs RR 1.19); RR's per-frame cost is less sensitive to source size (RR +7% from 320×240 to 640×480, LI +16%) |

The RR/LI ratio does drop across the edge at the class level (−4% in
pass 2), but the drop is carried entirely by the smallest-frame films
through LI's decode/PNG stage, not by the detector; at comparable
resolutions the ratio is flat, and LI's own detect stage — the only
per-stage detector timing held — does not move with source size at all,
which is what a fixed 560² model input predicts. Nothing in the held
records shows RR doing less detector work above the edge. Downstream, RR
does slightly *more*: its chunk count per film runs above LI's
(RecursiveCharacterTextSplitter vs SentenceSplitter; the cross files'
`chunk_count_ratio`), so its embedding stage embeds more chunks for the
same text. No per-frame RR detect timing is held: the engine's per-frame
debug line is off in the campaign images (both landed RR docker logs are
13 lines).

**What it does to the headline.** No correction toward RR is warranted.
The feared reading — RR ~6% behind on span while doing less work per
frame on 87% of the corpus — does not survive the source: the arms run
the same model work per frame; above 560 RR does marginally more
preprocessing and produces different scores. The +5.9% LI span figure
stands as measured; the report states the preprocessing difference and
its direction beside it. **Measured by V-D (2026-09-07)**: the model
consumed `[1, 3, 560, 560]` on BOTH paths (forward pre-hook on RF-DETR's
module at the eager call site) — pixels handed to `predict` 342,720 raw
vs 210,560 facade (×0.614), model input identical — **workload SYMMETRIC
at the model**; the facade's LANCZOS pass cost 4.64 ms (median of 5)
against ~0.84 s of detection per frame: RR's extra preprocessing above
560 is ~0.5% of per-frame cost, on RR's side.

**Configurability (TASK 2).** `infer_edge=560` is a **fixed constant**:
it lives in the module-level `BACKENDS` table (`detection.py:60`);
`Detector.__init__` (`:440-466`) takes `backend`, `model_name`,
`device`, `threshold`, `prompt`, `revision` and reads the edge from the
table with no parameter to override it — unlike the segmentation facade,
whose `max_edge` is a constructor argument ("client-side; not part of
identity", `segmentation.py:430-448`); the detect node's config surface
(`nodes/detect/services.json`) exposes `detect.threshold`,
`detect.prompt` and `detect.profile` only, and the node builds the
facade from exactly those (`IGlobal.py:49-75`). It is not reachable from
the pipe. The campaign pipe (`benchmark_video_detect.pipe`) wires only
detect's text lane onward, so the node's annotated-JPEG emit path never
runs (`IInstance.py:80`: image lane has no listener) — no second RR-side
per-frame cost hides there. Options, none taken here:
- **(A) LI applies the same LANCZOS pre-downscale before `predict`** — a
  six-line change on our own arm (`li_video/pipeline.py:211-215`,
  porting `resize_for_inference`). Like-for-like preprocessing; the
  prediction is that gate 3 then passes corpus-wide (a corpus-scale
  confirmation of the mechanism for free) and throughput moves within
  noise. Candidate for the next campaign, not this one.
- **(B) The engine drops or matches the facade's pre-downscale for
  backends that resize internally** — Ticket 6 criterion 4; the engine
  team's change, a new build, not comparable to the measured image.
- **(C) Scope this campaign's claims**: same model work per frame both
  arms (V-D measures it); different preprocessing above 560 on RR's side,
  small and against RR; detection-equality claims scoped to ≤560px;
  throughput claims stand with that sentence beside them.
  Recommendation: (C) for this report, (A) for the next campaign.

## Cross-team joins — cautions (2026-09-06, from Shashi's films50 figures as relayed)

- **His RR-vs-HS 1.58× carries a wave handicap he flags himself**: 50
  films over 32 workers = 1.56 waves, HS capped near 78% util, 10.8
  effective cores. His RR at 16 tokens runs 3.1 waves and is ramp/drain-
  depressed too, less so. Our 498 films over 16 lanes has no wave effect
  (span ≈ window, section (a)). Do not join his 1.58× to our +5.9%:
  different competitor arm, different N, wave-limited.
- **"2.6% apart on RR 16×2" is a throughput coincidence, not a
  steady-state agreement.** His 12.52 f/s is a wave-depressed span at N=50
  (our own 35→500 move was +24–25%, mostly ramp/drain) against our
  saturated 12.198 at N=498. On the wave-independent quantity — CPU-s per
  frame, cores ÷ f/s — his 2.198 versus our 2.543 is **+15.7%**, the same
  class as the AMI gap (+19.3% at 16×2, +20.1% at 8×4), on the assumption
  that his cores are the engine cgroup over the leg with the tokens live
  (idle burn included), as ours are and as Leela's METRICS.md:75 states
  for their harnesses. His engine reaches the same span rate at 86% util
  because it spends ~14% less CPU per frame; ours saturates at 97%. The
  cross-team CPU-per-frame question therefore replicates on a second
  corpus and a third harness — and where no corpus can be resident.
- **Warm-start versus cold-start bases.** His mitigation from films50
  onward is prewarm with `cache_resident_gb_before/after` recorded; our
  legs are cold by construction with proof. Neither is wrong; they are
  different bases, stated wherever the two are put side by side.
