# STEP 1 — Complete Fault Isolation Matrix

## Verdict: **on fault ISOLATION, RocketRide separates on nothing. On MEMORY under sustained concurrent pressure, it separates by 2.65×.**

Two distinct answers, and conflating them is how this becomes marketing:

- **Isolation (collateral per fault):** 11 of 12 cells are a perfect 0.00 for *every* framework.
  On the twelfth (hang @ 5 %) RocketRide is *beaten* by a correctly-sized thread pool. There is no
  fault class where RocketRide's isolation exceeds expert-tuned Python. **No separation.**
- **Memory (peak RSS under held allocations):** at matched pool width and matched wall time,
  RocketRide holds **5,040 MB vs asyncio's 13,363 MB**. This is the one genuine, matched-comparison
  differentiator found in the entire study — and it is a *memory* result, not an isolation one.

Seeds are deterministic (`harness/seeds.py`); plans verified identical across separate
interpreters and across differing `PYTHONHASHSEED`. Raw data: `results/fault_matrix/`.

---

## Isolation ratio — collateral clean items lost per injected fault

n=1,000 per cell, one 20 s wall-clock deadline applied identically to all four frameworks.

| fault | rate (injected) | rocketride | asyncio | threadpool(64) | processpool(14) |
| --- | --- | ---: | ---: | ---: | ---: |
| raise | 0.1 % (1) | 0.00 | 0.00 | 0.00 | 0.00 |
| raise | 1 % (5) | 0.00 | 0.00 | 0.00 | 0.00 |
| raise | 5 % (32) | 0.00 | 0.00 | 0.00 | 0.00 |
| hang | 0.1 % (0) | 0.00 | 0.00 | 0.00 | 0.00 |
| hang | 1 % (16) | 0.00 | 0.00 | 0.00 | **5.44** |
| hang | 5 % (53) | **12.60** | **12.45** | **0.00** | **12.81** |
| alloc | 0.1 % (1) | 0.00 | 0.00 | 0.00 | 0.00 |
| alloc | 1 % (12) | 0.00 | 0.00 | 0.00 | 0.00 |
| alloc | 5 % (54) | 0.00 | 0.00 | 0.00 | 0.00 |
| malformed | 0.1 % (0) | 0.00 | 0.00 | 0.00 | 0.00 |
| malformed | 1 % (7) | 0.00 | 0.00 | 0.00 | 0.00 |
| malformed | 5 % (46) | 0.00 | 0.00 | 0.00 | 0.00 |

`collateral_wrong_output` was **0 in every cell for every framework** — nobody stayed up by
silently corrupting survivors.

## The hang row is entirely explained by pool width

Effective concurrency width, measured directly (`scripts/pool_width.py`: hold each item T seconds,
steady-state throughput X, width = X·T):

| framework | effective width | how obtained |
| --- | ---: | --- |
| processpool | **14** | configured `max_workers` |
| **rocketride** | **~17** | **measured: 17.1 / 17.2 / 16.6 at T = 0.25 / 0.5 / 1.0 s (spread 0.6)** |
| asyncio | **18** | `to_thread` default = `min(32, cpu+4)`, *not* the Semaphore(64) in the code |
| threadpool | **64** | explicit `ThreadPoolExecutor(max_workers=64)` |

Now overlay the hang results:

- **16 hangs**: width 14 drowns (5.44); widths 17, 18, 64 all survive (0.00).
- **53 hangs**: widths 14, 17, 18 all drown (12.8, 12.6, 12.5 — indistinguishable); width 64
  survives completely (0.00).

The ratio is a **pure pool-width artefact**. A hang holds a slot for its full duration; once
concurrent hangs approach the width, clean work queues behind them and misses the deadline. Any
system with a 17-wide pool behaves like RocketRide here, and any system with a 64-wide pool does
not. This is not a property that distinguishes these frameworks — it is arithmetic.

**Practical consequence:** RocketRide's ~17-wide task pool is narrower than a default
`ThreadPoolExecutor` sized for I/O work, and it is not configurable from the pipeline file (see
`ThreadedQueue.hpp:48` — `threadCount` is a programmatic argument). The engine reports 24 OS
threads and task config reportedly defaults to `threadCount: 64`; **neither number is the
effective width**, which measures ~17.

## alloc — the cell expected to differentiate, and did not

54 concurrent injected 512 MB allocations (~27 GB of churn), each touched page-by-page so the
memory is genuinely resident.

| rate | rocketride | asyncio | threadpool | processpool |
| --- | ---: | ---: | ---: | ---: |
| 0.1 % (1 alloc) | 1,396.5 MB | 701.4 MB | 1,213.5 MB | 2,157.7 MB |
| 1 % (12 allocs) | 1,908.5 MB | 1,725.5 MB | 1,727.5 MB | 5,230.4 MB |
| 5 % (54 allocs) | **3,444.7 MB** | **1,725.7 MB** | 3,263.8 MB | **10,862.6 MB** |

- **Every framework survived with 0.00 collateral and 100 % goodput.**
- **macOS compressor delta and swapouts were 0.0 MB / 0 in every single cell.** Nothing was
  absorbed by compression or swap — the memory was genuinely available and genuinely released.
  Peak system memory never exceeded ~18 % used.
- The spread is a **memory-efficiency** story, not an isolation one: `ProcessPoolExecutor` peaks
  at **10.9 GB — 6.3× asyncio and 3.2× RocketRide** — because 14 separate interpreters each hold
  their own 512 MB blob plus interpreter overhead. That is the real cost of process-per-worker
  isolation, and it is the one number in this matrix where the architectures genuinely diverge.

**The plain `alloc` fault was a weak test** — each allocation frees in ~0.3 s, so few overlap and
peak RSS implies only ~3–6 concurrent allocations, not 54. It measured *sequential churn*, not
sustained pressure. Re-run with a **held** allocation below.

## alloc_hold — the corrected memory test, and the ONE genuine differentiator found

`alloc_hold:2.0` allocates 256 MB and **holds it for 2 s**, so concurrent allocations genuinely
overlap. n=1,000, rate 5 % (55 injected), randomised framework order, identical warm-up for all,
process pool pre-spawned outside the timed region (audit fixes A1/A2/A4/A5 applied).

| framework | effective width | wall | peak tree RSS | isolation ratio | goodput | compressor | swap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| processpool | 14 | 8.17 s | 4,279.5 MB | 0.00 | 100 % | 0 MB | 0 |
| **rocketride** | **~17** | **8.18 s** | **5,040.1 MB** | 0.00 | 100 % | 0 MB | 0 |
| **asyncio** | **18** | **8.13 s** | **13,363.2 MB** | 0.00 | 100 % | −15.8 MB | 0 |
| threadpool | 64 | 3.80 s | 13,237.1 MB | 0.00 | 100 % | +197.9 MB | 0 |

**Wall times independently confirm the measured pool widths.** With 55 held allocations of 2 s
each, elapsed time should be `ceil(55 / width) × 2 s`: width 64 → 2 s (observed 3.8 s), widths
14/17/18 → 8 s (observed 8.17 / 8.18 / 8.13 s). This is a completely independent confirmation of
the `W = X·T` width measurement, arrived at by a different method.

### The matched comparison

**RocketRide (width ~17) vs asyncio (width 18): same effective concurrency, same wall time
(8.18 s vs 8.13 s), 5,040 MB vs 13,363 MB — RocketRide uses 2.65× less peak memory.**

This is the only cell in the entire study where RocketRide separates from an expert-tuned Python
baseline on a matched comparison. The mechanism is not scheduling — both do the same amount of
concurrent work in the same time — it is **allocator behaviour across a process boundary**. The
in-process frameworks allocate and free 55 × 256 MB on a single shared heap, and the freed blocks
are not returned to the OS promptly, so high-water RSS accumulates across rounds. RocketRide's
node process and the process-pool workers each reuse a small heap, so their footprint stays near
`width × block_size` instead of growing toward `n_faults × block_size`.

Note `threadpool` (width 64) is the interesting counterpoint: it finishes **2.1× faster** (3.8 s)
because it holds all 55 allocations at once, and pays 13.2 GB plus the only measurable memory
compression in the study (+197.9 MB) to do it. That is a legitimate time/memory trade, not a
defect.

**Caveats before this becomes a claim:** one block size, one hold duration, one host, single run
per cell. Peak RSS for in-process frameworks reflects allocator retention rather than live
concurrent bytes, which is real but is a property of CPython's allocator rather than of "Python
frameworks". A `malloc_trim`-equivalent or a different allocator could change it.

## Model A (per-task processes), deconfounded — see STEP 4

n=50, setup fully excluded, deadline starting at first send, zero-fault control passing at 100 %:

| fault @ 5 % | injected | collateral | ratio | goodput |
| --- | ---: | ---: | ---: | ---: |
| control (0 faults) | 0 | 0 | — | 100 % |
| raise | 4 | 0 | **0.00** | 100 % |
| **hang** | 5 | 0 | **0.00** | 100 % |
| alloc | 4 | 0 | **0.00** | 100 % |
| malformed | 2 | 0 | **0.00** | 100 % |

**Model A isolates hangs perfectly where Model B does not** — each task owns its process, so a
hung item blocks nothing else. This is the one place RocketRide's process-per-task model shows a
real, measurable isolation advantage over its own shared-pool model.

It comes at a hard cost: Model A caps at ~50 live pipelines on this host (a zero-fault control at
n=100 scored 0 % goodput inside 20 s), setup runs ~0.6 s per pipeline, and it livelocks the engine
at ~150 (`PROCESS_SCALING.md`).

## Verdict, stated plainly

**On which fault classes does RocketRide's ISOLATION separate from an expert-tuned baseline? None.**

- `raise`, `alloc`, `malformed`: RocketRide is perfect — and so is every baseline. Tie.
- `hang`: RocketRide (~17-wide) loses 12.6 per fault; a 64-wide thread pool loses 0. **RocketRide
  loses this one**, and the cause is a narrower, non-configurable pool.
- The only genuine *isolation* advantage found is **Model A's per-task process isolation**, which
  handles hangs perfectly but does not scale past ~50 concurrent pipelines.
- The only genuine *matched-comparison* advantage of any kind is **peak memory under held
  allocations: 2.65× lower than asyncio at the same width and the same wall time** (`alloc_hold`
  above). That is a real result and it is the one worth building a claim on.

The defensible claim is *"RocketRide contains item-level faults with zero collateral damage and
zero silent corruption"* — true, verified, and **matched by every competent Python baseline
tested**. It is a table-stakes result, not a differentiator. Any marketing that implies Python
frameworks cascade failures where RocketRide does not is contradicted by this matrix.

## UNVERIFIED / outstanding

- `alloc` does not sustain concurrent pressure (above). Needs a hold variant before the
  memory-isolation claim means anything.
- Only one work unit (sha256 digest) and one payload size (64 B filler).
- Framework order within each cell is fixed, not randomised — see `ADVERSARIAL_AUDIT.md` A5.
- Whether RocketRide's ~17 width is tunable at all from outside the engine source.
