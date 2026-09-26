# DRAFT — ticket: default intra-op thread count for the detect node (not filed, posted or sent)

Figures cite analysis_p7.json P7_C (P6-C round 1 + P7-C round 2), analysis_p6.json P6_A and S5-A's analysis_output_shift.json by key.

## What

The detect node leaves the six thread variables unset, so torch runs its default intra-op pool (16 threads on the benchmark box, read back in-process [parity_p7 gates/G_cell_p7c_p5t16_2.json]). This ticket asks whether that default should change. It is separate from the single-inference-thread patch, which keeps today's default.

## Speed at 4 vs 16 threads (with the single inference thread; 16 videos, 16 in flight; one LlamaIndex instance beside)

- The forward pass takes 1.705x as long at 16 threads as at 4 (pooled over two rounds) [P7_C.readings.pooled.F_t16_over_F_t4] — SLOWER; per round 1.700 and 1.711 [..round_1, ..round_2].
- Frames/s: 2.489 at 16 threads [..pooled.fps_p5_t16_mean] vs 4.220 at 4 threads [analysis_p6.json P6_A.cells.p5_k16.frames_per_s.mean]; one LlamaIndex instance at 16 threads 2.642 [..pooled.fps_li_t16_mean].
- Caveat: the 16-thread rounds and the 4-thread reference are in different stages and sessions (not ABAB); the canaries are reported beside in the P7 report and adjust nothing.

## Output effect, stated plainly (S5-A, 16 videos, the current node) [batchsize_s5 analysis_output_shift.json s5a_thread_width_vs_default]

- At 4 threads vs today's default: labels identical on 3,203 of 3,203 frames, but scores shift (by at least 1.96e-03) and 0 of 16 videos are chunk-identical.
- Only unset / 16 threads reproduces today's default output: 16 of 16 videos chunk-identical, score shift 0.0.
- So changing the default changes every downstream score (not the labels, on this set); consumers that store or compare scores would see a one-time shift.

## Asked

- Decide whether a speed gain justifies a one-time output change; measure it at matched concurrency on your own hardware first (the reading above is one box type).
- Whatever the default, record the thread count with every output so runs can be compared.
