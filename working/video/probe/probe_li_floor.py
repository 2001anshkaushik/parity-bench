#!/usr/bin/env python3
"""LlamaIndex-arm MODEL FLOOR probe. Bare venv, no service, no HTTP.

Mirrors the engine's per-stage compute with the SAME weights, runtime and
parameters (verified against engine 3.3.1 source):

  frames:  ffmpeg (imageio-ffmpeg binary) -vf fps=1/INTERVAL,showinfo ->
           PNG image2pipe                       (frame.py filter string)
  detect:  rfdetr RFDETRBase().predict(threshold=0.3)   (detection.py:130-141)
  text:    per-frame json.dumps([{label,score,box,centroid}]) accumulated
           with '\n' joins, split ONCE          (detect/IInstance.py:79 +
                                                 preprocessor IInstance closing())
  split:   RecursiveCharacterTextSplitter() at LANGCHAIN LIBRARY DEFAULTS
           4000/200 — the ENGINE-REAL construction: its own size config is
           stripped by _filter_kwargs_for (adjudicated 2026-08-20), so the
           floor constructs with no kwargs, exactly like the engine does
           effectively
  embed:   sentence-transformers multi-qa-MiniLM-L6-cos-v1
           (embedding_transformer services.json miniLM profile)

This is a FLOOR, not a comparison: its outputs are the inference fraction,
the per-stage seconds, the independent frame count (verifies interval
semantics), the per-frame PNG hashes (cross-arm frame identity), and the
thread-scaling curve. The real LI arm is the service in ../li_video/.

Thread control: probe_run.sh exports the six variables; this script passes
PROBE_THREADS into torch and PRINTS read-backs from inside the process.

pip install imageio-ffmpeg rfdetr pillow numpy langchain-text-splitters sentence-transformers
(then record the resolved versions; the run plan pins them to the rr image's
engine/cache/constraints.txt — see ../li_video/extract_engine_pins.sh)
"""

import argparse
import hashlib
import io
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

THREADS = int(os.environ.get('PROBE_THREADS', '1'))
ENGINE_VAD_NOTE = 'audio out of scope this phase (settled decision 1)'


def versions() -> dict:
    from importlib.metadata import version, PackageNotFoundError
    out = {}
    for pkg in ['rfdetr', 'torch', 'torchvision', 'transformers', 'supervision',
                'sentence-transformers', 'langchain-text-splitters', 'imageio-ffmpeg',
                'pillow', 'numpy']:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


def readback() -> dict:
    import torch
    vals = {k: os.environ.get(k) for k in
            ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
             'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS']}
    vals['torch.get_num_threads'] = torch.get_num_threads()
    vals['PROBE_THREADS'] = THREADS
    return vals


def extract_frames(video: Path, interval: int) -> list[bytes]:
    import imageio_ffmpeg
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-loglevel', 'error',
           '-i', str(video), '-vf', f'fps=1/{interval}', '-f', 'image2pipe',
           '-fps_mode', 'passthrough', '-vcodec', 'png', '-']
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    sig = b'\x89PNG\r\n\x1a\n'
    frames, i = [], 0
    while True:
        j = raw.find(sig, i + 1)
        if j == -1:
            if i < len(raw):
                frames.append(raw[i:])
            break
        frames.append(raw[i:j])
        i = j
    return [f for f in frames if f.startswith(sig)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--interval', type=int, default=15)
    ap.add_argument('--out', default=str(Path(__file__).parent / f'probe_li_floor_t{THREADS}.json'))
    args = ap.parse_args()
    video = Path(args.video)

    report = {'threads_readback': readback(), 'versions': versions(),
              'interval_s': args.interval, 'stage_s': {}}
    print(json.dumps({'threads_readback': report['threads_readback']}))

    import torch
    torch.set_num_threads(THREADS)

    # ---- frames -----------------------------------------------------------
    t0 = time.monotonic()
    frames = extract_frames(video, args.interval)
    report['stage_s']['frame_extract_png'] = round(time.monotonic() - t0, 1)
    report['n_frames'] = len(frames)
    report['frame_png_sha16'] = [hashlib.sha256(f).hexdigest()[:16] for f in frames]
    print(f'frames: {len(frames)} in {report["stage_s"]["frame_extract_png"]}s')

    # ---- detect (identity asserted, not assumed: floor requires rfdetr) ----
    from PIL import Image
    import types
    sys.modules.setdefault('matplotlib.pyplot', types.ModuleType('matplotlib.pyplot'))  # engine's stub, mirrored
    from rfdetr import RFDETRBase  # ImportError here = floor cannot claim parity; fail loudly
    t0 = time.monotonic()
    detector = RFDETRBase()
    report['stage_s']['detr_load'] = round(time.monotonic() - t0, 1)
    report['detect_impl'] = 'rfdetr'  # the arm-level read-back lives in the service /health

    def to_detection(label, score, x1, y1, x2, y2):
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        return {'label': str(label), 'score': float(score),
                'box': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                'centroid': {'x': (x1 + x2) / 2.0, 'y': (y1 + y2) / 2.0}}

    per_frame_json, n_detections = [], 0
    t0 = time.monotonic()
    for fb in frames:
        img = Image.open(io.BytesIO(fb)).convert('RGB')
        preds = detector.predict(img, threshold=0.3)
        dets = []
        try:  # supervision Detections object (rfdetr's return type)
            class_names = getattr(detector, 'class_names', None) or {}
            for k in range(len(preds)):
                cid = int(preds.class_id[k])
                dets.append(to_detection(class_names.get(cid, str(cid)),
                                         float(preds.confidence[k]), *preds.xyxy[k]))
        except (TypeError, AttributeError):
            dets = [to_detection('unknown', 0.0, 0, 0, 0, 0)] if preds else []
        n_detections += len(dets)
        per_frame_json.append(json.dumps(dets))
    report['stage_s']['detect'] = round(time.monotonic() - t0, 1)
    report['n_detections'] = n_detections
    report['frame_label_multisets'] = [sorted(d['label'] for d in json.loads(fj))
                                       for fj in per_frame_json]
    report['frame_scores'] = [[d['score'] for d in json.loads(fj)] for fj in per_frame_json]
    report['detections_per_frame'] = round(n_detections / len(frames), 1) if frames else None
    print(f'detect: {n_detections} detections over {len(frames)} frames '
          f'in {report["stage_s"]["detect"]}s')

    # ---- accumulate + split (engine semantics: one blob, one split) -------
    blob = '\n'.join(per_frame_json) + '\n'
    report['total_chars'] = len(blob)
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    t0 = time.monotonic()
    # No kwargs ON PURPOSE: mirrors the engine's effective construction
    # (kwargs-filtered -> library defaults 4000/200).
    chunks = RecursiveCharacterTextSplitter().split_text(blob)
    report['stage_s']['split'] = round(time.monotonic() - t0, 2)
    lens = [len(c) for c in chunks]
    report['n_chunks'] = len(chunks)
    report['chunk_chars_min_mean_max'] = ([min(lens), round(sum(lens) / len(lens), 1), max(lens)]
                                          if lens else None)

    # ---- embed -------------------------------------------------------------
    from sentence_transformers import SentenceTransformer
    t0 = time.monotonic()
    model = SentenceTransformer('sentence-transformers/multi-qa-MiniLM-L6-cos-v1', device='cpu')
    report['stage_s']['embed_load'] = round(time.monotonic() - t0, 1)
    t0 = time.monotonic()
    vecs = model.encode(chunks, batch_size=64, show_progress_bar=False)
    report['stage_s']['embed'] = round(time.monotonic() - t0, 1)
    report['embed_dim'] = int(vecs.shape[1]) if len(chunks) else None

    total = sum(report['stage_s'].values())
    inference = report['stage_s']['detect'] + report['stage_s']['embed']
    report['total_s'] = round(total, 1)
    report['inference_fraction_of_floor'] = round(inference / total, 3) if total else None
    report['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1) \
        if sys.platform == 'linux' else round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 1)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != 'frame_png_sha16'}, indent=1))
    print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
