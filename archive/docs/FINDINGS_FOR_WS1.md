# benchmark-A → WS-1: Evidence Handover

**For: Shashi, Leela** · From: Ansh · 2026-08-05

benchmark-A was a parallel exploration that the Aug 4 exec review superseded. Rather than let the
work evaporate, this is everything from it that bears on WS-1 Service Parity — mapped to your
action items and open questions, with the method for each so you can re-derive or reject any of it.

**This is an offer of evidence, not a critique of the WS-1 plan.** Several items below are things
I got *wrong* first and had to correct; those are the most useful ones, because they are traps
that sit directly in WS-1's path. Where something is unreplicated or uncertain I say so.

Everything is reproducible: `benchmark-A/scripts/`, raw data in `benchmark-A/results/`.

---

## TL;DR — start with #1, it affects what you are building today

1. **⚠️ `sentence-transformers` silently runs on the Apple GPU (`mps`), and nothing declares it.**
   Our service computed on the GPU for a full day while reporting no device at all. It changes
   throughput 2–3× and run-to-run spread 10×. **RocketRide's engine lands on CPU** — verified
   empirically, and note that source inspection said the opposite, so please assert rather than
   read the code. If your service is on `mps` and the engine is on `cpu`, the parity run compares
   silicon. **Action: pin `device` explicitly and assert declared-vs-resolved at startup.**
   [VERIFIED, 3 methods] — §0 below.
2. **RocketRide's effective concurrency is ~17, not 64 and not 24.** Measured, reproducible in
   ~2 minutes — and the measuring tool has now been calibrated (±1%) and guarded against its own
   worst failure mode. [VERIFIED, 2 methods]
3. **A single-process load driver understates every service by up to 4.8×.** I shipped this bug and
   didn't notice for a full session. If WS-1's driver is single-process, all three services get
   mismeasured — and not equally. [VERIFIED]
4. **Most run-to-run variance is a warmup artefact and is fixable** — discarding the first two
   iterations took spread 17.7% → 1.7%. The load-average gate we originally proposed is **refuted**;
   drop it. [VERIFIED by null control]
5. **Poison-run accounting needs injected and collateral separated**, plus output verification —
   otherwise "it survived" can mean "it returned wrong answers fast". [VERIFIED against
   known-answer cases]

---

## 0a. ⚠️ Test-document shape decides the winner — do not benchmark on a convenience document

**Embedding cost is linear in TOKENS, not characters or chunks**, and the two services cross over
at **200–400 embedded tokens per document**. Below it LlamaIndex wins; above it RocketRide wins.

The verified mt10k corpus has a **median of 338 embedded tokens** — it straddles the crossover
(21.4 % of documents below 200, 38.3 % in the zone, 40.3 % above 400).

I learned this the hard way: I reported "LlamaIndex 1.73× faster" from a ~210-token synthetic
document, then measured **RocketRide 1.13× faster** on the real distribution. Same harness, same
concurrency, same device — different document. **That first number is withdrawn.**

Mechanism [VERIFIED, 2 methods]: RocketRide is **overhead-bound** (fixed WebSocket + DAP + IPC +
4-node-hop cost per request, which amortises as documents grow); LlamaIndex is **compute-bound**.
Across 50→400 tokens RocketRide retains 0.51× of its throughput, LlamaIndex only 0.22×.

**Action: benchmark on the real corpus distribution, and report the token distribution alongside
any throughput number.** Details in `PARITY_CORPUS_FINDINGS.md`.

## 0. ⚠️ The device finding — most actionable item in this document

**What happens:** `sentence-transformers` calls `get_device_name()` when `device` is unset and
silently selects the best available accelerator. On Apple Silicon that is `mps`. Nothing logs it,
nothing declares it, and the config value you never set is the one doing the work.

**Measured impact on our LlamaIndex service** [VERIFIED, 3 independent methods —
`CONCURRENCY_CEILING.md`]:

| | cpu | mps |
| --- | ---: | ---: |
| peak throughput | 101.8/s | 192.1/s |
| **run-to-run spread** | **3–4 %** | **44–53 %** |
| cores busy with 1 process | 1.00 (as it must be) | **0.45** ← work is off-CPU |

The 0.45 is the tell: one process embedding continuously used less than half a core, because the
work was not on the CPU at all.

**Is RocketRide affected?** The engine's embedding node calls
`SentenceTransformer(model_name_or_path=…, truncate_dim=…)` with **no `device=` argument**
(`engine/nodes/embedding_transformer/sentenceTransformer.py:84`) — so by the same logic it *should*
pick the GPU. **Source inspection said GPU and was wrong.** Measured empirically on Leela's
four-node pipeline: `cores_busy = 9.29`, firmly CPU (output verified first as real 384-dim
unit-norm vectors from the right model). Most likely the engine's bundled torch has no MPS support.

**This is exactly why the schema now requires an assertion, not a declaration.** Two of us read the
same code and drew the wrong conclusion; only measurement settled it.

**What we suggest you do** (~15 min per service):
1. Pass `device=` explicitly everywhere a model is constructed.
2. At startup, read the device **off the loaded parameters** and refuse to start on mismatch:
   `str(next(model._first_module().auto_model.parameters()).device)`.
3. Report both `device` and `resolved_device` in `/manifest` and every response.

Our implementation and its two-direction test are in `ws1/pipeline.py::warm()`.

---

## 1. Effective RocketRide pool width = **~17**

**Open question this answers:** which concurrency setting the earlier RocketRide runs actually ran at.

Three numbers were in circulation and **none of them is the effective width**:

| number | where it comes from | is it the width? |
| --- | --- | --- |
| `threadCount: 64` | task config default (Leela's `PREDICTIONS.md` #2) | **no** |
| 24 OS threads | what the engine process reports via `psutil` | **no** |
| **~17** | **measured end-to-end** | **yes** |

### Method (`scripts/pool_width.py`)

Hold each item inside the node for a known duration *T*, submit far more items than any plausible
width, measure steady-state throughput *X*. For a pool of width *W* serving holds of length *T*,
`X = W / T` exactly — so `W = X · T`, read off rather than guessed.

| hold *T* | items | throughput *X* | implied width |
| ---: | ---: | ---: | ---: |
| 0.25 s | 600 | 68.55/s | **17.1** |
| 0.5 s | 400 | 34.47/s | **17.2** |
| 1.0 s | 200 | 16.58/s | **16.6** |

Spread 0.6 across a 4× range of hold durations.

**Independently confirmed by a second method.** In a separate experiment, 55 items each holding a
256 MB allocation for 2 s took 8.18 s — and `ceil(55 / 17) × 2 s = 8 s`. The same arithmetic
predicted 8 s for a 14-worker pool (observed 8.17 s) and 8 s for an 18-thread pool (observed
8.13 s), and 2 s for a 64-wide pool (observed 3.8 s). Two unrelated methods, same answer.

### To reproduce (~2 min)

```bash
cd benchmark-A && bash scripts/start_engine.sh && ../.venv/bin/python scripts/pool_width.py
```

Requires the `fault_probe` node (in `benchmark-A/nodes/fault_probe/`, copy into `engine/nodes/`
and restart). It is ~90 lines and benchmark-only.

### Why it matters for WS-1

- Any RocketRide result is implicitly a **width-17 result**. If the LlamaIndex and LangChain
  services run with different effective widths, the comparison is measuring pool sizing, not
  frameworks. **Recommend: pin and report effective width for all three services** — hence the
  concurrency-pinning field in the schema proposal.
- `threadCount` is a programmatic argument in `packages/server/engine-core/apLib/async/ThreadedQueue.hpp:48`,
  not a pipeline-file setting. **UNVERIFIED whether width is tunable from outside the engine
  source at all.** If it is, someone should find the knob before WS-1 locks its configuration.

---

## 2. ⚠️ The single-process driver bug — highest-risk repeat

**This is the one I most want you to take from this document.**

For an entire session I reported RocketRide's throughput as ~2,600 items/s, flat from n=100 to
n=20,000. The curve looked textbook: throughput saturated, latency grew linearly exactly as
Little's Law predicts, zero errors. Nothing looked wrong.

**It was my client, not the engine.** A single-process Python asyncio driver saturates at
~2,500–3,400 req/s regardless of what it is talking to — its own event loop and GIL are the limit.

| driver processes | aggregate throughput |
| ---: | ---: |
| 1 | 3,412/s |
| 2 | 6,485/s (1.90×) |
| 4 | 11,408/s (3.34×) |
| 8 | 12,510/s |

Every RocketRide number I had collected understated the engine by ~3–4.8×.

### Why this is dangerous for WS-1 specifically

A saturated single-process driver produces results that are **internally consistent and completely
wrong**, and it does not fail loudly. Worse, it does not bias all services equally: a service with
lower per-request overhead hits the driver ceiling sooner and looks artificially *closer* to a
slower one. With three services under comparison, the driver becomes the thing you are measuring.

### Recommended gate before any WS-1 number is trusted

Run the driver-scaling check once per service: 1 → 2 → 4 → 8 driver processes. **If aggregate
throughput scales with driver count, you are measuring the driver.** Only when it plateaus are you
measuring the service. `scripts/driver_scaling.py` does this in ~4 minutes; it needs one
distinct pipeline/endpoint per driver (see §7 on `project_id`).

---


> ### ⚠️ CORRECTION 2026-08-05 (session 3) — this figure was corrected TWICE; the second correction was wrong
>
> **Current best value: 12,313.5/s at 4 drivers** [VERIFIED — n=5, warmup discarded, randomised
> order, spread **1.7%**, `results/engine_variance.json`].
>
> History, because the wobble is instructive:
> 1. First measured **11,408/s** (4 drivers), n=1.
> 2. Re-measured later the same day at **7,871 / 8,540 / 8,311/s**. I concluded the 11,408 was a
>    ~35% outlier and wrote a correction saying so. **That correction was wrong.**
> 3. Re-measured under the full variance protocol: **12,313.5/s, spread 1.7% across n=5.** This
>    supports the ORIGINAL figure and does not reproduce the 7,871–8,540 cluster at all.
>
> The 7,871–8,540 readings were taken during a session with heavy sustained prior benchmarking
> (15-min load average 20.01). **Why they were depressed is UNVERIFIED** — note that a direct null
> control refuted the simple "load-average carryover" hypothesis on a different service, so the
> obvious explanation does not hold. Treat any figure not taken under the variance protocol as
> unreliable in EITHER direction.

## 3. ±35% run-to-run variance → proposed minimum variance protocol

**Open item: how confident can we be in a single number?** On this host, not very.

The same configuration, measured four times across one session:

| run | 4 drivers | 8 drivers |
| --- | ---: | ---: |
| first measurement | 11,408/s | 12,510/s |
| Tier 2 sweep (randomised order) | 7,871/s | 5,248/s |
| re-run, engine as-is | 8,540/s | — |
| re-run, fresh engine restart | 8,311/s | 6,655/s |

Three consecutive runs cluster at 7,900–8,500/s; the first is a ~35% outlier and the 8-driver
figure varies ~2×. `pmset -g therm` recorded **no thermal warning**, but the 15-minute load
average was **20.01 on 14 cores** after sustained benchmarking.

> **UPDATE 2026-08-05 — partly attributed, and one hypothesis REFUTED.** On the LlamaIndex service
> we isolated two causes with direct experiments (`VARIANCE_PROTOCOL.md`):
> **(a) most variance is a warmup artefact** — discarding the first 2 iterations took spread from
> 17.7% to 1.7% [VERIFIED];
> **(b) GPU (`mps`) variance is irreducible** at 14–25% while CPU reaches 0.7–4.4% [VERIFIED, 2 methods].
> **(c) load-average carryover is NOT a cause** — measuring immediately after driving load to 7.88
> gave the *lowest* spread observed (0.7%). Our original proposal to gate on load average should
> be dropped [VERIFIED by null control].
> **RocketRide's ±35% remains UNVERIFIED** — it was measured on a no-model pipeline, so neither
> the GPU nor model warmup explains it. Do not assume this transfers.

### Proposed protocol (suggestion, not a mandate)

1. **n ≥ 5 repetitions** per configuration. Report median and a bootstrap 95% CI, never a single run.
2. **Randomised order** across services and configurations, with a fixed seed. Order effects are
   real: whoever runs first gets the cool machine and the clean page cache.
3. **Quiet-host gate.** Record load average and thermal state before and after; discard runs where
   1-min load exceeds a threshold at start. `harness/env_capture.py` does this.
4. **Publish the spread.** If the CI for two services overlaps, they are not distinguishable —
   say so rather than reporting the point estimate.
5. **Gate on variance itself:** if the spread across repetitions exceeds ~15%, the measurement is
   not ready to publish and something environmental needs fixing first.

`harness/stats.py` has percentile, bootstrap-CI and ratio-CI helpers (`ratio_ci` gives error bars
on an "N× faster" claim; if the interval spans 1.0 there is no demonstrated difference).

---

## 4. Poison-run methodology — action item #5

The core requirement: **separate the faults you injected from the damage they caused**, and verify
that survivors are actually correct.

### Accounting schema

```
injected          faults deliberately introduced
returned          items that produced any response at all
collateral        CLEAN items that were lost, split three ways:
                    collateral_failed          returned an error
                    collateral_missing         never returned
                    collateral_wrong_output    returned, but the wrong value
isolation_ratio   collateral / injected      ← the headline number
goodput_pct       clean items with a VERIFIED-correct result / clean items
```

**`collateral_wrong_output` is the one people leave out and it is the one that matters most.** A
framework that stays up while silently corrupting survivors would otherwise score as perfectly
isolating. Every clean item's output is compared against a single-threaded reference
(`sha256(item_id|filler)` in our case; for mt10k it would be the offline reference vectors Leela
already built). In our runs it was 0 everywhere — worth confirming rather than assuming.

### Fault classes worth injecting separately

They behave completely differently and averaging them hides the result:

| class | what it tests | our finding |
| --- | --- | --- |
| `raise` | per-item error containment | all frameworks 0.00 |
| `malformed` | contract/schema validation path | all frameworks 0.00 |
| `alloc` | memory spike | all 0.00 — but see below, weak as designed |
| `hang` | slot occupancy / pool starvation | **the only class that separates anything** |

**Faults that terminate are easy; faults that occupy are hard.** A raised exception frees its slot
immediately. A hang holds it. Once concurrent hangs approach the pool width, clean work queues
behind them and misses the deadline — which is why the hang result is *entirely* explained by pool
width (§1) and not by framework quality.

### Two methodology traps we hit — both produced false verdicts

1. **Deadline semantics must be identical across frameworks.** Our `ProcessPoolExecutor` path
   called `fut.result(timeout=…)` inside `as_completed()`, which only ever sees *already-completed*
   futures — the deadline never fired. It ran to 100 s and scored a fictitious perfect 0.00 while
   the other frameworks were cut off at 20 s. Separately, the asyncio path started its timer when
   an item *acquired the semaphore* rather than at batch start, effectively granting it a longer
   deadline. **Use one wall-clock deadline from batch start, enforced identically.**
2. **A zero-fault control run is mandatory.** Our Model A cells reported isolation ratios of 32
   and 49 — which were pure artefact: ~50 s of pipeline setup sat inside the timed region, so
   clean items timed out with no fault involved. A control with zero injected faults would have
   caught it immediately (it scored 0% goodput). **If the control does not pass at ~100%, the
   configuration cannot measure isolation at all.**

---

## 5. Tier 2 — FastAPI 29,067/s vs RocketRide 7,871/s

**Read the caveat before the number.**

Both sides driven by the **same** multi-process driver, same driver-count sweep, same payload, same
per-driver concurrency, same machine, same session, randomised order.

| | peak throughput | p50 at peak | p99 at peak |
| --- | ---: | ---: | ---: |
| RocketRide engine | 7,871/s (4 drivers) | 121.1 ms | 163.2 ms |
| FastAPI + uvicorn | **29,067/s** (4 drivers, 14 workers) | **10.7 ms** | 197.2 ms |

### ⚠️ Why this may not transfer to WS-1 — please read this as a prediction to test, not a result to accept

**The work unit was a sha256 digest — under a microsecond.** That measurement is almost entirely
transport, scheduling and serialization overhead. It is precisely the regime where a Python HTTP
stack is strongest and where RocketRide's per-item WebSocket/DAP round trip and 17-wide pool are
weakest.

**WS-1's workload is the opposite regime.** The mt10k pipeline is
`RecursiveCharacterTextSplitter` + MiniLM embedding — Leela's Stage 1 measured a batched encode at
~31 ms per 100-chunk document. With ~30 ms of real work per item, per-item overhead stops
dominating and the gap should compress substantially, possibly to nothing.

**Concrete prediction, offered so it can be falsified early:** on the mt10k workload the
FastAPI-vs-RocketRide throughput gap will be **under 1.5×**, not 3.7×. If WS-1's first parity run
shows a gap near 3.7×, something is wrong with the harness — most likely the driver (§2). If it
shows near-parity, this Tier 2 number simply did not transfer, which is the expected outcome.

**Two further caveats:**
- RocketRide's number carries the ±35% variance of §3. The *margin* is not precisely known.
- The FastAPI wrapper runs work **in-process**, so an interpreter crash takes every in-flight item
  with it — a failure mode RocketRide's separate engine process does not share. Throughput and
  blast radius trade against each other; both belong in any comparison.

---

## 6. The 2.65× memory advantage at matched width — under-replicated

The one genuine matched-comparison advantage found for RocketRide anywhere in benchmark-A.

Allocate 256 MB **and hold it for 2 s**, 55 concurrent injections, n=1,000:

| framework | effective width | wall | peak tree RSS |
| --- | ---: | ---: | ---: |
| **RocketRide** | **~17** | **8.18 s** | **5,040 MB** |
| **asyncio** | **18** | **8.13 s** | **13,363 MB** |
| processpool | 14 | 8.17 s | 4,280 MB |
| threadpool | 64 | 3.80 s | 13,237 MB |

**Matched width (17 vs 18), matched wall time (8.18 vs 8.13 s), 2.65× less peak memory.** The
mechanism is not scheduling — it is allocator behaviour across a process boundary. The in-process
frameworks allocate and free 55 × 256 MB on one shared heap and the freed pages are not returned
to the OS promptly, so high-water RSS accumulates. RocketRide's node process and the process-pool
workers reuse a small heap and stay near `width × block_size`.

### Flagged honestly

- **One run. One block size. One hold duration. One host.** Not replicated.
- It may be a **CPython allocator** property rather than a "Python framework" property — a
  different allocator or an explicit trim could change it. That distinction matters a lot for how
  the claim is worded.
- The *plain* (non-held) allocation test showed nothing, because each allocation freed in ~0.3 s
  so almost nothing overlapped. **If WS-1 tests memory, the allocation must be held** or the test
  measures sequential churn and reports a null result.

If WS-1 wants a memory claim, this is the most promising thread — and it needs replication before
it is worth anything.

---

## 7. Model A livelock at ~150 concurrent pipelines

Relevant if any WS-1 scenario deploys many pipelines rather than many requests through one.

RocketRide enforces **one live task per `project_id`** — concurrent `use()` on the same `.pipe`
returns `RuntimeError: Pipeline is already running.` N concurrent tasks therefore needs N distinct
pipeline files. (This also bit the driver-scaling harness twice; worth knowing up front.)

| concurrent pipelines | outcome |
| ---: | --- |
| 25 / 50 / 100 | fine — ~1.0 process per task, engine healthy after |
| **150** | **livelock** |
| 250 | livelock |

**Failure mode is a livelock, not a crash:** engine process alive at 97–99% CPU, port stops
accepting connections entirely, **81 `node.py` processes orphaned** and needing manual cleanup, no
recovery observed after 27 minutes. Reproduced twice; n=100 survived cleanly on both sides.

Related, and probably more relevant to WS-1: **per-send latency degrades steeply with the number of
live task trees** — n=5 → 0.01 s, n=20 → 2.17 s, n=50 → 12.78 s, n=100 → exceeds 20 s. Also:
`terminate()` costs ~5.5 s per task (it does parallelise), and pipeline setup is ~0.5 s each and
largely serialises.

**Practical suggestion:** if any WS-1 scenario holds many pipelines open, cap it well below 150 and
add an orphan-cleanup step between runs. `harness/engine_ops.py` has `preflight()`/`postflight()`
that do health check + orphan reaping + restart-on-unhealthy.

---

## 8. Smaller things that will cost someone an afternoon

| finding | detail |
| --- | --- |
| `.pipe` needs `source` | Docs call it optional/extension-managed; the engine rejects the pipeline without it (`Pipeline does not have a source component defined`). Also `components` must be first and `project_id` a literal GUID. |
| Engine tarball is **flat** | `rocketride-server-v3.3.1-darwin-arm64.tar.gz` extracts `engine`, `ai/`, `nodes/` at the root. Krish's `provision.sh` passes `--strip-components=1`, which would scatter it. |
| `/version` beats `/ping` for health | `/ping` needs auth and returns 401; `/version` is unauthenticated, returns 200 **and** the running build's version + hash — readiness and identity in one call. |
| `curl -w '%{http_code}' \|\| echo 000` is a trap | On connection failure curl prints `000` *and* exits non-zero, so `\|\|` appends a second `000` → `"000000"`, which compares unequal to `"000"` and passes a health check against a dead server. Assign the fallback, don't append it. |
| `setrlimit(RLIMIT_NPROC, …)` on macOS | Requesting a higher soft limit **succeeds** but silently clamps the *hard* limit down to `kern.maxprocperuid` (8,000 here), permanently, and it cannot be raised back. Never call it. |
| SDK `get_server_info()` is broken | Documented as unauthenticated; `public=True` is stored at `client.py:242` and never read, so it always runs the auth handshake with an empty key and raises. Use `GET /version`. |
| Engine cold start | ~60 s on first launch (bootstraps its embedded Python: pip, wheel, setuptools, uv, constraint compilation), ~1 s warm. Must be outside any timed region. |
| Version pairing | Server releases bundle a matching client: 3.2.0→1.1.0, 3.2.1→1.1.1, 3.2.2→1.2.0, 3.3.0→1.3.0, **3.3.1→1.3.0**. Krish's repo pins engine 3.2.1 with SDK 1.2.0 — a mismatched pair. |

---

## 9. Reusable instruments

Extracted as dependency-light drop-in modules — see `benchmark-A/handoff/` and its README.
Nothing here requires adopting benchmark-A's structure.

| module | what it solves |
| --- | --- |
| `seeds.py` | Deterministic seeding. `hash()` is salted per interpreter, so `hash((fault, rate))` gave a different plan every process — same config injected 44 faults one run and 66 the next. sha256-derived seeds fixed it; verified identical across interpreters and across `PYTHONHASHSEED` values. |
| `collector_proc.py` | Out-of-process metrics collector: whole-process-tree RSS, threads, fds, CPU. **Runs in a separate process on purpose** — the in-thread version slowed the measured system 100× on macOS and biased *against* in-process frameworks specifically. Ships with the overhead regression test. |
| `fault_injection.py` | The accounting of §4, self-contained. |
| `verify_frameworks.py` | Framework dossiers: PyPI identity, publisher, licence, release recency, isolated install, import check, vendor-endpoint and telemetry detection. |

---

## 10. What I'd treat as unresolved

1. **Whether the Tier 2 gap transfers to a real embedding workload.** Prediction in §5; genuinely
   uncertain and cheap to test early.
2. **The source of the ±35% variance.** Not thermal by `pmset`'s account, but the host was under
   sustained load. Until it is understood, every throughput number needs error bars.
3. **Whether RocketRide's ~17 width is tunable.** If yes, the hang behaviour is a configuration
   default rather than a ceiling, and the whole framing changes.

Happy to walk through any of this, hand over the scripts, or re-run anything on request.
