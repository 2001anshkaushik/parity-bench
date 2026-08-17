# Every cut, so a reviewer can reject one without rejecting the number

Read `COUNTING_RULE.md` first — the categories below (1–7) are defined there. Nothing in
`working/ws1/`, `docker/` or `weekend_worker.py` was modified; the minimal versions are new files
alongside. Benchmarking continues on the as-built code.

## LlamaIndex arm: 636 → 104

### `working/ws1/pipeline.py` + `working/ws1/schema.py` (210) → folded into `li/service.py`

| removed | category | why |
| --- | --- | --- |
| `PipelineResult` dataclass, `process()`, `split_ms` / `embed_ms` | 1 | per-stage timing; the only caller is the benchmark ladder |
| `resolved_device()` and the declared-vs-resolved assertion | 3 | audit machinery. Real value — sentence-transformers silently picks `mps` — but it exists to make a *comparison* trustworthy, not to make the service work |
| `splitter_mode="native"` branch, `_build_parser` dispatch, `splitter_name` | 6 | a second splitter kept for a separate experiment; parity runs only ever use `schema` |
| `WS1_PDF_PARSER` dispatch, the `pymupdf` branch, `parser_name`, `parser_version()` | 6 | second parser plus its licence commentary; parity uses pypdf |
| `is_warm` property | 2 | readiness reporting for a poller |
| `canonical_bytes()` | 5 | the cross-service hashing encoder |
| `build_meta`, `build_manifest`, `SCHEMA_VERSION`, `ErrorClass` Literal | 5 | provenance for cross-arm comparison |
| `ServiceConfig` — `effective_concurrency`, `concurrency_source`, `declared_workers`, `uvicorn_settings`, `input_transform` | 3 | declared-vs-measured audit fields, including a multi-line prose string recording how the concurrency knee was measured |
| `ProcessRequest`, `build_response`, `build_error` | — | **kept**, inlined: a caller must be able to read chunks back and tell a bad document from a broken service |

### `working/ws1/service.py` (195) → `li/service.py` (58)

| removed | category | why |
| --- | --- | --- |
| `WARM_ROOT`, `_supervisor_key()`, `_warm_dir()`, `_warm_count()` | 2 | the warm-marker apparatus, including the pid+start-time key that fixed `warm_workers=33`. It exists **because a harness polls it** |
| `/health`: `declared_workers`, `warm_workers`, `warm_count_valid`, `warm_key`, `torch_threads`, `torch_interop`, `thread_env` | 2, 3 | census and thread read-back. A deployment needs a liveness probe; it does not need a census of its own workers |
| `_library_versions()` and the whole `/manifest` endpoint | 3 | version provenance for comparison |
| `_maybe_inject()` and the `FAULT:` directive protocol | 4 | fault injection; its only caller is a poison run |
| `/process` (text-in endpoint) and its `trace` timing block | 1, 6 | the parity configuration is Parser IN and uses `/process_pdf` only |
| `out["extracted_text"]`, `extracted_chars`, `parser`, `timing_ms` | 1, 5 | the arm's own text is returned so a chunk-hash gate can build a per-arm reference |
| `effective_concurrency` / `concurrency_source` construction in `lifespan` | 3 | as above |
| the warm-line `print` with splitter/device/thread detail | 1 | measurement logging |
| **kept**: `lifespan` model load, `TOKENIZERS_PARALLELISM`, pypdf extract, `text + "\n"`, LangchainNodeParser at 4000/200, batched embed, per-item error classes with HTTP 200 | — | removing any of these changes what the service produces or breaks it under a forking server |

### `docker/Dockerfile.llamaindex` (153) + `run_service.sh` (11) → `li/Dockerfile` (25)

| removed | category | why |
| --- | --- | --- |
| `ARG EXPECT_ARCH` + both `RUN` arch assertions | 1 | guards against silently benchmarking under emulation |
| `COPY working/harness /app/harness`, `COPY docker/ladder.py` | 1 | the measurement harness shipped into the image |
| the fastapi/uvicorn tail layer and its rationale comment | 1 | exists to protect the baked-model build cache across benchmark iterations; merged into requirements here |
| `NUMEXPR_NUM_THREADS`, `TORCH_NUM_THREADS`, `PYTHONDONTWRITEBYTECODE` | 3 | belt-and-braces pins beyond the four BLAS variables that actually bind |
| all of `run_service.sh` | — | a laptop launcher resolving a venv two directories above the clone; the image has an `ENTRYPOINT` |
| **kept**: digest-pinned base, two-stage build, baked model, offline env, 4 BLAS pins | — | a runtime model fetch is a broken deployment, not a smaller one; unpinned BLAS inside forked workers costs most of the concurrency scaling |

### client (67) → `li/client.py` (21)

Removed from `LlamaHttpArm`: `rss()` process-tree sampling, listening-socket service discovery,
`container_root_pid` resolution, worker-count bookkeeping — category 1. What a developer writes to
use this service is a POST and a JSON parse.

## RocketRide arm: 208 → 121

**The same knife, and it cuts less because there was less to cut. That is the finding, not a
convenience.**

### `working/pipes/product_pdf.pipe` (78) → `rr/pipeline.pipe` (72)

| removed | category | why |
| --- | --- | --- |
| `viewport` `{x, y, zoom}` | — | canvas UI state, not pipeline behaviour |
| `hideForm: true` on the webhook | — | UI affordance |

Six lines. Every component, config and lane stays: this file *is* the pipeline.

### `docker/Dockerfile.rocketride` (58) → `rr/Dockerfile` (14)

| removed | category | why |
| --- | --- | --- |
| `ARG EXPECT_ARCH` + arch assertion | 1 | same guard as the other arm — cut on both |
| `lsof` from the apt list | 1 | installed so the harness can find the engine by listening socket |
| `python3`, `python3-pip` from the apt list | 7 | present only to run the pypdf install below |
| the whole pypdf-into-the-embedded-interpreter block (~9 lines) | 7 | its own comment says it is needed **only for the legacy `pdf_probe` node**, which the all-stock five-node pipeline does not use |
| `COPY working/nodes/env_probe`, `COPY working/nodes/pdf_probe` | 7 | benchmark probe nodes; `env_probe` exists so a thread-parity gate can read the environment back |
| the thread-policy comment block | 1 | explains a benchmark decision |
| **kept**: sha256 pin, the DT_NEEDED runtime libraries, `ENTRYPOINT` | — | a tag is mutable and a hash is not; the library list is measured from the ELF, not guessed |

### client (72) → `rr/client.py` (35)

Removed from `RocketArm`: `_engine_pid()` (lsof plus pidfile fallback), `rss()`, container-pid
resolution, and the text-in `process()` variant — category 1. **Kept: the unique `project_id`.**
The engine allows one live task per `project_id`, so a fixed id makes two pipelines collide; that
is product behaviour, not scaffolding.

## The numbers

| layer | LI built | LI min | RR built | RR min |
| --- | ---: | ---: | ---: | ---: |
| pipeline_definition | 210 | 0 | 78 | 72 |
| compute_transforms | 195 | 58 | 0 | 0 |
| serving_integration | 164 | 25 | 58 | 14 |
| client_harness | 67 | 21 | 72 | 35 |
| **arm total** | **636** | **104** | **208** | **121** |

* **as-built / as-built = 3.1×**
* **minimal / minimal = 0.9×** — RocketRide slightly *larger*
* **range = 0.5× .. 5.3×** (the mixed pairings, which bound a hostile reading)

`pipeline_definition` is 0 for minimal LlamaIndex because no declarative artifact exists on that
arm — the stage wiring *is* the handler, and it is counted once under `compute_transforms`.
`requirements.txt` is counted on **neither** arm, matching Leela, who counts no dependency
manifest for LangGraph or for RocketRide.

## The weakest number in the metric

The RocketRide `pipeline_definition` figure is the only one set by **indentation rather than
content**. The same pipeline counts:

| serialisation | as-built | minimal |
| --- | ---: | ---: |
| as stored | 78 | 72 |
| `json.dumps(indent=2)` | 78 | 72 |
| compact | 1 | 1 |
| one node per line | 7 | 7 |

RocketRide's minimal arm total therefore moves **50 .. 121** on formatting alone, and the
minimal/minimal ratio with it: **0.9× .. 2.1×**. Python line counts do not have this property, so
only the RocketRide arm is exposed. A repo-local format-on-save daemon rewrote this very file
mid-edit while it was being counted, which is how the sensitivity was noticed. **No single value
for this layer should be published.**

## Validation

**The minimal implementations are NOT validated by a run, and NOT EVEN IMPORT-CHECKED.**

`py_compile` passes on all four Python files and the `.pipe` parses as JSON with the five
expected components — that is the whole of it. `fastapi`, `pypdf`, `llama_index.core`,
`langchain_text_splitters` and `rocketride` are all **absent from this laptop**, so no import of
`li/service.py` or `rr/client.py` has ever been attempted. A typo in an import line would not
have been caught.

The LOC counts themselves are static and exact — the counter only reads files — but *functional
equivalence* is asserted from code reading and nothing more.

Equivalence means: same five stages, same model, same 4000/200 chunk config, same
`RecursiveCharacterTextSplitter`, same `text + "\n"`, same pypdf extraction, byte-identical chunk
hashes against the as-built service on the same documents. That needs the box. Until it runs,
treat the minimal column as **PROVISIONAL** and the as-built column as VERIFIED.

### Validating on the box

Build and start the minimal LlamaIndex service beside the existing one, on a different port so
nothing in flight is disturbed:

```bash
docker build -f working/minimal/li/Dockerfile -t li-min .
docker run -d --name li-min -p 8802:8801 -e WS1_WORKERS=4 li-min
```

Then compare chunk hashes document for document against the as-built arm. Identical hashes on a
sample is what turns "functionally equivalent" from an assertion into a measurement:

```bash
SMOKE_EXTERNAL=1 SMOKE_PORT=8802 SMOKE_CORPUS_GLOB='000_*.pdf' python3 - <<'PY'
import hashlib, sys, urllib.request, json
from pathlib import Path
sys.path.insert(0, "working")
docs = sorted(Path("corpus/govdocs1/pdfs").glob("000_*.pdf"))[:20]
def post(port, b):
    r = urllib.request.Request(f"http://127.0.0.1:{port}/process_pdf", data=b,
                               headers={"Content-Type": "application/pdf"})
    return json.loads(urllib.request.urlopen(r, timeout=600).read())
same = 0
for d in docs:
    b = d.read_bytes()
    a, m = post(8801, b), post(8802, b)
    ha = [hashlib.sha256(c["text"].encode()).hexdigest() for c in a.get("chunks", [])]
    hm = [hashlib.sha256(c["text"].encode()).hexdigest() for c in m.get("chunks", [])]
    same += (ha == hm)
    if ha != hm:
        print(f"DIFFERS {d.name}: as-built {len(ha)} chunks, minimal {len(hm)}")
print(f"{same}/{len(docs)} documents byte-identical")
PY
```

Anything short of 20/20 means the minimal service is not functionally equivalent and its column
is not a lower bound on the same thing.
