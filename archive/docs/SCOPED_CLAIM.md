# The Parity Claim, Scoped

## The sentence

> **On the verified mt10k corpus (20newsgroups train, first 10,000 documents; median 1,186 bytes,
> median 1 chunk, median 338 embedded tokens), with both services on CPU running
> `multi-qa-MiniLM-L6-cos-v1` behind `RecursiveCharacterTextSplitter(4000, 200)`, driven by one
> multi-process client at 8 concurrent requests on a 14-core M4 Pro, RocketRide processed
> 1.13× more documents per second than the LlamaIndex FastAPI service (233.95/s vs 202.27/s,
> ratio CI95 1.064–1.183, n=5 interleaved and randomised, warmup discarded).**

Read it aloud. Every clause is load-bearing: change the corpus, the device, the concurrency, or
the host and the number changes — in one case it **inverts**.


> ## ⚠️ CORRECTION 2026-08-05 (session 6) — THE 31 % SUSTAINED DECAY IS WITHDRAWN
>
> **The decay does not reproduce.** Instrumented replication of the identical configuration
> (1 process, 1 connection, 1 task, no cooldown, same document) gives **6.0 %**. A symmetric
> n=3 test — both arms, continuous load, randomised order — gives median **+1.5 % (RocketRide)**
> and **+1.0 % (LlamaIndex)**, with individual sequences swinging in BOTH directions
> (+5.2, −8.7, +1.5 and +6.4, −12.0, +1.0) and a per-sequence spread of 14–18 pp.
> **Zero request failures in ~10,000 requests.** Engine-tree RSS flat; throughput recovers to
> 98 % of opening rate after a 60 s idle; a fresh task per burst measures the same as a
> persistent one (0.0 % vs 6.0 %).
>
> The original 31.3 % was a **single unreplicated draw (n=1)** from a statistic whose own noise
> band is ±12–18 pp, taken with **no control arm** — the LlamaIndex service was never subjected
> to the same treatment.
>
> **Consequences, all in force:**
> * "RocketRide decays 31 % under sustained load" — **WITHDRAWN**
> * the **burst-vs-sustained framing** — **WITHDRAWN**; there is no measured decay separating them
> * the **sustained token curve and its direction** — **INVALID as reported**. The two harnesses
>   disagreed for configuration reasons, not because one measured "steady state"
> * anything below that derives from either — **do not quote**
>
> Replacement measurements (concurrency axis) are in `CONCURRENCY_CHARACTERIZATION.md`.


> ### ⚠️ CORRECTION 2026-08-05 (session 5) — this crossover was measured in BURST mode
>
> The numbers below come from a harness that created a **fresh RocketRide task per repetition**,
> which measures the engine's **burst capacity**. Directly measured: RocketRide's throughput
> **decays 31.3 % under sustained load** (86.6 → 59.0 req/s over ten consecutive bursts through
> one task) [VERIFIED].
>
> Under **sustained** load with a persistent task on both sides, **LlamaIndex is faster at every
> token level from 400 to 6,400** (ratio 0.727 → 0.946), and the crossover does not appear within
> the tested range. The *convergence* toward parity as documents get heavier holds in BOTH modes
> and is the robust finding; the *direction* depends on burst vs sustained.
>
> For a continuously-running service the sustained numbers are the relevant ones. See
> `CROSSOVER_FINDING.md`.

## What it does NOT establish

1. **It does not say RocketRide is faster than LlamaIndex in general.** The two cross over at
   200–400 embedded tokens per document. Below that LlamaIndex is up to 1.8× faster; above it
   RocketRide is up to 1.5× faster. mt10k straddles the crossover, which is why the margin is
   only 13 %. A corpus of short documents would reverse this claim.
2. **It does not establish a precise ratio.** The RocketRide arm's spread was 14.8 %, failing our
   own 10 % variance gate. The *direction* is corroborated by two independent experiments; the
   **1.13 point estimate is PROVISIONAL**.
3. **It says nothing about any other axis.** Not fault isolation, not memory, not operational
   complexity, not blast radius. On peak memory under held allocations RocketRide was better; on
   dependency footprint LlamaIndex's stack is far heavier. Throughput is one axis of several.
4. **It does not generalise off this host.** Apple Silicon, CPU-pinned, loopback networking,
   14 cores. Nothing here transfers to Linux/NVIDIA, and the device finding that made this
   measurable at all is Apple-specific.
5. **It does not isolate framework from pipeline topology.** RocketRide runs a 4-node pipeline;
   the LlamaIndex service does split+embed in one process. The engine's fixed per-request cost —
   the thing that makes it lose on short documents — is substantially those node hops. Whether a
   single-node RocketRide pipeline would close that gap is **UNVERIFIED**.
6. **It is not independently replicated.** I measured someone else's service with my harness.
   Shashi owns the RocketRide service and has not reproduced this. Until he does, treat it as one
   team's measurement, not a team result.
7. **It does not cover multi-chunk-heavy corpora.** Only 6.79 % of mt10k is multi-chunk. A corpus
   with a heavier tail would shift toward RocketRide, based on the chunk sweep.

## If you only remember one thing

**The winner depends on document length, and the corpus sits on the crossover.** Any parity number
quoted without its token distribution is uninterpretable.
