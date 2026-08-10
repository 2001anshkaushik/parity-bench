# STEP 5 — Adversarial Self-Audit: hunting bias that FAVOURS RocketRide

Every harness bug found so far biased *against* RocketRide (processpool's deadline never firing,
asyncio's per-item timer, the single-process load driver). Three-for-three in one direction is
itself a warning sign: it suggests I was only looking in one direction. This pass deliberately
hunts the opposite class.

**Result: 5 real asymmetries found that favour RocketRide, 4 checked and clean.** None of them
overturn the fault-isolation verdict (which is "no separation" — an asymmetry favouring
RocketRide cannot manufacture a null result), but two materially affect throughput and memory
comparisons and must be fixed before publication.

---

## FOUND — asymmetries that favour RocketRide

### A1. RocketRide gets a warm-up send outside the timed region; baselines get none
`run_rocketride()` issues `await c.send(token, payload("warm","ok"))` *before* `t0`. The first
send on a fresh task measured **18.9 ms vs ~2 ms warm** — that ~17 ms of first-call cost is
excluded for RocketRide and included for every baseline.
**Impact:** ~2 % of an 0.8 s RocketRide cell. Small, but it is free money in one direction only.
**Fix:** give every framework an identical discarded warm-up batch, or none.

### A2. ProcessPoolExecutor pays worker-spawn cost *inside* the timed region
`t0` is taken before the `with cf.ProcessPoolExecutor(...)` block, and workers spawn lazily on
first submit. Measured: **9.2 ms construction + 75.0 ms first-use spawn of 14 workers**, all
charged to processpool. RocketRide's engine is already running and warm.
**Impact:** ~84 ms per processpool cell. Against a 20 s deadline it changes no isolation verdict,
but on the sub-second `raise`/`malformed` cells (processpool 0.28–0.31 s vs asyncio 0.08–0.09 s)
it is roughly a quarter of the gap.
**Fix:** pre-spawn the pool before `t0`, as `baselines.py` already does via `_warm_worker`.

### A3. The engine is long-lived and warm across all cells; baselines are rebuilt every cell
RocketRide's engine process persists for the whole session — warm page cache, warm allocator,
warm Python imports inside its node processes. Every baseline constructs its executor fresh in
each cell.
**Impact:** unquantified, but systematically one-directional.
**Note:** this one is partly *legitimate* — a long-running server is how RocketRide is actually
deployed. It must be disclosed rather than "fixed", and the Tier 2 design (both sides behind a
persistent service) is the correct way to neutralise it.

### A4. `preflight()`/`postflight()` run only around RocketRide cells
The matrix calls `eo.preflight()` before each RocketRide cell — which kills orphaned processes and
restarts an unhealthy engine — then runs the three baselines with no equivalent hygiene. RocketRide
effectively gets a cleaned machine; the baselines get whatever state RocketRide left behind.
**Impact:** small on a quiet host (orphans were 0 in every observed preflight), but structurally
biased.
**Fix:** run the same hygiene step before every framework, or before every cell group.

### A5. RocketRide always runs first within each cell group
Order is fixed `rocketride → asyncio → threadpool → processpool`. First position benefits from a
cooler CPU and a quieter page cache; later positions inherit thermal load and whatever memory the
earlier frameworks churned — and the `alloc` cells churn gigabytes.
**Impact:** unquantified. On the `alloc` row, RocketRide runs before three frameworks that
allocate up to 10.9 GB, so it sees the cleanest memory state of the four.
**Fix:** randomise framework order per cell with a fixed seed, as `tier2_settle.py` already does.

---

## FOUND — an asymmetry that favours RocketRide *indirectly*, by handicapping a comparator

### A6. `asyncio.to_thread` silently uses an 18-worker pool, not the 64 the code implies
`run_asyncio()` bounds concurrency with `Semaphore(64)`, which reads as "64-wide". But
`asyncio.to_thread` dispatches to the loop's default executor, whose size is
`min(32, os.cpu_count() + 4)` = **18** on this host (measured directly). The semaphore is not the
binding constraint — the hidden 18-thread pool is.

This is why `asyncio` scored 12.45 on hang@5 % while an explicit `ThreadPoolExecutor(64)` scored
**0.00** on identical input. The asyncio number is an artefact of an undeclared default, and it
made RocketRide's 12.60 look normal when a properly-sized Python pool loses *nothing*.

**This is the most consequential finding in the audit.** It does not change the "no separation"
verdict, but it changes which baseline is the honest comparator: the correct statement is that
RocketRide (width ~17) behaves like a 17-wide pool, and a 64-wide Python pool beats it outright on
this fault class.
**Fix:** pass an explicit executor to `to_thread`, or state the effective width everywhere.

---

## CHECKED — clean

### C1. No hidden retries in the SDK
`RocketRideClient(persist=False)` is the default and the value used everywhere in this suite.
Grepped the SDK for `retry` / `reconnect` / `backoff`: reconnection exists but is gated on
`persist=True`, and there is no send-level retry. RocketRide is not getting free re-attempts the
baselines lack. **Clean.**

### C2. Error counting is symmetric
All four frameworks record a lost item identically as `(False, None)` and score through the same
`score()` function. RocketRide's per-item `error` key is mapped to failure, not silently dropped.
Timeouts, exceptions and missing results are all counted as collateral. **Clean.**

### C3. Correctness verification is symmetric and real
Every framework's clean items are compared against the same `sha256(item_id|filler)` reference.
`collateral_wrong_output` was 0 everywhere, so no framework is being credited for fast-but-wrong
output. RocketRide's engine appends `\n\n` to responses, which `.strip()` normalises — verified
that this does not mask a content difference. **Clean.**

### C4. Connection reuse is not an unfair advantage
RocketRide reuses one WebSocket across all 1,000 items. The in-process baselines have no
connection at all, so there is nothing to equalise — the cost RocketRide pays for having a
transport is already counted against it. In Tier 2 both sides reuse pooled connections
(`aiohttp.TCPConnector` vs one WebSocket), which is the correct comparison. **Clean.**

---

## What this changes

| finding | affects fault-isolation verdict? | affects throughput/memory numbers? |
| --- | --- | --- |
| A1 warm-up | no | yes, ~2 % |
| A2 pool spawn in timed region | no | yes, ~84 ms/cell |
| A3 warm engine | no | yes, unquantified |
| A4 one-sided hygiene | no | marginal |
| A5 fixed order | no | yes on `alloc` |
| A6 hidden 18-thread pool | **no — but changes the honest comparator** | yes |

The fault-isolation verdict is robust to all six: they would inflate RocketRide, and the verdict
is that RocketRide shows **no separation** from expert-tuned baselines. A bias in RocketRide's
favour cannot produce a null result — if anything, correcting these makes RocketRide look slightly
worse, not better.

### A7. (Tier 2, audited after the fact) RocketRide's resource census is honest; FastAPI's is not
`census()` reports FastAPI at `procs=1, threads=1` even with `--workers 14`, while RocketRide is
correctly reported at `procs=2, threads=63`. The comparison "RocketRide 200 MB vs FastAPI 30 MB"
therefore **understates FastAPI's footprint** — i.e. this one runs *against* RocketRide, not for
it, and the memory columns of `TIER2_RESULT.md` must not be used until fixed.

### A8. (Tier 2) Order randomisation worked, and is worth keeping
`tier2_settle.py` shuffles the (target, drivers, workers) combos with a fixed seed. The observed
execution order interleaved RocketRide and FastAPI runs, so neither side systematically occupied
the cool-machine slots. This is the fix that A5 needs applying to the fault matrix.

**Not yet audited:** whether the engine's `\n\n` response suffix costs measurable serialization
the baselines avoid; and whether RocketRide's ~17-wide pool is tunable, which would change whether
the hang result is a defect or a default.
