# Pre-registration — matched-layer concurrency sweep

**Written before the sweep was run, and before the sweep script existed in its final form.** The
point is that the interpretation cannot be retrofitted to whatever curve comes back. Registered
2026-08-11, against engine `3.3.1.35` / `pid 38379`.

Git provenance: this file is committed **before** any `matched_layers_sweep` result file exists. If
a result file predates this commit, the registration is void and must be treated as a post-hoc story.

---

## 1. The prediction, as registered

| quantity | predicted behaviour |
| --- | --- |
| **LlamaIndex memory** | ~**579 MB × workers**, linear in *C* |
| **RocketRide memory** | ~**240 MB** engine parent + ~**1,568 MB** task tree, **FLAT in *C*** |
| **Crossover** | ~**C = 3** (579·C = 1,808 ⇒ C = 3.12) |
| **Below crossover** | LlamaIndex lighter |
| **Above crossover** | RocketRide lighter, and the gap widens linearly in *C* |

**Reconciliation this predicts:** the 22.8× figure was RocketRide *idle* against 8 pre-loaded
workers; the 2.0× figure was C = 1, below the crossover. Both are points on one curve.

### FALSIFIED IF

**RocketRide's task-tree memory grows with *C* rather than staying flat.** This is the load-bearing
assumption and the sweep must test it directly, by measuring the task **process count** per cell —
not the total. A flat total cannot distinguish "flat because the engine pools" from "flat because
the workload never created pressure".

## 2. The basis for the flatness assumption — checked, and weaker than it looks

The prediction cites "the Model B finding: process count constant 100 → 20,000 concurrent". Two
things must be recorded honestly **before** the run:

**What is actually in the data** (`working/results/process_scaling/model_b_ceiling.json`): with one
pipeline and N concurrent `send()` calls, `node_procs` is **constant at 1** across every level from
100 to 20,000, and engine RSS moves only 91.1 → 96.8 MB. So the flat-process-count claim is real and
reproducible **for that experiment**. [VERIFIED for that workload]

**Why it may not transfer** — the caveat that makes this a prediction rather than a known result:

1. Model B drove `pipes/probe_minimal.pipe`, **not** the 4-node embed pipeline. It does essentially
   no work per request.
2. Its payloads were the strings `item-0 … item-N`, not documents.
3. Its rows report `wall_s: 0.042` for 100 requests — ~2,385 req/s, about **1,000× cheaper per
   request** than the embedding pipeline's measured ~2.4 docs/s.
4. A neighbouring claim from the same family — "RocketRide ~2,600/s flat from n=100 to 20,000" — is
   already marked **SUPERSEDED** in `STATE.md` §5: it was **client-bound, not engine-bound**. The
   flatness there was an artifact of a single-process driver, not a property of the engine.

**So the registered prediction extrapolates flat pooling from a no-op pipeline to a
model-loading, CPU-bound one.** That extrapolation is exactly what is being tested. Point 4 is the
specific reason to distrust it: the last time something looked flat across this concurrency range,
the flatness belonged to the instrument.

**Separately measured and NOT in doubt** (this session, `n=3`, spread ≤ 0.6 %): LlamaIndex idle is
linear in workers — 1 w = 592.8 MB, 8 w = 4,639.1 MB, 14 w = 8,094.4 MB, i.e. ~579 MB/worker. The
LlamaIndex half of the prediction is already [VERIFIED] at idle; the sweep tests it under load.

## 3. Design that tests it

**Matching rule: concurrent in-flight documents** — the only quantity both architectures express.

| | LlamaIndex | RocketRide |
| --- | --- | --- |
| shape | *C* uvicorn workers, *C* concurrent POSTs | **one pipeline, *C* concurrent `send()` calls** |
| rationale | its parallelism is processes | Model B's shape, so the prediction is tested on its own terms |

**RocketRide must be driven as one pipeline with *C* in-flight sends, not as *C* separate
pipelines.** Driving *C* separate pipelines would force *C* task processes **by construction** and
would falsify the flatness prediction through the harness's own design choice rather than through
the engine's behaviour. That would be an instrument artifact of exactly the kind this project keeps
producing.

**Grid:** C ∈ {1, 2, 4, 8, 16} — C = 2 included because the predicted crossover sits between 2 and
4. 500 documents per cell, n ≥ 3, pre-warmed, first 50 documents discarded, 10 % gate per cell,
concurrency levels in randomised order.

**Per-cell decomposition (the counts are the test, not the totals):**

* RocketRide — engine parent RSS, task-tree RSS, **task process count**, driver RSS
* LlamaIndex — uvicorn parent RSS, per-worker RSS, **worker count**, driver RSS

## 4. Rule 5 — this prediction favours RocketRide at high *C*, so the artifacts to hunt are the ones that would fake a flat curve

Registered in advance, so that finding them later is not presented as diligence after the fact:

| artifact that would spuriously flatten RocketRide | how the sweep detects it |
| --- | --- |
| **Requests queue instead of running concurrently.** If the engine serialises the *C* sends, memory stays flat because only one document is ever in flight | Track **achieved** in-flight concurrency continuously, not offered. Report max and median observed in-flight. If achieved ≈ 1 while offered = 16, the flatness is meaningless |
| **The driver is the bottleneck** — the exact defect that superseded the 2,600/s claim | Compare per-cell throughput against *C*. If throughput is flat in *C* for **both** arms, suspect the driver, not the engines |
| **The service never receives *C* concurrent requests** | Same achieved-concurrency instrument on the HTTP arm; a per-worker RSS spread of zero at C > 1 means only one worker ever worked |
| **The workload is too small to create pressure** — Model B's own weakness | 500 real documents per cell through the full embed pipeline, and report task-tree RSS alongside the count |
| **Sampling misses the peak** | Continuous 0.25 s sampling; a between-cell sample understates peaks ~4.8× on this host |

**If achieved concurrency does not reach offered concurrency, the cell is reported as such and its
ratio is not quoted.** A flat curve obtained by not actually being concurrent would confirm the
prediction for the wrong reason, which is worse than falsifying it.

## 5. What would count as each outcome

* **Confirmed:** RocketRide task-process count and task-tree RSS flat in *C*, achieved concurrency
  reaches offered, crossover observed near C = 3.
* **Falsified:** task-tree RSS rises with *C* (process count rising is the mechanism; RSS rising at
  constant count is a different, also-falsifying mechanism worth naming separately).
* **Void:** achieved concurrency does not track offered, or throughput is flat in *C* for both arms
  (driver-bound). In that case the sweep measures the harness and must be rebuilt before any curve
  is published.
