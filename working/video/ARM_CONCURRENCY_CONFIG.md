# Both arms, end to end — processes, threads, pools, and every config that shaped them

One page for the report and for anyone reproducing. Every value cited to
source, run_plan, or a per-leg read-back. Campaign: ami_full, n=168 measured
+ 2 warm, C=16, box 32 vCPU / 61 GB, both arms `--network host`,
`--memory 58g`.

---

## RocketRide arm (engine 3.3.1 patched, image `rr:patched-video`)

### Process tree (what "multiple servers" means here)
    docker: rr
    └─ engine master  — ai/eaas.py, uvicorn websocket server on :5565
       (ai/web/server.py:458; serves the DAP protocol; never infers)
       ├─ task process #1   — spawned by use() token 1 (task_engine.py:1561)
       ├─ ...
       └─ task process #M   — one PER TOKEN; the model runs IN-PROCESS here
- The separate **model server on :5590 is NOT used**: it activates only with
  `--modelserver=` (ai/common/models/base.py:206-238) and our entrypoint
  passes none (docker/rocketride-entrypoint.sh:16). Inference is local to
  each task process.
- **Serialization per task process:** detect holds `make_device_lock()` =
  `threading.Lock` (nodes/detect/IGlobal.py:81, base.py:241-252) — process-
  local, so **one inference at a time per token; M tokens = up to M
  concurrent inferences** (no cross-process lock exists in source; direct
  measurement = probe_concurrent_inference.sh).
- ffmpeg decode: subprocess per video (ai/common/avi/reader.py), **no
  `-threads` flag → auto**, outside all env pins.
- Splitter: `preprocessor_langchain` — chunk kwargs are DISCARDED by the
  constructor-signature filter (langchain.py:90-102,202) → **LangChain
  defaults 4000/200**, and overlap realizes as **0** on ami (whole-unit
  retention vs 1,726-char frame lines) → RR embeds ~4.75% fewer chars
  (CHAR_CONSERVATION_MECHANISM.md).

### The two postures (the ONLY knobs that differ)
| | DEFAULT (out-of-box) | PARITY |
|---|---|---|
| tokens M (= task processes) | 1 | **16** (16 distinct project_ids) |
| six env vars OMP/MKL/OPENBLAS/VECLIB/NUMEXPR/TORCH_NUM_THREADS | **unset** | **all = 2** (container `-e`, run_plan.sh:175) |
| in-process torch intra-op (read back per leg, fail-closed) | **16** (engine default) | **2** |
| torch inter-op | engine default, unpinned | same |
| `use()` | `filepath, ttl=0` — `threads=` passed in NEITHER posture | same |
| measured frames/s (span, p1/p2) | **2.443 / 2.446** | **12.729 / 12.753** |
| service CPU of 32 | 18.8% (~6 cores) | 91.6/92.1% (~29.3 cores) |

Concurrency math: default = 1 inference lane × 16-thread width ≈ 6 cores;
parity = 16 lanes × 2 threads ≈ 29 cores. Same physics as the LI budget
line: lanes beat width.

### Client (our driver) — identical for both postures
asyncio, ONE RocketRideClient = ONE websocket (tokens multiplex by seq);
semaphore C=16; payload read + sha in worker threads AFTER admission, ≤C
blobs resident (4ea3e41); **chunked 1 MiB writes** (58f2bb3, = send_files'
shape, ~237-238 round-trips per 248 MB, disclosed in every export as
`rr_write_path`); ttl=0 with retry-then-escalate terminate; warm-up = 2 warm
rows re-sent round-robin over all M tokens; per-arm flock; breaker K=3.

---

## LlamaIndex arm (image `li:video`, our service)

### Process tree
    docker: li_video
    └─ uvicorn master :8802 (Dockerfile.llamaindex-video:93; W=1 serves in-process)
       ├─ worker #1 ... worker #8   — `--workers ${WS1V_WORKERS}=8`
       │    each: FULL model set loaded in lifespan (rfdetr + embedder,
       │    service.py:94-101), warm marker written; /health counts markers
- Kernel accept picks the worker (accept is not a scheduler — Crossroads
  40/41); the gate for warmth is the MARKERS, not response-pid spread.

### Per-worker pool inventory (all of them)
| pool | size | where set | state |
|---|---|---|---|
| uvicorn workers | **8** | `-e WS1V_WORKERS=8` (run_plan.sh:204) | the concurrency ACROSS inferences |
| anyio request threadpool | 40 | library default (service.py:144 passes no limiter) | queueing; unpinned |
| model lock | **1 per worker** | pipeline.py:99 ("engine mirror") | detect+embed serialized per worker |
| torch intra-op | **4** | six env vars = 4 (`thread_env_args`, run_plan) | the width of one inference |
| torch inter-op | default | unset anywhere | exists, ~idle, unpinned (both arms) |
| BLAS family (OMP/MKL/OpenBLAS/vecLib/numexpr) | 4 each | same six vars | pinned |
| HF tokenizers | **off** | `TOKENIZERS_PARALLELISM=false` (pipeline.py:48) | fork-safety |
| ffmpeg decode | auto, uncapped | no `-threads` (pipeline.py:146-149) | subprocess, outside pins — symmetric with RR |

Per request (in a threadpool thread): extract (ffmpeg subprocess, unlocked)
→ detect (LOCKED, rfdetr per frame) → split (unlocked, SentenceSplitter
4000/200, overlap realized ~200) → embed (LOCKED, one batch). `stage_s`
stamped per stage — instrumentation the RR response structurally lacks
(stated limitation).

Concurrency math: 8 workers × 1 locked inference × 4 threads = 32 = cores.
Measured anchor: `sum(stage_s.detect)/span = 8.00` — exactly one inference
per worker, eight concurrent. Frames/s span 9.267/8.714 at ~40% CPU.

Config provenance: LI_WORKERS=8 / LI_THREADS_ENV=4 = best of the 3-point
W×T=32 budget line (4×8 0.0989 / **8×4 0.1473** / 16×2 0.0913, 15/16
serving) — swept family, not a proven global optimum (disclosed).

---

## The one-table cross-arm summary
| | RR default | RR parity | LlamaIndex |
|---|---|---|---|
| serving processes | 1 task | 16 tasks | 8 workers |
| inference concurrency | 1 | 16 | 8 |
| threads per inference | 16 (default) | 2 | 4 |
| lanes × width | 16 | 32 | 32 |
| effective cores | ~6 | ~29.3 | ~13 |
| f/s span | 2.44 | 12.73 | ~9.0 |
| per-inference lock | device_lock (threading.Lock/process) | same | pipeline lock (threading.Lock/worker) |
| stage timings | none (engine emits none) | none | stage_s per request |
