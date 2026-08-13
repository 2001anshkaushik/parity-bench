# WS-1 reconciliation against the team benchmark specification

**Ansh · 2026-08-13.** Response to Leela's *LangGraph vs RocketRide Benchmark Specification*, now the
team standard. Engine pinned to **3.3.1 + SDK 1.3.0** (our pairing, the only manifest-correct one);
Leela and Shashi are upgrading, and Shashi is dropping Qdrant/RAG for the shared ingest shape.

> ### ⚠️ I do not have the specification document
> It is not in `bench_langgraph_prod@b9b4736` — the only commit on the only branch — and no newer
> commit exists. **Everything below is reconciled against the item list as relayed to me, not
> against the document.** Where I could not assess an item without it, I say so rather than guess.
> Please send the doc (or a link) and I will redo the affected rows.

---

## 1. Gap table

**Legend:** HAVE = implemented and exercised · PARTIAL = exists but not in the spec's shape ·
MISSING = not built.

| spec item | status | detail | cost to close |
| --- | --- | --- | --- |
| **M0–M7 measurements** | **CANNOT ASSESS** | I have the labels, not the definitions. Our current measurement set is memory (median RSS, gated), wall clock (gated, first block excluded), goodput, fault classes by type, and explicitly **no throughput** — this host swings 2.2× on measurement order alone. | unknown until I see the definitions |
| **Setup probe (10 docs)** | **HAVE — built this session** | `working/scripts/setup_probe.py`: environment manifest, in-process thread parity on both arms, 10-document correctness pass, determinism re-run. Gates with a non-zero exit. **Field list is inferred** — please diff against yours. | done; field list may need edits |
| **Environment manifest** | **HAVE** | engine version + **binary sha256** (adopted from Shashi — a tag is mutable, a hash is not), SDK, library versions read from the live venv, host, python, splitter config read back off the object | done |
| **Determinism re-run** | **HAVE** | same 10 documents twice, chunk hashes compared | done |
| **Pinned equalities** (model, device, chunking) | **HAVE, all verified not declared** | model `multi-qa-MiniLM-L6-cos-v1` 384-d CPU; device read off loaded parameters with a **refuse-to-start** on mismatch; chunking 4000/200 read back from the splitter object | done |
| **Parser IN** | **HAVE** | RocketRide: stock 5-node `webhook → parse → preprocessor_langchain → embedding_transformer → response_documents`, your lane wiring (`tags`). LlamaIndex: `/process_pdf` takes raw bytes, parses with pypdf in-worker | done |
| **Closed-loop driving** | **HAVE** | C in-flight, held; **achieved concurrency measured per cell**, cells short of offered are marked and not quoted | done |
| **Concurrency ladder to 32** | **PARTIAL** | ours runs {1,2,4,8,16} with n=3 and per-cell gating. Extending to 32 is a parameter change. **But see §3(b) — 32 may not be measurable on RocketRide.** | ~1 h run time |
| **300 s timeout** | **PARTIAL** | ours is 1800 s per document. Tightening to 300 s is one constant — but our observed engine stalls sat at exactly 300 s and one ran 31 consecutive timeouts, so this changes what gets *recorded* as a fault | trivial change, needs a fault-taxonomy decision |
| **Census identity** (`offered = successful + expected + unexpected`) | **MISSING** | we count goodput and fault classes but do not assert the identity closes. This is a good check and I want it — it catches silently dropped documents, which is a failure mode we have hit | ~2 h: needs a fault taxonomy that partitions cleanly (see §3 and the asymmetry below) |
| **Per-arm parse gate** | **HAVE, with a proposed change** | `harness/chunk_hash.py` per-arm + `harness/tika_reference.py` (independent Tika reference, verified byte-exact 8/8). See `PROPOSAL_PARSE_GATE.md` — the §4.3 self-capture reference cannot fail on a deterministic defect, demonstrated on our NUL case | done our side; needs your decision |
| **Corpus + per-file sha256 manifest** | **MISSING** | we use GovDocs1 10k with a fetch script and no per-file manifest. **Both Leela and Shashi have one; we are the weakest of the three here.** | ~1 h |

### What we have that the spec does not require — and should keep

Four instruments that each caught a real defect here. I would argue for all of them going into the
shared standard, but they are ours to justify:

1. **Achieved-vs-offered concurrency, measured per cell.** A flat curve obtained by not actually
   being concurrent would confirm a hypothesis for the wrong reason. Our sweep verified achieved =
   offered in every cell; without it the numbers would have been unfalsifiable.
2. **A variance gate that refuses n=1.** A single measurement has zero spread by construction. A
   gate that cannot fail is worse than no gate.
3. **In-process thread verification with a config gate that refuses to run.** We added it *after* a
   full 10,000-document comparison ran with one arm on 1 thread and the other on 10 and nothing
   detected it. An exported variable proves nothing — torch caches its thread count at import.
4. **Result-file collision protection.** `<name>__<UTC>__<payload-hash>.json` with `O_EXCL`. Three
   scripts once wrote to the same path and the third silently overwrote the first two.

## 2. The warm-up scale question

The spec (via Shashi) proposes **25 warm-up documents per run**. **Measured: 25 is enough for
RocketRide and not enough for LlamaIndex.**

**First attempt was wrong and is reported here because the error matters.** I timed 400 consecutive
corpus documents and looked for convergence by document index. It showed no convergence and an early
band *faster* than steady state — because GovDocs1 document sizes span **2018×** (4,521 → 9,122,928
bytes) and per-band median size tracks per-band latency almost exactly (47 KB → 87 ms, 552 KB →
335 ms, 115 KB → 127 ms). **That measurement varied document size and document index together; it
measured size.** No convergence index from it is usable.

**Corrected design: one fixture document, repeated 200×, size held constant, so any trend is
warm-up.** Fixture `000_000010.pdf` (120,441 bytes).

| reps | LlamaIndex | × steady | RocketRide | × steady |
| --- | ---: | ---: | ---: | ---: |
| 0 (first request) | 139.4 ms | **1.61×** | 327.1 ms | **4.04×** |
| 1–5 | 98.7 | 1.14× | 110.5 | 1.37× |
| 5–10 | 98.6 | 1.14× | 100.6 | 1.24× |
| 10–25 | 98.5 | 1.14× | 86.1 | 1.06× |
| 25–50 | 93.4 | **1.08×** | 85.4 | 1.05× |
| 50–100 | 92.7 | 1.07× | 80.1 | 0.99× |
| 100–200 | 86.4 | 1.00× | 81.0 | 1.00× |

* **RocketRide** pays a large first-request cost (**4.04×**) that decays fast: within 6 % of steady
  by rep 10, within 5 % by rep 25. **25 warm-up documents is adequate.**
* **LlamaIndex** decays *slowly*: still **1.08× at reps 25–50** and 1.07 % at 50–100, reaching steady
  only after ~rep 100. Strict criterion (20 consecutive reps within 10 %) first satisfied at index
  **96**. **25 warm-up documents leaves roughly 8 % inflation on this arm.**

**Recommendation: 100 warm-up documents, not 25** — set by the slower-converging arm, since a shared
warm-up must satisfy both. The cost is ~100 documents per run; the benefit is removing an 8 % bias
from one arm and not the other, which is exactly the kind of asymmetry that becomes a false finding.

[**PROVISIONAL** — one fixture document, one host, n=1 per rep. The strict-convergence criterion
returned `None` for RocketRide because occasional spikes defeat a 20-consecutive test; the banded
medians are the robust read and they are what the recommendation rests on.]

**This does not explain the block-level effect.** Request-level warm-up converges in ~100 requests;
the 12–38 % gap between block 0 and blocks 1–2 spans 2,000-document blocks. Different scale,
probably a different mechanism (thermal state, page cache). **Not separated** — a block-level
exclusion is still needed on top of the document-level warm-up.

What we already knew going in: **block 0 runs 12–38 % slower than blocks 1–2 on both arms, with a
50-document warm-up already applied.** Excluding block 0 entirely, wall-clock spread drops to 0.24 %
(LlamaIndex) and 1.79 % (RocketRide); including it, both arms fail a 10 % gate. So the effect
survives a 50-document discard, which is twice what the spec proposes.

## 3. Three conflicts, with evidence

### (a) M6 is Lines of Code — the Aug 4 exec review asked for something else

The **2026-08-04 exec review** killed LOC as a metric and asked for **total technical overhead**
instead. `benchmark-A` was retired as a workstream in the same review (recorded in `STATE.md` §14 and
`archive/docs/FINDINGS_FOR_WS1.md`).

LOC is a poor proxy: it counts a verbose-but-declarative pipe file the same as dense imperative
code, and it does not count the work that actually hurt. On our side the expensive parts were **not
lines**: a custom node written to work around silently-dropped splitter kwargs, a dependency
hand-copied into an embedded interpreter with no supported install path, and a lane wiring that
contradicts its own README.

**Proposal:** keep a size measure if the room wants one, but report it **split four ways** —
pipeline definition, framework glue, workarounds-for-defects, and harness — and complement it with
our **toil instrument** (`TOIL_INSTRUMENT.md`), which records each obstacle, the time it cost, and
whether a supported path existed. Four-way split plus toil answers "total technical overhead"; a raw
count does not. **This is a proposal, not a refusal** — if the room wants LOC, we will produce it,
labelled for what it is.

### (b) The ladder runs to 32; RocketRide's measured pool width is 17.24

**VERIFIED, two methods, on macOS:** RocketRide's effective concurrency width is **17.24**
(hold-and-divide, confirmed by doubling). Above that, additional offered concurrency does not
produce additional in-flight work on the engine.

Two consequences, and I want to be careful about the first:

* **17.24 was measured on this laptop and must be RE-MEASURED on the 32-vCPU Linux box before anyone
  assumes it transfers.** Pool width plausibly scales with cores, and Leela separately observed a
  ~4-slot admission ceiling under burst on her setup — we cannot reconcile those two numbers today
  (different engine version, emulation, CPU budget). Treat 17.24 as a macOS number until re-measured.
* **If it holds near ~17**, ladder cells above it measure the other framework against a saturated
  engine. Those cells are still worth running — saturation behaviour is a real product property —
  but they must be **labelled as past-saturation**, not read as a scaling comparison.

**Proposal:** run the full ladder to 32, and re-measure pool width as its own step on the new host
first. Label every cell above the measured width.

### (c) Closed-loop vs blast-all — two questions, one table

Leela's spec locks **closed-loop** (hold C in flight). Shashi's note asks for **blast-all and
sequential**. These are not competing implementations of one measurement; they answer different
questions:

| driving | question it answers | what it measures |
| --- | --- | --- |
| closed-loop, C held | steady-state behaviour at a known concurrency | service capability at C |
| blast-all (open loop) | what happens when a queue arrives at once | queueing + admission control |
| sequential | per-document cost with no contention | clean latency baseline |

Leela's own PDF-1K numbers illustrate the hazard: her burst latency percentiles **explicitly include
queueing** (`"note": "includes queueing (open-loop burst)"`), so a p50 from a burst run and a p50
from a closed-loop run are different quantities with the same name.

**Proposal:** run all three, and **never put them in one table**. Report as three labelled sections
with the driving mode in the section title, and forbid a bare "latency" or "throughput" column that
does not carry its driving mode. If a single headline is needed, take it from closed-loop, which is
the only one of the three that has a defined operating point.

## 4. What I need from the team

1. **The specification document** — I have reconciled against a relayed item list.
2. **A decision on the parse gate reference** (`PROPOSAL_PARSE_GATE.md`).
3. **M0–M7 definitions** so I can fill the top row of the gap table.
4. **Whether the census identity's fault taxonomy is symmetric across arms.** Ours is not yet:
   LlamaIndex returns typed error classes (`parse_failed`, `empty_extraction`, `malformed_input`)
   while RocketRide signals failure by returning an **empty document list with no class**. Worse,
   the engine **does not reject non-PDF input** — 47 bytes of plain ASCII sent as
   `application/pdf` came back as **one successful chunk**, where LlamaIndex returned
   `parse_failed`. Until that is resolved, `offered = successful + expected + unexpected` will close
   on both arms while meaning different things.
