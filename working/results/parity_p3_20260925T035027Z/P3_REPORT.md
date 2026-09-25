# P3 — docs at full scale, the video discriminator, embedding thread shape, the parser rerun, and two drafts

Campaign `parity_p3_20260925T035027Z`, branch feat/parity-p3 (cut from the P2 deliverable eaa65223). Generated 2026-09-25T07:55:01Z from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison is ABAB inside one box session (see Session); banked figures from earlier phases appear only as context.

**Blind recomputation (P3_BLIND_VERIFICATION.json):** PASS — 604 figures checked by 4 verifiers; plants caught 4 of 4; other mismatches 0 (round 1: BLOCKED — one real mismatch in the prose, fixed; round 2 re-verified the changed sections: PASS).

## Verdicts

| experiment | verdict | measured (from the analysis files) | reading |
|---|---|---|---|
| P3-A docs full-scale headline | SUPPORTED | RR/LI = 1.0664 (n=1 per arm; readable band 0.7804–0.9196) | one RocketRide token reaches the 0.85 bar at full scale readably; whether it beats LlamaIndex's 24 workers is inside LlamaIndex's replicate spread |
| P3-B video discriminator | NO PRE-REGISTERED READING MATCHES (the three relations are reported) | (1) inspection: SUPPORTED | by the pre-registered rules: (2) no reading matches; (1) reads SUPPORTED but its rule is defective and the hypothesis is contradicted (register 59) |
| P3-C embedding thread shape | winner 4 | fired ['2', '4'] | smoke fired (vars=4 +60% on the 384 slice) but the full run is readably SLOWER than vars=1 (-4.56%): the slice's idle cores, not the shape |
| P3-D parser rerun | 'gains little': NOT SUPPORTED | fired variants ['hybrid', 'pure'] | HYBRID adoptable and +10.39% at full scale -> 'gains little' NOT SUPPORTED by the rule; PURE loses 5 documents; the gain comes with 10.9% fewer, different chunks |
| P3-E drafts (laptop) | written (not filed) | — | two drafts written in the campaign directory; nothing filed, posted or sent |

## Gate controls (the P3 rule: every gate whole, in its real runtime, positive must PASS, null must FAIL)

**gate_controls.json** (run 1): 20 of 24 controls as expected → all_pass **False** (59.4 s, boot 3a2dc046).

**gate_controls_run2.json** (run 2): 24 of 24 controls as expected → all_pass **True** (70.8 s, boot 3a2dc046).

| gate | positive control (must PASS) | null control(s) (must FAIL) |
|---|---|---|
| G_memstat | P2's p2a_rr_a → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | an empty memstat.jsonl → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_mandate_docs | P2's p2a_rr_a (clean) → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | the same leg marked violating → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_mandate_video | P2's p2b_rr_base_a (clean) → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | a leg with MANDATE_VIOLATION.json → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_health_A | P2's p2a_rr_b / p2a_li_b as the P3 legs → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | one chunk hash altered in the RR leg → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)); the LlamaIndex leg's memory sampler empty → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_smoke_C | vars=2 10% faster, chunks identical → as expected (expected ["2"], got ["2"]) | vars=2 and vars=4 as fast as vars=1 → as expected (expected [], got []); vars=2 faster but one chunk list differs → as expected (expected [], got []) |
| G_node_D | counters with text → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | P1's failure (text 0) → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_smoke_D | HYBRID 10% faster than Tika's spread, no coverage loss → as expected (expected ["hybrid"], got ["hybrid"]) | both variants inside Tika's spread → as expected (expected [], got []) |
| G_alone | no container on the box → as expected (expected 0 (pass/fired/clean), got 0 (pass/fired/clean)) | one created container present → as expected (expected 1 (fail/not fired/violation), got 1 (fail/not fired/violation)) |
| G_build_D | rr:p2-pdfium (pypdfium2 complete) → as expected (expected ok=True rc=0, got ok=True rc=0) | rr:p1-pdfium (pypdfium2_cfg missing) → as expected (expected ok=False rc=1, got ok=False rc=1) |
| P3B_one_model (a) | one model → as expected (expected rc=0, got rc=0) | --null-two-models → as expected (expected rc=3, got rc=3) |
| P3B_one_model (b) | one model → as expected (expected rc=0, got rc=0) | --null-two-models → as expected (expected rc=3, got rc=3) |

## Gate table (decisions)

Every threshold was committed in preregistration.json before its stage ran; records in gates/ and master_done.json.

| gate | threshold | measured | outcome | exit |
|---|---|---|---|---|
| G_controls | pre-registered | gate_controls_run2.json all_pass (the GATE CONTROLS rule) | PASS | 0 |
| BUDGET | pre-registered | 7 h from the first leg: deadline 2026-09-25T10:59:08Z (epoch 1790333948) | SET | 0 |
| G_build_D | pre-registered | p2_pdfium_build.sh rr:p3-pdfium -> p3d_build.json | PASS | 0 |
| G_node_D | pre-registered | gates/G_node_D_hybrid.json, gates/G_node_D_pure.json | PASS | 0 |
| PROTECTED_IDS | pre-registered | start: sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90 sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de  end: sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90 sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de  | UNCHANGED | 0 |
| G_memstat (p3a_rr_full) | ≥ 1 row in the first leg's memstat.jsonl | 1,687 | PASS | — |
| G_memstat (p3a_rr_h) | ≥ 1 row in the first leg's memstat.jsonl | 181 | PASS | — |
| G_memstat (p3b_a_1) | ≥ 1 row in the first leg's memstat.jsonl | 141 | PASS | — |
| G_memstat (p3c_t1_a) | ≥ 1 row in the first leg's memstat.jsonl | 182 | PASS | — |
| G_memstat (p3c_t4_full) | ≥ 1 row in the first leg's memstat.jsonl | 1,704 | PASS | — |
| G_memstat (p3d_hyb_full) | ≥ 1 row in the first leg's memstat.jsonl | 1,494 | PASS | — |
| G_memstat (p3d_s_fix_a) | ≥ 1 row in the first leg's memstat.jsonl | 132 | PASS | — |
| G_health_A | all four health conditions | both_verdicts_ok_or_degraded_with_all_rows: yes; d0_clean: yes; memory_sampler_non_empty: yes; rr_chunks_identical_to_p2a_on_shared_documents: yes | FIRED |  |
| G_smoke_C (vars=2) | correctness first; then mean/mean(vars=1) − 1 > max(0.82%, spreads) | chunks identical yes; Δ +34.49% vs 0.82% | FIRED |  |
| G_smoke_C (vars=4) | correctness first; then mean/mean(vars=1) − 1 > max(0.82%, spreads) | chunks identical yes; Δ +59.95% vs 0.82% | FIRED |  |
| G_smoke_D (hybrid) | (a) AND (b) (P2-C's gate) | (a) (T−V)/T +9.23% vs spread_T 1.62%; (b) 0 coverage losses | FIRED |  |
| G_smoke_D (pure) | (a) AND (b) (P2-C's gate) | (a) (T−V)/T +9.89% vs spread_T 1.62%; (b) 0 coverage losses | FIRED |  |

## Step 0

**SSO:** EXPIRED at 03:35Z 2026-09-25 (refresh failed) -> login flow started under STEP 0's rule; the first authorization expired unapproved at ~03:45Z; the second was APPROVED by Ansh at 03:46:22Z

**Harness stop-call search:** READ-ONLY. working/harness/box.sh (383 lines) contains exactly ONE call that stops the instance: box.sh:344 `"${A[@]}" ec2 stop-instances --instance-ids "$INSTANCE"`, inside the `stop)` branch of the command dispatch — it runs only when box.sh is invoked with the explicit subcommand `stop`. box.sh has NO `trap` statement at all (none on EXIT, HUP, TERM or INT), sources no other script, and calls only the aws CLI (ec2 describe-instances / start-instances / wait / stop-instances; ssm start-session / describe-sessions) and `script` (the pty for SSM); `shutdown`, `reboot` and the like appear only in its REFUSAL list (box.sh:110-131) and its self-test cases (box.sh:262-263), i.e. they are blocked, never issued. Nothing in it fires on disconnect. Repo-wide, no other script calls stop-instances / terminate-instances / shutdown / poweroff; the traps that exist are all EXIT traps that stop or remove CONTAINERS or temp directories (batchsize_docs_run.sh:116, batchsize_video_run.sh:69, p0_video_chain.sh:35, p1_video_chain.sh:37, p2_video_chain.sh:39, p1_tooling_test.sh:11, and the build scripts' temp-dir traps), never the instance. Nothing was changed; the 08:18Z stop was not investigated further, by instruction.

## Recommendation

Docs: at full scale one RocketRide token at the banked posture (six thread vars = 1) reaches 1.07x LlamaIndex's 24-worker optimum, n = 1 per arm: the 0.85 parity bar is met readably; 'beats it' is not readable yet — a second full pair would settle it. Do NOT adopt thread vars = 4 for docs: it wins on the drain-dominated slice and loses at full scale. Video: the gap is a concurrency effect inside the engine at 16 videos in flight (P3-B post-hoc); P4 should measure RocketRide and LlamaIndex at K = 1 and K = 16, T = 4, ABAB in one session, before any tracer, and then look at how 16 callers share the detector (the device lock and per-caller OpenMP teams). Parser: do not ship HYBRID on speed alone — its gain is a different output (fewer chunks; a tail of documents whose text differs sharply from Tika's); if pursued, pre-register a text-quality gate (for example against a labelled sample) before a speed gate. PURE is out (it loses five documents). Ship the wrapper fix as P2's ticket describes, and the noDebug / MALLOC_ARENA_MAX change as P3-E's ticket describes.

## P3-A — the docs headline at full scale

### Health smoke (a HEALTH gate by Ansh's ruling — not a performance proxy)

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p3a_rr_h | 3.2356 | 3.2356 | 382/384 | 4.058 | 13.128 | 41.0% | 18.725 | 1.217 | 19,902 MB | steal 0.01%, 2795.1 MHz |
| p3a_li_h | 4.0261 | 4.0261 | 381/384 | 3.325 | 13.387 | 41.8% | 18.511 | 0.026 | 18,019 MB | steal 0.01%, 2834.3 MHz |

**G_health_A:** both verdicts ok or degraded with all rows: yes; d0 clean: yes; memory sampler non empty: yes; rr chunks identical to p2a on shared documents: yes → **FIRED**. Identity against P2-A's committed legs: p2a_rr_a: 382 shared ok documents, 0 differ; p2a_rr_b: 382 shared ok documents, 0 differ.

### Full run (9,975, one run each)

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p3a_rr_full | 6.2969 | 6.2899 | 9,886/9,975 | 4.442 | 27.968 | 87.4% | 3.826 | 1.234 | 21,826 MB | steal 0.00%, 3140.7 MHz |
| p3a_li_full | 5.9046 | 5.8981 | 9,873/9,975 | 3.881 | 22.914 | 71.6% | 9.035 | 0.026 | 18,069 MB | steal 0.00%, 3071.9 MHz |

**The ratio, plainly: one RocketRide token 6.2969 docs/s ÷ LlamaIndex 24 workers 5.9046 docs/s = 1.0664** (n = 1 per arm). LlamaIndex's smoke-scale replicate spread (8.19%, P2-A) bounds how much of it is readable: readably at or above 0.85 needs ≥ 0.9196, readably below needs < 0.7804 → **SUPPORTED**. Excluded-straggler view: 6.2899 vs 5.8981 docs/s = 1.0664.

Lost documents: RocketRide 89 (000_000164.pdf, 000_000357.pdf, 001_001657.pdf, 002_002014.pdf, 002_002103.pdf, 002_002189.pdf, 002_002472.pdf, 002_002477.pdf, 002_002978.pdf, 003_003010.pdf), LlamaIndex 102 (000_000164.pdf, 000_000357.pdf, 001_001657.pdf, 002_002014.pdf, 002_002103.pdf, 002_002189.pdf, 002_002400.pdf, 002_002472.pdf, 002_002477.pdf, 002_002978.pdf). Empty documents: RocketRide 89, LlamaIndex 102; RocketRide-only 0 (none); LlamaIndex-only 13 (002_002400.pdf, 004_004306.pdf, 008_008724.pdf, 009_009802.pdf, 014_014222.pdf, 018_018542.pdf, 020_020747.pdf, 020_020806.pdf, 022_022819.pdf, 027_027613.pdf, 033_033689.pdf, 037_037919.pdf, 040_040669.pdf).

## P3-B — the video discriminator

**Frames:** 695 PNG frames from EN2001a.avi, EN2001b.avi, EN2001d.avi (fps=1/15 -fps_mode passthrough -vcodec png (li:video imageio-ffmpeg)); bare cells' frames identical to the manifest: yes; engine frame count equals the manifest's: yes; one model instance in every bare leg: yes; detections identical frame by frame between (a) and (b) (run 1): yes.

| leg | measured frames | forward per frame F (s) | cores busy during the forward | caller on-CPU / forward | torch threads | caller threads | frames/s (service legs) |
|---|---|---|---|---|---|---|---|
| p3b_a_1 | 695 | 0.1860 | 5.001 | 1.000 | 4 | 1 | bare |
| p3b_a_2 | 695 | 0.1861 | 5.001 | 1.000 | 4 | 1 | bare |
| p3b_b_1 | 695 | 0.1843 | 4.000 | 1.000 | 4 | 1 | bare |
| p3b_b_2 | 695 | 0.1849 | 4.001 | 1.000 | 4 | 1 | bare |
| p3b_c_1 | 695 | 0.1890 | 4.225 | 0.999 | 4 | 3 | 4.4551 |
| p3b_c_2 | 695 | 0.1910 | 4.226 | 0.999 | 4 | 3 | 4.4155 |
| p3b_d_1 | 695 | 0.1917 | 4.001 | 1.000 | 4 | 1 | 3.1420 |

| cell | legs | F (s) | mean | spread |
|---|---|---|---|---|
| a | p3b_a_1, p3b_a_2 | 0.1860, 0.1861 | 0.1861 | 0.03% |
| b | p3b_b_1, p3b_b_2 | 0.1843, 0.1849 | 0.1846 | 0.35% |
| c | p3b_c_1, p3b_c_2 | 0.1890, 0.1910 | 0.1900 | 1.05% |

**Relations (F):** a > b (+0.78% against 0.35%; beyond the 0.82% floor: no); a < c (-2.06% against 1.05%; beyond the 0.82% floor: yes); b < c (-2.81% against 1.05%; beyond the 0.82% floor: yes).

**(2) Reading (pre-registered): NO PRE-REGISTERED READING MATCHES (the three relations are reported).**

**(1) Runtime inspection: SUPPORTED.** RR task process families: ['blas:libopenblas', 'openmp:libgomp']; LlamaIndex detector process families: ['blas:libopenblas', 'openmp:libgomp']; only in RR: []; only in LlamaIndex: []; RR OpenMP files: ['/opt/rocketride/engine/lib/python3.12/site-packages/simsimd.libs/libgomp-e985bcbb.so.1.0.0', '/opt/rocketride/engine/lib/python3.12/site-packages/torch/lib/libgomp.so.1']; bare (a) ['blas:libopenblas', 'openmp:libgomp'], bare (b) ['blas:libopenblas', 'openmp:libgomp'].

Read by the letter of the pre-registration, (2) matches none of its three readings: the bare RocketRide-image cell is 0.78% slower than the bare LlamaIndex-image cell, which is beyond the larger of their replicate spreads (both runs of each bare cell were very stable) but inside the carried 0.82% floor; the bare cells' forward passes are 2.1% and 2.8% shorter than the engine cell's. Under the floor view (reported beside, as registered) the pattern would read a ~= b < c, the engine environment — but it is a 2-3% effect, not the gap. (1): the pre-registered rule reads SUPPORTED because the RocketRide task process maps two OpenMP runtime files; the rule's first clause never compared against LlamaIndex, and LlamaIndex's detector maps the SAME two files (torch's libgomp and a vendored libgomp that simsimd ships), as do both bare processes — so the hypothesis as written ('a runtime LlamaIndex's does not load') is contradicted by the evidence (register 59). POST-HOC, not pre-registered, and the finding that matters: with ONE video in flight the engine's forward pass (about 0.190 s per frame) is within 3% of the bare interpreters and equal to LlamaIndex's service at one video (about 0.192 s); the RocketRide engine ran 4.4 f/s at one video in flight (the mean of its two legs), faster than LlamaIndex's service at one video (3.1 f/s). The 0.38-vs-0.28 s gap P1/P2 measured exists at 16 videos in flight, not at one — so it is not the model, the libraries, the interpreter or the process environment at rest, but what 16 concurrent callers do inside one engine process. The premise ruled out beforehand ('P0 measured K=1 at 2.39 f/s, no faster than K=16') came from the batch-size campaign's default posture, which ran the engine with its default threads (batchsize_video_run.sh:122, --rr-threads-env unset: torch 16 threads), not T=4; at T=4 one video in flight ran 4.4 f/s here (cross-session against P2-B's 2.5 f/s at 16 videos, far beyond the 15.4% cross-session drift). Also post-hoc: the bare RocketRide-image process kept 5.0 cores busy during a T=4 forward where the LlamaIndex image kept 4.0, at the same forward time.

## P3-C — embedding thread shape (six thread variables in {1, 2, 4})

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p3c_t1_a | 3.2271 | 3.2271 | 382/384 | 4.066 | 13.111 | 41.0% | 18.802 | 1.234 | 20,091 MB | steal 0.00%, 2796.5 MHz |
| p3c_t2_a | 4.3242 | 4.3242 | 382/384 | 4.154 | 17.945 | 56.1% | 13.898 | 1.232 | 18,522 MB | steal 0.00%, 2905.5 MHz |
| p3c_t4_a | 5.1451 | 5.1451 | 382/384 | 4.337 | 22.294 | 69.7% | 9.513 | 1.223 | 18,086 MB | steal 0.01%, 3016.7 MHz |
| p3c_t1_b | 3.2124 | 3.2124 | 382/384 | 4.072 | 13.071 | 40.8% | 18.791 | 1.226 | 19,399 MB | steal 0.01%, 2815.1 MHz |
| p3c_t2_b | 4.3365 | 4.3365 | 382/384 | 4.147 | 17.970 | 56.2% | 13.922 | 1.234 | 19,550 MB | steal 0.01%, 2916.7 MHz |
| p3c_t4_b | 5.1548 | 5.1548 | 382/384 | 4.329 | 22.293 | 69.7% | 9.558 | 1.235 | 17,812 MB | steal 0.00%, 3011.4 MHz |

**vars=1 (reference):** 3.2197 docs/s, spread 0.46%; vector max |Δ| run a vs run b (determinism reference): 0.0 over 7,457 chunks.

**Correctness first, then speed:**

| shape | text chunks identical to vars=1 | embedding max |Δ| vs vars=1 (run a; run b) | mean docs/s | spread | Δ vs vars=1 | threshold | gate |
|---|---|---|---|---|---|---|---|
| vars=2 | yes | 1.08e-07 over 7,457 chunks; 1.08e-07 over 7,457 chunks | 4.3304 | 0.28% | +34.49% | 0.82% | FIRED |
| vars=4 | yes | 1.15e-07 over 7,457 chunks; 1.15e-07 over 7,457 chunks | 5.1499 | 0.19% | +59.95% | 0.82% | FIRED |

**G_smoke_C:** fired ['2', '4'], winner 4 (recomputed; agrees with the chain's record: yes).

**Full run:** vars=4 6.0095 vs p3a_rr_full 6.2969 docs/s = -4.56% (readable against 0.82%); chunk lists identical on 9,886 documents ok in both, differ 0, lost 0.

Correctness held at every shape: text chunks identical to vars=1 on every shared document, embedding vectors within about 1.1e-7 of vars=1 (vars=1 against itself: 0.0). The smoke gate fired for vars=2 (+34.5%) and vars=4 (+59.9%); the pre-registered full run of the winner, vars=4, was readably SLOWER than P3-A's vars=1 full leg (-4.56% against 0.82%), with identical chunks on all 9,886 documents and more CPU per document. POST-HOC reading: on the 384 slice both arms leave most of the box idle (the drain that made Ansh rule the P3-A smoke a health gate), so intra-op threads filled idle cores; on the full corpus vars=1 already keeps ~28 of 32 cores busy and extra threads only contend. The hypothesis ('32 single-threaded passes are not the best shape') is therefore true on the slice and false at full scale on this box; the slice-scale bias was not recorded as a known bias in P3-C's pre-registration and is recorded now (register 60), not corrected.

## P3-D — the parser rerun (P2-C amended; rr:p3-pdfium)

**Build (p3d_build.json):** rr:p3-pdfium `sha256:b81af529c79a` FROM rr:p1-tikafix; in-image check (engine Python): ok=True, pypdfium2 5.13.0, 1 page(s) / 10,314 characters, node flags {'HYBRID': False, 'STUB': None} / {'HYBRID': True, 'STUB': None}, rc 0 → **G_build_D PASS**.

**G_node_D:** hybrid: PASS (docs 36, text 36, fallback 0, errors 0); pure: PASS (docs 36, text 36, fallback 0, errors 0).

### Correctness first (384 slice)

| variant_run | documents | empty (Tika) | empty (variant) | variant empty where Tika recovers | named | variant recovers where Tika empty | char ratio p5 / p50 / p95 | Dice min / p5 / p50 |
|---|---|---|---|---|---|---|---|---|
| hybrid_a | 384 | 2 | 2 | 0 | — | 0 | 0.902 / 1.009 / 1.032 | 0.094 / 0.826 / 0.968 |
| hybrid_b | 384 | 2 | 2 | 0 | — | 0 | 0.902 / 1.009 / 1.032 | 0.094 / 0.826 / 0.968 |
| pure_a | 384 | 2 | 2 | 0 | — | 0 | 0.902 / 1.009 / 1.032 | 0.094 / 0.826 / 0.968 |
| pure_b | 384 | 2 | 2 | 0 | — | 0 | 0.902 / 1.009 / 1.032 | 0.094 / 0.826 / 0.968 |

### The eleven at C=1 — p50 parse bracket per leg

| leg | of the eleven with all stamps | p50 parse bracket (s) | not ok |
|---|---|---|---|
| p3d_s_fix_a | 11 | 0.300 | — |
| p3d_s_fix_b | 11 | 0.304 | — |
| p3d_s_hyb_a | 11 | 0.270 | — |
| p3d_s_hyb_b | 11 | 0.279 | — |
| p3d_s_pure_a | 11 | 0.273 | — |
| p3d_s_pure_b | 11 | 0.271 | — |

**G_smoke_D:** fired variants ['hybrid', 'pure'] (recomputed; agrees with the chain's record: yes).

### Speed, 384 slice ABAB (typical documents; ungated)

| leg | span docs/s | excl. eleven docs/s | ok/rows | CPU-s/doc | service cores | utilisation (of 32) | idle cores | idle spin cores | sampled memory peak | steal, MHz |
|---|---|---|---|---|---|---|---|---|---|---|
| p3d_fix_a | 3.2282 | 3.2282 | 382/384 | 4.074 | 13.130 | 41.0% | 18.759 | 1.219 | 18,721 MB | steal 0.00%, 2816.4 MHz |
| p3d_hyb_a | 3.9538 | 3.9538 | 382/384 | 3.282 | 12.949 | 40.5% | 18.870 | 1.232 | 16,778 MB | steal 0.00%, 2842.4 MHz |
| p3d_pure_a | 3.9291 | 3.9291 | 382/384 | 3.269 | 12.820 | 40.1% | 19.049 | 1.234 | 16,653 MB | steal 0.00%, 2834.8 MHz |
| p3d_fix_b | 3.2285 | 3.2285 | 382/384 | 4.062 | 13.096 | 40.9% | 18.818 | 1.234 | 21,103 MB | steal 0.00%, 2813.3 MHz |
| p3d_hyb_b | 3.9331 | 3.9331 | 382/384 | 3.272 | 12.845 | 40.1% | 19.032 | 1.231 | 16,656 MB | steal 0.01%, 2850.3 MHz |
| p3d_pure_b | 3.9000 | 3.9000 | 382/384 | 3.304 | 12.859 | 40.2% | 19.033 | 1.226 | 16,182 MB | steal 0.01%, 2849.6 MHz |

- hybrid vs fixed Tika: 3.2283 → 3.9434 docs/s = +22.15% against 0.82% → readable; parse share fixed ['5.8%', '5.8%'] vs hybrid ['15.0%', '16.1%'].
- pure vs fixed Tika: 3.2283 → 3.9145 docs/s = +21.25% against 0.82% → readable; parse share fixed ['5.8%', '5.8%'] vs pure ['15.7%', '15.2%'].

- **hybrid full correctness vs p3a_rr_full:** empty Tika 89 vs hybrid 89; hybrid empty where Tika recovers 0 (none) → **ADOPTABLE**; speed 6.2969 → 6.9513 docs/s = +10.39%.
- **pure full correctness vs p3a_rr_full:** empty Tika 89 vs pure 94; pure empty where Tika recovers 5 (004_004306.pdf, 008_008724.pdf, 009_009802.pdf, 018_018542.pdf, 037_037919.pdf) → **NOT ADOPTABLE**; speed 6.2969 → 6.9511 docs/s = +10.39%.

**P3-D verdict (pre-registered): 'a native parser gains little' is NOT SUPPORTED.** Correctness first: on the 384 slice neither variant is empty on any document fixed Tika extracts (both are empty only on Tika's own two empties), so both pass the pre-registered coverage gate; but their text is not Tika's (char ratio p5 about 0.90, Dice p5 about 0.83, one document near-disjoint), and they produce 12.2% FEWER CHUNKS (6,550 vs 7,457). POST-HOC: their +21-22% docs/s on the slice comes largely from that smaller embedding workload (CPU per document 4.07 -> 3.28 s), not from faster parsing — the parse bracket is SLOWER at C=32 (the prototype serialises PDFium behind one process-wide lock). At full scale (9,975), against P3-A's fixed-Tika full leg: HYBRID is ADOPTABLE (empty on exactly Tika's 89 documents, 0 lost) and 10.39% faster, readable and beyond the pre-registered +5.83% 'little' bar, so by the pre-registered rule the hypothesis 'a native parser gains little' is NOT SUPPORTED. PURE is NOT ADOPTABLE: empty on 5 documents Tika recovers (the five H6 predicted, all five also empty on LlamaIndex's pypdf path). POST-HOC, beside the rule and not replacing it: HYBRID's full-corpus output has 10.9% fewer chunks than Tika's (186,931 vs 209,797), and its text differs on a tail of documents (Dice below 0.5 on 115 of 9,886, below 0.1 on 34; which extraction is right was not judged). So HYBRID's gain is largely a smaller, different output, not a faster parser; adopting it is a product decision about text quality, not a speed result.

## P3-E — drafts (laptop; not filed)

- **Cross-document embedding batching design:** [P3E_DESIGN_CROSS_DOCUMENT_BATCHING.md](P3E_DESIGN_CROSS_DOCUMENT_BATCHING.md). Where the batch forms (Embedding.encodeChunks, a leader thread in the one Embedding object), its bound (B_max chunks, T_wait ms), per-request futures for routing, the correctness gate (text identity, vector tolerance, a routing null control), and the in-bounds proof. P3-C's full-scale result means the forward-concurrency half must be re-tuned at full scale, not on the slice.
- **Ticket draft, noDebug by default + MALLOC_ARENA_MAX=2:** [P3E_TICKET_DRAFT_NODEBUG_MALLOC.md](P3E_TICKET_DRAFT_NODEBUG_MALLOC.md). noDebug by default and MALLOC_ARENA_MAX=2 in the engine image; evidence: identical output on 16/16 videos and anonymous memory roughly halved in P2-B; the speed gain is NOT readable (pair b +3.42% inside ~5% spreads) and the draft says so; the debugger is not the source of the idle burn.

## Amendments to the pre-registration

- none

## Session

Box boot ids across every P3 leg in this report: ['3a2dc046-fb93-4b15-8616-7a3b64fcbdb0'] (one session).

## Register entries added

- 58 — the container that could not write where it was told to (li:video runs as uid 10002; caught by the gate controls before any leg)
- 59 — a rule that did not encode its own hypothesis (P3-B (1))
- 60 — a smoke slice's idle cores read as a shape's gain (P3-C: +60% on the 384 slice, -4.56% at full scale)

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (P3-A, P3-B, P3-C, P3-D, P3-E, every gate threshold and the gate-controls list); no amendment.
- **2. EVIDENCE:** every figure in this report is computed by working/scripts/p3_report.py from analysis_p3docs.json and analysis_p3b.json (produced by the committed analysers from the raw leg directories beside them), the gate-control records, the gate records in gates/, master_done.json and p3d_build.json. Large files stay in S3: every texts.jsonl.gz (the 384-slice and full-run chunk texts) and every vecs.jsonl.gz (P3-C's embedding vectors); the P3-B frames stay on the box (their sha256 manifest is committed).
- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json run 1: 20 of 24, the failure caught li:video's non-root user; gate_controls_run2.json: 24 of 24); the blind recomputation's planted figures had to be caught (P3_BLIND_VERIFICATION.json).
- **4. REGISTER:** 3 (one box session for every P3 leg); 34 (P3-B (2) left without a matching reading on its own terms); 48 (blind recomputation); 49 (the read-backs and the maps inspection run outside the measured windows); 54, 55 (hard gates; the sampler gated after every chain's first leg; DEGRADED-with-all-rows kept as a result); 56-57 (checks tested whole: the gate-controls rule); 58, 59, 60 (added).
- **5. NOT VERIFIED:** whether one token BEATS LlamaIndex's optimum at full scale (n = 1 per arm, inside LlamaIndex's spread); what inside the engine slows the forward at 16 videos in flight (P3-B post-hoc points there; not measured); why the bare RocketRide-image process keeps 5 cores busy in a T=4 forward; the P3-D variants' text quality beyond coverage (they differ from Tika's text and chunk differently); the drafts' proposals (source only).
- **6. GATES:** every P3 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls ran before launch; the master launched once and ran every stage in order with hard gates; protected image ids read back unchanged; the box is stopped with box.sh stop at the end and its state read back.

