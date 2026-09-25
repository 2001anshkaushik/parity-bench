# P5 design draft: a single inference thread for the detect node

DRAFT, not filed, posted or sent. It is the design only; no code is written or built in P4.

## The problem it answers

Two measurements set this up, from different sessions:

- **One video in flight** (P3-B, one session): the engine's forward pass takes about the same time per frame as a bare interpreter and as LlamaIndex's service. Source: `parity_p3_20260925T035027Z/analysis_p3b.json`.
- **Sixteen videos in flight** (P1-A, P2-B): the engine's forward is much slower than LlamaIndex's. Source: `parity_p2_20260924T160106Z/analysis_p2b.json`.

The P0 V3 source trace (`parity_p0_20260923T083031Z/source_traces.json`, `V3_lock_scope`) shows the two arms lock differently:

- **RocketRide:**
  - The lock is `engine/nodes/detect/IGlobal.py:79-81` → `make_device_lock()`, `engine/ai/common/models/base.py:241-252`: one `threading.Lock` per task process.
  - It is held around exactly one `self.IGlobal.detector.detect(image)` call per frame, at `engine/nodes/detect/IInstance.py:106-107`.
  - So with K videos in flight, K caller threads (one per in-flight video's pipeline instance) take turns at the lock frame by frame. Each forward runs on whichever caller holds the lock.
- **LlamaIndex:**
  - The lock is `pipeline.py:127`.
  - It is held around the whole per-video frame loop, at `pipeline.py:251-259`.
  - So one caller runs every frame of its video before the next caller gets the lock.

libgomp keeps a separate OpenMP thread team for each thread that starts a parallel region. So under RocketRide's per-frame hand-off, up to K different teams of T−1 workers take turns running forwards, and each team sleeps while the other callers hold the lock.

## The design

**Where.** Two files change; everything else is unchanged:
- **`IGlobal`** (the detect node's per-task-process global). It already owns the one `detector` and the `device_lock`. It gains an `InferenceWorker`: one daemon thread, a bounded `queue.Queue`, and one `concurrent.futures.Future` per request.
- **`IInstance.writeImage`**, the `AVI_ACTION.END` branch:
  1. Decode the frame's bytes on the caller thread, as today (`IInstance.py:103`, outside the lock today).
  2. Call `fut = IGlobal.infer.submit(image)`, then `detections = fut.result(timeout=...)`.
  3. Emit on the caller thread, as today (`_emit`).

**The inference thread.** A loop of three steps:
1. Take the next item.
2. Call `with device_lock: detections = detector.detect(image)`. This is the same call on the same object as today, with the same resize, pre-processing, forward, post-processing and rescale. The lock stays and is now uncontended, so any other user of the lock is still excluded.
3. Put the result, or the exception, on the item's future.

Every forward now runs on one OS thread, so libgomp uses one team. That team runs each frame back to back, so it's woken at most once per frame and never handed between callers. The thread counts are the same T variables as stock.

**Frame ordering and per-video result routing.** Both hold by construction, with no routing table:
- Each caller has at most ONE frame outstanding: it blocks on its own future before `writeImage` returns, and the engine delivers a video's frames to its pipeline instance in order.
- So a video's frames go through the queue in order, and each result returns on the future that its own caller holds.

Across videos, the queue is FIFO: callers are served in arrival order, which is round-robin in practice because each caller has one frame outstanding.

**Backpressure and memory bound.**
- **Queue depth:** at most the number of in-flight callers K, because each caller has at most one outstanding frame. The queue's `maxsize` is set to the engine's per-task concurrency, so `put` blocks and never grows without limit.
- **Memory:**
  - held: at most K decoded frames waiting plus the one inside `detect`;
  - freed: each frame is released when its caller's future resolves (the caller drops `image` after `_emit`, as today).
- **Stock comparison:** the stock node holds up to K decoded frames too (callers waiting at the lock), so the bound is the same.

**Failure behaviour.**
- An exception in `detect` is set on the future and re-raised in the caller. It reaches the node's existing `except` branch: the frame is dropped with the existing warning, the same observable behaviour as stock.
- `fut.result(timeout)` bounds the wait if the inference thread dies. The thread is restarted by `IGlobal` on the next `submit`, and the event is logged.
- **Shutdown:** `IGlobal`'s end puts a sentinel, joins the thread, and fails any pending future.

**What it does not change.** No batching: one frame per `detect` call, exactly as stock. Batching frames from several videos into one forward could change the floats, so it would be a separate step with its own correctness gate. Nor does it change decode, emit, the pipeline, the model, its weights or the thread variables.

## The correctness test (before any speed claim)

- **Output identity with stock at the same T:** per-video chunk sha256 AND frame scores equal on 16/16 videos of the AMI 16-video slice (`p0_analyse_video.identity`). Both the P5 build and stock `rr:patched-video` run at T=4, at K=16 and at K=1.
- **Null controls,** which must FAIL the same check:
  - the P5 build at T=16 against stock at T=4 (a known output change: P0 V1 `rr_t4_vs_default_output` differs on 16/16);
  - a deliberately mis-routing worker that swaps the results of two callers, which proves the check catches routing errors.
- **Only after identity passes:** the forward per frame and frames/s at K=1 and K=16, ABAB, in one session, as P4-A measured them.

## The in-bounds proof

- **One engine process, one pipeline (one token), one model instance.** The worker calls the SAME `IGlobal.detector` object; nothing is copied or loaded a second time.
  - D0: the on-token env_probe's `root_modules_with_params` must still show one `LWDETR` with `distinct_weights` 1, pre and post, and one task process for the leg.
- **Threads only:** one extra thread per task process, visible in the read-back's thread census, and still inside the "threads unrestricted" clause.

## Which P4-A readings make it the right next step

This section was written BEFORE P4-A's data. It reads as rules against the pre-registered readings.

| P4-A outcome | Is P5 the next step? |
|---|---|
| R1 SUPPORTED and R3 (NOT WAKE-UP) | **Yes.** The gap is concurrency-specific, and keeping OpenMP pools awake does not close it. Whatever remains is either caller interleaving (the forward runs on K different threads with K teams), which this design removes, or shared contention (other callers' decode and emit competing with the forward's T threads), which it does not. Its measurement separates the two: if F at K=16 under P5 falls to F at K=1, it was interleaving; if not, the next candidate is CPU partitioning for the inference thread's team. |
| R1 SUPPORTED and R2 (POOL WAKE-UP) | **Not first.** The configuration fix (`OMP_WAIT_POLICY=ACTIVE` or a spin-count setting) comes first. P5 is deferred and reconsidered only for the CPU that ACTIVE spends spinning idle pools, measured beside. |
| R1 NOT SUPPORTED | **No.** The gap is not concurrency-specific, so a design that changes how concurrent callers share the detector does not address it. What the K=1 cells show is explained first. |
| R2/R3 NOT EVALUABLE (output-changing, or no RR degradation) | P5 is not justified by P4-A. It stays a draft. |
