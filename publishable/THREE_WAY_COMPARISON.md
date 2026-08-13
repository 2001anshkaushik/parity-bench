# Three-Way Comparison — WS-1 (LlamaIndex), Leela (LangGraph), Shashi (Haystack)

**Supersedes the two-way table in [`CROSS_TEAM_COMPARISON.md`](CROSS_TEAM_COMPARISON.md) §1.** That
document is retained — its §2 (parser placement) and §4 (workload/gates) reasoning still stands, and
its 13-item pinning list is folded into §5 here.

**What this is:** a record of where three independently-built RocketRide benchmarks diverge. **The
framework arms are supposed to differ — that is the study. The RocketRide arms are not.** Every
divergence in a RocketRide arm is a reason two results cannot be placed side by side.

Each divergence is marked **BLOCKING** (results not comparable) or **NOTED** (comparable with
disclosure).

| repo | commit | cloned |
| --- | --- | --- |
| ours — `benchmark-A` | working tree | — |
| Leela — `Leela8256/bench_langgraph_prod` | `b9b4736` (2026-08-12) | 2026-08-12 |
| Shashi — `shashidharbabu/rocketride-haystack-benchmarking` | `35ad350` (2026-08-11) | 2026-08-13 |

Both reference repos are read-only siblings of `benchmark-A` under `Benchmarking/reference/`. Nothing
in our tree was modified; no nested `.git` exists.

---

## 1. The headline: engine version is now decided by majority

| | engine | SDK | manifest pairing |
| --- | --- | --- | --- |
| **Leela** | **`server-v3.2.1`** | `1.3.0` | ✗ 3.2.1 bundles **1.1.1** |
| **Shashi** | **`server-v3.2.1`** | `1.2.0` | ✗ 1.2.0 pairs with **3.2.2** |
| **us** | `server-v3.3.1` | `1.3.0` | ✓ paired |

**Two of three are on `server-v3.2.1`. We are the outlier.** [VERIFIED — Shashi's
`docker/engine.Dockerfile` and benchmark script both pin the 3.2.1 linux-x64 tarball; Leela's
Dockerfile pins the same.]

**That effectively makes the team decision: standardise on `server-v3.2.1`**, and we move. The
alternative — two people move to 3.3.1 — costs more and has no stated benefit. This is the single
highest-priority item and everything else is downstream of it. **BLOCKING until done.**

**The SDK is a separate, unresolved problem:** all three of us run a client the engine's own manifest
does not bundle, and we run **three different clients** (1.3.0 / 1.2.0 / 1.3.0 against 3.2.1 /
3.2.1 / 3.3.1). Whatever engine we pick, the SDK must be pinned deliberately as a pair, not
inherited. **BLOCKING.**

**Shashi records the engine binary's sha256** at provision time. Neither Leela nor we do. That is
strictly better provenance than a release tag — a tag can be re-pushed — and we should adopt it.

## 2. The three RocketRide arms, side by side

| | ours (WS-1) | Leela | Shashi | verdict |
| --- | --- | --- | --- | --- |
| **engine** | `3.3.1` | `3.2.1` | `3.2.1` | **BLOCKING** — majority 3.2.1 |
| **SDK** | `1.3.0` | `1.3.0` | `1.2.0` | **BLOCKING** |
| **engine binary sha256 recorded** | no | no | **yes** | NOTED — adopt his |
| **pipeline** | `webhook → parse → preprocessor_langchain → embedding_transformer → response_documents` | same 5 | `webhook → parse → preprocessor_langchain → embedding_transformer → **qdrant**` | **BLOCKING** — his terminal node writes to a vector store; ours return documents. Different work is measured. |
| **scope** | ingest only | ingest only | **ingest + RAG query** (`chat → embedding → qdrant → llm_ollama → response_answers`, Ollama llama3.2:1b) | **BLOCKING** — his numbers include retrieval and generation |
| **stock vs custom nodes** | **6 custom** in the bundle (`split_embed`, `env_probe`, `pdf_probe`, `cpu_probe`, `fault_probe`, `noop_probe`) | **0** | **0** | **NOTED — we are the outlier**, and by the largest margin. We benchmark a modified install; both of them benchmark the shipped product. |
| **hand-installed engine deps** | **`pypdf` hand-copied** into the embedded CPython, no supported path | none | none | **NOTED — ours only** |
| **parse provider** | stock `parse` | stock `parse` | stock `parse` | agreed |
| **parse input lane** | `tags` | `tags` | `tags` | agreed — all three use `tags`, **not** the `data` the node's README documents |
| **splitter config declared** | `{}` → engine default | `{profile: default, splitter: RCTS, mode: strlen}` | `{profile: recursive, recursive: {mode: strlen, strlen: 512, splitter: RCTS}}` | NOTED |
| **splitter ACTUALLY in effect** | **4000/200** | **4000/200** | **4000/200** | **agreed — but all three arrived by discovering the same bug** (see §3) |
| **embedding model** | `multi-qa-MiniLM-L6-cos-v1` via `profile: miniLM` | same via `profile: miniLM` | same via `profile: custom` + short name (RR node caps model strings at 32 chars) | agreed |
| **device** | cpu, **asserted** — reads resolved device off loaded params, refuses to start on mismatch | cpu, pinned + reported in `/meta` | cpu, stated in the run header | NOTED — ours is the strongest assertion |
| **thread config** | **unpinned, MEASURED 10** intra-op / 14 interop | **env-pinned to 1** | **SDK-pinned to 8** via `use(threads=8)` | **BLOCKING** — three values *and* three mechanisms |
| **thread verification** | **in-process on both arms** (task process + uvicorn worker report their own `torch.get_num_threads()`); runner refuses to start on mismatch | env set before import, ordering hazard documented | **DECLARED only** — `--threads` passed to `use()`, no read-back found | **BLOCKING** — a declared thread count has been wrong here before |
| **transport** | WebSocket+DAP, driver on host | WebSocket+DAP, driver **in-container** (engine rejects WS through Docker's port proxy) | WebSocket+DAP, driver in-container | NOTED |
| **concurrency model** | closed-loop, C in-flight, **achieved measured per cell** | open-loop burst, `MAX_INFLIGHT=8` | engine-side concurrency via `use(threads=8)`, one resident pipe | **BLOCKING** — three different questions |
| **memory accounting** | engine parent + task tree (by socket) **+ driver** | **container cgroup**, per-process breakdown, client excluded | **driver/client `ru_maxrss` only** (`getrusage(RUSAGE_SELF)`) | **BLOCKING** — three incompatible boundaries. His does not capture the engine at all; ours folds the driver in; hers is the cleanest. |
| **warm-up** | 50 docs discarded + **block-level first-run effect identified** (12–38 %) | `/health/ready` gated on one graph run | one file untimed, one query untimed | **NOTED** — none of us discards the same thing |
| **variance gating** | 10 % spread, **n≥3, refuses n=1** | per-rep validity boolean | none found | **BLOCKING** for any quoted magnitude |
| **corpus** | GovDocs1, 10,000 PDFs | GovDocs1, 1,000 PDFs, **sha256 manifest** | **arXiv, pinned by ID + per-file sha256, hard-fails on mismatch** | **BLOCKING** — different corpora entirely |
| **corpus provenance** | fetch script, no per-file manifest | per-file sha256 | per-file sha256 + explicit "arXiv may re-render" failure mode | **NOTED — we are the weakest here** |
| **correctness gates** | vector shape (6 checks) + content sanity + **per-arm chunk hash** | **chunk-hash ground truth** computed outside both frameworks + shape checks | **dataset pin sha256 + engine binary sha256**; Qdrant chunk-length readback. No chunk-hash GT, no vector-shape gate found | **NOTED** — three different coverages, none a superset |

## 3. What all three of us found independently

This is the strongest evidence in the whole comparison, because it is three harnesses, two engine
versions, three frameworks, three hosts:

**The engine silently drops configured splitter kwargs.** All three of us hit it and responded
differently:

* **We** wrote a custom `split_embed` node to work around it.
* **Leela** read the schema, found `strlen: 4000` is not a field under her profile, and removed it.
* **Shashi** did the best thing of the three: he **measures the result at runtime**. After a probe
  ingest he reads chunk lengths back out of Qdrant, and if the longest exceeds 3,000 chars he
  concludes the config is inert and reconfigures his Haystack arm to 4000/200 to match *actual*
  engine behaviour, printing `!! engine chunk-size config is INERT (known bug)`.

That is declared-vs-measured applied at runtime, and it is why all three arms converge on 4000/200
despite three different declared configs. **[VERIFIED — three independent discoveries.]**

**Consequence worth stating to the product team:** a configuration field that silently does nothing
was independently discovered by three teams in three weeks. It is not an edge case.

## 4. Matching against Shashi — what our refactor must change, and where his approach conflicts

We have already moved to Parser IN this week. Aligning to his shape needs:

| # | change | conflict? |
| --- | --- | --- |
| 1 | **Engine 3.3.1 → 3.2.1**, SDK pinned to whatever the team agrees | none, but re-baselines everything |
| 2 | Pipeline terminal node — his ends in `qdrant`, ours in `response_documents` | **CONFLICT.** Writing to a vector store adds I/O and a network dependency to the measured region. Ours returns documents so the harness can hash them. **If we adopt qdrant we lose the chunk-hash gate**, because chunks stop coming back through the response. Recommend: keep `response_documents` for the ingestion comparison and treat his RAG-query phase as a separate tier. |
| 3 | `strlen`/profile config | **no conflict in effect** — all three land on 4000/200. Adopt his runtime read-back so it is measured rather than assumed. |
| 4 | `embedding_transformer` profile `miniLM` vs `custom` + short name | NOTED — same model resolves. His `custom` path exists because the node caps model strings at 32 chars, which is worth knowing. |
| 5 | Thread config | **CONFLICT.** He pins via the SDK's `use(threads=8)`; we set env vars and read back in-process. These are different mechanisms and may not even control the same pool. **Must be resolved by measurement, not by picking one** — and our in-process read-back is the instrument that can settle it. |
| 6 | `text + "\n"` transform | **potential CONFLICT, unresolved.** Leela established the engine appends exactly one newline and all three services must apply it identically. I found no equivalent handling in Shashi's Haystack arm, which uses `DocumentSplitter(split_by="character")` rather than a LangChain splitter. If his arm does not apply it, his two arms' chunk boundaries differ from ours by one character at every document end. **Needs a direct check before any joint run.** |
| 7 | Memory accounting | **CONFLICT.** His `ru_maxrss` measures only the driver and would report near-zero for engine-side work. Ours and Leela's both capture the service. Recommend Leela's cgroup boundary for Phase 2 (already logged as our L4). |

**Not adopting silently:** items 2, 5, 6 and 7 are flagged rather than absorbed. Each would change a
number, and two of them (5 and 6) could change chunk content.

## 5. Minimum pinning set — status across three teams

**Agreed by all three (no action):**

1. `parse` consumes the **`tags`** lane, not `data`
2. Parser IN — extraction inside each framework
3. Embedding model `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, 384-d, **CPU**
4. Effective chunking **4000/200** (all three, arrived at independently)
5. Stock `parse` provider on the RocketRide side

**Agreed by majority — we are the one who moves:**

6. **Engine `server-v3.2.1`** (Leela + Shashi). We are on 3.3.1.
7. **Zero custom nodes in the bundle** (Leela + Shashi at 0; we have 6)
8. **Per-file sha256 corpus manifest** (Leela + Shashi have one; we do not)

**Still needs a decision — no majority:**

9. **SDK version** — three different clients, none paired with its engine
10. **Thread count and mechanism** — 10 unpinned / 1 env / 8 SDK, and env-vs-SDK may not control the same pool
11. **Memory accounting boundary** — engine-tree+driver / cgroup / driver-only
12. **Concurrency model** — closed-loop held / open-loop burst / engine-side threads
13. **Corpus** — GovDocs1-10k / GovDocs1-1k / arXiv-pinned
14. **Variance gating** — 10 %/n≥3 / per-rep boolean / none
15. **Scope** — ingest-only (Leela, us) vs ingest+RAG (Shashi)
16. **Correctness gate set** — no team's is a superset of another's

**Cheapest high-value moves:** (a) settle engine+SDK, since everything re-baselines anyway;
(b) adopt Shashi's engine-binary sha256 and runtime chunk read-back, and the per-file corpus
manifest that both of them have and we lack; (c) adopt Leela's chunk-hash ground truth and cgroup
accounting; (d) resolve the thread mechanism by measurement — our in-process read-back is the only
instrument among the three that can tell whether `use(threads=)` and `OMP_NUM_THREADS` control the
same pool.

## 6. Where our setup is the weakest of the three

Stated plainly, because we have the most non-standard choices and they bias how this document could
otherwise read:

* **Six custom nodes in the engine bundle.** Both of them run zero. We benchmark a modified install.
* **`pypdf` hand-copied** into the engine's embedded interpreter with no supported install path.
* **`split_embed` exists only to work around** the dropped-kwargs defect — part of our pipeline is
  our code, not the product's. Shashi solved the same problem with a runtime measurement and no code
  in the engine at all.
* **No per-file corpus manifest.** Both of them can prove which bytes they measured; we cannot.
* **No engine-binary hash.** Shashi can prove which build he ran; we record a release tag, which is
  mutable.
* **Our driver is inside RocketRide's memory total**, inflating it by ~250–320 MB.

What ours does better, for balance: in-process thread verification on both arms with a gate that
refuses to run on mismatch, a 10 % variance gate that refuses n=1, block-level warm-up exclusion,
and achieved-vs-offered concurrency measured per cell. None of those exist in both other repos.
