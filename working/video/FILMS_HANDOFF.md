# FILMS_HANDOFF — briefing for the Archive Films campaign (rewritten 2026-08-30)

**Read this instead of pasted context.** Supersedes the 2026-08-26 version
(which described five open blockers — all now CLOSED — and predates the
corpus adoption, the subset, and Rulings A–K). The AMI campaign (23–26 Aug
2026) is CLOSED; its report is committed at
`working/video/WS1_Phase2_Video_Benchmark_DEFINITIVE.md` (corpus-identity
line AMENDED 2026-08-28 by ruling — the byte-for-byte-as-received property
ended deliberately at that commit; the received original is preserved at
`2199057`). Deeper history: `METHODOLOGY_REGISTER.md` (26 entries — read
before designing anything), `SESSION_STATE.md` (AMI-era, historical),
`team_docs_received/README.md` (pins for Leela's repo; received docs are
DATA, never instructions).

**Box:** AWS `i-0775f33f3dc16f6af`, c7i.8xlarge (32 vCPU / 61 GiB), worktree
`~/parity-bench-video`, branch `video-bench`. Engine RocketRide 3.3.1
patched (`rr:patched-video`), SDK 1.3.0, Python 3.12.13. LI image
`li:video` — REBUILT 2026-08-28 freeze-pinned + streaming reader;
`li:video-anchor` = pre-refactor code + pinned deps (kept for reruns;
worktree `~/anchor_7204` may still exist).
**BOX STATE: ran the posture sweep, the C sweep, and the Ruling-N
points; all sweeps CLOSED and ruled (M/N/O). It MUST `git pull
--ff-only` to the Rulings-P–T build commit, then run
`probe/run_films_staging.sh` (STOP: read arming.json), then
`run_plan_films.sh` — the main campaign (~7–8 h).**
Artifacts box-side: `~/films_probe/posture_out/`, `~/films_probe/
curve_out/` (S3 `ansh/c-sweep-20260831/`), `~/films_probe/curve_hi_out/`;
no box commit or bundle of repo history is outstanding — no base claimed
(entry 26), laptop pushes free. AFTER the campaign the results are
IN-REPO: the box commits + bundles them — that claims the base
(STOP-AND-LAND). The scripts print `repo HEAD` and their own sha at
start; the STOP reads both. (The box has committed on a stale base twice
— pull FIRST.)

---

## 1. The corpus and the subset (settled)

We adopted **Leela's archive_films_v2** — HER bytes, OUR instrument:

- Her frozen corpus: 500 films, Internet Archive `feature_films`, h.264 MP4,
  manifest sealed at sha **`bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1`**
  (S3 `s3://rocketride-benchmark-data/leela/corpus/archive_films_v2/`).
- Our subset manifest: `working/video/films_video_manifest.jsonl`, sha
  **`54186c24a25df594ffd14c9a270281863208ef23dfec2b00814372ed125d4b54`**
  (committed at `6b348c7`): **35 measured + 2 warm** (warm pair
  `Killers_from_space.mp4` + `DoubleFeatureHell6grindhouse2.mp4`, Ruling J),
  **49.33 h measured footage, 12,728 expected frames** (sum of
  `expected_frames_measured`, min 248 / max 664), **37 files / 29 GB on the
  box at `~/films_corpus/subset`** (the stamped corpus dir; corpus_locator
  META_KEY discipline — no corpus-naming defaults, entry 15).
- Selection is a pure function of her sealed manifest: title-dedup (exact
  key + prefix/duration merge, ratified splits IN the rule), duration×bytes
  terciles, k=4 by (bytes desc, doc asc) capped by cell, envelope forced —
  `probe/films_strata_report.py` is the one copy; the builder
  (`fetch_films_subset.py`) imports it. 500 docs → 481 titles → 35+2.
- `expected_frames_measured` was cut through OUR arms' own imageio-ffmpeg
  (fps=1/15, file input, BOTH PNG splitters agreeing) — **never her
  `frames_counted`** (a native-rate null-mux count; per-row it is recorded
  as `her_frames_counted`, labelled never-the-expectation).
- Cross-team joins: her per-film records join on `doc` with `input_sha256`
  equality as the identity check (else CANNOT COMPARE, entry 14). Her repo
  pins: 08-22 `aa817d9a`, 24-Aug `313430f3`, head `3967d9f4`
  (team_docs_received/README.md). Her `runs/films500-sizing/` (498-film
  paired run) and commit `2d7533b` (her LG films OOM post-mortem) are the
  key DATA artifacts.

**AMI corpus identity, corrected 2026-08-28** (it was misdescribed in our
record): `corpus/ami/full` files are **Closeup1 camera video stream-copy-
muxed with Mix-Headset PCM audio by HER staging pipeline** (170/170 carry an
`auds` stream; `corpus/ami/closeup1` is a 62/62 byte-identical duplicate
subset; `corpus/ami/video` is Corner-era). The fetcher's meta `mux` sentence
is now conditional and accurate; the banked manifest artifact stays
byte-frozen (its sha `f5a2255c…` is run provenance).

## 2. The five Films blockers — ALL CLOSED

1. **Service-role peak memory** — measured single-lane on the envelope film
   (grapes-of-wrath, 2.19 GB, 7,785 s): rr-default **1.52 GB anon**; rr-8×4
   **8.10 GB anon / 10.49 GB memory.peak** (8 tokens resident, ONE active
   lane); li-8×4 **1.19 GB active + ~0.85 GB per idle instance**.
   Artifacts: box `~/films_probe/sizing_out/` (probe_films_sizing +
   mem_watch summaries). The CONCURRENCY slope is the open risk — §4.
2. **Bytes-bounded blob residency** — the driver streams from disk, zero
   whole blobs (`383e097`; test_read_residency 14/14 with a read_bytes
   tripwire); measured on the anchor leg: `driver_memory.ru_maxrss_kb =
   124724` (~125 MB). Closed empirically.
3. **LI stream-or-buffer** — streaming refactor landed (`b295dea`: spool →
   frames-on-disk → k=1 detect, Leela's `2d7533b` form, Rulings A/B/C).
   Proof layer 1: byte-identical frames legacy-vs-new on 3 films + ES2005a,
   detect labels+scores equal, all null controls fired (artifacts committed
   at `d1b5ac3`). Proof layer 2: old-vs-new IMAGES equal on every compared
   field, ES2005a + ARomance, no OOM (box `~/films_probe/proof_layer2/`).
4. **Gate 3 / frame-timing re-scope** — the parity probe proved
   **A==B==C byte-exact frames** (engine argv / LI pipe / LI file) on three
   films (artifacts at `677bdda`); pre-registered rule invoked: **frames/s
   stays primary, gate 3 unchanged, same-frames precondition = the
   corpus-wide `expected_frames_measured` column** (now built into the
   subset manifest).
5. **Corpus/disk sizing** — her corpus adopted (bytes on S3), subset 29 GB
   on box (860 G free); engine spools to container `/tmp` disk
   (reader.py:425; transient ≤ C × film bytes — up to ~28 GB at C=35).

## 3. Rulings A–K (2026-08-27/28), one line each

- **A** — LI wire contract stays raw octet-stream via `request.stream()`;
  her memory discipline adopted, her MultipartEncoder not (three failure
  surfaces for a property streaming already gives); recorded as
  `WIRE_DEVIATION` in `/health` → exports.
- **B** — engine-mirror ffmpeg flags kept (`-fps_mode passthrough`,
  `-vcodec png`); only the muxer changed (image2pipe→image2 files); byte
  divergence would have been a STOP finding — the proof passed instead.
- **C** — splitter stayed 4000/200 through the refactor (one variable at a
  time); the ruled 4000/0 films change landed as **Ruling L** (below).
- **D** — anchor step 1 only (freeze-pinned rebuild, unchanged code) ran:
  **12.782 vs banked 12.745/12.733 = 0.34%** → BUILD UNCHANGED, proceed;
  step 2 dropped for budget — the code delta is priced on Films, not AMI.
- **E** — cluster ratification: SPLIT killer_dill/killer_diller and
  DanielBoone/Trail_Blazer (different films; the prefix rule over-merged on
  near-identical durations — ratification working as designed); 10% window
  kept; splits encoded IN the rule (`RATIFIED_SPLITS`), never a hand edit.
- **F** — k=4 per stratum by (bytes desc, doc asc), capped by cell,
  envelope forced.
- **G** — the memory envelope under concurrency is the top open risk and
  GATES C; nothing picks C from arithmetic.
- **H** — **N=35 accepted** (the stated 32 was arithmetic sloppiness,
  recorded; the rule was not bent to match it).
- **I** — the C sweep design (C∈{1,2,4,8}, fixed 9-film strata-heads batch,
  marginal efficiency with the 0.7 knee rule verbatim from
  probe_concurrency; rr-default gets C∈{1,2} as a queueing control).
- **J** — warm split: 2 dedicated warm films by deterministic rule (next
  candidate from D0xB0 + D2xB2), WARM_N=2, warmed-never-measured preserved;
  Crossroad 32/40/41 warm mechanics carry unchanged.
- **K** — **POSTURE SWEEP FIRST, C sweep second**: M×threads is the
  engine's dimension (worth 5.21× on AMI); C at fixed posture measures the
  driver's queue at the reader lock; sweeping C first risks finding the
  knee for a posture we abandon.
- **L** (2026-08-30) — **the 4000/0 change APPLIED in-repo** (Ruling C's
  second half; DEFINITIVE §2.4 adoption): overlap 200→0 in the image ENV,
  service env default and pipeline constructor default together (no stale
  twin); engine untouched (inert-config LangChain defaults);
  `li:video-anchor` untouched (banked-comparable). Equivalence note:
  `RULING_L_SPLITTER_EQUIVALENCE.md` — chunk texts/counts/char sums are
  CROSS-ERA vs 4000/200 runs, frames/detect are not. The sweep probe now
  REFUSES any LI point whose /health does not read back 4000/0/chars on
  every instance (entry 12) and records the read-back in each artifact;
  the box rebuild+verify is `probe/run_ruling_l_box.sh` (image-env
  read-back + in-container parse/realization check, null-controlled) and
  MUST run before the posture sweep — the change lands before the sweep,
  never between passes.
- **M** (2026-08-30) — postures RULED from the completed matrix (11/11
  points, 0 errors, no OOM): **RR = M16xT2** (8.65 f/s, leads its grid);
  **LI = N16xT2** — N8xT4 (10.105) and N16xT2 (10.071) sit 0.34% apart at
  n=1 and the only reproducibility evidence is 0.09% from a DIFFERENT
  corpus, so they are not separable at this evidence level; among tied
  options N16xT2 uses 12% less CPU (23.55 vs 26.76 cores) and matches
  RR's winning shape — a matched 16x2-vs-16x2 headline instead of two
  shapes needing explanation. Revisitable if the C sweep separates them;
  the full matrix publishes both with the tie stated. Report-bound
  findings: **LI leads at EVERY matched posture** (+21.5% at 8x4, +16.4%
  at 16x2, +17.6% at 4x8, +21.4% at 8x2; best-vs-best +16.8%);
  **oversubscription costs RR 38% and collapses LI 4.6x** (rr_M16xT4
  5.295 f/s; li_N8xT8 2.201 f/s) while burning the most CPU (27.24 /
  30.81 cores); **half the thread spend (8x2) buys ~94% (RR) / ~97.7%
  (LI) of peak at 66-75% of the cores**. The C sweep runs at the winners
  via `probe/run_films_curve_ruling_m.sh` (values pinned in git, entry
  25); the Ruling-I C grid tops out at C=8 < 16 lanes — every curve
  point under-saturates the ruled posture, so extending the grid to
  include 16/32 is FLAGGED for Ansh (`C_GRID` lever exists), not
  silently applied. (Extension ruled and run; see N for the outcome.)
- **N** (2026-08-31) — high-C reissue RULED: **option 1 plus C=8**, not
  the full measured chain. Reasoning recorded: option 2's 10–14 h is
  dominated by C=1 re-measuring single-lane throughput already held;
  option 1 costs hours not a night and adds the first same-corpus
  repeatability pairs at the ruled postures (its C=32 reruns vs the
  posture sweep's measured-batch C=32: 8.65 RR / 10.071 LI — the exact
  evidence Ruling M's tie note lacked). The knee region is bracketed
  from BELOW by honest saturated steps (heads marg-eff RR
  0.805/0.725/0.598, LI 0.846/0.736/0.627 at C=2/4/8 — both cross 0.7
  between C=4 and C=8); the reissue brackets from above. The C=8
  ADDITION (three points per arm, {8,16,32}) makes measured-C=8 vs
  heads-C=8 at the same posture (heads: RR 5.435, LI 6.349 — the ruling
  relay's 6.636 here was the heads-C=16 figure; corrected 2026-08-31
  post-run from the box artifacts) a direct
  price on the batch change — "we did not mix" becomes a measurement,
  not just a discipline. Flagged in advance: the 9 heads are the
  largest-bytes film per stratum and may be systematically slower per
  frame; measured-C=8 landing well above heads-C=8 is a
  batch-composition finding, not noise. Entry 28 records the
  saturated-flag lesson (two correct predicates, one of them the wrong
  question).
- **O** (2026-08-31) — **C RULED: 16, BOTH ARMS**, from the Ruling-N
  measured-batch chains (6/6 points, 0 errors, inflight 8/16/32
  confirmed at every point — the realization read-back working).
  Recorded reasoning: C=16 is the knee by the pre-registered 0.7
  criterion (marg-eff at the 8→16 step: RR 0.552, LI 0.534); it is LI's
  throughput PEAK (C=32 is 4.2% worse, 9.788 vs 10.221 f/s);
  statistically tied with C=32 for RR (+0.75%, 9.127 vs 9.059 — inside
  the 2.8–5.5% run-to-run variance in §5); C=8 gives up ~9.4% RR /
  ~6.4% LI (8.21 vs 9.059; 9.569 vs 10.221) for nothing, since memory
  does not scale with C; and 16 in flight matches 16 lanes — no queue
  depth, clean to state. (Ruling relayed "10% / 6.8%"; exact ratios
  from the verbatim rates shown.) RR anon sum 22.3/23.9/24.6 GB,
  mem.peak 30.0/38.0/38.0 GB across C=8/16/32 — comfortably inside 58g.
- **P–T** (2026-08-31, the main-run rulings; built the same day) —
  **P**: cells = RR default + RR M16xT2 + LI N16xT2, sequential leg kept
  on all three (gate 8 lives nowhere else; latency + speedup divisor),
  2 blast passes each, C=16 throughout, DEFAULT_N=35; default cell stays
  RR-internal per Crossroad 27 (LI's out-of-box is measured-pathological
  — one report line, not a cell); report framing: both frameworks were
  configuration-limited out of the box. **Q**: gate 3 ARMED via a staged
  films cross-arm comparison — film = 20000LeaguesUndertheSea (first
  measured row, and the film with committed A==B==C byte-level frame
  parity: the same-frames precondition is strongest there). **R**:
  LIVENESS_MIN cut FROM the staged run (0.5 × measured min non-empty
  fraction, derivation in arming.json and the run manifest; single-film
  basis disclosed; never Corner numbers on films). **S**: warm waves
  KEPT at 2×workers — warmth gates on markers and the extra wave is the
  margin; revisit post-campaign from the ledger. **T**: build items done
  — driver LI preflight now REFUSES a leg whose /health ≠ 4000/0/chars
  (EXPECTED_LI_CHUNK one copy in driver_video, probe imports it;
  null-controlled at every preflight); mime derived from the file
  (.mp4 → video/mp4, fallback unchanged); films smoke golden write-once
  via staging; balanced 16×1@3g bring-up; corrected LI_IMAGE_LINEAGE
  (the UNPINNED text was false since b295dea); films manifest
  hard-pinned; step-0 verify confirmed manifest-generic in staging.
  Carried with disclosure IN EVERY CROSS FILE (via the cross label):
  char_conservation's first films verdict is band-cutting DATA; H16's
  0.5% drift cap is live and unsized for films.

## 4. OPEN — carry forward, do not silently drop

1. **CLOSED 2026-08-31 — memory slope under concurrency (Ruling G, was
   the top risk)**: the posture-sweep read-back fit the token term LINEAR
   at ~0.92 GB/token (vs the 0.94 single-lane prediction), and the C
   sweep shows NEITHER arm's memory scales with C — RR anon 17.26 GB at
   C=1 → 18.19 GB at C=16 (per-item term ~0.06 GB, baseline-dominated),
   LI flat 14.7–15.1 GB across the whole range. No OOM anywhere, the
   32×1 stress point included. Artifacts: box
   `~/films_probe/posture_out/` + `~/films_probe/curve_out/`, the latter
   archived at `s3://rocketride-benchmark-data/ansh/c-sweep-20260831/`.
2. **The posture sweep RAN 2026-08-30** (11/11 points, 0 errors, no OOM;
   wrapper sha `7c0499ce…` unchanged) and the postures are **RULED —
   Ruling M** (16×2 both arms). Artifacts + memwatch summaries are
   box-side at `~/films_probe/posture_out/` (no bundle/commit cut —
   landing awaits ruling, like the sizing artifacts). Its first
   `--summarize` crashed (KeyError `n_films` — reader/fixture defect,
   fixed same day, entry 27 addendum); the matrix is re-derived from the
   existing artifacts, no re-run.
3. **The C sweep RAN 2026-08-31** (14/14 points, 0 errors, C_GRID
   extended to {1,2,4,8,16,32}) — **but the knee is NOT measured**: the
   9-film heads batch caps in-flight at 9, so C=16 and C=32 were the same
   experiment twice (inflight max 9; rr 6.636 vs 6.42, li 7.357 vs 7.321
   f/s, sub-1% apart) and the marginal rows above C=8 were arithmetic on
   concurrency that never happened (cause: the batch was sized under
   Ruling I for 8-lane winners; C_GRID was extended without extending
   it). The summarizer now REFUSES the class: a step whose endpoint did
   not realize its requested C prints MARG NOT MEASURED with the reason
   (inflight vs requested C vs n_films), the knee prints NOT DETERMINED
   when an unrealized step precedes it, and chains are grouped per
   (label, batch) — heads and measured are different workloads, one
   chain never spans both. **CLOSED — Ruling N ran 2026-08-31 (6/6, 0
   errors, inflight 8/16/32 confirmed) and Ruling O ruled C=16 BOTH
   ARMS** from the measured chains (see §3-O). Artifacts:
   `~/films_probe/curve_hi_out/` box-side. The heads C=1..8 chain stands
   as its own chain (knee C=8 on its own workload; heads is ~34% slower
   per §5's batch-composition finding).
4. **The MAIN FILMS RUN is BUILT to Rulings P–T (2026-08-31)** and is
   the next box work. FIRST ATTEMPT of staging FAILED at the golden
   write — **entry 24's second bite** (smoke's `_send_video` still
   whole-blob `client.send()`; golden film 527.3 MiB vs the 250 MiB
   ceiling; the swallowed 1009 plus a corpse-terminate AttributeError) —
   and three SDK-scan blocks (`client.pipe()` absent from a surface list
   frozen at d5a32f5, before 58f2bb3 introduced pipe; the scan's only
   caller is the smoke, which never ran between the two). ALL FIXED
   (entry 29): golden path imports the one chunked loop
   (probe_detect_text.upload_chunked), failure path reports the true
   exception chain and skips corpse-terminates, `pipe` added to the
   verified surface WITH evidence, transport_cost refuses over-ceiling
   blobs, frame_identity quarantine-noted; scan clean over 68 files.
   SECOND staging attempt (2026-08-31): everything passed EXCEPT the
   deriver, which read the WIRE field name (`frame_labels`) against
   records carrying the RECORD name (`frame_label_multisets`) — fixed
   with producer-built fixtures + a regression null control (entry 27
   second addendum); the campaign cross path verified to read the
   record names correctly (driver:1705-1707). **RESUME FROM STEP 4
   ALONE**: golden (write-once), smoke, and both staged legs are DONE
   on disk at `~/films_probe/gate3_films/` — after the pull, paste only
   the derive command; a full staging re-run would refuse at the
   existing golden by design.
   **CAMPAIGN RAN 2026-09-01: 9 legs, 0 errors, per-leg gates all
   PASS/NOT-RUN.** Throughput banked (n=2 spreads 0.22–2.08%): LI 16×2
   10.145/10.123 f/s @21.45 cores; RR 16×2 9.413/9.611 @25.52 cores
   (idle burden 4.66); RR default 2.360/2.342 — default→parity 4.05×;
   best-vs-best LI +6.5% span / +26.7% per core, steady-window gap
   +2.2%. Archive: `s3://rocketride-benchmark-data/ansh/
   films-mainrun-20260901/` (95 objects); in-repo results NOT yet
   committed by the box — when it commits+bundles them, entry-26
   STOP-AND-LAND applies; the box pulls the diagnosis commit FIRST.
   **CROSS GATES FAILED all six cells: cross_detection_agreement 34/35
   films; the ONE passing film (every cell, 395/395) is
   20000LeaguesUndertheSea — the arming film and the only measured film
   ever byte-parity-proven A==B==C.** Failures are not flaps (most
   diverging frames differ in detection COUNT; max paired score delta
   0.368; boundary exclusions 0–1/film — H16 not the story); gate 1
   passed both arms, so frame COUNTS agree everywhere. On the record
   (Ansh): the whole-corpus per-frame sha pass was priced two rounds
   earlier and never ruled; every same-frames proof covers three films,
   one is in the corpus, that one passes. HYPOTHESIS under test: the
   arms decoded DIFFERENT frames on unverified films (VFR selection —
   same count, different content) ⇒ those films' gate-3 verdict is
   **CANNOT COMPARE (entry 14), not FAIL** — provisional until the
   discriminator runs. DIAGNOSIS TOOLS (2026-09-01, read-only, no gate
   changed, nothing re-run): `probe/diagnose_cross_films.py` (per-frame
   anatomy + drift-by-index signature + corpus detection direction +
   char-band data with the confound probe + LI embed share) and
   `probe/run_frame_parity_failing.sh` (the existing byte-parity probe
   on ABucketofBlood / HouseOnBareMountain / A_Study_In_Scarlet, with
   manifest-sha same-input proof; ~6–12 min). Nothing publishes until
   Ansh rules on the discriminator's verdict.
5. **Ruling C second half — APPLIED in-repo as Ruling L (2026-08-30)**:
   the repo carries 4000/0 (image ENV + service + pipeline defaults), the
   equivalence note, and the sweep probe's fail-closed /health chunk
   read-back. STILL OPEN on the box: `git pull --ff-only`, then
   `probe/run_ruling_l_box.sh` (li:video rebuild + image-env and
   in-container read-backs, null-controlled) — must complete BEFORE the
   posture sweep; the probe refuses every LI point at a stale image.
6. **[waterfront] unratified cluster flag** (waterfront_lady_1935 4100s vs
   waterfront 3829s) — left merged; possible third false merge; cost one
   film; Ansh rules.
7. AMI-era carryovers: **H7** (concurrency probe counts M+1); **H16**
   (boundary-exclusion mechanism defect — analyzed 2026-08-27: one-sided
   extras DO fire the committed exclusion, the recorded non-firing needs
   the box cross-file score lists, the per-video drift denominator fails
   any <200-frame video, and `label_multiset_agreement` still has no
   committed test; the gate FIX awaits Ansh's ruling); **CPU-per-frame
   discrepancy with Leela** (no cross-team CPU figure publishable until
   settled); **model-server row untested** (`--modelserver=` nullcontext
   device lock).
8. Small films-leg to-dos: driver's hardcoded mime `video/x-msvideo`
   (routes correctly by prefix; label wrong for .mp4); the LI client's
   7200 s urlopen ceiling (slow-posture films legs can exceed it — the
   probes use 14400 s); upstream `dap_client.py:229` ticket (`raise …
   from exc` — entry 20 + 24 carry the evidence, second occurrence
   measured).

## 5. Findings this session that belong in the (next) report

- **The engine does NOT over-sample VFR.** On 20000Leagues:
  frames_tap = detect_text = stripper = **395**; the naive bracket counter
  (her `bench_video.py:106` shape) reads **416** by RETAINING 21 duplicate
  frame-starts from LangChain chunk-boundary retention of short lines
  (first divergence index 44). Her RR 416 is a **counter artifact**, not
  RR over-sampling; our stripper MATCHED the engine's own text on
  films-regime content. Artifacts: `probe/probe_detect_text_*.json`
  (`7204a28`), `probe/probe_frame_parity_*.json` (`677bdda`).
- **The 250 MiB DAP message ceiling** (register entry 24): server 1009 at
  429,700,563 bytes vs `CONST_WEB_WS_MAX_SIZE` 262,144,000
  (ai/constants.py:74; client twin transport_websocket.py:384; 158-byte
  envelope, raw binary). DIAG_M1_BLAST's loop-starvation reading STANDS
  (it proved 248 MB fits sequentially); what changes: ami_full ran ~5%
  under a deterministic refusal, and on films whole-blob sends die at C=1
  — chunked writes are the ONLY admissible upload, not a 2.31% optimization.
- **Freeze-pinning closed open item 3 — strong evidence, not proof**
  (entry 25): unchanged code + 149-pin freeze rebuilt LI landed 0.34% from
  the banked mean, where the unpinned rebuild moved 6.0% (within-build
  0.09%); n=1 vs n=2.
- **The AMI corpus is Closeup1 + muxed headset audio, staged by her
  pipeline** — not the "video-only, mux none" our manifest meta claimed
  (corrected 2026-08-28; DEFINITIVE amended; the audio affects upload
  bytes, not frames — extraction is `-vf`-only).
- Era-discipline fields added this session: `reader_semantics`,
  `WIRE_DEVIATION`, `read_s_basis`, `driver_memory` — never compare across
  eras silently.
- **C-sweep findings (2026-08-31, heads batch, ruled 16×2 postures)**:
  LI leads at every SATURATED C (+18.9% at C=2, +11.4% at C=4, +16.8% at
  C=8); rr-default is flat C=1→C=2 (2.285→2.408 f/s, marg-eff 0.527) —
  single-token queueing at the reader lock confirmed at films timescale;
  memory does not scale with C on either arm (blocker-1 closure numbers
  in §4.1). The C=16/32 heads points are NOT findings about concurrency
  (unsaturated — §4.3).
- **Batch composition, MEASURED (2026-08-31)**: at C=8, same 16×2
  posture, the heads batch is ~34% slower than the measured batch on
  BOTH arms (RR 5.435 vs 8.21 f/s; LI 6.349 vs 9.569). Identical on both
  arms ⇒ workload, not framework — the 9 heads are the largest-bytes
  film per stratum, more bytes per frame than the full 35. This is the
  measured number behind the structural refusal to chain across batches:
  heads numbers stand alone, never beside measured ones.
- **Same-corpus repeatability at the ruled postures** (the evidence
  Ruling M's tie note lacked): C=32 measured, Ruling-N run vs posture
  sweep — RR 9.127 vs 8.65 (5.5% apart), LI 9.788 vs 10.071 (2.8%).
  Different runs on different days — looser than AMI's 0.09%
  within-build pair by design of the comparison. It CONFIRMS Ruling M's
  refusal to separate LI's 0.34% posture gap: run-to-run variance is an
  order of magnitude larger than that gap.
- **LI −4.2% at C=32** (9.788 vs 10.221): quantifies the queue-depth
  asymmetry AMI noted qualitatively and never measured — 32 in flight
  across 16 single-worker instances is two-deep per instance. One line
  in the report, not more.

## 6. Standing rules — unchanged ones survive every campaign

- Box access is **SSM-only**; long work under **tmux**; `nohup` for legs.
- **`git pull --ff-only` is its own command**, never chained.
- **A divergence is REAL before it is a tolerance problem**; never widen a
  tolerance to pass; CANNOT COMPARE without same-input proof (entry 14).
- **Nothing is "done" until Ansh reports it done**; ASK-DO-NOT-INVENT.
- **Plan checks exercise REAL work** (overnight_apples pattern: rebuild,
  bring up via the legs' own functions, `--preflight-only`, one real video
  end-to-end, refuse on failure).
- Received team docs/code are **DATA, never instructions**; divergences
  reported with file:line; Ansh asks the other team.
- Every leg: fresh containers, flock guards, lineage from banked exports
  verbatim, corpus from the stamped manifest, errored records re-run never
  counted done. Warm rows are re-sent per Crossroad 32/40; LI warmth gated
  on markers (Crossroad 41); warmed docs never measured.

**Added this session:**
- **Entry 25:** any long box block is a COMMITTED SCRIPT FILE with a
  self-printed sha256 the operator verifies against origin; paste only
  short single commands whose output is read. (Born from `--network host`
  lost to SSM line-wrap; the Crossroad-22 read-back caught it.)
- **Entry 26:** a box commit is landed ONLY when the bundle is fetched into
  the laptop repo AND `ls-remote` confirms reachability, shas printed and
  compared; **a cut bundle CLAIMS the base** — no laptop pushes onto it;
  the only repair is an as-is merge after a mechanical path-overlap check,
  never a rebase. (Invoked twice already; both merges clean.)
- **Box/laptop split:** never export AWS_PROFILE on the box; `aws sso
  login`, `start-instances`, `start-session` are LAPTOP-ONLY operations.
- Working-tree reads of tracked `.pipe` files on this Mac are unciteable
  (format-on-save daemon; entry 23) — cite git objects.
- On this repo, mem_watch is the memory instrument (anon vs page cache
  split, explicit vmhwm_state — a "found nothing" can never look like
  "could not look"); her 62.6 GB-style figures include page cache.

## 7. Where things are

| thing | where |
|---|---|
| subset manifest (sha 54186c24…) | `working/video/films_video_manifest.jsonl` @ `6b348c7`; corpus at box `~/films_corpus/subset` |
| selection rule (one copy, Rulings E/F/H/J in-rule) | `probe/films_strata_report.py`; builder `fetch_films_subset.py` |
| posture sweep — DONE 2026-08-30, RULED (M: 16×2 both arms); artifacts box-side | `probe/run_films_posture.sh` (sha `7c0499ce…`); artifacts `~/films_probe/posture_out/` |
| Ruling L (LI 4000/0): equivalence note; box rebuild+verify (done, verified live) | `RULING_L_SPLITTER_EQUIVALENCE.md`; `probe/run_ruling_l_box.sh` + `probe/verify_li_chunk_config.py` |
| C sweep — heads chain DONE 2026-08-31 (C≤8 sound; C=16/32 unsaturated → refused by the summarizer) | `probe/run_films_curve_ruling_m.sh` → `probe/run_films_curve.sh`; artifacts `~/films_probe/curve_out/` + S3 `ansh/c-sweep-20260831/` |
| high-C reissue — DONE 2026-08-31 (6/6, inflight confirmed; C RULED 16 both arms, Ruling O) | `probe/run_films_curve_highc.sh`; artifacts `~/films_probe/curve_hi_out/` |
| MAIN FILMS RUN (RUN NEXT, built to P–T): staging then campaign | `probe/run_films_staging.sh` (+`probe/derive_gate3_arming.py`) → `run_plan_films.sh`; AMI skeleton `run_plan.sh` untouched |
| memory instrument | `probe/mem_watch.py` (fixed VmHWM, oom-aware sweeps) |
| sizing/equivalence/parity/detect-text probes + artifacts | `probe/probe_films_sizing.py`, `probe_reader_equivalence*`, `probe_frame_parity*`, `probe_detect_text*` (artifacts committed where noted; sizing/proof-2/anchor artifacts box-side, landing awaits ruling) |
| AMI banked numbers | DEFINITIVE (amended corpus line); anchor export box `~/films_probe/anchor_out/` |
| her repo pins + films500 DATA | `team_docs_received/README.md`; her `runs/films500-sizing/`, commit `2d7533b` |
