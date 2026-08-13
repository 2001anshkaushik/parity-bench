# Matched Layers — the topology asymmetry, and the shape a valid comparison must have

**Status: the memory and wall-clock comparisons are affected. The functional-equivalence result is
not.** This document states what each arm actually ran, sizes the confound, and specifies the shape
a re-run must have. No number below is withdrawn; the affected ones are marked in place.

---

## 1. What each arm actually ran [VERIFIED — from the code, two runners plus the ladder]

| | LlamaIndex arm | RocketRide arm |
| --- | --- | --- |
| transport | **none** — direct Python method call | **WebSocket + DAP** to `ws://127.0.0.1:5565` |
| serialization | **none** — Python objects returned in-process | JSON encode of input, JSON decode of `page_content` + 384-float `embedding` per chunk, **both directions** |
| process topology | **1 process** — the driver *is* the worker | **3 processes** — driver + engine parent + 1 task child |
| `working/ws1/service.py` | **NOT USED** | n/a — the engine is already the service |
| what `rss()` returns | `rss_mb()` — the driver, which contains the model | `engine_tree_rss_mb(pid) + rss_mb()` — engine tree **plus** driver |

**Evidence, not summary:**

* [`weekend_worker.py:148`](../weekend_worker.py) — `LlamaArm.__init__` does
  `from ws1.pipeline import LlamaIndexPipeline`, then `self.p.process(text)`. It imports the
  **pipeline class**, never the service. No socket, no uvicorn, no HTTP.
* [`weekend_worker.py:196`](../weekend_worker.py) — `RocketArm.__init__` does
  `from rocketride import RocketRideClient`, `connect()`, `use(filepath=...)`, then
  `self.c.send(tok, text, mimetype="text/plain")` per document.
* `engine/rocketride/core/transport_websocket.py:378` — `await websockets.connect(...)`;
  `core/transport.py:24` — *"Transport Base Classes for DAP Protocol Communication."*
* `matched_replication.py:171` builds the same two arms and starts uvicorn **zero** times
  (`grep -c 'run_service\|uvicorn\|ws1.service'` → 0).
* `docker/ladder.py:70` also imports `LlamaIndexPipeline` directly — 0 uvicorn hits. (The ladder is
  LlamaIndex-only; RocketRide has no `linux-arm64` build.)

**Confirmed:** LlamaIndex ran in-process with no HTTP while RocketRide ran the full client–server
path. The runners are otherwise scrupulously matched — same documents, same order, same chunking,
same model, same device, interleaved blocks, thread-parity gate — which is why this went unnoticed:
everything *inside* the comparison was controlled, and the uncontrolled variable was the shape of the
comparison itself.

**Live confirmation of the process topology** (measured this session, engine `pid=38379`, 12
documents, 0.25 s sampling): RocketRide child-process count constant at **1**, so 3 OS processes
total; LlamaIndex spawns no worker and its RSS goes 22.9 MB → 560.0 MB across `warm()`, i.e. the
model is loaded **into the driver**. This independently reproduces STATE.md M1 ("process count
constant at 2" — engine parent + 1 child, excluding the driver).

## 2. Size and direction of the confound

### 2.1 Memory — the repo already contains both directions, and they disagree

This is the finding that matters most, and it was already published without the two halves being
reconciled:

| comparison | LlamaIndex topology | RocketRide | LlamaIndex | verdict |
| --- | --- | ---: | ---: | --- |
| `memory_ceiling.json` — idle | uvicorn, **8 workers** | 204 MB | **4,642 MB** | LlamaIndex **22.8× worse** |
| `memory_ceiling.json` — 6,400 tok, conc 32 | uvicorn, **8 workers** | 2,356 MB | **7,950 MB** | LlamaIndex **3.4× worse** |
| matched replication — 2,000 docs | **in-process, 1 worker** | **2,065 MB** | 1,029 MB | RocketRide **2.0× worse** |

**Same two systems. Opposite verdicts. The only variable that changed is the LlamaIndex arm's
topology and worker count.** Neither number is a property of the frameworks; both are properties of
a deployment choice. That is the whole finding.

### 2.2 What RocketRide pays that LlamaIndex did not [VERIFIED — six-block decomposition, blocks 4–6]

| component | block 4 | block 5 | block 6 | LlamaIndex counterpart |
| --- | ---: | ---: | ---: | --- |
| engine process (parent) | 238.7 | 242.2 | 242.5 | **none — it ran no server at all** |
| task tree (1 child) | 1,568.6 | 1,551.0 | 1,538.2 | inside its single process |
| our driver | 267.3 | 303.2 | 319.0 | same process as the work |

The engine parent is **~240 MB of pure topology cost with no counterpart in the other arm** — 23 % of
LlamaIndex's *entire* footprint. RocketRide also pays three Python interpreter + library baselines
where LlamaIndex pays one.

### 2.3 Wall clock and per-request latency [PROVISIONAL — fails the 10 % variance gate]

Paired, interleaved, randomised order, identical 21,600-char document, n=4 per arm:

| arm | median | spread |
| --- | ---: | ---: |
| LlamaIndex (in-process) | 77.7 ms | 36.4 % |
| RocketRide (WebSocket + DAP) | 114.0 ms | 41.4 % |

**Direction only: RocketRide pays ~+36 ms per document for transport and serialization.** The spread
is 36–41 %, far outside the 10 % gate, so the point estimate is not reportable.

Noted with deliberate suspicion: +36.3 ms × 2,000 documents = **+72.6 s**, and the observed block
wall-clock difference is **+72.7 s** (883.4 s vs 810.7 s) — agreement to 1.00. **Treat that as
coincidence, not corroboration.** With n=4 and 40 % spread, agreement to three digits is luck; the
honest statement is that the observed wall-clock gap is *of the same order as* transport overhead
alone, and the transport-only explanation cannot yet be separated from "the engine is genuinely
slower per document". §7 specifies the experiment that separates them.

### 2.4 Direction of bias — rule 5 applied in reverse, as instructed

The hypothesis (asymmetry penalises RocketRide) is the one that must be attacked hardest. Ways it
could instead **flatter** RocketRide, each considered:

1. **"RocketRide's task tree holds more models."** *Refuted.* The tree is **one** child process
   holding **one** model, measured live. Its extra memory is genuinely a heavier single worker, not
   a multiplication. So a matched re-run will **shrink** the gap, not erase it.
2. **"LlamaIndex's single process suffers fragmentation from doing pypdf and embedding together,
   inflating it."** Plausible and would flatter RocketRide, but it is bounded by LlamaIndex's total
   (1,029 MB) and cannot account for a 1,036 MB difference. Small.
3. **"The 8-worker service figure is the fair one, so RocketRide is really 22.8× better."**
   *Rejected.* 8 workers × 1 model is a configuration choice, not a framework property — the same
   objection, in the opposite direction. `run_service.sh` in fact defaults to **14** workers
   (`WORKERS="${WS1_WORKERS:-14}"`), not the 8 the docs describe: a declared ≠ measured gap that
   makes the point — the number moves with a shell variable.
4. **"Fresh process per block resets LlamaIndex's memory while the engine persists."** Already
   disclosed in `MEETING_2026-08-10.md`; biases **against** RocketRide, not for it.

**Conclusion: the asymmetry biases against RocketRide on both memory and wall clock, and no
mechanism was found by which it flatters RocketRide.** The user's read is confirmed. But the
correction is *not* "RocketRide is actually better" — it is that **neither published memory ratio is
a framework property**, and the honest headline is the one in §2.1.

### 2.5 Hostile-reviewer questions, answered

* *"You changed the conclusion after seeing which way it went."* — No number is changed; §2.1 shows
  the repo already contained both directions before this analysis.
* *"Your latency n=4 with 40 % spread proves nothing."* — Correct, and it is labelled direction-only.
  It is used to establish *sign*, not magnitude.
* *"The 1.00 wall-clock agreement is too good."* — Agreed, and called out as coincidence in §2.3.
* *"Is functional equivalence affected?"* — No. Goodput, fault classes and the NUL defect are
  properties of the bytes returned, not of the transport carrying them. Both arms returned identical
  goodput every block *through these different topologies*, which if anything strengthens it.

## 3. The shape a valid comparison must have

The fix is **not** a FastAPI wrapper around RocketRide — the engine is already a service, and
wrapping it would double a layer that the other arm has once. The fix is driving LlamaIndex through
`working/ws1/service.py` over HTTP, so both arms are:

```
client  ->  network  ->  service  ->  worker process(es)
```

| stage | LlamaIndex (matched) | RocketRide (unchanged) |
| --- | --- | --- |
| client | `aiohttp` in the driver | `RocketRideClient` in the driver |
| network | HTTP/1.1 over loopback | WebSocket over loopback |
| service | uvicorn parent | engine parent |
| worker | uvicorn worker process | engine task process |
| accounting | uvicorn parent + workers + driver | engine parent + task tree + driver |

**Both arms must pay: a separate driver process, a serialization boundary, a server parent, and at
least one out-of-process worker.** The driver must do PDF parsing in both arms (it already does), so
parsing stays common-mode and cancels.

## 4. What stays different, and is irreducible

These cannot be equalised. They must be **stated in every result**, not silently absorbed:

| residual | size | why it cannot be removed |
| --- | --- | --- |
| **HTTP/1.1 vs WebSocket + DAP** | unquantified | Each system's native protocol. Forcing either onto the other's protocol would measure a shim we wrote, not the product. |
| **uvicorn workers vs engine task processes** | structural | Different parallelism models: uvicorn pre-forks fixed workers; the engine spawns a task tree per pipeline. There is no setting at which they are "the same". |
| **JSON payload shape** | ~0.04 MB/doc at 6 chunks | The two wire contracts differ. Same information, different envelopes. |
| **Model residency** | 1 model per uvicorn worker vs 1 per task process | Follows from the parallelism models above. |

**How to state them honestly:** every memory or latency number from the matched re-run must carry
the worker count and the concurrency alongside it — e.g. *"2,065 MB at 1 worker, concurrency 1"* —
never a bare ratio. A ratio without a topology is not a finding, which is precisely how the current
2.0× and 22.8× came to contradict each other.

## 5. The worker-count decision — justified, not inherited

`run_service.sh` defaults to **14** workers; the published 4,642 MB idle figure was taken at **8**.
Neither was chosen against RocketRide's behaviour, and 8 workers × one model each is what produces
4,642 MB before a single request arrives.

**Decision: match on *concurrent in-flight documents*, not on worker count**, because that is the
only quantity both architectures express.

| run | LlamaIndex | RocketRide | rationale |
| --- | --- | --- | --- |
| **primary — matched replication re-run** | uvicorn, **1 worker** | 1 task process (driver is synchronous) | The current driver sends one document at a time and waits. One in-flight document ⇒ one worker each. This is the like-for-like memory and wall-clock comparison. |
| **secondary — concurrency sweep** | workers = *C* | concurrency = *C*, engine spawns its own tree | Sweep *C* ∈ {1, 4, 8, 16}. Report each arm's curve; **do not** quote a single ratio. |

Rejected alternatives, with reasons:

* **8 or 14 workers vs 1 task process** — the current published comparison. Gives LlamaIndex 8–14
  models against RocketRide's one. This is what produced the 22.8× idle figure.
* **Match on CPU cores** — would set LlamaIndex to 14 workers and leave RocketRide's tree
  self-sized. Same defect.
* **Match on total memory budget** — circular: memory is the thing being measured.

RocketRide's *effective* concurrency width is ~17 against a declared pool (`SCHEMA_PROPOSAL.md`
§ pool width), so the sweep must not exceed 16 without re-establishing that width first.

## 6. What this does and does not invalidate

| claim | status |
| --- | --- |
| **Functional equivalence** — identical goodput every block, arms differ by exactly 7 docs per 2,000, all NUL truncation | **UNAFFECTED.** Transport does not change which bytes come back. |
| **NUL truncation defect** | **UNAFFECTED** — proven offline and in-pipeline, independent of topology. |
| **Thread-configuration lever (1.43× → 3.04×)** | **UNAFFECTED** — measured within each arm against itself. |
| **~150 concurrent pipelines livelock** | **UNAFFECTED** — a RocketRide-only property. |
| **Throughput unmeasurable on this host (2.2× order effect)** | **UNAFFECTED** — an order-of-measurement artifact in both arms. |
| **Memory ratio ~2.0×** | **AFFECTED — topology-confounded, biases against RocketRide.** |
| **LlamaIndex 4,642 MB idle / 7,950 MB peak** | **AFFECTED — topology-confounded, biases against LlamaIndex.** |
| **Wall-clock parity (+9 %)** | **AFFECTED — the entire gap is of the order of transport overhead.** |

## 5b. PRIMARY RESULT — matched layers at concurrency 1 [2026-08-11]

> ### ⚠️ MEASURED PARSER-OUT — needs re-baselining under Parser IN (scope change 2026-08-12)
> Every number in this section was measured with **PDF extraction in the driver**, common-mode to
> both arms and outside each arm's measured region. The team has since standardised on **Parser
> IN**: extraction moves inside each framework so the whole product is benchmarked (Tier 2 in
> [`PARSER_DECISION.md`](PARSER_DECISION.md), chosen deliberately over the Tier 1 framework
> comparison these numbers represent).
>
> **Parsing adds work to both arms, in directions not yet measured.** The engine now runs Tika 3.2.3
> in-process; the LlamaIndex service now runs pypdf inside its workers. Memory and wall clock will
> both move, and **the C ≈ 3.2 memory crossover in particular may move** — it sits between two
> quotable levels only 2 apart.
>
> **These numbers are NOT withdrawn and NOT overwritten.** They are a valid Tier 1 framework
> comparison. They are simply no longer the topology the team is measuring. Re-baseline before
> quoting alongside any Parser IN result, and never place the two in the same table.
>
> **Also changed:** goodput and fault counts now include parser behaviour, so they are not
> comparable with the counts below.

Both arms `client -> network -> service -> worker`. LlamaIndex now runs through `ws1/service.py`
over HTTP at **1 uvicorn worker**; RocketRide unchanged. Config gate passed with both arms measured
at **10 intra-op / 14 interop** threads, read from inside each worker process.

| block | RocketRide RSS | wall | LlamaIndex-HTTP RSS | wall |
| --- | ---: | ---: | ---: | ---: |
| b0 | 2,001.3 MB | 1,119.9 s | 1,162.1 MB | 892.9 s |
| b1 | 2,163.1 MB | 819.8 s | 1,202.4 MB | 794.4 s |
| b2 | 2,158.9 MB | 805.3 s | 1,205.0 MB | 796.3 s |

**Functional equivalence, unchanged by the transport [VERIFIED]:** goodput **1,965 / 1,965 / 1,965**
(RocketRide) and **1,972 / 1,972 / 1,972** (LlamaIndex), faults **35** and **28**, identical in every
block — and identical to the original in-process run. Routing LlamaIndex through HTTP changed which
bytes come back not at all, which is what the earlier claim predicted.

### The headline numbers

| | in-process (original) | **matched layers** | gate |
| --- | ---: | ---: | --- |
| memory ratio RR/LI | 2.01× | **1.80×** | PASS (both arms ≤ 7.5 % over 3 blocks) |
| wall ratio RR/LI | 1.09× | **1.03×** | see below |

**Memory: 2.01× → 1.80×** [VERIFIED — 3 blocks, interleaved, randomised, gate passed]. Giving
LlamaIndex the same shape closes about a fifth of the gap. It does **not** close it: RocketRide is
still the heavier arm at concurrency 1, and §2.4's refuted objection is why — its task tree is one
process holding one model, so the excess is a genuinely heavier worker, not a multiplication.

**Wall: 1.09× → 1.03×** — effectively parity once LlamaIndex pays transport too. [PROVISIONAL, see
the warm-up caveat below.]

### Block 0 is warm-up at the BLOCK level — on both arms

| arm | all 3 blocks | first block excluded |
| --- | --- | --- |
| RocketRide wall | spread **38.4 %** — FAIL | spread **1.79 %** — PASS |
| LlamaIndex wall | spread **12.4 %** — FAIL | spread **0.24 %** — PASS |
| RocketRide memory | 7.49 % — PASS | 0.19 % — PASS |
| LlamaIndex memory | 3.57 % — PASS | 0.22 % — PASS |

The first block of each arm is 12–38 % slower than the two that follow, and the two that follow
agree to **0.24 %** and **1.79 %**. **The existing 50-document warm-up does not cover this** — the
effect is at block scale, and it is the single largest source of apparent instability on this host.
Excluding it, wall clock is not merely gate-passing but among the tightest measurements in this
project.

The ratios are unaffected either way (median is robust to one outlier): memory 1.80× both ways,
wall 1.03× all-three vs 1.02× excluding warm-up.

### Rule 5 — the gap shrank, which favours RocketRide, so the hunt was for artifacts that shrink it unfairly

**Candidate: summing RSS across forked uvicorn workers double-counts copy-on-write shared pages**,
inflating LlamaIndex and flattering RocketRide. Tested against the idle measurements: per-worker cost
is **592.8 → 579.9 → 578.2 MB** at 1, 8 and 14 workers — a 2.5 % decline across a 14× increase in
worker count. If sharing were material this would fall steeply; it does not, so each worker holds its
own copy and the sum is not meaningfully double-counting. [VERIFIED at idle; re-checked per cell in
the sweep, where the stakes are higher.]

**Known bias in the other direction, disclosed not corrected:** the LlamaIndex service stays warm
across the whole run (it is a service), while RocketRide's model-holding task process is torn down
between blocks. Measured: **854.7 MB** of LlamaIndex sits resident during RocketRide's blocks versus
**178.4 MB** of engine during LlamaIndex's — ~677 MB of asymmetric host pressure, **against
RocketRide**. Correcting it would move the ratio further in RocketRide's favour, so 1.80× is
conservative.

**Hostile reviewer:** *"n=2 after you discard block 0, and your own gate demands n≥3."* Correct — the
warm-up exclusion is labelled **PROVISIONAL** for that reason. The memory ratio does not depend on it
(it passes at n=3 including block 0); only the wall-clock gate does.

## 5c. THE CURVE — concurrency sweep, and the crossover [2026-08-11]

> ### ⚠️ MEASURED PARSER-OUT — needs re-baselining under Parser IN (scope change 2026-08-12)
> Every number in this section was measured with **PDF extraction in the driver**, common-mode to
> both arms and outside each arm's measured region. The team has since standardised on **Parser
> IN**: extraction moves inside each framework so the whole product is benchmarked (Tier 2 in
> [`PARSER_DECISION.md`](PARSER_DECISION.md), chosen deliberately over the Tier 1 framework
> comparison these numbers represent).
>
> **Parsing adds work to both arms, in directions not yet measured.** The engine now runs Tika 3.2.3
> in-process; the LlamaIndex service now runs pypdf inside its workers. Memory and wall clock will
> both move, and **the C ≈ 3.2 memory crossover in particular may move** — it sits between two
> quotable levels only 2 apart.
>
> **These numbers are NOT withdrawn and NOT overwritten.** They are a valid Tier 1 framework
> comparison. They are simply no longer the topology the team is measuring. Re-baseline before
> quoting alongside any Parser IN result, and never place the two in the same table.
>
> **Also changed:** goodput and fault counts now include parser behaviour, so they are not
> comparable with the counts below.

Pre-registered in [`PREREGISTRATION.md`](PREREGISTRATION.md) **before this ran**. 15 cells,
C ∈ {1,2,4,8,16} × n=3 × 500 documents, levels in randomised order, one service cold start per
level, achieved concurrency measured (never assumed), swap and compressor state recorded at the
start, middle and end of every cell.

| C | LlamaIndex | spread | RocketRide | spread | ratio RR/LI | RR task procs | RR task tree | LI compression | verdict |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1,131.2 MB | 5.3 % | 2,208.5 MB | 5.6 % | **1.952** | 1 | 1,598.5 | −0.0 % | **QUOTABLE** |
| 2 | 1,902.7 MB | 9.5 % | 2,587.6 MB | 4.6 % | **1.360** | 1 | 2,027.3 | −0.1 % | **QUOTABLE** |
| 4 | 3,405.6 MB | 4.3 % | 2,911.1 MB | 7.2 % | **0.855** | 1 | 2,319.4 | −0.0 % | **QUOTABLE** |
| 8 | 6,589.0 MB | **17.5 %** | 3,429.1 MB | 3.6 % | 0.520 | 1 | 2,828.2 | −0.1 % | gate FAIL |
| 16 | 7,703.6 MB | **57.0 %** | 4,043.4 MB | 3.7 % | 0.525 | 1 | 3,468.6 | **+66.2 %** | compressed |

Achieved concurrency reached offered in **every cell**; no cell was VOID on that criterion.

### The crossover [VERIFIED — both bracketing levels quotable]

**Measured C ≈ 3.2** (log-log interpolation between C=2 at 1.360 and C=4 at 0.855). The registered
prediction was **~C=3**. **Confirmed, and it falls inside the quotable range** — it rests on two
gate-passing, compression-clean levels, not on the compromised top of the curve.

Below C≈3 LlamaIndex is the lighter arm; above it RocketRide is, and the gap widens.

### The mechanism — and the registered falsifier DID fire

| | predicted | measured |
| --- | --- | --- |
| RocketRide **task process count** | flat | **flat at 1**, C=1 → C=16, with up to 16 documents genuinely in flight |
| RocketRide **task-tree memory** | flat | **1,598 → 3,469 MB, +117 %** |

`PREREGISTRATION.md` §5: *"FALSIFIED IF RocketRide's task-tree memory grows with C rather than
staying flat."* **It grows. That half of the prediction is falsified.**

Fitting memory ∝ C^k on the three quotable levels:

* **LlamaIndex k = 0.80** — close to linear in workers, as predicted
* **RocketRide k = 0.20** — clearly not flat (k=0), but strongly sub-linear

**So the crossover is real and lands where predicted, but for the wrong reason.** It exists because
LlamaIndex grows *faster*, not because RocketRide stays flat. Two errors in the registered arithmetic
partly cancelled: RocketRide's baseline was higher than assumed **and** it grows, while LlamaIndex's
per-worker cost under load (~700 MB) exceeds the 579 MB idle figure the prediction used. A correct
prediction from a wrong model is not a vindication of the model, and the practical consequence
differs: "flat" would have implied unlimited concurrency at fixed cost; **k=0.20 sets a real, if
distant, ceiling.**

Structurally, the Model B pooling claim **does** transfer from `probe_minimal.pipe` to the real
embedding pipeline: one task process absorbed 16 concurrent documents. It just is not free.

### Why C=8 and C=16 are not quotable — two different failures

* **C=16 — compressor, not swap.** Compressed pages rose **+66.2 % (+5.50 GB)** during the first
  cell. Compressed pages are absent from RSS exactly as swapped pages are, so the arm's measured RSS
  understates its working set. The tell: per-process LlamaIndex memory **fell below its own idle
  value** (453 vs 540 MB/proc) — a loaded worker cannot need less than an idle one. Swapouts were
  zero throughout, so a swap-only gate passes this cell; the compressor gate is what catches it.
  **This is the "LlamaIndex at 16 workers does not fit on this host" result**, arriving through the
  compressor.
* **C=8 — genuine drift, no compression.** LlamaIndex rose monotonically **6,432 → 6,589 → 7,584 MB
  across successive reps against one warm service** (+18 %), with compression flat at −0.05 % to
  −0.34 %. That is real growth, not an artifact. [**PROVISIONAL** — n=3 within a single service
  instance; allocator high-water behaviour that would plateau is not excluded from unbounded growth.]

**RocketRide passes its gate at every level** (3.6–7.2 %) and shows neither pathology.

Direction survives at both levels even though magnitude does not: RocketRide is lighter in all six
cells, and at C=16 the true LlamaIndex figure is *higher* than any measured value, so the real gap is
larger than 0.525 rather than smaller.

### Reconciliation of the two previously published numbers

**The 2.01× IS explained.** It sits at **C=1** on this curve, where the matched measurement gives
**1.952×** (sweep) and **1.795×** (primary). The topology confound was real but small; most of the
original 2× was simply the concurrency-1 operating point.

**The 22.8× is NOT explained by this curve, and that gap is itself the finding.** It compared
LlamaIndex idle at 8 workers (**4,642 MB**, eight models eagerly loaded at startup) against
RocketRide idle (**204 MB**, engine parent holding **no task and no model**). Those are not the same
state. It is not a point on this curve at any C, because it never measured concurrency at all — it
measured **eager versus lazy model residency**:

* **LlamaIndex pre-loads a model per worker at startup**, so it pays for capacity before any request
  arrives, and its floor is set by worker count.
* **RocketRide loads on task creation**, so an idle engine holds almost nothing, and its cost tracks
  work in flight.

That is a genuine and useful architectural difference — it is the right answer to *"what does an idle
deployment cost?"* — but it was published as though it answered *"which framework uses less memory?"*,
which it does not. Under matched load below C≈3 the answer is the opposite.

## 6b. `run_service.sh` has been broken since the restructure [VERIFIED]

**No clone of this repository could start the LlamaIndex service.** `run_service.sh` computed its
interpreter as `$ROOT/../.venv/bin/python` where `ROOT` is the directory *above* `ws1/`. That was
correct while `ws1/` sat at the clone root. When the tree was restructured into `working/ws1/`,
`ROOT` became `working/`, so the path resolved to `<clone>/.venv` — but the venv lives one level
above the clone (`PROVISIONING.md` §4). Nothing sets `WS1_PYTHON`, so every caller died at launch
with:

```
run_service.sh: line 23: .../working/../.venv/bin/python: No such file or directory
```

**Dating it:**

| | |
| --- | --- |
| last service-dependent result in the repo | `f_sustained_decay.json`, **2026-08-07 11:56** |
| every other service-mode result | 2026-08-05 → 2026-08-07, all earlier |
| initial git import, already in the broken `working/` layout | **2026-08-10 16:57** |
| fixed | 2026-08-11 |

**So every service-mode number in this repo — including the 4,642 MB idle figure and the whole
`memory_ceiling.json` table — was produced before the restructure, and none of them could be
reproduced from any committed state of the repo until today.** The results are not wrong; they are
simply not reachable by the instructions the repo ships. That is why this was invisible: nothing
after 2026-08-07 needed the service, because the in-process arm had replaced it.

Fixed to `$ROOT/../../.venv/bin/python`, plus an explicit `[ -x "$PY" ]` guard so a wrong path fails
with a named error instead of a shell "No such file or directory" at line 23.

## 7. Re-run cost — NOT YET RUN

**What must be built first:** a `LlamaHttpArm` in `weekend_worker.py` that drives
`working/ws1/service.py` over HTTP with the same `process(text) -> (chunks, embeddings)` contract as
the existing arms, and an `rss()` that sums **uvicorn parent + workers + driver** (mirroring
`engine_tree_rss_mb(pid) + rss_mb()`). The service must be started by the runner, warm-gated on one
`warm in` line per worker (not `/health` — §7 of `BENCHMARK_SETUP.md`), and torn down per block. The
existing thread-parity config gate must be extended to the new arm.

**Cost, derived from measured block times — not estimated:**

| run | shape | per block | total |
| --- | --- | ---: | ---: |
| dry run | `--docs 10 --blocks 2` | — | **~10 min** |
| **primary** — matched replication, 1 worker each | 3 blocks × 2 arms, interleaved | RR 883 s (measured) · LI-over-HTTP ~883 s (projected) | **~1.5 h** |
| **secondary** — concurrency sweep | *C* ∈ {1, 4, 8, 16}, 500 docs/cell, n≥3 | ~200 s/cell | **~1.5 h** |
| | | | **~3 h total** |

The LlamaIndex-over-HTTP block time is **projected**, using the direction-only +36 ms/document from
§2.3. If HTTP/1.1 is materially more expensive than WebSocket + DAP the primary run is longer; the
dry run will show it before the full run commits.

**What the primary run settles:** whether the ~2.0× memory ratio survives when both arms carry a
server parent and an out-of-process worker, and whether the +9 % wall-clock gap closes when
LlamaIndex pays transport too. **That is the experiment that separates "transport cost" from "the
engine is genuinely slower per document"** — the two explanations §2.3 could not distinguish.

**What the secondary run settles:** the shape of each arm's memory curve against concurrency, which
is the only honest way to present a comparison whose current answer moves by 22.8× in one direction
and 2.0× in the other depending on a worker count.
