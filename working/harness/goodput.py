"""GOODPUT GATE — proves a run actually did the work, not merely returned 200.

WHY THIS EXISTS
---------------
`llama_index.core` maps `.pdf -> PDFReader` from `llama-index-readers-file`. When that package is
absent it **warns and returns `{}`** — no exception, no error status. A 10,000-document PDF run
would then produce 10,000 HTTP 200s with flat memory and zero embeddings, and would look like a
triumphant stability demo. Measured directly on this machine before the reader was addressed:
`SimpleDirectoryReader.supported_suffix_fn()` returned **0 suffixes**.

That is the single most dangerous failure mode for the container demo, because every surface
signal (status codes, throughput, memory) looks healthy. So goodput is asserted per document and
failure is LOUD.

PER-DOCUMENT ASSERTIONS
  1. n_chunks > 0
  2. every chunk's text is non-empty after strip
  3. one vector per chunk
  4. every vector is EMBED_DIM (384) long
  5. every vector is L2-normalised to 1.0 within tolerance  <- catches zero/garbage vectors,
     which a dimension check alone would pass
  6. vectors are not all-identical across distinct chunks   <- catches a stuck/constant encoder

A run in which any document fails is not a run. There is no "mostly fine" mode.
"""
from __future__ import annotations

import math

EMBED_DIM = 384
L2_TOL = 1e-2


class GoodputFailure(AssertionError):
    """Raised when a document did not actually get processed. Never caught silently."""


def check_document(doc_id: str, chunks, vectors) -> dict:
    """Assert one document really produced embeddings. Returns per-doc goodput evidence."""
    if chunks is None or vectors is None:
        raise GoodputFailure(f"{doc_id}: chunks or vectors is None — the silent-{{}} path")
    if len(chunks) == 0:
        raise GoodputFailure(
            f"{doc_id}: n_chunks == 0. Either the document yielded no text (a PDF the reader "
            f"could not parse) or no reader was registered for its type.")
    if len(vectors) != len(chunks):
        raise GoodputFailure(f"{doc_id}: {len(chunks)} chunks but {len(vectors)} vectors")
    empties = [i for i, c in enumerate(chunks) if not str(c).strip()]
    if empties:
        raise GoodputFailure(f"{doc_id}: {len(empties)} empty chunk(s) at {empties[:5]}")
    norms = []
    for i, v in enumerate(vectors):
        if len(v) != EMBED_DIM:
            raise GoodputFailure(f"{doc_id}: vector {i} has dim {len(v)}, expected {EMBED_DIM}")
        n = math.sqrt(sum(float(x) * float(x) for x in v))
        if not math.isfinite(n):
            raise GoodputFailure(f"{doc_id}: vector {i} contains non-finite values")
        if abs(n - 1.0) > L2_TOL:
            raise GoodputFailure(
                f"{doc_id}: vector {i} L2 norm {n:.6f}, expected 1.0 +/- {L2_TOL} "
                f"(a zero or garbage vector passes a dimension check but not this)")
        norms.append(n)
    if len(vectors) > 1:
        a, b = vectors[0], vectors[-1]
        if chunks[0] != chunks[-1] and all(abs(float(x) - float(y)) < 1e-9 for x, y in zip(a, b)):
            raise GoodputFailure(
                f"{doc_id}: identical vectors for different chunks — encoder appears stuck")
    return {"doc_id": doc_id, "n_chunks": len(chunks),
            "chars": sum(len(str(c)) for c in chunks),
            "l2_min": round(min(norms), 6), "l2_max": round(max(norms), 6)}


def summarise(evidence: list[dict]) -> dict:
    if not evidence:
        return {"docs": 0, "goodput": 0.0}
    return {"docs": len(evidence),
            "total_chunks": sum(e["n_chunks"] for e in evidence),
            "total_chars": sum(e["chars"] for e in evidence),
            "min_chunks_per_doc": min(e["n_chunks"] for e in evidence),
            "l2_min_observed": min(e["l2_min"] for e in evidence),
            "l2_max_observed": max(e["l2_max"] for e in evidence),
            "goodput": 1.0}
