# FILMS-500 — the full sequence (scope-ruled 2026-09-03)

Scope (ruled): **RR M16xT2 + LI N16xT2 only, 498 measured films, two
blast passes each; RR default SKIPPED** (~19 h/pass to re-answer a
question answered twice at n=2 with 0.77% spreads — the out-of-box
finding ships from films-35 and AMI-168 at their own N, N stated
wherever it appears; her runbook defines no default-RocketRide cell).
**SEQ_N=5 per cell, explicitly NOT scaled** (gate 8, uncontended
latency, and the speedup divisor do not scale with N — baked with the
ruling comment in the plan). **$/1k footage-hour is PUBLISHED as a
results row** (already computed in every export; ruling recorded in the
run manifest). **Cross-gate expectation stated before the run**: gate 3
FAILS on the majority — every >560px film is expected to diverge
(Ruling U); not a stop condition; the finding surface is the
**partition check** (violation in either direction = exit 2, loud,
"THIS CHANGES RULING U").

Every box action through `working/harness/box.sh` (proven; transcript =
evidence surface). Scripts committed, self-printed sha256.

**KEEPALIVE RULE (added 2026-09-04 after the fetch died to the box's
idle watchdog — the failure Leela's runbook names and v1 omitted)**:
any near-idle long step carries a BOUNDED, SELF-TERMINATING keepalive
(N × `timeout <s> md5sum /dev/zero`, no respawn parent — the unbounded
respawning form contaminated the 18-Aug measured runs and is banned).
Who needs one, RE-RULED 2026-09-04 with the new measurement (the plan's
step-0 full sha pass — 263 GB single-threaded, low CPU — ran ≥7 h
unfinished and the watchdog killed the box; the earlier fetch-only
ruling's evidence covered the 35-campaign profile, not 500-scale
step 0):
- **fetch (step 1): YES** — v2 carries a 7200 s bounded keepalive + 12
  parallel workers.
- **step 0 / staging 0a corpus verify: the tax is DELETED, not
  kept-alive** — step 0 defaults to FAST (stamp + full stat census +
  5-film sha spot, seconds; `FULL_VERIFY=1` for the parallel full
  pass, CPU-heavy so self-protecting); staging 0a re-runs go size-only
  when the stamp is present (the stamp was written after a completed
  full verify) and only a FIRST-TIME stamp pays the full pass.
- **manifest decode (step 2): NO** — P=12 ffmpeg pegs 12 cores.
- **staging legs and campaign legs: NO** — detect keeps lanes busy,
  rr's idle burn floors CPU at 4.66 cores when up, and the
  35-campaign's 9.6 h overnight never tripped the watchdog (measured).
- **mirror: NO** — rides a busy box; exits on its sentinel.
No remaining step has a low-CPU stretch long enough to trip the
watchdog; the keepalive stays fetch-only because everything else
either burns CPU or now finishes in seconds.

| # | step | how | mark |
|---|---|---|---|
| 0 | Box up + repo current | `box.sh run --start 'git -C ~/parity-bench-video pull --ff-only && git -C ~/parity-bench-video rev-parse HEAD'` | **STOP** — HEAD must be this commit |
| 1 | Fetch the 500 (~252 GB; our 35 reused by hardlink; every file sha-verified against the frozen manifest bd0c915e) | `box.sh launch fetch500 'bash ~/parity-bench-video/working/video/probe/fetch_films500.sh'`; watch `box.sh tail fetch500` | safe-to-chain into 2 only after `verified=N/N … MISMATCHED=0`; **WALK-AWAY** (hours, detached) |
| 2 | Cut the 500 manifest (frames through pinned ffmpeg `e7e7fb30`, fps=1/15, P=12; width/height recorded — the partition check's basis and, for the first time, a held artifact the corpus-wide >560px fraction derives from; warm split = her last-2 convention, 498+2 matching her measured set; NULL CONTROL: the 35 knowns must reproduce the committed subset manifest or REFUSE) | `box.sh launch manifest500 'bash ~/parity-bench-video/working/video/probe/build_films500_manifest.sh'`; watch `box.sh tail manifest500` | **STOP** — read census (n=500 = 498+2, total_frames, footage h, >560px count) + the null-control line; **WALK-AWAY** (~0.5–2.5 h, self-calibrating) |
| 3 | Land the manifest (box commits `films500_video_manifest.jsonl` + bundles; laptop lands, entry 26) | box commit via `box.sh run`, bundle, laptop fetch/verify/push | **STOP** — laptop re-reads the census from the landed file |
| 4 | Staging (arming spans 560px: Leagues ≤560 control judged by the proven deriver; House >560 divergence EXPECTED and recorded; LIVENESS_MIN = Ruling-R formula over BOTH; golden REUSED in compare mode) | `box.sh launch stage500 'bash ~/parity-bench-video/working/video/probe/run_films500_staging.sh'`; watch `box.sh tail stage500` | **STOP** — read arming.json (armed, span basis, control verdict, diverger census, liveness_min); a NON-diverging House is itself a flag to Ansh; ~45–75 min |
| 5 | Preflight-only pass of the plan (~15 min: FAST step 0 in seconds + wiring/read-backs, nothing measured). MUST EXIT before step 6 — the plan-level lock refuses a second live plan, so an overlap is impossible rather than merely forbidden | `box.sh launch preflight500 'cd ~/parity-bench-video && PREFLIGHT_ONLY=1 bash working/video/run_plan_films500.sh'`; `box.sh tail preflight500` until `PREFLIGHT_ONLY COMPLETE` | **STOP** — read the preflight lines; confirm the process EXITED (`box.sh ps`) |
| 6 | THE CAMPAIGN — the mirror is SELF-LAUNCHED by the plan against its own out dir (no copy step, no placeholder; it stops on the MIRROR_STOP sentinel the plan touches at completion, and if the plan dies mid-run the mirror keeps syncing — that is the point) | `box.sh launch films500 'cd ~/parity-bench-video && bash working/video/run_plan_films500.sh'` | **WALK-AWAY** (~20–22 h; live sync every 300 s to `ansh/films500-live-<stamp>/`); periodic `box.sh tail films500` |
| 7 | Land + read | `box.sh run 'touch <OUT>/MIRROR_STOP'`; box commits OUT + bundles (entry-26 STOP-AND-LAND); laptop lands; partition_check.json is the first read | **STOP** — partition verdict first, then throughput, then the $/1k row |

**Projected wall (from measured films-35 rates; ~161,940 frames at
1/15 over 674.75 h; manifest measures the exact figure):**

| cell | rate basis (measured, films-35) | per pass | ×2 passes |
|---|---|---|---|
| LI N16xT2 blast | 10.134 f/s mean | ~4.44 h | ~8.9 h |
| RR M16xT2 blast | 9.512 f/s mean | ~4.73 h | ~9.5 h |
| sequential 5/cell + warm waves + staging + cross | — | — | ~2.0 h |
| **total** | | | **~20–22 h** |

Assumptions, named: the 35-film per-frame rates transfer to the 500 mix
(the 35 span her strata by construction, but the 500 skews longer
films — rates at 16 lanes are frames-normalized, so the first-order
effect cancels; ±20% envelope); warm-wave and cross overhead scaled
from the 35-campaign's measured excess. The skipped default cell would
have added ~19.1 h per pass (161,940 / 2.35 f/s) — the ruling's
arithmetic, confirmed. LI per-request ceiling `LI_HTTP_TIMEOUT_S=43200`
already landed (sizing in the driver constant's comment).

**Sizing facts** (Leela's committed films500 per_doc @3967d9f4; our
landed films-35 records; box reads via the wrapper): corpus 281.4 GB /
674.75 h; longest film 11,314 s; largest file 2.19 GB; her max wall
2,332 s at c32; box disk 839 GB free pre-fetch (~587 GB after; C=16
spool worst ~60 GB); her LG OOM class closed on our arm by mechanism
(frames-on-disk k=1; streamed uploads; see FILMS500 prep round in the
handoff).
