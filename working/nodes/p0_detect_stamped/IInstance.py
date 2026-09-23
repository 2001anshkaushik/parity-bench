# =============================================================================
# MIT License
#
# Copyright (c) 2026 Aparavi Software AG
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================

import json
import time

from rocketlib import IInstanceBase, AVI_ACTION, debug, warning
from ai.common.image import ImageProcessor
from .IGlobal import IGlobal

# ---------------------------------------------------------------------------------------------
# P0 V2 STAMPED COPY (benchmark-only; never part of RocketRide). Byte-for-byte the image's
# engine/nodes/detect/IInstance.py plus per-frame timing marks: the lock wait and hold around the
# UNCHANGED `with self.IGlobal.device_lock:` block, and pass-through timing wrappers on the
# facade's own steps (resize_for_inference, DetectorLoader.preprocess/inference/postprocess,
# Detector._rescale_to_original, RFDetrLoader.detect, the rfdetr model's predict) plus torch
# forward pre/post hooks on its root nn.Module. Every wrapper calls the original with the same
# arguments and returns its result unchanged. Copied into a RUNNING container's writable layer
# (never the image) only when that container's original file has the md5 this was derived from.
# ---------------------------------------------------------------------------------------------
import os as _os
import threading as _th

_TL = _th.local()
_OUT = _os.environ.get('P0_V2_OUT', '/tmp/p0_v2_stamps.jsonl')
_WLOCK = _th.Lock()
_INSTALLED = []


def _m(k):
    d = getattr(_TL, 'd', None)
    if d is not None and k not in d:
        d[k] = time.perf_counter()


def _wrap(orig, a, b):
    def w(*args, **kw):
        _m(a)
        r = orig(*args, **kw)
        _m(b)
        return r
    return w


_INSTALL_ERR = []


def _install():
    # An instrumentation failure must NEVER reach the frame: the node's own except below would drop
    # the frame and change the output. Failures are recorded and the frame runs uninstrumented.
    with _WLOCK:
        if _INSTALLED:
            return
        _INSTALLED.append(True)
        try:
            _install_inner()
        except Exception as e:                   # noqa: BLE001
            _INSTALL_ERR.append(f"{type(e).__name__}: {e}")


def _install_inner():
    if True:
        from ai.common.image import dense_resize as _dr
        from ai.common.models.vision import detection as _det
        _dr.resize_for_inference = _wrap(_dr.resize_for_inference, 'rs0', 'rs1')
        for name in ('preprocess', 'inference', 'postprocess'):
            setattr(_det.DetectorLoader, name,
                    staticmethod(_wrap(getattr(_det.DetectorLoader, name), name + '0', name + '1')))
        _det.Detector._rescale_to_original = staticmethod(
            _wrap(_det.Detector._rescale_to_original, 'sc0', 'sc1'))
        orig_detect = _det.RFDetrLoader.detect

        def rfd(self, *args, **kw):
            m = getattr(self, '_model', None)
            if m is not None and not getattr(self, '_p0_hooked', False):
                self._p0_hooked = True
                try:
                    import torch
                    mod = getattr(getattr(m, 'model', None), 'model', None)
                    if isinstance(mod, torch.nn.Module):
                        mod.register_forward_pre_hook(lambda *x: _m('fw0'))
                        mod.register_forward_hook(lambda *x: _m('fw1'))
                    m.predict = _wrap(m.predict, 'pr0', 'pr1')
                except Exception as e:           # noqa: BLE001
                    _INSTALL_ERR.append(f"hooks: {type(e).__name__}: {e}")
            _m('rfd0')
            r = orig_detect(self, *args, **kw)
            _m('rfd1')
            return r
        _det.RFDetrLoader.detect = rfd
        _INSTALLED.append(True)


def _span(d, a, b):
    return (d[b] - d[a]) if (a in d and b in d) else None


def _record(d, n_dets):
    lk_held = _span(d, 'lk1', 'lk3')
    inside = [_span(d, 'rs0', 'rs1'), _span(d, 'preprocess0', 'preprocess1'),
              _span(d, 'inference0', 'inference1'), _span(d, 'postprocess0', 'postprocess1'),
              _span(d, 'sc0', 'sc1')]
    rec = {'t_wall': d.get('wall'), 'tid': _th.get_native_id(), 'n_dets': n_dets,
           'decode': _span(d, 't0', 'dec1'), 'lock_wait': _span(d, 'lk0', 'lk1'),
           'lock_held': lk_held, 'resize': inside[0], 'preprocess': inside[1],
           'inference': inside[2], 'loader_post': inside[3], 'rescale': inside[4],
           'predict_pre': _span(d, 'pr0', 'fw0'), 'forward': _span(d, 'fw0', 'fw1'),
           'predict_post': _span(d, 'fw1', 'pr1'), 'dict_build': _span(d, 'pr1', 'rfd1'),
           'inside_other': (lk_held - sum(x for x in inside if x is not None)) if lk_held is not None else None,
           'emit': _span(d, 'lk3', 'em1')}
    if _INSTALL_ERR:
        rec['instrument_error'] = _INSTALL_ERR[:3]
    try:
        with _WLOCK:
            with open(_OUT, 'a') as f:
                f.write(json.dumps(rec) + '\n')
    except Exception:                            # noqa: BLE001 — never the frame's problem
        pass


class IInstance(IInstanceBase):
    """
    Per-frame object detection for the detect node.

    Accepts an image lane (AVI stream). Emits per frame:
      - text lane: JSON array of detections [{label, score, box, centroid}].
      - image lane: annotated frame with bounding boxes + labels.
    """

    IGlobal: IGlobal

    def __init__(self, *args, **kwargs):
        """Initialize per-instance image-accumulation state."""
        super().__init__(*args, **kwargs)
        self._image_data = None

    def _annotate(self, image, detections):
        """Draw boxes + labels onto a copy of the image.

        Args:
            image: Source PIL image.
            detections: Canonical detection dicts.

        Returns:
            Annotated PIL image copy.
        """
        from PIL import ImageDraw

        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        for det in detections:
            b = det['box']
            draw.rectangle([b['x1'], b['y1'], b['x2'], b['y2']], outline='lime', width=2)
            draw.text((b['x1'], b['y1'] - 10), f'{det["label"]} {det["score"]:.2f}', fill='lime')
        return annotated

    def _emit(self, image, detections):
        """Write detections (text lane) and the annotated frame (image lane).

        Args:
            image: Source PIL image for this frame.
            detections: Canonical detection dicts.
        """
        if self.instance.hasListener('text'):
            self.instance.writeText(json.dumps(detections))

        if self.instance.hasListener('image'):
            image_bytes = ImageProcessor.get_bytes(self._annotate(image, detections), fmt='JPEG')
            self.instance.writeImage(AVI_ACTION.BEGIN, 'image/jpeg')
            self.instance.writeImage(AVI_ACTION.WRITE, 'image/jpeg', image_bytes)
            self.instance.writeImage(AVI_ACTION.END, 'image/jpeg')

    def writeImage(self, action: int, mimeType: str, buffer: bytes):
        """Accumulate an inbound image stream and run detection on END.

        Args:
            action: AVI stream action (BEGIN/WRITE/END).
            mimeType: MIME type of the image chunk.
            buffer: Raw bytes for a WRITE action.

        Returns:
            preventDefault() on END to suppress default forwarding; None otherwise.
        """
        if action == AVI_ACTION.BEGIN:
            self._image_data = bytearray()
        elif action == AVI_ACTION.WRITE:
            self._image_data += buffer
        elif action == AVI_ACTION.END:
            try:
                _install()
                _TL.d = {'wall': time.time()}
                _m('t0')
                t0 = time.perf_counter()
                image = ImageProcessor.load_image_from_bytes(self._image_data)
                _m('dec1')
                t_decode = (time.perf_counter() - t0) * 1000
                t0 = time.perf_counter()
                _m('lk0')
                with self.IGlobal.device_lock:
                    _m('lk1')
                    detections = self.IGlobal.detector.detect(image)
                _m('lk3')
                t_detect = (time.perf_counter() - t0) * 1000
                t0 = time.perf_counter()
                self._emit(image, detections)
                _m('em1')
                try:
                    _record(_TL.d, len(detections))
                except Exception:                # noqa: BLE001 — never the frame's problem
                    pass
                _TL.d = None
                t_emit = (time.perf_counter() - t0) * 1000
                debug(
                    f'detect: decode={t_decode:.0f}ms detect={t_detect:.0f}ms '
                    f'emit={t_emit:.0f}ms total={t_decode + t_detect + t_emit:.0f}ms'
                )
            except Exception as exc:
                warning(f'detect: dropping frame due to inference error: {exc}')
            finally:
                self._image_data = None
            return self.preventDefault()
