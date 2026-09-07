# Archive Films — RocketRide vs LlamaIndex, end to end (35 films → 500 films)

**Status: FINAL, 2026-09-07 (Rulings AB / AC / AD).** One document, one set
of conclusions. It supersedes, where they differ, the 35-film sizing
report's per-core figure and its open detection mechanism — both are
explained below at the point where they were superseded. Every figure
traces to a committed artifact named beside it; the four campaign
documents it draws on stay in the repository as the record (Appendix).

## 1. One page: what was run, what was found, what it means

**What was run.** Two deployed AI video pipelines — RocketRide's engine
and a LlamaIndex-based service running the identical model stack
(RF-DETR base at threshold 0.3, one frame per 15 s, MiniLM embeddings)
— processed the same films on one 32-core machine (c7i.8xlarge, 61 GiB),
at the tuned configuration a measured sweep chose (16 workers × 2
threads on both sides, client concurrency 16). First 35 films (49.3 h of
footage) to size and choose the configuration; then the full corpus,
**498 films, 676 hours, 162,000 sampled frames**, twice inside one
container lifetime and then twice more inside two freshly started
container lifetimes. Ten measured legs on the full corpus, 498 films
each, zero errors, every gate passing.

**What was found.**

1. **The two engines do the work at the same cost per core; the entire
   visible gap is what RocketRide burns standing still.** Per effective
   core — the cost of the work once each side's idle spin leaves its own
   denominator — the two are a statistical tie (LlamaIndex +0.7%, with
   run-to-run spreads of 0.9% and 0.1%). Per measured core, the cost a
   user actually pays, LlamaIndex leads by 18%, and that whole difference
   is **4.65 cores — 14.5% of the machine — that RocketRide spends idle
   holding 16 workers resident**. In throughput terms LlamaIndex is
   +10.2% (12.80 vs 11.61 frames/s), which at one machine price is $8.22
   against $7.46 per thousand footage-hours. Same fact, three units.
2. **The big-video disagreement is explained, reproduced bit for bit,
   and it is the engine's own doing.** On video at or below 560 pixels
   the two systems agree to the last bit; above it their detections
   drift. The split held on all 498 films exactly as predicted before the
   run (433 diverge, 65 agree, zero exceptions). The cause is in the
   engine's source: its detection wrapper shrinks any frame wider than
   560 pixels with its own resampler before the detector applies its own
   resize; the comparison arm hands the detector the raw frame. The
   detector's work is identical either way (a 560×560 tensor on both
   paths, measured), so this changes scores, not speed.
3. **Four plausible explanations died on measurement** — floating-point
   noise under load, disk caching, drift over a long-lived container, and
   an asymmetric workload above 560 px — each killed by a measurement
   this document shows (§6). That is why the numbers above can be trusted.

**What it means.** Tuned, the engine's only measured disadvantage is the
idle cost of its worker model: 4.65 cores at 16 workers before any work
arrives. Removing it brings the cost per core to parity, since the work
itself already is; the throughput gap would close only to the extent
the freed cores actually do work, which was not measured. Out of the
box the engine runs at a quarter of its own tuned speed (2.35 vs 9.5
frames/s at 35 films; corroborated by two other teams on their own
corpora, §3). And the engine's pre-inference downscale means two correct
deployments of the same detector can disagree on borderline objects in
large video — now a named, reproducible behaviour with a one-line fix
path, filed upstream.

```
LlamaIndex's lead over RocketRide, 498 films, fresh container lifetimes (n = 2 per arm)
per effective core (the work itself)       + 0.7%  ██
span throughput                            +10.2%  ████████████████████████████████████
per measured core (the cost a user pays)   +18.1%  ███████████████████████████████████████████████████████████████
```

## 2. The headline table (500 films, fresh lifetimes — the numbers that ship)

Source: `results/films500_lifetimes_20260906T090339Z/export_*.json`
(box commit 405d3c6). Effective cores = measured cores minus each arm's
own measured idle burden (RR 4.647, LI 0.063). Three rows, not five: the
indented rows are the same fact in another unit, never a second finding.

| basis (p3 + p4 means) | LlamaIndex | RocketRide | LI vs RR |
|---|---|---|---|
| **frames/s per EFFECTIVE core** — the work itself, idle removed | 0.4420 | 0.4389 | **+0.7% — a statistical tie** |
| frames/s per MEASURED core — the cost a user pays, idle included | 0.4411 | 0.3733 | **LI +18.1%** |
| ↳ *the same fact as* RocketRide's CPU-seconds per frame: 2.679 vs 2.268 = RR +18.1% | | | |
| span throughput, frames/s | 12.800 | 11.613 | **LI +10.2%** |
| ↳ *the same fact in dollars* at $1.428/h: RR **$8.22** vs LI **$7.46** per 1,000 footage-hours | | | |

| leg | span f/s | steady window f/s | service cores | util | idle cores | CPU-s/frame | $/1k fh |
|---|---|---|---|---|---|---|---|
| RR pass 3 (fresh container) | 11.665 | 11.677 | 31.171 | 97.4% | 4.653 | 2.672 | 8.18 |
| RR pass 4 | 11.560 | 11.620 | 31.038 | 97.0% | 4.640 | 2.685 | 8.25 |
| LI pass 3 (fresh containers) | 12.791 | 12.772 | 29.044 | 90.8% | 0.063 | 2.271 | 7.46 |
| LI pass 4 | 12.809 | 12.794 | 28.994 | 90.6% | 0.062 | 2.264 | 7.45 |

Pass spreads: RR 0.91%, LI 0.14% — an order of magnitude below the
effect. The first campaign's two extra passes per arm (one container
lifetime, `results/films500_mainrun_20260904T204852Z/`) contain the
**excluded pass-1 pair** (§7): their settled pass 2 agrees with the table
(RR 11.609, LI 12.953) and is not in the means.

## 3. What this run is that no other run is

| | Shashi (RocketRide vs Haystack) | Leela (RocketRide vs LangGraph) | This campaign (RocketRide vs LlamaIndex) |
|---|---|---|---|
| films / footage | 50 films, 73.9 fh — the first 50 of the same sealed corpus | 498 films, ~675 fh — the same sealed corpus | **498 films, 675.7 fh** |
| RocketRide posture | tuned (16 tasks × OMP 2) | **default** (one pipeline, "engine threads unpinned") | **tuned (16 × 2)** |
| comparison arm | tuned (32 × 2) | c32 | **tuned (16 × 2)**, chosen by the same sweep method |
| replication | 2 reps (one cache-warm, one cold) | **1 rep — evidence grade SIZING; determinism NOT_RUN** | **n = 2 per arm across two fresh container lifetimes**, plus a settled campaign pass agreeing |
| legs / errors | 7 cells + 3 re-run cells | 2 | **10 legs, 0 errors, every gate PASS or NOT RUN** |
| source | `team_docs_received/VIDEO-FILMS50-RESULTS-2026-09-03.md` :3–6, :23–34, :225–226 | her `aws_videobench/runs/films500-sizing/report.txt` @ `3967d9f4` (object read; RR 2.367 f/s, $40.79) | this document, §2 |

Stated factually: ours is the only full-corpus run at tuned posture on
both arms with replication across container lifetimes. The other two
runs are the corroboration in §3 of `SHASHI_COMPARISON.md` and the
default-posture reference in §4 below; neither is a substitute.

## 4. How we got here — what changed the outcome

**The corpus, adopted.** Leela's sealed `archive_films_v2` (500
public-domain feature films, seal `bd0c915e…`, frozen 2026-08-23). Our 35
films are a pure function of her manifest (title-dedup, duration × bytes
terciles, k = 4 per cell; subset manifest `54186c24…`), our 498 measured
films are her measured set by construction (the two warm films derived as
corpus minus her set, diff = 0; `films500_video_manifest.jsonl`, box
commit `10b1e76b`), and Shashi's 50 are the first 50 rows of her nested
queue (his :52). Every file sha-verified against the seal at fetch. Three
teams, one corpus, byte-identical by construction.

**The 35-film sizing run (2026-09-01, `results/films_mainrun_20260901T204015Z/`,
commit `646eaea`; `WS1_Phase2_Films_Benchmark_DEFINITIVE.md`).** What it
bought: the configuration, measured rather than assumed (below); the
closure of the five blockers that stood between the 10-film smoke and a
full run — service-role peak memory measured single-lane on the largest
film, the driver made blob-free (~125 MB resident, tripwired), the
comparison arm rebuilt to stream frames to disk instead of holding whole
films (the failure Leela's LangGraph arm hit at 97 films), the same-frames
precondition proven byte-exact (A == B == C on three films), and disk
sizing; the out-of-box finding — **RocketRide's default runs at a quarter
of its own tuned speed (2.35 vs 9.5 f/s), using 20% of the machine**; the
idle burden — **4.66 cores at 16 tokens, 1.23 even with a single token**,
reported beside every number and never subtracted; and the detection
partition — 27 films above 560 px diverging, 8 at or below agreeing, with
an open mechanism. Two of its numbers are superseded here and only here:
its **+3.9% per effective core** (LI ahead) became **+0.7%** on the full
corpus with lifetimes controlled — at 35 films RocketRide was under-fed
(79.8% utilisation) and half the completions landed in ramp and drain,
so both per-core figures overstated the gap; and its "context-dependent"
mechanism became §5.

**The posture matrix — why the configuration is measured, not assumed.**
Eleven points, both arms swept by the same method, fresh containers per
point, thread environment read back fail-closed
(`results/posture-sweep-20260830/`; the DEFINITIVE §5):

```
frames/s at 35 films, C = min(2 × lanes, 35), one pass per point
rr  8×4    8.32 f/s  ██████████████████████████████████████████
rr 16×2    8.65 f/s  ███████████████████████████████████████████  ← chosen (Ruling M)
rr 32×1    6.86 f/s  ██████████████████████████████████
rr  4×8    7.29 f/s  ████████████████████████████████████
rr  8×2    8.13 f/s  █████████████████████████████████████████
rr 16×4    5.29 f/s  ██████████████████████████  (oversubscribed)
li  8×4   10.11 f/s  ███████████████████████████████████████████████████  (statistically tied with 16×2; 12% more CPU)
li 16×2   10.07 f/s  ██████████████████████████████████████████████████  ← chosen (Ruling M)
li  4×8    8.58 f/s  ███████████████████████████████████████████
li  8×2    9.87 f/s  █████████████████████████████████████████████████
li  8×8    2.20 f/s  ███████████  (oversubscribed)
```

LlamaIndex led at every matched posture; oversubscription cost RocketRide
38% and collapsed LlamaIndex 4.6×; half the thread spend (8 × 2) bought
~94% / ~98% of peak at 66–75% of the cores. (Two non-selected cells, rr
32×1 and li 8×2, carry an unexplained duplicate CPU reading, flagged
FINAL in the sizing report; their f/s values are unaffected.)

**The concurrency chain — the knee, by a rule written before the data
(0.7 marginal efficiency; `results/c-sweep-20260831/`,
`results/c-sweep-highc-20260831/`):**

```
frames/s vs client concurrency, 35 films, ruled postures, in-flight confirmed at every point
RR  C=8     8.21 f/s  █████████████████████████████████████████
RR  C=16    9.06 f/s  █████████████████████████████████████████████  ← knee (marginal efficiency 0.552 < 0.7)
RR  C=32    9.13 f/s  ██████████████████████████████████████████████  (+0.75%: a tie inside run-to-run variance)
LI  C=8     9.57 f/s  ████████████████████████████████████████████████
LI  C=16   10.22 f/s  ███████████████████████████████████████████████████  ← knee (0.534 < 0.7); LI's peak
LI  C=32    9.79 f/s  █████████████████████████████████████████████████  (−4.2%: two-deep per instance)
```

**Where the discipline caught something real.** Three catches changed
decisions; the rest of the smoke and staging work is in the record and
not here. (i) The 35-film gate-3 staging film was chosen for its
byte-parity proof, which selected a ≤ 560 px film — the one class that
cannot show the divergence; the 500-film staging therefore spanned the
edge, and the partition was predicted before the run. (ii) The first
isolation probe of the divergence was found, from its own recorded
thread fields, to have run at the wrong thread setting (register entry
30); the two-condition design followed. (iii) That probe, re-read against
the engine's source, turned out to have reproduced the comparison arm's
detector path on both sides — a probe measuring one arm twice (entry 33)
— which is what led to §5.

**The scale effect — why 500 films read faster than 35 on both arms.**
At 35 films the steady window ran 15–20% above the span (half the
completions in ramp and drain); at 498 films the two coincide. The 35-film
figures were right for 35 films; they were never steady-state figures.

```
span (█) vs steady window (░), frames/s — 35-film means vs 498-film fresh-lifetime means
RR   35 films  span     9.51  ████████████████████████████████████████████████
               window   8.26  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
RR  498 films  span    11.61  ██████████████████████████████████████████████████████████
               window  11.65  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
LI   35 films  span    10.13  ███████████████████████████████████████████████████
               window   8.44  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
LI  498 films  span    12.80  ████████████████████████████████████████████████████████████████
               window  12.78  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 5. The 560 px finding — predicted, held, named in source, reproduced

**Predicted before the run.** The 35-film partition (27 diverging above
the detector's 560 px input edge, 8 agreeing at or below) was written into
the 500-film plan as an expectation: 433 of the 498 measured films sit
above the edge (435 of 500; `films500_video_manifest.jsonl`), so gate 3
would fail on ~433 and the finding surface would be a partition check —
a violation in either direction would change the ruling.

**Held exactly, both passes.** `results/films500_mainrun_20260904T204852Z/
partition_check.json`: **433 above the edge diverge, 65 at or below agree
bit-for-bit, zero violations in either direction**; the one film at
exactly 560 px (JailBait, 560×380) agrees — the boundary is inclusive.
The lifetimes run, which had no partition step, reproduces it from its
records: 433 / 0 (`probe/films500_held_checks.py`, block A).

**Named in source.** The engine's detect node calls its `Detector` facade
(`engine/nodes/detect/IGlobal.py:74`, `IInstance.py:107`), whose `detect`
runs `resize_for_inference(image, infer_edge=560)` before the backend
(`ai/common/models/vision/detection.py:60, :466, :512-518`): a strict
no-op when the frame's long edge is ≤ 560, otherwise a PIL LANCZOS
downscale to the edge (`ai/common/image/dense_resize.py`). Only then does
RF-DETR apply its own resize — of every input — to a fixed 560×560 tensor
(`rfdetr/detr.py:379`). LlamaIndex hands RF-DETR the raw frame
(`li_video/pipeline.py:215`). Two resampling pipelines above 560 px, one
below. `infer_edge` is a fixed engine constant, unreachable from a pipe.
The source comment calls the downscale "lossless (boxes mapped back)":
true of coordinates, false of scores.

**Reproduced bit for bit (V-D, 2026-09-07,
`results/wrapper-resize-parity-20260907/`, box commit 844a990).** Frame 10
of HouseOnBareMountain (714×480), the campaign's diverging frame, through
the engine's own helper (714×480 → 560×376) then `predict`, inside the
engine image at the campaign thread condition with the checkpoint
md5-pinned: **RocketRide's six recorded detections, bit-equal at 9
decimals** (0.946473300 0.935210288 0.856113911 0.449365526 0.384643406
0.318114191). The raw frame: **LlamaIndex's five, bit-equal**. The ≤ 560
control is a no-op both ways; every prediction matched itself when run
twice. The model consumed `[1, 3, 560, 560]` on both paths (a forward
pre-hook at the eager call site) — **the work is symmetric**; the facade's
LANCZOS costs 4.64 ms per frame against ~0.84 s of detection, ~0.5% of
per-frame time, on RocketRide's side.

**Why it looked like something else for a week.** The 35-film campaign
excluded five candidates by measurement — different frames, PIL mode,
threshold amplification, library or build differences, and any static
difference in the detect path — and read the remainder as
"context-dependent". Its isolation probe had called `RFDETRBase().predict`
directly (the backend's path) on both sides: it faithfully reproduced
LlamaIndex's transformation chain twice, matched LlamaIndex, and never
entered the engine facade the node calls. Those five exclusions stand;
the reading is corrected in that report's §6 addendum. Filed upstream as
Ticket 6 (`working/upstream/RocketRide_Engine_Tickets.md`, measured
updates 3–4, criterion 4: match, remove, or document the facade
downscale).

## 6. Four mechanisms killed with data

| candidate | what would have shown it | what the data showed |
|---|---|---|
| **Reduction-order / thread-count variance under load** | run-to-run digest changes within an arm | **Zero.** Within each arm, pass 1 ≡ pass 2 (one lifetime), pass 3 ≡ pass 4 (a fresh lifetime), and campaign pass 2 ≡ pass 3 (different lifetimes, two days apart): labels, full-precision scores, counts and chunk shas identical **498 / 498 on both arms, every pairing, including all 433 films above the edge** (`probe/films500_held_checks.py`, block A). The thread-count effect exists and was measured on the same frame at 10⁻⁷ (`results/detector-parity-y-20260902/`, intraop 16 vs 2); the divergence is 10⁻²–10⁻¹, deterministic, between arms. |
| **Page cache** (a disk-caching effect another team measured on the same corpus) | I/O wait rising with cost; residency differences | Every leg starts corpus-cold by construction (fadvise eviction with a timed re-read proof, `driver_video.py:2299-2310`); the per-film cold read (`read_s`) is flat by position; a minute-by-minute `/proc/meminfo` sampler beside the lifetimes run, 938 rows joined (`probe/cachewatch_join.py`): **I/O wait ≤ 1.4% of the box, flat; ρ(cost, iowait) −0.12 … −0.03**. Exonerated for this run. |
| **Lifetime drift** (the first campaign's pass 1 read as a transient settling into pass 2's plateau — pre-registered with confirming and refuting shapes) | fresh containers drifting like the campaign's pass 1 | **Refuted on its own terms** (`probe/lifetimes_reading.py`): fresh-container first passes RR −2.3%, LI −3.1% first→last fifth (bands +1..+6 / −6..−13); pass 4 reproduces pass 3's profile at the same level; pass 4 vs the campaign's pass 2: RR −0.04% (paired SE 0.57%), LI +1.32% (SE 0.77%) — the "plateau" is the norm and the campaign's pass 1 the anomaly (§7). The filesystem variant died with it: the ext4 free-space proxy is flat across ~1 TB of spool churn (`lifetime_state_prerun/postrun.json`); per-token memory climbed identically in every pass with flat cost. |
| **Workload asymmetry above 560 px** (RocketRide feeding its detector a smaller image on 87% of the corpus) | RocketRide doing measurably less detector work above the edge | **The model's input is the same size on both paths — `[1, 3, 560, 560]`, measured (V-D)**; RocketRide does 4.64 ms *more* preprocessing per frame; LlamaIndex's detect stage is flat across source resolutions (0.831–0.850 s/frame from 320×240 to 720×480); the RR/LI cost ratio is flat across the edge at comparable resolutions (540×360 1.106 · 640×480 1.114 · 720×480 1.113) (`films500_held_checks.py`, block B). No correction toward RocketRide. |

## 7. What is open

- **The cross-team CPU-per-frame gap — ours to explain.** RocketRide in
  our harness spends ~20% more CPU per frame than in two other teams'
  harnesses at matched utilisation on byte-identical data: +19–20% on the
  AMI corpus (`AMI_CROSS_TEAM_RECONCILIATION.md` §3) and, on films,
  **+21.9%** against Shashi's tuned RR (2.679 vs 2.198; his :25) — where
  no corpus can be resident, so page cache is excluded (§9 there). The
  ask stands: a per-stage CPU split on one identical file, or an
  exchanged cgroup sampler stream (`AMI_CROSS_TEAM_COVER.md`). No
  cross-team CPU figure is publishable until it is settled.
- **The first campaign's pass-1 pair — excluded, named, unexplained.**
  Both first passes ran off their own settled level (RocketRide 5% fast,
  LlamaIndex 5% slow), in windows two days apart, each already visible in
  that window's warm-up sends before any measured work began, and
  RocketRide's did the same work in 5% fewer CPU-seconds at the same
  utilisation — an environmental effect on the machine, not a pass
  effect. Not a comparison between the systems. We lack the instrument
  (CPU frequency, host contention); Shashi's harness records CPU MHz, the
  read to adopt.
- **Per-token memory growth** — ~50 MB per film served, reset only when a
  token ends, reproduced in all four passes (16 tokens: 26.5 → 49–52 GiB
  RSS over 498 films); no throughput effect measured; Ticket 6.
- **Detection-equality claims are scoped to ≤ 560 px** until the like-
  for-like configuration (the comparison arm applying the engine's
  pre-downscale) is run; it is the next campaign's candidate, and it
  would also settle the char-band gate deferred under Ruling W. H16's
  drift cap stays unsized for films (conservative direction). The full
  inventory: `FILMS_HANDOFF.md`, closing block.

## 8. Appendix — where everything lives

| document / artifact | what it is |
|---|---|
| `WS1_Phase2_Films500_Benchmark_DEFINITIVE.md` | the 500-film FINAL report (13 sections; provenance and instrument defects) |
| `FILMS500_SUMMARY.md` | its two-minute plain-language layer |
| `WS1_Phase2_Films_Benchmark_DEFINITIVE.md` | the 35-film sizing report (FINAL 2026-09-03; §6 addendum 2026-09-07) |
| `FILMS_SUMMARY.md` | its plain-language layer |
| `FILMS500_RESULTS.md` | the working record, including the withdrawn readings kept as written |
| `SHASHI_COMPARISON.md` | our figures against Shashi's on the configurations both ran |
| `AMI_CROSS_TEAM_COVER.md`, `AMI_CROSS_TEAM_TABLE.md`, `AMI_CROSS_TEAM_RECONCILIATION.md` | the cross-team CPU package (AMI corpus) and its ask |
| `results/films_mainrun_20260901T204015Z/` | the 35-film campaign (commit `646eaea`) |
| `results/posture-sweep-20260830/`, `results/c-sweep-20260831/`, `results/c-sweep-highc-20260831/` | the posture matrix and C chain |
| `results/films500_mainrun_20260904T204852Z/` | the 500-film campaign (box commit `cc98ca6b`, bundle `1882c0d4…`) |
| `results/films500_lifetimes_20260906T090339Z/` | the lifetimes run (box commit `405d3c6`, bundle `dbe874bb…`) |
| `results/wrapper-resize-parity-20260907/` | V-D (box commit `844a990`, bundle `746208ce…`) |
| `results/detector-parity-y-20260902/`, `results/parity-failing-20260902/` | the isolation and frame-parity artifacts |
| `probe/films500_held_checks.py`, `probe/lifetimes_reading.py`, `probe/cachewatch_join.py` | the committed reproducers for every derived figure |
| `team_docs_received/` | the other teams' documents, held byte-for-byte with recorded hashes |
| `METHODOLOGY_REGISTER.md` | 35 entries — the discipline, with the incidents that taught it |
