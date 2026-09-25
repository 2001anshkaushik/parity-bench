# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)

Figures cite the P4 facts sheet row [F..] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md, each row naming its artifact and key) or a P5 analysis file and key.

## Documents

- **Matches, not beats.** One RocketRide token runs 6.2969 [F01] docs/s on the full corpus against LlamaIndex's 24-worker optimum at 5.9046 [F02]: a ratio of 1.066 [F03], one run per arm, inside LlamaIndex's replicate spread. The steady-phase ABAB ratios on the 384 slice agree across two sessions: 1.048 [F27] and 1.052 [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio; the same artifact as F27, not a facts-sheet row].
- **It depends on an unshipped fix.** Stock RocketRide runs 2.3454 [F15] docs/s; the Tika wrapper fix takes it to 5.3441 [F17] (+127.85% [F18]), with 0 of 9,885 [F20] chunk lists changed. The fix measured is a one-byte patch that turns inline-image extraction off for every pipeline, which breaks image pipelines; the shippable form is the source change in the wrapper ticket draft (parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12).
- **Costs.** CPU per document: RocketRide 4.442 [F05] s vs LlamaIndex 3.881 [F06] s. Sampled memory peak: 21,826 [F11] MB vs 18,069 [F12] MB. Idle spin with nothing submitted: 1.234 [F09] cores vs 0.026 [F10].
- **Out of the box** (stock image): 2.3454 [F15] docs/s at 7.706 [F16] CPU-s per document; no same-session LlamaIndex run, so no ratio is formed.

## Video

- **The gap.** One LlamaIndex instance runs +34.7% [F28] more frames/s than one RocketRide token at 16 videos in flight (T=4). Out of the box RocketRide runs 2.556 [F31] frames/s at 2.094 [F34] CPU-s per frame.
- **The mechanism (P4).** From one video in flight to sixteen RocketRide's forward pass slows x1.867 [F58], LlamaIndex's x1.403 [F59]; at one video in flight RocketRide is the faster engine (4.341 [F43] vs 2.980 [F49] frames/s). RocketRide's detector lock is taken per frame by up to 16 caller threads; OMP_WAIT_POLICY=ACTIVE did not help (closure -0.115 [F60]).
- **P5 (single inference thread; a benchmark prototype, not shipped), output identical to stock on 16/16 videos at K=1 and K=16** [analysis_p5a.json correctness.gate_pass]: at 16 videos in flight it runs 4.644 frames/s [cells.p5_k16.frames_per_s.mean] against stock 2.665 [cells.stock_k16.frames_per_s.mean] (+74.2% [readings.S1.pooled.fps_p5k16_over_stock_k16_minus_1]) and LlamaIndex 3.382 [cells.li_k16.frames_per_s.mean]; RocketRide/LlamaIndex 1.373 [readings.S2.pooled.fps_p5k16_over_li_k16]. Its forward at 16 in flight is +6.2% against one in flight [readings.S1.pooled.F_p5k16_over_p5k1_minus_1]. S1 (fix works): DOES NOT HOLD (pooled); round 1 does not, round 2 does not; S2 (parity >= 0.95): HOLDS (pooled); round 1 holds, round 2 holds.
- **P5-B 168-video confirmation: NOT RUN** — its pre-registered gate NOT FIRED [gates/G_smoke_P5B.json outcome]: S1 does not hold.

## What is not claimed

- That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).
- Any figure from the unshipped fixes as shipped behaviour.
- Any cross-session ratio.
