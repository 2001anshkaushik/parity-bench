# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)

Figures cite the P4 facts sheet [Fnn], the Stage 4 analysis, analysis_p6.json or analysis_p7.json by key.

**What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against ONE LlamaIndex instance.

## Documents (one token vs LlamaIndex's 24-worker optimum)

- **Matches, not beats.** 6.2969 [F01] vs 5.9046 [F02] docs/s: 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread; steady-phase ABAB ratios 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].
- **Needs an unshipped fix.** Stock 2.3454 [F15] docs/s; with the Tika wrapper fix 5.3441 [F17] (+127.85% [F18]), 0 of 9,885 [F20] chunk lists changed; the measured fix disables inline-image extraction for every pipeline (breaks image pipelines) — the shippable form is the source change in parity_p2 P2D_WRAPPER_TICKET_DRAFT.md:12.
- **Costs.** CPU per document 4.442 [F05] vs 3.881 [F06] s; memory peak 21,826 [F11] vs 18,069 [F12] MB; idle spin 1.234 [F09] vs 0.026 [F10] cores. **Out of the box:** 2.3454 [F15] docs/s, 7.706 [F16] CPU-s per document.

## Video (one token vs ONE LlamaIndex instance)

- **Stock.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one stock token at 16 in flight (T=4); out of the box 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame. Cause (P4): at 16 in flight RocketRide's forward slows x1.867 [F58], LlamaIndex's x1.403 [F59].
- **The single inference thread (a prototype, not shipped):** 4.220 vs one LlamaIndex instance 3.149 frames/s — parity 1.340 [P6_A.readings.Q1.pooled.ratio], 1.744x stock [..Q2.pooled.ratio]; 168 videos block-interleaved 1.304 [P6_B.ratio_rr_over_li_totals].
- **Output (P7).** Identical to stock at matched threads on every 16-video comparison; on 168 videos 166 of 168 matched one banked stock run [P6_B.correctness_vs_p1d]. The two misses are single frames where one run is not a reference: stock itself changed output across sessions on one [P7_B_tier1 TS3010a.avi#56], and the prototype varied run to run on the other where stock did not in three runs [P7_B_tier1 IN1002.avi#58]. Not a threshold artifact [p7a_frames.json: NOT BOUNDARY].
- **Thread count.** With the single inference thread, the forward takes 1.71x as long at 16 threads as at 4 [P7_C.readings.pooled.F_t16_over_F_t4] (T=16 is NOT faster by at least 5% (pooled); cross-session); T=4 stays the posture. Changing the default thread count changes scores (S5-A) — a separate ticket, drafted.
- **Context, not the comparison:** LlamaIndex's multi-instance configuration — 8 instances x 4 threads — runs 13.52 frames/s (Stage 4) [batchsize_s4 p5_li_video/analysis_video.json legs.0.frames_per_s; posture workers[declared_workers=8]; threads li_k16 export provenance_video.posture.threads_env_in_process_torch].

## Not claimed

- That RocketRide BEATS LlamaIndex on documents; any unshipped fix or prototype figure as shipped behaviour; any cross-session ratio as a comparison; output identity on the two non-reproducible frames.
