# Archive Films (50): out-of-the-box vs best-config, RocketRide vs Haystack

**Run `films50-20260903T183805Z`** on `i-0e8e460af8f139fa1` (c7i.8xlarge, 32 vCPU, 61 GB),
tree `b451ef0` on `benchmark/haystack-video`, launched 2026-09-03 18:38 UTC by
`orchestration/films_campaign.sh`. Mirrors `oob5-0830` (whole-AMI) cell for cell on a
new corpus: 50 public-domain feature films, 1080p `.mp4`, 73.9 footage-hours.

> **STATUS: main campaign complete** — 7/7 cells, 18:38 → 01:12 UTC (6.6 h), every cell ok,
> 17,728 frames and 50/50 proven on all, frame law 0 everywhere. Artifacts in
> `runs-local/video/films50-20260903T183805Z/` and
> `s3://rocketride-benchmark-data/shashidhar/films50-20260903T183805Z/`.
> **HS re-run with prefetch + page-cache prewarm complete** — `films50-hsfix-20260904T011434Z`,
> build `4342711`, 01:14 → 03:17 UTC, all three cells ok; artifacts in
> `runs-local/video/films50-hsfix-20260904T011434Z/`. **Box stopped 03:30 UTC.**

## Headline

Span-scoped CPU on both arms (cgroup read at the measured span edges; settle, model
load and the two-film warm-up excluded). `wall s` is the measured span. Cell 1 for
scale: warm-up of 16 tasks on 1080p took 535 s, settle 196 s, setup 122 s — none of
it in the span.

| cell | ok | ×RT | f/s | cores | CPU-s/fr | $/1k fh | RSS GB | wall s |
|---|---|---|---|---|---|---|---|---|
| rr-best-16x2-r1 | ✓ | 187.8 | 12.52 | 27.5 | 2.198 | 7.60 | 25.54 | 1416 |
| hs-best-32x2-r1 | ✓ | 118.7 | 7.91 | 10.8 | 1.361 | 12.03 | 20.7 | 2240 |
| rr-best-32x1-r1 | ✓ | 153.9 | 10.26 | 25.0 | 2.437 | 9.28 | 41.11 | 1728 |
| rr-best-16x2-r2 | ✓ | 159.7 | 10.65 | 27.7 | 2.604 | 8.94 | 26.04 | 1665 |
| hs-best-32x2-r2 | ✓ | 124.2 | 8.28 | 14.4 | 1.743 | 11.50 | 21.82 | 2141 |
| rr-oob-r1 | ✓ | 37.5 | 2.50 | 6.3 | 2.499 | 38.06 | 12.83 | 7088 |
| hs-oob-r1 | ✓ | 105.5 | 7.03 | 18.0 | 2.564 | 13.54 | 2.05 | 2521 |
| hs-best-32x2-r1 (prefetch) | ✓ | 121.3 | 8.08 | 13.1 | 1.623 | 11.78 | 24.2 | 2193 |
| hs-best-32x2-r2 (prefetch) | ✓ | 124.0 | 8.27 | 13.4 | 1.619 | 11.51 | 24.96 | 2144 |
| hs-oob-r1 (prefetch) | ✓ | 118.8 | 7.92 | 18.5 | 2.339 | 12.02 | 2.16 | 2238 |

**Reading the rows.** RR best (16×2, rep 1) over HS best (32×2, rep 1): **1.58×** the
throughput at 0.63× the cost per footage-hour ($7.60 vs $12.03 per 1k fh). Best over
out-of-the-box: **RR 5.0×** (one pipeline is serialized by the detect node's device
lock at 6.3 cores; 16 pipelines fill the box), **HS 1.13×** (one unpinned uvicorn
worker already lets torch spread over 18 cores). Out of the box, HS is 2.8× faster
than RR. On AMI the same cells read 231–243× / 218–223× (best) and 41.8× / 74.3× (OOB);
films cost ~20% more per frame for RR at 1080p and hurt HS's best cell much more — see
below. Rep-1 numbers are the cache-warm ones (see *Repeatability*).

## The corpus

| | |
|---|---|
| Source | `s3://rocketride-benchmark-data/leela/corpus/archive_films_v2/` — Leela's sealed 500-film corpus (506 objects, 281.4 GB, 677.2 fh), frozen 2026-08-23 |
| Seal | `corpus_manifest.sha256` = `bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1`, verified on the laptop and on the box; the pin header quotes the same sha |
| Mirror | server-side copy to `s3://rocketride-benchmark-data/shashidhar/corpus/archive_films_v2/` — 506 objects, 281,399,710,498 bytes, byte-identical total to the source (24 min, no egress) |
| Subset | **films50** = the first 50 rows of the nested `archive_films_100.txt` (subsets are nested in queue order; the 50 pin is not shipped). Derived on the box by `stage_films.sh` with a header quoting the seal |
| Naming | objects and manifest keys are `<id>.mp4`; the pin's second column (original archive.org filename) is carried as `source_filename` only |
| Staging | `/data/seed-videos-films50/` in the `docker_bench-data` volume — 50 files, 26.81 GiB, **every file re-hashed against the sealed manifest** by `bench/build_films_manifest.py`; `seed_manifest_films50.json` records `duration_s` = ffprobe video-stream duration |
| Licences | 417 CC-licensed + 83 public-domain across the 500; per-film class carried in the manifest |

The chain is seal → manifest → bytes on our side too: a staged file that does not hash
to the sealed manifest aborts staging, and `fetch_video_seeds` re-hashes again before an
arm runs.

## The experiment

Same seven cells as `oob5-0830`, whole subset per cell (`--videos 0`), one arm at a time,
services **recreated** with the cell's envelope and the envelope **read back from inside
both containers** before each cell (`<cell>.envelope.json`):

| cell | arm | posture | env |
|---|---|---|---|
| `rr-oob-r1` | RR | 1 pipeline, `use()` with no `threads` argument, no OMP pin | `compose.oob.yml` (all `*_NUM_THREADS` pins stripped) |
| `hs-oob-r1` | HS | 1 uvicorn worker, client offers all 50 at once, no OMP pin | `compose.oob.yml` |
| `rr-best-16x2-r1/r2` | RR | 16 tasks (16 pipe copies, distinct `project_id`) × OMP 2 | pinned |
| `rr-best-32x1-r1` | RR | 32 tasks × OMP 1 | pinned |
| `hs-best-32x2-r1/r2` | HS | 32 uvicorn workers × OMP 2, client concurrency 32 | pinned |

Pipe `benchmark_video_detect.pipe`: frame_grabber every 15 s → RF-DETR (RFDETRBase,
threshold 0.3) → text chunks of the detection JSON (4000/200) → MiniLM
(`multi-qa-MiniLM-L6-cos-v1`, 384-d). Haystack mirrors it as a service
(`hs_service.py`); the driver imports neither framework.

Images: engine pinned (RocketRide 3.3.1 build, 2 weeks old); `haystack` and `bench`
rebuilt at launch (`images.txt` in the run dir). Each envelope also records
`hs_streaming_build=1` — the haystack container is proven to run the streaming
`hs_service.py`, not a stale layer.

## What changed for this corpus

1. **Haystack streams frames and uploads** (`07aba2c`). The service used to hold the whole
   film in RAM, write every frame as PNG to disk, and load *all* of them as PIL images
   before detecting — ~2.3 GB per 90-minute 1080p print, >60 GB at 32 workers (the
   failure Leela's LangGraph arm hit at 97 films). Now uploads spool to disk, ffmpeg
   emits `-f image2pipe -vcodec png` (what the engine's `VideoFrameExtractor` does), and
   frames are detected one at a time off the pipe; the client streams a chunked
   multipart body instead of building it in memory. Verified pixel-identical to the
   old path locally; the smoke ran two 1080p films at **2.2 GB** peak RSS.
2. **Manifest adapter** (`b451ef0`): Leela's columnar manifest + a pin → our
   `files[].{filename, sha256, bytes, duration_s}`.
3. **Orchestrator** (`b451ef0`): `oob5_campaign.sh` recovered from the box and committed;
   `films_campaign.sh` derived from it.

## Smoke (films10, 2 films, 3.1 fh) — `films10-smoke-20260903T181640Z`

| cell | ok | frames | dets | chunks | ×RT | cores | RSS GB | wall s | frame-law viol |
|---|---|---|---|---|---|---|---|---|---|
| RR 2 tasks × OMP2 | ✓ | 750 | 2246 | 159 | 64.1 | 6.3 | 3.07 | 175 | 0 |
| HS 2 workers × OMP2 | ✓ | 750 | 2191 | 155 | 42.0 | 2.9 | 2.20 | 268 | 0 |

`.mp4` routing, vintage codecs inside h.264, and the streaming path all pass; frame
counts match the manifest durations exactly (330 + 420). RR ran 2.1 frames/s per task at
OMP 2 with the box otherwise idle.

## Caveat that must travel with the numbers: detection parity on films

Frames are the same instants on both arms (exact counts, frame law 0), but the
detections are **not identical** the way they were on AMI (±1 over 197k there):

| film | RR frames/dets/chunks | HS frames/dets/chunks |
|---|---|---|
| BloodyPitOfHorror | 330 / 1060 / 73 | 330 / 1022 / 67 |
| JungleBook | 420 / 1186 / 86 | 420 / 1169 / 88 |

HS returns 1.4–3.6% fewer detections per film, and chunk counts drift with them. The
pixels handed to RF-DETR must differ slightly between the two decoders. Hypothesis
(unverified): YUV→RGB conversion matrix — swscale defaults to BT.709 for HD material,
while a BT.601 path agrees only at SD, which is exactly where AMI's 352×288 lived.
Consequence for reading this page: **work parity on films is "same frames, detections
within ~3%"**, so CPU-per-detection and chunk counts are approximate across arms;
throughput, CPU-per-frame and cost per footage-hour are not affected. Leela's films
track documents the same regime ("equal work within ~1.5%", never "identical").

## Cross-arm parity and determinism

**Work parity** (rr-best-16x2-r1 vs hs-best-32x2-r1, per film, 50 films): frames
identical on **50/50**; detections −5.0 … +3.2% per film, median −0.8%, six films beyond
±3%; chunks −8.2 … +4.3%, median −0.3%. Totals: 17,728 / 17,728 frames, 80,180 vs
79,430 detections (−0.9%), 5,873 vs 5,802 chunks (−1.2%). Same instants, slightly
different pixels — the caveat above — so throughput, CPU-per-frame and cost are
comparable across arms; CPU-per-detection and chunk counts are approximate.

**Determinism** (per-film digests):

| pair | identical films | detections |
|---|---|---|
| RR 16×2 rep1 vs rep2 | **50/50** | 80,180 / 80,180 |
| HS 32×2 rep1 vs rep2 | **50/50** | 79,430 / 79,430 |
| RR 16×2 vs RR 32×1 (OMP 2 vs 1) | 0/50 | 80,180 / 80,178 |
| RR 16×2 vs RR oob (OMP 2 vs unpinned) | 0/50 | 80,180 / 80,177 |
| HS 32×2 vs HS oob (OMP 2 vs unpinned) | 0/50 | 79,430 / 79,430 |

Both arms are deterministic at a fixed thread count. Across thread counts every
per-film digest changes while the detection totals move by ≤3: BLAS reduction order
shifts scores in the last bits, a handful cross the 0.3 threshold, and the serialized
JSON — hence the chunk text and its digest — differs. That is a property of the
detector under OpenMP, identical on both arms, and is why the campaign compares reps
within a configuration only.

## Haystack's best cell converts only a third of the box on films

`hs-best-32x2-r1` finished clean but at **10.8 effective cores** (20.6 on AMI) and
118.7× vs RR's 187.8×, while using *less* CPU per frame than RR (1.36 vs 2.20 CPU-s).
Its workers are latency-bound, not inefficient. Two contributors:

1. **Wave effect (certain).** 50 films over 32 workers is 1.56 waves — the second wave
   runs 18 workers — so utilization is capped near 78% before anything else. AMI's
   170 videos were 5.3 waves. `rr-best-32x1-r1` has the same 32-way shape and is the
   fair RR comparator for this; `rr-best-16x2` at 3.1 waves does not suffer it.
2. **Pipe stall (hypothesis).** The streaming `hs_service.py` reads ffmpeg's stdout
   synchronously in the detect thread through a 64 KB pipe, so ffmpeg can run ahead by
   a fraction of one PNG: decode and detection alternate inside each worker. The
   engine's reader (`ai/common/avi/frame.py`) is asynchronous and never waits on the
   detector. A local test with a low decode share (5 s decode vs 28 s detect) showed
   only a ~3% cost, so the stall matters only where decode is a large share of
   per-worker time — which is the box under 32 contending ffmpegs, not a laptop.
   Unproven at box scale.

**Tested.** The HS cells were re-run on build `4342711` with a reader thread draining
the pipe into a bounded queue (`HS_FRAME_PREFETCH=8`, ~50 MB/worker) and a page-cache
prewarm before each cell (envelopes: `prefetch=8`, corpus 26.8 GB resident). Output is
byte-identical to the non-prefetch runs on every film (50/50, 50/50,
50/50 digests), so the change touched scheduling only. Result:

| | without prefetch | with prefetch |
|---|---|---|
| hs-best-32x2 rep1 / rep2 | 118.7× / 124.2× (10.8 / 14.4 cores) | 121.3× / 124.0× (13.1 / 13.4 cores) |
| hs-oob | 105.5× (18.0 cores) | **118.8×** (18.5 cores) |

The best cell did not move: four runs at 118.7, 124.2, 121.3, 124.0 — mean **122.1×, cv 1.9%**.
Twelve minutes into the prefetch cell the container was at 25 cores with ten ffmpeg
decoders live, so the overlap exists — but the *span average* stayed at 13 because the
cell spends its second half in a tail: after the first 32 films the remaining 18 run on
18 workers, and the box empties film by film as the longest prints finish alone. The
stall hypothesis is **not supported** as the cause of HS's low utilization; the wave and
tail of 50 long films over 32 workers is. hs-oob gained 13% (one worker, 50 requests:
there the prefetch and the warm cache do buy overlap). HS's films50 best-config number is
therefore robust at ~122× either way; a fairer HS best on this subset needs a worker count
matched to the film count (25 → two full waves, or films100 → 3.1 waves), which this
campaign did not sweep.

Memory note: `rr-best-32x1` ran 32 model copies at 40 GB engine RSS (51.7 GB summed
task RSS), 20 GB available, no swap, no OOM — the ceiling posture on this box.

## Repeatability on films is a page-cache effect

`rr-best-16x2` rep 1 vs rep 2: **identical output** (50/50 per-film digests, 80,180
detections, 5,873 chunks both times) but 187.8× vs 159.7× — rep 2 spent 18% more
CPU-seconds in the span (46.2k vs 39.0k) at the same 27.6 cores, and its warm-up
slowed by the same 18% (633 vs 535 s). AMI's two reps agreed to 0.1%.

The cores were not slower (3147 MHz, no throttling); they were spinning. Rep 1 ran
minutes after staging with the 27 GB corpus in page cache; the 41 GB 32-copy cell
evicted it, and every cell since has read films from the gp3 root volume (125 MB/s
ceiling) while OMP threads spin through the stalls. Probed during `hs-best-32x2-r2`:
**11% iowait, 6 processes blocked on I/O**, ~80% of the corpus resident, disk reads
ongoing. So in this campaign the rep-1 cells are cache-warm and the rep-2 and OOB
cells are cache-cold; treat the rep-1 numbers as the clean ones and the spread as an
environment effect, not framework variance.

Mitigation, applied from the HS re-run onward: `films_campaign.sh` reads every seed
file once before each cell (`PREWARM=1`) and records residency before/after in the
envelope (`cache_resident_gb_before/after`, `prewarm_s`). For subsets whose corpus
does not fit beside the arm's working set (32 model copies at 41 GB + 27 GB), raise
the volume's throughput instead.

## Evidence grade

Single campaign plus an HS re-run; RR best has two reps (one cache-warm, one cold), HS best
has four (two builds × two reps, cv 1.9%), OOB cells one or two → **SIZING**, as with
`oob5-0830`. Determinism across reps is proven from per-film digests (50/50 on every pair
at a fixed thread count).

## Reproduce

```bash
# box-side, tree deployed at /home/ssm-user/rocketride-haystack-benchmarking
cd haystack-benchmark/orchestration
SUBSET=50 bash stage_films.sh                      # pull + hash-verify + manifest
SUBSET=50 nohup bash films_campaign.sh > ~/logs/films50.log 2>&1 < /dev/null &
```

Results land in `/root/films50-<stamp>/`, sync to
`s3://rocketride-benchmark-data/shashidhar/films50-<stamp>/` after every cell, and the
box stops itself three minutes after the final sync.
