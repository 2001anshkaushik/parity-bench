# WS-1 Service Parity — start here

**Read this file first. Nothing else in this repository is a safe entry point.**
Last updated 2026-08-07.

---

## What this is

A measurement project comparing the **RocketRide engine** against a **LlamaIndex FastAPI service**
on an identical document split-and-embed pipeline, plus the instrumentation built to make that
comparison trustworthy. Ansh owns the LlamaIndex arm; Shashi owns the RocketRide service; Leela
owns the shared schema and the mt10k reference corpus.

**Nothing here has been sent to the team.** Every shared document is still a draft.

## ⚠️ Read this before quoting any number

This project has withdrawn more findings than it has kept. The instrument has been wrong more often
than the systems under test: a collector that biased results 100×, a driver that understated
throughput 4.8×, asymmetric deadlines that manufactured a 7× gap, and most recently an
**ascending concurrency sweep that under-measured by 2.2× because it profiled a machine in a
low-power state**.

**Consequences for a reader:**

* **All saturation points are withdrawn** (session 11). Any statement of the form "X saturates at
  concurrency N" in this repository is either archived or explicitly marked withdrawn.
* **The headline throughput comparison is withdrawn** and not replaced. The optimal-point
  comparison rested on saturation figures that no longer stand.
* `archive/` contains the superseded material. It is preserved deliberately — the correction
  history is the most reliable thing here — but **nothing in `archive/` may be quoted**.

## What currently stands

Every claim below is labelled. Anything unlabelled anywhere in this repo should be treated as
UNVERIFIED.

| finding | label | evidence |
| --- | --- | --- |
| The engine is **not** the concurrency bottleneck: request path scales 3.69×, Python-node dispatch costs ~3 %, pure-Python CPU in a node scales 3.59×; only the embedding arm is flat | **VERIFIED** | `working/results/a3_serialization.json` |
| Cause is **native thread oversubscription**. Pinning BLAS/torch threads changes scaling 1.46× → 3.19× and adds ~19 % throughput at concurrency 8, costing ~1.8× single-request latency | **VERIFIED** (intervention + CPU accounting, pure-Python null control unmoved) | `working/results/a3_threads.json` |
| Pinning torch **inter-op** threads is harmful: −14.3 % at concurrency 8, no effect at 2 | **VERIFIED** | `working/results/anchor_b_interop.json` |
| RocketRide effective pool width **17.24** | **VERIFIED** (guarded instrument, escaped tracking, confirmed by doubling) | `working/results/anchor_c_width.json` |
| LlamaIndex has **no single pool width** — sleeping holds do not occupy a worker (`/process` is a sync `def` on Starlette's threadpool). The instrument refused rather than reporting a number | **VERIFIED** | `working/results/anchor_c_width.json` |
| Neither service decays under sustained load (RR +1.5 %, LI +1.0 % median, n=3 randomised, 0 failures) | **VERIFIED** (2 methods) | `working/results/decay_symmetric.json` |
| Peak RSS: RocketRide 204 MB idle → 2,356 MB; LlamaIndex **4,642 MB idle** → 7,950 MB. Different memory *shapes* — LI's floor scales with worker count, RR grows with document size | **VERIFIED** (continuous 250 ms sampling) | `working/results/memory_ceiling.json` |
| Custom Python **parse** nodes run in the engine — Tika is a default, not a constraint | **VERIFIED** (executed; byte-identical to standalone pypdf) | `working/nodes/pdf_probe/` |
| PyMuPDF is **AGPL-3.0** / Artifex commercial; pypdf is BSD-3 and is LlamaIndex's own default | **VERIFIED** (package metadata) | `working/dossiers/` |
| Ascending concurrency sweeps under-measure by up to 2.2×; pre-warming reproduces descending order | **VERIFIED** (3 orderings) | STATE.md §4b |
| LlamaIndex saturates at **c16, ~226 /s @400 tok** when pre-warmed | **PROVISIONAL** (1 run) | `working/results/isolated_profile_llamaindex_PREWARM.json` |

## What was withdrawn, and why

| withdrawn | why |
| --- | --- |
| "LlamaIndex 1.73× faster" | artifact of a ~210-token test document; corpus median is 338 |
| "RocketRide decays 31 % under sustained load" | did not reproduce; n=1 from a statistic whose noise band is ±12–18 pp, with no control arm |
| The sustained token curve | rested on that decay |
| "RocketRide ~2,600 /s ceiling" | client-bound, not engine-bound |
| The ±35 % variance "correction" | **the correction was itself wrong** — the original number was right |
| "RocketRide arm is systematically noisier" | our own harness desynchronisation |
| Tier 2 "FastAPI 3.69× faster" | pre-protocol; recomputed 2.36× and still PROVISIONAL |
| All saturation points, and the optimal-point comparison | ascending cold sweeps (session 11) |

Full supersession history, with dates and evidence, is in **`STATE.md` §5**. That is the only place
withdrawn numbers legitimately appear outside `archive/`.

## Layout

```
publishable/   this directory — push-ready docs, every number labelled and traceable
  STATE.md          durable resume point + full supersession history  <- the reference
  INVENTORY.md      file-by-file classification and the withdrawn-number register
  PROVISIONING.md   what a fresh clone lacks and how to restore it
  ENVIRONMENT.md    pinned versions, engine SHA256
  VARIANCE_PROTOCOL.md / FAIRNESS_BASIS.md    how measurements are taken and compared
  PARSER_DECISION.md / PARSER_PREMISES.md / TWO_TIER_PARSER_DESIGN.md
  DOCKER_ARCHITECTURE.md / REBASELINE_PLAN.md / TOIL_INSTRUMENT.md    designs, nothing built
  A3_SERIALIZATION_FINDING.md    the product finding
  RUNBOOK_LLAMAINDEX.md / SCHEMA_PROPOSAL.md
working/       active harnesses, the service, raw results
archive/       superseded docs, guarded deprecated harnesses, invalidated results — DO NOT QUOTE
```

## Reproducing a result

```bash
# 1. provision — the engine bundle and venv are not committed
cat publishable/PROVISIONING.md

# 2. start the engine (nodes must be copied into the bundle first)
cp -R working/nodes/* engine/nodes/
bash working/scripts/start_engine.sh
curl -s http://127.0.0.1:5565/version

# 3. start the LlamaIndex service — /health is answered by ONE worker and is NOT a readiness gate
WS1_DEVICE=cpu WS1_WORKERS=8 bash working/ws1/run_service.sh > logs/ws1.out 2>&1 &
until [ "$(grep -c 'warm in' logs/ws1.out)" -ge 8 ]; do sleep 3; done

# 4. any measurement MUST pre-warm the machine to a high-power state first, and record that it did
```

**The pre-warm requirement is not optional.** It is the difference between 106 /s and 226 /s on the
same service with the same harness.

## Known traps

Recorded because each cost real time: `curl -w '%{http_code}' || echo 000` yields `000000` and a
dead server passes; `setrlimit(RLIMIT_NPROC)` on macOS permanently clamps the hard limit; process
census by cmdline grep undercounted 173×; `hash()` seeds are salted per interpreter; `.pipe` files
need one live task per `project_id`; the engine tarball extracts flat. Full list in `STATE.md` §9.
