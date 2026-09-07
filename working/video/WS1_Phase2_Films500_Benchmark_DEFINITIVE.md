# WS-1 Phase 2 — Archive Films, the full corpus (500 films): RocketRide vs LlamaIndex

**FINAL (2026-09-07; Rulings AB, AC, AD — "the campaign is closed on
evidence").** Companion to `WS1_Phase2_Films_Benchmark_DEFINITIVE.md`
(the 35-film sizing campaign, FINAL 2026-09-03, whose §6 this report's §6
closes) and `WS1_Phase2_Video_Benchmark_DEFINITIVE.md` (AMI). Three runs,
all landed in-repo by entry-26 bundle with box-printed hashes matched on
fetch: the **campaign** (`results/films500_mainrun_20260904T204852Z/`,
box commit `cc98ca6b`, bundle `1882c0d4…`; six legs, 2026-09-04/05), the
**lifetimes run** (`results/films500_lifetimes_20260906T090339Z/`, box
commit `405d3c6`, bundle `dbe874bb…`; four legs, 2026-09-06 09:03Z →
09-07 01:48Z; four landed files sha-matched the live S3 mirror) and
**V-D** (`results/wrapper-resize-parity-20260907/`, box commit `844a990`,
bundle `746208ce…`). Box `i-0775f33f3dc16f6af` (c7i.8xlarge, 32 vCPU /
61 GiB). **Ten measured legs, 498 films each, 0 errors, every per-leg
gate PASS or NOT RUN.** Every number below is the landed export's or
record's own field; where a claim is a reading, it says so. Working
record, including the readings this report withdraws, kept as written:
`FILMS500_RESULTS.md`. Plain-language layer: `FILMS500_SUMMARY.md`.

## 1. Corpus and configuration (ruled before the run)

- **Corpus**: the frozen 500-film Archive Films set — **498 measured + 2
  warm** (`yanks_are_coming.mp4`, `zontar_the_thing_from_venus.mp4`,
  derived at build as corpus minus Leela's measured set; our 498 ≡ hers
  by construction, diff = 0), corpus manifest sha `bd0c915e…`, files
  sha-verified at fetch; 162,511 frames at one per 15 s (161,932 in the
  measured 498), **675.73 h** of footage; frames cut by the arms' own
  pinned ffmpeg (`e7e7fb30…`). Dimensions on two labelled bases
  (container header, decoded PNG); they coincide on all 500; **435 of
  500 (433 measured) have a long edge above 560px** — the detector
  basis the partition uses. Video manifest committed at box commit
  `10b1e76b` (`films500_video_manifest.jsonl`, sha `075fc35b…`).
- **Posture** (Ruling: scope 2026-09-03): RocketRide M16×T2 (16 `use()`
  tokens on one websocket, six BLAS/OMP vars = 2, ttl = 0, engine
  `threads=` default 64 admission) vs LlamaIndex N16×T2 (16
  single-worker uvicorn instances, ports 8802–8817, six vars = 2);
  client concurrency C = 16; the RocketRide default cell deliberately
  NOT run at 500 (answered twice at n = 2, 0.77% spreads, at 35 and 168
  — it ships at its own N). Sequential n = 5 per cell, not scaled.
- **Stack, identical both arms**: RF-DETR base (rfdetr 1.5.2, `detr.py`
  byte-identical in both containers, weights md5 `b4d3ce46…`), threshold
  0.3, torch 2.10.0+cu128, torchvision 0.25.0, pillow 10.4.0; miniLM
  embeddings; RecursiveCharacterTextSplitter (RR) vs SentenceSplitter
  (LI) as before. Engine image `rr:patched-video` (`b7f51acc…`, Crossroad
  33 lineage), SDK 1.3.0; LI image `li:video` (149-pin freeze, b295dea).
- **Design of the lifetimes run** (ruled 2026-09-06 after a contest the
  measurement won): two FRESH container lifetimes, arms alternated
  against the campaign (RR first), two passes each, container age and
  pass-in-lifetime recorded in every export; throughput only — no cross
  gates, no partition step; every reading pre-registered before the run
  (`run_films500_lifetimes.sh` header; `probe/lifetimes_reading.py`
  committed first, null control against the campaign PASS).
- **Cold start by construction**: every leg evicts the corpus from page
  cache (`posix_fadvise(DONTNEED)` per file with a timed re-read proof;
  the driver refuses otherwise) and warms every instance on the two
  disjoint warm films; the 263 GB corpus can never be resident in 61 GiB.
  Cost basis $1.428/h (c7i.8xlarge on-demand, the basis both teams use).

## 2. The headline (Ruling AB — FINAL)

Lifetime-controlled: n = 2 per arm across two fresh container lifetimes,
four passes, **pass spreads 0.91% (RR) and 0.14% (LI)** — an order of
magnitude below the effect. Effective cores = measured cores minus each
arm's own idle burden (RR 4.647, LI 0.063).

| leg | span f/s | steady window f/s (n = 482) | service cores | util | idle cores | CPU-s/frame | $/1k footage-h |
|---|---|---|---|---|---|---|---|
| RR p3 (fresh container) | **11.665** | 11.677 | 31.171 | 97.4% | 4.653 | 2.672 | 8.18 |
| RR p4 | **11.560** | 11.620 | 31.038 | 97.0% | 4.640 | 2.685 | 8.25 |
| LI p3 (fresh containers) | **12.791** | 12.772 | 29.044 | 90.8% | 0.063 | 2.271 | 7.46 |
| LI p4 | **12.809** | 12.794 | 28.994 | 90.6% | 0.062 | 2.264 | 7.45 |
| sequential (campaign, n = 5) | LI 1.834 · RR 2.081 | — | 1.88 · 6.95 | 5.9 / 21.7% | — | — | — |

| basis (p3 + p4 means) | LI | RR | LI vs RR |
|---|---|---|---|
| **f/s per EFFECTIVE core** — the work itself, idle removed | 0.4420 | 0.4389 | **+0.7% — a statistical tie** |
| f/s per MEASURED core — the cost a user pays, idle included | 0.4411 | 0.3733 | **LI +18.1%** |
| ↳ *the same fact as* RR's CPU-s per frame, 2.679 vs 2.268 = RR +18.1% (one quantity, two units — not a second finding) | | | |
| span f/s | 12.800 | 11.613 | **LI +10.2%** |
| ↳ *the same fact in dollars* at one $/h: RR **$8.22** vs LI **$7.46** per 1,000 footage-hours (not a second finding) | | | |

**The sentence a product reader needs: the two engines do the work at
the same cost per core, and the entire visible gap is 4.65 cores — 14.5%
of the box — that RocketRide burns standing still holding 16 tokens.**
Per-pass effective-core pairs (LI vs RR): p3 0.4414 vs 0.4399 (+0.3%),
p4 0.4427 vs 0.4379 (+1.1%), and the campaign's settled pass 2, 0.4564
vs 0.4393 (+3.9%); the campaign's pass-1 pair (0.4293 vs 0.4634, RR
+7.9%) is excluded (§4). **The campaign's effective-core inversion
(RR +1.9%) was carried entirely by that pair and is WITHDRAWN; the
corrected figure is a tie.** The settled set p2 + p3 + p4 gives +1.8% /
+19.4% / +10.7% on the three bases — the same reading.

Why 500 films read faster than 35 on both arms (+24–25%): ramp/drain
geometry — at 35 films the steady window ran 15–20% above the span; at
498 the two coincide (span vs window: LI 12.791 vs 12.772, RR 11.665 vs
11.677), so the whole-batch rate is the saturated rate. The 35-film
figures were right for 35 films; they were never steady-state figures.

## 3. The idle burden — the token model's cost (unchanged mechanism)

With 16 tokens live and no work in flight the engine's cgroup burns
**4.653 / 4.640 cores** (server alone 1.007 / 1.008; **0.228 / 0.227
cores per token**, marginal); the LlamaIndex instances burn 0.063 /
0.062. Over a 3.86 h RR leg that is ~64,600 CPU-seconds — **14.9% of the
service's CPU** — reported beside every figure and never subtracted
(`efficiency.idle_burden` in each export). It is the whole of the
measured-core gap and of the dollar gap; the 35-film and AMI reports
found the same cost at the same size (4.66 / 4.66–4.71). Product
finding, not framework verdict: fix the idle spin and the measured-core
and span gaps close to the effective-core tie.

## 4. The excluded pass-1 pair (Ruling AC) — environmental, named, unexplained

The campaign's first passes — RR p1 12.198 f/s, LI p1 12.249 — are
**excluded from every mean**. Two held facts place the anomaly outside
the pass: (i) **it predates the pass** — the sixteen warm-up sends that
precede each pass were already anomalous before any pass state existed:
RR p1's ran at a median 152 s against 159 / 164 / 163 s in p2 / p3 / p4
(−5 to −7%), LI p1's at 834 s against 757 / 791 / 782 (+6 to +10%);
(ii) **it is CPU speed, not scheduling** — RR p1 did the same work in 5%
fewer engine-cgroup CPU-seconds (2.543 vs 2.672–2.685 CPU-s/frame) at
the same 97% utilisation. Opposite signs on the two arms, in windows two
days apart (LI 2026-09-04 20:49–00:30Z, RR 09-05 04:20–08:45Z). Every
provenance scalar is identical across the four RR passes (image, thread
env read back, task census 16 → 16, host networking, driver CPU share);
pre-leg load shows no pattern (3.59 / 4.58 / 0.52 / 5.8). **Unexplained.
What we lack**: no CPU-frequency, turbo or host-contention
instrumentation in any export, and the memory sampler postdates the
campaign. Not smoothed; not reproduced on n = 2 fresh lifetimes per arm.
(Ruling AD: the ~2.5–3% ramp over the first fifth of every pass,
reproduced 4/4 on both arms, is normal warm-up shape and not a finding.)

## 5. The partition — predicted before the run, held exactly, reproduced

`partition_check.json`, both campaign passes: **433 films above the
560px long edge diverge across arms, 65 at or below agree bit-for-bit,
zero violations in either direction** (`ABOVE_560_PASSING = []`,
`BELOW_560_FAILING = []`); Ruling U predicted 433 before the run from
the manifest census (435 of 500 above the edge, two of them warm). The
boundary is inclusive: the one corpus film at exactly 560 (JailBait,
560×380) agrees. The lifetimes run, which carried no partition step,
reproduces it from its records: 433 / 0 on pass 3. The 35-film subset
(27 of 35 above the edge, 77%) under-represented the divergence-prone
class; the corpus-wide figure is 87%.

## 6. The mechanism — the engine's own pre-inference downscale (V-D, CONFIRMED)

**Named in source.** The detect node builds the engine's `Detector`
facade (`engine/nodes/detect/IGlobal.py:74`) and calls its `detect`
(`IInstance.py:107`) on the losslessly decoded PNG frame. That facade
runs `resize_for_inference(image, self._infer_max_edge)` before the
backend (`ai/common/models/vision/detection.py:512-518`), with
`infer_edge = 560` a fixed constant in the `BACKENDS` table (`:60`,
`:466`; no constructor parameter, no node-config field —
`nodes/detect/services.json` exposes threshold, prompt and profile only;
unreachable from a pipe). `ai/common/image/dense_resize.py`: a strict
no-op when the long edge is ≤ 560, otherwise a PIL LANCZOS downscale to
`floor(w·s) × floor(h·s)`, `s = 560 / max(w, h)`, boxes mapped back
afterwards. Only then does RF-DETR apply its own resize — of every input,
whatever its size, to a fixed 560×560 tensor (`rfdetr/detr.py:379`).
LlamaIndex (`li_video/pipeline.py:215`) hands RF-DETR the raw frame. Two
resampling pipelines above 560px, one below. The source comment on the
spec, "downscale to it is lossless (boxes mapped back)", is true of
coordinates and false of scores.

**Reproduced (V-D, 2026-09-07 03:23Z, inside `rr:patched-video` at
intraop 2, weights md5 `b4d3ce46…` pinned to the Ruling-Y artifact;
`results/wrapper-resize-parity-20260907/`).** Frame 10 of
HouseOnBareMountain (714×480, PNG sha `83a02b92…`, the campaign's
diverging frame) through the engine's own helper — imported by path from
the image and matched pixel-for-pixel by the probe's port, 714×480 →
560×376 — then `RFDETRBase().predict`, reproduces campaign-RR's output
**bit-equal at 9 dp**: six detections, 0.946473300 0.935210288
0.856113911 0.449365526 0.384643406 0.318114191. The raw frame
reproduces campaign-LI's five (0.953240395 0.934387743 0.862633228
0.489725053 0.432809502) bit-equal. The ≤560 control is a no-op both
ways; every predict matched itself when run twice.

**The work is symmetric.** A forward pre-hook on RF-DETR's module at the
eager call site (`detr.py:407`) recorded the tensor the model consumed:
`[1, 3, 560, 560]` on BOTH paths. The facade changes the pixels RF-DETR's
resize starts from — hence the scores — not the model's input. Pixels
handed to `predict` differ (342,720 raw vs 210,560 facade, ×0.614; over
the corpus 46.6 vs 35.0 Gpx, frames-weighted facade area ratio 0.750,
range 0.154–0.978), the model's do not (313,600 per frame, both arms).
**RocketRide pays 4.64 ms of LANCZOS per frame above 560px** (median of
5) against ~0.84 s of detection — ~0.5% of per-frame cost, on its side.
Held measurements agree: LlamaIndex's per-stage `detect` time is flat
across source resolution (0.831–0.85 s/frame from 320×240 to 720×480),
and the RR/LI per-frame cost ratio is flat across the edge at comparable
resolutions (540×360 1.106 · 640×480 1.114 · 720×480 1.113).

**What it closes.** The 35-film campaign's §6 left the mechanism open
with five candidates excluded and a "context-dependent" reading; the
context-dependence was our isolation probe calling the backend's
`predict` rather than the facade's `detect` — it reproduced the
comparison arm's path on both sides, a probe measuring one arm twice
(register entry 33). The 35-film measurements stand; that reading is
corrected by the addendum now in its §6. Filed upstream: Ticket 6,
measured updates 3–4, acceptance criterion 4 (match, remove, or document
the facade downscale; correct the "lossless" comment).

## 7. Four mechanisms killed with data

| candidate | what would have shown it | what the data showed |
|---|---|---|
| **Reduction-order / thread-count variance under load** (Shashi's account) | run-to-run digest changes within an arm | **Zero.** Within each arm, pass 1 ≡ pass 2 (campaign, one lifetime), pass 3 ≡ pass 4 (fresh lifetime) and campaign pass 2 ≡ pass 3 (different lifetimes, two days apart): labels, full-precision scores, counts and chunk shas identical **498 / 498 on both arms, every pairing, including all 433 films above the edge**. The thread-count effect exists and was measured on the same frame at 10⁻⁷ (intraop 16 vs 2: 0.953240275 vs 0.953240395, Ruling-Y artifacts); the divergence is 10⁻²–10⁻¹, deterministic, between arms. |
| **Page cache** (Shashi's rep1→rep2 eviction) | iowait rising with cost; residency differences | Cold by construction with proof in every leg; the per-film cold read (`read_s`, the driver's sha pass) flat by position in all campaign legs; the minute-by-minute `/proc/meminfo` sampler beside the lifetimes run (938 rows joined, `probe/cachewatch_join.py`): **iowait ≤ 1.4% of the box, flat; ρ(cost, iowait) −0.12 … −0.03**; container file cache squeezed 30 → 19 GiB by the anon climb in each RR pass with flat cost. Exonerated for this run; silent on the campaign (sampler postdates it). |
| **Lifetime drift** (pass 1 a transient, pass 2 a plateau — the campaign's reading, pre-registered with confirming and refuting shapes) | fresh containers drifting like the campaign's pass 1 | **Refuted on its own terms.** Fresh-container first passes: RR −2.3% first→last fifth (band +1..+6), LI −3.1% (band −6..−13); pass 4 reproduces pass 3's profile at the same level; plateau level p4 vs campaign p2: RR −0.04% (paired SE 0.57%), LI +1.32% (SE 0.77%) — the "plateau" is the norm and the campaign's pass 1 the anomaly (§4). The filesystem variant died with it: the ext4 free-space proxy is flat across ~1 TB of spool churn (avg free extent 43,608 → 43,082 KiB; ≥4 MiB share 0.9936 → 0.9933; `lifetime_state_prerun/postrun.json`); per-token memory climbed identically in every pass with flat cost (§8); no spool leak. |
| **Workload asymmetry above 560px** (RR feeding its detector a smaller image on 87% of the corpus) | RR doing measurably less detector work above the edge | **The model's input is the same size on both paths — `[1, 3, 560, 560]`, measured (V-D)**; RR does 4.64 ms MORE preprocessing per frame; LI's detect stage flat across resolutions; RR/LI ratio flat across the edge at comparable resolutions; the class-level ratio drop (≤560 1.168 vs >560 1.121) is carried by the 320×240 films, where LI's decode-and-PNG stage is disproportionately cheap. No correction toward RR. |

## 8. Memory and spool

- **Per-token memory growth — a finding at n = 4.** With 16 tokens live
  the engine's service tree climbs **26.7 → 52.5 GiB RSS (p3) and 26.5
  → 49.2 (p4)**, cgroup anon 19.2 → 44.8 and 19.0 → 41.6 GiB, over 498
  films — ~50 MB per film served — and resets only when the tokens end
  (ttl = 0; the campaign's p1 and p2 climbed identically). At leg end
  the token processes sit at 3.4–3.6 GiB each; the server stays small
  (`lifetime_state.leg_end.containers.rr.procs.top_by_rss`). Throughput
  did not move with it. Under a 58 GiB cgroup a token reaches the limit
  in ~1,100 films. Ticket 6 criterion 5; LlamaIndex is flat at ~22 GiB.
- **Spool**: no leak — rr `/tmp` at leg end holds 16 per-token webhook
  files and two empty locks, zero `media_*`, both passes; LI 3 files /
  32 KiB per instance. One whole-film spool per token in flight (16
  files, 8.9 GiB at C = 16); fs-level spool high-water 12.0 GiB (RR) /
  13.9 GiB (LI) above the leg-start level.
- Host memory never under pressure (`mem_available` ≥ 14.8 GiB at every
  RR pass end).

## 9. Provenance and landings

All three run dirs are box-committed and bundle-landed (header). Every
export carries the image id, thread-env read-backs (declared and
in-process), the task census, the container lifetime (created, age at
driver start, pass-in-lifetime), the idle burden with its basis, the
collector summary, the per-leg gates, and — from the lifetimes run —
`lifetime_state` (spool, cgroup and per-process memory, host filesystem
and fragmentation proxy at leg start and end; a 5 s statvfs stream).
Manifest provenance, one line: the exports hash the box's working copy
of the video manifest (`c5a09a34…`), which differs from the committed
file (`075fc35b…`) by its `_meta` line only — the corpus locator's stamp;
the measured rows are proven byte-identical (every record's frames,
duration, bytes and submitted sha equal the committed row, 498/498 on all
eight blast legs). Recorded, not a defect. The `rf-detr-base.pth` V-D
used is md5-pinned and reproducible from `li:video`, not landed.

## 10. Cross-team joins — cautions

- Shashi's films50 (relayed; document not held): his RR-vs-HS 1.58×
  carries a wave handicap he flags (50 films / 32 workers = 1.56 waves,
  HS ~78% util cap); his RR at 16 tokens runs 3.1 waves; ours has none —
  do not join multiples. His "2.6% apart" span is a wave-depressed N = 50
  span against our saturated N = 498; on the wave-independent quantity
  the gap is **RR 2.68 vs his 2.198 CPU-s/frame = +21.9%** (assumption
  stated: his cores are the engine cgroup with tokens live, as ours are).
  Warm-start (his prewarm) vs cold-start-with-proof (ours) are different
  bases.
- The cross-team CPU-per-frame question therefore stands on two corpora
  and three harnesses; page cache is excluded as its explanation
  (`AMI_CROSS_TEAM_RECONCILIATION.md` §9); the ask is unchanged
  (`AMI_CROSS_TEAM_COVER.md`). No cross-team CPU figure is publishable
  until settled.
- Leela's 500-film sizing run (her `runs/films500-sizing` at pin
  `3967d9f4`) shares the corpus by construction; joins carry the 560px
  caution (§6) and the frame-counter caution from the 35-film report §9.

## 11. Instrument defects, with direction of bias (campaign discipline)

| defect | status | bias on published numbers |
|---|---|---|
| Fetch died to the box's idle watchdog (v1 had no keepalive) | v2: bounded self-terminating keepalive + 12 workers | none — no data produced |
| Manifest builder called a non-existent `ffprobe` | rebuilt on `read_frames` header meta + PIL; fail-fast startup check; null control (entry 31) | none — refused |
| Staging golden chosen by a derived selector (wrong film), and the comparator talked past its own refusal | golden self-pins; same-input gate + null control (entry 32) | none — refused |
| Plan step-0 full corpus sha (≥7 h, low CPU) killed by the watchdog | FAST verify; plan lock; self-launched mirror | none — before any leg; two preflight-only orphan dirs |
| The Ruling-Y isolation probe replicated the backend's `predict`, not the facade's `detect` (entry 33) | corrected by V-D | made the divergence read as context-dependent; the 35-film measurements unaffected, its §6 reading corrected |
| Pre-registered mechanism read's baseline was the anomalous pass 1 | declared VOID | none — the rule fired and was set aside on a pre-stated premise |
| V-D runner v1 could not find the engine interpreter | v2 reuses the Y runner's capability search + weights pin + EXIT trap | none — refused; one rr container left running ~2 h, removed |
| `/proc/diskstats` device name (`/dev/root`) | absence recorded | churn volume not captured; no figure depends on it |
| `age_at_leg_start_s` is age at DRIVER start (leg start follows the ~40 min warm-up) | label only; the fsstream row-0 utc is the leg anchor | none |
| Join tool: tied correlations read as indeterminate; sampler's iowait parsed as percent | both fixed before any run data was read; self-tests | none |
| H16 drift cap unsized for films | open, disclosed | conservative (PASS→FAIL only) |
| RR idle burden | not a defect: measured, reported beside, never subtracted | disclosed; favours LI per measured core; stated as the token model's real cost |

## 12. What remains open

The standing inventory across both films campaigns is kept in one place,
`FILMS_HANDOFF.md` (closing block, 2026-09-07): H16's cap and the char
band (Ruling W; settled by the next campaign's like-for-like
preprocessing run), the cross-team CPU-per-frame gap, the environmental
pass-1 anomaly and the instrument it needs, per-token memory growth and
the facade downscale (both the engine's, Ticket 6), tooling follow-ups
that affect no published figure, box housekeeping, and the 35-film
carry-overs.

## 13. Limitations

1. **n = 2 per arm on fresh lifetimes** (plus one settled campaign pass
   each that agrees and is not in the means); spreads published.
2. **One box, one corpus**; one configuration per arm (the ruled 16×2
   posture); the RocketRide default cell not re-run at 500 by ruling.
3. **The pass-1 anomaly is unexplained** (§4): an environmental effect
   the exports could not measure; a CPU-frequency / host-contention
   sampler beside every leg is the next instrument.
4. **Above 560px the arms are not like-for-like in preprocessing** —
   the engine's fixed facade downscale; detection-equality claims are
   scoped to ≤ 560px; throughput claims stand with §6 beside them. The
   like-for-like configuration (the comparison arm applying the same
   pre-downscale) is a next-campaign candidate, not run.
5. **RR records carry no stage timings**; the per-stage flatness
   argument in §6 is LI-side, the RR/LI ratio is whole-film.
6. **The wall estimate ran 8% short**: 16.75 h against 15.5 h, the excess
   in four ~40 min warm-ups the estimate under-priced.
7. **Sequential n = 5** is a latency spot check, not scaled; gate 8 is
   within-leg only.
