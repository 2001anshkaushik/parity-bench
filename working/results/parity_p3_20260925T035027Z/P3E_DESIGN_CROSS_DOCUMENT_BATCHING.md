# DESIGN DRAFT: cross-document embedding batching inside the one model instance

> **DRAFT, source-level design only.** Nothing here is built or measured in P3; cross-document batching is a node patch and
> is out of P3's scope (preregistration.json P3_C). It has not been filed or sent anywhere.

## The problem, from source (P2-D embedding trace, `working/results/parity_p2_20260924T160106Z/P2D_EMBEDDING_TRACE.md`)

- Each document's chunks are embedded in their own `encode()` call, and no batch ever spans documents:
  - `engine/nodes/embedding_transformer/IInstance.py:40-96` buffers per document (`open()` resets it, `close()` flushes
    it);
  - `_flushDocuments` (`IInstance.py:51-64`) calls `self.IGlobal.embedding.encodeChunks(self.documents)`.
- `Embedding.encodeChunks` (`engine/nodes/embedding_transformer/sentenceTransformer.py:140-162`) builds the strings,
  calls the engine wrapper's `encode()` (forward passes of up to 32, `sentence_transformers.py:334,380-381`) and writes
  each vector back into its chunk.
- The model object is **one per node**, held in `IGlobal.embedding` (`IGlobal.py:29-42`) and shared by every pipe. There
  is no lock around it.
- Up to 32 executor threads can each run their own single-threaded forward at the same time; the executor is 32 wide
  and the pipe semaphore is 64 (P0 H1).
- The embed stage is **~0.92** of summed per-document stage time (P1-B, stamped PROFILE).
- Many forward calls on small batches mean many Python dispatches, tokenizer calls and GIL hand-offs. That per-call
  Python work is multiplied across 32 threads that share one GIL. How much it costs has **not** been measured.

## Where the batch forms

In **`Embedding.encodeChunks`** (`sentenceTransformer.py:140-162`): the one method every pipe thread already calls with
one document's chunk list. It runs on the pipe's executor thread, and the node's `IInstance` does not change.

```
encodeChunks(chunks):                         # called by N pipe threads at once
    req = Request(texts=[prefix + c.page_content for c in chunks], future=Future())
    self._batcher.submit(req)                  # enqueue; returns immediately
    vectors = req.future.result()              # this pipe thread waits for its own rows only
    for i, c in enumerate(chunks):             # unchanged write-back (one .tolist() per chunk; see F4)
        c.embedding_model = self._model
        c.embedding = vectors[i]
```

`_batcher` is a **single leader thread** owned by the one `Embedding` object. It is created in `Embedding.__init__`, and
`IGlobal.endGlobal` stops it. Its loop:

1. Block until at least one request is queued.
2. Keep collecting requests until the batch holds **B_max chunks** (the bound below), or **T_wait** has passed since the
   first request, or the queue is empty and no pipe is between `open` and `close`. The last case keeps a lone document
   from waiting.
3. Concatenate the requests' texts in arrival order and remember each request's `[start, end)` slice.
4. Run the **existing** wrapper call once over the concatenation, `self._embedding.encode(all_texts, batch_size=B_fwd)`.
   A length sort inside the batch, as sentence-transformers' own `encode()` does, is an allowed refinement. It must
   un-sort before step 5.
5. Set each request's future to its own slice of rows.

A request larger than `B_max` (one very long document) is a batch of its own, and the wrapper still splits it into
forward passes of `B_fwd`.

## Its bound

- **B_max** (chunks per batch): a configuration value, proposed default **128**. That is four of today's 32-row
  forwards; the 32 in-flight documents at C=32 carry about 20 chunks each on the 384 slice.
- **T_wait** (the longest a request waits for company): proposed **2 ms**. That is small against a document's embed
  stage, which is tens to hundreds of milliseconds, so the latency it adds is bounded by T_wait plus one batch.
- **Memory:** one batch's activations, at `B_fwd` rows × up to 512 tokens × the hidden size of 384 (MiniLM).
  `B_fwd` = 32 keeps today's peak per forward; raising it is a separate knob (F7).
- **Threads:** the leader runs one forward at a time. To keep the cores busy it must be paired with
  forward-concurrency shaping (F2): either the leader's forward runs with k intra-op threads (`torch.set_num_threads`
  scoped to the leader), or S leaders each take batches, with S × k ≈ 32 vCPUs. **Without F2, batching would move work
  from 32 parallel single-threaded forwards onto one thread and would be slower.** P3-C measures only the thread-shape
  half (the six variables), without batching.

## How results route back per document

- Every request carries its own `Future` and its slice indices. The leader sets each future exactly once, with the
  rows `[start:end)` of the batch output, in the request's own chunk order. Arrival order sets only the offsets.
- **Exceptions:** if the batch forward raises, every request in that batch gets the exception on its future. Each pipe
  thread's `encodeChunks` then raises as it does today, so the document fails the same way it would now; no document
  fails silently.
- **Shutdown:** `endGlobal` stops the leader, which fails any request still queued with a clear error.

## The correctness test (gate; correctness before speed)

Run on the 384 slice, both runs of an ABAB with batching on and off, on one image:

1. **Text chunk identity:** every document's `chunk_sha256` list equals the unbatched run's, on every shared ok
   document, and no document is lost. The splitter is untouched, so any difference is a bug.
2. **Vector tolerance:** for every chunk, the maximum absolute element difference against the unbatched vector
   (`P3_VEC_DUMP`, as P3-C does) is at most **1e-5**, and cosine similarity is at least **0.999999**.
   - Batch composition changes padding lengths, and float32 GEMM reduction order, so exact bit identity is not
     expected.
   - The unbatched run's own run-a-vs-run-b delta is reported beside it as the determinism reference, as P3-C does.
   - A chunk outside the tolerance fails the gate and is named.
3. **Routing null control:** a test build that deliberately rotates slices by one request must fail step 2. It proves
   the test catches a vector delivered to the wrong document.
4. **Order independence:** the same documents submitted in two different orders at C=32 give identical per-document
   vectors within the tolerance.

## In-bounds proof (the single-instance mandate)

- **ONE engine process:** the batcher is a thread inside the task process. No process is created.
- **ONE pipeline / token:** nothing changes on the client or in the pipeline definition.
- **ONE model instance:** the batcher calls the **same** `self._embedding` object that `IGlobal.embedding` holds today.
  No copy is loaded, and there is no pool of models.
- **Read-back:** the benchmark's env_probe D0 counts loaded model instances in the task process. It must still read
  one, and a second instance is a mandate violation that stops the run.
- **Threads are unrestricted** under the mandate. The leader thread, and any intra-op threads it uses, are in bounds.

## What P3 measures towards it

P3-C tries the thread-shape half (the six variables in {1, 2, 4} at C=32) without batching, with correctness
(text-chunk identity) first and vector deltas reported. If a shape wins, it is the starting k for F2. Batching itself
needs its own pre-registered experiment: the gate above, then ABAB speed on the 384 slice, then a full run.
