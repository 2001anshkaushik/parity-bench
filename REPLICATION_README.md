# Matched Replication — what this run can and cannot establish

**Written BEFORE any results exist, so it cannot be retrofitted.** Launched 2026-08-10.

## Why it exists

The 10,000-document endurance comparison had two defects: the arms ran with **different thread
counts** (RocketRide 1, LlamaIndex 10) and the two runs were **two days apart**. Neither defect
touches goodput or fault classification, but both make a ratio claim unsafe.

## Configuration — matched on evidence, not by assumption

Both arms: **unpinned (torch default = 10 intra-op threads), concurrency 1, sequential.**
Chosen by measuring each arm against *itself* on this corpus (n=3, interleaved, all cells
gate-passing): unpinned beats pinned by **3.07×** for RocketRide and **3.26×** for LlamaIndex, so
unpinned is each arm's own best setting at this concurrency and the two coincide.
Full reasoning: `publishable/FAIRNESS_BASIS.md`.

**The run refuses to start unless both arms report the same in-process thread count**, read from
the engine's task process and the LlamaIndex process. It also refuses if both are pinned to 1 —
matched but not best.

## Design

2,000 documents per block · **3 blocks per arm** · **interleaved A-B-A-B-A-B** with the pair order
randomised per round (seeded) · machine **pre-warmed before every block** · first 50 documents
excluded from every median · both arms gated at 10 % spread · **a gate needs n ≥ 3** (a
single-block spread is identically zero and would pass trivially).

## CAN establish

* **Matched memory ratio** with per-arm spread, under a configuration that is each arm's best.
* **Matched goodput and fault classes** on identical documents in identical order.
* **Stability under a matched configuration** — whether RocketRide's run-to-run memory spread
  persists once the thread asymmetry is removed.

## CANNOT establish

* **A quotable throughput comparison.** Open item A13 is a property of this host: cold-versus-warm
  ordering alone moves results 2.2×. No configuration fixes it. Wall clock is recorded as **run
  cost**, never as a benchmark, and the field in the result JSON is named
  `docs_per_s_RUN_COST_ONLY` so it cannot be quoted by accident.
* **Anything about Linux.** Every measurement is macOS/arm64.
* **Anything about concurrency > 1.** This run is sequential by design; the thread choice above is
  correct *at concurrency 1* and would invert above roughly concurrency 4.

## Where results land

`working/results/matched_replication__<UTC>__<hash>.json` · per-block checkpoints in
`repl_state/` · log `repl_logs/replication.log` · live status `repl_status.txt`.

```bash
cat repl_status.txt          # one-line progress
```
