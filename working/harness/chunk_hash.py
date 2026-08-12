"""Chunk-hash verification against an offline single-threaded reference.

**Approach adopted from Leela's `bench_langgraph_prod`** (`pdf1k/ground_truth.py`,
`pdf1k/validate_rep.py`, commit `b9b4736`). Her benchmark verifies that each arm returns the
*expected content*, not merely well-formed vectors, by hashing chunk texts against a ground truth
computed outside both frameworks. That is a strictly stronger correctness check than ours was, and
the reasoning below is hers.

WHY THIS MATTERS MORE THAN VECTOR CHECKS
---------------------------------------
`harness.goodput` asserts vectors are well-*shaped*: one per chunk, 384-d, finite, L2 ≈ 1, not all
identical. Every one of those can pass while the text is wrong, because garbage embeds as cleanly as
prose (BENCHMARK_SETUP.md section 5).

Vector *similarity* is also weaker evidence than it looks. Leela measured that the embedder
**truncates at 512 tokens while our chunks are ~4,000 characters** (her CONTEXT_SNAPSHOT section
4.10; saturation observed ~3,000-3,500 chars). So two chunks that differ only after ~512 tokens
produce near-identical vectors. Cosine similarity therefore cannot detect content loss in the tail
of a chunk — which is exactly where truncation defects live.

Hashing the chunk text detects it exactly, with no threshold to tune.

THE REFERENCE IS COMPUTED OUTSIDE BOTH FRAMEWORKS
-------------------------------------------------
`reference_chunks()` imports **only** `langchain_text_splitters` — no llama_index, no engine, no
service. If it went through either arm it could not falsify that arm. Single-threaded and
deterministic: same input, same chunks, on any host.

The `text + "\\n"` transform is applied here because the engine appends exactly one newline
(Leela's Stage 0/1 finding, already noted in `ws1/pipeline.py`); a reference built without it fails
chunk comparison on every multi-chunk document.
"""

from __future__ import annotations

import hashlib


CHUNK_SIZE = 4000       # RecursiveCharacterTextSplitter library default
CHUNK_OVERLAP = 200     # ditto. The engine drops configured kwargs (_filter_kwargs_for), so the
                        # defaults are what BOTH arms actually run — see SCHEMA_PROPOSAL.md.


class ChunkHashMismatch(AssertionError):
    """An arm returned chunk text that differs from the offline reference."""


def reference_chunks(text: str) -> list[str]:
    """Chunk `text` the way both arms should, using ONLY the splitter library.

    Deliberately imports nothing from llama_index, ws1, or the engine: a reference that shares code
    with the thing under test cannot falsify it.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    prepared = text + "\n"
    if not prepared.strip():
        return []                       # matches the engine: split_text('') yields 0 chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    return splitter.split_text(prepared)


def hash_chunks(chunks) -> list[str]:
    """sha256 of each chunk's exact bytes. No normalisation — normalising would hide the defects."""
    return [hashlib.sha256(str(c).encode("utf-8")).hexdigest() for c in chunks]


def effective_config() -> dict:
    """Read the splitter's ACTUAL settings off the object, not the constants above.

    Leela's read-back discipline: `s._chunk_size` rather than trusting what was requested. If a
    library version changes its defaults, this is what notices.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    s = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, length_function=len)
    return {"splitter": "RecursiveCharacterTextSplitter",
            "chunk_size": s._chunk_size, "chunk_overlap": s._chunk_overlap}


def check_chunks(doc_id: str, returned, source_text: str) -> dict:
    """Assert an arm's returned chunks match the offline reference exactly.

    Returns per-document evidence. Raises ChunkHashMismatch on any divergence, naming the first
    differing chunk and how it differs — a count mismatch and a content mismatch have different
    causes and must not be reported as the same failure.
    """
    ref = reference_chunks(source_text)
    ref_h, got_h = hash_chunks(ref), hash_chunks(returned)

    if len(got_h) != len(ref_h):
        raise ChunkHashMismatch(
            f"{doc_id}: chunk COUNT {len(got_h)} != reference {len(ref_h)}. "
            f"Chunking diverged (splitter, size/overlap, or the text+'\\n' transform), "
            f"not content loss within a chunk.")

    for i, (g, r) in enumerate(zip(got_h, ref_h)):
        if g != r:
            gt, rt = str(returned[i]), ref[i]
            detail = (f"len {len(gt)} vs reference {len(rt)}"
                      if len(gt) != len(rt) else "same length, different bytes")
            extra = ""
            if "\x00" in rt and "\x00" not in gt:
                extra = "  <- reference contains NUL, returned does not: truncation at the NUL"
            elif len(gt) < len(rt):
                extra = "  <- returned is SHORTER: content lost in the tail, invisible to cosine"
            raise ChunkHashMismatch(
                f"{doc_id}: chunk {i}/{len(ref_h)} content differs ({detail}).{extra}")

    return {"doc": doc_id, "n_chunks": len(ref_h), "chunk_sha256": got_h,
            "text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "text_chars": len(source_text)}
