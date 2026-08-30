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
**BOX STATE: at `6b348c7`, pre-Ruling-K. It MUST `git pull --ff-only` to
the Ruling-L commit (the commit carrying this handoff revision, later than
`21c6ff2`) and then run `probe/run_ruling_l_box.sh` (li:video rebuild +
read-backs) before the posture sweep runs** — at `6b348c7` the sweep
wrapper does not exist and the point probe is the old, abortable,
OOM-blind one; at `21c6ff2` the Dockerfile still bakes 4000/200 and the
probe has no chunk read-back, so a sweep from there would silently measure
the wrong workload. The wrappers print `repo HEAD` and their own sha at
start; the STOP reads both. (The box has now committed on a stale base
twice — pull FIRST.)

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

## 4. OPEN — carry forward, do not silently drop

1. **Memory slope under concurrency** (Ruling G, top risk): 8.10 GB anon at
   ONE active lane is unextrapolated. Single-lane differencing gives
   ~0.94 GB/token resident + ~0.58 GB/active-lane (two equations, two
   points — assumes linearity through 8× BLAS scratch, allocator
   contention, coincident embeds, C×2.2 GB spool page cache). The **32×1
   posture point (~30 GB projected baseline, C=35) is the deliberate
   stress point**; mem_watch rides every point; an OOM there is a FINDING
   (oom block in every artifact: OOMKilled + memory.events deltas).
2. **The posture sweep is UNRUN** (`probe/run_films_posture.sh`, sha
   `7c0499ce…`): RR grid 8×4 / 16×2 / 32×1 / 4×8 / 8×2(under) /
   16×4(over); LI grid 8×4 / 16×2 / 4×8 / 8×2 / 8×8(over), W=1 held
   (kernel-accept skew measured pathological at AMI); C=min(2×lanes,35) on
   the full measured 35; SKIP_OVERSUB=1 is the budget lever. Ansh rules
   both postures from the printed POSTURE MATRIX.
3. **The C sweep is UNRUN** (`probe/run_films_curve.sh`, sha `1d0d846b…`):
   runs AFTER the posture ruling with RR_TOKENS/RR_TENV/LI_INSTANCES/
   LI_TENV set to the winners (defaults are AMI shapes and say so). Ansh
   rules C from the marginal chain.
4. **No warm-gated films leg until both sweeps land and are ruled.**
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
| posture sweep (RUN NEXT, after the box pulls the Ruling-L commit AND run_ruling_l_box.sh passes) | `probe/run_films_posture.sh` + `probe/probe_films_curve.py` |
| Ruling L (LI 4000/0): equivalence note; box rebuild+verify | `RULING_L_SPLITTER_EQUIVALENCE.md`; `probe/run_ruling_l_box.sh` + `probe/verify_li_chunk_config.py` |
| C sweep (after posture ruling) | `probe/run_films_curve.sh` (winners via env) |
| memory instrument | `probe/mem_watch.py` (fixed VmHWM, oom-aware sweeps) |
| sizing/equivalence/parity/detect-text probes + artifacts | `probe/probe_films_sizing.py`, `probe_reader_equivalence*`, `probe_frame_parity*`, `probe_detect_text*` (artifacts committed where noted; sizing/proof-2/anchor artifacts box-side, landing awaits ruling) |
| AMI banked numbers | DEFINITIVE (amended corpus line); anchor export box `~/films_probe/anchor_out/` |
| her repo pins + films500 DATA | `team_docs_received/README.md`; her `runs/films500-sizing/`, commit `2d7533b` |
