# WS-1 Phase 2 — Video Benchmark: RocketRide vs LlamaIndex
### Definitive report · 23–26 Aug 2026

**Corpus:** ami_full — 168 measured AMI meeting videos (+2 warm), 23,049 frames, ~96.1 h footage
**Box:** AWS `i-0775f33f3dc16f6af`, c7i.8xlarge — Xeon Platinum 8488C, 32 vCPU, 61 GiB RAM
**Engine:** RocketRide 3.3.1 (patched) · SDK `rocketride` 1.3.0 · Python 3.12.13
**Artifacts:** `s3://rocketride-benchmark-data/ansh/video-ami-20260826/`

> **Sourcing rule.** Every figure is read from a run export, preflight artifact, probe output, or
> source citation produced during the campaign. Ratios are marked **[derived]**. Superseded
> figures are shown struck through with the reason.

---

## 1. Executive summary

**Both frameworks are configuration-limited out of the box. Neither team had found it. Once both
are given equivalent work distribution, LlamaIndex is ~9% faster and ~17% more CPU-efficient on
this workload.**

| Finding | Figure |
|---|---|
| RocketRide out-of-box | 2.44 f/s at **18.9%** of a 32-core box |
| Token count recovers RocketRide | **5.21×** → 12.74 f/s at 91.9% |
| LlamaIndex out-of-box (as *we* deployed it) | 8.99 f/s at 39.9% |
| Balancing recovers LlamaIndex | **1.42×** → 12.74 f/s at 88.0% |
| **Headline, both balanced, 8 instances × 4 threads each** | **LlamaIndex +9.5% span, +9.0% window** |
| **Per-core** | **LlamaIndex +17.1%** |
| **Authorship burden** | **identical functional size — 8 CFP on both arms — costs 283–387 LOC on LlamaIndex vs 8–158 declarative lines on RocketRide** |
| Independently corroborated (default posture) | our RR-default 2.443 vs Leela's 2.44 — **0.1% apart** |
| Independently corroborated (multi-token posture) | our RR 8×4 11.633 vs Leela's 11.07 — **5.1% apart** |

**Two earlier claims are withdrawn.** A draft reporting *RocketRide ahead by 1.30–1.42×* compared a
hand-balanced RocketRide arm against a LlamaIndex arm our own harness left on kernel scheduling
(§7, H9). A draft disclosing *chunked writes as overhead against RocketRide* was refuted by direct
measurement — chunking is **2.31% faster** (§4).

---

## 2. Headline result

**8 instances × 4 threads on each arm**, n=168, C=16, n=2 passes, both arms driver-balanced,
corrected collector, symmetric hashing. Run 26 Aug.

| | span f/s | window f/s (n=152) | Effective cores | Box util | Records / errors |
|---|---|---|---|---|---|
| **RocketRide** 8 tokens × 4 | 11.694 / 11.571 | 11.258 / 11.438 | 30.411 / 29.843 | 95.0% / 93.3% | 168 / 0 both |
| **LlamaIndex** 8 instances × 4 | **12.745 / 12.733** | **12.330 / 12.405** | 28.250 / 28.101 | 88.3% / 87.8% | 168 / 0 both |
| **means** | RR 11.633 · **LI 12.739** | RR 11.348 · **LI 12.367** | RR 30.13 · LI 28.18 | RR 94.1% · LI 88.0% | — |

**[derived]** LlamaIndex leads **+9.5% on span**, **+9.0% on the steady window**, using **6 percentage
points less of the box**.

**Per-core efficiency [derived]:** LlamaIndex **0.452** vs RocketRide **0.386** frames/s per
effective core — **+17.1%**.

**Reproducibility [derived, range ÷ mean]:** LlamaIndex span **0.09%** / window 0.61%;
RocketRide span 1.06% / window 1.59%. LlamaIndex's 0.09% is the tightest figure in the campaign.

---

## 3. All postures measured

### 3.1 RocketRide

| Posture | span f/s | window f/s | cores | util | n |
|---|---|---|---|---|---|
| Default — 1 token, no thread env | 2.443 / 2.446 | 2.337 / 2.340 | 6.029 / 6.046 | 18.8% / 18.9% | 2 |
| **8 tokens × 4 threads (headline)** | **11.694 / 11.571** | 11.258 / 11.438 | 30.411 / 29.843 | 95.0% / 93.3% | 2 |
| 16 tokens × 2 threads | 12.729 / 12.753 | 12.755 / 12.796 | 29.328 / 29.482 | 91.7% / 92.1% | 2 |
| 8 × 4 (24 Aug, earlier session) | 12.048 | 11.825 | 30.037 | 93.9% | 1 |

The 24-Aug 8×4 figure (12.048) sits ~3.6% above the 26-Aug pair. Same configuration, different
session. **The n=2 pair is the quotable one**; the single earlier run was optimistic.

### 3.2 LlamaIndex

| Posture | span f/s | window f/s | cores | util | n |
|---|---|---|---|---|---|
| Default — W=8, one port, kernel accept | 9.267 / 8.714 | 9.435 / 9.683 | 13.013 / 12.497 | 40.7% / 39.1% | 2 |
| Default — W=16, one port | 8.793 | 9.374 | 9.291 | 29.0% | 1 |
| **Balanced 8 × 4 (headline)** | **12.745 / 12.733** | 12.330 / 12.405 | 28.250 / 28.101 | 88.3% / 87.8% | 2 |
| ~~Balanced 8 × 4 (25 Aug)~~ | ~~13.676 / 13.434~~ | ~~13.005 / 12.989~~ | **CPU defective** | — | 2 |

**The 25-Aug balanced pair is not quotable for CPU** — the collector sampled 1 of 8 containers
(§7, H10). Its throughput figures are valid but sit **6.0% above** the 26-Aug pair on a different
image build. Within each build reproducibility is excellent (0.09% on the 26-Aug pair), so this is
an **inter-build difference we have not explained**. Stated, not reconciled.

### 3.3 Cross-posture comparisons **[derived]**

| Comparison | Span |
|---|---|
| RocketRide parity 16×2 vs RocketRide default | **5.212×** |
| LlamaIndex balanced vs LlamaIndex default | **1.417×** |
| LlamaIndex default vs RocketRide default (both out-of-box) | 3.678× |

---

## 4. Why each arm was configuration-limited

### 4.1 RocketRide — tokens are the throughput dimension

From engine 3.3.1 source: one `use()` = one token = one Task = **one OS subprocess**, each holding
**one model instance** behind a process-local `threading.Lock`
(`make_device_lock()`, `ai/common/models/base.py:241-252`). `threads=` is per-task item concurrency
(default 64) and those threads **queue at that lock** — they do not parallelize inference.

A token is a checkout lane; `threads=` are baggers in the lane. The engine default is one lane.

**Verified, not assumed:**
- **Census:** `declared_tokens 16 → census_after 16`, 16 distinct task pids and `project_id`s.
  Default: 1 → 1.
- **Thread env** read back *inside the task process*, fail-closed: parity reads 2 with torch 2;
  8×4 reads 4 with torch 4; default reads all six `None` with torch 16.
- **Concurrent inference:** `/proc/<pid>/stat` at 1 s across all task processes, busy = ≥0.3
  cores/tick → **max 8 of 8 simultaneously busy, verdict CONCURRENT**. Null control at M=1 returned
  **max 1 of 1** — the instrument can return the bad answer, which is what makes the result a
  measurement.
- **No cross-process serializer** in source: a `threading.Lock` cannot serialize across processes;
  the model server (port 5590) is active only with `--modelserver=`, which the entrypoint does not
  pass; a sweep for `fcntl`/`flock`/`filelock`/`multiprocessing.Lock`/`sem_*`/shm across the pipe's
  nodes found none.

**Trap:** token identity hashes `(userId, project_id, source)` (`task_server.py:1073-1080`) and
`useExisting` returns the existing task (`:1126-1129`). Sixteen `use()` calls on one pipe file with
`use_existing=True` give **16 handles onto one task process**.

**Idle burden** (reported beside throughput, never subtracted):

| Tokens live | Idle cores | % of box |
|---|---|---|
| container only | 1.007–1.029 | ~3.2% |
| 1 | 1.23–1.24 | 3.8–3.9% |
| 8 | 2.83–2.84 | 8.8–8.9% |
| 16 | 4.66–4.71 | 14.6–14.7% |

LlamaIndex's equivalent: **0.005–0.037 cores**.

### 4.2 LlamaIndex — admission control is the throughput dimension

The service is `async def` with the pipeline dispatched via `anyio.to_thread.run_sync`, and there is
**no `--limit-concurrency`, no semaphore, no queue, no balancer** (`Dockerfile:93`). A worker keeps
accepting connections while saturated; a request commits at kernel `accept()` and never moves.

Videos served per worker at W=8:

```
p2:  48 · 29 · 28 · 25 · 19 · 7 · 7 · 5      (even share = 21, max/min ≈ 10×)
p1:  39 · 39 · 26 · 22 · 17 · 13 · 6 · 6
```

Reproduced across both passes — structural. Effective busy workers pin at **~4.4–5 regardless of
W**, which is why W=16 used *less* CPU than W=8. **This is our deployment's defect, not a
LlamaIndex property**; production deployments front a least-connections balancer, set
`--limit-concurrency`, or queue externally.

**Balanced posture:** 8 single-worker instances on ports 8802–8809, driver round-robins ports — the
structural twin of the RocketRide token round-robin. Proof run distributed exactly 2 per port
across all 8.

### 4.3 Transport — measured, and the earlier disclosure withdrawn

RocketRide sends each 248 MB video as ~237 chunked 1 MiB websocket writes; LlamaIndex sends
whole-body HTTP. Earlier drafts disclosed this as overhead against RocketRide. **Measured at C=1,
same container, same token, same file, 4 interleaved pairs:**

| | wall |
|---|---|
| whole-frame | 106.59 s |
| **chunked 1 MiB** | **104.12 s** |
| delta | **−2.46 s = −2.31%** (chunked faster) |

Chunked won all four pairs; same-mode spread ~0.5 s against a 2.46 s delta; verdict CONCLUSIVE.
Whole-frame does not survive C=16 at this payload, so the C=1 figure is the available bound.
**Chunking is not a handicap and the earlier disclosure is withdrawn.**

---

## 5. Correctness certification

| Gate | RR 8×4 vs LI 8×4 (headline, 26 Aug) | Earlier cells |
|---|---|---|
| `cross_detection_agreement` (strict label-multiset equality, zero tolerance) | **FAIL — 1 of 168 videos** | PASS 168/168 on three prior cells |
| `char_conservation` (±2%) | FAIL, worst 4.86% | identical 4.86% on every cell |
| `boundary_exclusions_total` | 0 | 0 |

### 5.1 The single detection divergence — a threshold-boundary artifact

`IN1002.avi`, frame 58 of 165. Both arms observed 165 frames.

- `score_triage`: **164 of 165 frames have `max_paired_delta = 0.0`** — byte-identical scores.
- Frame 58: RocketRide reports 18 detections, LlamaIndex 17. RocketRide's extra detection scores
  **0.3004** against the **0.3** threshold — 4 ten-thousandths above the cut. LlamaIndex's lowest
  is 0.3189.

One detection in ~23,000 frames landed on the knife edge. **Every other detection in the corpus is
identical to the fourth decimal place**, so the arms are doing identical work; the gate's zero
tolerance is what surfaces a boundary case as a failure.

**Open instrument question:** `boundary_eps` is 0.001 and 0.3004 is within 0.001 of the threshold,
yet `n_boundary_excluded` reported 0. Either the mechanism requires *both* arms near the boundary,
or it has a defect. Unresolved — flagged, not worked around.

### 5.2 `char_conservation` — explained and measured, not data loss

167 of 168 pairs outside ±2%; ratio RR/LI min 0.9514, median 0.9528, **every ratio below 1.0**,
spread proportionally across all six meeting series.

**Mechanism, from source:** both splitters are configured 4000/200. The engine's
`preprocessor_langchain._filter_kwargs_for` (`langchain.py:90-102`) keeps only kwargs named in the
splitter constructor's signature; `chunk_size` and `chunk_overlap` ride in `**kwargs` and are
discarded, so LangChain defaults run. `_merge_splits` realizes overlap by retaining **whole split
units**; the atomic unit is a per-frame detection JSON line of ~1,726 chars, always exceeding 200 —
so **the engine's effective overlap is 0** while LlamaIndex realizes ~200.

**Measured confirmation:** correcting each LlamaIndex video for `200 × (n_chunks − 1)` duplicated
characters moves the distribution from median 0.9528 → **1.0021**, min **1.0010** (no video below
1.0), 158/168 within ±2%. Chunk counts confirm: RR median **53** chunks × **3,350** chars;
LI median **45** × **3,993**.

**Verdict: boundary accounting, not lost content.** RocketRide genuinely embeds ~4.75% fewer
characters, so this bias **flatters RocketRide**. Regime-dependent — the Corner corpus measured
0.9817.

> **Methodology lesson:** `chunk_config_parity((4000,200),(4000,200))` is true, measured, and still
> misleading. **Configuration parity is not realization parity.**

---

## 6. Authorship burden — LOC and COSMIC

Method is Phase 1's, unchanged: `working/minimal/COUNTING_RULE.md` (four layers, the knife,
report-the-range), with Leela's `m6_loc.count_loc` counter at `a5c3b5d` **imported, not
reimplemented**. **COSMIC is new in Phase 2** — Phase 1 contains none, so its rules are ours and
are not inherited precedent.

**Scope:** only what a developer writes and maintains to stand up this video pipeline. Harness,
driver, gates, collector, probes and instrumentation excluded.

### 6.1 COSMIC — identical functional size, both arms

Same functional boundary on both sides (client, model weights on disk, and the ffmpeg subprocess
are outside it).

| Functional process | Movements | Both arms |
|---|---|---|
| **FP1 — start and warm the service** | detector weights (Read), embedder weights (Read), readiness (Exit) | 3 CFP |
| **FP2 — process one video** | video bytes in (Entry), video to extractor (Exit), frames back (Entry), result (Exit), error result (Exit) | 5 CFP |
| **Total** | | **8 CFP each** |

Detect, chunk and embed are *data manipulation*, not data movements, so they add no CFP.

**8 CFP costs 283–387 LOC on LlamaIndex and 8–158 declarative lines on RocketRide.** This is the
cleanest statement of the delta available: COSMIC is implementation-independent by construction,
so unlike any LOC ratio it cannot be argued down on counting rules.

### 6.2 LlamaIndex — line-by-line classification, published

Every line is classified with a reason in `working/video/loc/classification_video.json`, so a
reviewer can reject one rule and re-run rather than reject the measurement.

| file | service | instrumentation | ambiguous |
|---|---|---|---|
| `li_video/service.py` | 73 | 35 | 5 |
| `li_video/pipeline.py` | 111 | 27 | 7 |
| `li_video/schema.py` | 14 | 25 | 5 |
| **Python total** | **198** | **87** | **17** |
| `docker/Dockerfile.llamaindex-video` | 85 | — | — |

**Instrumentation is 29% of the authored Python** — `frame_labels`, `frame_scores`,
`embedding_norms`, `stage_s`, `stage_s_semantics`, `hashing_locus`, `chunk_sha256`, per-frame
hashing, warm markers, and `/health` fields beyond liveness. The ambiguous set is what one would
genuinely argue about: `total_chars`/`n_chunks`, `is_warm`/`identity`, and the health endpoint
itself.

| LlamaIndex totals | LOC |
|---|---|
| as-built (service + instrumentation + ambiguous + Dockerfile) | 387 |
| service + ambiguous + Dockerfile | 300 |
| **service only + Dockerfile** | **283** |

### 6.3 RocketRide — sizing a declarative pipeline

Phase 1's rule for declarative artifacts applies: a JSON file's line count is set by its
indentation, so report the spread, never one number.

| formatting | lines |
|---|---|
| as stored / `indent=2` | 158 |
| one node per line | 8 |
| compact | 1 |

`compute_transforms` **0**, `serving_integration` **0**, `client_harness` **0** — the engine image
serves the pipeline; no developer-written service, no Dockerfile authored for it.

**Formatting-immune cross-check:** RocketRide **6 declared nodes** vs LlamaIndex **21 authored
Python units** (functions/classes/methods) — **3.5×**, and whitespace cannot move it.

**[derived] Honest range, LI ÷ RR: 1.8× to 35×** (283 service-only against RocketRide at its most
verbose 158; against 8 nodes-per-line at its most compact). **The range is the publishable claim** —
a single number invites an argument about which cut was fair.

### 6.4 Fairness caveat — state this wherever these numbers appear

**The RocketRide engine's own source is not counted.** The metric is *developer-written-and-
maintained* code, not code executed. The engine supplies, free and uncounted: frame extraction,
detector loading and lifecycle, model and process management, chunking, embedding, HTTP/websocket
transport, and task/token management. Symmetrically, LlamaIndex's, torch's, rfdetr's and ffmpeg's
internals are uncounted on the other arm.

**What these numbers compare is authorship burden, not total system complexity.** A reader who
wants the second thing will not find it here.

The RocketRide zero cells are load-bearing and inherited from Leela's Phase 1 rule
(*"engine-internal: product code, not user code"*). A reviewer who rejects that rule rejects the
comparison — which is why the caveat sits beside the number rather than in a footnote.

### 6.5 Defects needed to reach a working service — and the asymmetry of kind

| Arm | Count | Defects |
|---|---|---|
| **LlamaIndex** | **7** | hermetic model-cache fix · entrypoint parameterization · serving-stack install (fastapi/uvicorn/uvloop/httptools, pinned by us) · **absent admission control** · hashing-locus fix · stage stamps inside the lock · schema/service disagreement (18/18 legs 500'd *after* the work completed) |
| **RocketRide** | **4** | onnxruntime patching · token discovery (undocumented; the 5.2× recovery depends on it) · `ttl` is an idle timer, not a lifetime · whole-frame `send()` cannot survive 248 MB at C=16 |

**The categories differ, and that matters more than the count.** LlamaIndex's are **authorship**
defects — we wrote the service, so we wrote the bugs. RocketRide's are **discovery** defects — the
engine worked, but idle-`ttl` semantics, token concurrency and payload limits were not discoverable
from its surface, and each cost a measured leg.

**Fewer lines to write also means fewer lines to get wrong, and more product behaviour to discover
the hard way.**

---

## 7. Incident log

### 7.1 Our faults

| # | Issue | Root cause | Resolution |
|---|---|---|---|
| **H9** | **A draft claimed RocketRide won by 1.30–1.42×** | Our driver round-robined RocketRide's tokens but left LlamaIndex on **kernel accept with no admission control** — worth **41.7%** of LlamaIndex's throughput. We hand-balanced our own arm and left the competitor to kernel scheduling | LlamaIndex re-run balanced; headline reversed; banked legs re-labelled LI-default posture |
| H1 | RR default blast failed 16/16, all sends dying within ~10 ms at t+219.63 s | Driver read each 248 MB file **synchronously on the event loop** before the semaphore and gathered all 168 tasks — loop blocked ~197 s, ~41 GB accumulating | `4ea3e41`: reads/hashing off-loop; a row cannot read bytes until it holds a slot |
| H2 | Connection died at ~66–71 s | Client sent each 248 MB video as **one websocket message**, so control frames could not interleave | `58f2bb3`: adopted 1 MiB chunking (later measured *faster*, §4.3) |
| H10 | Exports reported ~3.0 cores for an arm using ~30 | `--li-container` took one name; collector sampled 1 of 8 | `7c1cd81`: sums all N, fails closed on a single-container sample in multi-instance posture |
| H11 | Claimed `sum(stage_s.detect)/span = 8.00` proved eight concurrent inferences — **wrong** | `stage_s` stamps start *before* the device lock, so the clock includes queue wait. A worker cannot execute 4.84 s of detect per second of its own span | `00b86e1`: stamps moved inside the lock; `stage_s_semantics` field added |
| H13 | LI legs died at minute 40: `li_video: not running` | The driver's preflight running-checked the dead `li_video` default because service-set resolution ran 800 lines *after* preflight | `014686a`: resolution moved before any name check; raw attributes replaced with a sentinel that raises on read |
| H14 | Both LI legs returned 18/18 `HTTPError 500` after full inference work | The hashing-locus change removed `chunk_sha256` from the service response but left it **required** in the pydantic schema | `e158479`: field dropped; structural test parses service kwargs against schema required fields |
| H15 | Three failures in one session that a single real request would have caught | Plan check validated **descriptions of work**, not work | Dry preflight now boots the real image, runs the real preflight, and pushes one real video through the real service before any leg may start |
| H3 | C=4 probe returned `NoneType.disconnect` | **Two drivers against one container** — a `pkill` did not execute; the chain `docker rm`'d the container mid-probe | Probe re-run; `flock` guard added to the driver |
| H4 | Leg started with empty `--image-lineage` | `/tmp/lineage.txt` cleared by the box | Killed within a minute; lineage re-extracted |
| H5 | `li_video` exited (3), `Address already in use` | Stale `li_w16` held port 8802 under host networking | Removed. Weights read-back fail-closed correctly |
| H12 | `rf-detr-base.pth md5 None` | `--li-container` defaulted to a container dead 21 hours | Pointed at the live set |
| H6 | C=4 briefly proposed as a campaign value | Generalized from a single n=6 dry pass | Withdrawn before any leg ran at it |
| H7 | Concurrency probe counted M+1 processes | Likely the engine's own eaas server matching the filter | **Open, minor** — verdict unaffected |
| H8 | Neither arm's instance count was swept before the main run | Probes built, never executed | Closed retroactively |
| H16 | `boundary_exclusions` did not fire on a 0.3004 detection with `boundary_eps` 0.001 | Unknown | **Open** (§5.1) |

### 7.2 Engine and SDK findings

| # | Finding | Evidence | Impact |
|---|---|---|---|
| E1 | **Default posture is a single detector** | Source + census; 18.9% box util | Out-of-box RocketRide is 3.68× slower than out-of-box LlamaIndex. Two teams missed the knob |
| E2 | **Single-token concurrency is negative-yield** — 42.83 s for one video alone; ~1,060 s each for 16 concurrent, 6 of 16 failing | `probe_m1_concurrency` | Per-item latency ~24.8× worse **[derived]** |
| E3 | **`dap_client.py:229` discards the true exception**; `on_disconnected` then fails all pending futures at once | Source `dap_client.py:120-142, 214, 229, 246` | **Cost three full legs of diagnosis** |
| E4 | **Whole-frame writes kill the connection** at large payloads under concurrency; `send_files` chunks at 1 MiB but plain `send()` does not, with no warning | Death at ~66–71 s at 248 MB, C=16 | Any user sending large payloads via `send()` hits this |
| E5 | **`CONST_DATA_PIPE_TIMEOUT = 60.0`** reaps pipes as zombies during long uploads | Uniform ~92.66 s failures | `PipeException('Write pipe with id N not found')` |
| E6 | **ttl is an idle timer**; finite ttl kills tasks mid-batch | Both teams hit it independently **on 23 Aug** | One joint ticket |
| E7 | **Chunk configuration is inert** | `langchain.py:90-102`, byte-identical 3.3.1 ↔ HEAD | Ticket 3 |
| E8 | **Engine idle spin** — ~1.0 core at rest, 4.66–4.71 at M=16 | Measured per posture | 14.6% of the box before any work at M=16 |
| E9 | **No per-stage timings exposed** | Full result-path review | Structural instrumentation asymmetry; Leela's V4 names it too |

---

## 8. Cross-team corroboration

| | Leela (`native170-20260822T070136Z`) | Ours (RR default) |
|---|---|---|
| RocketRide throughput | 2.44 f/s | **2.443 / 2.446 f/s** |
| Span | 9,444.98 s | 9,435.9 / 9,422.4 s |
| Effective cores | 5.98 | 6.029 / 6.046 |

Two independently built harnesses, byte-identical corpus, **0.1–0.2% apart**. The most robust
result in the campaign.

**Corroboration on the multi-token posture too.** Her `rr_matched_8x4` cell (26 Aug, 8 tasks ×
4 threads, fail-closed census 8/8) measures **11.07 f/s** against our **11.633** — **5.1% apart**
**[derived]**, again on different harnesses. So the token finding is now reproduced across two
teams on two postures. Her cell is labelled SIZING (n=1) and discloses a keepalive burning ~1 core
inside its measured span.

**One open cross-team discrepancy.** At nominally the same posture she reports **23.87 effective
cores (74.6%) and 2.16 CPU-s/frame**; we report **30.13 cores (94.1%)**, roughly 2.59 CPU-s/frame
**[derived]**. We get ~5% more throughput for ~26% more CPU, and her figure should be *inflated* by
the disclosed keepalive — so the real per-frame gap is wider than it appears. Candidate causes: her
sharded-blast admission (unbounded per shard; 114 concurrent decoders observed, memory pinned at
the 58 GB limit — she attributes ~8% to this herself) versus our client-bounded C=16 feed, or a
difference in CPU accounting basis. **Unresolved; to be settled between the arms before either set
of CPU-efficiency figures is published.**

**Her splitter setting is the fix for our `char_conservation` failure.** Her comparison arm runs
`RecursiveCharacterTextSplitter 4000/0` — overlap **0**, matching what the engine actually
realizes — and her `chunk_ratio` sits in band with `workload_ratio` 1.024. We ran LlamaIndex at
4000/**200**, which is precisely why our cell fails at 4.86% (§5.2). So that failure is not only
boundary accounting to be disclosed; it is a configuration we could have matched and she did.
**Credit to Leela; adopt 4000/0 on the comparison arm in the next campaign.**

Her verdict on that basis — **LangGraph 6 · ties 3 · RocketRide 0**, attributed to a "~6-core
scheduling ceiling … architectural" — reproduces exactly at 1 token. **The ceiling is real per
token, not architectural:** `M > 1` appears nowhere in her code; her sweeps varied task threads
while holding tokens at 1. Her own label on that run is *"sizing evidence, not final numbers"*
(1 rep, no envelope) and travels with any quote of her figures.

---

## 9. Limitations

1. **n=2 on the headline cells.** By Leela's own standard this is sizing evidence, not final
   numbers. Supporting cells (RR 16×2 24-Aug, LI W=16, RR 8×4 24-Aug) are n=1 or n=2 as marked.
2. **One box, one corpus.**
3. **Unexplained 6.0% inter-build difference** on the LlamaIndex balanced arm (13.555 on 25 Aug vs
   12.739 on 26 Aug). Within-build reproducibility is 0.09%, so this is not noise.
4. **The 16×2 ceiling legs were dropped** for time. The queue-depth asymmetry at C=16 — LlamaIndex
   runs 2-deep per instance while RocketRide at 16 tokens runs ≤1-deep — is therefore stated
   qualitatively and **not quantified**. It plausibly costs LlamaIndex in the 8×4 cell.
5. **RocketRide's cgroup includes the non-serving engine master** — a small charge against
   RocketRide's CPU figures.
6. **Memory limit shapes differ**: RR one container at 58 GiB; LI 8 containers at 7 GiB each.
   Observed usage 1.1–2.3 GiB per instance, so almost certainly non-binding.
7. **Image vintage differs**: `rr:patched-video` frozen 22 Aug; `li:video` rebuilt 26 Aug with an
   unpinned serving stack (per-run `pip freeze` is the record).
8. **LlamaIndex's ~200-char overlap realization is inferred** from config, measured packing, and the
   arithmetic fit; its splitter source is container-installed and unpinned.
9. **Two open instrument questions** — H7 and H16.
10. **The LOC figures rest on one counter.** Phase 1 ran a second independent counter (Method B,
    `tokenize`+`ast`) after two counting errors were found; it has **not** been run against the
    video files for time. The COSMIC result (§6.1) does not depend on it. The classification is
    regex-over-lines, so a line touching both concerns lands in one bucket — which is why every
    line is published with its reason.
11. **The RocketRide/Leela CPU-per-frame discrepancy (§8) is unresolved**, so cross-team
    CPU-efficiency figures should not be published until it is settled.

---

## 10. Upstream tickets

1. **Default posture discoverability** (E1) — token count is undocumented as a throughput
   dimension; two independent teams missed it.
2. **`dap_client.py:229` exception swallowing** (E3).
3. **`send()` whole-frame writes at large payloads** (E4) — chunk like `send_files`, or warn.
4. **`CONST_DATA_PIPE_TIMEOUT` zombie reaping** (E5).
5. **ttl semantics** (E6) — joint filing with Leela's arm.
6. *(filed)* Ticket 3 — chunk config ignored (E7).

**Internal follow-ups:** concurrency-probe process filter (H7); boundary-exclusion behaviour (H16);
Crossroad-38 band re-centre for the ami regime; the unexplained LI inter-build delta (§9.3);
quantify the queue-depth asymmetry with the dropped 16×2 cells.

---

*Prepared from run exports, preflight artifacts, probe outputs and source citations produced during
the 23–26 Aug 2026 campaign. All artifacts archived at
`s3://rocketride-benchmark-data/ansh/video-ami-20260826/`.*
