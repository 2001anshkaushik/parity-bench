# Phase 1 → Phase 2 carryover

**Audience:** a session with no memory of the Phase 1 (PDF) benchmark campaign, starting video
benchmarking in this repository.

**What Phase 1 was.** A three-way comparison of document-ingestion throughput and correctness:
the RocketRide engine against LlamaIndex (this repo), against Haystack, and against LangGraph
(two teammates, separate repos). One shared 5-node pipeline, one shared corpus family
(GovDocs1 PDFs), on `c7i.8xlarge` hosts. This repo is the LlamaIndex harness.

**How to read this file.** Every claim below is sourced from a file in this repository, its git
history, or a run artifact. Where something could not be verified from those, it says UNKNOWN.
Nothing here is reconstructed from memory or from what seems plausible. Where a claim contradicts
an existing document in this repo, the contradiction is flagged rather than quietly resolved.

**Written at:** branch `video-bench`, forked from `main` at `17f77aa`.

---

## A. Instrument defect register

### The count, and two discrepancies you must know about

`publishable/STATE.md:130` heads the register **"Defect register, sessions 20–34"** and
`:135` states **"Twenty-one instrument defects in twenty-three sessions."**

* **Discrepancy 1 — the heading is stale.** The register's own entries run to session 42
  (defect #39). The heading was not updated as entries were appended. The entries are correct;
  the heading is not.
* **Discrepancy 2 — the numbering starts at #19.** Defects **#1–#18 are not listed in any
  register in this repository.** They are referenced only by number. So "twenty-one" counts
  exactly the entries #19–#39 (21 entries — arithmetic checks). **The campaign's true total is
  UNKNOWN and is at least 39.** Do not repeat "twenty-one defects" as a campaign total.

**Verified count of registered defects: 21 (#19 through #39, inclusive, none skipped).**

### The register

Direction of bias is stated as it affects the *comparison*: "against RR" means the defect made
RocketRide look worse than it was; "for RR" means it flattered RocketRide; "neither" means it
corrupted a number without favouring an arm.

| # | Symptom | Root cause | Bias | Detected by | Fix landed |
|---|---|---|---|---|---|
| 19 | 1.53 → 13.07 docs/s on the same 5-doc fixture | a Tika reference gate ran INSIDE the timed loop, RocketRide arm only | **against RR** (~8.5×) | fixture rate implausible | all our gates moved post-loop |
| 20 | model bake did not reach the runtime loader | `llama-index-embeddings-huggingface` ignores `HF_HOME` (uses `LLAMA_INDEX_CACHE_DIR`/platformdirs) | neither | own null control was passing when it had to fail — leaking from `~/.cache` | `LLAMA_INDEX_CACHE_DIR` set in the LI image |
| 21 | readiness poll never completed | counted distinct worker PIDs; uvicorn workers share one listening socket and kernel accept bias routes to few | neither | poll ran to timeout on a warm service | aggregate `warm_workers` marker-file count |
| 22 | credentials resolved from a gitignored `.env` | absent on a fresh clone | neither | fresh-clone failure | `harness/rr_credentials.py`, one resolver |
| 23 | `warm_workers=33` of 32 declared | container PID namespace restarts at 1 on `docker start`; marker dir reused across runs | neither | census exceeded population | supervisor key = pid + start time; driver refuses > declared |
| 24 | external mode honoured in 1 of 6 discovery sites | per-site reimplementation | neither | code audit | single discovery path, both arms |
| 25 | gate adapter contradicted the legacy path | expected-empty never plumbed; same doc classified differently per leg | neither | two paths disagreed on one document | one `classify_ok` rule for both legs |
| 26 | `peakRSS` reported as a footprint | it is the peak of a SUM of per-process RSS; shared pages counted once per process | **against LI** (32-worker fork tree inflates most) | 34.4 GB harness figure vs 20.06 GiB `docker stats` | `harness/memory_sources.py`; cgroup `anon` is the quotable figure |
| 27 | a killed run lost everything | records buffered in memory, written once after the loop | neither | a kill at ~7k of 10k | `harness/jsonl_stream.py` — append+flush per record, resume |
| 28 | fetcher printed `DONE total_pdfs=10000` on a 9,800-file corpus | counted its own arithmetic (`have += n`), never the disk or the manifest | neither | independent verifier disagreed | manifest-driven fetcher; DONE means verified |
| 29 | RR blast p50 1120 s vs LI 2.05 s | LI stamped `submit_ns` at admission, RR before the semaphore — `gather` starts all coroutines at once, so every RR doc stamped at batch open | **against RR** (~550× on the printed gap) | submit-stamp spread measured: LI 97.6 % of leg, RR 0.0 % | both arms record `enqueue_ns` AND `admit_ns`; `test_blast_symmetry.py` |
| 30 | 84,960 MB peakRSS printed beside a 1,025 MB cgroup anon | memory table populated only in the sequential leg, keyed by arm; the metrics line beside it was a blast-leg peak | neither (two different measurements) | 83× vs a printed 1.48× sharing factor | memory captured per arm PER LEG |
| 31 | cgroup `anon` printed under a "peak" heading | read once, AFTER the leg | neither | 2-proc / 1,025 MB reading after the engine released | sampled on the collector's 0.5 s tick |
| 32 | 10k sequential died at doc 9,629; 371 contiguous failures | **UNCONFIRMED.** Server default `ttl` is 900 s IDLE (`ai/constants.py:55`), reset only at submission; our per-doc client deadline was 1800 s — an inversion | neither | 371 identical "pipeline is not running" records | `ttl=7200` passed explicitly; K=3 consecutive-failure breaker. **Root cause still UNKNOWN** |
| 33 | both `rr` images built green, then crash-looped | image recipe omitted the onnxruntime `1.20.1→1.20.2` patch (1.20.1 was never published to PyPI; the engine compiles all requirements at boot) | neither | container crash loop on the box | patch + build-time boot assertion (`docker/bootcheck_rocketride.py`) |
| 34 | `cpu_utilization` 1.5832, flagged INVALID | divided by the DRIVER's `taskset` affinity (8) instead of the service container's cpuset (24) | **against RR** (invalidated a real result) | `cpu_utilization_valid` flagged rather than clamped | `experiment_common.service_available_cpus()` reads the container's own cgroup |
| 35 | `engine_side_concurrency` 281.266 against threads=24 | summed completion OFFSETS as if they were per-file durations; `upload_time` is an offset from batch open | **for RR** (impossible parallelism) | value exceeded the thread count | `classify_upload_time()`; publishes only under duration semantics |
| 36 | `NameError: LI_CONTAINER`, post-loop, after 9,975 records | bare name inside an `if EXTERNAL` branch; `py_compile` cannot see undefined names | neither (destroyed a run) | the run itself | `harness/static_names.py` + suite + smoke section 0 |
| 37 | smoke passed with the engine UNPINNED at torch=16 | thread pins read back on ONE arm only | **for RR or against — UNKNOWN**, the arms were simply not matched | operator noticed the container lacked the `-e` vars | smoke section D: both arms, absent-pins-fail-first |
| 38 | census "offered 9975 = successful 0 → FAIL" on both arms | under `SMOKE_LEGS=blast` the verdict path read the empty SEQUENTIAL set while metrics read the blast set | neither (a false FAIL) | 9,975 records existed and metrics computed fine | gates follow the leg that ran; `gates_shared.not_run()`; `scripts/rederive_gates.py` |
| 39 | `blast_batchpos` warm_n=0 1.665 docs/s vs warm_n=64 2.7664 on the same leg | ONE `enqueue_ns` stamped before BOTH runners; arms run sequentially, so arm 2's batch-open predated its own leg by arm 1's entire leg | neither (corrupts a latency column) | operator queried it as a "minor windowing artifact" | per-arm stamps; `rederive_gates.py` corrects existing records via `min(admit_ns)` |

**Pattern worth carrying into Phase 2, stated in STATE.md:135:** in this project the instrument
has been wrong far more often than the system under test. Of the 21 registered defects, **zero**
were product defects found by us in that window. Two (#19, #29) were direction-asymmetric and
both ran against RocketRide; one (#35) flattered it. **The instrument has no loyalty.**

**Recurring class — "the one-armed check" (#24, #25, #37).** Three separate times, a check was
honoured on one arm and not the other. If you write a check in Phase 2, write it as one function
fed by both arms.

---

## B. Harness module contracts

For each: what it guarantees, what it assumes, which defect fixes it carries, what a caller must
never do. **The assumptions section is the one that matters for video** — these modules were
built around PDF-shaped input and several assumptions will mislead rather than fail loudly.

### `working/harness/metrics_shared.py` (288 lines)

* **Guarantees.** Pure functions, no I/O, no globals. Every definition cites the teammate source
  it was adopted from. Unavailable ⇒ `None`, never `0` ("a failed run cannot masquerade as a
  fast one"). `cpu_utilization > 1.0` is flagged INVALID, never clamped — that flag is what
  surfaced #34.
* **Assumes.** Percentiles are **nearest-rank, no interpolation** (settled team decision).
  `perf_window` slices by **completion rank**. The cost-series contract is
  `(ts_epoch_s, cpu_total_s_cumulative, rss_mb)` tuples.
* **PDF-SHAPED — will mislead on video.**
  1. **`warm_n` by completion rank assumes many short records.** With 10,000 PDFs, dropping 64
     completions is a small fraction. With, say, 200 videos, dropping 64 discards a third of the
     run — and it discards the *fastest* 64, inflating what remains. `WARM_N_PRIMARY` is already
     `0` (driver-side warm-up replaced it); **keep it at 0 for video** and do warm-up in the
     driver on disjoint items.
  2. **Percentiles over a small n are unstable.** Nearest-rank p95 over 200 records is the 190th
     value — a single outlier. PDF runs had 10k records; video runs will not.
  3. **`docs_per_s` as a headline is scale-dependent** — see §F, trap 6. On heavy-tailed inputs
     a short run understates converged throughput by a factor that grows with concurrency. Video
     will be *more* heavy-tailed than PDFs, not less.
  4. **Timing granularity** is nanosecond epoch stamps; fine for seconds-to-minutes items.
     UNKNOWN whether anything breaks for hours-long items — no such run has happened.
* **Carries fixes:** #26 (peak RSS naming), #29 (mode labels), #34 (`available_cpus` is a
  parameter — the CALLER must supply the service's allocation, not its own).
* **Never.** Never pass the driver's `os.cpu_count()` or `sched_getaffinity()` as
  `available_cpus` for a containerised service (#34). Never add a metric neither teammate has —
  this module exists to be comparable, not complete.

### `working/harness/gates_shared.py` (600 lines)

* **Guarantees.** Both teammates' gate dialects implemented separately and reported as three
  verdicts (theirs, theirs, and the union). `gate_verdict` is fail-closed: PASS is `True`
  exactly. `not_run()` reports NOT RUN with a denominator for a gate whose leg did not execute
  (#38) — but a leg that RAN and produced zero records is still a FAIL.
* **Assumes.** `EMBED_DIM_DEFAULT = 384` (overridden by a per-run probe). `NORM_TOL = 1e-3`
  absolute per vector. `NEAR_DUP_FACTOR = 1.9` reported, never gated.
* **PDF-SHAPED — will mislead on video.**
  1. **`repeat_factor` / `self_duplication` assume an ordered list of text chunks per record.**
     For video the emitted unit is UNKNOWN (frames? segments? transcript chunks?). If the unit
     is not an ordered list with stable hashes, this gate silently checks nothing —
     `self_duplication` returns `PASS: False` with `vacuous: True` on empty input, which is
     correct, but a gate that never fires because the field is absent is worse.
  2. **`duplication_verdict`'s `over_chunk_trigger` is `>= 64 chunks`** — that is the engine's
     `maxDocuments` flush threshold for the *embedding_transformer text path*. A video pipeline
     may not use that node at all. **Do not carry the 64 predicate over without re-deriving it.**
  3. **Census keys on offered COUNT (Leela) and on document NAMES (Shashi).** Both assume one
     record per submitted item. If a video yields many records per input, both censuses break.
  4. **`CENSUS_EMPTY_POLICY=report`** exists because ~1.3 % of real PDFs defeat an extractor.
     The equivalent rate for video is UNKNOWN and must be measured, not assumed.
* **Carries fixes:** #25 (one `classify_ok` for both legs), #38 (`not_run`, NOT-RUN-aware
  `three_verdicts`).
* **Never.** Never let a NOT RUN gate fold into a suite conjunction as a pass. Never gate on
  `ground_truth_match` or `parity_fixture` — implemented for parity, but they have zero call
  sites in the teammate's own runner and gating on them would diverge from him.

### `working/harness/collector.py` (592 lines)

* **Guarantees.** Out-of-process sampler (running it in-thread was measured slowing the harness
  100× and biased *toward* the external-engine arm). Walks a full descendant tree from a root
  pid via one system-wide scan. Rolls forward CPU of dead PIDs so short-lived per-task children
  are not lost. Since #31, reads the container's cgroup on the same tick.
* **Assumes.** `DEFAULT_INTERVAL_S = 0.10` (drivers pass 0.5). `USS_DECIMATION = 20` ticks —
  **USS/PSS are sampled every 20th tick only**, so a run shorter than 20 ticks collects neither
  and reports `None`. `SYSTEM_DECIMATION = 10`.
* **PDF-SHAPED — will mislead on video.** A 0.5 s tick over a 60-minute PDF run gives ~7,200
  samples. For a short video run the same interval may give too few for a stable peak, and the
  USS/PSS decimation makes the deduplicated cross-check disappear entirely. **Check
  `cgroup_samples` in the output before trusting any memory figure.**
* **Carries fixes:** #26, #31.
* **Never.** Never sample by process NAME — a five-day-old unrelated engine was once counted
  that way. Never treat summed RSS as a footprint.

### `working/harness/memory_sources.py` (229 lines)

* **Guarantees.** Every memory figure named for what it is, never merged. Source hierarchy, best
  first: cgroup `memory.peak` (kernel HWM, unsampled) → cgroup `anon` (what BOTH teammates
  report — **this is the quotable figure**) → summed PSS → summed RSS (**never quote**). Flags a
  summed RSS that exceeds the cgroup's own limit as impossible-as-a-footprint. Also holds
  `parse_cpuset` / `cgroup_cpuset_count` (#34).
* **Assumes.** cgroup **v2**. On cgroup v1 or macOS every field is `None` — correct, but the
  caller must notice.
* **PDF-SHAPED.** Mostly input-agnostic. One caveat: the over-count factor of summed RSS scales
  with the number of processes sharing pages, so a video arm with a different process topology
  will have a different (and still unknown) sharing factor. Do not carry a sharing factor across
  arms or legs.
* **Carries fixes:** #26, #30, #31, #34.
* **Never.** Never quote summed RSS. Never apply one leg's sharing factor to another leg.

### `working/harness/provenance_leela.py` (161 lines)

* **Guarantees.** Emits the **24 fields** a teammate requires for a run to be publishable, under
  HIS key names, so neither side has to re-derive.
* **Assumes.** Fields like `parser`, `chunk_config`, `embedding_model` are text-pipeline shaped.
* **PDF-SHAPED — will mislead on video.** `chunk_size=4000, chunk_overlap=200` and
  `parser="pypdf"/"tika-3.2.3"` are hard-coded at the call site in
  `working/scripts/smoke50_parser_in.py:989-990`. **On a video pipeline these become confidently
  wrong provenance** — worse than absent, because a reader will believe them.
* **Carries fixes:** the requirement itself came from a teammate's post-`a5c3b5d` rule.
* **Never.** Never let a provenance field state something the run did not do. **KNOWN STALE
  TODAY:** `smoke50_parser_in.py:986` still reports `warmup_policy` as "metric-side, first 0
  completions excluded" when warm-up is now driver-side with 25 disjoint documents. That string
  is wrong on `main` right now — fix it before quoting provenance from any new run.

### `working/harness/jsonl_stream.py` (115 lines)

* **Guarantees.** One record appended and flushed as each item completes, so a kill costs at most
  the in-flight item. Thread-safe (`threading.Lock` around write+flush). A torn LAST line is
  tolerated and reported; an unparseable line that is NOT last raises rather than silently
  resuming from corruption.
* **Assumes.** `fsync_every = 0` by default — records reach the OS page cache, which survives
  process death but **not host power loss**. This is deliberate (10k fsyncs per run) and
  documented in the module.
* **PDF-SHAPED.** Minimal exposure. One consideration: video records may carry far more per-item
  payload (frame hashes, per-segment vectors). Watch the JSONL size — a per-record blob that was
  negligible for PDFs may not be.
* **Carries fixes:** #27.
* **Never.** Never open the file with `"w"` — resume depends on append. Never assume
  multi-PROCESS safety; the lock is per-process only.

### `working/harness/static_names.py` (84 lines)

* **Guarantees.** Finds names a function loads that are neither local, free, module-level, nor
  builtin — **without executing any branch**. Uses Python's own `symtable`, so scoping is real
  rather than heuristic. Null-controlled on the live #36 defect before that defect was fixed: it
  reported `LI_CONTAINER`/`RR_CONTAINER` at the exact lines, then swept 101 files clean.
* **Assumes.** Static analysis only.
* **Stated limits (in the module).** Module-level use-before-definition is NOT caught. Names
  created dynamically (`setattr`/`exec`) would false-positive — this repo has none. A star import
  makes a file unverifiable and is REPORTED as such rather than skipped.
* **Carries fixes:** #36.
* **Never.** Never remove it from `smoke_phase2` section 0 — its whole value is running before a
  long run, not after.

### `working/scripts/smoke_phase2.py` (451 lines)

* **Guarantees.** Five checks, under 5 minutes, exit non-zero on any failure: (0) static gate,
  (A) duplication fixture, (B) golden record, (C) read-backs (cpuset in effect, worker count,
  corpus vs manifest), (D) thread pins on BOTH arms.
* **Assumes — and this section is almost entirely PDF-shaped.**
  1. `CORPUS = corpus/govdocs1/pdfs`, globbed `*.pdf`.
  2. `FIXTURE_SHA` — **five hard-coded PDF sha256 prefixes** that duplicated on the stock engine.
     Meaningless for video.
  3. The golden record compares chunk-hash lists from a prior PDF run.
  4. Section A's control direction: on a STOCK engine the fixture MUST duplicate; if it does not,
     the conclusion is that the FIXTURE is broken, not that the patch is unneeded.
* **Carries fixes:** #36 (section 0), #37 (section D, absent-pins-fail-first so two unpinned arms
  agreeing cannot pass).
* **Never.** Never run a long leg without it. Never weaken section D's ordering — absence must
  fail before agreement is checked.

---

## C. The box — exact working commands

> **WARNING: `publishable/RUN_ON_EC2.md:496-512` IS STALE.** It still shows `--cpus 32`,
> `WS1_WORKERS=32` and image tags `rr-engine:3.3.1` / `ws1-llamaindex:x86_64`. Those were
> superseded by the cpuset switch and the patched/stock image split. **The corrected
> invocations below exist in no other file in this repo** — they were established in session and
> are written down here for the first time. Treat this section as authoritative over
> `RUN_ON_EC2.md` for container startup, and consider fixing that file early in Phase 2.

### Build both engine images

```bash
docker build --build-arg RR_DUP_PATCH=1 -f docker/Dockerfile.rocketride -t rr:patched .
docker build --build-arg RR_DUP_PATCH=0 -f docker/Dockerfile.rocketride -t rr:stock .
docker build --build-arg EXPECT_ARCH=x86_64 -f docker/Dockerfile.llamaindex -t li:phase2 .
```

The RocketRide build contains a **throwaway boot-check stage** that starts the engine, waits for
the listener and performs a real SDK WebSocket handshake — the build fails with the boot log if
it does not come up (#33). It needs network at build time (the constraints compile). Its compiled
constraints cache is COPIED into the final image, so first container boot skips the 10–30 minute
compile. `RR_BOOT_CHECK=0` skips the check and ships an EMPTY cache; the skip is recorded in
`/opt/rocketride/.boot-check`.

### Start both arms — arms run ONE AT A TIME, never concurrently

```bash
docker rm -f rr li 2>/dev/null

docker run -d --name rr \
  --cpuset-cpus 0-23 --memory 58g \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e VECLIB_MAXIMUM_THREADS=1 -e NUMEXPR_NUM_THREADS=1 -e TORCH_NUM_THREADS=1 \
  -p 5565:5565 \
  rr:patched

docker run -d --name li \
  --cpuset-cpus 0-23 --memory 58g \
  -e WS1_WORKERS=24 \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e VECLIB_MAXIMUM_THREADS=1 -e NUMEXPR_NUM_THREADS=1 -e TORCH_NUM_THREADS=1 \
  -p 8801:8801 \
  li:phase2
```

The driver runs on the **complementary** cores:

```bash
taskset -c 24-31 python3 working/scripts/<driver>.py
```

### Operational rules learned the hard way

1. **`--cpuset-cpus`, NOT `--cpus`.** A CFS quota and a cpuset are two different limiters; do not
   set both. `smoke_phase2` section C reads `NanoCpus` back and FAILS if `--cpus` is still set.
2. **All six thread variables, on BOTH containers, every time you recreate.** Omitting them once
   produced defect #37 — the engine ran unpinned at torch=16 while LlamaIndex ran pinned at 1,
   and two N=1000 probes measured that mismatch as though it were the product. **A container
   recreated without these silently produces a wrong number.**
3. **`WS1_WORKERS=24`, matching the cpuset width.** The image bakes 24
   (`docker/Dockerfile.llamaindex:144`); passing it explicitly is belt-and-braces. A worker count
   above the cpuset width oversubscribes.
4. **The utilisation denominator must come from the SERVICE container's cgroup, never from the
   driver.** With the driver on `taskset -c 24-31`, `sched_getaffinity` in the driver returns 8
   while the service has 24 (#34).
5. **Run the smoke before every long run**, and read section D's output — both arms must report
   the same `torch intra`.
6. **Arms run one at a time.** Both containers share cpuset 0-23; running them concurrently means
   they contend and every number is contaminated.
7. **`${PIPESTATUS[0]}`, never `$?`, after a pipe into `tee`** — `$?` reports tee's status, which
   is always 0. Every runbook example in this repo uses `${PIPESTATUS[0]}`.
8. **First boot on a fresh image is 10–30 minutes at near-zero CPU** unless the constraints cache
   was carried forward. Do not interpret it as a hang.
9. **Verify the image label after any rebuild:**
   `docker inspect -f '{{index .Config.Labels "benchmark.rocketride.duplication_patch_applied"}}' rr:patched`
   Provenance reads this label rather than asserting a value.

---

## D. What never ran, and why

| Planned | Status | Blocker | Analysis missing as a result |
|---|---|---|---|
| **Fault-isolation experiment** (`working/scripts/exp_fault_isolation.py`) | **WRITTEN, NEVER RUN** — zero result JSONs in `working/results/` | never scheduled before the campaign closed | no resilience measurement for either arm; the poison-document protocol is untested |
| **Data-isolation experiment** (`working/scripts/exp_data_isolation.py`) | **WRITTEN, NEVER RUN** — zero result JSONs | as above | no cross-tenant leak measurement; **and its mandatory null control never ran**, so the detector is unvalidated. A zero from it would currently prove nothing |
| **Batched-arm 10k** (`exp_batched_blast.py`) | two N=1000 probes ran ON THE BOX; **both superseded** (#34, #35, #37 — measured with the engine unpinned). No 10k. No result JSON in this repo | thread-pin defect discovered after the probes | the batch-scheduler comparison rests on operator-reported numbers, not on artifacts readable here |
| **Pinned sequential 10k** | UNKNOWN — no result JSON in this repo | — | **no speedup or parallel-efficiency figure exists**, because that ratio needs the sequential leg's `chunks_per_s` on the same corpus |
| **The 52.8 % / 52.9 % cross-harness corroboration** | **VOID**, banner in STATE.md | measured with the engine unpinned (#37) | the strongest cross-harness agreement in the campaign is retracted pending a pinned re-take |
| **`cross_arm`, `verify_output.py`, `blast_radius` gates** | DECLINED, deliberately | scoped out as architecture changes | our gate suite is narrower than a teammate's; `cross_arm` in particular would probably have FAILED us for a non-defect reason (our two arms use different extractors) |
| **`#32` root cause** | **OPEN** | the ttl-inversion hypothesis was never confirmed | why the 10k sequential died at 9,629 is still UNKNOWN. The mitigation (ttl=7200, K=3 breaker) is in place regardless |
| **S3 artifact listing from this machine** | UNKNOWN | `aws s3 ls` returns `NoCredentials` on this laptop (`aws login` needed); `boto3` absent | `publishable/RUN_INVENTORY.md` reports the box/S3 rows as UNKNOWN. **Regenerate it on the box** — the generator is committed |

**Bluntly: no result JSON in this repository is quotable.** All 96 parsed local files are macOS
wiring validation or pre-stamp laptop probes. `publishable/RUN_INVENTORY.md` states this at the
top of its section 2. The quotable Phase 1 artifacts live on the box and in S3.

### Correction, 2026-08-20 — Section D described the laptop's tree, not the campaign

This section was written from the tree reachable at `17f77aa`. The box's `main` carried a
commit that never reached origin — `88eeef7` ("phase 2: 10k per-doc blast + batched + seq200,
run inventory"), diverged from `0a117e3` — recovered on 2026-08-20 via
`s3://rocketride-benchmark-data/ansh/rescue-20260820/parity-bench-all-88eeef7.bundle`
(bundle verified: complete history) and merged to `origin/main` as `c06673a`
(128 files added, `publishable/RUN_INVENTORY.md` regenerated; the divergence's origin side had
touched only the tickets file, so the merge is conflict-free by construction). Rescue ref:
`origin/rescue/box-main-20260820`. Three rows above are corrected by its contents:

* **"Batched-arm 10k … No 10k. No result JSON in this repo"** — now false on `main`:
  `working/results/exp_batched_blast__20260818T150551Z__373adce246fc.json` is the batched arm
  over 9,975 (operator-reported spans: blast_batchpos 5967.518 s vs per-doc 3578.954 s), beside
  the per-doc 10k blast `smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json` (9,975,
  workers=24 threads=1 C=32, LI blast span 2381.162 s).
* **"Pinned sequential 10k — UNKNOWN … no speedup or parallel-efficiency figure exists"** — a
  pinned sequential run EXISTS at n=200:
  `smoke50_parser_in__20260818T155557Z__4c468512ae75.json` (complete, 198/200 ok on both arms,
  workers=24 threads=1 C=4; operator-reported spans RR 925.333 s vs LI 408.007 s). Still true:
  no sequential at 10k. The speedup divisor Phase 2's LEGS section wants does exist at n=200.
* **"No result JSON in this repository is quotable"** — true of the laptop tree when written;
  false of `main` since `c06673a`, which carries the box-run JSONs stamped Linux/x86_64 and
  inventoried as publishable-platform rows in the regenerated `RUN_INVENTORY.md`.
* Also stale in this section's table: **"S3 artifact listing from this machine — UNKNOWN
  (NoCredentials)"** — the laptop reads the bucket via `AWS_PROFILE=rocketride` (SSO) as of
  2026-08-20; the default profile remains credential-less.

The claims above the correction are left as written (this file does not rewrite its own
history); read them as "true of the laptop's view on 2026-08-19."

### Correction #2, 2026-08-21 — a pinned sequential 10k DOES exist

The 2026-08-20 correction's sentence "Still true: no sequential at 10k" is itself wrong.
`smoke50_parser_in__20260816T220254Z__4151041d3ea9.json` is a **sequential leg at n=10,000**
(`legs_run: ["sequential"]`, workers=32 threads=1), with thread pins **read back in-artifact on
both arms** (`pinned.torch_threads_measured`: env_probe in-task on RR, per-worker `/health` on
LI, all six variables = 1, torch intra = 1). It is **partial — the defect #32 casualty**: the
leg died at ~doc 9,629 (9,540 usable records of 9,628 written; the 371-contiguous-failure
signature in Section A's register row #32 is this run). Its own sampler
(`run10k/sampler_rr_sequential.jsonl`) predates the collector's `system_tick` channel, so its
load cleanliness rests on process forensics (the background loop's parent shell started
2026-08-18 02:15:20; this ran 2026-08-16), not on in-artifact load samples.

---

## E. Directory hygiene

Parent directory: `/Users/ansh/RocketRide/Benchmarking/`.

| Directory | Status | Notes |
|---|---|---|
| **`benchmark-A/`** | **CURRENT — THE ONLY AUTHORITATIVE DIRECTORY** | this repo. All harness code, results, docs |
| `rocketride-server/` | CURRENT (read-only reference) | upstream engine source clone, HEAD `11389361`. **SHALLOW (1 commit)** — no history. Read for source verification; never edit |
| `ref-p2/`, `ref-final/` | CURRENT-ish (read-only) | most recent teammate clones (`leela/`, `shashi/`). Snapshots, not live |
| `reference/`, `reference-fresh/`, `reference-fresh2/`, `reference-latest/`, `reference-now/` | **STALE** | five older generations of the same two teammate clones. Kept only as history |
| `benchmark-A.backup-prerestore/` | **STALE — DANGEROUS** | a pre-restore snapshot of this repo. Looks authoritative, is not |
| `benchmark (Leela)/` | STALE (other person's repo, local copy) | HEAD `3fa0c30`. Not ours to edit |
| `rocketride-bench (Krish)/` | STALE (other person's repo) | HEAD `5a61b8d` |

**Rules:**

* **Never read code out of `benchmark-A.backup-prerestore/`.** It is a stale copy of this repo
  and the single easiest way to resurrect a fixed defect.
* **Never copy code out of any `reference*` directory.** They are teammate snapshots. Adopt
  their *definitions* with a file:line citation (as `gates_shared.py` does); do not vendor their
  code.
* **Re-clone teammate repos before any comparison** — during Phase 1 they moved almost daily, and
  several sessions found the previous day's clone already superseded.
* **`benchmark-A/` only** for anything you write.

---

## F. Traps — mistakes actually made, and the tell that caught each

1. **A null control that passed when it had to fail.** The model-bake check was leaking from
   `~/.cache`, so four earlier "passes" were false. **Tell:** the control was asked to fail and
   did not. *If a control cannot fail, it is not a control.*
2. **Two components agreeing while both wrong.** The duplication defect is invisible to cross-arm
   equality gating: when both arms share an engine, both duplicate identically and equality
   passes. **Tell:** only a per-side, reference-free repeat detector (`self_duplication`) sees it.
   *Agreement between two things that share a cause is not evidence.*
3. **A green build that could not run.** Both engine images built successfully and crash-looped
   (#33). **Tell:** nothing in the build had ever executed the artifact the image exists to run.
   Now a boot-check stage does.
4. **`py_compile` mistaken for validation.** #36 passed compile and every local run because the
   name lived in an untaken branch. **Tell:** the branch was `if EXTERNAL`, and local runs are
   never external. *Parsing is not name resolution.*
5. **A stale fact surviving in prose while dying in code.** The onnxruntime patch was documented
   in this repo's own STATE.md §1, applied in an earlier image, present in a teammate's
   Dockerfile — and absent from our Phase-2 recipe from the day it was written (verified: zero
   occurrences in that file's entire git history). **Tell:** it crash-looped. *A fact recorded in
   a document is not a fact enforced by a build.*
6. **A number that was reproducible AND wrong.** Simulation showed a 1,000-document run
   understates converged throughput by ~3.4× with a run-to-run spread of ~2.5 % — three reps
   would agree closely and all three would be wrong by the same factor. **Tell:** the same
   distribution replayed at different n. *Precision is not accuracy.* Expect this to be worse for
   video, whose duration distribution is likely more heavy-tailed than PDF page counts.
7. **A fail-closed gate over an empty input.** #38 shipped "FAIL" on both arms from zero records
   while 9,975 real records sat in a file the metrics block read correctly. **Tell:** metrics and
   gates disagreed about whether the run existed. *A fail-closed verdict over an empty input is
   indistinguishable from a real failure — that is how a false product finding gets published.*
8. **Three counting errors in one metric.** The lines-of-code comparison had a slicer that ran
   past end-of-file, a layer mapping that counted a dependency manifest as a pipeline definition,
   and a counter that never stripped comments from files named `Dockerfile.<suffix>`. **Tell:** an
   independent second method (AST + tokenize) disagreed with the first on 4 of 25 cells.
9. **A conclusion that flipped on whitespace.** The same LOC metric moved across the 1.0× line
   depending purely on JSON indentation of one file. **Tell:** deliberately recounting the same
   artifact under four serialisations.
10. **A file edited underneath the session.** A format-on-save daemon rewrote `.pipe` files in the
    working tree, which once produced a **false accusation that a teammate's committed pipe had
    drifted** — his bytes were always correct. **Tell:** his git blob hash was checked directly.
    *When a file disagrees with git, suspect your editor before suspecting the author.*
11. **Attribution reasoned rather than read.** An 84,960 MB memory figure was attributed to the
    wrong arm by per-process arithmetic — in the direction that flattered us. The record was
    available and was not fetched. **Tell:** the operator read the file. *A plausible mechanism is
    not evidence of which side it happened on.*
12. **Two correct changes that contradicted each other.** A `sched_getaffinity` fix was right
    until the same day's runbook pinned the driver with `taskset` — then it divided the service's
    utilisation by the driver's core count (#34). **Tell:** `cpu_utilization_valid` flagged
    rather than clamped. *Every "fix" is a change; check it against the other changes in flight.*
13. **A docstring that broke on its own subject.** Writing the tokenizer-based checker, its
    docstring embedded a literal triple quote and failed to parse — demonstrating the exact bug
    class the checker exists to catch.

---

## G. Open upstream items

### Two tickets drafted, not yet filed

`working/upstream/RocketRide_Engine_Tickets.md` — de-personalised, verified against engine
source, ready to hand to the engine team via a teammate who documents and forwards.

* **Ticket 1 — `BUG_CHUNK_DUPLICATION`.** `embedding_transformer.writeDocuments()` does not
  prevent the default action on the flush path, so every batch reaching `maxDocuments` (64) is
  emitted twice. **Source-verified:** `nodes/src/nodes/embedding_transformer/IInstance.py`,
  authored (not generated), **byte-identical at `server-v3.2.0` through `v3.3.1` and at current
  HEAD `1138936` — unfixed upstream today.** Regression test written and null-controlled both
  directions: `working/upstream/test_embedding_transformer_flush.py` (stock fails exactly 2 of 7,
  patched passes 7 of 7).
* **Ticket 2 — batch scheduler stranding on heterogeneous input.** The native `send_files()` batch
  API leaves roughly half the allocated cores idle on mixed-size corpora. **Note the corrected
  mechanism:** dispatch is ALREADY a shared demand-driven queue
  (`engLib/task/core/pipetask.process.cpp:73,127`) — the stranding is a work-granularity effect
  (documents are indivisible; the tail holds one worker each), not a failure to migrate work. Two
  questions are deliberately left open for the engine team rather than answered wrongly.

### Recommended, not drafted

* **Ticket 3 — surface parse failures.** A corrupt document returns `action: "complete"` with an
  objectId, metadata and an empty document list — structurally indistinguishable from a
  legitimately empty file. All three harnesses hit it.

### Unresolved questions handed to other people

* **Warm-up policy divergence.** The two teammates differ in both count AND disjointness — one
  warms 25 documents from BEYOND the measured set, the other warms `max(4, 2×threads)` on
  `files[:warm_n]`, i.e. the first MEASURED documents, which are then measured cache-hot. **We
  chose the disjoint policy.** Neither teammate has flagged this; it needs a group decision and
  the open question is recorded in the batched arm's export.
* **Corpus rule divergence.** Our selection rule is identical to one teammate's (verified: our
  file order IS globally sorted by basename); the other adds a `%PDF-` magic check and an
  `/Encrypt` exclusion that drops **485 of our 10,000 documents (4.85 %)**. Unresolved: whether
  the three-way table uses the intersection (9,515) or one team re-fetches.
* **`speedup_blast_over_sequential` divisor.** A teammate's definition divides by a single
  concurrency number; our per-document arm has both a threads value and a client-side cap.
  Which is the divisor needs one sentence of agreement.
* **Provenance field-name collision.** `engine_boot_patch` is one teammate's ONNX field; the
  duplication keys are `duplication_patch_applied` / `duplication_patch_id`, and the *id values*
  differ between teams. Do not conflate them.
* **`publishable/RUN_INVENTORY.md` "Full reports" row** was rewritten to a generic description
  because three named report filenames could not be verified to exist. If those reports are real,
  the row should name their S3 paths.
