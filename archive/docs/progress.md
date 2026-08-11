# benchmark-A — Progress Log

> **2026-08-05 — SCOPE CHANGE.** After the Aug 4 exec review the team pivoted: benchmark-A is no
> longer a deliverable. WS-1 "Service Parity" is, and Ansh owns the **LlamaIndex FastAPI service**.
> No further benchmark-A sweeps. Work harvested into `FINDINGS_FOR_WS1.md` (team brief),
> `handoff/` (reusable instruments), `SCHEMA_PROPOSAL.md` (for Leela),
> `ws1/` (the service) and `TOIL_LLAMAINDEX.md` (toil log, a primary deliverable).
>
> **Headline from the new work: my own service declared `effective_concurrency: 14` and measured
> ~4.** Throughput scales linearly to concurrency 4 (89 → 167 → 339/s) then falls to 199/s at 6.
> Cause UNVERIFIED. Also: a cmdline-based process census undercounted the service's memory 173×
> (19.6 MB reported vs 3,404 MB actual) — the same bug flagged as A7 in the adversarial audit.

Single source of truth for state across sessions. Updated at each milestone.

> **Session headings: transcription errors CORRECTED 2026-08-10.** Two headings carried the wrong
> day or number because sessions crossed local midnight: session 12 was headed 2026-08-08 although
> it followed session 11 (2026-08-09), and the session 2 / session 4 labels were swapped. Both are
> corrected above. The body text of each entry was not altered. **`STATE.md` remains authoritative
> for ordering**; this file is a narrative log.
>
> (These were pre-existing transcription errors, not damage from the file-corruption incident of
> 2026-08-10 — a character-level insertion and its removal cannot alter a digit.)


**Host:** Apple M4 Pro, 14 cores (10P + 4E), 48 GiB RAM, macOS (darwin 25.6.0), arm64
**Python:** `.venv` at `$REPO/../.venv` → 3.12.13
**Cost constraint:** $0 — 100% local, no paid cloud.

---

## Grounded facts (verified at source — do not re-derive)

| Fact | Evidence |
| --- | --- |
| RocketRide = **C++ runtime orchestrating Python nodes** | `rocketride-bench (Krish)/README.md` states it outright; repo has 790 C++ files vs 757 Python node files |
| Scheduler is a **work-stealing thread pool**, per-thread bounded queues | `packages/server/engine-core/apLib/async/ThreadedQueue.hpp:30,48-69` |
| Concurrency knobs `threadCount` / `queueDepth` are **programmatic**, not config | `ThreadedQueue.hpp:48` — `start(location, namePrefix, threadCount, queueDepth, cb)` |
| Engine default `threadCount: 64` | Leela `PREDICTIONS.md` #2 (observed in task config when `threads` omitted) |
| Engine spawns a **per-task process tree** (`engine … node.py <task.json>`) | Leela `findings/stage0_findings.md` — "sampler must track the whole tree" |
| Engine ships an **embedded Python 3.12** for nodes | Leela `stage0_findings.md` — `dist/server/lib/python3.12/site-packages` |
| SDK is **fully async over WebSocket** (DAP) | `packages/client-python` — `core/transport_websocket.py`, `dap_client.py` |
| License **MIT** (Aparavi Software AG) | `rocketride-server/LICENSE` — publishing results is unencumbered |
| Known engine bug: splitter kwargs silently dropped | Leela `stage1_findings.md` — `_filter_kwargs_for` in `preprocessor_langchain/langchain.py` |
| Docker Desktop VM capped at **8.32 GB** while host has 48 GB | `docker info` — **asymmetry hazard, see Risks** |
| macOS exposes no PSS, no `io_counters()` | Leela `src/common/process_sampler.py`; confirmed in our collector |

## Version drift — RESOLVED
- Krish `requirements.txt` pins `rocketride==1.2.0`; Leela installed `1.3.0` from a local path.
- **Standardised on SDK 1.3.0 + engine `server-v3.3.1`**, a pairing verified from release
  manifests rather than assumed. See "Engine — pinned and running" below and `ENVIRONMENT.md`.

---

## Phase status

| Phase | State | Notes |
| --- | --- | --- |
| 0 — Recon & grounding | ✅ done | Facts table above |
| 1 — Harness core + collector | ✅ **done — 34/34 green** | 2,687 LOC |
| 1b — Framework verification (dossiers) | ✅ done | 10 candidates, 5 installed & introspected |
| 1c — Engine provisioned & running | ✅ **done — gate green** | 3.3.1.35 native arm64 on 127.0.0.1:5565 |
| 2.0 — Process scaling probe (STEP 0 gate) | ✅ **done** | `PROCESS_SCALING.md` — 10k reachable in Model B; Model A livelocks ~150 |
| 2.1 — Fault isolation probe | ✅ done | `FAULT_ISOLATION_PROBE.md` — headline survives, stated precisely |
| 2.2 — Deployment parity | ✅ done | `DEPLOYMENT_PARITY.md` — wrapper overhead measured; Tier 2 unresolved |
| 2.3 — Ceiling attribution | ✅ done | `CEILING.md` — **2,600/s was OUR CLIENT; engine does ~12,500/s** |
| 2.4 — Operational complexity | ✅ done (downscaled) | `OPERATIONAL_COMPLEXITY.md` |
| 2.5 — Pre-registration | ⏸ **awaiting user** | After user reads this report |
| 2.6 — Adapters | ⏸ blocked on 2.5 | Not built this run, per instruction |

## Session 4 findings (seeds / full matrix / tier2 / pool width / model A / audit)

**STEP 0 seeds — PASS.** `harness/seeds.py` uses sha256, not `hash()`. Plans verified identical
across separate interpreters AND across differing `PYTHONHASHSEED`. Reproducible.

**STEP 1 fault matrix — VERDICT: RocketRide separates on NOTHING.** 11/12 cells all four
frameworks score 0.00. The 12th (hang@5%) RocketRide *loses*: 12.60 vs threadpool(64) 0.00.
`collateral_wrong_output = 0` everywhere — nobody corrupts survivors. alloc: everyone survives
27 GB of churn, zero compression, zero swap; processpool peaks at 10.9 GB vs asyncio 1.7 GB.

**STEP 3 pool width = ~17** (17.1/17.2/16.6 at three hold durations, spread 0.6). Neither the 24
OS threads the engine reports nor the `threadCount: 64` in task config. The hang row is a pure
pool-width artifact: width 14 drowns at 16 hangs; widths 17/18 drown at 53; width 64 never drowns.

**STEP 4 Model A — measurable at n=50, NOT at n=100.** Zero-fault control at n=100 scored 0 %
goodput even with setup excluded (engine send latency grows steeply with live task count:
n=5 → 0.01 s, n=20 → 2.17 s, n=50 → 12.78 s, n=100 → >20 s). At n=50 all four fault classes score
**0.00 including hang** — per-task processes isolate hangs where Model B's shared pool cannot.

**STEP 2 Tier 2 — FastAPI WINS decisively.** Both sides, same multi-process driver, randomised
order: RocketRide peak 7,871/s @ p50 121 ms; FastAPI peak 29,067/s @ p50 10.7 ms. **3.69×
throughput, 11× lower latency.** RocketRide's one edge is p99 stability (<600 ms across the sweep).
> **SUPERSEDED in session 3:** the 7,871/s was pre-protocol. Under protocol the engine measures
> 12,313.5/s (spread 1.7 %, n=5), making the ratio **2.36×, PROVISIONAL** — see TIER2_RESULT.md.

**REPRODUCIBILITY PROBLEM:** CEILING.md's 11,408/12,510 do not reproduce (now 7,871–8,540 @ 4
drivers). ±35 % run-to-run variance. No single-run throughput figure is publishable.
> **SUPERSEDED in session 3 — and this conclusion was WRONG.** Under the full protocol the engine
> measures 12,313.5/s at 4 drivers with 1.7 % spread, which supports the ORIGINAL 11,408 and does
> not reproduce the 7,871–8,540 cluster. The ±35 % was a between-session effect, not within-session
> noise. See VARIANCE_PROTOCOL.md Finding 4.

**alloc_hold (extra, beyond the brief) — THE ONE GENUINE DIFFERENTIATOR.** Plain `alloc` freed
immediately so nothing overlapped. Holding 256 MB for 2 s: at MATCHED width and MATCHED wall time
(rocketride ~17 / 8.18 s vs asyncio 18 / 8.13 s), peak RSS is **5,040 MB vs 13,363 MB — 2.65×
less**. Mechanism is allocator behaviour across a process boundary, not scheduling. Wall times
independently confirm the pool-width measurement (ceil(55/width)x2s).

**STEP 5 audit — 5 asymmetries found that favour RocketRide** (warm-up outside timed region,
processpool spawn inside it, warm long-lived engine, one-sided preflight hygiene, fixed order) and
one that handicaps a comparator (`asyncio.to_thread` silently uses 18 threads, not the Semaphore's
64). 4 checks clean (no SDK retries, symmetric error counting, symmetric correctness verification,
fair connection reuse). None overturn the "no separation" verdict — bias toward RocketRide cannot
manufacture a null result.

## Session 3 findings (fault isolation / parity / ceiling / complexity)

**Fault isolation — headline SURVIVES, precisely stated.** RocketRide Model B: zero collateral,
zero silent corruption on `raise`, `alloc` (57 × 512 MB), `malformed` at rates to 5 %. Matches —
does not beat — asyncio and processpool. Hangs at 5 % degrade *every* framework to ratio 9.1–10.0
and ~30–36 % goodput; a queueing property, not a differentiator.

**Ceiling — the big correction.** ~2,600/s was our single-process client, not the engine. Driver
scaling: 1→3,412/s, 2→6,485/s, 4→11,408/s, 8→12,510/s. **All prior throughput numbers understate
RocketRide by ~4.8×.** Load generators must be multi-process for any throughput claim.

**Three of my own harness bugs produced false verdicts this session** — two ran against
RocketRide, one against the Python baseline:
1. processpool's hang deadline never fired (`result()` on already-completed futures) → fictitious
   perfect 0.00.
2. asyncio's timer started on semaphore acquisition, not batch start → asyncio got a longer
   effective deadline than RocketRide, manufacturing a "7× worse" result.
3. Single-process load driver → engine throughput understated 4.8×.

**Model A fault cells are CONFOUNDED** (setup contention, not fault cascade) — `collateral_wrong
= 0` in every cell proves nothing was corrupted, items merely missed the deadline.

**Seeds are not reproducible across processes** — `hash()` is salted per interpreter. Within-run
comparisons valid; absolute injected counts are not. Fix with a fixed integer seed.
| 3 — Calibration | ⏳ | Partly done: see calibration.json |
| 4 — Execution sweeps | ⏳ | |
| 5 — Analysis | ⏳ | |
| 6 — Publication | ⏳ | |

## Engine — pinned and running (full record: ENVIRONMENT.md)

| Item | Value |
| --- | --- |
| Release | `server-v3.3.1` (2026-07-07, stable) |
| Running version | **3.3.1.35** hash `a0817cc6` |
| SHA256 | `846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836` |
| Binary arch | `Mach-O 64-bit executable arm64` (verified via `file`) |
| Bind | `127.0.0.1:5565` (loopback only) |
| Start / stop | `bash scripts/start_engine.sh` · `bash scripts/stop_engine.sh` |
| Gate | `../.venv/bin/python scripts/verify_engine.py` → exit 0 |

**SDK compatibility: VERIFIED by co-release pairing.** Server manifests bundle a client tarball:
3.2.0→1.1.0, 3.2.1→1.1.1, 3.2.2→1.2.0, 3.3.0→1.3.0, **3.3.1→1.3.0**. Python and TS clients are
lockstep at 1.3.0. *Mechanism* is UNVERIFIED — the SDK has no `min_server_version`, no protocol
constant and no handshake, so nothing enforces the pairing at runtime.

Rejected `3.3.0-prerelease` (2026-08-04) and `3.3.0-hackathon` (2026-08-03): dated later but
flagged prerelease and carrying a lower version than 3.3.1.

**Version pairings across team repos** (recorded so environments can be stated when numbers are
compared, not to grade any repo): Krish pins engine 3.2.1 with SDK 1.2.0, a combination the release
manifests do not pair (3.2.1 ships 1.1.1; 1.2.0 ships with 3.2.2). Leela measured a *source build*
(commit `1ec7454`) rather than a release artifact, so reconstructing that environment needs the
commit rather than a published tarball.

## Phase 1 task list — COMPLETE

- [x] Directory scaffold `benchmark-A/`
- [x] `harness/collector.py` — macOS process-tree sampler
- [x] `harness/collector_proc.py` — **out-of-process** collector (required for real runs)
- [x] `harness/workload.py` — 4 kernels + seeded fault injection + correctness reference
- [x] `harness/adapters/base.py` — adapter protocol
- [x] `harness/adapters/baselines.py` — asyncio / threadpool / procpool / **chunked** procpool
- [x] `harness/runner.py` — open-loop + closed-loop driver
- [x] `harness/stats.py`, `harness/env_capture.py`
- [x] `scripts/verify_frameworks.py` — anti-hallucination dossier generator
- [x] `scripts/selftest.py` — 34-check Phase 1 gate
- [x] Deps installed (psutil 7.2.2, numpy 2.5.1), selftest green

## Calibration constants (results/selftest/calibration.json)

| Constant | Value | Why it matters |
| --- | --- | --- |
| Process-boundary floor (p50) | **0.95 ms** | Workload items must cost ≫ this or we measure IPC, not schedulers |
| Collector observer overhead | **−0.8%** (noise 3.1%) | Instrument no longer perturbs the measurement |
| GIL-bound process/thread ratio | 5.8× → 8.5× (small → large items) | Track A premise confirmed |
| GIL-free process/thread ratio | 0.44× → 0.27× | Threads win on numpy — the honest counter-case |

## Bugs found and fixed in Phase 1 (all now regression-tested)

1. **Collector caused 100× slowdown** (5,412 → 58 items/s) and was *biased* toward external
   engines. Fixed: single process-table scan per decimated cycle + separate collector process.
   Guarded by T10. **This one would have fabricated a RocketRide win on its own.**
2. **Process-boundary floor mis-measured** as 155 ms; true value 0.95 ms. Guarded by T9.
3. **ProcessPool warm-up inadequate** — `spawn` interpreter startup leaked into the timed region.
4. **Collector startup race** — stale samples file satisfied the readiness check, so SIGTERM
   could kill the child before its handler was installed; runs silently reported 0 MB / 0 CPU.
   Fixed with an explicit `.ready` handshake + stale-artifact cleanup.
5. **Classifier libelled competitors** — LangGraph flagged HOSTED_API on a docstring placeholder,
   CrewAI on `api.openai.com`. Fixed: only vendor-owned domains count, and they yield
   REVIEW_REQUIRED, never a verdict.
6. **T10 itself was too noisy to be meaningful** (±43%) — resized to 1,500 items / median of 3,
   now 3.1% spread, and it asserts its own noise floor via T10b.
7. **My own `start_engine.sh` health check reported a dead engine as healthy.**
   `curl -w '%{http_code}' || echo 000` appends a second `000` on connection failure (curl prints
   `000` *and* exits 7), so the variable held `000000`, compared unequal to `000`, and passed.
   The engine was still bootstrapping with no listener. Fixed by assigning the fallback instead of
   appending, and by switching the probe from `/ping` (401, auth-gated) to `/version` (200,
   unauthenticated, carries version + hash so readiness and identity are one call).

## SDK 1.3.0 defects found (both "accepted and silently ignored")

Same shape as the `_filter_kwargs_for` splitter bug Leela documented — worth reporting upstream.

1. **`get_server_info()` is unusable against an auth-requiring engine.** It passes `public=True`,
   but `_public` is written at `client.py:242` and never read anywhere in the SDK; `connect()`
   unconditionally runs `_internal_login()` with `auth: ''` → `AuthenticationException`.
2. **`rrext_public_probe` omits the `version` field** its docstring promises. Observed body:
   `platform`, `capabilities`, `apps` only. Protocol-reported version is **UNVERIFIED**; version
   comes from `GET /version` instead, which matches the binary's `--version` exactly.

## Framework eligibility verdicts (dossiers/INDEX.md)

| Framework | Version | Publisher | Maintenance | Verdict |
| --- | --- | --- | --- | --- |
| langgraph | 1.2.10 | LangChain | ACTIVE (6d) | Track A LIKELY — behavioural probe pending |
| crewai | 1.15.10 | — | ACTIVE (0d) | PENDING — `app.crewai.com` + `telemetry.crewai.com` |
| deepagents | 0.7.4 | LangChain | ACTIVE | Track A LIKELY — **built on LangGraph, NOT independent** |
| omnigent | 0.8.1 | **Databricks, Inc.** | ACTIVE (0d) | PENDING — `omnigent-app.databricksapps.com` |
| lyzr | 0.1.43 | lyzr | **ABANDONED (600d)** | **NO** — fails to install on Python 3.12 |

## Phase 2 entry criteria

- [x] RocketRide engine running natively (NOT Docker — 8.32 GB VM cap makes memory invalid)
- [x] Environment pinned with SHA256 (ENVIRONMENT.md)
- [ ] RocketRide adapter implementing `harness/adapters/base.py`
- [ ] Behavioural locality probe for crewai + omnigent (can a trivial pipeline run offline?)
- [ ] Telemetry opt-outs applied uniformly and recorded in the env block
- [ ] Pre-registered predictions written before the first real sweep

## STEP 0 RESULT (full detail: PROCESS_SCALING.md)

**10,000 concurrent IS reachable — in Model B. RLIMIT_NPROC binds nothing.**

| | Model A (N pipelines) | Model B (N sends, 1 pipeline) |
| --- | --- | --- |
| Process cost | ~1.0 per task | **0** — flat 718-720 procs from n=100 to n=20,000 |
| Max reached | **livelock at 150** (100 OK) | **20,000, zero errors** |
| Failure mode | livelock: 99% CPU, port dead, orphaned node procs, no recovery in 27 min | clean backpressure: throughput flat ~2,600/s, latency linear |

Baselines: asyncio 0 proc/unit @10k; threadpool 0 proc/unit; processpool ~1.0 per *worker*
(14 workers = 14 procs, not per task).

Arithmetic: cap 8,000 - idle 720 = 7,280 headroom. Model A would allow 7,280 by NPROC but the
engine dies at ~150 (2% of the OS ceiling). No Track A adapter is NPROC-constrained.

**macOS trap: never call `setrlimit(RLIMIT_NPROC, ...)`.** Requesting soft=12000 succeeds but
silently clamps the HARD limit to 8000, permanently, and an unprivileged process cannot restore
it. `kern.maxprocperuid=8000` is the real cap; the reported 12,000 hard limit is `kern.maxproc`.

Proposed sweep: Model B 100→10,000 (primary); Model A 10→100 hard-stopped (livelock reported as
a result, not engineered around).

## Watch during Phase 2

- **`RLIMIT_NPROC` = 8,000 soft / 12,000 hard** is the binding host ceiling, not fds
  (`ulimit -n` is 1,048,576). A process-per-task engine or oversized pool hits it first, and
  that failure would read as a framework defect if not attributed.
- Engine cold start ~1 min (embedded-Python bootstrap), warm ~1 s. Never inside a timed region.
- The engine spawns a per-task `node.py` process tree — the collector's `engine` role must use
  the cmdline-pattern form so those children are counted.

---

## Open risks (carry forward)

1. **Docker memory asymmetry.** Engine-in-Docker gets 8.32 GB; native Python gets 48 GB. Any
   memory comparison across that boundary is invalid. Fix: run engine natively, or impose an
   identical RSS ceiling on both sides via the collector watchdog.
2. **"C++ vs Python GIL" framing is not supported by the architecture.** RocketRide's nodes are
   Python. It avoids the GIL by *multi-process* execution, not by C++ threading. The honest
   claim is about the *scheduler + process model*, not language.
3. **Thin-client accounting trap.** RocketRide's harness-side process is a WebSocket client;
   its real work happens in engine processes. Measuring harness RSS only would flatter
   RocketRide enormously. Collector MUST sum whole process trees for both sides.
4. **macOS ≠ Linux for OOM.** macOS compresses memory and uses jetsam rather than a Linux OOM
   killer. Crash/OOM rates measured here are *indicative*, not production-grade evidence.
   Final confirmation run should happen on Linux before external publication.
5. **Open-loop latency is batch-position latency**, not service latency (Leela limitation #3).
   Runner must label the mode explicitly and never mix the two.

## 2026-08-05 session 2 — runbook, corpus-shape gate, scoped claim, handoff

**STEP 1 RUNBOOK VERIFIED** — `RUNBOOK_LLAMAINDEX.md`; every command executed in a fresh shell,
outputs recorded in §5. `ws1/smoke.py` added (ALL PASS, exit 0). Learned by running it: warm is
~5.7 s/worker on a warm machine, not the ~36 s quoted from a cold cache.

**STEP 2 CORPUS GATE — THE 1.73× IS WITHDRAWN.** Corpus verified (10,000/10,000 sha256 vs Leela's
manifest). mt10k: median 1,186 bytes, **median 1 chunk (93.2% single-chunk)**, **median 338
embedded tokens**. On the real distribution **RocketRide is 1.13× faster** [CI95 1.064–1.183]
(PROVISIONAL point — the RR arm spread 14.8% fails the gate; direction corroborated by two other
experiments). Chunk sweep: RocketRide ahead at every chunk count (1.23–1.55×).
**Mechanism [VERIFIED, 2 methods]:** the instrument contradicted itself (LlamaIndex 394/s vs 180/s
same config) — isolated to the DOCUMENT, not the harness. Cost is linear in **tokens**, not chars.
RocketRide is **overhead-bound**, LlamaIndex **compute-bound**; crossover at 200–400 tokens; the
corpus straddles it (21.4% below / 38.3% within / 40.3% above). My original doc was ~210 tokens —
lighter than 79% of the corpus.

## 2026-08-05 session 3 — schema v0.2, guards, variance closure, parity

**STEP 1 SCHEMA v0.2** — `device` now a REQUIRED field pinned to cpu, with a **declared-vs-resolved
startup assertion** (service refuses to start on mismatch; guard tested in both directions).
Warmup-discard folded into the contract. **Load-average gate REMOVED** — the null control refuted
it. FINDINGS_FOR_WS1 now leads with the device finding.

**STEP 2 pool_width GUARDED** [VERIFIED] — auto-escalates offered concurrency until the estimate
stops tracking it, hard-fails rather than guessing. Re-calibrated: −0.7 % to −0.9 % error at known
widths 4/8/16/64; starting at offered=2 against a true width of 16 now escalates [2,4,8,16,32,64]
and returns 15.87 instead of ~2. Short holds rejected; unbounded pools refused.

**STEP 3 RocketRide ±35 % — COLLAPSED** [VERIFIED, n=5]. Under protocol: 1 driver 3,416.8/s (4.3 %),
2 drivers 6,730.2/s (7.4 %), 4 drivers **12,313.5/s (1.7 %)**. All pass the 10 % gate.
**My earlier correction was itself wrong**: 12,313 supports the ORIGINAL 11,408, not the
7,871–8,540 I "corrected" to. The ±35 % was a BETWEEN-session effect; cause still UNVERIFIED.
Correction banners added to CEILING.md, TIER2_RESULT.md, FINDINGS_FOR_WS1.md; TIER2 headline
recomputed 3.69× → **2.36× (PROVISIONAL — FastAPI side not yet re-measured)**.

**STEP 4 PARITY — WITHDRAWN in session 4** (unrepresentative document; see below). Original:
matched concurrency 8, same driver, device=cpu asserted, n=5/n=7,
warmup discarded, randomised: **RocketRide 227.83/s (5.0 %) vs LlamaIndex 394.37/s (5.3 %) →
LlamaIndex 1.73× faster**, CIs widely separated. Response bytes symmetric (0.99×). The suspected
handicap (engine pinned to 8 vs its width 17) was **tested and REFUTED** — at its own width 16 the
engine is *slower* (210.60/s, p50 ~70 ms). My own arm failed the 10 % gate first (13.7 %) and was
re-run rather than reported.

## 2026-08-05 session 4 — verification protocol run

**STEP 3 pool_width CALIBRATED** [VERIFIED]: error −0.7% to −1.0% against known widths 4/8/16/64.
Two failure modes quantified: hold <0.25 s under-reads by up to 19%; **offered concurrency below
the true width silently returns the OFFERED value (−75% error at offered=4/true=16) with 0.0%
spread** — a confidently wrong number. Our RocketRide ~17 used offered=512, so it is safe.

**STEP 4 fault path + accounting VALIDATED** [VERIFIED]: error_class contract correct
(raise→embed_failed, malformed→malformed_input, HTTP 200 + ok:false). Accounting validated against
known-answer cases including the two that catch a broken scorer — a deliberately dropped item was
counted as `collateral_missing`, a deliberately corrupted output as `collateral_wrong_output`, and
the ratio moved 0.0 → 0.2857 in response.

**RocketRide device check** [VERIFIED, source inspection was WRONG]: engine passes no `device=` to
SentenceTransformer, so source review suggested GPU. Empirically it is **CPU** (cores_busy 9.29,
output verified as real 384-dim unit-norm vectors). Leela's "CPU embedding" claim is correct.

**STEP 1 ROOT CAUSE FOUND — the concurrency-4 ceiling is the GPU.** [VERIFIED, 2 methods]
`sentence-transformers` silently selects `mps` (Apple GPU) on this host. Null control (model only,
NO HTTP, N processes): mps 1 proc 107.9/s, 14 procs 281.7/s = 2.61x, **cores_busy 1.69** — work is
off-CPU, and 14 processes contend for one GPU. Forcing `device="cpu"`: 1 proc 32.6/s, 14 procs
112.8/s, **cores_busy 8.09** — CPU genuinely scales but saturates lower.
The HTTP layer is INNOCENT: the ceiling reproduces with uvicorn entirely removed.
**Parity impact: Leela's RocketRide runs MiniLM on CPU. My service defaulted to GPU. A parity run
would have compared silicon, not frameworks.** Device is now explicit config, default `cpu`,
reported in every response and manifest.

## 2026-08-05 — session 5: extended sweep, topology, chunking, crossover deliverable

- STEP 1 token sweep extended to 400/800/1600/3200/6400 in BOTH harness modes.
  Fresh-task (burst): ratio 1.482/1.488/1.658/1.515/1.322.
  Persistent (sustained): 0.727/0.823/0.905/0.891/0.946.
  The two disagreed on DIRECTION -> resolved by burst_vs_sustained.py.
- burst_vs_sustained: 10 bursts through one task = 86.6 -> 59.0 req/s, 31.3% decay.
  VERDICT: fresh-task harness measures BURST capacity; persistent measures steady state.
  Sustained is the production-relevant mode. Correction banners added to
  PARITY_CORPUS_FINDINGS.md and SCOPED_CLAIM.md.
- STEP 2 topology: built nodes/split_embed + pipes/single_node.pipe. 1-node vs 4-node
  = 0.88-1.13x. Node hops are NOT the engine's fixed cost.
  CAUGHT: the 1-node arm returns 159B vs 9-24KB (vector dims, not vectors) - confound
  favouring RocketRide. Disclosed; retired using the chunking arm (below).
- STEP 3 chunk vs token: ratio 0.932/0.824/1.024/0.995 across 1-13 chunks, no trend.
  Per-chunk Python cost REFUTED; per-request overhead amortisation stands.
  Design flaw disclosed: MiniLM's 512-token cap broke the constant-total-token intent,
  so absolute throughput is confounded; the ratio is not.
  Bonus: LlamaIndex payload grew 100x->555x (15.9->115.4KB) with no ratio movement,
  which bounds response-payload cost near zero and retires the STEP 2 confound.
- REPLICATION FOUND: topology_persistent is also sustained mode and covers 100-1600 tok.
  Overlaps the sweep at 400/800/1600 and agrees within 0.6-4.1%. Sustained DIRECTION
  upgraded PROVISIONAL -> VERIFIED; point estimates remain PROVISIONAL (RR variance gate).
- STEP 4 wrote CROSSOVER_FINDING.md (291 lines, the presentable deliverable).
- STATE.md updated: findings 1a-1f added, headline section reframed, open items A/B/C
  closed, new open item A2 (cause of the 31% decay, ~40 min).

## 2026-08-05 — session 6: the 31% decay is WITHDRAWN; concurrency is the real axis

- STEP 1 root-caused item A2. THE DECAY DOES NOT REPRODUCE.
  * exact replication (1proc/1conn/1task, no cooldown, 20 bursts): 6.0%, not 31.3%
  * 0 failures in ~10,000 requests -> rival (d) silent failures REFUTED
  * engine-tree RSS flat 891MB; recovery to 98% after 60s idle; fresh-task == persistent
    (0.0% vs 6.0%) -> rival (b) pipeline accumulation REFUTED
  * INTERLEAVED RR/LI on one shared host timeline: RR +1.1%, LI -0.8%, neither decays
    -> rival (c) thermal/host REFUTED
  * symmetric continuous n=3, randomised: RR median +1.5% (+5.2,-8.7,+1.5),
    LI median +1.0% (+6.4,-12.0,+1.0). Both arms swing BOTH directions, spread 14-18pp.
  * null control: no decay-vs-session-position trend -> session drift REFUTED
  VERDICT: no rival survives because there is no phenomenon. The original was n=1, no
  control arm, from a statistic whose noise band is +/-12-18pp.
- CONSEQUENCE: burst-vs-sustained framing WITHDRAWN; sustained token curve INVALID.
  Correction banners applied same turn to CROSSOVER_FINDING.md (marked ON HOLD, do not send),
  PARITY_CORPUS_FINDINGS.md, SCOPED_CLAIM.md, STATE.md.
- STEP 2 re-measured on the axis that actually matters: CONCURRENCY.
  * RocketRide is FLAT 2->32 in flight (56-65/s @400tok, 24-29/s @1600tok)
  * LlamaIndex scales to a plateau by conc 8 (~93/s @400tok, ~37/s @1600tok)
  * refutes my own earlier hypothesis that the 8-in-flight sweeps UNDER-DROVE RocketRide:
    it does not go faster at 16 or 32 either. Pool width != throughput scaling.
  * RR ahead 1.190x [1.184,1.196] at 1600tok/conc2 with BOTH arms passing the gate -
    the only gate-passing head-to-head advantage in the whole project.
- FOUR instrument defects found, three of them introduced during this investigation:
  burst_vs_sustained n=1/no control/swallowed failures; phase-5 per-burst-index aggregation
  (fake U-curve 140->40->87); wall-clock-union aggregation (depressed all cells);
  per-rep burst boundaries (12-58% spreads). Fixed by BARRIER-SYNCHRONISED fixed-duration
  windows -> 8/10 RR cells now pass the 10% gate.
- "The RocketRide arm is systematically noisier" WITHDRAWN - it was our harness desync.
- STEP 3 wrote CONCURRENCY_CHARACTERIZATION.md (INTERNAL working notes, not team-facing).

## 2026-08-06 — session 7: A3 CLOSED (it isn't the engine); environment design docs

- STEP 1 closed item A3 on native, before containerising. Built two new benchmark nodes
  (noop_probe, cpu_probe) + pipes, installed into engine/nodes/, restarted engine.
  FOUR-ARM LADDER (same 400-tok doc, barrier-synchronised windows, randomised, up to 4 drivers):
    1 minimal (no python node)  458.8 -> 1693.0/s   3.69x
    2 noop    (python node)     444.3 -> 1534.9/s   3.45x
    3 cpu     (15ms pure py)     51.4 ->  184.3/s   3.59x
    4 embed   (MiniLM)           49.7 ->   67.7/s   1.46x   <- only flat arm
  => THE ENGINE IS NOT THE BOTTLENECK. Serialization is model/native-stack specific.
- MECHANISM [VERIFIED, 2 methods]: native thread oversubscription.
  * intervention: OMP/MKL/OPENBLAS/VECLIB/NUMEXPR/TORCH_NUM_THREADS=1 at engine start
    embed default   c1=50.3 c8=73.3  scaling 1.46x
    embed threads=1 c1=27.4 c8=87.6  scaling 3.19x   (+19% throughput @c8)
    NULL CONTROL: cpu arm unchanged (55.2 vs 56.0, 2%) - pure python uses no BLAS. HOLDS.
  * CPU accounting (system-wide cpu_times deltas; process-tree walk UNDERCOUNTS - it read
    ~1.0 cores in every condition and was discarded):
    one embed = 1.45 cores at default vs 0.49 pinned; per-request CPU inflates 80% under
    concurrency at default vs 47% pinned.
  * TRADE-OFF: pinning costs ~1.8x single-request latency. Latency-vs-throughput knob with
    NO documented config surface - only process env at engine start, global to the engine.
- CONSEQUENCE: all prior RR-vs-LI throughput comparisons were TUNED SERVICE vs UNTUNED ENGINE
  (ws1 pins OMP_NUM_THREADS=1; the engine did not). Correction banner added to
  CONCURRENCY_CHARACTERIZATION.md; STATE 1b3 downgraded to CONDITIONAL; new findings 1g-1j.
- STEP 2 llama-deploy: DEPRECATED upstream ("use llama-agents instead"). Also pins
  llama-index-core<0.14.0 vs our 0.14.23 (forced downgrade), license undeclared, last release
  2026-04-06, deps = Kafka/Redis/RabbitMQ/OTel (distributed control plane, not an HTTP wrapper).
  RECOMMEND: keep FastAPI. Successor llama-index-workflows requires Workflow/@step/event
  structure our split+embed does not need, but CAN be mounted into an existing app -
  that decision goes to Leela/Shashi, not taken unilaterally.
- STEPS 3-6: wrote DOCKER_ARCHITECTURE.md (NOTHING BUILT - awaiting approval),
  REBASELINE_PLAN.md, TOIL_INSTRUMENT.md (pre-registered, with COI declaration),
  PDF_PIPELINE_NOTES.md.
- PDF parser asymmetry CONFIRMED from source: engine ships Apache Tika 3.2.3 JVM incl.
  tika-parser-pdf-module; NO PyMuPDF/fitz/pdfminer/pypdf anywhere in engine python.
  java on PATH. Also a llamaparse node = HOSTED API (excluded from $0 local benchmarking).
- Docker daemon/CLI NOT reachable this session; settings-store declares MemoryMiB=32768 but
  that is DECLARED, not measured. docker info is the authoritative check.

## 2026-08-06 — session 8: re-anchored thread-pinned; fairness basis; memory ceiling; parser verdicts

- BUILT nodes/env_probe to answer DECLARED vs MEASURED for thread pinning. Gate on every block:
  default engine -> torch.get_num_threads()=10 ; pinned -> 1. Pin DOES reach the task process.
  NOTE: torch_num_interop_threads stays 14 even when pinned (no env var reaches it) -> item A8.
- STEP 1 ANCHOR A (ABA design: tuned / untuned / tuned-again, n=5, gated, randomized):
    400tok  RR tuned scaling c1->c32 = 3.04x ; untuned = 1.43x
    1600tok RR tuned scaling c1->c32 = 3.05x ; untuned = 1.18x
    Tuning HURTS below conc~4 (0.41-0.55x at c=1) and HELPS above (1.05-1.18x).
- STEP 1 ANCHOR B — the headline reversal:
    UNTUNED  1600tok/c2  RR/LI = 1.201 [1.185,1.217]  <- reproduces the 1.190x reference
    TUNED    1600tok/c2  RR/LI = 0.926 [0.917,0.934]  <- RR's only advantage DISAPPEARS
    Both arms pass the 10% gate in both blocks. Best-achievable config is CONCURRENCY-DEPENDENT.
- DRIFT CONTROLS: block1-vs-block3 within +/-3.2% except the 1600/c8 cell (+9.7%/+12.3%, and that
  cell had a 99.3% spread untuned - unreliable). NULL CONTROL DID NOT FULLY HOLD: LlamaIndex,
  which cannot be affected by the engine's thread setting, moved +3.4% median (range -2.0% to
  +19.5%) between blocks. => deltas under ~5% are NOT trustworthy. Logged as A9.
- STEP 3 MEMORY: continuous 250ms sampling (between-cell sampling understates peak ~4.8x).
    RocketRide idle  204 MB -> peak 2,356 MB @6400tok/c32
    LlamaIndex idle 4,642 MB -> peak 7,950 MB @6400tok/c32
  8GB cap = 99.4% of LI peak, 29% of RR peak -> would OOM one arm only. RECOMMEND 16 GB/service,
  VM allocation raised 24 -> 40 GiB. DOCKER_ARCHITECTURE.md §3 updated.
  CAUGHT MY OWN BUG: a3_load.py hardcoded ~400 tokens and ignored the token arg, so every
  RocketRide memory cell ran at 400 tokens (flat ~86/s gave it away). Fixed and re-measured.
- STEP 4 A6 RESOLVED: units bug in my own probe (psutil.cpu_percent is % of TOTAL capacity, needs
  xNC to become cores). Corrected: one embed at default threads = time-average 2.42 cores (c=1) /
  4.83 (c=8); p95 4.17/10.08; PEAK 7.75/13.09. Finding 7's 9.29 is a p95/peak under load;
  session 7's 1.45 was a time-average with a contaminated baseline. Both real, not interchangeable.
- STEP 4 PDF: engine --tika VERIFIED BY EXECUTION -> com.rocketride.tika_api.TikaApi. JVM is loaded
  IN-PROCESS VIA JNI, so no separate java process ever appears - the check I proposed last session
  would have given a FALSE NEGATIVE. Engine bundles OpenJDK 17.0.19 Temurin aarch64.
  CORRECTED MY OWN ERROR: "java on PATH" was wrong - /usr/bin/java is a macOS stub, java -version
  says no runtime installed.
  LlamaIndex has NO PDF reader installed at all; core maps .pdf->PDFReader from the absent
  llama-index-readers-file and SILENTLY RETURNS {} (PDFs skipped, not error). Default is pypdf
  (llama-index-readers-file 0.6.0 requires pypdf<7,>=6.1.3); PyMuPDF is an optional extra.
  Tika vs pypdf on a simple 3-page text PDF: 99.10% agreement; pypdf 100.00% vs source.
- STEP 2 wrote FAIRNESS_BASIS.md (best-to-best; full tuning inventory both arms; fairness ledger).
- NOTHING BUILT: no Dockerfile, no image, no daemon started.

## 2026-08-07 — session 9: interop closed, Anchor C, both parser premises refuted, isolated profile

- STEP 1 INTEROP (fairness asymmetry 2) CLOSED. Wired SE_INTEROP_THREADS into split_embed calling
  torch.set_num_interop_threads() before model load; node reports from INSIDE the task process:
  inter_before 14 -> inter_after 1, interop_set "ok". Gate on every block.
  ANCHOR B at 1600tok, three engine configs, drift control held (LI spread 0.7%/4.8%):
    conc 2:  A(intra1,inter1) 0.915 | B(intra1,inter14) 0.919 | C(untuned) 1.352
    conc 8:  A 0.813 | B 0.926 | C 0.743
  INTEROP EFFECT: c2 0.999x (none), c8 0.857x -> PINNING INTEROP COSTS 14.3%. Leave at default.
  This REMOVES a knob rather than adding one - against RocketRide's best case.
  CAVEAT: this run used single_node.pipe (1-node) while session 8's Anchor B used embed_probe.pipe
  (4-node), so 1.352 vs 1.201 are NOT strictly comparable. Disclosed.
- ANCHOR C (was gated, never run):
    RocketRide width = 17.24 VERIFIED (escaped tracking, confirmed by doubling) - reproduces
      finding 8's ~17 exactly.
    LlamaIndex: instrument REFUSED - estimate tracked offered concurrency to 96 (15.2/28.7/54.5).
      Because the hold is a sleep and /process is a sync def on Starlette's threadpool, sleeping
      requests do not occupy a worker. LlamaIndex has NO single width; finding 9's 8 is its CPU
      knee, not its slot count. The guard did its job - refused rather than reporting 96.
    First attempt FAILED: escalation to MAX_OFFERED=4096 through one client hung task creation for
      300s (past the ~150 livelock, finding 16). Bounded to 96 and re-ran.
- STEP 2a PREMISE REFUTED: custom PARSE nodes DO work. nodes/pdf_probe ran pypdf 6.15.0 inside the
  engine's embedded CPython 3.12.13: 3 pages, 15,065 chars, BYTE-IDENTICAL to standalone pypdf.
  Tika is a DEFAULT, not architecturally forced. COST: no supported way to add a dependency to the
  engine's interpreter - hand-copied into engine/lib/python3.12/site-packages/. Toil entry.
- STEP 2b PREMISE REFUTED: PyMuPDF is "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial".
  AGPL network clause is disqualifying for a service without a procurement decision.
  pypdf 6.15.0 BSD-3 (and LlamaIndex's OWN default), pdfplumber 0.11.10 MIT, pdfminer.six MIT/STALE.
  RECOMMEND pypdf - permissive AND the framework default, so it needs no fairness justification.
- STEP 3 wrote TWO_TIER_PARSER_DESIGN.md: Tier 1 same-text (frameworks), Tier 2 end-to-end native
  (products) with a QUALITY metric alongside speed - fidelity distribution vs a 2-of-3 consensus
  reference, plus token-ratio, reading-order, table-recall, and an EMPTY-EXTRACTION check (a parser
  returning nothing is infinitely fast and would otherwise win). Tiers never share a table.
- STEP 4 ISOLATED PROFILE (LlamaIndex only, no comparison), n=5 gated, P50/P95/P99/P99.9, RSS, err:
    400tok:  c1 30.7 | c2 60.8 | c4 74.7 PEAK | c8 61.3 | c16 70.4 | c32 64.5 | c64 58.7
    1600tok: c1 11.6 | c2 23.6 | c4 29.1 PEAK | c8 23.9 | c16 25.4 | c32 30.6 | c64 29.0
    SATURATION = concurrency 4 at BOTH token levels. 0 errors at every level up to c=64.
    P99.9 goes 42.8ms (c1) -> 2,987ms (c64) at 400tok.
  => SESSIONS 6-8 COMPARED AT c=8/16/32, ALL PAST SATURATION. Those measured queueing.
  NOTE: the automated KNEE field is unreliable (reports c32 at 1600tok from noise recovery in
  non-monotonic data). Use SATURATION, not knee.
- STEP 5 installed pypdf 6.15.0 into the measurement venv (BSD-3 per the licence finding).
  llama-index-readers-file still absent. Wrote READINESS.md with an 8-item gap list.
- DOCKER_ARCHITECTURE.md §3: 16GB -> 12GB per service with the arithmetic. 32GiB VM - ~4GiB
  driver/overhead = 28GiB for services = 14GiB each max; 12GB gives 1.51x headroom on the heavier
  arm (7,950MB) and fits. VM requirement 28GiB, still DECLARED not measured.
- NOTHING BUILT: no Dockerfile, no image, no daemon started.

## 2026-08-08 — session 10: RocketRide isolated profile, optimal-point comparison, canonical pipeline

- STEP 1 ROCKETRIDE ISOLATED PROFILE (4-node embed_probe.pipe, tuned AND untuned, n=5, gated,
  P50/P95/P99/P99.9 + peak RSS + error rate, escalation bounded to c64 = 16/driver, well under
  the ~150 livelock). 0 errors in every cell of both configs.
    RR tuned|400     c1 25.5 | c2 50.2 | c4 56.0 | c8 64.3 | c16 50.8 | c32 55.0 | c64 60.0
    RR tuned|1600    c1 10.8 | c2 19.3 | c4 19.3 | c8 20.8 | c16 20.8 | c32 24.6 | c64 25.5
    RR untuned|400   c1 42.7 | c2 58.9 | c4 59.5 | c8 59.5 | c16 64.2 | c32 63.4 | c64 66.2
    RR untuned|1600  c1 18.9 | c2 27.2 | c4 28.6 | c8 27.2 | c16 28.9 | c32 26.1 | c64 30.7
  The scripted 95%-of-peak rule again picked noisy maxima, so saturation was re-derived as
  "first concurrency reaching 95% of the PLATEAU MEDIAN (median of the top half)":
    RR tuned/400 c4 | RR tuned/1600 c32 | RR untuned/400 c16 | RR untuned/1600 c4
    LlamaIndex c4 at BOTH token levels.
  => SATURATION IS CONFIG- AND SIZE-DEPENDENT for RocketRide, fixed for LlamaIndex. Saying
  "RocketRide saturates at N" is incomplete without naming config and document size.
- STEP 2 OPTIMAL-POINT COMPARISON — first head-to-head in the project with BOTH arms inside their
  serving regime. One session, interleaved, randomized, n=5, CIs. DRIFT NULL CONTROL EXCELLENT
  (LlamaIndex -0.4% / -1.4% across the two engine-config blocks).
    untuned  400tok  RR 72.54 @c16 | LI 90.99 @c4 | 0.789 [0.776,0.800]  both gate-pass
    untuned 1600tok  RR 30.55 @c4  | LI 34.56 @c4 | 0.886 [0.871,0.902]  both gate-pass
    tuned    400tok  RR 67.74 @c4  | LI 90.63 @c4 | 0.758 [0.742,0.786]  both gate-pass
    tuned   1600tok  RR 34.85 @c32 | LI 34.07 @c4 | 0.973 [0.890,1.025]  RR GATE -> direction only
  HYPOTHESIS REFUTED: not near-parity, and RocketRide is not ahead at 1600. LlamaIndex leads at
  every quotable point. Closest RR gets is 0.973 (tuned @c32) and that cell fails the gate.
- INSTRUMENT CHECK (rule 3): LlamaIndex read 74.7/s @400tok/c4 in the isolated profile but 89-91/s
  in two later runs the same day (+22%). Suspected my own RSS sampler thread. NULL CONTROL, sampler
  on vs off alternated n=3: -0.4%, NO material effect. Sampler exonerated; cause of the +22%
  UNKNOWN -> new open item A13. The saturation SHAPE is what the operating points rest on, but the
  absolutes are not stable across runs.
- STEP 3 CANONICAL PIPELINE FIXED (closes A11): 4-node embed_probe.pipe is canonical, as WORKLOAD
  DEFINITION not a tuning knob. Two independent reasons: (1) it is built from shipped components
  and is what a user deploys, whereas 1-node split_embed is our workaround for silently-dropped
  splitter kwargs; (2) payload symmetry - 4-node returns full vectors like LlamaIndex, 1-node
  returns a 159-byte summary. Session 8's 1.201 STANDS as the anchor; session 9's 1.352 is marked
  NON-CANONICAL. split_embed retained as a labelled diagnostic instrument only.
- STEP 4 wrote PARSER_DECISION.md for Shashi (neutral, he owns the call).
- STEP 5 SATURATION BLAST RADIUS: added section 4b to STATE.md. 6 findings marked [PAST-SAT]
  (1a, 1b3, 1i/AnchorA, 1r, 4, 5). 1b4 (@c2) is WITHIN saturation and stands. Nothing re-run -
  the banner marks what each number describes.
- NOTHING BUILT: no Dockerfile, no image, no daemon started.

## 2026-08-09 — session 11: A13 RESOLVED — ascending sweeps under-measure; all saturation points WITHDRAWN

- STOPPED AT STEP 1 AS INSTRUCTED. The drift is NON-UNIFORM, so steps 2-4 were not attempted.
- A13: LlamaIndex read 74.7/s (session 9) vs 89-91/s later. Ruled out, each by direct experiment:
  * READINESS GATE (the specific hypothesis): profile gated on GET /manifest, which service.py:128
    answers from ONE worker (reports os.getpid()). Documented gate is 8x 'warm in' lines.
    A/B n=3 alternated: cold-gate 90.35/s vs warm-gate 88.20/s = 102.4%. REFUTED.
    Notably ALL 8 WORKERS WERE WARM AT START IN BOTH ARMS - the manifest gate happened to suffice.
  * RSS SAMPLER: null control, sampler on/off alternated n=3 -> -0.4%. REFUTED (session 10).
  * BACKGROUND CPU LOAD: 4 hogs left c8 at 99.4% while the c1 CONTROL fell to 86%. REFUTED
    (and note: the opposite of the prediction - high concurrency was immune, low was not).
  * SUSTAINED DECAY: 5 min continuous at c8, per-10s buckets, 190-204/s throughout, -3.5%. REFUTED.
  * HARNESS DESIGN: single-process vs 4-process(4x2) back to back = 1.010x. REFUTED.
- CAUSE FOUND — MACHINE POWER/PERFORMANCE STATE AT MEASUREMENT START.
  Identical harness, 400 tok, LlamaIndex, ONLY cell order changed:
    ascending (cold)     c1 30.5 | c2 63.5 | c4 89.0 | c8 106.5 | c16 102.7 | c32 101.7 | c64 101.5
    descending           c1 39.8 | c2 84.0 | c4 124.1| c8 204.8 | c16 248.7 | c32 228.1 | c64 240.6
    ascending + 30s prewarm at c64
                         c1 39.2 | c2 82.7 | c4 106.8| c8 183.7 | c16 225.7 | c32 223.6 | c64 225.0
  Pre-warming an ASCENDING sweep reproduces the DESCENDING one => the variable is the machine's
  power state when measurement begins, not concurrency, harness, or service.
  Note c1-measured-LAST in the descending run reads HIGHER (39.8) than c1-measured-FIRST in the
  ascending run (30.5), so this is NOT progressive within-run degradation - the whole run lands in
  a fast or slow regime.
- WITHDRAWN: LlamaIndex saturation c4 (s9) and c8 (s11 re-run); ALL FOUR RocketRide saturation
  points (s10 profile also swept ascending from c1); the optimal-point comparison (findings 1y),
  which placed each arm at a saturation point that does not exist and measured both cold.
  Also withdrew 1v ("sessions 6-8 compared past saturation") - it rested on the withdrawn c4.
- BEST CURRENT ESTIMATE [PROVISIONAL, 1 run]: LlamaIndex saturates at c16, ~226/s @400tok -
  3x the throughput and 4x the concurrency of the withdrawn figure.
- LIKELY CLOSES OPEN ITEM F: the unexplained between-session drift since session 6 has the same
  signature. One cause, not two. Needs one confirmation run.
- PROTOCOL CHANGE REQUIRED: every future measurement must pre-warm to a high-power state and
  record that it did. Randomised cell order does NOT fix this - it smears the depression across
  cells instead of concentrating it in the early ones, which is why sessions 6/8 had noisy cells.
- New open items: A15 (re-run both profiles pre-warmed, then redo the optimal-point comparison,
  ~1.5h), A16 (is the depression symmetric across arms? if not, cold head-to-heads are BIASED,
  not merely low).
- NOTHING BUILT: no Dockerfile, no image, no daemon started.

## 2026-08-09 — session 12: integrity audit, goodput gate, GovDocs1, container ladder

- STEP 0 INTEGRITY AUDIT (non-negotiable, done first). 51/51 result writes were HARDCODED with no
  variable component; 6 output names claimed by >1 script. TWO runs were silently destroyed:
  the session-9 ascending profile (saved only by an accidental manual backup) and the
  DESCENDING-order run (whose JSON is gone; it was also piped to grep so no log exists either).
  All 22 result files cited by publishable/ docs verified intact, parseable, plausible timestamps.
  Built working/harness/resultio.py: unique <name>__<UTC>__<payloadhash>.json, O_EXCL create,
  ResultCollision on any existing path, provenance envelope, latest()/load() so callers never
  hardcode. GUARD PROVEN both ways (syscall FileExistsError + API ResultCollision).
- STEP 1 GOODPUT GATE. llama-index core maps .pdf->PDFReader and WARNS+RETURNS {} when the reader
  is absent — measured: supported_suffix_fn() returned 0 suffixes. A 10k run in that state gives
  10k successes, flat memory, zero embeddings. Gate asserts per document: n_chunks>0, non-empty
  chunks, 1 vector/chunk, 384-dim, L2 norm 1.0+/-0.01, vectors not identical across chunks.
  PROVEN against 6 injected failures (all caught) + null control (correct doc passes).
  llama-index-readers-file NOT installable for the PDF path alone: its __init__ pulls pandas.
  Using pypdf directly (what PDFReader wraps).
- STEP 2 CORPUS GovDocs1: 2,471 distinct PDFs, sha256 manifest.
  median 227,567 B / ~6,345 tokens vs mt10k 1,186 B / 338 tokens => 192x bytes, 19x tokens.
  p99 167,698 tok; max 708,396 tok; max 1,000 pages. Natural fault rate 1.42%
  (34 empty_extraction + 1 PdfReadError) — CLASSIFIED, not filtered.
- STEP 3 IMAGE. FOUR build failures, each a real defect: (1) INVENTED base digest, (2) INVENTED
  uvicorn version, (3) pip READ TIMEOUT on files.pythonhosted.org, (4) model baked via
  SentenceTransformer as root but loaded via HuggingFaceEmbedding as ws1 — HuggingFaceEmbedding
  derives cache_dir from the CALLING USER's home, not HF_HOME, so offline load failed with a
  misleading "couldn't connect to huggingface.co". Fixed by priming AS THE RUNTIME USER and
  proving the offline load as that user IN THE BUILD.
  MANIFEST VERIFIED: base digest == registry; all 9 pinned versions == versions installed IN THE
  IMAGE; run digest == docker inspect. arch aarch64; torch intra=1/interop=14;
  cgroup memory.max = 12,884 MB; os.cpu_count()=14 (HOST) inside a 4-CPU quota — which is exactly
  why threads are pinned explicitly.
- STEP 4 LADDER (12GB cap, swap=memory, network none):
    rung 100: 175s, goodput 98, faults 2, peak RSS 1,405 MB (12% of limit)
    ckpt 250: current RSS 1,121 MB, peak still 1,405 MB -> high-water then RELEASE, no leak
  12GB HELD comfortably. My expectation that GovDocs would exceed 7.95GB was WRONG, and the reason
  matters: 7.95GB was 8 uvicorn workers x conc 32; this ladder is ONE in-process pipeline, one doc
  at a time. Container memory is dominated by WORKER COUNT, not document size.
  Rung 2000 did NOT complete (~0.26 docs/s => ~2h). Checkpointed, so the partial curve survives.
- NOT DELIVERED: RocketRide image (not built), simultaneous both-arms run, rung 3, 10k distinct
  PDFs (fetch relaunched detached; ~200 PDFs per 486MB zip => 10k needs ~24GB/~5h).
- A13 evidence rebuilt as a13_ordering_reconstructed__*.json with MIXED PROVENANCE stated:
  ascending block LOG-PARSED; descending and prewarm blocks TRANSCRIBED from the session-11 report
  table because their JSON was clobbered AND their stdout was piped to grep. Spreads/gates/CIs
  unrecoverable for those two. STATE.md citation repointed with the caveat inline.
