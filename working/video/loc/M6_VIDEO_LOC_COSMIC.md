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
