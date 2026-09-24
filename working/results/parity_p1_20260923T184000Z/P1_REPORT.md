# P1 — the first engine changes under the single-instance mandate

Campaign `parity_p1_20260923T184000Z`, branch feat/parity-p1 (cut from the P0 deliverable fb211c2). Generated 2026-09-24T15:30:43Z from committed analysis files; every figure is computed from raw records and rounded only here. Every comparison is ABAB inside one box session (see Session); banked P0 figures appear only as context.

**Blind recomputation (P1_BLIND_VERIFICATION.json):** PASS — every plant caught, no other mismatch — 468 figures checked by 3 verifiers; plants caught 3 of 3; other mismatches 0.

## Verdicts

| experiment | verdict | measured (from the analysis files) | reading |
|---|---|---|---|
| P1-A E2 (video thread stall) | UNREADABLE (null control) — none | D (OFF legs) 0.099 s per frame; D (ON legs) 0.103 s | UNREADABLE by the pre-registered null control (the tracer's own cost); untraced, RocketRide's forward pass is slower at identical pool settings and its calling thread is on-CPU for less of it |
| P1-B Tika wrapper fix | SUPPORTED | correctness PASS; smoke 60.1x at p50 on the 11, exec census drop 99.99%; 384 ABAB +12.61% vs 0.82%; full 9,975 +127.85% (one run each) | the pathological holds are the wrapper's inline-image extraction and per-image tool probing; turning both off leaves the text lane unchanged and removes the tail |
| P1-C native parser | NOT RUN — the prototype's parser never ran | node counters: text 0 in every leg; context: HYBRID (no text of its own; its output is fixed Tika's) chunk-identical to fixed Tika on 9,886 documents; replay cost -0.57% vs 1.39% | the question was not answered: the prototype's parser never ran; the hybrid's replay path gave fixed Tika's output, chunk-identical over the full corpus |
| P1-D V1 at 168 videos | NOT RUN | RocketRide ran: 168 videos, 2.532 frames/s, output identical to P0 on 16 shared videos; LlamaIndex: NOT RUN (budget) | only the RocketRide arm ran (deterministic against P0 on the shared videos); the gap needs the LlamaIndex leg |

## Gates

| gate | threshold | measured | outcome |
|---|---|---|---|
| E2 null control (rr) | tracer ON vs OFF within max(0.82%, spreads) and identical output | -5.73% vs 0.82%; identical [True, True] | FAIL |
| E2 null control (li) | tracer ON vs OFF within max(0.82%, spreads) and identical output | -6.43% vs 1.09%; identical [True, True] | FAIL |
| P1-B correctness | 384 slice chunk-identical, no document lost | 382 documents; 0 differ; 0 lost | PASS |
| P1-B smoke (full runs) | ≥ 10x at p50 on the 11 AND exec census drop ≥ 90% | 60.1x; drop 99.99% | FIRED |
| P1-C HYBRID adoptable | empty on no document the fixed-Tika full run recovers | the prototype's parser never ran | NOT RUN |
| P1-C PURE adoptable | empty on no document the fixed-Tika full run recovers | the prototype's parser never ran | NOT RUN |
| P1-D confirmation | gap − max(0.82%, P0 V1 spreads) ≥ +10 points | — | NOT RUN |

## P1-B vs P1-C recommendation

Ship P1-B's wrapper fix: it is output-neutral on the gate slice and chunk-identical over the full corpus, and it more than doubles full-corpus docs/s at lower CPU per document. P1-C cannot be recommended or rejected: its prototype never parsed a document. Its wiring is proven: with the node producing no text, every document still came out through the fixed Tika, chunk-identical over the full corpus, at no readable cost. P2 can therefore test pypdfium2 with only the missing module added.

## The E2 cause

Not established. The pre-registered readings (GIL contention, pool or affinity configuration, CPU contention) needed the traced legs, and the tracer's own cost failed the null control on both arms, so none is supported or refuted. What the untraced legs establish: at T=4 with identical torch, OpenMP and MKL settings and identical affinity, RocketRide's forward pass is slower per frame, and its calling thread is on-CPU for a smaller share of that pass (see P1-A). The read-backs differ only outside the pool fields: the debugger is attached in RocketRide's task process, LlamaIndex sets MALLOC_ARENA_MAX=2, and RocketRide's process runs many more threads. Those are P2's candidates.

## Bottlenecks and in-bounds fixes, ranked by ROI (P0's three columns; scope first, then share)

(a) is the mean share of run total over this session's two stamped legs named by the item (P1-B's 384-slice legs: baseline for the wrapper item, fixed for the rest). Scope rank, fixed before the P1 data: CONFIG and THREADING, then PATCH, then PYTHON, then CPP.

| rank | bottleneck | in-bounds single-instance fix | (a) share of run total (D1, this session) | (b) 1/(1 − share) | (c) scope | evidence |
|---|---|---|---|---|---|---|
| 1 | video: RocketRide's T=4 forward pass is slower than LlamaIndex's at identical libraries and pool settings; its calling thread is on-CPU for less of it | not yet named: E2's pre-registered readings are unreadable (the tracer failed its null control). Candidates for P2, from E2's read-backs: the attached debugger (pydevd as sys.monitoring tool 0, RocketRide only), the per-frame device lock rotating forward calls across 16 pipe threads each with its own OpenMP pool, MALLOC_ARENA_MAX=2 (LlamaIndex only), the task process's thread count. Scope THREADING is provisional | — | — | THREADING | E2 OFF legs (forward times, caller CPU ratio) and read-backs |
| 2 | the docs parse tail: the engine's Tika wrapper extracted every PDF inline image and probed external tools per image | DONE in P1-B (rr:p1-tikafix): TikaApi.getPdfConfig code byte 9 iconst_1 -> iconst_0 (setExtractInlineImages off; PATCH) and two parser-exclude lines in tika-config.xml (CONFIG); output-neutral on the 384 slice (the gate) and chunk-identical over the full corpus (context). Ready to ship as a wrapper change | 35.1% | 1.54x | PATCH | P1-B correctness, smoke, 384 ABAB and full runs |
| 3 | per-document embedding (MiniLM) — after the wrapper fix, nearly all of document time | encode the chunks of several in-flight documents in one call inside the one model instance; output effect to be verified (batch composition can move floats) | 92.1% | 12.61x | PYTHON | P1-B fixed legs' D1 stage shares |
| 4 | response path: vectors serialised as JSON text on the websocket | binary vector encoding on the response lane | 1.9% | 1.02x | PYTHON | P1-B fixed legs' D1 stage shares |

### Out of bounds (recorded, not proposed)

- a second token, more task processes, model or engine pools, the model-server mode (unchanged from P0)

### NOT RUN

- P1-C's native-parser question: the prototype's pypdfium2 never ran (the image lacked pypdfium2's top-level pypdfium2_cfg module; the build's own check failed with rc 8 and my master did not gate on it). Needs: the module added (install the wheel into the engine's site-packages), the counters checked after the first leg, then the pre-registered P1-C design (about 1.5 h of box time)
- P1-D's LlamaIndex 168-video leg: the chain's per-leg budget check found the 11-hour budget passed; the gap is not computed. Needs about 2 h of box time plus a RocketRide leg in the same session
- E2's tracer-ON readings (GIL wait in forward, run-queue wait, busy OpenMP workers): unreadable because the tracer itself cost about 6% on both arms (null control failed). Needs a lighter instrument (for example bpftrace off-CPU accounting only for the forward-calling threads) and its own null control
- memory samples for p1b_base_a and p1b_fix_a: the runner's sampler never ran on them (register 55); later docs legs are covered by the outside watcher
- rr:p1-pdfium's build record (p1c_build.json): the build script stopped at its failed in-image check before writing it; the image id is in chain_p1c_done.json

### Register entries added

- 53 — the tracer that could not stop (per-CPU preallocated maps), and a repeat of entry 50 (sudo in a one-shot run)
- 54 — the build check that failed and the orchestration that did not listen (P1-C)
- 55 — the sampler with nowhere to write, and the DEGRADED leg retried twice

## P1-A — E2: the video thread stall (DIAGNOSTIC tracer; OFF legs are the null control)

| leg | frames/s | forward s per frame | caller CPU / forward wall | process cores in forward | idle cores (engine, before work) | memory peak (sampled) | steal / MHz |
|---|---|---|---|---|---|---|---|
| e2_rr_on_a | 2.384 | 0.406 | 0.61 | 2.40 | 1.223 | 8,673 MB | 0.001% / 2,725 |
| e2_rr_on_b | 2.390 | 0.405 | 0.60 | 2.40 | 1.230 | 7,615 MB | 0.001% / 2,752 |
| e2_rr_off_a | 2.533 | 0.382 | 0.60 | 2.45 | 1.228 | 7,537 MB | 0.001% / 2,754 |
| e2_rr_off_b | 2.531 | 0.382 | 0.60 | 2.45 | 1.230 | 7,604 MB | 0.001% / 2,705 |
| e2_li_on_a | 3.100 | 0.300 | 0.75 | 2.79 | 0.005 | 5,407 MB | 0.001% / 2,773 |
| e2_li_on_b | 3.067 | 0.304 | 0.75 | 2.77 | 0.005 | 5,337 MB | 0.001% / 2,712 |
| e2_li_off_a | 3.285 | 0.284 | 0.75 | 2.81 | 0.005 | 5,356 MB | 0.001% / 2,764 |
| e2_li_off_b | 3.305 | 0.282 | 0.75 | 2.81 | 0.005 | 5,336 MB | 0.001% / 2,845 |

**Readings (pre-registered rules; readable only if both null controls pass: NO).** D = F_rr − F_li: OFF legs 0.099 s, ON legs 0.103 s per frame.

| candidate | measured | bar (0.5 × D_on) | reading |
|---|---|---|---|
| (a) GIL contention | G_rr − G_li = 0.006 s per frame | 0.051 | not supported |
| (c) CPU contention | R_rr − R_li = 0.003 s per frame | 0.051 | not supported |
| (b) pool / affinity | 0 read-back difference(s); busy OMP workers RR [0, 0] vs LI [0, 0] | difference AND fewer busy workers | not supported |


**Supported:** none. The tracer-ON figures below are DIAGNOSTIC context only: they carry no reading.

### e2_rr_on_a — compute threads per frame: on-CPU 0.375 s, run queue 0.004 s, sleep 6.546 s; callers' total GIL wait 0.013 s per frame; G (in forward) 0.006 s

| thread (top by on-CPU) | name | on-CPU s |
|---|---|---|
| 7581 | engine | 297.4 |
| 9760 | scanner-50 | 61.3 |
| 9847 | scanner-50 | 60.5 |
| 9402 | scanner-50 | 60.1 |
| 9491 | scanner-50 | 60.0 |
| 9670 | scanner-50 | 58.7 |
| 9047 | scanner-50 | 57.6 |
| 9582 | scanner-50 | 57.6 |

GIL holders (py-spy --gil, innermost frame): _transport_receive (rocketride/core/transport.py) 21.2%; forward (rfdetr/models/backbone/dinov2_with_windowed_attn.py) 12.3%; forward (torch/nn/modules/linear.py) 9.1%; layer_norm (torch/nn/functional.py) 5.4%; _call_impl (torch/nn/modules/module.py) 4.6%

### e2_rr_on_b — compute threads per frame: on-CPU 0.372 s, run queue 0.004 s, sleep 6.529 s; callers' total GIL wait 0.013 s per frame; G (in forward) 0.006 s

| thread (top by on-CPU) | name | on-CPU s |
|---|---|---|
| 23241 | engine | 296.5 |
| 25334 | scanner-50 | 60.1 |
| 24978 | scanner-50 | 59.7 |
| 25068 | scanner-50 | 59.7 |
| 25421 | scanner-50 | 59.6 |
| 25243 | scanner-50 | 59.3 |
| 24621 | scanner-50 | 57.8 |
| 24802 | scanner-50 | 56.6 |

GIL holders (py-spy --gil, innermost frame): _transport_receive (rocketride/core/transport.py) 20.9%; forward (rfdetr/models/backbone/dinov2_with_windowed_attn.py) 12.0%; forward (torch/nn/modules/linear.py) 9.0%; layer_norm (torch/nn/functional.py) 5.8%; _call_impl (torch/nn/modules/module.py) 4.1%

### e2_li_on_a — compute threads per frame: on-CPU 0.286 s, run queue 0.001 s, sleep 5.414 s; callers' total GIL wait 0.011 s per frame; G (in forward) 0.000 s

| thread (top by on-CPU) | name | on-CPU s |
|---|---|---|
| 14256 | python | 60.4 |
| 13916 | python | 60.0 |
| 14086 | python | 58.2 |
| 14171 | python | 58.2 |
| 13831 | python | 57.7 |
| 14001 | python | 55.5 |
| 13661 | python | 54.6 |
| 13486 | python | 52.2 |

GIL holders (py-spy --gil, innermost frame): forward (rfdetr/models/backbone/dinov2_with_windowed_attn.py) 13.7%; forward (torch/nn/modules/linear.py) 9.5%; _call_impl (torch/nn/modules/module.py) 8.1%; layer_norm (torch/nn/functional.py) 6.2%; transpose_for_scores (rfdetr/models/backbone/dinov2_with_windowed_attn 5.9%

### e2_li_on_b — compute threads per frame: on-CPU 0.287 s, run queue 0.001 s, sleep 5.481 s; callers' total GIL wait 0.011 s per frame; G (in forward) 0.000 s

| thread (top by on-CPU) | name | on-CPU s |
|---|---|---|
| 29657 | python | 60.5 |
| 29317 | python | 59.8 |
| 29402 | python | 58.9 |
| 29742 | python | 57.9 |
| 29487 | python | 57.8 |
| 29147 | python | 56.7 |
| 29572 | python | 56.5 |
| 28972 | python | 52.1 |

GIL holders (py-spy --gil, innermost frame): forward (rfdetr/models/backbone/dinov2_with_windowed_attn.py) 14.9%; forward (torch/nn/modules/linear.py) 9.1%; _call_impl (torch/nn/modules/module.py) 8.6%; layer_norm (torch/nn/functional.py) 6.5%; transpose_for_scores (rfdetr/models/backbone/dinov2_with_windowed_attn 5.4%

## P1-B — the Tika wrapper fix

**Build (p1b_build.json):** rr:p1-tikafix `sha256:35d4b4774784` FROM rr:patched; PATCH (TikaApi.getPdfConfig code byte 9: iconst_1 -> iconst_0); CONFIG (tika-config.xml parser-exclude x2; ConfigBuilder.excludeExternalParserIfUnavailable offsets 0-8). Protected image ids before and after: ['rr:patched sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90', 'rr:patched-video sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de'].

**Correctness first (384 slice, C=32):** 382 documents ok in both; chunk lists differ on 0; lost by the fix 0; gained 0 → **PASS (pure win)**.

**Context — chunk identity over the full 9,975 (not the gate; the eleven stragglers are only here):** 9,885 documents ok in both; differ 0 ([]); lost by the fix 0; gained 1; stragglers ok in both 10, of which differ 0.

**Smoke (E1's engine path on the 11, this session):** p50 baseline 342.7 s vs fixed 5.70 s → 60.1x; exec census 3,380,028 → 452 (drop 99.99%) → **FIRED**.

| document | baseline s | fixed s |
|---|---|---|
| 000_000344.pdf | 342.7 | 5.50 |
| 002_002489.pdf | 269.8 | 5.64 |
| 008_008871.pdf | 492.1 | 6.02 |
| 011_011464.pdf | 819.8 | 5.70 |
| 011_011730.pdf | 426.1 | 5.45 |
| 014_014261.pdf | 357.4 | 5.18 |
| 014_014969.pdf | 200.7 | 5.17 |
| 031_031239.pdf | 284.4 | 6.60 |
| 033_033172.pdf | 300.8 | 6.05 |
| 034_034697.pdf | 212.1 | 5.75 |
| 039_039660.pdf | 1,796.7 | 6.38 |

**Speed, 384 slice ABAB:** baseline 2.5495 / 2.5621 vs fixed 2.8891 / 2.8668 docs/s → +12.61% against 0.82% → readable.

**Full 9,975, one run each:** baseline 2.3454 vs fixed 5.3441 docs/s → +127.85% against 0.82%; without the 11: +39.88%.

| leg | span docs/s | docs/s without the 11 | engine cores | idle spin cores | memory peak (total, sampled 1 Hz in window) | anon peak | lost docs | parse share of run total | steal / MHz |
|---|---|---|---|---|---|---|---|---|---|
| p1b_base_a | 2.5495 | 2.5495 | 16.33 | 1.220 | not recorded | not recorded | 2 | 34.7% | 0.001% / 2,816 |
| p1b_fix_a | 2.8891 | 2.8891 | 13.88 | 1.220 | not recorded | not recorded | 2 | 5.5% | 0.001% / 2,593 |
| p1b_base_b | 2.5621 | 2.5621 | 16.47 | 1.237 | 19,822 MB | 11,740 MB | 2 | 35.6% | 0.001% / 2,773 |
| p1b_fix_b | 2.8668 | 2.8668 | 13.79 | 1.218 | 20,405 MB | 12,330 MB | 2 | 5.5% | 0.001% / 2,608 |
| p1b_base_full | 2.3454 | 3.8161 | 18.07 | 1.234 | 25,386 MB | 17,250 MB | 90 | 41.3% | 0.001% / 2,835 |
| p1b_fix_full | 5.3441 | 5.3381 | 28.40 | 1.231 | 22,954 MB | 14,866 MB | 89 | 4.4% | 0.001% / 2,586 |

### p1b_base_full — stages (PROFILE; 9885 documents with a complete stamp set)

| stage | count | share of run total | min s | mean s | sd s | p50 s | p90 s | p95 s | p99 s | max s | mean/p50 | occupancy max / mean / p50 / p95 | timed from |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| admission | 9,885 | 0.1% | 0.001 | 0.008 | 0.023 | 0.003 | 0.016 | 0.033 | 0.092 | 0.860 | 2.79 | 30 / 0.02 / 0 / 0 | OUTSIDE (client submit -> engine pipe open) |
| parse_bracket | 9,885 | 41.3% | 0.014 | 3.372 | 29.883 | 0.266 | 3.852 | 8.746 | 51.646 | 1,695.658 | 12.70 | 32 / 7.91 / 9 / 16 | OUTSIDE (pipe open -> parse's last text): upload, executor-thread wait, Tika and engine glue; parse is native C++ |
| split | 9,885 | 0.1% | 0.000 | 0.005 | 0.015 | 0.002 | 0.010 | 0.017 | 0.045 | 0.423 | 2.75 | 5 / 0.01 / 0 / 0 | INSIDE at node boundaries (LangChain splitter, Python) |
| embed | 9,885 | 57.0% | 0.015 | 4.655 | 12.002 | 1.798 | 9.803 | 16.201 | 45.126 | 440.369 | 2.59 | 28 / 10.92 / 15 / 22 | INSIDE at node boundaries (MiniLM, Python/torch; node's buffered flush) |
| return | 9,885 | 1.5% | 0.004 | 0.122 | 0.269 | 0.049 | 0.254 | 0.436 | 1.333 | 5.571 | 2.47 | 17 / 0.29 / 0 / 1 | OUTSIDE (embed's last documents -> client completion) |

### p1b_fix_full — stages (PROFILE; 9886 documents with a complete stamp set)

| stage | count | share of run total | min s | mean s | sd s | p50 s | p90 s | p95 s | p99 s | max s | mean/p50 | occupancy max / mean / p50 / p95 | timed from |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| admission | 9,886 | 0.3% | 0.001 | 0.017 | 0.039 | 0.006 | 0.038 | 0.063 | 0.156 | 0.659 | 2.81 | 29 / 0.09 / 0 / 1 | OUTSIDE (client submit -> engine pipe open) |
| parse_bracket | 9,886 | 4.4% | 0.017 | 0.257 | 0.421 | 0.151 | 0.503 | 0.749 | 1.943 | 15.337 | 1.70 | 32 / 1.37 / 1 / 4 | OUTSIDE (pipe open -> parse's last text): upload, executor-thread wait, Tika and engine glue; parse is native C++ |
| split | 9,886 | 0.1% | 0.000 | 0.006 | 0.013 | 0.003 | 0.015 | 0.022 | 0.047 | 0.344 | 2.26 | 4 / 0.03 / 0 / 0 | INSIDE at node boundaries (LangChain splitter, Python) |
| embed | 9,886 | 92.6% | 0.028 | 5.407 | 13.600 | 2.163 | 11.285 | 18.843 | 51.715 | 491.625 | 2.50 | 32 / 28.89 / 30 / 32 | INSIDE at node boundaries (MiniLM, Python/torch; node's buffered flush) |
| return | 9,886 | 2.6% | 0.004 | 0.149 | 0.277 | 0.068 | 0.321 | 0.543 | 1.459 | 5.276 | 2.19 | 20 / 0.80 / 0 / 3 | OUTSIDE (embed's last documents -> client completion) |

## P1-C — native parser prototype (pypdfium2; PURE and HYBRID)

**Verdict: NOT RUN — the prototype's parser never ran: pypdfium2 failed on every document in every P1-C leg (node counters: text 0 in every leg, errors on at least 90% of the documents counted; the counters are snapshots written every 50 documents, so they trail the leg's totals); PURE returned no text, and HYBRID produced text for no document itself — its documents came out through the fixed Tika.** The prototype node's own counters, per leg (docs / text / fallback / errors): p1c_hyb_full 10000/0/10000/10000; p1c_pure_full 10000/0/0/10000; p1c_hyb_a 300/0/300/300; p1c_pure_a 303/0/0/297; p1c_hyb_b 350/0/348/348; p1c_pure_b 403/0/0/396.

**Context (not the P1-C question):** the node produced no text, so HYBRID's output is fixed Tika's behind the node's buffer-and-replay path. Full corpus: 9,886 documents ok in both, chunk lists differ on 0, lost 0, gained 0; docs/s 5.3441 (fixed Tika) vs 5.3037 (replay) → -0.76% against 0.82%. 384 ABAB: 2.8711 / 2.8602 vs 2.8293 / 2.8690 → -0.57% against 1.39% (UNREADABLE).

| leg | span docs/s | docs/s without the 11 | engine cores | idle spin cores | memory peak (total, sampled 1 Hz in window) | anon peak | lost docs | parse share of run total | steal / MHz |
|---|---|---|---|---|---|---|---|---|---|
| p1c_hyb_full | 5.3037 | 5.2978 | 28.11 | 1.229 | 21,929 MB | 13,842 MB | 89 | 4.8% | 0.002% / 2,586 |
| p1c_pure_full | 0.0000 | 0.0000 | 2.56 | 1.218 | 9,320 MB | 1,262 MB | 9,975 | — | 0.001% / 3,062 |
| p1c_fix_a | 2.8711 | 2.8711 | 13.92 | 1.236 | 18,824 MB | 10,751 MB | 2 | 6.0% | 0.001% / 2,576 |
| p1c_hyb_a | 2.8293 | 2.8293 | 13.58 | 1.232 | 19,574 MB | 11,500 MB | 2 | 6.0% | 0.001% / 2,591 |
| p1c_pure_a | 0.0000 | 0.0000 | 2.58 | 1.228 | 9,100 MB | 1,052 MB | 384 | — | 0.005% / 2,900 |
| p1c_fix_b | 2.8602 | 2.8602 | 13.83 | 1.225 | 20,429 MB | 12,355 MB | 2 | 5.9% | 0.001% / 2,582 |
| p1c_hyb_b | 2.8690 | 2.8690 | 13.73 | 1.239 | 19,890 MB | 11,815 MB | 2 | 6.4% | 0.001% / 2,595 |
| p1c_pure_b | 0.0000 | 0.0000 | 2.54 | 1.229 | 9,118 MB | 1,067 MB | 384 | — | 0.000% / 2,955 |


## P1-D — V1 at 168 videos

| arm | leg | videos | errors | frames | frames/s | CPU-s per frame | memory peak (sampled) | determinism vs P0 V1 |
|---|---|---|---|---|---|---|---|---|
| rr | v1full_rr_t4 | 168 | 0 | 23,049 | 2.532 | 1.514 | 16,693 MB | 16 videos, identical yes |

**Gap: NOT RUN** — the LlamaIndex 168-video leg did not run: the chain's per-leg check found the P1 11-hour budget passed (chain_video_v1full_done.json: v1full_li_t4:NOT_RUN_budget); one arm has no comparison.

## Amendments to the pre-registration

- preregistration_amendment_1.json: P1 amendment 1 — before any measured leg (only tooling tests had run)

## Session

Box boot ids across every P1 leg in this report: ['e293381c-aa59-4b05-92e2-c0e4f6167125'] (one session).

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (P1-A E2, P1-B, P1-C, P1-D) and amendment 1 (the tracer's maps and GIL buckets, before any measured leg).
- **2. EVIDENCE:** every figure in this report is computed by working/scripts/p1_report.py from analysis_e2.json, analysis_p1docs.json and analysis_v1full168.json, produced by committed analysers from the raw leg directories beside them (large files as lossless gzip copies, originals in S3 — E2_FILES_NOTE.md, P1_FILES_NOTE.md); the build and gate records are p1b_build.json, p1b_correctness.json and p1b_smoke_gate.json; the chain logs are in box_logs/.
- **3. NULL CONTROL:** E2: tracer ON vs OFF, per arm, had to agree within the floor with identical output — it FAILED on both arms (output identical, throughput not), and the ON-leg readings are withdrawn as readings. P1-B: the 384-slice chunk identity had to hold (it did). The blind recomputation's planted figures had to be caught (see P1_BLIND_VERIFICATION.json).
- **4. REGISTER:** 2 (self-consistency: E2's null control crosses the tracer boundary and failed); 3 (conditions: one box session, boot e293381c, for every P1 leg); 34 (a pre-registration refuted or left unreadable on its own terms: E2); 48 (blind recomputation); 49 (a read-back must not become part of the measurement: the E2 read-back runs once per process); 50, 53 (sudo in a one-shot run, again); 54 (the build check nobody listened to); 55 (the sampler with nowhere to write; the DEGRADED leg retried).
- **5. NOT VERIFIED:** why RocketRide's forward pass waits (E2 unreadable); pypdfium2 inside the engine (P1-C never ran it); the 168-video gap (LlamaIndex leg not run); memory on P1-B's first pair; that the full-corpus chunk identity would hold for other corpora; the texts of the full runs are in S3 only and were not re-read for this report (P1-B's full-corpus identity is by chunk hash).
- **6. GATES:** every P1 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the box was stopped by the operator at 08:18Z, started by me at about 15:18Z for two minutes to upload the watcher's files and logs, and stopped again with box.sh stop, read back as stopped at 15:20:49Z. This session was idle from about 00:00Z to 15:16Z (no monitoring in that time); the chains ran by themselves as designed.

