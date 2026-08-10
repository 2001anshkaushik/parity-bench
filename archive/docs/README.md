# benchmark-A

Production-grade benchmark suite: RocketRide vs Python AI orchestration frameworks.

Built to be **falsifiable**. Every design choice below exists because the opposite choice would
let this suite produce a number that is technically real and practically wrong. If RocketRide
wins here, the result survives an outside reviewer re-running it; if it loses somewhere, we find
out internally before a customer does.

```bash
# Phase 1 gate — must be 34/34 before any real run
../.venv/bin/python scripts/selftest.py

# Framework eligibility dossiers (evidence, not recollection)
../.venv/bin/python scripts/verify_frameworks.py --install
```

## Two tracks, because one comparison would be dishonest

| | Track A — execution substrate | Track B — orchestration overhead |
| --- | --- | --- |
| Question | Can the engine move work through hardware faster? | What does the framework itself cost per step? |
| Competitors | `asyncio`, `ThreadPoolExecutor`, `ProcessPoolExecutor` (per-item **and** chunked), Ray, Dask | LangGraph, CrewAI, DeepAgents, Omnigent |
| LLM calls | none | fixed-latency stub |

LangGraph and CrewAI are **not** pipeline execution engines — they are agent orchestrators where
>90% of wall-clock is LLM wait. Benchmarking their raw throughput on 10,000 document transforms
would be like benchmarking a project manager on typing speed: we would win, and the win would
mean nothing. Track B holds model latency constant with a stub so what remains is framework cost.

## Layout

```
harness/
  collector.py        process-tree sampler (macOS/arm64): RSS, USS, threads, fds, CPU, ctx switches
  collector_proc.py   out-of-process collector — REQUIRED for real runs, see "Observer effect"
  workload.py         4 kernels + seeded fault injection + correctness reference
  runner.py           closed-loop and open-loop drivers
  adapters/base.py    the only interface a framework must implement
  adapters/baselines.py  expert-tuned Python controls
  stats.py            percentiles, bootstrap CIs, ratio CIs with error bars
  env_capture.py      environment fingerprint recorded with every run
scripts/
  selftest.py         34-check Phase 1 gate
  verify_frameworks.py  eligibility dossiers per framework
```

## Four things that would have broken this benchmark

Each was found by the harness testing itself, and each is now a regression test.

**1. The instrument was corrupting the measurement — by 100×.**
The collector originally ran as a thread inside the harness, calling `children(recursive=True)`
per root per tick. On macOS that rescans the entire process table *while holding the GIL*.
Measured: 5,412 → 58 items/s. The bias direction is what makes it fatal — in-process frameworks
(LangGraph, CrewAI) run inside the harness and would eat the penalty, while RocketRide's external
engine would not. It would have fabricated a RocketRide win out of pure instrumentation.
Fixed by one process-table scan per decimated cycle plus a separate collector process.
Now −0.8% against 3.1% run-to-run noise. Guarded by **T10**.

**2. Process pools looked 14× slower than they are.**
A near-zero-work task appeared to cost 155 ms. Almost all of it was the collector bug above; the
true figure is **0.95 ms**. Had we sized workloads against the bad number, every process-isolated
engine — RocketRide included — would have been measured on IPC overhead instead of its scheduler.
Guarded by **T9**, and the floor is written to `results/selftest/calibration.json` for workload sizing.

**3. Per-item dispatch is not what a competent engineer ships.**
`ProcessPoolExecutor` pays one pickle/pipe round-trip per item. At 10,000 items that is 10,000
round-trips versus ~50 for a chunked pool. Publishing only the per-item variant would be the
single easiest way to manufacture a win, so `ChunkedProcessPoolAdapter` is a required baseline.
It has a real trade-off worth reporting: chunking amortises IPC but weakens fault isolation —
one crash takes the whole chunk. That is a legitimate axis for RocketRide, and we measure it
rather than assert it.

**4. The framework classifier libelled the competition.**
The first version flagged LangGraph `HOSTED_API` on the strength of
`https://api.myauth-provider.com` — a docstring placeholder — and CrewAI on `api.openai.com`.
Every agent framework calls an LLM provider; it says nothing about where the graph executes.
That error would have wrongly excluded the two most important competitors from Track A: the
mirror image of a strawman, and just as disqualifying. Now only *vendor-owned* domains count,
and even those yield `REVIEW_REQUIRED`, never a verdict — locality is settled behaviourally.

## Metrics

Priority order per leadership, with what backs each claim:

1. **Memory & stability** — peak RSS summed across *whole process trees*, RSS slope over the back
   half of a run (leak signal), macOS compressor pages and swap deltas, uniform RSS ceiling with
   recorded `oom_event`s.
2. **Fault isolation** — collateral failures per injected fault. Clean items that die because
   something else failed. The sharpest single measure of whether failures cascade.
3. **Latency & throughput scaling** — full distribution p50/p95/p99/p99.9, never means. Separate
   closed-loop (service latency) and open-loop (batch-position latency) modes, never mixed.
4. **Cost per unit** — CPU-seconds and peak RSS per 1,000 items.

Plus **goodput**: items that are correct, not merely returned. Verified against a single-threaded
reference. A framework that is fast and wrong, or that silently drops items, must not score as
successful.

## Non-negotiables

- **Whole-tree accounting.** RocketRide runs a thin WebSocket client in the harness and does the
  work in engine-spawned process trees; in-process frameworks do everything in the harness. Both
  sides are summed across all their processes or the comparison is meaningless.
- **Adapters implemented as each framework's own docs recommend**, then reviewed by someone who
  likes that framework before publication. Beating a naive baseline proves nothing.
- **Telemetry disabled uniformly.** CrewAI and Omnigent phone home by default; a background POST
  during a timed run is measured latency that belongs to their analytics.
- **Pre-registered predictions** before each run series, so interpretation cannot be retrofitted.
- **Publish the losses.** RocketRide will lose somewhere — ecosystem, cold start, dev velocity.
  Reporting that is what makes the wins believable.

## Known limitations

- **macOS is not Linux for OOM.** macOS compresses memory and uses jetsam rather than a Linux OOM
  killer. Crash/OOM numbers here are *indicative*. Any published stability claim needs a Linux
  confirmation run.
- **Docker VM is capped at 8.32 GB** while the host has 48 GB. Running the engine in Docker
  against native Python is an invalid memory comparison. Run the engine natively, or apply an
  identical RSS ceiling to both sides.
- **Apple Silicon throttles under sustained load.** Thermal state is captured before and after
  every run; a run that throttled partway is not comparable to one that did not.
