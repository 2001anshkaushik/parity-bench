# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# STEP 2 — topology vs framework.
#
# The 4-node pipeline (webhook -> preprocessor_langchain -> embedding_transformer ->
# response_documents) pays three inter-node hops per document. That hop cost is a large part of
# RocketRide's fixed per-request overhead, which is what makes it lose on short documents and win
# on long ones. This node collapses split+embed into ONE node so the pipeline becomes
# webhook -> split_embed -> response_documents (one hop instead of three).
#
# Comparing 4-node vs 2-node vs the LlamaIndex service separates "the engine is slow per request"
# from "this pipeline shape is slow per request". A reviewer will ask this first.
#
# Deliberately uses the SAME libraries and the SAME parameters as both the 4-node pipeline and the
# LlamaIndex service: RecursiveCharacterTextSplitter(4000, 200, len) over text + '\n', then one
# batched encode of all chunks via sentence-transformers multi-qa-MiniLM-L6-cos-v1 on CPU.
import os
import sys

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from rocketlib import IInstanceBase

_MODEL = os.environ.get("SE_MODEL", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
# Chunk size is env-configurable HERE because the deployed engine silently drops splitter kwargs
# passed through pipeline config (`_filter_kwargs_for`, found by Leela's Stage 1). Without this
# there is no way to vary chunk count on the RocketRide side, and the chunk-vs-token experiment
# cannot be run symmetrically. Defaults to the contract value.
_CHUNK_SIZE = int(os.environ.get("SE_CHUNK_SIZE", "4000"))
_CHUNK_OVERLAP = int(os.environ.get("SE_CHUNK_OVERLAP", "200"))
# FAIRNESS ASYMMETRY 2 (FAIRNESS_BASIS.md): TORCH_NUM_THREADS=1 pins torch's INTRA-op pool but
# leaves INTER-op at the core count (measured: 14) because no environment variable reaches it.
# The only way to set it is torch.set_num_interop_threads(), which must be called BEFORE any
# parallel work — torch raises if it is already running. Unset by default so the node's behaviour
# is unchanged unless the harness asks for it.
_INTEROP = os.environ.get("SE_INTEROP_THREADS")
_SPLITTER = None
_EMBED = None
_THREAD_REPORT = {}


def _lazy():
    """Loaded once per task process, on first use. The harness warms before timing."""
    global _SPLITTER, _EMBED
    if _EMBED is None and not _THREAD_REPORT:
        # Do this BEFORE SentenceTransformer is constructed: once torch has started its parallel
        # runtime, set_num_interop_threads() raises and the setting is silently lost. Whether it
        # actually took is RECORDED, not assumed — that is the whole point of the exercise.
        try:
            import torch
            _THREAD_REPORT["intra_before"] = torch.get_num_threads()
            _THREAD_REPORT["inter_before"] = torch.get_num_interop_threads()
            if _INTEROP:
                try:
                    torch.set_num_interop_threads(int(_INTEROP))
                    _THREAD_REPORT["interop_set"] = "ok"
                except Exception as e:
                    _THREAD_REPORT["interop_set"] = f"FAILED {type(e).__name__}: {e}"
            else:
                _THREAD_REPORT["interop_set"] = "not_requested"
            _THREAD_REPORT["intra_after"] = torch.get_num_threads()
            _THREAD_REPORT["inter_after"] = torch.get_num_interop_threads()
            _THREAD_REPORT["pid"] = os.getpid()
        except Exception as e:
            _THREAD_REPORT["error"] = f"{type(e).__name__}: {e}"
    if _SPLITTER is None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        _SPLITTER = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP, length_function=len)
    if _EMBED is None:
        from sentence_transformers import SentenceTransformer
        # device pinned explicitly: sentence-transformers silently selects mps on Apple Silicon
        # when device is unset, which would make this node incomparable to everything else.
        _EMBED = SentenceTransformer(_MODEL, device="cpu")
    return _SPLITTER, _EMBED


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        splitter, embed = _lazy()
        prepared = self.buf + "\n"          # canonical transform, same as every other service
        if not prepared.strip():
            self.instance.writeText("")
            return
        chunks = splitter.split_text(prepared)
        if not chunks:
            self.instance.writeText("")
            return
        vecs = embed.encode(chunks, show_progress_bar=False)   # ONE batched encode per document
        # Emit a compact text payload: this node exists to measure the pipeline shape, and the
        # response component is response_text rather than response_documents. Byte size is
        # reported by the harness so any serialization asymmetry is visible.
        out = ";".join(f"{len(v)}" for v in vecs)
        if os.environ.get("SE_REPORT_THREADS") == "1":
            # DECLARED != MEASURED: report the thread state from INSIDE the task process that
            # actually runs the embedding, not from the shell that launched the engine.
            import json as _json
            self.instance.writeText("THREADS " + _json.dumps(_THREAD_REPORT))
            return
        self.instance.writeText(f"{len(chunks)}|{out}")

    def close(self):
        self.buf = ""
