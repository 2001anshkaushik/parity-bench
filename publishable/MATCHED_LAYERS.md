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
