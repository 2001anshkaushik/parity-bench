# WS-1 Service Parity — start here

**Read this file first. Nothing else in this repository is a safe entry point.**
Last updated **2026-08-14**.

---

## ⏸️ CURRENT STATE — Phase 2, waiting on the AWS box

**Resuming with no memory of this work? Read `STATE.md` §0a first — it is the complete handoff.**
This section is the 60-second version.

* **Box `i-0775f33f3dc16f6af` is verified end to end** (SSM, S3 both directions, repo clone) and is
  **STOPPED**. **Billing starts on `start-instances`.** Auto-stop is silent — an idle session will
  kill the box without warning.
  > **CORRECTION 2026-08-14 — the auto-stop threshold is disputed.** This file previously said
  > **1 % CPU for an hour**. Shashi's `AWS-RUNBOOK.md`, written after Dmitrii provisioned all three
  > boxes, says **< 20 % instance CPU for 60 minutes** — on 32 vCPU that is 6.4 cores, against a
  > measured 12.7 % idle floor. Both cannot be right and neither is measured. **Assume 20 %**: the
  > error is asymmetric, and the one-core keep-alive this repo used to recommend (~3 %) would not
  > save the box. `RUN_ON_EC2.md` §1a has an eight-core keep-alive. [UNVERIFIED — open item for
  > Dmitrii]
* **Team is pinned:** engine **3.3.1** + SDK **1.3.0**, **Parser IN**, stock 5-node pipeline. All
  three teams aligned. **Shashi and Leela are already running on AWS; we are behind.**
* **Done locally:** Parser IN on both arms · five correctness gates · 50-doc smoke passing both arms
  · setup probe passing · 10,000-file corpus manifest + verifier · metrics docs shipped
  (`METRICS_AND_VERIFICATION.md`, `TEAM_HANDOUT.md`) · 12 pass + 1 known xfail in the suite.
* **TODAY'S PLAN IS `RUN_ON_EC2.md`** — a native 200-document smoke, engine straight from the
  release tarball. `BUILD_ON_EC2.md` is **superseded for today** (it builds images; not one step of
  it has ever run).
* **NEVER RUN:** any x86-64 Docker build of **our** images · anything on the box beyond what
  `RUN_ON_EC2.md` sequences.
  > **CORRECTION 2026-08-14 — "the RocketRide image has never existed anywhere" is no longer true.**
  > Leela's `rocketride/Dockerfile` builds engine 3.3.1 and pins the **same extracted-binary
  > sha256 we independently verified** (`95768e26…`); Shashi's `engine.Dockerfile` carries the
  > onnxruntime boot patch. The accurate statement is that **ours** has never been built. Leela's is
  > the documented fallback if the native path stalls — `RUN_ON_EC2.md` §10.
* **🚫 Do not carry these to Phase 2 — all macOS/arm64, all must be re-measured on Linux:** the
  C ≈ 3.2 memory crossover, every C-sweep cell, pool width 17.24, the 12.4 % wall swing and the
  whole A13 story, the C=16 macOS-compression invalidation (**Linux has no compressor**), and
  **every throughput figure**. The gates, harness, manifest and bug reports travel; the performance
  numbers do not.
* **Two filed bugs:** `BUG_CHUNK_DUPLICATION.md` (>~239.8k chars → chunks emitted exactly twice;
  4-line synthetic reproducer; **5.34 % of the corpus is over the threshold**) and
  `BUG_NUL_TRUNCATION.md` (truncation at first NUL; 0/303 under Tika, 0.70 % on pypdf paths).
* **Three open cross-team questions:** the Tika-vs-pypdf extraction ratio (which is the reference?),
  the exact definition of the 10 % spread gate, and the warm-up count.
  > **CORRECTION 2026-08-14 — the warm-up question was mis-attributed.** It is not "25 (Shashi) vs
  > 100 (ours)". On his agreed branch Shashi's warm-up is **computed**,
  > `max(4, 2 × threads)` for blast and **2** for sequential — that is **64** at 32 threads, not 25.
  > **Leela** is the one on 25. Three values, not two: 64 / 25 / 100.
* **🚩 CORPUS DIVERGENCE — the three result sets are not comparable.** Shashi is on **24
  sha256-pinned arXiv cs.LG PDFs, hardlink-replicated** up to N; Leela and I are both on
  **GovDocs1**. His "10,000 documents" is 24 unique files seen ~417 times each. This is not a
  variant of one corpus, and no amount of harness alignment fixes it. Escalate before anyone builds
  a three-way table.

**First commands on the box** — full sequence in **`RUN_ON_EC2.md`**:

```bash
aws ec2 start-instances --instance-ids i-0775f33f3dc16f6af   # BILLING STARTS HERE
aws ssm start-session --target i-0775f33f3dc16f6af
```

---

## What this is

A measurement project comparing the **RocketRide engine** against a **LlamaIndex FastAPI service**
on an identical document split-and-embed pipeline, plus the instrumentation built to make that
comparison trustworthy. Ansh owns the LlamaIndex arm; Shashi owns the RocketRide service; Leela
owns the shared schema and the mt10k reference corpus.

**Team state (2026-08-14):** the team is *aligned* on the engine 3.3.1 + SDK 1.3.0 pin and the
Parser IN 5-node shape, and the metrics documents (`METRICS_AND_VERIFICATION.md`,
`TEAM_HANDOUT.md`) are prepared for the pre-Phase-2 sync. **Which documents have actually been
sent is not tracked in this repo — ask Ansh before assuming any of them landed.** Treat everything
here as a draft until told otherwise.

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

> ### ⚠️ TOPOLOGY-CONFOUNDED — see [`MATCHED_LAYERS.md`](MATCHED_LAYERS.md)
> This comparison runs LlamaIndex behind uvicorn at **8 workers**, each holding its own model,
> against RocketRide's single task process. The 4,642 MB floor is **8 × one model**, a
> configuration choice — `run_service.sh` in fact defaults to **14** workers.
> **Direction: biases AGAINST LlamaIndex.** Not withdrawn, correct as measured, but it is a
> property of the worker count, not of the framework. The matched replication reports the
> **opposite** verdict (RocketRide 2.0× worse) with LlamaIndex in-process at 1 worker.
> Worker-count decision and re-run design: `MATCHED_LAYERS.md` §5.

> **RESOLVED 2026-08-11 — [`MATCHED_LAYERS.md`](MATCHED_LAYERS.md) §5c.** This figure is **not** a
> point on the matched concurrency curve, at any C. It compares LlamaIndex idle at 8 workers (eight
> models **eagerly loaded at startup**) against RocketRide idle (engine parent holding **no task and
> no model**). It is the right answer to *"what does an idle deployment cost?"* — LlamaIndex pays for
> capacity before any request arrives; RocketRide loads on task creation — but it is **not** an
> answer to *"which framework uses less memory?"*. Under matched load below C ≈ 3 the answer is the
> opposite: RocketRide is the heavier arm.


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
