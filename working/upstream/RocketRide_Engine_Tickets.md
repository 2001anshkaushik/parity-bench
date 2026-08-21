# RocketRide Engine — Five Tickets

Drafted from the WS-1 cross-team benchmark campaign, 14–21 August 2026.
Three independent harnesses — each comparing RocketRide against a different framework
(LangGraph, Haystack, LlamaIndex) — three separately built corpora, three separate
c7i.8xlarge hosts. Harnesses are identified below by the framework they measured against;
all three findings are reproducible from the artifacts listed in the appendix.

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
| **LangGraph harness** (Tika-vs-Tika) | 51 of 987 documents at `repeat_factor = 2` → **0 of 987** after the fix. With both arms on the same extractor, corrected RocketRide chunk counts converge to LangGraph's to within 7 |
| **Haystack harness** | `doc-00003` emitted 2× — caught by a newly added duplication gate. Before/after smoke: `220 → 110` chunks on that document, `351 → 241` total. Cross-arm workload ratio `1.58 → 1.09`. Root-caused in source |
| **LlamaIndex harness** | Fixture above halves exactly, 5 of 5. **`self_duplication` = 0 duplicated of 9,847 documents at 10k scale.** Correction verified *in the shipped artifact* (`grep -c preventDefault` = 1 stock / 2 patched) before any measurement |

## Impact

**Silent corruption of output.** Consumers index duplicate vectors. In a RAG system this skews
retrieval scoring toward documents that happen to cross the buffer threshold.

**Pre-fix throughput figures are wrong in two directions.** `chunks_per_s` is inflated and
`cpu_s_per_chunk` deflated because duplicates are counted — but **`docs_per_s` is *depressed***,
because the engine genuinely performs the doubled embedding work. Measured inflation ~16% on
the Haystack harness's corpus, higher on corpora with more large documents.

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

**Client-side view of the same queue behaviour** (LangGraph harness, c128, 10k): the worst wait in the run
was a **3-chunk document that waited 34 minutes** — FIFO position behind indivisible large
items, not processing time. Wait grows with backlog: 310 s at n=1,000 → 2,050 s at n=10,000.

## Replication — three harnesses, five configurations

| Harness | Submission shape | CPU utilisation | Effective cores |
|---|---|---:|---:|
| LlamaIndex harness | native batch, 24-core cpuset | **50.4%** | 12.09 / 24 |
| Haystack harness | native batch, 32 host cores | **52.9%** | 16.9 / 32 |
| LangGraph harness | c128, 32 cores | **56.7%** | 18.1 / 32 |
| LangGraph harness | SDK batch, 24 threads | **60.9%** | 14.6 / 24 |
| **LlamaIndex harness** | **per-document, C=32** | **69.2%** | **16.61 / 24** |

The engine plateaus at **~12–18 effective cores whether offered 24 or 32.**

## Counter-evidence that isolates the cause to input heterogeneity

**On a uniform corpus the same engine saturates.** A contract corpus (24 seed PDFs
replicated to 10,000 — every document the same size) reached **92.8% utilisation, 29.7 of 32
cores**, on the identical engine build.

**Cost per chunk is flat across corpora** — 0.285 → 0.281 CPU-s per chunk measured
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
entire call completes (confirmed). A first result was measured at **3,466 s** against a
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

- **Ticket 3 (recommended, not drafted here): surface parse failures.** A corrupt document currently returns `action: "complete"` with an objectId, metadata and an empty document list — structurally indistinguishable from a legitimately empty PDF. All three harnesses hit this; surfacing scored 0/1 and 0/4 in two of them, against competitor frameworks surfacing 4/4. Separate defect, separate fix, same campaign.
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
| Full reports | Per-harness benchmark reports and run specifications, published alongside the artifacts |
| Artifacts | `s3://rocketride-benchmark-data/` |


---

# TICKET 3 — `BUG_CHUNK_CONFIG_IGNORED`

**Title:** `preprocessor_langchain` silently discards its entire chunk-size configuration — `_filter_kwargs_for` strips `**kwargs`-routed constructor parameters, so every pipeline chunks at LangChain library defaults (4000 chars / 200 overlap)

**Type:** Bug · **Severity:** High (silent configuration no-op affecting every text pipeline) · **Component:** `nodes/preprocessor_langchain`

**Affects:** `langchain.py` is **byte-identical at `server-v3.3.1` and current `HEAD` (`1138936`)** — unfixed at HEAD today. (Older tags not checked for this file.)

**Found by:** a benchmark harness whose source-derived chunk-size prediction (512) lost to its own record measurements (≈4000); the discrepancy was traced to this mechanism and reproduced.

## Summary

The node reads its chunking configuration correctly — `strlen` (default 512, and 512 in every
shipped profile), `mode`, `tokens` — and then loses ALL of it before the splitter is built.
`_getSplitter()` assembles `base_kwargs = dict(chunk_overlap=0, chunk_size=<strlen>,
length_function=<mode-aware>)` and passes them through `_filter_kwargs_for()`, which keeps only
kwargs **named in the target constructor's signature** (`langchain.py:96-99`):

```python
params = set(inspect.signature(cls.__init__).parameters.keys())
params.discard('self')
return {k: v for k, v in kwargs.items() if k in params}
```

LangChain's `RecursiveCharacterTextSplitter.__init__` names only `separators`,
`keep_separator`, `is_separator_regex` — `chunk_size`, `chunk_overlap` and `length_function`
are consumed by the `TextSplitter` base class via `**kwargs`. The filter therefore reduces the
engine's settings to `{}`, and the constructor runs at **LangChain's library defaults:
`chunk_size=4000, chunk_overlap=200`** — regardless of any value the operator configures.

## Operator-visible symptom

Configured values have **no effect and no warning is emitted**. The UI offers `strlen`
(default 512); output chunks are ~4000 characters with 200-character overlap. `tokens` mode is
doubly wrong: the token-aware length function is also dropped, so "512 tokens" silently
becomes "4000 characters" (the post-split `_split_safely_by_tokens` safety net still caps
model-limit overflow, but the configured chunk size is never honoured). The **only** knob that
survives the filter is `separators`.

## Affected splitter classes

- `RecursiveCharacterTextSplitter` — **executed and confirmed** (see reproduction).
- `CharacterTextSplitter`, `MarkdownTextSplitter`, `LatexTextSplitter`, `NLTKTextSplitter`,
  `SpacyTextSplitter` — **inferred, not executed**: the same LangChain `**kwargs` constructor
  shape applies; each named-parameter set excludes the size kwargs.

## Reproduction

```python
import inspect
from langchain_text_splitters import RecursiveCharacterTextSplitter
params = set(inspect.signature(RecursiveCharacterTextSplitter.__init__).parameters); params.discard('self')
base = dict(chunk_overlap=0, chunk_size=512, length_function=len)   # the engine's base_kwargs
filtered = {k: v for k, v in base.items() if k in params}           # the engine's filter
sp = RecursiveCharacterTextSplitter(**filtered)
print(filtered, sp._chunk_size, sp._chunk_overlap)                  # {} 4000 200
```

Confirmed on `langchain-text-splitters` **0.3.8 and 1.1.2** (both ends of the plausible
resolution range — the node's requirements leave the package unpinned, so any resolved version
in that range behaves identically).

## Evidence — production-scale records

19,080+ per-document records across two independent 10k-document benchmark runs and one
n=200 sequential run (engine 3.3.1, response documents read straight off the pipeline):
mean chunk length 3375–3468 characters, **maximum 3983–3993** — the 4000 ceiling with
separator losses — against a configured/profiled `strlen` of 512.

## Proposed fix

Filter against the **union of the MRO's constructor signatures** (the base `TextSplitter`
names `chunk_size`, `chunk_overlap`, `length_function` explicitly), or explicitly allowlist
those three; and **emit a warning naming any kwarg the filter drops** — a silently discarded
configuration value is the defect class here, independent of which kwargs it hits next.

## Acceptance criteria

1. A pipeline configured `strlen=512` produces no chunk longer than 512 characters.
2. `tokens` mode measures length with the token-aware function it configures.
3. Any constructor kwarg dropped by filtering produces a visible warning at pipeline load.

## Impact

Every RocketRide text pipeline using this node — the default RAG ingest path — chunks at
4000/200 no matter what the operator sets. Retrieval-granularity tuning silently no-ops;
any documentation or benchmark that states a configured chunk size for this node describes
values that were never in effect.


---

# TICKET 4 — Idle engine consumes one full CPU core continuously

**Title:** The engine burns ~1.0 core busy-waiting with zero pipelines loaded and zero work submitted — measured 1.002 cores by `/proc` stat delta on an otherwise idle host

**Type:** Performance · **Severity:** Medium (constant resource drain; measurement bias in any CPU-accounted deployment) · **Component:** engine core (attribution to eaas server vs task subprocess pending — see Open questions)

**Affects:** engine 3.3.1 (release binary, Linux x64), measured 2026-08-21. Not source-diffed across versions (the spin is in compiled code or the served python's event loop; the reproduction is behavioural).

## Summary

A freshly started engine container (`engine ai/eaas.py --host --port`, no `use()` issued, no
data submitted) consumes a steady **1.002 cores**. Measurement: host `/proc` stat delta over an
idle window on a box whose only other activity floors load1 at ~0; box load1 with the idle
engine present reads 1.00 flat. The container cgroup's `cpu.stat usage_usec` delta over the
same window attributes the burn to the engine's cgroup, not to any host process.

## Reproduction

```bash
docker run -d --name rr -p 5565:5565 <engine-3.3.1 image>   # boot, then wait for the listener
A=$(docker exec rr cat /sys/fs/cgroup/cpu.stat | awk '/usage_usec/{print $2}'); sleep 30
B=$(docker exec rr cat /sys/fs/cgroup/cpu.stat | awk '/usage_usec/{print $2}')
echo "idle cores: $(( (B - A) / 30 ))e-6"    # observed: ~1.002
```

## Impact — measured, not hypothetical

* **Deployment:** one core of every host running an idle or lightly-loaded engine is spent on
  nothing. On small instances this is a material fraction of capacity.
* **Benchmark bias, Phase 1 (PDF campaign):** the engine ran under `--cpuset-cpus 0-23`; the
  spin means RocketRide had **23 effective working cores against LlamaIndex's 24**, and every
  cgroup-CPU-based figure for the engine carried a constant ~one-core inflation — a bias
  **AGAINST RocketRide on both throughput and CPU-efficiency**, present in every leg.
* **Benchmark handling, Phase 2:** hygiene gates that bound host load had to move from absolute
  thresholds to excess-over-measured-baseline, because the system under test violates any
  absolute bound by existing.

## Open questions (deliberately left to the engine team rather than answered wrongly)

1. **Where is the spin?** Candidates: a polling loop in the C++ core, the embedded python
   server's event loop, or a timer with a zero/short period. Not attributed here.
2. **Does it scale with task subprocesses?** Each `use()` spawns an isolated task process; if
   each carries its own spin, an engine serving M pipelines idles at ~M cores. (The Phase 2
   harness measures idle cores as a function of token count; the number can be supplied on
   request once that sweep runs.)

## Acceptance criteria

1. An idle engine (booted, listening, zero pipelines) consumes < 0.05 cores sustained.
2. Idle consumption does not scale with the number of loaded-but-idle pipelines.


---

# TICKET 5 — Intra-op threads above the knee: constant work costs 40–50% more CPU, then steady-state wall collapses behind the detect device lock

**Type:** Performance / Architecture · **Severity:** Medium-High (the pathological region includes plausible default configurations; no guidance or clamp ships) · **Component:** `nodes/detect` under BLAS/OMP intra-op threading

**Affects:** engine 3.3.1 (patched build `rr:patched-video`; independent of Tickets 1 and 3). Measured 2026-08-21.

**Found by:** the Phase 2 video harness's per-thread-count probe; **reproduced in a second, fresh container the same day (Crossroad 24)** before this ticket was drafted.

## Summary

With the six BLAS/OMP variables (`OMP_NUM_THREADS` … `TORCH_NUM_THREADS`) set to 32 on a
32-vCPU host, a single-token engine processing a **byte-identical workload** (one video →
83 frames → 2,154 detections → 166 chunks, identical at every thread count):

1. **burns 40–50% more CPU-seconds than at 8 threads for the same work**, and then
2. **collapses to ~2.1× the wall time in steady state** (the send *after* first use of the
   loaded model), while still burning that CPU.

Detect inference is serialized by a per-process device lock, so intra-op threads are the
node's *only* parallelism — and past the knee they invert: more threads, more CPU, more wall.

## Measured — two independent runs, identical workload

Wall and `cpu.stat`-derived utilisation are per send; CPU-seconds = util × 32 × wall.
Send 1 = first use of the loaded model; send 2 = steady state. Same video, same 83/2,154/166
workload at every point (counts read back from the responses, not assumed).

| point | send 1 wall | send 2 wall | util (of 32) | send 1 CPU-s | send 2 CPU-s |
|---|---:|---:|---:|---:|---:|
| t1 | 85.3 s | 89.6 s | 0.072 | ≈197 | ≈206 |
| **t8** | **16.0 s** | **17.2 s** | 0.265 | ≈136 | **≈146** |
| t32, run 1 | 15.0 s | **35.9 s** | 0.4638 → 0.1805 | ≈223 | ≈207 |
| t32, run 2 (fresh container) | 16.2 s | **38.2 s** | 0.4683 → 0.1814 | ≈243 | ≈222 |

Two runs, same shape, same magnitude. The CPU-seconds framing is the point: **t32's steady
send does the identical work as t8's in ≈207–222 CPU-s against t8's ≈146 — 40–50% more CPU —
across 2.1× the wall.** Utilisation *fell* (0.46 → 0.18) while wall doubled: contention, not
work. Subtracting the constant ~1.0-core idle spin (Ticket 4) from every cell does not change
the shape — t32 steady remains ≈33–43% above t8 steady, and the send-1 gap widens.

## Mechanism — what is verified vs. left open

**Source-verified (pinned 3.3.1 tarball; a source trace, labeled as such):** detect inference
runs under a per-process device lock (`make_device_lock`, vision model base), so a task's
detections execute one frame at a time regardless of task-level concurrency; intra-op BLAS/OMP
threading inside each locked call is the only parallelism on this path. The engine ships **no
guidance, default, or clamp** for these variables on detect-bearing pipelines: they were set
explicitly on the container in these runs, and unset they fall to the BLAS/torch library
defaults — which on this host class resolve above the measured knee (a Phase-1 in-process
read-back on the same instance type measured unpinned torch at 16 intra-op threads).

**Deliberately left open rather than answered wrongly:**

1. Why send 1 escapes the regression in both runs (15–16 s at t32, comparable to t8) while
   every subsequent send pays 2.1× — allocator state, thread-pool re-spawn, and interop
   spin-wait growth are candidates; not attributed here.
2. Whether the task-level thread parameter (`use(threads=)`, default 64) interacts — these
   runs used the default.
3. Whether the library-default point (~16 on this host class) sits on the flat or the cliff —
   the sweep measured 1/8/32; 16 is untested.

## Reproduction

Baked 3.3.1 image, host networking, single token, any real video (~20 min of 25 fps footage
shows it clearly). Two sends minimum — **the regression only appears from send 2 onward**:

```bash
docker run -d --name rrprobe --memory 58g \
  -e OMP_NUM_THREADS=32 -e MKL_NUM_THREADS=32 -e OPENBLAS_NUM_THREADS=32 \
  -e VECLIB_MAXIMUM_THREADS=32 -e NUMEXPR_NUM_THREADS=32 -e TORCH_NUM_THREADS=32 \
  --network host rr:patched-video
# wait for readiness (a real SDK connect, not TCP), then send the same video twice
# through one pipeline token and read wall + cgroup cpu.stat per send.
# Harness form: working/video/probe/probe_rr.py --video <avi> --sends 2
```

Compare against the same commands with the six variables at 8: send 2 wall ≈17 s vs ≈36–38 s.

## Impact

* Operators who pin "all the cores" — or leave the variables unset on hosts where library
  defaults land high — pay ~40–50% extra CPU per unit of detect work and then lose ~2× wall in
  sustained operation, silently. Nothing in the engine warns that the detect path's lock makes
  intra-op threading past the knee strictly harmful.
* Benchmark handling: this harness sets the per-arm thread values from a measured sweep
  (knee = 8 on this host) and reads them back in-process per run; results published from this
  campaign do not include the pathological region on the RocketRide arm.

## Acceptance criteria

1. Documented intra-op threading guidance (or an engine-set default/clamp relative to
   available cores) for detect-bearing pipelines.
2. On the reference workload, no supported thread configuration shows steady-state wall
   > 1.5× first-use wall on constant per-send work — or the configuration is rejected/warned
   at pipeline load.
3. At the guidance configuration, steady-state CPU-seconds per unit work within 15% of the
   measured knee point.
