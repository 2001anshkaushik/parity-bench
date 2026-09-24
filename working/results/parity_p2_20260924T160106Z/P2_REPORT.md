# P2 — docs headline, parser rerun, video configuration suspects, and the source traces

Campaign `parity_p2_20260924T160106Z`, branch feat/parity-p2 (cut from the P1 deliverable d367c99). Generated 2026-09-24T19:25:53Z from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison is ABAB inside one box session (see Session); banked P0/P1/Stage-4 figures appear only as context.

**Blind recomputation (P2_BLIND_VERIFICATION.json):** PASS — 326 figures checked by 3 verifiers; plants caught 3 of 3; other mismatches 0.

## Verdicts

| experiment | verdict | measured (from the analysis files) | reading |
|---|---|---|---|
| P2-A docs headline | NOT RUN at full scale (gate not fired) | smoke ratio 0.8262 (gate 0.85: NOT FIRED); full NOT RUN | one RocketRide token reached less than 0.85 of LlamaIndex's 24-worker optimum on the 384 slice, so the full-scale comparison was not run; per unit (the 96 anchor), one token is far ahead of one worker |
| P2-B video configuration | CONFIGURATION DOES NOT EXPLAIN THE GAP (at this strength: the debugger and MALLOC_ARENA_MAX jointly ruled out as the main cause) | closure 0.252; COMBINED +8.55% vs baseline; gap +34.00% | debugger off + MALLOC_ARENA_MAX=2: output-identical, readably faster, closes about a quarter of the gap (bar: half) |
| P2-C native parser | 'gains little': NOT RUN (G_build_C: the image or its in-image check failed or never ran) | fired variants []; build FAIL/NOT RUN | NOT RUN: the in-image check failed on a bug in the check itself (register 57); the master stopped P2-C as pre-registered |
| P2-D source (laptop) | done (source; no measurement) | — | embedding path traced on both arms, fixes ranked; the wrapper product-fix ticket drafted (not filed) |

## Gate table

Every threshold was committed in preregistration.json before its stage ran; each gate's record is in gates/ and master_done.json.

| gate | threshold | measured | outcome | known bias (recorded before data) |
|---|---|---|---|---|
| G_memstat (p2a_rr_a) | ≥ 1 row in the first leg's memstat.jsonl | 316 | PASS | — |
| G_memstat (p2b_rr_base_a) | ≥ 1 row in the first leg's memstat.jsonl | 1,469 | PASS | — |
| G_mandate (D0, every RocketRide cell) | no violation | 0 violations in 8 docs legs; video chain complete with no violation record | PASS | — |
| G_smoke_A (P2-A) | mean RR / mean LI span docs/s ≥ 0.85 (384 slice) | 0.8262 (RR 2.6075, LI 3.1561 docs/s; spreads RR 1.83%, LI 8.19%; floors RR 0.82%, LI 9.87%) | NOT FIRED | none of the eleven is in the 384 slice; P1-B +12.6% on the 384 slice vs +128% full: the gate understates RocketRide |
| G_build_C (rr:p2-pdfium) | build + in-image import-and-parse check pass, base ids unchanged | check ok=False, chars 10,314, pypdfium2 5.13.0, rc 1; error: UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 267: ordinal not in range(128) | FAIL | — |
| G_smoke_C (hybrid, pure) | (a) (T − V)/T > spread_T on the eleven AND (b) 0 coverage losses on the 384 slice | no P2-C leg ran | NOT RUN (G_build_C failed) | recorded before data (preregistration.json SMOKE_GATE_P2_C.KNOWN_BIAS) |
| G_manip_B (p2b_rr_base_a, base) | baseline must show the debugger loaded and no MALLOC_ARENA_MAX | debugger loaded yes; MALLOC_ARENA_MAX unset; detector OS threads 182 | PASS | — |
| G_manip_B (p2b_rr_comb_a, comb) | COMBINED must show no debugger (pydevd_loaded false, no sys.monitoring tool) and MALLOC_ARENA_MAX=2 | debugger loaded no; MALLOC_ARENA_MAX 2; detector OS threads 179 | PASS | — |
| P2-B correctness (COMBINED vs baseline) | chunk-identical 16/16 in both pairs | p2b_rr_base_a vs p2b_rr_comb_a: 16 compared, chunk differ 0, scores differ 0; p2b_rr_base_b vs p2b_rr_comb_b: 16 compared, chunk differ 0, scores differ 0 | PASS | — |
| budget | 8 h from the first leg | 8 h from the first leg: deadline 2026-09-25T00:13:15Z (epoch 1790295195) | SET | — |
| protected image ids (rr:patched, rr:patched-video) | unchanged start → end | start: sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90 sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de  end: sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90 sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de  | UNCHANGED | — |

## NOT RUN

- P2-A full run (9,975, both arms): the pre-registered smoke gate did not fire (gates/G_smoke_A.json); per the protocol only that full run is skipped. Its known bias (the eleven are not in the 384 slice) was recorded before data and is not corrected.
- P2-C smoke and full runs (both variants): G_build_C failed (p2c_build.json). The image's pypdfium2 half passed; the check failed on its own reading of the node source (register 57). Ansh was asked at 16:50Z whether to rerun P2-C with the check fixed, on a new tag, recorded as amendment 2; no answer was received before the report was written, so P2-C stays NOT RUN, as the hard-gate rule says.
- The 168-video confirmation: deferred to P3 with its own gate, by the P2 instructions.
- P2-B single-knob decomposition: not designed, because the pre-registered condition for it (closure of at least half the gap) was not met.

## The 08:18Z stop (CloudTrail, read-only)

READ-ONLY, nothing changed. The StopInstances event at 08:18:37Z on 2026-09-24 could not be looked up: cloudtrail:LookupEvents and cloudtrail:DescribeTrails are denied to the BenchmarkBoxOperator role (AccessDeniedException), as is ec2:DescribeTags. What the role can read: the SSM session history shows no session on the box between 23:31:39Z on 2026-09-23 and 15:18:56Z on 2026-09-24, so the stop was not issued from inside the OS through a session; and the chain record read 'User initiated', EC2's wording for an API or console StopInstances. The principal is NOT known. P1's report attributed the stop to 'the operator' without evidence; that attribution is withdrawn (register 56; the landed P1 files are not edited). Someone with CloudTrail read access can get the principal with: aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=ResourceName,AttributeValue=i-0775f33f3dc16f6af --start-time 2026-09-24T08:00:00Z --end-time 2026-09-24T08:40:00Z

## Recommendation

Docs: one RocketRide token does not reach LlamaIndex's 24-worker optimum on the 384 slice, and neither arm uses half of the 32 cores there; the lever that remains inside one instance is the embedding stage (P2-D: cross-document micro-batching with forward-concurrency shaping, then the per-chunk conversions), which should be the next docs experiment, gated on output identity. Video: launch RocketRide's task with noDebug and set MALLOC_ARENA_MAX=2. The change is output-identical and readably faster, and it holds far less anonymous memory, but it is not the cause of the gap; P3 should trace the engine-side idle burn and the thread population, with an instrument light enough to pass its own null control. Wrapper: ship P1-B's result as the source-level change in the ticket draft (image extraction only when the image lane has a listener; the tool probe once per process), never as the one-byte patch. Parser: P2-C is unanswered; it can run as soon as the check is fixed (the image content passed its pypdfium2 check).

## P2-A — the docs headline: one RocketRide token vs LlamaIndex's 24-worker optimum

**Correctness first.** rr:p1-tikafix's output was decided in P1-B (chunk-identical to rr:patched on the 384 gate slice, and over the full corpus as context); P2-A changes no cell. Within this session: RocketRide's two 384 runs agree on 382 documents ok in both, chunk lists differ on 0, lost 0.

### Smoke (1): the 384 slice, C=32, ABAB two runs each

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p2a_rr_a | 2.6314 | 2.6314 | 382/384 | 5.116 | 13.461 | 42.1% | 18.412 | 1.240 | 19,471 MB | steal 0.00%, 2537.4 MHz |
| p2a_li_a | 3.0268 | 3.0268 | 381/384 | 4.117 | 12.460 | 38.9% | 19.438 | 0.041 | 18,011 MB | steal 0.00%, 2585.1 MHz |
| p2a_rr_b | 2.5835 | 2.5835 | 382/384 | 5.181 | 13.384 | 41.8% | 18.509 | 1.238 | 19,907 MB | steal 0.00%, 2540.6 MHz |
| p2a_li_b | 3.2854 | 3.2854 | 381/384 | 4.196 | 13.785 | 43.1% | 18.085 | 0.041 | 17,565 MB | steal 0.00%, 2555.4 MHz |

**Gate G_smoke_A:** mean RocketRide 2.6075 vs mean LlamaIndex 3.1561 docs/s → ratio **0.8262** against 0.85 → **NOT FIRED**. Beside it: within-session spreads RocketRide 1.83%, LlamaIndex 8.19%; noise floors RocketRide 0.82%, LlamaIndex 9.87%. Known bias (recorded before data): none of the eleven is in the 384 slice; P1-B +12.6% on the 384 slice vs +128% full: the gate understates RocketRide. Recomputed here from the raw legs; agrees with the chain's record: yes.

### Smoke (2): the per-unit anchor, 96 slice, C=8 (no gate)

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p2a_an_rr_a | 1.7384 | 1.7384 | 96/96 | 3.510 | 6.101 | 19.1% | 25.853 | 1.224 | 13,050 MB | steal 0.00%, 2588.6 MHz |
| p2a_an_li_a | 0.4085 | 0.4085 | 95/96 | 2.448 | 1.000 | 3.1% | 30.994 | 0.002 | 808 MB | steal 0.01%, 2462.1 MHz |
| p2a_an_rr_b | 1.7535 | 1.7535 | 96/96 | 3.497 | 6.131 | 19.2% | 25.787 | 1.232 | 12,805 MB | steal 0.01%, 2592.1 MHz |
| p2a_an_li_b | 0.4079 | 0.4079 | 95/96 | 2.452 | 1.000 | 3.1% | 30.994 | 0.002 | 797 MB | steal 0.00%, 2463.0 MHz |

One RocketRide token 1.7460 vs one LlamaIndex worker 0.4082 docs/s → ratio 4.278 (+327.76%) against max(9.87%, spreads) = 9.87% → readable. Read with P2-D: one LlamaIndex worker processes one document at a time (its endpoint runs the work on its event loop), while one RocketRide token at C=8 runs up to 8 documents' forwards at once inside one process, so the per-unit ratio measures RocketRide's in-instance concurrency, not two like units.

### Full run (9,975, one run each)

**NOT RUN** — the pre-registered smoke gate did not fire (the ratio fell short of 0.85), so the full run was skipped, as the protocol says. The gate's known bias was recorded before any data and is not corrected: none of the eleven pathological PDFs is in the 384 slice, where P1-B's fix gained least. Whether one token matches the 24-worker optimum at full scale is therefore NOT answered in this session.

## P2-C — the native parser rerun (pypdfium2; PURE and HYBRID)

**Build (p2c_build.json):** rr:p2-pdfium `sha256:e75222cffc22` FROM rr:p1-tikafix; wheel installed by its RECORD (pypdfium2, pypdfium2-5.13.0.dist-info, pypdfium2_cfg, pypdfium2_cli, pypdfium2_raw); in-image check (the engine's own Python): ok=False, pypdfium2 5.13.0, pypdfium2_cfg imported from /opt/rocketride/engine/lib/python3.12/site-packages/pypdfium2_cfg/__init__.py, 1 page(s) / 10,314 characters from 002_002489.pdf, node flags None / None; base ids before and after: ['rr:patched sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90', 'rr:patched-video sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de', 'rr:p1-tikafix sha256:35d4b477478417b55fcd29b516e83d885975df3100f8e0f4e066dc797a5d879b']. **G_build_C: FAIL.**

### Smoke (i) and (ii), the gate, and the full runs

**NOT RUN** — no P2-C leg ran: G_build_C failed, and the master stopped every stage that depends on the image (preregistration.json hard_dependency_gates).

**P2-C verdict (pre-registered): the hypothesis 'a native parser gains little' is NOT RUN (G_build_C: the image or its in-image check failed or never ran).** The build gate failed on a bug in my own check, not in the image (register 57): the pypdfium2 half passed inside the image (pypdfium2_cfg imported, the test PDF parsed), and the check then read the node's UTF-8 source with the engine interpreter's ASCII default. The master stopped P2-C as the rule requires. Ansh was asked at 16:50Z whether to rerun P2-C with the check fixed, on a new tag, recorded as amendment 2; no answer was received before the report was written, so P2-C stays NOT RUN, as the hard-gate rule says.

## P2-B — video configuration suspects, untraced (16 videos, K=16, T=4)

| leg | frames/s (export) | frames/s (records) | errors | forward per frame (s) | caller on-CPU / forward | debugger (env_probe; detector sys.monitoring) | malloc env (detector) | detector OS threads | sampled memory peak anon / total |
|---|---|---|---|---|---|---|---|---|---|
| p2b_rr_base_a | 2.4387 | 2.4611 | 0 | 0.3970 | 0.607 | pydevd {'d0_pre': True}, tools {'0': 'pydevd'} | unset | 182 | 5,209 MB / 8,540 MB |
| p2b_rr_base_b | 2.5649 | 2.5897 | 0 | 0.3773 | 0.602 | pydevd {'d0_pre': True}, tools {'0': 'pydevd'} | unset | 182 | 5,585 MB / 7,512 MB |
| p2b_rr_comb_a | 2.7789 | 2.8081 | 0 | 0.3473 | 0.625 | pydevd {'d0_pre': False}, tools {} | {'MALLOC_ARENA_MAX': '2'} | 179 | 2,428 MB / 5,664 MB |
| p2b_rr_comb_b | 2.6526 | 2.6790 | 0 | 0.3642 | 0.622 | pydevd {'d0_pre': False}, tools {} | {'MALLOC_ARENA_MAX': '2'} | 179 | 2,401 MB / 5,719 MB |
| p2b_li_a | 3.3161 | 3.3568 | 0 | 0.2811 | 0.738 | pydevd {}, tools {} | {'MALLOC_ARENA_MAX': '2'} | 34 | 1,645 MB / 5,992 MB |
| p2b_li_b | 3.3887 | 3.4321 | 0 | 0.2754 | 0.743 | pydevd {}, tools {} | {'MALLOC_ARENA_MAX': '2'} | 34 | 1,665 MB / 5,363 MB |

**Correctness first:** COMBINED vs baseline — p2b_rr_base_a vs p2b_rr_comb_a: 16 videos, chunk hashes differ 0, frame scores differ 0; p2b_rr_base_b vs p2b_rr_comb_b: 16 videos, chunk hashes differ 0, frame scores differ 0 → **PASS**.

Determinism (context): p2b_rr_base_a_vs_p2b_rr_base_b: identical (16 videos); p2b_li_a_vs_p2b_li_b: identical (16 videos); p2b_rr_base_a_vs_P1_e2_rr_off_a: identical (16 videos); p2b_li_a_vs_P1_e2_li_off_a: identical (16 videos).

| cell | legs | frames/s | mean | spread |
|---|---|---|---|---|
| rr_base | p2b_rr_base_a, p2b_rr_base_b | 2.4387, 2.5649 | 2.5018 | 5.04% |
| rr_comb | p2b_rr_comb_a, p2b_rr_comb_b | 2.7789, 2.6526 | 2.7158 | 4.65% |
| li_ref | p2b_li_a, p2b_li_b | 3.3161, 3.3887 | 3.3524 | 2.17% |

**Reading (pre-registered, PRIMARY frames/s):** gap LlamaIndex over RocketRide baseline +34.00% against 5.04% → reproduced in session; COMBINED over baseline +8.55% against 5.04% (beyond the replicate spread); closure 0.252 of the gap (bar 0.5). **Verdict: CONFIGURATION DOES NOT EXPLAIN THE GAP (at this strength: the debugger and MALLOC_ARENA_MAX jointly ruled out as the main cause).**

Mechanism (secondary, reported beside): forward per frame baseline 0.3871 s, COMBINED 0.3558 s, LlamaIndex 0.2782 s → COMBINED -8.10% vs baseline; closure on F 0.288.

Read-back differences that remain between RocketRide COMBINED and LlamaIndex (detector process): os_threads_detector: {"rr_comb": 179, "li": 34}; python_threads_detector: {"rr_comb": 8, "li": 18}; env_detector: {"TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": {"rr_comb": "1", "li": null}}.

Removing the debugger and setting MALLOC_ARENA_MAX=2 together made RocketRide's video leg readably faster, and its output was identical to the baseline's on every video. It closed about a quarter of the gap to LlamaIndex, well short of the pre-registered half, so configuration does NOT explain the gap. The same cell also held far less anonymous memory than the baseline; that is a memory result, reported without a pre-registered floor. POST-HOC observations for P3 (not pre-registered): RocketRide's task process burns about one core with nothing submitted (the measured idle burden), which LlamaIndex does not; net of that burn, RocketRide's CPU per frame is close to LlamaIndex's, but its forward pass runs on fewer cores at once and its calling thread is off-CPU for more of it; both arms have 16 forward-calling threads and identical pool settings. The next suspects named from the read-backs are that constant engine-side burn (which threads spin, and whether they compete with the forward's OpenMP team) and the task process's thread population (engine pools named pipeline, scanner, AwsEventLoop and Work, against LlamaIndex's 34 threads). The single-knob decomposition is not designed, because the pre-registered bar for it was not met.

**POST-HOC figures behind the observations above (not pre-registered; context for P3):**

| leg | service cores | idle cores with the instance live (nothing submitted) | CPU-s per frame | CPU-s per frame net of that idle burn | process cores during the forward pass |
|---|---|---|---|---|---|
| p2b_rr_base_a | 3.688 | 1.232 | 1.512 | 1.007 | 2.462 |
| p2b_rr_base_b | 3.650 | 1.232 | 1.423 | 0.943 | 2.425 |
| p2b_rr_comb_a | 3.815 | 1.234 | 1.373 | 0.929 | 2.569 |
| p2b_rr_comb_b | 3.755 | 1.238 | 1.416 | 0.949 | 2.509 |
| p2b_li_a | 2.984 | 0.005 | 0.900 | 0.898 | 2.756 |
| p2b_li_b | 3.021 | 0.005 | 0.891 | 0.890 | 2.784 |

## P2-D — laptop, from source

- **Embedding trace:** [P2D_EMBEDDING_TRACE.md](P2D_EMBEDDING_TRACE.md). Neither arm batches across documents. RocketRide runs every chunk of a document through the engine's own sentence-transformer wrapper in forward passes of up to 32, and up to 32 documents' forwards run at once in one process with no lock, one thread each. Each LlamaIndex worker handles one document at a time, in slices of 10. The in-bounds fixes are ranked with P0's three columns there: cross-document micro-batching paired with forward-concurrency shaping (PYTHON, THREADING), inference_mode, removing the per-chunk conversions and caching a per-call parameter walk (PATCH), and noDebug (CONFIG).
- **Wrapper product-fix ticket (DRAFT, not filed):** [P2D_WRAPPER_TICKET_DRAFT.md](P2D_WRAPPER_TICKET_DRAFT.md). The per-image process spawns come from RocketRide's own wrapper: for every embedded image it rebuilds its whole Tika configuration, which re-runs an external-tool probe. The engine already checks whether anything listens on the image lane, but only after Tika has extracted and streamed every image. The fix passes a 'listener present' flag into the wrapper, reuses the configuration built at start-up, and memoises the probe. The test proves image lanes still deliver, with a null control.

## Amendments to the pre-registration

- preregistration_amendment_1.json: P2 pre-registration AMENDMENT 1 — written 16:25Z, BEFORE any P2-B leg (the master was on P2-A smoke leg 1; P2-B runs third); corrects a definition's wording to the function it names; no threshold or rule changes

## Session

Box boot ids across every P2 leg in this report: ['dc407ed6-d6b2-4cde-9dc9-3b3a2608066d'] (one session).

## Register entries added

- 56 — an attribution nobody could read (the P1 box stop), and a check that could never have passed (P1's in-image check imported the node outside the engine runtime)
- 57 — the check tested in pieces and never whole (P2's in-image check read the node's UTF-8 source with the engine interpreter's ASCII default)

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (P2-A, P2-B, P2-C, P2-D, every smoke-gate threshold and known bias) and amendment 1 (P2-B's primary metric: its words corrected to the function it names, before any P2-B leg).
- **2. EVIDENCE:** every figure in this report is computed by working/scripts/p2_report.py from analysis_p2docs.json and analysis_p2b.json (produced by the committed analysers from the raw leg directories beside them), the gate records in gates/, master_done.json and p2c_build.json; the box log is box_logs/p2_master.log. The P2-D documents cite file:line or bytecode offsets, each marked checked or UNVERIFIED.
- **3. NULL CONTROL:** each gate in p2_gates.py was tested offline on a case built to pass and a null control built to fail (p2_tooling_test.py: 31 pass, 0 fail); the in-image check failed on P1's broken image, as it had to; the P2-B manipulation gate passed the baseline and failed it as COMBINED, on P1's banked read-backs. The blind recomputation's planted figures had to be caught (P2_BLIND_VERIFICATION.json).
- **4. REGISTER:** 3 (one box session, boot dc407ed6, for every P2 leg); 34 (the P2-C pre-registration left unanswered on its own terms); 48 (blind recomputation); 49 (the read-backs run once per process, outside the measured work); 54 (the master gated on every build and check, and did stop P2-C); 55 (the sampler started after its directory existed and was verified after the first leg; a DEGRADED leg is a result); 56 and 57 (added).
- **5. NOT VERIFIED:** whether one RocketRide token matches the 24-worker optimum at full scale (the gate did not fire); anything about pypdfium2 inside the engine (P2-C did not run); the cause of the video gap (configuration explains about a quarter; the rest is untraced); the post-hoc idle-burn and thread-population observations (not pre-registered); the P2-D fixes' sizes (source only); the wrapper ticket's C++ citations come from a source checkout outside this repository.
- **6. GATES:** every P2 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the master launched once (box.sh launch) at 16:13:15Z and ran to completion at 19:16:55Z, protected image ids read back unchanged at start and end; the box is stopped with box.sh stop at the end and its state read back.

