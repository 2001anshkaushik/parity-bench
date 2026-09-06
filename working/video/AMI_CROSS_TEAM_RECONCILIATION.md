# AMI cross-team reconciliation — the ~20% RR-vs-RR question (2026-09-02)

**Trigger**: Leela's table (received image, transcribed — DATA) shows her RR
and Shashi's RR at 15.314/15.39 f/s ("16 × OMP 2") and 16.213/16.17
("32 × OMP 1") on ami_full (168 meetings, 23,049 frames, 96.06 h), agreeing
cross-team to 0.3–0.5%. Our banked AMI 16×2 is 12.729/12.753 — **~20% below
both, at nominally the same posture on the same corpus**. Per the received-
docs hard rule: divergences are REPORTED with sources and verdicts; Ansh
asks them; nothing here resolves a disagreement by inference, and nothing
here is constructed to flatter our side. Her new cells postdate our held
pins (aa817d9a / 313430f3 / 3967d9f4), so every claim about them is marked.

## 1. (a) Is her knob our knob?

**At the held pin — YES at the engine surface.** Her matched pattern is
N independent tasks — one `use()` each on its own pipe copy, `ttl=0`,
`threads=` OMITTED (engine default 64 admission), six BLAS/OMP vars = T
verified in every task pid's `/proc/environ`, fail-closed task census
(`MATCHED_POSTURE.md` §§1–2 @3967d9f4). That is the same engine knob as our
M×T (N task processes × thread env; our `threads=` also unset ⇒ default
64). **Differences that are real but not the knob**: her client topology is
one client+websocket per task (N sockets) vs our one client with N tokens
multiplexed on ONE websocket; her ingestion is a sharded, client-unbounded
blast (§5). **Her "32 × OMP 1" / "16 × OMP 2" cells are post-pin** —
`RESULTS_AMI_POSTURES.md` @3967d9f4 lists only default + matched-8×4 — so
"same knob" for the new cells is **HYPOTHESIS (strong: her naming and the
pattern's continuity), unverifiable from held objects.**

## 2. (b) Idle burden bases

Same KIND, different window. Hers: a deliberate **30 s idle window between
warm-up and the barrier**, cgroup CPU quoted as cores (MATCHED_POSTURE §2).
Ours: a cgroup-rate sample with instances live before the leg
(`container_idle_cores`; the AMI legs sampled **6 s** —
`idle_burden.sample_s: 6.0` in all six landed exports — the films-era
driver later shortened it to 4 s, driver_video.py:963; reported beside,
never subtracted, :1003-1015). Values at 16: ours 4.66–4.71
(DEFINITIVE idle table; films reproduced 4.657/4.656), hers 5.69 —
**Δ≈1 core, UNRESOLVED** (window timing, master accounting, or her
16-socket keepalives are candidates — HYPOTHESIS, not adjudicated). One
consistency worth recording: our PARTIAL idle model (~1.0 core + ~0.26/token,
measured 2026-08-21, driver:1003-1015) predicts ~9.3 cores at 32 tokens;
her 32-task row reads 8.91 — her measurement is consistent with our own
idle structure at a posture we never ran.

## 3. (c) CPU per frame — the discrepancy reduces to this, and it is stable

Both sides measure effective cores as **cgroup Δusage/Δt** (her METRICS.md
:75; our collector/cgroup bracket). Computed from our banked cells
(23,049 frames; cores × span ÷ frames = cores ÷ f/s):

| posture | ours (banked) | hers | ours vs hers |
|---|---|---|---|
| 8×4 (26-Aug era) | 30.13 ÷ 11.633 = **2.590** CPU-s/frame | 2.156 (her rr_matched_8x4; the DEFINITIVE's recorded 2.16) | **+20.1%** |
| 16×2 | 29.405 ÷ 12.741 = **2.308** | 1.934 (her table) | **+19.3%** |

A **stable ~19–20% multiplicative CPU-per-frame gap across both matched
postures**, at matched utilization in the new cells (ours 91.9%, hers 93%),
with the same pipe composition — her `benchmark_video_detect.pipe`
@3967d9f4 carries the identical five stages and configs (interval 15,
rfdetr thr 0.3, default preprocessor, miniLM; only cosmetic layout differs)
— and identical frame totals (her 137.2/video, 23,049 = ours). This also
re-frames the 8×4-era "+5.1% agreement" (DEFINITIVE:41): her 8×4 ran at
74.6% utilization (admission-limited), which masked the CPU/frame gap; her
new postures reach ~90–93% util and the gap surfaces as throughput.
**Two independent harnesses (hers and Shashi's) agree to 0.3–0.5%; ours is
the outlier. The burden of explanation sits on our harness/build until the
delta is traced.**

Candidates, all HYPOTHESIS, none resolved here:
- **Engine build delta, the one code difference held in evidence**: she
  runs 3.3.1 + two patches incl. the **chunk-duplication correction**
  (RESULTS_AMI_POSTURES §1); we run the STOCK duplication behavior — and
  our own provenance field says so and says why it matters
  (provenance_leela.py:137-141: "A patched result is not comparable with
  this one"). Weakening fact: our AMI legs' `self_duplication_any` gate
  found no organic whole-list doubling on video docs, so the patch's
  direct work delta on AMI may be ~0. Still the one named build
  difference.
- CPU-bracket windows (both claim warm-excluded; exact bracket edges
  differ by construction).
- Client topology (our 16 tokens on ONE websocket vs her 16 sockets;
  recv/reassembly CPU lands in the engine cgroup on both sides for the
  same ~29 GB).
- Our env_probe image layer vs her build (both 3.3.1; different derived
  layers).
What would settle it: a per-stage CPU split on one identical file through
both harnesses at the same posture, or the two teams exchanging one
leg's cgroup sampler streams. **Ansh asks them; we change nothing.**

## 4. (d) Corpus identity

- Meeting list: **PROVEN identical** — her `ami_full.txt` held byte-verbatim
  (sha `601620b4…`, team_docs_received/README.md) and pinned in our
  manifest meta as `meeting_list_sha256`; same positional 168+2 split.
- Frames: **identical** (23,049 both; her 137.2/video).
- Footage: hers 96.06 h probed; ours ~96.1 h. Same basis family.
- Per-file BYTES: **PROVEN IDENTICAL, 168/168 (2026-09-02)** — our
  records' per-video `submitted_sha256` (the bytes the driver actually
  sent; consistent within and across both pass-1 legs) match Leela's
  canonical `corpus_manifest.json` per-file sha256 exactly for all 168
  measured meetings; zero differ (`results/AMI_LANDING.md`, byte-identity
  section; her manifest landed beside it, S3 object dated 2026-08-22,
  before every compared run). CORRECTION to this document's earlier text:
  the two corpora were NOT staged from one shared prefix — ours was
  fetched from the Corner/Overhead mirrors (`fetch_ami_video.py:16`),
  hers from the AMI mirror into her staging; that error previously
  understated the result. Independent fetches, identical bytes. The 2
  warm meetings are uncompared (never in any measured figure); her runs'
  disk-vs-manifest agreement is her own fail-closed corpus_pin gate's
  claim.
- Boxes differ: hers `i-0bdc8b1e…`, ours `i-0775f33f…` — same instance
  type; our own 24-vs-26-Aug sessions differed 3.6% on one box, so
  cross-box variance is real but an order short of 20%.

## 5. (e) Sharded blast vs our C=16

Her ingestion floods each task's 64-deep admission from N concurrent
`send_files` shards behind a barrier (default cell: ONE send_files of all
168). Ours is a client-side C=16 semaphore, 1-deep per token. **At her new
cells both sides run ~90–93% utilization, so admission differences cannot
plausibly account for 20% there** — what admission DID do is explain her
own 8×4 cell (74.6% util, under-fed). Verdict: harness difference, not a
posture difference; the 20% gap rides (c), not (e).

## 6. The 560px question on AMI — RESOLVED from held records

AMI Closeup1 footage is **352×288, uniform** — our own AMI-era record
states it against the 560 edge explicitly (SESSION_STATE.md:1945: "our
frames are 352×288, so coordinates are never scaled"), her setup doc
corroborates (VIDEO-BENCHMARK-SETUP-2026-08-21.md:210, DATA), and the
internal signature matches: AMI gate 3 passed with **byte-identical
scores** (max_paired_delta 0.0 on 164/165 frames, DEFINITIVE:202) — the
same clean-class behavior our 8 ≤560px films showed. **AMI sits below the
edge; the films divergence mechanism cannot fire there; AMI's cross-arm
numbers are unaffected and the 168/168 zero-tolerance passes need no new
explanation.** This does not touch the RR-vs-RR gap above (same engine
both sides of that comparison).

## 7. Row-for-row: what we hold against her table (inventory, no new computation)

| her row | our status at full AMI corpus |
|---|---|
| frames/s (32×1) | **NOT HELD — we never ran 32×1 on AMI** (first 32×1 anywhere is the films posture sweep) |
| frames/s (16×2) | HELD, n=2: 12.729 / 12.753 (banked) |
| x_realtime | held on a DERIVABLE basis (footage ÷ span from banked cells); never published as a row |
| eff cores /32 | HELD (29.328/29.482, 91.7/92.1% — same cgroup basis) |
| CPU-s/frame | not published; derivable from banked cells (2.308 at 16×2, computed above) |
| span | derivable exactly from banked f/s (≈1810.7 / 1807.3 s); raw span_s in box-side exports |
| $/1k footage-h | **NOT HELD, never computed**; formula held on both sides (her METRICS.md:93 = instance $/h ÷ x_realtime × 1000; our driver carries the same $1.428/h basis) — computable from banked cells |
| idle burden | HELD at 16 tokens (4.66–4.71) and 8 (2.83–2.84); **no 32-token value exists** |
| peak memory | held on a DIFFERENT basis: cgroup-family (collector samples; films-era adds mem_watch's anon-vs-cache split); RSS not banked. Her own table already mixes bases (her 61.1 GB cgroup-incl-cache vs Shashi's 44.4 GB RSS, same cell) — any joined row must carry its basis |
| gates | HELD (per-leg gates green; thread/task read-backs fail-closed) |

## 8. Our AMI full-corpus cell inventory (Task 4; DEFINITIVE §3 is the bank)

| cell | span f/s | window f/s | cores | util | n | status |
|---|---|---|---|---|---|---|
| RR default (1 token) | 2.443 / 2.446 | 2.337 / 2.340 | 6.029 / 6.046 | 18.8 / 18.9% | 2 | banked |
| RR 8×4 (26-Aug) | 11.694 / 11.571 | 11.258 / 11.438 | 30.411 / 29.843 | 95.0 / 93.3% | 2 | banked (headline) |
| **RR 16×2** | **12.729 / 12.753** | 12.755 / 12.796 | 29.328 / 29.482 | 91.7 / 92.1% | 2 | banked |
| RR 8×4 (24-Aug) | 12.048 | 11.825 | 30.037 | 93.9% | 1 | superseded ("optimistic") |
| RR 32×1 | — | — | — | — | 0 | **does not exist on AMI, our side** |
| LI default W=8 | 9.267 / 8.714 | 9.435 / 9.683 | 13.013 / 12.497 | 40.7 / 39.1% | 2 | banked |
| LI default W=16 | 8.793 | 9.374 | 9.291 | 29.0% | 1 | banked (n=1) |
| LI balanced 8×4 | 12.745 / 12.733 | 12.330 / 12.405 | 28.250 / 28.101 | 88.3 / 87.8% | 2 | banked (headline) |
| LI balanced 8×4 (25-Aug) | 13.676 / 13.434 | — | — | — | 2 | **never-quote for CPU** (collector defect; +6.0% on a different build) |

Both prior beliefs CONFIRMED: RR 16×2 exists at 12.729/12.753 n=2; RR 32×1
does not exist on AMI on our side. **In-repo gap — since CLOSED**: the
exports behind all three cells are now landed from the S3 archive with
per-file sha256 and contents-based identification
(`results/AMI_LANDING.md`); the landed exports confirm every banked
f/s/cores/util figure exactly, and this document's computed CPU-s/frame
values are the exports' own recorded `cpu_s_per_frame` (2.304/2.312 at
16×2, 2.601/2.579 at 8×4). The joined table is
`AMI_CROSS_TEAM_TABLE.md`.

## 9. The page-cache hypothesis for the ~20% (2026-09-06, from Shashi's films50 figures as relayed) — what the artifacts settle

**Hypothesis (relayed)**: the AMI corpus (~23 GB) fits the 61 GB page
cache while films (263 GB) cannot; if their AMI runs were warm and ours
cold, that makes an AMI gap and no films gap. Shashi's films50 RR 16×2
(12.52 f/s, 27.5 cores, 2.198 CPU-s/frame) sits 2.6% from our 12.198.

What the held artifacts settle:
- **Ours were cold, by construction, with proof.** Every leg evicts the
  corpus with `posix_fadvise(DONTNEED)` and a read-back that refuses if a
  sampled file still reads hot (`driver_video.py:2299-2310`,
  `probe/drop_cache_fadvise.py`; in the driver since 56ee341 on
  2026-08-20 — before the 24/26-Aug AMI runs). The per-leg proof lines are
  in the S3 run logs (not landed); the landed AMI exports carry
  `preleg_container_idle_cores` and the collector summaries and no cache
  field; the per-tick streams (`mem_available`, `cg_current − cg_anon`)
  are on S3, not landed.
- **Theirs are unrecorded and uncontrolled.** Leela's harness at both pins
  (aa817d9a, 3967d9f4; object reads only) has no drop_caches, fadvise,
  vmtouch, prewarm or residency field — the only cache mentions are the
  cgroup peak-memory basis notes (`cgroup_sampler.py:56`,
  `v_metrics.py:141/191`). Whether her AMI runs were warm cannot be read
  from held objects; with nothing evicting and 23 GB fitting, warm after
  the first pass is the default expectation, not a measurement. Shashi's
  `cache_resident_gb_before/after` exists only from films50 on.
- **The gap's form does not admit it.** The discrepancy is engine-cgroup
  CPU-s per frame at matched ~92% utilisation (§3). Corpus residency acts
  on the client-side file reads — outside the engine cgroup on both
  harnesses (our driver's sha pass and streamed send; her `send_files`
  client) — and shows up as iowait and lost throughput, not as CPU
  seconds; both sides ran ~92% util, so neither was I/O-starved. A warm
  client cannot lower the engine's CPU per frame.
- **It replicates where residency is impossible.** On films, Shashi's RR
  16×2 does 2.198 CPU-s/frame against our 2.543 (+15.7%, the wave-
  independent quantity; assumption stated in FILMS500_RESULTS.md's
  cross-team cautions) at 86% vs 97% util; the span rates coincide (12.52
  vs 12.198) only because his N=50 span is ramp/drain-depressed (3.1
  waves) while ours is saturated at N=498. A third harness, a second
  corpus, no possible residency, the same gap class.

**Verdict**: not supported for the AMI gap, contradicted by the films
replication; it does not answer the open question. The ask in §3 stands
— per-stage CPU split on one identical file through both harnesses at
the same posture, or one leg's cgroup sampler stream exchanged — with one
cheaper item now available: their cores basis stated (engine cgroup over
the leg with tokens live, idle burn included?) and, for any AMI rerun,
their `cache_resident_gb_before/after` beside ours (cold, proven).
