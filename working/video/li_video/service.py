"""WS-1 Phase 2 video/detect LlamaIndex service — FastAPI + uvicorn.

Layering per ws1: schema.py = wire contract, pipeline.py = LlamaIndex work,
service.py = HTTP only. Model load in lifespan, per worker, BEFORE traffic
(ws1/service.py:97-107 pattern). Worker identity markers use supervisor-pid +
start-time keys (defect #23: container PID namespaces reuse low pids across
restarts).

CONCURRENCY IS A PARAMETER, NOT A DECISION: WS1V_WORKERS is read by uvicorn
and echoed by /health. Its value for measured runs comes from the probe's
token-topology census (HELD until the probe reports). Every response carries
the serving pid, so distinct-instances-serving is read back from responses,
never inferred from config.

Run:
    uvicorn working.video.li_video.service:app --port 8802 --workers ${WS1V_WORKERS}
(the Dockerfile's entrypoint does exactly this)
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .pipeline import READER_SEMANTICS, STAGE_SEMANTICS, LlamaIndexVideoPipeline
from .schema import ErrorResponse, HealthResponse, ProcessVideoResponse

# Ruling A (2026-08-27), recorded where the export will carry it: we adopt
# Leela's memory discipline from her films500 OOM post-mortem (her commit
# 2d7533b — stream, never buffer; frames on disk; detect one at a time) but
# KEEP our raw octet-stream wire contract, streamed via request.stream(),
# instead of her MultipartEncoder: multipart would change the wire contract,
# add a dependency to a frozen image, and add a server-side parser — three
# failure surfaces for a memory property request.stream() already gives.
WIRE_DEVIATION = ('adopted 2d7533b memory discipline; kept raw octet-stream '
                  'body via request.stream() (no MultipartEncoder — Ruling A '
                  '2026-08-27)')

EMBED_MODEL = os.environ.get('WS1V_MODEL', 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1')
INTERVAL_S = int(os.environ.get('WS1V_INTERVAL_S', '15'))
THRESHOLD = float(os.environ.get('WS1V_THRESHOLD', '0.3'))
# 4000/0 — RULING L (2026-08-30, Ruling C's second half). The engine's own
# chunk config is inert (kwargs-filter bug) and its splitter runs at LangChain
# library defaults 4000/200 — but LangChain REALIZES overlap in whole split
# units (nothing retained on long-line regimes; only short lines on films),
# while SentenceSplitter at 200 realized a true ~200 chars/boundary: the AMI
# char_conservation 4.86% failure (CHAR_CONSERVATION_MECHANISM.md; DEFINITIVE
# §2.4 — "adopt 4000/0 on the comparison arm"). We benchmark what the engine
# DOES, so the comparison arm carries overlap 0. /health reports the values
# this process loaded; the films sweep probe refuses any other read-back.
CHUNK_SIZE = int(os.environ.get('WS1V_CHUNK_SIZE', '4000'))
CHUNK_OVERLAP = int(os.environ.get('WS1V_CHUNK_OVERLAP', '0'))
SPLIT_UNIT = os.environ.get('WS1V_SPLIT_UNIT', 'chars')  # 'chars' matches engine strlen; see pipeline.py
DEVICE = os.environ.get('WS1V_DEVICE', 'cpu')
WORKERS = int(os.environ.get('WS1V_WORKERS', '1'))
WARM_ROOT = Path(os.environ.get('WS1V_WARM_DIR', '/tmp/ws1v_warm'))
# Spool + frames dir root (streaming refactor 2026-08-27). None = system tmp.
SPOOL_DIR = os.environ.get('WS1V_SPOOL_DIR') or None

THREAD_ENV_KEYS = ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                   'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS']

_pipeline: LlamaIndexVideoPipeline | None = None


def _supervisor_key() -> str:
    """pid+start-time of the uvicorn supervisor — pid alone is NOT unique across
    container restarts (defect #23)."""
    ppid = os.getppid()
    try:
        with open(f'/proc/{ppid}/stat') as fh:
            starttime = fh.read().rsplit(')', 1)[1].split()[19]
    except OSError:
        starttime = 'na'
    return f'{ppid}_{starttime}'


def _mark_warm() -> None:
    d = WARM_ROOT / _supervisor_key()
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{os.getpid()}').write_text(str(time.time()))


def _warm_workers() -> int:
    d = WARM_ROOT / _supervisor_key()
    return len(list(d.glob('*'))) if d.exists() else 0


def _versions() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ['rfdetr', 'torch', 'torchvision', 'transformers', 'supervision',
                'llama-index-core', 'llama-index-embeddings-huggingface',
                'sentence-transformers', 'imageio-ffmpeg', 'fastapi', 'uvicorn']:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


def _torch_threads() -> int:
    import torch
    return torch.get_num_threads()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    _pipeline = LlamaIndexVideoPipeline(
        embed_model_name=EMBED_MODEL, interval_s=INTERVAL_S, threshold=THRESHOLD,
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        split_unit=SPLIT_UNIT, device=DEVICE)
    _pipeline.warm()          # refuses (ImportError) rather than falling back — identity over uptime
    _mark_warm()
    yield


app = FastAPI(title='WS-1 video/detect LlamaIndex service', lifespan=lifespan)


@app.get('/health')
async def health() -> HealthResponse:
    ident = _pipeline.identity() if _pipeline else {'detect_impl': 'NOT-LOADED', 'model_names': {}}
    return HealthResponse(
        status='ok' if _pipeline and _pipeline.is_warm else 'cold',
        pid=os.getpid(),
        warm=bool(_pipeline and _pipeline.is_warm),
        warm_workers=_warm_workers(),
        declared_workers=WORKERS,
        detect_impl=ident['detect_impl'],
        model_names=ident['model_names'],
        versions=_versions(),
        torch_num_threads=_torch_threads(),
        python_version=__import__('sys').version.split()[0],
        thread_env={k: os.environ.get(k) for k in THREAD_ENV_KEYS},
        split_unit=SPLIT_UNIT,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        interval_s=INTERVAL_S,
        reader_semantics=READER_SEMANTICS,
        wire_deviation=WIRE_DEVIATION,
        spool_dir=SPOOL_DIR or tempfile.gettempdir(),
    )


@app.post('/process_video')
async def process_video(request: Request):
    """Body = raw video bytes, STREAMED to a spool file (never held whole —
    streaming refactor 2026-08-27, adopting 2d7533b's memory discipline with
    the Ruling-A wire deviation recorded in WIRE_DEVIATION). Sync model work
    runs in the threadpool; the pipeline's internal lock keeps one model call
    at a time per worker."""
    if _pipeline is None or not _pipeline.is_warm:
        return JSONResponse(status_code=503,
                            content=ErrorResponse(error='cold', pid=os.getpid()).model_dump())
    t0 = time.monotonic()
    spool = tempfile.NamedTemporaryFile(delete=False, dir=SPOOL_DIR,
                                        prefix='ws1v_spool_', suffix='.vid')
    bytes_spooled = 0
    try:
        try:
            with spool as fh:
                async for chunk in request.stream():
                    fh.write(chunk)
                    bytes_spooled += len(chunk)
        except Exception as exc:  # noqa: BLE001 — a broken upload is the client's failure, said plainly
            return JSONResponse(status_code=400,
                                content=ErrorResponse(error='body stream failed',
                                                      pid=os.getpid(),
                                                      detail=repr(exc)).model_dump())
        if bytes_spooled == 0:
            return JSONResponse(status_code=400,
                                content=ErrorResponse(error='empty body', pid=os.getpid()).model_dump())
        try:
            import anyio
            r = await anyio.to_thread.run_sync(_pipeline.process, spool.name)
        except Exception as exc:  # noqa: BLE001 — the wire carries the failure, never hides it
            return JSONResponse(status_code=500,
                                content=ErrorResponse(error='pipeline failure', pid=os.getpid(),
                                                      detail=repr(exc)).model_dump())
    finally:
        try:
            os.unlink(spool.name)
        except OSError:
            pass
    ident = _pipeline.identity()
    return ProcessVideoResponse(
        n_frames=r.n_frames, n_detections=r.n_detections,
        detections_per_frame=r.detections_per_frame,
        total_chars=r.total_chars, n_chunks=r.n_chunks,
        chunk_chars=r.chunk_chars, chunks=r.chunks,
        hashing_locus='driver_post_response',
        embed_dim=r.embed_dim, embedding_norms=r.embedding_norms,
        frame_labels=r.frame_labels, frame_scores=r.frame_scores,
        stage_s=r.stage_s, stage_s_semantics=STAGE_SEMANTICS,
        reader_semantics=READER_SEMANTICS,
        bytes_spooled=bytes_spooled, frames_dir_bytes=r.frames_dir_bytes,
        wall_s=round(time.monotonic() - t0, 2),
        pid=os.getpid(), detect_impl=ident['detect_impl'],
        model_names=ident['model_names'],
        torch_num_threads=_torch_threads(), versions=_versions(),
    )
