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
- **Crossroad 21: NOT IN THIS SESSION'S TRANSCRIPT.** The operator's final
  message implies it exists ("Crossroads 15-21"). ASK; do not invent it.
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

Instances so far: (1) push surface (commits reported done but never pushed);
(2) interpreter (bare python3 in scripts; box python3=3.10 no psutil);
(3) venv creator (python3 -m venv assumed; ensurepip stripped);
(4) interpreter version ("both arms are 3.12" argued from prose — engine
embeds its own CPython, resolved from the pinned binary);
(5) checker's own shell (this laptop's Bash tool runs **zsh — unquoted $VAR
does NOT word-split**; bit the ten-minute sweep 3x);
(6) **SDK import surface (RESOLVED 2026-08-22, the sharpest yet):** every
video-tree file imported `RocketRide`, a class in NO generation of the SDK —
eight sites, six files, perfectly self-consistent, none executed. The bake
died on the first import ever attempted. Measured surface: `RocketRideClient`
(Phase 1's 40+ sites + the installed wheel's inspect.signature paste). The
lesson beyond the fix: N self-consistent copies of one memory are ONE
observation — `working/video/sdk_identity.py` now owns the verified surface
(names + PARAMETERS, null-controlled) and its `--scan` breaks the pattern
statically before first execution. The wheel's use() carries `team_id` which
the dev checkout lacks — checkout != wheel, proven.

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
  2026-08-22 as `8ea9be50…` (prefix; the sidecar at
  `working/video/probe/media/black_60s_352x288.avi.sha256.txt` ON THE BOX
  remains the full authority). ffmpeg 7.0.2-static. Disk: 48 G free.
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

## RESOLVED (2026-08-22): the bake failure — and the audit it opened

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

**NEXT: the bake retry is the FIRST EXECUTION of any of this**, then LI image
build (+ canonical freeze), probe_run.sh, dry pass, sweeps. Crossroad 21 is
STILL unrelayed — ASK, do not invent.

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
    (phase2-video-bench-state.md) — since 2026-08-22 the CURRENT copy lives in
    the `-benchmark-A` project's memory dir (the cwd changed projects); an
    older copy at the parent-dir project is superseded. This file wins on
    conflict for session facts.
12. **The SDK exports `RocketRideClient` — nothing else from rocketride is
    verified.** `working/video/sdk_identity.py` owns the verified surface
    (five methods, parameter-level). Any new SDK call must extend
    REQUIRED_METHOD_PARAMS with evidence (measured, not docs) or the smoke's
    static scan and the bake's stage 0 will fail it — by design.
