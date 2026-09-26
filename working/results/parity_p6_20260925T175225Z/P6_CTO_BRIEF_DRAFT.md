# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)

Figures cite the P4 facts sheet [Fnn] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md), the Stage 4 analysis, or the P6 analysis (parity_p6_20260925T175225Z/analysis_p6.json) by key.

**What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against ONE LlamaIndex instance.

## Documents (one token vs LlamaIndex's 24-worker optimum)

- **Matches, not beats.** 6.2969 [F01] vs 5.9046 [F02] docs/s on the full corpus: 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread; the steady-phase ABAB ratios on the 384 slice agree in two sessions: 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].
- **Needs an unshipped fix.** Stock 2.3454 [F15] docs/s; with the Tika wrapper fix 5.3441 [F17] (+127.85% [F18]), 0 of 9,885 [F20] chunk lists changed. The fix measured is a one-byte patch that turns inline-image extraction off for every pipeline, which breaks image pipelines; the shippable form is the source change in parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12.
- **Costs.** CPU per document 4.442 [F05] vs 3.881 [F06] s; sampled memory peak 21,826 [F11] vs 18,069 [F12] MB; idle spin 1.234 [F09] vs 0.026 [F10] cores.
- **Out of the box** (stock image): 2.3454 [F15] docs/s at 7.706 [F16] CPU-s per document; no same-session LlamaIndex run, no ratio.

## Video (one token vs ONE LlamaIndex instance)

- **Stock.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one stock RocketRide token at 16 videos in flight (T=4); out of the box RocketRide runs 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame.
- **Mechanism (P4).** From one video in flight to sixteen RocketRide's forward slows x1.867 [F58], LlamaIndex's x1.403 [F59]: 16 caller threads take turns at the model frame by frame.
- **The single inference thread (rr:p5-infer, a benchmark prototype, not shipped), output identical to stock on 16/16 in both rounds** [P6_A.correctness.gate_pass]: 4.220 frames/s [P6_A.cells.p5_k16.frames_per_s.mean] vs one LlamaIndex instance 3.149 [P6_A.cells.li_k16.frames_per_s.mean] and stock 2.419 [P6_A.cells.stock_k16.frames_per_s.mean]: parity 1.340 [P6_A.readings.Q1.pooled.ratio] (Q1 >= 0.95: HOLDS (pooled); round 1 holds, round 2 holds), speedup 1.744x [P6_A.readings.Q2.pooled.ratio] (Q2 >= 1.20: HOLDS (pooled); round 1 holds, round 2 holds).
- **Known residual (descriptive, cross-session).** Its forward at 16 in flight is +17.2% over one video in flight [P6_A.descriptive_forward_degradation.F_over_ref_minus_1]: median +12.5%, p99 +143.6% [..p50_over_ref_minus_1, ..p99_over_ref_minus_1] — a tail.
- **168 videos, block-interleaved:** RocketRide 4.089 vs LlamaIndex 3.134 frames/s [P6_B.per_arm.*.total_frames_per_s], ratio 1.304 [P6_B.ratio_rr_over_li_totals] against 0.95; per block 0.987 to 1.351 (median 1.311) [P6_B.per_block_ratio_distribution]; output vs the banked stock run: 166 of 168 identical; IN1002.avi, TS3010a.avi differ — cause not established (stock never replicated on them) [P6_B.correctness_vs_p1d].
- **Out-of-box threads (T=16) with the single inference thread, one round (the second was cut by the budget):** forward 1.700x the T=4 forward [P6_C.readings.round_1.F_t16_over_F_t4] — slower, not faster; frames/s vs one LlamaIndex instance at T=16 0.955 [P6_C.readings.round_1.fps_p5_t16_over_li_t16]; T=4 remains the posture to use.
- **Context, not the comparison:** LlamaIndex's multi-instance video configuration — 8 instances x 4 threads — runs 13.52 frames/s on the 168 videos (Stage 4) [batchsize_s4_20260921T013303Z/p5_li_video/analysis_video.json legs.0.frames_per_s; posture workers[declared_workers=8]; threads: li_k16/export_llamaindex_video_workers_blast.json provenance_video.posture.threads_env_in_process_torch]. That is 8 model instances; the comparisons above hold RocketRide to one token and LlamaIndex to one instance.

## What is not claimed

- That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).
- Any figure from an unshipped fix or prototype as shipped behaviour.
- Any cross-session ratio as a comparison.
