# P4 — video concurrency; the smoke metric, the parser close-out, the P5 design and the facts sheet

Campaign `parity_p4_20260925T092942Z`, branch feat/parity-p4 (from feat/parity-p3 f9f1efe7). Generated 2026-09-25T13:40:52Z from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every P4-A comparison is ABAB inside one box session; figures from earlier sessions appear only as context and are labelled so.

**Blind recomputation (P4_BLIND_VERIFICATION.json):** PASS (round 2) — round 1 BLOCKED — all 4 plants caught; real trace defects in the facts sheet (F23 showed its key negated, F24 showed its key minus one, F15's caveat quoted a figure with no key), one undefined beside-threshold (P4-B (1) check 2), one label (the budget row's 'first leg' was the stage start); fixed; round 2 re-verified the changed sections with new plants — both plants caught, no other mismatch. 661 figures checked in round 1 by 4 verifiers, 211 in round 2 by 2.

## Summary

- Correctness: every output comparison is identical on 16/16 videos (ACTIVE vs K=16; K=1 vs K=16 on both arms; run to run).
- P4-A R1 SUPPORTED: RocketRide's forward per frame degrades x1.867 from one video in flight to sixteen, LlamaIndex's x1.403; at one video in flight RocketRide is the faster arm (4.341 vs 2.980 frames/s). The per-instance video gap is a concurrency effect.
- P4-A R3 NOT WAKE-UP: OMP_WAIT_POLICY=ACTIVE closes -0.115 of RocketRide's degradation (the rule needs 0.5) and costs +72.47% CPU-s per frame. The P5 candidate is a single inference thread.
- P4-B (1) steady-phase docs/s as the smoke metric: VALIDATES (post-hoc validation).
- P4-B (2) parser close-out: HYBRID's +10.39% docs/s is all fewer chunks; keep fixed Tika; the parser track is closed.
- P4-B (3) P5 design drafted (not filed). P4-B (4) facts sheet written. NOT RUN: nothing.

## Step 0 and the recorded correction

- checked 2026-09-25T09:21Z: role credentials valid (refreshed from the 03:46Z approval; the SSO session has lasted ~15.5 h before, so it is expected to hold until ~19:15Z); not expired and not within 2 h of expiry -> no login
- autoland self-test: 71 pass, 0 fail
- feat/parity-p3 on origin = f9f1efe7 (ls-remote); feat/parity-p4 created from it
- **Recorded correction (the advisor's error, recorded as instructed):** P3-B's 'ruled out beforehand' rested on P0's 'K=1 no faster than K=16', which was measured at the engine's default of 16 torch threads (batchsize_video_run.sh:122, the batch-size campaign's default posture: --rr-threads-env unset), not at T=4. It has no bearing on T=4 and is withdrawn as a premise. P4-A measures K=1 and K=16 at T=4 in one session.

## Gates

| gate | rule | measured | outcome |
|---|---|---|---|
| G_d0 (every leg) | RR: export p0 d0_pre, d0_post, mandate clean; LI: one container, one process, --workers 1 | p4a_rr16_1: CLEAN; p4a_li16_1: CLEAN; p4a_rr1_1: CLEAN; p4a_li1_1: CLEAN; p4a_act_1: CLEAN; p4a_rr16_2: CLEAN; p4a_li16_2: CLEAN; p4a_rr1_2: CLEAN; p4a_li1_2: CLEAN; p4a_act_2: CLEAN | CLEAN |
| G_cell (every leg) | read-back T=4, OMP_WAIT_POLICY as declared, 16 videos, max in flight = K, stamps on every measured frame | p4a_rr16_1: PASS; p4a_li16_1: PASS; p4a_rr1_1: PASS; p4a_li1_1: PASS; p4a_act_1: PASS; p4a_rr16_2: PASS; p4a_li16_2: PASS; p4a_rr1_2: PASS; p4a_li1_2: PASS; p4a_act_2: PASS | PASS |
| G_memstat (first leg) | memstat.jsonl ≥ 1 row | p4a_rr16_1: 1,286 rows | PASS |
| G_correct_active (end of chain) | every (ACTIVE, RR K=16) pair identical on 16/16 videos | p4a_act_1 vs p4a_rr16_1: identical, 16 videos; p4a_act_1 vs p4a_rr16_2: identical, 16 videos; p4a_act_2 vs p4a_rr16_1: identical, 16 videos; p4a_act_2 vs p4a_rr16_2: identical, 16 videos | PASS |
| protected image ids | rr:patched, rr:patched-video unchanged start → end | rr:patched sha256:073b43d8b5f9 rr:patched-video sha256:b7f51acc9533 | UNCHANGED |
| budget | 5 h from the first leg (deadline set as the chain enters its first leg) | run stage start 2026-09-25T09:43:27Z; deadline 2026-09-25T14:43:28Z; chain done 2026-09-25T13:27:07Z | WITHIN |

### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)

**gate_controls.json** (run 1, boot ff48c148): 25 of 25 controls as expected → all_pass **True**.

| gate | positive control(s) (must PASS) | null control(s) (must FAIL) |
|---|---|---|
| G_memstat | P2 p2b_rr_base_a → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no memory sampler) → as expected (FAIL (rc 1)) |
| G_d0 rr | P2 p2b_rr_base_a → as expected (PASS (rc 0))<br>the control leg p4ctl_active (its own on-token D0) → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no on-token D0: absence) → as expected (FAIL (rc 2))<br>a copy of p2b_rr_base_a holding MANDATE_VIOLATION.json → as expected (FAIL (rc 1))<br>a copy of p2b_rr_base_a whose export p0 mandate says violation → as expected (FAIL (rc 1)) |
| G_d0 li | P2 p2b_li_a (one container, one worker) → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (eight LlamaIndex containers) → as expected (FAIL (rc 1)) |
| G_cell rr K=16 T=4 unset n=16 | P2 p2b_rr_base_a → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no read-back, default threads) → as expected (FAIL (rc 2))<br>the control leg p4ctl_active (ACTIVE, K=2, n=2) → as expected (FAIL (rc 1)) |
| G_cell rr K=1 T=4 unset n=3 | P3 p3b_c_1 (K=1, T=4, stamped) → as expected (PASS (rc 0)) | P2 p2b_rr_base_a (K=16, n=16) → as expected (FAIL (rc 1)) |
| G_cell li K=16 T=4 unset n=16 | P2 p2b_li_a → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (no read-back) → as expected (FAIL (rc 2)) |
| G_cell li K=1 T=4 unset n=3 | P3 p3b_d_1 → as expected (PASS (rc 0)) | P2 p2b_li_a (K=16, n=16) → as expected (FAIL (rc 1)) |
| G_cell rr ACTIVE (control-leg spec K=2 T=4 n=2) | the control leg p4ctl_active → as expected (PASS (rc 0)) | — |
| G_cell rr ACTIVE K=16 T=4 n=16 | — | P2 p2b_rr_base_a (OMP_WAIT_POLICY absent) → as expected (FAIL (rc 1)) |
| G_correct_active | P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16) → as expected (PASS (rc 0)) | P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16) → as expected (FAIL (rc 1))<br>P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos) → as expected (FAIL (rc 1)) |
| G_alone | no container on the box → as expected (PASS (rc 0)) | one created container present → as expected (FAIL (rc 1)) |

## P4-A — video concurrency (one session, ABAB, T=4, 16 videos, every leg alone)

### Correctness first

| ACTIVE vs RR K=16 | videos compared | identical | chunk hash differs | frame scores differ |
|---|---|---|---|---|
| p4a_act_1 vs p4a_rr16_1 | 16 | yes | none | none |
| p4a_act_1 vs p4a_rr16_2 | 16 | yes | none | none |
| p4a_act_2 vs p4a_rr16_1 | 16 | yes | none | none |
| p4a_act_2 vs p4a_rr16_2 | 16 | yes | none | none |

**CORRECTNESS GATE (ACTIVE vs RR K=16, 16/16): PASS.**

Beside (context: K should not change output):

| comparison | legs | videos | identical |
|---|---|---|---|
| rr k16 run to run | p4a_rr16_1 vs p4a_rr16_2 | 16 | yes |
| rr k1 run to run | p4a_rr1_1 vs p4a_rr1_2 | 16 | yes |
| rr k1 vs rr k16 | p4a_rr1_1 vs p4a_rr16_1 | 16 | yes |
| rr k1 vs rr k16 | p4a_rr1_1 vs p4a_rr16_2 | 16 | yes |
| rr k1 vs rr k16 | p4a_rr1_2 vs p4a_rr16_1 | 16 | yes |
| rr k1 vs rr k16 | p4a_rr1_2 vs p4a_rr16_2 | 16 | yes |
| li k16 run to run | p4a_li16_1 vs p4a_li16_2 | 16 | yes |
| li k1 run to run | p4a_li1_1 vs p4a_li1_2 | 16 | yes |
| li k1 vs li k16 | p4a_li1_1 vs p4a_li16_1 | 16 | yes |
| li k1 vs li k16 | p4a_li1_1 vs p4a_li16_2 | 16 | yes |
| li k1 vs li k16 | p4a_li1_2 vs p4a_li16_1 | 16 | yes |
| li k1 vs li k16 | p4a_li1_2 vs p4a_li16_2 | 16 | yes |
| active run to run | p4a_act_1 vs p4a_act_2 | 16 | yes |

### Per cell (mean of two legs; spread = |a − b| / mean)

| cell | frames/s (spread) | forward s/frame F (spread) | forward p50 / p95 s | lock duty | cores busy in the forward | CPU-s/frame | caller switch rate | caller threads (per leg) |
|---|---|---|---|---|---|---|---|---|
| RocketRide K=1 | 4.341 (6.55%) | 0.1940 (7.08%) | 0.1910 / 0.2225 | 86.1% | 4.23 | 1.197 | 0.005 | 16/16 |
| RocketRide K=16 | 2.671 (3.77%) | 0.3622 (3.85%) | 0.3648 / 0.4072 | 99.9% | 2.44 | 1.371 | 0.997 | 16/16 |
| LlamaIndex K=1 | 2.980 (15.19%) | 0.2027 (19.79%) | 0.2107 / 0.2245 | 63.0% | 4.00 | 0.929 | 0.000 | 1/1 |
| LlamaIndex K=16 | 3.299 (9.88%) | 0.2844 (10.35%) | 0.2820 / 0.3976 | 100.0% | 2.79 | 0.919 | 0.005 | 16/16 |
| RocketRide K=16, OMP_WAIT_POLICY=ACTIVE | 2.554 (16.15%) | 0.3816 (16.49%) | 0.3887 / 0.4366 | 99.9% | 4.74 | 2.365 | 0.997 | 16/16 |

### Per leg

| leg | frames/s | frames | F s | lock duty | cores in fwd | caller on-CPU | CPU-s/frame | switch rate | sampled mem peak | torch T / OMP_WAIT_POLICY | steal, MHz open→close |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p4a_rr16_1 | 2.721 | 3,203 | 0.3552 | 99.9% | 2.43 | 0.594 | 1.345 | 0.997 | 7,432 MB | 4 / ABSENT | steal 0.000%, 2638→2754 MHz |
| p4a_li16_1 | 3.462 | 3,203 | 0.2697 | 99.9% | 2.73 | 0.729 | 0.858 | 0.005 | 6,014 MB | 4 / ABSENT | steal 0.000%, 2603→2671 MHz |
| p4a_rr1_1 | 4.483 | 3,203 | 0.1872 | 85.8% | 4.23 | 0.999 | 1.158 | 0.005 | 2,286 MB | 4 / ABSENT | steal 0.000%, 2687→2738 MHz |
| p4a_li1_1 | 3.206 | 3,203 | 0.1826 | 61.6% | 4.00 | 1.000 | 0.843 | 0.000 | 1,412 MB | 4 / ABSENT | steal 0.000%, 2730→2675 MHz |
| p4a_act_1 | 2.760 | 3,203 | 0.3501 | 99.9% | 4.85 | 0.644 | 2.219 | 0.997 | 7,484 MB | 4 / ACTIVE | steal 0.000%, 2676→2616 MHz |
| p4a_rr16_2 | 2.621 | 3,203 | 0.3692 | 99.9% | 2.44 | 0.597 | 1.398 | 0.997 | 7,430 MB | 4 / ABSENT | steal 0.000%, 2642→2764 MHz |
| p4a_li16_2 | 3.136 | 3,203 | 0.2991 | 100.0% | 2.85 | 0.753 | 0.981 | 0.005 | 5,326 MB | 4 / ABSENT | steal 0.000%, 2760→2718 MHz |
| p4a_rr1_2 | 4.198 | 3,203 | 0.2009 | 86.3% | 4.23 | 0.999 | 1.236 | 0.005 | 2,212 MB | 4 / ABSENT | steal 0.000%, 2676→2618 MHz |
| p4a_li1_2 | 2.754 | 3,203 | 0.2227 | 64.4% | 4.00 | 1.000 | 1.015 | 0.000 | 1,379 MB | 4 / ABSENT | steal 0.000%, 2625→2683 MHz |
| p4a_act_2 | 2.348 | 3,203 | 0.4130 | 99.9% | 4.64 | 0.656 | 2.511 | 0.997 | 7,430 MB | 4 / ACTIVE | steal 0.000%, 2728→2764 MHz |

CPU model on every leg: Intel(R) Xeon(R) Platinum 8488C; sessions: ff48c148.

### Forward pass per frame, full D1 metric set (per leg, seconds)

| leg | count | mean | sd | min | p50 | p90 | p95 | p99 | max | mean/p50 |
|---|---|---|---|---|---|---|---|---|---|---|
| p4a_rr16_1 | 3,203 | 0.3552 | 0.0348 | 0.2274 | 0.3623 | 0.3793 | 0.3839 | 0.4709 | 0.8132 | 0.980 |
| p4a_li16_1 | 3,203 | 0.2697 | 0.0839 | 0.1812 | 0.2777 | 0.3687 | 0.3716 | 0.3766 | 0.4490 | 0.971 |
| p4a_rr1_1 | 3,203 | 0.1872 | 0.0034 | 0.1793 | 0.1865 | 0.1917 | 0.1944 | 0.1981 | 0.2087 | 1.004 |
| p4a_li1_1 | 3,203 | 0.1826 | 0.0080 | 0.1788 | 0.1800 | 0.1852 | 0.2004 | 0.2285 | 0.2301 | 1.014 |
| p4a_act_1 | 3,203 | 0.3501 | 0.0612 | 0.2064 | 0.3508 | 0.3915 | 0.4101 | 0.5473 | 2.0185 | 0.998 |
| p4a_rr16_2 | 3,203 | 0.3692 | 0.0467 | 0.2392 | 0.3673 | 0.4166 | 0.4304 | 0.5746 | 0.7759 | 1.005 |
| p4a_li16_2 | 3,203 | 0.2991 | 0.0715 | 0.2272 | 0.2862 | 0.4105 | 0.4236 | 0.4291 | 0.4585 | 1.045 |
| p4a_rr1_2 | 3,203 | 0.2009 | 0.0189 | 0.1824 | 0.1954 | 0.2448 | 0.2507 | 0.2559 | 0.2654 | 1.028 |
| p4a_li1_2 | 3,203 | 0.2227 | 0.0283 | 0.1803 | 0.2414 | 0.2468 | 0.2485 | 0.2514 | 0.2590 | 0.922 |
| p4a_act_2 | 3,203 | 0.4130 | 0.0640 | 0.2267 | 0.4266 | 0.4525 | 0.4630 | 0.5607 | 1.7632 | 0.968 |

### Readings (pre-registered)

| quantity | value |
|---|---|
| D_RR = F(RR K=16) / F(RR K=1) | 1.867 |
| D_LI = F(LI K=16) / F(LI K=1) | 1.403 |
| D_RR / D_LI − 1 | +33.03% |
| S1 = the largest F spread of the four cells | 19.79% |
| clause 1: RR degrades more than LI beyond S1 | yes |
| RR K=1 frames/s vs LI K=1 frames/s | 4.341 vs 2.980 (+45.66%) |
| clause 2: RR K=1 f/s ≥ LI K=1 f/s | yes |
| beside: sum of the four F spreads (context, not the rule) | 41.06% |

**R1 (CONCURRENCY-SPECIFIC): SUPPORTED**.

| quantity | value |
|---|---|
| RR degradation F(K=16)/F(K=1) − 1 | +86.67% |
| its threshold max(spread RR K=1, RR K=16) | 7.08% |
| precondition: degradation beyond its spreads | yes |
| precondition: correctness gate | PASS |
| closure c = (F16 − F_ACTIVE) / (F16 − F1) | -0.115 |
| ACTIVE's reduction F16 / F_ACTIVE − 1 | -5.08% |
| S2 = max(spread RR K=16, spread ACTIVE) | 16.49% |
| beside: ACTIVE frames/s vs RR K=16 | -4.37% |

**R2 / R3: R3 NOT WAKE-UP (caller interleaving or shared contention; P5 candidate: a single inference thread).**

R1 is SUPPORTED. From one video in flight to sixteen, RocketRide's forward pass per frame goes from 0.1940 s to 0.3622 s (x1.867); LlamaIndex's goes from 0.2027 s to 0.2844 s (x1.403). RocketRide's degradation exceeds LlamaIndex's by +33.03% against S1 19.79% (beyond). At one video in flight RocketRide runs 4.341 frames/s and LlamaIndex 2.980 (+45.66%); at sixteen, 2.671 and 3.299. R2/R3: R3 NOT WAKE-UP (caller interleaving or shared contention; P5 candidate: a single inference thread). The ACTIVE cell is output-identical to RR K=16 on 16/16 videos in every pair; it closes -0.115 of RocketRide's K=1 to K=16 forward degradation (the rule needs 0.5); F(RR K=16) / F(ACTIVE) − 1 is -5.08% against S2 16.49%; and its frames/s is -4.37% against RR K=16. POST-HOC, not pre-registered (analysis_p4a_posthoc.json). (i) Every cell's second run was slower than its first: the forward per frame rose by +3.93% (rr_k16) to +21.96% (li_k1); steal stayed near zero and the per-leg MHz snapshots do not explain it. The ABAB order put both runs of every cell in each round, so the drift widened the spreads (S1 is li_k1's 19.79%) rather than biasing a comparison. Read per round, RocketRide's degradation exceeds LlamaIndex's by +28.52% (round 1) and +36.83% (round 2), and ACTIVE's closure is 0.030 and -0.261: both rounds give the pooled readings. (ii) ACTIVE is a cost, not a fix: +72.47% CPU-s per frame, 6.01 service cores against 3.66 at K=16, and no shorter forward. (iii) At K=16 the process keeps fewer cores busy during a forward than at K=1 on both arms (RocketRide 4.23 -> 2.44, LlamaIndex 4.00 -> 2.79); at K=16 that figure is an upper bound on the forward's own cores (the registered bias), and ACTIVE raises it to 4.74 (its spinning pools count) without shortening the forward. (iv) Within this session LlamaIndex at K=16 runs +23.52% frames/s over RocketRide at K=16. (v) At K=1 RocketRide's lock duty is 86.1% against LlamaIndex's 63.0%, consistent with the source trace: LlamaIndex extracts a video's frames before it takes its lock, and at K=1 nothing overlaps that extraction.

## P4-B (1) — steady-phase docs/s as the smoke metric (POST-HOC VALIDATION on committed legs)

Definition: P0 steady-phase docs/s = ok documents completed by the last submission / (last submission - first submission). Full-scale reference: P3-A's RR/LI span ratio 1.0664; agreement bound ±8.19%.

| leg (384 slice) | ok/rows | span docs/s | steady-phase docs/s | drain share of span |
|---|---|---|---|---|
| p2a_rr_a | 382/384 | 2.6314 | 6.4073 | 62.4% |
| p2a_rr_b | 382/384 | 2.5835 | 6.3395 | 62.7% |
| p2a_li_a | 381/384 | 3.0268 | 6.1840 | 55.2% |
| p2a_li_b | 381/384 | 3.2854 | 5.9769 | 49.6% |
| p3a_rr_h | 382/384 | 3.2356 | 8.0209 | 63.0% |
| p3a_li_h | 381/384 | 4.0261 | 7.6214 | 51.6% |
| p3c_t1_a | 382/384 | 3.2271 | 8.0325 | 63.2% |
| p3c_t1_b | 382/384 | 3.2124 | 8.0430 | 63.4% |
| p3c_t2_a | 382/384 | 4.3242 | 7.4304 | 46.7% |
| p3c_t2_b | 382/384 | 4.3365 | 7.3900 | 46.2% |
| p3c_t4_a | 382/384 | 5.1451 | 7.0127 | 32.8% |
| p3c_t4_b | 382/384 | 5.1548 | 7.0341 | 32.9% |

| session | steady RR/LI | vs full-scale − 1 | agrees (±8.19%) | span RR/LI (beside) |
|---|---|---|---|---|
| P2-A | 1.0482 | -1.71% | yes | 0.8262 |
| P3-A health | 1.0524 | -1.31% | yes | 0.8036 |

| shape (P3-C smoke) | steady mean | steady spread | span mean (beside) | span spread (beside) |
|---|---|---|---|---|
| vars=1 | 8.0378 | 0.13% | 3.2197 | 0.46% |
| vars=2 | 7.4102 | 0.54% | 4.3304 | 0.28% |
| vars=4 | 7.0234 | 0.30% | 5.1499 | 0.19% |

Check 1 (both sessions agree): **PASS**. Check 2 (vars=4 slower than vars=1 on the steady phase; -12.62%; reported beside, not the rule: the threshold max(0.82% floor, the vars=1 and vars=4 steady spreads) = 0.82%): **PASS**.

**Verdict: VALIDATES**.

By the pre-registered rule the steady-phase metric VALIDATES (POST-HOC, on committed legs). Check 1: the 384-slice steady-phase RocketRide/LlamaIndex ratio is 1.0482 in P2-A's session and 1.0524 in P3-A's, -1.71% and -1.31% from P3-A's full-scale 1.0664 (bound ±8.19%), where the span ratio on the same legs read 0.8262 and 0.8036. Check 2: the steady phase ranks vars=4 -12.62% against vars=1, the full-scale sign, where span docs/s ranked it +59.95%. A register entry proposing steady-phase docs/s as the smoke metric for future throughput gates is DRAFTED in P4B_REGISTER_ENTRY_DRAFT_STEADY_PHASE.md (not added to the register). Limits: two sessions and one shape comparison, post-hoc; only ratios and rankings carry over — the slice's absolute steady-phase rate is not full-scale throughput and is never quoted as throughput.

## P4-B (2) — parser track close-out (P3's committed full legs, same session)

| arm | ok/rows | span s | docs/s | chunks | chunks/s | CPU-s | CPU-s per chunk | chunks per ok doc |
|---|---|---|---|---|---|---|---|---|
| FIX (p3a_rr_full) | 9,886/9,975 | 1570.0 | 6.2969 | 209,797 | 133.63 | 43,913.7 | 0.2093 | 21.222 |
| HYB (p3d_hyb_full) | 9,886/9,975 | 1422.2 | 6.9513 | 186,931 | 131.44 | 37,119.0 | 0.1986 | 18.909 |

| ratio (HYBRID / fixed Tika) | value |
|---|---|
| docs/s, R_docs | 1.1039 |
| chunks per ok document, R_cpd | 0.8910 |
| chunks/s, R_chunks | 0.9836 |
| CPU-s per chunk | 0.9487 |
| check: R_chunks / R_cpd (= R_docs) | 1.1039 |
| share of the docs/s gain that is fewer chunks, ln(1/R_cpd) / ln(R_docs) | 116.7% |
| share from chunk throughput, ln(R_chunks) / ln(R_docs) | -16.7% |

Closing statement. HYBRID's full-corpus docs/s gain over fixed Tika is +10.39%. All of it is fewer chunks: HYBRID emits 10.9% fewer chunks for the same 9,886 ok documents (chunks per ok document 21.222 -> 18.909); against fixed Tika its chunks/s is -1.64% and its CPU-s per chunk -5.13%. By the log decomposition 116.7% of the gain is fewer chunks and -16.7% is chunk throughput. The parser track is CLOSED: keep fixed Tika; a parser change is a text-quality decision (HYBRID's text differs from Tika's on a tail of documents, P3-D), and any text-quality gate comes before any parser speed claim.

## P4-B (3) — P5 design draft (not filed)

Embedded from `P4B_P5_DESIGN_SINGLE_INFERENCE_THREAD.md`.

The draft's last section was written before any P4-A data, as rules against the pre-registered readings. P4-A produced R1 SUPPORTED and R3 NOT WAKE-UP, so the row that applies is: R1 SUPPORTED and R3 (NOT WAKE-UP): the design IS the right next step.

> # P5 design draft: a single inference thread for the detect node
>
> DRAFT, not filed, posted or sent. It is the design only; no code is written or built in P4.
>
> ## The problem it answers
>
> Two measurements set this up, from different sessions:
>
> - **One video in flight** (P3-B, one session): the engine's forward pass takes about the same time per frame as a bare interpreter and as LlamaIndex's service. Source: `parity_p3_20260925T035027Z/analysis_p3b.json`.
> - **Sixteen videos in flight** (P1-A, P2-B): the engine's forward is much slower than LlamaIndex's. Source: `parity_p2_20260924T160106Z/analysis_p2b.json`.
>
> The P0 V3 source trace (`parity_p0_20260923T083031Z/source_traces.json`, `V3_lock_scope`) shows the two arms lock differently:
>
> - **RocketRide:**
>   - The lock is `engine/nodes/detect/IGlobal.py:79-81` → `make_device_lock()`, `engine/ai/common/models/base.py:241-252`: one `threading.Lock` per task process.
>   - It is held around exactly one `self.IGlobal.detector.detect(image)` call per frame, at `engine/nodes/detect/IInstance.py:106-107`.
>   - So with K videos in flight, K caller threads (one per in-flight video's pipeline instance) take turns at the lock frame by frame. Each forward runs on whichever caller holds the lock.
> - **LlamaIndex:**
>   - The lock is `pipeline.py:127`.
>   - It is held around the whole per-video frame loop, at `pipeline.py:251-259`.
>   - So one caller runs every frame of its video before the next caller gets the lock.
>
> libgomp keeps a separate OpenMP thread team for each thread that starts a parallel region. So under RocketRide's per-frame hand-off, up to K different teams of T−1 workers take turns running forwards, and each team sleeps while the other callers hold the lock.
>
> ## The design
>
> **Where.** Two files change; everything else is unchanged:
> - **`IGlobal`** (the detect node's per-task-process global). It already owns the one `detector` and the `device_lock`. It gains an `InferenceWorker`: one daemon thread, a bounded `queue.Queue`, and one `concurrent.futures.Future` per request.
> - **`IInstance.writeImage`**, the `AVI_ACTION.END` branch:
>   1. Decode the frame's bytes on the caller thread, as today (`IInstance.py:103`, outside the lock today).
>   2. Call `fut = IGlobal.infer.submit(image)`, then `detections = fut.result(timeout=...)`.
>   3. Emit on the caller thread, as today (`_emit`).
>
> **The inference thread.** A loop of three steps:
> 1. Take the next item.
> 2. Call `with device_lock: detections = detector.detect(image)`. This is the same call on the same object as today, with the same resize, pre-processing, forward, post-processing and rescale. The lock stays and is now uncontended, so any other user of the lock is still excluded.
> 3. Put the result, or the exception, on the item's future.
>
> Every forward now runs on one OS thread, so libgomp uses one team. That team runs each frame back to back, so it's woken at most once per frame and never handed between callers. The thread counts are the same T variables as stock.
>
> **Frame ordering and per-video result routing.** Both hold by construction, with no routing table:
> - Each caller has at most ONE frame outstanding: it blocks on its own future before `writeImage` returns, and the engine delivers a video's frames to its pipeline instance in order.
> - So a video's frames go through the queue in order, and each result returns on the future that its own caller holds.
>
> Across videos, the queue is FIFO: callers are served in arrival order, which is round-robin in practice because each caller has one frame outstanding.
>
> **Backpressure and memory bound.**
> - **Queue depth:** at most the number of in-flight callers K, because each caller has at most one outstanding frame. The queue's `maxsize` is set to the engine's per-task concurrency, so `put` blocks and never grows without limit.
> - **Memory:**
>   - held: at most K decoded frames waiting plus the one inside `detect`;
>   - freed: each frame is released when its caller's future resolves (the caller drops `image` after `_emit`, as today).
> - **Stock comparison:** the stock node holds up to K decoded frames too (callers waiting at the lock), so the bound is the same.
>
> **Failure behaviour.**
> - An exception in `detect` is set on the future and re-raised in the caller. It reaches the node's existing `except` branch: the frame is dropped with the existing warning, the same observable behaviour as stock.
> - `fut.result(timeout)` bounds the wait if the inference thread dies. The thread is restarted by `IGlobal` on the next `submit`, and the event is logged.
> - **Shutdown:** `IGlobal`'s end puts a sentinel, joins the thread, and fails any pending future.
>
> **What it does not change.** No batching: one frame per `detect` call, exactly as stock. Batching frames from several videos into one forward could change the floats, so it would be a separate step with its own correctness gate. Nor does it change decode, emit, the pipeline, the model, its weights or the thread variables.
>
> ## The correctness test (before any speed claim)
>
> - **Output identity with stock at the same T:** per-video chunk sha256 AND frame scores equal on 16/16 videos of the AMI 16-video slice (`p0_analyse_video.identity`). Both the P5 build and stock `rr:patched-video` run at T=4, at K=16 and at K=1.
> - **Null controls,** which must FAIL the same check:
>   - the P5 build at T=16 against stock at T=4 (a known output change: P0 V1 `rr_t4_vs_default_output` differs on 16/16);
>   - a deliberately mis-routing worker that swaps the results of two callers, which proves the check catches routing errors.
> - **Only after identity passes:** the forward per frame and frames/s at K=1 and K=16, ABAB, in one session, as P4-A measured them.
>
> ## The in-bounds proof
>
> - **One engine process, one pipeline (one token), one model instance.** The worker calls the SAME `IGlobal.detector` object; nothing is copied or loaded a second time.
>   - D0: the on-token env_probe's `root_modules_with_params` must still show one `LWDETR` with `distinct_weights` 1, pre and post, and one task process for the leg.
> - **Threads only:** one extra thread per task process, visible in the read-back's thread census, and still inside the "threads unrestricted" clause.
>
> ## Which P4-A readings make it the right next step
>
> This section was written BEFORE P4-A's data. It reads as rules against the pre-registered readings.
>
> | P4-A outcome | Is P5 the next step? |
> |---|---|
> | R1 SUPPORTED and R3 (NOT WAKE-UP) | **Yes.** The gap is concurrency-specific, and keeping OpenMP pools awake does not close it. Whatever remains is either caller interleaving (the forward runs on K different threads with K teams), which this design removes, or shared contention (other callers' decode and emit competing with the forward's T threads), which it does not. Its measurement separates the two: if F at K=16 under P5 falls to F at K=1, it was interleaving; if not, the next candidate is CPU partitioning for the inference thread's team. |
> | R1 SUPPORTED and R2 (POOL WAKE-UP) | **Not first.** The configuration fix (`OMP_WAIT_POLICY=ACTIVE` or a spin-count setting) comes first. P5 is deferred and reconsidered only for the CPU that ACTIVE spends spinning idle pools, measured beside. |
> | R1 NOT SUPPORTED | **No.** The gap is not concurrency-specific, so a design that changes how concurrent callers share the detector does not address it. What the K=1 cells show is explained first. |
> | R2/R3 NOT EVALUABLE (output-changing, or no RR degradation) | P5 is not justified by P4-A. It stays a draft. |

## P4-B (4) — CTO facts sheet

Embedded from `P4_FACTS_SHEET.md` (generated by `working/scripts/p4_facts.py`).

Every figure is read by working/scripts/p4_facts.py from the named committed artifact at the named key; a key ending in '− 1' shows that value minus one, and a percent shows 100 × the value; session = boot id prefix; one caveat line each. Withdrawn figures are not listed.

| id | area | figure | value | source (artifact : key) | session | n | caveat |
|---|---|---|---|---|---|---|---|
| F01 | docs parity | RocketRide, one token, full corpus (9,975): span docs/s | 6.2969 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.rr_docs_per_s` | 3a2dc046 | 1 run | requires the UNSHIPPED P1-B Tika wrapper fix (image rr:p1-tikafix); banked posture (six thread vars = 1) |
| F02 | docs parity | LlamaIndex, 24 workers, full corpus: span docs/s | 5.9046 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.li_docs_per_s` | 3a2dc046 | 1 run | LlamaIndex's measured optimum (24 workers, C=32), same session |
| F03 | docs parity | RocketRide / LlamaIndex, full corpus | 1.066 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.ratio_rr_over_li` | 3a2dc046 | 1 run per arm | MATCHES, NOT BEATS: the margin is inside LlamaIndex's 8.19% replicate spread; needs the unshipped fix |
| F04 | docs parity | the same ratio excluding the eleven pathological PDFs | 1.066 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.excluded_straggler.ratio_rr_over_li` | 3a2dc046 | 1 run per arm | with the fix the eleven no longer move the ratio |
| F05 | docs cost | RocketRide CPU-s per document (full corpus) | 4.442 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.rr.cpu_s_per_doc` | 3a2dc046 | 1 run | service container CPU over the leg window / ok documents |
| F06 | docs cost | LlamaIndex CPU-s per document (full corpus) | 3.881 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.li.cpu_s_per_doc` | 3a2dc046 | 1 run | service container CPU over the leg window / ok documents |
| F07 | docs cost | RocketRide service cores (full corpus) | 27.97 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.rr.engine_cores` | 3a2dc046 | 1 run | of 32 vCPU, unconstrained (Ruling A) |
| F08 | docs cost | LlamaIndex service cores (full corpus) | 22.91 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.li.engine_cores` | 3a2dc046 | 1 run | of 32 vCPU, unconstrained (Ruling A) |
| F09 | docs cost | RocketRide idle spin, cores burned with nothing submitted | 1.234 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.rr.idle_spin_cores` | 3a2dc046 | 1 run | measured before the leg; never added back to throughput; source untraced |
| F10 | docs cost | LlamaIndex idle spin, cores burned with nothing submitted | 0.026 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.li.idle_spin_cores` | 3a2dc046 | 1 run | measured before the leg; never added back to throughput; source untraced |
| F11 | docs cost | RocketRide sampled memory peak (total), MB | 21,826 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.rr.memory.peak_bytes.total` | 3a2dc046 | 1 run | 1 Hz sampler over the leg window (MB = bytes / 1e6) |
| F12 | docs cost | LlamaIndex sampled memory peak (total), MB | 18,069 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.li.memory.peak_bytes.total` | 3a2dc046 | 1 run | 1 Hz sampler over the leg window (MB = bytes / 1e6) |
| F13 | docs output | RocketRide empty documents of 9,975 | 89 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.rr.lost_documents.n` | 3a2dc046 | 1 run | a document is empty if not ok or zero chunks |
| F14 | docs output | LlamaIndex empty documents of 9,975 | 102 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_A.full.per_arm.li.lost_documents.n` | 3a2dc046 | 1 run | a document is empty if not ok or zero chunks |
| F15 | docs out of box | stock rr:patched, one token, full corpus: span docs/s | 2.3454 | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `p1b.full.a_docs_per_s` | e293381c | 1 run | the out-of-box baseline; no same-session LlamaIndex full run: form no ratio with a LlamaIndex figure (register 46) |
| F16 | docs out of box | stock rr:patched CPU-s per document (full corpus) | 7.706 | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `legs.p1b_base_full.cpu_s_per_doc` | e293381c | 1 run | stock image at the banked posture |
| F17 | docs fix | with the wrapper fix (rr:p1-tikafix), full corpus: span docs/s | 5.3441 | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `p1b.full.b_docs_per_s` | e293381c | 1 run | UNSHIPPED fix (P2-D ticket draft, not filed); chunk-identical to stock |
| F18 | docs fix | wrapper fix vs stock, full corpus | +127.85% | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `p1b.full.delta_b_vs_a` | e293381c | 1 run per arm | one run each, same session; the gain is the tail of eleven pathological PDFs |
| F19 | docs fix | wrapper fix vs stock, 384 slice (ABAB) | +12.61% | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `p1b.speed_384.delta_b_vs_a` | e293381c | 2 runs per arm | the slice holds none of the eleven, so it understates the fix |
| F20 | docs fix | chunk lists that differ, fix vs stock, full corpus | 0 of 9,885 | `working/results/parity_p1_20260923T184000Z/analysis_p1docs.json` : `p1b.correctness_full_corpus_context` | e293381c | 1 run per arm | output-neutral: documents ok in both |
| F21 | docs tuning | thread vars = 4 vs vars = 1, full corpus | -4.56% | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_C.full.delta` | 3a2dc046 | 1 run per arm | DO NOT ADOPT: its gain on the 384 slice came from the slice's idle cores (register 60) |
| F22 | docs parser | HYBRID parser vs fixed Tika, full corpus: docs/s | +10.39% | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_D.full.hybrid.speed.delta` | 3a2dc046 | 1 run per arm | a smaller, different output, not a faster parser; parser track closed |
| F23 | docs parser | HYBRID vs fixed Tika: chunks, share fewer | 10.9% fewer | `working/results/parity_p4_20260925T092942Z/analysis_p4b.json` : `item2_parser_close_out.chunks_fewer` | 3a2dc046 | 1 run per arm | fewer chunks for the same documents: its text differs from Tika's |
| F24 | docs parser | HYBRID vs fixed Tika: chunks/s | -1.64% | `working/results/parity_p4_20260925T092942Z/analysis_p4b.json` : `item2_parser_close_out.R_chunks_per_s − 1` | 3a2dc046 | 1 run per arm | per chunk HYBRID is not faster: all of its docs/s gain is fewer chunks |
| F25 | docs parser | PURE parser: documents lost that fixed Tika recovers | 5 | `working/results/parity_p3_20260925T035027Z/analysis_p3docs.json` : `P3_D.full.pure.correctness.n_loses` | 3a2dc046 | 1 run | not adoptable; the five P0's H6 predicted |
| F26 | docs method | 384 slice span docs/s ratio RR/LI (P2-A smoke) | 0.826 | `working/results/parity_p2_20260924T160106Z/analysis_p2docs.json` : `P2_A.smoke_gate.ratio_rr_over_li` | dc407ed6 | 2 runs per arm | drain-dominated slice: not a parity figure (superseded by P3-A full) |
| F27 | docs method | 384 slice STEADY-PHASE ratio RR/LI (P2-A legs) | 1.048 | `working/results/parity_p4_20260925T092942Z/analysis_p4b.json` : `item1_steady_phase.check_1.sessions.P2-A.steady_ratio` | dc407ed6 | 2 runs per arm | POST-HOC validation of a smoke metric, not a throughput claim |
| F28 | video parity | one LlamaIndex instance vs one RocketRide token, T=4, 16 videos in flight: LI/RR - 1 | +34.7% | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `gap.li_over_rr_minus_1` | a58bf81c | 2 runs per arm | the per-instance video gap at K=16 (P0 V1) |
| F29 | video parity | RocketRide, T=4, 16 videos in flight: frames/s | 2.553 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.rr_t4.mean` | a58bf81c | 2 runs | mean of two runs; K=16 |
| F30 | video parity | LlamaIndex, T=4, 16 videos in flight: frames/s | 3.440 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.li_t4.mean` | a58bf81c | 2 runs | mean of two runs; K=16 |
| F31 | video out of box | RocketRide, engine default threads (out of box), 16 videos in flight: frames/s | 2.556 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.rr_default.mean` | a58bf81c | 2 runs | mean of two runs; K=16; LlamaIndex's cell ran at T=4 |
| F32 | video cost | RocketRide, T=4: CPU-s per frame | 1.423 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.rr_t4.cpu_s_per_frame (mean of two)` | a58bf81c | 2 runs | service container CPU / frames |
| F33 | video cost | LlamaIndex, T=4: CPU-s per frame | 0.878 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.li_t4.cpu_s_per_frame (mean of two)` | a58bf81c | 2 runs | service container CPU / frames |
| F34 | video cost | RocketRide, default threads: CPU-s per frame | 2.094 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `cells.rr_default.cpu_s_per_frame (mean of two)` | a58bf81c | 2 runs | service container CPU / frames |
| F35 | video cost | RocketRide idle cores with the instance live, nothing submitted | 1.23 | `working/results/parity_p0_20260923T083031Z/analysis_v1.json` : `legs.v1_rr_t4_{a,b}.idle_burden.idle_cores_with_instances_live (mean)` | a58bf81c | 2 runs | LlamaIndex's: about zero (same file); source untraced |
| F36 | video parity | P2-B reproduction, T=4, K=16: LI/RR - 1 | +34.0% | `working/results/parity_p2_20260924T160106Z/analysis_p2b.json` : `reading.gap.li_over_base_minus_1` | dc407ed6 | 2 runs per arm | reproduced in a second session |
| F37 | video config | noDebug + MALLOC_ARENA_MAX=2 vs stock, K=16: frames/s | +8.55% | `working/results/parity_p2_20260924T160106Z/analysis_p2b.json` : `reading.combined.comb_over_base_minus_1` | dc407ed6 | 2 runs per arm | closes about a quarter of the gap; pair b alone is inside the spreads |
| F38 | video config | noDebug + MALLOC_ARENA_MAX=2: output identical | 16 of 16 videos, both pairs | `working/results/parity_p2_20260924T160106Z/analysis_p2b.json` : `correctness_gate` | dc407ed6 | 2 pairs | chunk hashes and frame scores |
| F39 | video config | noDebug + MALLOC_ARENA_MAX=2: sampled anonymous-memory peak, stock -> combined, MB | 5,397 -> 2,415 | `working/results/parity_p2_20260924T160106Z/analysis_p2b.json` : `legs.p2b_rr_{base,comb}_{a,b}.memstat.sampled_peak_bytes.anon (means)` | dc407ed6 | 2 runs per arm | the UNSHIPPED ticket (P3-E draft, not filed) |
| F40 | video one in flight | RocketRide engine, ONE video in flight, T=4: frames/s | 4.44 | `working/results/parity_p3_20260925T035027Z/analysis_p3b.json` : `legs.p3b_c_{1,2}.frames_per_s (mean)` | 3a2dc046 | 2 runs | 3-video slice |
| F41 | video one in flight | LlamaIndex service, ONE video in flight, T=4: frames/s | 3.14 | `working/results/parity_p3_20260925T035027Z/analysis_p3b.json` : `legs.p3b_d_1.frames_per_s` | 3a2dc046 | 1 run | 3-video slice; one run (context leg) |
| F42 | video one in flight | forward pass per frame, engine at one video in flight, s | 0.190 | `working/results/parity_p3_20260925T035027Z/analysis_p3b.json` : `cells.c.mean` | 3a2dc046 | 2 runs | within 3% of a bare interpreter (cells.a.mean): the model and libraries are not the gap |
| F43 | video concurrency | RocketRide K=1, T=4, 16 videos: frames/s | 4.341 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k1.frames_per_s.mean` | ff48c148 | 2 runs | same session, ABAB; the two runs differ by 6.6% (every cell slower in round 2) |
| F44 | video concurrency | RocketRide K=1: forward pass per frame, s | 0.1940 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k1.F_s.mean` | ff48c148 | 2 runs | mean over measured frames; the two runs differ by 7.1% |
| F45 | video cost | RocketRide K=1: CPU-s per frame | 1.197 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k1.cpu_s_per_frame.mean` | ff48c148 | 2 runs | service container CPU / frames |
| F46 | video concurrency | RocketRide K=16, T=4, 16 videos: frames/s | 2.671 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16.frames_per_s.mean` | ff48c148 | 2 runs | same session, ABAB; the two runs differ by 3.8% (every cell slower in round 2) |
| F47 | video concurrency | RocketRide K=16: forward pass per frame, s | 0.3622 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16.F_s.mean` | ff48c148 | 2 runs | mean over measured frames; the two runs differ by 3.9% |
| F48 | video cost | RocketRide K=16: CPU-s per frame | 1.371 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16.cpu_s_per_frame.mean` | ff48c148 | 2 runs | service container CPU / frames |
| F49 | video concurrency | LlamaIndex K=1, T=4, 16 videos: frames/s | 2.980 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k1.frames_per_s.mean` | ff48c148 | 2 runs | same session, ABAB; the two runs differ by 15.2% (every cell slower in round 2) |
| F50 | video concurrency | LlamaIndex K=1: forward pass per frame, s | 0.2027 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k1.F_s.mean` | ff48c148 | 2 runs | mean over measured frames; the two runs differ by 19.8% |
| F51 | video cost | LlamaIndex K=1: CPU-s per frame | 0.929 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k1.cpu_s_per_frame.mean` | ff48c148 | 2 runs | service container CPU / frames |
| F52 | video concurrency | LlamaIndex K=16, T=4, 16 videos: frames/s | 3.299 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k16.frames_per_s.mean` | ff48c148 | 2 runs | same session, ABAB; the two runs differ by 9.9% (every cell slower in round 2) |
| F53 | video concurrency | LlamaIndex K=16: forward pass per frame, s | 0.2844 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k16.F_s.mean` | ff48c148 | 2 runs | mean over measured frames; the two runs differ by 10.3% |
| F54 | video cost | LlamaIndex K=16: CPU-s per frame | 0.919 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.li_k16.cpu_s_per_frame.mean` | ff48c148 | 2 runs | service container CPU / frames |
| F55 | video concurrency | RocketRide K=16, OMP_WAIT_POLICY=ACTIVE, T=4, 16 videos: frames/s | 2.554 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16_active.frames_per_s.mean` | ff48c148 | 2 runs | same session, ABAB; the two runs differ by 16.2% (every cell slower in round 2) |
| F56 | video concurrency | RocketRide K=16, OMP_WAIT_POLICY=ACTIVE: forward pass per frame, s | 0.3816 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16_active.F_s.mean` | ff48c148 | 2 runs | mean over measured frames; the two runs differ by 16.5% |
| F57 | video cost | RocketRide K=16, OMP_WAIT_POLICY=ACTIVE: CPU-s per frame | 2.365 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `cells.rr_k16_active.cpu_s_per_frame.mean` | ff48c148 | 2 runs | service container CPU / frames |
| F58 | video concurrency | forward degradation K=1 -> K=16, RocketRide (x) | 1.867 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `readings.R1.D_RR` | ff48c148 | 2 runs per cell | R1 SUPPORTED |
| F59 | video concurrency | forward degradation K=1 -> K=16, LlamaIndex (x) | 1.403 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `readings.R1.D_LI` | ff48c148 | 2 runs per cell | R1 SUPPORTED |
| F60 | video concurrency | share of RocketRide's K=1 -> K=16 forward degradation that ACTIVE closes | -0.115 | `working/results/parity_p4_20260925T092942Z/analysis_p4a.json` : `readings.R2_R3.closure` | ff48c148 | 2 runs per cell | R3 NOT WAKE-UP (caller interleaving or shared contention; P5 candidate: a single inference |

## NOT RUN

- nothing: every pre-registered leg and item ran.

## Methodology register

- 61 — a gate that read the record before its writer finished it (G_d0 read the preflight's pre-leg block; caught by the laptop dry run's positive control before commit)
- 62 — a session that drifted between its rounds (every P4-A cell slower in round 2; ABAB kept the readings intact)

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (P4-A hypothesis, cells, metrics, the correctness gate, R1/R2/R3 and their thresholds, every gate and its controls; P4-B rules), committed at 1fcb6ce4; no amendment.
- **2. EVIDENCE:** every figure in this report is computed by working/scripts/p4_report.py and p4_write_specs.py from analysis_p4a.json (p4_analyse_a.py over the raw P4-A leg directories beside it), analysis_p4b.json (p4_analyse_b.py over P2's and P3's committed legs), p4_facts.json (p4_facts.py over committed analysis files), the gate-control record, the gate records in gates/ and the chain start/done records.
- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json, including a real ACTIVE control leg); the blind recomputation's planted figures had to be caught (P4_BLIND_VERIFICATION.json).
- **4. REGISTER:** 3 (one box session for every P4-A leg); 48 (blind recomputation); 54, 55 (hard gates; the memory sampler gated after the first leg; DEGRADED-with-all-rows kept); 56-58 (gates tested whole, positive and null; the container's user); 59 (each reading's clauses checked against the hypothesis's own condition); 60 (the smoke-slice bias, P4-B (1)); new entries listed above.
- **5. NOT VERIFIED:** which of caller interleaving or shared contention drives RocketRide's K=16 forward degradation (R3 holds; P5's measurement would separate them); why every P4-A cell ran slower in its second round (POST-HOC; steal and the MHz snapshots do not explain it); the P5 design (source only, not built); the steady-phase metric beyond two sessions and one shape comparison (post-hoc); whether one token BEATS LlamaIndex on docs at full scale (n = 1 per arm, inside LlamaIndex's spread).
- **6. GATES:** every P4 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls ran before launch; the chain launched once and ran its legs in order with hard gates after every leg; protected image ids read back at chain start and end; the box is stopped with box.sh stop at the end and its state read back.

