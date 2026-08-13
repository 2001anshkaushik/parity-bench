"""The LlamaIndex processing pipeline: raw text -> chunks -> normalized 384-dim vectors.

Kept separate from `service.py` (HTTP) and `schema.py` (wire format) so each can be tested and
swapped independently. This module knows nothing about HTTP and nothing about the wire contract.

Splitter choice — see TOIL_LLAMAINDEX.md JUDGMENT CALL #1
--------------------------------------------------------
The WS-1 contract mandates `RecursiveCharacterTextSplitter()` at LangChain defaults, but
LlamaIndex's *native* parser is `SentenceSplitter`, a different algorithm with different chunk
boundaries. Satisfying both is impossible. Default is `schema` mode — LlamaIndex's own
`LangchainNodeParser` bridge wrapping the mandated splitter, which keeps chunks byte-identical
across the three services while still running through LlamaIndex's node-parser pipeline. `native`
mode uses `SentenceSplitter` and is available for the separate (and genuinely interesting)
question of what LlamaIndex's own chunker costs. It must not be used for parity runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

# Set before torch/tokenizers import: HuggingFace tokenizers fork a thread pool that warns and
# can deadlock under a forking server. uvicorn --workers forks, so this is load-bearing here.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

SplitterMode = Literal["schema", "native"]


@dataclass
class PipelineResult:
    chunks: list[str]
    embeddings: list[list[float]]
    split_ms: float
    embed_ms: float


class LlamaIndexPipeline:
    """Loads once per worker process, then processes documents.

    Model load is ~6 s and torch import ~30 s; both happen in `warm()`, which the service calls
    during startup so no request ever pays for them. This is the same class of trap as
    RocketRide's ~60 s cold start.
    """

    def __init__(self, model_name: str, chunk_size: int = 4000, chunk_overlap: int = 200,
                 splitter_mode: SplitterMode = "schema", device: str = "cpu"):
        self.model_name = model_name
        # EXPLICIT device. sentence-transformers silently selects `mps` on Apple Silicon, and
        # measured, that choice changes throughput 3.3x single-process (107.9/s mps vs 32.6/s cpu)
        # and changes the SCALING SHAPE completely: mps peaks at 281.7/s but barely scales with
        # processes (14 procs contend for one GPU, 1.69 cores busy); cpu scales to 8.09 cores busy
        # but saturates at 112.8/s. Leela's RocketRide setup runs MiniLM on CPU, so a parity run
        # with this service on mps would compare different silicon, not different frameworks.
        # Default cpu for parity. Never leave this implicit.
        self.device = device
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter_mode: SplitterMode = splitter_mode
        self._embed = None
        self._parser = None
        self._warm = False
        self._resolved_device = "unloaded"

    # -- lifecycle ---------------------------------------------------------
    def resolved_device(self) -> str:
        """The device the model is ACTUALLY on, read off the loaded parameters.

        Not the value we passed in — the value that took effect. `sentence-transformers` silently
        auto-selects `mps` on Apple Silicon when device is unset, and a config value that is
        ignored is exactly the class of bug this project keeps hitting.
        """
        if self._embed is None:
            return "unloaded"
        try:
            inner = self._embed._model
            return str(next(inner._first_module().auto_model.parameters()).device)
        except Exception:
            try:
                return str(self._embed._model.device)
            except Exception:
                return "unknown"

    def warm(self) -> None:
        """Import torch, build the parser, load the model, assert the device, warm the encode.

        The throwaway encode matters: sentence-transformers lazily initialises parts of the
        pipeline on first use, so a service that only *loads* the model still pays a one-off cost
        on its first real request.
        """
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        self._parser = self._build_parser()
        self._embed = HuggingFaceEmbedding(model_name=self.model_name, device=self.device)

        # DECLARED vs RESOLVED. Refuse to run if they disagree: a service that silently embeds on
        # a different device than it reports makes every cross-service number invalid, and it
        # fails silently rather than loudly. `mps:0` vs `cpu` is a 2-3x throughput difference and
        # a 10x difference in run-to-run spread, so this is not a cosmetic mismatch.
        resolved = self.resolved_device()
        if not resolved.startswith(self.device):
            raise RuntimeError(
                f"DEVICE ASSERTION FAILED: declared device={self.device!r} but the model resolved "
                f"to {resolved!r}. Refusing to start. sentence-transformers auto-selects an "
                f"accelerator when device is unset or unavailable; a service reporting one device "
                f"while computing on another invalidates every cross-service comparison. "
                f"Set WS1_DEVICE to the device you actually want, or fix availability."
            )
        self._resolved_device = resolved
        self._embed.get_text_embedding_batch(["warmup"])
        self._warm = True

    @property
    def is_warm(self) -> bool:
        return self._warm

    def _build_parser(self):
        if self.splitter_mode == "native":
            from llama_index.core.node_parser import SentenceSplitter
            return SentenceSplitter(chunk_size=self.chunk_size,
                                    chunk_overlap=self.chunk_overlap)
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from llama_index.core.node_parser import LangchainNodeParser
        # Library defaults, passed explicitly so the manifest can assert them rather than trusting
        # that the installed version's defaults still match what the contract assumes.
        return LangchainNodeParser(RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        ))

    @property
    def splitter_name(self) -> str:
        return ("SentenceSplitter" if self.splitter_mode == "native"
                else "RecursiveCharacterTextSplitter")

    # -- extraction (Parser IN, 2026-08-12) --------------------------------
    def extract(self, pdf_bytes: bytes) -> str:
        """PDF bytes -> text, INSIDE the service.

        Parser IN scope change: extraction used to happen in the driver, common-mode to both arms.
        It now happens inside each arm so the whole product is benchmarked (Tier 2 in
        PARSER_DECISION.md). Consequence: parse failures are this arm's failures and must surface
        through the response as error classes, not be counted by the driver.

        Parser selection, switchable via WS1_PDF_PARSER:

        * ``pypdf`` (DEFAULT) — BSD-3. This is what llama-index's own PDFReader uses underneath
          (`llama-index-readers-file` pins `pypdf<7,>=6.1.3`). We call pypdf directly rather than
          going through PDFReader because that package **hard-requires pandas<3,>=2.0.0** — verified
          against its PyPI metadata, not assumed — and pulling pandas into the measured service to
          reach the same pypdf call would inflate the arm's memory for no functional gain.
        * ``pymupdf`` — **AGPL-3.0, and its network clause reaches a service**. Selecting it is a
          procurement decision, not a technical one. Never the default; the licence is restated at
          the point of use so nobody enables it casually.
        """
        parser = os.environ.get("WS1_PDF_PARSER", "pypdf").lower()
        if parser == "pypdf":
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if parser == "pymupdf":
            # AGPL-3.0. Running this inside a network service triggers the network clause, which
            # obliges you to offer the service's complete corresponding source to its users.
            import fitz                                            # type: ignore
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                return "\n".join(page.get_text() for page in doc)
        raise ValueError(f"unknown WS1_PDF_PARSER={parser!r} (pypdf | pymupdf)")

    @property
    def parser_name(self) -> str:
        return os.environ.get("WS1_PDF_PARSER", "pypdf").lower()

    def parser_version(self) -> str:
        if self.parser_name == "pypdf":
            import pypdf
            return f"pypdf {pypdf.__version__}"
        import fitz                                                # type: ignore
        return f"pymupdf {fitz.__doc__.strip().splitlines()[0] if fitz.__doc__ else '?'}"

    # -- processing --------------------------------------------------------
    def split(self, text: str) -> list[str]:
        """Chunk one document. Applies the canonical `text + '\\n'` transform.

        The trailing newline is not cosmetic: Leela's Stage 0/1 work found the RocketRide engine
        appends exactly one, and an offline reference built without it failed chunk-level
        comparison on every multi-chunk document. All three services must apply it identically.
        """
        from llama_index.core import Document

        prepared = text + "\n"
        if not prepared.strip():
            # `split_text('')` yields 0 chunks in the engine; match that rather than emitting a
            # single empty chunk. An empty document is a valid input with an empty result.
            return []
        nodes = self._parser.get_nodes_from_documents([Document(text=prepared)])
        return [n.get_content() for n in nodes]

    def embed(self, chunks: list[str]) -> list[list[float]]:
        """One batched encode per document — matches the engine's `encodeChunks` behaviour.

        Deliberately NOT passing `normalize_embeddings`: this model carries its own `Normalize`
        module, so the vectors are already unit length (verified: L2 norm = 1.000000). Passing the
        flag would normalise twice, which is harmless but makes the config differ from the other
        services for no reason.
        """
        if not chunks:
            return []
        return self._embed.get_text_embedding_batch(chunks)

    def process(self, text: str) -> PipelineResult:
        import time

        t0 = time.perf_counter()
        chunks = self.split(text)
        t1 = time.perf_counter()
        vecs = self.embed(chunks)
        t2 = time.perf_counter()
        return PipelineResult(chunks=chunks, embeddings=vecs,
                              split_ms=round((t1 - t0) * 1000, 3),
                              embed_ms=round((t2 - t1) * 1000, 3))
