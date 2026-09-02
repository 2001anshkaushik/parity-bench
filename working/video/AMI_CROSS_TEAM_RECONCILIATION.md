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
(`container_idle_cores`, 4 s sample; reported beside, never subtracted —
driver_video.py:963, :1003-1015). Values at 16: ours 4.66–4.71
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
- Per-file BYTES: our per-file sha256s live in the box-side AMI manifest
  (verified by `--verify` before every leg); her corpus_pin verifies hers.
  Both corpora were staged by HER pipeline to the same S3 prefix and ours
  was fetched from it. **Byte identity is very likely but NOT PROVEN from
  laptop-held objects** — provable in minutes on the box (our manifest
  shas vs her committed/manifested shas). HYPOTHESIS until then.
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
does not exist on AMI on our side. **In-repo gap, stated**: the AMI export
files themselves are NOT committed (only the 08-23 run_manifest +
run_plan.log are in-repo); the banked numbers live in the DEFINITIVE with
exports box-side. If the reconciliation goes cross-team, landing the AMI
exports the way the films results were landed is the first step.
