"""LlamaIndex video/detect pipeline — the two-stage lane as LlamaIndex work.

Parity by construction with engine 3.3.1 (each choice cites the engine
source it mirrors):

  frames:  the IDENTICAL ffmpeg binary (imageio-ffmpeg, same pinned version
           as the engine resolves -> byte-identical executable, proven by
           probe_frame_parity 2026-08-27: sha-equal binaries, byte-equal
           frames A==B==C on three films) with the engine-mirror flags
           ('fps=1/{interval}', '-fps_mode passthrough', '-vcodec png' —
           Ruling B 2026-08-27), reading the SPOOLED FILE like the engine
           reads its cache file (reader.py:418-437, :425) and writing
           frames TO DISK, loaded one at a time for detection.
           STREAMING REFACTOR (2026-08-27, adopting Leela's post-mortem fix
           2d7533b — her LG arm OOM-died at 42.7 GB buffering every frame
           of 32 films in flight): the old shape decoded the whole PNG
           stream into memory (subprocess stdout + a second sliced copy +
           the full frame list resident through detection). Frames now live
           on disk until detection reads them one at a time; bounded
           resident frames k=1. Muxer change image2pipe -> image2 files is
           certified byte-identical by probe_reader_equivalence before any
           measured leg (Ruling B: a byte difference there is a STOP and a
           finding, never a loosened comparison).
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
           tokenizer; size/overlap default 4000/0 — RULING L (2026-08-30,
           the separate round Ruling C promised). The engine's chunk config
           is inert and LangChain library defaults 4000/200 run, but
           LangChain realizes overlap in whole split units (~0 realized on
           the engine), while SentenceSplitter at 200 realized a true
           ~200/boundary — the AMI char_conservation 4.86% failure
           (DEFINITIVE §2.4: adopt 4000/0 on the comparison arm). We match
           what the engine DOES, and the writeup carries one line saying we
           supplied the length function.
  embed:   HuggingFaceEmbedding multi-qa-MiniLM-L6-cos-v1 (the exact string
           the engine's miniLM profile pins), device from WS1V_DEVICE.

Model load happens in warm(), called from the service lifespan per worker
(ws1 pattern — no request pays for torch import). One threading.Lock
serializes model calls within a worker: honest mirror of the engine's
per-process device_lock, and it makes 'requests per worker' a clean unit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Set before torch/tokenizers import (ws1 lesson): fork-safety warning + hangs.
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

# Which clock the stage stamps used — recorded on every response so legs from
# the two eras are never silently compared (2026-08-25 ruling).
STAGE_SEMANTICS = 'device_only'   # before 2026-08-25: 'includes_lock_wait'

# Which reader shape produced the frames — same discipline as STAGE_SEMANTICS
# and hashing_locus: eras are never silently compared (ruling 2026-08-27).
# Before this date the implicit value was 'buffered_pipe_in_memory'
# (subprocess.run(input=video), full stdout, all frames resident).
READER_SEMANTICS = 'spooled_file_frames_on_disk'


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
    chunks: list[str] = field(default_factory=list)   # texts; hashed driver-side
    embed_dim: int = 0
    frame_png_sha16: list[str] = field(default_factory=list)
    stage_s: dict[str, float] = field(default_factory=dict)
    frames_dir_bytes: int = 0     # disk high-water of the per-request frame dir


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
                 chunk_overlap: int = 0,
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
    def _extract_frames(self, video_path: str) -> tuple[str, list[str]]:
        """Decode the SPOOLED FILE to per-frame PNGs ON DISK; return
        (frames_dir, sorted paths). The caller owns the dir and removes it.

        Engine-mirror argv (Ruling B 2026-08-27): same filter, '-fps_mode
        passthrough', explicit '-vcodec png' — only the muxer changes,
        image2pipe -> image2 files (Leela's disk form, 2d7533b; her literal
        argv drops passthrough/vcodec and is proven count-equal only, so we
        keep the engine-anchored flags the parity probe certified byte-exact).
        File input matches the engine's cache-file topology (reader.py:425)
        and removes the moov-at-end pipe failure class outright.
        check=True stays: a decode failure REFUSES the request (the engine
        fails open here, reader.py:344 — we deliberately do not mirror that).
        """
        td = tempfile.mkdtemp(prefix='ws1v_frames_',
                              dir=os.environ.get('WS1V_SPOOL_DIR') or None)
        out = Path(td)
        cmd = [self._ffmpeg, '-nostdin', '-loglevel', 'error',
               '-i', str(video_path),
               '-vf', f'fps=1/{self.interval_s}',
               '-f', 'image2', '-fps_mode', 'passthrough',
               '-vcodec', 'png', str(out / 'f_%06d.png')]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(td, ignore_errors=True)
            tail = (e.stderr or b'')[-500:].decode('utf-8', 'replace')
            # Keep the true cause on the wire — the dap_client.py:229 lesson.
            raise RuntimeError(f'ffmpeg rc={e.returncode}: {tail}') from e
        return td, [str(p) for p in sorted(out.glob('f_*.png'))]

    @staticmethod
    def _load_frame(path: str):
        """One extracted PNG -> RGB, from disk (Leela's load_frame shape:
        same pixels the detector saw when frames were in memory — certified
        by probe_reader_equivalence's detect layer, not assumed)."""
        from PIL import Image
        with Image.open(path) as im:
            return im.convert('RGB').copy()

    def _detect_frame(self, img) -> list[dict]:
        preds = self._detector.predict(img, threshold=self.threshold)
        dets = []
        for k in range(len(preds)):
            cid = int(preds.class_id[k])
            dets.append(_to_detection(self._class_names.get(cid, str(cid)),
                                      float(preds.confidence[k]), *preds.xyxy[k]))
        return dets

    # --------------------------------------------------------------- process
    def process(self, video_path: str) -> VideoPipelineResult:
        """The full lane over a SPOOLED video file (the service streams the
        request body to disk and hands the path here — no whole-video bytes
        object exists anywhere in this process)."""
        if not self.is_warm:
            raise RuntimeError('pipeline not warm — lifespan did not run')
        r = VideoPipelineResult()

        t0 = time.monotonic()
        frames_dir, frame_paths = self._extract_frames(video_path)
        r.stage_s['extract'] = round(time.monotonic() - t0, 2)
        r.n_frames = len(frame_paths)
        r.frames_dir_bytes = sum(os.stat(p).st_size for p in frame_paths)
        # HASHING LOCUS (ruling 2026-08-25): NO hashing inside wall_s. Frame
        # hashes had no leg-gate consumer and are gone from the serving path
        # (the probe's floor hashing is separate code); chunk hashes are
        # computed DRIVER-side from the returned texts — the same place and
        # formula as the RocketRide arm's. Responses carry hashing_locus so
        # tonight's legs are never silently compared with the banked ones.

        per_frame_json: list[str] = []
        try:
            # STAMP SEMANTICS (2026-08-25, ruling): stamps INSIDE the lock so
            # stage_s measures the DEVICE, not the queue. Every response
            # carries stage_s_semantics so eras are never silently compared.
            # BOUNDED RESIDENCY (2026-08-27, Leela's form): one frame is
            # loaded from disk, detected, and freed per iteration — k=1.
            with self._lock:
                t0 = time.monotonic()
                for p in frame_paths:
                    img = self._load_frame(p)
                    dets = self._detect_frame(img)
                    r.detections_per_frame.append(len(dets))
                    r.frame_labels.append(sorted(d['label'] for d in dets))
                    r.frame_scores.append([d['score'] for d in dets])
                    per_frame_json.append(json.dumps(dets))
                r.stage_s['detect'] = round(time.monotonic() - t0, 2)
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)   # her cleanup-in-finally
        r.n_detections = sum(r.detections_per_frame)

        # Engine semantics: accumulate with '\n', split ONCE per video.
        blob = '\n'.join(per_frame_json) + '\n'
        r.total_chars = len(blob)
        t0 = time.monotonic()
        chunks = self._splitter.split_text(blob)
        r.stage_s['split'] = round(time.monotonic() - t0, 2)
        r.n_chunks = len(chunks)
        r.chunk_chars = [len(c) for c in chunks]
        r.chunks = chunks          # texts ride the response; the driver hashes them

        with self._lock:
            t0 = time.monotonic()
            vectors = self._embedder.get_text_embedding_batch(chunks, show_progress=False) \
                if chunks else []
            r.stage_s['embed'] = round(time.monotonic() - t0, 2)
        r.embed_dim = len(vectors[0]) if vectors else 0
        r.embedding_norms = [round(sum(x * x for x in v) ** 0.5, 6) for v in vectors]
        return r
