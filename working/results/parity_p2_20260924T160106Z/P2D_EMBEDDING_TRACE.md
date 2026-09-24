# P2-D (1): how each arm embeds, from source (laptop, no box time)

A source reading is not a measurement (register entry 1). The one measured figure used here is from P1-B's committed
analysis: the embed stage's share of summed per-document stage time on the fixed Tika image, stamped PROFILE, is
**0.921 and 0.920** on the 384 slice (p1b_fix_a, p1b_fix_b) and **0.926** on the full corpus (p1b_fix_full)
(`working/results/parity_p1_20260923T184000Z/analysis_p1docs.json`, `legs.<leg>.d1.stages.embed.share_of_run_total`).
This is a share of stage time, not of wall clock.

**Method.** The trace was drafted by a read-only agent and checked by me afterwards. I re-opened the citations marked ✓
at the line given. Paths starting `engine/` are the untracked 3.3.1.35 bundle (the macOS build of the version the box
images report). `venv:` is the laptop's llama-index / sentence-transformers install, at the versions pinned in
`docker/requirements.txt`. Whether the LlamaIndex image was built from those exact pins is **UNVERIFIED**. The repository's
`working/ws1/service.py` md5 `b5162a51…` equals the image copy's md5 that the runner pins
(`batchsize_docs_run.sh` LI_TIMED_BASE_MD5) ✓. The image's `/app/ws1/pipeline.py` and `/app/ws1/service.py` were md5-read on the box after the P2 master finished: `7883de6d…` and `b5162a51…`, equal to the repository copies ✓.

## Summary

| Question | RocketRide (one token, one task process, one model) | LlamaIndex (ws1 service) |
|---|---|---|
| Chunks per model call | Every chunk of **one document** in one `encode()`, run as forward passes of **≤ 32**, the engine wrapper's own default. `engine/ai/common/models/transformers/sentence_transformers.py:334` ✓, slicing `:380-381` ✓. sentence-transformers' own `encode()` is not on the path. | Chunks of one document in slices of **10**, the LlamaIndex default `embed_batch_size` (`venv:llama_index/core/constants.py:8`), because `HuggingFaceEmbedding(...)` is built without one (`working/ws1/pipeline.py:94` ✓). |
| The "64 buffer" | `IInstance.maxDocuments = 64` (`engine/nodes/embedding_transformer/IInstance.py:40` ✓). It is per document: reset in `open()` (`:42-49` ✓) and flushed in `close()` (`:94-96` ✓). | none |
| Does a batch span documents? | **No** (SOURCE). The buffer is bracketed by each object's open/close. The splitter emits a document's chunks in one list, at close (`engine/nodes/preprocessor_langchain/IInstance.py:84-87` ✓). | **No.** One `/process_pdf` request is one document (`working/ws1/service.py:245-280` ✓). |
| Lock around the model call | **None.** No lock in the node or the wrapper's local path. The engine's device lock (`engine/ai/common/models/base.py:241-252`) is used only by vision nodes. Up to 32 executor threads can be inside the one model at once. | No lock needed: `/process_pdf` is `async def` and runs extract, split and embed synchronously on the event loop (`service.py:245-280` ✓). **Each worker processes one document at a time.** |
| Intra-op threads | 1: the six variables are set by `docker run -e` and read back in-process, and the engine never calls `set_num_threads`. | 1: the same six variables, plus the image ENV, read back through `/health`. |
| Forwards at once | Up to 32 single-threaded forwards in one process (executor 32, pipe semaphore 64; P0 H1). | One per worker. 24 workers at the optimum, each with its own model copy. |
| Per-call extras | `torch.no_grad` rather than `inference_mode` (`sentence_transformers.py:190` ✓). Manual mean pooling and normalisation. A per-row tensor→list conversion (`:233-238` ✓), then a float64 `np.array` (`:415` ✓), then a second per-row `.tolist()` in the node (`embedding_transformer/sentenceTransformer.py:162` ✓). A walk over every parameter per call for a metric (`:411` ✓). The pydevd debugger attached unless the task is launched with `noDebug` (`engine/ai/modules/task/task_engine.py:296, 1499-1507` ✓). | `inference_mode`, a length sort, `self.to(device)` and `eval()` per call, normalisation twice (idempotent), one `.tolist()`, and LlamaIndex event dispatch per slice. |

**Chunking is the same on both arms, and not what RocketRide's config says.** RocketRide's configured 512/0 is dropped by
`_filter_kwargs_for`, which keeps only named `__init__` parameters (`engine/nodes/preprocessor_langchain/langchain.py:88-100` ✓).
`RecursiveCharacterTextSplitter` takes `**kwargs`, so the library defaults apply: 4000 characters with 200 overlap
(`engine/lib/python3.12/site-packages/langchain_text_splitters/base.py:49-50` ✓). LlamaIndex passes 4000/200 explicitly. Both
arms truncate to 512 tokens. A 4000-character chunk is probably longer than 512 tokens (UNVERIFIED: the chunk-length
distribution was not measured), so most forwards are ~512-token sequences on both arms.

## What this means for "one token vs one worker"

- **Per unit (the P2-A anchor):** one LlamaIndex worker at C=8 runs one forward at a time. One RocketRide token at C=8 can
  run up to 8 at once, each single-threaded. The per-unit comparison is therefore not like for like in concurrency. That
  is by design, since concurrency inside one instance is RocketRide's unit, and the report reads the anchor that way.
- **At the optimum:** LlamaIndex's 24 workers are 24 processes, each with its own GIL, its own model copy, and one
  document at a time. RocketRide's one token runs up to 32 documents' forwards in one process, sharing one GIL for all
  the Python-held per-chunk work (below) and one model object.

## Per-chunk (not per-batch) Python work in RocketRide's path (SOURCE; size NOT measured)

- One pydantic `Doc` plus a `metadata.model_copy()` per chunk from the splitter (`preprocessor_langchain/IInstance.py:45-60`).
- Per chunk: a dict, an `extract_outputs` call and a `.cpu().tolist()` (384 Python floats). Then a float64 ndarray built
  from Python floats, then a second `.tolist()` (`sentence_transformers.py:233-238, 397-416` ✓; `sentenceTransformer.py:162` ✓).
- `document.toDict()`, i.e. `model_dump`, per chunk in the response node. Then the per-document JSON response.
- No per-chunk traffic between processes was found. The nodes are in-process, and the only hop is the per-document close
  response.

## In-bounds single-instance fixes (P0's three-column ROI)

Every row keeps ONE engine process, ONE token and ONE model instance; threads are unrestricted. Column (a) is the only
measured share: the embed stage at **~0.92** of summed per-document stage time (P1-B). (b) = 1/(1 − share) = **12.5x**. That is
a ceiling for removing the whole stage, not an expected gain; a sub-share inside embed is **not measured** and is marked so.

| # | Fix | (a) share it acts on | (b) bound | (c) scope | Evidence |
|---|---|---|---|---|---|
| F1 | **Cross-document micro-batching inside the one instance**: a batcher in `IGlobal` gathers chunks from several documents' threads, runs one length-sorted forward, and scatters the rows back. It needs F2 alongside it; otherwise it trades 32 parallel single-thread forwards for fewer, larger ones on fewer cores. Output must be re-verified, because padding and batch composition can move floats. | ≤ 0.92 (embed) | ≤ 12.5x | PYTHON | SOURCE: batches never span documents today, and there is no lock. UNVERIFIED: any speed-up; at ~512-token sequences each forward is already a large GEMM, so the gain would be fewer Python dispatches and GIL hand-offs. |
| F2 | **Shape forward concurrency against intra-op threads**: S concurrent forwards × k threads ≈ 32 vCPUs, to keep cores busy when fewer than 32 documents are in embed (the drain tail). This departs from the declared threads-at-1 posture on BOTH arms, so it must be declared and applied symmetrically, or recorded as an asymmetry. | ≤ 0.92 | ≤ 12.5x | THREADING | SOURCE: 1 intra-op thread per caller today. UNVERIFIED: the per-caller OpenMP team behaviour and any benefit. |
| F3 | **`torch.inference_mode()` in place of `no_grad()`** (`sentence_transformers.py:190` ✓), which is what LlamaIndex gets through sentence-transformers. | sub-share (not measured) | ceiling only | PATCH | SOURCE for the difference; size UNVERIFIED. |
| F4 | **Remove the per-chunk conversions**: one float32 `.numpy()` per slice instead of per-row `.tolist()` → float64 ndarray → per-row `.tolist()`. One `.tolist()` per chunk stays, because `Doc.embedding` is `List[float]`. | sub-share (not measured) | ceiling only | PATCH | SOURCE `sentence_transformers.py:233-238, 415` ✓; `sentenceTransformer.py:162` ✓. |
| F5 | **Cache the parameter walk** (`model_gpu_gb`) at load instead of running it on every `encode()`. | sub-share, once per call (not measured) | ceiling only | PATCH | SOURCE `sentence_transformers.py:411` ✓. |
| F6 | **Launch the task with `noDebug`**, which removes pydevd (sys.monitoring tool 0 over all Python in the task). The SDK's `use()` has no parameter for it; the benchmark drivers add the one field. P0 H7 on docs was unreadable, but it ran before the Tika fix. P2-B tests it jointly with MALLOC_ARENA_MAX on video. | Python-held work within 0.92 (not measured) | ceiling only | CONFIG | SOURCE `task_engine.py:296, 1499-1507` ✓; read back on P1-B (`nodebug_launch false`, `{"0": "pydevd"}`). |
| F7 | **A wrapper `batch_size` above 32**, passed at `sentenceTransformer.py:156`. It changes only documents with more than 32 chunks. | sub-share (large documents only; distribution not read) | ceiling only | PATCH | SOURCE `sentence_transformers.py:334` ✓; CPU benefit UNVERIFIED. |

Not fixes: changing `maxDocuments` (it is per document and flushed at close, so it matters only inside F1); the
engine's model-server mode (it batches remotely, but is OUT OF BOUNDS under the mandate); changing chunk size or
truncation (that changes the output).

## Banked readings this trace corrects (flagged; the files are not edited here)

- `working/scripts/exp_batchsize_sweep.py:1249-1251` (export field `not_swept.embedding_batch`) says RocketRide "calls
  encode() at the sentence-transformers default". It calls the **engine wrapper's** `encode(batch_size=32)`. The number is
  the same, but the mechanism differs, and the 64-buffer is per document.
- `working/ws1/pipeline.py:203-206` says normalisation is deliberately not requested. LlamaIndex's `HuggingFaceEmbedding`
  requests it anyway. This is harmless, since normalising twice gives the same result.

## NOT FOUND / UNVERIFIED

- Whether an `IInstance` object is one per pipe: this is in the C++ binary, and the no-span conclusion does not depend on it.
- GIL release inside the HF fast tokenizer and the ATen kernels (compiled code).
- The chunk-count and token-length distributions, and the post-fix GIL and debugger shares: not measured.
