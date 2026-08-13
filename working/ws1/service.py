"""WS-1 LlamaIndex service — FastAPI + uvicorn.

Layering is deliberate:
    schema.py    the wire contract, isolated so it swaps when Leela's version lands
    pipeline.py  LlamaIndex work, knows nothing about HTTP
    service.py   HTTP only, constructs no wire dicts itself

Deployment follows LlamaIndex's own production guidance where it exists, and uvicorn's where
LlamaIndex is silent. Where BOTH are silent the call is recorded in TOIL_LLAMAINDEX.md rather
than left implicit — this is my framework in the parity study, so any tuning shortcut biases the
result against LlamaIndex and in favour of the others.

Run:
    ws1/run_service.sh                      # tuned defaults
    WS1_WORKERS=4 ws1/run_service.sh        # override
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .pipeline import LlamaIndexPipeline
from .schema import (
    ProcessRequest, ServiceConfig, build_error, build_manifest, build_response,
)

MODEL = os.environ.get("WS1_MODEL", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
CHUNK_SIZE = int(os.environ.get("WS1_CHUNK_SIZE", "4000"))
CHUNK_OVERLAP = int(os.environ.get("WS1_CHUNK_OVERLAP", "200"))
SPLITTER_MODE = os.environ.get("WS1_SPLITTER_MODE", "schema")
# cpu by default: matches RocketRide's CPU MiniLM path so parity compares frameworks,
# not silicon. Override with WS1_DEVICE=mps to measure the faster-but-unscalable path.
DEVICE = os.environ.get("WS1_DEVICE", "cpu")
WORKERS = int(os.environ.get("WS1_WORKERS", "1"))

_pipeline: LlamaIndexPipeline | None = None
_cfg: ServiceConfig | None = None
_lib_versions: dict = {}


def _library_versions() -> dict:
    import importlib.metadata as md

    out = {}
    for p in ("llama-index-core", "llama-index-embeddings-huggingface",
              "sentence-transformers", "torch", "transformers",
              "langchain-text-splitters", "fastapi", "uvicorn"):
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model at startup, per worker, BEFORE the worker accepts traffic.

    torch import is ~30 s and model load ~6 s. If this happened lazily on first request, the first
    N requests of every run would carry it and every latency number would be wrong. uvicorn does
    not route to a worker until its lifespan startup completes, so doing it here is what makes
    `/health`'s `model_loaded` flag trustworthy as a start gate for the driver.
    """
    global _pipeline, _cfg, _lib_versions
    t0 = time.perf_counter()
    _pipeline = LlamaIndexPipeline(model_name=MODEL, chunk_size=CHUNK_SIZE,
                                   chunk_overlap=CHUNK_OVERLAP,
                                   splitter_mode=SPLITTER_MODE,  # type: ignore[arg-type]
                                   device=DEVICE)
    _pipeline.warm()
    warm_s = time.perf_counter() - t0
    _lib_versions = _library_versions()
    _cfg = ServiceConfig(
        model_name=MODEL, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        splitter_name=_pipeline.splitter_name,
        device=DEVICE,
        resolved_device=_pipeline.resolved_device(),
        # MEASURED per device, not declared. The width is a property of the DEVICE, not of the
        # worker count: on cpu the knee is 8 (30.7 -> 86.5 -> 101.8 -> 100.9/s at conc 1/4/8/14),
        # on mps it is ~8 but unstable (spread 44-53%). An earlier reading of "4" was taken on mps
        # and is superseded. `uvicorn --workers` is NOT the width; declaring it would overstate
        # capacity ~1.75x on cpu.  n=3 randomised, see results/ws1_service_device.json
        effective_concurrency=int(os.environ.get(
            "WS1_MEASURED_CONCURRENCY", "8" if DEVICE == "cpu" else "8")),
        concurrency_source=(
            f"MEASURED knee on device={DEVICE}: throughput peaks at concurrency 8 "
            f"({'101.8/s, spread 3%' if DEVICE == 'cpu' else '192.1/s, spread 53% — UNSTABLE'}); "
            f"uvicorn --workers {WORKERS} is the DECLARED worker count, not the effective width. "
            f"Method: throughput-vs-concurrency sweep, n=3 randomised"),
        declared_workers=WORKERS,
        uvicorn_settings={
            "workers": WORKERS,
            "loop": os.environ.get("WS1_LOOP", "uvloop"),
            "http": os.environ.get("WS1_HTTP", "httptools"),
            "access_log": False,
            "limit_concurrency": None,
        },
    )
    # torch threads are reported from INSIDE the worker, not inferred from the env it was launched
    # with: torch caches its thread count at import, so an exported variable proves nothing. Thread
    # count is the largest single lever measured in this project (3.07x at concurrency 1), so an
    # arm-to-arm comparison that does not read this from the live worker is not matched.
    import torch as _t
    print(f"[ws1] worker {os.getpid()} warm in {warm_s:.1f}s "
          f"(splitter={_pipeline.splitter_name}, mode={SPLITTER_MODE}, "
          f"device declared={DEVICE} resolved={_pipeline.resolved_device()}, "
          f"torch_threads={_t.get_num_threads()} torch_interop={_t.get_num_interop_threads()})",
          flush=True)
    yield


app = FastAPI(title="WS-1 LlamaIndex service", lifespan=lifespan)


@app.get("/health")
async def health():
    """Cheap enough to poll during a run — does no model work."""
    return {
        "status": "ok",
        "service": "llamaindex",
        "model_loaded": bool(_pipeline and _pipeline.is_warm),
        "worker_pid": os.getpid(),
    }


@app.get("/manifest")
async def manifest():
    if _cfg is None or _pipeline is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    return build_manifest(_cfg, _lib_versions, _pipeline.is_warm, os.getpid())


def _maybe_inject(doc_id: str, text: str) -> None:
    """Fault injection for poison runs, driven by a directive in the payload.

    The directive travels IN THE PAYLOAD because faults must vary per item within one batch —
    that is what a partial-failure test is. Wire form: text beginning `FAULT:<kind>|` where kind
    is one of raise | hang | alloc | malformed. Anything else is a normal document, so ordinary
    traffic is unaffected and no separate endpoint is needed.

    Mapped onto the schema's error_class contract by the caller:
        raise      -> embed_failed      (an exception inside the work)
        malformed  -> malformed_input   (input that violates the contract)
        hang/alloc -> surface as timeout / resource pressure, not as a distinct class
    """
    if not text.startswith("FAULT:"):
        return
    kind = text.split("|", 1)[0][len("FAULT:"):]
    if kind == "raise":
        raise RuntimeError(f"injected fault on {doc_id}")
    if kind == "malformed":
        raise ValueError(f"injected malformed input on {doc_id}")
    if kind == "hang":
        time.sleep(float(os.environ.get("WS1_FAULT_HANG_S", "25")))
    if kind == "alloc":
        mb = int(os.environ.get("WS1_FAULT_ALLOC_MB", "256"))
        blob = bytearray(mb * 1024 * 1024)
        for off in range(0, len(blob), 4096):
            blob[off] = 1
        del blob


@app.post("/process_pdf")
async def process_pdf(request: Request):
    """Raw PDF bytes -> chunks + vectors, parsed INSIDE this service (Parser IN).

    The body is the PDF itself, not JSON: base64 in a JSON envelope would add ~33 % transfer and
    a decode step to the measured path for no benefit.

    Extraction faults surface as `parse_failed` / `empty_extraction` error classes. They used to be
    counted by the driver; if they were not returned here the fault taxonomy would read zero and
    look like an improvement.
    """
    pid = os.getpid()
    if _pipeline is None or _cfg is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    doc_id = request.headers.get("x-doc-id", "unknown")
    body = await request.body()
    if not body:
        return build_error(doc_id, "malformed_input", "empty body", _cfg, pid)

    t0 = time.perf_counter()
    try:
        text = _pipeline.extract(body)
    except Exception as e:
        return build_error(doc_id, "parse_failed", f"{type(e).__name__}: {e}", _cfg, pid)
    if not text.strip():
        return build_error(doc_id, "empty_extraction",
                           f"parser returned {len(text)} chars, none printable", _cfg, pid)

    try:
        chunks = _pipeline.split(text)
    except Exception as e:
        return build_error(doc_id, "split_failed", f"{type(e).__name__}: {e}", _cfg, pid)
    try:
        vecs = _pipeline.embed(chunks)
    except Exception as e:
        return build_error(doc_id, "embed_failed", f"{type(e).__name__}: {e}", _cfg, pid)

    out = build_response(doc_id, chunks, vecs, _cfg, pid, None)
    # The arm's OWN extracted text, so the per-arm chunk-hash gate can build its reference from it.
    # Under Parser IN a shared reference would false-fire on every document.
    out["extracted_text"] = text
    out["extracted_chars"] = len(text)
    out["parser"] = _pipeline.parser_version()
    out["timing_ms"] = {"total": round((time.perf_counter() - t0) * 1000, 3)}
    return out


@app.post("/process")
def process(req: ProcessRequest):
    """One document -> chunks + vectors.

    Declared `def`, not `async def`, on purpose. The work is CPU-bound (tokenise + forward pass);
    an `async def` endpoint would run it directly on the event loop and block every other request
    on this worker. Starlette dispatches sync endpoints to its threadpool instead, which keeps the
    loop free to accept and to answer `/health`. This is FastAPI's own documented guidance for
    blocking work and it is the single most consequential line in the file.

    Faults return HTTP 200 with `ok: false` — see schema.build_error for why.
    """
    pid = os.getpid()
    if _pipeline is None or _cfg is None:
        return JSONResponse({"status": "starting"}, status_code=503)

    t0 = time.perf_counter()
    try:
        _maybe_inject(req.doc_id, req.text)
    except ValueError as e:
        # Contract violation -> malformed_input, distinct from a failure during work.
        return build_error(req.doc_id, "malformed_input", f"{type(e).__name__}: {e}", _cfg, pid)
    except Exception as e:
        return build_error(req.doc_id, "embed_failed", f"{type(e).__name__}: {e}", _cfg, pid)

    try:
        chunks = _pipeline.split(req.text)
    except Exception as e:
        return build_error(req.doc_id, "split_failed", f"{type(e).__name__}: {e}", _cfg, pid)
    t1 = time.perf_counter()

    try:
        vecs = _pipeline.embed(chunks)
    except Exception as e:
        return build_error(req.doc_id, "embed_failed", f"{type(e).__name__}: {e}", _cfg, pid)
    t2 = time.perf_counter()

    timing = None
    if req.trace:
        timing = {
            "total": round((t2 - t0) * 1000, 3),
            "split": round((t1 - t0) * 1000, 3),
            "embed": round((t2 - t1) * 1000, 3),
        }
    return build_response(req.doc_id, chunks, vecs, _cfg, pid, timing)
