# Video benchmark setup — RocketRide vs Haystack, and the three-track parity contract

**2026-08-21.** Two things in one document:

- **Part I (§1–§12)** — the complete, reproducible setup of the RocketRide-vs-Haystack
  video track as it actually stands today, down to model identities, thread pinning,
  gate thresholds and the commands that produced `VIDEO-FULL50-RESULTS-2026-08-21.md`.
- **Part II (§13–§15)** — the **invariant set**: exactly what the LangGraph (Leela) and
  LlamaIndex (Ansh) tracks must hold identical so that all three benchmarks are *the
  same experiment with one arm swapped*, plus what may legitimately differ and must
  therefore be disclosed.

The three tracks are:

| Track | Competitor arm | Owner | Repo |
|---|---|---|---|
| RR-vs-HS (this one) | Haystack service | Shashi | `rocketride-haystack-benchmarking` |
| RR-vs-LG | LangGraph service | Leela | `github.com/Leela8256/benchmark` |
| RR-vs-LI | LlamaIndex service | Ansh | (his repo) |

**RocketRide is the common arm in all three.** That is the entire reason the setup has
to be shared: if the RR arm is configured differently on three boxes, the three
competitor numbers are not comparable to each other and the three-way report is
arithmetic on incompatible units. Everything in Part II exists to protect that.

---

# Part I — the RR-vs-HS video setup

## 1. The shape of the experiment

One sentence: **both frameworks run as their own network service, a driver that imports
neither sends the same pinned videos to both, and every number is gated before it is
allowed to be a number.**

```
                    ┌──────────────────────────────┐
                    │  bench driver (container)     │   imports NEITHER framework
                    │  bench_video.py               │
                    │   ├── rr_video_app.py         │
                    │   └── hs_video_app.py         │
                    └───┬──────────┬──────────┬─────┘
      websocket         │          │ HTTP     │ docker.sock (ro)
      ws://engine:5565  │          │ multipart│ per-container cpu_s / RSS / tasks
                        ▼          ▼          ▼
        ┌───────────────────┐  ┌───────────────────┐
        │ engine            │  │ haystack          │
        │ RocketRide 3.3.1  │  │ haystack-ai 3.0.0 │
        │ linux/amd64       │  │ uvicorn × N       │
        │ RR_THREADS = N    │  │ HS_WORKERS = N    │
        └───────────────────┘  └───────────────────┘
             identical cpuset · identical OMP_NUM_THREADS · shared hf-cache volume
```

Definitions that the whole suite rests on:

- **one document = one video.**
- **produced work = chunks.** On the detect pipe a "chunk" is a text chunk of the
  detection JSON; on the CLIP pipe it is a frame. The key is literally `chunks` in every
  result file so that every document-benchmark metric and gate applies unchanged.
- **the measured span** excludes pipeline setup (`use()` / HTTP warm) and warm-up
  documents. `t_measure_start` / `t_measure_end` bound the CPU-sampling window so cost
  is attributed to exactly the work that was timed.

Why services and not in-process imports: on 2026-08-04 the CTO/COO rejected the earlier
benchmarks because RocketRide paid a websocket + temp-disk tax that the competitors,
reading straight off local disk, never paid. Production-vs-production is the standing
correction. The bench image deliberately **does not install Haystack** — an accidental
in-process import would silently reopen that gap.

## 2. Host baseline

| Item | Value |
|---|---|
| Instance | `c7i.8xlarge` — 32 vCPU, 61 GB RAM, us-east-1a |
| Disk | gp3, **grown to 1 TB** for the long-form corpus (100 GB is the first hard wall) |
| Boxes | shashi `i-0e8e460af8f139fa1` · leela `i-0bdc8b1e18f2a5348` · ansh `i-0775f33f3dc16f6af` — provisioned identical by design |
| Docker | 29.7.2, Compose v5.4.0, rootless-capable (`docker` without sudo) |
| Arch | **x86_64 native.** The engine ships linux/amd64 only; on ARM it runs emulated and the export stamps `timings_valid: false` — functional testing only |
| Price input | `INSTANCE_USD_PER_H=1.428` (c7i.8xlarge us-east-1 on-demand), recorded in provenance and used for the V5 cost metrics |

**Auto-stop hazard.** The boxes stop themselves after 60 minutes sustained below 20%
instance CPU, with no warning (the SNS channel was never wired). On 32 vCPU that is 6.4
cores. A Haystack sequential phase sits at ~1 core ≈ 3%, and a hung run busy-spins at
~3% — both are inside the kill band. Long-form sequential phases must stay short
(`--seq-docs 3` for full-length videos) or be interleaved with blast work, which resets
the 60-minute clock.

**`preflight.sh` does not cover video.** It gates disk at ≥30 GB with no corpus
allowance, models RAM as `NPROC × 0.7 GB` (the miniLM figure, not CLIP/RFDETR), verifies
only `benchmark_pdf.pipe`, and never checks for `ffmpeg`/`ffprobe`, the video manifest
or the seed directory. Treat a preflight pass as *not* a video-readiness signal until
that branch is written.

## 3. The pipeline under test

The benchmarked pipe is the cross-team contract. The repo-root `.pipe` file is the
single source of truth; `run.sh` re-syncs it into the docker build context and prints
its sha256 immediately before every build, because editors and format-on-save hooks have
been observed rewriting fields in the build copy.

### 3.1 `benchmark_video_detect.pipe` — the primary long-form pipe

`sha256 = b34a1c54d4541aefe4f6c99e40588823d5e57d437c9f192c14243e2a873f9590`

```
webhook
  └─(video)→ frame_grabber   profile "interval", interval 15 s, start 0, duration 0
       └─(image)→ detect     profile "rfdetr", threshold 0.3
            └─(text)→ preprocessor_langchain   RecursiveCharacterTextSplitter, mode strlen
                 └─(documents)→ embedding_transformer   profile "miniLM"
                      └─(documents)→ response_documents  lane "documents"
```

Resolved identities — the harness reads these **from the pipe file** and mirrors them to
the competitor, so configuration cannot drift between the two sides:

| Node | What it actually resolves to | Notes |
|---|---|---|
| `frame_grabber` interval 15 s | ffmpeg `fps=1/15`, **PNG** (`-f image2pipe -vcodec png`, lossless) | The engine's `VideoFrameExtractor` shells out to ffmpeg; the mirror must use the same invocation |
| `detect` profile `rfdetr` | **Roboflow `rfdetr` package, `RFDETRBase()`**, `predict(image, threshold=0.3)` on the ORIGINAL PIL frame | Package-first: the engine falls back to transformers `PekingU/rtdetr_r50vd` only if the import fails, and the engine image ships `rfdetr==1.5.2`, so `RFDETRBase` is what runs |
| detection dict | `{label, score, box{x1,y1,x2,y2}, centroid{x,y}}`, **full floats, no rounding** | Label precedence `preds.data['class_name']` → `class_names[cid]` → `'object'`, then a score `< threshold` re-filter |
| `preprocessor_langchain` | **4000 / 200** (langchain defaults) | ⚠ The engine's chunk config is **INERT** — it falls through to the langchain defaults regardless of what the pipe asks for. Mirrored deliberately and disclosed |
| text accumulation | The engine's `IInstance` accumulates the text lane **per source**: `open()` clears, `writeText()` appends `text + '\n'` per frame, `closing()` splits the whole buffer **once** | So one video = one text document = a handful of chunks. **Chunks track total text volume, not frame count** |
| `embedding_transformer` profile `miniLM` | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, **384-d, unit-norm** | Not `all-MiniLM-L6-v2` — a long-standing trap |
| `response_documents` | Every chunk plus its embedding goes back over the wire | The mirror must return them too; omitting them is a free saving |

**No vector store, no LLM, no query phase.** Ingest only.

### 3.2 `benchmark_video.pipe` — CLIP pipe (first-light / smoke)

`webhook → frame_grabber(interval 2 s) → embedding_image(openai/clip-vit-base-patch16) →
response_documents`. Here chunks **are** frames, 512-d. Kept because it exercises the
video path with a much cheaper model; not the workload the exec asked for.

### 3.3 `benchmark_video_multimodal.pipe` — not runnable yet

`frame_grabber + audio_transcribe → detect → preprocess → miniLM`. Blocked: **AMI video
files carry no audio stream**, so `audio_transcribe` has nothing to transcribe. Either
drop that node or source audio from AMI's separate audio distribution before this pipe
means anything.

## 4. How the competitor arm is built (the mirror rules)

Haystack has no video and no object-detection components. The rule the whole comparison
depends on: **where the competitor lacks a native component, the mirror reproduces the
engine's node at the service boundary using the identical model object and identical
mechanics — and says so.** Anything the competitor *does* have natively must run
natively as a real framework pipeline.

| Engine node | Haystack mirror | Native or service-level |
|---|---|---|
| `webhook` | FastAPI multipart upload | service-level (equivalent ingress) |
| `frame_grabber` | `extract_frames()` — ffmpeg `fps=1/interval`, PNG | service-level, disclosed |
| `detect` | `detect_frame()` — same `rfdetr==1.5.2` package, same call, same dict | service-level, disclosed |
| `preprocessor_langchain` | Haystack `DocumentSplitter(split_by="function", …)` wrapping the **same langchain splitter** at 4000/200 | **native Haystack Pipeline** |
| `embedding_transformer` | `SentenceTransformersDocumentEmbedder(multi-qa-MiniLM-L6-cos-v1)` | **native Haystack Pipeline** |
| `response_documents` | JSON body with content + embedding + meta | service-level |

Two mirror bugs that were caught and are worth carrying as warnings to the other tracks:

1. **JPEG vs PNG.** The first mirror wrote JPEG frames. Measured `cosine(jpg, png)`
   dipped to **0.9808** — the same magnitude as two genuinely different frames. Both
   sides now embed byte-equivalent pixels.
2. **Wrong checkpoint.** The first detect mirror used the RTDetr *fallback* checkpoint.
   Its `tvmonitor` labels against the engine's `tv` exposed it. Same-package,
   same-version pinning is the fix; label vocabulary is the tell.

## 5. Parity controls (identical on both sides, verified not assumed)

| Control | Value | Why it exists |
|---|---|---|
| `OMP_NUM_THREADS` / `MKL` / `OPENBLAS` | **1 on both services** | Without it the engine's torch grabs every core for intra-op matmuls while each uvicorn worker is capped at 1 — measured **528 vs 260 CPU-s** on an otherwise identical 50-doc run. Document-level concurrency is the variable under test; intra-op threading is a confound |
| `TOKENIZERS_PARALLELISM` | `false` both sides | same reason |
| Concurrency | `RR_THREADS == HS_WORKERS`, pinned and reported in every result | engine worker threads vs uvicorn worker processes |
| `cpuset` | identical string on both services (empty = full host) | and **verified from each container's own cgroup** (`online_cpus`), never from the compose config |
| Ingress | client upload on both sides (websocket / HTTP multipart) | no local-filesystem shortcut for either arm |
| Model cache | shared `hf-cache` volume | ⚠ wipe it when model provenance must be *proven* rather than inferred |
| Daemon freshness | `run.sh` restarts **both** services before every invocation | an aged engine daemon has been observed busy-spinning at 100% while idle, starving new pipelines |
| Warm-up | outside the measured span, both sides; `WARM_DOCS=4` on long-form corpora | the default blast warm-up (`max(4, workers)` docs) would re-process ~32 full-length videos outside the span — an hour of wasted work |
| Concurrent runs | refused — `run.sh` aborts if another bench container is live | a second `use()` of the same pipe fails with "Pipeline is already running" mid-run |

### Engine boot patches (disclosed in every export as `engine_boot_patch`)

Release 3.3.1 does not boot or produce correct output unmodified. Both patches are
applied in `engine.Dockerfile` with build-time guards that fail if the source drifts:

1. **`onnxruntime-gpu 1.20.1 → 1.20.2`** in three non-benchmark node manifests. 1.20.1
   was removed from PyPI and the engine's all-or-nothing constraints compile refuses to
   boot over it. (`ENGINE-ISSUE-3.3.1-onnxruntime-pin-2026-08-13.md`)
2. **`BUG_CHUNK_DUPLICATION`** — `embedding_transformer`'s flush path is missing
   `preventDefault()`, so once a batch reaches `maxDocuments=64` the engine's default
   forward emits the same batch a second time and the whole chunk list lands twice. One
   inserted `return self.preventDefault()`. Upstream HEAD still carries the bug.
   (`ENGINE-ISSUE-3.3.1-chunk-duplication-2026-08-15.md`)

## 6. The corpus

**AMI Meeting Corpus**, pulled from the Edinburgh mirror
(`groups.inf.ed.ac.uk/ami/AMICorpusMirror//amicorpus`).

| Property | Long-form corpus (primary) | Clip corpus (first-light only) |
|---|---|---|
| Builder | `build_ami_video_manifest_full.py` | `build_ami_video_manifest.py` |
| Shape | **native duration, no transcode** | 30 s cuts |
| Size in use | **50 videos · 38.56 footage-hours · 138,813 s · 3.7 GB · p50 ≈ 43 min** | 8 × 30 s |
| Manifest | `seed_manifest_ami_full.json` | `seed_manifest_ami_video.json` |
| Status | the benchmark | retained for wiring checks; the exec explicitly rejected clip-shaped workloads |

Why no transcode: the AMI video distribution is already uniform — mpeg4 AVI, 352×288,
25 fps, no audio stream, verified across all four sites — so decode cost is comparable
by construction, and the sha256 pins the **upstream** bytes. That makes the corpus
reproducible from the mirror forever, with none of the build-once transcode caveats.

Selection is deterministic: meetings alphabetically, cameras in a fixed priority order
(`Closeup1..4, Corner, C, Overview1, Overhead`), at most `--max-per-meeting` cameras per
meeting for content diversity, first N sources whose ffprobe duration ≥ `--min-duration`
win. Duration is probed over HTTP range requests first, so a too-short source costs
seconds rather than a download. Dead URLs are skipped and recorded.

The manifest carries `filename / sha256 / bytes / duration_s`. **`fetch_video_seeds()`
re-hashes every file before every run** and hard-fails on drift
(`VIDEO PIN VIOLATION: … do not run`). `video_seconds` — the denominator of the headline
metric — comes from the manifest, never from a runtime probe.

**Known corpus limit, worth stating in any report:** at 352×288 / 0.31 Mb/s, AMI cannot
support the data-movement or memory-ceiling metrics. Those axes are dead on this corpus
and should be dropped from the report rather than filled with numbers that measure
nothing. A second HD corpus is the only fix.

## 7. Run modes

Modes are **never blended** — MLPerf discipline. Each is a separate span with its own
gates.

| Mode | What it is | What it yields | What it must never yield |
|---|---|---|---|
| **probe** | 1 video through the engine before anything else | proof the configured interval is *live*, and `dims == [expected]` | — |
| **sequential** | one video at a time | p50/p95 latency, latency per footage-minute, per-stream `x_realtime` | throughput claims at scale |
| **blast** | all N offered at once (RR: one atomic `send_files`; HS: a thread pool of size `workers`) | throughput, `effective_cores`, `threads_activated` | **per-document latency claims** |
| **c\<N\>** | fixed offered concurrency | the exec's "~10 concurrent" question | **not implemented yet** — see §14 |
| **fault** | kill-and-recover | recovery time | anything mixed into throughput numbers |

The interval probe deserves its own note: it is the video edition of the
chunk-config-INERT lesson. A pipe can *ask* for a 15 s interval and the engine can
quietly do something else. On the CLIP pipe the probe bounds chunks at 0.5–1.5× of
`duration/interval` both ways; on the detect pipe, where chunks follow text volume, it
can only bound from above (`chunks ≤ 1.5 × expected + 1` — more chunks than frames means
over-sampling). Cross-arm sampling asymmetry is caught by the frame-parity gate either
way.

## 8. Gates — a run that fails any produces no quotable numbers

| Gate | Check | Catches |
|---|---|---|
| **Corpus pin** | sha256 + bytes + duration per video vs manifest | anyone benchmarking different files |
| **Interval probe** | 1 video through the engine; chunk band + `dims` | a dead/ignored interval config, wrong embedding |
| **Census** | `offered = recorded`, no missing / duplicate / unexpected / silent-empty | a document vanishing and reading as speed |
| **Structure** | per chunk: finite vector, expected dim (384 miniLM / 512 CLIP), L2 within 1e-3 of 1.0 | wrong model, broken load, truncated vectors |
| **`frame_law`** (per arm) | `frames == ⌊duration/interval⌋ + 1`, tolerance **±1**, against the **manifest** | silent frame drops — checked against ground truth, not against the other arm |
| **`frame_parity`** (cross-arm, detect) | per-video `n_frames` **exact** match | same fps rule on the same bytes must give the same frames |
| **`chunk_ratio`** (cross-arm) | per-video and total, **hard 0.8–1.25, warn 0.95–1.05** | one side doing materially more/less work |
| **`detection_ratio`** | total + per-video extremes, **warn 0.90–1.10** | model divergence *before* it moves a chunk boundary |
| **`label_overlap`** | per-video Jaccard — **reported, never gated** | semantic drift tripwire |
| **Normalization parity** | both sides' norm status agree | one side embedding unnormalised silently changes every similarity |
| **Determinism** | per-video embedding digests, blast ∩ sequential, per side | send-mode-dependent output |
| **Metric coverage** | every asserted metric non-null | "we did not check" reading as "it passed" |

Two hard-won implementation rules:

- **Gates read the full result files on disk**, not the drivers' stdout line — stdout
  strips `per_doc`, and a gate fed from it silently checks nothing. A real 4-vs-6
  divergence once passed the per-video clause for exactly this reason.
- **Anything uncomputable is `None`, never `0`, never `inf`** — so a failed run can
  never masquerade as a fast one.

Our `chunk_ratio` band is deliberately **tighter than the RR-vs-LG suite's 0.4–2.5**:
Leela's arms are two independent implementations, ours is a same-package same-version
mirror, so any drift is floating-point jitter, not implementation freedom.

## 9. Metrics — the shared V-suite vocabulary

Every formula is a pure function in `docker/bench/metrics.py` with exact expected values
in `test_metrics.py`. `bench_video.py` only wires inputs; nothing is computed inline in a
driver. Names follow **Leela's V-suite**, with our previous names kept as aliases so the
three-way report lines up for free.

**Headline / throughput**

| Metric | Formula | Note |
|---|---|---|
| **`x_realtime`** | `video_seconds / wall_s` | *the* headline: seconds of footage ingested per wall-second |
| `realtime_streams` | same number | operator framing: sustainable live feeds |
| `docs_per_s` | `docs / wall_s` | videos/s — comparable only on identical corpora |
| `chunks_per_s` | `chunks / wall_s` | produced-work rate; the unit used for speedup |
| `frames_per_video`, `n_frames_total`, `n_detections_total` | counters | frames counted symmetrically from returned chunk text on both arms |

**Efficiency (needs `docker.sock`; otherwise exempt from coverage and logged null)**

| Metric | Formula | Note |
|---|---|---|
| **`cpu_s_per_footage_min`** | `cpu_s / (video_seconds/60)` | **primary** efficiency number — robust to the ~5× chunk-density variance across AMI rooms |
| `cpu_s_per_frame` / `cpu_s_per_detection` | component-level | density-independent |
| `cpu_s_per_chunk` / `cpu_s_per_doc` | continuity with the PDF track | density-sensitive on video |
| `peak_rss_mb` | max sampled RSS (cgroup minus page cache) | at N workers this is dominated by N model copies, not per-video work |
| `storage_amplification` | container writable-layer delta / input bytes | reported, never asserted |

**Concurrency**

| Metric | Formula | Note |
|---|---|---|
| `effective_cores` (`achieved_parallelism`) | `cpu_s / wall_s` | average cores actually busy — the check against configured concurrency |
| `scaling_efficiency` (`cpu_utilization`) | `cpu_s / (wall_s × online_cpus)` | fraction of the allocation used |
| `threads_activated` | `peak_tasks − baseline_tasks` | evidence the configured concurrency actually activated. **Exempt in sequential** — a warm pool adds no kernel tasks; that is physics, not a logging gap |
| `speedup_blast_over_sequential` | `chunks_per_s(blast) / chunks_per_s(seq)` | ratio of ratios — each arm against **itself**, immune to "you gave one side more workers" |
| `parallel_efficiency` | `speedup / configured_concurrency` | meaningful only when `docs ≥ concurrency` |

**Latency (sequential only)**

`lat_ms_p50` / `lat_ms_p95` (nearest-rank, no interpolation, `None` excluded),
`latency_per_footage_min_p50/p95`, `failed_items` (counted, never averaged into
latency), and `time_to_first_result_s` — which is **only ever read together with
`time_to_first_result_basis`**, because RR's blast is one atomic `send_files` whose first
observable result *is* batch completion, while HS's is the first completed HTTP response
across the pool. Both are honest; they are not the same quantity.

**Cost / ops** — `usd_per_1k_footage_hours`, `videos_per_day_per_box`,
`cold_to_ready_s` (setup + warm, excluded from every span).

**Reporting rules**
- A single rep is a **sizing-quality** result. Quote it as `INSUFFICIENT_REPS`, not as a
  point value.
- Blast never produces per-document latency.
- TTFR never appears without its basis string.
- Cross-arm ratios are published alongside the raw numbers, never instead of them.

## 10. Provenance stamped in every export

`pipe_sha256`, `pipe`, `pipeline_kind` (clip|detect), `interval_s`, `expect_dim`, model
identities (`detect_model` + `threshold` + `embed_model` + `split_length/overlap`, or
`clip_model`), `bench_arch`, `engine_platform`, `engine_native`, **`timings_valid`**,
`hs_arch` / `hs_version` / `hs_workers`, `omp_num_threads`, `cpuset`, `rr_threads`,
`video_manifest`, `ingress`, `instance_usd_per_h`, `engine_boot_patch`.

⚠ `pipe_sha256` currently churns because tooling rewrites `project_id` on copy —
semantics are identical; canonicalised hashing is an open TODO. Until then, compare the
*node graph*, not only the hash, across tracks.

## 11. Runbook

### 11.1 Getting code onto the box

The `AWS-RUNBOOK.md` git-clone bootstrap **does not work** — the repo is private and the
boxes carry no GitHub credentials. Working transport:

```bash
# laptop
git archive --format=tar.gz -o /tmp/bench.tgz HEAD
aws s3 cp /tmp/bench.tgz s3://rocketride-benchmark-data/_transport/

# box (instance profile rocketride-benchmark can read/write that bucket)
apt-get install -y unzip          # the AWS CLI and unzip are NOT installed
aws s3 cp s3://rocketride-benchmark-data/_transport/bench.tgz . && tar -xzf bench.tgz
```

Agent-driven sessions must use `aws ssm send-command`; `ssm start-session` is
interactive and unusable non-interactively. Docker images and the `hf-cache` volume
persist across box stops, so a rebuild is minutes — but a persisted `hf-cache` means
model resolution comes back *inferred* rather than proven; wipe it when provenance has
to be proven.

### 11.2 Build the corpus (once)

```bash
docker compose run --rm --no-deps bench python /app/build_ami_video_manifest_full.py \
  --videos 50 --min-duration 1800 --manifest /data/seed_manifest_ami_full.json
```

### 11.3 Run

```bash
cd haystack-benchmark/docker

RR_THREADS=32 \
OMP_NUM_THREADS=1 \
VIDEO_MANIFEST=/data/seed_manifest_ami_full.json \
VIDEO_SEED_DIR=/data/seed-videos-full \
WARM_DOCS=4 \
SMOKE_DOCS=50 \
SEQ_DOCS=3 \
INSTANCE_USD_PER_H=1.428 \
./run.sh video-detect
```

`run.sh` syncs and hashes the shared pipes, builds all three images, restarts both
services for a fresh daemon, waits on healthchecks, then runs the driver. Artifacts land
in `docker/results/`; `VIDEO-SMOKE-METRICS.json` is the export to share.

### 11.4 Environment matrix

| Variable | Default | Meaning |
|---|---|---|
| `RR_THREADS` | host core count on x86 (4 on ARM) | engine threads **and** `HS_WORKERS` |
| `OMP_NUM_THREADS` | 1 | pinned on both services |
| `BENCH_CPUSET` | empty (full host) | must be identical for both services |
| `BENCH_PIPE` | `benchmark_pdf.pipe` | set by the `video-detect` / `video-smoke` modes |
| `VIDEO_MANIFEST` / `VIDEO_SEED_DIR` | clip corpus | point both at the full-length pair for long-form |
| `SMOKE_DOCS` / `SEQ_DOCS` | 8 / 3 | blast N and sequential N |
| `WARM_DOCS` | `max(4, workers)` | **set to 4 on long-form** |
| `INSTANCE_USD_PER_H` | 1.428 | V5 cost input, recorded |
| `CENSUS_EMPTY_POLICY` | `fail` | `report` only for real-world corpora, and disclosed |
| `DETECT_MODEL` / `EMB_MODEL_FULL` | resolved from the pipe | override only when an engine release changes the profile map |

Timeouts on the long-form path: driver `--timeout 21600`, subprocess wall `22000 s`.

## 12. What this setup has produced

50 full-length AMI videos, detect pipe, c7i.8xlarge, 32 threads = 32 workers,
`timings_valid: true`, **every gate passed, `problems: []`, 96 metrics logging on both
sides**, identical produced work (1,858 chunks/side, detection ratio 1.000, label
Jaccard 1.0).

| Blast, 50 concurrent | RocketRide | Haystack |
|---|---|---|
| Wall | 6,217 s | **830 s** |
| `x_realtime` | 22.3× | **167.3×** |
| `effective_cores` | **2.42** of 32 | 10.22 of 32 (tail-bound) |
| `cpu_s_per_footage_min` | 6.50 | **3.67** |
| `usd_per_1k_footage_hours` | $64.0 | **$8.5** |
| `peak_rss_mb` | 10.8 GB | 27.8 GB (32 × models) |

Sequential (per-stream) is parity: 21.7× vs 20.3×, p50 163 s vs 177 s.

**The finding the setup exists to have produced:** RR aggregate throughput is flat at
~22.3× and ~2.4 cores regardless of offered concurrency *or* configured threads — 21.1×
at 1 video/32 threads, 22.3× at 50/32, 22.3× at 8/**16**, 22.4× at 8/**8**, with 2,921
threads spawned during the 50-blast. Per-thread probing shows the engine's CPU
concentrated in singleton hot threads (pump ~95% of a core, scanner/inference ~90%, a
second engine thread ~58%, plus ~5% `av:mpeg` decoder threads), with detect inference
additionally serialised behind the detect node's global `device_lock`. Adding threads
adds waiters, not workers.

Full write-up and caveats: `VIDEO-FULL50-RESULTS-2026-08-21.md`.

---

# Part II — the three-track contract

## 13. What "the same setup, fundamentally" means

Three tiers. Tier A is what makes the three tracks one experiment; Tier B is what makes
the numbers comparable; Tier C is what may differ, provided it is disclosed in the same
words on all three sides.

### Tier A — must be byte-identical across all three tracks

| Item | How to prove it |
|---|---|
| **The pipe file** | Same `.pipe`, from the repo-root source of truth. Compare `pipe_sha256` across exports — and, until canonical hashing lands, compare the node graph too |
| **The engine release** | RocketRide **3.3.1**, same tarball URL, same two boot patches, same `engine_boot_patch` string in the export |
| **The RocketRide SDK** | `rocketride==1.2.0` |
| **The corpus** | Same manifest file: same `filename / sha256 / bytes / duration_s` rows. Sharing the manifest is sharing the corpus — the sha256 pins upstream bytes |
| **The resolved model identities** | `RFDETRBase` from `rfdetr==1.5.2`, threshold 0.3; `multi-qa-MiniLM-L6-cos-v1`; splitter 4000/200 — on **both** arms of **each** track |
| **Frame extraction** | ffmpeg `fps=1/interval`, **PNG** |

### Tier B — must be equal-valued (verified from the running system, not from config)

| Item | Value | Verified how |
|---|---|---|
| Instance shape | c7i.8xlarge, 32 vCPU, 61 GB, x86 native | `bench_arch`, `engine_native`, `timings_valid` in the export |
| Intra-op threads | `OMP/MKL/OPENBLAS = 1` on **every** service | recorded per run; read back from the live object where the framework allows it |
| Document concurrency | `RR_THREADS == <competitor workers>`, pinned and reported | `configured_concurrency` + `threads_activated` |
| CPU allocation | identical cpuset for both services of a track | read from each container's cgroup `online_cpus`, never from compose |
| Ingress | client upload on both arms | `ingress` string in provenance |
| Return payload | documents + embeddings returned on both arms | otherwise one side gets a free saving |
| Span discipline | setup and warm-up outside the measured span; cost sampled over `t_measure_start..end` | |
| Mode discipline | sequential / blast / c\<N\> never blended | |

### Tier C — may differ, must be disclosed identically

| Difference | Disclosure rule |
|---|---|
| **Service-level mirrors** where the competitor has no native component | Name the node, name what replaced it, state that the framework-native stages still run natively. HS: frame-grab + detect are service-level; split + embed are a real Haystack Pipeline |
| **API shape** — RR's `send_files` is atomic; HTTP arms stream per-request | Report the asymmetry itself; TTFR always with its basis string; no synthetic completion curve on the RR side |
| **`framework_overhead`** (e2e − Σ node timings) | LangGraph can instrument it; Haystack's analog is the `read_s` / `pipeline_s` split; **RR is a black box on every track** and that is stated, not worked around |
| **Parity band width** | Independent-implementation arms (LG, LI) may need wider `chunk_ratio` bands than our same-package mirror. State the band and the reason. Suggested for long-form: hard 0.8–1.25, warn 0.95–1.05 |
| **Pipe composition** | Different pipes move the RR core constant (our detect pipe holds ~2.4 cores; Leela measured ~5.5–5.9 on hers). The **flat-vs-threads shape** is the shared finding; the constant is not |

## 14. Deltas to close, per track

**Ours (RR-vs-HS) — owed to the shared suite**

1. **`c<N>` fixed-concurrency mode.** The exec's "~10 concurrent" question maps to this
   mode, not to blast. HS side is trivial (a semaphore of N). **The RR side is the open
   question** — concurrent single-file sends over one websocket may serialise inside the
   SDK. *Ask Leela how her RR arm offers fixed concurrency before inventing a second
   answer;* two different RR c\<N\> implementations would break Tier A.
2. **Reps.** Everything published so far is single-rep. Adopt Leela's rule verbatim:
   single-rep runs are sizing runs and quote no point value.
3. **Declared ≠ measured read-back** (Ansh's, and he is right): read thread counts,
   device and chunk size back off the *live* objects. A 10,000-document comparison of his
   once ran 1-thread vs 10-thread and nothing detected it.
4. **Mutation-test the gates.** Break each gate on purpose, confirm it fails, restore.
   Neither we nor Leela do this. Ansh does.
5. **Text-quality gate** ("the extracted text is readable prose"), which Ansh has and we
   do not.
6. **Extend `preflight.sh`** with a video branch (§2).

**What we should push back into the shared suite** — the interval-live probe, the
normalisation-parity gate, PNG pixel-parity doctrine plus same-package pinning, the
census silent-empty policy, `timings_valid` / engine-native provenance, and the metric
coverage gate.

**Cross-track, unresolved**

- **Storage amplification.** Leela measured RR retaining ~1.0× of input bytes for the
  container lifetime; **it does not reproduce on our engine** (writable layer returns to
  baseline; transient ≈1× per video in flight, net 0.0). Different pipe or different
  engine configuration — worth pinning down before anyone quotes it.
- **The core ceiling.** Ours 2.4, hers 5.5–5.9. Same shape, different constant. The
  cores-vs-configured-threads curve should be a first-class deliverable on all three
  tracks, plotted on the same axes.

## 15. Checklist — declaring a track "on the shared setup"

A track is on the shared setup when its export can answer all of these from its own
recorded fields:

- [ ] `pipe_sha256` (and node graph) matches the other tracks
- [ ] engine 3.3.1, same boot patches, `engine_boot_patch` string present
- [ ] corpus manifest identical: same filenames, same sha256s, same durations
- [ ] `detect_model` / `threshold` / `embed_model` / `split_length` / `split_overlap` match
- [ ] frame extraction is ffmpeg `fps=1/interval`, PNG, on both arms
- [ ] `timings_valid: true` (x86 native)
- [ ] `omp_num_threads: 1` on every service
- [ ] `rr_threads == <competitor workers>`, both recorded
- [ ] `cpuset` recorded and read from cgroup `online_cpus`
- [ ] `ingress` says client upload on both arms
- [ ] gates: census, structure, `frame_law`, cross-arm frame parity, `chunk_ratio`,
      `detection_ratio`, `label_overlap`, normalisation parity, determinism — all present
      and all passing, with bands stated
- [ ] metric coverage gate ran and `problems: []`
- [ ] V-suite metric names used: `x_realtime`, `effective_cores`, `scaling_efficiency`,
      `cpu_s_per_footage_min`, `cold_to_ready_s`, `usd_per_1k_footage_hours`
- [ ] TTFR carries its basis string
- [ ] rep count stated; single-rep results labelled `INSUFFICIENT_REPS`
- [ ] every service-level mirror named and disclosed

## 16. Not measured (do not let a report imply otherwise)

Bytes-over-network per video, full-copy count, transport-vs-processing split;
peak-RSS-vs-length slope, max-concurrent-before-OOM, the three binary capability tests;
embedding equivalence against an offline reference and the pts-based truncation gate;
blast radius / recovery for video; toil. Also: WER/mAP (same models both arms —
controlled by construction), tokens/s (no LLM), energy (no counters on EC2), and byte
parity of chunks (bands replace it).

---

**Source files** — `haystack-benchmark/docker/compose.yml`, `run.sh`,
`engine.Dockerfile`, `hs.Dockerfile`, `bench.Dockerfile`;
`docker/bench/{bench_video.py, rr_video_app.py, hs_video_app.py, hs_service.py,
correctness.py, metrics.py, cstats.py, build_ami_video_manifest_full.py}`;
pipes at repo root. Companion documents: `VIDEO-FULL50-RESULTS-2026-08-21.md`,
`REVIEW-leela-video-metrics-2026-08-20.md`, `docs/VIDEO-METRICS-IMPLEMENTED.md`,
`docs/METRICS-THREE-WAY-2026-08-14.md`, `haystack-benchmark/HANDOFF.md`,
`haystack-benchmark/AWS-RUNBOOK.md`.
