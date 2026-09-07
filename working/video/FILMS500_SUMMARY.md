# Archive Films, all 500 — two-minute summary (2026-09-07)

**What we ran.** The same two deployed AI video pipelines as the 35-film
benchmark — RocketRide's engine and a LlamaIndex-based service running
the identical model stack — processed the full 498-film Archive Films
corpus (676 hours of footage, 162,000 sampled frames) on one 32-core
machine, both at the tuned configuration the 35-film campaign chose,
each run twice inside one container lifetime and then twice more inside
two freshly started containers. Every number below is read from the
committed run artifacts.

## What we found

**1. The two engines do the work at the same cost per core; the entire
visible gap is what RocketRide burns standing still.** Per effective
core — the cost of the work itself once each side's idle spin leaves its
own denominator — the two are a statistical tie (LlamaIndex +0.7%, with
run-to-run spreads of 0.9% and 0.1%). Per measured core, the cost a user
actually pays, LlamaIndex is **+18%** ahead, and that whole difference is
**4.65 cores — 14.5% of the machine — that RocketRide spends idle just
holding its 16 workers resident.** On plain throughput LlamaIndex is
+10.2% (12.80 vs 11.61 frames/s), which is the same fact in a third unit:
at one machine price, RocketRide costs $8.22 per thousand footage-hours
to LlamaIndex's $7.46. The idle burden is a property of the engine's
process model and is the number to fix; it is not a difference in how
efficiently either side does the work.

**2. The big-video disagreement is explained, reproduced, and it is the
engine's own doing.** On the 35 films the two systems agreed to the last
bit on video at or below 560 pixels and drifted apart above it, and no
one could say why. On all 498 films the split held exactly as predicted
before the run — 433 films above the edge diverge, 65 at or below agree,
no exceptions, and the one film at exactly 560 pixels agrees. The cause
is in the engine's source: before it hands a frame to the detector, the
engine's detection wrapper shrinks any frame wider than 560 pixels with
its own resampler, and only then does the detector apply its own resize;
the comparison arm hands the detector the raw frame. Two resampling
pipelines above 560 pixels, one below. A committed probe reproduced both
systems' recorded detections for a diverging frame **bit for bit** by
that step alone. The detector's real work is identical on both sides —
the model receives an identically sized 560×560 tensor either way — so
this changes scores, not speed (the engine's extra shrink costs 4.6 ms a
frame). It is filed upstream with the fix stated.

**3. Four plausible explanations died on measurement, which is why the
numbers above can be trusted.** That the drift was floating-point noise
under load — no: repeated passes of either system are bit-identical on
every film, and the measured thread-count effect is ten thousand times
smaller than the observed shifts. That the throughput gap was disk
caching — no: a minute-by-minute sampler beside the run showed I/O wait
under 1.5% and flat. That the systems drift over a long-lived container —
no: fresh containers ran at exactly the settled level from their first
films, and the drift seen in the first campaign was an environmental
anomaly on the machine that day, present in both systems' warm-up sends
before any measured work began, excluded from every mean and reported as
unexplained. That RocketRide was doing less work per frame on 87% of the
corpus because it shrinks frames first — no: the model's input is the
same size on both sides, measured.

## What it means for the product

The 35-film findings stand and sharpen. Out of the box the engine still
runs at a fraction of its own tuned speed (that number lives in the
35-film report). Tuned, the engine's only measured disadvantage is the
idle cost of its worker model — 4.65 cores at 16 workers before any work
arrives — and removing it would bring the engine to parity on every
throughput basis. Separately, the engine's pre-inference downscale means
two correct deployments of the same detector can disagree on borderline
objects in large video; that is now a named, reproducible behaviour with
a one-line fix path rather than an open mystery.

## Not settled

Why the machine ran ~5% faster for one system and slower for the other
during one four-hour window of the first campaign — we lack a CPU-
frequency or neighbour-load instrument, and the anomaly did not recur.
And the cross-team question stands: our RocketRide runs ~20% more CPU
per frame than two other teams measure at matched utilization, on
byte-identical data, now on two corpora; the handover package with its
specific ask is ready.

## Where the detail lives

`WS1_Phase2_Films500_Benchmark_DEFINITIVE.md` — the full report; every
figure traces to a committed artifact. `FILMS500_RESULTS.md` — the
working record, including the withdrawn readings kept as written.
`WS1_Phase2_Films_Benchmark_DEFINITIVE.md` — the 35-film sizing report,
with its §6 addendum. `AMI_CROSS_TEAM_COVER.md` — the cross-team CPU
question.
