# Container Demo — Stability, Wiring and Memory Endurance on Heavy PDFs

**Meeting artifact.** Ansh · 2026-08-07.
**This is not a speed test.** Throughput from this host is invalid (open item A13, §7); what this
run establishes is that the pipeline is wired end to end, that it genuinely does the work, and how
it behaves under a hard memory ceiling on documents far heavier than anything we have run before.

---

## What this proves

| claim | label | evidence |
| --- | --- | --- |
| The containerised pipeline works end to end: PDF → text → chunks → 384-d vectors, offline, under a cgroup limit | **VERIFIED** | ladder run, §3 |
| Every document really did the work — no silent no-ops | **VERIFIED** (per-document gate, §2) | `working/harness/goodput.py` |
| Peak RSS is flat: identical (1,405.5 MB) at 100 and 500 documents, 12 % of the 12 GB cap | **PROVISIONAL** (one run) | §4 |
| Resident memory drifts +150 MB / 1,000 docs — real but small, and NOT flat | **PROVISIONAL** (20 noisy samples) | §4 |
| The image is genuinely arm64 and genuinely offline | **VERIFIED** (build- and run-time assertions) | §5 |
| Every digest and version in the manifest is a resolved value, not a constructed one | **VERIFIED** | §5 |

## 1. The corpus — why document count understates this run

**GovDocs1** (digitalcorpora.org): US government work, public domain, bulk-downloadable, and
genuinely messy. Chosen over arXiv (3 s API rate limit, per-paper licence mix) and over any blended
source (an anomaly in a blend is unattributable).

**2,471 distinct PDFs**, sha256-manifested at `corpus/govdocs1/manifest.jsonl`.

| | GovDocs1 | mt10k (previous corpus) | ratio |
| --- | ---: | ---: | ---: |
| median bytes/doc | **227,567** | 1,186 | **192×** |
| median tokens/doc (est.) | **6,345** | 338 | **19×** |
| p90 tokens | 35,276 | — | |
| p99 tokens | 167,698 | — | |
| max tokens | 708,396 | — | |
| median pages | 12 | n/a | |
| max pages | **1,000** | n/a | |

**Report volume in bytes and tokens, not document count.** 2,471 GovDocs PDFs is roughly **40× the
ingestion work** of 10,000 mt10k documents by token volume. A "we did 10,000 documents" headline on
mt10k would be a far smaller claim than this one.

**Natural fault rate 1.42 %** — 34 empty extractions and 1 `PdfReadError` in 2,471. These are
**classified, not filtered**: malformed files are the fault-isolation story, not noise to remove.
pypdf emitted hundreds of recoverable warnings (`invalid pdf header`, `incorrect startxref
pointer`, `Multiple definitions in dictionary`) while still extracting text — which is exactly the
messiness the corpus was chosen for.

## 2. The goodput gate — the failure mode that would have faked this demo

`llama_index.core` maps `.pdf → PDFReader` from `llama-index-readers-file`. When that package is
absent it **warns and returns `{}`** — no exception, no error status. Measured directly on this
machine: `SimpleDirectoryReader.supported_suffix_fn()` returned **0 suffixes**.

A 10,000-document PDF run in that state produces **10,000 successes with flat memory and zero
embeddings**, and every surface signal — status codes, throughput, memory — looks healthy.

So goodput is asserted **per document** and failure is loud and fatal to the run:

1. `n_chunks > 0` · 2. every chunk non-empty after strip · 3. one vector per chunk ·
4. every vector exactly 384-d · 5. every vector L2-normalised to 1.0 ± 0.01 ·
6. vectors not identical across distinct chunks

**Proven against six deliberately broken inputs**, all caught:

| injected failure | caught by |
| --- | --- |
| silent `{}` (no reader registered) | `n_chunks == 0` |
| PDF parsed to empty text | empty-chunk check |
| zero vector (correct dimension) | L2 norm — a dimension check alone passes this |
| wrong dimension (768) | dimension check |
| chunk/vector count mismatch | count check |
| stuck encoder (identical vectors) | cross-chunk identity check |

**Null control:** a genuinely correct document passes. `working/harness/goodput.py`.

> *Hostile reviewer: "How do I know the gate isn't just always passing?"*
> It was run against six broken inputs and failed all six, and against a correct input and passed.
> The negative cases are in the module's self-test.

## 3. The ladder — what completed

Container: `--cpus 4.0 --memory 12g --memory-swap 12g --pids-limit 4096 --network none`.
Swap set equal to memory so memory pressure produces a clean OOM rather than silent swapping.

| rung | documents | wall | goodput | faults | fault rate | chunks | peak RSS | RSS at end | limit hit? |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 100 | 174.9 s | **98** | 2 | 2.0 % | 1,039 | **1,405.5 MB** | 1,144.0 MB | no |
| 2 | 500 | 1,206.3 s | **495** | 5 | 1.0 % | 8,410 | **1,405.5 MB** | 1,123.9 MB | no |
| 3 | 2,000 | **did not complete before the deadline** | — | — | — | — | — | — | — |

All 5 faults are `empty_extraction` — PDFs that parsed without raising but yielded no text. That
is **1.0 %, consistent with the corpus's independently-measured 1.42 % natural fault rate**, and
it is corpus data, not pipeline failure. **The goodput gate never fired**: every document that
produced text produced valid 384-d unit-norm vectors.

**Rung 3 did not finish.** At the observed rate (~0.26 docs/s on documents averaging ~6,300 tokens)
2,000 documents needs ~2 hours. Checkpoints were written every 250 documents, so the partial curve
is preserved rather than lost. This is a scope shortfall, not a failure: nothing OOMed, nothing
errored, it simply ran out of clock.

## 4. Memory — the axis A13 does not touch

**Peak RSS 1,405.5 MB against a 12 GB ceiling — 12 % utilisation — and identical at 100 and 500
documents.** The high-water mark did not move at all as the run grew 5×.

⚠️ **But resident memory does drift upward, and I am not going to call that flat.** The RSS series
(20 samples over 500 documents) runs 1,040 → 1,140 MB with noise:

```
n25=1040  n75=1058  n125=1070  n175=1122  n225=1083  n275=1130  n325=1140  n375=1125  n425=1149  n475=1139
```

**Measured slope over the last 60 % of the run: +150 MB per 1,000 documents** [PROVISIONAL — 20
samples, visibly noisy, single run]. Extrapolated naively, 10,000 documents would add ~1.5 GB —
still far inside 12 GB, but it is **not** a flat line and must not be presented as one.

**Strongest rival explanation, not separated:** allocator retention / arena fragmentation (memory
held but reusable) versus genuine accumulation. The flat *peak* favours the former — a true leak
would eventually push the high-water mark up, and it did not move across a 5× increase in
documents. **Separating experiment:** run rung 3 to 2,000+ and check whether peak stays pinned at
1,405 MB while current RSS keeps climbing. ~2 h; the run was still in flight at the deadline.

**12 GB held comfortably, and the expectation that it would not was wrong.** The prediction was
that GovDocs' 6,345-token median would push past the 7.95 GB previously seen. It did not, and the
reason matters:

> The 7.95 GB figure was **8 uvicorn worker processes each holding a model**, under concurrency 32.
> This ladder runs **one in-process pipeline, one document at a time**. Memory here is dominated by
> **worker count, not document size** — the LlamaIndex service's floor scales with workers
> (4.6 GB idle at 8 workers), while per-document cost is modest even at 6,345 tokens.
>
> ⚠️ **Topology-confounded — the 8-worker floor is a configuration choice, not a framework
> property. See [`MATCHED_LAYERS.md`](MATCHED_LAYERS.md).**

> **RESOLVED 2026-08-11 — [`MATCHED_LAYERS.md`](MATCHED_LAYERS.md) §5c.** This figure is **not** a
> point on the matched concurrency curve, at any C. It compares LlamaIndex idle at 8 workers (eight
> models **eagerly loaded at startup**) against RocketRide idle (engine parent holding **no task and
> no model**). It is the right answer to *"what does an idle deployment cost?"* — LlamaIndex pays for
> capacity before any request arrives; RocketRide loads on task creation — but it is **not** an
> answer to *"which framework uses less memory?"*. Under matched load below C ≈ 3 the answer is the
> opposite: RocketRide is the heavier arm.


**That is the memory-efficiency story, and it is a configuration lever rather than a framework
property**: a service sized to its actual concurrency needs far less memory than one sized to its
worker count. [PROVISIONAL — one run, one concurrency.]

**Not measured: the RocketRide arm.** Its image was not built (§6), so the memory comparison
between the two arms and the "both fit in 32 GB" simultaneous proof are **not delivered**. The
native-versus-container figures we hold for RocketRide (204 MB idle → 2,356 MB peak) are from a
different environment and must not be set against the container numbers above.

## 5. Image integrity — verified, not asserted

Two values in this Dockerfile were **invented and caught** during construction: a base-image digest
and a package version, both fabricated rather than resolved. Everything is therefore verified
against the registry and against the running image:

| item | declared | resolved | |
| --- | --- | --- | --- |
| base image | `python:3.12-slim@sha256:229a2c5b…` | same, from `docker inspect` | ✅ |
| 9 pinned packages | requirements.txt | versions **installed in the image** | ✅ 0 mismatches |
| run image digest | `IMAGE_DIGEST.txt` | `docker inspect` | ✅ |

**Arch, asserted four ways:** `--platform linux/arm64`; a build-time `RUN` that fails on non-aarch64
in both stages; a runtime check that exits 3; and the image digest in the run manifest. Measured
inside the container: `aarch64`, `torch intra=1 / interop=14`, `cgroup memory.max = 12,884 MB`.

**`os.cpu_count()` reports the host's 14 inside a 4-CPU quota** — measured, not assumed. This is
why threads are pinned explicitly: a container that lets torch size its own pools recreates the
oversubscription pathology from `A3_SERIALIZATION_FINDING.md` (19 % throughput, most of the
concurrency scaling).

**Offline is proven, not configured.** The build fails if the model cannot load with the hub
disabled **as the runtime user**. That check exists because three earlier attempts passed as root
and failed as `ws1`: `HuggingFaceEmbedding` derives its cache directory from the calling user's
home rather than `HF_HOME`, so "the model is baked" was true of one load path and one user, and
false of the pair actually used. It surfaced as a misleading *"couldn't connect to
huggingface.co"*.

## 6. What is NOT delivered

| gap | why |
| --- | --- |
| **RocketRide container image** | not built — the LlamaIndex image consumed the session (four build failures: invented digest, invented version, pip read timeout, model-cache-vs-user) |
| **Simultaneous both-arms run** | requires the RocketRide image |
| **Rung 3 (2,000 documents)** | ~2 h at the observed rate; ran out of clock |
| **10,000 documents** | 2,471 distinct PDFs on disk. ~200–260 PDFs per 250–490 MB zip, so 10,000 distinct needs ~20 GB and several hours. **A first relaunch of the fetch failed silently** — it used `setsid`, which does not exist on macOS, so `nohup` exited immediately and the corpus sat static while I assumed it was growing. Relaunched without `setsid` and verified by PID |
| **`llama-index-readers-file`** | its `__init__` imports the tabular readers, which need **pandas**; the PDF path does not. We call **pypdf** directly — what `PDFReader` wraps. Recorded as toil |

## 7. Throughput from this host is invalid — read before quoting any rate

Ascending-load measurements on this machine profile it in a low-power state. Identical harness,
same service, **only the cell order changed**: ascending-cold reads **101 /s** at concurrency 64
where descending reads **241 /s**, and pre-warming an ascending sweep reproduces the descending
result. The variable is the machine's power state at measurement start.

**Therefore: the `docs_per_s` field in the result files is recorded for completeness and must not
be quoted.** The stability and memory findings above are unaffected — they do not depend on rate.

## 8. Reproduction

```bash
# 1. corpus (public domain; manifest carries sha256, pages, bytes, token estimate)
../.venv/bin/python working/scripts/fetch_govdocs.py 2500
../.venv/bin/python -c "…"   # characterisation writes via harness.resultio

# 2. image — base digest and every version are resolved, not constructed
docker build --platform linux/arm64 -f docker/Dockerfile.llamaindex -t ws1-llamaindex:demo .
docker build --platform linux/arm64 -f docker/Dockerfile.llamaindex.layer -t ws1-llamaindex:demo2 .

# 3. ladder — swap disabled so pressure gives a clean OOM, network off so offline is real
docker run --rm --platform linux/arm64 \
  --cpus 4.0 --memory 12g --memory-swap 12g --pids-limit 4096 --network none \
  -e LADDER_RUNGS=100,500,2000 -e LADDER_ARM=llamaindex \
  -e IMAGE_DIGEST="$(cat docker/IMAGE_DIGEST.txt)" \
  -v "$PWD/corpus/govdocs1/pdfs:/corpus:ro" -v "$PWD/docker/out:/app/out" \
  ws1-llamaindex:demo2
```

Results land in `docker/out/` and, for everything written this session, under
`working/results/<name>__<UTC>__<hash>.json` — a path that **cannot collide**, because two runs
were silently destroyed this project by hardcoded output paths before the guard existed.
