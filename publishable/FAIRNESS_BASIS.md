# Fairness Basis — which comparison WS-1 actually runs

**Decision record.** Ansh · 2026-08-06. Applies to every number produced from here on, native or
containerised.

---

## The basis: BEST-ACHIEVABLE-CONFIGURATION, both arms

Two defensible bases exist, and they answer different questions:

| basis | question it answers | what it rewards |
| --- | --- | --- |
| out-of-the-box defaults | "what do I get if I install it and run it?" | good defaults |
| **best-achievable configuration** | "what can this framework do if I configure it properly?" | ceiling capability |

**We run best-to-best.** Every arm is tuned as well as we know how, and **any tuning applied to one
arm must have an attempted equivalent on the other**. Where no equivalent exists, that absence is
recorded twice: once as a fairness note here, and once as a toil entry in `TOIL_INSTRUMENT.md`.

**Why this matters right now:** until session 7 we were running best-to-best on one side only. Our
LlamaIndex service has pinned `OMP_NUM_THREADS=1` since it was written; the engine ran at defaults.
That single asymmetry cost the engine ~19 % throughput and most of its concurrency scaling
[`A3_SERIALIZATION_FINDING.md`]. Every RocketRide-versus-LlamaIndex throughput number published
before session 8 was **tuned service versus untuned engine** and is void as a framework comparison.

**Corollary, and it cuts against us:** the defaults comparison is not worthless — it is a real
result that RocketRide's default configuration is bad for concurrent serving while ours is good.
That belongs in the report as a *defaults* finding, clearly separated from the *capability*
comparison. It must not be presented as a framework-throughput difference.

## Tuning inventory — every knob, both arms

### Applied to the LlamaIndex arm

| # | knob | value | why | RocketRide equivalent |
| --- | --- | --- | --- | --- |
| 1 | `OMP_NUM_THREADS` | 1 | avoid intra-op oversubscription across workers | **`OMP_NUM_THREADS=1` at engine start — NOW APPLIED (session 8)** |
| 2 | `MKL_NUM_THREADS` | 1 | as above | same, applied |
| 3 | `OPENBLAS_NUM_THREADS` | 1 | as above | same, applied |
| 4 | `VECLIB_MAXIMUM_THREADS` | 1 | as above (Accelerate on Apple silicon) | same, applied |
| 5 | `TOKENIZERS_PARALLELISM` | false | HF tokenizers fork-safety warning + contention | **NO EQUIVALENT EXPOSED** — the engine's node ships its own tokenizer config |
| 6 | `--workers` | 8 | process-level parallelism; 8 is the *measured* knee (finding 9), not the declared 14 | **NO CONFIG SURFACE** — engine pool width ~17 is not tunable from outside (open item H) |
| 7 | `--loop uvloop` | — | faster event loop | **N/A** — engine's transport is not ours to configure |
| 8 | `--http httptools` | — | faster HTTP parser | **N/A** — same |
| 9 | `--no-access-log` | — | removes per-request logging from the hot path | **UNKNOWN** — engine logging verbosity not investigated |
| 10 | `device=cpu`, asserted at startup | cpu | `mps` has 14–25 % irreducible variance (finding 13) | engine measured to use CPU (finding 7); not a knob we set |
| 11 | model loaded once in `lifespan` | — | keeps model load out of the request path | engine loads per task process; not ours to configure |

### Applied to the RocketRide arm

| # | knob | value | why | LlamaIndex equivalent |
| --- | --- | --- | --- | --- |
| A | thread-limit env vars | 1 | **new in session 8** — closes the asymmetry above | already applied since the service was written |
| B | `SE_CHUNK_SIZE` / `SE_CHUNK_OVERLAP` | 4000 / 200 | matches the splitter config on the other side | set directly in `working/ws1/pipeline.py` |
| C | custom `split_embed` node | — | **compensating for a defect**: the engine silently drops splitter kwargs via `_filter_kwargs_for`, so configuration that appears to apply does not | no equivalent needed — config applies normally |
| D | persistent task per driver | — | mirrors the persistent service on the other side | inherent to a long-running service |

### Knobs with no equivalent — the fairness ledger

| gap | direction | consequence |
| --- | --- | --- |
| **Thread count has no per-pipeline config surface in RocketRide** — only process env at engine start, global to every pipeline on that engine | favours neither once applied globally, but blocks per-workload tuning | fairness: acceptable for a single-workload benchmark. **Toil: recorded** — a multi-tenant deployment cannot give two pipelines different settings |
| **Worker/pool width not tunable in RocketRide** (~17, open item H) | we tuned LlamaIndex's workers to its measured knee (8); we cannot do the equivalent for RocketRide | **This favours LlamaIndex.** Disclosed on every comparison. If item H resolves and width becomes tunable, RocketRide must be re-tuned and the anchors re-measured |
| **`TOKENIZERS_PARALLELISM` not exposed** | unknown magnitude, untested | logged; likely small next to thread pinning |
| **Engine access-log/verbosity not investigated** | unknown | logged as an open tuning item |
| **Splitter kwargs silently dropped** | required writing a custom node to reach parity | fairness: parity restored. **Toil: recorded** |

## Rules that follow from the basis

1. **Symmetric attempt.** Before applying a knob to one arm, an equivalent must be sought on the
   other and the outcome recorded — applied, no surface, or not applicable. Silence is not allowed.
2. **Measured, not declared.** A tuning is only "applied" once measured in effect. Thread pinning is
   verified inside the task process via `working/nodes/env_probe` (`torch.get_num_threads()`), because torch
   caches its thread count at import and an exported variable proves nothing on its own. The
   LlamaIndex worker count was likewise measured (8) rather than trusted (14).
3. **Tuning is frozen before measurement.** Knobs are not adjusted after seeing results. Any change
   requires re-running both arms.
4. **Every published comparison names its basis** — "best-to-best" or "defaults" — and never mixes
   them in one table.
5. **A tuning that helps one arm and has no equivalent is disclosed at the point of use**, not only
   here.

## Known residual asymmetries — disclose with any result

| # | asymmetry | who it favours | status |
| --- | --- | --- | --- |
| 1 | LlamaIndex workers tuned to a measured knee; RocketRide pool width not tunable | **LlamaIndex** | open item H |
| 2 | ~~`torch_num_interop_threads` stays 14 when pinned~~ | **CLOSED 2026-08-07 — favours nobody** | Tested: `torch.set_num_interop_threads(1)` inside the node lands (inter 14→1, verified in-process) but **costs 14.3 % at conc 8** (32.00 vs 37.34 /s) and does nothing at conc 2 (0.999×). **Leave inter-op at default.** `working/results/anchor_b_interop.json` |
| 3 | Engine torch 2.10.0 vs service torch 2.13.0 | unknown | different embedded stacks; not reconcilable without rebuilding the engine |
| 4 | I build and tune one arm; Shashi builds the other | **LlamaIndex** | conflict declared in `TOIL_INSTRUMENT.md` §1 |

**Asymmetry 2 is CLOSED (2026-08-07).** `SE_INTEROP_THREADS` was wired into `working/nodes/split_embed`,
calling `torch.set_num_interop_threads()` before the model loads, and the node reports the result
from inside the task process: `inter_before 14 → inter_after 1, interop_set "ok"`. Measured at
1,600 tokens:

| concurrency | inter=1 | inter=14 (default) | effect |
| ---: | ---: | ---: | ---: |
| 2 | 21.99 /s | 22.01 /s | 0.999× — none |
| 8 | 32.00 /s | 37.34 /s | **0.857× — pinning COSTS 14.3 %** |

Drift null control held (LlamaIndex spread 0.7 % / 4.8 % across blocks), so the 14.3 % is real.
**Verdict: the engine's inter-op default is correct and constraining it is harmful.** This removes
a knob rather than adding one, which is a result that goes *against* RocketRide's best case — it
had one fewer tuning option than we assumed, not one more.

**Consequence for the tuning inventory:** the RocketRide arm's best configuration is
`intra=1, inter=default` above concurrency ~4, and full defaults below it.

## CANONICAL PIPELINE — fixed 2026-08-07, closes open item A11

**Decision: the 4-node `embed_probe.pipe` is canonical for every RocketRide measurement.**

Session 8 measured Anchor B on the 4-node pipeline (ratio 1.201); session 9 measured it on the
1-node `single_node.pipe` (ratio 1.352) and compared the two across that change. They are not
comparable, and this fixes which one counts.

| | 4-node `embed_probe.pipe` | 1-node `single_node.pipe` |
| --- | --- | --- |
| built from | **shipped engine components** (`webhook → preprocessor_langchain → embedding_transformer → response_documents`) | a **custom node we wrote** (`working/nodes/split_embed`) |
| why it exists | it is what a user assembles from the product | a **workaround**: the engine silently drops splitter kwargs via `_filter_kwargs_for`, so chunk size could not be varied any other way |
| response payload | **full embedding vectors** (9–24 KB) | **159-byte summary** (vector dimensions only) |

**Two independent reasons, either sufficient:**

1. **It is what a real user would deploy.** The 1-node version is a benchmark artifact of our own
   making. Benchmarking it would measure a pipeline no customer has.
2. **Payload symmetry.** The LlamaIndex service returns full vectors. The 1-node node returns a
   159-byte summary, so using it hands RocketRide a payload advantage — the confound already
   disclosed in session 5 and retired only because response size was separately shown not to
   matter at those rates. Removing the confound entirely is better than relying on that.

**This is WORKLOAD DEFINITION, not a tuning knob.** It sits with chunk size, model identity,
device and the wire contract in the "fixed by construction" list below. It is not adjusted to
improve a result, and changing it invalidates every comparison measured under it.

**`working/nodes/split_embed` is retained as a diagnostic instrument** — it is the only way to vary chunk
size on the RocketRide side, and it is how the topology and chunk-count questions were answered.
Any number produced with it is labelled *diagnostic, non-canonical* and never enters a head-to-head.

### Comparability banner required on prior numbers

| measurement | pipeline used | status |
| --- | --- | --- |
| Session 8 Anchor B — RR/LI **1.201** [1.185, 1.217] @1600tok/c2 untuned | 4-node | **canonical — stands** |
| Session 9 Anchor B — RR/LI **1.352** @1600tok/c2 untuned | 1-node | **NON-CANONICAL** — do not quote as an anchor; retained as the interop experiment's internal control |
| Session 9 interop effect (0.999× @c2, 0.857× @c8) | 1-node | **stands** — it is a within-pipeline A/B, so the topology cancels |
| Session 5 topology and chunk-count findings (1d, 1e, 1f) | both, deliberately | **stand** — comparing the pipelines *was* the experiment |


## MATCHED CONFIGURATION FOR THE CONCURRENCY-1 REPLICATION — fixed 2026-08-10

**Decision: both arms run UNPINNED (torch default threads) at concurrency 1 sequential.**

"Default" is the absence of a configuration, not a configuration, and two stacks' defaults are not
matched by construction. So the setting was **chosen on measurement**, per arm, on the actual
GovDocs corpus, interleaved and repeated (n=3), each arm compared only against itself within one
session — the one comparison this host can still answer despite open item A13.

| arm | unpinned (default) | pinned to 1 | ratio | spread | best at concurrency 1 |
| --- | ---: | ---: | ---: | ---: | --- |
| RocketRide | **12.102 docs/s** | 3.945 | **3.07×** | 3.0 % / 0.4 % | **unpinned** |
| LlamaIndex | **10.673 docs/s** | 3.275 | **3.26×** | 2.2 % / 5.8 % | **unpinned** |

All four cells pass the 10 % variance gate. Evidence:
`working/results/thread_choice_rocketride__*.json`, `working/results/thread_choice_llamaindex__*.json`.

**Why this is genuinely matched, not merely identical-looking:** both arms end up with
`torch.get_num_threads() == 10`, verified **inside** each process — the engine's task process via
`nodes/env_probe`, the LlamaIndex process by direct interrogation. Pinning is the correct choice
only above roughly concurrency 4 (see `A3_SERIALIZATION_FINDING.md`); at concurrency 1 it starves
both arms of intra-op parallelism, and it costs them almost exactly the same factor.

**Declared ≠ measured is enforced at run start.** The replication refuses to begin unless both
arms report the same in-process thread count. Two configuration fixes in this project have
silently failed before (a PID lookup that fell back to name matching; an `rm` that never cleared
state), so the check is an assertion, not a comment.

## What is NOT tuning, and stays fixed

Chunk size/overlap, model identity and revision, device, document corpus, and the wire contract are
**workload definition**, not tuning. They are identical on both arms by construction and changing
one for one arm invalidates the comparison outright.
