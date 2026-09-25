#!/usr/bin/env python3
"""P5 laptop test of the single-inference-thread worker (no engine, no torch): routing, order, one detect thread,
backpressure, error propagation, close — for BOTH the clean and the stamped worker. The null control is a
deliberately mis-routing worker (results swapped between two callers), which the routing check must catch.

    p5_worker_test.py   -> exit 0 iff every check passes AND the null control is caught
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = []


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeDetector:
    """detect(x) returns x's payload; records which OS thread ran each call."""
    def __init__(self, delay=0.0005, fail_on=None):
        self.threads, self.calls, self.delay, self.fail_on = set(), 0, delay, fail_on

    def detect(self, image):
        self.threads.add(threading.get_native_id())
        self.calls += 1
        if self.fail_on is not None and image == self.fail_on:
            raise ValueError('boom')
        time.sleep(self.delay)
        return ('det', image)


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")


def routing(worker_cls, stamped: bool, swap: bool = False, callers=16, frames=40):
    det = FakeDetector()
    w = worker_cls(det, maxsize=64)
    if swap:                                         # the null control: route results to the wrong caller
        orig = w._run

        def bad_run():
            pending = []
            while True:
                item = w._q.get()
                if item is None:
                    return
                pending.append(item)
                if len(pending) == 2:
                    (i1, f1, *_), (i2, f2, *_) = pending
                    for f in (f1, f2):
                        f.set_running_or_notify_cancel()
                    f1.set_result(det.detect(i2))
                    f2.set_result(det.detect(i1))
                    pending = []
        w._q.put(None); w._thread.join(); w._thread = threading.Thread(target=bad_run, daemon=True); w._thread.start()
        del orig
    got, errors, depths = {}, [], []

    def caller(c):
        out = []
        for k in range(frames):
            img = (c, k)
            ctx = {} if stamped else None
            try:
                r = w.detect(img, timeout=30, **({'ctx': ctx} if stamped else {}))
            except Exception as e:                   # noqa: BLE001
                errors.append(repr(e)); return
            out.append(r)
            if stamped:
                depths.append(ctx.get('qdepth'))
                if not all(k2 in ctx for k2 in ('sub0', 'ws', 'we', 'h0_mono', 'h1_mono', 'infer_tid')):
                    errors.append(f'missing stamp keys {sorted(ctx)}')
        got[c] = out
    ts = [threading.Thread(target=caller, args=(c,)) for c in range(callers)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    ok = not errors and all(got.get(c) == [('det', (c, k)) for k in range(frames)] for c in range(callers))
    w.close()
    return ok, det, errors, depths


def main() -> int:
    src = ROOT / "working" / "nodes"
    for flavour, path, stamped in (("clean", src / "p5_infer_src" / "infer_worker.py", False),
                                   ("stamped", src / "p5_infer_stamped" / "infer_worker.py", True)):
        print(f"== {flavour} worker ({path.relative_to(ROOT)})")
        m = load(path, f"iw_{flavour}")
        ok, det, errors, depths = routing(m.InferenceWorker, stamped)
        check(f"{flavour}: 16 callers x 40 frames, every caller gets its own results in order", ok, f"errors {errors[:2]}")
        check(f"{flavour}: every detect ran on ONE thread (not a caller)", len(det.threads) == 1, f"{len(det.threads)} thread(s)")
        check(f"{flavour}: detect called once per frame", det.calls == 16 * 40, f"{det.calls}")
        if stamped:
            check("stamped: queue depth recorded on every frame, bounded by the callers", depths and all(d is not None and 0 <= d <= 16 for d in depths),
                  f"max {max(depths) if depths else None}")
        # error propagation: the failing frame raises in ITS caller only
        det2 = FakeDetector(fail_on=(0, 1))
        w = m.InferenceWorker(det2, maxsize=4)
        r0 = w.detect((0, 0), timeout=10)
        try:
            w.detect((0, 1), timeout=10); raised = False
        except ValueError:
            raised = True
        r2 = w.detect((0, 2), timeout=10)
        check(f"{flavour}: a detect error reaches its own caller and the worker keeps serving", raised and r0 == ('det', (0, 0)) and r2 == ('det', (0, 2)))
        # backpressure: a full queue blocks put
        slow = FakeDetector(delay=0.2)
        w2 = m.InferenceWorker(slow, maxsize=1)
        w2.submit((9, 0)); time.sleep(0.05); w2.submit((9, 1))       # one running, one queued
        t = threading.Thread(target=lambda: w2.submit((9, 2)), daemon=True); t.start(); t.join(0.05)
        check(f"{flavour}: a full queue blocks the submitter (bounded memory)", t.is_alive())
        t.join(2); w2.close(); w.close()
        check(f"{flavour}: close() stops the thread", not w.thread.is_alive())
    print("== null control: a mis-routing worker must FAIL the routing check")
    m = load(src / "p5_infer_src" / "infer_worker.py", "iw_null")
    ok, *_ = routing(m.InferenceWorker, False, swap=True, callers=4, frames=10)
    check("null control caught (mis-routing detected)", not ok)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} checks pass")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
