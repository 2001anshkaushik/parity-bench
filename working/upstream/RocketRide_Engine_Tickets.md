# RocketRide Engine — Two Tickets

Drafted from the WS-1 cross-team benchmark campaign, 14–18 August 2026.
Three independent harnesses (Leela / LangGraph · Shashi / Haystack · Ansh / LlamaIndex),
three separately built corpora, three separate c7i.8xlarge hosts.

> All bundle- and source-side facts below are verified against
> `rocketride-org/rocketride-server` at HEAD `1138936` and every `server-v3.x` tag; the
> scheduler description in Ticket 2 is verified against `engLib` source, not inferred.

---
---

# TICKET 1 — `BUG_CHUNK_DUPLICATION`

**Title:** `embedding_transformer.writeDocuments()` does not prevent the default action on the flush path — every batch reaching `maxDocuments` is emitted twice

**Type:** Bug · **Severity:** High (silent data duplication) · **Component:** `nodes/embedding_transformer`

**Affects:** the file is **byte-identical at `server-v3.2.0`, `v3.2.1`, `v3.2.2`, `v3.3.0`, `v3.3.1` and current `HEAD` (`1138936`)** — every tagged release since 3.2.0, **and unfixed at HEAD today.**

**Found by:** three independent benchmark harnesses, separately, across three corpora.

## Summary

`writeDocuments()` invokes `preventDefault()` on the **buffer** path but not on the **flush**
path. When the buffer reaches `maxDocuments`, the node flushes the batch downstream and then
returns normally — so **the engine's default action forwards the in-flight event as well**, and
the identical chunk list is delivered a second time.

No error, no warning, no duplicate detection anywhere in the path. Consumers receive a chunk
list exactly 2× the correct length with identical content.

## Root cause — exact code

`nodes/src/nodes/embedding_transformer/IInstance.py` (source) · `nodes/embedding_transformer/IInstance.py` (shipped bundle — the bundle flattens the `src/` segment). The bundle file is **byte-identical to the committed source** at every ref checked; it is authored, not generated.

```python
40    maxDocuments: int = 64          # class attribute — the trigger

51    def _flushDocuments(self):
55        # If we have no documents, stop here
56        if len(self.documents) == 0:
57            return
59        # Encode the documents
60        self.IGlobal.embedding.encodeChunks(self.documents)
62        # Write the documents to the instance
63        self.instance.writeDocuments(self.documents)
65        # Clear the documents
66        self.documents = []

68    def writeDocuments(self, documents: List[Doc]):
75        # Add this set of documents to the list
76        self.documents.extend(documents)
78        # If we have less than the max documents, stop here
79        if len(self.documents) < self.maxDocuments:
80            return self.preventDefault()      # buffer path — default IS prevented
82        # Flush the documents
83        self._flushDocuments()                # flush path — default is NOT prevented
                                               # control returns; default action forwards
                                               # the in-flight event → duplicate emission
```

**Note on `preventDefault()`:** it **raises** — `rocketlib/filters.py:180-190`,
`raise APERR(Ec.PreventDefault, …)`. It never returns a value, so the `return` keyword at `:80`
is dead code. The asymmetry is that line `:80` *raises* and line `:83` does not.

**Why sub-`maxDocuments` documents never duplicate.** Documents that never fill the buffer drain
through `close()` (`:94-96`), where **no event is in flight** for the default action to forward.
Only the mid-stream flush at `:83` occurs while an event is live. This is why the defect is
sharply bounded at the buffer threshold rather than size-proportional.

## Trigger

`maxDocuments: int = 64`, a **class attribute at `IInstance.py:40`**, referenced only at `:79`.
A grep across `nodes/` and `packages/ai` on both the bundle and the source finds **exactly two
sites and no configuration plumbing**; `services.json` carries no such key on either side.

**Predicate: a document producing ≥ `maxDocuments` chunks (64, hard-coded default, not exposed
in node config).** Stated against the attribute rather than the literal so the ticket survives
the value changing.

## Proposed fix

One line, after the flush:

```python
        # Flush the documents
        self._flushDocuments()
        # Flush already delivered this batch downstream.
        return self.preventDefault()
```

## Reproduction — real corpus

GovDocs1 documents, sha256-pinned in the benchmark corpora, standard 4000/200 splitter:

| document | chunks, stock | chunks, corrected |
|---|---:|---:|
| `000_000159.pdf` | 164 | **82** |
| `000_000595.pdf` | 276 | **138** |
| `000_000674.pdf` | 1,872 | **936** |
| `000_000762.pdf` | 132 | **66** |
| `000_000887.pdf` | 344 | **172** |

Every count halves **exactly** — the correction removes precisely the phantom copy and nothing
else. (One repro caveat: `000_000674.pdf` carries an `/Encrypt` marker — the engine's Tika path
parses it, but a repro attempt with a different parser may fail on that one document.)

## Regression test — written, null-controlled both directions

`working/upstream/test_embedding_transformer_flush.py` (commit `ae53b44`), stdlib-only with
stubs for `rocketlib` and `ai.common.schema` so it runs anywhere.

**Design note:** the duplicate emission is performed by the engine's **default action**, which no
unit test reaches. The test therefore pins the contract whose violation causes it — *`writeDocuments`
must prevent the default on every path* — rather than attempting to observe the duplicate.

```
stock:    FAIL exactly 2 of 7 — "64th chunk: default STILL prevented", "64 in one write"
patched:  7 of 7 PASS  (also asserts: encoded exactly once, written downstream exactly once,
                        buffer cleared)
63-chunk case: passes on BOTH — the control inside the control
```

The 63-chunk case passing on stock is what proves the test discriminates the defect rather than
the patch.

*End-to-end synthetic (optional, for CI at the pipeline level): a separator-free repeated-character
text under strlen 4000/200 (stride 3800) of length `L = 4000 + 3800·(n−1)` → 243,400 chars for
n=64 and 239,600 for n=63; assert emitted length and `repeat_factor` (2 stock / 1 patched at 64;
1 / 1 at 63). **`L` is PROVISIONAL** — the engine appends a newline and RecursiveCharacterTextSplitter
boundary semantics deserve one empirical check before this number enters a ticket. The five-document
sha-pinned fixture above is the verified end-to-end reproduction.*

## Evidence — three independent confirmations

| Harness | Finding |
|---|---|
| **Leela** (LangGraph, Tika-vs-Tika) | 51 of 987 documents at `repeat_factor = 2` → **0 of 987** after the fix. With both arms on the same extractor, corrected RocketRide chunk counts converge to LangGraph's to within 7 |
| **Shashi** (Haystack) | `doc-00003` emitted 2× — caught by a newly added duplication gate. Before/after smoke: `220 → 110` chunks on that document, `351 → 241` total. Cross-arm workload ratio `1.58 → 1.09`. Root-caused in source |
| **Ansh** (LlamaIndex) | Fixture above halves exactly, 5 of 5. **`self_duplication` = 0 duplicated of 9,847 documents at 10k scale.** Correction verified *in the shipped artifact* (`grep -c preventDefault` = 1 stock / 2 patched) before any measurement |

## Impact

**Silent corruption of output.** Consumers index duplicate vectors. In a RAG system this skews
retrieval scoring toward documents that happen to cross the buffer threshold.

**Pre-fix throughput figures are wrong in two directions.** `chunks_per_s` is inflated and
`cpu_s_per_chunk` deflated because duplicates are counted — but **`docs_per_s` is *depressed***,
because the engine genuinely performs the doubled embedding work. Measured inflation ~16% on
Shashi's corpus, higher on corpora with more large documents.

**Undetectable by cross-arm equality gating.** When both benchmark arms share an engine, both
duplicate identically and equality passes. Only per-side repeat detection catches this class —
now a permanent gate in all three harnesses.

## Acceptance criteria

- [ ] A document producing ≥ `maxDocuments` chunks emits its chunk list exactly once
- [ ] `test_embedding_transformer_flush.py` lands with the fix (currently 2/7 failing on stock, 7/7 passing patched)
- [ ] Fix applied at HEAD; backport decision recorded for tags ≥ 3.2.0

## Workaround in use today

All three benchmark harnesses apply the one-line correction as a **build-time patch** with
fail-closed guards: the file must exist, contain exactly one `preventDefault` before patching,
match the anchor at exactly 8 spaces, and contain exactly two after — the build fails otherwise.
Every published export from all three teams carries a `duplication_patch_applied` provenance
field.

**No benchmark result from any team describes stock behaviour on this path.**

## Open provenance note

Our upstream clone is **shallow (1 commit)**, so commit-history evidence of authorship is
UNKNOWN. The evidence that the file is authored rather than generated is byte-identity between
the shipped bundle and the committed source across seven refs, plus the absence of codegen
markers and the presence of a human MIT header.

---
---

# TICKET 2 — Batch scheduler starvation on heterogeneous input

**Title:** Native batch API leaves ~50% of allocated cores idle on real-world document mixes — 45% throughput cost versus per-document submission

**Type:** Performance / Architecture · **Severity:** High · **Component:** batch scheduler / `send_files` dispatch
**Affects:** 3.3.1 (patched build — this is independent of `BUG_CHUNK_DUPLICATION`)
**Measured by:** three independent harnesses; isolated by a controlled single-variable experiment

> **Scope note.** This ticket reports a **measurement and an acceptance test**, not a design.
> The controlled experiment establishes that the loss is attributable to the submission path
> rather than to processing speed. Choosing the scheduling approach is the engine team's call —
> the candidate approaches listed are illustrative, not prescriptive.

## Summary

When documents are delivered through the native atomic `send_files()` batch API, the engine
plateaus at roughly half its allocated CPU on corpora with mixed document sizes. Cost per chunk
is unchanged, so the engine is not doing the work more slowly — **it is not being kept fed.**

The same engine, on the same hardware, processing the same documents, achieves **45% higher
throughput** when documents are streamed individually with a bounded in-flight window instead.

## The controlled experiment

Same corpus (9,975 unique GovDocs1 PDFs, sha256 `22177c33c3651fce`), same host, same 24-core
cpuset, same thread pins verified inside both task processes, same patched engine build, same
pipeline (canonical digest `f61165f7cf7ab1db`). **Only the submission path differs.**

| RocketRide, 9,975 documents | per-document, 32 in flight | native `send_files` | delta |
|---|---:|---:|---|
| docs/s | **2.776** | 1.910 | **+45%** |
| chunks/s | **57.39** | 40.51 | +42% |
| CPU utilisation | **69.2%** | 50.4% | +18.8 pp |
| effective cores (of 24) | **16.61** | 12.09 | +4.5 cores |
| wall time | **59.7 min** | 86.3 min | −31% |
| documents returned | 9,975 | 9,975 | — |

**Configuration note, stated because it works against the finding:** the batched run was given
an explicit `use(threads=24)`; the per-document run passed no `threads` parameter and used the
engine default. The arm with **more** configured parallelism used **fewer** cores. The gap is
therefore a conservative estimate.

Artifacts: `smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json` (per-document) ·
`exp_batched_blast__20260818T150551Z__373adce246fc.json` (batch).

## Mechanism — tail-drain stranding (verified against the scheduler source)

Live CPU sampling of the batched run shows two distinct regimes:

| phase | container CPU | cores busy of 24 |
|---|---:|---:|
| steady state | ~1,780% | ~17.7 |
| **tail drain** | **~237%** | **~2.4** |

The batch sustains near-full utilisation while the queue is deep, then **strands up to 21 of
24 cores** while the last large documents finish.

**What the source shows — checked so this ticket does not mis-describe the scheduler:** worker
threads pull per-document work items from a **shared queue**
(`engLib/task/core/pipetask.process.cpp:73` and `:127`, `m_queue.pop()`). Dispatch is already
demand-driven; there is no per-worker pre-assignment to migrate. The stranding is therefore a
**work-granularity** effect: a document is an indivisible item, so once the queue empties, each
remaining large document holds exactly one worker while the rest go idle — and on this corpus
the tail is where the work is (the slowest ~1% of documents carry ~59% of total service
seconds).

Two questions this ticket deliberately leaves open for the engine team rather than answering
wrongly: why steady state holds at ~17.7 of 24 while the queue is still deep, and why the
per-document client path measures higher average utilisation on identical input. The controlled
experiment bounds the effect and localises it to the submission path; no further.

**Client-side view of the same queue behaviour** (Leela, c128, 10k): the worst wait in the run
was a **3-chunk document that waited 34 minutes** — FIFO position behind indivisible large
items, not processing time. Wait grows with backlog: 310 s at n=1,000 → 2,050 s at n=10,000.

## Replication — three harnesses, five configurations

| Harness | Submission shape | CPU utilisation | Effective cores |
|---|---|---:|---:|
| Ansh | native batch, 24-core cpuset | **50.4%** | 12.09 / 24 |
| Shashi | native batch, 32 host cores | **52.9%** | 16.9 / 32 |
| Leela | c128, 32 cores | **56.7%** | 18.1 / 32 |
| Leela | SDK batch, 24 threads | **60.9%** | 14.6 / 24 |
| **Ansh** | **per-document, C=32** | **69.2%** | **16.61 / 24** |

The engine plateaus at **~12–18 effective cores whether offered 24 or 32.**

## Counter-evidence that isolates the cause to input heterogeneity

**On a uniform corpus the same engine saturates.** Shashi's contract corpus (24 seed PDFs
replicated to 10,000 — every document the same size) reached **92.8% utilisation, 29.7 of 32
cores**, on the identical engine build.

**Cost per chunk is flat across corpora** — Shashi measures 0.285 → 0.281 CPU-s per chunk
between the uniform and heterogeneous corpora. Processing is not slower on real documents;
scheduling is.

Both facts together rule out "the engine is slower on messy PDFs" and leave dispatch as the
explanation.

## Impact

**Throughput.** Every cross-team comparison in the campaign shows RocketRide losing under
concurrent load — 1.4× to LlamaIndex, 2.1× to Haystack, 2.4× to LangGraph. The controlled
experiment attributes a substantial share of that gap to the submission path rather than to the
engine.

**Cost.** At 50% utilisation, half the provisioned compute produces nothing.

**Latency predictability.** Worst-case waits land on **small** documents, not large ones, making
them unattributable to the work requested and impossible to write an SLA around.

**Time to first result.** Under an atomic batch, no per-document RESULT is returned until the
entire call completes (confirmed). Shashi measured a first result at **3,466 s** against a
streaming competitor's **0.089 s**. The SDK does document per-file progress events for
`send_files` (`open`/`write`/`close`/`complete`/`error` — `rocketride/mixins/data.py`); none of
the three harnesses consumed them, and whether `complete` fires per file mid-batch is untested.
The first-result figures compare the response channel, not the event channel.

## Acceptance criteria

- [ ] **Under a native batch on a heterogeneous corpus, sustain ≥17 of 24 effective cores (≥70% utilisation)** — parity with what the per-document path already achieves on identical input
- [ ] The batched/per-document throughput gap on the same corpus closes to **within 10%** (currently 45%)
- [ ] Tail drain bounded: CPU does not fall below 50% of steady-state utilisation for more than ⟨threshold TBD⟩ of the run
- [ ] Worst-case wait becomes proportional to document size rather than queue position — a small document must not wait behind large ones for tens of minutes

**Suggested acceptance test:** re-run the controlled experiment above. Same corpus, same
hardware, both submission shapes. The delta is the metric.

## Candidate approaches — illustrative, not prescriptive

Offered only to show the acceptance criteria are reachable. **The engine team should choose.**
Dispatch is already a shared demand-driven queue (see Mechanism), so the remaining levers are
ordering and granularity:

- **Size-aware ordering (LPT)** — sort the batch largest-first (page count or byte size as the
  estimate) so the long documents overlap with everything else instead of forming the drain
- **Finer tail granularity** — allow a single large document's chunk embedding to be split
  across idle workers once the queue empties, so the drain runs at N cores rather than one per
  remaining document
- **Streaming results behind the existing interface** — keep `send_files` but return each
  document's result as it completes, which also gives the caller its first result in seconds
  rather than at batch completion

## Related

- **Ticket 3 (recommended, not drafted here): surface parse failures.** A corrupt document currently returns `action: "complete"` with an objectId, metadata and an empty document list — structurally indistinguishable from a legitimately empty PDF. All three harnesses hit this; surfacing scored 0/1 (Ansh) and 0/4 (Leela) against competitors surfacing 4/4. Separate defect, separate fix, same campaign.
- **`BUG_CHUNK_DUPLICATION`** (Ticket 1) is independent — all measurements above are on a corrected build.

---

## Appendix — provenance for both tickets

| | |
|---|---|
| Engine | 3.3.1, `/version` hash `a0817cc6`, stamp `2026-07-07T04:45:25Z` |
| Engine binary | extracted sha256 `95768e2640df2d34dd6dfea2e456f36da03ad80b091f9d057c116dfe748d9747` |
| Release tarball | `rocketride-server-v3.3.1-linux-x64.tar.gz`, sha256 `d8dad45b…` |
| Second required patch | onnxruntime `1.20.1 → 1.20.2` across five requirements files — **1.20.1 was never published to PyPI, so stock 3.3.1 cannot boot on any Linux host.** Separately reported |
| Pipeline | 5-node, canonical digest `f61165f7cf7ab1db`, identical across all three harnesses |
| Model | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, 384-d, resolved from the engine's own `nodes/embedding_transformer/services.json` |
| Hardware | c7i.8xlarge, 32 vCPU, 61 GiB MemTotal measured (64 GiB nominal), Linux x86-64 native |
| Corpus | GovDocs1, 9,975–10,000 unique documents, sha256-pinned per document |
| Measurement | kernel cgroup counters via container PID · client-observed clocks · fail-closed gates · no framework self-reporting |
| Full reports | Ansh `WS1_Benchmark_Complete.md` · Shashi `RESULTS-RR-vs-HS-2026-08-17.md` + `RUN-SPECS` · Leela `BENCHMARK_RUNS.md` |
| Artifacts | `s3://rocketride-benchmark-data/` |
