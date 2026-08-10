# STEP 3 — Where the ~2,600 items/s ceiling comes from

**Answer: it was our own client. Not the engine, not the WebSocket, not serialization.**

**Every RocketRide throughput number collected before this probe understates the engine by
roughly 3×.** Best reproducible estimate of the engine's saturation point on this host is
**~8,000–8,500 items/s at 4 driver processes** (three consecutive measurements). An earlier
single run reached 11,408–12,510/s and did **not** reproduce — see the correction below.

Raw data: `results/ceiling/driver_scaling.json`, `results/ceiling/ceiling.json`.

---

## The isolating experiment

Four candidate causes, each varied independently so the answer is evidence rather than a
hypothesis. The decisive one is driver processes: if throughput scales with *independent client
processes*, the bottleneck was the client; if it stays pinned, the engine is the ceiling.

### 1. Driver processes — THE ANSWER

Each driver is a separate OS process, its own connection, its own pipeline (one live task per
`project_id`, so they cannot share a file).

| driver processes | aggregate throughput | scaling vs 1 | per-driver rates |
| ---: | ---: | ---: | --- |
| 1 | 3,412/s | 1.00× | [3412] |
| 2 | 6,485/s | **1.90×** | [3327, 3158] |
| 4 | **11,408/s** | **3.34×** | [2960, 2743, 2861, 2844] |
| 8 | 12,510/s | 3.67× | [1721, 1883, 1126, 1801, 1326, 1637, 1074, 1943] |


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

> **CORRECTION — these figures do not reproduce.** Re-measured three times later in the same
> session (including immediately after a clean engine restart): 4 drivers gives **7,871 / 8,540 /
> 8,311 /s** and 8 drivers gives **5,248 / 6,655 /s**. The 11,408 and 12,510 above are ~35 % and
> ~2× optimistic. `pmset -g therm` shows no thermal warning, but the 15-min load average reached
> 20.01 on 14 cores after sustained benchmarking. **Run-to-run variance is at least ±35 %; no
> single-run RocketRide throughput figure is publishable.** See `TIER2_RESULT.md`.
> The *qualitative* conclusion of this document is unaffected: throughput scales with driver
> processes, so the ~2,600/s ceiling was the client, not the engine.

Throughput scales **near-linearly to 4 drivers**, then degrades at 8. A single Python client
process cannot push the engine past ~2,500–3,400/s — its own event loop and GIL are the limit,
not anything on the engine side. That qualitative conclusion is robust across all four runs; only
the absolute level varies.

### 2. Client connections within one driver — NOT the cause

| connections | throughput |
| ---: | ---: |
| 1 | 2,345/s |
| 2 | 2,857/s |
| 4 | 2,535/s |
| 8 | 1,868/s |

Adding sockets inside one process does not help and eventually hurts — consistent with a single
GIL-bound event loop being the constraint, not socket multiplexing. This rules out "one
multiplexed WebSocket is the bottleneck".

### 3 & 4. Payload size and pipeline node count

Not completed this session: the ceiling probe aborted at the driver-process stage on the
"Pipeline is already running" error (each driver needs its own `project_id`), and the targeted
re-run covered only the decisive experiment within the session budget. **Stated, not dropped** —
both remain outstanding, though neither can overturn the driver-process result: a client-side
bottleneck was demonstrated directly.

## What this changes

1. **Every previously reported RocketRide throughput number is a client-side artefact.** The
   `PROCESS_SCALING.md` Model B table reports ~2,600/s flat from n=100 to n=20,000 and attributes
   it to clean engine backpressure. The flatness is real; the *level* is our driver's ceiling. The
   engine sustains ~12,500/s given enough independent clients. That table needs a correction note.

2. **The Step 2 comparison had to be re-run entirely.** `DEPLOYMENT_PARITY.md` concluded
   FastAPI+uvicorn was 6.5× faster using a single-process driver on both sides. Driving both sides
   multi-process (`TIER2_RESULT.md`) gives RocketRide 7,871/s and FastAPI 29,067/s — **FastAPI
   still wins, by 3.69×**. Correcting the driver flaw helped RocketRide in absolute terms but did
   not change the winner.

3. **Benchmark drivers must be validated before their numbers are trusted.** A single-process
   asyncio client saturating at ~3,400 req/s is not unusual, and nothing in the results looked
   wrong — the throughput curve was flat and clean, exactly what a well-behaved saturated server
   produces. The flatness was the client's, and it was indistinguishable from the engine's without
   this experiment.

## Consequences for the sweep design

- The load generator must be **multi-process** (≥4 drivers) for any RocketRide throughput claim.
- Concurrency levels should be expressed as **total in-flight across drivers**, not per-driver.
- The same validation is owed to every Tier 2 framework: the FastAPI numbers in
  `DEPLOYMENT_PARITY.md` came from a single-process `aiohttp` driver and are **very likely
  understated for the same reason**. Until that is re-run multi-process, the Tier 2 comparison is
  not settled in either direction.

## UNVERIFIED

- Payload-size and node-count sweeps not completed (above).
- Where the ~8,000/s saturation itself comes from — engine scheduler, host CPU, or loopback — is
  not established. Per-driver rates degrade from ~2,900 to ~1,500 between 4 and 8 drivers, which
  is consistent with real contention somewhere, but the cause was not isolated.
- All measurements are loopback on one host; drivers and engine competed for the same 14 cores.
  Some of the 8-driver degradation is likely CPU contention with the engine itself rather than an
  engine limit.
