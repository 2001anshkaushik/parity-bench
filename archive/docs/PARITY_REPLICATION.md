# STEP 4 — Parity Replication: RocketRide vs LlamaIndex on the real embedding workload

## ~~Result: LlamaIndex ~1.7× faster at matched concurrency.~~ **WITHDRAWN**

> ## ⛔ WITHDRAWN 2026-08-05 — this result does not survive the corpus-shape gate
>
> **The "LlamaIndex 1.73× faster" finding below is an artifact of an unrepresentative test
> document and is withdrawn.** The document used was ~210 embedded tokens; the real mt10k corpus
> median is **338 tokens**, and the two services **cross over at 200–400 tokens**.
>
> **Corpus-representative result: RocketRide is 1.13× faster** [CI95 1.064–1.183] on the verified
> mt10k distribution. RocketRide is ahead at every chunk count on longer text (1.23×–1.55×).
>
> Mechanism [VERIFIED, 2 methods]: RocketRide is **overhead-bound** (high fixed per-request cost —
> WebSocket + DAP + IPC + 4 node hops — that amortises on larger documents); LlamaIndex is
> **compute-bound**. Across 50→400 tokens RocketRide retains 0.51× of throughput, LlamaIndex 0.22×.
>
> **Everything below is retained as the record of how the wrong answer was reached.** See
> `PARITY_CORPUS_FINDINGS.md` for the replacement.


This is **unfavourable to RocketRide**, so it was measured under the strictest conditions in this
project and every artifact that could unfairly penalise the engine was hunted and tested rather
than argued about. One suspected artifact was found, tested, and **refuted** — the engine does not
gain from removing it.

Raw data: `results/parity_replication.json`, `results/parity_llamaindex_regate.json`,
`results/parity_rocketride_own_width.json`.

---

## The numbers

Same driver pool, same document, same device (`cpu`, asserted at startup), both pinned to **8
in-flight** (2 drivers × 4), 20 warmup requests discarded per run, randomised order.

| service | median | spread | CI95 | p50 latency | response bytes |
| --- | ---: | ---: | --- | ---: | ---: |
| **RocketRide** | **227.83/s** | 5.0 % ✅ | [225.6, 232.7] | 35.65 ms | 10,288 |
| **LlamaIndex** | **394.37/s** | 5.3 % ✅ | [386.3, 396.0] | 17.05 ms | 10,368 |

**Ratio: LlamaIndex 1.73× faster** (0.578 as RocketRide/LlamaIndex). The confidence intervals do
not merely fail to overlap — they are separated by a wide margin (232.7 vs 386.3), so this is not
a marginal call.

Cross-check with the first, fully-randomised pass (LlamaIndex median 381.08/s there): ratio 1.67×.
**Both computations land at ~1.7×**, so the conclusion does not depend on which LlamaIndex run is
used.

## Rule 5 in reverse — artifacts hunted that would PENALISE the engine

| # | suspected artifact | how it was handled | result |
| --- | --- | --- | --- |
| A1 | Cold start / model load inside the timed region | Engine `connect()` + `use()` + first request hoisted out; **20 warmup requests discarded** on both sides before timing | Controlled |
| A2 | Per-request connection setup | Engine WebSocket opened once outside timing; HTTP side uses a pooled keep-alive session. First-request latency reported separately (RR 32 ms vs LI 17 ms) and **excluded** from the measurement | Controlled |
| A3 | Serialization asymmetry — one side shipping more bytes | Response measured with the canonical encoder on both: **10,288 vs 10,368 bytes = 0.99×**. Both return 1 chunk, 384 dims | **Symmetric — no artifact** |
| A4 | Per-request overhead the engine pays and mine does not | Engine pays WebSocket framing + DAP + engine IPC + a node-process hop. **Structural, reported not absorbed** — see below | Disclosed |
| A5 | **Concurrency pinning handicap** — engine width is 17, pinned to 8 | I predicted this penalised the engine, so I measured it: RocketRide at its own width (~16 in flight) | **REFUTED — see below** |

### A5 in detail: the handicap I expected did not exist

Pinning both services to 8 puts LlamaIndex at its measured optimum (knee = 8) while RocketRide runs
at 8 of its 17. That looked like an unfair handicap, so it was tested directly:

| RocketRide configuration | median | spread | p50 |
| --- | ---: | ---: | ---: |
| pinned to 8 in-flight (the comparison) | **227.83/s** | 5.0 % | 35.65 ms |
| at its own width, ~16 in-flight | **210.60/s** | 6.3 % | ~70 ms |

**Running the engine at its own measured width makes it slower, not faster** (−7.6 % throughput,
2× worse latency). The pinned comparison is therefore *favourable* to RocketRide, not unfair to it.
Reporting the 8-wide figure is the conservative choice.

## Rule 6 — strongest rival explanation

**Rival:** the engine runs a four-node pipeline
(`webhook → preprocessor_langchain → embedding_transformer → response_documents`) while the
LlamaIndex service does split+embed inside one process. The engine therefore pays several
inter-node hops for the same logical work, and this gap could be measuring *pipeline topology*
rather than framework efficiency.

**Is that an artifact or the thing being measured?** It is genuinely the thing being measured —
a dataflow engine's per-node hop cost is part of what you get when you choose that engine, and
the WS-1 brief specifies this pipeline. But the honest statement is narrower than "LlamaIndex is
faster": it is **"for this 4-node pipeline shape on a single-chunk document, LlamaIndex is 1.7×
faster."**

**The experiment that would separate them** (not run): implement the same logical work as a
*single* RocketRide node and compare. That isolates per-node hop cost from framework cost. ~1 hour.
**Skipped under the stopping rule** — it changes the interpretation, not the WS-1 answer, since
WS-1 specifies the four-node pipeline. Logged as an open item.

## Rule 7 — what a hostile reviewer would say

> *"You benchmarked your own framework against a competitor and your framework won. Why should
> anyone believe that?"*

Because the one asymmetry I found in RocketRide's favour was tested and reported (A5 — pinning at
8 *helps* the engine, and I kept it), because the arm that failed the variance gate was **mine**
and I re-ran it rather than reporting it, and because response bytes were verified symmetric to
within 1 %. The result also contradicts my own earlier prediction that the two would land within
1.5× on the real workload — I predicted closer parity and was wrong.

> *"LlamaIndex's first measurement failed your own 10 % gate at 13.7 %. Did you re-run until you
> got a number you liked?"*

Fair challenge. The re-run was n=7 (not a cherry-picked subset), the median moved from 381.08 to
394.37 — **3.5 %**, which does not change the conclusion — and the first, gate-failing run is
reported here alongside the second. The ratio is ~1.7× either way.

> *"The engine's 4-node pipeline is doing more work per request."*

Answered above under Rule 6, and it is why the claim is scoped to this pipeline shape.

## Confidence and scope

**Label: VERIFIED**, with these boundaries:

- **Scope: one document shape** (~1.6 KB, single chunk). Multi-chunk documents change the
  embed:overhead ratio and could move this substantially — a 10-chunk document does 10× the model
  work against the same per-request overhead, which should favour the engine. **UNVERIFIED at
  other document sizes, and this is the single most likely thing to change the answer.**
- **Scope: this host, `device=cpu`, this 4-node pipeline.**
- The LlamaIndex arm's first pass failed the variance gate and was re-run; both figures reported.
- The head-to-head randomisation covers the first pass; the re-gated LlamaIndex run was sequential.
  Minor protocol deviation, disclosed; the two LlamaIndex medians differ by 3.5 %.

## What this does NOT say

It does **not** say LlamaIndex is a better choice than RocketRide. It says that on this specific
pipeline, document shape, and host, it processes ~1.7× more documents per second at matched
concurrency. Fault isolation, memory under pressure, operational complexity and blast radius are
separate axes measured elsewhere in this repo, and on at least one of them (peak memory under held
allocations) RocketRide was the better performer.
