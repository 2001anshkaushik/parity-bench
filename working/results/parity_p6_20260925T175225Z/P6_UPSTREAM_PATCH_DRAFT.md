# DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)

## What changed

- `nodes/detect/IGlobal.py` (+11 / -6 lines): after building the one `Detector`, it starts an `InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of `make_device_lock()`; `endGlobal` stops the worker before disconnecting the detector.
- `nodes/detect/IInstance.py` (+4 / -2 lines): `with self.IGlobal.device_lock: detections = self.IGlobal.detector.detect(image)` becomes `detections = self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.
- `nodes/detect/infer_worker.py` (new, 88 lines): `InferenceWorker.submit/detect/close`. Each caller has at most one frame outstanding and blocks on its own `Future`, so a video's frames stay in order and each result returns to its caller without a routing table; a detect exception reaches its own caller's existing `except` branch; a full queue blocks the submitter.
- Base files: IInstance.py md5 984d80e45e885b5ae21e987664850b4c, IGlobal.py md5 9edc29c94a5a34ba366d938d048e89fd — equal to the image's own node files [parity_p5_20260925T141647Z/p5a_build.json base_node] (the local engine bundle, 3.3.1.35 per parity_p5_20260925T141647Z/PROGRESS_LOG.md:5; the line counts above are against that bundle, which is not in the repository). Patched: IGlobal.py 22fc2536b8b3bebdcc708375f9aa52e5, IInstance.py 780202974588b9d85287f2096c0b67bb, infer_worker.py b522c83ffeed93dca8de340e3b0b8799.

## Output identity

- P5 (parity_p5_20260925T141647Z): identical to stock (per-video chunk sha256 AND frame scores) on 16/16 videos in every comparison, at K=16 and K=1, both rounds, and against an earlier session's stock K=1 leg [analysis_p5a.json correctness.gate_pass = True].
- P6: identical to stock on 16/16 in both rounds [analysis_p6.json P6_A.correctness.gate_pass = True]; on the 168-video slice, 166 of 168 videos identical to a banked stock run from another session [P6_B.correctness_vs_p1d]: IN1002.avi, TS3010a.avi differ (chunk hashes and frame scores); whether the patch or run-to-run variation in stock causes it is NOT established — stock was never replicated on those videos (register 65).

## Mandate compliance

- One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector` object; the on-token D0 read exactly one LWDETR before and after every measured leg (P5, P6 gate records G_d0).
- Threads only: one extra thread (`detect-infer`) per task process.

## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB)

- Frames/s: 4.220 vs stock 2.419 (+74.4%) [P6_A.cells.*.frames_per_s.mean]; one LlamaIndex instance 3.149.
- CPU-s per frame: 1.317 vs stock 1.489 (-11.5%) [P6_A.cells.*.cpu_s_per_frame.mean].
- Sampled memory peak: 5,649 MB vs stock 7,583 MB [P6_A.cells.*.memory_peak_total_bytes.mean].
- The inference thread is busy 99.95% of the window [P6_A.cells.p5_k16.duty.mean]: it is now the bottleneck.

## Known residual

- With 16 videos in flight the forward pass is +17.2% longer than with one (mean; median +12.5%, p99 +143.6%) [P6_A.descriptive_forward_degradation; the one-video reference is P5's session] — a tail of slow forwards while the other callers decode; its cause was not measured.

## What a reviewer should test

- Output identity against the current node on your own video set at the same thread count, at 1 and at many videos in flight — and, first, the current node against ITSELF on the same set (two runs), so a mismatch can be attributed; start with IN1002.avi, TS3010a.avi, which differed here.
- Teardown: a pipeline stopped with frames queued ends cleanly (the worker fails pending frames and `endGlobal` returns).
- Errors: a frame whose detect raises is dropped with the existing warning and the next frame is served.
- Model-server (proxy) mode: `make_device_lock()` returned a no-op there; the worker still serialises calls — check throughput in that mode.
- Very high concurrency: the queue bound (`RR_DETECT_QUEUE_MAX`) and memory (one decoded frame per waiting caller).
- Other nodes or code that used `IGlobal.device_lock` (none in the detect node itself).
