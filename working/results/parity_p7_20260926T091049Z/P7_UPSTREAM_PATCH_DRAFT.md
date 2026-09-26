# DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)

Updated in P7 (parity_p7_20260926T091049Z). Figures cite analysis_p5a.json, analysis_p6.json, p7a_frames.json and analysis_p7.json by key.

## What changed

- `nodes/detect/IGlobal.py` (+11 / -6 lines): after building the one `Detector`, it starts an `InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of `make_device_lock()`; `endGlobal` stops the worker first.
- `nodes/detect/IInstance.py` (+4 / -2 lines): the locked `detector.detect(image)` becomes `self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.
- `nodes/detect/infer_worker.py` (new, 88 lines): each caller has at most one frame outstanding and blocks on its own `Future`, so a video's frames stay in order and each result returns to its caller.
- Base files: IInstance.py md5 984d80e45e885b5ae21e987664850b4c, IGlobal.py md5 9edc29c94a5a34ba366d938d048e89fd — equal to the image's own node files [parity_p5 p5a_build.json base_node] (the local engine bundle, 3.3.1.35 per parity_p5_20260925T141647Z/PROGRESS_LOG.md:5, not in the repository). Patched: IGlobal.py 22fc2536b8b3bebdcc708375f9aa52e5, IInstance.py 780202974588b9d85287f2096c0b67bb, infer_worker.py b522c83ffeed93dca8de340e3b0b8799.
- **The thread count is not changed.** The patch keeps today's default; every identity claim below compares it with the current node AT THE SAME thread count.

## Output identity — exactly what is claimed, and on what evidence

- **16 videos, matched threads (T=4), 16 in flight:** identical to the current node (per-video chunk sha256 AND frame scores) on 16/16 in every ABAB comparison [analysis_p5a.json correctness.gate_pass = True; analysis_p6.json P6_A.correctness.gate_pass = True].
- **16 videos, the out-of-box thread count (the six variables unset):** identical on 16/16 to the current node's committed out-of-box output [analysis_p6.json P6_C.correctness.gate_pass = True; analysis_p7.json P7_C.correctness_C2.pass = True].
- **168 videos (23,049 frames):** 166 of 168 videos identical to ONE banked run of the current node from another session [P6_B.correctness_vs_p1d]; IN1002.avi, TS3010a.avi differ on one frame each. P7 re-ran those videos (two runs of each node, one session):
  - TS3010a.avi frame 56: the CURRENT node gives 2 different outputs across sessions (the banked run, and two runs today that match every prototype run) [analysis_p7.json P7_B_tier1.per_frame.TS3010a.avi#56.post_hoc_distinct_outputs]. The difference does not need the patch.
  - IN1002.avi frame 58: the current node gave 1 output in its 3 runs; the prototype gave 3 different outputs in its 3 runs, one of them equal to the current node's [..IN1002.avi#58.post_hoc_distinct_outputs]. On this frame the prototype varies run to run where the current node has not been seen to; the cause is not established.
  - Each of these changes moves the whole frame — every score (up to 0.0173 in P6-B vs the banked run [p7a_frames.json frames.*.max_rank_paired_score_delta]) — not a detection on the 0.3 threshold [p7a_frames.json reading: NOT BOUNDARY]; every other frame of these videos agreed in all four P7 runs [P7_B_tier1.other_frames.*.other_frames_where_any_two_of_the_four_runs_disagree: 0 frames].
- **So the claim is:** output-identical to the current node at matched threads on every video compared, except 2 frames of 23,049 where a single run is not a reference: on one (TS3010a.avi frame 56) the current node itself changed output across sessions; on the other (IN1002.avi frame 58) the prototype varied run to run where the current node has not (three runs each). On that frame the prototype is not shown output-identical.

## Mandate compliance

- One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector`; the on-token D0 read exactly one LWDETR before and after every measured leg (P5, P6, P7 gate records G_d0).
- Threads only: one extra thread (`detect-infer`) per task process.

## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB) [analysis_p6.json P6_A.cells.*]

- Frames/s: 4.220 vs 2.419 (+74.4%); one LlamaIndex instance 3.149. 168 videos, block-interleaved: 4.089 vs one LlamaIndex instance 3.134 [P6_B.per_arm].
- CPU-s per frame: 1.317 vs 1.489 (-11.5%); sampled memory peak 5,649 MB vs 7,583 MB.

## Known residual

- With 16 videos in flight the forward pass is +17.2% longer than with one (median +12.5%, p99 +143.6%) [P6_A.descriptive_forward_degradation; cross-session reference] — a tail; its cause was not measured.
- The run-to-run variation on IN1002.avi frame 58 above.

## What a reviewer should test

- Output identity at the SAME thread count, on your own videos, at 1 and many in flight — and first the current node against ITSELF, several runs, so a mismatch can be attributed. Start with IN1002.avi frame 58 (run each node three or more times) and TS3010a.avi frame 56 (the current node alone changed output across sessions).
- Teardown with frames queued; a frame whose detect raises; model-server (proxy) mode, where `make_device_lock()` was a no-op; the queue bound at very high concurrency.
- Other code that used `IGlobal.device_lock` (none in the detect node itself).
