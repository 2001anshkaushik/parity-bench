# SESSION STATE — 2026-08-21, written pre-compaction

**Audience: the post-compaction session, holding only this repo.** This is a
briefing, not a summary. Read PHASE1_CARRYOVER.md first (its corrections
appendix included), then this. Verify anything here marked UNRELAYED before
using it.

---

## Rulings this session (operator = the reviewer relaying Ansh's decisions)

- **Crossroad 15:** corpus re-cut to **44 measured + 16 warm** over the 60 ES
  files. Do NOT widen views to Closeup/IS/TS — framing homogeneity beats four
  meetings (IS rooms name views C/L/R, TS rooms Overview1/2 — mirror-surveyed;
  the fetcher was correct, not buggy). WARM_N=16 is provisional until the
  sweeps give serving-instance counts.
- **Crossroad 16:** NO batched re-run before Monday. Monday leads with the
  16-Aug per-doc 10k pair (clean on both axes) + the four engine tickets, and
  states plainly the batched comparison awaits a clean re-take. Paragraph
  drafted in session reports.
- **Crossroad 17:** thread values are PER-ARM OPTIMA, not forced equal. Same
  sweep matrix both arms, each arm takes its own optimum, full matrix
  published, declared==measured enforced PER ARM (docker-inspect env vs
  in-process), cross-arm difference RECORDED never failed. #37 was undeclared
  asymmetry, not asymmetry. LI_WORKERS is its own evidence-derived number
  (default 1 is a handicap).
- **Crossroad 18:** bake vision deps ONCE into `rr:patched-video`
  (bake_rr_video.sh: one pipe load, docker commit, four fail-closed
  read-backs: labels survive, pins inside, weights md5, no-install <180s +
  zero download lines). All probe/run_plan defaults point at the baked image.
  LI image needs no bake (build-time hermetic).
- **Crossroad 19:** `ws1-llamaindex:x86_64` (Phase 1 image) STAYS — no
  pin-locked Dockerfile means a rebuild can't reproduce it and the Crossroad-16
  re-take needs it. Reclaim from docker build cache only, and only under 15 GB
  free. The test is "could we get it back", never "does anything reference it".
- **Crossroad 20:** local verification is bounded to SYNTAX AND ARGUMENT
  CONTRACTS. No mocks of engine or LI service — a mock tests the mock.
  Everything semantic is box-side.
- **Crossroad 21 (relayed 2026-08-21): keep-alive policy.** REQUIRED during
  downloads and builds; FORBIDDEN during probe_disk, the probe, both sweeps,
  and every measured leg. Bounded by `timeout` so it cannot outlive its
  purpose, and greppable by its own command string — the old one showed in ps
  only as `-bash`, which is why it hid for three days and contaminated every
  18-Aug run.
- **Crossroad 22 (2026-08-21): both arms run `--network host`**, matching
  Phase 1 carryover section C. Reasons: docker-proxy inserts a userspace hop
  into every message (latency is a measured quantity), and a silent deviation
  from the configuration Phase 1's numbers came from breaks cross-phase
  comparability for no gain. Arms run one at a time, so no port conflict.
  The mode is a RECORDED provenance value with a fail-closed preflight check,
  never an implicit flag. Readiness is never TCP (instance seven): RR = real
  SDK connect() retry with deadline, LI = /health JSON (+warm_workers==W) —
  one helper, `working/video/probe/wait_ready.py`, everywhere a container
  starts.
- **Crossroad 24 (2026-08-21): CLOSED — REPRODUCED.** Recheck (fresh
  container): send1 16.2 s @ 0.4683, send2 38.2 s @ 0.1814, vs original
  15.0/35.9 @ 0.4638/0.1805. Two runs, same shape, same magnitude — the t32
  steady-state regression is REAL. **RR KNEE = 8; RR_THREADS_ENV = 8 (the
  first of the eight run-plan numbers, LANDED).** LI_THREADS_ENV is NOT 32
  either (knee between 8 and 32, closer to 8) — the worker sweep decides it,
  since workers and threads compete for the same 32 cores. **Ticket 5
  drafted** (working/upstream/RocketRide_Engine_Tickets.md) with the
  CPU-seconds arithmetic: identical workload (83 frames / 2,154 dets / 166
  chunks) at ≈146 CPU-s (t8 steady) vs ≈207–222 (t32 steady) across 2.1×
  the wall — architecture, not noise.
  **CLOBBER INCIDENT (register entry 7):** the recheck was run as
  `PROBE_MATRIX=32 probe_run.sh` — the disqualified form — overwriting the
  original probe_rr_t32.json (also re-ran li_floor_t32 / identity_early /
  census_m2: equivalent-config re-measurements, acceptable). Original t32
  full JSON is UNRECOVERABLE; headline numbers survive in
  phase2_logs/probe_20260821_195214.log and here. RESTORE (box, probe dir):
  verify the current file IS the recheck (`python -c "import json;
  print([s['wall_s'] for s in json.load(open('probe_rr_t32.json'))['sends']])"`
  → expect ≈[16.2, 38.2]), then `mv probe_rr_t32.json
  probe_rr_t32_recheck.json`, and drop a non-JSON sidecar
  `probe_rr_t32.CLOBBERED.txt` naming the incident, the preserved numbers,
  and the log — so the summarizer never presents one run as two. probe_run.sh
  now has preserve(): existing outputs move to `*.prev_<ts>` before any
  write; the quotable command can no longer destroy evidence.
  **RESTORE DONE AND VERIFIED (2026-08-21):** probe_rr_t32.json printed
  [16.17, 38.24] before the rename; now probe_rr_t32_recheck.json with the
  CLOBBERED sidecar beside it.
- **Crossroad 23 (2026-08-21): DELETE THE FORMULA, MEASURE THE COLUMN.**
  fps=1/15 emits t=0,15,…,1230 on a 1248.3 s stream — 83 frames;
  floor(d/15)+1 said 84. NO corrected formula (fitting the check to one
  observation is reverse-engineering). `expected_frames_measured` is counted
  at manifest build through the arms' own imageio-ffmpeg via pipe:0
  (fetch_ami_video --build-manifest, ~12 s/video); the driver REFUSES rows
  without the column. est_chunks columns re-derived from probe-measured
  dpf + chars/det (REQUIRED build args; probe/summarize_probe_rr.py prints
  both). Gate 1 keeps full force. Register entry 5.
- **Gate rulings:** gate 1 frames-census is THE dropped-frame detector; log
  scrape is ATTRIBUTION only, fail-closed on its own channel liveness. Gate 3
  STRICT zero tolerance, armed only via --gate3-armed <probe_run_id> after the
  staged ES2002a comparison; on divergence the FIRST hypothesis is a real
  difference, never "tolerance too tight"; score_triage is diagnostic-only
  (has no PASS key by construction); only a human downgrades, in writing.
  Gate 4 (PNG identity) is probe-scope. Gates 7 (embed integrity) + 8
  (determinism repeat) adopted. Char conservation ±2% stays, after gate 3.
  Duplication: organic only, NOT RUN below 64 chunks (never PASS); the Phase 1
  PDF fixture survives ONLY as the image-identity check in the smoke.
  NOT RUN is first-class: arming condition never occurred; never counts as
  pass. Every detector ships a null control that must fire.
- **Metric set:** frames/s primary (6.2x duration spread, 470.6–2905.4 s,
  kills videos/hour); realtime factor derived; chunks/s as Phase 1 bridge;
  steady window vs total span BOTH, labelled, window_n structurally required;
  latency normalized to wall-s per video-minute with raw beside it; p50/max/n
  only below n=50; per-instance memory as well as per-arm; submission order =
  manifest-seq both arms (NOT longest-first), recorded with reason. DROPPED:
  docs/s, chunks-per-doc as proxy, fixed 64-chunk predicate as universal.
- **Quiet-box:** gate on FOREIGN EXCESS = load1 − measured per-container idle
  baselines (threshold 2.0), values recorded, never booleans. Born from the
  18-Aug +8-core contamination caught two days late via system_tick.load1.

## The environment-identity rule (generalized, adopted)

**Any premise of the form "X and Y are the same" or "X is what runs" gets a
measurement before it bears load; repeated load → standing read-back.**
Environment identities get the model-identity treatment (we md5 weights; the
same rigor now applies to interpreters, creators, delivery surfaces).

Canonized 2026-08-21 (read these before writing many call sites again):
**"Eight self-consistent sites are one observation, not eight."** and
**"The check has to cross an independence boundary"** — execution, or an
artifact your writing didn't produce. Same lesson as "a source trace is not a
measurement", from two directions; both entries live side by side in
`working/video/METHODOLOGY_REGISTER.md` (draft — placement is Ansh's).

Instances so far: (1) push surface (commits reported done but never pushed);
(2) interpreter (bare python3 in scripts; box python3=3.10 no psutil);
(3) venv creator (python3 -m venv assumed; ensurepip stripped);
(4) interpreter version ("both arms are 3.12" argued from prose — engine
embeds its own CPython, resolved from the pinned binary);
(5) checker's own shell (this laptop's Bash tool runs **zsh — unquoted $VAR
does NOT word-split**; bit the ten-minute sweep 3x);
(6) **SDK import surface (RESOLVED 2026-08-21, the sharpest yet):** every
video-tree file imported `RocketRide`, a class in NO generation of the SDK —
eight sites, six files, perfectly self-consistent, none executed. The bake
died on the first import ever attempted. Measured surface: `RocketRideClient`
(Phase 1's 40+ sites + the installed wheel's inspect.signature paste). The
lesson beyond the fix: N self-consistent copies of one memory are ONE
observation — `working/video/sdk_identity.py` now owns the verified surface
(names + PARAMETERS, null-controlled) and its `--scan` breaks the pattern
statically before first execution. The wheel's use() carries `team_id` which
the dev checkout lacks — checkout != wheel, proven;
(7) **readiness predicate under a changed network mode (2026-08-21, operator-
diagnosed):** the TCP port check was MEASURED meaningful in Phase 1 under
`--network host`; carried into `-p 5565:5565` it silently measured
docker-proxy instead of the engine (the proxy binds the published port the
instant docker run returns). A measurement is bound to the conditions it was
taken under. Fixed by Crossroad 22 + wait_ready.py; register entry 3.

Known still-unmeasured sameness claims: LI image python micro version
(read-back lands at first /health); floor-vs-engine ffmpeg build strings
(gate 4 measures the consequence); glibc/OpenMP across container bases (torch
bundles its own OpenMP; the staged gate-3 comparison is the measurement).

## Exact box state (as relayed; box paths relative to ~/parity-bench)

- **Floor venv GREEN:** `venv_creator: base-interpreter (/usr/bin/python3.12
  (3.12.13))`; 11/11 pins exact; base ~/.venv torch 2.13.0+cpu UNMOVED;
  psutil 7.2.2. uv, virtualenv, pip3 all ABSENT on the host; system python3 =
  3.10.12 with ensurepip stripped.
- **Corpus:** 60/60 sha-verified, 44 measured + 16 warm, REUSE PROOF
  fetched=0. Manifest: `working/video/ami_video_manifest.jsonl` (BOX-side
  artifact — may not be in this repo's tree; check before assuming).
- **Pins** (`working/video/li_video/engine_pins.txt`, box-generated):
  rfdetr==1.5.2, torch==2.10.0+cu128, torchvision==0.25.0+cu128,
  transformers==4.53.3, timm==1.0.28, supervision==0.30.0,
  imageio-ffmpeg==0.6.0, sentence-transformers==5.7.0,
  langchain-text-splitters==1.1.2, numpy==2.5.2, pillow==10.4.0.
  cu128 wheels need `--extra-index-url https://download.pytorch.org/whl/cu128`.
- **Weight lineage:** rfdetr 1.5.2 → rf-detr-base.pth ←
  storage.googleapis.com/rfdetr/rf-detr-base-coco.pth,
  **md5 b4d3ce46099eaed50626ede388caf979** (package registry, wheel-inspected).
  RFDETR_BASE_MD5 in the driver; read back in-container per run.
- **Engine interpreter:** CPython **3.12.13 EMBEDDED in the engine ELF**
  (version string in the pinned 3.3.1 binary; 808-member lib/python3.12-only
  stdlib; no python binary file ships). Container PATH python3 = apt 3.10.12,
  SDK/bootcheck only, never runs node code. 3.12.13 == ~/.venv == floor.
- **Engine idle spin: 1.002 cores** measured, box otherwise idle (Ticket 4).
  Whether it scales per token = probe_concurrency's idle-at-M answers.
- **Black fixture:** generated box-side by make_black_fixture.sh; sha relayed
  2026-08-21 as `8ea9be50…` (prefix; the sidecar at
  `working/video/probe/media/black_60s_352x288.avi.sha256.txt` ON THE BOX
  remains the full authority). ffmpeg 7.0.2-static.
- **THE 1 TB LANDED (2026-08-21, relayed): nvme0n1 1000G, partition+fs already
  extended, / at 969G with 902 GB free — disk is NO LONGER A CONSTRAINT** (no
  pruning, no two-pass concerns, no retention limits). Survived the stop: all
  six images incl. li:video + rr:patched-video, no containers, load 0.23,
  keepalive dead, box repo at 53aa368.
- Image labels confirmed: duplication_patch_applied=1,
  patch_id=preventDefault-after-embedding-flush, engine_version=3.3.1.
- 8x md5sum keep-alive (team's own): 18-Aug 02:15:20 → 21-Aug 01:18, killed.
  18-Aug runs contaminated (+8 load1 floor); 16-Aug run10k blast pair
  (RR 2500 s / LI 1565 s) is the both-axes-clean Phase 1 result.

## Build order: DONE vs PENDING, honestly

DONE (all on origin, every push ls-remote-verified):
pipe fixed (source key, threshold sub-object, inert strlen REMOVED);
fetcher + planning columns; probe suite (fetch/disk/run/rr/floor/identity/
concurrency/li_workers/fixture/fadvise/setup_floor_venv w/ 4-way creator);
driver (postures, gates wired, windows, quiet-box excess, latency block,
interpreter+checkpoint read-backs); gates_shared batches 1+2 (all
null-controlled); smoke_video.py (5 sections; NEVER YET RUN against a live
engine); run_plan.sh (8 required vars + DRY_PASS + run_manifest.json);
bake_rr_video.sh; Dockerfile.llamaindex-video + li_video skeleton;
samples + reviewer README; query_phase1_chunks (box-run, adjudicated);
Ticket 3 + Ticket 4 drafted; carryover corrections #1+#2 appended.

PENDING, box-side, in order: **bake retry (failure RESOLVED — below; this is
the first execution of the fixed SDK batch)** → LI image build
→ probe_run.sh (incl. identity load-proof FIRST, staged gate-3, frame-count
84 check) → dry pass (DRY_PASS=1) → RR concurrency sweep → LI worker sweep →
thresholds land (M_TOKENS, LI_WORKERS, RR/LI_THREADS_ENV, LIVENESS_MIN,
GATE3_RUN_ID, BLAST_C, final WARM_N + re-cut if ≠16) → smoke --write-golden →
full smoke → run_plan.sh. HELD until sweeps: the eight numbers. Monday
deliverables drafted (lead paragraph, methodology register entry — placement
is Ansh's).

## RESOLVED (2026-08-21): the bake failure — and the audit it opened

The failure was `ImportError: cannot import name 'RocketRide' from
'rocketride'` — MY OWN invented class name, in every video-tree SDK site
(instance six above). NOT the pre-flagged joints, though joint (b) WAS also
real and is now fixed (dist-info listing, no interpreter needed — the engine
ships no python binary file). The full audit found and the batch fixed:

- **D1** all 8 import sites -> `RocketRideClient()` BARE + env credentials
  (driver/smoke via `rr_credentials.resolve(strict=True)`; probes/bake via
  explicit env), `connect(timeout=60000)` (Phase 1's measured pattern).
- **D2** `terminate()` was absent EVERYWHERE -> now in every finally/stop()
  (Ticket 4: a leaked ttl=7200 token idle-spins ~1 core in the cgroup the
  next leg's collector reads; run_plan keeps rr up across postures).
- **D3 — the finding of the night:** the engine derives the task token from
  (userId, project_id, source) (task_server.py:1074), so M use() calls on the
  measured pipe's FIXED project_id are ONE task — the parity posture would
  have silently collapsed to a queue ("RocketRide doesn't scale" from our own
  driver). Fixed: every use() loads a fresh-uuid5 variant
  (probe_rr.fresh_project_pipe, one minter); driver asserts M NEW task
  processes via settled census (fail-closed, ruling: stays regardless of
  use_existing semantics); sdk_identity.assert_unique_project_ids per run.
  Wheel-confirmed 2026-08-21: `use_existing` defaults to **None — falsy — so
  the LOUD variant is live** (a colliding token raises rather than silently
  sharing); the census assertion is belt-and-braces by construction, kept.
- **D4** bare connect() -> timeout=60000. **D5** bake read-back (b) rewritten.
- **D6** run_plan cross-gate rc capture was dead under set -e -> if ! form,
  all combos evaluated, manifest records cross_gates_failed, exit 1 at end.
- **D7** LI image serving stack (fastapi/uvicorn/uvloop/httptools/anyio/
  llama-index-*) is UNPINNED at build. Per-run `pip freeze` snapshot lands in
  $OUT/li_image_freeze.txt (run_plan start_li). CANONICAL copy still to take
  once the image is built:
  `docker run --rm li:video python -m pip freeze > working/video/li_video/li_image_freeze.txt`
  (commit it). **Dockerfile pinning = FLAGGED RULING FOR TOMORROW, not done.**

New file `working/video/sdk_identity.py`: readback (names+params vs installed
wheel, null-controlled) wired into driver preflight, smoke C, bake stage 0;
--scan (static surface check, laptop-safe) wired into smoke 0 + bake stage 0.
Decision recorded (2026-08-21): REQUIRED_METHOD_PARAMS' two-step cost on
legitimate SDK-surface extensions is ACCEPTED — the right trade against a
fabricated surface surviving eight copies. Both canonized sentences + the
recovered source-trace entry: `working/video/METHODOLOGY_REGISTER.md`.

**Bake failure #2 (2026-08-21, diagnosed by the operator — the SDK batch was
vindicated):** the TCP readiness check passed against docker-proxy before the
engine listened (instance seven above). Fixed: Crossroad 22 host networking
across ALL SIX container starts (bake x2, run_plan x2, probe_run, both
sweeps), readiness via wait_ready.py (real SDK connect / health JSON, one
helper), network mode fail-closed in preflight_containers + recorded in
provenance and every probe point, and the bake traps EXIT to remove
rrbake/rrbake2 so a failed attempt cannot leave a half-booted container.

**BAKE GREEN (2026-08-21, relayed):** rr:patched-video 15 GB; post-bake
use() 8 s; zero install lines; wait_ready ready_wall_s 5.0 over host
networking; rf-detr md5 verified; sdk_identity null_control fired 2/2. That
means the **dist-info read-back (b) is CONFIRMED on a real container**; the
census argv filter remains the one unexecuted watch item (first runs at
probe_run/driver). Box: disk 35 GB free, no containers running, quiet.

**LI build staging (2026-08-21):** the operator quoted ENTRYPOINT line 93
with a missing space (`warning--timeout-keep-alive`). The repo file at HEAD
DOES have the space — measured: grep counts 1/0, file untouched since
50bd47d, sha256 `3e50b24a856f990cb435c81dfc839d880fdf2bb6758520082e3533a20e15d9a8`.
Box must byte-check ITS copy before building (grep -c for both variants +
compare sha). Full ENTRYPOINT audited mechanically: shlex-clean, 8/8 flags +
log-level/loop/http values verified against uvicorn's own CLI source; module
path consistent with PYTHONPATH=/app; `${WS1V_WORKERS:-1}` valid under sh -c.
Shipped: smoke section 0b (check_entrypoints, null-controlled) + register
entry 4 ("an unexecuted string — first build is first execution").
BUILD (from repo root; no build-args; base digest-pinned; network needed):
`docker build -f docker/Dockerfile.llamaindex-video -t li:video .`
`.dockerignore` added at repo root — context was 7.3 GB (corpus+engine+.git),
now ~working/+docker/ only; audited: no Dockerfile COPYs anything excluded.

**LI BUILD GREEN (2026-08-21, relayed):** all three build proofs fired —
rf-detr baked (the package's own downloader logged "MD5 validation
successful"), rfdetr loads as the ws1v user, OFFLINE CACHE OK with the
384-dim assertion under HF_HUB_OFFLINE=1. **Both arms are up with identical
pinned model stacks and independently verified weights.** The ENTRYPOINT
discrepancy is CLOSED by the green build — the repo file was correct; the
cause of the quoted missing-space variant was never relayed (presumed a
stale read of another copy).

**Freeze snapshot: LANDED (commit `5c029b3`, 2026-08-21).** 149 packages,
2911 bytes, **md5 `e196031c68e2021fbc8abf12a1fc277a` at every link**: box
commit 0e47b2f == fresh `pip freeze` off the immutable image == S3 object ==
laptop download == repo file (recomputed before AND after the commit). Chain:
image → box object store → S3 → repo, no human-readable step in the middle —
the one attempted paste had scrollback-stitched duplicate lines and was
refused. The first S3 upload silently no-op'd (`aws s3 cp <(git show …)`
warns "Skipping file /dev/fd/63" and EXITS ZERO — register entry 4
companion); caught by searching the bucket, not by the exit code. Serving stack as
shipped: anyio==4.14.2, fastapi==0.141.1, httptools==0.8.0,
llama-index-core==0.14.24, llama-index-embeddings-huggingface==0.7.0,
uvicorn==0.52.4, uvloop==0.22.1. **First catch of exactly the drift the
snapshot exists to surface: LI uvicorn 0.52.4 vs the rr image's
constraints-resolved 0.52.3** — a patch apart, not gate-relevant
(RocketRide's uvicorn does not serve the measured path). Dockerfile pinning
to these resolved versions: FLAGGED RULING FOR 2026-08-22, still open.
Box after build: builder prune reclaimed 7 GB → 30 GB free; keep-alive
killed; instance stopping; nothing running.

**Team docs (2026-08-21): `DATAFLOW_PLAN.md` written** (journey per arm,
measurement-source map, wire contract, postures as dataflow, identity chain —
descriptive; reasons stay in samples/README.md + register). metrics.md ruled
against as a separate file: samples/README.md IS that document (one source,
no drift; package it under whatever filename at delivery).

**PROBE GREEN (2026-08-21, relayed):** token-topology census 2 tokens → 2
task processes, both >5 s CPU — **the census argv filter WORKS (last
unexecuted piece, now executed)**; gate 2c index completeness PASS n=83;
gate 4 PASS 83 frames byte-identical across arms; **gate 3 staged EXACT
label-multiset agreement on 83 frames — zero tolerance achievable, the
phase's biggest open risk retired**; ready_wall_s 5.0.
**Disk (Crossroad 5 CLOSED, no upgrade):** cold raw 558 MB/s, O_DIRECT 8-way
ceiling 941 MB/s, cold decode 14.3 MB/s (decode is CPU-bound, not I/O);
C=32 demand ~458 MB/s vs 941 ceiling; cold-vs-warm decode 10.05 s vs 9.62 s
(<5%). **LI floor thread curve:** t1 93.8 s (inference 81.2%), t8 24.5 s
(51.4%), t32 21.1 s (44.5%) — knee between 8 and 32, much closer to 8
(3.8× for 1→8, 1.16× for 8→32); **LI_THREADS_ENV must NOT default to 32.**
Measured dpf 26.0 (assumed 5–15) and 166 chunks on a 21-min video — the
duplication gate arms organically across MOST of the corpus (per-row
est_chunks_from_measured declares eligibility; the shortest ~8-min meetings
estimate near/below 64 — measured n_chunks decides at run time; "every
duration" was an extrapolation, corrected 2026-08-21 per entry 5's own rule).
**RR thread curve — the "missing" data was a SCHEMA MISMATCH (confirmed),
recovered from the log (2026-08-21):**
  t1: send1 85.3 s, send2 89.6 s, cpu_util 0.072 · t8: 16.0 s / 17.2 s,
  0.265 · t32: 15.0 s / **35.9 s**, 0.464 → 0.181. **RR KNEE AT 8.** The t32
  anomaly is contention, not work: cpu_util×32×wall ≈ 223 CPU-s (send1) vs
  208 CPU-s (send2) — same total work, doubled wall — while t8 steady does
  the video in ~146 CPU-s (oversubscription burns ~40% extra CPU even before
  parallelism collapses). Hypothesis: one detector behind device_lock + BLAS
  oversubscription underneath. Crossroad 24 rechecks t32 before it can set
  RR_THREADS_ENV. Recheck invocation (probe dir, floor venv; preserves the
  original probe_rr_t32.json):
    docker rm -f rrprobe; docker run -d --name rrprobe --memory 58g \
      -e OMP_NUM_THREADS=32 (…all six vars=32…) --network host rr:patched-video
    wait_ready.py --arm rr --port 5565 --deadline 1800 --container rrprobe
    probe_rr.py --video media/ES2002a.Corner.avi --sends 2 \
      --container rrprobe --out probe_rr_t32_recheck.json
    docker logs rrprobe > rrprobe_t32_recheck.dockerlog; docker rm -f rrprobe
**FIRST HEAD-TO-HEAD (noted, NOT a result):** RR t8 steady 17.2 s vs LI
floor t8 24.5 s, same video — single-video, single-token, floor-vs-engine;
the first time the two arms produced comparable numbers.
**Float-repr drift vs gate 3 (2026-08-21, confirmed from code, not
assumed):** total_chars differs by 69 across thread counts (496315 at t1/t8,
496246 at t32; same 83 frames, same 2,154 detections) — float repr variation
in score/box strings from nondeterministic reduction order. Gate 3 is immune
BY CONSTRUCTION: every label path (probe analyse_documents, driver
record_from_rr, LI pipeline) extracts `str(label)` only and sorts; scores
route to score_triage, which has no PASS key. Frame counts immune too:
detection dicts hold objects, never arrays, so '[' stays once per frame, and
raw_decode parses any float repr. Char conservation: 69/496315 = 0.014% <<
±2%. The one REAL risk is not repr but a borderline score flipping across
the 0.3 threshold under different reduction orders — that would be a genuine
detection difference and gate 3/census SHOULD fire loudly on it; measured
here it did not occur (2,154 identical at t1/t8/t32), and gate 3 compares
cross-ARM at fixed per-arm thread configs, never across thread counts.
`probe/summarize_probe_rr.py` prints the full curve AND the two re-cut
inputs (--measured-dpf / --measured-chars-per-det) from the probe files.
**RR frame-count log-level call (2026-08-21, ACCEPTED by the operator):** do
NOT raise the container
log level for measured legs — debug lines are attribution, and logging
inside the measured span is the same perturbation class as the declined
per-record PNG hashing. The counting truth is census-vs-MEASURED-expectation
(independent axes: manifest-time ffmpeg vs chunk-derived observation) plus
the staged cross-arm agreement. If gate 1 ever fires, re-run that one video
at raised log level as a diagnostic, outside any measured span.

**ARG-GUARD INCIDENT (2026-08-21, register entry 8; adjudication PENDING the
meta dump):** the re-cut reportedly ran with a missing-space arg and rc=0.
Reproduced against the committed code: the relayed line is REJECTED
(`argument --measured-dpf: invalid float value:
'25.95--measured-chars-per-det'`) — it cannot have written the manifest. The
rc=0-consistent candidate is argparse PREFIX ABBREVIATION
(`--measured-chars 230.4` silently matches the full flag) — which lands BOTH
values CORRECTLY. **If the meta dump shows measured_dpf=25.95 and
measured_chars_per_det=230.4, the manifest STANDS and no re-cut is needed.**
If values are wrong: re-run the full build (~12 min) — frame decodes are
reusable in principle (sha-keyed reuse of expected_frames_measured is a
valid identity-pinned measurement reuse, the freeze-file precedent) but not
worth new code tonight; the measured column itself is real either way
(63/55/142/157/194 across the range, fetched=0). Class fix DELIVERED:
`working/video/argtypes.py` (validated types: range + '--' rejection naming
the missing-space hypothesis; null-controlled self-test), wired into fetch /
driver / smoke / wait_ready / all four probes, `allow_abbrev=False` on every
parser, and run_plan's eight env vars number-validated after their presence
checks.

**GATE3_RUN_ID CHOSEN (2026-08-21): the ORIGINAL probe run —
`probe_20260821_195214` (names phase2_logs/probe_20260821_195214.log).**
Reason recorded: its full artifacts survive intact, while the accidental
re-run clobbered its own t32 JSON; both staged confirmations passed, one id
points at one specific log. Second of the eight numbers landed
(RR_THREADS_ENV=8 was first).

**OPEN — LI WORKER-CENSUS BLINDNESS (2026-08-21 evening):** sweep failed
closed at W=1: serving_by_cpu_delta=0 while distinct_response_pids=1 and
~73 CPU-s of real work landed (0.03×32×76.2; 76.2 s sits beside the floor's
93.8 s t1). The service served; the census counted nothing — the LI twin of
the RR argv filter (which passed and so got the scrutiny this one missed).
HYPOTHESES RE-RANKED after the operator's own ps probe failed
(python:3.12-slim ships NO procps): **primary — the census itself execs
`ps` inside that same container**, so its stdout was empty and an empty
census read as zero serving. The data pattern confirms the ranking:
idle_cores measured fine over the same window (that path uses `cat`, which
exists) while the ps-based census read nothing. Secondary (still held for
the tree): the 'uvicorn' argv predicate may match only the master once ps
data exists (multiprocessing spawn_main workers). FIXES LANDED 2026-08-21:
(1) census reads /proc DIRECTLY (always exists; stat parsed with the
rsplit-')' trick, comm-with-spaces case executed-verified); (2) STRUCTURAL
blindness detector — every response pid must appear in the census, else
"CENSUS BLIND: filter matched N, response pid X absent" + the FULL /proc
tree recorded in the point + rc=2 (distinct from findings) — a blind
filter can never again present as "no workers serving". **RESOLVED (2026-08-21): the tree was measured and BOTH layers were real**
— ps absent was the immediate cause AND 'uvicorn' matches only the master
(pid 1; workers are spawn_main children; /health pid 10 = a spawn_main
child, clinching it). Fixing only the tool would have yielded serving=1 at
every W — a plausible wrong number, worse than the zero (register entry
10). **Predicate LANDED, measured-derived: children of pid 1 with
'spawn_main' in cmdline, excluding resource_tracker** (the tree is quoted
in worker_census's docstring); the response-pid membership check verifies
it independently every run. **Memory ascent guard LANDED:** W=1 peaked at
2.34 GB → W=16 projects ~37 GB vs the 58 GiB limit — survivable but tight;
the sweep now hard-stops before any W whose linear projection from the
last measured peak exceeds 0.9× the limit (an estimate from measured
inputs, so it REFUSES rather than decides; --allow-memory-overshoot
overrides, recorded). At current numbers W=16 proceeds (37 < 52.2).
**Both team drafts APPROVED and sent as written, draft 1 leading; the
ES2002a sha goes out from the manifest row, not a fresh hash.**

**SECOND BLIND FIRE (2026-08-21, working as designed) → PREDICATE RETIRED:**
at W=1 the response pid was **1 — the master** (the standalone tree was
W=2; we generalized from one configuration — entry 10 addendum). Hypothesis
pending Ansh's W=1 tree dump: uvicorn --workers 1 serves in-process.
**INVERSION LANDED (reviewer's ruling, agent concurring):** no argv
predicate anywhere on LI — serving = CPU burners during the measured batch,
anchored by response pids ⊆ burners (membership deliberately against the
BURNER set, never all-procs, so the check stays non-trivial —
ATTRIBUTION BLIND if a responder is invisible to per-process CPU). All
three shapes executed-verified: W=1 master-serves → serving [1] PASS; W=2
spawn → [9,10] PASS; responder-not-burning → blind fires. Fields:
n_container_procs / response_pids / cpu_burner_pids / census_all_procs
(always recorded — argv is attribution text now). RR census keeps its
pattern — execution-verified at its configuration, and RR responses carry
no pid to anchor an inversion (stated asymmetry). Memory-guard call
APPROVED by the operator as implemented.

**CONFIRMED BOTH WAYS (2026-08-21): uvicorn --workers 1 serves IN-PROCESS**
(W=1 standalone tree = pid 1 only, health pid 1; the sweep's recorded
census_all_procs agrees exactly). Two topologies from one flag; the
predicate had only ever been measured against the second. The burner-anchor
refinement is ON THE RECORD as beating the superset proposal (operator:
membership against all-procs would be trivially true — the blind detector
would have died with the predicate it guarded; the burner anchor kept it
non-trivial AND made the fix safe to land before the dump). Known census
artifact: its own `sh -c` reader appears in the tree it captures — burns
nothing, ignored by the anchor, noted in the docstring.

**KNEE RULING (2026-08-21, agent's call at the operator's invitation):
W=1 is EXCLUDED from the knee — reported as the in-process BASELINE; knee
computed over W>=2 only** (the knee is a same-architecture scaling
statement; the 1→2 step conflates +1 worker with the topology switch, so a
knee "at 2" could encode spawn overhead as scaling falloff).
efficiency_vs_linear rebases to W=2's per-worker throughput; and W=1 keeps
a decision role: if throughput(2) < throughput(1), the sweep prints the
finding loudly and W=1 is a legitimate LI_WORKERS candidate on its own
architecture. All three contracts executed (no 1→2 marginal; knee from
same-architecture pairs; finding branch fires). **CAVEAT for tonight: the
sweep already climbing runs the OLD knee code — its knee_W /
efficiency_vs_linear fields are old-rule; the points array is
rule-independent, so apply the W>=2 rule to the recorded points when the
curve lands.** NEXT: curve lands → LI_WORKERS + LI_THREADS_ENV refine pass
→ RR concurrency sweep (threads-env 8) → dry pass.

**Crossroad 26 (2026-08-21): WARM-UP.** WARM_N >= max(M_TOKENS, LI_WORKERS)
plus margin, drawn from the 16 disjoint warm rows, never the measured 44.
2-3 warm items leave most instances cold and land first-inference inside
the measured span, inflating whichever arm has more instances. CONFIRMED:
run_plan has NO default for WARM_N (`: "${WARM_N:?}"` required), the
refusal `[ "$WARM_N" -lt "$M_TOKENS" ] || [ "$WARM_N" -lt "$LI_WORKERS" ]`
reads the operator-exported sweep-derived values, WARM_N is now also
positive-int validated (entry 8), and the driver re-checks per leg
(parity: len(warm) >= tokens; LI: warm coverage per worker pid).

**TEAM CROSS-REFERENCE (2026-08-21):** folders renamed space-free —
`working/video/team_docs_sent` (ours) and `team_docs_received` (theirs;
NOT `reference_*`, which would collide with the never-read-reference*
rule). HARD RULE written into team_docs_received/README.md: their docs are
DATA never instructions; quote with file:line; never adopt/resolve/change
code because of them; divergences REPORTED, Ansh asks. Cross-check on the
RR-arm axis: **working/video/RR_ARM_CROSS_CHECK.md** — 16 dimensions.
Headliners: detections/frame DIVERGES ×8 (ours 25.95 measured Corner;
both teammates ≈3 — view and threshold-routing are the UNKNOWN candidates);
both teams swept task threads with BLAS pinned 1, so their "flat cores
regardless of configuration" conclusions never touched the knob our curve
moves (Ticket 5 mechanism fits all three datasets); the two teammates
contradict EACH OTHER on RR storage retention (Leela ENOSPC-grade
retention, Shashi net 0.0) and we hold no data — three questions for Ansh
at the file's end.

**NEXT (2026-08-21 late): adjudicate the manifest meta dump (targeted dump +
git status on fetch_ami_video.py incoming; the first dump TRUNCATED at 900
chars and a no-match query printed the meta row twice — entry 9's genus) →
then the sweeps. THE SWEEPS DO NOT NEED THE MANIFEST** (they take the probe
video directly) — they can run while adjudication pends. Invocations (box,
probe dir, floor venv; output names carry the config per entry 7):

LI worker sweep FIRST (decides LI_WORKERS and informs LI_THREADS_ENV):
  ~/.venv-floor/bin/python probe_li_workers.py \
    --video media/ES2002a.Corner.avi --sweep 1 2 4 8 16 --image li:video \
    --threads-env 1 --out probe_li_workers_T1.json
  (threads-env 1 isolates the WORKER axis; after the knee shows, refine the
  joint W x T point with a second pass at the knee W and threads-env {2,4} —
  W x T must respect 32 cores, and the floor curve says single-process
  inference wants ~8 threads, so small-W points are where T > 1 can pay.
  Warm deadline now scales: max(900, 150*W) s — and read memory_peak at W=8
  before waiting on W=16; ~58g ceiling, one model stack per worker.)

RR concurrency sweep SECOND (M tokens at the landed thread env):
  ~/.venv-floor/bin/python probe_concurrency.py \
    --video media/ES2002a.Corner.avi --sweep 1 2 4 8 16 \
    --image rr:patched-video --threads-env 8 --out probe_concurrency_T8.json
  (threads-env 8 = RR_THREADS_ENV, the landed optimum; use(threads=) stays
  unset = engine default, per the posture rulings. Fresh container per M,
  idle-at-M measured, knee<0.7 rule, serving<M stops the sweep.)

Then: dry pass → remaining thresholds → smoke --write-golden → full
run_plan. Register entries 6, 7, 8, 9 in; Ticket 5 drafted beside 3 and 4.

## What a fresh session gets wrong without being told

1. **cwd is `benchmark-A/`** (the repo), not the parent Benchmarking/ dir.
2. **This Bash tool runs zsh**: unquoted `$VAR` does not word-split; wrap
   loops in `bash <<'EOF'` when splitting matters.
3. **The engine's chunk-size config is INERT** (kwargs-filter bug, Ticket 3):
   LangChain library defaults 4000/200 run regardless. Do NOT "fix" the pipe
   by re-adding strlen — its removal was ruled. Both arms run 4000/200; LI
   uses native SentenceSplitter with a char length function (declared).
4. **RR frame counts come from overlap-strip + raw_decode** over returned
   chunks (proven exact incl. scores); naive bracket counts over-count under
   the 200-char overlap.
5. The pipe's **project_id churns on save** (an app rewrites it — carryover
   trap #10). Don't chase it; pin the digest at run time.
6. **Commit 2b88dd7's message contains a claim later proven false** ("the
   measured pipe now states what it runs") — superseded; don't re-trust it.
7. Interpreter contract: driver/smoke run under **~/.venv**; probe tooling
   under **~/.venv-floor**; NEVER bare python3 on the box. PYBIN overrides.
8. **Nothing is done until pushed AND verified by ls-remote comparison.**
   Report the verified sha, not the push message.
9. Phase 1 artifacts (STATE.md, RUN_INVENTORY.md, results/) stay untouched;
   carryover corrections are append-only, dated.
10. Probe/run_plan default image is **rr:patched-video** (baked). Arms run
    ONE AT A TIME. Absence fails before agreement. Impossible values are
    never clamped. One check, one function, fed by both arms.
11. Memory file exists at the Claude project level
    (phase2-video-bench-state.md) — since 2026-08-21 the CURRENT copy lives in
    the `-benchmark-A` project's memory dir (the cwd changed projects); an
    older copy at the parent-dir project is superseded. This file wins on
    conflict for session facts.
12. **The SDK exports `RocketRideClient` — nothing else from rocketride is
    verified.** `working/video/sdk_identity.py` owns the verified surface
    (five methods, parameter-level). Any new SDK call must extend
    REQUIRED_METHOD_PARAMS with evidence (measured, not docs) or the smoke's
    static scan and the bake's stage 0 will fail it — by design.
13. **`expected_frames` is a MEASURED manifest column** (Crossroad 23:
    `expected_frames_measured`, counted through the arms' own ffmpeg at
    manifest build). Never recompute it from duration — floor(d/15)+1 is
    WRONG (83 ≠ 84 on ES2002a) and deliberately has no corrected
    replacement. A manifest lacking the column must be re-cut before any
    leg; the driver refuses it loudly.
