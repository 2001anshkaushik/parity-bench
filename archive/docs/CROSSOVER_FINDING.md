# ⛔ ON HOLD — DO NOT SEND, DO NOT PRESENT

**This document's central framing was refuted on 2026-08-05.** It is retained only as a record of what was believed. Every number in it that depends on the burst/sustained distinction is withdrawn.

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


---

# Document Weight, Sustained Load, and Which Architecture Suits Which Workload

**For: Shashi, Leela, leadership** · Ansh · 2026-08-05
**Status: draft, not yet sent. All claims labelled. No advocacy — the curve, the mechanism, and
what it implies for workload selection.**

---

## Summary

Three things determine which architecture is faster on the WS-1 embedding pipeline, and only one
of them is the framework:

1. **Document weight (embedded tokens).** Cost is linear in tokens — not characters, not chunks.
   Under sustained load the HTTP service leads by 2.7× on 100-token documents, and the gap closes
   steadily to statistical parity by 6,400 tokens as model compute swamps everything else.
   [direction VERIFIED — replicated in 2 runs agreeing within 0.6–4.1 %; the narrowing at the heavy
   end is also the one result both harness variants agree on]
2. **Burst vs sustained load.** RocketRide's throughput **decays 31 % under sustained load**
   (86 → 59 req/s over ten consecutive bursts through one task). A benchmark that measures short
   bursts against a freshly-created task reports its *burst* capacity, which is ~1.5× its steady
   state. [VERIFIED — this reversed a result of ours]
3. **Pipeline topology is NOT a factor.** Collapsing the 4-node pipeline into 1 node changes
   throughput by 0.88–1.13× — indistinguishable from no change. The engine's fixed per-request
   cost is in the engine's request path, not the node hops. Response payload size does not matter
   either. [VERIFIED — one measurement asymmetry disclosed in §3 and retired in §4]

**mt10k has a median of 338 embedded tokens, which is at the light end of this curve.**

---

## 1. The curve

Both services, CPU-pinned, matched concurrency (8 in flight), interleaved and randomised within a
session, warmup discarded, n=5. Raw data: `results/token_sweep_persistent.json` (sweep run) and
`results/topology_persistent.json` (topology run).

**Sustained load (one long-lived task/service on both sides — the production-relevant mode).** Two
independent runs on different days cover this range; they overlap at 400/800/1,600 tokens and are
shown side by side as a replication check.

| tokens/doc | RocketRide | LlamaIndex | ratio (sweep run) | ratio (topology run) | agreement | gap |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 177.0/s | 493.7/s | — | **0.368** | — | LlamaIndex 2.7× |
| 200 | 153.3/s | 310.6/s | — | **0.521** | — | LlamaIndex 1.9× |
| 400 | 98.8/s | 141.7/s | **0.727** | 0.714 | **1.8 %** | LlamaIndex +38 % |
| 800 | 72.9/s | 89.3/s | **0.823** | 0.789 | **4.1 %** | LlamaIndex +22 % |
| 1,600 | 36.6/s | 40.8/s | **0.905** | 0.911 | **0.6 %** | LlamaIndex +11 % |
| 3,200 | 18.4/s | 21.5/s | **0.891** | — | — | LlamaIndex +12 % |
| 6,400 | 7.3/s | 8.6/s | **0.946** | — | — | **CI spans 1.0 — no demonstrated difference** |

*Throughput columns are the sweep run for 400–6,400 tokens and the topology run for 100–200
(the sweep did not cover those levels). Ratios are each run's own.*

**The curve rises monotonically toward parity across a 64× span** — 0.368 → 0.521 → 0.72 → 0.81 →
0.91 → 0.89 → 0.95 — with one small dip at 3,200. At 6,400 tokens the 95 % CI is [0.828, 1.119],
statistically indistinguishable.

**The two runs agree to within 0.6–4.1 % wherever they overlap.** They are separate sessions with
separate randomisation and a separately-built RocketRide arm, so this is a genuine replication of
the sustained direction — though both use the same harness design, so it is a replication rather
than a second independent *method*.

**Narrowing at the heavy end is the most robust thing in the study** — it is the one result that
holds in *both* harness variants, which disagree on direction (§2). The two curves have different
shapes, so stated precisely:

| tokens | 400 | 800 | 1,600 | 3,200 | 6,400 |
| --- | ---: | ---: | ---: | ---: | ---: |
| burst mode (ratio RR/LI) | 1.482 | 1.488 | **1.658** | 1.515 | **1.322** |
| sustained mode (ratio RR/LI) | **0.727** | 0.823 | 0.905 | 0.891 | **0.946** |

The sustained curve rises toward 1.0 nearly monotonically. The burst curve **rises first, peaking
at 1.658 at 1,600 tokens, then falls** to its closest-to-parity value at 6,400. So the claim both
harnesses support is about the heavy end:

> **Above ~1,600 tokens both harnesses move toward parity, and both reach their closest-to-parity
> value at 6,400 tokens.** Below that they disagree on direction, and only the sustained curve
> (replicated twice, §1) covers 100–400 tokens.

**Why convergence is expected:** at 6,400 tokens both services spend almost all their time in the
same MiniLM forward pass on the same CPU. Architecture can only compete for the shrinking
remainder.

## 2. ⚠️ Burst vs sustained — this reversed one of our own results

We measured this comparison two ways and got **opposite directions**:

| harness | RocketRide task lifecycle | result at 400–6,400 tokens |
| --- | --- | --- |
| fresh task per repetition | new task, short measured window | RocketRide **1.32–1.66× faster** |
| one task, repeated bursts | persistent, sustained | LlamaIndex **1.06–1.38× faster** |

Rather than pick one, we tested the mechanism: ten consecutive bursts of 60 requests through a
single RocketRide task.

| burst | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| req/s | 86.6 | 83.5 | 85.9 | 67.3 | 61.1 | 59.1 | 60.3 | 56.6 | 59.0 | 59.7 |

**Throughput drops 31.3 % and then holds flat at ~59/s.** First three bursts median 85.9/s; last
three 59.0/s. [VERIFIED]

**Consequence: a benchmark that creates a fresh task per measurement reports RocketRide's burst
capacity, roughly 1.5× its steady state.** For a service that runs continuously, the sustained
number is the honest one, and that is what §1 reports.

**Cause of the decay: UNVERIFIED.** Candidates not yet separated: queue/backlog accumulation in
the task, allocator growth in the node process, or thermal. **Separating experiment:** run a
30-minute soak with per-burst timing and RSS sampling — a flat-but-lower plateau with stable RSS
points to queueing; climbing RSS points to allocator growth; a slow downward drift points to
thermal. **~40 min, not run.** This matters for capacity planning and is the single most valuable
follow-up in this document.

## 3. Topology is not the explanation [VERIFIED — asymmetry disclosed, then retired]

The obvious hypothesis for RocketRide's fixed per-request cost was its 4-node pipeline
(`webhook → preprocessor_langchain → embedding_transformer → response_documents`) — three
inter-node hops per document. We built a single node doing split+embed and compared.

| tokens | 4-node | 1-node | LlamaIndex | **1-node / 4-node** | 1-node / LlamaIndex |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 177.0/s | 168.6/s | 493.7/s | **0.932** | 0.343 |
| 200 | 153.3/s | 172.9/s | 310.6/s | **1.125** | 0.586 |
| 400 | 95.0/s | 93.5/s | 140.9/s | **1.003** | 0.716 |
| 800 | 78.7/s | 71.6/s | 103.4/s | **0.941** | 0.742 |
| 1,600 | 40.7/s | 35.4/s | 50.1/s | **0.880** | 0.801 |

**Collapsing four nodes into one changes nothing measurable** (0.88–1.13, straddling 1.0, no
trend).

⚠️ **Disclosure: the 1-node arm also returns a smaller response.** The benchmark node emits a
159–163 byte summary (chunk count plus vector *dimensions*) instead of the full embedding payload
the 4-node pipeline and LlamaIndex both return (9.2 KB at 100 tokens, 24.6 KB at 1,600). So the
1-node arm does **strictly less work** on two axes at once — three fewer hops *and* no payload
serialisation.

That confound runs **in RocketRide's favour**, and the result is still no speedup. The inference
therefore survives, in a slightly different form:

> **Removing three node hops AND up to 24.6 KB of response serialisation produces no measurable
> throughput gain.** Both are strictly-less-work changes, so neither can be hiding a large cost.
> Their *combined* contribution is bounded at roughly ±13 %.

**The payload half of that confound is retired by independent data.** In §4 LlamaIndex carries a
response payload growing from 15.9 KB to 115.4 KB — up to 555× the RocketRide node's — with **no
systematic movement in the ratio**. Response serialisation is therefore not a measurable cost at
these rates, which leaves node hops as the isolated variable above and restores the plain reading:
**node count is not a throughput factor.**

**Strongest rival explanation [not separated]:** the 4-node pipeline may overlap splitting and
embedding across node processes, so the 1-node arm loses pipelining. This is bounded small —
splitting is a few percent of the work at every level tested (LlamaIndex does split+embed
end-to-end at 493/s on 100-token documents) — so it cannot conceal a large hop cost.
**Separating experiment:** make the benchmark node return the full payload and re-run two token
levels, ~15 min. Not run.

**Practical implication: restructuring a pipeline to use fewer nodes is not a throughput
optimisation.** Choose node count for clarity and fault isolation instead.

## 4. Chunk count is not the driver either [VERIFIED, with a caveat]

Two rival mechanisms for the ratio: per-request overhead amortisation, or per-chunk Python cost.
They predict opposite things when chunk count varies at fixed work.

| chunk_size | chunks emitted | RocketRide (1-node) | LlamaIndex | ratio | LI response bytes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8,000 | 1 | 106.9/s | 115.2/s | 0.932 | 15,947 |
| 3,600 | 3 | 24.0/s | 25.3/s | 0.824 | 32,542 |
| 1,500 | 6 | 22.2/s | 22.7/s | 1.024 | 57,470 |
| 760 | 13 | 22.7/s | 22.9/s | 0.995 | 115,449 |

**The ratio shows no systematic trend with chunk count** (0.824–1.024, no ordering). Per-chunk
Python cost is **refuted** as the driver; per-request overhead amortisation stands.

⚠️ **Caveat 1 — the design intent was violated and the absolute numbers are confounded.** The plan
was to hold total embedded tokens constant. It did not: MiniLM truncates at **512 tokens per
chunk**, so the 1-chunk cell embedded ~512 tokens while the 13-chunk cell embedded ~2,200. That is
why absolute throughput collapses from 107/s to ~23/s between rows. **The ratio comparison remains
valid** — both services truncate identically at each setting — but the absolute column should not
be read as a chunking cost curve.

**Caveat 2 — and it happens to answer §3's open question.** The RocketRide arm here is the same
summary-emitting benchmark node, returning 159–208 bytes against LlamaIndex's full 15.9–115.4 KB
payload — a handicap on LlamaIndex that grows from **100× to 555×** across the sweep.

If response serialisation were a meaningful cost, the ratio would climb steadily as LlamaIndex's
payload grew 7× in absolute bytes. **It does not move.** That independently bounds response-payload
cost near zero at these rates (115 KB × 22.9/s ≈ 2.6 MB/s over loopback), which is what retires the
confound flagged in §3 and leaves node hops as the isolated variable there.

## 5. Where mt10k sits

| | value |
| --- | ---: |
| documents | 10,000 (verified: 10,000/10,000 sha256 vs Leela's manifest) |
| median size | 1,186 bytes |
| median chunks | 1 (93.2 % single-chunk) |
| **median embedded tokens** | **338** |
| p75 / p99 | 512 / 2,143 tokens |

**mt10k sits at the light end of the curve, where the architectural gap is widest.** It is
therefore **near worst-case for RocketRide** among the workloads we measured — the corpus offers
the least opportunity for the engine's fixed per-request cost to amortise.

Where exactly the median document lands depends on which load mode you measure:

| mode | position of a 338-token document | implication |
| --- | --- | --- |
| **sustained** | between the 200 (0.521) and 400 (0.714) rows → ratio ≈ **0.66** | LlamaIndex roughly 1.5× ahead |
| **burst** | directly on the 200–400 token crossover | the two are near even; small changes in corpus shape flip the winner |

**This is why our own mt10k parity numbers have been unstable**, and why two earlier results on
this corpus pointed in opposite directions before we understood the mechanism. A corpus sitting on
a crossover is the worst place to take a headline number from.

That is a statement about the corpus, not a criticism of either system. A parity number taken on
mt10k should not be generalised to heavier workloads, in either direction — and if WS-1 needs a
single defensible number, it should be taken at a token level well away from the seam, with the
corpus median reported alongside it.

## 6. The practical rule

| workload shape | tokens/doc | what the measurements show |
| --- | --- | --- |
| short records, chat turns, log lines, titles | < 200 | HTTP service ahead by a wide margin (2.7× at 100 tokens, 1.9× at 200) |
| short prose: newsgroup posts, tickets, emails — **mt10k lives here (median 338)** | 200–400 | HTTP service ~1.4–1.9× ahead |
| typical documents | 400–1,600 | HTTP service ahead by 11–38 % |
| long-form: reports, transcripts, papers, books | > 3,200 | **converging to parity**; at 6,400 tokens statistically indistinguishable |
| any shape, sustained | — | expect ~31 % less from RocketRide than a burst benchmark suggests |

**For leadership's long-form target specifically:** the gap closes as documents get heavier, and
at 6,400 tokens we cannot distinguish the two on throughput. Selection at that end should turn on
the other axes — fault isolation, memory, operational complexity, blast radius — not throughput,
because throughput is where they stop differing.

## 7. Confidence and what would change this

| claim | label | basis |
| --- | --- | --- |
| Cost is linear in tokens, not chars or chunks | VERIFIED | 2 harnesses + the chunk sweep |
| Gap narrows toward parity at the heavy end | VERIFIED | holds in both harness variants despite their disagreeing on direction |
| RocketRide decays ~31 % under sustained load | VERIFIED | direct 10-burst measurement; explains the harness disagreement |
| Topology (node count) is not a throughput factor | VERIFIED | 0.88–1.13 across 5 token levels; payload confound retired by §4 |
| Chunk count does not drive the ratio | VERIFIED | no trend across 1–13 chunks |
| Response payload size is not a measurable cost | VERIFIED | ratio flat while LlamaIndex's payload grew 100×→555× |
| **Sustained-mode direction (LlamaIndex ahead at 100–6,400)** | **VERIFIED (direction)** | replicated in 2 independent runs agreeing within 0.6–4.1 % |
| Sustained-mode *point estimates* at any single token level | **PROVISIONAL** | RocketRide arm fails the 10 % variance gate in most cells — see below |
| Cause of the sustained decay | UNVERIFIED | ~40 min soak test would settle it |

### Why the point estimates are PROVISIONAL even though the direction is VERIFIED

**The RocketRide arm failed our 10 % variance gate in most cells** (spreads 9.8–28.4 %), while the
LlamaIndex arm mostly passed (3.9–22.7 %, usually < 10 %). The engine is systematically harder to
measure with this harness than the service is. That asymmetry means our RocketRide numbers carry
more uncertainty than our LlamaIndex numbers — a bias to disclose rather than average away.

Inspecting the raw repetitions shows why: the RocketRide rates are tight with **one fast outlier**
(e.g. at 400 tokens: 100.8, 98.8, 95.7, 95.9, **122.4**). The spread is driven by occasional fast
runs, not by instability in the slow direction — which is consistent with the burst-decay mechanism
in §2 and means the median is unlikely to be understating RocketRide.

So: the **direction** is replicated twice and survives; any **single ratio** should be quoted with
its CI, not to three decimals. Shashi reproducing this independently remains the right next step.

### Hostile-reviewer questions, answered

> *"You reported RocketRide faster earlier today and slower now. Which is it?"*

Both were correct measurements of different things. The earlier harness created a fresh task per
repetition and measured burst capacity; this one measures sustained throughput. The 31 % decay is
directly measured and reconciles them. For a continuously-running service, sustained is the
relevant number.

> *"You own the LlamaIndex service and it wins. Why should we believe you?"*

The variance-gate failures are on the RocketRide arm, which is exactly why every point estimate
here is labelled PROVISIONAL and why the whole thing is packaged for Shashi to reproduce
independently (`handoff/parity/`). We also withdrew an earlier finding of ours that favoured
LlamaIndex 1.73× once we found the test document was unrepresentative, and we reversed our own
burst-mode result in §2 when the sustained test contradicted it. The corrections have run in both
directions.

> *"Isn't this a narrow range?"*

The sustained curve spans 100–6,400 tokens — a 64× range covering everything from a log line to a
long report. Above 6,400 the two are already statistically indistinguishable, so extending further
is unlikely to change the conclusion; below 100 tokens the workload stops resembling document
processing.

> *"Your single-node benchmark arm returns 159 bytes while the others return 9–115 KB. Isn't that
> rigged?"*

It is an asymmetry, it is disclosed in §3 and §4, and it runs **in RocketRide's favour** — the
stripped arm does strictly less work. It did not win anyway. Separately, §4 shows LlamaIndex
absorbing a payload growing to 115 KB with no ratio movement, which bounds the effect near zero.
The 4-node vs LlamaIndex comparisons in §1 and §2 — the ones the conclusions rest on — use
symmetric full payloads (9,367 vs 9,391 bytes measured previously, 0.997×).

## 8. What we did not do

| skipped | cost | why |
| --- | ---: | --- |
| 30-min soak to explain the sustained decay | ~40 min | most valuable follow-up; does not change the curve |
| Re-run the 1-node arm returning the full payload | ~15 min | would isolate node hops cleanly; §4 already bounds the confound near zero |
| Re-run sustained sweep until every RocketRide cell passes the gate | ~45 min | would firm the point estimates; direction already consistent |
| Sustained levels below 100 tokens | ~25 min | below 100 the workload stops resembling document processing |
| LangChain/LangGraph third arm | — | not built; Shashi/Leela own it |
