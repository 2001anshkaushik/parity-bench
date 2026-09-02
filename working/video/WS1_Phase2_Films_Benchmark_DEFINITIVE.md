# WS-1 Phase 2 — Archive Films Benchmark: RocketRide vs LlamaIndex

**DRAFT (2026-09-02) — nothing here is published until Ansh reports it done.**
Companion to `WS1_Phase2_Video_Benchmark_DEFINITIVE.md` (the AMI campaign,
closed 2026-08-28). Campaign: 2026-09-01, box `i-0775f33f3dc16f6af`
(c7i.8xlarge, 32 vCPU / 61 GiB), 9 legs, **0 errors, every per-leg gate
PASS or NOT-RUN, zero FAIL**. Run dir `working/video/results/
films_mainrun_20260901T204015Z/` — **landed in-repo at commit `646eaea`**
(entry-26 bundle, parent `79e4676`; also archived
`s3://rocketride-benchmark-data/ansh/films-mainrun-20260901/`, 95
objects). The campaign ran at repo `1560b28…`; its run_manifest reads
`completed: true`, `cross_gates_failed: true`, every ruled number
matching Rulings P/O/M/L/J/S, arming
`films-staging-20260901T203906Z-1560b286` with LIVENESS_MIN 0.385
(Ruling-R derivation embedded). Wall clock 20:40Z→06:16Z (~9.6 h against
the ~7–8 h estimate; the excess sits in warm-up waves and the default
cell). Every number below is from the
banked records or the committed diagnosis artifacts; where a claim is a
reading, it says so.

## 1. Corpus and configuration (all ruled before the run)

**Corpus**: 35 measured + 2 warm feature films from Leela's frozen
`archive_films_v2` (her manifest sha `bd0c915e…`; our subset manifest sha
`54186c24…`, selection a pure function of her manifest — title-dedup,
duration×bytes terciles, k=4 per cell, envelope forced). 49.33 h measured
footage; 11,841 measured expected frames per pass at fps=1/15, **measured
per film at manifest build through the arms' own sha-pinned ffmpeg
(`e7e7fb30…`), never derived from duration** (Crossroad 23).

**Configuration, with its evidence trail**:
- **Postures (Ruling M)**: RR 16 tokens × 2 threads; LI 16 single-worker
  instances × 2 threads (driver round-robins ports — the structural twin
  of token round-robin). Chosen from an 11-point posture matrix, both arms
  swept by the same method (Crossroad 17) — full matrix in §5.
- **Concurrency C=16 (Ruling O)**: the knee by the pre-registered 0.7
  marginal-efficiency criterion on the measured-batch chain (§5); LI's
  throughput peak; statistically tied with C=32 for RR.
- **Splitter 4000/0 both comparison bases (Ruling L)**: overlap 0 matches
  what the engine's inert-config LangChain splitter realizes; read back
  fail-closed from every LI worker's /health at every leg preflight.
- **Warm-up**: 2 dedicated warm films (Ruling J), re-sent in waves,
  warmth gated on model-load markers; warmed rows never measured.
- **Gate-3 arming (Rulings Q/R)**: staged cross-arm comparison on
  20000LeaguesUndertheSea (395/395 frames, zero divergence) with
  LIVENESS_MIN cut from that run (0.5 × measured min non-empty-frame
  fraction; single-film basis disclosed). §6 records why this arming was
  structurally uninformative about the corpus — a finding in itself.
- **Passes**: 2 per blast cell; sequential legs (n=5) per cell carry the
  determinism repeat (gate 8), uncontended latency and the speedup divisor.

## 2. Throughput (banked; unaffected by §6 — see §2.1)

| cell | blast f/s (p1 / p2) | spread | service cores | util | steady window f/s |
|---|---|---|---|---|---|
| LI N16xT2 | 10.145 / 10.123 | 0.22% | 21.45 | 67.0% | 8.634 / 8.244 |
| RR M16xT2 | 9.413 / 9.611 | 2.08% | 25.52 | 79.8% | 8.218 / 8.303 |
| RR default | 2.360 / 2.342 | 0.77% | 6.40 | 20.0% | 1.540 / 1.526 |

- **The headline, scoped — at the ruled 16×2-vs-16×2 posture, C=16, on
  this 35-film archive corpus with RF-DETR base: LlamaIndex delivered
  +6.5% span throughput (10.134 vs 9.512 f/s, pass means); +26.7% per
  MEASURED core, because that is the cost a user actually pays, idle
  included; and +3.9% per EFFECTIVE core, because that is the cost of
  the work itself once each arm's idle spin leaves its own
  denominator.** Read together, the finding is not "LlamaIndex is more
  efficient at the work" — **the two engines do the work at nearly the
  same per-core cost, and RocketRide's process model spends 4.66 cores
  (14.6% of the box) standing still**: a specific product finding with
  a mechanism (§3), not a framework verdict. Both per-core figures are
  in this sentence because either alone misleads — measured-core alone
  overstates the framework gap, effective-core alone hides the tax. A
  measured result at one measured configuration (§10).
- **The per-core computation, both ways** (the difference between them
  IS the token model's idle tax, §3):
  - per *measured* service core (idle included in the denominator):
    LI 0.4724 vs RR 0.3727 f/s/core — **LI +26.7%** (per-pass ratios
    +28.2% / +25.3%);
  - per *effective* core (each arm's measured idle spin removed from
    its own denominator — RR 25.52−4.66=20.86, LI 21.45−0.07=21.38):
    LI 0.4740 vs RR 0.4560 — **LI +3.9%**.
  Throughput itself is never idle-adjusted (discipline); these are two
  denominators for the same banked numbers.
- The steady-window gap is only **+2.2%** (8.439 vs 8.261) — both
  published; §2.2 explains the difference from the records.
- **Out-of-box → tuned: 4.05×** (RR default 2.351 → RR 16×2 9.512, an
  RR-internal ratio per Crossroad 27 — the default cell is never a
  cross-arm performance comparison, and its cross files say so). LI's
  out-of-box (single container, kernel-accept serving) is
  measured-pathological (LI_SERVING_SKEW) and is disclosed here rather
  than run as a cell. **Both frameworks are configuration-limited out of
  the box** — the AMI headline, reproduced on films.
- Pass-to-pass repeatability: 0.22% / 2.08% / 0.77% — beside the
  cross-day same-corpus figure of 2.8–5.5% (§5).

### 2.1 Why the throughput comparison stands despite §6

Gate 1 (frames_census) asserts `frames_observed == expected_frames_measured`
**exactly, per film, both arms** — and passed in every leg. Both arms
performed the same number of frame extractions, detector inferences and
per-frame embeds per film; frames/s therefore compares equal work counts
(the ruled blocker-4 basis). The one asymmetry §6 injects is embed-stage
text volume, bounded by the measured stage shares: extract 22.5% / detect
74.9% / split 0.02% / **embed 2.6%** of LI wall (RR records carry no
stage_s; stated). A char-volume asymmetry riding on 2.6% of wall cannot
move a +6.5% headline.

### 2.2 Why the span gap (+6.5%) exceeds the window gap (+2.2%)

The steady window is defined as `[first in-flight==C, last in-flight>=C]`
with completions inside (driver `steady_window`); the span additionally
carries the ramp (lanes filling) and the drain tail (the last long films
finishing on emptying lanes). Measured: the RR windows ran 734.4/726.9 s
holding 19 of 35 completions (6,035 frames → 8.218/8.303 f/s); the LI
windows 637.5/646.3 s holding 17 (5,504/5,328 frames → 8.634/8.244).
So the **saturated rates are near-equal (+2.2%)** and roughly half the
completions per leg land outside the window — in ramp and drain, where
per-lane speed and tail scheduling dominate and where most of the +6.5%
span advantage is earned. Both numbers are published because they answer
different questions: the window is the sustained rate a long queue would
see; the span is what a 35-film batch actually costs end to end.

## 3. The idle burden — the token model's cost (product finding)

RR at 16 tokens burns **4.66 cores (14.6% of the box) before any work
arrives** (export `efficiency.idle_burden.idle_cores_with_instances_live`
4.657/4.656 across passes; ~1.01 of it is the engine master alone, and
even the single-token default posture idles 1.23 cores); LI's 16 idle
instances burn 0.066–0.069 cores. Reported beside every RR number,
**never subtracted from throughput** (campaign discipline): it is what a
user pays to hold 16 engine tokens resident. Its size is exactly the gap
between the two per-core figures in §2 — **+26.7% per measured core
collapses to +3.9% per effective core once each arm's idle spin is
removed from its own denominator** — so RR's parity cell reaches
9.5 f/s while paying a ~4.66-core tax LI does not pay, and both readings
are published rather than one netted number.

## 4. Memory (Ruling-G risk, retired)

Neither arm's memory scales with concurrency: RR anon 17.26 GB at C=1 →
18.19 GB at C=16 (~0.06 GB/item, baseline-dominated); LI flat 14.7–15.1 GB
across the range. The posture sweep fit the RR token term **linear at
~0.92 GB/token** (predicted 0.94); the 32×1 stress point (48.6 GB
predicted full-load) ran with no OOM. Sweep peaks: RR anon sum
22.3/23.9/24.6 GB, memory.peak 30/38/38 GB at C=8/16/32 — inside the 58 GiB
lid throughout.

## 5. How the configuration was chosen (published beside the choice)

**Posture matrix** (11 points, full measured corpus, C=min(2×lanes,35),
fresh containers per point, thread env + chunk config read back
fail-closed per point):

| posture | f/s | cores | | posture | f/s | cores |
|---|---|---|---|---|---|---|
| rr 8×4 | 8.32 | 26.03 | | li 8×4 | 10.105 | 26.76 |
| rr 16×2 | **8.65** | 22.67 | | li 16×2 | **10.071** | 23.55 |
| rr 32×1 | 6.859 | 17.55 | | li 4×8 | 8.577 | 22.65 |
| rr 4×8 | 7.292 | 21.43 | | li 8×2 | 9.869 | 17.55 |
| rr 8×2 | 8.128 | 19.45 | | li 8×8 (oversub) | 2.201 | 30.81 |
| rr 16×4 (oversub) | 5.295 | 27.24 | | | | |

Matrix findings: LI led at every matched posture (+21.5% / +16.4% /
+17.6% / +21.4%); oversubscription cost RR 38% and collapsed LI 4.6×,
both at the highest CPU; half the thread spend (8×2) bought ~94% (RR) /
~97.7% (LI) of peak at 66–75% of the cores. LI 16×2 was chosen over the
statistically-tied 8×4 (0.34% apart at n=1, against 2.8–5.5% run-to-run
variance) for 12% less CPU and the matched-shape headline (Ruling M).

**C chain** (measured batch, ruled postures, in-flight confirmed = requested
at every point): RR 8.21 → 9.059 → 9.127 f/s and LI 9.569 → 10.221 →
9.788 at C=8/16/32. Marginal efficiency at the 8→16 step: 0.552 / 0.534 —
**knee C=16 by the pre-registered 0.7 rule**, both arms. 16→32: RR +0.75%
(a tie inside run-to-run variance), LI **−4.2%** — the measured price of
running two-deep per instance (the queue-depth asymmetry AMI noted
qualitatively). Same-corpus repeatability at C=32, cross-day: RR 9.127 vs
8.65 (5.5%), LI 9.788 vs 10.071 (2.8%).

**Batch composition, measured**: the 9-film strata-heads batch (largest
bytes per stratum) runs ~34% slower than the full 35 at identical posture
and C on BOTH arms (RR 5.435 vs 8.21; LI 6.349 vs 9.569) — workload, not
framework; the number behind the discipline that no chain ever spans
batches.

## 6. The detection divergence — a real cross-arm difference (Ruling U)

**cross_detection_agreement failed on 27 of 35 films in every cell; the
8 passing films are exactly the films that need no downscale.** The
partition is exact, 35/35, on RF-DETR's own 560px input edge:

| long edge | films | verdict |
|---|---|---|
| 320×240 (×4), 464×368 (×2), 540×360, 560×380 | 8 | bit-identical detections across arms |
| 624×480, 640×276, 640×480, 704×480, 714×480, 720×432, 720×480, 720×544, 720×576, 936×720, 1424×1072 | 27 | diverging |

Anatomy: the arms find the **same objects at 0.5–5% shifted scores**
(e.g. HouseOnBareMountain frame 10 — RR [bottle .946, bottle .935, chair
.856, chair .449, chair .385, person .318] vs LI [bottle .953, bottle
.934, chair .863, chair .490, person .433]); divergence appears where a
score crosses the 0.3 threshold from opposite sides; the direction is
systematic — **RR detects more on 22 films, LI on 5, equal on 8**.

**Four mechanisms excluded, each by measurement**:
1. **Different frames** — killed by byte-level frame parity: A==C EXACT
   per-frame PNG hashes on three failing films (ABucketofBlood,
   HouseOnBareMountain, A_Study_In_Scarlet; manifest-sha same-input
   proof), plus the committed A==B==C artifact on 20000Leagues.
2. **PIL mode** (the arms' one load-path delta, `.convert('RGB')` vs
   mode-preserving open) — killed by the census: all 35 films decode to
   RGB; the delta is a no-op on this corpus.
3. **Threshold amplification** — killed by the near-threshold split:
   clean vs diverging median near-threshold rates 0.05119 vs 0.04514
   (clean slightly HIGHER) at ±0.01, 0.21297 vs 0.18781 at ±0.05; only
   0.524 of diverging frames are threshold-adjacent.
4. **Library or build difference** — killed by Layer-1 identity: both
   containers run torch 2.10.0+cu128 (git `449b1768…`, cuda 12.8, wheel
   `cp312-cp312-manylinux_2_28_x86_64`, identical torch/lib — no MKL, no
   OpenBLAS: torch built-in kernels both sides), numpy 2.5.2, pillow
   10.4.0, torchvision 0.25.0+cu128, rfdetr 1.5.2 with **byte-identical
   detr.py** (sha `d0cf8916…` both), and md5-verified identical weights
   on every instance of both arms.

**Verdict (Ruling U)**: two arms running identical code on identical
inputs produce different detections above 560px. That is a **real
cross-arm difference, not an instrument artifact**. Gate 3's strict
verdict is CORRECT and stands: 27 films FAIL, 8 films PASS.

**How general is the 560px boundary?** Within our 35, 27 films (77%)
sit above it — but that fraction is selection-weighted (duration×bytes
strata over her corpus), not an estimate of the archive. **Her sealed
500-film manifest records no resolution** (its per-film contract carries
duration, bytes/sha, frames_counted, nominal_fps, license, audio —
`team_docs_received/ARCHIVE_FILMS.md` §3 — and our subset builder
consumed no dimension field), so the corpus-wide fraction above 560px is **not derivable from
any artifact we hold**. Establishing it would take one read-only header
probe over her 500 S3 objects (or her census EDA, if it captured
dimensions — unverified). Until then, the finding's scope is: every
measured film above 560px diverged, every one at or below did not, on
this subset.

**Where the §6 evidence lives** (provenance pass at `646eaea`): the
Leagues A==B==C parity and detect-text artifacts are COMMITTED
(`probe/probe_frame_parity_20000LeaguesUndertheSea.json`,
`probe/probe_detect_text_20000LeaguesUndertheSea.json`); the
near-threshold split is REPRODUCIBLE in-repo from the landed records
(`probe/diagnose_cross_films.py --near-threshold` over the results dir);
the three failing-film parity artifacts, the mode/size census, and the
Layer-1 build-read outputs are BOX-SIDE
(`~/films_probe/parity_failing/`, `~/films_probe/detector_parity/`) —
relayed verbatim into the record but not yet landed; a small bundle
lands them if this document is to be fully self-contained at one commit.

**Ruled (V): the 500-header probe was considered and NOT run.** The
reasoning, recorded so this reads as ruled rather than overlooked: the
scope statement above is the honest form of the claim; a header pass
over her S3 prefix would generalize a finding on her data without her
involvement; and the 77% figure is load-bearing for nothing this
document asserts.

**Open, bounded, not pursued this campaign**: the remaining candidates
are properties of *how* each arm runs the same code — thread counts at
inference time, batch shape, memory layout, allocator state. What would
settle them: completing the single-frame side test (raw scores at
threshold 0.001 on one identical frame per size class, with per-side
`torch.get_num_threads()` captured in the same process), then a
controlled thread-count sweep on that harness. The instrument exists
(`probe/probe_detector_parity.py` + `probe/run_side_prediction.sh`); its
last run stopped on a fixed argument-contract defect. **Ruled (X): this
paragraph goes upstream as the ticket, side-test harness attached; it
is not a publication gate.**

## 7. Not publishable from this run, and why

- **char_conservation / the films char band**: failed on all six cells,
  but the verdict is **band-cutting data, not a finding** (Ruling T
  disclosure, stamped into every cross file). It is confounded by §6:
  median |ratio−1| is 0.0188 in the high-divergence half vs 0.0085 in the
  low. The only uncontaminated band evidence is the 8 clean films (n=8);
  the three quoted in diagnosis sit 1.0011 / 1.0023 / 1.0056 — within
  0.6% above 1.0, the direction the Ruling-L equivalence note predicted
  from engine short-line retention **before the data existed**.
- **H16's boundary-drift cap** (0.5%/video) is live and unsized for films
  content — also stamped as a disclosure into every cross file; no gate-3
  verdict here leaned on it (exclusions ran 0–1 per film).
- **Cross-team CPU-per-frame**: still blocked on the unresolved AMI-era
  accounting discrepancy with Leela's team.

**Ruled (W): the char band and the H16 cap are formally DEFERRED to the
next campaign.** The band is settled only by a run whose detection sets
agree — this run's input is confounded, and its n=8 clean films are
themselves a ≤560px-biased subsample of the corpus. H16 is settled by a
films-sized denominator **ruled before the data, never after**; until
then the 0.5% cap stays live and disclosed in every export.

## 8. Instrument defects, with direction of bias (campaign discipline)

| defect | status | bias on published numbers |
|---|---|---|
| Sweep summarizer KeyError (`n_films`) | fixed; matrix re-derived from artifacts | none — it refused, nothing misread |
| Marginal efficiency computed at unrealized C (heads batch capped in-flight at 9) | refused by the realization gate; measured-batch reissue ruled (N) | pre-fix output overstated the knee's position; retracted before any ruling consumed it |
| `import re` sweep abort | fixed same day; 15 min box time | none — no data produced |
| Whole-blob golden send vs the 250 MiB ceiling | converted to the one chunked loop | none — staging blocker only |
| Arming deriver read the wire name, not the record name | fixed; producer-built fixtures | none — it refused real records |
| Side-test interpreter + stdout-capture defects | fixed (capability resolution; file-based artifacts) | none — diagnostics only |
| H16 drift cap unsized for films | open, disclosed in every cross file | conservative: could only flip PASS→FAIL, never FAIL→PASS |
| RR idle burden | not a defect: measured 4.66 cores, reported beside, never subtracted | disclosed, direction favors LI in per-core terms and is stated as the token model's real cost |
| mime label pre-fix (`x-msvideo` for .mp4) | fixed before the campaign | none — label only, routing by prefix |

## 9. Cross-team joins (Leela)

Her per-film records filter to our 35 by `doc`, with `input_sha256`
equality as the identity check — **no equality proof, no comparison**
(CANNOT COMPARE, register entry 14). Her repo pins: 08-22 `aa817d9a`,
24-Aug `313430f3`, head `3967d9f4`. Two standing cautions for any join:

1. **Frame counts**: her RR frame counts carry the counter artifact we
   measured — her `bench_video.py:106`-shape bracket counter retains
   chunk-boundary duplicates (416 on 20000Leagues where the engine's own
   frame stream, detect text and our overlap-stripped counter all agree on
   395; first divergence at index 44; committed artifacts at `7204a28`).
2. **The 560px edge (§6)**: on content whose frame long edge exceeds
   560px, the two arms produce genuinely different detections from
   identical frames and identical library builds. Any joined
   detection-level figure (labels, scores, agreement rates) on >560px
   content must carry that finding; ≤560px content joins clean. The AMI
   corpus (352×288, uniform) sits below the edge and is unaffected —
   consistent with its byte-identical gate-3 scores.

This section is document text inside the results package; nothing in it
travels as a direct message to her team — the package is handed over by
Ansh, and questions flow back the same way.

## 10. Limitations

1. **n=2 blast passes per cell** — sizing evidence by the same standard
   both teams use; pass-to-pass spreads published (0.22–2.08%).
2. **One box, one corpus** (35 films of one archive's profile;
   resolutions 320×240–1424×1072).
3. **The §6 divergence is unexplained beyond its boundary** — pinned to
   the downscale path by exclusion, mechanism inside identical code
   unresolved; bounded (sub-percent score shifts; does not touch frame
   counts or §2).
4. **The arming lesson**: the staged gate-3 film was chosen for its
   byte-parity proof — which selected a ≤560px film, the one class that
   structurally cannot exhibit the divergence. The staging pass was real
   and uninformative about the corpus. Next campaign: the same-frames
   staging set must span the resolution classes, above and below the
   model's input edge.
5. **Gate 5's threshold** derives from one film's measured distribution
   with a stated 2× margin (Ruling R; disclosed in the run manifest).
6. RR records carry no stage timings; the embed-share bound in §2.1 is
   LI-side only (stated where used).
7. **The wall estimate ran wrong in a knowable direction**: 9.6 h
   against the 7–8 h estimate, the excess in the warm-up waves and the
   default cell. The estimate was built from measured single-lane rates
   and under-priced warm-up at 16 lanes — the cost Ruling S accepted
   knowingly (2×-worker waves kept as the marker-gate margin). An
   estimate wrong in a knowable direction belongs here, not buried.
