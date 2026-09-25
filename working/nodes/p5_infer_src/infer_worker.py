# =============================================================================
# P5 prototype (benchmark-only; not RocketRide source): a single inference thread for the detect node.
# The P4-B (3) design (parity_p4_20260925T092942Z/P4B_P5_DESIGN_SINGLE_INFERENCE_THREAD.md).
#
# One dedicated thread owns the node's single Detector and runs EVERY detect() call. Callers (one pipeline
# instance per in-flight video) decode their frame, submit it to one bounded queue and block on their own
# Future, so each caller has at most one frame outstanding: a video's frames go through in order and each
# result returns to the caller that submitted it (no routing table). The queue replaces the per-frame
# device lock: only this thread ever calls the detector, so its OpenMP team is the only one that runs a
# forward pass. Nothing here changes a frame, a detection or the model.
# =============================================================================

import queue
import threading
from concurrent.futures import Future


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

    def submit(self, image) -> Future:
        """Queue one decoded frame; blocks while the queue is full (backpressure)."""
        if self._closed:
            raise RuntimeError('detect: inference worker is closed')
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._start()
        fut = Future()
        self._q.put((image, fut))
        return fut

    def detect(self, image, timeout=None):
        """Submit and wait: the drop-in replacement for `with device_lock: detector.detect(image)`."""
        return self.submit(image).result(timeout=timeout)

    def _run(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            image, fut = item
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(self._detector.detect(image))
            except BaseException as exc:  # noqa: BLE001 — the caller's own except branch handles it
                fut.set_exception(exc)

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
                _, fut = item
                if fut.set_running_or_notify_cancel():
                    fut.set_exception(RuntimeError('detect: inference worker closed'))
