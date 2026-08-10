# STEP 2 — Deployment Parity

**The service boundary costs +5.3 to +9.7 ms at p50 and cuts throughput to ~20–26 % of
in-process. That is large enough that comparing RocketRide to in-process Python was never
defensible.** The Tier 2 comparison drawn here was later corrected by Step 3 — see the corrected
section below; the wrapper-overhead measurements themselves stand.

Raw data: `results/deployment_parity/deployment_parity.json`. Wrapper: `wrappers/asyncio_service.py`.

---

## The problem this fixes

Every RocketRide number collected so far includes a WebSocket round trip to a separate process.
Every in-process Python number does not. That gap runs *against* RocketRide, so the fix is
structural rather than a footnote.

| | Tier 1 — in-process | Tier 2 — service behind a socket |
| --- | --- | --- |
| Members | asyncio, ProcessPoolExecutor, ThreadPoolExecutor, langgraph, crewai | **RocketRide engine** vs each framework behind FastAPI+uvicorn |
| Boundary | none | HTTP/socket, separate process, real serialization |
| Role | upper bound on the language runtime | **the headline comparison** |

**RocketRide has no Tier 1 entry. This is a stated limitation, not an omission.** The engine is a
standalone server; there is no in-process embedding mode. Any Tier 1 chart therefore shows Python
frameworks only, and RocketRide must never be placed on it — including by a reader who assumes the
missing bar means "too slow to plot".

## Measured wrapper overhead

Same work unit (sha256 digest), same driver, n=2,000 at concurrency 200.

| configuration | throughput | p50 | p95 | p99 | errors | wrapper RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Tier 1** in-process, no boundary | **64,714/s** | 2.096 ms | 3.043 ms | 3.334 ms | 0 | — |
| Tier 2 · uvicorn 1 worker | 12,862/s | 11.796 ms | 23.313 ms | 24.725 ms | 0 | 61.3 MB |
| Tier 2 · uvicorn 4 workers | 16,316/s | 11.640 ms | 25.779 ms | 28.066 ms | 0 | 30.3 MB |
| Tier 2 · uvicorn 14 workers | **16,827/s** | **7.444 ms** | 18.752 ms | 30.237 ms | 0 | 30.4 MB |

**Overhead attributable to the boundary alone:**

| workers | p50 added | p99 added | throughput retained |
| --- | ---: | ---: | ---: |
| 1 | +9.700 ms | +21.391 ms | 19.9 % |
| 4 | +9.544 ms | +24.732 ms | 25.2 % |
| 14 | **+5.348 ms** | +26.903 ms | **26.0 %** |

Adding workers beyond 4 buys little throughput (16,316 → 16,827/s) but halves p50 (11.6 → 7.4 ms)
by removing queueing at the accept loop. p99 *worsens* slightly with more workers — more workers
means more scheduling variance in the tail.

## Tuning — what was set and why

Defaults would have made this a strawman. Per uvicorn's own deployment guidance:

| flag | value | why |
| --- | --- | --- |
| `--workers` | 1 / 4 / 14 | uvicorn is single-process by default; production runs one per core. Swept rather than assumed. |
| `--loop` | `uvloop` | uvicorn's recommended loop; materially faster than the asyncio default. |
| `--http` | `httptools` | C parser; the pure-Python `h11` fallback is slower. |
| `--no-access-log` | on | per-request logging is a well-known throughput tax, off in production. |
| `--limit-concurrency` | unset | so backpressure is the server's own behaviour, not a cap we imposed. |

The wrapper returns faults as **200-with-error payloads**, matching how RocketRide reports a node
exception (a per-item `error` key). Making one side raise a transport error and the other return a
payload error would measure the error convention rather than the system.

## The result that matters — CORRECTED BY STEP 3

This section originally concluded that FastAPI+uvicorn (16,827/s) was **6.5× faster** than
RocketRide (~2,600/s). **That conclusion was wrong.** Step 3 (`CEILING.md`) showed the ~2,600/s
figure was our single-process client's own limit, not the engine's: with 4 independent driver
processes RocketRide sustains **11,408/s**, saturating near **12,510/s**.

| | throughput | driver |
| --- | ---: | --- |
| FastAPI+uvicorn, 14 workers | 16,827/s | single-process `aiohttp` |
| RocketRide engine | 12,510/s | 8 driver processes |

The honest gap is **1.35×, not 6.5×** — and even that is not settled, because the FastAPI number
came from a **single-process driver**, exactly the flaw that produced the original error. Applying
the same correction to the Python side would very likely raise it too. **Until both sides are
driven multi-process, Tier 2 is unresolved in either direction and must not be published.**

Note the tension with Step 1: the FastAPI wrapper runs the work **in-process**, so a single
interpreter crash takes every in-flight item with it — a failure mode RocketRide's separate engine
process does not share. Throughput and blast radius trade against each other here, and the report
must show both.

## UNVERIFIED

- **`wrapper_processes` reads 1 for every worker count**, which cannot be right for
  `--workers 14`. The detector matches on `uvicorn` + `asyncio_service` in the cmdline and is
  evidently missing forked children. Wrapper RSS (61.3 → 30.4 MB) is therefore also suspect —
  it likely reports the master only. **The process/memory column of this table is not
  trustworthy; the latency and throughput columns are.** Needs a process-tree walk like the one
  `harness/collector_proc.py` already implements.
- Only `asyncio` has a reference wrapper. langgraph and crewai wrappers are specified but not
  built (out of scope this run).
- Single host, loopback networking. A real deployment crosses a NIC, which would add latency to
  *both* tiers but not necessarily symmetrically.
