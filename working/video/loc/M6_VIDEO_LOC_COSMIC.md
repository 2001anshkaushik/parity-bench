# Phase 2 (video) M6 — LOC + COSMIC, both arms

## What I found, and where — the method is Phase 1's, unchanged
Located at `working/minimal/` before measuring anything:

| artifact | what it fixes |
|---|---|
| `COUNTING_RULE.md` | the four layers (§2), **the knife** (§3, categories 1-7), as-built/minimal + ratio *range* output (§4) |
| `count_loc.py` | **METHOD A** — Leela's `m6_loc.count_loc` at `a5c3b5d`, imported not reimplemented (non-blank, non-comment, docstrings excluded) |
| `verify_loc.py` | **METHOD B** — independent `tokenize`+`ast` counter; plus two formatting-immune measures: **semantic units** and **canonical bytes** |
| `loc_report.json` / `verify_report.json` | the output format reproduced here |

Reused verbatim: the counter (via `_load_counter()`, provenance string carried into the
report), the four layers, the knife, `pipe_formatting_spread`, semantic units, and the
"report the range, not one number" rule.

**COSMIC is NEW in Phase 2.** Phase 1 contains no COSMIC/CFP work (grepped repo-wide: no
`cosmic`, `CFP`, or `function point`). Its rules are stated below and are mine, not inherited —
flagged so nobody reads them as Phase 1 precedent.

**Load-bearing inheritance:** Leela's `"compute_transforms": []` for RocketRide — *"engine-internal:
product code, not user code."* The rule is symmetric (LlamaIndex's, torch's, ffmpeg's internals
are not counted either); the *result* is asymmetric, and that asymmetry is the product
difference the metric exists to measure.

**Scope ruling (operator, 2026-08-26):** only what a developer writes and maintains to stand up
this video pipeline. Harness, driver, gates, collector, probes, instrumentation: excluded.

## The classification — per file, re-auditable line by line
Full per-line output with a reason per line: `working/video/loc/classification_video.json`
(fields: line, class, why, text). Rules are in `count_loc_video.py` (`INSTR`, `AMBIG`), so a
reviewer can reject one rule without rejecting the measurement.

| file | (a) service | (b) instrumentation | (c) ambiguous |
|---|---|---|---|
| `li_video/service.py` | 73 | 35 | 5 |
| `li_video/pipeline.py` | 111 | 27 | 7 |
| `li_video/schema.py` | 14 | 25 | 5 |
| `li_video/__init__.py` | 0 | 0 | 0 |
| **Python total** | **198** | **87** | **17** |
| `docker/Dockerfile.llamaindex-video` | 85 | — | — |

(b) is 29% of the authored Python — the operator's list (`frame_labels`, `frame_scores`,
`embedding_norms`, `stage_s`, `stage_s_semantics`, `hashing_locus`, `chunk_sha256`, per-frame
hashing, warm markers, `/health` beyond liveness) plus what `schema.py`'s own comments declare
("gate 3 reads these", "gate 7"). (c) is genuinely arguable: `total_chars`/`n_chunks` (a real
caller might want them; gates certainly do), `is_warm`/`identity`, and the health endpoint
itself (liveness is service; its fields are census).

**LlamaIndex totals — with and without (c), Dockerfile included:**
| | LOC |
|---|---|
| as-built (a+b+c+docker) | **387** |
| service + ambiguous (a+c+docker) | **300** |
| service only (a+docker) | **283** |

## RocketRide — sizing a JSON pipeline against Python
Phase 1 **has** a rule for declarative artifacts and it is used here: a JSON file's line count is
set by its indentation, so report the **spread**, never one number.

| formatting | lines |
|---|---|
| as stored | 158 |
| `json.dumps(indent=2)` | 158 |
| one node per line | 8 |
| compact | 1 |

`compute_transforms` **0**, `serving_integration` **0**, `client_harness` **0** — the engine
image serves it; no developer-written service, no Dockerfile authored for this pipeline.

**Formatting-immune cross-check (semantic units):** RocketRide **6 declared nodes**;
LlamaIndex **21 authored Python units** (functions/classes/methods). Ratio **3.5x** — and unlike
LOC it cannot be moved by whitespace.

**The honest range**, LI ÷ RR: **1.8x** (LI service-only 283 vs RR at its most verbose 158)
to **35x** (283 vs 8 nodes-per-line). The range is the publishable claim; a single number
invites an argument about which cut was fair.

## COSMIC — same functional process, same boundary, both arms
**Boundary:** around the video-processing service as the developer configures it. Outside it:
the client, model weights on disk (persistent storage), and the ffmpeg subprocess. Counted
identically on both arms.

**FP1 — start and warm the service**
| movement | type | both arms |
|---|---|---|
| detector weights from disk | Read | 1 |
| embedder weights from disk | Read | 1 |
| readiness signalled to caller | Exit | 1 |

**FP2 — process one video** (accept → extract → detect → chunk → embed → return)
| movement | type | both arms |
|---|---|---|
| video bytes in | Entry | 1 |
| video out to frame extractor | Exit | 1 |
| frames back from extractor | Entry | 1 |
| result (chunks + embeddings + counts) | Exit | 1 |
| error result | Exit | 1 |

**Total: 8 CFP on each arm.** Detect/chunk/embed are *data manipulation*, not movements, so they
add no CFP — which is the point: **the functional size is identical and the authored volume is
not.** 8 CFP costs 283-387 LOC on LlamaIndex and 8-158 declarative lines on RocketRide.

## Fairness caveat — state this wherever the numbers appear
**The RocketRide engine's own source is not counted.** The metric is *developer-written-and-
maintained* code, not code executed. The engine supplies, for free and uncounted: frame
extraction, detector loading and lifecycle, model/process management, chunking, embedding, HTTP/
websocket transport, and task/token management. Symmetrically, LlamaIndex's, torch's,
rfdetr's and ffmpeg's internals are uncounted on the other arm. **What the numbers compare is
authorship burden, not total system complexity** — a reader who wants the second thing will not
find it here.

## Defects and workarounds needed to reach a working service
Not LOC, but part of the real delta — the cost of authorship is also the cost of getting it right.

**LlamaIndex arm (ours to build, therefore ours to break): 7**
1. hermetic model-cache fix (offline weights) · 2. entrypoint change (port/worker
parameterization) · 3. serving-stack install (fastapi/uvicorn/uvloop/httptools pinned by us)
· 4. **admission control absent** — no `--limit-concurrency`, kernel accept skewed one worker to
48 of 168 videos; fixed by 8 single-worker instances + driver round-robin · 5. hashing-locus fix
(instrumentation charged one arm's wall) · 6. stage stamps inside the lock (`stage_s` measured
the queue) · 7. schema/service disagreement — `chunk_sha256` stayed REQUIRED after the service
stopped sending it: 18/18 legs 500'd *after* the pipeline had done all the work.

**RocketRide arm: 4**
1. onnxruntime patching · 2. token discovery (multi-token posture is undocumented; the 5.2x
recovery from 2.44 → 12.7 f/s depends on it) · 3. `ttl` is an **idle** timer, not a lifetime —
killed a leg at 2 h · 4. whole-frame `send()` cannot survive 248 MB at C=16 — three deaths
before adopting the SDK's own 1 MiB chunked shape.

**Reading:** 7 vs 4, and the categories differ. LlamaIndex's are *authorship* defects — we wrote
the service, so we wrote the bugs. RocketRide's are *discovery* defects — the engine worked, but
its semantics (idle-ttl, token concurrency, payload limits) were not discoverable from its
surface, and each cost a measured leg. **Fewer lines to write also means fewer lines to get
wrong, and more product behaviour to discover the hard way.** Both belong in the report.

---

## Re-count at the current tree, under the chart rule (2026-09-09)

Two reasons the figures above cannot be lifted onto a chart whose stated rule
is *non-blank, non-comment code lines, excluding Dockerfiles and requirements,
broken down by layer*:

| | the M6 figures above | what the chart rule needs |
|---|---|---|
| file set | all three totals (387 / 300 / 283) include the Dockerfile; `layers.serving_integration` 172 carries its 85 inside | Dockerfile and requirements excluded |
| tree | measured 2026-08-26 at `6ce2f9c` | measured at the current tree — the LI streaming refactor (`b295dea`, 08-27) rewrote `pipeline.py` and `service.py`, and Ruling L (`6143aab`, 08-29) changed the splitter defaults |

Re-counted with the **same counter, unmodified** — `count_loc_video.classify`,
the same line rules and the same service / instrumentation / ambiguous knife —
only the file set and the output path differ. Reproducer:
`recount_loc_head.py`; artifact: `loc_report_video_HEAD.json` (carries each
file's sha256 and the measuring commit).

**Comparison arm, per file, at the current tree** (Python only, Dockerfile and
requirements excluded):

| file | layer | (a) service | (b) instrumentation | (c) ambiguous | all classes | Δ service vs M6 |
|---|---|---|---|---|---|---|
| `working/video/li_video/pipeline.py` | `compute_transforms` | 123 | 27 | 7 | 157 | +12 |
| `working/video/li_video/service.py` | `serving_integration` | 100 | 36 | 5 | 141 | +27 |
| `working/video/li_video/schema.py` | `serving_integration` | 20 | 25 | 5 | 50 | +6 |
| `working/video/li_video/__init__.py` | `serving_integration` | 0 | 0 | 0 | 0 | 0 |
| **total** | | **243** | **88** | **17** | **348** | **+45** |

**By layer** — `pipeline_definition` 0 and `client_harness` 0 on this arm (the
service is the pipeline; the harness is excluded by the scope ruling):

| layer | service only | all classes |
|---|---|---|
| `compute_transforms` | 123 | 157 |
| `serving_integration` | 120 | 191 |
| **total** | **243** | **348** |

**Delta against M6, like for like** (both sides Python-only, Dockerfile
excluded from both): service 198 → **243** (+45), instrumentation 87 → **88**
(+1), ambiguous 17 → **17** (0), all classes 302 → **348** (+46). The growth is
the streaming refactor and its read-backs: `service.py` +27 service lines (the
spool-file request path, the `/health` surface), `pipeline.py` +12 (frames to
disk, one frame resident at a time), `schema.py` +6 (additive response fields).

**Files present in the arm's tree and deliberately not counted**:

| file | lines | why not counted |
|---|---|---|
| `docker/Dockerfile.llamaindex-video` | 122 raw, 114 by METHOD A | Dockerfile — excluded by the chart rule (it was 85 at M6; the 149-pin freeze install is what grew it) |
| `working/video/li_video/li_image_freeze.txt` | 149 | requirements — excluded by the chart rule |
| `working/video/li_video/extract_engine_pins.sh` | 52 | build-time provenance tooling — outside the M6 scope ruling |

**RocketRide side unchanged**: `benchmark_video_detect.pipe` reports the
formatting spread, not one number — 158 as stored, 158 at `indent=2`, 8 one
node per line, 1 compact — with `compute_transforms` 0 and
`serving_integration` 0 (engine-internal stages are product code, and no
Dockerfile is authored for this pipeline). Formatting-immune cross-check at the
current tree: **22** authored Python units (was 21) against **6** declared
nodes.

**If these go on a chart beside another framework's bar**, the bar's rule must
match on all four points: the same counter class (non-blank, non-comment,
docstrings excluded), the same exclusions (Dockerfile, requirements), the same
scope ruling (developer-written service only — no harness, driver, gates,
collector or probes), and the same layer names (COUNTING_RULE §2). Whether the
`instrumentation` and `ambiguous` classes are in or out has to match too: this
arm's service-only bar is 243 and its as-built bar is 348, and the choice moves
it by 105 lines.

---

## The AMI-era figure under a rule that excludes Dockerfiles and requirements (2026-09-09)

**The one adjusted number: LI service-only is 198**, not 283. The 85-line
difference is exactly the Dockerfile, which every total in the tables above
includes; the requirements file was never counted on either side. Per layer, on
that rule: `compute_transforms` **111**, `serving_integration` **87**,
`pipeline_definition` 0, `client_harness` 0 — and note the banked
`layers.serving_integration` of 172 in `loc_report_video.json` is 87 plus the
Dockerfile's 85, so it cannot be quoted under this rule either.

**Files counted, all four, at the tree the AMI headline legs ran:**

| file | layer | service | instrumentation | ambiguous |
|---|---|---|---|---|
| `working/video/li_video/pipeline.py` | `compute_transforms` | 111 | 27 | 7 |
| `working/video/li_video/service.py` | `serving_integration` | 73 | 35 | 5 |
| `working/video/li_video/schema.py` | `serving_integration` | 14 | 25 | 5 |
| `working/video/li_video/__init__.py` | `serving_integration` | 0 | 0 | 0 |
| **total** | | **198** | **87** | **17** |

**Files present and excluded by the rule**, so the delta is visible:
`docker/Dockerfile.llamaindex-video` 93 raw lines, **85** by METHOD A;
`working/video/li_video/li_image_freeze.txt` **149** lines, which existed from
`5c029b3` (2026-08-21) and so was present for the whole AMI campaign;
`working/video/li_video/extract_engine_pins.sh` 52 lines, already outside the
scope ruling.

**Consequence for the published range.** The 1.8x–35x range is computed from
283, which carries the Dockerfile. On 198 the same two cuts give **1.25x**
(198 vs the pipe's 158 as-stored) and **25x** (198 vs 8 nodes-per-line). Quote
the range with the rule that produced it.

### Timing: the AMI figure is final, and only a films-era count needs re-running

| event | when | effect on this figure |
|---|---|---|
| AMI default cells ran | 2026-08-24T02:55:50Z | tree `62d9243`; counted files unchanged since `2b1e969` |
| AMI balanced headline legs ran | 2026-08-26T07:42:03Z | tree `e1584796`, committed 07:29:33Z, 12 minutes earlier |
| M6 counted | `6ce2f9c`, 2026-08-26T19:58:35Z | counted files **byte-identical** to the headline tree |
| LI streaming refactor | `b295dea`, 2026-08-28T00:08:56Z | **after every AMI leg** |

So M6 measures the service as the AMI headline cells actually ran it, and the
refactor cannot reach back into that figure: **the AMI LOC number is final at
198 under this rule.** Only a films-era count needed re-running, and it is
`loc_report_video_HEAD.json` — 243 service, +45.

**One correction the era check surfaces**: the 24-Aug default cells ran a
slightly earlier service than M6 counted — **199 service / 84 instrumentation**,
layers 111 / 88 (`service.py` 74/33/5, `pipeline.py` 111/28/7, `schema.py`
14/23/5). The balanced-posture, hashing-locus and schema commits landed between
those cells and the headline pair. A LOC figure attached specifically to the
default cells is 199, not 198.

Artifacts, both from the same committed counter via `recount_loc_head.py --rev`:
`loc_report_video_AMI.json` (headline tree) and
`loc_report_video_AMI_default_cells.json`, each carrying its commit, its date
and every counted file's sha256.
