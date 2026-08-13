# Cross-Team Comparison — WS-1 (LlamaIndex) and Leela's LangGraph benchmark

**What this is:** a record of where two independently-built RocketRide benchmarks diverge, so that
results from either can be read correctly. **It is not an assessment of which setup is right.** Both
contain deliberate compromises and both contain choices the other team would question; they are
listed together in the same tables.

**Reference clone:** `github.com/Leela8256/bench_langgraph_prod` at commit
`b9b473606cba19fabc09e27f103af6933ed4cf1e` (2026-08-12), cloned 2026-08-12T20:24:41Z to
`Benchmarking/reference/leela-bench_langgraph_prod/` — a **sibling** of `benchmark-A`, never nested
inside it. Read-only; nothing in `benchmark-A` was modified and no nested `.git` exists in our tree.

**Why this matters:** if the two RocketRide arms differ, then "LangGraph vs RocketRide" and
"LlamaIndex vs RocketRide" do not share a baseline, and the two framework results cannot be placed
side by side — the difference between them would partly be the difference between our two engines.

---

> ### ⚠️ SUPERSEDED 2026-08-13 — this two-way table is now three-way
> Shashi's Haystack repo has since been read, and the comparison is in
> [`THREE_WAY_COMPARISON.md`](THREE_WAY_COMPARISON.md). **Use that one.** The table below covers only
> two of the three teams and its "we parse outside" rows are also out of date — we moved to Parser IN
> on 2026-08-12.
>
> **The headline that changed:** Shashi is also on **`server-v3.2.1`**, so two of three teams share
> an engine and **we are the outlier**. That settles by majority what the two-way table could only
> pose as an open question.
>
> This document is retained, not deleted: its §2 (parser placement) and §4 (workload and gates)
> reasoning still stands, and its 13-item pinning list is folded into the three-way §5.

## 1. The RocketRide arms — the shared baseline

| | WS-1 (ours) | Leela's | direction / size |
| --- | --- | --- | --- |
| **engine version** | `server-v3.3.1` (2026-07-07) | **`server-v3.2.1`** (2026-05-29) | **Different builds, two releases apart.** Unquantified — no cross-version measurement exists on either side. This is the single largest obstacle to comparing results. |
| **SDK** | `rocketride` 1.3.0 — the client **bundled with** 3.3.1 | `rocketride==1.3.0` pinned, against an engine whose manifest bundles **1.1.1** | A pairing the release manifests do not pair. Reconstructing her environment needs the pin, not a published artifact. Effect unmeasured. |
| **transport** | WebSocket + DAP, `ws://127.0.0.1:5565`, driver on host | WebSocket + DAP, `ws://127.0.0.1:5565/task/service`, **driver inside the container** | Same protocol. She runs in-container because the engine **rejects WS upgrades through Docker's port proxy** (her §4.6) — a product finding we have not hit, since we run native. |
| **pipeline** | 4 stock components: `webhook → preprocessor_langchain → embedding_transformer → response_documents` | 5 stock: `webhook → **parse** → preprocessor_langchain → embedding_transformer → response_documents` | **She parses inside the engine; we parse outside it.** See §2 — this is the deepest structural divergence. |
| **custom nodes in the bundle** | **Yes** — `split_embed`, `env_probe`, `pdf_probe`, `cpu_probe`, `fault_probe`, `noop_probe` copied into `engine/nodes/` | **None.** Every provider is stock | Ours measures a modified install; hers measures the shipped product. Ours is the larger deviation from what a customer runs. |
| **hand-installed deps in the engine** | **Yes** — `pypdf` hand-copied into the engine's embedded CPython (not manifest-reproducible; `PROVISIONING.md` §3) | None required — the engine's own `parse` handles PDFs | Ours is a reproducibility gap we carry deliberately and document as toil. |
| **splitter config** | `preprocessor_langchain` config `{}` → engine default | `{profile: default, splitter: RecursiveCharacterTextSplitter, mode: strlen}` → engine default | **Effectively the same.** Both land on LangChain's defaults because the engine drops splitter kwargs (`_filter_kwargs_for`). She discovered independently that `strlen: 4000` **is not a schema field** and removed it; we wrote a custom `split_embed` node to work around the same defect. Same root cause, two different responses. |
| **effective chunking** | 4000 / 200 (LangChain defaults) | 4000 / 200 — **and she reads the values back off the splitter object** (`s._chunk_size`) rather than trusting config | **They match.** Her probe capture measures real chunks at median **3,966 chars** (max 3,969), consistent with a 4000 target. Her read-back is the stronger verification; we assert ours from documentation. |
| **embedding model** | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, 384-d, CPU | identical, via `profile: miniLM`; engine reports the resolved id back per document | **Match.** Both L2-normalised. |
| **device assertion** | Asserted — pipeline refuses to start on mismatch; `resolved_device()` read off loaded parameters | Pinned `DEVICE` + reported in `/meta`; RR side reads the engine's returned `embedding_model` | Both verify rather than assume. |
| **thread config** | **Unpinned — measured 10 intra-op / 14 interop**, both arms gated to match | **Pinned to 1** (`TORCH_THREADS=1`, `OMP_NUM_THREADS=1`), both arms | **The largest single lever we measured: 3.07× at concurrency 1.** Neither is wrong — we chose each arm's own best; she chose fairness-by-pinning — but results are not comparable across this axis. |
| **thread verification** | In-process, read from the live worker (`torch.get_num_threads()` in the task process and in the uvicorn worker) | Env pins set before library import, with a note that they only apply if set early | Ours measures; hers sets correctly and documents the ordering hazard. Ours is the stronger check on this specific axis. |
| **concurrency model** | Closed-loop, one pipeline, **C in-flight sends**; achieved concurrency measured per cell | **Open-loop burst** — all documents dispatched at once (`send_window_s ≈ 0.0001`), `MAX_INFLIGHT_REQUESTS=8` | Different question. Hers measures queueing under burst; ours measures steady state at a held concurrency. Her latency percentiles explicitly include queueing. |
| **pool width observed** | **17.24** (VERIFIED, 2 methods) | **~4-slot admission ceiling** under burst; separately, pool size 8 against one shared instance | Divergent, and unresolved. Different engine version, emulation, and container CPU budget all differ — cannot be attributed. **Open question.** |
| **project_id strategy** | **Unique per phase/pid/timestamp** → separate backend per driver | Shared `project_id` + `use_existing=True` → three clients received the **same token**, one backend | Materially different topology: ours spawns per-driver backends, hers multiplexes one. Affects memory and concurrency semantics. |
| **memory accounting** | engine parent + task tree (by PID) **+ our driver**, one number | **Container-scoped**: `rss_mb_sum` over all procs in the cgroup, with per-process breakdown and cmd; client `maxrss` recorded separately | Hers is cleaner — the cgroup is an unambiguous boundary and she keeps the client out of the arm total. Ours folds the driver in, which we disclose but which inflates our RocketRide figure. |
| **warm-up** | 50 documents discarded before any statistic; block-level first-run effect now also identified | `/health/ready` gated on the graph having run once; warm-up **fixture** PDF; no documented discard of the first N measured documents | Ours excludes warm-up from statistics; hers gates readiness but appears to include early documents. Direction: would inflate her early-run figures. |

## 2. The deepest divergence: where PDF parsing happens

| | WS-1 (ours) | Leela's |
| --- | --- | --- |
| RocketRide arm | driver extracts with **pypdf**, sends text | engine's **`parse`** provider extracts (Tika-class) |
| framework arm | driver extracts with **pypdf**, sends text | service extracts with **pypdf** |
| symmetric within the study? | **Yes** — both arms get identical pre-extracted text, so extraction is common-mode and cancels | **No** — her two arms use *different parsers* |

Neither choice is free:

* **Ours** keeps extraction out of both arms, so the comparison isolates split+embed — but it means
  our RocketRide numbers **exclude work the engine would do in production**, and we had to hand-copy
  `pypdf` into the engine for the separate `pdf_probe` path.
* **Hers** is more production-shaped (the service does the whole job) but introduces a parser
  asymmetry between arms. She measured it rather than assuming: on 140 real GovDocs PDFs the median
  RR/LG character ratio is **0.994** (p10 0.971, p90 1.030), and she explicitly corrected an earlier
  "~3.3% inflation" figure that had over-generalised from one synthetic fixture.

**Consequence for combining results:** goodput and fault counts are not comparable across teams at
all. Ours count failures of split+embed on identical text; hers count failures of parse+split+embed
on text each arm produced itself.

## 3. Her framework arm **does** run over HTTP — she did not make our mistake

**LangGraph runs behind FastAPI/uvicorn on port 8100**, driven over HTTP. Both her arms are
`client → network → service → worker`.

This is the thing we most wanted to check, because we published three weeks of numbers with
LlamaIndex **in-process** against RocketRide **over WebSocket** before catching it
(`MATCHED_LAYERS.md`). Her layering was matched from the start. The relevant part of our finding for
her is not a warning but a calibration:

| LlamaIndex topology | RocketRide | verdict |
| --- | ---: | --- |
| in-process, 1 worker | 2.0× worse | RocketRide heavier |
| uvicorn, 8 workers, idle | 22.8× better | LlamaIndex heavier |

Same two systems, opposite verdicts, and the only variable is the framework arm's topology and
worker count. Our measured crossover is at **C ≈ 3.2** — below it RocketRide is heavier, above it
lighter. **Her `EXECUTOR_WORKERS=4` / `MAX_INFLIGHT_REQUESTS=8` sits right at that crossover**, which
is the region where a memory ratio moves fastest with configuration. Worth pinning explicitly in any
result she publishes, for the same reason ours needed it.

## 4. Workload and gates

| | WS-1 (ours) | Leela's |
| --- | --- | --- |
| corpus | GovDocs1, **10,000** PDFs, 5.9 GB | GovDocs1, **1,000** PDFs, 618 MB, with `manifest.jsonl` (name, bytes, sha256, selection rule) |
| derivation recorded | fetch script + characterisation | **per-document sha256 manifest** — stronger provenance than ours |
| documents per run | 2,000/block × 3 blocks (primary); 500/cell × 3 (sweep) | 200 / 500 / 1,000 tiers |
| repetitions | n=3, randomised order, interleaved arms | 3-rep alternating protocol (`chain200.sh`) |
| goodput / correctness gate | 6 shape checks (chunks>0, non-empty, 1 vector/chunk, 384-d, L2≈1, vectors distinct) + content sanity (NUL, printable ratio) | dims / finite / norms / ids-unique / all-returned **plus ground-truth chunk-hash comparison** (`gt_exact`, `gt_hash_mismatches`) |
| variance gate | 10 % spread, n≥3, refuses n=1 | not a formal spread gate; validity is per-rep boolean |
| timing reportable? | Yes on the framework arm, native; **throughput never** (2.2× order effect) | **No — explicitly `metrics_emulated_relative_only`.** Both arms emulated `linux/amd64` on arm64 |

**She has a correctness gate we lack:** ground-truth chunk hashes. Our goodput gate proves vectors
are *well-formed*; hers proves the *content is the expected content*. Given her §4.10 finding —
**the embedder truncates at 512 tokens while chunks are ~4,000 chars**, so vectors saturate and
cross-arm vector similarity is weak evidence — chunk hashes are the stronger gate. That finding
applies to our runs too and we have not documented it.

**We have a variance gate she lacks**, and warm-up exclusion she does not appear to have.

## 5. Our own questionable choices, listed plainly

Not as caveats to hers — as the same class of thing:

1. **Custom nodes copied into the engine bundle.** We benchmark a modified install. Hers is stock.
2. **`pypdf` hand-copied into the engine's embedded interpreter** — not manifest-reproducible, will
   not survive an upgrade, must be redone in any image.
3. **`split_embed` exists to work around an engine defect** (dropped splitter kwargs), so part of our
   pipeline is our code, not the product's.
4. **Our driver is counted in RocketRide's memory total** — disclosed, and it inflates our RocketRide
   figure by ~250–320 MB.
5. **We excluded PDF parsing from both arms**, which makes the comparison cleaner but less
   production-shaped than hers.
6. **We published a topology-confounded memory ratio for three weeks** before catching it.
7. **Our engine has been up 30+ hours across runs**; hers restarts per container run. We have one
   observed 300 s task-creation stall that may relate.

## 6. Independent corroborations worth noting

Two setups, two engine versions, same failure families — which raises confidence these are product
behaviours rather than either harness:

| finding | ours | hers |
| --- | --- | --- |
| task/backend lifecycle stalls | 300 s `INITIALIZING` stall after ~14 create/terminate cycles (PROVISIONAL, once) | **wedge**: 31 consecutive 300 s timeouts, zero recovery, WebSocket healthy, nothing surfaced to client (§4.3) |
| orphaned backends after teardown | ~150 concurrent pipelines livelock leaving orphaned node processes | `terminate()` did not reap a wedged backend at **2.6 GB RSS**; `--autoterm` did not fire (§4.8) |
| silent success-shaped failures | NUL truncation: success response, truncated `page_content` | per-doc defects failing *silently* with success-shaped response and empty payload (§4.2) |
| splitter kwargs ignored | `_filter_kwargs_for` drops them | `strlen: 4000` is not a schema field; removed |

## 7. Minimum pinning set for comparable results

For any two of the three teams to place results side by side, **all** of these must be identical and
recorded with the result:

| # | must be pinned | agreed? |
| --- | --- | --- |
| 1 | **Engine release tag** and **SDK version**, as a stated pair | ❌ **OPEN — we differ (3.3.1 vs 3.2.1). Highest priority.** |
| 2 | Pipeline component list, and whether any node is custom | ❌ open — ours has custom nodes, hers does not |
| 3 | **Where PDF extraction happens** (in-service vs in-driver) and which parser | ❌ open — the deepest structural divergence |
| 4 | Embedding model id, device, normalisation | ✅ agreed — same model, CPU, normalised, both verified |
| 5 | Effective chunk size / overlap, **read back from the live splitter** | ✅ agreed in value (4000/200); ⚠️ only she verifies by read-back |
| 6 | Thread counts, **measured in-process**, not exported | ❌ open — unpinned-10 vs pinned-1 |
| 7 | Concurrency: offered **and achieved**, closed- vs open-loop | ❌ open — held-C vs open-loop burst |
| 8 | Memory accounting boundary (container cgroup vs process tree; driver in or out) | ❌ open |
| 9 | Warm-up exclusion at document **and block** level | ❌ open — we exclude 50 docs; she gates readiness only |
| 10 | Corpus identity: source, subset, per-document sha256 manifest | ⚠️ same corpus family (GovDocs1), different subsets; she has the stronger manifest |
| 11 | Native vs emulated execution | ❌ open — hers is emulated and correctness-only by her own statement |
| 12 | Variance gate and n | ❌ open — we gate at 10 % n≥3; she uses per-rep validity |
| 13 | Correctness gate: shape checks **and** ground-truth content hashes | ⚠️ partial — she has hashes, we have shape + content sanity; neither has both |

**Already agreed: 4 and 5** (model and chunking) — and those converged independently, which is
encouraging. **Everything else is open.**

**Status of adoption (2026-08-12):** the chunk-hash gate is **adopted** (`harness/chunk_hash.py`, regression test `chunk_hash_gate`), and the 512-token limit is documented with an independent measurement. **cgroup-scoped memory accounting is deferred to Phase 2** — it is the better boundary, but switching mid-project would make our historical figures incomparable with their own successors; Phase 2 on Linux with real cgroups v2 is the natural point to change it. Logged as STATE.md L4.

**Cheapest high-value moves**, in order: (1) agree an engine+SDK pair and both re-run a small tier on
it; (2) adopt her ground-truth chunk-hash gate, which is a strictly better correctness check than
ours and cheap to add; (3) adopt our block-level warm-up exclusion and 10 % variance gate; (4) decide
jointly where extraction happens, since no amount of statistics reconciles two different parsers.

**Note on 512-token truncation (her §4.10):** it affects both teams and both arms equally, so it does
not bias any comparison — but it means vector-similarity evidence is weak everywhere, including in
our NUL-truncation work where we used cosine similarity as a check. Our conclusion there rests on
`cos = 1.0000` against a reference computed the same way, so it is unaffected, but it is worth
re-reading with this in mind.
