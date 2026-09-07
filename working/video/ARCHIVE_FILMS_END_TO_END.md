# Archive Films — RocketRide vs LlamaIndex, end to end (35 films → 500 films)

**Status: FINAL, 2026-09-07.** One document, one set of conclusions. Where
it differs from the 35-film sizing report — one per-core figure and one
open detection mechanism — §6 says what was superseded and why. Every
figure traces to a committed artifact named beside it (§10).

## 1. Summary — the two engines do the work at the same cost per core; the visible gap is RocketRide's idle spin

| | |
|---|---|
| **What was run** | Two deployed video pipelines — RocketRide's engine and a LlamaIndex-based service on the identical model stack (RF-DETR base, threshold 0.3, one frame per 15 s, MiniLM embeddings) — on one 32-core machine (c7i.8xlarge, 61 GiB), at the configuration a measured sweep chose (16 workers × 2 threads on both arms, client concurrency 16). First 35 films to size and choose; then the full corpus, **498 films, 675.73 h, 161,932 frames per leg**, twice in one container lifetime and twice more in two freshly started container lifetimes. **Ten measured legs on the full corpus, 498/498 films each, 0 errors, every gate PASS or NOT RUN.** |
| **Finding 1 — cost per core** | Per effective core (the work once each side's idle spin leaves its own denominator) the two engines are a **statistical tie: LlamaIndex +0.7%**, at run-to-run spreads of 0.91% and 0.14%. Per measured core — the cost a user pays — **LlamaIndex +18.1%**, and that whole difference is **4.65 cores, 14.5% of the machine, that RocketRide spends idle holding 16 workers resident**. In throughput terms LlamaIndex +10.2% (12.80 vs 11.61 frames/s); at one machine price **$8.22 vs $7.46 per 1,000 footage-hours**. Same fact, three units. |
| **Finding 2 — detections above 560 px** | At or below 560 px the two arms' detections are bit-identical; above it they differ. On all 498 films the split held exactly as predicted before the run: **433 diverge, 65 agree, zero exceptions**. Cause, in the engine's source: its detection wrapper shrinks any frame wider than 560 px with its own resampler before the detector's own resize; the comparison arm hands the detector the raw frame. Reproduced bit for bit on the campaign's diverging frame. The detector's work is identical either way (a 560×560 tensor on both paths, measured), so scores change, speed does not. |
| **Finding 3 — why the numbers hold** | Four plausible alternatives — floating-point noise under load, disk caching, drift over a long-lived container, an asymmetric workload above 560 px — each died on a measurement this document shows (§8). |
| **What it means** | Tuned, the engine's only measured disadvantage is the idle cost of its worker model. Removing it brings cost per core to parity, since the work already is; the throughput gap would close only as far as the freed cores do work, which was not measured. Out of the box the engine runs at a quarter of its own tuned speed (2.35 vs 9.5 frames/s at 35 films; the same class of finding as the earlier AMI campaign's). The pre-inference downscale is a named, reproducible behaviour with a one-line fix path, filed upstream. |

```
LlamaIndex's lead over RocketRide, 498 films, fresh container lifetimes (n = 2 per arm)
per effective core (the work itself)       + 0.7%  ██
span throughput                            +10.2%  ████████████████████████████████████
per measured core (the cost a user pays)   +18.1%  ███████████████████████████████████████████████████████████████
```

## 2. Headline figures — three bases, one fact

| metric | RocketRide | LlamaIndex | difference |
|---|---|---|---|
| **Frames/s per EFFECTIVE core** (the work itself, idle removed) | 0.4389 | 0.4420 | **LI +0.7% — a statistical tie** |
| Frames/s per MEASURED core (the cost a user pays, idle included) | 0.3733 | 0.4411 | **LI +18.1%** |
| ↳ the same fact as CPU-seconds per frame | 2.679 | 2.268 | RR +18.1% |
| Span throughput (frames/s) | 11.613 | 12.800 | **LI +10.2%** |
| ↳ the same fact in dollars: cost per 1,000 footage-hours ($, at $1.428/h) | 8.22 | 7.46 | RR +10.2% |

Source: `results/films500_lifetimes_20260906T090339Z/export_*.json`, means of
passes 3 and 4 (decimal half-up rounding of the exports' own values);
effective cores = service cores minus each arm's own measured idle burden.
Three findings, not five: each indented row is the row above it in another
unit.

## 3. Full metric set, 498 films — RocketRide vs LlamaIndex

Means of the two fresh-lifetime passes unless a row says otherwise; the
per-leg table follows. Direction is stated in words in every row; the
source column, last, names the export field or reproducer behind it.

| metric | RocketRide | LlamaIndex | difference | source |
|---|---|---|---|---|
| **Scope** | | | | |
| Films measured per leg (count) | 498 / 498 | 498 / 498 | matched | `n_records` / `n_offered`, every leg |
| Footage (hours; corpus, 498 measured + 2 warm) | 675.73 | 675.73 | matched | `films500_video_manifest.jsonl` `_meta` |
| Frames per leg (count; one frame per 15 s) | 161,932 | 161,932 | matched | `throughput.total_frames` |
| Posture | 16 tokens × 2 threads | 16 instances × 2 threads | matched | thread environment read back in-process, fail-closed |
| Client concurrency (lanes) | 16 | 16 | matched | the export's provenance field `offered_concurrency` |
| Passes (count) | 2 + 2 | 2 + 2 | matched | 2 per fresh lifetime (passes 3–4) + 2 in one campaign lifetime (passes 1–2) |
| **Throughput** | | | | |
| Span throughput (frames/s) | 11.613 | 12.800 | LI +10.2% | `throughput.total_frames_per_s` |
| Steady-window throughput (frames/s; n = 482) | 11.649 | 12.783 | LI +9.7% | `steady_window.window_frames_per_s`; n = completions inside the window |
| Realtime factor (× footage time) | 173.8 | 191.6 | LI +10.2% | `throughput.total_realtime_factor` |
| Leg wall clock (s) | 13,944 | 12,651 | RR +10.2% longer | `throughput.total_span_s` (3.87 h / 3.51 h) |
| Sequential uncontended throughput (frames/s; C = 1, n = 5) | 2.081 | 1.834 | RR +13.5% | campaign `export_*_sequential.json`; the steady window is undefined at C = 1 by design |
| Sequential per-film latency, p50 (s per video-minute) | 1.81 | 2.10 | LI +16% (RocketRide faster) | `latency_normalized.p50`, sequential legs |
| **CPU** | | | | |
| Service cores (cgroup Δusage/Δt over the leg) | 31.10 | 29.02 | RR +7.2% | `efficiency.effective_cores` |
| Utilisation of the box (%) | 97.2 | 90.7 | RR +6.5 pts | `efficiency.cpu_util_of_box` |
| Idle burden (cores; instances live, no work) | 4.647 | 0.063 | RR 74× higher | `efficiency.idle_burden.idle_cores_with_instances_live` |
| Effective cores (service minus idle) | 26.46 | 28.96 | LI +9.4% | derived |
| Frames/s per measured core | 0.3733 | 0.4411 | LI +18.1% | derived |
| Frames/s per effective core | 0.4389 | 0.4420 | LI +0.7% (tie) | derived |
| CPU-seconds per frame | 2.679 | 2.268 | RR +18.1% | `efficiency.cpu_s_per_frame` |
| CPU-seconds per footage-minute | 10.74 | 9.09 | RR +18.1% | `efficiency.cpu_s_per_footage_min` |
| **Cost** | | | | |
| Cost per 1,000 footage-hours ($, at $1.428/h) | 8.22 | 7.46 | RR +10.2% | `efficiency.usd_per_1k_footage_hours` |
| **Memory** | | | | |
| Peak service RSS, process tree (GiB; p3 / p4) | 53.2 / 50.8 | 22.7 / 22.6 | RR 2.3× higher | `collector_summary.roles.service.peak_rss_bytes` |
| Peak cgroup anon (GiB; p3 / p4) | 45.5 / 43.1 | 1.08 / 1.08 | RR 41× higher | `collector_summary.roles.service.peak_cgroup_anon_mb` |
| Growth across a leg (GiB, first → last 5 min; p3; p4) | 26.7 → 52.5; 26.5 → 49.2 | 22.1 → 21.6; 21.8 → 21.6 | RR grows +25.7 / +22.7 GiB; LI flat | `lifetime_state.service_memory_trajectory.rss` |
| Per-film retention (MiB per film served; p3; p4) | 52.9; 46.6 | −1.1; −0.4 | RR retains; LI flat | growth ÷ 498; resets when the tokens end |
| Spool high-water on the host fs (GiB above leg start; p3 / p4) | 12.0 / 12.0 | 13.9 / 13.8 | LI +15.6% | `lifetime_state.fs_stream.paths.docker_root.max_used_minus_start` |
| Spool residue at leg end (files / KiB) | 18 / 76 (no media) | 3 / 32 per instance | — (no leak) | `lifetime_state.leg_end.containers.*.spool` |
| **Correctness** | | | | |
| Films completed (count, every leg) | 498 / 498 | 498 / 498 | matched | `n_records` |
| Errors (count) | 0 | 0 | matched | `n_errors` |
| Per-leg gates (PASS / NOT RUN / FAIL; both legs) | 8 / 1 / 0 | 7 / 1 / 0 | no FAIL either side | `gates`; NOT RUN = `determinism_repeat`, a sequential-leg gate (PASS there) |
| Determinism within arm, pass 3 ≡ pass 4 (films identical) | 498 / 498 | 498 / 498 | matched | labels, full-precision scores, chunk shas — `films500_held_checks.py` A |
| Determinism across lifetimes, campaign p2 ≡ p3 (films identical) | 498 / 498 | 498 / 498 | matched | same; two container lifetimes, two days apart |
| Cross-arm agreement ≤ 560 px (films bit-identical) | 65 of 65 | same films | matched | `partition_check.json`, both campaign passes; lifetimes pass 3: 0 differing |
| Cross-arm agreement > 560 px (films diverging) | 433 of 433 | same films | differ (engine pre-downscale, §7) | same; 0 violations either direction |
| **Reproducibility** | | | | |
| Pass-to-pass spread, fresh lifetime (%) | 0.91 | 0.14 | LI tighter | passes 3 vs 4 |
| Across lifetimes, campaign p2 vs fresh-lifetime mean (%) | +0.03 | −1.2 | both within 1.2% | 11.609 vs 11.613; 12.953 vs 12.800 |
| **Not in the records** | | | | |
| Per-stage timings (extract / detect / embed) | absent | present (`stage_s`) | — | RocketRide records carry no stage timings; the stage-flatness evidence in §7 is LlamaIndex-side |

Two memory rows, two instruments: **peak service RSS** is the collector's
maximum over 0.5 s samples of the whole leg; **growth across a leg** is the
same stream's first- and last-five-minute means — which is why the peak
(53.2 GiB) sits above the end-of-leg mean (52.5 GiB). Both are
given because the peak sizes the container and the growth names the
mechanism.

Per-leg detail (the settled campaign pass 2 shown for reference; the
campaign's pass 1 is excluded, §9):

| leg | span f/s | window f/s | CPU-s/frame | $/1k fh | service cores | util % | idle cores | × realtime | wall s | peak RSS GiB | container age at driver start |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RR pass 3 (fresh container) | 11.665 | 11.677 | 2.672 | 8.18 | 31.171 | 97.4 | 4.653 | 174.62 | 13,881 | 53.2 | 6 s |
| RR pass 4 | 11.560 | 11.620 | 2.685 | 8.25 | 31.038 | 97.0 | 4.640 | 173.05 | 14,008 | 50.8 | 16,530 s |
| RR campaign pass 2 (settled) | 11.609 | 11.613 | 2.678 | 8.22 | 31.084 | 97.1 | 4.656 | 173.77 | 13,949 | 54.3 | — |
| LI pass 3 (fresh containers) | 12.791 | 12.772 | 2.271 | 7.46 | 29.044 | 90.8 | 0.063 | 191.46 | 12,660 | 22.7 | 24 s |
| LI pass 4 | 12.809 | 12.794 | 2.264 | 7.45 | 28.994 | 90.6 | 0.062 | 191.73 | 12,642 | 22.6 | 13,563 s |
| LI campaign pass 2 (settled) | 12.953 | 12.957 | 2.196 | 7.36 | 28.450 | 88.9 | 0.067 | 193.90 | 12,501 | 22.8 | — |

## 4. Correctness and verification — what the gates assert, what the two arms are, what refuses a leg, and how to check the work

### 4a. The gates, named — what each asserts, its role, its null control, its verdict on this run

Per-leg gates run inside every measured leg on that arm's own records
(`export_*.json` → `gates`); the cross-arm gates run on the paired records
of the campaign's two passes (`cross_parity_blast*.json`); the partition
check is the plan-level finding surface (`partition_check.json`). "Absence
fails first": every gate treats a missing field as a failure, never as a
pass. Library: `harness/gates_shared.py`; wiring: `driver_video.py`
`leg_gates` / `cross_gates`.

| gate | asserts | role | null control | verdict on this run |
|---|---|---|---|---|
| `frames_census` (gate 1) | frames observed, read back from the arm's own records, equal `expected_frames_measured` per film exactly (frames cut by the same pinned ffmpeg at manifest build) | load-bearing — the equal-work basis of every frames/s figure | absence rule: an arm that cannot report its count fails; zero records fail | PASS, 498/498, all ten legs, both arms |
| `errors` | no errored record in the leg | load-bearing | — | PASS, 0 errors, all ten legs |
| `self_duplication_any` + `duplication_trigger` | the stock engine's flush defect (the whole chunk list emitted twice) is absent on every record; records with ≥ 64 chunks are the trigger-eligible set; an undecidable record reads "indeterminate", never PASS | load-bearing (the image label `duplication_patch_applied=1` is the fix; this gate proves it in the output) | indeterminate is a third state, not a pass | PASS: 0 doubled, 0 indeterminate; 428 trigger-eligible films (RR) |
| `chunkid_monotone` | chunk ids strictly increasing within every record | load-bearing (ordering) | — | PASS, 0 violations |
| `detection_liveness` (gate 5) | per leg, the fraction of frames with ≥ 1 detection ≥ 0.385 — a threshold derived by a committed rule from the staging run's measured per-film distribution, never a guess; absent → NOT RUN | load-bearing | the all-black-frame fixture (`probe/make_black_fixture.sh`) must produce ~all-empty frames and FAIL it | PASS (aggregate non-empty fraction 0.921 RR) |
| `embed_integrity` (gate 7) | every vector has dimension 384 and unit L2 norm within 0.001; absent vectors fail | load-bearing | absence rule | PASS, 53,522 (RR) / 40,970 (LI) vectors per blast leg |
| `determinism_repeat` (gate 8) | the same film sent twice through the same arm yields the identical chunk-hash list — nothing in this pipeline samples | load-bearing on sequential legs | an absent repeat side fails | PASS on both sequential legs; **NOT RUN on every blast leg by construction** (no repeat record exists there — the "1 NOT RUN" in §3) |
| `frame_count_methods_agree` (RR only) | the overlap-stripped bracket count of frames agrees with the raw-decode count; the naive bracket count is recorded as an upper bound only | load-bearing for RR frame counts | — | PASS, 0 disagreeing |
| `dropped_frame_attribution` (RR only, gate 2 attribution) | the engine log is scraped for dropped-frame warnings behind a liveness marker; a log with no marker reads UNKNOWN, never "no drops" | diagnostic (attributes; gate 1 detects) | fail-closed on its own channel | channel alive, 0 drop warnings |
| `thread_pin_parity` (preflight) | every reader — each RR task process, each LI worker — reports all six BLAS/OMP variables and the in-process torch thread count, and every value agrees with the posture; absence fails before agreement | load-bearing (posture identity) | `thread_pins_self_test`, both modes (pinned and unset) | PASS: 2 in every RR task process; 2 in all 16 LI workers |
| `cross_detection_agreement` (gate 3, `label_multiset_agreement`) | per-frame label multisets identical across arms, zero tolerance; a detection scored within 0.001 of the 0.3 threshold on both sides may be boundary-excluded, capped at 0.5% of a film's frames | load-bearing for detection equality only; never a throughput gate | **no committed null control** (a recorded gap); its verdict is corroborated by the partition prediction below and by `score_triage`, a diagnostic that separates threshold flapping from wholesale mismatch and never becomes a verdict | FAIL on 433 of 498 films, both passes — the ruled expectation, stated before the run; 49 frames boundary-excluded per pass (the cap is live and unsized for films: conservative, it can only turn a PASS into a FAIL) |
| partition check | every film above the 560 px long edge fails gate 3 and every film at or below it passes, on the decoded-frame dimension basis; a violation in either direction changes the ruling | load-bearing — the campaign's finding surface | the prediction (433 / 65) was written before the run | **HOLDS both passes: 433 / 65, 0 / 0 violations, 0 missing dimensions** (§7) |
| `char_conservation` | per film, the sum of chunk characters on the two arms agrees within ±2% | **DEFERRED** — confounded by §7 (different detections above 560 px produce different text), so the band it cuts is data, not a verdict; settled only by a like-for-like preprocessing run | absence fails per row | recorded PASS = false, worst deviation 6.1% at tol 2%, 498 pairs — ruled, not missed |
| `chunk_count_ratio` | RR chunks ÷ LI chunks per film | reported, not gated — the arms split with different native algorithms (4b) | — | min / median / max 1.114 / 1.292 / 1.482 |

### 4b. The two arms — checkable, not asserted

| | RocketRide arm | comparison arm (LlamaIndex) |
|---|---|---|
| image | `rr:patched-video`, id `b7f51acc…` — RocketRide 3.3.1 plus one documented derived layer; labels record `duplication_patch_applied=1` | `li:video`, id `0a52afcb…` — 149-pin frozen install with a fail-closed read-back of every pin at build (`docker/Dockerfile.llamaindex-video`) |
| serving shape | one engine; 16 `use()` tokens on ONE websocket from the SDK 1.3.0 client, ttl = 0; engine `threads=` unset (its default 64 admission); six BLAS/OMP variables = 2 in every task process | 16 uvicorn instances × 1 worker, ports 8802–8817; six variables = 2 in every worker; the driver spreads the films across the 16 ports |
| request path | webhook → `frame_grabber` (interval profile: one frame every 15 s, from 0, whole film) → `detect` (profile rfdetr = RF-DETR base, threshold 0.3; the facade's pre-inference downscale above 560 px, §7) → `preprocessor_langchain` (RecursiveCharacterTextSplitter, strlen mode) → `embedding_transformer` (miniLM profile, 384-d) → `response_documents` (`benchmark_video_detect.pipe`) | body streamed to a spool file, never held whole → ffmpeg `fps=1/15`, PNG frames on disk → RF-DETR base `predict` per frame, one frame resident at a time (k = 1), threshold 0.3 → SentenceSplitter with a character length function, 4000 / 0 → MiniLM 384-d (`li_video/service.py`, `pipeline.py`) |
| checkpoint | `rf-detr-base.pth` md5 `b4d3ce46…`, verified on the container at preflight | the same md5, verified on every one of the 16 instances at preflight |
| **known difference 1 — splitters** | RecursiveCharacterTextSplitter; realized chunk max 4000 chars, median 3,344 | SentenceSplitter at 4000 / 0 (read back from `/health` on every worker); realized max 4000, median 3,992. Consequence: RR emits 1.11–1.48× the chunks for the same text (median 1.29×), so chunk counts are never compared and chunk-level cost figures carry that ratio |
| **known difference 2 — preprocessing above 560 px** | the engine downscales the frame to a 560 px long edge before the detector (§7) | the raw frame reaches the detector |
| what is identical, proven | frames: same instants, same count per film (gate 1); detector code and weights (byte-identical `detr.py`, md5-matched checkpoint); model input tensor `[1, 3, 560, 560]` on both paths (§7) | |

### 4c. What refuses a leg before it starts

Every row is fail-closed unless marked "recorded": the driver stops with
`NOT DONE` and the leg never measures. Run log for this run:
`results/films500_lifetimes_20260906T090339Z/launch_console.log`.

| check | compares | on mismatch |
|---|---|---|
| corpus fetch | every file's sha256 against the sealed manifest; resume by sha | file refetched; the leg cannot see an unverified file |
| corpus at leg start | every file's size against the manifest plus 5 deterministic spot shas; the locator's `_meta.corpus_dir` stamp must name this corpus (full sha pass on demand) | `NOT DONE` |
| manifest rows | the leg's `--n` equals the manifest's measured rows (498) | `NOT DONE` |
| container flags | memory limit, log limit, image tag as declared in the plan | `NOT DONE` |
| network mode | host networking on both arms | recorded in provenance |
| quiet box | foreign busy cores = `/proc/stat` busy − our containers' cgroup − our own process; must be ≤ 2.0 cores (this run: 0.03 and 0.01) | `NOT DONE` unless `--allow-noisy-box`, which is itself recorded |
| SDK identity | the client's package version and entry-point surface (1.3.0); its own null control fires first | `NOT DONE` |
| thread environment | the six variables declared to docker, read back from every task process / worker, and the in-process torch thread count — all equal to the posture; absence fails before agreement | `NOT DONE` |
| task census | tokens declared (16) against new task processes measured in the container (16) | `NOT DONE` |
| checkpoint md5 | `rf-detr-base.pth` on the RR container and on every LI instance equals the registry md5 | `NOT DONE` |
| LI `/health` read-back | every declared worker answers; detector implementation reads back as rfdetr; chunk config reads back 4000 / 0; the read-back's own pass/refuse null controls must fire | `NOT DONE` |
| page-cache eviction | `posix_fadvise(DONTNEED)` over every corpus file, then a read-back: the `/proc/meminfo` Cached delta and timed 8 MiB re-reads of sampled files at device speed, not memory speed | `NOT DONE — eviction not proven` |
| CPU bracket and collector | every service container's cgroup `cpu.stat` readable; every container's root pid resolvable for the sampler | `NOT DONE` |
| warm-up coverage | every instance served a warm film before the leg (per-send ledger `warmup_*.json`) | the leg waits; coverage is gated |
| liveness threshold | present, derived from the staging artifact that must read `armed: true` and span the 560 px edge | gate 5 reads NOT RUN, never a guess; the plan refuses an unarmed staging |
| plan lock | one campaign or lifetimes run at a time (`flock`) | refuses, naming the live pid and its run dir |

### 4d. Reproduce, or join your own results against these

| what | value / where |
|---|---|
| corpus seal | `bd0c915e…` (the sealed 500-film manifest; every file sha-verified against it at fetch) |
| video manifests | 35-film subset `54186c24…`; 500-film `films500_video_manifest.jsonl` committed `075fc35b…` (box commit `10b1e76b`; the runs hashed the box's `_meta`-stamped working copy `c5a09a34…` — measured rows identical, 498/498, checked by the reproducer below) |
| pinned ffmpeg | `e7e7fb30…` — frame counts measured at manifest build through the arms' own binary |
| run dirs and commits | 35-film campaign `results/films_mainrun_20260901T204015Z/` (`646eaea`); posture sweep and C chain `results/posture-sweep-20260830/`, `results/c-sweep-20260831/`, `results/c-sweep-highc-20260831/`; 500-film campaign `results/films500_mainrun_20260904T204852Z/` (box `cc98ca6b`, bundle `1882c0d4…`); lifetimes `results/films500_lifetimes_20260906T090339Z/` (box `405d3c6`, bundle `dbe874bb…`); V-D `results/wrapper-resize-parity-20260907/` (box `844a990`, bundle `746208ce…`); isolation and frame-parity artifacts `results/detector-parity-y-20260902/`, `results/parity-failing-20260902/` |
| scripts, by stage | fetch `probe/fetch_films500.sh`; manifest `probe/build_films500_manifest.sh`; staging `probe/run_films500_staging.sh`; campaign `run_plan_films500.sh`; lifetimes `run_films500_lifetimes.sh`; V-D `probe/run_wrapper_resize_parity.sh`; the leg driver `driver_video.py`; box access `harness/box.sh` (every box action transcripted) |
| reproducers for every derived figure | `probe/films500_held_checks.py` (identity, partition, ratios, stage flatness, warm-ups, corpus reduction, manifest-row identity), `probe/lifetimes_reading.py` (drift, plateau, pre-registered verdicts; null control against the campaign), `probe/cachewatch_join.py` (the page-cache join), and `probe/end_to_end_figures_check.py`, which recomputes every figure in this document from the landed files and gates its commit |
| join key | per film: the manifest `file` name (= each record's `video`) and the file's sha256 (= each record's `submitted_sha256`, the bytes the driver actually sent) |
| caution 1 | any detection-equality comparison is scoped to ≤ 560 px on the long edge; above it the engine's pre-downscale makes the arms non-identical by construction (§7) |
| caution 2 | frame counts must come from a method that strips chunk-boundary retention (`frames_observed_method: bracket-count-overlap-stripped`; the naive count is recorded beside it as `frames_observed_naive_upper_bound`); a naive bracket counter over-reads — on one film it reads 416 where the engine's own stream, the detect text and the stripped count all agree on 395 |

## 5. Scope — a replicated, tuned, cold-start run of the full corpus

| property | this campaign |
|---|---|
| corpus | a frozen 500-film public-domain feature-film set with a sealed manifest (sha `bd0c915e…`), every file sha-verified at fetch; 498 measured + 2 disjoint warm films; 675.73 h; per-film frame counts measured at manifest build through the arms' own sha-pinned ffmpeg (`e7e7fb30…`) |
| posture | tuned on both arms (16 × 2), chosen by an 11-point posture sweep and a concurrency chain on the same corpus (§6) |
| replication | n = 2 per arm across two fresh container lifetimes (4 legs), plus 2 passes in one campaign lifetime; 10 measured legs in all, 0 errors |
| cold start | every leg evicts the corpus from page cache with a read-back proof and warms every instance on the two warm films before measuring |
| provenance | every export carries image id, thread-environment read-backs, task census, container age, idle burden with its basis, gates, and — in the lifetimes run — spool, cgroup and per-process memory and a host-filesystem fragmentation proxy at leg start and end |

What that gives: replication across container lifetimes rather than
within one; a measured configuration rather than an assumed one; and
cold-start figures that no cache state flatters.

## 6. How the configuration was measured, and what the 35-film run settled

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
| the detection partition | 27 films above 560 px diverging, 8 at or below agreeing; mechanism open | its §7 |

| superseded by the 500-film run | 35-film value | 500-film value | why |
|---|---|---|---|
| per effective core | LI +3.9% | LI +0.7% (tie) | at 35 films RocketRide was under-fed (79.8% utilisation) and half the completions landed in ramp and drain; both per-core figures overstated the gap |
| the divergence mechanism | "context-dependent; candidates engine-first" | the engine's pre-inference downscale, named and reproduced (§7) | the isolation probe had reproduced the comparison arm's detector path on both sides |

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

## 7. Above 560 px the detections differ because the engine pre-downscales — predicted, held, reproduced

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

## 8. Four alternative explanations, each killed by a measurement

| candidate | what would have shown it | what the data showed |
|---|---|---|
| **Reduction-order / thread-count variance under load** | run-to-run digest changes within an arm | **Zero.** Within each arm, pass 1 ≡ pass 2 (one lifetime), pass 3 ≡ pass 4 (a fresh lifetime), campaign pass 2 ≡ pass 3 (different lifetimes, two days apart): labels, full-precision scores, counts and chunk shas identical **498 / 498 on both arms, every pairing, including all 433 films above the edge** (`probe/films500_held_checks.py` A). The thread-count effect exists and measures 10⁻⁷ on the same frame (`results/detector-parity-y-20260902/`, intraop 16 vs 2); the divergence is 10⁻²–10⁻¹, deterministic, between arms. |
| **Page cache** | I/O wait rising with cost; residency differences | Every leg starts corpus-cold by construction (fadvise eviction with a timed re-read proof, `driver_video.py:2299-2310`); the per-film cold read (`read_s`) is flat by position; a minute-by-minute `/proc/meminfo` sampler beside the lifetimes run, 938 rows joined (`probe/cachewatch_join.py`): **I/O wait ≤ 1.4% of the box, flat; ρ(cost, iowait) −0.12 … −0.03**. Exonerated. |
| **Lifetime drift** (the campaign's pass 1 read as a transient settling into pass 2's plateau — pre-registered with confirming and refuting shapes) | fresh containers drifting like the campaign's pass 1 | **Refuted on its own terms** (`probe/lifetimes_reading.py`): fresh-container first passes RR −2.3%, LI −3.1% first → last fifth (bands +1..+6 / −6..−13); pass 4 reproduces pass 3's profile at the same level; pass 4 vs the campaign's pass 2: RR −0.04% (paired SE 0.57%), LI +1.32% (SE 0.77%) — the "plateau" is the norm and the campaign's pass 1 the anomaly (§9). The filesystem variant died with it: the ext4 free-space proxy is flat across ~1 TB of spool churn (`lifetime_state_prerun/postrun.json`); per-token memory climbed identically in every pass with flat cost. |
| **Workload asymmetry above 560 px** (RocketRide feeding its detector a smaller image on 87% of the corpus) | RocketRide doing measurably less detector work above the edge | **The model's input is the same size on both paths — `[1, 3, 560, 560]`, measured (V-D)**; RocketRide does 4.64 ms *more* preprocessing per frame; LlamaIndex's detect stage is flat across source resolutions (0.830–0.850 s/frame from 320×240 to 720×480); the RR/LI cost ratio is flat across the edge at comparable resolutions (540×360 1.106 · 640×480 1.114 · 720×480 1.113) (`films500_held_checks.py` B). No correction toward RocketRide. |

## 9. What remains open

| item | what we know | what would settle it |
|---|---|---|
| **our engine's CPU per frame** | RocketRide in our harness spends ~20% more CPU per frame than other measurements of the same engine at matched utilisation, on two corpora; page cache is excluded as the cause; unexplained, and ours to explain (`AMI_CROSS_TEAM_RECONCILIATION.md`) | a per-stage CPU split of one identical file through both harnesses, or an exchanged cgroup sampler stream |
| **the campaign's pass-1 pair — excluded, named, unexplained** | both first passes ran off their own settled level (RocketRide 5% fast, LlamaIndex 5% slow), in windows two days apart, each already visible in that window's warm-up sends before any measured work; RocketRide's did the same work in 5% fewer CPU-seconds at the same utilisation — an environmental effect, not a pass effect and not a comparison between the systems; every provenance scalar identical across passes | a CPU-frequency / host-contention sampler beside every leg; none existed |
| **per-token memory growth** | ~50 MB per film served, retained until the token ends; reproduced in all four passes (16 tokens: 26.5 → 49–52 GiB RSS over 498 films); no throughput effect | Ticket 6, criterion 5 |
| **detection-equality claims scoped to ≤ 560 px** | above the edge the arms are not like-for-like in preprocessing (the engine's fixed facade constant); throughput claims stand with §7 beside them | the comparison arm applying the same pre-downscale — the next campaign's candidate; it would also settle the deferred char-band gate |
| **H16's boundary-drift cap** | live, unsized for films; conservative direction (can only turn a PASS into a FAIL) | a films-sized denominator ruled before data |

## 10. Appendix — documents (run directories, scripts and reproducers are in §4d)

| document / artifact | what it is |
|---|---|
| `WS1_Phase2_Films500_Benchmark_DEFINITIVE.md` | the 500-film FINAL report (provenance, instrument defects, limitations) |
| `FILMS500_SUMMARY.md` | its two-minute plain-language layer |
| `WS1_Phase2_Films_Benchmark_DEFINITIVE.md` | the 35-film sizing report (FINAL 2026-09-03; its §6 addendum 2026-09-07) |
| `FILMS_SUMMARY.md` | its plain-language layer |
| `FILMS500_RESULTS.md` | the working record, including the withdrawn readings kept as written |
| `AMI_CROSS_TEAM_RECONCILIATION.md`, `AMI_CROSS_TEAM_COVER.md` | the CPU-per-frame reconciliation and its ask |
| `METHODOLOGY_REGISTER.md` | 35 entries — the discipline, with the incidents that taught it |
