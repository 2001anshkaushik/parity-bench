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
import os
import threading
import time

from rocketlib import IInstanceBase, AVI_ACTION, debug, warning
from ai.common.image import ImageProcessor
from .IGlobal import IGlobal

# =============================================================================
# S5-B PATCH — PATCHED-ENGINE, NOT OUT-OF-THE-BOX. Benchmark-only; lives in the tagged image
# rr:s5b-microbatch, built FROM rr:patched-video, which is never modified.
#
# The stock node detects each frame alone at END. This copy QUEUES decoded frames and runs ONE
# rfdetr predict() over S5B_BATCH of them (rfdetr already accepts a list, resizes each to one
# square resolution and torch.stacks them — the engine simply never passed more than one).
# Results are emitted in the ORIGINAL frame order, so the downstream text is identical whenever
# the detections are; a partial batch is flushed at closing(), the end of the video.
#
# The batched code path is used EVEN AT S5B_BATCH=1 (a list of one frame), so the null control
# "patched B=1 == stock" tests this file's reimplementation of the detector's output conversion,
# not merely that the image rebuilt. The conversion below is copied from the backend's rfdetr
# branch (ai/common/models/vision/detection.py, 3.3.1) and the rescale from Detector.detect.
#
# S5B_TAP=1 appends every emitted frame's detections (labels, scores, OUTPUT-space boxes) to
# S5B_TAP_OUT, keyed by video name and frame index, for the Tier 2 comparison.
# =============================================================================
S5B_BATCH = max(1, int(os.environ.get('S5B_BATCH', '1')))
S5B_TAP = os.environ.get('S5B_TAP', '') not in ('', '0')
S5B_TAP_OUT = os.environ.get('S5B_TAP_OUT', '/tmp/s5b_tap.jsonl')
_TAP_LOCK = threading.Lock()


class IInstance(IInstanceBase):
    """Per-frame object detection, micro-batched (S5-B patch; see the header)."""

    IGlobal: IGlobal

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._image_data = None
        self._pending = []
        self._video = None
        self._frame_idx = 0

    def open(self, obj):
        self._video = obj.name if getattr(obj, 'hasName', False) else None
        self._frame_idx = 0
        self._pending = []

    def _annotate(self, image, detections):
        from PIL import ImageDraw

        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        for det in detections:
            b = det['box']
            draw.rectangle([b['x1'], b['y1'], b['x2'], b['y2']], outline='lime', width=2)
            draw.text((b['x1'], b['y1'] - 10), f'{det["label"]} {det["score"]:.2f}', fill='lime')
        return annotated

    def _emit(self, image, detections):
        if self.instance.hasListener('text'):
            self.instance.writeText(json.dumps(detections))

        if self.instance.hasListener('image'):
            image_bytes = ImageProcessor.get_bytes(self._annotate(image, detections), fmt='JPEG')
            self.instance.writeImage(AVI_ACTION.BEGIN, 'image/jpeg')
            self.instance.writeImage(AVI_ACTION.WRITE, 'image/jpeg', image_bytes)
            self.instance.writeImage(AVI_ACTION.END, 'image/jpeg')

    def _detect_batch(self, images):
        """Detector.detect for a LIST: per-frame downscale, ONE predict(), per-frame conversion
        (the rfdetr branch of the backend, verbatim) and per-frame rescale to original size."""
        from ai.common.image.dense_resize import resize_for_inference
        from ai.common.models.vision.detection import Detector, DetectorLoader, _to_detection

        det = self.IGlobal.detector
        backend = det._bundle['detector'] if isinstance(getattr(det, '_bundle', None), dict) else None
        if det._proxy_mode or backend is None or backend._impl != 'rfdetr':
            return [det.detect(im) for im in images]          # not the path under test
        thr = det.threshold
        smalls, origs = [], []
        for im in images:
            small, orig = resize_for_inference(im, det._infer_max_edge)
            smalls.append(small)
            origs.append(orig)
        # The STOCK preprocessing, called rather than reimplemented: it converts any non-RGB frame
        # to RGB before predict(), exactly as Detector.detect does for one frame.
        prepped = DetectorLoader.preprocess(det._bundle, smalls, det._metadata)['images']
        preds_list = backend._model.predict(prepped, threshold=thr)
        if not isinstance(preds_list, list):
            preds_list = [preds_list]
        out_all = []
        for preds, small, (orig_w, orig_h) in zip(preds_list, smalls, origs):
            boxes = getattr(preds, 'xyxy', None)
            scores = getattr(preds, 'confidence', None)
            class_ids = getattr(preds, 'class_id', None)
            labels = getattr(preds, 'data', {}).get('class_name') if hasattr(preds, 'data') else None
            out = []
            if boxes is not None and scores is not None:
                for i in range(len(boxes)):
                    x1, y1, x2, y2 = [float(v) for v in boxes[i]]
                    score = float(scores[i])
                    if score < thr:
                        continue
                    if labels is not None:
                        label = str(labels[i])
                    elif class_ids is not None:
                        cid = int(class_ids[i])
                        label = str(backend._class_names.get(cid, cid))
                    else:
                        label = 'object'
                    out.append(_to_detection(label, score, x1, y1, x2, y2))
            out_all.append(Detector._rescale_to_original(out, small.size, orig_w, orig_h))
        return out_all

    def _tap(self, detections):
        if not S5B_TAP:
            return
        rec = {'video': self._video, 'frame': self._frame_idx, 'batch': S5B_BATCH,
               'dets': detections}
        with _TAP_LOCK:
            with open(S5B_TAP_OUT, 'a') as f:
                f.write(json.dumps(rec) + '\n')

    def _flush(self):
        if not self._pending:
            return
        images, self._pending = self._pending, []
        try:
            t0 = time.perf_counter()
            with self.IGlobal.device_lock:
                results = self._detect_batch(images)
            t_detect = (time.perf_counter() - t0) * 1000
            for image, detections in zip(images, results):
                self._emit(image, detections)
                self._tap(detections)
                self._frame_idx += 1
            debug(f'detect[s5b B={S5B_BATCH}]: {len(images)} frame(s) detect={t_detect:.0f}ms')
        except Exception as exc:
            warning(f'detect[s5b]: dropping {len(images)} frame(s) due to inference error: {exc}')

    def writeImage(self, action: int, mimeType: str, buffer: bytes):
        if action == AVI_ACTION.BEGIN:
            self._image_data = bytearray()
        elif action == AVI_ACTION.WRITE:
            self._image_data += buffer
        elif action == AVI_ACTION.END:
            try:
                self._pending.append(ImageProcessor.load_image_from_bytes(self._image_data))
                if len(self._pending) >= S5B_BATCH:
                    self._flush()
            except Exception as exc:
                warning(f'detect[s5b]: dropping frame due to decode error: {exc}')
            finally:
                self._image_data = None
            return self.preventDefault()

    def closing(self):
        self._flush()                 # the partial batch at the end of the video
