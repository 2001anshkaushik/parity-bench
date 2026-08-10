# STEP 0 — Process Scaling Probe

**Gate result: 10,000 concurrent IS reachable — but only under one of RocketRide's two
concurrency models, and `RLIMIT_NPROC` turns out not to be the binding constraint for anything.**

Host: Apple M4 Pro, 14 cores, 48 GiB, macOS 26.6, AC power. Engine `3.3.1.35` hash `a0817cc6`,
native arm64, `127.0.0.1:5565`. Raw data: `results/process_scaling/`.

---

## 1. The OS ceiling is lower than reported, and cannot be raised

| Quantity | Value |
| --- | --- |
| `kern.maxprocperuid` | **8,000** ← the real per-uid cap |
| `kern.maxproc` (system-wide) | 12,000 |
| `RLIMIT_NPROC` as reported | soft 8,000 / hard 12,000 |
| Idle processes owned by uid 501 | **710–722** (measured across the session; the desktop session) |
| Usable headroom | **≈ 7,280** |

**The soft limit cannot be raised at all.** The reported hard limit of 12,000 is `kern.maxproc`
and is not usable per-uid. Two behaviours, both measured:

```
setrlimit(NPROC, (12000, hard))  ->  no exception, result becomes (8000, 8000)
                                     the SOFT limit did not move; the HARD limit was clamped DOWN
setrlimit(NPROC, (10000, hard))  ->  ValueError: not allowed to raise maximum limit
setrlimit(NPROC, ( 8001, hard))  ->  ValueError: not allowed to raise maximum limit
```

The first call is the dangerous one: it *succeeds*, silently lowers the process's own hard limit
to 8,000, and an unprivileged process can never raise a hard limit back. Any code that tries to
"raise NPROC toward the hard limit" on macOS permanently reduces its own ceiling instead. The
benchmark harness must not call `setrlimit(RLIMIT_NPROC, ...)` at all.

Raising the real cap needs `sudo sysctl -w kern.maxprocperuid=N`, which requires the user's
password — **UNVERIFIED whether that is acceptable on this machine; not attempted.**

## 2. RocketRide has two concurrency models with completely different process costs

The engine enforces **one live task per `project_id`**: concurrent `use()` calls against the same
`.pipe` return `RuntimeError: Pipeline is already running.` N concurrent *tasks* therefore
requires N distinct pipeline files, not N calls. This matters — it means a deployed pipeline
serving many concurrent requests is Model B *by construction*.

| | Model A | Model B |
| --- | --- | --- |
| Shape | N concurrent pipelines (N `use()`) | N concurrent `send()` on one pipeline |
| Process cost | **≈ 1.0 per task** | **0** |
| Realistic analogue | deploying N different pipelines | one service handling N concurrent requests |
| What Leela's 10k run did | — | ✅ this one |

## 3. Model B — flat, clean, and reaches the target

One pipeline, N concurrent in-flight `send()` calls.

| n | ok | err | wall | throughput | p50 | p99 | max | uid procs | node procs | engine RSS | threads |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 100 | 0 | 0.04 s | 2,385/s | 30.9 ms | 39.7 ms | 39.7 ms | 718 | 1 | 91.6 MB | 24 |
| 500 | 500 | 0 | 0.19 s | 2,614/s | 115.6 ms | 180.2 ms | 180.4 ms | 718 | 1 | 93.8 MB | 24 |
| 1,000 | 1,000 | 0 | 0.38 s | 2,640/s | 207.2 ms | 358.4 ms | 358.7 ms | 718 | 1 | 96.8 MB | 24 |
| 2,000 | 2,000 | 0 | 0.77 s | 2,612/s | 423.0 ms | 718.1 ms | 719.8 ms | 720 | 1 | 102.0 MB | 24 |
| 5,000 | 5,000 | 0 | 1.94 s | 2,576/s | 1,021 ms | 1,829 ms | 1,838 ms | 720 | 1 | 118.4 MB | 24 |
| **10,000** | **10,000** | **0** | 3.82 s | 2,617/s | 2,071 ms | 3,498 ms | 3,516 ms | 719 | 1 | 134.2 MB | 24 |
| 20,000 | 20,000 | 0 | 7.91 s | 2,529/s | 4,308 ms | 7,078 ms | 7,132 ms | 718 | 1 | 163.1 MB | 24 |

> **CORRECTION (Step 3).** The ~2,600/s figure in this table is **our single-process client's
> ceiling, not the engine's**. With 4 independent driver processes the engine sustains 11,408/s,
> saturating near 12,510/s — see `CEILING.md`. The *flatness* of the curve and every process /
> memory / thread column below stand unchanged; only the throughput level is understated, by ~4.8×.

**Fit: process count is constant. Zero growth over a 200× concurrency range.** Node processes
stay at 1, OS threads stay at 24, and engine RSS grows 91 → 163 MB (+72 MB for 200× the
concurrency, ≈ 3.6 KB per additional in-flight item).

**Failure mode: clean backpressure, textbook.** Throughput saturates at ~2,600 items/s and stays
flat; latency grows linearly with N exactly as Little's Law predicts for a saturated server
(W = N/λ ⇒ 10,000/2,617 ≈ 3.8 s, observed 3.82 s wall). Zero errors at every level including
20,000. Nothing queues unboundedly, nothing crashes, no memory blow-up.

`RLIMIT_NPROC` is **completely irrelevant** to Model B. The ceiling here is throughput and
latency tolerance, not the process table.

## 4. Model A — livelocks at ~150, far below the OS ceiling

N concurrent pipelines, each with its own task process tree.

| n | tasks created | use errors | setup | procs/task | node procs | engine healthy after |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 25 | 25/25 | 0 | 21.0 s | 1.56 | 25 | ✅ (CPU 0.2 %) |
| 50 | 50/50 | 0 | 23.4 s | 1.06 | 51 | ✅ (CPU 0.2 %) |
| 100 | 100/100 | 0 | 49.1 s | 0.94 | 101 | ✅ (CPU 0.2 %) |
| **150** | — | — | — | — | 153 | ❌ **LIVELOCK** |
| 250 (first run) | — | — | — | — | 81 orphaned | ❌ **LIVELOCK** |

**Fit: ≈ 1.0 process per task** (node processes = n + 1 at every surviving level).

**Failure mode: livelock — the worst of the three possibilities.** Not clean backpressure, not a
clean crash:

- engine process alive, state `R`, pinned at **97–99 % CPU**
- port stops accepting connections entirely (`/version` → connection refused)
- **task processes orphaned** — 81 `node.py` processes survived the first occurrence and had to
  be killed manually
- **no recovery** — the first occurrence was left 27 minutes and never came back

Observed twice (n=250, then reproduced at n=150), with n=100 surviving cleanly both before and
after. **Threshold is bracketed at 100 < n < 150; not bisected more finely** — each occurrence
costs a manual cleanup of the process table, and the bracket is enough to set the sweep range.

Secondary observations, both real costs worth reporting:

- **Setup does not scale**: 21 s for 25 pipelines, 49 s for 100 — roughly 0.5 s per pipeline
  launched, and launches largely serialise.
- **`terminate()` costs ≈ 5.5 s per task** but does parallelise (1 task 5.6 s, 2 concurrently
  5.17 s). Teardown of 100 tasks is ~6 s parallel, ~9 minutes if done sequentially.
- The engine is **transiently unresponsive to HTTP while launching pipelines in bulk**, even at
  n=100 where it fully recovers afterwards.

## 5. Baseline process cost per unit of concurrency

| Adapter | Concurrency | Peak uid procs | Δ vs base | Processes per unit |
| --- | ---: | ---: | ---: | ---: |
| asyncio | 100 | 714 | 0 | **0.000** |
| asyncio | 1,000 | 714 | 0 | **0.000** |
| asyncio | 10,000 | 714 | 0 | **0.000** |
| threadpool | 100 (100 workers) | 714 | 0 | **0.000** |
| threadpool | 1,000 (512 workers) | 714 | 0 | **0.000** |
| processpool | 4 workers | 719 | +5 | 1.25 /worker |
| processpool | 10 workers | 725 | +11 | 1.10 /worker |
| processpool | 14 workers | 729 | +15 | 1.07 /worker |
| processpool | 28 workers | 743 | +29 | 1.04 /worker |
| processpool | 56 workers | 771 | +57 | 1.02 /worker |

`ProcessPoolExecutor` costs ≈ 1 process **per worker plus one manager** — asymptotically 1.0/worker
— and workers are bounded by core count in any sane configuration, not by task count. At 10,000
tasks with 14 workers it uses **14 processes, not 10,000**.

## 6. Arithmetic — maximum reachable concurrency

```
per-uid cap            8,000
idle desktop           - 720
                      -------
headroom               7,280

Model B      0 proc/unit    -> NPROC never binds.        Measured OK at 20,000. Target 10,000 MET.
Model A      1 proc/task    -> NPROC would allow 7,280 …
                              … but the ENGINE livelocks at ~150, i.e. 2 % of the OS ceiling.
asyncio      0 proc/unit    -> NPROC never binds.
threadpool   0 proc/unit    -> bounded by OS threads, not processes.
processpool  1 proc/worker  -> 14 workers = 14 procs. NPROC never binds.
```

**No adapter in Track A is constrained by `RLIMIT_NPROC`.** The premise that the 8,000-process
limit would cap us at 10,000 concurrent tasks does not hold — because neither RocketRide's
realistic model nor any Python baseline forks per unit of work.

## 7. Proposed sweep range

**Model B is the benchmark's primary axis: 100 → 500 → 1,000 → 2,000 → 5,000 → 10,000.**
All verified error-free, well inside memory, and directly comparable against asyncio /
threadpool / processpool, none of which fork per unit either. 20,000 is available as a
stress point but latency there (p99 ≈ 7 s) is past anything an ICP would ship.

**Model A gets its own bounded series: 10 → 25 → 50 → 100, hard-stopped at 100.** Going higher
reproduces the livelock and costs a manual process-table cleanup. The livelock is reported as a
result, not engineered around.

This is *not* leadership's "10,000 concurrent tasks each with its own process tree" — that shape
is unreachable here, by a factor of ~65×, and the wall is RocketRide's own scheduler rather than
the OS. The 10,000 target is met in the shape that actually matches production usage.

## 8. What this means for the headline claim

The pre-registered headline is **fault isolation under partial failure**. Step 0 reshapes it:

- In **Model B**, RocketRide keeps *one* process for any number of in-flight items. That is
  excellent for memory and throughput, but it means a process-level fault has **no blast radius
  containment between concurrent items** — they share the task process. The interesting question
  becomes whether an item-level failure is contained *within* the shared process.
- In **Model A**, isolation is genuinely per-task (1 process each) — but the model livelocks at
  ~150, so the isolation advantage cannot be exercised at the scales leadership wants.

Both belong in the report. The honest framing is a trade-off curve — isolation vs scale — not a
single winner.

## 9. UNVERIFIED

- Whether the Model A livelock is a defect or a documented limit. Not in any doc read so far; no
  upstream issue searched yet.
- The precise livelock threshold (bracketed 100–150, not bisected).
- Whether `sudo sysctl -w kern.maxprocperuid` is acceptable on this machine — not attempted.
- Whether the livelock reproduces on Linux, or is macOS-specific.
- Engine reports **24 OS threads**, not the `threadCount: 64` Leela observed in task config. The
  relationship between that config value and actual OS threads is not established.
