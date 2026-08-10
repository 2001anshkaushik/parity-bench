# STEP 2 — Tier 2 Settled: RocketRide vs FastAPI+uvicorn

## Winner: **FastAPI + uvicorn — but by 2.4×, not the 3.7× first reported.**

> **Headline revised 2026-08-05 (session 3).** RocketRide's peak in the table below (7,871.6/s) was
> measured without the variance protocol and does not reproduce. Under protocol (n=5, warmup
> discarded, randomised) the engine measures **12,313.5/s at 4 drivers, spread 1.7%**. Recomputed
> against FastAPI's 29,066.9/s the ratio is **2.36×, not 3.69×**. FastAPI still wins this synthetic
> comparison; the margin was overstated by ~56%. The FastAPI side has NOT been re-measured under
> protocol either, so the corrected ratio is itself **PROVISIONAL** — see "Still outstanding".

Both sides driven by the **same multi-process driver**, same driver-count sweep, same payload,
same per-driver concurrency, same machine, same session, **randomised order**. This is the
apples-to-apples comparison; the earlier single-process-driver result is superseded.

Raw data: `results/tier2/tier2.json`.

---

## Results

1,500 items per driver, concurrency 250 per driver.

### RocketRide engine

| drivers | throughput | p50 | p99 | procs | threads | RSS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2,700.8/s | 80.8 ms | 117.8 ms | 2 | 63 | 199.8 MB |
| 2 | 5,003.4/s | 83.3 ms | 137.5 ms | 2 | 63 | 199.8 MB |
| **4** | **7,871.6/s** | 121.1 ms | 163.2 ms | 2 | 63 | 199.9 MB |
| 8 | 5,248.0/s | 374.7 ms | 585.4 ms | 2 | 63 | 200.5 MB |

### FastAPI + uvicorn

| drivers | workers | throughput | p50 | p99 | RSS\* |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 10,484.1/s | 18.3 ms | 63.2 ms | 30.4 MB |
| 2 | 4 | 20,416.3/s | 12.1 ms | 62.3 ms | 30.3 MB |
| 4 | 4 | 16,703.6/s | 11.6 ms | 340.7 ms | 30.3 MB |
| 8 | 4 | 21,192.7/s | 14.0 ms | 1,077.1 ms | 30.3 MB |
| 1 | 14 | 12,010.7/s | 12.6 ms | 49.6 ms | 30.4 MB |
| 2 | 14 | 24,261.1/s | 12.5 ms | 44.8 ms | 31.0 MB |
| **4** | **14** | **29,066.9/s** | **10.7 ms** | 197.2 ms | 31.0 MB |
| 8 | 14 | 5,806.3/s | 18.1 ms | 1,094.7 ms | 30.4 MB |

\* **RSS and process counts for FastAPI are not trustworthy** — the census reports `procs=1,
threads=1` even at `--workers 14`, so it is counting the master only. Carried over from
`DEPLOYMENT_PARITY.md`; still unfixed. The throughput and latency columns are sound.

## Head to head, each at its own best configuration

| | RocketRide | FastAPI+uvicorn | ratio |
| --- | ---: | ---: | ---: |
| peak throughput ~~(pre-protocol)~~ | ~~7,871.6/s~~ | 29,066.9/s | ~~3.69×~~ |
| **peak throughput (protocol applied to RocketRide only)** | **12,313.5/s** [VERIFIED n=5, 1.7% spread] | 29,066.9/s [PROVISIONAL, n=1] | **2.36× — PROVISIONAL** |
| p50 at peak | 121.1 ms | **10.7 ms** | **11.3× lower** |
| p50 at 1 driver | 80.8 ms | 12.6 ms | 6.4× lower |
| p99 at peak | 163.2 ms | 197.2 ms | comparable |

FastAPI wins throughput at every driver count and latency at every driver count. RocketRide's
only relative strength here is **p99 stability**: its tail stays under 600 ms across the whole
sweep, while FastAPI's p99 blows out to ~1.1 s at 8 drivers where the process count (8 drivers +
14 workers = 22) oversubscribes 14 cores.

## Both sides have a knee, and both are past it at 8 drivers

- **RocketRide** peaks at 4 drivers (7,872/s) and *loses 33 %* at 8 (5,248/s), with p50 tripling
  to 375 ms. It does not simply plateau — it degrades.
- **FastAPI/14 workers** peaks at 4 drivers (29,067/s) and collapses 80 % at 8 (5,806/s).
- **FastAPI/4 workers** is the more robust configuration: 21,193/s at 8 drivers, no collapse.

More uvicorn workers is better up to the core count and worse beyond it, exactly as uvicorn's
deployment guidance implies. The 14-worker peak is the highest number measured; the 4-worker
configuration is what I would actually ship.


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

## Reproducibility problem — flagged, not hidden

`CEILING.md` reported RocketRide at **11,408/s (4 drivers)** and **12,510/s (8 drivers)**. Those
numbers **do not reproduce**. Re-measured twice this session, including immediately after a clean
engine restart:

| run | 4 drivers | 8 drivers |
| --- | ---: | ---: |
| CEILING.md (earlier session state) | 11,408/s | 12,510/s |
| Tier 2 sweep (randomised order) | 7,871/s | 5,248/s |
| driver_scaling re-run (engine as-is) | 8,540/s | — |
| driver_scaling re-run (fresh engine) | 8,311/s | 6,655/s |

Three consecutive measurements cluster at **7,900–8,500/s at 4 drivers**; the earlier 11,408 is a
~35 % outlier and the 8-driver figure differs by ~2×. `pmset -g therm` records no thermal warning,
but the 15-minute load average was **20.01 on 14 cores** after ~40 minutes of continuous
benchmarking — the host was not quiet.

**Consequence, as revised:** the ±35% turned out to be *between-session* wobble, not irreducible
noise. Within a session under protocol the engine is stable to 1.7%. The Tier 2 winner is
unchanged — 12,313/s still loses to 29,067/s — but the margin is **2.36×, and that number is
PROVISIONAL** because only one side has been re-measured under protocol.

## Still outstanding

**The FastAPI side of this table is still n=1, pre-protocol.** Re-measuring it would take ~20 min
and could move the ratio in either direction. Until then, quote the comparison as "FastAPI faster
on a synthetic payload, roughly 2-3×, PROVISIONAL" and not as a precise figure. Logged as an open
item under the stopping rule — it is not load-bearing for WS-1, which uses the real embedding
workload where this comparison is expected not to transfer at all.

## What this does and does not say

**Does:** for a trivial request/response work unit over loopback, a tuned FastAPI+uvicorn service
moves 3.5× more requests per second at a tenth the median latency, using a fraction of the
resident memory.

**Does not:** say anything about workloads with real per-item work. This unit is a sha256 digest
— under a microsecond. The measurement is almost entirely transport, scheduling and serialization
overhead, which is precisely where a Python HTTP stack is strongest and where RocketRide's
per-item WebSocket/DAP round trip and ~17-wide task pool are weakest. A workload with 50 ms of
real work per item would compress this gap substantially and is the more ICP-representative test.

**Also does not:** account for the fault-tolerance difference. The FastAPI wrapper executes work
in-process, so an interpreter crash takes all in-flight items; RocketRide's separate engine
process does not share that failure mode. Throughput and blast radius trade against each other
and both belong in the report.
