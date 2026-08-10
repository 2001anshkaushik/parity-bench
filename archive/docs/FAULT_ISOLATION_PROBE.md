# STEP 1 — Fault Isolation Probe

**Verdict: the fault-isolation headline SURVIVES, stated precisely. RocketRide Model B isolates
exceptions, 512 MB allocation spikes and lane contract violations with ZERO collateral damage and
zero silent corruption — matching, not beating, expert-tuned Python. Concurrent hangs degrade
RocketRide, `asyncio` and `ProcessPoolExecutor` by the same amount (9.1–10.0 collateral per
fault); that is a queueing property, not a differentiator.**

Engine `3.3.1.35`, Model B n=1,000, four fault classes × three rates, identical injection plan and
identical work unit across every framework via the `fault_probe` node and its Python twin.
Raw data: `results/fault_isolation/`.

---

## What this probe was correcting

The earlier inference — *"Model B keeps one process, therefore no blast-radius containment"* —
conflated **process isolation** with **fault isolation**. They are different things: a dataflow
lane can catch a per-item error and keep the batch alive with no process boundary anywhere. That
inference was wrong, and this probe is what shows it.

**Fault isolation ratio** = collateral damage per injected fault, where collateral counts clean
items that failed, went missing, *or returned a wrong digest*. Every clean item's output is
verified against a single-threaded reference, so a framework that stays up while silently
corrupting survivors cannot score well.

## Result — RocketRide Model B (one pipeline, n=1,000)

| fault | rate | injected | returned | collateral | **ratio** | goodput | engine healthy after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| raise | 0.1 % | 0 | 1000 | 0 | **0.00** | 100 % | ✅ |
| raise | 1 % | 8 | 1000 | 0 | **0.00** | 100 % | ✅ |
| raise | 5 % | 46 | 1000 | 0 | **0.00** | 100 % | ✅ |
| alloc (512 MB each) | 0.1 % | 1 | 1000 | 0 | **0.00** | 100 % | ✅ |
| alloc | 1 % | 8 | 1000 | 0 | **0.00** | 100 % | ✅ |
| alloc | 5 % | **57** | 1000 | 0 | **0.00** | 100 % | ✅ |
| malformed (lane type violation) | 0.1 % | 0 | 1000 | 0 | **0.00** | 100 % | ✅ |
| malformed | 1 % | 13 | 1000 | 0 | **0.00** | 100 % | ✅ |
| malformed | 5 % | 47 | 1000 | 0 | **0.00** | 100 % | ✅ |
| hang | 0.1 % | 0 | 1000 | 0 | **0.00** | 100 % | ✅ |
| hang | 1 % | 9 | 1000 | 0 | **0.00** | 100 % | ✅ |
| **hang** | **5 %** | **44** | 1000 | **608** | **13.82** \* | **36.4 %** | ✅ |

\* first-pass figure, superseded by the symmetric-deadline re-run below (**9.24**). The
asymmetric-deadline bug is documented under "Two harness bugs".

Eleven of twelve cells are a perfect 0.00. The engine reports a node exception as a **per-item
`error` key on an otherwise normal response** — the batch is never torn down, sibling items are
untouched, and no survivor is corrupted. **57 concurrent 512 MB allocations** (≈29 GB of churn)
also produced zero collateral and left the engine healthy.

The single failure is **hangs at 5 %**: 44 hung items cost 608 clean ones.

## Why hangs behave differently

Exceptions, bad allocations and contract violations all *terminate* — the item finishes, fails,
and releases its slot. A hang **holds its slot for the full duration**. Once enough slots are
held, clean items queue behind them and miss the client deadline. This is worker-pool starvation,
not a fault-containment defect, and it is exactly the blast radius the earlier process-count
argument was groping at — just mediated by pool occupancy rather than process death.

Note the threshold behaviour: 1 % (9 hangs) is completely absorbed; 5 % (44 hangs) collapses
goodput to 36 %. The ratio is a function of `concurrent hangs ÷ effective pool width`, **not a
pure property of the framework** — and the comparative table below confirms exactly that: every
framework lands in the same 9–10 band once the deadline is applied symmetrically.

## Comparative — identical injection, identical 20 s per-item deadline

| fault @ 5 % | RocketRide Model B | asyncio | ProcessPoolExecutor |
| --- | ---: | ---: | ---: |
| raise | **0.00** | 0.00 | 0.00 |
| alloc | **0.00** | 0.00 | 0.00 |
| malformed | **0.00** | 0.00 | 0.00 |
| hang (symmetric deadline) | **9.24** | 9.11 | 9.97 |
| — goodput | 34.7 % | 35.7 % | 29.6 % |

On everything that terminates, RocketRide ties the Python baselines at a perfect 0.00. **On hangs
all three are statistically indistinguishable (9.1–10.0).**

### Two harness bugs found and corrected here — both had produced false verdicts

The first pass reported RocketRide 13.82 vs asyncio 1.95 vs processpool 0.00, and I drew the
conclusion "RocketRide is ~7× worse than asyncio at absorbing hangs". **That conclusion was
wrong, and it was wrong because of the harness, twice over:**

1. `ProcessPoolExecutor` called `fut.result(timeout=…)` inside `as_completed()`, which only ever
   sees futures that have *already* completed — the deadline never fired at all. It ran to 100 s
   and scored a fictitious perfect 0.00 while RocketRide's items were killed at 20 s.
2. The asyncio path started its 20 s timer when an item *acquired the semaphore*, not at batch
   start. Items that queued behind hangs therefore each got a fresh 20 s, so asyncio was
   effectively given a far longer deadline than RocketRide's wall-clock 20 s.

Re-run with ONE wall-clock deadline enforced identically for all three
(`scripts/hang_symmetry_fix.py` → `results/fault_isolation/hang_symmetric.json`), the difference
disappears entirely. **Hang collateral is a queueing property — a function of concurrent hangs
versus effective pool width — not a property that distinguishes these frameworks.**

Both bugs happened to run *against* RocketRide. The lesson generalises: deadline semantics must be
identical across frameworks, or the isolation ratio measures the harness rather than the system.

## Model A (N pipelines, n=100) — CONFOUNDED, not usable

| fault @ 5 % | injected | returned | collateral_failed | collateral_wrong | ratio | wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raise | 3 | 100 | 97 | 0 | 32.33 | 57.4 s |
| hang | 2 | 100 | 98 | 0 | 49.00 | 58.0 s |

**These numbers do not measure fault isolation and must not be reported as if they did.** Model A
spends ~50 s launching 100 pipelines (0.5 s each, largely serialised); the 20 s per-item deadline
then fires while the engine is still saturated with setup, so essentially every clean item times
out regardless of any injected fault. The tell is that `collateral_wrong_output = 0` in both
cells — nothing was corrupted, everything simply missed its deadline.

A valid Model A measurement needs the deadline to start *after* setup completes, with setup
excluded from the timed region. Not re-run inside this session's budget; recorded as outstanding.

## Verdict on the headline claim

**Keep fault isolation as the headline, but state it precisely:**

> Under partial failure, RocketRide contains item-level faults with zero collateral damage and
> zero silent corruption — for faults that terminate. Injected exceptions, 512 MB allocation
> spikes and lane contract violations at rates up to 5 % cost exactly zero clean items and leave
> the engine healthy.

That claim is true, verified against a correctness reference, and matched (not beaten) by
expert-tuned Python on the same three classes.

**What must ship alongside it:** at a 5 % hang rate every framework tested — RocketRide, asyncio
and ProcessPoolExecutor alike — loses roughly 9–10 clean items per hung item and drops to ~30–36 %
goodput. Nobody handles this well, and RocketRide is neither better nor worse. Claiming an
advantage here would not survive a re-run; so would claiming a deficit.

**The strongest honest framing is not "we isolate faults better".** It is: *RocketRide matches
expert-tuned Python on fault containment — zero collateral on every terminating fault class — and
does it behind a service boundary rather than in-process. Concurrent hangs degrade every framework
equally and are an unsolved problem for all of them without an explicit shed/timeout policy.*

## UNVERIFIED / outstanding

- The effective pool width of a RocketRide task is not established, so the hang threshold cannot
  be predicted from configuration — only measured. Engine reports 24 OS threads; the relationship
  to `threadCount: 64` in task config is still unknown.
- Whether a client-side or node-side timeout would let RocketRide shed hung items and recover its
  goodput. If so the weakness is a configuration gap, not an architectural one — worth one
  experiment before publication.
- Model A fault isolation: confounded here; needs setup excluded from the timed region.
- **Seeds are not reproducible across processes.** The fault plan uses `hash((fault, rate))`, and
  Python salts string hashing per interpreter, so injected counts differ between runs (44 vs 66
  hangs at the same nominal 5 %). Comparisons *within* a run are valid — all frameworks share one
  plan — but absolute counts are not reproducible run-to-run. Fix before publication: a fixed
  integer seed, not `hash()`.
- Only one work unit (digest) and one payload size were tested. A heavier per-item workload would
  change pool occupancy and therefore the hang threshold.
