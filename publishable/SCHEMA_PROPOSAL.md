# WS-1 Shared Endpoint Schema — Proposal **v0.2**

**For agreement: Leela, Shashi** · From: Ansh · 2026-08-05
**Status: PROPOSAL. Not implemented as agreed — the LlamaIndex service is built against this with
the schema layer isolated so it swaps cheaply if you want changes.**

> ### What changed in v0.2 — please re-read §5 and §4
> 1. **`device` is now a REQUIRED contract field, pinned to `cpu`.** We found our service silently
>    computing on the Apple GPU. [VERIFIED, 3 methods]
> 2. **New: a startup assertion.** A service must refuse to start if the *resolved* device differs
>    from the *declared* one. Declared alone is not enough — that is how we got caught.
> 3. **New: warmup-discard is part of the measurement contract**, not just advice. It took observed
>    spread from 17.7% to 1.7%. [VERIFIED]
> 4. **REMOVED: the load-average precondition.** A direct null control refuted it — measuring
>    immediately after driving load average to 7.88 gave the *lowest* spread we have recorded
>    (0.7%). Gating on it would have rejected good runs. [VERIFIED by null control]

One contract, three services (RocketRide, LangChain/LangGraph, LlamaIndex). If the wire shapes
differ at all, the comparison measures serialization rather than frameworks.

---

## 1. Endpoints

Every service exposes exactly these three:

| method | path | purpose |
| --- | --- | --- |
| `POST` | `/process` | one document in, chunks + vectors out |
| `GET` | `/health` | readiness + identity, unauthenticated, no side effects |
| `GET` | `/manifest` | the run manifest (config actually in effect) |

`/health` is deliberately separate from `/manifest`: health must stay cheap enough to poll during
a run without perturbing it.

## 2. Request

```json
{
  "doc_id": "doc-00042",
  "text": "raw document text, exactly as read from the corpus",
  "trace": false
}
```

| field | type | required | notes |
| --- | --- | --- | --- |
| `doc_id` | string | yes | Stable corpus identifier. Echoed verbatim in the response. |
| `text` | string | yes | **Raw** text. The service applies the `+ '\n'` transform itself (§5). |
| `trace` | bool | no, default `false` | Per-request timing breakdown. Off by default so tracing never taxes a measured run. |

**Deliberately excluded:** no batching, no per-request model or chunk overrides. One document per
request keeps the concurrency model explicit and comparable. If we want batching later it should
be a separate endpoint, not an optional field that silently changes the unit of work.

## 3. Response

```json
{
  "doc_id": "doc-00042",
  "ok": true,
  "n_chunks": 3,
  "chunks": [
    {
      "chunk_id": 0,
      "text": "chunk text exactly as the splitter emitted it",
      "embedding": [0.0123, -0.0456, "... 384 floats total"]
    }
  ],
  "meta": {
    "service": "llamaindex",
    "service_version": "0.1.0",
    "embedding_model": "sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
    "embedding_dim": 384,
    "normalized": true,
    "splitter": "RecursiveCharacterTextSplitter",
    "chunk_size": 4000,
    "chunk_overlap": 200,
    "effective_concurrency": 8,
    "declared_workers": 14,
    "concurrency_source": "MEASURED knee on device=cpu: peaks at concurrency 8 (101.8/s, spread 3%), n=3 randomised",
    "worker_pid": 51234
  },
  "timing_ms": { "total": 31.4, "split": 0.6, "embed": 30.1, "serialize": 0.7 }
}
```

On failure:

```json
{
  "doc_id": "doc-00042",
  "ok": false,
  "error_class": "split_failed",
  "error": "RecursiveCharacterTextSplitter: ...",
  "meta": { "...": "same meta block" }
}
```

**Failures return HTTP 200 with `ok: false`, not a 5xx.** A per-item fault is data, not a
transport error — and RocketRide already reports node exceptions as a per-item `error` key on an
otherwise normal response. If one service raises a 500 and another returns a payload error, the
poison-run harness measures the error convention rather than fault isolation. **5xx is reserved
for the service genuinely being broken** (not started, out of memory, crashed worker).

`error_class` is a small closed set so poison runs can be scored by class:
`split_failed | embed_failed | malformed_input | timeout | internal`.

## 4. ⭐ Concurrency pinning — `effective_concurrency`

**This is the field I most want agreement on.**

benchmark-A found RocketRide's *effective* concurrency width is **~17**, while its config says
`threadCount: 64` and its process reports 24 OS threads. Three numbers, none of which was the one
doing the work. Any result is implicitly a result *at that width* — and if the three services run
at different widths, we are comparing pool sizing, not frameworks.

**Every response and every run manifest must carry:**

| field | meaning |
| --- | --- |
| `effective_concurrency` | integer — how many documents this service can genuinely process simultaneously |
| `concurrency_source` | free text — **how that number was arrived at**, so a reader can audit it |

`concurrency_source` matters as much as the number. Examples:

- `"MEASURED knee on device=cpu: peaks at concurrency 8 (101.8/s, spread 3%), n=3 randomised"`
  ← what a *verified* source looks like. Our own service first declared 14 (its worker count) and
  measured 8 on cpu — declaring the worker count would have overstated capacity 1.75×.
- `"measured: W = throughput x hold = 17.1 (see pool_width.py)"`
- `"asyncio.to_thread default executor = min(32, cpu+4) = 18"` ← this one bit us; the code *said*
  64 via a semaphore, but the real limit was an undeclared 18-thread default pool.

**Recommendation: pin all three services to the same effective concurrency for parity runs**, and
report a width sweep separately. If we cannot pin them equal, we must at minimum report each one's
width alongside every number.

**Verification, not declaration.** A service can declare anything. The width should be *measured*
with the hold-and-divide method (`W = throughput × hold`) and the measured value compared to the
declared one. `working/scripts/pool_width.py` does this in ~2 minutes.

## 5. Canonical processing contract

All three services must produce **byte-identical** output for the same input, or goodput
verification is impossible.

| step | specification | source |
| --- | --- | --- |
| input transform | `text + '\n'` — exactly one trailing newline appended before splitting | Leela `findings/limitations.md` #2 — the RocketRide engine does this, so the others must too |
| splitter | `RecursiveCharacterTextSplitter()` **at library defaults** | Leela's Stage 1 discovery |
| chunk_size | **4000** | LangChain default — *not* the 2048 in the `.pipe`, which the engine silently drops (`_filter_kwargs_for`) |
| chunk_overlap | **200** | LangChain default |
| length_function | `len` (Python character count) | |
| separators | `["\n\n", "\n", " ", ""]` (library default, not passed explicitly) | |
| empty document | `split_text('')` → 0 chunks → response with `n_chunks: 0`, `ok: true` | |
| **device** | **`cpu` — REQUIRED and must match across services** |
| model | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` | |
| dimension | 384 | |
| normalization | unit-normalized — the model's own `Normalize` module does this; **do not pass `normalize_embeddings`** | Leela Stage 0 #9 |
| encode call | one batched `encode(list_of_chunks)` per document | Leela Stage 0 #10 |
| batch_size | sentence-transformers internal default (32), not overridden | |

### ⚠️ `device` — REQUIRED, pinned to `cpu`, and asserted at startup

**The mechanism, because it is not obvious and it caught us.** `sentence-transformers` calls
`get_device_name()` when `device` is unset and silently selects the best available accelerator —
which on Apple Silicon is `mps`. Nothing logs it. Nothing declares it. Our service ran on the GPU
for its entire first day while reporting nothing about a device at all.

**Measured impact** (`CONCURRENCY_CEILING.md`, 3 independent methods):

| | cpu | mps |
| --- | ---: | ---: |
| peak throughput (our service) | 101.8/s | 192.1/s |
| **run-to-run spread** | **3–4 %** | **44–53 %** |
| cores busy, 1 process | 1.00 | **0.45** ← work is off-CPU |

**RocketRide's engine embeds on CPU** — verified empirically (cores_busy 9.29 on the four-node
`webhook → preprocessor_langchain → embedding_transformer → response_documents` pipeline, with the
output confirmed as real 384-dim unit-norm vectors first). Note the engine's node passes **no
`device=` argument** either, so source inspection alone suggested GPU and was **wrong** — which is
precisely why this field must be asserted rather than assumed.

**A parity run with any service on `mps` compares silicon, not frameworks.**

#### Required: declared-vs-resolved startup assertion

Declaring the device is not sufficient — a declared value that the library ignores is exactly the
failure we hit. Every service must read the device **off the loaded model** and refuse to start on
mismatch:

```python
resolved = str(next(model._first_module().auto_model.parameters()).device)
if not resolved.startswith(declared_device):
    raise RuntimeError(f"DEVICE ASSERTION FAILED: declared={declared_device} resolved={resolved}")
```

Both `device` (declared) and `resolved_device` must appear in `/manifest` and in every response
`meta`. Our implementation is in `working/ws1/pipeline.py::warm()`; the guard is tested in both
directions (it passes on a match and fires on a deliberate mismatch).

⚠️ **The 4000/200 values are the *engine's actual behaviour*, not the intended 2048/0 contract.**
Leela's Stage 1 found the deployed engine drops configured splitter kwargs. We match observed
behaviour so the three services agree; if that engine bug is fixed, this schema must change with it.

## 6. Canonical encoder

For hashing, comparison and byte-size measurement, all three services and the harness use:

```python
json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

No spaces, no sort, `ensure_ascii=False`, UTF-8. Floats use Python's `repr` shortest-roundtrip
form. **Float formatting is the likeliest source of cross-service byte mismatch** — if any service
serializes via numpy or a different JSON library, digests will differ on identical vectors.

**Recommendation:** compare embeddings with a **tolerance** (`allclose`, atol 1e-6) for
correctness, and reserve exact-byte digests for the chunk *text*, which must match exactly. Trying
to enforce bit-identical floats across three stacks will burn a day and prove nothing.

## 7. `/health` and `/manifest`

```jsonc
// GET /health  -> 200, cheap, no model work
{ "status": "ok", "service": "llamaindex", "model_loaded": true, "worker_pid": 51234 }

// GET /manifest -> 200, the config ACTUALLY in effect (read from the live objects, not constants)
{
  "service": "llamaindex", "service_version": "0.1.0",
  "library_versions": { "llama-index-core": "0.14.23", "sentence-transformers": "5.x", "torch": "2.x" },
  "embedding_model": "sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
  "embedding_dim": 384, "normalized": true,
  "splitter": "RecursiveCharacterTextSplitter", "chunk_size": 4000, "chunk_overlap": 200,
  "input_transform": "text + '\\n'",
  "effective_concurrency": 14,
  "concurrency_source": "uvicorn --workers 14, 1 request in flight per worker",
  "uvicorn": { "workers": 14, "loop": "uvloop", "http": "httptools", "access_log": false },
  "model_warm": true, "schema_version": "0.2"
}
```

`model_loaded` on `/health` is load-bearing: the driver must not start timing until every worker
has its model resident, or the first N requests carry model-load cost. **Model load must be
outside every timed region** — this is the same class of error as RocketRide's ~60 s cold start.

## 8. Measurement protocol — part of the contract, not advice

A service that conforms to the wire shape but is measured badly still produces an invalid
comparison. Full detail in `VARIANCE_PROTOCOL.md`; the contract-level requirements are:

| requirement | why | evidence |
| --- | --- | --- |
| **Discard the first 2 iterations** of every series | Largest single fixable source of variance | spread 17.7% → **1.7%** [VERIFIED] |
| **n ≥ 5** measured repetitions | n=3 detects gross problems only | — |
| **Randomised order**, fixed seed | Whoever runs first gets the cool machine | — |
| **Reject spread > 10 %** | CPU-pinned, warmup-discarded runs achieve 0.7–4.4 % | [VERIFIED] |
| **Model fully warm before timing** | ~36 s of import + load per worker | [VERIFIED] |
| **Effective concurrency MEASURED, not declared** | ours declared 14, measured 8 | [VERIFIED] |

**Explicitly NOT required: a load-average precondition.** v0.1 proposed gating runs on a quiet
host. A null control refuted it — we drove load average to 7.88 with 12 spinners and measured
immediately, and got the *lowest* spread we have recorded (0.7 %) and the *highest* median. Gating
on load average would have rejected good runs for no reason. [VERIFIED by null control]

**Width measurement must use the guarded tool** (`working/handoff/pool_width.py`). The unguarded version
returns the OFFERED concurrency when offered is below the true width — a −75 % error delivered at
0.0 % spread, i.e. confidently wrong and looking precise. The guarded version escalates until the
estimate stops tracking and hard-fails rather than guessing. Re-calibrated: −0.7 % to −0.9 % error
at known widths 4/8/16/64. [VERIFIED]

## 9. Open questions for Leela

1. **Do you want `ok:false` + HTTP 200, or a 4xx/5xx for per-item faults?** I have argued for the
   former; happy to switch — it just has to be the same across all three.
2. **Exact-byte float agreement, or tolerance-based?** I propose tolerance (§6).
3. **Should `/process` accept a pre-split document** so splitter differences can be isolated from
   embedding differences? Useful for debugging a mismatch; adds a second code path.
4. **Do we pin all three services to one `effective_concurrency`,** or run each at its natural
   width and report both? I lean toward pinning for the headline and sweeping separately.
5. **Is `schema_version` worth carrying?** I have included it so a mid-study change is detectable
   in old result files rather than silently mixed in.

6. **Does RocketRide's service wrapper also assert its device?** The engine node passes no
   `device=`; it lands on CPU on this host, but that is an accident of what torch was built with,
   not a guarantee. Worth an explicit assertion on your side too.

Nothing here is expensive to change **today**. All of it is expensive to change after the first
full parity run.
