# P6 — the single inference thread against one LlamaIndex instance; the out-of-box thread count; two drafts

Campaign `parity_p6_20260925T175225Z`, branch feat/parity-p6 (from feat/parity-p5 c76bb99c). Generated 2026-09-26T03:00:21Z from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison inside a stage is interleaved ABAB; tolerances are FIXED (register 64); the canary adjusts nothing.

## Summary

- P6-A correctness: rr:p5-infer's output is identical to stock on 16/16 videos in both rounds.
- Q1 PARITY (P5 / one LlamaIndex instance >= 0.95): HOLDS (pooled); round 1 holds, round 2 holds — 1.359 in round 1, 1.321 in round 2, 1.340 pooled (4.220 vs 3.149 frames/s).
- Q2 SPEEDUP (P5 / stock >= 1.20): HOLDS (pooled); round 1 holds, round 2 holds — 1.748, 1.741, 1.744 pooled (stock 2.419 frames/s).
- Forward degradation (descriptive, never gated; cross-session reference): mean +17.21%, p50 +12.55%, p99 +143.62% against P5's one-video forward.
- P6-B (168 videos, block-interleaved, warm-symmetric): RocketRide P5 4.089 vs one LlamaIndex instance 3.134 frames/s — ratio 1.304 against 0.95 (meets); per block 0.987 to 1.351 (median 1.311); output vs the banked stock run: 2 of 168 differ (IN1002.avi, TS3010a.avi; cause not established — register 65).
- P6-C (T=16, six vars unset): round 2 NOT RUN (the budget), so the pooled reading is NOT EVALUABLE. Round 1: the P5 forward at T=16 is 1.700x its T=4 forward (the bar is 0.95: NOT faster — slower); P5 T=16 / LlamaIndex T=16 = 0.955 (reported against 0.95); output identical to the out-of-box reference on 16/16; cross-stage, not ABAB-protected.
- Drift: the canary did NOT move (within the 0.82% floor) (canary -0.28% from P6-A round 1 to round 2; P6-A cells' median +2.59%).
- Both drafts (the CTO brief and the upstream patch description) are below; neither is sent, posted or filed.

## Step 0 and the recorded statements

- sso: checked 17:43Z: role credentials valid to 19:31Z — within 2 h of expiry, so a login was required; Ansh approved it at 17:44Z (the new SSO session carries a refresh token and outlasts the 8 h budget)
- autoland_self_test: 71 pass, 0 fail
- origin: feat/parity-p5 on origin = c76bb99c; feat/parity-p6 created from it
- p5_verdict_stands: P5's verdict stands unchanged: S1 does not hold, P5-B NOT RUN. P6 is a NEW experiment informed by P5's data, not a re-reading of P5.
- register_64_applied: every equivalence or superiority claim in P6 uses a FIXED tolerance stated here, never a noise-derived one. P5's forward clause asked for zero degradation under concurrent decoding, which LlamaIndex itself does not achieve (1.40x in P4); P6 reports forward degradation as a number and never gates on it.
- addendum 1 (before the first measured leg): P5's committed rule (parity_p5_20260925T141647Z/preregistration.json P5_C_laptop (2)), applied to P6-A: the canary MOVED iff |F(p6c_can_a2) / F(p6c_can_a1) - 1| > 0.82% (the RR floor); it moved WITH the cells iff it moved in the same direction as the median of the P6-A cells' round-2 / round-1 forward changes (stock, P5, LlamaIndex). The P6-B canaries (before block 1, after block 6) and the P6-C canaries (before each P6-C round) are reported beside, in time order, with the same arithmetic. No figure is adjusted.

## Gates

| gate | rule | measured | outcome |
|---|---|---|---|
| G_d0 (every leg / block / canary it applies to) | preregistration.json gates | p6a_li16_1: CLEAN; p6a_li16_2: CLEAN; p6a_p5k16_1: CLEAN; p6a_p5k16_2: CLEAN; p6a_stock16_1: CLEAN; p6a_stock16_2: CLEAN; p6b_li_b01: CLEAN; p6b_li_b02: CLEAN; p6b_li_b03: CLEAN; p6b_li_b04: CLEAN; p6b_li_b05: CLEAN; p6b_li_b06: CLEAN; p6b_li_b07: CLEAN; p6b_li_b08: CLEAN; p6b_li_b09: CLEAN; p6b_li_b10: CLEAN; p6b_li_b11: CLEAN; p6b_li_startwarm: CLEAN; p6b_rr_b01: CLEAN; p6b_rr_b02: CLEAN; p6b_rr_b03: CLEAN; p6b_rr_b04: CLEAN; p6b_rr_b05: CLEAN; p6b_rr_b06: CLEAN; p6b_rr_b07: CLEAN; p6b_rr_b08: CLEAN; p6b_rr_b09: CLEAN; p6b_rr_b10: CLEAN; p6b_rr_b11: CLEAN; p6b_rr_startwarm: CLEAN; p6c_lit16_1: CLEAN; p6c_p5t16_1: CLEAN | ALL CLEAN |
| G_cell (every leg / block / canary it applies to) | preregistration.json gates | p6a_li16_1: PASS; p6a_li16_2: PASS; p6a_p5k16_1: PASS; p6a_p5k16_2: PASS; p6a_stock16_1: PASS; p6a_stock16_2: PASS; p6b_li_b01: PASS; p6b_li_b02: PASS; p6b_li_b03: PASS; p6b_li_b04: PASS; p6b_li_b05: PASS; p6b_li_b06: PASS; p6b_li_b07: PASS; p6b_li_b08: PASS; p6b_li_b09: PASS; p6b_li_b10: PASS; p6b_li_b11: PASS; p6b_li_startwarm: PASS; p6b_rr_b01: PASS; p6b_rr_b02: PASS; p6b_rr_b03: PASS; p6b_rr_b04: PASS; p6b_rr_b05: PASS; p6b_rr_b06: PASS; p6b_rr_b07: PASS; p6b_rr_b08: PASS; p6b_rr_b09: PASS; p6b_rr_b10: PASS; p6b_rr_b11: PASS; p6b_rr_startwarm: PASS; p6c_lit16_1: PASS; p6c_p5t16_1: PASS | ALL PASS |
| G_warm (every leg / block / canary it applies to) | preregistration.json gates | p6b_li_b01: PASS; p6b_li_b02: PASS; p6b_li_b03: PASS; p6b_li_b04: PASS; p6b_li_b05: PASS; p6b_li_b06: PASS; p6b_li_b07: PASS; p6b_li_b08: PASS; p6b_li_b09: PASS; p6b_li_b10: PASS; p6b_li_b11: PASS; p6b_li_startwarm: PASS; p6b_rr_b01: PASS; p6b_rr_b02: PASS; p6b_rr_b03: PASS; p6b_rr_b04: PASS; p6b_rr_b05: PASS; p6b_rr_b06: PASS; p6b_rr_b07: PASS; p6b_rr_b08: PASS; p6b_rr_b09: PASS; p6b_rr_b10: PASS; p6b_rr_b11: PASS; p6b_rr_startwarm: PASS | ALL PASS |
| G_canary (every leg / block / canary it applies to) | preregistration.json gates | p6c_can_a1: PASS; p6c_can_a2: PASS; p6c_can_b0: PASS; p6c_can_bmid: PASS; p6c_can_c1: PASS | ALL PASS |
| G_alone (before every leg and canary, and the P6-B stage) | no container on the box (P6-B's canaries: no RUNNING container; the paused arms allowed) | box_logs/p6_run.log: 12 checks, containers present = 0; running-only check on p6c_can_b0, p6c_can_bmid; NOT_ALONE entries in the chain record: 0 | PASS |
| G_memstat (first leg) | memstat.jsonl ≥ 1 row | p6a_stock16_1: 1,425 rows | PASS |
| G_correct_A1 (HARD) | P5 output identical on 16/16 (A: to stock in the round; C1: to the out-of-box reference P0 v1_rr_def_a) | p6a_p5k16_1 vs p6a_stock16_1: identical, 16 videos | PASS |
| G_correct_A2 (HARD) | P5 output identical on 16/16 (A: to stock in the round; C1: to the out-of-box reference P0 v1_rr_def_a) | p6a_p5k16_2 vs p6a_stock16_2: identical, 16 videos | PASS |
| G_correct_C1 (HARD) | P5 output identical on 16/16 (A: to stock in the round; C1: to the out-of-box reference P0 v1_rr_def_a) | p6c_p5t16_1 vs v1_rr_def_a: identical, 16 videos | PASS |
| G_smoke_P6B | correctness both rounds AND Q1 in round 1, round 2 and pooled | Q1 HOLDS (pooled); round 1 holds, round 2 holds | FIRED |
| image ids | rr:patched, rr:patched-video unchanged; rr:p5-infer = P5's, not rebuilt | rr:patched sha256:073b43d8b5f9 rr:patched-video sha256:b7f51acc9533 rr:p5-infer sha256:b42c03b69f17 | UNCHANGED |
| budget | 8 h from the run stage's first leg | run start 2026-09-25T18:15:35Z; first leg 18:15:37Z; deadline 2026-09-26T02:15:37Z; chain done 2026-09-26T02:50:50Z | SEE NOT RUN |

### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)

**gate_controls.json** (run 1, boot eb83839f): 33 of 33 controls as expected → all_pass **True**.

| gate | positive control(s) (must PASS) | null control(s) (must FAIL) |
|---|---|---|
| G_memstat | P5 p5a_stock16_1 → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no memory sampler) → as expected (FAIL (rc 1)) |
| G_d0 rr | P5 p5a_p5k16_1 → as expected (PASS (rc 0))<br>the control leg p6ctl_p5t16 (out of box) → as expected (PASS (rc 0)) | batchsize_smoke rr_k16 (no on-token D0: absence) → as expected (FAIL (rc 2))<br>a copy of p5a_p5k16_1 whose post-leg D0 counts TWO LWDETR instances → as expected (FAIL (rc 1)) |
| G_d0 li | P5 p5a_li16_1 → as expected (PASS (rc 0))<br>the control leg p6ctl_lit16 → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (eight LlamaIndex containers) → as expected (FAIL (rc 1)) |
| G_cell p5 T=4 | P5 p5a_p5k16_1 → as expected (PASS (rc 0)) | p6ctl_p5t16 against T=4 (torch 16, the six vars unset) → as expected (FAIL (rc 1)) |
| G_cell p5 T=16 unset | the control leg p6ctl_p5t16 → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 against T=16 unset (torch 4, vars set) → as expected (FAIL (rc 1)) |
| G_cell li T=16 | the control leg p6ctl_lit16 → as expected (PASS (rc 0)) | P5 p5a_li16_1 against T=16 (torch 4) → as expected (FAIL (rc 1)) |
| G_cell stock T=4 | P5 p5a_stock16_1 → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 against the stock spec (image, stamps) → as expected (FAIL (rc 2)) |
| G_cell li T=4 | P5 p5a_li16_1 → as expected (PASS (rc 0)) | batchsize_smoke li_k16 (no read-back) → as expected (FAIL (rc 2)) |
| G_warm | the control leg p6ctl_warm_rr (2 at 2) → as expected (PASS (rc 0))<br>the control leg p6ctl_warm_li (2 at 2) → as expected (PASS (rc 0)) | P5 p5a_p5k16_1 (the default warm policy, nothing declared) → as expected (FAIL (rc 1))<br>p6ctl_warm_rr against 16 at 16 → as expected (FAIL (rc 1)) |
| G_canary | P5 p5c_can_1 (committed canary) → as expected (PASS (rc 0)) | P3 p3b_a_1 (the same bench over all three videos) → as expected (FAIL (rc 1)) |
| G_correct | P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16) → as expected (PASS (rc 0))<br>P0 v1_rr_def_b vs v1_rr_def_a (identical 16/16) → as expected (PASS (rc 0)) | P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16) → as expected (FAIL (rc 1))<br>P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos) → as expected (FAIL (rc 1)) |
| G_smoke_P6B | P6-A cells = P5's stock / P5 / LI K=16 legs (Q1 1.35 and 1.40, identical output) → as expected (PASS (rc 0)) | the 'P5' cell = P5's STOCK legs (P5/LI below 0.95; output identical) → as expected (FAIL (rc 1)) |
| G_alone | no container on the box → as expected (PASS (rc 0)) | one created container present → as expected (FAIL (rc 1)) |

## P6-A — smoke, T=4, 16 videos, K=16, two ABAB rounds

### Correctness first

| P5 vs stock (same round) | videos compared | identical |
|---|---|---|
| p6a_p5k16_1 vs p6a_stock16_1 | 16 | yes |
| p6a_p5k16_2 vs p6a_stock16_2 | 16 | yes |

**CORRECTNESS (hard): PASS.**

Beside:

| comparison | legs | videos | identical |
|---|---|---|---|
| stock run to run | p6a_stock16_1 vs p6a_stock16_2 | 16 | yes |
| p5 run to run | p6a_p5k16_1 vs p6a_p5k16_2 | 16 | yes |
| li run to run | p6a_li16_1 vs p6a_li16_2 | 16 | yes |

### Per cell (round 1 / round 2; mean (spread of the two ABAB runs))

| cell | frames/s | forward F s | forward p50 s | forward p99 s | inference duty | cores busy in the forward | CPU-s/frame | sampled memory peak |
|---|---|---|---|---|---|---|---|---|
| RR stock K=16 | 2.450 / 2.388; 2.419 (2.54%) | 0.3955 / 0.4057; 0.4006 (2.56%) | 0.3977 / 0.4084; 0.4031 (2.66%) | 0.5318 / 0.5495; 0.5406 (3.27%) | 99.93% / 99.93%; 99.93% (0.00%) | 2.39 / 2.39; 2.39 (0.33%) | 1.469 / 1.509; 1.489 (2.65%) | 7,594 MB / 7,573 MB |
| RR P5 K=16 | 4.283 / 4.157; 4.220 (2.99%) | 0.2245 / 0.2317; 0.2281 (3.18%) | 0.2114 / 0.2202; 0.2158 (4.06%) | 0.5227 / 0.5233; 0.5230 (0.11%) | 99.93% / 99.97%; 99.95% (0.04%) | 4.21 / 4.21; 4.21 (0.06%) | 1.297 / 1.337; 1.317 (3.06%) | 5,516 MB / 5,783 MB |
| LlamaIndex K=16 | 3.151 / 3.148; 3.149 (0.10%) | 0.2972 / 0.2974; 0.2973 (0.08%) | 0.3352 / 0.3248; 0.3300 (3.15%) | 0.4142 / 0.4110; 0.4126 (0.76%) | 100.00% / 100.00%; 100.00% (0.00%) | 2.70 / 2.75; 2.73 (1.89%) | 0.928 / 0.947; 0.937 (1.97%) | 5,387 MB / 5,358 MB |

### Per leg

| leg | count | mean | sd | p50 | p90 | p99 | max | inference duty | queue depth mean / p50 / max | frames/s | CPU-s/frame | steal, MHz open→close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p6a_stock16_1 | 3,203 | 0.3955 | 0.0320 | 0.3977 | 0.4167 | 0.5318 | 0.6638 | 99.93% | — | 2.450 | 1.469 | steal 0.006%, 2953→2637 MHz |
| p6a_p5k16_1 | 3,203 | 0.2245 | 0.0523 | 0.2114 | 0.2286 | 0.5227 | 0.5759 | 99.93% | 12.80 / 15 / 15 | 4.283 | 1.297 | steal 0.005%, 2981→2712 MHz |
| p6a_li16_1 | 3,203 | 0.2972 | 0.0962 | 0.3352 | 0.4029 | 0.4142 | 0.6738 | 100.00% | — | 3.151 | 0.928 | steal 0.006%, 3033→2609 MHz |
| p6a_stock16_2 | 3,203 | 0.4057 | 0.0316 | 0.4084 | 0.4242 | 0.5495 | 0.7322 | 99.93% | — | 2.388 | 1.509 | steal 0.006%, 2958→2716 MHz |
| p6a_p5k16_2 | 3,203 | 0.2317 | 0.0543 | 0.2202 | 0.2277 | 0.5233 | 0.7132 | 99.97% | 12.81 / 15 / 15 | 4.157 | 1.337 | steal 0.005%, 2864→2724 MHz |
| p6a_li16_2 | 3,203 | 0.2974 | 0.0884 | 0.3248 | 0.3978 | 0.4110 | 0.4688 | 100.00% | — | 3.148 | 0.947 | steal 0.006%, 2926→2649 MHz |

### Q1 and Q2 (fixed tolerances), per round and pooled

|  | Q1: fps(P5) / fps(LI) | ≥ 0.95 | Q2: fps(P5) / fps(stock) | ≥ 1.20 |
|---|---|---|---|---|
| round 1 | 1.359 | HOLDS | 1.748 | HOLDS |
| round 2 | 1.321 | HOLDS | 1.741 | HOLDS |
| pooled | 1.340 | HOLDS | 1.744 | HOLDS |

**Q1: HOLDS (pooled); round 1 holds, round 2 holds. Q2: HOLDS (pooled); round 1 holds, round 2 holds.**

**Forward degradation (DESCRIPTIVE ONLY, never gated; the one-video reference is P5's committed K=1 legs, another session):** mean +17.21% (P5 K=16 0.2281 s vs 0.1946 s), p50 +12.55% (0.2158 vs 0.1918 s), p99 +143.62% (0.5230 vs 0.2147 s).

Stated plainly, per round and pooled: Q1 holds in round 1 (1.359) and in round 2 (1.321); pooled 1.340 — HOLDS. Q2: round 1 1.748, round 2 1.741, pooled 1.744 — HOLDS pooled. POST-HOC, about the descriptive figure only: its one-video reference is P5's session, and this session's canary (P6-A rounds, mean 0.2040 s) read +8.73% against P5's canaries (mean 0.1876 s) — part of the +17.21% is the box, not the node; nothing is adjusted.

## P6-B — 168 videos, block-interleaved, warm-symmetric

| block leg | videos | errors | frames | span s | frames/s | D0 | cell | warm | paused arm (state, CPU during block) |
|---|---|---|---|---|---|---|---|---|---|
| p6b_rr_b01 | 16 | 0 | 3,203 | 800.6 | 4.001 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b01 | 16 | 0 | 3,203 | 1044.0 | 3.068 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b02 | 16 | 0 | 2,071 | 500.8 | 4.135 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b02 | 16 | 0 | 2,071 | 668.3 | 3.099 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b03 | 16 | 0 | 1,922 | 475.6 | 4.041 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b03 | 16 | 0 | 1,922 | 619.3 | 3.104 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b04 | 16 | 0 | 1,686 | 411.9 | 4.093 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b04 | 16 | 0 | 1,686 | 546.8 | 3.083 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b05 | 16 | 0 | 2,120 | 501.3 | 4.229 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b05 | 16 | 0 | 2,120 | 663.3 | 3.196 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b06 | 16 | 0 | 2,846 | 715.7 | 3.977 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b06 | 16 | 0 | 2,846 | 934.3 | 3.046 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b07 | 16 | 0 | 1,807 | 464.8 | 3.888 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b07 | 16 | 0 | 1,807 | 609.5 | 2.965 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b08 | 16 | 0 | 1,659 | 424.5 | 3.908 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b08 | 16 | 0 | 1,659 | 550.2 | 3.015 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b09 | 16 | 0 | 2,354 | 568.0 | 4.144 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b09 | 16 | 0 | 2,354 | 755.1 | 3.117 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b10 | 16 | 0 | 2,339 | 546.6 | 4.279 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b10 | 16 | 0 | 2,339 | 738.2 | 3.169 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |
| p6b_rr_b11 | 8 | 0 | 1,042 | 227.7 | 4.576 | CLEAN | PASS | PASS | li_bal_0: true paused, 0.000 CPU-s |
| p6b_li_b11 | 8 | 0 | 1,042 | 224.7 | 4.637 | CLEAN | PASS | PASS | rr: true paused, 0.000 CPU-s |

| arm | blocks | videos | errors | frames | Σ span s | total frames/s |
|---|---|---|---|---|---|---|
| rr | 11 | 168 | 0 | 23,049 | 5637.5 | 4.089 |
| li | 11 | 168 | 0 | 23,049 | 7353.7 | 3.134 |

| arm, over the blocks BOTH arms ran | blocks | videos | frames | Σ span s | total frames/s |
|---|---|---|---|---|---|
| rr | 11 | 168 | 23,049 | 5637.5 | 4.089 |
| li | 11 | 168 | 23,049 | 7353.7 | 3.134 |

All 168 videos on both arms: **yes**. Over the 11 blocks both arms ran (beside the pre-registered totals, so both arms cover the same videos): RR/LI **1.304** (meets 0.95).

RR/LI of the totals: **1.304** against Q1's 0.95 (meets); per-block ratio over 11 blocks: min 0.987, p50 1.311, max 1.351. Start warms: p6b_rr_startwarm: PASS, p6b_li_startwarm: PASS.

**Correctness vs the banked P1-D stock output:** 166 of 168 videos identical; differ: IN1002.avi (frame index 58 of 165); TS3010a.avi (frame index 56 of 69). Whether the patch or run-to-run variation in stock causes it is not established: stock was never replicated on these videos (register 65).

11 RocketRide and 11 LlamaIndex blocks ran (168 and 168 videos; errors 0 and 0). Every block ran. The paused arm used at most 0.000 CPU-s during any block. POST-HOC: the lowest per-block ratio (0.987) is block 11, which holds 8 videos (so at most that many in flight).

## P6-C — the out-of-box thread count (T=16), smoke

| P5 T=16 vs the out-of-box reference | videos compared | identical |
|---|---|---|
| p6c_p5t16_1 vs P0 v1_rr_def_a (out of box, committed) | 16 | yes |

**CORRECTNESS: PASS.**

| cell | frames/s | forward F s | forward p50 s | forward p99 s | inference duty | cores busy in the forward | CPU-s/frame | sampled memory peak |
|---|---|---|---|---|---|---|---|---|
| RR P5 T=16 (six vars unset) | 2.535 / —; — (—) | 0.3817 / —; — (—) | 0.3741 / —; — (—) | 0.8146 / —; — (—) | 99.99% / —; — (—) | 4.22 / —; — (—) | 2.131 / —; — (—) | 5,716 MB / — |
| LlamaIndex T=16 | 2.654 / —; — (—) | 0.3555 / —; — (—) | 0.3583 / —; — (—) | 0.3830 / —; — (—) | 100.00% / —; — (—) | 3.62 / —; — (—) | 1.420 / —; — (—) | 6,873 MB / — |

| leg | count | mean | sd | p50 | p90 | p99 | max | inference duty | queue depth mean / p50 / max | frames/s | CPU-s/frame | steal, MHz open→close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p6c_p5t16_1 | 3,203 | 0.3817 | 0.0535 | 0.3741 | 0.3887 | 0.8146 | 0.8962 | 99.99% | 12.95 / 15 / 15 | 2.535 | 2.131 | steal 0.005%, 3044→2718 MHz |
| p6c_lit16_1 | 3,203 | 0.3555 | 0.0173 | 0.3583 | 0.3716 | 0.3830 | 0.4054 | 100.00% | — | 2.654 | 1.420 | steal 0.006%, 2957→2619 MHz |
| p6c_p5t16_2 | NOT RUN / absent | — | — | — | — | — | — | — | — | — | — | — | — |
| p6c_lit16_2 | NOT RUN / absent | — | — | — | — | — | — | — | — | — | — | — | — |

|  | F(P5 T=16) / F(P5 T=4, P6-A) | ≤ 0.95 (faster by ≥ 5%) | fps(P5 T=16) / fps(LI T=16) | against 0.95 |
|---|---|---|---|---|
| round 1 | 1.700 | no | 0.955 | ≥ 0.95 |
| round 2 | — | — | — | — |
| pooled | — | — | — | — |

**P6-C: pooled NOT EVALUABLE (round 2 NOT RUN); round 1 alone: NOT faster.** P6-A's T=4 legs and P6-C's T=16 legs are in different stages of the session (not ABAB); the canary per round is reported beside.

Stated plainly: round 2 was NOT RUN (the budget), so the pre-registered pooled reading is NOT EVALUABLE. Round 1 alone: at T=16 (the out-of-box posture) the single-inference-thread node's forward is 1.700x its T=4 forward in P6-A's round 1 — slower, the opposite of the hypothesis — and it runs 0.955 of one LlamaIndex instance at T=16. Its output is identical to the committed out-of-box stock output on 16/16. This comparison crosses stages of the session (not ABAB).

## Canary drift note

| canary (time order) | mean forward s | vs the first canary |
|---|---|---|
| p6c_can_a1 | 0.2042 | +0.00% |
| p6c_can_a2 | 0.2037 | -0.28% |
| p6c_can_b0 | 0.2090 | +2.31% |
| p6c_can_bmid | 0.1914 | -6.27% |
| p6c_can_c1 | 0.1923 | -5.85% |
| p6c_can_c2 | — | — |

|  | value |
|---|---|
| canary change, P6-A round 2 / round 1 − 1 | -0.28% |
| P6-A cells' forward change, round 2 / round 1 − 1 | stock_k16 +2.59%; p5_k16 +3.23%; li_k16 +0.08% |
| their median | +2.59% |

**Reading (addendum 1's rule): the canary did NOT move (within the 0.82% floor).** No figure is adjusted.

## P6-D (1) — CTO brief draft (not sent, posted or filed)

Embedded from `P6_CTO_BRIEF_DRAFT.md`.

> # DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)
>
> Figures cite the P4 facts sheet [Fnn] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md), the Stage 4 analysis, or the P6 analysis (parity_p6_20260925T175225Z/analysis_p6.json) by key.
>
> **What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against ONE LlamaIndex instance.
>
> ## Documents (one token vs LlamaIndex's 24-worker optimum)
>
> - **Matches, not beats.** 6.2969 [F01] vs 5.9046 [F02] docs/s on the full corpus: 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread; the steady-phase ABAB ratios on the 384 slice agree in two sessions: 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].
> - **Needs an unshipped fix.** Stock 2.3454 [F15] docs/s; with the Tika wrapper fix 5.3441 [F17] (+127.85% [F18]), 0 of 9,885 [F20] chunk lists changed. The fix measured is a one-byte patch that turns inline-image extraction off for every pipeline, which breaks image pipelines; the shippable form is the source change in parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12.
> - **Costs.** CPU per document 4.442 [F05] vs 3.881 [F06] s; sampled memory peak 21,826 [F11] vs 18,069 [F12] MB; idle spin 1.234 [F09] vs 0.026 [F10] cores.
> - **Out of the box** (stock image): 2.3454 [F15] docs/s at 7.706 [F16] CPU-s per document; no same-session LlamaIndex run, no ratio.
>
> ## Video (one token vs ONE LlamaIndex instance)
>
> - **Stock.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one stock RocketRide token at 16 videos in flight (T=4); out of the box RocketRide runs 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame.
> - **Mechanism (P4).** From one video in flight to sixteen RocketRide's forward slows x1.867 [F58], LlamaIndex's x1.403 [F59]: 16 caller threads take turns at the model frame by frame.
> - **The single inference thread (rr:p5-infer, a benchmark prototype, not shipped), output identical to stock on 16/16 in both rounds** [P6_A.correctness.gate_pass]: 4.220 frames/s [P6_A.cells.p5_k16.frames_per_s.mean] vs one LlamaIndex instance 3.149 [P6_A.cells.li_k16.frames_per_s.mean] and stock 2.419 [P6_A.cells.stock_k16.frames_per_s.mean]: parity 1.340 [P6_A.readings.Q1.pooled.ratio] (Q1 >= 0.95: HOLDS (pooled); round 1 holds, round 2 holds), speedup 1.744x [P6_A.readings.Q2.pooled.ratio] (Q2 >= 1.20: HOLDS (pooled); round 1 holds, round 2 holds).
> - **Known residual (descriptive, cross-session).** Its forward at 16 in flight is +17.2% over one video in flight [P6_A.descriptive_forward_degradation.F_over_ref_minus_1]: median +12.5%, p99 +143.6% [..p50_over_ref_minus_1, ..p99_over_ref_minus_1] — a tail.
> - **168 videos, block-interleaved:** RocketRide 4.089 vs LlamaIndex 3.134 frames/s [P6_B.per_arm.*.total_frames_per_s], ratio 1.304 [P6_B.ratio_rr_over_li_totals] against 0.95; per block 0.987 to 1.351 (median 1.311) [P6_B.per_block_ratio_distribution]; output vs the banked stock run: 166 of 168 identical; IN1002.avi, TS3010a.avi differ — cause not established (stock never replicated on them) [P6_B.correctness_vs_p1d].
> - **Out-of-box threads (T=16) with the single inference thread, one round (the second was cut by the budget):** forward 1.700x the T=4 forward [P6_C.readings.round_1.F_t16_over_F_t4] — slower, not faster; frames/s vs one LlamaIndex instance at T=16 0.955 [P6_C.readings.round_1.fps_p5_t16_over_li_t16]; T=4 remains the posture to use.
> - **Context, not the comparison:** LlamaIndex's multi-instance video configuration — 8 instances x 4 threads — runs 13.52 frames/s on the 168 videos (Stage 4) [batchsize_s4_20260921T013303Z/p5_li_video/analysis_video.json legs.0.frames_per_s; posture workers[declared_workers=8]]. That is eight model instances; the comparisons above hold RocketRide to one token and LlamaIndex to one instance.
>
> ## What is not claimed
>
> - That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).
> - Any figure from an unshipped fix or prototype as shipped behaviour.
> - Any cross-session ratio as a comparison.

## P6-D (2) — upstream patch description draft (not filed, posted or sent)

Embedded from `P6_UPSTREAM_PATCH_DRAFT.md`.

> # DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)
>
> ## What changed
>
> - `nodes/detect/IGlobal.py` (+11 / -6 lines): after building the one `Detector`, it starts an `InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of `make_device_lock()`; `endGlobal` stops the worker before disconnecting the detector.
> - `nodes/detect/IInstance.py` (+4 / -2 lines): `with self.IGlobal.device_lock: detections = self.IGlobal.detector.detect(image)` becomes `detections = self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.
> - `nodes/detect/infer_worker.py` (new, 88 lines): `InferenceWorker.submit/detect/close`. Each caller has at most one frame outstanding and blocks on its own `Future`, so a video's frames stay in order and each result returns to its caller without a routing table; a detect exception reaches its own caller's existing `except` branch; a full queue blocks the submitter.
> - Base files: IInstance.py md5 984d80e45e885b5ae21e987664850b4c, IGlobal.py md5 9edc29c94a5a34ba366d938d048e89fd (engine 3.3.1.35; the line counts above are against that local bundle, which is not in the repository). Patched: IGlobal.py 22fc2536b8b3bebdcc708375f9aa52e5, IInstance.py 780202974588b9d85287f2096c0b67bb, infer_worker.py b522c83ffeed93dca8de340e3b0b8799.
>
> ## Output identity
>
> - P5 (parity_p5_20260925T141647Z): identical to stock (per-video chunk sha256 AND frame scores) on 16/16 videos in every comparison, at K=16 and K=1, both rounds, and against an earlier session's stock K=1 leg [analysis_p5a.json correctness.gate_pass = True].
> - P6: identical to stock on 16/16 in both rounds [analysis_p6.json P6_A.correctness.gate_pass = True]; on the 168-video slice, 166 of 168 videos identical to a banked stock run from another session [P6_B.correctness_vs_p1d]: IN1002.avi, TS3010a.avi differ (chunk hashes and frame scores); whether the patch or run-to-run variation in stock causes it is NOT established — stock was never replicated on those videos (register 65).
>
> ## Mandate compliance
>
> - One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector` object; the on-token D0 read exactly one LWDETR before and after every measured leg (P5, P6 gate records G_d0).
> - Threads only: one extra thread (`detect-infer`) per task process.
>
> ## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB)
>
> - Frames/s: 4.220 vs stock 2.419 (+74.4%) [P6_A.cells.*.frames_per_s.mean]; one LlamaIndex instance 3.149.
> - CPU-s per frame: 1.317 vs stock 1.489 (-11.8%) [P6_A.cells.*.cpu_s_per_frame.mean].
> - Sampled memory peak: 5,649 MB vs stock 7,583 MB [P6_A.cells.*.memory_peak_total_bytes.mean].
> - The inference thread is busy 99.95% of the window [P6_A.cells.p5_k16.duty.mean]: it is now the bottleneck.
>
> ## Known residual
>
> - With 16 videos in flight the forward pass is +17.2% longer than with one (mean; median +12.5%, p99 +143.6%) [P6_A.descriptive_forward_degradation; the one-video reference is P5's session] — a tail of slow forwards while the other callers decode; its cause was not measured.
>
> ## What a reviewer should test
>
> - Output identity against the current node on your own video set at the same thread count, at 1 and at many videos in flight — and, first, the current node against ITSELF on the same set (two runs), so a mismatch can be attributed; start with IN1002.avi, TS3010a.avi, which differed here.
> - Teardown: a pipeline stopped with frames queued ends cleanly (the worker fails pending frames and `endGlobal` returns).
> - Errors: a frame whose detect raises is dropped with the existing warning and the next frame is served.
> - Model-server (proxy) mode: `make_device_lock()` returned a no-op there; the worker still serialises calls — check throughput in that mode.
> - Very high concurrency: the queue bound (`RR_DETECT_QUEUE_MAX`) and memory (one decoded frame per waiting caller).
> - Other nodes or code that used `IGlobal.device_lock` (none in the detect node itself).

## NOT RUN

- P6-C round 2 (the canary p6c_can_c2 and the legs p6c_p5t16_2, p6c_lit16_2): the 8-hour budget passed at 02:15:37Z while round 1's LlamaIndex leg was in flight; by the rule that leg finished and the rest is NOT RUN — so P6-C's pooled reading is not evaluable and round 1 is reported

## Methodology register

- 65 — an output reference with no replicate of its own (P6-B: 2 of 168 videos differ from the banked stock run on one frame each; cause not established)

## SELF-AUDIT

- **1. HYPOTHESIS:** stated before the first leg in preregistration.json (committed 8e4cf34a) and preregistration_addendum_1.json (the drift-note rule, committed c0af3f83 before the first measured leg); FIXED tolerances throughout (register 64); no other amendment.
- **2. EVIDENCE:** every figure is computed by working/scripts/p6_report.py and p6_write_specs.py from analysis_p6.json (p6_analyse.py over the raw legs and blocks), the gate-control record, the gate records and the chain records (the P6-B stamp files, which no analysis reads, are kept in S3 only — p6b_stamps_s3_only.json lists each with its sha256); the drafts from p4_facts.json, the Stage 4 analysis, analysis_p6.json, the P5 analysis and build record, and the node sources.
- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json; real control legs for the out-of-box posture, LlamaIndex at T=16 and the warm flags); the driver's warm flags have a laptop test with a null control; the blind recomputation's planted figures had to be caught.
- **4. REGISTER:** 3, 48, 54, 55, 56-58, 59, 61, 62 (ABAB and the canary), 64 (fixed tolerances; forward degradation descriptive only); new: 65 (an output reference with no replicate of its own).
- **5. NOT VERIFIED:** what the residual forward penalty at 16 in flight is made of; P6-C's T=16 vs T=4 comparison is across stages, not interleaved; the brief and the patch description are drafts; the prototype is not a RocketRide change.
- **6. GATES:** every landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg and block; image ids read back at every stage's start and end (rr:p5-infer not rebuilt); the box stopped with box.sh stop and its state read back.

