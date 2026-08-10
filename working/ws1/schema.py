"""WS-1 wire schema — ISOLATED so it swaps cheaply when Leela's version lands.

Everything that touches the wire format lives here and nowhere else. The service imports
`ProcessRequest`, `build_response`, `build_error`, `build_manifest` and never constructs a wire
dict itself. If the agreed contract differs from `SCHEMA_PROPOSAL.md`, this file changes and
`service.py` does not.

Contract source: `benchmark-A/SCHEMA_PROPOSAL.md` v0.2 (PROPOSED, not yet agreed).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.2"

ErrorClass = Literal["split_failed", "embed_failed", "malformed_input", "timeout", "internal"]


# --------------------------------------------------------------------------- canonical encoder
def canonical_bytes(obj: Any) -> bytes:
    """The one encoder every service and the harness must use for hashing and byte sizes.

    Separators without spaces, no key sorting, `ensure_ascii=False`, UTF-8. Float formatting is
    the likeliest cross-service byte mismatch (numpy vs stdlib vs orjson all differ), which is why
    SCHEMA_PROPOSAL recommends tolerance-based vector comparison and exact-byte comparison only
    for chunk text.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------- request
class ProcessRequest(BaseModel):
    doc_id: str
    text: str
    trace: bool = False


# --------------------------------------------------------------------------- response builders
def build_meta(cfg: "ServiceConfig", worker_pid: int) -> dict:
    return {
        "service": cfg.service_name,
        "service_version": cfg.service_version,
        "embedding_model": cfg.model_name,
        "embedding_dim": cfg.embedding_dim,
        "normalized": True,
        "device": cfg.device,
        "resolved_device": cfg.resolved_device,
        "splitter": cfg.splitter_name,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        # Concurrency pinning — see SCHEMA_PROPOSAL section 4. Every response carries BOTH the
        # number and how it was arrived at, because a service can declare anything and the
        # declared value has to be auditable against a measured one.
        "effective_concurrency": cfg.effective_concurrency,
        "declared_workers": cfg.declared_workers,
        "concurrency_source": cfg.concurrency_source,
        "worker_pid": worker_pid,
        "schema_version": SCHEMA_VERSION,
    }


def build_response(doc_id: str, chunks: list[str], embeddings: list[list[float]],
                   cfg: "ServiceConfig", worker_pid: int,
                   timing_ms: dict | None = None) -> dict:
    out: dict = {
        "doc_id": doc_id,
        "ok": True,
        "n_chunks": len(chunks),
        "chunks": [
            {"chunk_id": i, "text": t, "embedding": e}
            for i, (t, e) in enumerate(zip(chunks, embeddings))
        ],
        "meta": build_meta(cfg, worker_pid),
    }
    if timing_ms is not None:
        out["timing_ms"] = timing_ms
    return out


def build_error(doc_id: str, error_class: ErrorClass, error: str,
                cfg: "ServiceConfig", worker_pid: int,
                timing_ms: dict | None = None) -> dict:
    """Per-item failure. Returned with HTTP 200 by design — see SCHEMA_PROPOSAL section 3.

    A per-item fault is data, not a transport error. RocketRide already reports node exceptions as
    a per-item `error` key on an otherwise normal response; if this service raised a 5xx instead,
    a poison-run harness would be measuring the error convention rather than fault isolation.
    5xx stays reserved for the service itself being broken.
    """
    out: dict = {
        "doc_id": doc_id,
        "ok": False,
        "error_class": error_class,
        "error": error[:500],
        "meta": build_meta(cfg, worker_pid),
    }
    if timing_ms is not None:
        out["timing_ms"] = timing_ms
    return out


def build_manifest(cfg: "ServiceConfig", library_versions: dict,
                   model_warm: bool, worker_pid: int) -> dict:
    """The config ACTUALLY in effect — read from live objects by the caller, not from constants."""
    return {
        "service": cfg.service_name,
        "service_version": cfg.service_version,
        "library_versions": library_versions,
        "embedding_model": cfg.model_name,
        "embedding_dim": cfg.embedding_dim,
        "normalized": True,
        "device": cfg.device,
        "resolved_device": cfg.resolved_device,
        "splitter": cfg.splitter_name,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        "input_transform": cfg.input_transform,
        "effective_concurrency": cfg.effective_concurrency,
        "declared_workers": cfg.declared_workers,
        "concurrency_source": cfg.concurrency_source,
        "uvicorn": cfg.uvicorn_settings,
        "model_warm": model_warm,
        "worker_pid": worker_pid,
        "schema_version": SCHEMA_VERSION,
    }


# --------------------------------------------------------------------------- config
class ServiceConfig(BaseModel):
    service_name: str = "llamaindex"
    service_version: str = "0.1.0"
    model_name: str = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
    embedding_dim: int = 384
    device: str = "cpu"           # DECLARED device
    resolved_device: str = "cpu"  # what the model ACTUALLY loaded onto; asserted equal at startup
    splitter_name: str = "RecursiveCharacterTextSplitter"
    chunk_size: int = 4000
    chunk_overlap: int = 200
    input_transform: str = "text + '\\n'"
    effective_concurrency: int = 1        # MEASURED width, not worker count
    declared_workers: int = 1             # what the config asked for
    concurrency_source: str = "unset"     # how the measured number was obtained
    uvicorn_settings: dict = Field(default_factory=dict)
