# Parity Replication Request — for Shashi

**This is a request for replication, not a result to accept.**

I measured the RocketRide service with my own harness. That is your service and out of my lane, so
the number below should not enter any deck until you have reproduced or refuted it independently.
Everything needed is in this directory.

## What I measured

On the verified mt10k corpus, both services CPU-pinned at 8 concurrent requests:
**RocketRide 233.95/s vs LlamaIndex 202.27/s — RocketRide 1.13× faster** [CI95 1.064–1.183].

**Caveat I want you to check first:** the RocketRide arm's run-to-run spread was **14.8 %**, which
fails our own 10 % variance gate. By protocol that arm is an invalid measurement standing alone.
I report it because two other experiments point the same way, but the point estimate is
**PROVISIONAL** and reproducing it is exactly what would settle it.

## Why the earlier number was wrong (worth 2 minutes)

I previously reported "LlamaIndex 1.73× faster" and **withdrew it**. The test document was
~210 embedded tokens; mt10k's median is 338; the services cross over at 200–400 tokens. I was
benchmarking a document lighter than 79 % of the corpus.

**Embedding cost is linear in tokens, not characters or chunks.** RocketRide is overhead-bound
(fixed WebSocket + DAP + IPC + 4-node-hop cost per request); LlamaIndex is compute-bound. Across
50→400 tokens RocketRide retains 0.51× of throughput, LlamaIndex 0.22×.

**If you take one thing from this: never benchmark on a convenience document.**

## Conditions required for the result to be valid

A run that violates any of these is not a slow result, it is an invalid measurement:

| # | condition | how to check |
| --- | --- | --- |
| 1 | **Both services on `device=cpu`, asserted not declared** | read the device off the loaded model; ours refuses to start on mismatch. `sentence-transformers` silently picks `mps` on Apple Silicon. |
| 2 | **Corpus verified** | `corpus_characterize.py` rebuilds mt10k and checks 10,000 sha256 against Leela's manifest. Must be 10,000/10,000. |
| 3 | **Report the token distribution** with any throughput number | the winner depends on it |
| 4 | **Both pinned to the same effective concurrency, MEASURED** | `handoff/pool_width.py` (guarded — it escalates offered concurrency and hard-fails rather than returning the offered value) |
| 5 | **Warmup discarded** (≥20 requests), setup/model-load outside the timed region | our 4.8× and 100× errors both came from this class of mistake |
| 6 | **n ≥ 5, interleaved and randomised in ONE session** | between-session drift is real here and within-session repetition will not catch it |
| 7 | **Both arms pass the 10 % variance gate** | `variance_gate.py`, exits non-zero on failure |

## How to run it

```bash
cd benchmark-A
../.venv/bin/python scripts/corpus_characterize.py      # verifies the corpus, ~2 min
bash scripts/start_engine.sh                            # RocketRide engine
../.venv/bin/python scripts/parity_corpus.py            # both arms, interleaved, ~25 min
```

Outputs `results/parity_corpus.json` with per-rep rates, spreads, CIs and the chunk sweep.

`parity_corpus.py` starts the LlamaIndex service itself and asserts `resolved_device == cpu`
before measuring. To point it at a different RocketRide pipeline, edit `pipes/embed_probe.pipe`.

## What I would most like you to challenge

1. **Is `pipes/embed_probe.pipe` the right RocketRide configuration?** It is
   `webhook → preprocessor_langchain → embedding_transformer → response_documents` with
   `profile: miniLM`. If the engine should be configured differently, my number is measuring the
   wrong thing and I would rather know now.
2. **Is the 4-node hop cost avoidable?** It is the main component of the fixed per-request cost
   that makes RocketRide lose on short documents. If a single-node pipeline does the same work,
   the crossover moves and so does the answer. I did not test this — ~1 hour, and it is your call
   whether it is worth it.
3. **Does the 14.8 % spread reproduce?** If it does not on your setup, the point estimate firms up.
   If it does, we should find out why before either of us quotes a ratio.

Happy to walk through the harness, hand it over entirely, or re-run anything with you watching.
