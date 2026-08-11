# RUNBOOK — WS-1 LlamaIndex Service

**Every command below was executed exactly as written, in a fresh shell, on 2026-08-05.**
Verification status and actual output are recorded in §5. A runbook nobody has run is UNVERIFIED.

Host: Apple M4 Pro, macOS 26.6. Python 3.12.13 at `$REPO/.venv`.

---

## 1. File map

### The three layers — this is the important part

| layer | absolute path | what it does |
| --- | --- | --- |
| **① schema** | `$REPO/working/ws1/schema.py` | The wire contract, and **nothing else**. Request/response/manifest shapes, `error_class` values, the canonical JSON encoder. When Leela's contract lands, only this file changes. |
| **② pipeline** | `$REPO/working/ws1/pipeline.py` | The LlamaIndex work: split → embed. Knows nothing about HTTP. Owns the device assertion and the `text + '\n'` transform. |
| **③ service** | `$REPO/working/ws1/service.py` | HTTP only. Routes, lifespan/warmup, fault injection hook. **Constructs no wire dicts itself** — it calls into ①. |

### Everything else

| path | purpose |
| --- | --- |
| `working/ws1/run_service.sh` | Launcher. Pins device, thread env, uvicorn tuning. **Use this, not a bare uvicorn command.** |
| `working/ws1/__init__.py` | Package marker (empty). |
| `working/ws1/exp_layer_isolation.py` | Experiment: model-only scaling with no HTTP. Found the GPU. |
| `working/ws1/exp_service_device.py` | Experiment: cpu-vs-mps at the service level, n=3 randomised. |
| `working/ws1/exp_variance_cause.py` | Experiment: what causes run-to-run variance. |
| `working/ws1/exp_fault_path.py` | Validates `error_class` contract + injected-vs-collateral accounting. |
| `working/scripts/parity_replication.py` | Parity harness (single synthetic doc). |
| `working/scripts/parity_corpus.py` | Parity on the real mt10k distribution + chunk sweep. |
| `working/scripts/corpus_characterize.py` | Rebuilds mt10k, verifies sha256 vs Leela's manifest. |
| `working/scripts/variance_gate.py` | Runnable gate; exits non-zero if spread > threshold. |
| `working/handoff/pool_width.py` | Guarded effective-width measurement. |
| `data/mt10k/mt10k_sample.json` | First 2,000 verified mt10k docs, for the parity runs. |

---

## 2. Startup

### 2.1 Start the service

From a fresh terminal, copy-paste:

```bash
cd "$(git rev-parse --show-toplevel)"
WS1_DEVICE=cpu WS1_WORKERS=8 WS1_PORT=8801 bash working/ws1/run_service.sh
```

That is the whole thing. **No venv activation needed** — `run_service.sh` resolves the interpreter
itself (`$ROOT/../.venv/bin/python`). It also exports the device pin, `TOKENIZERS_PARALLELISM=false`,
and `OMP/MKL/OPENBLAS/VECLIB_NUM_THREADS=1`, then launches uvicorn with `--loop uvloop
--http httptools --no-access-log`.

To run it in the background instead:

```bash
cd "$(git rev-parse --show-toplevel)" && WS1_DEVICE=cpu WS1_WORKERS=8 WS1_PORT=8801 nohup bash working/ws1/run_service.sh > logs/ws1.out 2>&1 &
```

**Knobs** (all optional): `WS1_DEVICE` (`cpu` default — do not use `mps` for parity runs),
`WS1_WORKERS` (8), `WS1_PORT` (8801), `WS1_SPLITTER_MODE` (`schema` default, `native` uses
LlamaIndex's own SentenceSplitter — never for parity).

### 2.2 Confirm ALL workers are warm before sending anything

**`/health` is answered by whichever worker uvicorn routes to, so a single 200 does NOT mean the
service is ready.** Each worker independently imports torch (~30 s) and loads the model (~6 s).
Count the warm lines instead:

```bash
cd "$(git rev-parse --show-toplevel)" && until [ "$(grep -c 'warm in' logs/ws1.out)" -ge 8 ]; do sleep 3; done; grep -c 'warm in' logs/ws1.out
```

That prints `8` when all eight workers are up. Each line looks like:

```
[ws1] worker 2410 warm in 5.4s (splitter=RecursiveCharacterTextSplitter, mode=schema, device declared=cpu resolved=cpu)
```

`device declared=cpu resolved=cpu` is the assertion passing. If they ever differ the worker
**refuses to start** — that is deliberate.

### 2.3 Stop

```bash
pkill -f "uvicorn ws1.service"
```

---

## 3. Test requests

### 3.1 Health

```bash
curl -s http://127.0.0.1:8801/health
```

```json
{"status":"ok","service":"llamaindex","model_loaded":true,"worker_pid":2410}
```

### 3.2 Manifest — the config actually in effect

```bash
curl -s http://127.0.0.1:8801/manifest | python3 -m json.tool
```

Abridged (full output in §5):

```json
{
    "service": "llamaindex",
    "embedding_model": "sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
    "embedding_dim": 384,
    "normalized": true,
    "device": "cpu",
    "resolved_device": "cpu",
    "splitter": "RecursiveCharacterTextSplitter",
    "chunk_size": 4000,
    "chunk_overlap": 200,
    "input_transform": "text + '\\n'",
    "effective_concurrency": 8,
    "declared_workers": 8,
    "concurrency_source": "MEASURED knee on device=cpu: throughput peaks at concurrency 8 ...",
    "schema_version": "0.2"
}
```

`device` vs `resolved_device` and `effective_concurrency` vs `declared_workers` are the two
declared-vs-measured pairs. Both must agree with reality, not with the config file.

### 3.3 Process a document

```bash
curl -s -X POST http://127.0.0.1:8801/process -H 'Content-Type: application/json' -d '{"doc_id":"demo-1","text":"Machine learning systems require careful evaluation before deployment.","trace":true}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['chunks'][0]; print(json.dumps({**r,'chunks':[{**c,'embedding':c['embedding'][:4]+['... 380 more floats']}]}, indent=2))"
```

Expected (vector truncated by the one-liner above):

```json
{
  "doc_id": "demo-1",
  "ok": true,
  "n_chunks": 1,
  "chunks": [
    {
      "chunk_id": 0,
      "text": "Machine learning systems require careful evaluation before deployment.",
      "embedding": [0.0173, -0.0512, 0.0330, 0.0246, "... 380 more floats"]
    }
  ],
  "meta": { "...": "as in /manifest, plus worker_pid" },
  "timing_ms": { "total": 12.4, "split": 0.5, "embed": 11.9 }
}
```

Notes: `trace: true` adds `timing_ms` (leave it off in measured runs). Embeddings are 384-dim and
already unit-normalised — the model's own `Normalize` module does it, so we never pass
`normalize_embeddings`.

### 3.4 Script version

```bash
cd "$(git rev-parse --show-toplevel)" && ../.venv/bin/python working/ws1/smoke.py
```

Checks health, manifest, a single-chunk doc, a multi-chunk doc, an empty doc, and a fault — and
verifies the vector is 384-dim with L2 norm 1.0. Exits non-zero on any failure.

---

## 4. Architecture — how to explain this to a teammate

### 4.1 Why three layers

```
   HTTP request
        │
        ▼
  ③ service.py     routes, warmup, fault hook          "knows HTTP, not LlamaIndex"
        │
        ▼
  ② pipeline.py    split → embed, device assertion     "knows LlamaIndex, not HTTP"
        │
        ▼
  ① schema.py      builds the wire dict                "knows the contract, nothing else"
        │
        ▼
   HTTP response
```

**The reason is that the contract is not agreed yet.** Leela owns the shared schema and it may
change. With this split, a contract change touches `schema.py` only — `service.py` never builds a
response dict by hand and `pipeline.py` has never heard of JSON. It also means the pipeline can be
unit-tested with no server running, and the service can be tested with a stub pipeline.

### 4.2 Why LangchainNodeParser instead of LlamaIndex's native SentenceSplitter

LlamaIndex's own chunker is `SentenceSplitter`. We do **not** use it. We use LlamaIndex's
`LangchainNodeParser` wrapping LangChain's `RecursiveCharacterTextSplitter(4000, 200)`.

**Why:** the WS-1 contract mandates `RecursiveCharacterTextSplitter` at library defaults, because
that is what the RocketRide engine actually runs. `SentenceSplitter` is a different algorithm and
produces **different chunk boundaries** — different text, therefore different vectors. If the three
services chunk differently, you cannot verify that any of them produced the *correct* output, and
goodput verification (the thing that catches a service being fast and wrong) becomes impossible.

**What it costs us:** we are not measuring LlamaIndex's native chunking path, so this benchmark
says nothing about whether `SentenceSplitter` is faster or better. That is a real gap. It is a
*separate experiment*, and `WS1_SPLITTER_MODE=native` exists to run it — the code is written, just
never benchmarked. Cost is small in practice: splitting is **0.5 ms of a ~12 ms request** (~4%).

**What it does NOT cost us:** this is still a LlamaIndex service. The document flows through
LlamaIndex's `Document` type and its node-parser pipeline; the embedding goes through LlamaIndex's
`HuggingFaceEmbedding` wrapper. Only the chunking *algorithm* is pinned to the shared contract.

### 4.3 Request path, side by side with RocketRide

```
                LlamaIndex service                    RocketRide engine
                ──────────────────                    ─────────────────
  client        aiohttp, pooled keep-alive            rocketride SDK, one WebSocket
                       │                                       │
  transport     HTTP/1.1 POST /process                 WebSocket frame, DAP protocol
                JSON body over loopback                JSON over loopback
                       │                                       │
                       ▼                                       ▼
  dispatch      uvicorn master → 1 of 8 worker         engine process → task process
                processes (SO_REUSEPORT)               (per-task tree), 17-wide pool
                       │                                       │
                       ▼                                       ▼
  split         LangchainNodeParser wrapping           node: preprocessor_langchain
                RecursiveCharacterTextSplitter          → RecursiveCharacterTextSplitter
                (4000/200, text + '\n')                 (4000/200, text + '\n')
                       │                                       │
                       │                              ── node hop ──
                       ▼                                       ▼
  embed         HuggingFaceEmbedding →                 node: embedding_transformer →
                sentence-transformers                  sentence-transformers
                multi-qa-MiniLM-L6-cos-v1, cpu         multi-qa-MiniLM-L6-cos-v1, cpu
                384-dim, unit-normalised               384-dim, unit-normalised
                       │                                       │
                       │                              ── node hop ──
                       ▼                                       ▼
  response      schema.build_response()                node: response_documents
                {doc_id, chunks[{text,embedding}]}     {documents[{page_content,embedding}]}
                ~10,368 bytes                          ~10,288 bytes
```

**Why this is apples-to-apples:** same model, same device (`cpu`, asserted on both — the engine's
was verified empirically at `cores_busy 9.29`), same splitter with the same parameters, same
`text + '\n'` transform, same 384-dim unit-normalised output, response payloads within **1%** of
each other in bytes, same client machine, same driver processes, same concurrency, same session.

**Where they genuinely differ — and these are the framework, not the harness:**

| | LlamaIndex service | RocketRide |
| --- | --- | --- |
| transport | HTTP/1.1, keep-alive | WebSocket + DAP |
| process model | 8 uvicorn workers, model in each | 1 engine + per-task process tree |
| pipeline shape | one process does split+embed | **4 nodes with hops between them** |
| memory | ~243 MB per worker (~2 GB at 8) | ~200 MB total |
| effective width | 8 (measured) | 17 (measured) |

The **4-node hop count** is the difference most likely to matter, and it is a genuine property of
choosing a dataflow engine — not an artifact. It is also why the parity claim is scoped to "this
pipeline shape" rather than "LlamaIndex is faster than RocketRide". See `PARITY_REPLICATION.md`.

---

## 5. Verification log — every command above, actually run

**Executed 2026-08-05 in a fresh shell, exactly as written above.** Status: **VERIFIED**.

| § | command | result |
| --- | --- | --- |
| 2.1 | `WS1_DEVICE=cpu WS1_WORKERS=8 WS1_PORT=8801 bash working/ws1/run_service.sh` (background form) | started |
| 2.2 | the `until … grep -c 'warm in'` wait loop | printed `8` |
| 2.2 | warm line format | `[ws1] worker 7323 warm in 5.7s (splitter=RecursiveCharacterTextSplitter, mode=schema, device declared=cpu resolved=cpu)` |
| 3.1 | `curl -s .../health` | `{"status":"ok","service":"llamaindex","model_loaded":true,"worker_pid":7319}` |
| 3.2 | `curl -s .../manifest \| python3 -m json.tool` | full manifest, `device=cpu resolved_device=cpu`, `effective_concurrency=8`, `schema_version=0.2` |
| 3.3 | the `/process` curl with the truncating one-liner | valid JSON, 1 chunk, 4 floats + `"... 380 more floats"`, `timing_ms {total 4.343, split 0.415, embed 3.928}` |
| 3.4 | `../.venv/bin/python working/ws1/smoke.py` | **ALL PASS**, exit code 0 |
| 2.3 | `pkill -f "uvicorn ws1.service"` | stopped cleanly, port refuses connections |

Two things worth knowing that only showed up by running it:

1. **Warm time is ~5.7 s per worker here, not the ~36 s quoted elsewhere.** The 36 s figure was a
   cold HuggingFace cache plus a cold torch import. On a warm machine it is ~6 s. Budget for the
   cold case on a fresh checkout.
2. **`/process` returns in ~4 ms for a short document** (3.9 ms of it embedding). Longer documents
   cost proportionally more — cost is linear in **tokens**, not characters. See
   `PARITY_CORPUS_FINDINGS.md`; this matters more than it sounds.
