"""Minimal LlamaIndex PDF service — the same five stages, nothing that exists to measure them.

Functionally equivalent to working/ws1/{service,pipeline,schema}.py for the parity
configuration: same model, same chunk size/overlap, same splitter, same `text + "\n"` transform,
same pypdf extraction, same HTTP surface for /process_pdf. It is NOT a replacement — the ws1
service stays exactly as it is and remains what the benchmark runs. This exists only to put a
lower bound on the lines-of-code metric.

What is gone and why is listed line by line in ../REMOVED.md. In one sentence: everything here
makes the pipeline work; nothing here exists to prove that it worked.
"""
from __future__ import annotations

import io
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MODEL = os.environ.get("WS1_MODEL", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
CHUNK_SIZE = int(os.environ.get("WS1_CHUNK_SIZE", "4000"))
CHUNK_OVERLAP = int(os.environ.get("WS1_CHUNK_OVERLAP", "200"))
DEVICE = os.environ.get("WS1_DEVICE", "cpu")

# Set before torch/tokenizers import: HuggingFace tokenizers fork a thread pool that warns and
# can deadlock under a forking server, and uvicorn --workers forks. Load-bearing, so it stays.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_embed = None
_parser = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model before the worker accepts traffic.

    Kept, not cut: uvicorn does not route to a worker until lifespan startup completes, so this
    is what stops the first requests of a run paying a ~36 s torch import plus model load. A
    developer who omitted it would ship a service whose first users time out.
    """
    global _embed, _parser
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from llama_index.core.node_parser import LangchainNodeParser
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    _parser = LangchainNodeParser(RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, length_function=len))
    _embed = HuggingFaceEmbedding(model_name=MODEL, device=DEVICE)
    _embed.get_text_embedding_batch(["warmup"])
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    """One flag. A deployment needs a liveness probe; it does not need a census."""
    return {"status": "ok", "model_loaded": _embed is not None}


@app.post("/process_pdf")
async def process_pdf(request: Request):
    """Raw PDF bytes in, chunks + vectors out. Parse, split, embed — inside the service.

    Per-item faults return HTTP 200 with ok:false. That is not scaffolding: a caller must be able
    to tell "this document is bad" from "the service is broken", and 5xx has to stay reserved for
    the latter.
    """
    import pypdf
    from llama_index.core import Document

    if _embed is None or _parser is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    doc_id = request.headers.get("x-doc-id", "unknown")
    body = await request.body()
    if not body:
        return {"doc_id": doc_id, "ok": False, "error_class": "malformed_input",
                "error": "empty body"}
    try:
        reader = pypdf.PdfReader(io.BytesIO(body))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        return {"doc_id": doc_id, "ok": False, "error_class": "parse_failed",
                "error": f"{type(e).__name__}: {e}"}
    if not text.strip():
        return {"doc_id": doc_id, "ok": False, "error_class": "empty_extraction",
                "error": f"parser returned {len(text)} chars, none printable"}
    try:
        # The trailing newline is the canonical transform: the engine appends exactly one, and a
        # reference built without it fails chunk comparison on every multi-chunk document.
        nodes = _parser.get_nodes_from_documents([Document(text=text + "\n")])
        chunks = [n.get_content() for n in nodes]
        vecs = _embed.get_text_embedding_batch(chunks) if chunks else []
    except Exception as e:
        return {"doc_id": doc_id, "ok": False, "error_class": "embed_failed",
                "error": f"{type(e).__name__}: {e}"}
    return {"doc_id": doc_id, "ok": True, "n_chunks": len(chunks),
            "chunks": [{"chunk_id": i, "text": t, "embedding": e}
                       for i, (t, e) in enumerate(zip(chunks, vecs))]}
