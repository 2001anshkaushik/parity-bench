# STATE — durable resume point

**Written 2026-08-05, handoff section added 2026-08-14.** Assumes the reader knows nothing about
this project. Read this first.

---

## 0a. ⏸️ HANDOFF — READ THIS BEFORE ANYTHING ELSE (2026-08-16)

**A session with zero memory of this work starts here. Everything below §0a is history, newest
session first from `SESSION 35` down.** Sessions 20–35 are the current architecture; anything
older describes a harness that has since been substantially rebuilt.

### Where we are

| | |
| --- | --- |
| **Phase** | Phase 2 is RUNNING. Both arms execute in **Docker on x86-64**. A 200-doc run on the box is green and publishable; **the 10k run is the next milestone and is unblocked as of session 33.** |
| **AWS box** | `i-0775f33f3dc16f6af`, c7i.8xlarge, 32 vCPU / 61 GB. Driven by SSM only — **`ssm:SendCommand` is DENIED** for our role (AccessDeniedException, verified), so interactive `start-session` with piped stdin is the only channel. |
| **Auto-stop** | **DISPUTED — assume < 20 % instance CPU for 60 min**, i.e. 6.4 cores on 32 vCPU, against a 12.7 % idle floor. Our older note said 1 %. Use the eight-core keep-alive in `RUN_ON_EC2.md` §1a. [UNVERIFIED — open item for Dmitrii] |
| **Topology rule** | **Both arms containerized or the run is unpublishable.** One native + one containerized is the exact confound in `MATCHED_LAYERS.md` that produced two opposite memory verdicts. |
| **Team pin** | engine **3.3.1** + SDK **1.3.0**, Parser IN, stock 5-node pipe. Measured-pipe canonical digest **`f61165f7cf7ab1db`** — check it before comparing anything. |

### The document to execute

**`publishable/RUN_ON_EC2.md` §12** is the Docker sequence. §1–§2 (preflight, Python 3.12, apt
set), §3a (onnxruntime patch), §4 (corpus), §8 (exfil), §9 (traps) still apply. §3/§6/§7 describe
the superseded native path — do not run them. `BUILD_ON_EC2.md` is superseded entirely.

### Peer scale — the reason NOT to run 10k blindly [VERIFIED from their uploads, session 33 recon]

**Nobody is running 10,000 unique documents. Nobody is close.**

| | corpus | unique docs | offered | reps |
| --- | --- | ---: | ---: | ---: |
| Shashi `measured/2026-08-14/n200-seq50-191105Z` | arXiv cs.LG | **24** (hardlink-replicated) | 200 blast / 50 seq | 1 |
| Shashi `sessions/2026-08-15/s500-043653Z` | arXiv | 24 | 500 | **FAILED** (smoke rc=1, measured rc=1) |
| Leela `blast/20260814T210610Z` (LangGraph) | GovDocs1 | **150** | 150 | 3 |
| Leela `rr/2026081[45]*` × 5 (RocketRide) | GovDocs1 | **200** | 200 | 1 each |

Shashi's `materialize()` does `seeds[i % 24]` with hardlinks, so his "200 documents" is 24 files
seen ~8.3× each — **his docs/s is not comparable with ours in either direction**. Leela's two arms
are also not comparable *with each other*: 150 vs 200 docs, 3 vs 1 reps, 12-CPU cap vs uncapped.
`run.sh 10000` exists in Shashi's runbook as a planned command; it has never executed.

**Peer refs move almost daily. Re-clone before any comparison.** As of session 35: Leela
`aws-bench` **`6f7ce2e`**, Shashi `benchmark/shared-pipe-engine-3.3.1` **`ce15326`** — both moved
that same day. Shashi's `main` (`35ad350`) is NOT his benchmark branch.

### ⚠ Scale is not comparable across n — the single most important cross-site rule [VERIFIED, session 35]

**A 200-document throughput figure is structurally biased LOW against a 10,000-document one for
the same engine, and the bias worsens with concurrency.** Throughput is `(n − warm) / span` and
`span` ends when the LAST document finishes; GovDocs1 is severely heavy-tailed — **the slowest
1 % of documents carry 58.6 % of all service seconds**. At n=200, C=32 there are ~6 waves, so the
span is set by maxima; at n=10,000 there are ~312 and it converges to `C / mean`. Simulated from
ONE measured service-time distribution: 0.850 docs/s at n=200 vs 8.026 at n=10,000, a **9.44×**
ratio at C=32 (1.72× at C=4, 3.01× at C=8).

That is why Leela's 0.68–0.74 (200 docs) and our 4.03 (10k) are **the same engine**, and why our
own 200-doc runs read 0.52–0.67. **Never put figures from different n in one table.** Reproduce
with `working/scripts/throughput_ramp.py <perdoc.jsonl> --concurrency 32`.

### Envelope gaps vs BOTH teammates — named, UNQUANTIFIED [session 35]

| | us | Leela | Shashi |
|---|---|---|---|
| CPU allocation | `--cpus 32` CFS **quota** | **cpuset 0-23** (24 cores) | **cpuset**, both services identical |
| client / driver | **host, unpinned, shares the arm's cores** | own container, cpuset 24-31 | own container |
| memory | **`--memory 58g` hard cap** | **uncapped**, measured | **uncapped** |
| per-request deadline | 300 s | 3600 s, one deadline both arms | per-phase budget |

None of the four is measured. Our driver competing with the container under test is the one most
likely to matter, and it is not symmetric between arms.

### Parallelism — MEASURED, and it refutes the concern that preceded it [session 35]

**RocketRide 23.05 effective cores, LlamaIndex 30.51**, on the box. We pass no `use(threads=)`;
Shashi passes `threads=<host cores>` and gets 24.28. **Our RocketRide arm sits next to Shashi's,
not near Leela's 5.8–5.9** — Leela's figure describes his 24-core cpuset and single batched
`send_files`, not an engine default. No `use(threads=)` change is warranted. Residual RR-vs-LI
gap **1.32×**.

### Current architecture — what exists now

| module | what it is |
| --- | --- |
| `working/harness/metrics_shared.py` | THE metrics module, arm-agnostic, pure functions, 64 unit tests. Settled decisions are frozen here — do not re-litigate. |
| `working/harness/gates_shared.py` | Both teammates' gate dialects + the union, every function citing its source file:line. 60 unit tests, each mutation-tested. |
| `working/harness/memory_sources.py` | cgroup reader. **Quote `cgroup anon`**, never summed RSS. |
| `working/harness/jsonl_stream.py` | Crash-durable per-doc records + resume. Thread-safe writer. |
| `working/harness/rr_credentials.py` | Endpoint + key resolution; runs on `harness` import. |
| `working/scripts/smoke50_parser_in.py` | The driver. Both arms, both legs, five gates, three verdicts, metrics, memory. |
| `working/scripts/fetch_govdocs.py` | Manifest-driven corpus fetcher. `DONE` means verified. |
| `working/scripts/blast_latency_salvage.py` | Recovers service latency from pre-`79ad702` blast records (FIFO admission model, null-controlled). |
| `working/scripts/analyze_sampler.py` | Process fan-out + memory trajectory from sampler streams already on disk. |
| `working/scripts/throughput_ramp.py` | Replays measured service times through a C-server queue: why n=200 and n=10k disagree. |

### Settled decisions — do not change without the team

* **Warm-up**: metric-side, by completion rank (Leela's `perf_window`). Primary **64**, secondary 25 also emitted. (Shashi computes `max(4, 2×threads)` = 64 at 32 threads; Leela uses 25. Three values, one unresolved question.)
* **Percentile**: nearest-rank, integer ceil, no interpolation (Shashi's).
* **Threads**: 32 workers × **1 BLAS thread**, `TORCH_INTEROP_THREADS` **unset** on both arms.
* **Embedding dim**: probed from each arm's loaded model, never a 384 constant.
* **Unavailable ⇒ `None`**, never 0 or inf. `cpu_utilization > 1.0` is INVALID, never clamped.
* **Model**: all four arms load `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`. VERIFIED from the engine's own `nodes/embedding_transformer/services.json:81-87`; `miniAll` is a 384-dim decoy.

### Driver flags

| flag | effect |
| --- | --- |
| `SMOKE_EXTERNAL=1` | services are containers; never start one, discovery becomes non-fatal |
| `SMOKE_LEGS=sequential\|blast` | run one leg (default both); the other's records are read from disk |
| `SMOKE_RESUME=1` + `SMOKE_RUN_DIR` | continue a killed run from what survived |
| `SMOKE_PREFLIGHT=1` | thread-propagation gate only, no documents, exit 0/4 |
| `SMOKE_TIKA_SAMPLE=N` | deterministic stride sample for the JVM-per-doc check (0.599 s/doc) |
| `SMOKE_WORKERS` / `SMOKE_THREADS` / `SMOKE_BLAST_C` / `SMOKE_CORPUS_GLOB` / `SMOKE_WARM_N` | the pins |
| `SMOKE_LI_CONTAINER` / `SMOKE_RR_CONTAINER` | container names for `docker inspect` pid discovery |
| `SMOKE_REQUIRE_TIKA=1` | make a missing Tika reference fatal instead of reported |

### ⛔ Numbers that must never be quoted

* **`rocketride 1,025.4 MB cgroup anon` from the 10k blast** — a post-leg point sample, taken after the engine released its task processes (defect #31). **No valid cgroup figure exists for either 10k blast leg.**
* **Any `peakRSS` from before session 30** — it is a SUM of per-process RSS, over-counting shared pages by a factor that *scales with worker count* (32-worker LI badly inflated, 2-process RR nearly correct). Not usable even as a ratio.
* **Any performance figure from macOS/arm64** — superseded by policy. The metrics block now derives the caveat from `platform.system()/machine()`.
* **Anything in `archive/`.**
* **BUG_CHUNK_DUPLICATION's "~239.8k chars" and "5.34 % of corpus"** — the real predicate is **≥ 64 chunks** (root-caused by Shashi); the char figures are proxies needing re-derivation.
* **Every blast-leg latency written before `79ad702`** — RocketRide's clock started at batch open and LlamaIndex's at admission, so the two arms measured different quantities (defect #29). The 10k run's `rocketride blast p50 1120 s / p95 2150 s` is ~99 % client-side queue wait. **Blast throughput from the same records is unaffected and stands.**

### Defect register, sessions 20–34 — all found in OUR instrument

`#19` Tika gate inside the timed loop (~8.5× against RR) · `#20` model bake missed the runtime loader (llama-index ignores `HF_HOME`) · `#21` readiness by PID sampling (kernel accept bias) · `#22` credentials from a gitignored `.env` · `#23` readiness over-count after `docker start` (container PID namespace resets) · `#24` external mode honoured in 1 of 6 discovery sites · `#25` gate adapter contradicted the legacy path · `#26` peakRSS a summed RSS · `#27` killed run lost everything · `#28` fetcher counted its own arithmetic (session 33) · `#29` blast stamped the latency clock at different points on the two arms (~550× against RR) · `#30` memory table described the sequential leg while the metrics line beside it carried a blast-leg peak · `#31` cgroup anon read once AFTER the leg and printed under a "peak" heading (session 34) · `#32` OPEN — unset `ttl` defaults to 900 s idle while our own per-doc deadline is 1800 s; 371 docs lost, cause unconfirmed (session 36).

**The pattern, stated plainly: in this project the instrument is wrong more often than the system
under test. Thirteen instrument defects in fifteen sessions, zero product defects found by us in that
window that were not already known.** Behave accordingly — the Standing Verification Protocol in
§2 is not ceremony.

**Two of the twelve (#19, #29) were direction-asymmetric and both ran AGAINST RocketRide.** That is
worth knowing when the direction-of-bias rule tempts you to relax on a finding that hurts us: the
instrument has no loyalty, and an artifact that flatters the rival is exactly as likely.

### 🔴 OPEN — the 10k sequential leg died at document 9,629; ttl is the prime suspect [session 36]

**371 contiguous failures** (docs 9,630–10,000), every one "Your pipeline is not running … task
terminated". Container never restarted (`restarts=0`, up 27 h). Engine log: `child process pid
2045259 exit status already read: will report returncode 255`.

**From the SDK/server source — VERIFIED, not inferred:**

| fact | source |
|---|---|
| SDK sends **no** `ttl` when not passed; server applies its own default | `engine/rocketride/mixins/execution.py:245` |
| server default `CONST_DEFAULT_TTL = 15 * 60` = **900 s** | `packages/ai/src/ai/constants.py:55`, used at `task_server.py:1087` |
| it is an **IDLE** timer, not wall-clock: swept every 60 s, `_idle_time += 60`, terminate when `_idle_time >= _ttl` | `task_server.py:355-380` |
| `reset_idle_timer()` has **exactly one** call site — the top of `_send_data()`, i.e. at SUBMISSION. The clock therefore runs for the whole time a document is being processed | `task_engine.py:734`, `:1699` |
| `ttl=0` means **no timeout** ("Skip TTL enforcement if ttl is 0") | `task_server.py:365` |
| a TTL stop does `engine.terminate()` → `engine.kill()`, awaiting `engine.wait()` (which reaps the status) | `task_engine.py:2320-2340` |

**What each of us passes:** Shashi `ttl=0` (`rr_app.py:138`) · Leela `ttl=7200`
(`rr_driver.py:177`) · **us: nothing → 900 s**. We are the only one of the three relying on a
default we never read.

**THE INVERSION, and it is ours.** Our sequential per-document client deadline is **1800 s**
(`weekend_worker.py:409-410`) — **twice** the engine's 900 s idle TTL. Any document taking
900–1800 s is killed by the engine mid-processing while our client is still waiting. **A ttl must
always exceed the client's own per-request timeout; 900 < 1800 is a configuration error on our
side.**

**Cause NOT yet established, and one piece of evidence cuts against TTL.** Doc 9,629 is
`039_039660.pdf` (3.32 MB, 39 pages, 10,699 chars — top 2.6 % most image-heavy by bytes/char),
but five *worse* documents earlier in the corpus (indices 591, 3,492, 5,236, 6,343, 6,854) all
passed. "A monster document stalled" is not obviously the story.

**THE ONE CHECK THAT SETTLES IT** — consecutive `submit_ns` gaps in
`working/results/run10k/perdoc_rr_sequential.jsonl` near index 9,629. In a tight sequential loop
the gap between submissions IS the previous document's service time.

* any gap **≥ 900 s** → TTL fired, the engine did what it documents, **this is our config gap and
  a footnote**;
* largest gap **well under 900 s** → TTL did not fire, something else killed the child, **and that
  is a product finding**.

**Nothing about this goes in a report until that check runs.** Note also that the TTL termination
message goes through `debug_message`, so its absence from the engine log is not evidence against
TTL. The `returncode 255` line is *consistent* with the TTL path (`stop_task` awaits
`engine.wait()`, reaping the status, and a later reader finds it already read) but does not prove
it.

**Direction of bias:** 371 documents recorded as RocketRide failures. Publishing that as a
RocketRide reliability result, if the cause is our unset `ttl`, would be a false product finding
against our own engine.

### 🔴 COMPARABILITY BLOCKER — Leela patched the engine; our 10k did not [session 37]

Leela `aws-bench` **`a5c3b5d`** "RocketRide BUG_CHUNK_DUPLICATION: patch, permanent gate,
provenance" (2026-08-16). Shashi `benchmark/shared-pipe-engine-3.3.1` moved to **`d2b210d`**.

**It is an ENGINE-SIDE patch, and it changes what the engine EMITS.** `aws_bench/arms/
rocketride/Dockerfile` rewrites `nodes/embedding_transformer/IInstance.py` at image build,
inserting `return self.preventDefault()` after `self._flushDocuments()` — the flush already
delivers the batch downstream, and the node then also falls through to the default forwarding
action, emitting the same document list twice. Build-time guards fail the build if the file is
missing, the source shape changed, or the patch is already applied. Gated behind
`ARG RR_DUP_PATCH=1`; `RR_DUP_PATCH=0` builds stock 3.3.1 so the delta can be quantified.
Image carries `LABEL benchmark.rocketride.duplication_patch=...`.

He *also* added a harness-side **gate** (`metrics/m0_correctness.py::self_duplication`,
repeat_factor over ordered chunk hashes) — but that is detection, not correction. **The
correction is in the product.**

**Our exposure, MEASURED on our own records (unpatched engine):** **5 of 199 documents (2.5 %)
at repeat_factor exactly 2**, reproduced across two independent local 200-doc runs and on BOTH
legs. Leela measures 51/987 (5.2 %) on his corpus; same defect, same factor, different rate
because different documents. All five of ours have ≥64 chunks (164, 276, 1872, 132, 344),
consistent with Shashi's root cause (`maxDocuments=64` flush) — **our `over_chunk_trigger ≥ 64`
predicate caught 5 of 5**, so our gate is mechanically right, not an arbitrary threshold.

**What it contaminates in our 10k:** chunk counts for affected documents are doubled, so
`chunks_per_s` is inflated and `cpu_s_per_chunk` deflated; the engine also did the extra work,
so `docs_per_s` is depressed — **against RocketRide**. Determinism is unaffected (both legs
duplicate identically).

**A patched-engine result and an unpatched-engine result are not comparable.** Before any joint
table: agree whether the three-way run is stock 3.3.1 or patched, and record engine sha256 +
patch id in provenance either way (Leela now makes those REQUIRED fields).

### New scope — fault tolerance, data isolation, LOC: who has what [session 37]

| | Leela | Shashi | us |
|---|---|---|---|
| **fault tolerance** | `metrics/m4_m5_faults.py` — M4 `blast_radius`, M5 `fault_isolation`. **Code exists, NOT wired** into `report.py` or `matched_run.sh`; no `fault_manifest` in the repo | `bench.py:526`, **wired** at `:662`. 1 poison PDF + 6 good, blast, separate run, engine restarted first | none |
| **data isolation** | **nothing** | **nothing** | none |
| **lines of code** | `metrics/m6_loc.py` — complete counting rule, static, standalone | **nothing** | none |

Neither has *published results* for any of the three. Definitions exist for two of them; data
isolation is unclaimed by all three.

**Shashi's fault protocol (the one to match — it is the only one wired):** 1 poison document
(valid `%PDF-1.7` header + 64 KB `os.urandom`, so magic-byte sniffing does not catch it) plus 6
good documents, blast mode, as a SEPARATE run — "exception paths and retries change timing, so a
poisoned batch measures resilience, not speed". Recorded: `batch_survived`, `good_docs_ok`,
`collateral_failures` (**the** metric), `service_alive_after`, `recovery_ok`, `surfacing` (did the
SERVICE report the failure, or only our proof layer — a success-shaped empty response scores 0).
Leela's M4 adds `time_to_next_success_s` and an attribution window (60 s), free from our records.

**M6 LOC — Leela's rule, adopted verbatim.** Count = non-blank, non-comment lines; Python
docstrings excluded; pure Python, no `cloc`. Four layers per arm: `pipeline_definition`,
`compute_transforms`, `serving_integration`, `client_harness`. **The load-bearing line is
`"compute_transforms": []  # engine-internal: product code, not user code` for RocketRide** — the
engine's internals are not counted because a developer does not write them, exactly as
LangChain's/LangGraph's internals are not counted for the other arm. Symmetric in rule, asymmetric
in result, and that asymmetry IS the product difference being measured. **A hostile reviewer goes
straight at this line, so it must be stated before the number, not after.**

Applied to our repo with Leela's `count_loc` verbatim:

| layer | llamaindex | rocketride |
|---|---:|---:|
| pipeline_definition | 210 | 78 |
| compute_transforms | 195 | 0 |
| serving_integration | 164 | 58 |
| client_harness | 140 | 13 |
| **arm total** | **709** | **149** |

**4.8×.** Our measurement harness (`working/harness/*`, ~5,400 lines) is **excluded** — it is
benchmark scaffolding, not what a developer writes to build the pipeline. **PROVISIONAL**: one
counting pass, no second method.

### 🔴 FINAL SWEEP before the meeting — Leela moved again, Shashi did not [session 38, 2026-08-17]

**Shashi: ZERO commits since `d2b210d`.** Nothing to revise on his side.

**Leela `aws-bench` `a5c3b5d` → `0a0b558`** (5 commits). What matters:

| change | effect on us |
|---|---|
| **M4 `blast_radius` redefined** (`0a0b558`): now counts **DISTINCT** collateral docs and takes `independent_failures`, a set of docs that fail in a clean baseline | **METHOD WE COPIED IS STALE.** `working/harness/fault_metrics.py` has the pre-fix version. Our 1-poison protocol makes the distinct-vs-sum defect inert, and all 7 documents our fault experiment selects extract text (276–26,005 chars), so no independent failure can fire — **by luck of the draw, not by design.** 21/10,000 corpus documents are text-free |
| Leela **retracted a finding** with it: his first real fault run reported blast radius 3 (LG) / 2 (RR); both were the SAME always-failing text-free PDF. Re-derived to 0/0, PASS | nothing of ours changes; it is a live instance of exactly the defect class our register tracks |
| **He now HAS data isolation** (`e728d51`, `fault_report.py::data_isolation`) | **CONTRADICTS OUR SUMMARY CLAIM** that neither teammate has any. His definition differs: unrelated docs must be **byte-identical to a clean baseline within a fault run**. Ours is two tenants, disjoint corpora, concurrent, cross-tenant content. Adjacent, not the same question |
| **Fault work is now WIRED** (`run/fault_run.sh`) and has been run | our "neither has published results" is now false for Leela |
| His fault corpus is **4 kinds** — corrupt, zero_byte, truncated, oversized_garbage (`corpus/make_faults.py`) | ours copies **Shashi's** single poison (%PDF header + 64 KB random). Say which we match; we do not match Leela here |
| **`native_saturation` mode**: the arms deliberately use DIFFERENT submission interfaces — LangGraph a bounded HTTP window, RocketRide one whole-corpus SDK batch. *"Fairness lives in the equal cpuset, not the interface."* | **contradicts our framing** that our N-individual-sends shape is a deviation from their batched shape. He now argues forcing a match "would benchmark our misuse of one API rather than either product" |
| **"we measured per-document RocketRide submission at roughly a third of its batched throughput"** | **CHANGES A NUMBER WE PRESENT.** Our blast leg is per-document sends at C=32. Our 4.03 docs/s may understate RocketRide by ~3× purely from submission shape — **a handicap we imposed on our own arm** |
| `verify_output.py` (`240d570`) reads the ACTUAL text and vectors, not just hashes — "a hash is just as stable for garbage as for prose" | a correctness capability neither we nor Shashi have. Not a contradiction; a gap |
| `rr_driver.py`: new assert that `threads` reached `use()`. **ttl still 7200. WARM still 25. cpuset unchanged. deadline still 3600 s both arms** | no config beliefs change |
| **`RR_DUP_PATCH` default still `1`** | unchanged: he runs patched, we run stock. Comparability blocker stands |

No result JSONs are committed to his repo; S3 could not be checked from this laptop (no `aws`/`boto3`).

### Before the 10k run — the remaining checklist

1. ✅ Corpus complete and manifest-verified (session 33).
2. ✅ Both legs stream + resume; legs separable.
3. ✅ Blast clock symmetric on both arms; both stamps recorded (session 34, `79ad702`).
4. ⬜ **One cgroup-instrumented 200-doc run** — `memory_sources.py` shipped after the last box run, so **no cgroup memory figure exists yet**. ~20 min, and it converts the OOM question from an extrapolation of an over-counted number into a measurement.
5. ⬜ Decide `SMOKE_TIKA_SAMPLE=200` (recommended) vs full (adds ~1.7 h).
6. ⬜ Raise the corpus divergence with the group before anyone builds a three-way table.
7. ⬜ **Re-run the blast leg (~40 min)** to replace the reconstructed latencies with measured ones. Sequential is unaffected and does not need re-running.

## 0. What this is

Ansh owns the **LlamaIndex FastAPI service** for **WS-1 "Service Parity"** — a three-way
comparison (RocketRide engine, LangChain/LangGraph, LlamaIndex) all implementing the same
document-embedding pipeline behind the same wire contract. Teammates: **Shashi** (owns the
RocketRide service), **Leela** (owns the shared schema and the mt10k reference data).

`benchmark-A/` was an earlier parallel exploration, superseded by WS-1 after the Aug 4 exec
review. Its findings were harvested into `FINDINGS_FOR_WS1.md`; the directory is now where the
LlamaIndex service and all measurement work lives.

## 1. Environment

| | |
| --- | --- |
| Host | Apple M4 Pro, 14 cores (10P + 4E), 48 GiB, macOS 26.6, arm64 |
| Python | `$REPO/.venv` → 3.12.13 |
| Working dir | the clone root (`$REPO/parity-bench`) |
| Engine | `server-v3.3.1`, reports `3.3.1.35` hash `a0817cc6`, installed at `<clone>/engine/` |
| Engine SHA256 | `846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836` |
| SDK | `rocketride` 1.3.0 (co-released with server 3.3.1 — pairing verified from release manifests) |
| Key libs | llama-index-core 0.14.23, sentence-transformers 5.6.1, torch 2.13.0, langchain-text-splitters 1.1.2, **rocketride 1.3.0 (the client SDK — pip-installed; `rocketlib` is the bundle-supplied one imported by nodes INSIDE the engine)** |

**⚠️ THIS TABLE DESCRIBES THE LAPTOP. The measurement target is the AWS box** — c7i.8xlarge,
32 vCPU / 61 GB, Ubuntu, x86-64, both arms in Docker. The `$0 / no paid cloud` constraint that
used to sit here is **obsolete**: the box is metered at ~$1.43/h and is the only platform whose
numbers are publishable. Laptop figures are wiring validation, and the metrics block now derives
that caveat from `platform.system()/machine()` rather than asserting it.

Platform facts that matter, all VERIFIED by parsing the artifacts:

* Engine binary is **x86-64 only** — no linux-arm64 asset exists. Tarball sha256
  `d8dad45b…ce0281d8`; extracted `engine` binary `95768e26…d9747` (matches Leela's independently
  derived pin). Tarball extracts **flat** — never `--strip-components`.
* Highest glibc symbol referenced is **2.35** — Ubuntu 22.04 exactly, **zero headroom**.
* Real `DT_NEEDED`: `libc.so.6`, `ld-linux-x86-64.so.2`, `libm.so.6`, `libgcc_s.so.1`, `libjvm.so`,
  `libc++.so.1`, `libc++abi.so.1`, `libunwind.so.1`. So apt needs exactly
  `libc++1 libc++abi1 libunwind8`. `libnuma`/`libcrypto` are dlopen probes — do NOT install them.
* Ubuntu 22.04's system Python is **3.10 and cannot install our pins** — `numpy==2.5.1` and
  `scikit-learn==1.9.0` have no cp310 wheel. Install 3.12 first.
* Engine 3.3.1 **cannot cold-boot on Linux unpatched**: `onnxruntime-gpu==1.20.1` was removed from
  PyPI and the constraints compile is all-or-nothing. The pin is in **five** manifests, not three.
* The engine's dependency cache is `<engine dir>/cache`, **shared across all pipelines** — once any
  pipeline installs torch it stays importable, which is why a local "it works" can be a false pass.

## 2. THE STANDING VERIFICATION PROTOCOL (verbatim — this governs everything)

```
=== STANDING VERIFICATION PROTOCOL — applies to every step, every run ===

Track record so far: the collector biased results 100×; IPC cost was
mis-measured by 115×; a single-process driver understated throughput 4.8×;
asymmetric deadlines manufactured a fake 7× gap; the alloc test freed memory
immediately so it never tested what it claimed; the hang ratio turned out to be
pool-width arithmetic; a service declaring 14 workers measured 4. In this
project, the instrument is wrong more often than the system under test. Behave
accordingly.

BEFORE reporting any number:
1. TWO INDEPENDENT METHODS. Any load-bearing number needs a second method with
   different failure modes. One method = label it PROVISIONAL, never headline.
2. DECLARED ≠ MEASURED. Never trust a config value, a flag, a worker count, or
   a docstring. Measure it. When they disagree, that gap IS a finding.
3. NULL CONTROL. Run the variant where you predict no difference. If a
   difference appears, the instrument is broken — stop and fix it.
4. REPRODUCE. n≥3, randomized order, report spread. A single-run number is
   never reported as fact.
5. DIRECTION-OF-BIAS. For each finding ask: does this favor RocketRide? If yes,
   hunt twice as hard for the artifact. Favorable results get more scrutiny,
   not less.
6. STRONGEST ALTERNATIVE. Before writing a conclusion, state the best rival
   explanation and the experiment that separates them. If you can't separate
   them, say so in the report rather than picking one.
7. WHAT WOULD A HOSTILE REVIEWER SAY. One sentence per finding, answered.

LABEL EVERY CLAIM: VERIFIED (two methods, reproduced) / PROVISIONAL (one
method) / UNVERIFIED (asserted, not established). No unlabeled claims.

WHEN A NUMBER IS SUPERSEDED: add a correction banner to every doc carrying the
old value, in the same turn. Never leave a stale figure anywhere.

STOPPING RULE — this must not become infinite. Verification effort scales with
how load-bearing the number is: headline claims get the full protocol,
incidental observations just get a label. If a check would take >30 min and
isn't load-bearing, label it PROVISIONAL, log it as an open item, and move on.
Say what you skipped and why.
=== END PROTOCOL ===
```

Standing operational rules layered on top: pre/post health checks and orphan cleanup around every
probe (`working/harness/engine_ops.py::preflight/postflight`), a 90 s livelock watchdog, never leave the
process table above ~750, append to `progress.md` as you go.

## 3. THE HEADLINE FINDING — document weight (the burst/sustained story is DEAD)

> **⚠️ SESSION 6 — READ THIS BEFORE ANYTHING ELSE IN THIS SECTION.**
> The **31 % sustained decay is WITHDRAWN** — it does not reproduce (6.0 % on exact replication;
> median +1.5 % RR / +1.0 % LI over a symmetric n=3 with randomised order, both arms swinging in
> both directions, 0 failures in ~10,000 requests). It was a single unreplicated draw from a
> statistic whose own noise band is ±12–18 pp, with no control arm.
> **Therefore the burst-vs-sustained framing and the sustained token curve are both invalid.**
> `CROSSOVER_FINDING.md` is ON HOLD and must not be sent or presented.
> What actually differs between the harnesses is **configuration**, and the live axis is
> **concurrency** — see `CONCURRENCY_CHARACTERIZATION.md`.

**[VERIFIED, 2 independent methods — BURST MODE]** Measured with a fresh task per repetition, the
two services cross over at **200–400 embedded tokens per document**. Below it LlamaIndex wins;
above it RocketRide wins.

| tokens/doc | RocketRide | LlamaIndex | ratio RR/LI |
| ---: | ---: | ---: | ---: |
| ~50 | 477.4/s | 879.1/s | 0.553 — LlamaIndex 1.81× ahead |
| ~100 | 350.2/s | 649.3/s | 0.533 |
| ~200 | 320.1/s | 406.6/s | 0.787 |
| ~400 | 244.2/s | 196.2/s | **1.272 — RocketRide 1.27× ahead** |

Across 50→400 tokens: **RocketRide retains 0.51× of its throughput; LlamaIndex retains 0.22×.**

### Mechanism [VERIFIED]

> **RocketRide is overhead-bound.** It pays a high fixed per-request cost — WebSocket + DAP
> protocol + engine IPC + **4 node hops** — that dominates small documents and amortises as
> documents grow.
>
> **LlamaIndex is compute-bound.** Cheap request path (HTTP + in-process), so throughput tracks
> token count almost directly.

**Embedding cost is linear in TOKENS, not characters and not chunks.** This is the single most
important operational fact in the project.

### Why it matters: mt10k sits ON the seam

| token band | share of mt10k | favours |
| --- | ---: | --- |
| < 200 | 21.4 % | LlamaIndex |
| 200–400 | 38.3 % | crossover zone |
| ≥ 400 | 40.3 % | RocketRide |

mt10k median = **338 embedded tokens**. That is why the real-corpus margin is a modest 13 % rather
than decisive either way — **mt10k is near worst-case for RocketRide.**


## 3b. WEEKEND RUN — launched 2026-08-07 22:42, unattended (read this on Monday)

**Operational detail, phase caps, status command, stop/resume: `publishable/WEEKEND_RUN.md`.**

### The blocker that shaped the design

**RocketRide cannot be containerised on this host.** `server-v3.3.1` ships **darwin-arm64,
linux-x64 and win64 — there is no linux-arm64 asset**, and the repo's Docker workflow targets
`linux/amd64` only. Containerising it here needs x86 emulation, which `DOCKER_ARCHITECTURE.md` §1
forbids because emulation would silently corrupt the numbers. One arm containerised + one native
would be asymmetric, which is worse.

**Decision: both arms run NATIVELY and symmetrically.** The memory ceiling is therefore a **soft**
limit enforced by the worker, not a cgroup — it detects a breach, it does not prove the process
would have been killed. Disclose that with any result. The LlamaIndex container demo remains a
separate delivered artifact.

**If a container comparison is ever required, the options are:** (a) obtain/produce a linux-arm64
engine build, (b) run both arms under x86 emulation so at least the emulation is symmetric —
slow and still not production-representative, or (c) move to a linux-x64 host, where the shipped
linux-x64 build runs natively. **(c) is the only one that yields production-meaningful numbers.**

### Runner design

* `weekend_runner.sh` — phase orchestrator, hard wall-clock cap per phase, advances on expiry.
  `set -uo pipefail` **without `-e`**: a failing phase must advance, not abort the weekend.
* `weekend_worker.py` — one phase/arm, **continuous processing, not rungs** (rungs reprocess
  0..N repeatedly and waste hours), checkpoint every 100 docs, heartbeat every 60 s before *and*
  after each document, goodput asserted per document, resume from checkpoint, OOM caught as a
  result with the RSS curve preserved.
* `weekend_summarise.py` — rolls all checkpoints into `publishable/WEEKEND_RESULTS.md`; safe to
  run at any time against a live run.
* Every result goes through `harness.resultio` (unique path, cannot clobber).

### Bugs found and fixed during build — all would have cost the weekend

| bug | consequence if unfixed |
| --- | --- |
| **Fixed `project_id` in the RocketRide arm** | one live task per `project_id` (STATE §9): p0, p3 and p4 would each have died with *"Pipeline is already running"* — **the entire RocketRide arm lost**. Now unique per phase+pid+time |
| **zsh `nomatch` aborted the state-clearing `rm`** | the first launch silently resumed from dry-run checkpoints and "completed" p0 in 33 s. Use `find -delete`, never `rm glob` |
| Heartbeat only fired after a document | a 1,000-page PDF would look frozen for minutes — the exact "slow vs dead" ambiguity the heartbeat exists to remove |
| OOM before the first RSS sample | empty memory curve at precisely the moment the curve matters |
| `timeout` used in the dry run | not present on macOS |

### What to do with the data on Monday

1. `cat status.txt` — is it still running, and which phase?
2. `../.venv/bin/python weekend_summarise.py` — regenerate `publishable/WEEKEND_RESULTS.md`.
3. Compare **peak RSS and RSS slope** between arms. That is the axis A13 does not touch and the
   one leadership asked for. **Do not compare throughput** — invalid on this host.
4. Check fault classes per arm on identical inputs: same corpus, same documents, so a divergence
   in fault classes is a real behavioural difference, not corpus noise.
5. If any phase shows `memory_limit_exceeded`, the breach index, document and full curve are in
   its checkpoint — that is a finding, not a failure.

### Early signal (first minutes, PROVISIONAL — one phase, small n)

p0 insurance, 200 documents each, identical corpus: LlamaIndex completed 200 in ~68 s; RocketRide
peak RSS reached **2,651 MB** by document 100 against LlamaIndex's sub-1 GB working set. Consistent
with the memory *shapes* already established (finding 1m) but **not** a result — n is small, one
run, and the arms were not interleaved.


## 3c. WEEKEND RUN FORENSICS (2026-08-09) — full analysis in `publishable/WEEKEND_FORENSICS.md`

**Denominator first: LlamaIndex processed 10,000 documents; RocketRide processed 267 (2.7 %).**
There is **no RocketRide endurance result** from this run.

| # | finding | label |
| --- | --- | --- |
| W1 | **RocketRide truncates returned `page_content` at the first NUL byte.** Embeddings are computed correctly over the full text (cos = 1.0000 vs LlamaIndex on all 11 chunks); only the returned text is lost. Truncation offset matched the first NUL exactly on 11/11 chunks; clean-ASCII null control byte-identical | **VERIFIED** (3/3 reproduction + mechanism + null control) ⚠️ The `cos = 1.0000 vs LlamaIndex on all 11 chunks` half of this is **WEAKER than it reads**: two chunks agreeing in their first ~512 tokens return 1.0000 regardless of their tails, so that comparison could not have detected a late-chunk divergence. The truncation-offset match (11/11) and the null control are unaffected and carry the finding |
| W2 | The failing document `001_001157.pdf` (index 267, sha256 `5e35cfd7…`) is **not** in the known 1.42 % malformed set — it parses cleanly but yields binary control characters from a broken font encoding | **VERIFIED** |
| W3 | **The engine did not crash or cascade.** The run stopped because our gate is deliberately fatal | **VERIFIED** |
| W4 | LlamaIndex completed 10,000 docs, 9,898 goodput; its 102 faults are pypdf extraction faults in shared pre-arm code, identical for both arms | **VERIFIED** |
| W5 | ~~RocketRide leaks ~1,500 MB / 1,000 docs~~ | **WITHDRAWN** — window mismatch (267 vs 10,000 docs) plus endpoint placement inside a ±500 MB oscillation. Excluding warm-up, BOTH arms show a negative slope, which is not a physical claim |
| W6 | LlamaIndex post-ramp memory ≈ flat: **+14.8 MB/1k** (p2, sequential, 10,000 docs) and **+20.4 MB/1k** (p4, under contention, 8,888 docs). Peak drifts while current plateaus → allocator retention, not runaway accumulation | **VERIFIED** (2 independent windows) |
| W7 | RocketRide resident memory is higher than LlamaIndex on identical work, **both arms native, same session** | **VERIFIED (direction)**; magnitude **PROVISIONAL** at 1.82×–3.19× depending on window/statistic |
| W8 | **The goodput gate cannot detect garbage input.** LlamaIndex embedded 39,803 chars of binary control codes into 11 confident unit-norm vectors and passed every check | **REFUTED** (the gate's claim to verify work is shape-only) |

**Instrument defects found (fix before the next run):** the RocketRide memory sampler matched
processes by **name**, so it counted a five-day-old unrelated engine (104 MB, ~5.8 % of the
median) — match by **PID** instead; no system-wide memory cross-check was recorded, so the tree
walk could not be falsified; and a fatal content gate ended a 16-hour phase at 2.7 % completion.

**The weekend run was native-on-native**, not containerised-vs-native. The containerised ladder in
`DOCKER_DEMO_RESULTS.md` is a separate run and its numbers are not comparable to these.


## 3d. SESSION 14 — NUL bug filed, content blind spot closed, regression suite added

| # | finding | label |
| --- | --- | --- |
| S1 | **NUL truncation reduced to a minimal reproducer**: `send("AAAA\x00BBBB")` returns `"AAAA"`. No PDF involved — the defect is in the text path | **VERIFIED** |
| S2 | **Direction proven OUTBOUND, not inferred**: cos(returned vector, embedding of FULL text) = **1.0000**; vs truncated-text embedding = 0.7698. The engine embeds the full text and loses it only in the response | **VERIFIED** ⚠️ **Cosine has a measured blind spot** — it cannot discriminate content lost beyond ~2,000–2,500 chars into a chunk (measured 2026-08-12; embedder truncates at 512 tokens, credit Leela §4.10). **S2 stands**: every measured NUL offset (max 2,174) falls inside the discriminating window, which is why 1.0000 vs 0.7698 separated the hypotheses at all. Content now verified by chunk hash instead |
| S3 | **Only `0x00` truncates.** All 32 other control chars (`0x01`–`0x1F`, `0x7F`) return intact | **VERIFIED** |
| S4 | Only `page_content` is affected; `embedding`, `embedding_model`, `metadata`, `type` and all top-level keys are intact. **Untested:** error payloads, non-`response_documents` components | **VERIFIED** (within fields observed) |
| S5 | Always cut at the **first** NUL — leading NUL empties the chunk entirely; trailing NUL loses nothing | **VERIFIED** (6 boundary cases) |
| S6 | **Prevalence 0.30 % [VERIFIED — 2 independent methods]**: offline scan 3 of 991 (Wilson95 0.10–0.89 %); live pipeline detection 8 of 2,200 = 0.36 %, inside that CI ≈ **30 documents in 10,000**. Loss per affected document is severe and unpredictable: one document with a *clean-looking* printable ratio of 0.992 loses **98.9 %** of its text | **VERIFIED** (seeded random sample) |
| S7 | **A printable-ratio heuristic CANNOT detect the NUL bug.** Two of the three NUL documents (0.9923, 0.9884) sit inside the legitimate range (10 lowest legit: 0.9757–0.9944). Two independent checks are required | **VERIFIED** |
| S8 | **Content-sanity threshold derived from the corpus, not chosen**: legit p1 = 0.9944, 2nd-lowest = 0.9757; known garbage = 0.700 and 0.679. Threshold **0.90** sits in the empty band. Catches document 267 (`garbage_and_nul`); **0/40 legitimate documents flagged** | **VERIFIED** |
| S9 | **Reclassification of LlamaIndex's 9,898 "goodput" documents: ~30 (0.30 %, CI 10–88) would fail content sanity.** They did real embedding work, so throughput/memory are unaffected — what changes is what "goodput" means for retrieval quality | **PROVISIONAL** (sample-based extrapolation) |
| S10 | **p0-vs-p3 RocketRide peak discrepancy explained**: post-ramp oscillation amplitude is 1,180 MB (p0) / 1,033 MB (p3), *larger* than the 798 MB peak difference. Both ran the identical first 200 documents yet medians differ by 713 MB — **RocketRide memory is not reproducible run-to-run to better than ~700 MB** | **VERIFIED** |

**Regression suite added**: `working/scripts/regression_selftest.py` — **8 tests, one per defect
that produced a wrong number**: NUL truncation (xfail, open upstream), engine-by-PID-not-name,
non-fatal gate, slope window guard, content sanity, resultio collision, goodput shape checks,
and a `setsid` guard. 7 pass, 1 xfail, exit 0.

**`setsid` recurrence:** the endurance launch used `nohup setsid …` again and died instantly
(`setsid: No such file or directory` — it does not exist on macOS). Caught in 60 s this time by
verifying the PID rather than assuming. Now covered by a regression test.

**Filed:** `publishable/BUG_NUL_TRUNCATION.md` — filing-ready, with reproducer, scope, boundaries,
direction proof, prevalence, version/build identity, and answers to maintainer objections.


## 3e. SESSION 15 — oscillation mechanism, and the meeting artifact

| # | finding | label |
| --- | --- | --- |
| M1 | **Sawtooth is NOT process spawn/exit.** Sampled the engine tree at 0.5 s for 120 s during a live run: process count **constant at 2**, one child PID throughout, while tree RSS still swung **488 MB**. The architectural explanation that would have exonerated the engine is refuted | **VERIFIED** |
| M2 | **Sawtooth is NOT document-size variance.** RocketRide corr(document size in flight, RSS) = **−0.14** (none). LlamaIndex has a *stronger* size correlation (−0.52) yet oscillates far less on the **identical** documents in the **identical** order | **VERIFIED** |
| M3 | Oscillation mechanism itself | **UNVERIFIED** — both leading candidates eliminated; remaining candidate is allocator behaviour inside the engine's task process, not inspectable from outside |
| M4 | **Operational statement (not a stability verdict): size containers to PEAK, not median.** RocketRide peak/median **1.76×**, LlamaIndex **1.16×** — sizing to the median undersizes RocketRide by 76 % vs 16 % | **VERIFIED** |
| M5 | **42 % run-to-run spread on byte-identical input** (medians 2,397 / 1,639 / 1,811 MB over the same first 200 docs). NOT the sawtooth: divergence is present in the **first** post-warm-up sample (2,631 vs 1,949 vs 1,951), so it is set at task creation, not accumulated. Same engine PID served all three, so not a fresh-engine effect | **cause UNVERIFIED** |
| M6 | **No `linux-arm64` build has EVER been published.** All **51 releases** examined: win64 36, darwin-arm64 24, linux-x64 24, linux-arm64 **0**. Strengthens the platform verdict from "this release lacks it" to "the project has never shipped one" | **VERIFIED** |
| M7 | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md)** — Memory ratio **2.08×** median-to-median (matched windows) vs **3.0×** peak-to-peak. Different statistics, both real: 2.08× is consumption, 3.0× is what must be provisioned | **VERIFIED (direction)**, magnitude **PROVISIONAL** |

**Meeting artifact: `publishable/MEETING_2026-08-10.md`** — platform verdict, what was measured,
three product findings, memory, what is not established, and the phased roadmap. Verified clean:
zero withdrawn figures, zero broken file references, no future dates.


## 3f. SESSION 16 — matched replication (complete)

| # | finding | label |
| --- | --- | --- |
| R1 | **Goodput and faults are perfectly reproducible under a matched configuration.** 3 blocks x 2,000 docs, identical every block: LlamaIndex 1,972 goodput / 28 faults, RocketRide 1,965 / 35. Difference is **exactly 7 documents per 2,000 (0.35 %)** — the NUL truncation — and nothing else | **VERIFIED** (3/3 identical) |
| R2 | **Matched memory ratio 2.60x [1.96, 2.69] — DIRECTION ONLY.** RocketRide fails the 10 % gate at **24.0 % spread**; LlamaIndex passes at 4.3 % | **direction VERIFIED, point estimate NOT REPORTABLE** |
| R3 | ~~RocketRide memory rose +32 % across three identical blocks, monotonic~~ | **WITHDRAWN (session 17)** — three further blocks on the same engine gave 2,055 / 2,070 / 2,112. Four of six cluster at 2,055–2,112 (2.7 % spread); blocks 2–3 were a transient excursion that fully reverted. Three points caught the rising half |
| R4 | Mechanism of the **excursion** (not growth) | **UNVERIFIED** — intermittent, not cumulative. The earlier reasoning was also flawed: teardown RSS is not operating RSS, so "192 MB after teardown" never ruled out parent growth. Now measured properly (S17-2) |
| R5 | **Harness asymmetry favouring LlamaIndex**: it gets a fresh process per block while the engine persists. Correcting for it moves the ratio further AGAINST RocketRide. Two defensible numbers: **fresh-vs-fresh 2.05x**, **long-running 2.5-2.6x** | **VERIFIED** |
| R6 | The **2.05x fresh-vs-fresh** figure independently reproduces the earlier matched-window **2.08x** from a different run and harness | **VERIFIED** (2 methods) |
| R7 | Run cost 14.7 vs 13.5 min/2,000 docs (**1.09x**), against the endurance run's 2.2x. Consistent with most of that gap being configuration, **NOT a throughput finding** — A13 stands | **hypothesis for Phase 2, UNVERIFIED** |
| R8 | **The endurance wall-clock comparison is VOID, not correctable.** The 3.07x pinning cost came from short blocks under different thermal/memory conditions and must not be applied to a 2.47 h continuous run | **VERIFIED (methodological)** |

**New open item A17:** `A3_SERIALIZATION_FINDING.md` says pinning helps above concurrency ~4, from
400/1,600-token synthetic text. With the concurrency-1 cost now measured at **3.07x on real
documents**, the crossover concurrency is **UNVERIFIED for this corpus**. Not re-measured — logged.

**New open item A18:** does RocketRide's +32 %/3-blocks growth continue, plateau, or reset on
engine restart? Blocks the memory magnitude claim. ~40 min.


## 3g. SESSION 17 — leak vs plateau resolved, and a claim of mine withdrawn

| # | finding | label |
| --- | --- | --- |
| S17-1 | **NOT A LEAK.** Six 2,000-doc blocks, same engine, never restarted: 2,065 / 2,674 / 2,717 / **2,055** / 2,070 / 2,112 MB. Block 4 fell 662 MB back to block 1's level. Modal cluster of 4 blocks at **2,055–2,112 (2.7 % spread)**; blocks 2–3 were a transient excursion that reverted | **VERIFIED** (6 blocks) |
| S17-2 | **Component decomposition, sampled separately during each block**: engine parent **flat** (238.7 → 242.5 MB), task tree **declining** (1,568.6 → 1,538.2), **our own driver growing +51.7 MB**. Neither the engine nor its task grows; the only growth is our harness (~2.5 % of RocketRide's total, inflating it) | **VERIFIED** |
| S17-3 | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md)** — **Memory ratio ~2.0×, three independent methods**: matched-window 2.08×, fresh-vs-fresh 2.05×, all-six-block median **2.03×**. The earlier 2.5–2.6× came from the two excursion blocks and is superseded | **direction VERIFIED (3 methods)**, magnitude ~2.0× **PROVISIONAL** (gate fails at 24 % from bimodality, not centre uncertainty) |
| S17-4 | **Goodput identical in all SIX RocketRide blocks** (1,965 every time) and all three LlamaIndex blocks (1,972). The 7-document difference per 2,000 is the NUL truncation, now reproduced 6/6 | **VERIFIED** |
| S17-5 | The 24 % gate failure is **bimodality, not drift** — capacity must cover the excursion, but the service is not degrading over time | **VERIFIED** |
| S17-6 | **CI estimator check**: 2.60× [1.96, 2.69] was ratio-of-medians with a bootstrap interval; correct estimator, but at n=3 the interval is the entire attainable range and the point sat high because the sample was left-skewed. **No central estimate belongs on a trending/bimodal sample** | **VERIFIED (methodological)** |

**A18 retired as originally framed** — restarting the engine between blocks was meant to reset
growth, and there is no growth to reset. Replaced by **A19: what triggers the ~+30 % excursion?**
It is intermittent; catching one with instrumentation running needs many more blocks. Not run.

**Artifact restructured** to lead §2 with functional equivalence (identical goodput and fault
counts, arms differing by exactly 7 documents per 2,000 — all NUL truncation), memory demoted to
the secondary result.


## 3h. SESSION 18 — A19 tested and refuted; an accounting trap avoided

| # | finding | label |
| --- | --- | --- |
| S18-1 | **The excursion is NOT caused by a neighbouring LlamaIndex block.** Retrospective correlation was 6/6 (excursion in exactly the 2 RocketRide blocks following a LlamaIndex block, none of the 4 others) but confounded by session and time. Controlled RO→LL→RO test: 1,826.0 → 1,819.6 MB, **−0.4 %** | **REFUTED** (direct test) |
| S18-2 | Host-level memory sampling (used / available / swap) added to the harness. The excursion window showed nothing distinguishing; A19 is now **instrumented but not yet triggered** | **VERIFIED** (instrument added) |
| S18-3 | ⚠️ **See MATCHED_LAYERS.md** — **Excluding our driver from RocketRide's total is ASYMMETRIC and must not be done.** It moves the ratio 2.01× → 1.74×, but LlamaIndex's single-process figure already contains the same harness work and cannot have it subtracted. Symmetric: count-on-both **2.01×**, exclude-from-both **~2.47×**. As-measured **2.01×** stands and is conservative | **VERIFIED (methodological)** |
| S18-4 | Goodput reproduced again: RocketRide **1,965** in blocks 7 and 9, LlamaIndex **1,972** in block 8 — now **8/8** and **4/4** respectively | **VERIFIED** |

**Regression test #10 added**: asserts the meeting artifact's protected content (thread-asymmetry
table, "disadvantageous configuration", the VOID marking, the functional-equivalence lead, the
no-reversal caveat, the withdrawn-leak marker) is present, and that withdrawn figures never appear
without a withdrawal marker nearby. An edit destroyed this content twice; it is now structural.

## 3f. SESSION 19 — the arms did not run the same shape [VERIFIED]

**`publishable/MATCHED_LAYERS.md` is the full analysis.** Read it before quoting any memory or
wall-clock number.

| # | finding | label |
| --- | --- | --- |
| T1 | **LlamaIndex ran in-process; RocketRide ran client–server.** `weekend_worker.py:148` imports `LlamaIndexPipeline` and calls `self.p.process(text)` — no socket. `RocketArm` uses `RocketRideClient` over **WebSocket + DAP** to `:5565`. `matched_replication.py` and `docker/ladder.py` start uvicorn **zero** times. `working/ws1/service.py` was **never used** in any published run | **VERIFIED** (code + live process measurement) |
| T2 | **Process topology 1 vs 3.** Live, engine `pid=38379`, 0.25 s sampling: RocketRide = driver + engine parent + **1** task child; LlamaIndex = 1 process, model loaded into the driver (RSS 22.9 → 560.0 MB across `warm()`). Independently reproduces M1 | **VERIFIED** (2 methods) |
| T3 | **RocketRide carries a ~240 MB engine parent with no counterpart** in the other arm — 23 % of LlamaIndex's entire footprint — plus two extra interpreter baselines | **VERIFIED** (six-block decomposition, blocks 4–6) |
| T4 | **The repo already published both directions and never reconciled them.** In-process LlamaIndex → RocketRide 2.0× worse. Uvicorn LlamaIndex at 8 workers → LlamaIndex **22.8× worse at idle** (4,642 vs 204 MB). Same two systems, opposite verdicts; the only variable is the LlamaIndex arm's topology. **Neither ratio is a framework property** | **VERIFIED** |
| T5 | Transport cost ~+36 ms/document (n=4, spread 36–41 %, **fails the 10 % gate**). Over 2,000 docs that is the same order as the entire observed +72.7 s block gap — but transport cost and genuine per-document cost are **not separated** | **PROVISIONAL — direction only** |
| T6 | `run_service.sh` defaults to **14** workers while the published 4,642 MB was taken at **8** — declared ≠ measured, and it moves the headline with a shell variable | **VERIFIED** |
| T7 | **Functional equivalence is UNAFFECTED.** Goodput, fault classes and the NUL defect are properties of the bytes returned, not the transport. Both arms returned identical goodput every block *through different topologies* | **VERIFIED** |

**Direction of bias:** the asymmetry biases **against RocketRide** on memory and wall clock. Hunted
for mechanisms by which it instead flatters RocketRide (MATCHED_LAYERS.md §2.4); the strongest —
"its task tree holds more models" — is **refuted**: the tree is one process holding one model, so a
matched re-run will shrink the gap, not erase it.

### Platform addendum — 2026-08-11

| # | finding | label |
| --- | --- | --- |
| P1 | **The first block of a run is warm-up at BLOCK scale** — 12–38 % slower than the blocks that follow, on **both** arms (LlamaIndex-HTTP 892.9 → 794.4 → 796.3 s; RocketRide 1,119.9 → 819.8 → 805.3 s; identical goodput and faults throughout). Excluding it, wall-clock spread is **0.24 %** and **1.79 %** — the tightest in this project. Including it, both arms FAIL the 10 % gate (12.4 %, 38.4 %). The existing 50-document warm-up does not cover this. **Wall clock IS quotable here with a block-level exclusion.** This entry has been revised three times: first claimed 'nothing changed' (wrong — block position did), then '12–37 % run-to-run instability, gate unmeetable' (wrong — one contaminated point, too pessimistic). Does not affect the 2.2× sweep-order result; throughput remains unpublishable from this host | **PROVISIONAL** — n=2 after exclusion, below the project's own n≥3; adjacent blocks are the pair most likely to agree, so a thermal steady state is not excluded. Memory does not depend on it (passes at n=3) |

### Matched-layer sweep — 2026-08-11 (pre-registered)

Prediction registered in `PREREGISTRATION.md` **before** the sweep ran; `MATCHED_LAYERS.md` §5b–5c
carries the full analysis.

| # | finding | label |
| --- | --- | --- |
| S1 | **Memory crossover at C ≈ 3.2.** Matched at equal in-flight documents: C=1 → 1.95×, C=2 → 1.36×, C=4 → 0.86× (RR/LI). Below C≈3 RocketRide is heavier, above it LlamaIndex is. Both bracketing levels pass their gates and are compression-clean | **VERIFIED** (n=3/level, randomised level order, achieved concurrency measured) |
| S2 | **The registered flatness prediction is FALSIFIED.** RocketRide task-tree memory grows **1,598 → 3,469 MB (+117 %)** from C=1 to C=16. Fitted memory ∝ C^k: RocketRide **k=0.20**, LlamaIndex **k=0.80**. The crossover is real but happens because LlamaIndex grows *faster*, not because RocketRide is flat | **VERIFIED** |
| S3 | **Pooling confirmed structurally**: RocketRide task **process count constant at 1** from C=1 to C=16 with up to 16 documents genuinely in flight. Model B's claim transfers from `probe_minimal.pipe` to the real embedding pipeline — but it is not free (see S2) | **VERIFIED** |
| S4 | **C=16 is unquotable — compressor, not swap.** Compressed pages +66.2 % (+5.50 GB) in one cell; swapouts zero, so a swap-only gate passes it. Tell: LlamaIndex per-process RSS fell **below its own idle value** (453 vs 540 MB/proc), which is physically impossible for a loaded worker. **LlamaIndex at 16 workers does not fit this host** | **VERIFIED** |
| S5 | **LlamaIndex memory drifts upward across successive workloads at C=8**: 6,432 → 6,589 → 7,584 MB (+18 %) against one warm service, compression flat (−0.05 to −0.34 %), so it is real growth. Fails the 10 % gate at 17.5 % | **PROVISIONAL** — n=3 within one service instance; allocator high-water vs unbounded growth not separated |
| S6 | **The 22.8× idle figure is NOT a point on the matched curve at any C.** It compared LlamaIndex idle at 8 workers (8 models eagerly pre-loaded) against RocketRide idle (engine parent, **no task, no model**). It measures **eager vs lazy model residency**, not memory efficiency. Correct answer to "what does an idle deployment cost"; not an answer to "which framework uses less memory" | **VERIFIED** |
| S7 | RocketRide passes its variance gate at **every** concurrency level (3.6–7.2 %); LlamaIndex fails at C=8 and C=16 | **VERIFIED** |
| S8 | **RocketRide task creation hung in `INITIALIZING` for 300 s** after ~14 create/terminate cycles on a 31.8 h engine. No orphans, engine responsive at 188 MB, and a manual probe then created a task in 6.8 s — transient, not degradation. Retry produced a ratio within 1 % of the other reps | **PROVISIONAL** (observed once) |

### Adopted from Leela's benchmark, and deferred items — 2026-08-12

| # | item | status |
| --- | --- | --- |
| L1 | **Chunk-hash content gate** (`harness/chunk_hash.py`) — hash returned chunk text against a reference computed **outside both frameworks**, rather than checking vector shape. Approach from her `pdf1k/ground_truth.py`. Demonstrated: on a NUL-bearing document the vector-shape gate **passes** while the chunk-hash gate **fails** with the exact offset. Both arms verified chunk-identical to the reference, 12/12 documents | **ADOPTED** — regression test `chunk_hash_gate` |
| L2 | **512-token embedder truncation** (her CONTEXT_SNAPSHOT §4.10). Independently measured here: cosine stops discriminating past **~2,000–2,500 chars / 500–625 tokens** (cos 0.9378 at 2,000 → 1.0000 at 2,500). Every cosine claim in this repo re-examined; see S2 and W1 | **ADOPTED as a documented limit** (2 methods: her finding + our measurement) |
| L3 | **`text + '\n'` canonical transform** — her Stage 0/1 finding, already in `ws1/pipeline.py` | previously adopted |
| L4 | **cgroup-scoped memory accounting** — she sums RSS over all processes in the container cgroup, with per-process breakdown, and keeps the client out of the arm total. Cleaner boundary than our engine-tree + driver sum, which folds our driver into RocketRide's total (~250–320 MB inflation, disclosed) | **DEFERRED to Phase 2, deliberately.** Switching now would make every historical figure in this repo incomparable with its own successor. Phase 2 runs on Linux with real cgroups v2, where this becomes both natural and enforceable — adopt it at that boundary, not before. **Open item.** |
| L5 | Ground-truth **reference embedding vectors** for a fixed sample (her `sample_vectors.json`) — drift detection across engine versions | **not adopted** — lower value for us than L1 given L2; logged for Phase 2 |

### SCOPE CHANGE — Parser IN (2026-08-12)

**Team decision, taken with eyes open.** PDF extraction moves inside each framework: the engine uses
its stock `parse` node (Tika 3.2.3), the LlamaIndex service uses pypdf in-worker. This is **Tier 2
(product comparison)** from `PARSER_DECISION.md`, chosen over the **Tier 1 (framework comparison)**
we had been running. Shashi and Leela are doing the same.

| # | consequence | label |
| --- | --- | --- |
| PI1 | **Every existing number was measured parser-out and needs re-baselining.** Memory crossover C≈3.2, the C-sweep, matched-layer 1.80×, the endurance runs. Not withdrawn — they are a valid Tier 1 result — but they are a different question and must never share a table with a Parser IN number | **superseded in scope, not in validity** |
| PI2 | **Goodput and fault counts now include parser behaviour.** They are not comparable with the parser-out counts | **VERIFIED** (by construction) |
| PI3 | **The chunk-hash gate had to be split.** One shared reference across two parsers would fire on every document with no defect present. Now: per-arm hash (hard gate, against that arm's own extracted text) + cross-arm fidelity (reported metric, not gated). Both directions asserted in regression test `parser_in_gate_split` | **VERIFIED** |
| PI4 | **Cross-arm extraction fidelity, first measurement on real documents from our side** (n=12): char ratio median **1.0068** (p10 0.9898, p90 1.0435) — agrees with Leela's 0.994 on 140 PDFs. Word jaccard median **0.9899**; seq similarity median **0.9567**, min **0.3838**. Of 12 documents: 5 agree, **5 are same-words-different-order** (Tika vs pypdf disagree on multi-column/table reading order), 1 where Tika extracted materially more, 1 differing in content | **PROVISIONAL** (n=12, one host) |
| PI5 | **The engine does not reject non-PDF input** — sent 47 bytes of plain ASCII with `mimetype=application/pdf`, it returned **1 successful chunk** rather than a fault. The LlamaIndex arm returns `parse_failed`. A misidentified file is a silent success on one arm and a typed fault on the other | **PROVISIONAL** (single probe) |
| PI6 | **Fault taxonomies are asymmetric.** LlamaIndex returns typed classes (`parse_failed`, `empty_extraction`, `malformed_input`); RocketRide signals failure by returning an **empty document list**, with no class. Fault-class comparisons between arms are not like-for-like | **VERIFIED** (4 probe cases) |

### Three-way cross-team recon — 2026-08-13

`publishable/THREE_WAY_COMPARISON.md` is the full table. Shashi's repo: `35ad350` (2026-08-11).

| # | finding | label |
| --- | --- | --- |
| T3-1 | **Engine version is settled by majority: Leela and Shashi are BOTH on `server-v3.2.1`; we are alone on `3.3.1`.** We move. Everything re-baselines anyway | **VERIFIED** (both Dockerfiles + Shashi's benchmark script pin the 3.2.1 linux-x64 tarball) |
| T3-2 | **All three run an SDK the engine manifest does not bundle, and three different ones**: ours 1.3.0/3.3.1 (paired), Leela 1.3.0/3.2.1 (3.2.1 bundles 1.1.1), Shashi 1.2.0/3.2.1 (1.2.0 pairs with 3.2.2) | **VERIFIED** |
| T3-3 | **The dropped-splitter-kwargs defect was found independently by all three teams**, three harnesses, two engine versions. Shashi's response is the best of the three: he reads chunk lengths back out of Qdrant after a probe ingest and reconfigures his framework arm to match *actual* engine behaviour, printing `engine chunk-size config is INERT (known bug)`. All three arms converge on **4000/200** from three different declared configs | **VERIFIED** (3 independent discoveries) |
| T3-4 | **Shashi's pipeline terminates in `qdrant`, not `response_documents`**, and he benchmarks ingest **+ a full RAG query phase** (chat → embedding → qdrant → llm_ollama → response_answers, Ollama llama3.2:1b). Different work is measured; his numbers are not ingestion-comparable with ours or Leela's | **VERIFIED** |
| T3-5 | **Three thread configurations AND three mechanisms**: ours unpinned-measured-10 (env, read back in-process), Leela env-pinned-1, Shashi SDK-pinned-8 via `use(threads=8)`. Whether `use(threads=)` and `OMP_NUM_THREADS` control the same pool is **UNVERIFIED** — our in-process read-back is the only instrument among the three that could settle it | **BLOCKING, mechanism UNVERIFIED** |
| T3-6 | **Three incompatible memory boundaries**: ours engine-tree+driver, Leela's container cgroup, Shashi's `getrusage(RUSAGE_SELF)` — driver only, which does not capture engine-side work at all | **VERIFIED** |
| T3-7 | **We are the weakest of the three on provenance**: no per-file corpus sha256 manifest (both of them have one) and no engine-binary hash (Shashi records one). We also carry 6 custom nodes and a hand-copied pypdf where both of them carry zero | **VERIFIED** |
| T3-8 | **Unresolved conflict for our refactor:** no `text + '\n'` transform found in Shashi's Haystack arm, which uses `DocumentSplitter(split_by="character")` rather than a LangChain splitter. Leela established the engine appends exactly one newline. Needs a direct check before any joint run | **UNVERIFIED — flagged, not assumed** |

### SESSION 35 — why our numbers differ from the teammates': it is scale (2026-08-16)

Analysis only; nothing in the measurement path changed. Peer repos re-cloned into
`reference-latest/`; **both had moved that day**:

| repo | branch | was | **now** | that day's commit |
|---|---|---|---|---|
| Leela | `aws-bench` | `2cc0cca` | **`6f7ce2e`** | corpus: OFFSET for a disjoint document set; warm-up docs never measured |
| Shashi | `benchmark/shared-pipe-engine-3.3.1` | `c8b4b2b` | **`ce15326`** | Support alternative pinned corpora: SEED_MANIFEST + SEED_N + 500-seed builder |

**The question.** Leela's RocketRide blast reports 0.68–0.74 docs/s on 200 documents (~285 s);
ours reports 4.03 on 10,000 (~2,470 s). Our own 200-doc blast was 0.52–0.67 — agreeing with his,
not with our own 10k.

#### The answer: a 200-document throughput number is structurally biased LOW

**Corpus is not the cause.** Our first 200 documents average **616.4 KB** against **616.2 KB**
for all 10,000, and are *lighter* by pages (22.9 vs 29.6 mean). Heavier documents would have made
the small run slower; they are not heavier.

**The obvious ramp test is invalid and was discarded.** Slicing a run into deciles by COMPLETION
RANK always shows a decaying rate, because completion rank sorts documents by duration — the fast
ones finish first by construction. That profile measures the size distribution, not the engine.

**The mechanism is heavy tail × finite wave count.** Throughput is `(n − warm) / span`, and
`span` ends when the *last* document finishes. Measured on our own blast records, **the slowest
1 % of documents carry 58.6 % of all service seconds** (mean 3.261 s, median 0.203 s). At n=200
with C=32 there are only ~6 waves, so the span is governed by the slowest document in each wave —
a **maximum**. At n=10,000 there are ~312 waves and it converges to `C / mean`.

Replaying ONE measured service-time distribution through a C-server FIFO queue
(`working/scripts/throughput_ramp.py`):

| C | n | waves | sim docs/s | ratio vs n=200 |
|---|---|---|---|---|
| 4 | 200 | 50 | 0.683 | 1.00× |
| 4 | 10000 | 2500 | 1.177 | 1.72× |
| 8 | 200 | 25 | 0.761 | 1.00× |
| 8 | 10000 | 1250 | 2.290 | 3.01× |
| 32 | 200 | 6 | 0.850 | 1.00× |
| 32 | 10000 | 312 | 8.026 | **9.44×** |

Simulated n=200 at C=32 is **0.850 docs/s** against Leela's observed 0.68–0.74 and our 0.52–0.67.
The predicted 200→10k ratio at C=32 is 9.4×; observed is 4.03/0.6 ≈ 6.7×. Same direction, same
order, and the effect **grows with C exactly as the wave argument requires** — a prediction the
simulation made before it was checked against the box numbers. **VERIFIED** (simulation +
independent agreement with two separately-measured small-n figures).

> **RULE FOR THE THREE-WAY TABLE: 200-document and 10,000-document throughput figures must never
> share a row, in either direction.** Given the tail weight, 200 is too few for a stable figure
> whoever runs it — our n=200 simulation spread was ±0.413 on a 0.683 mean, roughly ±60 %. This
> needs raising with the group **before** the table is built.

#### effective_cores: my `use(threads=)` concern was WRONG

I flagged that we pass nothing to `use()` while Shashi passes `threads=8`, and reasoned from
Leela's comment ("~5.8–5.9 effective cores… the limiter is the engine's pool") that our
RocketRide arm was running at a fifth of our LlamaIndex arm's parallelism.

**Measured on the box, that is refuted: RocketRide 23.05 effective cores, LlamaIndex 30.51.**

RocketRide lands next to Shashi's `threads=<host cores>` figure of 24.28, not near Leela's 5.8.
**Leela's 5.8 is the outlier, not ours** — his arm is confined to a 24-core cpuset and drives the
engine through one batched `send_files`, so his number describes his configuration, not an engine
default. The engine's default pool is not inherently ~6-way, and no `use(threads=)` change is
warranted here. The residual RR-vs-LI gap is **1.32×**, worth noting and nothing like 5×.

*Register note: I reasoned from a teammate's measurement of a different configuration to a claim
about ours, and stated it as the headline concern. Ours was measurable from a record already on
disk. Measure our own instrument before importing someone else's number as a finding about it.*

#### Four envelope gaps where we differ from BOTH of them

| | us | Leela | Shashi |
|---|---|---|---|
| CPU allocation | `--cpus 32` — CFS **quota**, whole box | **cpuset 0-23**, arm gets 24 cores | **cpuset**, identical for both services |
| client / driver | **on the host, unpinned**, sharing the arm's cores | own container, **cpuset 24-31** | own container |
| memory | **`--memory 58g` hard cap** | **uncapped**, measured ("a 10 g cap would have OOM-killed RocketRide, peak 10,536 MB") | **uncapped** |
| per-request deadline | 300 s | 3600 s, **one deadline both arms** | per-phase budget |

Leela pins the measuring client onto separate cores so it "can never steal from the arm it is
measuring". Ours competes with the container under test on the same 32 cores — with 32 uvicorn
workers plus a 32-thread driver that is oversubscription, and it is not symmetric between arms.
All four are **UNQUANTIFIED**: named, not measured.

#### What is genuinely aligned, and what differs in definition

**Aligned:** all three pipelines are `webhook → parse → preprocessor_langchain →
embedding_transformer → response_documents`, parsing inside the framework; all three now run
correctness gates **post-loop** (that was our defect #19, not theirs); all three on GovDocs1; all
three cgroup-based on memory. `pipelineTraceLevel` was checked and is a non-difference — the SDK
captures a trace only when set, and Leela's probe found `_trace` never materialises anyway.

**Differs by definition:**

| | blast implementation | per-doc timestamps | warm-up |
|---|---|---|---|
| Leela | ONE `send_files(200 files)`; engine holds the backlog | **derived** from the engine's `upload_time`, self-labelled `timing_source: "batch_upload_time (derived, not measured)"` | 25 **disjoint** docs, excluded, timed separately |
| Shashi | ONE `send_files(files)` | none in blast; `wall_s` only | `max(4, 2×threads)`, excluded |
| us | N individual `send()` with a client semaphore of C | client-observed | metric-side: drop the first 64 **completions of the measured corpus** |

His per-document figure is the engine's self-reported processing time; ours is a client-observed
round trip including transport. Our warm-up drops the 64 *fastest* documents rather than the
first 64 submitted, and they are measured-corpus documents rather than disjoint ones — his
policy is the better of the two.

Also worth carrying forward: Leela records **372–399 threads alive** at a client concurrency of
8–11, corroborating that the box's "307–321 PIDs" is a **thread** count (defect #31).

**Could not fetch his S3 exports** — no `aws` CLI or `boto3` on the laptop. Everything above is
from committed peer code plus our own per-document records. His records would settle per-document
service time directly; his code was enough to establish what those records mean.

### SESSION 34 — defects #29 and #30, found in the 10k blast output (2026-08-16)

The 10k blast leg completed. Two defects in its own report, both caught by a reader doing
arithmetic across two lines of the same page. Sequential was still running on the box and was
not touched; **nothing in this session's diagnosis required the box.**

#### #29 — the two arms started the latency clock at different points

The report said:

| arm | blast p50 | blast p95 | docs/s |
|---|---|---|---|
| llamaindex | 2.05 s | 17.6 s | 6.40 |
| rocketride | **1120 s** | **2150 s** | 4.03 |

RocketRide's p95 was 87 % of the whole 2,481 s leg, which is the signature of every document
being stamped as submitted at *t*=0.

**Concurrency was matched; the clock was not.** `SMOKE_BLAST_C` bounds in-flight work on both
arms — `cf.ThreadPoolExecutor(max_workers=BLAST_C)` on LlamaIndex, `asyncio.Semaphore(BLAST_C)`
on RocketRide. But LlamaIndex stamped `submit_ns` **inside** the pool worker, which runs only
once a thread is free (admission), while RocketRide stamped it **before** `async with sem`. As
`asyncio.gather` starts every coroutine in the loop's first pass, all N documents were stamped
within milliseconds of batch open, and each one carried the full client-side queue wait as
"latency".

**Measured, not inferred** — submit-stamp spread as a fraction of leg duration, two local
200-doc runs:

| run | arm | n | leg | submit spread | % of leg |
|---|---|---|---|---|---|
| `…044726Z` | llamaindex | 200 | 66.6 s | 64.97 s | **97.6 %** |
| `…044726Z` | rocketride | 200 | 319.1 s | 0.001 s | **0.0 %** |
| `…051154Z` | llamaindex | 200 | 68.9 s | 67.25 s | **97.5 %** |
| `…051154Z` | rocketride | 200 | 319.4 s | 0.001 s | **0.0 %** |

Four more runs at n=5/6 show the same direction. **Direction of bias: against RocketRide**, by
roughly 550× at 10k.

**Throughput is untouched, verified by null control.** At `warm_n>0` the throughput window spans
*completion to completion* and never reads `submit_ns`. Forcing either stamping convention onto
either arm leaves `docs_per_s` bit-identical (3.0662 → 3.0662, 0.4491 → 0.4491) on both local
runs. **The blast throughput comparison in the 10k report stands as published.**

**The fix keeps both definitions.** Both arms now record `enqueue_ns` *and* `admit_ns`, with
`submit_ns == admit_ns`, so service latency and Leela's batch-position latency come out of one
set of records and the choice never costs another run. The old label was also wrong for both
arms: a bounded client pool is not open-loop, and blast is now reported as `closed-loop` with
`client_concurrency` beside it, plus a separate `blast_batchpos` row carrying Leela's
definition.

**Salvage without re-running:** `working/scripts/blast_latency_salvage.py`. A bounded pool of C
is a FIFO queue, so `admit[k] = completion_sorted[k−C]` for `k ≥ C`. Gated on a null control
that reconstructs the arm which *already* recorded real admission stamps — it must reproduce
them or the script reports nothing. On `…051154Z` it reproduced LlamaIndex's recorded p50/p90/
p95/p99 to **worst error 0.014 %**. Applied to RocketRide it turns p50 36.11 s → **0.148 s** and
p95 88.95 s → **9.33 s** (PROVISIONAL — a model, superseded by any post-fix run).

#### #30 — the memory table and the metrics line described different legs

`peakRSS=84960.6MB` on one line; `summed RSS 1,513.8 · cgroup anon 1,025.4 · 1.48×` on another.
84,960/1,025 is 83×, not 1.48×.

**Both figures were right for what they measured and were never the same measurement.**
`mem_sources` was populated only inside the sequential leg and keyed on the arm alone, so the
table always described a 1–2 process tree, while the metrics line beside it carried a *blast*
peak from a tree of `BLAST_C`-plus processes. The over-count scales with the number of processes
sharing pages, so the sequential leg's 1.48× sharing factor is meaningless applied to a blast
peak — a point `memory_sources.py`'s own docstring already made, which the report then violated
by printing them adjacent.

**Why 85 GB survived a 58 GB cap:** the cgroup charges a shared page **once**, however many
processes map it; summed RSS charges it once **per** process. A footprint that size would have
been OOM-killed. **The number surviving is the proof that it is not a footprint** — now an
automatic check (`summed_rss_exceeds_cgroup_limit`), since it costs one comparison.

> **CORRECTION (same session).** I attributed the 84,960.6 MB to LlamaIndex by inferring
> 84,960/33 uvicorn workers = 2,574 MB per process. **Wrong, and wrong in the direction that
> flattered us.** From the record: **llamaindex blast 36,427.1 MB, rocketride blast 84,960.6 MB.**
> The inference was per-process arithmetic run backwards — it assumed the arm with more known
> processes owned the larger sum, when the sum is what identifies the fan-out, not the reverse.
> The lesson for the register: *a plausible mechanism is not evidence of which side it happened
> on.* I had the record's location and did not fetch it (no `aws`/`boto3` on the laptop) and
> should have marked the attribution UNKNOWN rather than naming a most-likely arm.

**This inverts the memory headline.** At 200-doc sequential, RocketRide was 3.0 GB anon against
LlamaIndex 20.8 GB. At 10k blast the *summed* ordering reverses. RocketRide blast summed RSS was
**9,209 MB at 200 docs and 84,960 MB at 10k under the same C=32** — concurrency held constant
while the figure moved 9.2×, so the fan-out is not explained by concurrency alone.

**There is NO valid cgroup figure for either 10k blast leg.** The table's `rocketride 1,025.4
anon / 2 procs` is a post-leg point sample taken after the engine released its task processes —
see defect #31.

Fixed: memory captured per arm **per leg**, sharing factor scoped to its own leg, the three
cgroup columns labelled for what they are (this-leg peak / **point sample** / all-leg HWM), and
the metrics-line field renamed `peak_summed_process_rss_mb` so it cannot be lifted out and read
as a footprint.

New tests, both passing: `test_blast_symmetry.py` (both concurrency patterns against one
synthetic service, plus a deliberately reintroduced bug the control is required to catch) and
`test_memory_sources.py`. All five suites pass. Pushed as `79ad702`.

#### #31 — cgroup anon was read once, AFTER the leg, and printed in a column headed "peak"

`capture_memory` called `memory_report()` after the span closed, so `anon` and `current` were
point samples of a container that had already released whatever the leg was holding. Only
`memory.peak` was a real high-water mark, and it is cumulative over the container's lifetime, so
it spans every leg. Three different kinds of number, three adjacent columns, one heading.

**Minimum fix, and why it is where it is.** anon has no kernel HWM (`memory.peak` tracks
`memory.current`, which includes page cache), so an anon peak must be sampled. It is now sampled
**on the collector's existing 0.5 s process tick** — `collector.py::_sample_cgroup` resolves the
container's cgroup once from any tracked pid and reads `memory.stat anon`, `memory.current` and
`pids.current` on every tick, tracking peaks in `RoleAggregate`. No new thread, no new file, no
new argument, and one clock: `cost_window()` already slices the tick stream to the throughput
window, so anon gets the same treatment as CPU and RSS. Fields reach the report through
`summary()` as `peak_cgroup_anon_mb` / `peak_cgroup_current_mb` / `peak_cgroup_tasks`.

**`pids.current` counts TASKS, not processes.** The box's reported 307–321 "PIDs" is very likely
threads: the local macOS RocketRide blast leg reached **290 threads in 2 processes** at C=4. The
report now prints `procs` and `tasks` in separate columns with `tasks_per_process_at_peak`, so
the two can never be read as the same quantity again.

Also new: `working/scripts/analyze_sampler.py` — reads the sampler streams already on disk and
separates *bounded-by-concurrency* from *grows-with-documents* from *per-process leak*, using
the second-half slope so a model load is not reported as a leak.

### SESSION 33 — defect #28: the fetcher counted its own arithmetic; peer-scale recon (2026-08-16)

**BLOCKER, found on the box.** `verify_corpus_manifest.py` FULL reported 9,800/10,000 with 200
missing from zip 040, while `fetch_govdocs.py 10000` had printed `DONE total_pdfs=10000`.

**The divergence, exactly.** The manifest defines **248** files from zip 040 (10,000 across zips
000–040). The fetcher took **48** — short by exactly 200, the number already on disk from the
earlier `fetch_govdocs.py 200`. Cause: `have` was seeded from the disk once, then advanced by
`have += n` where `n` counted files **written**. Re-extracting zip 000, whose 200 files were
already present, added 200 to the counter and 0 to the disk, so the counter ran +200 ahead for the
rest of the walk, reached 10,000 while the disk held 9,800, and truncated zip 040 mid-way. The
re-run repeated the same re-extraction and printed DONE again. **It read the disk once at startup
and the manifest never** — the same defect class as `echo $?` reporting tee's status: the success
signal measured the wrong object.

**Fix:** the fetcher is manifest-driven. It computes the missing set, downloads only the zips
containing missing files, extracts only those members, verifies every file against the recorded
size (sha256 with `--verify`), and prints `DONE` only on a match; incomplete **exits 1** and names
the files. Discovery mode (`--no-manifest`) survives for BUILDING a manifest and now re-measures
the disk each pass and skips existing files.

[Verified by reproducing the box state locally — hid the same 200 files from zip 040; the fetcher
identified `need 1 zip(s): [40]`, fetched only `040.zip`, repaired in **3m18s**, and
`verify_corpus_manifest.py` FULL then returned **MATCH 10000/10000, 0 missing, 0 changed**. Null
control: 3 files hidden + network blocked → "NOT DONE", named them, exit 1. The 200-doc path is
unaffected.]

**Peer-scale recon [VERIFIED from their S3 uploads and `git ls-remote`].** Full ref enumeration:
three refs, no tags; Shashi's `main` is a strict ancestor of his benchmark branch (`0 14`), so
nothing is unanalysed. Findings are in §0a — the short version is that **no teammate runs 10,000
unique documents**, Shashi replicates 24 arXiv seeds by hardlink, and Leela's two arms are not
comparable with each other. A correction to my own earlier report: I initially listed one Leela RR
run; there are **five** — my `s3 ls` had been truncated by `head` and I reported the truncated view
as complete.

### SESSION 32 — blast leg durable, legs separable, Tika priced (2026-08-16)

**Blast leg now streams and resumes, same contract as sequential.** The LlamaIndex blast leg
writes from a `ThreadPoolExecutor`, so `JsonlWriter` took a `threading.Lock` around write+flush:
two threads interleaving inside one write would splice a line that is neither record — corruption
mid-file, which `read_completed` correctly refuses to resume from, by which point the run is lost.
The RocketRide blast leg is a single-threaded asyncio loop and needs no lock, but shares the
writer: one contract beats two. **The lock is not multi-process safe** and is documented as such.
`dump_jsonl` is deleted — no call sites remain, so the buffered path cannot come back by habit.

[Verified the same way as sequential: `kill -9` mid-blast left **14 records durable and 0
unparseable lines** — the lock holds under real concurrency. Resume then reported "14 on disk,
16 to go" and finished at **30 records / 30 unique / 0 duplicates**, with determinism 30/30 on
both arms across two separate invocations.]

**Legs are separable — `SMOKE_LEGS=sequential|blast`** (default both), so short supervised work and
long overnight work are different invocations against one `SMOKE_RUN_DIR`. Determinism compares the
legs, so whichever runs second reads the other's records from disk; a leg that has never run is
reported as such and its documents are unproven rather than passing on no evidence.

**Tika priced at scale [MEASURED, not estimated].** 25 real GovDocs through
`tika_reference.standalone_text`: mean **0.599 s/doc**, p50 0.574, p95 0.652, max 1.028 — one JVM
per document. **10,000 docs ≈ 1.7 h** on the RocketRide arm alone, for a check that is advisory by
its own docstring and load-bearing for neither teammate.

**Recommendation: sample it at 10k, do not drop it.** `SMOKE_TIKA_SAMPLE=200` runs a deterministic
stride sample (every k-th by sorted name — reproducible, and spread across the corpus rather than
clustered at the small documents up front), costs ~2 minutes instead of 1.7 hours, and records
`tika_sample_size` in the manifest with per-arm coverage. **What we lose:** it is the only gate
that catches a *deterministic* defect — census, structure and determinism all PASS on a doubled
document, and this is what caught BUG_CHUNK_DUPLICATION. At 200/10,000 we would expect to see
~2 % of duplication instances, so we would detect that the defect exists but **not** enumerate
every affected document. Given the engine bug is now root-caused and patched upstream by Shashi,
detection is enough; enumeration is not worth 1.7 h. Dropping it entirely would leave zero
independent evidence on the RocketRide arm, which is why sampling beats disabling.

### SESSION 31 — defect #27: a killed run lost everything; and the 10k memory question (2026-08-16)

**The smoke buffered.** `dump_jsonl` did `write_text` on the complete list **after** the loop
finished. A run killed at document 7,000 of 10,000 left **nothing on disk** — the file did not
exist yet, the list died with the process, and the result JSON is written later still. At ~25 h
for 10k that is an all-or-nothing bet on a box whose auto-stop fires silently.

**Fixed for the sequential leg** — `working/harness/jsonl_stream.py`. One line appended and
flushed per document; `SMOKE_RESUME=1` + `SMOKE_RUN_DIR` continues from what survived.
`flush()` (page cache, survives process death) per record, `fsync` at close, not per line —
10k syncs to defend against power loss we are not trying to defend against. A torn final line is
expected and skipped with a note; an unparseable line that is not last raises as corruption.
Refusing to resume without the flag is deliberate: silently appending would merge two runs.
[Verified by `kill -9` mid-run: 16 records durable; refusal without the flag; torn line detected;
resume then produced **40 records, 40 unique, 0 duplicates**.]

⚠️ **The blast leg is still buffered and not resumable.** On the box's 200-doc run the blast legs
were 70 s (LI) and 277 s (RR) — scaled to 10k, roughly **4 hours of all-or-nothing work**. Left
undone deliberately rather than rushed: the LI blast writes from a `ThreadPoolExecutor` and needs
a write lock, and I would rather flag it than ship a poorly-tested concurrent writer. **Decision
needed before 10k.**

**MEMORY SLOPE — from the box's own sampler streams** (`ansh/smoke_metrics_20260815T233408Z`,
Linux x86_64, 200 docs). Back-half fit, which excludes the warm-up ramp for the reason
`collector._leak_slope` already documents:

| stream | start MB | peak MB | end MB | back-half slope | MB/doc |
| --- | ---: | ---: | ---: | ---: | ---: |
| li_sequential | 33,946 | **34,412** | 34,282 | +0.490 MB/s | +0.86 |
| rr_sequential | 1,506 | 2,813 | 2,415 | +0.174 MB/s | +0.74 |
| li_blast | 34,306 | 35,456 | 34,207 | +0.134 MB/s | +0.05 |
| rr_blast | 157 | **10,184** | 113 | −1.422 MB/s | −1.97 |

**LlamaIndex memory is FLAT, and that is the finding.** It *starts* at 33,946 MB before documents
are processed and peaks at 34,412 — total growth across 200 documents is **466 MB on a 34 GB
base**. It is a fixed startup cost (32 workers × model), not a document-count function. RocketRide
sequential grows +0.74 MB/doc and is decelerating (whole-run average 1.54 MB/s vs back-half 0.17);
RocketRide blast spikes to 10.2 GB and **fully releases** (ends at 113 MB), so it is transient, not
accumulation.

**Does 10k risk OOM? On this evidence, not from document count.** Naive linear extrapolation adds
~8.6 GB (LI) and ~7.4 GB (RR seq) over 10k — but both slopes are decelerating plateaus, so linear
is an upper bound, and the dominant LI term does not scale with documents at all.
**Caveat that matters:** every figure above is **summed per-process RSS**, which over-counts
shared pages by the sharing factor (defect #26) — the LI 34 GB is 32 workers each counted with the
same model pages. The real footprint is smaller and the real headroom larger. `memory_sources.py`
now collects cgroup `anon` and `memory.peak`, but **shipped after this run**, so no cgroup figure
exists yet. **Get one cgroup-instrumented 200-doc run before betting 25 hours on an extrapolation
of an over-counted number.**

### SESSION 30 — defect #26: peakRSS was a SUM of per-process RSS (2026-08-16)

**Do not quote `peakRSS` from any run before this session.** The box reported LlamaIndex peak
memory as **34,411.8 MB** while `docker stats` on the same container showed **20.06 GiB** and the
a-priori estimate was ~580 MB × 32 ≈ 18.6 GB. The harness was the outlier and the harness was
wrong.

**What it measured [VERIFIED from code].** `collector.py:360` `rss += snap.rss` over every process
in the tree; `:378` `peak_rss = max(peak_rss, rss)`. So it is **the peak of a SUM of per-process
RSS**, and `psutil.memory_info().rss` counts a resident page in full for *every* process mapping
it. The 32 uvicorn workers fork after loading torch and the model, so those pages are shared
copy-on-write and were counted 33 times. **A summed RSS is a footprint multiplied by an unknown
sharing factor, not a footprint.**

**We had no deduplicated cross-check at all.** `want_uss` defaults False (`collector.py:218`) and
`collector_proc.py` never set it, so USS was never collected and PSS was never implemented. Both
now are — PSS is the only per-process figure that sums correctly (private + shared/n_mappers).

**The bias is not a constant, which matters more than the absolute error.** It scales with the
number of processes sharing pages: LlamaIndex forks 32 workers off one model (badly inflated);
RocketRide runs engine parent + 1 task child with almost nothing shared (close to correct). **So a
LlamaIndex-over-RocketRide memory ratio from summed RSS is wrong in a direction that scales with
worker count** — the arms skew in opposite directions, which is exactly the pattern observed.

**RocketRide's opposite skew is page cache, as suspected.** `docker stats` MemUsage is
`memory.current − inactive_file` and therefore includes active page cache; a run that read 7.78 GB
of PDF blocks fills it. That is why RR shows 6.5–7.5 GiB there against ~2.8 GB of anonymous
memory. Page cache is reclaimable and is not the arm's footprint; cgroup `anon` excludes it.

**Comparability — the answer to "which figure do we quote".** Leela reads cgroup `memory.stat anon`
(`cgroup_sampler.py:55-62`, with the explicit note that `memory.current` includes page cache);
Shashi reads the Docker API `memory_stats.stats.rss`, falling back to `usage − file`
(`cstats.py:132-140`). **Both are cgroup-level and deduplicated** — the kernel charges a shared
page to the cgroup once. **Our summed RSS is not comparable to either. Quote cgroup `anon`.**

**Built:** `working/harness/memory_sources.py` reads the container's own cgroup from the host,
resolving the path via `/proc/<pid>/cgroup` rather than guessing Docker's directory layout, and
reports every figure named — `memory.peak` (kernel HWM, **unsampled**, so it cannot miss a spike
between ticks, which answers Shashi's review point on our M5), `anon`, `file`, `current`, and a
`docker_stats_equivalent` so a reader comparing against a screenshot knows which line they are
looking at. The smoke prints a named memory table and writes `pinned.memory_sources`, including
`sharing_factor_summed_over_anon` — the sum-over-anon ratio, which *is* the sharing factor made
visible rather than hidden.

Source hierarchy, best first: cgroup `memory.peak` (unsampled HWM) → cgroup `anon` (comparable to
the teammates) → summed PSS (deduplicated but decimated every 20 ticks ≈ 10 s) → summed RSS
(never quote).

[Verified: USS/PSS plumbing proven end to end — a 33-sample collector run returns
`peak_uss_bytes=36,585,472`. PSS is **Linux-only**: `hasattr(memory_full_info(), "pss")` is False
on Darwin, so it reads `-` here and will populate on the box. The cgroup reader correctly reports
unavailable on macOS rather than fabricating a number. **Not yet exercised on Linux** — the cgroup
figures first appear on the next box run.]

### SESSION 29 — defect #25: the gate adapter contradicted the legacy path on identical records (2026-08-15)

The box's 200-doc run at `525ea7d` produced two verdicts over ONE record set that disagreed:
legacy said census 200 = 198 + 2 + 0 PASS and determinism 200/200 identical; the gate table said
census FAIL on both arms under BOTH rules and determinism FAIL under the symmetric rule.
**A gate failing identically on both arms under both rule sets is a harness defect**, and it was —
in the adapter that built rows for the suites, which lived inline in the smoke and was never
tested against the legacy path it was meant to reproduce.

The box JSON was not in the repo or S3 (`ansh/` holds only `t.txt`), so I diagnosed on the
**committed local 200-doc record, which has the identical shape** — 198 successful plus two
legitimately empty documents. Reproduced exactly, then fixed:

1. **Expected-empty was never plumbed.** `000_000164.pdf` and `000_000357.pdf` return zero chunks
   legitimately. The adapter passed no allowlist and labelled them with OUR vocabulary
   (`completed_empty`), which is not in Leela's `EMPTY_FAIL_REASONS` (`{"no_documents"}`). Her
   census counted them unexpected failures; Shashi's counted them silent empties. **Both FAIL,
   both arms** — exactly the reported signature. Fixed with `expected_empty_docs()` plus
   `to_leela_reason()`, which maps our vocabulary to hers at the boundary rather than editing her
   constant.
2. **The two legs classified the same document differently.** Sequentially those docs are
   `outcome="expected"` so the adapter set `ok=False`; in the blast leg the send returned, so
   `ok=True` with zero chunks. The symmetric rule then reported `only_in_b` for documents **both
   legs had processed** — an asymmetry manufactured by the adapter. `classify_ok()` is now the one
   rule applied to both legs.
   *Answering the question directly:* the phantoms were real entries produced by inconsistent
   classification, not by any document missing from a leg. Separately, the local record carries
   **one genuine asymmetry** — `000_000344.pdf` succeeds sequentially and hits the 300 s blast
   timeout — and the symmetric rule is right to fail on it. The regression test distinguishes the
   two: every `only_in_*` must be explained by a real leg-side failure.
3. **Structure differing between A and B is NOT a defect.** Tolerance (1e-3) and dimension (384)
   are identical, as verified — but they are not the only inputs. The A-side folds duplication
   into structure (`chunk_list_duplicated` counts toward `n_bad`); the B-side has no duplication
   concept. On the RR arm's 5 duplicated documents A fails and B passes. Pinned as intended so
   nobody "fixes" it into agreement.

**Regression test:** `working/harness/test_gate_agreement.py` — a golden-record test over the
committed 200-doc result. Asserts census agrees three ways (legacy, count-keyed, name-keyed),
that the two whole-corpus determinism rules agree, that no `only_in_*` is unexplained, and that
the A/B structure divergence is intentional. Synthetic rows would not have caught this: the defect
only appears when a document is neither a success nor a failure.

**Platform caveat was hardcoded.** The metrics block printed "macOS = wiring validation" on a Linux
box run. It is now derived: `platform.system()/machine()`, publishable only on Linux x86_64, with
`platform` / `publishable` / `not_publishable_reason` in the manifest. Same class of defect as a
hardcoded verdict — the caveat had stopped tracking the thing it describes.

### SESSION 28 — defect #24: external mode honoured in one place out of six (2026-08-15)

The 200-doc smoke passed readiness (`32/32 workers warm`) and then died at
`weekend_worker.py:264 RuntimeError: no service listening on 8801`. **Two detection methods
disagreeing about the same port inside one process.** `SMOKE_EXTERNAL` was wired into the readiness
path only; every other discovery site still assumed the service was a host process this driver
had started.

**Full audit — six sites, all host-side, all blind to a container:**

| site | mechanism | was |
| --- | --- | --- |
| `weekend_worker.py:262` `LlamaHttpArm.__init__` | `lsof` via `serving_pids` | **hard raise** — the reported crash |
| `weekend_worker.py:198` `RocketArm.__init__` | `lsof` on 5565, pidfile fallback | stored `None`, deferred the damage |
| `weekend_worker.py:226` `RocketArm.rss` | `engine_tree_rss_mb(None)` → **falls back to matching processes NAMED `engine`** | the 104 MB wrong-process trap, re-armed |
| `weekend_worker.py:285` `LlamaHttpArm.rss` | psutil tree walk | driver-only number reading as a measurement |
| `smoke:service_root_pid` | both of the above | fed the sampler |
| `smoke:CostSpan.__init__` | raised on `pid is None` | would have killed the run a second time |

**Fix:** one predicate, `weekend_worker.external_services()`, reading the same `SMOKE_EXTERNAL`.
In external mode host-side discovery becomes optional and non-fatal — readiness is proven by the
HTTP/`/version` gates that do cross the boundary — and anything genuinely needing a host PID
reports unavailable rather than guessing. `rss()` returns NaN instead of silently attributing some
other process's memory; **the name-matching fallback is now unreachable in external mode**, which
matters more than the crash did.

> **CORRECTED SAME DAY — "host psutil cannot sample a container" was WRONG.** Ansh challenged it
> with box evidence (`lsof -i :8801` under sudo listing host pids 3307/3321 for uid 10001) and was
> right. Docker on Linux does not hide container processes from the host; they appear in the host
> PID table under host numbering. psutil reads `/proc/<pid>/stat` for CPU
> (`_pslinux.py:1828`) and `/proc/<pid>/statm` for RSS (`:1878`), **both 0444 world-readable**, so
> an unprivileged host process CAN sample a container's tree. I generalised from macOS, where
> Docker runs in a VM and container pids genuinely are not host-visible. Wrong platform, wrong
> conclusion.
>
> **The real defect is discovery, one layer up, and it is not UID resolution either.** `lsof` maps
> a listening socket to a pid by reading `/proc/<pid>/fd/*`, which is **0500 owner-only**. The
> containers run as uid 10001 (`Dockerfile.llamaindex`, `useradd -u 10001 ws1`) and the driver runs
> as ssm-user, so `lsof -iTCP:8801` returns nothing. Run under sudo it succeeds and emits
> "no pwd entry for UID 10001" per line — root can read the fds, but no host passwd entry exists
> for that uid. The warning is a symptom of the privileged path working, not the cause of the
> unprivileged path failing.
>
> **Fix:** `container_root_pid()` uses `docker inspect -f '{{.State.Pid}}'`, which needs no procfs
> privilege, and hands the host pid to the existing psutil sampler. Applied to **both arms
> identically** (`SMOKE_LI_CONTAINER` / `SMOKE_RR_CONTAINER`, defaults `li` / `rr`), so neither is
> sampled by a different source. `lsof` also gains `-l` on both paths to stop the uid-warning
> flood. Cost is therefore AVAILABLE in Docker mode; Leela's in-container cgroup sampler stays the
> documented alternative in `metrics_shared`, not a necessity.
>
> Cost still reports `None` with a named reason if *neither* lsof nor docker inspect resolves a
> pid — but the reason now says it is a discovery failure and names the env vars to set, rather
> than claiming a sampling limitation that does not exist.

[Verified: with `SMOKE_EXTERNAL` unset an arm on a dead port still RAISES; with it set the same arm
constructs, `parent_pid=None`, `rss=nan`. Full external-mode run completes end to end.]

**Presentation:** verdict labels no longer name people — A = intersection determinism / name-keyed
census, B = symmetric determinism / count-keyed census, C = union. Gate names are unchanged and
remain the teammates' own identifiers. Output is fixed-width ASCII, PASS/FAIL only, no trailing
padding. The `gate_verdicts` JSON block is untouched, so it still carries the original keys — the
display describes the rule, the JSON preserves machine compatibility.

**Runbook:** every `tee` example now reads `${PIPESTATUS[0]}`. `$?` reports tee's status, and tee
succeeds when the run it is capturing crashes — a failed run was printing `EXIT: 0`.

### SESSION 27 — correctness-gate parity: both dialects adopted, three verdicts (2026-08-15)

Fresh clones: **Shashi `c8b4b2b3`** (moved from `70259e4`), **Leela `2cc0ccad`** (unchanged since
session 24). Shashi's new commit root-causes BUG_CHUNK_DUPLICATION — see the correction below.

**Which gates are LOAD-BEARING, from the code, not from prose:**

| | load-bearing (can fail a run) | defined but cannot fail anything |
| --- | --- | --- |
| **Leela** | census, structure, determinism — `gate_verdict()` → `m0_PASS` → `overall_PASS` → `sys.exit(1)` (`smoke2_report.py:46,117,142`) | **`ground_truth_match()` and `parity_fixture()` have ZERO call sites** in any report or runner |
| **Shashi** | every gate is a bare `assert` in `bench.py`: both arms produced chunks (:333-334), chunk-config parity (:337), workload ratio 0.4–2.5 (:356), multi-process serving (:370), census present+ok (:389-390), structure present + `docs_checked>0` + `norm_ok` (:399-403), **duplication present+ok (:413-414)**, structure ok (:431), determinism ok (:800) | near-duplicate band (logged), `workload_asymmetry` 0.8–1.25 (warn), `threads_activated`, `emb_model_source` |

So Shashi's suite is strictly larger, and `parity_fixture` — which the ask listed as one of theirs —
is **not** load-bearing for Leela today. Adopted anyway, labelled accurately.

**Adopted** into `working/harness/gates_shared.py`, every function citing its source file:line:
Leela's `gate_verdict` (PASS is True exactly), per-arm `REQUIRED_TRUE`, `leela_census`,
`leela_structure`, `leela_determinism`, `parity_fixture`; Shashi's `repeat_factor`,
`duplication_verdict`, the identical-vector check (`vectors_not_distinct`), `shashi_census`,
`shashi_structure` (with the `docs_checked>0` vacuous-coverage refusal), `shashi_determinism`,
plus the three cross-arm gates step 2 turned up that we did not have: **workload-ratio hard band,
chunk-config parity, normalization parity**. 60 unit tests, each gate mutation-tested (break the
defect it catches, confirm FAIL). `metrics_shared.py` untouched.

**Two genuine conflicts, both implemented and labelled, neither chosen:**
1. **Determinism asymmetry.** Shashi compares the intersection only and is silent on
   `only_in_a`/`only_in_b` (`correctness.py:440-469`) — correct for him, his blast phase is `n` and
   sequential is `seq_n`. Leela FAILS on asymmetry (`m0_correctness.py:150-158`) — correct for her,
   both passes are the same corpus. Ours runs the same corpus both ways, so Leela's is the stricter
   and more apt reading, but both are computed and reported.
2. **Census shape.** Shashi keys on document NAMES (duplicates/missing/unexpected/non-allowlisted
   empty); Leela keys on offered COUNT (records==offered, no dup, no unexpected failures, manifest
   check). Different denominators, both computed.
   *Not* a conflict, checked: both use `NORM_TOL = 1e-3` absolute per vector and 384 dims.

**Output**: the smoke now prints `SHASHI / LEELA / UNION` per arm plus Shashi's cross-arm block, and
writes `gate_verdicts` to the result JSON with every component verdict kept. Union is the
conjunction. Nobody has to re-derive ours and nothing is hidden behind a single boolean.

> **CORRECTION — BUG_CHUNK_DUPLICATION trigger.** Shashi root-caused it:
> `embedding_transformer/IInstance.py` `writeDocuments()` omits `preventDefault()` on the flush
> path, so at `maxDocuments = 64` the node writes the batch downstream AND the engine forwards the
> original event. **The predicate is `>= 64 chunks`, not `~239,800 characters`** — ours was a proxy
> (64 × ~3,750). **The "5.34 % of the corpus" census is therefore a proxy figure and must be
> re-derived on chunk count.** Banner added to `BUG_CHUNK_DUPLICATION.md`; the verdict now reports
> both `over_chunk_trigger` and `over_char_proxy`.

### SESSION 26 — the thread probe needed torch in its own task process (2026-08-15)

Box result: `env_probe` reaches the engine, pid 66, **all six thread vars = "1"**, `os_cpu_count`
32 — the container `-e` pins DO reach the task process. Remaining failure was
`ModuleNotFoundError: No module named 'torch'`, because `a3_env.pipe` contains only `env_probe`,
which declares no requirements, so nothing in that pipeline installs or imports torch.

**One pipeline is one task process [VERIFIED — code + prior measurement].** `ai/node.py` takes no
per-component argument (only debug flags), reports `monitorStatus('Loading pipeline')` — singular —
and hands the whole `sys.argv` to `rocketlib.processArguments`. There is no mechanism by which it
could be per-component: it is never told which component it is. Corroborated by measurement already
in the repo: `MATCHED_LAYERS.md` §1 records the 5-node `product_pdf.pipe` running with
**child-process count constant at 1**.

**Fix:** new `working/pipes/a3_env_torch.pipe` — `webhook → preprocessor_langchain →
embedding_transformer` alongside `webhook → env_probe → response_text`. The embedding node's import
chain (`sentenceTransformer.py:34` `depends()` → `requirements_sentence_transformers.txt` →
sentence-transformers → torch) loads torch at pipeline-load time, in the process `env_probe` runs
in. `env_probe` still declares **no requirements file**, so the constraints cache key
(`_compute_hash(_find_requirement_files())`) is unchanged and no recompile is paid. `a3_env.pipe`
is left in place; the measured pipe is untouched, canonical digest `f61165f7cf7ab1db`.

**⚠️ My local pass is NOT evidence the fix works, and I am recording that rather than claiming it.**
`engine_cache_dir()` is `<engine dir>/cache`, **shared across every pipeline of an engine install**,
so once any pipeline has installed torch it stays importable. Our long-lived local engine already
had it — the bare `a3_env.pipe` reports torch here too. The local run therefore proves only that
the two-node pipe is valid and runs; it cannot distinguish "the added node supplied torch" from
"torch was already installed". The code chain is the evidence. **First real test is the box.**

Consequence worth knowing: on a container that has not yet run an embedding pipeline, the probe's
first run installs sentence-transformers + torch into the engine cache — minutes and network. The
smoke pays that cost anyway; the probe front-loads it out of the first measured block.

### SESSION 25 — defect #23: the readiness counter over-counted after `docker start` (2026-08-15)

`/health` reported `warm_workers=33` against `declared_workers=32` on a restarted container.

**My keying was wrong, and wrong in the environment it was written for.** I keyed the marker
directory on `getppid()` and claimed it would differ after a restart. Inside a container the **PID
namespace restarts at 1**, so `docker start` hands the uvicorn supervisor the same low pid it had
before, the previous run's marker directory is reused, and the count becomes the UNION of two
runs' workers. The reasoning assumed host-like pid churn; containers are the opposite.

**Direction of the error is the dangerous one.** Over-counting means `warm >= want` can be
satisfied while real workers are still loading, so the run measures a partially warm service and
nothing in the output says so.

**Fixed three ways, deliberately redundant:**
1. Key is now `pid-<supervisor start time>` (`psutil.Process(ppid).create_time()`, `/proc` field 22
   fallback). Start time survives a PID-namespace reset because the kernel keeps running.
2. The image entrypoint does `rm -rf /tmp/ws1_warm` before `exec uvicorn` — race-free, before any
   worker exists, and stops the directory growing without bound.
3. **`warm_workers > declared_workers` is a HARD ERROR**, in the service (`warm_count_valid`) and
   in the driver, which refuses to measure. Yes it should be: a census cannot exceed its
   population, so the reading is not a datum but a defect — the same call Leela makes on
   `cpu_utilization > 1.0` (`m7_resources.py:131-135`) and Shashi on `threads_activated` when
   peak < baseline (`metrics.py:79-80`). Never clamped.

[Verified: two sequential runs with markers deliberately left on disk produce distinct keys and
`warm=2 declared=2 valid=True` each; a stubbed 33/32 is refused with a named error; a clean 32/32
still passes immediately. **Not reproduced locally:** the pid *collision* itself — that needs a
container PID namespace, and it is exactly what the start-time component addresses.]

**Minor, resolved:** the manifest recorded `http://127.0.0.1:5565` while both images declare
`ws://127.0.0.1:5565/task/service`. Not a divergence — the SDK normalises http(s)/bare host:port to
`ws(s)://host:port/task/service` (`connection.py:396-410`), confirmed by resolving it. The manifest
now records `resolved_websocket` alongside the input, so a cross-site diff cannot read the two
spellings as a mismatch.

### SESSION 24 — defect #22: RocketRide credentials came from a gitignored file (2026-08-15)

The thread gate failed on the RocketRide arm with `AuthenticationException: No authorization
provided`, reported as intra=None. Not a thread failure — the env_probe never reached the engine.

**Cause [VERIFIED — from the SDK and the engine's own auth module]:** every RocketRide client in
the driver is constructed bare (`weekend_worker.py:211`, `smoke50_parser_in.py:327,537`). The SDK
resolves URI and key itself (`client.py:200-205`): explicit argument, else `os.environ`, else a
**`.env` in the CWD**, else a default. `.env` is gitignored (`.gitignore:62`), so the laptop had
`ROCKETRIDE_URI`/`ROCKETRIDE_APIKEY` and a fresh clone on the box had neither.

**The engine does NOT accept any non-empty key.** `ai/account/oss/__init__.py:92-99` reads the
SERVER's own `ROCKETRIDE_APIKEY` and does
`if oss_key and oss_key != credential: return (401, 'Invalid API key')` —
an exact `hmac.compare_digest` match. Both engine images set `local-dev`
(ours `docker/Dockerfile.rocketride:59`, Leela's compose), while `start_engine.sh` defaults to
`MYAPIKEY` for the native path. If the server key is empty the check is skipped entirely, but
neither image does that.

**The measured path had the identical gap** — the sequential leg (`weekend_worker.py:211`) and the
blast leg (`:537`) construct the client exactly the same way. The env_probe only failed first
because it runs first; the 200-doc smoke would have failed on both RR legs.

**Second, worse trap found in the same code:** with `ROCKETRIDE_URI` unset the SDK falls back to
`CONST_DEFAULT_WEB_CLOUD`. A driver with a missing variable does not fail — it silently measures
the hosted service over the internet. The resolver now refuses any non-loopback URI.

**Fix:** `resolve_rr_credentials()` runs before any client is built, resolves both values
(environment → `.env` → default) and writes them into `os.environ` so every bare client in the
process inherits them. Source of each value and the key's `sha256[:8]` (never the key) go into the
manifest under `pinned.rocketride_client`. An auth failure now names the fingerprint it used and
tells you to compare against `docker exec <rr> printenv ROCKETRIDE_APIKEY`.
[Verified: bare `RocketRideClient()` connects with the environment stripped; non-loopback URI
refused; defaults resolve to `local-dev`. **Not yet verified:** the `local-dev` default against a
live container — the native engine here uses `MYAPIKEY`, so that path first executes on the box.]

**Widened 2026-08-15 (same day).** The first fix lived inside `smoke50_parser_in.py` and therefore
covered only that script. An audit of every `RocketRideClient(` construction found **~30 other
entry points with the identical gap**, including two the runbook itself invokes
(`regression_selftest.py:79`, `verify_parser_in.py:17`). The resolver now lives in
`working/harness/rr_credentials.py` and runs from `harness/__init__.py` on import
(`strict=False`, so it can never raise at import time), which covers every script that imports the
harness — all three runbook scripts do. The measured drivers additionally call
`resolve(strict=True)`, where a non-loopback endpoint is fatal.
Provenance is recorded on FIRST resolution and reused: without that, the driver's second call
reported "process environment" for everything — true, but only because the import-time call had
just put it there, which would have written a useless source into the manifest.

**`rocketride==1.3.0` added to `requirements.txt`.** It was missing and had to be hand-installed on
the box. The "NOT here, deliberately" note conflated `rocketlib` (bundle-supplied, imported by our
custom nodes inside the engine) with `rocketride` (the client SDK, pip-installed, used by every
driver). Corrected.

### SESSION 23 — defect #21: readiness by PID sampling; and a gate that reported 0 FAIL without running (2026-08-15)

**#21 — `wait_external` could not finish against a healthy container.** It polled `/health` until
`want_workers` DISTINCT `worker_pid`s had been seen. That is not a container-boundary problem —
the PIDs only need to be distinct, not host-resolvable — it is a **sampling** problem: uvicorn
workers share one listening socket, and the kernel's accept bias for short-lived connections is
strongly non-uniform, so a fully warm 32-worker service can return the same two or three PIDs
indefinitely. Coupon-collector against a sampler that may never emit most coupons. The 900 s
default timeout with no progress output completed the illusion of a hang.
**Correct signal: an aggregate the service computes itself.** Each worker writes a marker file at
the end of lifespan startup, keyed by `getppid()` (the uvicorn supervisor, shared by that run's
workers, different after a restart, so stale markers cannot inflate it); `/health` returns
`warm_workers`. One request answers it. Verified: log line count 4 == `warm_workers` 4. Timeout
now 300 s with a progress line, and an image lacking the field is a named error, not a hang.
Note the thread read-back in external mode is **one sampled worker, not a census** — same accept
bias — and is now labelled that way in the output.

**A gate that printed `0 FAIL` having run on zero documents.** The Tika independent-reference
check needs `engine/java/jre/bin/java`, which Docker mode never extracts; the run printed
`UNAVAILABLE` once and then reported `independent-reference hash: 0 FAIL`. A second, distinct
fail-open existed on the LlamaIndex arm: if a response omitted `extracted_text` the document was
skipped with no trace. Both now record `not_run:<reason>` per document, and the verdict prints
**coverage with its denominator** — `NOT RUN (0/198 covered)` or `N FAIL over C/198 covered`,
flagging partial coverage. Adopted from Leela's `ground_truth_match`: zero coverage is a vacuous
result, not a pass.
**On whether a missing gate dependency should be fatal:** for a *gate*, yes — census, structure
and determinism already hard-fail. This particular check is **advisory by design**
(`tika_reference.py` docstring: standalone Tika disagrees with the engine's in-process Tika on
some glyphs; as a hard gate it produced 4 false failures in 5 on a 50-doc run), so the default is
loud-and-recorded rather than fatal, with `SMOKE_REQUIRE_TIKA=1` to make it fatal. The silence was
the bug; the fatality is a per-check judgement.

**Ordering:** `RUN_ON_EC2.md` §12 put the thread gate before the corpus fetch, but the driver
validated the corpus first and exited 2. Preflight sends no documents, so it no longer requires a
corpus at all, and the runbook now fetches the corpus first regardless.

### SESSION 22 — instrument defect #20: the model bake never covered the runtime loader (2026-08-15)

The x86-64 LlamaIndex container failed at startup, every uvicorn worker, with
`OSError: We couldn't connect to 'https://huggingface.co' ... couldn't find them in the cached
files`, despite `HF_HOME=/opt/hf`, `HF_HUB_OFFLINE=1` and a baked model.

**Cause [VERIFIED — reproduced locally with the identical error, then fixed and re-verified]:**
`llama-index-embeddings-huggingface` does not use `HF_HOME`.
`base.py:145` does `cache_folder = cache_folder or get_cache_dir()`; `llama_index/core/utils.py:442`
resolves that to `LLAMA_INDEX_CACHE_DIR` or `platformdirs.user_cache_dir("llama_index")`
(`~/.cache/llama_index` on Linux). That `cache_folder` is handed to SentenceTransformer and
**overrides HF_HOME**. The builder bakes with raw `SentenceTransformer(...)`, which honours
HF_HOME and fills `/opt/hf`; the runtime loads with `HuggingFaceEmbedding(...)`, which looks in a
directory that is empty for user `ws1`. Same model, two cache roots.

**Why it never showed before:** the container is the project's first hermetic environment. Under a
hermetic `HOME` the baked cache fails; with a developer `HOME` it passes, because
`~/.cache/llama_index` already held the model. **Four of my own diagnostic runs passed for that
reason and were false passes — the null control (empty HF_HOME) also passed, which is what
exposed the leak.** The macOS runs in sessions 20–21 were reading from the user cache, not from
any baked location; the "model baked into the image" claim was true only for the
SentenceTransformer path, never for the path the service actually uses.

**Refuted along the way, with evidence, so nobody re-runs them:** the fastapi/uvicorn/uvloop/
httptools tail layer upgrades nothing (`uv pip compile` before/after: five additions, zero version
changes — transformers, huggingface_hub, tokenizers, torch, safetensors, numpy all identical);
huggingface_hub 1.26.0 → 1.27.0 is additive only and loads offline fine; a read-only HF_HOME loads
fine.

**Fix:** tail layer pins `LLAMA_INDEX_CACHE_DIR=/opt/li-cache`, populates it with the runtime
loader (network on, at build time only), and a following `RUN` as `ws1` with `HOME` forced to a
scratch dir proves an offline load. Neither the builder pip layer nor the baked-model layer is
touched. A build that cannot load offline now fails the build instead of shipping an image that
32 workers discover at startup with exit code 0.

### SESSION 21 — metrics adoption: one arm-agnostic module, wired and run (2026-08-14/15, laptop only)

**Decision recorded:** Phase 2 runs **both arms in Docker** on the box — the native plan in
`RUN_ON_EC2.md` is superseded for execution (banner added there). Metric functions are
container-agnostic; only the cost sampler is pluggable.

**Built:** `working/harness/metrics_shared.py` — pure functions, every definition cited to the
teammate file:line it was adopted from (Leela's `perf_window`/latency shape/`cpu_utilization_valid`;
Shashi's nearest-rank percentile/None-never-0; both teammates' cost-window slicing). Unit tests:
`working/harness/test_metrics_shared.py`, **64/64 exact-value checks pass**. Cost sources:
psutil `ProcessCollector` tree (native, 0.5 s, service tree only, driver excluded) and Leela's
cgroup-sampler JSONL (Docker) — same tuple schema, identical downstream math.

**Audit before building (their-code-vs-ours):** docs_per_s existed in 4 places here
(runner.py:270, matched_layers_sweep.py:413, matched_replication.py:243, ladder.py:145) but never
in the smoke; **chunks_per_s and cpu_utilization existed NOWHERE in our tree** (tree-wide grep);
warm-up existed only driver-side (runner.py:109-114 — Shashi's placement, superseded by the
settled metric-side rule); stats.py percentile is linear-interpolated and is NOT used by the new
module (settled: nearest-rank).

**Instrument defect #19, caught by the first 200-doc run:** the independent-reference gate (a
standalone Tika JVM per doc, RR arm only) ran INSIDE the timed loop, landing in the
completion-to-completion span — RR sequential read 0.25 docs/s; moving the gate post-loop gives
~13 docs/s on the same 5-doc fixture (~9×, biased AGAINST RocketRide). All our gates now run
post-loop from records, which is also both teammates' shape. Determinism semantics fixed in the
same pass: a blast-leg failure now counts **unproven**, not drift (their shared semantics).

**⚠️ RR docs/s from this run is NOT a throughput number — it is one stalled document.**
`000_000344.pdf` (2.6 MB, returns **1 chunk**) took **314.5 s** in RR sequential — **52 % of the
entire RR span** — and in the v1 blast leg the same document hit the 300 s timeout. Top 5 docs =
82 % of RR's span; the equivalent LI figure is 31 %. Cross-arm on the same documents:
000_000344 RR 314.5 s vs LI 1.74 s (**181×**), 000_000859 51×, 000_000282 25×; **15/198 documents
are >10× slower on RR**, and slowness does not track chunk count (the worst offender emits one
chunk). Candidate engine finding — large PDF, tiny text yield, enormous parse-path stall —
reproducing in **both** send modes. **PROVISIONAL** (one host, n=1, macOS). Re-test on the box
before it is claimed; if it reproduces on Linux it is a bug report, not a benchmark number.

**200-doc run (v2, macOS — wiring validation; per policy no number here is publishable):** see
`working/results/smoke50_parser_in__20260815T053227Z__c79e799b3baa.json` +
`smoke_metrics_20260815T051154Z/` raw JSONL.
Findings from v1 that stand: **5/18 independent-reference FAILs are exact whole-list 2× repeats**
(BUG_CHUNK_DUPLICATION: docs 159, 595, 674, 762, 887 — note 762 duplicated at reference-extracted
**213k chars, below the 239.8k synthetic threshold**; threshold is payload-path-dependent, worth
a line in the bug report); the other 13 are ±1-char reference-vs-engine extraction offsets
(instrument disagreement, open item T3-8 class, NOT new engine bugs); 1 RR blast doc
(000_000344, 1.5 kB) hit the 300 s send timeout while big docs completed — engine blast-path
starvation candidate, watch on the box.

### SESSION 20 — cross-team alignment + native run plan (2026-08-14, laptop only, box stayed stopped)

Peer repos re-fetched into `reference/` (Leela `main` @ `e1cd611`, Shashi
`benchmark/shared-pipe-engine-3.3.1` @ `70259e4`) and diffed against ours on the seven things that
decide comparability. Deliverable: **`publishable/RUN_ON_EC2.md`** — a native 200-doc smoke.

**Established this session, with labels:**

| finding | label | method |
| --- | --- | --- |
| All three teams' pipes are **semantically identical** — same 5 providers, same lane wiring; they differ only in `project_id` and whitespace. Canonical digest `f61165f7cf7ab1db…` on all three | **VERIFIED** | line-diff **and** key-sorted canonical hash, two methods |
| Shashi's raw-`sha256` pipe gate therefore produces **three different values on identical pipes** — a false alarm, and his own doc's source-of-truth hash (`78d381d3…`, = Leela's file) no longer matches his repo-root file (`3cee2722…`) | **VERIFIED** | hashed all three files |
| Engine tarball `d8dad45b…ce0281d8`; extracted `engine` binary `95768e26…d9747`. **Different objects — label which one you mean** | **VERIFIED** (two parties) | our pin ✓, and Leela's independently-derived `ENGINE_SHA256` ✓ |
| Engine hard deps are exactly `libc++1 libc++abi1 libunwind8` (+ base libc/libm/libgcc); `libjvm` from the bundled JRE via `DT_RUNPATH`. `libnuma`/`libcrypto` are dlopen probes, **not** required | **VERIFIED** | real `DT_NEEDED` parse, cross-checked against a string scan |
| Highest glibc symbol is **2.35** — Ubuntu 22.04 exactly, zero headroom | **VERIFIED** | `.gnu.version_r` scan |
| `onnxruntime-gpu==1.20.1` is genuinely gone from PyPI; 1.20.0 and 1.20.2 remain. The pin is in **five** manifests, not three; `REQUIREMENTS_GLOBS` is recursive so all five compile | **VERIFIED** | PyPI JSON + grep over the extracted tarball. Shashi's *Dockerfile* catches all five; only his prose says three |
| **Ubuntu 22.04's Python 3.10 cannot install our pins** — `numpy==2.5.1` and `scikit-learn==1.9.0` have no cp310 wheel, sdist only | **VERIFIED** | PyPI JSON per package |
| 200 docs = **exactly govdocs1 zip 000**, and its first ten are name-for-name Leela's box selection | **VERIFIED** | null control: `sorted(*.pdf)[:200]` ≡ `sorted(000_*.pdf)[:200]`; all 200 match the committed manifest |
| Shashi's corpus is **24 arXiv PDFs replicated**, not GovDocs1 | **VERIFIED** | `seed_manifest.json`, `bench.py:fetch_seed_pdfs` |

**Changed in the harness** (all still 12 pass / 1 known xfail; validated by a real 3-doc run, all
five gates PASS both arms): `smoke50_parser_in.py` gained `SMOKE_WORKERS` / `SMOKE_THREADS` /
`SMOKE_BLAST_C` / `SMOKE_CORPUS_GLOB` (defaults reproduce the old behaviour exactly), a
short-corpus refusal, and a `pipeline`/`corpus`/`pinned` provenance block matching Shashi's export
keys; `verify_corpus_manifest.py` gained `--subset` (same gate scoped, refuses an empty directory);
new `exfil_s3.sh` and `install_awscli_userdir.sh` — **we had no S3 path at all before today**.

**Not done, deliberately:** no new metric, no new gate, no throughput number, no memory number.

### PHASE 2 HANDOFF — 2026-08-13

Engine pinned **3.3.1 + SDK 1.3.0** (team decision; our pairing, the only manifest-correct one).
Parser IN on both arms. `publishable/PRE_AWS_READINESS.md` carries the evidence.

**TRAVELS TO AWS — gate-clean locally**

| item | evidence |
| --- | --- |
| Parser IN, both arms | 50/50 documents, census closes on both arms |
| Leela's census + structure + determinism gates | implemented; PASS on both arms (L2 tolerance 1e-3) |
| Determinism under concurrency | 50/50 blast vs sequential, both arms |
| In-process thread parity, refuses to run on mismatch | 10 intra-op / 14 interop, both arms, every run |
| Content sanity (NUL + printable ratio) | 0 false positives on 50 documents |
| Setup probe + environment manifest incl. **engine binary sha256** | `working/scripts/setup_probe.py` |
| Cross-arm extraction fidelity as a REPORTED metric | median char ratio 0.9963 over 50 docs |
| Per-arm chunk hash for the **LlamaIndex** arm | 0 failures on 50; reference is the arm's own returned text |

**PROMOTED — parse-tap reference [VERIFIED]**

Build the chunk reference from the engine's own `parse` output (tapped via a second `response_text`
node on the `text` lane), not standalone Tika. **97/98 exact** vs 4-in-5 false failures the other
way. Catches defects downstream of parse; cannot catch defects inside parse. Travels.

**NUL scope changed under Parser IN [PROVISIONAL]:** the ~0.30 % prevalence in
`BUG_NUL_TRUNCATION.md` was measured parser-out with pypdf. On `038_038716.pdf` the engine's Tika
output contains **no NUL**, so nothing truncates on that path. The defect is unchanged and still
reproduces on text/plain (`'AAAA\\x00BBBB'` → `'AAAA'`, re-verified 2026-08-13); only the prevalence
needs re-deriving from Tika extractions. Bannered in the bug report. **First correctness item on AWS.**

**DOES NOT TRAVEL**

| item | why | label |
| --- | --- | --- |
| **`harness/tika_reference.py` as a GATE** | standalone Tika does not reproduce in-process Tika byte-for-byte — glyph mapping differs (soft hyphen vs space, em-quad vs em-space) despite identical version, jars, `tika-config.xml` and JVM defaults. On 50 documents it produced 5 failures, **4 of them this artifact**. **ADVISORY ONLY. Do not run as a gate.** | root cause **UNVERIFIED** |
| **The `+'\n\n'` reference rule as published** | measured byte-exact 8/8 on the *first 8 sorted* documents; holds **2 of 6** on a wider draw. The earlier 8/8 overstated it and is corrected in place. Must be re-derived, and re-derived again on 3.2.1 | **superseded** |
| **Census identity as a HARD gate** | closes on both arms but the fault taxonomies are asymmetric — LlamaIndex returns typed error classes, RocketRide signals failure with an empty document list. It closes while meaning different things | **VERIFIED asymmetry** |
| **Per-file corpus sha256 manifest** | still not built. Both Leela and Shashi have one; we are the weakest of the three on corpus provenance | MISSING |
| **Warm-up at 25 documents** | insufficient for the LlamaIndex arm (1.08× steady at reps 25–50). Use **100** | **PROVISIONAL** |

**NO independent parse reference exists for the RocketRide arm.** That is the honest state. The
LlamaIndex arm has one (its own returned `extracted_text`); RocketRide does not, because the only
candidate does not reproduce the engine byte-for-byte. Raised with the team as an open question
rather than papered over — `publishable/TEAM_MESSAGE_2026-08-13.md`.

**`000_000159` duplication — status recorded [VERIFIED what, UNVERIFIED why]**

Engine returns the document's chunk list **twice, concatenated** (164 = 2 × 82, 82 unique hashes,
first half == second half == reference). Three harness explanations tested and refuted: the two
`parse` nodes are byte-identical; a single-input preprocessor variant reproduces it; the plain
pipeline reproduces it.

**Second instance found** on a size ladder: `009_009442.pdf` at **2.25 MB**, also exact `[ref+ref]`
doubling (144 = 2 × 72). **NOT a simple size threshold** — documents at 3.00, 3.01, 4.00 and 5.00 MB
are clean, and the 2.25 MB case is smaller than the 4.05 MB one. Prevalence **1/98** on an arbitrary
sample; **2 instances total** across ~110 documents examined. Mechanism unknown, so not filed to the
NUL report's standard. Impact if indexed: those documents are stored and retrieved double-weighted,
silently, with every vector individually valid.

**Detection [VERIFIED]:** the parse-tap reference catches it while ALL THREE of Leela's gates pass —
determinism n=3 (164 chunks every run), structure (all 164 vectors 384-d, finite, L2 within 1e-3),
census (1 = 1). Real-data demonstration of the self-comparison blind spot.

**Closed 2026-08-13 — the two pre-AWS questions [VERIFIED]**

| # | question | answer |
| --- | --- | --- |
| Q1 | Can NUL truncation occur under Parser IN? | **No observed path via PDF ingestion**: 0/303 documents have NUL — or any control char beyond \t\n\r — in Tika output, including all 3 known pypdf-NUL docs. Tika sanitises them. Defect itself still reproduces on text/plain. Bug report re-scoped |
| Q2 | Is chunk duplication size-correlated? | **Yes — to extracted-TEXT length, not file size.** Threshold between **239,062 and 239,843 chars**, bisected, deterministic n=3 both sides. Synthetic minimal reproducer (4 lines, plain text). Factor exactly 2 up to 750k chars. 5 affected documents found; every one above threshold, every clean one below. **Filed: `BUG_CHUNK_DUPLICATION.md`** |

**Cross-team, cross-version confirmations [VERIFIED]**

| # | finding | label |
| --- | --- | --- |
| X1 | Leela's two expected-fail documents (`000164.pdf`, `000357.pdf`) return **0 documents on our engine 3.3.1**, reproducing her 3.2.1 result. Two teams, two engine versions, two harnesses | **VERIFIED** (2/2) |
| X2 | Her `EXPECTED_FAIL` set is hardcoded to filenames that match **zero** documents in a `000_000164.pdf`-style corpus, so the check passes vacuously there. The underlying finding is sound; the mechanism does not port | **VERIFIED** |

**Instrument defects caught this session** — the twelfth and thirteenth in this project, both of
which would have travelled as RocketRide findings:

* Driving `RocketPdfArm.process()` from a `ThreadPoolExecutor` calls `run_until_complete` on one
  asyncio loop from several threads, silently abandoning coroutines and reporting **7/8 false
  non-determinism**. Fixed to one loop with `asyncio.gather`; 50/50 clean after.
* The 400-document warm-up measurement varied document index and document size together on a corpus
  whose sizes span **2018×**. It measured size. Discarded and redone with a fixed fixture.

## 4. Verified findings, with labels

| # | finding | label | evidence |
| --- | --- | --- | --- |
| 1 | Crossover at 200–400 tokens (**BURST mode only**); RR overhead-bound, LI compute-bound | **VERIFIED** (2 methods) | `working/results/token_sensitivity.json`, `working/results/parity_corpus.json` |
| 1a | ~~Sustained mode: LlamaIndex faster at 100–6,400 tokens~~ | **INVALID (session 6)** — rested on the withdrawn decay; both harnesses were configuration-dependent | superseded by `working/results/concurrency_barrier.json` |
| 1b | ~~RocketRide decays 31.3 % under sustained load~~ | **WITHDRAWN (session 6)** — does not reproduce; 6.0 % on exact replication, +1.5 % median over n=3; LlamaIndex shows the same ±12–18 pp swing | `archive/results/decay_rootcause.json`, `working/results/decay_symmetric.json` |
| 1b2 | **Neither arm decays under sustained load** — RR +1.5 %, LI +1.0 % median (n=3, randomised, 0 failures) | **VERIFIED** (2 methods: exact replication + symmetric n=3) | `working/results/decay_symmetric.json` |
| 1b3 | RocketRide flat in offered concurrency 2→32 — **ONLY AT DEFAULT THREAD SETTINGS, and not caused by the engine** (session 7) | **VERIFIED but CONDITIONAL** | `working/results/concurrency_barrier.json` + `working/results/a3_serialization.json` |
| 1g | **The engine is NOT the bottleneck**: request path scales 3.69×, Python-node dispatch costs ~3 %, pure-Python CPU in a node scales 3.59×; only the embedding arm is flat (1.46×) | **VERIFIED** | `working/results/a3_serialization.json` |
| 1h | **Cause = native thread oversubscription.** One embed occupies 1.45 cores at default vs 0.49 pinned; per-request CPU inflates 80 % under concurrency | **VERIFIED** (2 methods: intervention + system-wide CPU-time accounting; pure-Python null control unmoved) | `working/results/a3_threads.json` |
| 1i | **Thread pinning at engine start → RR scaling 1.43×→3.04× @400tok and 1.18×→3.05× @1600tok**; helps above conc≈4, HURTS below (0.41–0.55× at conc 1) | **VERIFIED** (2 sessions, ABA design, n=5, gated) | `working/results/reanchor_tuned.json` |
| 1k | **Pin verified INSIDE the task process**: `torch.get_num_threads()` = 10 default → 1 pinned. `torch_num_interop_threads` stays **14 even when pinned** — no env var reaches it | **VERIFIED** | `working/nodes/env_probe`, `working/results/reanchor_tuned.json` |
| 1l | **Anchor B flips with tuning**: 1600tok/conc2 RR/LI = **1.201 [1.185,1.217] untuned** (reproduces the 1.190× reference) but **0.926 [0.917,0.934] tuned**. Best-achievable config is CONCURRENCY-DEPENDENT | **VERIFIED** (both arms pass the gate in both blocks) | `working/results/reanchor_tuned.json` |
| 1m | ⚠️ **TOPOLOGY-CONFOUNDED (MATCHED_LAYERS.md, opposite direction)** — **Peak RSS**: RR idle 204 MB → 2,356 MB @6400tok/c32; LI idle **4,642 MB** → **7,950 MB**. LI's floor is fixed (8 workers × model); RR grows with document size | **VERIFIED** (continuous 250 ms sampling) | `working/results/memory_ceiling.json`, `working/results/memory_rr_fixed.json` |
| 1n | **A6 RESOLVED — 9.29 and 1.45 measure different statistics.** At default threads one embed: time-average **2.42 cores** (c=1) / 4.83 (c=8); p95 **4.17** / **10.08**; peak **7.75** / **13.09**. Finding 7's 9.29 is a p95/peak under load; session-7's 1.45 was a time-average with a contaminated baseline | **VERIFIED** | `working/scripts/a6_peak_vs_mean.py` |
| 1o | **Engine PDF path is Tika, VERIFIED by execution** — `com.rocketride.tika_api.TikaApi`, JVM loaded **in-process via JNI** (no separate java process). Engine bundles OpenJDK 17.0.19 Temurin aarch64 | **VERIFIED** (source + execution) | `pdftest/`, engine binary strings |
| 1p | **LlamaIndex has NO PDF reader installed**; core maps `.pdf`→`PDFReader` from the absent `llama-index-readers-file` and **silently returns `{}`**. Default parser once installed is **pypdf**, not PyMuPDF | **VERIFIED** | PyPI metadata + `llama_index.core` source |
| 1q | Tika vs pypdf on a simple 3-page text PDF: **99.10 % agreement**; pypdf 100.00 % vs source, Tika 99.10 % | **PROVISIONAL** (one easy PDF; says nothing about scanned/multi-column) | `working/results/pdf_parser_diff.json` |
| 1r | **Inter-op thread pinning is HARMFUL** — lands in-process (14→1) but costs 14.3 % @conc8, 0.999× @conc2 | **VERIFIED** (gated, drift control held) | `working/results/anchor_b_interop.json` |
| 1s | **ANCHOR C: RocketRide width = 17.24, VERIFIED** by the guarded instrument (escaped tracking, confirmed by doubling) — reproduces finding 8's ~17 | **VERIFIED** | `working/results/anchor_c_width.json` |
| 1t | **LlamaIndex has NO single pool width** — the guarded instrument REFUSED (estimate tracked offered concurrency to 96). Sleeping holds do not occupy a worker: `/process` is a sync `def` on Starlette's threadpool. Finding 9's width=8 is its **CPU knee**, not its slot count | **VERIFIED** (instrument refused rather than guessing) | `working/results/anchor_c_width.json` |
| 1u | ~~LlamaIndex saturates at concurrency 4~~ **WITHDRAWN session 11** — ascending cold sweep; pre-warmed estimate is c16 @ ~226/s. Original: (74.7/s @400tok, 29.1/s @1600tok). Past it throughput is flat-to-degrading while P99.9 goes 96 ms → 2,987 ms. **0 errors at every level to c=64** | **PROVISIONAL** (1 session, n=5 gated per cell) | `working/results/isolated_profile_llamaindex_PREWARM.json` (the session-9 ascending run it originally cited was overwritten by the pre-warm re-run; the withdrawn session-9 data is preserved at `archive/results/isolated_profile_llamaindex_SESSION9.json`) |
| 1v | ~~Sessions 6–8 compared past saturation~~ **WITHDRAWN session 11** — rested on the withdrawn c4 figure; with saturation at c16 those concurrencies were at or below it. Original: Those numbers measure queueing, not serving capacity | **VERIFIED** (follows from 1u) | — |
| 1w | **Custom PARSE nodes work in the engine** — `pdf_probe` ran pypdf 6.15.0 in the engine's embedded CPython, output byte-identical to standalone. **Tika is a default, not architecturally forced.** But adding the dependency required hand-copying into `engine/lib/python3.12/site-packages/` — no supported path | **VERIFIED** (executed) | `working/nodes/pdf_probe/`, `PARSER_PREMISES.md` |
| 1y | ~~OPTIMAL-POINT COMPARISON~~ **WITHDRAWN session 11** — placed each arm at a saturation point that does not exist, and measured both cold. Original: — both arms at their OWN saturation, one session, drift control −0.4%/−1.4%**: untuned RR/LI = **0.789** [0.776,0.800] @400tok, **0.886** [0.871,0.902] @1600tok; tuned = **0.758** [0.742,0.786] @400tok, 0.973 [0.890,1.025] @1600tok (RR gate-failed). **LlamaIndex ahead at every quotable point.** The hypothesis of near-parity-with-RR-ahead-at-1600 is REFUTED | **VERIFIED** (both arms gate-pass in 3 of 4 cells; drift control held) | `archive/results/optimal_point.json` |
| 1z | ~~RocketRide saturation config/size-dependent~~ **WITHDRAWN session 11** — ascending cold sweep. Original:: c4 (tuned/400), c32 (tuned/1600), c16 (untuned/400), c4 (untuned/1600). LlamaIndex is c4 throughout. Peak plateaus: RR untuned 63.8/s @400, 28.7/s @1600 | **PROVISIONAL** (1 profile run; absolutes did not reproduce — see A13) | `archive/results/isolated_profile_rocketride.json` |
| 1aa | **RSS sampler is NOT an observer effect** — sampler on vs off, alternated n=3: −0.4 % | **VERIFIED by null control** | `working/results/sampler_nullcontrol.json` |
| 1x | **PyMuPDF is AGPL-3.0 / Artifex commercial** — disqualifying for a network service without procurement. pypdf BSD-3 (and LlamaIndex's own default), pdfplumber MIT, pdfminer.six MIT-but-STALE | **VERIFIED** (package metadata) | `working/dossiers/`, `PARSER_PREMISES.md` |
| 1j | **All prior RR-vs-LI throughput comparisons were tuned-service-vs-untuned-engine** (our service pins threads, the engine did not) | **VERIFIED** (follows from 1h + `working/ws1/run_service.sh`) | — |
| 1b4 | **RocketRide ahead 1.190× at 1,600 tokens / concurrency 2** [CI 1.184–1.196], BOTH arms pass the 10% gate (1.6%/0.5%) | **PROVISIONAL** (1 harness) — the only gate-passing head-to-head advantage in the project | `working/results/concurrency_barrier.json` |
| 1b5 | ~~The RocketRide arm is systematically noisier than LlamaIndex~~ | **WITHDRAWN (session 6)** — was our own harness desync. Under barrier-synchronised windows RR passes the gate in 8/10 cells (1.2–9.8% at 1600tok) | `working/results/concurrency_barrier.json` |
| 1c | ~~Services converge toward parity as documents get heavier~~ | **DOWNGRADED to UNVERIFIED (session 6)** — both supporting sweeps are configuration-dependent; not retested | — |
| 1d | **Pipeline topology is NOT a throughput factor** — 1-node vs 4-node = 0.88–1.13× | **VERIFIED** (1-node arm returns 159B vs 9–24KB — confound favours RR, retired by 1f) | `working/results/topology_persistent.json` |
| 1e | Chunk count does not drive the ratio (no trend, 1→13 chunks) | **VERIFIED** | `working/results/topology_persistent.json` |
| 1f | **Response payload size is not a measurable cost** — LI payload grew 100×→555× (15.9→115.4 KB) with no ratio movement | **VERIFIED** | `working/results/topology_persistent.json` chunk_vs_token bytes |
| 2a | **Result writes could not collide before session 12** — audit found 51/51 hardcoded output paths and 6 names claimed by >1 script; TWO runs were silently destroyed (session-9 ascending profile, and the descending-order run) | **VERIFIED** (audit + reproduction) | `working/harness/resultio.py` |
| 2b | **Collision guard proven** — `O_EXCL` at the syscall level and `ResultCollision` at the API level both refuse to overwrite | **VERIFIED** (attempted overwrite, both blocked) | `working/harness/resultio.py` |
| 2c | **Goodput gate catches the silent-`{}` PDF path** plus 5 other failure modes, and passes a correct document | **VERIFIED** (6 negative cases + null control) | `working/harness/goodput.py` |
| 2d | **GovDocs1 is 192× heavier per document than mt10k by bytes, 19× by tokens** (median 227,567 B / ~6,345 tok vs 1,186 B / 338 tok); max 1,000 pages; natural fault rate 1.42 % | **VERIFIED** | `working/results/govdocs1_characterization__*.json` |
| 2e | **Containerised pipeline works end to end offline under a 12 GB cgroup cap**: peak RSS 1,405 MB at 100 docs (12 % of limit), current RSS *fell* 1,405→1,121 MB by doc 250 — allocator high-water then release, no accumulation | **PROVISIONAL** (1 run, rung 3 incomplete) | `working/results/docker_ladder/ladder_llamaindex_*.json` |
| 2f | **Container memory is dominated by WORKER COUNT, not document size** — the 7.95 GB figure was 8 workers × concurrency 32; one in-process pipeline on 6,345-token documents peaks at 1.4 GB | **PROVISIONAL** (1 run, 1 concurrency) | as above |
| 2g | **`HuggingFaceEmbedding` derives its cache dir from the CALLING USER's home, not `HF_HOME`** — "model is baked" was true as root and false as the runtime user, surfacing as a misleading "couldn't connect to huggingface.co" | **VERIFIED** (build passed as root, failed as ws1, fixed by priming as ws1) | `docker/Dockerfile.llamaindex.layer` |
| 2h | **`llama-index-readers-file` cannot be installed for the PDF path alone** — its `__init__` imports the tabular readers, requiring pandas. We call pypdf directly | **VERIFIED** | `PARSER_DECISION.md` |
| 2 | mt10k corpus is the real one | **VERIFIED** | 10,000/10,000 sha256 vs Leela's manifest |
| 3 | mt10k shape: median 1,186 bytes, median 1 chunk (93.2 % single-chunk), median 338 tokens | **VERIFIED** | `working/results/corpus_characterization.json` |
| 4 | On real mt10k, RocketRide 1.13× faster (233.95 vs 202.27/s) | **direction VERIFIED, point PROVISIONAL** | RR arm spread 14.8 % FAILS the 10 % gate; direction corroborated by chunk sweep + token sweep |
| 5 | RocketRide ahead at every chunk count on 444-token-per-chunk text (1.23×–1.55×) | **VERIFIED** | `working/results/parity_corpus.json` chunk sweep |
| 6 | `sentence-transformers` silently selects `mps` (Apple GPU) when device unset | **VERIFIED** (3 methods) | null control with HTTP removed; direct device interrogation; service-level sweep |
| 7 | RocketRide's engine embeds on **CPU** | **VERIFIED** | `cores_busy 9.29`; source inspection said GPU and was **WRONG** |
| 8 | RocketRide effective pool width = **~17** | **VERIFIED** (2 methods) | hold-and-divide (17.1/17.2/16.6); alloc-hold wall-time arithmetic |
| 9 | LlamaIndex service effective width = **8** on cpu (declared 14 workers) | **VERIFIED** | throughput knee sweep, n=3 |
| 10 | Engine throughput under protocol: 12,313.5/s @ 4 drivers, spread 1.7 % | **VERIFIED** | n=5, warmup discarded, randomised |
| 11 | Most run-to-run variance is a warmup artefact (17.7 % → 1.7 %) | **VERIFIED** | `working/results/ws1_variance_cause.json` |
| 12 | Load-average carryover is NOT a variance cause | **VERIFIED by null control** | drove load to 7.88, got the *lowest* spread (0.7 %) |
| 13 | GPU (`mps`) variance is irreducible (14–25 %); CPU reaches 0.7–4.4 % | **VERIFIED** (2 methods) | pin `device=cpu` for all parity work |
| 14 | Fault isolation: RocketRide separates from expert-tuned Python on **nothing** | **VERIFIED** | 11/12 matrix cells all 0.00 for all frameworks |
| 15 | Peak memory under *held* allocations: RR 5,040 MB vs asyncio 13,363 MB at matched width | **PROVISIONAL** (1 run) | the one genuine RR advantage found |
| 16 | Model A (N concurrent pipelines) livelocks at ~150 | **VERIFIED** | reproduced twice; 81 orphaned `node.py` |
| 17 | pool_width instrument accurate to ~1 % when guarded | **VERIFIED** | calibrated vs known widths 4/8/16/64 |


> ## 🛑 CORRECTION 2026-08-07 (session 11) — ASCENDING CONCURRENCY SWEEPS UNDER-MEASURE. ALL SATURATION POINTS WITHDRAWN.
>
> **Open item A13 is resolved, and the cause invalidates every saturation point in this project.**
>
> A benchmark that begins at low concurrency and ramps up measures a machine that never leaves a
> low-power state. Identical harness, 400 tok, LlamaIndex, only the CELL ORDER changed:
>
> | concurrency | 1 | 2 | 4 | 8 | 16 | 32 | 64 |
> | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
> | ascending (cold) | 30.5 | 63.5 | 89.0 | 106.5 | 102.7 | 101.7 | 101.5 |
> | descending | 39.8 | 84.0 | 124.1 | 204.8 | **248.7** | 228.1 | 240.6 |
> | ascending + 30 s pre-warm at c64 | 39.2 | 82.7 | 106.8 | 183.7 | **225.7** | 223.6 | 225.0 |
>
> Pre-warming reproduces the descending run (both ~2.2× the cold ascending run above c8), so the
> variable is **the machine's power/performance state at the moment measurement starts**, not the
> concurrency level, not the harness, and not the service.
>
> **Ruled out first, each by direct experiment:** readiness/warm gate (cold gate read 102.4 % of
> warm gate; all 8 workers warm in both); RSS sampler (null control −0.4 %); background CPU load
> (4 hogs left c8 at 99.4 %, while the c1 control fell to 86 %); sustained decay (5 min continuous
> at c8 held 190–204 /s, −3.5 %); harness design (single-process vs 4-process agreed to 1.010×).
>
> **WITHDRAWN — every saturation point:**
> * LlamaIndex "saturates at c4" (session 9) — artifact of an ascending cold sweep
> * LlamaIndex "saturates at c8" (session 11 re-run) — same artifact, milder
> * **all four RocketRide saturation points** (session 10) — that profile also swept ascending from
>   c1, so it is depressed by an unmeasured amount
> * **the optimal-point comparison** (session 10, findings 1y) — it placed each arm at a saturation
>   point that does not exist, and both arms were measured cold
>
> **Best current estimate, pre-warmed [PROVISIONAL, 1 run]: LlamaIndex saturates at c16, ~226 /s at
> 400 tokens** — 3× the throughput and 4× the concurrency of the withdrawn figure.
>
> **This is almost certainly open item F.** The unexplained between-session drift since session 6
> has the same signature: runs that began under light load read low. It is one cause, not two.
>
> **Protocol consequence — every future measurement must pre-warm to a high-power state and record
> that it did.** Randomised cell order does not fix this; it only smears the depression across
> cells instead of concentrating it in the early ones.

## 4b. ⚠️ SATURATION COMPARABILITY BANNER (added 2026-08-07)

Both arms now have isolated saturation profiles. **LlamaIndex saturates at concurrency 4; the
engine's point depends on config and document size (c4–c32).** Any comparison taken at a
concurrency past an arm's saturation measures **queueing behaviour**, not serving capacity — the
service is already at its throughput ceiling and the extra load only accumulates in a queue.

**Every finding below that was measured past LlamaIndex's saturation point of 4 is marked
`[PAST-SAT]`.** They are not wrong — they are answers to a different question, and they must not be
quoted as "how fast is this service".

| finding | concurrency used | status |
| --- | --- | --- |
| 1a (withdrawn sustained curve) | 8 (2 drivers × 4) | `[PAST-SAT]` — already INVALID for other reasons |
| 1b3 (RR flat in concurrency 2→32) | 2–32 | `[PAST-SAT]` above c4 — the flat region IS the post-saturation plateau |
| 1b4 (RR ahead 1.190× @1600tok/**c2**) | **2** | **within saturation — stands** |
| 1i / Anchor A (tuned vs untuned scaling) | 1–32 | `[PAST-SAT]` above c4; the *scaling* claim is about the whole curve, so it stands as a curve statement |
| 1r (interop effect @c8) | 8 | `[PAST-SAT]` — a post-saturation A/B; the 14.3 % cost is real but describes queued behaviour |
| 1s (RR width 17.24) | escalated to 96 | structural measurement, saturation not applicable |
| 4 (mt10k parity 1.13×) | 8 | `[PAST-SAT]` |
| 5 (chunk sweep 1.23–1.55×) | 8 | `[PAST-SAT]` |
| 10 (engine 12,313/s @4 drivers) | high | request-path capacity, not the embedding workload — not applicable |
| **1y (optimal-point comparison)** | **each arm at its own saturation** | **the only head-to-head in the project taken inside both arms' serving regime** |

**Count: 6 findings carry `[PAST-SAT]`.** None is re-run here; the banner marks what each number
describes.

## 5. SUPERSEDED NUMBERS — including a correction that was itself wrong

**Read this section before quoting any number from an older doc.**

### 5.1 The ±35 % variance saga — a correction that was WRONG

| step | value | what happened |
| --- | ---: | --- |
| 1 | **11,408/s** @ 4 drivers | first measurement, n=1 |
| 2 | **7,871 / 8,540 / 8,311/s** | re-measured later the same day. I concluded 11,408 was a ~35 % outlier and **wrote correction banners saying so** |
| 3 | **12,313.5/s, spread 1.7 %, n=5** | re-measured under the full variance protocol — **supports the ORIGINAL 11,408 and does not reproduce the 7,871–8,540 cluster at all** |

**The step-2 correction was wrong.** The ±35 % turned out to be a **between-session** effect, not
within-session noise. Within a session under protocol the engine is stable to 1.7 %.
**Why the step-2 session read low is UNVERIFIED** — it coincided with a 15-min load average of
20.01, but the load-carryover hypothesis was refuted by direct null control (finding 12).

**Operational consequence: between-session comparisons are the dangerous ones, and within-session
repetition will not catch them.** Anything compared must be measured in ONE interleaved session.

### 5.2 Everything else superseded

| old claim | status | replaced by |
| --- | --- | --- |
| RocketRide ~2,600/s (flat from n=100 to 20,000) | **SUPERSEDED** | client-bound, not engine-bound. A single-process driver saturates ~2,500–3,400/s regardless of target. Engine does 12,313/s @ 4 drivers |
| "LlamaIndex 1.73× faster" (parity) | **WITHDRAWN** | artifact of a ~210-token test document; corpus median is 338 and the crossover is 200–400. Replaced by RocketRide 1.13× on real mt10k |
| LlamaIndex service effective concurrency = 4 | **SUPERSEDED** | that was an `mps` reading; on `cpu` the knee is **8** |
| Tier 2: FastAPI 3.69× faster than RocketRide | **SUPERSEDED** | RocketRide's arm was pre-protocol. Recomputed **2.36×**, and **PROVISIONAL** — the FastAPI side has still not been re-measured under protocol |
| "RocketRide is worse than asyncio at absorbing hangs (13.82 vs 1.95)" | **WITHDRAWN** | two harness bugs (processpool deadline never fired; asyncio timer started on semaphore acquire). Symmetric deadline → all frameworks 9.1–10.0, i.e. indistinguishable |
| `alloc` fault shows no memory difference | **SUPERSEDED** | the test freed memory immediately so nothing overlapped. `alloc_hold` (256 MB held 2 s) shows RR 5,040 MB vs asyncio 13,363 MB at matched width |
| Engine's embedding node runs on GPU (from source inspection) | **WRONG** | measured empirically: CPU (`cores_busy 9.29`) |

## 6. Open uncertainties, with cost estimates

| # | open item | cost | why it matters |
| --- | --- | ---: | --- |
| A | ~~Token sweep stops at 400~~ **DONE session 5** — extended to 6,400; services converge to parity | — | RR advantage does NOT keep growing |
| B | ~~Topology vs framework~~ **DONE session 5** — node count is NOT a factor (0.88–1.13×) | — | fixed cost is the engine's request path |
| C | ~~Chunk vs token~~ **DONE session 5** — no chunk-count trend; per-request overhead confirmed | — | caveat: MiniLM 512-token cap broke constant-token design; ratio still valid |
| A2 | ~~Cause of the 31 % sustained decay~~ **CLOSED session 6** — there is no decay to explain | — | all three rivals (funnelling / accumulation / thermal) moot; the phenomenon was an artifact |
| A3 | ~~Why is RocketRide flat in concurrency?~~ **CLOSED session 7** — native thread oversubscription, not the engine; fixable with thread-limit env vars | — | see `A3_SERIALIZATION_FINDING.md`; product recommendation: expose thread limits as pipeline config |
| A5 | **Optimal thread count** (1 vs 2 vs 4) never swept | ~30 min | 1 beats default under concurrency, but may not be optimal |
| A6 | ~~9.29 vs 1.45 cores~~ **CLOSED session 8** — peak/p95 vs time-average; both real, not interchangeable | — | only the time-average belongs in cost-per-request arithmetic |
| A7 | ~~Re-run the concurrency curve thread-pinned~~ **DONE session 8** — ABA design, n=5, both arms | — | `working/results/reanchor_tuned.json` |
| A8 | ~~interop threads unpinnable~~ **CLOSED session 9** — pinning lands but COSTS 14.3 % @conc8, does nothing @conc2. Leave at default | — | `working/results/anchor_b_interop.json` |
| A9 | **Drift null control did NOT fully hold**: LlamaIndex moved +3.4 % median (range −2.0 % to +19.5 %) between blocks it cannot be affected by | ~1 h | tuning deltas smaller than ~5 % are not trustworthy; relates to open item F |
| A10 | Best-achievable config is concurrency-dependent (default wins below conc≈4, pinned above) | ~30 min | FAIRNESS_BASIS.md needs a per-regime rule, not one setting |
| A11 | ~~Anchor B measured on two different pipelines~~ **CLOSED session 10** — 4-node `embed_probe.pipe` is canonical (FAIRNESS_BASIS.md); session 9's 1.352 is non-canonical. Original: — session 8 used `embed_probe.pipe` (4-node, ratio 1.201), session 9 used `single_node.pipe` (1-node, ratio 1.352). Not strictly comparable | ~20 min | pick ONE pipeline for the anchor and restate it; finding 1d says 1-node≈4-node within 0.88–1.13× but that band covers the gap |
| A12 | ~~RocketRide has no isolated profile~~ **CLOSED session 10** | — | `archive/results/isolated_profile_rocketride.json` |
| A13 | ~~LlamaIndex throughput does not reproduce~~ **CLOSED session 11**; evidence rebuilt session 12 as `working/results/a13_ordering_reconstructed__*.json` — **MIXED PROVENANCE**: the ascending block is log-parsed, the descending and pre-warm blocks are transcribed from the session-11 report table because their JSON was clobbered AND their stdout was piped to grep rather than a log. Spreads, gates and CIs are unrecoverable for those two. — ascending sweeps measure a machine in a low-power state; pre-warm reproduces descending order. Original: — 74.7/s @400tok/c4 in the isolated profile vs 89–91/s in two later runs the same day (+22 %). **Not the RSS sampler** (null control: −0.4 %). Cause unknown | ~1 h | the saturation *shape* is what the operating points rest on; the absolutes are not stable. Relates to open item F |
| A14 | **RocketRide saturation is config- and size-dependent** (c4 tuned/400, c32 tuned/1600, c16 untuned/400, c4 untuned/1600) while LlamaIndex is c4 throughout | ~30 min | 'RocketRide saturates at N' is incomplete without naming config and document size |
| A4 | ~~RR arm fails the gate under every harness~~ **CLOSED session 6** — barrier-synchronised fixed-duration windows fix it (8/10 cells pass) | — | the noise was per-burst boundaries across unsynchronised drivers, not the engine |
| B2 | Re-run sustained sweep until every RocketRide cell passes the 10 % gate | ~45 min | would upgrade the direction from PROVISIONAL to VERIFIED |
| D | RR arm of the real-corpus parity failed the 10 % gate (14.8 %) | ~20 min | the 1.13× point estimate stays PROVISIONAL until it passes |
| E | FastAPI side of Tier 2 never re-measured under protocol | ~20 min | the 2.36× is PROVISIONAL |
| F | Between-session drift cause | **LIKELY CLOSED session 11** — same signature as A13 (runs beginning under light load read low). Needs one confirmation: re-measure a session-6-era number with pre-warm | ~30 min | if confirmed this explains the ±35 % saga and most unreproducible absolutes |
| A15 | **Re-run BOTH isolated profiles with pre-warm**, then redo the optimal-point comparison | ~1.5 h | everything in STEP 2-4 of session 11 is blocked on this |
| A17 | **Pinning crossover concurrency UNVERIFIED for this corpus** — §3.2's "helps above ~4" is from synthetic text; concurrency-1 cost is 3.07x on real documents | ~40 min | affects which config is 'best' at any concurrency |
| A18 | ~~Does the +32 % growth plateau or reset on restart?~~ **RETIRED session 17** — there is no growth; it plateaus | — | resolved by 6-block series |
| A19 | **What triggers the intermittent ~+30 % memory excursion?** Neighbouring-LlamaIndex hypothesis **REFUTED** (session 18, −0.4 %). Host sampling now in the harness; **instrumented but not yet triggered** | unknown, many blocks | it is what makes the gate fail; capacity planning needs the frequency |
| A16 | Does the pre-warm requirement change RocketRide's numbers by the same factor as LlamaIndex's? | ~40 min | if the depression is asymmetric, every cold head-to-head is biased, not merely low |
| G | Why `mps` scales poorly (contention vs power vs driver) | ~1 h | doesn't change the recommendation (pin CPU) |
| H | Is RocketRide's ~17 width tunable from outside engine source? | ~30 min | if yes, the hang behaviour is config, not a ceiling |
| I | Memory advantage (finding 15) is one run, one block size | ~30 min | it's the only genuine RR advantage found; under-replicated |
| J | Nothing generalises off Apple Silicon | — | the device finding is Apple-specific; CUDA differs |

## 7. What has NOT been sent to the team

**Nothing has been sent. Every shared doc is still a draft I can revise freely.**

| doc | audience | status |
| --- | --- | --- |
| `FINDINGS_FOR_WS1.md` | Shashi, Leela | drafted, NOT sent |
| `SCHEMA_PROPOSAL.md` (v0.2) | Leela — needs agreement | drafted, NOT sent |
| `VARIANCE_PROTOCOL.md` | whole team | drafted, NOT sent |
| `working/handoff/` (seeds, collector, fault injection, verify_frameworks, pool_width) | Shashi | drafted, NOT sent |
| `working/handoff/parity/` (replication request) | Shashi | drafted, NOT sent |
| `SCOPED_CLAIM.md` | Ansh, for presenting | drafted, NOT sent — **carries a burst-mode caveat banner** |
| `CROSSOVER_FINDING.md` | — | **ON HOLD, DO NOT SEND** — central framing refuted session 6 |
| `RUNBOOK_LLAMAINDEX.md` | Ansh | VERIFIED by execution, not sent |
| `A3_SERIALIZATION_FINDING.md` | product + team | **drafted session 7, NOT sent** — product finding with a fix |
| `LLAMAINDEX_DEPLOY_QUESTION.md` | Leela, Shashi | **drafted session 7, NOT sent** — a decision, not a change |
| `DOCKER_ARCHITECTURE.md` | Ansh (review gate) | **awaiting approval — NOTHING BUILT** |
| `REBASELINE_PLAN.md` | Ansh (review gate) | drafted session 7 |
| `TOIL_INSTRUMENT.md` | Leela, Shashi (challenge before build) | **pre-registered session 7** |
| `PDF_PIPELINE_NOTES.md` | team | drafted session 7 — **carries session-8 corrections** |
| `PARSER_PREMISES.md` | Leela, Shashi | drafted session 9 — both premises REFUTED |
| `TWO_TIER_PARSER_DESIGN.md` | team | drafted session 9 — design only |
| `READINESS.md` | Ansh, Leela | drafted session 9 — gap list for head-to-head |
| `PARSER_DECISION.md` | **Shashi — he owns the call** | drafted session 10, NOT sent |
| `FAIRNESS_BASIS.md` | whole team | drafted session 8, asymmetry 2 closed session 9 |

**Implication: the schema is UNAGREED.** Keep `working/ws1/schema.py` swappable — it is the only file
that touches the wire format, by design.

## 8. Exact commands

**The current run path is `RUN_ON_EC2.md` §12 (Docker, both arms).** The commands below are the
LOCAL/native ones, kept for laptop work and for the harnesses that predate Phase 2. Anything that
starts a service natively is not the Phase 2 path.

### Corpus (manifest-driven; DONE means verified)

```bash
../.venv/bin/python working/scripts/fetch_govdocs.py 10000    # fetches only what is missing
echo "FETCH EXIT: $?"                                          # 0 = matches the manifest, 1 = not
../.venv/bin/python working/scripts/verify_corpus_manifest.py            # FULL, independent
../.venv/bin/python working/scripts/verify_corpus_manifest.py --subset   # smoke-sized slice
```

### The driver — see §0a for the full flag table

```bash
# thread-propagation gate, no documents, exit 0/4
SMOKE_EXTERNAL=1 SMOKE_PREFLIGHT=1 SMOKE_WORKERS=32 SMOKE_THREADS=1 SMOKE_PORT=8801 \
  ../.venv/bin/python working/scripts/smoke50_parser_in.py

# one leg at a time, resumable, same run dir
SMOKE_LEGS=blast      SMOKE_RUN_DIR=<dir> SMOKE_RESUME=1 ... smoke50_parser_in.py 10000
SMOKE_LEGS=sequential SMOKE_RUN_DIR=<dir> SMOKE_RESUME=1 ... smoke50_parser_in.py 10000
echo "EXIT: ${PIPESTATUS[0]}"    # NOT $? if you piped to tee — tee succeeds when the run dies
```

### Test suites — all four must pass before anything is quoted

```bash
../.venv/bin/python working/harness/test_metrics_shared.py    # 64 exact-value checks
../.venv/bin/python working/harness/test_gates_shared.py      # 60, each gate mutation-tested
../.venv/bin/python working/harness/test_gate_agreement.py    # golden-record, legacy vs gates
../.venv/bin/python working/scripts/regression_selftest.py    # 12 pass + 1 known xfail
```

### Engine and service, natively (laptop only)

```bash
bash working/scripts/start_engine.sh     # idempotent; refuses a second instance on the port
curl -s http://127.0.0.1:5565/version    # readiness AND identity; /ping is auth-gated (401)
WS1_DEVICE=cpu WS1_WORKERS=8 WS1_PORT=8801 nohup bash working/ws1/run_service.sh > logs/ws1.out 2>&1 &
until [ "$(grep -c 'warm in' logs/ws1.out)" -ge 8 ]; do sleep 3; done
```

`/health` returning 200 does **NOT** mean ready — it is answered by one worker. Count `warm in`
lines natively; in a container read `/health`'s aggregate `warm_workers` (and the driver refuses
`warm_workers > declared_workers`).

### Exfil

```bash
bash working/scripts/exfil_s3.sh working/results logs/<run>.log   # -> s3://.../ansh/<stamp>/
```

## 9. Traps that have already cost time

| trap | detail |
| --- | --- |
| `curl -w '%{http_code}' \|\| echo 000` | on failure curl prints `000` **and** exits non-zero, so `\|\|` appends a second `000` → `"000000"` ≠ `"000"` → a dead server passes a health check. Assign the fallback, don't append |
| `setrlimit(RLIMIT_NPROC, …)` on macOS | requesting a higher soft limit **succeeds** but silently clamps the *hard* limit to `kern.maxprocperuid` (8,000), permanently. Never call it |
| Process census by cmdline grep | uvicorn workers spawn via multiprocessing; their cmdline has no "uvicorn". Undercounted our service **173×** (19.6 MB vs 3,404 MB actual). Walk the tree from a root PID |
| `hash()` for seeds | salted per interpreter — same config gave 44 injected faults one run, 66 the next. Use `working/harness/seeds.py` (sha256) |
| `asyncio.to_thread` default pool | `min(32, cpu+4)` = 18 here, **not** whatever your Semaphore says |
| `.pipe` files | need `source`, `components` first, literal GUID `project_id`. One live task per `project_id` — N concurrent tasks needs N distinct files |
| Engine tarball | extracts **flat**; `--strip-components=1` destroys it |
| SDK `get_server_info()` | broken — `public=True` is stored and never read. Use `GET /version` |
| Model load / engine cold start | ~36 s and ~60 s respectively. Must be outside every timed region |
| pool_width without the guard | if offered concurrency < true width it returns the OFFERED value at 0.0 % spread — confidently wrong, looks precise. Use `working/handoff/pool_width.py` |

## 10. Layout

```
<clone>/
  working/harness/        THE SHARED LIBRARY — everything below is current architecture
    metrics_shared.py       arm-agnostic metrics, pure functions, settled decisions frozen
    gates_shared.py         both teammates' gate dialects + union + the record adapter
    memory_sources.py       cgroup reader; quote `anon`, never summed RSS
    jsonl_stream.py         crash-durable records + resume; thread-safe writer
    rr_credentials.py       endpoint/key resolution, runs on `harness` import
    collector.py            psutil tree sampler (RSS/USS/PSS, 0.5 s, out-of-process)
    collector_proc.py       parent-side handle; spawns the sampler in its own interpreter
    chunk_hash.py / content_sanity.py / extraction_fidelity.py / tika_reference.py / goodput.py
    ws1_service.py          service lifecycle + PID-by-listening-socket resolution
    test_metrics_shared.py / test_gates_shared.py / test_gate_agreement.py
  working/ws1/            THE LLAMAINDEX SERVICE — schema.py (wire contract) | pipeline.py
                          (no HTTP) | service.py (HTTP + /health with warm_workers) | run_service.sh
  working/scripts/        smoke50_parser_in.py (THE DRIVER) | fetch_govdocs.py (manifest-driven)
                          verify_corpus_manifest.py | start_engine.sh | exfil_s3.sh
                          install_awscli_userdir.sh | regression_selftest.py | setup_probe.py
  working/pipes/          product_pdf.pipe (THE MEASURED PIPE, canonical f61165f7cf7ab1db)
                          a3_env_torch.pipe (thread probe: env_probe + embedding_transformer so
                          torch is loaded in the same task process) | a3_env.pipe (torch-less)
  working/nodes/          benchmark-only engine nodes; env_probe is the one Phase 2 needs.
                          NONE carry requirements.txt, so copying them pays no constraints recompile
  working/results/        raw JSON + smoke_metrics_<stamp>/ per-doc JSONL and sampler streams
  corpus/govdocs1/pdfs/   10,000 GovDocs1 PDFs, manifest-verified
  docker/                 Dockerfile.llamaindex (serves uvicorn) | Dockerfile.rocketride
  engine/                 the RocketRide 3.3.1 bundle (x86-64; extract flat)
  reference-fresh2/       teammates' repos, re-cloned fresh — treat older clones as void
```

Key docs: **`RUN_ON_EC2.md` §12 is the run path.** Memory comparability → session 30 + §0a;
gate dialects → `gates_shared.py` docstring; bug reports → `BUG_CHUNK_DUPLICATION.md` (trigger
corrected to ≥64 chunks), `BUG_NUL_TRUNCATION.md`; topology confound → `MATCHED_LAYERS.md`.

<!-- trap appended 2026-08-10: `setsid` does not exist on macOS. `nohup ... &` alone survives the
     parent shell. A `nohup setsid ...` invocation dies instantly with "setsid: No such file or
     directory" and, if unverified, looks exactly like a running job. Verify every detached launch
     BY PID, never by assumption — this failure has now occurred twice in this project. -->

<!-- trap appended 2026-08-15: a JSON `.pipe` file in a working tree on this Mac is rewritten by
     a format-on-save daemon within seconds — a fresh clone showed ` M` immediately, with three
     different hashes across three reads. It expands compact JSON, so our already-expanded pipe is
     untouched and a teammate's compact one is not. NEVER hash a .pipe from a working tree; use
     `git show HEAD:<path> | shasum -a 256`. This produced a false accusation that a teammate's
     pipe had drifted; his committed bytes were correct all along. -->
