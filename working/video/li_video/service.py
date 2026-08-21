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
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .pipeline import LlamaIndexVideoPipeline
from .schema import ErrorResponse, HealthResponse, ProcessVideoResponse

EMBED_MODEL = os.environ.get('WS1V_MODEL', 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1')
INTERVAL_S = int(os.environ.get('WS1V_INTERVAL_S', '15'))
THRESHOLD = float(os.environ.get('WS1V_THRESHOLD', '0.3'))
# 4000/200 matches MEASURED engine behaviour (re-ruled 2026-08-20): the
# engine's own chunk-size config is inert (kwargs-filter bug) and its splitter
# runs at LangChain library defaults. We benchmark what the engine DOES.
CHUNK_SIZE = int(os.environ.get('WS1V_CHUNK_SIZE', '4000'))
CHUNK_OVERLAP = int(os.environ.get('WS1V_CHUNK_OVERLAP', '200'))
SPLIT_UNIT = os.environ.get('WS1V_SPLIT_UNIT', 'chars')  # 'chars' matches engine strlen; see pipeline.py
DEVICE = os.environ.get('WS1V_DEVICE', 'cpu')
WORKERS = int(os.environ.get('WS1V_WORKERS', '1'))
WARM_ROOT = Path(os.environ.get('WS1V_WARM_DIR', '/tmp/ws1v_warm'))

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
        thread_env={k: os.environ.get(k) for k in THREAD_ENV_KEYS},
        split_unit=SPLIT_UNIT,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        interval_s=INTERVAL_S,
    )


@app.post('/process_video')
async def process_video(request: Request):
    """Body = raw video bytes. Sync model work runs in the threadpool; the
    pipeline's internal lock keeps one model call at a time per worker."""
    if _pipeline is None or not _pipeline.is_warm:
        return JSONResponse(status_code=503,
                            content=ErrorResponse(error='cold', pid=os.getpid()).model_dump())
    blob = await request.body()
    if not blob:
        return JSONResponse(status_code=400,
                            content=ErrorResponse(error='empty body', pid=os.getpid()).model_dump())
    t0 = time.monotonic()
    try:
        import anyio
        r = await anyio.to_thread.run_sync(_pipeline.process, blob)
    except Exception as exc:  # noqa: BLE001 — the wire carries the failure, never hides it
        return JSONResponse(status_code=500,
                            content=ErrorResponse(error='pipeline failure', pid=os.getpid(),
                                                  detail=repr(exc)).model_dump())
    ident = _pipeline.identity()
    return ProcessVideoResponse(
        n_frames=r.n_frames, n_detections=r.n_detections,
        detections_per_frame=r.detections_per_frame,
        total_chars=r.total_chars, n_chunks=r.n_chunks,
        chunk_chars=r.chunk_chars, chunk_sha256=r.chunk_sha256,
        embed_dim=r.embed_dim, embedding_norms=r.embedding_norms,
        frame_labels=r.frame_labels, frame_scores=r.frame_scores,
        frame_png_sha16=r.frame_png_sha16,
        stage_s=r.stage_s, wall_s=round(time.monotonic() - t0, 2),
        pid=os.getpid(), detect_impl=ident['detect_impl'],
        model_names=ident['model_names'],
        torch_num_threads=_torch_threads(), versions=_versions(),
    )
