# P7 — where the two frames sit; the prototype or stock; the thread count; three drafts

Campaign `parity_p7_20260926T091049Z`, branch feat/parity-p7 (from feat/parity-p6 6f08e6a6). Generated 2026-09-26T10:43:26Z from committed analysis, gate and chain files; every figure is computed from raw records and rounded only here. Tolerances are FIXED; the canary adjusts nothing.

## Summary

- P7-A (committed exports only): **NOT BOUNDARY**. C1 FAILED; C2 holds; C3 NOT EVALUABLE. On both frames every detection's score differs between the banked stock run and the prototype (IN1002.avi#58: 18 of 18 detections, largest rank-paired shift 0.0173, TS3010a.avi#56: 12 of 12 detections, largest rank-paired shift 0.0144); every other frame of both videos is identical in scores and labels. The August 0.3004 figure is not in any committed artifact and is not used.
- P7-B Tier 1 (K=3, T=4, two ABAB runs per image): **UNCLASSIFIED** — the control IN1009.avi identical in all four runs; stock agrees with itself on both frames: yes; stock video-identical to the banked P1-D output on both videos: NO (frames where today's stock differs from P1-D: IN1002.avi none; TS3010a.avi 56; IN1009.avi none); the prototype agrees with itself on both frames: NO. Tier reached: 1. Tier 2 NOT RUN: G_tier2 did not fire (it fires only on CONDITION-DEPENDENT).
- POST-HOC, descriptive: IN1002.avi#58 — 3 distinct outputs across the banked P1-D stock run, the banked P6-B prototype run and the four Tier 1 runs: {banked P1-D stock, p7b_stock_1, p7b_stock_2, p7b_p5_2}; {banked P6-B prototype}; {p7b_p5_1}.
- POST-HOC, descriptive: TS3010a.avi#56 — 2 distinct outputs across the banked P1-D stock run, the banked P6-B prototype run and the four Tier 1 runs: {banked P1-D stock}; {banked P6-B prototype, p7b_stock_1, p7b_stock_2, p7b_p5_1, p7b_p5_2}.
- P6-C pooled reading (P6-C round 1 + P7-C round 2, cross-session): the P5 forward at T=16 is 1.705x its T=4 forward (the bar: <= 0.95) — T=16 is NOT faster by at least 5% (pooled); P5 T=16 / LlamaIndex T=16 frames/s 0.942 (reported against 0.95); P7-C's output identical to the out-of-box reference: yes.
- The three drafts (patch description, thread-count ticket, CTO brief) are below; none is sent, posted or filed.

## Step 0 and the recorded statements

- sso: checked 08:55Z: role credentials valid to 11:09Z (more than 2 h away), the SSO session carries a refresh token — no login; re-checked before any box time (if the credentials will lapse before a leg can finish, Ansh is asked to re-login)
- origin: origin/feat/parity-p6 = 6f08e6a6; feat/parity-p7 created from it
- autoland_self_test: 71 pass, 0 fail
- p6_standing: P6's report stands as landed (6f08e6a6): P6-B 166 of 168 videos identical to the banked P1-D stock output; IN1002.avi frame 58 and TS3010a.avi frame 56 differ; cause not established (register 65). P6-C round 2 NOT RUN.
- data_seen_before_this_file: While locating the committed data for P7-A (08:58-09:05Z), the two named frames' score lists and label multisets (P1-D vs P6-B) and the other frames' largest score difference were printed to the session. P7-A's reading rule is Ansh's, verbatim below; the definitions under P7_A were fixed afterwards and are the only ones the committed records permit (their labels are sorted, so detections can only be paired by rank; they carry no boxes). Nothing else of P7 was computed.
- sso_before_box: 09:13:46Z: role credentials valid to 11:09:41Z — within 2 h of expiry, and the 3-hour run would outlast them; box.sh login opened the authorization page and Ansh approved it (09:14Z; the new session carries a refresh token)
- box_start: 09:14Z box.sh start; boot e80a450e; no container; rr:patched 073b43d8b5f9, rr:patched-video b7f51acc9533, li:video 0a52afcbe9d4, rr:p5-infer b42c03b69f17 read back; microcode 0x2b000661
- worktree: ~/parity-bench-p7 at ed2cb388 (git worktree of ~/parity-bench)
- control_stage: 09:15:46Z-09:18:50Z p7ctl_cap rc 0 (a gate-control target, not a measured leg)
- gate_controls: 09:19Z gate_controls.json run 1 on the box: 42 of 42 as expected, all_pass
- run_stage_launch: 09:19:38Z p7_run

## Gates

| gate | rule | measured | outcome |
|---|---|---|---|
| G_alone (before every leg and canary) | no container on the box | box_logs/p7_run.log: 9 checks, containers present = 0; NOT_ALONE entries in the chain record: 0 | PASS |
| G_d0 (every leg it applies to) | preregistration.json gates | p7b_p5_1: CLEAN; p7b_p5_2: CLEAN; p7b_stock_1: CLEAN; p7b_stock_2: CLEAN; p7c_lit16_2: CLEAN; p7c_p5t16_2: CLEAN | ALL CLEAN |
| G_cell (every leg it applies to) | preregistration.json gates | p7b_p5_1: PASS; p7b_p5_2: PASS; p7b_stock_1: PASS; p7b_stock_2: PASS; p7c_lit16_2: PASS; p7c_p5t16_2: PASS | ALL PASS |
| G_detcap (every leg it applies to) | preregistration.json gates | p7b_p5_1: PASS; p7b_p5_2: PASS; p7b_stock_1: PASS; p7b_stock_2: PASS | ALL PASS |
| G_canary (every leg it applies to) | preregistration.json gates | p7b_can_1: PASS; p7b_can_2: PASS; p7c_can_c2: PASS | ALL PASS |
| G_memstat (first leg) | memstat.jsonl ≥ 1 row | p7b_stock_1: 203 rows | PASS |
| G_tier2 | fires iff the Tier 1 reading is CONDITION-DEPENDENT | reading UNCLASSIFIED | NOT FIRED |
| G_correct_C2 (HARD for P7-C) | p7c_p5t16_2 identical on 16/16 to P0 v1_rr_def_a | p7c_p5t16_2 vs v1_rr_def_a: identical, 16 videos | PASS |
| image ids | rr:patched, rr:patched-video unchanged; rr:p5-infer = P5's, not rebuilt | rr:patched sha256:073b43d8b5f9 rr:patched-video sha256:b7f51acc9533 rr:p5-infer sha256:b42c03b69f17 | UNCHANGED |
| budget | 3 h from the run stage's first leg | run start 2026-09-26T09:19:36Z; first leg 09:19:37Z; deadline 2026-09-26T12:19:37Z; chain done 2026-09-26T10:41:11Z | WITHIN |

### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL; G_tier2's must also give their reading)

**gate_controls.json** (run 1, boot e80a450e): 42 of 42 controls as expected → all_pass **True**.

| gate | positive control(s) (must PASS) | null control(s) (must FAIL) |
|---|---|---|
| G_memstat | P5 p5a_stock16_1 → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no memory sampler) → as expected (FAIL (rc 1)) |
| G_d0 rr | P5 p5a_p5k16_1 → as expected (PASS (rc 0))<br>P6's control leg p6ctl_p5t16 (out of box) → as expected (PASS (rc 0))<br>the control leg p7ctl_cap (stock, capture on) → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no on-token D0: absence) → as expected (FAIL (rc 2))<br>a copy of p5a_p5k16_1 whose post-leg D0 counts TWO LWDETR instances → as expected (FAIL (rc 1)) |
| G_d0 li | P5 p5a_li16_1 → as expected (PASS (rc 0))<br>P6's control leg p6ctl_lit16 → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (eight LlamaIndex containers) → as expected (FAIL (rc 1)) |
| G_cell p5 T=4 | P5 p5a_p5k16_1 → as expected (PASS (rc 0)) | p6ctl_p5t16 against T=4 (torch 16, the six vars unset) → as expected (FAIL (rc 1)) |
| G_cell p5 T=16 unset | P6's control leg p6ctl_p5t16 → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 against T=16 unset (torch 4, vars set) → as expected (FAIL (rc 1)) |
| G_cell li T=16 | P6's control leg p6ctl_lit16 → as expected (PASS (rc 0)) | P5 p5a_li16_1 against T=16 (torch 4) → as expected (FAIL (rc 1)) |
| G_cell stock T=4 | P5 p5a_stock16_1 → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 against the stock spec (image, stamps) → as expected (FAIL (rc 2)) |
| G_cell stock T=4 K=1 | the control leg p7ctl_cap → as expected (PASS (rc 0)) | p7ctl_cap against the P5 spec (image, stamps) → as expected (FAIL (rc 2)) |
| G_cell li T=4 | P5 p5a_li16_1 → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (no read-back) → as expected (FAIL (rc 2)) |
| G_warm | P6's control leg p6ctl_warm_rr (2 at 2) → as expected (PASS (rc 0))<br>P6's control leg p6ctl_warm_li (2 at 2) → as expected (PASS (rc 0))<br>P6-B p6b_rr_startwarm (16 at 16) → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 (the default warm policy, nothing declared) → as expected (FAIL (rc 1))<br>p6ctl_warm_rr against 16 at 16 → as expected (FAIL (rc 1)) |
| G_canary | P5 p5c_can_1 (committed canary) → as expected (PASS (rc 0)) | P3 p3b_a_1 (the same bench over all three videos) → as expected (FAIL (rc 1)) |
| G_correct | P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16) → as expected (PASS (rc 0))<br>P0 v1_rr_def_b vs v1_rr_def_a (identical 16/16) → as expected (PASS (rc 0)) | P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16) → as expected (FAIL (rc 1))<br>P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos) → as expected (FAIL (rc 1)) |
| G_detcap | the control leg p7ctl_cap (capture on) → as expected (PASS (rc 0)) | P6 p6a_stock16_1 (no capture file) → as expected (FAIL (rc 2))<br>a copy of p7ctl_cap with one captured score changed by 1e-9 → as expected (FAIL (rc 1)) |
| G_tier2 | all four identical (named frames EN2001a.avi:1,EN2001b.avi:0, control EN2001d.avi) → as expected (PASS (rc 0), reading CONDITION-DEPENDENT) | one stock run shifted on a named frame → as expected (FAIL (rc 1), reading STOCK VARIES)<br>both prototype runs shifted on both named frames → as expected (FAIL (rc 1), reading PROTOTYPE SHIFTS)<br>the control video shifted in one prototype run → as expected (FAIL (rc 1), reading UNREADABLE) |
| G_alone | no container on the box → as expected (PASS (rc 0)) | one created container present → as expected (FAIL (rc 1)) |

## P7-A — where do the two frames sit? (laptop, committed exports only, before any box time)

- **August evidence:** NOT COMMITTED — the figure is not used. the 26 Aug result directories committed (working/video/results/apples_20260826T041510Z, apples_20260826T052915Z) hold the RocketRide exports and collector summaries only — no LlamaIndex records and no cross_detection_agreement output; no committed file other than the report carries the 0.3004 figure for IN1002; the only committed mention is working/video/WS1_Phase2_Video_Benchmark_DEFINITIVE.md section 5.1 (commit 21990572, a byte-for-byte copy of a received report).
- **S5-B evidence:** committed — working/results/batchsize_s5_20260921T205917Z/analysis_output_shift.json s5b_tier2_label_set_failures_explained.2.label_set_failures[0].detections_crossing_the_band_edge[0] (score_B1, score_B2).

### IN1002.avi#58 — banked stock (parity_p1 v1full_rr_t4) vs the prototype (parity_p6_20260925T175225Z/p6b_rr_b06)

Detections: 17 vs 18; label-multiset difference: only in the prototype {'book': 1}, only in banked stock none; chunks differing: 1 of 260 (index 87).

| rank | score, banked stock | score, prototype | |Δ| | distance from 0.3 (stock / prototype) | within ±0.001 in either run | label | box |
|---|---|---|---|---|---|---|---|
| 0 | 0.8572 | 0.8635 | 0.0062 | 0.5572 / 0.5635 | no | not recoverable | not recorded |
| 1 | 0.6003 | 0.6009 | 0.0005 | 0.3003 / 0.3009 | no | not recoverable | not recorded |
| 2 | 0.5769 | 0.5826 | 0.0057 | 0.2769 / 0.2826 | no | not recoverable | not recorded |
| 3 | 0.5247 | 0.5271 | 0.0023 | 0.2247 / 0.2271 | no | not recoverable | not recorded |
| 4 | 0.5237 | 0.5249 | 0.0012 | 0.2237 / 0.2249 | no | not recoverable | not recorded |
| 5 | 0.5037 | 0.5099 | 0.0062 | 0.2037 / 0.2099 | no | not recoverable | not recorded |
| 6 | 0.5014 | 0.5014 | 0.0000 | 0.2014 / 0.2014 | no | not recoverable | not recorded |
| 7 | 0.4857 | 0.4887 | 0.0031 | 0.1857 / 0.1887 | no | not recoverable | not recorded |
| 8 | 0.4745 | 0.4833 | 0.0088 | 0.1745 / 0.1833 | no | not recoverable | not recorded |
| 9 | 0.4617 | 0.4790 | 0.0173 | 0.1617 / 0.1790 | no | not recoverable | not recorded |
| 10 | 0.4615 | 0.4551 | 0.0064 | 0.1615 / 0.1551 | no | not recoverable | not recorded |
| 11 | 0.4377 | 0.4349 | 0.0028 | 0.1377 / 0.1349 | no | not recoverable | not recorded |
| 12 | 0.4336 | 0.4290 | 0.0046 | 0.1336 / 0.1290 | no | not recoverable | not recorded |
| 13 | 0.4208 | 0.4204 | 0.0003 | 0.1208 / 0.1204 | no | not recoverable | not recorded |
| 14 | 0.3757 | 0.3763 | 0.0006 | 0.0757 / 0.0763 | no | not recoverable | not recorded |
| 15 | 0.3712 | 0.3703 | 0.0009 | 0.0712 / 0.0703 | no | not recoverable | not recorded |
| 16 | 0.3189 | 0.3238 | 0.0049 | 0.0189 / 0.0238 | no | not recoverable | not recorded |
| 17 | — | 0.3017 | unpaired | — / 0.0017 | no | book | not recorded |

### TS3010a.avi#56 — banked stock (parity_p1 v1full_rr_t4) vs the prototype (parity_p6_20260925T175225Z/p6b_rr_b10)

Detections: 12 vs 12; label-multiset difference: only in the prototype none, only in banked stock none; chunks differing: 1 of 59 (index 48).

| rank | score, banked stock | score, prototype | |Δ| | distance from 0.3 (stock / prototype) | within ±0.001 in either run | label | box |
|---|---|---|---|---|---|---|---|
| 0 | 0.8578 | 0.8578 | 0.0001 | 0.5578 / 0.5578 | no | not recoverable | not recorded |
| 1 | 0.6839 | 0.6866 | 0.0028 | 0.3839 / 0.3866 | no | not recoverable | not recorded |
| 2 | 0.6589 | 0.6732 | 0.0144 | 0.3589 / 0.3732 | no | not recoverable | not recorded |
| 3 | 0.6330 | 0.6342 | 0.0012 | 0.3330 / 0.3342 | no | not recoverable | not recorded |
| 4 | 0.5117 | 0.5101 | 0.0015 | 0.2117 / 0.2101 | no | not recoverable | not recorded |
| 5 | 0.4787 | 0.4795 | 0.0008 | 0.1787 / 0.1795 | no | not recoverable | not recorded |
| 6 | 0.4287 | 0.4272 | 0.0015 | 0.1287 / 0.1272 | no | not recoverable | not recorded |
| 7 | 0.3635 | 0.3577 | 0.0058 | 0.0635 / 0.0577 | no | not recoverable | not recorded |
| 8 | 0.3576 | 0.3552 | 0.0024 | 0.0576 / 0.0552 | no | not recoverable | not recorded |
| 9 | 0.3570 | 0.3549 | 0.0021 | 0.0570 / 0.0549 | no | not recoverable | not recorded |
| 10 | 0.3446 | 0.3507 | 0.0061 | 0.0446 / 0.0507 | no | not recoverable | not recorded |
| 11 | 0.3206 | 0.3185 | 0.0022 | 0.0206 / 0.0185 | no | not recoverable | not recorded |

### Every other frame of both videos

| video | frames compared | max score delta | frames with a count or label difference | max box delta |
|---|---|---|---|---|
| IN1002.avi | 164 | 0.00e+00 | 0 | NOT EVALUABLE (no boxes committed) |
| TS3010a.avi | 68 | 0.00e+00 | 0 | NOT EVALUABLE (no boxes committed) |

### Sessions

| video | run | leg | CPU | microcode | MHz open → close | boot |
|---|---|---|---|---|---|---|
| IN1002.avi | banked stock | parity_p1_20260923T184000Z/v1full_rr_t4 | Intel(R) Xeon(R) Platinum 8488C | not recorded (no leg file carries /proc/cpuinfo's microcode line) | 2765 → 2604 | e293381c |
| IN1002.avi | prototype | parity_p6_20260925T175225Z/p6b_rr_b06 | Intel(R) Xeon(R) Platinum 8488C | not recorded (no leg file carries /proc/cpuinfo's microcode line) | 2956 → 2734 | eb83839f |
| TS3010a.avi | banked stock | parity_p1_20260923T184000Z/v1full_rr_t4 | Intel(R) Xeon(R) Platinum 8488C | not recorded (no leg file carries /proc/cpuinfo's microcode line) | 2765 → 2604 | e293381c |
| TS3010a.avi | prototype | parity_p6_20260925T175225Z/p6b_rr_b10 | Intel(R) Xeon(R) Platinum 8488C | not recorded (no leg file carries /proc/cpuinfo's microcode line) | 3226 → 2712 | eb83839f |

| clause | result |
|---|---|
| C1 every differing detection's score, in either run, within +/-0.001 of 0.3 | FAILED |
| C2 every other frame of both videos: max score delta <= 1e-5 (and the same count and labels) | holds |
| C3 every other frame of both videos: box delta <= 1e-3 px | NOT EVALUABLE |

**P7-A: NOT BOUNDARY** — FAILED: C1 every differing detection's score, in either run, within +/-0.001 of 0.3; NOT EVALUABLE from committed exports: C3 every other frame of both videos: box delta <= 1e-3 px.

Stated plainly: the hypothesis was a detection sitting on the 0.3 threshold. That is not what the committed records show. On each frame EVERY detection's score moves (up to 0.0173); the only near-threshold detection is IN1002.avi's extra one in the prototype run, 0.0017 from 0.3 — outside ±0.001 — and it moves with the rest of the frame. Every other frame of both videos is identical in scores and labels. The committed records cannot say whether boxes moved.

## P7-B — is it the prototype or stock itself?

### Tier 1 (IN1002.avi, TS3010a.avi, the control IN1009.avi; K=3, T=4; ABAB, two runs each, canary first)

| leg (run order) | image | frames | frames/s | D0 | cell | detcap | session |
|---|---|---|---|---|---|---|---|
| p7b_stock_1 | rr:patched-video | 318 | 3.795 | CLEAN | PASS | PASS | microcode 0x2b000661, 2828→2981 MHz |
| p7b_p5_1 | rr:p5-infer | 318 | 3.795 | CLEAN | PASS | PASS | microcode 0x2b000661, 3130→2832 MHz |
| p7b_stock_2 | rr:patched-video | 318 | 3.763 | CLEAN | PASS | PASS | microcode 0x2b000661, 2929→2708 MHz |
| p7b_p5_2 | rr:p5-infer | 318 | 3.768 | CLEAN | PASS | PASS | microcode 0x2b000661, 2927→2700 MHz |

Control IN1009.avi identical across all six pairs of runs: **yes** (6 of 6 pairs).

| frame | stock agrees with itself | prototype agrees with itself | prototype agrees with stock (round 1 / 2) | all four agree | stock video-identical to P1-D (run 1 / 2) | agrees with banked P1-D (s1 s2 p1 p2) | agrees with banked P6-B (s1 s2 p1 p2) |
|---|---|---|---|---|---|---|---|
| IN1002.avi#58 | yes | NO | NO / yes | NO | yes / yes | yes yes NO yes | NO NO NO NO |
| TS3010a.avi#56 | yes | yes | yes / yes | yes | NO / NO | NO NO NO NO | yes yes yes yes |

Deltas against S5-B's Tier 2 tolerances (labels outside ±0.001 of 0.3, score ≤ 1e-5, box ≤ 1e-3 px; `batchsize_analyse_s5b.tier2_frame` on the captured detections):

| frame | pair | detections | rank-paired max score Δ (records) | Tier 2 max score Δ | Tier 2 max box Δ px | vs S5-B's tolerances |
|---|---|---|---|---|---|---|
| IN1002.avi#58 | stock 1 vs stock 2 | 17 / 17 | 0.0000 | 0.00e+00 | 0.00e+00 | within |
| IN1002.avi#58 | prototype 1 vs prototype 2 | 17 / 17 | 0.0100 | 1.22e-02 | 7.00e-01 | OUTSIDE |
| IN1002.avi#58 | prototype 1 vs stock 1 | 17 / 17 | 0.0100 | 1.22e-02 | 7.00e-01 | OUTSIDE |
| IN1002.avi#58 | prototype 2 vs stock 2 | 17 / 17 | 0.0000 | 0.00e+00 | 0.00e+00 | within |
| TS3010a.avi#56 | stock 1 vs stock 2 | 12 / 12 | 0.0000 | 0.00e+00 | 0.00e+00 | within |
| TS3010a.avi#56 | prototype 1 vs prototype 2 | 12 / 12 | 0.0000 | 0.00e+00 | 0.00e+00 | within |
| TS3010a.avi#56 | prototype 1 vs stock 1 | 12 / 12 | 0.0000 | 0.00e+00 | 0.00e+00 | within |
| TS3010a.avi#56 | prototype 2 vs stock 2 | 12 / 12 | 0.0000 | 0.00e+00 | 0.00e+00 | within |

| video | frames | OTHER frames where any two of the four runs disagree | frames where stock run 1 disagrees with the banked P1-D run |
|---|---|---|---|
| IN1002.avi | 165 | none | none |
| TS3010a.avi | 69 | none | 56 |
| IN1009.avi | 84 | none | none |

**P7-B Tier 1: UNCLASSIFIED.** Pattern: stock agrees with itself on both frames: yes; stock video-identical to the banked P1-D output on both videos: NO; the prototype agrees with itself on both frames: NO; frames where the prototype (run 1) disagrees with stock: IN1002.avi#58. None of STOCK VARIES, PROTOTYPE SHIFTS or CONDITION-DEPENDENT describes this pattern. **Tier reached: 1.** Tier 2 NOT RUN: G_tier2 did not fire (it fires only on CONDITION-DEPENDENT).

**POST-HOC, descriptive (added after Tier 1 ran; decides nothing):** the runs grouped by identical output on each named frame.

| frame | output | runs giving it | detections | top score | lowest score |
|---|---|---|---|---|---|
| IN1002.avi#58 | 1 | banked P1-D stock, p7b_stock_1, p7b_stock_2, p7b_p5_2 | 17 | 0.8572 | 0.3189 |
| IN1002.avi#58 | 2 | banked P6-B prototype | 18 | 0.8635 | 0.3017 |
| IN1002.avi#58 | 3 | p7b_p5_1 | 17 | 0.8568 | 0.3165 |
| TS3010a.avi#56 | 1 | banked P1-D stock | 12 | 0.8578 | 0.3206 |
| TS3010a.avi#56 | 2 | banked P6-B prototype, p7b_stock_1, p7b_stock_2, p7b_p5_1, p7b_p5_2 | 12 | 0.8578 | 0.3185 |

Stated plainly: on each frame one of the two images does not give one answer. On TS3010a.avi frame 56 STOCK itself gave 2 different outputs across sessions (the banked P1-D run, and today's two runs, which match every prototype run); so the P6-B difference on that frame does not need the prototype. On IN1002.avi frame 58 stock gave 1 output across its three runs while the prototype gave 3 different outputs across its three (P6-B, today's run 1, today's run 2 — which matches stock); so the prototype varies run to run on that frame where stock has not been seen to. Each change moves the whole frame (every score, and boxes by up to 7.00e-01 px on IN1002.avi), far beyond S5-B's tolerances; every other frame of the three videos agrees across all four runs (0 other frames disagree). What makes one frame of a video non-reproducible is not measured here.

## P7-C — P6-C round 2 (the thread count); P6-C's pooled reading

**CORRECTNESS (G_correct_C2, hard for P7-C): PASS** — p7c_p5t16_2 vs P0 v1_rr_def_a: 16 videos, identical yes.

| leg | session | forward F s | p50 | p99 | frames/s | CPU-s/frame |
|---|---|---|---|---|---|---|
| p6c_p5t16_1 | P6 | 0.3817 | 0.3741 | 0.8146 | 2.535 | 2.131 |
| p7c_p5t16_2 | P7 | 0.3963 | 0.3907 | 0.8181 | 2.443 | 2.298 |
| p6c_lit16_1 | P6 | 0.3555 | 0.3583 | 0.3830 | 2.654 | 1.420 |
| p7c_lit16_2 | P7 | 0.3588 | 0.3584 | 0.3829 | 2.629 | 1.487 |
| p6a_p5k16_1 | P6 | 0.2245 | 0.2114 | 0.5227 | 4.283 | 1.297 |
| p6a_p5k16_2 | P6 | 0.2317 | 0.2202 | 0.5233 | 4.157 | 1.337 |

|  | F(P5 T=16) / F(P5 T=4) | ≤ 0.95 (faster by ≥ 5%) | fps(P5 T=16) / fps(LI T=16) | against 0.95 |
|---|---|---|---|---|
| round 1 | 1.700 | no | 0.955 | ≥ 0.95 |
| round 2 | 1.711 | no | 0.929 | < 0.95 |
| pooled | 1.705 | no | 0.942 | < 0.95 |

**P6-C pooled (as P6 pre-registered it): T=16 is NOT faster by at least 5% (pooled); P5 T=16 / LlamaIndex T=16 = 0.942.** P6-C round 1 and P6-A (the T=4 reference) are in P6's box session; P7-C round 2 is in P7's. P6's pooled rule is applied as written; the canaries of both sessions are reported beside and adjust nothing.

### Canaries (P7, and P6's for the cross-session comparison)

| canary | mean forward s | frames |
|---|---|---|
| p7b_can_1 | 0.2043 | 239 |
| p7b_can_2 | 0.2038 | 239 |
| p7c_can_c2 | 0.2047 | 239 |
| P6 p6c_can_a1 | 0.2042 | 239 |
| P6 p6c_can_a2 | 0.2037 | 239 |
| P6 p6c_can_c1 | 0.1923 | 239 |

## P7-D (1) — upstream patch description draft (not filed, posted or sent)

Embedded from `P7_UPSTREAM_PATCH_DRAFT.md`.

> # DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)
>
> Updated in P7 (parity_p7_20260926T091049Z). Figures cite analysis_p5a.json, analysis_p6.json, p7a_frames.json and analysis_p7.json by key.
>
> ## What changed
>
> - `nodes/detect/IGlobal.py` (+11 / -6 lines): after building the one `Detector`, it starts an `InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of `make_device_lock()`; `endGlobal` stops the worker first.
> - `nodes/detect/IInstance.py` (+4 / -2 lines): the locked `detector.detect(image)` becomes `self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.
> - `nodes/detect/infer_worker.py` (new, 88 lines): each caller has at most one frame outstanding and blocks on its own `Future`, so a video's frames stay in order and each result returns to its caller.
> - Base files: IInstance.py md5 984d80e45e885b5ae21e987664850b4c, IGlobal.py md5 9edc29c94a5a34ba366d938d048e89fd — equal to the image's own node files [parity_p5 p5a_build.json base_node] (the local engine bundle, 3.3.1.35 per parity_p5_20260925T141647Z/PROGRESS_LOG.md:5, not in the repository). Patched: IGlobal.py 22fc2536b8b3bebdcc708375f9aa52e5, IInstance.py 780202974588b9d85287f2096c0b67bb, infer_worker.py b522c83ffeed93dca8de340e3b0b8799.
> - **The thread count is not changed.** The patch keeps today's default; every identity claim below compares it with the current node AT THE SAME thread count.
>
> ## Output identity — exactly what is claimed, and on what evidence
>
> - **16 videos, matched threads (T=4), 16 in flight:** identical to the current node (per-video chunk sha256 AND frame scores) on 16/16 in every ABAB comparison [analysis_p5a.json correctness.gate_pass = True; analysis_p6.json P6_A.correctness.gate_pass = True].
> - **16 videos, the out-of-box thread count (the six variables unset):** identical on 16/16 to the current node's committed out-of-box output [analysis_p6.json P6_C.correctness.gate_pass = True; analysis_p7.json P7_C.correctness_C2.pass = True].
> - **168 videos (23,049 frames):** 166 of 168 videos identical to ONE banked run of the current node from another session [P6_B.correctness_vs_p1d]; IN1002.avi, TS3010a.avi differ on one frame each. P7 re-ran those videos (two runs of each node, one session):
>   - TS3010a.avi frame 56: the CURRENT node gives 2 different outputs across sessions (the banked run, and two runs today that match every prototype run) [analysis_p7.json P7_B_tier1.per_frame.TS3010a.avi#56.post_hoc_distinct_outputs]. The difference does not need the patch.
>   - IN1002.avi frame 58: the current node gave 1 output in its 3 runs; the prototype gave 3 different outputs in its 3 runs, one of them equal to the current node's [..IN1002.avi#58.post_hoc_distinct_outputs]. On this frame the prototype varies run to run where the current node has not been seen to; the cause is not established.
>   - Each of these changes moves the whole frame — every score (up to 0.0173 in P6-B vs the banked run [p7a_frames.json frames.*.max_rank_paired_score_delta]) — not a detection on the 0.3 threshold [p7a_frames.json reading: NOT BOUNDARY]; every other frame of these videos agreed in all four P7 runs [P7_B_tier1.other_frames.*.other_frames_where_any_two_of_the_four_runs_disagree: 0 frames].
> - **So the claim is:** output-identical to the current node at matched threads on every video compared, except 2 frames of 23,049 where a single run is not a reference: on one (TS3010a.avi frame 56) the current node itself changed output across sessions; on the other (IN1002.avi frame 58) the prototype varied run to run where the current node has not (three runs each). On that frame the prototype is not shown output-identical.
>
> ## Mandate compliance
>
> - One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector`; the on-token D0 read exactly one LWDETR before and after every measured leg (P5, P6, P7 gate records G_d0).
> - Threads only: one extra thread (`detect-infer`) per task process.
>
> ## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB) [analysis_p6.json P6_A.cells.*]
>
> - Frames/s: 4.220 vs 2.419 (+74.4%); one LlamaIndex instance 3.149. 168 videos, block-interleaved: 4.089 vs one LlamaIndex instance 3.134 [P6_B.per_arm].
> - CPU-s per frame: 1.317 vs 1.489 (-11.5%); sampled memory peak 5,649 MB vs 7,583 MB.
>
> ## Known residual
>
> - With 16 videos in flight the forward pass is +17.2% longer than with one (median +12.5%, p99 +143.6%) [P6_A.descriptive_forward_degradation; cross-session reference] — a tail; its cause was not measured.
> - The run-to-run variation on IN1002.avi frame 58 above.
>
> ## What a reviewer should test
>
> - Output identity at the SAME thread count, on your own videos, at 1 and many in flight — and first the current node against ITSELF, several runs, so a mismatch can be attributed. Start with IN1002.avi frame 58 (run each node three or more times) and TS3010a.avi frame 56 (the current node alone changed output across sessions).
> - Teardown with frames queued; a frame whose detect raises; model-server (proxy) mode, where `make_device_lock()` was a no-op; the queue bound at very high concurrency.
> - Other code that used `IGlobal.device_lock` (none in the detect node itself).

## P7-D (2) — ticket draft: default intra-op thread count for the detect node (not filed, posted or sent)

Embedded from `P7_THREAD_TICKET_DRAFT.md`.

> # DRAFT — ticket: default intra-op thread count for the detect node (not filed, posted or sent)
>
> Figures cite analysis_p7.json P7_C (P6-C round 1 + P7-C round 2), analysis_p6.json P6_A and S5-A's analysis_output_shift.json by key.
>
> ## What
>
> The detect node leaves the six thread variables unset, so torch runs its default intra-op pool (16 threads on the benchmark box, read back in-process [parity_p7 gates/G_cell_p7c_p5t16_2.json]). This ticket asks whether that default should change. It is separate from the single-inference-thread patch, which keeps today's default.
>
> ## Speed at 4 vs 16 threads (with the single inference thread; 16 videos, 16 in flight; one LlamaIndex instance beside)
>
> - The forward pass takes 1.705x as long at 16 threads as at 4 (pooled over two rounds) [P7_C.readings.pooled.F_t16_over_F_t4] — SLOWER; per round 1.700 and 1.711 [..round_1, ..round_2].
> - Frames/s: 2.489 at 16 threads [..pooled.fps_p5_t16_mean] vs 4.220 at 4 threads [analysis_p6.json P6_A.cells.p5_k16.frames_per_s.mean]; one LlamaIndex instance at 16 threads 2.642 [..pooled.fps_li_t16_mean].
> - Caveat: the 16-thread rounds and the 4-thread reference are in different stages and sessions (not ABAB); the canaries are reported beside in the P7 report and adjust nothing.
>
> ## Output effect, stated plainly (S5-A, 16 videos, the current node) [batchsize_s5 analysis_output_shift.json s5a_thread_width_vs_default]
>
> - At 4 threads vs today's default: labels identical on 3,203 of 3,203 frames, but scores shift (by at least 1.96e-03) and 0 of 16 videos are chunk-identical.
> - Only unset / 16 threads reproduces today's default output: 16 of 16 videos chunk-identical, score shift 0.0.
> - So changing the default changes every downstream score (not the labels, on this set); consumers that store or compare scores would see a one-time shift.
>
> ## Asked
>
> - Decide whether a speed gain justifies a one-time output change; measure it at matched concurrency on your own hardware first (the reading above is one box type).
> - Whatever the default, record the thread count with every output so runs can be compared.

## P7-D (3) — CTO brief draft (not sent, posted or filed)

Embedded from `P7_CTO_BRIEF_DRAFT.md`.

> # DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)
>
> Figures cite the P4 facts sheet [Fnn], the Stage 4 analysis, analysis_p6.json or analysis_p7.json by key.
>
> **What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against ONE LlamaIndex instance.
>
> ## Documents (one token vs LlamaIndex's 24-worker optimum)
>
> - **Matches, not beats.** 6.2969 [F01] vs 5.9046 [F02] docs/s: 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread; steady-phase ABAB ratios 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].
> - **Needs an unshipped fix.** Stock 2.3454 [F15] docs/s; with the Tika wrapper fix 5.3441 [F17] (+127.85% [F18]), 0 of 9,885 [F20] chunk lists changed; the measured fix disables inline-image extraction for every pipeline (breaks image pipelines) — the shippable form is the source change in parity_p2 P2D_WRAPPER_TICKET_DRAFT.md:12.
> - **Costs.** CPU per document 4.442 [F05] vs 3.881 [F06] s; memory peak 21,826 [F11] vs 18,069 [F12] MB; idle spin 1.234 [F09] vs 0.026 [F10] cores. **Out of the box:** 2.3454 [F15] docs/s, 7.706 [F16] CPU-s per document.
>
> ## Video (one token vs ONE LlamaIndex instance)
>
> - **Stock.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one stock token at 16 in flight (T=4); out of the box 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame. Cause (P4): at 16 in flight RocketRide's forward slows x1.867 [F58], LlamaIndex's x1.403 [F59].
> - **The single inference thread (a prototype, not shipped):** 4.220 vs one LlamaIndex instance 3.149 frames/s — parity 1.340 [P6_A.readings.Q1.pooled.ratio], 1.744x stock [..Q2.pooled.ratio]; 168 videos block-interleaved 1.304 [P6_B.ratio_rr_over_li_totals].
> - **Output (P7).** Identical to stock at matched threads on every 16-video comparison; on 168 videos 166 of 168 matched one banked stock run [P6_B.correctness_vs_p1d]. The two misses are single frames where one run is not a reference: stock itself changed output across sessions on one [P7_B_tier1 TS3010a.avi#56], and the prototype varied run to run on the other where stock did not in three runs [P7_B_tier1 IN1002.avi#58]. Not a threshold artifact [p7a_frames.json: NOT BOUNDARY].
> - **Thread count.** With the single inference thread, the forward takes 1.71x as long at 16 threads as at 4 [P7_C.readings.pooled.F_t16_over_F_t4] (T=16 is NOT faster by at least 5% (pooled); cross-session); T=4 stays the posture. Changing the default thread count changes scores (S5-A) — a separate ticket, drafted.
> - **Context, not the comparison:** LlamaIndex's multi-instance configuration — 8 instances x 4 threads — runs 13.52 frames/s (Stage 4) [batchsize_s4 p5_li_video/analysis_video.json legs.0.frames_per_s; posture workers[declared_workers=8]; threads li_k16 export provenance_video.posture.threads_env_in_process_torch].
>
> ## Not claimed
>
> - That RocketRide BEATS LlamaIndex on documents; any unshipped fix or prototype figure as shipped behaviour; any cross-session ratio as a comparison; output identity on the two non-reproducible frames.

## NOT RUN

- P7-B Tier 2: G_tier2 did not fire — the Tier 1 reading is UNCLASSIFIED, and Tier 2 was pre-registered to run only on CONDITION-DEPENDENT.

## Methodology register

- 65, addendum (P7): the banked stock output is not reproducible on one of the two frames (TS3010a.avi frame 56: the banked P1-D run vs today's two stock runs) and the prototype is not reproducible run to run on the other (IN1002.avi frame 58); a single run is not a reference for these frames.
- 66 — three readings that did not cover what happened: P7-B's pattern fit none of STOCK VARIES, PROTOTYPE SHIFTS or CONDITION-DEPENDENT; the pre-registered UNCLASSIFIED branch named it. A classification needs a named residual reading, and 'stable' must say over runs, sessions or both.

## SELF-AUDIT

- **1. HYPOTHESIS:** every reading was stated before its data in preregistration.json (committed 06a9d543, before P7-A was computed and before any leg); the look at the two frames' scores before that file is recorded in it; P7-A's reading rule is Ansh's verbatim; the Tier 1 output grouping is POST-HOC and labelled so.
- **2. EVIDENCE:** every figure is computed by working/scripts/p7_report.py from p7a_frames.json (p7_frames.py over committed exports), analysis_p7.json (p7_analyse.py over the raw legs), the gate and gate-control records, the chain records and the box log; the drafts from the same files and the committed P4, P5, P6 and S5 artifacts they cite.
- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json; G_tier2's controls also had to give their reading); the driver's capture flag has a laptop test with null controls; the blind recomputation's planted figures had to be caught.
- **4. REGISTER:** 3, 48, 54-59, 61, 62 (ABAB and the canary), 64 (fixed tolerances), 65 (and its P7 addendum); new: 66.
- **5. NOT VERIFIED:** what makes one frame of a video non-reproducible; whether boxes moved on the P6-B frames (no committed export records boxes); the cross-session thread-count comparison is not ABAB-protected; the drafts are drafts.
- **6. GATES:** every landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg; image ids read back at each stage's start and end (rr:p5-infer not rebuilt); the box stopped with box.sh stop and its state read back.

