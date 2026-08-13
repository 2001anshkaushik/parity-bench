# WS-1 Setup Disclosure — for the cross-team pre-AWS comparison

**From:** Ansh (WS-1, LlamaIndex arm) · **Date:** 2026-08-12 · **For:** Leela, Shashi, Joe

Answers to the six questions. Every number below is labelled **MEASURED** (read back from the
running system) or **DECLARED** (what we asked for). Where they differ, that gap is stated — it has
been a finding more than once here.

---

## ⚠️ Read this before matching anything

**Pinning threads and concurrency across two different engine versions still does not produce
comparable results.** We are on `server-v3.3.1`; Leela is on `server-v3.2.1` — two releases apart,
with no cross-version measurement on either side. Until we agree an **engine + SDK pair**, matching
everything else buys nothing, because any difference between our final numbers is partly the
difference between our engines.

**Engine + SDK pair first. Everything below second.**

The full 13-item pinning checklist — what is already agreed and what is still open — is in
[`CROSS_TEAM_COMPARISON.md`](CROSS_TEAM_COMPARISON.md) §7. I am not restating it here; that is the
list to work from.

---

## 1. Framework setup

**LlamaIndex behind FastAPI/uvicorn**, three files with hard boundaries: `schema.py` is the wire
contract and nothing else, `pipeline.py` does the LlamaIndex work and knows nothing about HTTP,
`service.py` is HTTP only and constructs no wire dicts itself.

| | value | how known |
| --- | --- | --- |
| engine | `server-v3.3.1`, reports **`3.3.1.35`** hash `a0817cc6` | **MEASURED** — `GET /version` on the live engine |
| SDK | `rocketride` **1.3.0** — the client bundled with 3.3.1 | DECLARED (pinned), matches the release manifest |
| llama-index-core | 0.14.23 | **MEASURED** — `importlib.metadata` on the venv that ran the results |
| sentence-transformers / torch | 5.6.1 / 2.13.0 | **MEASURED** |
| langchain-text-splitters | 1.1.2 | **MEASURED** |
| pypdf | 6.15.0 | **MEASURED** |
| fastapi / uvicorn | 0.141.1 / 0.52.1 | **MEASURED** |
| Python | 3.12.13 | **MEASURED** |

Full pinned set: `requirements.txt` at the repo root — every version **read from the venv that
produced the results**, not chosen, and verified by a clean install into an empty venv.

**Host:** Apple M4 Pro, 14 cores / 33.6 GB, macOS. Both arms run **natively** — see §6 for why
nothing is containerised on this host.

## 2. Metrics

| metric | what exactly | status |
| --- | --- | --- |
| **memory** | median RSS over a block, sampled every 5 documents after a 50-document warm-up. RocketRide = engine parent + task tree (resolved **by listening socket**, never by process name) **+ our driver**. LlamaIndex-HTTP = uvicorn parent + all workers + driver | reportable, gated |
| **wall clock** | seconds per 2,000-document block | reportable **only with the first block discarded** — see below |
| **goodput** | documents that pass every correctness gate in §4 | reportable |
| **fault classes** | parse / empty-extraction / goodput-failure / error, counted separately | reportable |
| **throughput** | — | **NOT REPORTED, and not reportable from this host.** An ascending cold sweep reads 101 /s where a descending one reads 241 /s on the same service: a **2.2× swing from measurement order alone**. No configuration fixes it. |

**Two gates decide whether a number is quotable:**

* **10 % variance gate**, n ≥ 3 — a cell is reportable only if repeated measurements agree within
  10 %. It **refuses n=1**, because a single measurement has zero spread by construction and a gate
  that cannot fail is worse than no gate.
* **First block is warm-up at BLOCK scale.** MEASURED: block 0 is 12–38 % slower than the blocks
  after it, on **both** arms (LlamaIndex 892.9 → 794.4 → 796.3 s; RocketRide 1,119.9 → 819.8 →
  805.3 s), with identical goodput and fault counts throughout. Excluding it, spread is **0.24 %**
  and **1.79 %** — including it, both arms fail the gate. **A 50-document warm-up does not cover
  this**; the effect is one level up. If you take one operational thing from this document, take
  this one — it is cheap and it changes whether wall clock is usable at all.
  [PROVISIONAL — n=2 after exclusion, below our own n≥3 rule.]

## 3. Pipeline, and how it is reproduced

> ### ⚠️ UPDATED 2026-08-12 — we now parse INSIDE the arms, like you
> This section previously said we parse outside both arms and run a 4-node pipeline. **That is no
> longer true**, and since you are matching against it: we have moved to **Parser IN**.
> * RocketRide: the stock **5-node** pipeline `webhook → parse → preprocessor_langchain →
>   embedding_transformer → response_documents`, with your lane wiring (`parse` consumes `tags`,
>   not the `data` its README documents — thank you, that saved a cycle). All stock; we did not add
>   a seventh custom node.
> * LlamaIndex: a `/process_pdf` endpoint takes raw PDF bytes and parses with **pypdf** in-worker.
>   We call pypdf directly rather than through `PDFReader` because `llama-index-readers-file`
>   hard-requires **pandas<3,>=2.0.0** (checked against its PyPI metadata) to reach the same pypdf.
> * Driver: no longer extracts. It sends bytes.
>
> **So our two arms now use different parsers, like yours** — Tika 3.2.3 vs pypdf. Everything below
> describing parser-out topology is superseded; the numbers it produced are being re-baselined.


**Canonical 4-node RocketRide pipeline** (`working/pipes/embed_probe.pipe`), all stock providers:

```
webhook → preprocessor_langchain → embedding_transformer → response_documents
```

**Note the difference from Leela's:** she has a fifth node, `parse`, and sends PDFs into the engine.
**We parse outside both arms** — our driver extracts with pypdf and sends text, so extraction is
common-mode and cancels in the comparison. Her arms are more production-shaped; ours isolates
split+embed. Neither is wrong, but goodput and fault counts are **not comparable between us**
because they count failures of different work. This is the deepest divergence between our setups
([`CROSS_TEAM_COMPARISON.md`](CROSS_TEAM_COMPARISON.md) §2).

**Effective chunking: 4000 / 200.** DECLARED in our LlamaIndex arm; on the RocketRide side the
engine **silently drops configured splitter kwargs** (`_filter_kwargs_for`), so what actually runs is
LangChain's default — which is also 4000/200. So the two agree, but by default, not by
configuration. Leela reached the same place from the other direction: she found `strlen: 4000` is
not a schema field and removed it. **Her verification method is better than ours** — she reads
`_chunk_size` back off the live splitter object rather than trusting the config. We have adopted
that read-back in `harness/chunk_hash.py`.

**Embedding:** `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, CPU, 384-d, L2-normalised.
**MEASURED** — the pipeline reads the resolved device off the loaded model parameters and **refuses
to start** on a mismatch, because sentence-transformers silently selects `mps` on Apple Silicon and
that alone changes throughput ~3× and invalidates every cross-service number.

**One canonical transform:** `text + "\n"` before splitting. This is **Leela's Stage 0/1 finding** —
the engine appends exactly one newline, and an offline reference built without it fails chunk
comparison on every multi-chunk document. All three services must apply it identically.

**Reproduce:**

```bash
cat publishable/PROVISIONING.md          # engine bundle + corpus are not in the repo
bash working/scripts/start_engine.sh     # unpinned: export no thread vars
../.venv/bin/python matched_layers_run.py --docs 2000 --blocks 3 --workers 1
```

Dry-run first with `--docs 10 --blocks 2 --dry-run`. Results land in
`working/results/matched_layers__<UTC>__<payload-hash>.json` — the naming makes overwriting
impossible, after three scripts silently clobbered each other's output.

### Our non-standard choices — you have to match against these, so they are your problem too

1. **Six custom nodes copied into the engine bundle** (`split_embed`, `env_probe`, `pdf_probe`,
   `cpu_probe`, `fault_probe`, `noop_probe`). **We benchmark a modified install; Leela's is stock.**
   Ours is the larger deviation from what a customer runs.
2. **`pypdf` hand-copied into the engine's embedded CPython.** There is **no documented
   package-management path** for adding a dependency to that interpreter. Not manifest-reproducible,
   will not survive an engine upgrade, must be redone in any image. Recorded as toil, not endorsed.
3. **`split_embed` exists only to work around an engine defect** — the dropped splitter kwargs above.
   Chunk size could not be varied any other way. So part of our pipeline is our code, not the
   product's.
4. **Our driver is counted inside RocketRide's memory total** (~250–320 MB). Disclosed, and it
   **inflates our RocketRide figure**. Leela's cgroup-scoped accounting is the cleaner boundary; we
   have logged it for Phase 2 rather than adopting it now, because switching mid-project would make
   our historical figures incomparable with their own successors.

## 4. How we validate parsed / chunked / embedded correctness

**Two gates. The second is Leela's approach, adopted after reading her benchmark**
(`pdf1k/ground_truth.py`), and it is strictly stronger than what we had.

### Gate 1 — vector shape (`harness/goodput.py`)

Per document: `n_chunks > 0` · every chunk non-empty after strip · one vector per chunk · every
vector exactly 384-d · every vector L2-normalised to 1.0 ± 0.01 · vectors not identical across
distinct chunks.

Plus content sanity: NUL presence, and printable ratio < 0.90 (threshold derived from a
991-document sample, not chosen — legitimate documents sit at p1 = 0.9944, known-garbage at 0.679).

**What it catches:** the silent-`{}` failure mode, zero vectors, dimension drift, garbage extraction.

### Gate 2 — chunk hash against an offline reference (`harness/chunk_hash.py`) — **adopted from Leela**

Hash each returned chunk's exact bytes and compare against a reference computed **outside both
frameworks**. The reference imports *only* `langchain_text_splitters` — no llama_index, no engine, no
service — because a reference sharing code with the thing under test cannot falsify it.

**Why this is necessary, and it is her finding:** the embedder **truncates at 512 tokens** while our
chunks are ~4,000 characters. We re-measured it independently (MiniLM CPU, text identical to N chars
then divergent):

| divergence at | ~tokens | cos(full, truncated) | discriminating? |
| ---: | ---: | ---: | --- |
| 1,000 | 250 | 0.7499 | yes |
| 2,000 | 500 | 0.9378 | yes |
| **2,500** | **625** | **1.0000** | **no — indistinguishable** |
| 4,000 | 1,000 | 1.0000 | no |

**Cosine cannot see content lost beyond ~2,000–2,500 characters into a chunk.** Two chunks differing
only in the tail embed identically. Vector similarity is therefore weak evidence for content
equality, everywhere.

**The demonstration that matters** — a document with a NUL at offset 1,920, run through the engine:

```
Gate 1 (vector shape): PASS   <- vectors well-formed, the defect is invisible
Gate 2 (chunk hash)  : FAIL   chunk 0/4 differs (len 1920 vs reference 3999)
                              <- reference contains NUL, returned does not: truncation at the NUL
```

**Gate 1 passes on content the engine silently destroyed. Gate 2 names the offset.** That is the
whole argument for adopting it.

**Null control:** both our arms match the offline reference **12/12 documents** exactly — so our two
arms are chunk-identical, which nothing previously verified. Guarded by regression test
`chunk_hash_gate`, which also asserts Gate 1 still *passes* the bad input, so the test documents why
it exists.

**Effect on our published claims:** the NUL-truncation direction finding stands — every measured NUL
offset (0, 0, 50, 170, 193, 455, 1,144, 1,294, 2,174) falls **inside** the discriminating window,
which is why `cos = 1.0000` vs `0.7698` separated the hypotheses at all. One sub-claim was weaker
than it read and is now labelled: "cos = 1.0000 vs LlamaIndex on all 11 chunks" could not have
detected a late-chunk divergence.

## 5. Concurrency level and thread configuration

### Threads — unpinned at a MEASURED 10 intra-op

**Both arms run unpinned, and both measure 10 intra-op / 14 interop threads.**

**How it is verified, so you can do the same check:** an exported variable proves nothing — torch
caches its thread count at import, so a variable set after import has no effect, and a variable
exported to the engine parent does not guarantee the *task process* inherited it. So we ask each
worker directly:

* **RocketRide side:** a benchmark node (`working/scripts/probe_env.py`) runs *inside the engine's
  task process* and reports its own `torch.get_num_threads()`.
* **LlamaIndex side:** the service prints `torch_threads=` / `torch_interop=` from **inside each
  uvicorn worker** at warm-up, and the harness reads them back per worker.
* **The runner refuses to start if they differ** — `CONFIG GATE FAILED — REFUSING TO RUN`.

We added that gate *after* a full 10,000-document comparison ran with RocketRide on 1 thread and
LlamaIndex on 10, and nothing detected it.

**Why unpinned rather than pinned:** pinning costs **3.07×** (RocketRide) and **3.26×**
(LlamaIndex) at concurrency 1 on real documents, so unpinned is each arm's own best, and they happen
to coincide at 10. **Leela pins to 1**, which is a defensible fairness choice — but thread count is
the single largest lever we measured, so results are not comparable across this axis. This is item 6
on the pinning list.

Note `TORCH_NUM_THREADS=1` does **not** reach `torch_num_interop_threads`, which stays at 14. The
pin is partial, and only measurement reveals that.

### Concurrency — offered vs ACHIEVED, verified per cell

We drive **C concurrent in-flight documents** and **measure what was actually achieved**, never
assume it. An in-flight counter is incremented immediately before each await and decremented after;
a sampler records it continuously. **A cell whose achieved concurrency falls short of offered is
marked and its ratio is not quoted** — a flat curve obtained by not actually being concurrent would
confirm a hypothesis for the wrong reason. In our sweep, achieved reached offered in **every** cell.

Matching rule: **concurrent in-flight documents** — the only quantity both architectures express.
LlamaIndex gets C uvicorn workers and C concurrent POSTs; RocketRide gets **one pipeline with C
in-flight sends**. (Driving RocketRide as C separate pipelines would force C task processes *by
construction* and answer the question with the harness rather than the engine.)

### The measured memory crossover — this one matters to you directly

| C | LlamaIndex | RocketRide | RR/LI | verdict |
| ---: | ---: | ---: | ---: | --- |
| 1 | 1,131 MB | 2,209 MB | **1.95×** | quotable |
| 2 | 1,903 MB | 2,588 MB | **1.36×** | quotable |
| 4 | 3,406 MB | 2,911 MB | **0.86×** | quotable |
| 8 | 6,589 MB | 3,429 MB | 0.52× | direction only (LI spread 17.5 %) |
| 16 | 7,704 MB | 4,043 MB | 0.53× | direction only (host compressed 5.5 GB) |

**Crossover at C ≈ 3.2** — below it RocketRide is the heavier arm, above it LlamaIndex is, and the
gap widens. RocketRide's task **process count stayed at 1** from C=1 to C=16 with up to 16 documents
genuinely in flight; its memory grows sub-linearly (fitted C^0.20) while LlamaIndex grows nearly
linearly in workers (C^0.80).

**Leela: your `EXECUTOR_WORKERS=4` / `MAX_INFLIGHT_REQUESTS=8` sits right on that crossover.** That
is the region where the memory ratio moves fastest with configuration — it is where a small change in
worker count flips which framework looks better. Worth pinning explicitly and quoting with the
concurrency attached, for the same reason ours needed it: this repo published **2.0× (RocketRide
worse)** and **22.8× (LlamaIndex worse)** simultaneously for three weeks, and the only difference
between them was topology and worker count.

**Also relevant:** RocketRide's effective pool width is **17.24** (VERIFIED, two methods), so
concurrency above ~17 stops exercising RocketRide at all — you would be measuring the other framework
against a saturated engine. Your burst run observed a **~4-slot** admission ceiling, which we cannot
reconcile with our 17.24 (different engine version, emulation, and CPU budget all differ). **Open
question**, and a good candidate for the first joint measurement once we share a version.

## 6. Docker image to import to EC2 — the honest answer

**We have no RocketRide image, and the LlamaIndex image we do have cannot be imported to an x86-64
box either.** Both need building on EC2.

### What exists

| | status |
| --- | --- |
| LlamaIndex image | `ws1-llamaindex:demo2`, digest `sha256:3e8f5e92…`, **8.9–9.3 GB**, base `python:3.12-slim` (Debian bookworm) |
| **its architecture** | **`arch=arm64`** — MEASURED via `docker image inspect`. **Not runnable on x86-64.** |
| RocketRide image | **does not exist** |

The LlamaIndex Dockerfile also hard-asserts `[ "$(uname -m)" = "aarch64" ]` at **both** build stages
and would fail immediately on an x86-64 builder. Those assertions exist deliberately — they were
added to make emulation impossible to do by accident — but they have to be parameterised before the
image builds anywhere else. **That is a small change; the rebuild itself is routine.**

### Why there is no RocketRide image, and why that is not a gap we left open

**It was never buildable on this host.** Across **all 51 releases** examined: 36 carry `win64`, 24
`darwin-arm64`, 24 `linux-x64`, and **zero** carry `linux-arm64`. The project has never shipped an
arm64 Linux build. Containerising RocketRide here would have required x86 emulation, which changes
every number and would have looked like a framework difference — so we ran both arms natively and
said so.

**On EC2 x86-64 it becomes possible for the first time.**

### What building it will actually require

I downloaded and inspected the `linux-x64` release asset to answer this properly (231 MB compressed,
sha256 `d8dad45b…`):

| requirement | detail | effort |
| --- | --- | --- |
| base OS | **glibc ≥ 2.35** — `GLIBC_2.35` is the max symbol version in the ELF. **Ubuntu 22.04 minimum; 20.04 (glibc 2.31) will not load it.** | trivial, once known |
| runtime libs | **`libc++1`, `libc++abi1`, `libunwind8`** — hard `DT_NEEDED`, and it links **libc++ (LLVM), not libstdc++**. Not installed by default on Ubuntu Server | trivial |
| JRE | **bundled** in the tarball (`java/jre`, 393 files) — do **not** install a system Java | none |
| Python | the engine bundles its own CPython 3.12 | none |
| **six custom nodes** | copied into `engine/nodes/`, then the engine restarted | scripted, straightforward |
| **`pypdf` inside the engine's embedded interpreter** | **no supported install path exists.** Currently a hand-copy of the package directory into `engine/lib/python3.12/site-packages/` | **this is the real work** |

**On timing, realistically:** everything above except the last row is a normal Dockerfile and would
take about a day including a verification run. The `pypdf` row is the one I would not promise
against a date — it has no supported mechanism, so the image build has to reproduce a hand-copy, and
whether that survives contact with a container layer cache and an engine restart is untested. It is
also exactly the kind of step that works once interactively and then fails in CI.

**My honest assessment: the LlamaIndex image rebuild lands before the boxes are useful; the
RocketRide image lands after them, not before.** I would rather provision the boxes and build there —
we cannot test an x86-64 image on this hardware anyway, so building it here would be building blind.
If a date is needed, I would say **the RocketRide image is a post-provisioning task, and the first
thing it should do on the new host is prove `pypdf` reaches the embedded interpreter reproducibly.**

Related: the compute spec I sent Shashi has been checked against the binary and amended — Ubuntu
**22.04 LTS minimum**, the three runtime packages above, swap disabled, gp3 with 3000 IOPS. Worth
matching if you are specifying your own box.

---

## What I would do first

1. **Agree the engine + SDK pair.** Nothing else is worth doing before this.
2. **Adopt the chunk-hash gate** if you have not — it is cheap and it catches content loss that
   vector checks pass. It is your approach; we just took it.
3. **Discard the first block** of every run. Ours is 12–38 % slower than the blocks after it.
4. **Quote every memory number with its concurrency and worker count attached.** A bare ratio is what
   let 2.0× and 22.8× coexist here.
5. Work the remaining items from [`CROSS_TEAM_COMPARISON.md`](CROSS_TEAM_COMPARISON.md) §7.
