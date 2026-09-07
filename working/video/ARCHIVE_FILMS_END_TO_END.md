# Archive Films — RocketRide vs LlamaIndex, end to end (35 films → 500 films)

**Status: FINAL, 2026-09-07.** One document, one set of conclusions. Where
it differs from the 35-film sizing report — one per-core figure and one
open detection mechanism — §5 says what was superseded and why. Every
figure traces to a committed artifact named beside it (§9).

## 1. Summary — the two engines do the work at the same cost per core; the visible gap is RocketRide's idle spin

| | |
|---|---|
| **What was run** | Two deployed video pipelines — RocketRide's engine and a LlamaIndex-based service on the identical model stack (RF-DETR base, threshold 0.3, one frame per 15 s, MiniLM embeddings) — on one 32-core machine (c7i.8xlarge, 61 GiB), at the configuration a measured sweep chose (16 workers × 2 threads on both arms, client concurrency 16). First 35 films to size and choose; then the full corpus, **498 films, 675.73 h, 161,932 frames per leg**, twice in one container lifetime and twice more in two freshly started container lifetimes. **Ten measured legs on the full corpus, 498/498 films each, 0 errors, every gate PASS or NOT RUN.** |
| **Finding 1 — cost per core** | Per effective core (the work once each side's idle spin leaves its own denominator) the two engines are a **statistical tie: LlamaIndex +0.7%**, at run-to-run spreads of 0.91% and 0.14%. Per measured core — the cost a user pays — **LlamaIndex +18.1%**, and that whole difference is **4.65 cores, 14.5% of the machine, that RocketRide spends idle holding 16 workers resident**. In throughput terms LlamaIndex +10.2% (12.80 vs 11.61 frames/s); at one machine price **$8.22 vs $7.46 per 1,000 footage-hours**. Same fact, three units. |
| **Finding 2 — detections above 560 px** | At or below 560 px the two arms' detections are bit-identical; above it they differ. On all 498 films the split held exactly as predicted before the run: **433 diverge, 65 agree, zero exceptions**. Cause, in the engine's source: its detection wrapper shrinks any frame wider than 560 px with its own resampler before the detector's own resize; the comparison arm hands the detector the raw frame. Reproduced bit for bit on the campaign's diverging frame. The detector's work is identical either way (a 560×560 tensor on both paths, measured), so scores change, speed does not. |
| **Finding 3 — why the numbers hold** | Four plausible alternatives — floating-point noise under load, disk caching, drift over a long-lived container, an asymmetric workload above 560 px — each died on a measurement this document shows (§7). |
| **What it means** | Tuned, the engine's only measured disadvantage is the idle cost of its worker model. Removing it brings cost per core to parity, since the work already is; the throughput gap would close only as far as the freed cores do work, which was not measured. Out of the box the engine runs at a quarter of its own tuned speed (2.35 vs 9.5 frames/s at 35 films; the same class of finding as the earlier AMI campaign's). The pre-inference downscale is a named, reproducible behaviour with a one-line fix path, filed upstream. |

```
LlamaIndex's lead over RocketRide, 498 films, fresh container lifetimes (n = 2 per arm)
per effective core (the work itself)       + 0.7%  ██
span throughput                            +10.2%  ████████████████████████████████████
per measured core (the cost a user pays)   +18.1%  ███████████████████████████████████████████████████████████████
```

## 2. Headline figures — three bases, one fact

Source: `results/films500_lifetimes_20260906T090339Z/export_*.json` (means of
passes 3 and 4; effective cores = service cores minus each arm's own
measured idle burden). Three findings, not five: each indented row is the
row above it in another unit.

| basis | unit | LlamaIndex | RocketRide | LI vs RR |
|---|---|---|---|---|
| **per EFFECTIVE core** — the work itself, idle removed | frames/s/core | 0.4420 | 0.4389 | **+0.7% — a statistical tie** |
| per MEASURED core — the cost a user pays, idle included | frames/s/core | 0.4411 | 0.3733 | **LI +18.1%** |
| ↳ the same fact as CPU-seconds per frame | CPU-s/frame | 2.268 | 2.679 | RR +18.1% |
| span throughput | frames/s | 12.800 | 11.613 | **LI +10.2%** |
| ↳ the same fact in dollars ($1.428/h) | $/1k footage-h | 7.46 | 8.22 | RR +10.2% |

## 3. Full metric set, 498 films — RocketRide vs LlamaIndex

Means of the two fresh-lifetime passes unless a row says otherwise; per-leg
values follow. Sources: the four lifetimes exports (`results/films500_lifetimes_
20260906T090339Z/`), the campaign's sequential and pass-2 exports
(`results/films500_mainrun_20260904T204852Z/`), `partition_check.json`,
and `probe/films500_held_checks.py` for the derived rows.

| metric | unit | RocketRide | LlamaIndex | note / source |
|---|---|---|---|---|
| **Scope** | | | | |
| films measured per leg | count | 498 / 498 | 498 / 498 | `n_records` / `n_offered`, every leg |
| footage | hours | 675.73 (corpus) | 675.73 | `films500_video_manifest.jsonl` `_meta` (498 measured + 2 warm films) |
| frames per leg | count | 161,932 | 161,932 | `throughput.total_frames`; one frame per 15 s |
| posture | — | 16 tokens × 2 threads | 16 instances × 2 threads | thread environment read back in-process, fail-closed |
| client concurrency | lanes | 16 | 16 | the export's provenance field `offered_concurrency` |
| passes | count | 2 per fresh lifetime (+ 2 in one campaign lifetime) | same | passes 3–4; campaign passes 1–2 |
| **Throughput** | | | | |
| span | frames/s | 11.613 | 12.800 | `throughput.total_frames_per_s` |
| steady window | frames/s (n) | 11.649 (n = 482) | 12.783 (n = 482) | `steady_window.window_frames_per_s`; n = completions inside the window |
| realtime factor | × | 173.8 | 191.6 | `throughput.total_realtime_factor` |
| leg wall clock | s | 13,944 | 12,651 | `throughput.total_span_s` (3.87 h / 3.51 h) |
| sequential, uncontended (C = 1, n = 5, campaign) | frames/s | 2.081 | 1.834 | `export_*_sequential.json`; steady window undefined at C = 1 by design |
| sequential per-film latency, p50 | s per video-minute | 1.81 | 2.10 | `latency_normalized.p50`, sequential legs |
| **CPU** | | | | |
| service cores | cores | 31.10 | 29.02 | `efficiency.effective_cores` (cgroup Δusage/Δt over the leg) |
| utilisation of the box | % | 97.2 | 90.7 | `efficiency.cpu_util_of_box` |
| idle burden, instances live, no work | cores | 4.647 | 0.063 | `efficiency.idle_burden.idle_cores_with_instances_live` |
| effective cores (service minus idle) | cores | 26.46 | 28.96 | derived |
| frames/s per measured core | frames/s/core | 0.3733 | 0.4411 | derived |
| frames/s per effective core | frames/s/core | 0.4389 | 0.4420 | derived |
| CPU-seconds per frame | CPU-s | 2.679 | 2.268 | `efficiency.cpu_s_per_frame` |
| CPU-seconds per footage-minute | CPU-s | 10.74 | 9.09 | `efficiency.cpu_s_per_footage_min` |
| **Cost** | | | | |
| cost per 1,000 footage-hours | $ | 8.22 | 7.46 | `efficiency.usd_per_1k_footage_hours` at $1.428/h |
| **Memory** | | | | |
| peak service RSS, process tree | GiB | 53.2 / 50.9 (p3 / p4) | 22.7 / 22.6 | `collector_summary.roles.service.peak_rss_bytes` |
| peak cgroup anon | GiB | 45.5 / 43.1 | 1.08 / 1.08 | `collector_summary.roles.service.peak_cgroup_anon_mb` |
| growth across a leg (first → last 5 min) | GiB | 26.7 → 52.5 (p3); 26.5 → 49.2 (p4) | 22.1 → 21.6; 21.8 → 21.6 | `lifetime_state.service_memory_trajectory.rss` |
| per-film retention | MiB per film served | 52.9 (p3); 46.6 (p4) | −1.1; −0.4 | growth ÷ 498; resets when the tokens end |
| spool high-water, host filesystem | GiB above leg start | 12.0 / 12.0 | 13.9 / 13.8 | `lifetime_state.fs_stream.paths.docker_root.max_used_minus_start` |
| spool residue at leg end | files / KiB | 18 / 76 (no media files) | 3 / 32 per instance | `lifetime_state.leg_end.containers.*.spool` — no leak |
| **Correctness** | | | | |
| films completed | count | 498 / 498, every leg | 498 / 498, every leg | `n_records` |
| errors | count | 0 | 0 | `n_errors` |
| per-leg gates | PASS / NOT RUN / FAIL | 8 / 1 / 0 (both legs) | 7 / 1 / 0 (both legs) | `gates`; NOT RUN = `determinism_repeat`, a sequential-leg gate (PASS there) |
| within-arm determinism, pass 3 ≡ pass 4 | films identical | 498 / 498 | 498 / 498 | labels, full-precision scores, chunk shas (`films500_held_checks.py` A) |
| within-arm determinism, campaign pass 2 ≡ pass 3 (two lifetimes, two days apart) | films identical | 498 / 498 | 498 / 498 | same |
| cross-arm agreement, ≤ 560 px | films bit-identical | 65 / 65 | | `partition_check.json` (campaign, both passes); lifetimes pass 3: 0 differing |
| cross-arm agreement, > 560 px | films diverging | 433 / 433 | | same; 0 violations either direction |
| **Reproducibility** | | | | |
| pass-to-pass spread, fresh lifetime | % | 0.91 | 0.14 | passes 3 vs 4 |
| across lifetimes, campaign pass 2 vs fresh-lifetime mean | % | +0.03 | −1.2 | 11.609 vs 11.613; 12.953 vs 12.800 |
| **Not in the records** | | | | |
| per-stage timings (extract / detect / embed) | — | absent | present (`stage_s`) | RocketRide records carry no stage timings; the stage-flatness evidence in §6 is LlamaIndex-side |

Per-leg detail (the settled campaign pass 2 shown for reference; the campaign's pass 1 is excluded, §8):

| leg | span f/s | window f/s | × realtime | wall s | service cores | util % | idle cores | CPU-s/frame | $/1k fh | peak RSS GiB | container age at driver start |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RR pass 3 (fresh container) | 11.665 | 11.677 | 174.62 | 13,881 | 31.171 | 97.4 | 4.653 | 2.672 | 8.18 | 53.2 | 6 s |
| RR pass 4 | 11.560 | 11.620 | 173.05 | 14,008 | 31.038 | 97.0 | 4.640 | 2.685 | 8.25 | 50.9 | 16,530 s |
| RR campaign pass 2 (settled) | 11.609 | 11.613 | 173.77 | 13,949 | 31.084 | 97.1 | 4.656 | 2.678 | 8.22 | 54.3 | — |
| LI pass 3 (fresh containers) | 12.791 | 12.772 | 191.46 | 12,660 | 29.044 | 90.8 | 0.063 | 2.271 | 7.46 | 22.7 | 24 s |
| LI pass 4 | 12.809 | 12.794 | 191.73 | 12,642 | 28.994 | 90.6 | 0.062 | 2.264 | 7.45 | 22.6 | 13,563 s |
| LI campaign pass 2 (settled) | 12.953 | 12.957 | 193.90 | 12,501 | 28.450 | 88.9 | 0.067 | 2.196 | 7.36 | 22.8 | — |

## 4. Scope — a replicated, tuned, cold-start run of the full corpus

| property | this campaign |
|---|---|
| corpus | a frozen 500-film public-domain feature-film set with a sealed manifest (sha `bd0c915e…`), every file sha-verified at fetch; 498 measured + 2 disjoint warm films; 675.73 h; per-film frame counts measured at manifest build through the arms' own sha-pinned ffmpeg (`e7e7fb30…`) |
| posture | tuned on both arms (16 × 2), chosen by an 11-point posture sweep and a concurrency chain on the same corpus (§5) |
| replication | n = 2 per arm across two fresh container lifetimes (4 legs), plus 2 passes in one campaign lifetime; 10 measured legs in all, 0 errors |
| cold start | every leg evicts the corpus from page cache with a read-back proof and warms every instance on the two warm films before measuring |
| provenance | every export carries image id, thread-environment read-backs, task census, container age, idle burden with its basis, gates, and — in the lifetimes run — spool, cgroup and per-process memory and a host-filesystem fragmentation proxy at leg start and end |

What that gives: replication across container lifetimes rather than
within one; a measured configuration rather than an assumed one; and
cold-start figures that no cache state flatters.

## 5. How the configuration was measured, and what the 35-film run settled

**The 35-film sizing run** (`results/films_mainrun_20260901T204015Z/`, commit
`646eaea`; `WS1_Phase2_Films_Benchmark_DEFINITIVE.md`): 35 measured films
chosen as a pure function of the sealed manifest (title-dedup, duration ×
bytes terciles, k = 4 per cell; subset manifest `54186c24…`), 49.3 h.

| what it settled | figure | source |
|---|---|---|
| the posture, both arms | 16 × 2 (chart below) | `results/posture-sweep-20260830/` |
| the client concurrency | C = 16, the knee by a rule written before the data | `results/c-sweep-20260831/`, `results/c-sweep-highc-20260831/` |
| the five blockers between a smoke and a full run | service-role peak memory measured single-lane; the driver made blob-free (~125 MB resident, tripwired); the comparison arm rebuilt to stream frames to disk; the same-frames precondition proven byte-exact (A == B == C on three films); disk sizing | `FILMS_HANDOFF.md` §2 |
| out-of-the-box RocketRide | 2.35 frames/s, 20% of the machine — a quarter of its tuned 9.5 | `export_rocketride_video_default_blast*.json` |
| the idle burden | 4.66 cores at 16 tokens; 1.23 with a single token | `efficiency.idle_burden` |
| the detection partition | 27 films above 560 px diverging, 8 at or below agreeing; mechanism open | its §6 |

| superseded by the 500-film run | 35-film value | 500-film value | why |
|---|---|---|---|
| per effective core | LI +3.9% | LI +0.7% (tie) | at 35 films RocketRide was under-fed (79.8% utilisation) and half the completions landed in ramp and drain; both per-core figures overstated the gap |
| the divergence mechanism | "context-dependent; candidates engine-first" | the engine's pre-inference downscale, named and reproduced (§6) | the isolation probe had reproduced the comparison arm's detector path on both sides |

```
frames/s at 35 films, C = min(2 × lanes, 35), one pass per point — the posture matrix
rr  8×4    8.32 f/s  ██████████████████████████████████████████
rr 16×2    8.65 f/s  ███████████████████████████████████████████  ← chosen
rr 32×1    6.86 f/s  ██████████████████████████████████
rr  4×8    7.29 f/s  ████████████████████████████████████
rr  8×2    8.13 f/s  █████████████████████████████████████████
rr 16×4    5.29 f/s  ██████████████████████████  (oversubscribed)
li  8×4   10.11 f/s  ███████████████████████████████████████████████████  (tied with 16×2; 12% more CPU)
li 16×2   10.07 f/s  ██████████████████████████████████████████████████  ← chosen
li  4×8    8.58 f/s  ███████████████████████████████████████████
li  8×2    9.87 f/s  █████████████████████████████████████████████████
li  8×8    2.20 f/s  ███████████  (oversubscribed)
```

LlamaIndex led at every matched posture; oversubscription cost RocketRide
38% and collapsed LlamaIndex 4.6×; half the thread spend (8 × 2) bought
~94% / ~98% of peak at 66–75% of the cores. (Two non-selected cells, rr
32×1 and li 8×2, carry an unexplained duplicate CPU reading, flagged FINAL
in the sizing report; their frames/s are unaffected.)

```
frames/s vs client concurrency, 35 films, chosen postures, in-flight confirmed at every point
RR  C=8     8.21 f/s  █████████████████████████████████████████
RR  C=16    9.06 f/s  █████████████████████████████████████████████  ← knee (marginal efficiency 0.552 < 0.7)
RR  C=32    9.13 f/s  ██████████████████████████████████████████████  (+0.75%: a tie inside run-to-run variance)
LI  C=8     9.57 f/s  ████████████████████████████████████████████████
LI  C=16   10.22 f/s  ███████████████████████████████████████████████████  ← knee (0.534 < 0.7); LlamaIndex's peak
LI  C=32    9.79 f/s  █████████████████████████████████████████████████  (−4.2%: two-deep per instance)
```

**Three catches that changed decisions** (the rest of the smoke and staging
work is in the record, not here):

| catch | consequence |
|---|---|
| the 35-film gate-3 staging film was chosen for its byte-parity proof, which selected a ≤ 560 px film — the one class that cannot show the divergence | the 500-film staging spanned the edge, and the partition was predicted before the run |
| the first isolation probe of the divergence was found, from its own recorded thread fields, to have run at the wrong thread setting | the two-condition design followed |
| that probe, re-read against the engine's source, had reproduced the comparison arm's detector path on both sides — a probe measuring one arm twice | the confirmation in §6 |

**The scale effect — why 498 films read faster than 35 on both arms:** at
35 films the steady window ran 15–20% above the span (half the
completions in ramp and drain); at 498 the two coincide. The 35-film
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

## 6. Above 560 px the detections differ because the engine pre-downscales — predicted, held, reproduced

| step | result | source |
|---|---|---|
| predicted before the run | 433 of 498 measured films sit above the detector's 560 px input edge (435 of 500); gate 3 expected to fail on ~433; a violation in either direction would change the ruling | `films500_video_manifest.jsonl`; `run_plan_films500.sh` |
| held, campaign pass 1 and pass 2 | **433 above diverge, 65 at or below agree bit-for-bit, 0 violations**; the one film at exactly 560 px (560×380) agrees — inclusive boundary | `results/films500_mainrun_20260904T204852Z/partition_check.json` |
| reproduced, lifetimes pass 3 (no partition step) | 433 / 0 | `probe/films500_held_checks.py` A |

**Named in source:**

| component | where | behaviour |
|---|---|---|
| detect node | `engine/nodes/detect/IGlobal.py:74`, `IInstance.py:107` | builds the engine's `Detector` facade and calls its `detect` on the losslessly decoded frame |
| the facade | `ai/common/models/vision/detection.py:60, :466, :512-518` | runs `resize_for_inference(image, infer_edge=560)` before the backend; `infer_edge` is a fixed constant, not reachable from a pipe |
| the helper | `ai/common/image/dense_resize.py` | no-op when the long edge is ≤ 560; otherwise a PIL LANCZOS downscale to `floor(w·s) × floor(h·s)`, `s = 560 / max(w, h)`; boxes mapped back |
| the detector | `rfdetr/detr.py:379` | resizes every input, whatever its size, to a fixed 560×560 tensor before inference |
| the comparison arm | `li_video/pipeline.py:215` | hands the detector the raw frame |

Two resampling pipelines above 560 px, one below. The source comment calls
the downscale "lossless (boxes mapped back)" — true of coordinates, false
of scores.

**Reproduced bit for bit** (V-D, 2026-09-07, `results/wrapper-resize-parity-
20260907/`, box commit 844a990; inside the engine image at the campaign
thread condition, checkpoint md5-pinned; frame 10 of the campaign's
diverging film, 714×480):

| path | detections at threshold 0.3 | matches |
|---|---|---|
| raw frame → detector | 5: 0.953240395 0.934387743 0.862633228 0.489725053 0.432809502 | LlamaIndex's campaign record, bit-equal at 9 decimals |
| engine helper (714×480 → 560×376) → detector | 6: 0.946473300 0.935210288 0.856113911 0.449365526 0.384643406 0.318114191 | RocketRide's campaign record, bit-equal at 9 decimals |
| ≤ 560 px control, both ways | identical | no-op confirmed |
| model input tensor, both paths | `[1, 3, 560, 560]` | the work is symmetric |
| cost of the facade's LANCZOS pass | 4.64 ms per frame (median of 5) | ~0.5% of ~0.84 s per-frame detection, on RocketRide's side |

Every prediction matched itself when run twice. Filed upstream as Ticket 6
(`working/upstream/RocketRide_Engine_Tickets.md`, measured updates 3–4,
criterion 4: match, remove, or document the facade downscale).

## 7. Four alternative explanations, each killed by a measurement

| candidate | what would have shown it | what the data showed |
|---|---|---|
| **Reduction-order / thread-count variance under load** | run-to-run digest changes within an arm | **Zero.** Within each arm, pass 1 ≡ pass 2 (one lifetime), pass 3 ≡ pass 4 (a fresh lifetime), campaign pass 2 ≡ pass 3 (different lifetimes, two days apart): labels, full-precision scores, counts and chunk shas identical **498 / 498 on both arms, every pairing, including all 433 films above the edge** (`probe/films500_held_checks.py` A). The thread-count effect exists and measures 10⁻⁷ on the same frame (`results/detector-parity-y-20260902/`, intraop 16 vs 2); the divergence is 10⁻²–10⁻¹, deterministic, between arms. |
| **Page cache** | I/O wait rising with cost; residency differences | Every leg starts corpus-cold by construction (fadvise eviction with a timed re-read proof, `driver_video.py:2299-2310`); the per-film cold read (`read_s`) is flat by position; a minute-by-minute `/proc/meminfo` sampler beside the lifetimes run, 938 rows joined (`probe/cachewatch_join.py`): **I/O wait ≤ 1.4% of the box, flat; ρ(cost, iowait) −0.12 … −0.03**. Exonerated. |
| **Lifetime drift** (the campaign's pass 1 read as a transient settling into pass 2's plateau — pre-registered with confirming and refuting shapes) | fresh containers drifting like the campaign's pass 1 | **Refuted on its own terms** (`probe/lifetimes_reading.py`): fresh-container first passes RR −2.3%, LI −3.1% first → last fifth (bands +1..+6 / −6..−13); pass 4 reproduces pass 3's profile at the same level; pass 4 vs the campaign's pass 2: RR −0.04% (paired SE 0.57%), LI +1.32% (SE 0.77%) — the "plateau" is the norm and the campaign's pass 1 the anomaly (§8). The filesystem variant died with it: the ext4 free-space proxy is flat across ~1 TB of spool churn (`lifetime_state_prerun/postrun.json`); per-token memory climbed identically in every pass with flat cost. |
| **Workload asymmetry above 560 px** (RocketRide feeding its detector a smaller image on 87% of the corpus) | RocketRide doing measurably less detector work above the edge | **The model's input is the same size on both paths — `[1, 3, 560, 560]`, measured (V-D)**; RocketRide does 4.64 ms *more* preprocessing per frame; LlamaIndex's detect stage is flat across source resolutions (0.831–0.850 s/frame from 320×240 to 720×480); the RR/LI cost ratio is flat across the edge at comparable resolutions (540×360 1.106 · 640×480 1.114 · 720×480 1.113) (`films500_held_checks.py` B). No correction toward RocketRide. |

## 8. What remains open

| item | what we know | what would settle it |
|---|---|---|
| **our engine's CPU per frame** | RocketRide in our harness spends ~20% more CPU per frame than other measurements of the same engine at matched utilisation, on two corpora; page cache is excluded as the cause; unexplained, and ours to explain (`AMI_CROSS_TEAM_RECONCILIATION.md`) | a per-stage CPU split of one identical file through both harnesses, or an exchanged cgroup sampler stream |
| **the campaign's pass-1 pair — excluded, named, unexplained** | both first passes ran off their own settled level (RocketRide 5% fast, LlamaIndex 5% slow), in windows two days apart, each already visible in that window's warm-up sends before any measured work; RocketRide's did the same work in 5% fewer CPU-seconds at the same utilisation — an environmental effect, not a pass effect and not a comparison between the systems; every provenance scalar identical across passes | a CPU-frequency / host-contention sampler beside every leg; none existed |
| **per-token memory growth** | ~50 MB per film served, retained until the token ends; reproduced in all four passes (16 tokens: 26.5 → 49–52 GiB RSS over 498 films); no throughput effect | Ticket 6, criterion 5 |
| **detection-equality claims scoped to ≤ 560 px** | above the edge the arms are not like-for-like in preprocessing (the engine's fixed facade constant); throughput claims stand with §6 beside them | the comparison arm applying the same pre-downscale — the next campaign's candidate; it would also settle the deferred char-band gate |
| **H16's boundary-drift cap** | live, unsized for films; conservative direction (can only turn a PASS into a FAIL) | a films-sized denominator ruled before data |

## 9. Appendix — artifacts and documents

| document / artifact | what it is |
|---|---|
| `WS1_Phase2_Films500_Benchmark_DEFINITIVE.md` | the 500-film FINAL report (provenance, instrument defects, limitations) |
| `FILMS500_SUMMARY.md` | its two-minute plain-language layer |
| `WS1_Phase2_Films_Benchmark_DEFINITIVE.md` | the 35-film sizing report (FINAL 2026-09-03; §6 addendum 2026-09-07) |
| `FILMS_SUMMARY.md` | its plain-language layer |
| `FILMS500_RESULTS.md` | the working record, including the withdrawn readings kept as written |
| `AMI_CROSS_TEAM_RECONCILIATION.md`, `AMI_CROSS_TEAM_COVER.md` | the CPU-per-frame reconciliation and its ask |
| `results/films_mainrun_20260901T204015Z/` | the 35-film campaign (commit `646eaea`) |
| `results/posture-sweep-20260830/`, `results/c-sweep-20260831/`, `results/c-sweep-highc-20260831/` | the posture matrix and concurrency chain |
| `results/films500_mainrun_20260904T204852Z/` | the 500-film campaign (box commit `cc98ca6b`, bundle `1882c0d4…`) |
| `results/films500_lifetimes_20260906T090339Z/` | the lifetimes run (box commit `405d3c6`, bundle `dbe874bb…`) |
| `results/wrapper-resize-parity-20260907/` | V-D (box commit `844a990`, bundle `746208ce…`) |
| `results/detector-parity-y-20260902/`, `results/parity-failing-20260902/` | the isolation and frame-parity artifacts |
| `probe/films500_held_checks.py`, `probe/lifetimes_reading.py`, `probe/cachewatch_join.py` | committed reproducers for every derived figure |
| `METHODOLOGY_REGISTER.md` | 35 entries — the discipline, with the incidents that taught it |
