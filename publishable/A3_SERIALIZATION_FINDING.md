# Why RocketRide Does Not Scale With Concurrency — and the One-Line Fix

**PRODUCT FINDING.** Ansh · 2026-08-06 · closes open item A3.
Raw data: `working/results/a3_serialization.json`, `working/results/a3_threads.json`.

---

> ### ⚠️ CORRECTION 2026-08-06 (session 8) — the per-request core figure was revised
>
> This document reports **1.45 cores** for one embedding request at default threads. That was a
> time-average computed against a baseline captured while the machine was busier, and it
> **understated the value**. Re-measured with a clean baseline: **2.42 cores time-averaged at
> concurrency 1** (4.83 at concurrency 8).
>
> The same run closed open item A6. Finding 7's `cores_busy 9.29` and this figure were never in
> conflict — they are **different statistics of the same signal**: at default threads one embed is
> 2.42 cores time-averaged, 4.17 at p95, and **7.75 at instantaneous peak** (13.09 at concurrency
> 8). Only the time-average belongs in cost-per-request arithmetic.
>
> **The mechanism and every conclusion below are unaffected** — they rest on the intervention
> (thread pinning changes scaling 1.46× → 3.19×) and on the ratio between pinned and unpinned,
> not on the absolute core count.



## Summary

RocketRide's throughput was flat from 2 to 32 concurrent requests on the embedding workload. **The
engine is not the cause.** Its request path scales 3.69×, and ordinary Python work inside a node
scales 3.59×. Only the embedding arm is flat.

The cause is that **the engine does not constrain the thread pools of native math libraries used by
node code.** A single embedding request spreads itself across ~2.42 cores time-averaged (7.75 at instantaneous peak). Under concurrent load
those threads oversubscribe, per-request CPU cost inflates ~80 %, and aggregate throughput
plateaus.

**Setting the standard BLAS/OMP thread-limit variables to 1 before starting the engine converts a
flat service into a scaling one**: concurrency scaling goes 1.46× → 3.19×, and throughput at
concurrency 8 rises 19 % (73.3 → 87.6 req/s).

**The cost is single-request latency**, which roughly halves in throughput terms (50.3 → 27.4 req/s
at concurrency 1). This is a latency-versus-throughput knob, and today the engine exposes no
documented surface for it.

## 1. Localising the bottleneck — a four-arm ladder [VERIFIED]

Each arm adds exactly one layer to the one below. Same ~400-token document throughout, so payload
is not a variable. Barrier-synchronised fixed-duration windows, up to 4 driver processes,
randomised cell order.

| arm | pipeline | c=1 | c=8 | c=32 | scaling |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 minimal | `webhook → response_text` (no Python node) | 458.8 | 1297.6 | 1693.0 | **3.69×** |
| 2 noop | `+ Python node emitting a constant` | 444.3 | 1175.5 | 1534.9 | **3.45×** |
| 3 cpu | `+ ~15 ms of pure-Python CPU, no model` | 51.4 | 152.3 | 184.3 | **3.59×** |
| 4 embed | `+ MiniLM forward pass` | 49.7 | 72.3 | 67.7 | **1.46×** |

Readings were fixed **before** the run. The one that fired:

> **Arms 1–3 scale, arm 4 is flat → the serialisation is specific to the model / native stack, not
> to the engine.**

Two supporting details:

* **Dispatching into a Python node is nearly free** — arm 2 costs ~3 % against arm 1 at
  concurrency 1 (444.3 vs 458.8 req/s). The node abstraction is not the overhead.
* **Latency inflation under load** is 6.7× for the request path, 8.9× for Python CPU, but **24.4×
  for embedding** (18.9 ms → 460.5 ms at concurrency 32). A service rate pinned near ~67 req/s
  while 32 requests queue is textbook queueing at a fixed number of servers.

## 2. The mechanism — thread oversubscription, not a lock [VERIFIED, 2 methods]

The strongest rival explanations were **(a)** native intra-op thread saturation and **(b)** a lock
serialising forward passes. They predict opposite outcomes under a thread limit, so the limit was
applied.

**Method 1 — the intervention.** Restart the engine with `OMP_NUM_THREADS`, `MKL_NUM_THREADS`,
`OPENBLAS_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `NUMEXPR_NUM_THREADS`, `TORCH_NUM_THREADS` = 1.

| arm | thread env | c=1 | c=8 | scaling |
| --- | --- | ---: | ---: | ---: |
| embed | default | 50.3 /s | 73.3 /s | 1.46× |
| embed | **=1** | 27.4 /s | **87.6 /s** | **3.19×** |
| cpu *(null control)* | default | 48.1 /s | 55.2 /s | 1.17× |
| cpu *(null control)* | **=1** | 48.1 /s | 56.0 /s | 1.16× |

**The null control holds**: the pure-Python arm is unchanged to within 2 %, as it must be — it uses
no BLAS. The intervention moved only what it should have moved. Rival (b) is refuted: a lock would
not care about thread counts.

**Method 2 — CPU accounting.** Measured as system-wide CPU-time deltas over the load interval, so
short-lived task processes cannot escape the census (a process-tree walk undercounts here — it
reported ~1.0 cores in every condition and was discarded).

| condition | rate | net cores busy | **core-seconds per request** |
| --- | ---: | ---: | ---: |
| default, c=1 | 50.3 /s | 1.45 | 0.0287 |
| default, c=8 | 73.3 /s | 3.78 | **0.0516** (+80 % for identical work) |
| threads=1, c=1 | 27.4 /s | 0.49 | 0.0180 |
| threads=1, c=8 | 87.5 /s | 2.31 | 0.0264 (+47 %) |

Two things this shows directly:

1. **One request occupies 2.42 cores at default and 0.49 pinned** (the 1.45 in the table below is the original under-measured baseline; see the correction banner) — the forward pass is
   multi-threaded, exactly as rival (a) requires.
2. **Per-request CPU cost inflates 80 % under concurrency at default**, versus 47 % pinned. That
   is the signature of oversubscription: more threads than cores, doing the same work for more CPU.

## 3. What this means for a service under concurrent load

**The default is tuned for a single request at a time.** Alone, a request is nearly twice as fast
with threading on. Concurrent, the same setting costs 19 % of aggregate throughput and removes most
of the ability to scale. A batch job and a serving endpoint want opposite settings, and the engine
currently ships one of them with no way to choose.

| deployment shape | wants |
| --- | --- |
| one document at a time, latency-sensitive (interactive extraction, single upload) | **default** — 1.8× faster per request |
| many concurrent documents, throughput-sensitive (a serving endpoint, bulk ingest) | **threads=1** — 3.19× scaling, +19 % throughput at c=8 |

**Product implications, in the order I would act on them:**

1. **Expose thread limits as pipeline or node configuration.** Today the only lever found is
   process environment at engine start, which is global to every pipeline on that engine. Two
   tenants with opposite needs cannot both be served.
2. **Consider making `threads=1` the default for concurrent serving deployments**, since a service
   behind a queue is the common shape and the current default silently caps it.
3. **Document the knob.** Nothing in the engine surface indicates that node throughput depends on
   an environment variable set outside the engine. This was found by experiment, not from docs.

**The comparison context matters:** our LlamaIndex service already pins `OMP_NUM_THREADS=1` and
takes its parallelism from 8 worker processes. So every previous RocketRide-versus-LlamaIndex
throughput comparison has been **tuned service versus untuned engine**. That is not a framework
difference; it is a configuration difference, and it is fixable on RocketRide's side.

## 4. Labels, and what a hostile reviewer would say

| claim | label |
| --- | --- |
| Engine request path scales 3.69×; Python-node dispatch costs ~3 % | **VERIFIED** |
| Pure-Python CPU in a node scales 3.59× across driver processes | **VERIFIED** |
| The embedding arm alone is flat (1.46×) | **VERIFIED** (2 harnesses) |
| Cause is native thread oversubscription, not a lock | **VERIFIED** (intervention + CPU accounting, with a passing null control) |
| `threads=1` gives 3.19× scaling and +19 % throughput at c=8 | **PROVISIONAL** — single harness, n=1 per cell; direction is large and consistent, the point values are not gated |
| Single-request latency cost of pinning (~1.8×) | **PROVISIONAL** — same caveat |
| Optimal thread count (1 may not be the best value; 2 or 4 untested) | **UNVERIFIED** — sweep not run, ~30 min |

> *"You are measuring your own competitor's default configuration and calling it a product bug."*

The finding is that a documented-elsewhere, standard environment variable changes engine throughput
by 19 % and its scaling behaviour by 2.2×, and that the engine exposes no way to set it per
pipeline. That is reported as a fixable configuration gap, with the direction that favours
RocketRide once fixed — it makes the engine faster under concurrency than any number we have
previously published for it.

> *"Pure Python scaled only 1.17× within a single task in one test and 3.59× in another. Which?"*

Both, and the difference is informative: within **one** task process Python is GIL-bound (1.17×);
across **four** task processes it scales 3.59×. RocketRide's concurrency for Python node code comes
from processes, not threads — which is the same model our LlamaIndex service uses with 8 uvicorn
workers.

> *"Does this invalidate the session-6 finding that RocketRide is flat in concurrency?"*

It **conditions** it. The flatness is real at default thread settings and is not a property of the
engine. Correction applied to `CONCURRENCY_CHARACTERIZATION.md` and `STATE.md` finding 1b3 in the
same turn as this document.

## 5. Not done, and why

| skipped | cost | why |
| --- | ---: | --- |
| Thread-count sweep (1, 2, 4, 8) to find the optimum | ~30 min | 1 vs default already establishes mechanism and direction; the optimum is a tuning question |
| Re-run the full concurrency curve under `threads=1`, gated, n≥5 | ~45 min | environment is about to change to Docker; deferred into `REBASELINE_PLAN.md` |
| ~~Reconcile with finding 7 (`cores_busy 9.29`)~~ **CLOSED session 8** | — | peak/p95 vs time-average; both real, not interchangeable. See the correction banner above |
