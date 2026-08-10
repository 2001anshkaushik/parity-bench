# Toil Log — LlamaIndex Service (WS-1)

Written **during** the work, not reconstructed afterwards. Every scaffolding decision, every
error, every judgment call where the docs were silent, with wall-clock cost.

## Starting state — honest baseline

| | |
| --- | --- |
| Author | Ansh (via Claude, pair-working) |
| **Prior LlamaIndex experience** | **None.** Never used the library. No prior knowledge of its reader API, node parsers, embedding wrappers, or deployment guidance. |
| Prior FastAPI/uvicorn experience | Yes — built the benchmark-A `asyncio_service` wrapper (Aug 4) |
| Prior embedding-service experience | None with `multi-qa-MiniLM-L6-cos-v1` specifically |
| Host | Apple M4 Pro, 14 cores (10P+4E), 48 GiB, macOS 26.6, AC power |
| Venv | `Benchmarking/.venv`, Python 3.12.13 |

This matters for the toil comparison: the RocketRide side of WS-1 is being built by people who
wrote the engine. The LlamaIndex side is being built by someone starting from zero. Any
"time to working service" comparison must state both starting points or it is meaningless.

---

## Running log

### 11:42 — Session start, machine hygiene
Checked host state before touching anything (standing rule): 787 uid processes, 3 stray
`node.py` from the benchmark-A engine (not ours, left running), engine healthy on :5565.
No cleanup needed. **Cost: 1 min.**

### 11:42 — Launched LlamaIndex verification in background
`scripts/verify_frameworks.py llamaindex --install` — installs into a disposable venv, so it is
network/disk bound and can run while I write the team brief. Deliberate parallelism.
**Cost: 0 min (backgrounded).**

### 11:45 — LlamaIndex stack install
`uv pip install llama-index-core llama-index-embeddings-huggingface sentence-transformers`.
Pulled torch 2.13.0 + transformers 5.14.1 as transitive deps. One warning:
`huggingface-hub==1.26.0 does not have an extra named 'inference'` — a stale extra reference in a
dependency's metadata, not fatal. Noted, ignored.
Versions landed: llama-index-core 0.14.23, llama-index-embeddings-huggingface 0.7.0,
sentence-transformers 5.6.1, torch 2.13.0. **Cost: ~2 min (backgrounded).**

### 11:45 — Found and fixed 2 bugs in our own verify_frameworks.py
Running LlamaIndex through it surfaced two tool defects that would have misled the team:
1. **False `ModuleNotFoundError`** — it derived the import name from the distribution name by
   `dash -> underscore`, giving `llama_index_core`. The real import is `llama_index.core`.
   Namespaced packages break the naive rule. Fixed to try several spellings.
2. **False "depends on another framework under test"** — `llama-index-core` matched the token
   `llama-index` against *itself*. Fixed to exclude self-tokens.
Both are now fixed in the copy going to Shashi. **Cost: 4 min.**

### 11:46 — Behavioural probe of the native path (Step 3 requirement)
Wrote a throwaway probe rather than trusting the dossier. All native paths import and run with
**no API key of any kind** (explicitly unset OPENAI/LLAMA_CLOUD/HF tokens first):

| check | result | cost |
| --- | --- | ---: |
| `llama_index.core` import | OK, v0.14.23 | 4,804 ms |
| `SentenceSplitter` (native) | OK, splits | 288 ms |
| `SimpleDirectoryReader` (native) | OK | 0 ms |
| `LangchainNodeParser` bridge present | OK | 0 ms |
| `HuggingFaceEmbedding` import | OK | **31,436 ms** |
| no API key required | OK | 0 ms |

⚠️ **Import cost is the story here: 31.4 s to import the embedding wrapper (torch), 4.8 s for
core.** That is ~36 s of cold start before a single document is processed, and it must sit outside
every timed region. Same class of trap as RocketRide's ~60 s first launch.
**Cost: 6 min including writing the probe.**

### 11:48 — Model verified against the schema contract
`multi-qa-MiniLM-L6-cos-v1` via `HuggingFaceEmbedding`: **384 dims, L2 norm = 1.000000, normalized
without passing any `normalize_embeddings` flag** — confirming Leela's Stage 0 #9 finding that the
model's own `Normalize` module does it. Model load 6.37 s (warm HF cache), batch encode of 2
chunks 1.98 s cold.
Noted: HF prints `You are sending unauthenticated requests to the HF Hub` — downloads work but are
rate-limited. Not a blocker locally; would be one in CI. **Cost: 3 min.**

### 11:50 — ⚠️ JUDGMENT CALL #1: which splitter? (the biggest decision in this service)
**The conflict:** the WS-1 canonical contract mandates `RecursiveCharacterTextSplitter()` at
LangChain defaults (4000/200). LlamaIndex's *native* node parser is `SentenceSplitter`, which is a
different algorithm and produces **different chunk boundaries**. I cannot satisfy both.

Options considered:
- **(a) Native `SentenceSplitter`** — most faithful to "a LlamaIndex service", but produces
  different chunks from the other two services, which makes cross-service goodput verification
  impossible. The whole point of the shared schema dies.
- **(b) `LangchainNodeParser(RecursiveCharacterTextSplitter())`** — LlamaIndex ships this bridge
  for exactly this purpose. Identical chunks across services; still executed through LlamaIndex's
  node-parser pipeline.
- **(c) Call LangChain's splitter directly, bypassing LlamaIndex** — identical chunks but no
  longer meaningfully a LlamaIndex service.

**Decision: (b) as the default, with (a) available behind a config flag.**
Rationale: parity is the deliverable, and comparing chunkers is a *different* experiment. Building
both costs ~20 extra lines and lets us later measure what LlamaIndex's own splitter costs, which
is a genuinely interesting question that should not be silently foreclosed today.
Installed `langchain-text-splitters` for this (small, standalone — not the full LangChain).
**Flagged for Leela in SCHEMA_PROPOSAL open questions. Cost: 5 min including the install.**

### 11:52 — Service built: 3 modules, deliberately layered
`ws1/schema.py` (wire contract, isolated), `ws1/pipeline.py` (LlamaIndex, no HTTP),
`ws1/service.py` (HTTP, constructs no wire dicts). If Leela's schema differs, only `schema.py`
changes. **Cost: 12 min.**

**JUDGMENT CALL #2 — `def` not `async def` for `/process`.** The work is CPU-bound (tokenise +
forward pass). An `async def` endpoint runs directly on the event loop and would block every other
request on that worker, including `/health`. Declaring it `def` makes Starlette dispatch it to its
threadpool. This is FastAPI's documented guidance for blocking work and is the single most
consequential line in the service. Getting it wrong is a classic strawman-by-accident.

**JUDGMENT CALL #3 — model load in `lifespan`, not lazily.** torch import ~30 s + model load ~6 s.
uvicorn does not route to a worker until lifespan startup completes, so this makes `/health`'s
`model_loaded` a trustworthy start gate and keeps ~36 s out of every latency measurement.

**JUDGMENT CALL #4 — thread env pinned to 1 in the launcher.** 14 uvicorn workers × torch/BLAS
defaulting to one thread per core = ~200 threads on 14 cores. Pinned `OMP/MKL/OPENBLAS/VECLIB` to
1 so each worker is single-threaded and concurrency comes from workers. Docs are silent on this
interaction; recorded as a call.

**JUDGMENT CALL #5 — `TOKENIZERS_PARALLELISM=false` set before torch import.** HF tokenizers fork
a thread pool and warn (and can deadlock) under a forking server; `uvicorn --workers` forks.
Set in both `pipeline.py` (module import) and the launcher, belt and braces.

**Uvicorn tuning (per its deployment docs, not defaults):** `--workers 14` (one per logical core),
`--loop uvloop`, `--http httptools`, `--no-access-log`, `--timeout-keep-alive 30`.
`--limit-concurrency` deliberately left unset so backpressure is the server's own behaviour rather
than a cap I imposed.

### 11:53 — Conformance test: ALL PASS, including the one that matters
Wrote `/tmp/ws1_conform.py` against the running service. The critical assertion is chunk-level:
service output compared **byte-for-byte** against a reference
`RecursiveCharacterTextSplitter(4000, 200).split_text(text + '\n')`.

| check | result |
| --- | --- |
| manifest carries splitter/chunk_size/overlap/effective_concurrency/concurrency_source | PASS |
| 384-dim, L2 norm = 1.000000 | PASS |
| multi-chunk count matches reference (9 vs 9) | PASS |
| **chunk text matches reference byte-for-byte** | **PASS** |
| empty document -> `ok:true`, 0 chunks | PASS |
| canonical encoder produces compact JSON | PASS |

Per-doc timing at trace: **total 28.7 ms (split 0.56 ms, embed 28.1 ms)** — consistent with
Leela's Stage 1 figure of ~31 ms per 100-chunk encode. **Cost: 8 min.**

### 11:55 — ⚠️ BROKE: 14-worker startup looked half-dead, and my process census was lying
Started with `WS1_WORKERS=14`. `/health` returned `model_loaded: true` after 15 s but only **2 of
14** workers had logged "warm", and `pgrep -f "uvicorn ws1.service" | wc -l` reported **1 process
using 19.6 MB**.

Two separate things, one real and one an instrument bug:
1. **Not actually broken.** `/health` is answered by whichever worker uvicorn routes to, so it can
   report healthy while siblings are still loading. Waiting 30 s more: all 14 warm.
   **`model_loaded` on a single worker is NOT a whole-service start gate** — the driver must poll
   until it has seen every worker warm, or use worker count from the manifest. Fixing this in the
   schema note for Leela.
2. **My census was undercounting by 16×.** uvicorn spawns workers via `multiprocessing`, so their
   cmdline is `python -c from multiprocessing.resource_tracker import ...` — it does not contain
   "uvicorn". Matching on cmdline finds only the master.

Walking the process tree from the master PID instead gives the truth:
**16 processes (master + 14 workers + 1 resource tracker), 3,404 MB RSS, 90 threads.**
So per-worker footprint is ~243 MB and the honest 14-worker memory cost is **3.4 GB, not 19.6 MB**.

This is exactly the bug flagged as A7 in `ADVERSARIAL_AUDIT.md` — benchmark-A's Tier 2 table
reported FastAPI at "30 MB" for the same reason. **Any WS-1 memory comparison must walk process
trees from a root PID, never grep cmdlines.** Fixed in the packaged collector.
**Cost: 6 min to diagnose. Would have silently corrupted every memory number.**

### 12:00 — ⚠️ THE BIG ONE: declared concurrency 14, MEASURED concurrency ~4
Applied the schema's own rule ("verification, not declaration") to my own service. It failed.

Throughput vs client concurrency, 14 uvicorn workers:

| concurrency | throughput | p50 | p99 | distinct workers hit |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 89.1/s | 10.47 ms | 15.06 ms | 1 |
| 2 | 167.1/s | 10.35 ms | 20.20 ms | 2 |
| **4** | **338.8/s** | **11.28 ms** | 16.61 ms | 4 |
| 6 | 198.5/s | 27.48 ms | 54.54 ms | 5 |
| 8 | 164.7/s | 37.07 ms | 310.35 ms | 6 |
| 16 | 189.3/s | 70.56 ms | 345.27 ms | 7 |
| 32 | 193.5/s | 100.38 ms | 597.77 ms | 6 |

**Perfectly linear to 4 (89 → 167 → 339, i.e. 1.0x / 1.9x / 3.8x), then a cliff.** Beyond
concurrency 4 throughput *falls* and p50 triples. The service has an effective width of ~4 despite
running 14 workers.

Corroborating evidence gathered while chasing this:
- A multi-process driver made it *worse*, not better: 1 driver 446/s → 2 drivers 223/s →
  4 drivers 171/s. **This is the opposite of the RocketRide single-driver bug** — here the client
  was never the ceiling, and adding client processes just added contention.
- Per-core CPU during load: `[41,33,26,19,4,3,1,1,1,38,33,29,22,17]` — ~2.7 cores of 14 busy.
  **Nothing is saturated.** Not CPU-bound at the point where it stops scaling.
- Only 6–7 of 14 workers ever receive traffic under keep-alive; connections pin to whichever
  worker accepted them, and the accept distribution is uneven.

> **CORRECTION (2026-08-05, later session): CAUSE FOUND — it was the GPU. [VERIFIED, 2 methods]**
> `sentence-transformers` silently selects `mps` (Apple GPU) on this host. A null control with the
> ENTIRE HTTP layer removed reproduced the ceiling: 14 independent processes gave 2.61x, with only
> **1.69 cores busy** — the work was off-CPU. Forcing `device="cpu"` gives 8.09 cores busy and
> proper CPU scaling. The web stack was innocent; so were memory bandwidth, E-cores and accept
> distribution as *primary* causes. The "~4" figure was an mps measurement; on cpu the knee is 8.
> See `CONCURRENCY_CEILING.md`.

~~**Cause: UNVERIFIED.** Candidates I could not distinguish in the time available: memory-bandwidth
contention between concurrent MiniLM forward passes; macOS scheduling workers onto the 4
efficiency cores; or accept-distribution unevenness leaving most workers idle while a few queue.~~
*(superseded — retained to show what the reasoning looked like before the null control.)*

**What I changed as a result:** the manifest no longer declares `effective_concurrency: 14`. It
now reports the *measured* value with the measurement method, and carries the declared value
separately so the discrepancy is visible rather than hidden. **A service that declares its worker
count as its concurrency is lying by default** — mine was, for about 20 minutes.
**Cost: 12 min to find. Highest-value 12 minutes of the session.**

### 12:04 — Measurement variance on my own service, too
The same nominal load measured 446/s in one run and 165/s in another (conc=8, ~2.7x). This is the
same ±35%-or-worse variance flagged in `FINDINGS_FOR_WS1.md` §3, on a completely different
service — which argues it is a property of this **host**, not of RocketRide. The variance
protocol needs to apply to all three WS-1 services, not just the engine.

### 12:10 — Packaged the reusable instruments (Step 2)
`handoff/` — `seeds.py`, `fault_injection.py`, `tree_collector.py` (single file, merged from two),
`test_collector_overhead.py`, `verify_frameworks.py`, plus a README with integration notes.
The collector merge broke first: naive concatenation of two modules left a second
`from __future__ import annotations` mid-file (`SyntaxError`). Rebuilt with a proper import
de-duplication pass. Overhead test on this host: **−6.1% overhead, 6.9% baseline noise, PASS**.
**Cost: 14 min.**

### 12:14 — Re-verified LlamaIndex with the fixed tool; restarted service; final conformance
Dossier now clean: `import_ok: OK`, `depends_on_frameworks_under_test: []`, no telemetry
endpoints, MIT, ACTIVE (41 days since release). Still `REVIEW_REQUIRED` on locality because the
source mentions `api.cloud.llamaindex.ai` — that is LlamaCloud, their hosted product, and the
behavioural probe at 11:46 proved the local path needs no key. **The heuristic is right to flag it
and wrong to conclude from it; the behavioural probe is what settles it.**

Restarted the service so the manifest picks up the measured-concurrency change. All 14 workers
warm. Manifest now reports `effective_concurrency: 4, declared_workers: 14` with the method
inline. Full conformance suite re-run: **ALL PASS**. **Cost: 6 min.**

---

## Time summary

| step | wall-clock |
| --- | ---: |
| Machine hygiene + verification launch | 1 min |
| LlamaIndex install (backgrounded) | 2 min |
| Fixing 2 bugs in our own verify_frameworks | 4 min |
| Behavioural probe of native path | 6 min |
| Model verification against schema | 3 min |
| Splitter judgment call + install | 5 min |
| Building the 3-module service | 12 min |
| Conformance test | 8 min |
| Debugging 14-worker startup + census undercount | 6 min |
| **Measuring effective concurrency (found declared 14 vs real 4)** | **12 min** |
| Packaging instruments | 14 min |
| Re-verify + restart + final conformance | 6 min |
| **Total hands-on** | **~79 min** |

Excludes writing `FINDINGS_FOR_WS1.md` and `SCHEMA_PROPOSAL.md` (separate deliverables, ~25 min).

**Starting from zero LlamaIndex experience, a schema-conformant service took ~79 minutes** — but
that number is only meaningful next to two things: (a) most of it was *verification*, not
construction; the service itself is ~250 lines and took 12 minutes, and (b) ~18 of those minutes
went to finding two problems that would have silently corrupted results (the census undercount and
the declared-vs-measured concurrency gap). A version of this service built without those checks
would have taken ~35 minutes and been wrong.

## What broke, in order

1. `verify_frameworks.py` reported a false `ModuleNotFoundError` (namespaced package).
2. `verify_frameworks.py` reported a false self-dependency.
3. 14-worker startup *looked* half-dead — `/health` is answered by one worker and is not a
   whole-service gate.
4. Process census undercounted the service 173× (cmdline grep vs process tree).
5. Merged collector module had a duplicate `__future__` import (SyntaxError).
6. **Declared concurrency 14, measured 4.** My own service failed the rule I wrote into the schema.
   *(Superseded: the "4" was measured on mps. Root cause was the GPU — on `cpu` the knee is 8.
   See `CONCURRENCY_CEILING.md`. The failure it records is still real: I declared a worker count
   as a concurrency.)*

## Open items for this service

- ~~Cause of the concurrency-4 ceiling is UNVERIFIED.~~ **RESOLVED: it was the GPU (`mps`).**
  Device is now explicit, default `cpu` for parity. See `CONCURRENCY_CEILING.md`.
- Only 6–7 of 14 workers receive traffic under keep-alive. If that is the cause, a
  `--limit-max-requests` or a connection-recycling client would change the picture.
- Native `SentenceSplitter` mode is implemented but never benchmarked.
- Measurement variance on this service is ~2.7× between runs at the same nominal load. The
  variance protocol in `FINDINGS_FOR_WS1.md` §3 applies here too.
