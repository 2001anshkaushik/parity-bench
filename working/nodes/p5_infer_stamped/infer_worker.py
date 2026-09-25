# =============================================================================
# P5 STAMPED COPY (benchmark-only; never part of RocketRide) of working/nodes/p5_infer_src/infer_worker.py.
# Byte-for-byte the clean worker's behaviour plus per-frame timing marks written into the frame's own stamp
# dict (the `ctx` the caller passes): the queue depth right after the frame is queued, the moment the
# inference thread picks it up and finishes it, and the thread/process CPU across the detect call. The worker
# sets the module's thread-local TL.d to that dict while it runs the frame, so the stamped IInstance's forward
# hooks (which fire on THIS thread) write into the same record. Copied into a RUNNING container's writable
# layer only when that container's clean files carry the md5 this copy was derived from (p5_stamp.sh).
# =============================================================================

import queue
import threading
import time
from concurrent.futures import Future

TL = threading.local()          # the per-thread current stamp dict (caller thread and inference thread)
ON_FRAME_DONE = []              # optional callbacks run on the inference thread after each frame (read-back)


def _c(d, k):
    if d is not None and (k + '_mono') not in d:
        d[k + '_mono'] = time.monotonic()
        d[k + '_tcpu'] = time.thread_time()
        d[k + '_pcpu'] = time.process_time()


class InferenceWorker:
    """One daemon thread, one bounded FIFO queue, one Future per submitted frame."""

    def __init__(self, detector, maxsize: int = 64, name: str = 'detect-infer'):
        self._detector = detector
        self._q = queue.Queue(maxsize=max(1, int(maxsize)))
        self._name = name
        self._start_lock = threading.Lock()
        self._closed = False
        self._thread = None
        self._start()

    def _start(self):
        t = threading.Thread(target=self._run, name=self._name, daemon=True)
        t.start()
        self._thread = t

    @property
    def thread(self):
        return self._thread

    @property
    def maxsize(self) -> int:
        return self._q.maxsize

    def qsize(self) -> int:
        return self._q.qsize()

    def submit(self, image, ctx=None) -> Future:
        """Queue one decoded frame; blocks while the queue is full (backpressure)."""
        if self._closed:
            raise RuntimeError('detect: inference worker is closed')
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._start()
        fut = Future()
        if ctx is not None:
            ctx['sub0'] = time.perf_counter()
        self._q.put((image, fut, ctx))
        if ctx is not None:
            ctx['qdepth'] = self._q.qsize()
        return fut

    def detect(self, image, timeout=None, ctx=None):
        """Submit and wait: the drop-in replacement for `with device_lock: detector.detect(image)`."""
        return self.submit(image, ctx).result(timeout=timeout)

    def _run(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            image, fut, ctx = item
            if not fut.set_running_or_notify_cancel():
                continue
            if ctx is not None:
                ctx['ws'] = time.perf_counter()
                ctx['infer_tid'] = threading.get_native_id()
                _c(ctx, 'h0')
            TL.d = ctx
            try:
                result = self._detector.detect(image)
            except BaseException as exc:  # noqa: BLE001 — the caller's own except branch handles it
                TL.d = None
                fut.set_exception(exc)
                continue
            if ctx is not None:
                _c(ctx, 'h1')
                ctx['we'] = time.perf_counter()
            TL.d = None
            for cb in ON_FRAME_DONE:
                try:
                    cb()
                except Exception:  # noqa: BLE001 — never the frame's problem
                    pass
            fut.set_result(result)

    def close(self, timeout: float = 30.0):
        """Stop the thread after the frames already queued, then fail anything left."""
        self._closed = True
        self._q.put(None)
        if self._thread is not None:
            self._thread.join(timeout)
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                fut = item[1]
                if fut.set_running_or_notify_cancel():
                    fut.set_exception(RuntimeError('detect: inference worker closed'))
