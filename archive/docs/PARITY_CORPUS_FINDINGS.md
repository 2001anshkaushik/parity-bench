# STEP 2 — Corpus-Shape Gate: the 1.73× does NOT survive

## Verdict: **the earlier "LlamaIndex 1.73× faster" was an artifact of an unrepresentative test document and is WITHDRAWN.**

On the real mt10k distribution, **RocketRide is 1.13× faster** [CI95 1.064–1.183]. The two
services cross over at ~200–400 embedded tokens per document, and the real corpus sits directly on
that crossover (median 338 tokens).

Three independent methods agree on the mechanism. Raw data: `results/parity_corpus.json`,
`results/token_sensitivity.json`, `results/corpus_characterization.json`.

---

## 1. The corpus is verified, then characterized [VERIFIED]

Rebuilt `fetch_20newsgroups(subset="train", remove=(), shuffle=False)` and hashed every document
against Leela's `data/mt10k/manifest.jsonl`: **10,000 / 10,000 sha256 match.** Same corpus.

| | value |
| --- | ---: |
| document bytes | median 1,186 · p90 3,164 · p99 13,848 · max 75,154 |
| chunks per document (4000/200) | median **1** · mean 1.179 · p99 5 · max 22 |
| **single-chunk documents** | **93.21 %** |
| multi-chunk | 6.79 % |
| **embedded tokens per document** | min 44 · p25 216 · **median 338** · p75 512 · p99 2,143 |

**The single-chunk assumption in the original test was fine. The token count was not.**

## 2. Parity on the real distribution [VERIFIED — but see the gate caveat]

Documents drawn from the verified corpus in natural proportions. Same driver, same device (`cpu`,
asserted), both pinned to 8 in-flight, 20 warmup requests discarded, n=5, interleaved and
randomised in one session.

| service | median | spread | CI95 | p50 |
| --- | ---: | ---: | --- | ---: |
| **RocketRide** | **233.95/s** | 14.8 % ⚠️ | — | 31.2 ms |
| **LlamaIndex** | **202.27/s** | 8.1 % ✅ | — | 28.3 ms |

**Ratio RocketRide/LlamaIndex = 1.128 [CI95 1.064, 1.183]** — RocketRide faster by ~13 %, CI
excludes 1.0.

⚠️ **The RocketRide arm's spread is 14.8 %, which fails the 10 % variance gate.** By the protocol
that arm is an invalid measurement on its own. It is reported because two independent experiments
below reach the same conclusion by different routes — but the **1.128 point estimate is
PROVISIONAL**, and the direction (RocketRide ahead on this corpus) is what is VERIFIED.

Note the gate failure lands on the arm that **favours** RocketRide. Under rule 5 that gets more
scrutiny, not less, which is why it is not being reported as a clean number.

## 3. Chunk sweep — RocketRide ahead at every chunk count [VERIFIED]

Synthetic documents at exact chunk counts, same everything else, n=3 (2 measured after 1 warmup):

| chunks/doc | RocketRide | LlamaIndex | ratio RR/LI |
| ---: | ---: | ---: | ---: |
| 1 | 221.62/s | 179.59/s | 1.234 [1.136, 1.341] |
| 2 | 116.99/s | 75.49/s | 1.550 [1.532, 1.567] |
| 5 | 46.45/s | 30.47/s | 1.524 [1.474, 1.576] |
| 10 | 22.02/s | 15.70/s | 1.403 [1.317, 1.497] |
| 20 | 9.35/s | 7.50/s | 1.246 [1.196, 1.297] |

RocketRide is ahead at **every** chunk count with this text. Note this contradicts the original
1-chunk result (LlamaIndex 1.73× ahead) — which is what forced the investigation below.

## 4. The instrument contradicted itself, and that is how the mechanism was found

Two harnesses reported LlamaIndex at **394 /s** and **180 /s** for the same nominal config. Rather
than pick one, the difference was isolated by varying one thing at a time:

| variant | throughput |
| --- | ---: |
| "Machine learning systems…" doc (1,560 chars), 300 req/driver | 386.3/s |
| same doc, 100 req/driver | 390.8/s |
| "The quick brown fox…" doc (2,000 chars), 300 req/driver | 182.8/s |
| same doc, 100 req/driver | 186.4/s |

**Request count is irrelevant. The document is everything.** A 28 % larger document cost 2.1× the
throughput — because embedding cost is linear in **tokens**, and the two filler texts differ ~2×
in tokens per character.

**My original parity document was ~210 tokens. The real corpus median is 338.** The original test
was measuring a document lighter than 79 % of the corpus.


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

## 5. The mechanism, and the crossover [VERIFIED, 2 methods]

Token count varied directly, chunk count held at 1:

| tokens/doc | RocketRide | LlamaIndex | ratio RR/LI |
| ---: | ---: | ---: | ---: |
| ~50 | 477.4/s | 879.1/s | 0.553 — LlamaIndex 1.81× ahead |
| ~100 | 350.2/s | 649.3/s | 0.533 |
| ~200 | 320.1/s | 406.6/s | 0.787 |
| **~400** | 244.2/s | 196.2/s | **1.272 — RocketRide 1.27× ahead** |

Across 50 → 400 tokens: **RocketRide retains 0.51× of its throughput; LlamaIndex retains 0.22×.**

> **RocketRide is overhead-bound: a high fixed per-request cost (WebSocket + DAP + engine IPC +
> 4 node hops) that dominates small documents and amortises on large ones. LlamaIndex is
> compute-bound: cheap request path, so its throughput tracks token count almost directly.**

**The crossover is 200–400 tokens.** And the corpus sits on it:

| token band | share of mt10k | favours |
| --- | ---: | --- |
| < 200 | 21.4 % | LlamaIndex |
| 200–400 | 38.3 % | crossover zone |
| ≥ 400 | 40.3 % | RocketRide |

That is exactly why the real-distribution result is a modest 1.13× rather than a decisive win
either way — the corpus straddles the crossing point.

### Rule 6 — the rival explanation, and what would falsify this one

The proposed mechanism (per-request overhead amortisation) made a falsifiable prediction: the
ratio must move monotonically toward RocketRide as work per request rises. It does —
0.553 → 0.533 → 0.787 → 1.272.

**The strongest rival:** the difference is per-chunk work, not per-request overhead — e.g.
LlamaIndex's `HuggingFaceEmbedding` wrapper has more per-chunk Python overhead than the engine's
node. **Separating experiment:** hold total tokens constant while varying chunk count (10 chunks
of 40 tokens vs 1 chunk of 400). Overhead amortisation predicts no ratio change; per-chunk cost
predicts a large one. **Not run — ~25 min, and it refines the explanation without changing the
WS-1 answer.** Logged as an open item.

### Rule 5 in reverse — artifacts hunted that would penalise RocketRide

| artifact | handling | result |
| --- | --- | --- |
| cold start in the timed region | engine `connect()`+`use()` hoisted out; 20 warmup requests discarded on both sides | controlled |
| connection setup per request | engine WebSocket opened once; HTTP pooled keep-alive; first-request latency measured separately and excluded | controlled |
| serialization asymmetry | response bytes measured: **9,367 (RR) vs 9,391 (LI) = 0.997×** | symmetric |
| 4 node hops the engine pays | **structural, and it is the main component of the fixed cost that makes RocketRide lose on short documents** — reported, not absorbed | disclosed |
| concurrency pinning (8 vs engine width 17) | previously tested: engine is *slower* at its own width 16 (210.6/s vs 227.8/s) | refuted |

### Rule 7 — hostile reviewer

> *"You reported LlamaIndex 1.73× faster yesterday and RocketRide 1.13× faster today. Which is it?"*

Both measurements were correct for the document they used; neither was correct for the corpus. The
first used a ~210-token document against a corpus whose median is 338, and the winner flips at
200–400 tokens. The corpus-representative answer is RocketRide 1.13×, and the earlier claim is
withdrawn.

> *"The RocketRide arm failed your own variance gate. Why report it?"*

The point estimate is labelled PROVISIONAL for exactly that reason. The direction is supported by
two other experiments that did not fail their gates (the chunk sweep and the token sweep).

## 6. What changed

| claim | before | after |
| --- | --- | --- |
| parity on WS-1 workload | LlamaIndex 1.73× faster [VERIFIED] | **WITHDRAWN** — artifact of a ~210-token document |
| parity on real mt10k | not measured | RocketRide 1.13× faster [PROVISIONAL point, VERIFIED direction] |
| mechanism | unknown | RocketRide overhead-bound, LlamaIndex compute-bound; crossover 200–400 tokens [VERIFIED, 2 methods] |
