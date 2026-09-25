# P5 — a single inference thread for the detect node; the CTO brief draft

Campaign `parity_p5_20260925T141647Z`, branch feat/parity-p5 (from feat/parity-p4 264872d7). Generated 2026-09-25T17:23:32Z from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison is interleaved ABAB (register 62); the canary explains drift and adjusts nothing.

## Summary

- Correctness: rr:p5-infer's output is identical to stock rr:patched-video on 16/16 videos in all 6 gate comparisons (K=16 and K=1, both rounds, and against P4's committed stock K=1 leg).
- S1 (fix works): DOES NOT HOLD (pooled); round 1 does not, round 2 does not. With 16 videos in flight the P5 forward is +6.19% against one in flight (within 2.47% is the rule), and P5 runs 4.644 frames/s against stock's 2.665 (+74.22%; beyond 3.93% is the rule).
- S2 (parity >= 0.95): HOLDS (pooled); round 1 holds, round 2 holds. P5 at 16 in flight / LlamaIndex at 16 in flight = 1.373 pooled (1.349 in round 1, 1.397 in round 2); LlamaIndex ran 3.382 frames/s.
- P5-B: NOT RUN — its gate did not fire.
- Drift: the canary moved AGAINST the cells (canary +2.53% from round 1 to round 2; P5-A cells' median -1.59%).
- The CTO brief draft is below; it is not sent, posted or filed.

## Step 0

- sso: checked 2026-09-25T14:02Z: role credentials valid to 19:31:40Z; neither expired nor within 2 h of expiry -> no login. The 7.5 h budget will outlast the credentials; Ansh is asked to re-login before a leg that would outlast them.
- autoland_self_test: 71 pass, 0 fail
- origin: feat/parity-p4 on origin = 264872d7; feat/parity-p5 created from it
- register: the drafted steady-phase entry added as register entry 63 (Ansh's ruling: steady-phase docs/s is the pre-registered metric for docs throughput smoke gates from P5 on; span still reported)

## Gates

| gate | rule | measured | outcome |
|---|---|---|---|
| G_build_A (rr:p5-infer) | node identity, compiles, one frame end to end on the inference thread, same as direct, ONE LWDETR | identity True; ran on detect-infer; same as direct True; LWDETR 1; image sha256:b42c03b69f17 | PASS |
| G_d0 (every leg and block) | see the pre-registration | p5a_li16_1: CLEAN; p5a_li16_2: CLEAN; p5a_p5k16_1: CLEAN; p5a_p5k16_2: CLEAN; p5a_p5k1_1: CLEAN; p5a_p5k1_2: CLEAN; p5a_stock16_1: CLEAN; p5a_stock16_2: CLEAN | ALL CLEAN |
| G_cell (every leg and block) | see the pre-registration | p5a_li16_1: PASS; p5a_li16_2: PASS; p5a_p5k16_1: PASS; p5a_p5k16_2: PASS; p5a_p5k1_1: PASS; p5a_p5k1_2: PASS; p5a_stock16_1: PASS; p5a_stock16_2: PASS | ALL PASS |
| G_canary (every canary) | the canary ran on exactly v00_EN2001a's 239 manifest frames, one model, T=4 | p5c_can_1: PASS; p5c_can_2: PASS; p5ctl_canary: PASS | PASS |
| G_memstat (first measured leg) | memstat.jsonl ≥ 1 row | p5a_stock16_1: 1,335 rows | PASS |
| G_correct_A1 (HARD, after round 1) | rr:p5-infer output identical to stock on 16/16 at K=16 and K=1 | p5a_p5k16_1 vs p5a_stock16_1: identical, 16 videos; p5a_p5k1_1 vs p5a_stock16_1: identical, 16 videos; p5a_p5k1_1 vs p4a_rr1_1: identical, 16 videos | PASS |
| G_correct_A (all pairs, recorded) | rr:p5-infer output identical to stock on 16/16 at K=16 and K=1 | p5a_p5k16_1 vs p5a_stock16_1: identical, 16 videos; p5a_p5k1_1 vs p5a_stock16_1: identical, 16 videos; p5a_p5k16_2 vs p5a_stock16_2: identical, 16 videos; p5a_p5k1_2 vs p5a_stock16_2: identical, 16 videos | PASS |
| G_smoke_P5B | correctness AND S1 AND S2 (pooled) | S1 DOES NOT HOLD (pooled); round 1 does not, round 2 does not; S2 HOLDS (pooled); round 1 holds, round 2 holds | NOT FIRED |
| protected image ids | rr:patched, rr:patched-video unchanged: before and after the build, at run start and end | rr:patched sha256:073b43d8b5f9 rr:patched-video sha256:b7f51acc9533 | UNCHANGED |
| budget | 7.5 h from the run stage's first leg | run start 2026-09-25T14:34:08Z; deadline 2026-09-25T22:04:10Z; chain done 2026-09-25T17:19:06Z | WITHIN |

### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)

**gate_controls.json** (run 1, boot b9a0e24b): 28 of 28 controls as expected → all_pass **True**.

| gate | positive control(s) (must PASS) | null control(s) (must FAIL) |
|---|---|---|
| G_memstat | P4 p4a_rr16_1 → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no memory sampler) → as expected (FAIL (rc 1)) |
| G_d0 rr | P4 p4a_rr16_1 → as expected (PASS (rc 0))<br>the control leg p5ctl_p5 (rr:p5-infer) → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no on-token D0: absence) → as expected (FAIL (rc 2))<br>a copy of p4a_rr16_1 holding MANDATE_VIOLATION.json → as expected (FAIL (rc 1))<br>a copy of p4a_rr16_1 whose post-leg D0 counts TWO LWDETR instances → as expected (FAIL (rc 1)) |
| G_d0 li | P4 p4a_li16_1 → as expected (PASS (rc 0))<br>the control leg p5ctl_li → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (eight LlamaIndex containers) → as expected (FAIL (rc 1)) |
| G_cell stock | the control leg p5ctl_stock → as expected (PASS (rc 0)) | p5ctl_p5 against the STOCK spec (image, stamps) → as expected (FAIL (rc 2))<br>p5ctl_stock against K=1 (two in flight) → as expected (FAIL (rc 1)) |
| G_cell p5 | the control leg p5ctl_p5 → as expected (PASS (rc 0)) | p5ctl_stock against the P5 spec (image, node) → as expected (FAIL (rc 2)) |
| G_cell li | the control leg p5ctl_li → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (no read-back, no image record) → as expected (FAIL (rc 2)) |
| G_canary | the control canary p5ctl_canary → as expected (PASS (rc 0)) | P3 p3b_a_1 (the same bench over all three videos) → as expected (FAIL (rc 1)) |
| G_correct | P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16) → as expected (PASS (rc 0)) | P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16) → as expected (FAIL (rc 1))<br>P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos) → as expected (FAIL (rc 1)) |
| G_smoke_P5B | P5 K=16 cells = P4's stock K=1 legs (no slowdown, faster than stock K=16, above LI) → as expected (PASS (rc 0)) | P5 K=16 cells = P4's ACTIVE legs (the K=16 slowdown kept) → as expected (FAIL (rc 1)) |
| G_build_A | rr:p5-infer (the P5 node loads; one frame end to end on the inference thread; one LWDETR) → as expected (PASS (rc 0)) | rr:patched-video (fails the node-identity check) → as expected (FAIL (rc 1)) |
| G_alone | no container on the box → as expected (PASS (rc 0)) | one created container present → as expected (FAIL (rc 1)) |

## P5-A — single inference thread, smoke (one session, two ABAB rounds, T=4, 16 videos)

### Correctness first

| pair | videos compared | identical |
|---|---|---|
| p5a_p5k16_1 vs p5a_stock16_1 | 16 | yes |
| p5a_p5k1_1 vs p5a_stock16_1 | 16 | yes |
| p5a_p5k1_1 vs P4 p4a_rr1_1 (stock, K=1, committed) | 16 | yes |
| p5a_p5k16_2 vs p5a_stock16_2 | 16 | yes |
| p5a_p5k1_2 vs p5a_stock16_2 | 16 | yes |
| p5a_p5k1_2 vs P4 p4a_rr1_1 (stock, K=1, committed) | 16 | yes |

**CORRECTNESS GATE: PASS.**

Beside:

| comparison | legs | videos | identical |
|---|---|---|---|
| stock k16 run to run | p5a_stock16_1 vs p5a_stock16_2 | 16 | yes |
| p5 k16 run to run | p5a_p5k16_1 vs p5a_p5k16_2 | 16 | yes |
| p5 k1 vs p5 k16 round 1 | p5a_p5k1_1 vs p5a_p5k16_1 | 16 | yes |
| li k16 run to run | p5a_li16_1 vs p5a_li16_2 | 16 | yes |

### Per cell (round 1 / round 2; mean; spread of the two ABAB runs)

| cell | frames/s | forward s/frame F | inference duty | cores busy in the forward | CPU-s/frame | sampled memory peak |
|---|---|---|---|---|---|---|
| RR stock K=16 | 2.613 / 2.718; 2.665 (3.93%) | 0.3703 / 0.3556; 0.3630 (4.04%) | 99.9% / 99.9%; 99.9% (0.00%) | 2.43 / 2.46; 2.44 (1.39%) | 1.398 / 1.357; 1.377 (2.97%) | 7,603 MB / 7,368 MB |
| RR P5 K=16 | 4.587 / 4.701; 4.644 (2.45%) | 0.2092 / 0.2041; 0.2066 (2.47%) | 100.0% / 100.0%; 100.0% (0.00%) | 4.21 / 4.21; 4.21 (0.10%) | 1.214 / 1.187; 1.200 (2.30%) | 5,503 MB / 5,723 MB |
| RR P5 K=1 | 4.280 / 4.307; 4.294 (0.63%) | 0.1953 / 0.1939; 0.1946 (0.75%) | 85.7% / 85.5%; 85.6% (0.21%) | 4.23 / 4.23; 4.23 (0.02%) | 1.212 / 1.203; 1.208 (0.73%) | 1,846 MB / 1,872 MB |
| LlamaIndex K=16 | 3.400 / 3.364; 3.382 (1.07%) | 0.2751 / 0.2778; 0.2764 (0.99%) | 100.0% / 100.0%; 100.0% (0.00%) | 2.77 / 2.74; 2.75 (0.88%) | 0.881 / 0.883; 0.882 (0.17%) | 5,359 MB / 5,358 MB |

### Per leg: forward D1 metric set (seconds), inference duty, queue depth (P5 legs)

| leg | count | mean | sd | min | p50 | p90 | p95 | p99 | max | mean/p50 | inference duty | queue depth mean / p50 / p95 / max | frames/s | steal, MHz open→close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p5a_stock16_1 | 3,203 | 0.3703 | 0.0358 | 0.2450 | 0.3715 | 0.4008 | 0.4087 | 0.5019 | 0.6041 | 0.997 | 99.9% | — | 2.613 | steal 0.005%, 2994→2949 MHz |
| p5a_p5k16_1 | 3,203 | 0.2092 | 0.0486 | 0.1850 | 0.1968 | 0.2127 | 0.2301 | 0.4761 | 0.6957 | 1.063 | 100.0% | 12.79 / 15 / 15 / 15 | 4.587 | steal 0.005%, 3085→2712 MHz |
| p5a_p5k1_1 | 3,203 | 0.1953 | 0.0089 | 0.1843 | 0.1913 | 0.2078 | 0.2129 | 0.2209 | 0.2612 | 1.021 | 85.7% | 1.00 / 1 / 1 / 1 | 4.280 | steal 0.005%, 3099→2752 MHz |
| p5a_li16_1 | 3,203 | 0.2751 | 0.0849 | 0.1832 | 0.2881 | 0.3744 | 0.3798 | 0.3887 | 0.6694 | 0.955 | 100.0% | — | 3.400 | steal 0.005%, 2838→2631 MHz |
| p5a_stock16_2 | 3,203 | 0.3556 | 0.0366 | 0.2339 | 0.3605 | 0.3869 | 0.4003 | 0.4661 | 0.6536 | 0.986 | 99.9% | — | 2.718 | steal 0.005%, 2894→2692 MHz |
| p5a_p5k16_2 | 3,203 | 0.2041 | 0.0500 | 0.1851 | 0.1909 | 0.2082 | 0.2289 | 0.4687 | 0.5765 | 1.069 | 100.0% | 12.76 / 15 / 15 / 15 | 4.701 | steal 0.005%, 3141→2695 MHz |
| p5a_p5k1_2 | 3,203 | 0.1939 | 0.0057 | 0.1844 | 0.1922 | 0.2022 | 0.2042 | 0.2085 | 0.2387 | 1.009 | 85.5% | 1.00 / 1 / 1 / 1 | 4.307 | steal 0.004%, 2993→2681 MHz |
| p5a_li16_2 | 3,203 | 0.2778 | 0.0882 | 0.1811 | 0.2921 | 0.3790 | 0.3925 | 0.4096 | 0.6248 | 0.951 | 100.0% | — | 3.364 | steal 0.005%, 2895→2705 MHz |

Queue depth histograms (depth: frames): p5a_p5k16_1: 1: 13, 2: 11, 3: 23, 4: 32, 5: 33, 6: 25, 7: 184, 8: 83, 9: 10, 10: 567, 11: 9, 12: 10, 13: 134, 14: 281, 15: 1,788; p5a_p5k1_1: 1: 3,203; p5a_p5k16_2: 1: 14, 2: 8, 3: 26, 4: 33, 5: 36, 6: 24, 7: 186, 8: 81, 9: 11, 10: 570, 11: 17, 12: 15, 13: 134, 14: 271, 15: 1,777; p5a_p5k1_2: 1: 3,203.

| canary (rr:patched-video bare, v00_EN2001a, T=4) | frames | mean forward s | p50 | p95 |
|---|---|---|---|---|
| p5c_can_1 | 239 | 0.1852 | 0.1855 | 0.1898 |
| p5c_can_2 | 239 | 0.1899 | 0.1881 | 0.1966 |

### Readings (pre-registered), per round and pooled

|  | F(P5 K=16)/F(P5 K=1) − 1 | within 2.47% | fps(P5 K=16)/fps(stock K=16) − 1 | beyond 3.93% | S1 FIX WORKS | fps(P5 K=16)/fps(LI K=16) | S2 PARITY (≥ 0.95) |
|---|---|---|---|---|---|---|---|
| round 1 | +7.10% | no | +75.54% | yes | does not hold | 1.349 | HOLDS |
| round 2 | +5.27% | no | +72.95% | yes | does not hold | 1.397 | HOLDS |
| pooled | +6.19% | no | +74.22% | yes | does not hold | 1.373 | HOLDS |

**S1: DOES NOT HOLD (pooled); round 1 does not, round 2 does not. S2: HOLDS (pooled); round 1 holds, round 2 holds.**

Stated plainly, per round and pooled. S1: round 1 does not hold (forward +7.10%, frames/s vs stock +75.54%); round 2 does not hold (forward +5.27%, frames/s vs stock +72.95%); pooled DOES NOT HOLD. S2: round 1 1.349, round 2 1.397, pooled 1.373 against 0.95 — HOLDS pooled. POST-HOC, not pre-registered (from analysis_p5a.json). (i) Against the same one-video forward, stock's forward at 16 in flight is +86.53% and P5's +6.19%: P5 removes 92.8% of the slowdown, not all of it, and the residual is beyond this session's replicate spread, which is why S1 does not hold. (ii) The inference thread is busy for 99.97% of the window at 16 in flight and keeps 4.21 cores busy during a forward (stock at 16: 2.44; P5 at one in flight: 4.23); the queue's median depth is 15 and 15 in the two runs — with 16 callers and one frame in the forward, that is every other caller's frame waiting: the one thread is the bottleneck. (iii) P5 at 16 in flight runs +8.15% frames/s over P5 at one in flight (decoding overlaps the forward). (iv) Cost: CPU-s per frame 1.200 vs stock 1.377 (-12.84%) and LlamaIndex 0.882; sampled memory peak 5,613 MB vs stock 7,485 MB and LlamaIndex 5,359 MB (means of two runs). (v) The residual sits in the tail: the median forward (mean of the two runs' p50) is 193.9 ms at 16 in flight against 191.8 ms at one (+1.10%), while the p99 is 476 and 469 ms against 221 and 209 ms. What the residual forward penalty at 16 in flight is made of was not measured.

## P5-B — 168 videos, block-interleaved

NOT RUN: the P5-B gate (correctness AND S1 AND S2, pooled) did not fire, so the 168-video confirmation was not started.

## P5-C (2) — canary drift note

|  | value |
|---|---|
| canary forward, round 1 / round 2 (s) | 0.1852 / 0.1899 |
| canary change round 2 / round 1 − 1 | +2.53% |
| P5-A cells' forward change round 2 / round 1 − 1 | stock_k16 -3.96%; p5_k16 -2.44%; p5_k1 -0.75%; li_k16 +1.00% |
| their median | -1.59% |
| P4's round drift (forward, round 2 / round 1 − 1; no canary then) | rr_k1 +7.34%; rr_k16 +3.93%; li_k1 +21.96%; li_k16 +10.91%; rr_k16_active +17.97% |

**Reading (rule fixed in the pre-registration): the canary moved AGAINST the cells.** No figure is adjusted.

The canary is the same bare microbenchmark every round, alone, in rr:patched-video; it measures the box, not either engine. P4, which had no canary, drifted by +3.93% to +21.96% between its rounds. No figure in this report is adjusted by the canary.

## P5-C (1) — CTO brief draft (not sent, posted or filed)

Embedded from `P5_CTO_BRIEF_DRAFT.md` (generated by `working/scripts/p5_brief.py`).

> # DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)
>
> Figures cite the P4 facts sheet row [F..] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md, each row naming its artifact and key) or a P5 analysis file and key.
>
> ## Documents
>
> - **Matches, not beats.** One RocketRide token runs 6.2969 [F01] docs/s on the full corpus against LlamaIndex's 24-worker optimum at 5.9046 [F02]: a ratio of 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread. The steady-phase ABAB ratios on the 384 slice agree across two sessions: 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio; the same artifact as F27, not a facts-sheet row].
> - **It depends on an unshipped fix.** Stock RocketRide runs 2.3454 [F15] docs/s; the Tika wrapper fix takes it to 5.3441 [F17] (+127.85% [F18]), with 0 of 9,885 [F20] chunk lists changed. The fix measured is a one-byte patch that turns inline-image extraction off for every pipeline, which breaks image pipelines; the shippable form is the source change in the wrapper ticket draft (parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12).
> - **Costs.** CPU per document: RocketRide 4.442 [F05] s vs LlamaIndex 3.881 [F06] s. Sampled memory peak: 21,826 [F11] MB vs 18,069 [F12] MB. Idle spin with nothing submitted: 1.234 [F09] cores vs 0.026 [F10].
> - **Out of the box** (stock image): 2.3454 [F15] docs/s at 7.706 [F16] CPU-s per document; no same-session LlamaIndex run, so no ratio is formed.
>
> ## Video
>
> - **The gap.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one RocketRide token at 16 videos in flight (T=4). Out of the box RocketRide runs 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame.
> - **The mechanism (P4).** From one video in flight to sixteen RocketRide's forward pass slows x1.867 [F58], LlamaIndex's x1.403 [F59]; at one video in flight RocketRide is the faster engine (4.341 [F43] vs 2.980 [F49] frames/s). RocketRide's detector lock is taken per frame by up to 16 caller threads; OMP_WAIT_POLICY=ACTIVE did not help (closure -0.115 [F60]).
> - **P5 (single inference thread; a benchmark prototype, not shipped), output identical to stock on 16/16 videos at K=1 and K=16** [analysis_p5a.json correctness.gate_pass]: at 16 videos in flight it runs 4.644 frames/s [cells.p5_k16.frames_per_s.mean] against stock 2.665 [cells.stock_k16.frames_per_s.mean] (+74.2% [readings.S1.pooled.fps_p5k16_over_stock_k16_minus_1]) and LlamaIndex 3.382 [cells.li_k16.frames_per_s.mean]; RocketRide/LlamaIndex 1.373 [readings.S2.pooled.fps_p5k16_over_li_k16]. Its forward at 16 in flight is +6.2% against one in flight [readings.S1.pooled.F_p5k16_over_p5k1_minus_1]. S1 (fix works): DOES NOT HOLD (pooled); round 1 does not, round 2 does not; S2 (parity >= 0.95): HOLDS (pooled); round 1 holds, round 2 holds.
> - **P5-B 168-video confirmation: NOT RUN** — its pre-registered gate NOT FIRED [gates/G_smoke_P5B.json outcome]: S1 does not hold.
>
> ## What is not claimed
>
> - That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).
> - Any figure from the unshipped fixes as shipped behaviour.
> - Any cross-session ratio.

## NOT RUN

- P5-B (the 168-video block-interleaved confirmation): its pre-registered gate G_smoke_P5B did not fire — S1 does not hold (the P5 forward at 16 videos in flight is beyond this session's replicate spread of its one-video forward), although S2 holds and the correctness gate passed

## Methodology register

- 63 — steady-phase docs/s is the smoke metric for docs throughput gates (Ansh's ruling, added at Step 0)
- 64 — an 'equal within the spread' clause that tightens as the session gets quieter (S1's forward clause; the verdict as written stands)

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (P5-A hypothesis, build, the in-image check, the hard correctness gate, S1/S2 per round and pooled, the P5-B gate and block design with its container choice, the P5-C rules including the drift rule), committed at 504cf101; no amendment.
- **2. EVIDENCE:** every figure is computed by working/scripts/p5_report.py and p5_write_specs.py from analysis_p5a.json (p5_analyse_a.py over the raw smoke legs), (P5-B did not run, so there is no analysis_p5b.json), analysis_p5_drift.json, the build record, the gate-control record, the gate records and the chain records; the brief from p4_facts.json and the P5 analysis files.
- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json, real control legs for every G_cell flavour, the in-image check in both images); the laptop worker test has a mis-routing null control; the blind recomputation's planted figures had to be caught.
- **4. REGISTER:** 3 (one session); 48 (blind recomputation); 54, 55 (hard gates, the sampler gated after the first leg); 56-58 (gates tested whole; containers' users); 59 (reading clauses against the hypothesis); 61 (a gate reads the record its writer finalises last: D0 from the export); 62 (ABAB rounds, the canary); 63 (the steady-phase metric).
- **5. NOT VERIFIED:** whether P5's gain holds on other videos, other T or other hardware; why the box drifts between rounds (the canary describes it, nothing explains it); the P5 node beyond this benchmark's pipeline (source only, not a RocketRide change); the CTO brief is a draft.
- **6. GATES:** every P5 landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg; protected ids read back before and after the build and at stage start and end; the box stopped with box.sh stop and its state read back.

