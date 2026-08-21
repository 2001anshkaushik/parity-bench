"""LlamaIndex video/detect pipeline — the two-stage lane as LlamaIndex work.

Parity by construction with engine 3.3.1 (each choice cites the engine
source it mirrors):

  frames:  the IDENTICAL ffmpeg binary (imageio-ffmpeg, same pinned version
           as the engine resolves -> byte-identical executable) with the
           identical filter string 'fps=1/{interval}' -> PNG image2pipe
           (ai/common/avi/frame.py builds exactly this).
  detect:  rfdetr RFDETRBase().predict(image, threshold=0.3), canonical
           detection dicts {label, score, box, centroid} serialized with
           json.dumps — byte-shaped like nodes/detect/IInstance.py:79.
           NO silent fallback: if rfdetr does not import, this arm REFUSES
           to serve (the engine falls back to RT-DETR silently; we surface
           identity instead of imitating the silence).
  text:    per-frame JSON accumulated with '\n' joins, split ONCE per video
           (preprocessor_langchain IInstance.writeText/closing semantics —
           a naive per-frame split would silently diverge chunk counts).
  split:   LlamaIndex-NATIVE SentenceSplitter (approved decision 3;
           cross-arm chunk-hash equality stays declined). Size semantics:
           WS1V_SPLIT_UNIT='chars' (default) passes a character-length
           tokenizer; size/overlap default 4000/200 to match MEASURED engine
           behaviour (re-ruled 2026-08-20: the engine's chunk config is inert
           and LangChain library defaults run — we match what the engine
           DOES, and the writeup carries one line saying we supplied the
           length function).
  embed:   HuggingFaceEmbedding multi-qa-MiniLM-L6-cos-v1 (the exact string
           the engine's miniLM profile pins), device from WS1V_DEVICE.

Model load happens in warm(), called from the service lifespan per worker
(ws1 pattern — no request pays for torch import). One threading.Lock
serializes model calls within a worker: honest mirror of the engine's
per-process device_lock, and it makes 'requests per worker' a clean unit.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field

# Set before torch/tokenizers import (ws1 lesson): fork-safety warning + hangs.
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

PNG_SIG = b'\x89PNG\r\n\x1a\n'


@dataclass
class VideoPipelineResult:
    n_frames: int = 0
    n_detections: int = 0
    detections_per_frame: list[int] = field(default_factory=list)
    frame_labels: list[list[str]] = field(default_factory=list)
    frame_scores: list[list[float]] = field(default_factory=list)
    embedding_norms: list[float] = field(default_factory=list)
    total_chars: int = 0
    n_chunks: int = 0
    chunk_chars: list[int] = field(default_factory=list)
    chunk_sha256: list[str] = field(default_factory=list)
    embed_dim: int = 0
    frame_png_sha16: list[str] = field(default_factory=list)
    stage_s: dict[str, float] = field(default_factory=dict)


def _to_detection(label: str, score: float, x1, y1, x2, y2) -> dict:
    # Byte-shaped like ai/common/models/vision/detection.py:_to_detection.
    x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    return {'label': str(label), 'score': float(score),
            'box': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
            'centroid': {'x': (x1 + x2) / 2.0, 'y': (y1 + y2) / 2.0}}


class LlamaIndexVideoPipeline:
    def __init__(self,
                 embed_model_name: str = 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1',
                 interval_s: int = 15,
                 threshold: float = 0.3,
                 chunk_size: int = 4000,
                 chunk_overlap: int = 200,
                 split_unit: str = 'chars',
                 device: str = 'cpu'):
        self.embed_model_name = embed_model_name
        self.interval_s = interval_s
        self.threshold = threshold
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.split_unit = split_unit
        self.device = device
        self._detector = None
        self._embedder = None
        self._splitter = None
        self._ffmpeg = None
        self._class_names: dict = {}
        self._lock = threading.Lock()  # engine mirror: one model instance per process, serialized

    # ------------------------------------------------------------------ warm
    def warm(self) -> None:
        """Load everything, per worker, before traffic (ws1 lifespan pattern)."""
        import imageio_ffmpeg
        self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        import sys
        import types
        # supervision imports matplotlib.pyplot at module load; the engine stubs it
        # (detection.py:121-128) — mirror the stub, not the crash.
        sys.modules.setdefault('matplotlib.pyplot', types.ModuleType('matplotlib.pyplot'))
        from rfdetr import RFDETRBase  # ImportError = arm refuses to serve (no silent RT-DETR)
        self._detector = RFDETRBase()
        self._class_names = getattr(self._detector, 'class_names', None) or {}

        from llama_index.core.node_parser import SentenceSplitter
        if self.split_unit == 'chars':
            # Native algorithm, character length semantics: len(tokenizer(t)) == len(t).
            self._splitter = SentenceSplitter(chunk_size=self.chunk_size,
                                              chunk_overlap=self.chunk_overlap,
                                              tokenizer=lambda text: text)
        else:
            self._splitter = SentenceSplitter(chunk_size=self.chunk_size,
                                              chunk_overlap=self.chunk_overlap)

        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        self._embedder = HuggingFaceEmbedding(model_name=self.embed_model_name,
                                              device=self.device)
        # First-inference warm so no request pays allocator/JIT cost.
        self._embedder.get_text_embedding_batch(['warm'])

    @property
    def is_warm(self) -> bool:
        return self._embedder is not None and self._detector is not None

    def identity(self) -> dict:
        return {
            'detect_impl': 'rfdetr' if self._detector is not None else 'NOT-LOADED',
            'model_names': {
                'detector': type(self._detector).__name__ if self._detector else 'NOT-LOADED',
                'embedder': self.embed_model_name,
            },
        }

    # --------------------------------------------------------------- stages
    def _extract_frames(self, video: bytes) -> list[bytes]:
        cmd = [self._ffmpeg, '-nostdin', '-loglevel', 'error', '-i', 'pipe:0',
               '-vf', f'fps=1/{self.interval_s}', '-f', 'image2pipe',
               '-fps_mode', 'passthrough', '-vcodec', 'png', '-']
        raw = subprocess.run(cmd, input=video, check=True, capture_output=True).stdout
        frames, i = [], 0
        while True:
            j = raw.find(PNG_SIG, i + 1)
            if j == -1:
                if i < len(raw):
                    frames.append(raw[i:])
                break
            frames.append(raw[i:j])
            i = j
        return [f for f in frames if f.startswith(PNG_SIG)]

    def _detect_frame(self, png: bytes) -> list[dict]:
        from PIL import Image
        img = Image.open(io.BytesIO(png)).convert('RGB')
        preds = self._detector.predict(img, threshold=self.threshold)
        dets = []
        for k in range(len(preds)):
            cid = int(preds.class_id[k])
            dets.append(_to_detection(self._class_names.get(cid, str(cid)),
                                      float(preds.confidence[k]), *preds.xyxy[k]))
        return dets

    # --------------------------------------------------------------- process
    def process(self, video: bytes) -> VideoPipelineResult:
        if not self.is_warm:
            raise RuntimeError('pipeline not warm — lifespan did not run')
        r = VideoPipelineResult()

        t0 = time.monotonic()
        frames = self._extract_frames(video)
        r.stage_s['extract'] = round(time.monotonic() - t0, 2)
        r.n_frames = len(frames)
        r.frame_png_sha16 = [hashlib.sha256(f).hexdigest()[:16] for f in frames]

        per_frame_json: list[str] = []
        t0 = time.monotonic()
        with self._lock:
            for png in frames:
                dets = self._detect_frame(png)
                r.detections_per_frame.append(len(dets))
                r.frame_labels.append(sorted(d['label'] for d in dets))
                r.frame_scores.append([d['score'] for d in dets])
                per_frame_json.append(json.dumps(dets))
        r.stage_s['detect'] = round(time.monotonic() - t0, 2)
        r.n_detections = sum(r.detections_per_frame)

        # Engine semantics: accumulate with '\n', split ONCE per video.
        blob = '\n'.join(per_frame_json) + '\n'
        r.total_chars = len(blob)
        t0 = time.monotonic()
        chunks = self._splitter.split_text(blob)
        r.stage_s['split'] = round(time.monotonic() - t0, 2)
        r.n_chunks = len(chunks)
        r.chunk_chars = [len(c) for c in chunks]
        r.chunk_sha256 = [hashlib.sha256(c.encode()).hexdigest() for c in chunks]

        t0 = time.monotonic()
        with self._lock:
            vectors = self._embedder.get_text_embedding_batch(chunks, show_progress=False) \
                if chunks else []
        r.stage_s['embed'] = round(time.monotonic() - t0, 2)
        r.embed_dim = len(vectors[0]) if vectors else 0
        r.embedding_norms = [round(sum(x * x for x in v) ** 0.5, 6) for v in vectors]
        return r
