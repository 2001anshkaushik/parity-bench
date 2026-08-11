# STATE — durable resume point

**Written 2026-08-05.** Assumes the reader knows nothing about this project. Read this first.

---

## 0. What this is

Ansh owns the **LlamaIndex FastAPI service** for **WS-1 "Service Parity"** — a three-way
comparison (RocketRide engine, LangChain/LangGraph, LlamaIndex) all implementing the same
document-embedding pipeline behind the same wire contract. Teammates: **Shashi** (owns the
RocketRide service), **Leela** (owns the shared schema and the mt10k reference data).

`benchmark-A/` was an earlier parallel exploration, superseded by WS-1 after the Aug 4 exec
review. Its findings were harvested into `FINDINGS_FOR_WS1.md`; the directory is now where the
LlamaIndex service and all measurement work lives.

## 1. Environment

| | |
| --- | --- |
| Host | Apple M4 Pro, 14 cores (10P + 4E), 48 GiB, macOS 26.6, arm64 |
| Python | `$REPO/.venv` → 3.12.13 |
| Working dir | the clone root (`$REPO/parity-bench`) |
| Engine | `server-v3.3.1`, reports `3.3.1.35` hash `a0817cc6`, installed at `<clone>/engine/` |
| Engine SHA256 | `846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836` |
| SDK | `rocketride` 1.3.0 (co-released with server 3.3.1 — pairing verified from release manifests) |
| Key libs | llama-index-core 0.14.23, sentence-transformers 5.6.1, torch 2.13.0, langchain-text-splitters 1.1.2 |

**Cost constraint: $0. Everything runs locally. No paid cloud.**

## 2. THE STANDING VERIFICATION PROTOCOL (verbatim — this governs everything)

```
=== STANDING VERIFICATION PROTOCOL — applies to every step, every run ===

Track record so far: the collector biased results 100×; IPC cost was
mis-measured by 115×; a single-process driver understated throughput 4.8×;
asymmetric deadlines manufactured a fake 7× gap; the alloc test freed memory
immediately so it never tested what it claimed; the hang ratio turned out to be
pool-width arithmetic; a service declaring 14 workers measured 4. In this
project, the instrument is wrong more often than the system under test. Behave
accordingly.

BEFORE reporting any number:
1. TWO INDEPENDENT METHODS. Any load-bearing number needs a second method with
   different failure modes. One method = label it PROVISIONAL, never headline.
2. DECLARED ≠ MEASURED. Never trust a config value, a flag, a worker count, or
   a docstring. Measure it. When they disagree, that gap IS a finding.
3. NULL CONTROL. Run the variant where you predict no difference. If a
   difference appears, the instrument is broken — stop and fix it.
4. REPRODUCE. n≥3, randomized order, report spread. A single-run number is
   never reported as fact.
5. DIRECTION-OF-BIAS. For each finding ask: does this favor RocketRide? If yes,
   hunt twice as hard for the artifact. Favorable results get more scrutiny,
   not less.
6. STRONGEST ALTERNATIVE. Before writing a conclusion, state the best rival
   explanation and the experiment that separates them. If you can't separate
   them, say so in the report rather than picking one.
7. WHAT WOULD A HOSTILE REVIEWER SAY. One sentence per finding, answered.

LABEL EVERY CLAIM: VERIFIED (two methods, reproduced) / PROVISIONAL (one
method) / UNVERIFIED (asserted, not established). No unlabeled claims.

WHEN A NUMBER IS SUPERSEDED: add a correction banner to every doc carrying the
old value, in the same turn. Never leave a stale figure anywhere.

STOPPING RULE — this must not become infinite. Verification effort scales with
how load-bearing the number is: headline claims get the full protocol,
incidental observations just get a label. If a check would take >30 min and
isn't load-bearing, label it PROVISIONAL, log it as an open item, and move on.
Say what you skipped and why.
=== END PROTOCOL ===
```

Standing operational rules layered on top: pre/post health checks and orphan cleanup around every
probe (`working/harness/engine_ops.py::preflight/postflight`), a 90 s livelock watchdog, never leave the
process table above ~750, append to `progress.md` as you go.

## 3. THE HEADLINE FINDING — document weight (the burst/sustained story is DEAD)

> **⚠️ SESSION 6 — READ THIS BEFORE ANYTHING ELSE IN THIS SECTION.**
> The **31 % sustained decay is WITHDRAWN** — it does not reproduce (6.0 % on exact replication;
> median +1.5 % RR / +1.0 % LI over a symmetric n=3 with randomised order, both arms swinging in
> both directions, 0 failures in ~10,000 requests). It was a single unreplicated draw from a
> statistic whose own noise band is ±12–18 pp, with no control arm.
> **Therefore the burst-vs-sustained framing and the sustained token curve are both invalid.**
> `CROSSOVER_FINDING.md` is ON HOLD and must not be sent or presented.
> What actually differs between the harnesses is **configuration**, and the live axis is
> **concurrency** — see `CONCURRENCY_CHARACTERIZATION.md`.

**[VERIFIED, 2 independent methods — BURST MODE]** Measured with a fresh task per repetition, the
two services cross over at **200–400 embedded tokens per document**. Below it LlamaIndex wins;
above it RocketRide wins.

| tokens/doc | RocketRide | LlamaIndex | ratio RR/LI |
| ---: | ---: | ---: | ---: |
| ~50 | 477.4/s | 879.1/s | 0.553 — LlamaIndex 1.81× ahead |
| ~100 | 350.2/s | 649.3/s | 0.533 |
| ~200 | 320.1/s | 406.6/s | 0.787 |
| ~400 | 244.2/s | 196.2/s | **1.272 — RocketRide 1.27× ahead** |

Across 50→400 tokens: **RocketRide retains 0.51× of its throughput; LlamaIndex retains 0.22×.**

### Mechanism [VERIFIED]

> **RocketRide is overhead-bound.** It pays a high fixed per-request cost — WebSocket + DAP
> protocol + engine IPC + **4 node hops** — that dominates small documents and amortises as
> documents grow.
>
> **LlamaIndex is compute-bound.** Cheap request path (HTTP + in-process), so throughput tracks
> token count almost directly.

**Embedding cost is linear in TOKENS, not characters and not chunks.** This is the single most
important operational fact in the project.

### Why it matters: mt10k sits ON the seam

| token band | share of mt10k | favours |
| --- | ---: | --- |
| < 200 | 21.4 % | LlamaIndex |
| 200–400 | 38.3 % | crossover zone |
| ≥ 400 | 40.3 % | RocketRide |

mt10k median = **338 embedded tokens**. That is why the real-corpus margin is a modest 13 % rather
than decisive either way — **mt10k is near worst-case for RocketRide.**


## 3b. WEEKEND RUN — launched 2026-08-07 22:42, unattended (read this on Monday)

**Operational detail, phase caps, status command, stop/resume: `publishable/WEEKEND_RUN.md`.**

### The blocker that shaped the design

**RocketRide cannot be containerised on this host.** `server-v3.3.1` ships **darwin-arm64,
linux-x64 and win64 — there is no linux-arm64 asset**, and the repo's Docker workflow targets
`linux/amd64` only. Containerising it here needs x86 emulation, which `DOCKER_ARCHITECTURE.md` §1
forbids because emulation would silently corrupt the numbers. One arm containerised + one native
would be asymmetric, which is worse.

**Decision: both arms run NATIVELY and symmetrically.** The memory ceiling is therefore a **soft**
limit enforced by the worker, not a cgroup — it detects a breach, it does not prove the process
would have been killed. Disclose that with any result. The LlamaIndex container demo remains a
separate delivered artifact.

**If a container comparison is ever required, the options are:** (a) obtain/produce a linux-arm64
engine build, (b) run both arms under x86 emulation so at least the emulation is symmetric —
slow and still not production-representative, or (c) move to a linux-x64 host, where the shipped
linux-x64 build runs natively. **(c) is the only one that yields production-meaningful numbers.**

### Runner design

* `weekend_runner.sh` — phase orchestrator, hard wall-clock cap per phase, advances on expiry.
  `set -uo pipefail` **without `-e`**: a failing phase must advance, not abort the weekend.
* `weekend_worker.py` — one phase/arm, **continuous processing, not rungs** (rungs reprocess
  0..N repeatedly and waste hours), checkpoint every 100 docs, heartbeat every 60 s before *and*
  after each document, goodput asserted per document, resume from checkpoint, OOM caught as a
  result with the RSS curve preserved.
* `weekend_summarise.py` — rolls all checkpoints into `publishable/WEEKEND_RESULTS.md`; safe to
  run at any time against a live run.
* Every result goes through `harness.resultio` (unique path, cannot clobber).

### Bugs found and fixed during build — all would have cost the weekend

| bug | consequence if unfixed |
| --- | --- |
| **Fixed `project_id` in the RocketRide arm** | one live task per `project_id` (STATE §9): p0, p3 and p4 would each have died with *"Pipeline is already running"* — **the entire RocketRide arm lost**. Now unique per phase+pid+time |
| **zsh `nomatch` aborted the state-clearing `rm`** | the first launch silently resumed from dry-run checkpoints and "completed" p0 in 33 s. Use `find -delete`, never `rm glob` |
| Heartbeat only fired after a document | a 1,000-page PDF would look frozen for minutes — the exact "slow vs dead" ambiguity the heartbeat exists to remove |
| OOM before the first RSS sample | empty memory curve at precisely the moment the curve matters |
| `timeout` used in the dry run | not present on macOS |

### What to do with the data on Monday

1. `cat status.txt` — is it still running, and which phase?
2. `../.venv/bin/python weekend_summarise.py` — regenerate `publishable/WEEKEND_RESULTS.md`.
3. Compare **peak RSS and RSS slope** between arms. That is the axis A13 does not touch and the
   one leadership asked for. **Do not compare throughput** — invalid on this host.
4. Check fault classes per arm on identical inputs: same corpus, same documents, so a divergence
   in fault classes is a real behavioural difference, not corpus noise.
5. If any phase shows `memory_limit_exceeded`, the breach index, document and full curve are in
   its checkpoint — that is a finding, not a failure.

### Early signal (first minutes, PROVISIONAL — one phase, small n)

p0 insurance, 200 documents each, identical corpus: LlamaIndex completed 200 in ~68 s; RocketRide
peak RSS reached **2,651 MB** by document 100 against LlamaIndex's sub-1 GB working set. Consistent
with the memory *shapes* already established (finding 1m) but **not** a result — n is small, one
run, and the arms were not interleaved.


## 3c. WEEKEND RUN FORENSICS (2026-08-09) — full analysis in `publishable/WEEKEND_FORENSICS.md`

**Denominator first: LlamaIndex processed 10,000 documents; RocketRide processed 267 (2.7 %).**
There is **no RocketRide endurance result** from this run.

| # | finding | label |
| --- | --- | --- |
| W1 | **RocketRide truncates returned `page_content` at the first NUL byte.** Embeddings are computed correctly over the full text (cos = 1.0000 vs LlamaIndex on all 11 chunks); only the returned text is lost. Truncation offset matched the first NUL exactly on 11/11 chunks; clean-ASCII null control byte-identical | **VERIFIED** (3/3 reproduction + mechanism + null control) |
| W2 | The failing document `001_001157.pdf` (index 267, sha256 `5e35cfd7…`) is **not** in the known 1.42 % malformed set — it parses cleanly but yields binary control characters from a broken font encoding | **VERIFIED** |
| W3 | **The engine did not crash or cascade.** The run stopped because our gate is deliberately fatal | **VERIFIED** |
| W4 | LlamaIndex completed 10,000 docs, 9,898 goodput; its 102 faults are pypdf extraction faults in shared pre-arm code, identical for both arms | **VERIFIED** |
| W5 | ~~RocketRide leaks ~1,500 MB / 1,000 docs~~ | **WITHDRAWN** — window mismatch (267 vs 10,000 docs) plus endpoint placement inside a ±500 MB oscillation. Excluding warm-up, BOTH arms show a negative slope, which is not a physical claim |
| W6 | LlamaIndex post-ramp memory ≈ flat: **+14.8 MB/1k** (p2, sequential, 10,000 docs) and **+20.4 MB/1k** (p4, under contention, 8,888 docs). Peak drifts while current plateaus → allocator retention, not runaway accumulation | **VERIFIED** (2 independent windows) |
| W7 | RocketRide resident memory is higher than LlamaIndex on identical work, **both arms native, same session** | **VERIFIED (direction)**; magnitude **PROVISIONAL** at 1.82×–3.19× depending on window/statistic |
| W8 | **The goodput gate cannot detect garbage input.** LlamaIndex embedded 39,803 chars of binary control codes into 11 confident unit-norm vectors and passed every check | **REFUTED** (the gate's claim to verify work is shape-only) |

**Instrument defects found (fix before the next run):** the RocketRide memory sampler matched
processes by **name**, so it counted a five-day-old unrelated engine (104 MB, ~5.8 % of the
median) — match by **PID** instead; no system-wide memory cross-check was recorded, so the tree
walk could not be falsified; and a fatal content gate ended a 16-hour phase at 2.7 % completion.

**The weekend run was native-on-native**, not containerised-vs-native. The containerised ladder in
`DOCKER_DEMO_RESULTS.md` is a separate run and its numbers are not comparable to these.


## 3d. SESSION 14 — NUL bug filed, content blind spot closed, regression suite added

| # | finding | label |
| --- | --- | --- |
| S1 | **NUL truncation reduced to a minimal reproducer**: `send("AAAA\x00BBBB")` returns `"AAAA"`. No PDF involved — the defect is in the text path | **VERIFIED** |
| S2 | **Direction proven OUTBOUND, not inferred**: cos(returned vector, embedding of FULL text) = **1.0000**; vs truncated-text embedding = 0.7698. The engine embeds the full text and loses it only in the response | **VERIFIED** |
| S3 | **Only `0x00` truncates.** All 32 other control chars (`0x01`–`0x1F`, `0x7F`) return intact | **VERIFIED** |
| S4 | Only `page_content` is affected; `embedding`, `embedding_model`, `metadata`, `type` and all top-level keys are intact. **Untested:** error payloads, non-`response_documents` components | **VERIFIED** (within fields observed) |
| S5 | Always cut at the **first** NUL — leading NUL empties the chunk entirely; trailing NUL loses nothing | **VERIFIED** (6 boundary cases) |
| S6 | **Prevalence 0.30 % [VERIFIED — 2 independent methods]**: offline scan 3 of 991 (Wilson95 0.10–0.89 %); live pipeline detection 8 of 2,200 = 0.36 %, inside that CI ≈ **30 documents in 10,000**. Loss per affected document is severe and unpredictable: one document with a *clean-looking* printable ratio of 0.992 loses **98.9 %** of its text | **VERIFIED** (seeded random sample) |
| S7 | **A printable-ratio heuristic CANNOT detect the NUL bug.** Two of the three NUL documents (0.9923, 0.9884) sit inside the legitimate range (10 lowest legit: 0.9757–0.9944). Two independent checks are required | **VERIFIED** |
| S8 | **Content-sanity threshold derived from the corpus, not chosen**: legit p1 = 0.9944, 2nd-lowest = 0.9757; known garbage = 0.700 and 0.679. Threshold **0.90** sits in the empty band. Catches document 267 (`garbage_and_nul`); **0/40 legitimate documents flagged** | **VERIFIED** |
| S9 | **Reclassification of LlamaIndex's 9,898 "goodput" documents: ~30 (0.30 %, CI 10–88) would fail content sanity.** They did real embedding work, so throughput/memory are unaffected — what changes is what "goodput" means for retrieval quality | **PROVISIONAL** (sample-based extrapolation) |
| S10 | **p0-vs-p3 RocketRide peak discrepancy explained**: post-ramp oscillation amplitude is 1,180 MB (p0) / 1,033 MB (p3), *larger* than the 798 MB peak difference. Both ran the identical first 200 documents yet medians differ by 713 MB — **RocketRide memory is not reproducible run-to-run to better than ~700 MB** | **VERIFIED** |

**Regression suite added**: `working/scripts/regression_selftest.py` — **8 tests, one per defect
that produced a wrong number**: NUL truncation (xfail, open upstream), engine-by-PID-not-name,
non-fatal gate, slope window guard, content sanity, resultio collision, goodput shape checks,
and a `setsid` guard. 7 pass, 1 xfail, exit 0.

**`setsid` recurrence:** the endurance launch used `nohup setsid …` again and died instantly
(`setsid: No such file or directory` — it does not exist on macOS). Caught in 60 s this time by
verifying the PID rather than assuming. Now covered by a regression test.

**Filed:** `publishable/BUG_NUL_TRUNCATION.md` — filing-ready, with reproducer, scope, boundaries,
direction proof, prevalence, version/build identity, and answers to maintainer objections.


## 3e. SESSION 15 — oscillation mechanism, and the meeting artifact

| # | finding | label |
| --- | --- | --- |
| M1 | **Sawtooth is NOT process spawn/exit.** Sampled the engine tree at 0.5 s for 120 s during a live run: process count **constant at 2**, one child PID throughout, while tree RSS still swung **488 MB**. The architectural explanation that would have exonerated the engine is refuted | **VERIFIED** |
| M2 | **Sawtooth is NOT document-size variance.** RocketRide corr(document size in flight, RSS) = **−0.14** (none). LlamaIndex has a *stronger* size correlation (−0.52) yet oscillates far less on the **identical** documents in the **identical** order | **VERIFIED** |
| M3 | Oscillation mechanism itself | **UNVERIFIED** — both leading candidates eliminated; remaining candidate is allocator behaviour inside the engine's task process, not inspectable from outside |
| M4 | **Operational statement (not a stability verdict): size containers to PEAK, not median.** RocketRide peak/median **1.76×**, LlamaIndex **1.16×** — sizing to the median undersizes RocketRide by 76 % vs 16 % | **VERIFIED** |
| M5 | **42 % run-to-run spread on byte-identical input** (medians 2,397 / 1,639 / 1,811 MB over the same first 200 docs). NOT the sawtooth: divergence is present in the **first** post-warm-up sample (2,631 vs 1,949 vs 1,951), so it is set at task creation, not accumulated. Same engine PID served all three, so not a fresh-engine effect | **cause UNVERIFIED** |
| M6 | **No `linux-arm64` build has EVER been published.** All **51 releases** examined: win64 36, darwin-arm64 24, linux-x64 24, linux-arm64 **0**. Strengthens the platform verdict from "this release lacks it" to "the project has never shipped one" | **VERIFIED** |
| M7 | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md)** — Memory ratio **2.08×** median-to-median (matched windows) vs **3.0×** peak-to-peak. Different statistics, both real: 2.08× is consumption, 3.0× is what must be provisioned | **VERIFIED (direction)**, magnitude **PROVISIONAL** |

**Meeting artifact: `publishable/MEETING_2026-08-10.md`** — platform verdict, what was measured,
three product findings, memory, what is not established, and the phased roadmap. Verified clean:
zero withdrawn figures, zero broken file references, no future dates.


## 3f. SESSION 16 — matched replication (complete)

| # | finding | label |
| --- | --- | --- |
| R1 | **Goodput and faults are perfectly reproducible under a matched configuration.** 3 blocks x 2,000 docs, identical every block: LlamaIndex 1,972 goodput / 28 faults, RocketRide 1,965 / 35. Difference is **exactly 7 documents per 2,000 (0.35 %)** — the NUL truncation — and nothing else | **VERIFIED** (3/3 identical) |
| R2 | **Matched memory ratio 2.60x [1.96, 2.69] — DIRECTION ONLY.** RocketRide fails the 10 % gate at **24.0 % spread**; LlamaIndex passes at 4.3 % | **direction VERIFIED, point estimate NOT REPORTABLE** |
| R3 | ~~RocketRide memory rose +32 % across three identical blocks, monotonic~~ | **WITHDRAWN (session 17)** — three further blocks on the same engine gave 2,055 / 2,070 / 2,112. Four of six cluster at 2,055–2,112 (2.7 % spread); blocks 2–3 were a transient excursion that fully reverted. Three points caught the rising half |
| R4 | Mechanism of the **excursion** (not growth) | **UNVERIFIED** — intermittent, not cumulative. The earlier reasoning was also flawed: teardown RSS is not operating RSS, so "192 MB after teardown" never ruled out parent growth. Now measured properly (S17-2) |
| R5 | **Harness asymmetry favouring LlamaIndex**: it gets a fresh process per block while the engine persists. Correcting for it moves the ratio further AGAINST RocketRide. Two defensible numbers: **fresh-vs-fresh 2.05x**, **long-running 2.5-2.6x** | **VERIFIED** |
| R6 | The **2.05x fresh-vs-fresh** figure independently reproduces the earlier matched-window **2.08x** from a different run and harness | **VERIFIED** (2 methods) |
| R7 | Run cost 14.7 vs 13.5 min/2,000 docs (**1.09x**), against the endurance run's 2.2x. Consistent with most of that gap being configuration, **NOT a throughput finding** — A13 stands | **hypothesis for Phase 2, UNVERIFIED** |
| R8 | **The endurance wall-clock comparison is VOID, not correctable.** The 3.07x pinning cost came from short blocks under different thermal/memory conditions and must not be applied to a 2.47 h continuous run | **VERIFIED (methodological)** |

**New open item A17:** `A3_SERIALIZATION_FINDING.md` says pinning helps above concurrency ~4, from
400/1,600-token synthetic text. With the concurrency-1 cost now measured at **3.07x on real
documents**, the crossover concurrency is **UNVERIFIED for this corpus**. Not re-measured — logged.

**New open item A18:** does RocketRide's +32 %/3-blocks growth continue, plateau, or reset on
engine restart? Blocks the memory magnitude claim. ~40 min.


## 3g. SESSION 17 — leak vs plateau resolved, and a claim of mine withdrawn

| # | finding | label |
| --- | --- | --- |
| S17-1 | **NOT A LEAK.** Six 2,000-doc blocks, same engine, never restarted: 2,065 / 2,674 / 2,717 / **2,055** / 2,070 / 2,112 MB. Block 4 fell 662 MB back to block 1's level. Modal cluster of 4 blocks at **2,055–2,112 (2.7 % spread)**; blocks 2–3 were a transient excursion that reverted | **VERIFIED** (6 blocks) |
| S17-2 | **Component decomposition, sampled separately during each block**: engine parent **flat** (238.7 → 242.5 MB), task tree **declining** (1,568.6 → 1,538.2), **our own driver growing +51.7 MB**. Neither the engine nor its task grows; the only growth is our harness (~2.5 % of RocketRide's total, inflating it) | **VERIFIED** |
| S17-3 | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md)** — **Memory ratio ~2.0×, three independent methods**: matched-window 2.08×, fresh-vs-fresh 2.05×, all-six-block median **2.03×**. The earlier 2.5–2.6× came from the two excursion blocks and is superseded | **direction VERIFIED (3 methods)**, magnitude ~2.0× **PROVISIONAL** (gate fails at 24 % from bimodality, not centre uncertainty) |
| S17-4 | **Goodput identical in all SIX RocketRide blocks** (1,965 every time) and all three LlamaIndex blocks (1,972). The 7-document difference per 2,000 is the NUL truncation, now reproduced 6/6 | **VERIFIED** |
| S17-5 | The 24 % gate failure is **bimodality, not drift** — capacity must cover the excursion, but the service is not degrading over time | **VERIFIED** |
| S17-6 | **CI estimator check**: 2.60× [1.96, 2.69] was ratio-of-medians with a bootstrap interval; correct estimator, but at n=3 the interval is the entire attainable range and the point sat high because the sample was left-skewed. **No central estimate belongs on a trending/bimodal sample** | **VERIFIED (methodological)** |

**A18 retired as originally framed** — restarting the engine between blocks was meant to reset
growth, and there is no growth to reset. Replaced by **A19: what triggers the ~+30 % excursion?**
It is intermittent; catching one with instrumentation running needs many more blocks. Not run.

**Artifact restructured** to lead §2 with functional equivalence (identical goodput and fault
counts, arms differing by exactly 7 documents per 2,000 — all NUL truncation), memory demoted to
the secondary result.


## 3h. SESSION 18 — A19 tested and refuted; an accounting trap avoided

| # | finding | label |
| --- | --- | --- |
| S18-1 | **The excursion is NOT caused by a neighbouring LlamaIndex block.** Retrospective correlation was 6/6 (excursion in exactly the 2 RocketRide blocks following a LlamaIndex block, none of the 4 others) but confounded by session and time. Controlled RO→LL→RO test: 1,826.0 → 1,819.6 MB, **−0.4 %** | **REFUTED** (direct test) |
| S18-2 | Host-level memory sampling (used / available / swap) added to the harness. The excursion window showed nothing distinguishing; A19 is now **instrumented but not yet triggered** | **VERIFIED** (instrument added) |
| S18-3 | ⚠️ **See MATCHED_LAYERS.md** — **Excluding our driver from RocketRide's total is ASYMMETRIC and must not be done.** It moves the ratio 2.01× → 1.74×, but LlamaIndex's single-process figure already contains the same harness work and cannot have it subtracted. Symmetric: count-on-both **2.01×**, exclude-from-both **~2.47×**. As-measured **2.01×** stands and is conservative | **VERIFIED (methodological)** |
| S18-4 | Goodput reproduced again: RocketRide **1,965** in blocks 7 and 9, LlamaIndex **1,972** in block 8 — now **8/8** and **4/4** respectively | **VERIFIED** |

**Regression test #10 added**: asserts the meeting artifact's protected content (thread-asymmetry
table, "disadvantageous configuration", the VOID marking, the functional-equivalence lead, the
no-reversal caveat, the withdrawn-leak marker) is present, and that withdrawn figures never appear
without a withdrawal marker nearby. An edit destroyed this content twice; it is now structural.

## 3f. SESSION 19 — the arms did not run the same shape [VERIFIED]

**`publishable/MATCHED_LAYERS.md` is the full analysis.** Read it before quoting any memory or
wall-clock number.

| # | finding | label |
| --- | --- | --- |
| T1 | **LlamaIndex ran in-process; RocketRide ran client–server.** `weekend_worker.py:148` imports `LlamaIndexPipeline` and calls `self.p.process(text)` — no socket. `RocketArm` uses `RocketRideClient` over **WebSocket + DAP** to `:5565`. `matched_replication.py` and `docker/ladder.py` start uvicorn **zero** times. `working/ws1/service.py` was **never used** in any published run | **VERIFIED** (code + live process measurement) |
| T2 | **Process topology 1 vs 3.** Live, engine `pid=38379`, 0.25 s sampling: RocketRide = driver + engine parent + **1** task child; LlamaIndex = 1 process, model loaded into the driver (RSS 22.9 → 560.0 MB across `warm()`). Independently reproduces M1 | **VERIFIED** (2 methods) |
| T3 | **RocketRide carries a ~240 MB engine parent with no counterpart** in the other arm — 23 % of LlamaIndex's entire footprint — plus two extra interpreter baselines | **VERIFIED** (six-block decomposition, blocks 4–6) |
| T4 | **The repo already published both directions and never reconciled them.** In-process LlamaIndex → RocketRide 2.0× worse. Uvicorn LlamaIndex at 8 workers → LlamaIndex **22.8× worse at idle** (4,642 vs 204 MB). Same two systems, opposite verdicts; the only variable is the LlamaIndex arm's topology. **Neither ratio is a framework property** | **VERIFIED** |
| T5 | Transport cost ~+36 ms/document (n=4, spread 36–41 %, **fails the 10 % gate**). Over 2,000 docs that is the same order as the entire observed +72.7 s block gap — but transport cost and genuine per-document cost are **not separated** | **PROVISIONAL — direction only** |
| T6 | `run_service.sh` defaults to **14** workers while the published 4,642 MB was taken at **8** — declared ≠ measured, and it moves the headline with a shell variable | **VERIFIED** |
| T7 | **Functional equivalence is UNAFFECTED.** Goodput, fault classes and the NUL defect are properties of the bytes returned, not the transport. Both arms returned identical goodput every block *through different topologies* | **VERIFIED** |

**Direction of bias:** the asymmetry biases **against RocketRide** on memory and wall clock. Hunted
for mechanisms by which it instead flatters RocketRide (MATCHED_LAYERS.md §2.4); the strongest —
"its task tree holds more models" — is **refuted**: the tree is one process holding one model, so a
matched re-run will shrink the gap, not erase it.

### Platform addendum — 2026-08-11

| # | finding | label |
| --- | --- | --- |
| P1 | **Run-to-run wall-clock swing of 12–37 % on identical work**: LlamaIndex-HTTP 892.9 → 794.4 s (12.4 %), RocketRide 1,119.9 → 819.8 s (36.6 %); same 2,000 docs, same order, identical goodput and fault counts in both blocks. **Both arms were slowest on their FIRST block**, so this shares the documented cold/power-state mechanism rather than being independent of it — an earlier draft claimed "nothing changed between them", which was wrong and is corrected. Consequence: the **10 % gate cannot be met for wall clock on this host**, and the first block of a run is warm-up at the BLOCK level (the 50-document warm-up does not cover it) | **VERIFIED** (same run, same log) |

## 4. Verified findings, with labels

| # | finding | label | evidence |
| --- | --- | --- | --- |
| 1 | Crossover at 200–400 tokens (**BURST mode only**); RR overhead-bound, LI compute-bound | **VERIFIED** (2 methods) | `working/results/token_sensitivity.json`, `working/results/parity_corpus.json` |
| 1a | ~~Sustained mode: LlamaIndex faster at 100–6,400 tokens~~ | **INVALID (session 6)** — rested on the withdrawn decay; both harnesses were configuration-dependent | superseded by `working/results/concurrency_barrier.json` |
| 1b | ~~RocketRide decays 31.3 % under sustained load~~ | **WITHDRAWN (session 6)** — does not reproduce; 6.0 % on exact replication, +1.5 % median over n=3; LlamaIndex shows the same ±12–18 pp swing | `archive/results/decay_rootcause.json`, `working/results/decay_symmetric.json` |
| 1b2 | **Neither arm decays under sustained load** — RR +1.5 %, LI +1.0 % median (n=3, randomised, 0 failures) | **VERIFIED** (2 methods: exact replication + symmetric n=3) | `working/results/decay_symmetric.json` |
| 1b3 | RocketRide flat in offered concurrency 2→32 — **ONLY AT DEFAULT THREAD SETTINGS, and not caused by the engine** (session 7) | **VERIFIED but CONDITIONAL** | `working/results/concurrency_barrier.json` + `working/results/a3_serialization.json` |
| 1g | **The engine is NOT the bottleneck**: request path scales 3.69×, Python-node dispatch costs ~3 %, pure-Python CPU in a node scales 3.59×; only the embedding arm is flat (1.46×) | **VERIFIED** | `working/results/a3_serialization.json` |
| 1h | **Cause = native thread oversubscription.** One embed occupies 1.45 cores at default vs 0.49 pinned; per-request CPU inflates 80 % under concurrency | **VERIFIED** (2 methods: intervention + system-wide CPU-time accounting; pure-Python null control unmoved) | `working/results/a3_threads.json` |
| 1i | **Thread pinning at engine start → RR scaling 1.43×→3.04× @400tok and 1.18×→3.05× @1600tok**; helps above conc≈4, HURTS below (0.41–0.55× at conc 1) | **VERIFIED** (2 sessions, ABA design, n=5, gated) | `working/results/reanchor_tuned.json` |
| 1k | **Pin verified INSIDE the task process**: `torch.get_num_threads()` = 10 default → 1 pinned. `torch_num_interop_threads` stays **14 even when pinned** — no env var reaches it | **VERIFIED** | `working/nodes/env_probe`, `working/results/reanchor_tuned.json` |
| 1l | **Anchor B flips with tuning**: 1600tok/conc2 RR/LI = **1.201 [1.185,1.217] untuned** (reproduces the 1.190× reference) but **0.926 [0.917,0.934] tuned**. Best-achievable config is CONCURRENCY-DEPENDENT | **VERIFIED** (both arms pass the gate in both blocks) | `working/results/reanchor_tuned.json` |
| 1m | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md, opposite direction)** — **Peak RSS**: RR idle 204 MB → 2,356 MB @6400tok/c32; LI idle **4,642 MB** → **7,950 MB**. LI's floor is fixed (8 workers × model); RR grows with document size | **VERIFIED** (continuous 250 ms sampling) | `working/results/memory_ceiling.json`, `working/results/memory_rr_fixed.json` |
| 1n | **A6 RESOLVED — 9.29 and 1.45 measure different statistics.** At default threads one embed: time-average **2.42 cores** (c=1) / 4.83 (c=8); p95 **4.17** / **10.08**; peak **7.75** / **13.09**. Finding 7's 9.29 is a p95/peak under load; session-7's 1.45 was a time-average with a contaminated baseline | **VERIFIED** | `working/scripts/a6_peak_vs_mean.py` |
| 1o | **Engine PDF path is Tika, VERIFIED by execution** — `com.rocketride.tika_api.TikaApi`, JVM loaded **in-process via JNI** (no separate java process). Engine bundles OpenJDK 17.0.19 Temurin aarch64 | **VERIFIED** (source + execution) | `pdftest/`, engine binary strings |
| 1p | **LlamaIndex has NO PDF reader installed**; core maps `.pdf`→`PDFReader` from the absent `llama-index-readers-file` and **silently returns `{}`**. Default parser once installed is **pypdf**, not PyMuPDF | **VERIFIED** | PyPI metadata + `llama_index.core` source |
| 1q | Tika vs pypdf on a simple 3-page text PDF: **99.10 % agreement**; pypdf 100.00 % vs source, Tika 99.10 % | **PROVISIONAL** (one easy PDF; says nothing about scanned/multi-column) | `working/results/pdf_parser_diff.json` |
| 1r | **Inter-op thread pinning is HARMFUL** — lands in-process (14→1) but costs 14.3 % @conc8, 0.999× @conc2 | **VERIFIED** (gated, drift control held) | `working/results/anchor_b_interop.json` |
| 1s | **ANCHOR C: RocketRide width = 17.24, VERIFIED** by the guarded instrument (escaped tracking, confirmed by doubling) — reproduces finding 8's ~17 | **VERIFIED** | `working/results/anchor_c_width.json` |
| 1t | **LlamaIndex has NO single pool width** — the guarded instrument REFUSED (estimate tracked offered concurrency to 96). Sleeping holds do not occupy a worker: `/process` is a sync `def` on Starlette's threadpool. Finding 9's width=8 is its **CPU knee**, not its slot count | **VERIFIED** (instrument refused rather than guessing) | `working/results/anchor_c_width.json` |
| 1u | ~~LlamaIndex saturates at concurrency 4~~ **WITHDRAWN session 11** — ascending cold sweep; pre-warmed estimate is c16 @ ~226/s. Original: (74.7/s @400tok, 29.1/s @1600tok). Past it throughput is flat-to-degrading while P99.9 goes 96 ms → 2,987 ms. **0 errors at every level to c=64** | **PROVISIONAL** (1 session, n=5 gated per cell) | `working/results/isolated_profile_llamaindex_PREWARM.json` (the session-9 ascending run it originally cited was overwritten by the pre-warm re-run; the withdrawn session-9 data is preserved at `archive/results/isolated_profile_llamaindex_SESSION9.json`) |
| 1v | ~~Sessions 6–8 compared past saturation~~ **WITHDRAWN session 11** — rested on the withdrawn c4 figure; with saturation at c16 those concurrencies were at or below it. Original: Those numbers measure queueing, not serving capacity | **VERIFIED** (follows from 1u) | — |
| 1w | **Custom PARSE nodes work in the engine** — `pdf_probe` ran pypdf 6.15.0 in the engine's embedded CPython, output byte-identical to standalone. **Tika is a default, not architecturally forced.** But adding the dependency required hand-copying into `engine/lib/python3.12/site-packages/` — no supported path | **VERIFIED** (executed) | `working/nodes/pdf_probe/`, `PARSER_PREMISES.md` |
| 1y | ~~OPTIMAL-POINT COMPARISON~~ **WITHDRAWN session 11** — placed each arm at a saturation point that does not exist, and measured both cold. Original: — both arms at their OWN saturation, one session, drift control −0.4%/−1.4%**: untuned RR/LI = **0.789** [0.776,0.800] @400tok, **0.886** [0.871,0.902] @1600tok; tuned = **0.758** [0.742,0.786] @400tok, 0.973 [0.890,1.025] @1600tok (RR gate-failed). **LlamaIndex ahead at every quotable point.** The hypothesis of near-parity-with-RR-ahead-at-1600 is REFUTED | **VERIFIED** (both arms gate-pass in 3 of 4 cells; drift control held) | `archive/results/optimal_point.json` |
| 1z | ~~RocketRide saturation config/size-dependent~~ **WITHDRAWN session 11** — ascending cold sweep. Original:: c4 (tuned/400), c32 (tuned/1600), c16 (untuned/400), c4 (untuned/1600). LlamaIndex is c4 throughout. Peak plateaus: RR untuned 63.8/s @400, 28.7/s @1600 | **PROVISIONAL** (1 profile run; absolutes did not reproduce — see A13) | `archive/results/isolated_profile_rocketride.json` |
| 1aa | **RSS sampler is NOT an observer effect** — sampler on vs off, alternated n=3: −0.4 % | **VERIFIED by null control** | `working/results/sampler_nullcontrol.json` |
| 1x | **PyMuPDF is AGPL-3.0 / Artifex commercial** — disqualifying for a network service without procurement. pypdf BSD-3 (and LlamaIndex's own default), pdfplumber MIT, pdfminer.six MIT-but-STALE | **VERIFIED** (package metadata) | `working/dossiers/`, `PARSER_PREMISES.md` |
| 1j | **All prior RR-vs-LI throughput comparisons were tuned-service-vs-untuned-engine** (our service pins threads, the engine did not) | **VERIFIED** (follows from 1h + `working/ws1/run_service.sh`) | — |
| 1b4 | **RocketRide ahead 1.190× at 1,600 tokens / concurrency 2** [CI 1.184–1.196], BOTH arms pass the 10% gate (1.6%/0.5%) | **PROVISIONAL** (1 harness) — the only gate-passing head-to-head advantage in the project | `working/results/concurrency_barrier.json` |
| 1b5 | ~~The RocketRide arm is systematically noisier than LlamaIndex~~ | **WITHDRAWN (session 6)** — was our own harness desync. Under barrier-synchronised windows RR passes the gate in 8/10 cells (1.2–9.8% at 1600tok) | `working/results/concurrency_barrier.json` |
| 1c | ~~Services converge toward parity as documents get heavier~~ | **DOWNGRADED to UNVERIFIED (session 6)** — both supporting sweeps are configuration-dependent; not retested | — |
| 1d | **Pipeline topology is NOT a throughput factor** — 1-node vs 4-node = 0.88–1.13× | **VERIFIED** (1-node arm returns 159B vs 9–24KB — confound favours RR, retired by 1f) | `working/results/topology_persistent.json` |
| 1e | Chunk count does not drive the ratio (no trend, 1→13 chunks) | **VERIFIED** | `working/results/topology_persistent.json` |
| 1f | **Response payload size is not a measurable cost** — LI payload grew 100×→555× (15.9→115.4 KB) with no ratio movement | **VERIFIED** | `working/results/topology_persistent.json` chunk_vs_token bytes |
| 2a | **Result writes could not collide before session 12** — audit found 51/51 hardcoded output paths and 6 names claimed by >1 script; TWO runs were silently destroyed (session-9 ascending profile, and the descending-order run) | **VERIFIED** (audit + reproduction) | `working/harness/resultio.py` |
| 2b | **Collision guard proven** — `O_EXCL` at the syscall level and `ResultCollision` at the API level both refuse to overwrite | **VERIFIED** (attempted overwrite, both blocked) | `working/harness/resultio.py` |
| 2c | **Goodput gate catches the silent-`{}` PDF path** plus 5 other failure modes, and passes a correct document | **VERIFIED** (6 negative cases + null control) | `working/harness/goodput.py` |
| 2d | **GovDocs1 is 192× heavier per document than mt10k by bytes, 19× by tokens** (median 227,567 B / ~6,345 tok vs 1,186 B / 338 tok); max 1,000 pages; natural fault rate 1.42 % | **VERIFIED** | `working/results/govdocs1_characterization__*.json` |
| 2e | **Containerised pipeline works end to end offline under a 12 GB cgroup cap**: peak RSS 1,405 MB at 100 docs (12 % of limit), current RSS *fell* 1,405→1,121 MB by doc 250 — allocator high-water then release, no accumulation | **PROVISIONAL** (1 run, rung 3 incomplete) | `working/results/docker_ladder/ladder_llamaindex_*.json` |
| 2f | **Container memory is dominated by WORKER COUNT, not document size** — the 7.95 GB figure was 8 workers × concurrency 32; one in-process pipeline on 6,345-token documents peaks at 1.4 GB | **PROVISIONAL** (1 run, 1 concurrency) | as above |
| 2g | **`HuggingFaceEmbedding` derives its cache dir from the CALLING USER's home, not `HF_HOME`** — "model is baked" was true as root and false as the runtime user, surfacing as a misleading "couldn't connect to huggingface.co" | **VERIFIED** (build passed as root, failed as ws1, fixed by priming as ws1) | `docker/Dockerfile.llamaindex.layer` |
| 2h | **`llama-index-readers-file` cannot be installed for the PDF path alone** — its `__init__` imports the tabular readers, requiring pandas. We call pypdf directly | **VERIFIED** | `PARSER_DECISION.md` |
| 2 | mt10k corpus is the real one | **VERIFIED** | 10,000/10,000 sha256 vs Leela's manifest |
| 3 | mt10k shape: median 1,186 bytes, median 1 chunk (93.2 % single-chunk), median 338 tokens | **VERIFIED** | `working/results/corpus_characterization.json` |
| 4 | On real mt10k, RocketRide 1.13× faster (233.95 vs 202.27/s) | **direction VERIFIED, point PROVISIONAL** | RR arm spread 14.8 % FAILS the 10 % gate; direction corroborated by chunk sweep + token sweep |
| 5 | RocketRide ahead at every chunk count on 444-token-per-chunk text (1.23×–1.55×) | **VERIFIED** | `working/results/parity_corpus.json` chunk sweep |
| 6 | `sentence-transformers` silently selects `mps` (Apple GPU) when device unset | **VERIFIED** (3 methods) | null control with HTTP removed; direct device interrogation; service-level sweep |
| 7 | RocketRide's engine embeds on **CPU** | **VERIFIED** | `cores_busy 9.29`; source inspection said GPU and was **WRONG** |
| 8 | RocketRide effective pool width = **~17** | **VERIFIED** (2 methods) | hold-and-divide (17.1/17.2/16.6); alloc-hold wall-time arithmetic |
| 9 | LlamaIndex service effective width = **8** on cpu (declared 14 workers) | **VERIFIED** | throughput knee sweep, n=3 |
| 10 | Engine throughput under protocol: 12,313.5/s @ 4 drivers, spread 1.7 % | **VERIFIED** | n=5, warmup discarded, randomised |
| 11 | Most run-to-run variance is a warmup artefact (17.7 % → 1.7 %) | **VERIFIED** | `working/results/ws1_variance_cause.json` |
| 12 | Load-average carryover is NOT a variance cause | **VERIFIED by null control** | drove load to 7.88, got the *lowest* spread (0.7 %) |
| 13 | GPU (`mps`) variance is irreducible (14–25 %); CPU reaches 0.7–4.4 % | **VERIFIED** (2 methods) | pin `device=cpu` for all parity work |
| 14 | Fault isolation: RocketRide separates from expert-tuned Python on **nothing** | **VERIFIED** | 11/12 matrix cells all 0.00 for all frameworks |
| 15 | Peak memory under *held* allocations: RR 5,040 MB vs asyncio 13,363 MB at matched width | **PROVISIONAL** (1 run) | the one genuine RR advantage found |
| 16 | Model A (N concurrent pipelines) livelocks at ~150 | **VERIFIED** | reproduced twice; 81 orphaned `node.py` |
| 17 | pool_width instrument accurate to ~1 % when guarded | **VERIFIED** | calibrated vs known widths 4/8/16/64 |


> ## 🛑 CORRECTION 2026-08-07 (session 11) — ASCENDING CONCURRENCY SWEEPS UNDER-MEASURE. ALL SATURATION POINTS WITHDRAWN.
>
> **Open item A13 is resolved, and the cause invalidates every saturation point in this project.**
>
> A benchmark that begins at low concurrency and ramps up measures a machine that never leaves a
> low-power state. Identical harness, 400 tok, LlamaIndex, only the CELL ORDER changed:
>
> | concurrency | 1 | 2 | 4 | 8 | 16 | 32 | 64 |
> | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
> | ascending (cold) | 30.5 | 63.5 | 89.0 | 106.5 | 102.7 | 101.7 | 101.5 |
> | descending | 39.8 | 84.0 | 124.1 | 204.8 | **248.7** | 228.1 | 240.6 |
> | ascending + 30 s pre-warm at c64 | 39.2 | 82.7 | 106.8 | 183.7 | **225.7** | 223.6 | 225.0 |
>
> Pre-warming reproduces the descending run (both ~2.2× the cold ascending run above c8), so the
> variable is **the machine's power/performance state at the moment measurement starts**, not the
> concurrency level, not the harness, and not the service.
>
> **Ruled out first, each by direct experiment:** readiness/warm gate (cold gate read 102.4 % of
> warm gate; all 8 workers warm in both); RSS sampler (null control −0.4 %); background CPU load
> (4 hogs left c8 at 99.4 %, while the c1 control fell to 86 %); sustained decay (5 min continuous
> at c8 held 190–204 /s, −3.5 %); harness design (single-process vs 4-process agreed to 1.010×).
>
> **WITHDRAWN — every saturation point:**
> * LlamaIndex "saturates at c4" (session 9) — artifact of an ascending cold sweep
> * LlamaIndex "saturates at c8" (session 11 re-run) — same artifact, milder
> * **all four RocketRide saturation points** (session 10) — that profile also swept ascending from
>   c1, so it is depressed by an unmeasured amount
> * **the optimal-point comparison** (session 10, findings 1y) — it placed each arm at a saturation
>   point that does not exist, and both arms were measured cold
>
> **Best current estimate, pre-warmed [PROVISIONAL, 1 run]: LlamaIndex saturates at c16, ~226 /s at
> 400 tokens** — 3× the throughput and 4× the concurrency of the withdrawn figure.
>
> **This is almost certainly open item F.** The unexplained between-session drift since session 6
> has the same signature: runs that began under light load read low. It is one cause, not two.
>
> **Protocol consequence — every future measurement must pre-warm to a high-power state and record
> that it did.** Randomised cell order does not fix this; it only smears the depression across
> cells instead of concentrating it in the early ones.

## 4b. ⚠️ SATURATION COMPARABILITY BANNER (added 2026-08-07)

Both arms now have isolated saturation profiles. **LlamaIndex saturates at concurrency 4; the
engine's point depends on config and document size (c4–c32).** Any comparison taken at a
concurrency past an arm's saturation measures **queueing behaviour**, not serving capacity — the
service is already at its throughput ceiling and the extra load only accumulates in a queue.

**Every finding below that was measured past LlamaIndex's saturation point of 4 is marked
`[PAST-SAT]`.** They are not wrong — they are answers to a different question, and they must not be
quoted as "how fast is this service".

| finding | concurrency used | status |
| --- | --- | --- |
| 1a (withdrawn sustained curve) | 8 (2 drivers × 4) | `[PAST-SAT]` — already INVALID for other reasons |
| 1b3 (RR flat in concurrency 2→32) | 2–32 | `[PAST-SAT]` above c4 — the flat region IS the post-saturation plateau |
| 1b4 (RR ahead 1.190× @1600tok/**c2**) | **2** | **within saturation — stands** |
| 1i / Anchor A (tuned vs untuned scaling) | 1–32 | `[PAST-SAT]` above c4; the *scaling* claim is about the whole curve, so it stands as a curve statement |
| 1r (interop effect @c8) | 8 | `[PAST-SAT]` — a post-saturation A/B; the 14.3 % cost is real but describes queued behaviour |
| 1s (RR width 17.24) | escalated to 96 | structural measurement, saturation not applicable |
| 4 (mt10k parity 1.13×) | 8 | `[PAST-SAT]` |
| 5 (chunk sweep 1.23–1.55×) | 8 | `[PAST-SAT]` |
| 10 (engine 12,313/s @4 drivers) | high | request-path capacity, not the embedding workload — not applicable |
| **1y (optimal-point comparison)** | **each arm at its own saturation** | **the only head-to-head in the project taken inside both arms' serving regime** |

**Count: 6 findings carry `[PAST-SAT]`.** None is re-run here; the banner marks what each number
describes.

## 5. SUPERSEDED NUMBERS — including a correction that was itself wrong

**Read this section before quoting any number from an older doc.**

### 5.1 The ±35 % variance saga — a correction that was WRONG

| step | value | what happened |
| --- | ---: | --- |
| 1 | **11,408/s** @ 4 drivers | first measurement, n=1 |
| 2 | **7,871 / 8,540 / 8,311/s** | re-measured later the same day. I concluded 11,408 was a ~35 % outlier and **wrote correction banners saying so** |
| 3 | **12,313.5/s, spread 1.7 %, n=5** | re-measured under the full variance protocol — **supports the ORIGINAL 11,408 and does not reproduce the 7,871–8,540 cluster at all** |

**The step-2 correction was wrong.** The ±35 % turned out to be a **between-session** effect, not
within-session noise. Within a session under protocol the engine is stable to 1.7 %.
**Why the step-2 session read low is UNVERIFIED** — it coincided with a 15-min load average of
20.01, but the load-carryover hypothesis was refuted by direct null control (finding 12).

**Operational consequence: between-session comparisons are the dangerous ones, and within-session
repetition will not catch them.** Anything compared must be measured in ONE interleaved session.

### 5.2 Everything else superseded

| old claim | status | replaced by |
| --- | --- | --- |
| RocketRide ~2,600/s (flat from n=100 to 20,000) | **SUPERSEDED** | client-bound, not engine-bound. A single-process driver saturates ~2,500–3,400/s regardless of target. Engine does 12,313/s @ 4 drivers |
| "LlamaIndex 1.73× faster" (parity) | **WITHDRAWN** | artifact of a ~210-token test document; corpus median is 338 and the crossover is 200–400. Replaced by RocketRide 1.13× on real mt10k |
| LlamaIndex service effective concurrency = 4 | **SUPERSEDED** | that was an `mps` reading; on `cpu` the knee is **8** |
| Tier 2: FastAPI 3.69× faster than RocketRide | **SUPERSEDED** | RocketRide's arm was pre-protocol. Recomputed **2.36×**, and **PROVISIONAL** — the FastAPI side has still not been re-measured under protocol |
| "RocketRide is worse than asyncio at absorbing hangs (13.82 vs 1.95)" | **WITHDRAWN** | two harness bugs (processpool deadline never fired; asyncio timer started on semaphore acquire). Symmetric deadline → all frameworks 9.1–10.0, i.e. indistinguishable |
| `alloc` fault shows no memory difference | **SUPERSEDED** | the test freed memory immediately so nothing overlapped. `alloc_hold` (256 MB held 2 s) shows RR 5,040 MB vs asyncio 13,363 MB at matched width |
| Engine's embedding node runs on GPU (from source inspection) | **WRONG** | measured empirically: CPU (`cores_busy 9.29`) |

## 6. Open uncertainties, with cost estimates

| # | open item | cost | why it matters |
| --- | --- | ---: | --- |
| A | ~~Token sweep stops at 400~~ **DONE session 5** — extended to 6,400; services converge to parity | — | RR advantage does NOT keep growing |
| B | ~~Topology vs framework~~ **DONE session 5** — node count is NOT a factor (0.88–1.13×) | — | fixed cost is the engine's request path |
| C | ~~Chunk vs token~~ **DONE session 5** — no chunk-count trend; per-request overhead confirmed | — | caveat: MiniLM 512-token cap broke constant-token design; ratio still valid |
| A2 | ~~Cause of the 31 % sustained decay~~ **CLOSED session 6** — there is no decay to explain | — | all three rivals (funnelling / accumulation / thermal) moot; the phenomenon was an artifact |
| A3 | ~~Why is RocketRide flat in concurrency?~~ **CLOSED session 7** — native thread oversubscription, not the engine; fixable with thread-limit env vars | — | see `A3_SERIALIZATION_FINDING.md`; product recommendation: expose thread limits as pipeline config |
| A5 | **Optimal thread count** (1 vs 2 vs 4) never swept | ~30 min | 1 beats default under concurrency, but may not be optimal |
| A6 | ~~9.29 vs 1.45 cores~~ **CLOSED session 8** — peak/p95 vs time-average; both real, not interchangeable | — | only the time-average belongs in cost-per-request arithmetic |
| A7 | ~~Re-run the concurrency curve thread-pinned~~ **DONE session 8** — ABA design, n=5, both arms | — | `working/results/reanchor_tuned.json` |
| A8 | ~~interop threads unpinnable~~ **CLOSED session 9** — pinning lands but COSTS 14.3 % @conc8, does nothing @conc2. Leave at default | — | `working/results/anchor_b_interop.json` |
| A9 | **Drift null control did NOT fully hold**: LlamaIndex moved +3.4 % median (range −2.0 % to +19.5 %) between blocks it cannot be affected by | ~1 h | tuning deltas smaller than ~5 % are not trustworthy; relates to open item F |
| A10 | Best-achievable config is concurrency-dependent (default wins below conc≈4, pinned above) | ~30 min | FAIRNESS_BASIS.md needs a per-regime rule, not one setting |
| A11 | ~~Anchor B measured on two different pipelines~~ **CLOSED session 10** — 4-node `embed_probe.pipe` is canonical (FAIRNESS_BASIS.md); session 9's 1.352 is non-canonical. Original: — session 8 used `embed_probe.pipe` (4-node, ratio 1.201), session 9 used `single_node.pipe` (1-node, ratio 1.352). Not strictly comparable | ~20 min | pick ONE pipeline for the anchor and restate it; finding 1d says 1-node≈4-node within 0.88–1.13× but that band covers the gap |
| A12 | ~~RocketRide has no isolated profile~~ **CLOSED session 10** | — | `archive/results/isolated_profile_rocketride.json` |
| A13 | ~~LlamaIndex throughput does not reproduce~~ **CLOSED session 11**; evidence rebuilt session 12 as `working/results/a13_ordering_reconstructed__*.json` — **MIXED PROVENANCE**: the ascending block is log-parsed, the descending and pre-warm blocks are transcribed from the session-11 report table because their JSON was clobbered AND their stdout was piped to grep rather than a log. Spreads, gates and CIs are unrecoverable for those two. — ascending sweeps measure a machine in a low-power state; pre-warm reproduces descending order. Original: — 74.7/s @400tok/c4 in the isolated profile vs 89–91/s in two later runs the same day (+22 %). **Not the RSS sampler** (null control: −0.4 %). Cause unknown | ~1 h | the saturation *shape* is what the operating points rest on; the absolutes are not stable. Relates to open item F |
| A14 | **RocketRide saturation is config- and size-dependent** (c4 tuned/400, c32 tuned/1600, c16 untuned/400, c4 untuned/1600) while LlamaIndex is c4 throughout | ~30 min | 'RocketRide saturates at N' is incomplete without naming config and document size |
| A4 | ~~RR arm fails the gate under every harness~~ **CLOSED session 6** — barrier-synchronised fixed-duration windows fix it (8/10 cells pass) | — | the noise was per-burst boundaries across unsynchronised drivers, not the engine |
| B2 | Re-run sustained sweep until every RocketRide cell passes the 10 % gate | ~45 min | would upgrade the direction from PROVISIONAL to VERIFIED |
| D | RR arm of the real-corpus parity failed the 10 % gate (14.8 %) | ~20 min | the 1.13× point estimate stays PROVISIONAL until it passes |
| E | FastAPI side of Tier 2 never re-measured under protocol | ~20 min | the 2.36× is PROVISIONAL |
| F | Between-session drift cause | **LIKELY CLOSED session 11** — same signature as A13 (runs beginning under light load read low). Needs one confirmation: re-measure a session-6-era number with pre-warm | ~30 min | if confirmed this explains the ±35 % saga and most unreproducible absolutes |
| A15 | **Re-run BOTH isolated profiles with pre-warm**, then redo the optimal-point comparison | ~1.5 h | everything in STEP 2-4 of session 11 is blocked on this |
| A17 | **Pinning crossover concurrency UNVERIFIED for this corpus** — §3.2's "helps above ~4" is from synthetic text; concurrency-1 cost is 3.07x on real documents | ~40 min | affects which config is 'best' at any concurrency |
| A18 | ~~Does the +32 % growth plateau or reset on restart?~~ **RETIRED session 17** — there is no growth; it plateaus | — | resolved by 6-block series |
| A19 | **What triggers the intermittent ~+30 % memory excursion?** Neighbouring-LlamaIndex hypothesis **REFUTED** (session 18, −0.4 %). Host sampling now in the harness; **instrumented but not yet triggered** | unknown, many blocks | it is what makes the gate fail; capacity planning needs the frequency |
| A16 | Does the pre-warm requirement change RocketRide's numbers by the same factor as LlamaIndex's? | ~40 min | if the depression is asymmetric, every cold head-to-head is biased, not merely low |
| G | Why `mps` scales poorly (contention vs power vs driver) | ~1 h | doesn't change the recommendation (pin CPU) |
| H | Is RocketRide's ~17 width tunable from outside engine source? | ~30 min | if yes, the hang behaviour is config, not a ceiling |
| I | Memory advantage (finding 15) is one run, one block size | ~30 min | it's the only genuine RR advantage found; under-replicated |
| J | Nothing generalises off Apple Silicon | — | the device finding is Apple-specific; CUDA differs |

## 7. What has NOT been sent to the team

**Nothing has been sent. Every shared doc is still a draft I can revise freely.**

| doc | audience | status |
| --- | --- | --- |
| `FINDINGS_FOR_WS1.md` | Shashi, Leela | drafted, NOT sent |
| `SCHEMA_PROPOSAL.md` (v0.2) | Leela — needs agreement | drafted, NOT sent |
| `VARIANCE_PROTOCOL.md` | whole team | drafted, NOT sent |
| `working/handoff/` (seeds, collector, fault injection, verify_frameworks, pool_width) | Shashi | drafted, NOT sent |
| `working/handoff/parity/` (replication request) | Shashi | drafted, NOT sent |
| `SCOPED_CLAIM.md` | Ansh, for presenting | drafted, NOT sent — **carries a burst-mode caveat banner** |
| `CROSSOVER_FINDING.md` | — | **ON HOLD, DO NOT SEND** — central framing refuted session 6 |
| `RUNBOOK_LLAMAINDEX.md` | Ansh | VERIFIED by execution, not sent |
| `A3_SERIALIZATION_FINDING.md` | product + team | **drafted session 7, NOT sent** — product finding with a fix |
| `LLAMAINDEX_DEPLOY_QUESTION.md` | Leela, Shashi | **drafted session 7, NOT sent** — a decision, not a change |
| `DOCKER_ARCHITECTURE.md` | Ansh (review gate) | **awaiting approval — NOTHING BUILT** |
| `REBASELINE_PLAN.md` | Ansh (review gate) | drafted session 7 |
| `TOIL_INSTRUMENT.md` | Leela, Shashi (challenge before build) | **pre-registered session 7** |
| `PDF_PIPELINE_NOTES.md` | team | drafted session 7 — **carries session-8 corrections** |
| `PARSER_PREMISES.md` | Leela, Shashi | drafted session 9 — both premises REFUTED |
| `TWO_TIER_PARSER_DESIGN.md` | team | drafted session 9 — design only |
| `READINESS.md` | Ansh, Leela | drafted session 9 — gap list for head-to-head |
| `PARSER_DECISION.md` | **Shashi — he owns the call** | drafted session 10, NOT sent |
| `FAIRNESS_BASIS.md` | whole team | drafted session 8, asymmetry 2 closed session 9 |

**Implication: the schema is UNAGREED.** Keep `working/ws1/schema.py` swappable — it is the only file
that touches the wire format, by design.

## 8. Exact commands

All from the clone root.

### Engine

```bash
bash working/scripts/start_engine.sh          # ~60 s cold (embedded-Python bootstrap), ~1 s warm
bash working/scripts/stop_engine.sh
curl -s http://127.0.0.1:5565/version # health + identity in one call. /ping is auth-gated, returns 401
```

### LlamaIndex service

```bash
WS1_DEVICE=cpu WS1_WORKERS=8 WS1_PORT=8801 nohup bash working/ws1/run_service.sh > logs/ws1.out 2>&1 &
until [ "$(grep -c 'warm in' logs/ws1.out)" -ge 8 ]; do sleep 3; done; grep -c 'warm in' logs/ws1.out
../.venv/bin/python working/ws1/smoke.py      # ALL PASS expected, exit 0
pkill -f "uvicorn ws1.service"
```

`/health` returning 200 does **NOT** mean the service is ready — it is answered by one worker.
Count `warm in` lines instead.

### Parity harness

```bash
../.venv/bin/python working/scripts/corpus_characterize.py   # verify corpus, ~2 min, must be 10000/10000
bash working/scripts/start_engine.sh
../.venv/bin/python working/scripts/parity_corpus.py         # both arms interleaved + chunk sweep, ~25 min
```

### Other instruments

```bash
../.venv/bin/python working/scripts/engine_variance.py       # engine throughput under full protocol
../.venv/bin/python working/scripts/variance_gate.py --cmd "..." --reps 5 --threshold 0.10
../.venv/bin/python working/scripts/pool_width.py            # RocketRide effective width (needs fault_probe node)
cd handoff && ../../.venv/bin/python test_collector_overhead.py
```

## 9. Traps that have already cost time

| trap | detail |
| --- | --- |
| `curl -w '%{http_code}' \|\| echo 000` | on failure curl prints `000` **and** exits non-zero, so `\|\|` appends a second `000` → `"000000"` ≠ `"000"` → a dead server passes a health check. Assign the fallback, don't append |
| `setrlimit(RLIMIT_NPROC, …)` on macOS | requesting a higher soft limit **succeeds** but silently clamps the *hard* limit to `kern.maxprocperuid` (8,000), permanently. Never call it |
| Process census by cmdline grep | uvicorn workers spawn via multiprocessing; their cmdline has no "uvicorn". Undercounted our service **173×** (19.6 MB vs 3,404 MB actual). Walk the tree from a root PID |
| `hash()` for seeds | salted per interpreter — same config gave 44 injected faults one run, 66 the next. Use `working/harness/seeds.py` (sha256) |
| `asyncio.to_thread` default pool | `min(32, cpu+4)` = 18 here, **not** whatever your Semaphore says |
| `.pipe` files | need `source`, `components` first, literal GUID `project_id`. One live task per `project_id` — N concurrent tasks needs N distinct files |
| Engine tarball | extracts **flat**; `--strip-components=1` destroys it |
| SDK `get_server_info()` | broken — `public=True` is stored and never read. Use `GET /version` |
| Model load / engine cold start | ~36 s and ~60 s respectively. Must be outside every timed region |
| pool_width without the guard | if offered concurrency < true width it returns the OFFERED value at 0.0 % spread — confidently wrong, looks precise. Use `working/handoff/pool_width.py` |

## 10. Layout

```
<clone>/
  working/ws1/            THE SERVICE — schema.py (wire contract, isolated) | pipeline.py (LlamaIndex,
                  no HTTP) | service.py (HTTP only) | run_service.sh | smoke.py | exp_*.py
  working/scripts/        engine start/stop, parity harnesses, corpus tools, variance gate, pool_width
  working/handoff/        drop-in modules for Shashi + parity/ replication request
  working/harness/        engine_ops, seeds, stats, collector, env_capture
  working/pipes/          probe_minimal.pipe, fault_probe.pipe, embed_probe.pipe (4-node w/ embedding)
  working/nodes/          fault_probe — benchmark-only engine node
  data/mt10k/     verified corpus sample (2,000 docs)
  working/results/        all raw JSON
  engine/         the RocketRide 3.3.1 binary bundle
```

Key docs: `CROSSOVER` work → `PARITY_CORPUS_FINDINGS.md`; claim scoping → `SCOPED_CLAIM.md`;
running the service → `RUNBOOK_LLAMAINDEX.md`; team brief → `FINDINGS_FOR_WS1.md`;
history → `progress.md`.

<!-- trap appended 2026-08-10: `setsid` does not exist on macOS. `nohup ... &` alone survives the
     parent shell. A `nohup setsid ...` invocation dies instantly with "setsid: No such file or
     directory" and, if unverified, looks exactly like a running job. Verify every detached launch
     BY PID, never by assumption — this failure has now occurred twice in this project. -->
