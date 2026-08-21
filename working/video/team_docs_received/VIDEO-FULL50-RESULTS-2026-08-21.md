# Long-form video benchmark — 50 full-length AMI videos, detect pipe (2026-08-21)

First valid x86 numbers for the video track. Corpus: **50 full-length AMI videos,
38.56 footage-hours (138,813 s), 3.7 GB, native duration p50 ~43 min**, original
upstream bytes sha-pinned (`seed_manifest_ami_full.json`). Pipe:
`benchmark_video_detect.pipe` (frame_grabber@15s → detect rfdetr/RFDETRBase thr 0.3 →
preprocessor_langchain → miniLM → response_documents). Box: c7i.8xlarge, 32 vCPU,
61 GB, engine native x86 (`timings_valid: true`), RR_THREADS=32 = HS_WORKERS,
OMP_NUM_THREADS=1 both sides. Artifacts: `runs-local/vfull50-0821/` +
`s3://rocketride-benchmark-data/shashidhar/vfull50-stage2/`.

**Every gate passed on every run**: census 50/50, structure (384-d unit-norm),
frame law 50/50 both arms (⌊dur/15⌋+1 ±1), frames EXACT cross-arm, chunk ratio
1.000, detection ratio 1.000 (29,451 detections), label jaccard 1.0, determinism
ok, 96 metrics logging, `problems: []`.

## Headline — blast, 50 videos concurrent, identical produced work (1,858 chunks/side)

| | RocketRide | Haystack | ratio |
|---|---|---|---|
| Wall | 6,217 s (1h44) | **830 s (14 min)** | 7.5× |
| **x_realtime (aggregate)** | 22.3× | **167.3×** | 7.5× |
| Effective cores | **2.42 of 32** | 10.22 of 32 (tail-bound) | |
| Threads spawned | 2,921 | 1,311 | |
| CPU-s per footage-min | 6.50 | **3.67** | 1.8× |
| **$ per 1k footage-hours** | $64.0 | **$8.5** | 7.5× |
| Time to first result | 6,217 s (batch API = span) | 136 s | |
| Peak RSS | 10.8 GB | 27.8 GB (32 workers × models) | |
| Storage amplification | 0.0 net (transient ≈1× per video) | 0.0 net | |

## Per-stream — sequential, one video at a time: parity

| | RR | HS |
|---|---|---|
| x_realtime | 21.7× | 20.3× |
| Effective cores | 2.34 | 1.02 |
| p50 latency / video | 163 s | 177 s |
| Latency per footage-min | 2.77 s | 2.96 s |
| Speedup blast/seq | **1.11×** | **8.89×** |

## The core-ceiling question — answered

**RR aggregate throughput is flat at ~22.3× realtime and ~2.4 cores no matter the
offered concurrency or configured threads:**

| Evidence | Value |
|---|---|
| 1 video, 32 threads (stage-1) | 21.1× · 2.35 cores |
| 50 videos, 32 threads | 22.3× · 2.42 cores |
| 8 videos, **16 threads** (sweep) | **22.3× · 2.39 cores** |
| 8 videos, **8 threads** (sweep) | **22.4× · 2.39 cores** |
| Threads spawned during 50-blast | 2,921 — and still 2.42 cores busy |

Sweep artifacts: `runs-local/vsweep-0821/{t16,t8}/` (all gates passed in both).

**Mechanism (per-thread probe, sampled every 10 s through the blast):** the engine's
CPU is concentrated in singleton hot threads — the pipeline pump thread at ~95% of
one core, a scanner/inference thread at ~90%, a second engine thread ~58%, plus a
fleet of ~5% `av:mpeg` decoder threads. Detect inference is additionally serialized
behind the detect node's global `device_lock` (3.3.1 source: IInstance wraps
`detector.detect()` in the IGlobal mutex) with `OMP_NUM_THREADS=1` pinning torch to
one core. Adding threads adds *waiters*, not workers. This is an architectural
property of the engine's video path, not a tuning issue: it reproduces at 1, 8 and
50 videos and at 16 vs 32 threads to the decimal.

Note vs Leela's ~5.5–5.9-core observation (RR-vs-LangGraph): our detect pipe holds
~2.4. Different pipe composition can move the constant; the *flat-vs-threads* shape
is the shared finding.

Haystack's 10.22 of 32 in blast is a different, smaller story: per-request
single-core processing means a 50-video batch over 32 workers is tail-bound by its
longest videos (830 s ≈ two ~60-min videos back-to-back per worker); only 15 worker
pids served requests. It scales with workers; RR does not scale with threads.

## Secondary findings

- **Leela's storage-retention finding does not reproduce on our engine**: writable
  layer returns to baseline after every run (transient ≈1× copy per video in
  flight, net 0.0). The ENOSPC risk she hit is not present in this configuration.
- **Cold-to-ready**: RR ~188 s, HS ~223 s (32 workers warming RFDETR+miniLM) — ops
  cost, excluded from spans, now reported.
- HS RSS at 32 workers is ~27.8 GB (model replication) — the 61 GB box holds it;
  worth `HS_WORKERS` tuning guidance for production sizing, not a defect.
- 1 TB EBS applied and live-grown mid-run (969 G, zero downtime).

## Caveats

- Single rep: per the V-suite reporting rules this is a **sizing-quality result**
  until repeated (`INSUFFICIENT_REPS` discipline); the cross-arm deltas (7.5×) are
  far outside plausible rep noise, but publish with reps.
- `c<N>` fixed-concurrency mode not yet run (pending alignment with Leela's
  implementation); blast/sequential bracket the answer.
- TTFR basis differs by API shape (RR websocket batch returns everything at
  completion) — reported with basis strings, not comparable as bare numbers.
- Threads sweep used 8 videos (5.5 fh) vs the main run's 50 — sufficient for the
  flat-line claim; not for absolute throughput comparison across rows.

## Cost of the campaign (compute)

Corpus build ~25 min + stage-1 ~35 min + stage-2 ~4.2 h + sweep ~1.7 h ≈ **7 h of
c7i.8xlarge ≈ $10**.
