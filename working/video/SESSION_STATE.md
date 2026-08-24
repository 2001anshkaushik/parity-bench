# SESSION STATE — last written 2026-08-23 (after the step-0 death; relaunch sequence at the top)
# (the 2026-08-23 briefing immediately below supersedes every block after it)

**Audience: the post-compaction session, holding only this repo.** This is a
briefing, not a summary. Read PHASE1_CARRYOVER.md first (its corrections
appendix included), then this. Verify anything here marked UNRELAYED before
using it.

---

## ▶▶ COMPACTION BRIEFING — 2026-08-23, PHASE B FOR ami_full. THIS BLOCK WINS over everything below it, including the 2026-08-21 briefing.

**LAUNCH 3 ALSO FAILED at the LI warm-up (5/8, pids 10/11/13 unserved, 32 sends
in 2 waves). Two hypotheses were killed from the code: the post paths are
IDENTICAL (both urllib, fresh TCP connection per post — measured: 14 requests,
14 connections, `Connection: close`), and run_plan has ALWAYS created fresh
containers (`docker rm -f` then `docker run -d`, both arms). What differs is
WHAT IS COUNTED: `probe_li_workers` headlines `serving_by_cpu_delta` (CPU
burners) and reports `distinct_response_pids` alongside, documenting that the
latter is expected to be < W; the driver's gate counts ONLY response pids. Run
`working/video/probe/which_8_of_8.sh` on the box to settle which number the
probe's 8/8 was — this is the pivotal open question (register entry 17).
Mechanism: `/process_video` is async + `anyio.to_thread.run_sync`, so ONE
worker can accept unbounded concurrent connections; client concurrency raises
the odds of distribution but cannot compel it.**

**WHERE WE ARE (updated 2026-08-23, third launch pending):** Phase B COMPLETE
— gate 3 armed on `probe_20260823_122005`, golden identical at 13 chunks,
170/170 sha (all relayed). **Launch 1 died at step 0** (Corner-era corpus-dir
default + a verify that fetched — register entry 15, FIXED, manifest stamped on
the box). **Launch 2 died at leg 2 of 9, ~45 min in** — LI warm-up reached
6/8 worker pids in 18 sends: the top-up loop sent ONE post at a time and kernel
accept does not distribute low-concurrency traffic (register entry 16,
**Crossroad 40**: warm-up now goes CONCURRENT in waves of max(2 x workers, leg
concurrency), coverage rule UNCHANGED, per-send ledger written before any
verdict, RR arithmetic untouched). **Leg 1 of launch 2 is BANKED**: llamaindex
sequential, 6 records / 5 offered, 0 errors, 2.743 f/s (33.66x realtime), CPU
9.1%, gates PASS 7 · NOT RUN 1 · FAIL 0, collector ok — but the campaign
RESTARTS FROM SCRATCH, so it will be re-measured, not reused. Relaunch = pull +
the same launch line (stamp already done); see THE LAUNCH SEQUENCE below. The
Corner campaign is BANKED.

### B1-B6, done, with their values
| step | value |
|---|---|
| B1 dpf / chars-per-det | **7.77 detections/frame, 222.2 chars/detection** — pooled over 3 Closeup1 videos, 342 frames. (Corner was 25.95 / 230.4; the ~3.3x density drop is the framing change, as predicted.) |
| B2 LIVENESS_MIN | **0.5** — minimum non-empty frame fraction measured **1.000 over n=6**; 0.5 sits far below anything observed and the black fixture still fails it |
| B3 manifest | **170 rows, 168 measured + 2 warm**, HER order from `team_docs_received/leela_ami_full.txt`, **23,372 total frames** |
| B4 verify | **170/170 sha256 match** |
| B5 LI budget line (Closeup1) | 4x8 **0.0989** · 8x4 **0.1473** · 16x2 **0.0913 serving 15/16** -> **LI_WORKERS=8, LI_THREADS_ENV=4** |
| B6 RR spot-check | M=16/T=2 **0.1152**, idle **5.323** cores (Corner read 5.24 — consistent) -> **M_TOKENS=16, RR_THREADS_ENV=2** |
| WARM_N | **2** — the size of the warm SET, not the number of warm SENDS. `run_plan.sh:260-265` REFUSES anything that does not equal the manifest's warm row count. The driver covers 16 tokens by RE-SENDING those 2 rows (Crossroad 32): 2 first-batch + 14 top-ups, budget 32, coverage assert still fails closed. |

### THE B7 BUG — FIVE SITES, ALL FIXED. The BOX needs a pull.
Do NOT re-implement these; verify the box has the fix commit first.
* **The defect, one sentence:** `sorted(glob('probe_li_floor_t*.json'))[-1]` is
  LEXICOGRAPHIC, so **t8 beats t32/t2/t1**, and the loaded file was never checked
  for WHICH VIDEO produced it. Floor jsons carried no `video` field at all before
  2026-08-23, so nothing could catch it: 93 fresh ES2009a hashes were compared
  against 83 stale Corner ones and a correct decode was reported as a gate-4
  FAILURE.
* **It was at FIVE sites, patched three times at whichever site had just been
  seen failing.** `probe_frame_identity.py` (early identity, `4c659541`);
  `probe_run.sh` gate-3 staging (`78d630f0`); then still live until 2026-08-23:
  `probe_run.sh` gate 4, `probe_run.sh` frame-count agreement (whose rc is the
  probe's exit code), and `summarize_probe_rr.py` (which emits the
  `--measured-dpf` / `--measured-chars-per-det` that RE-CUT THE MANIFEST).
* **CORRECTION to `4c659541`'s message, which this file previously repeated:** it
  claims the post-matrix gate-4 compare "did not exist". It DID — since
  `01b82de`, broken — and `4c659541` added a SECOND one beside it. The twin is
  what printed the failure the operator saw. The duplicate is now deleted; there
  is ONE gate-4 comparator.
* **The fix is one copy:** `working/video/probe/artifact_identity.py` holds the
  only selector (`select_by_video` / `select_all_by_video` /
  `require_same_video`); every site calls it. Register entry 14.
* **New verdict vocabulary, and it changes how a failure reads:** 0 PASS,
  1 REAL DIFFERENCE, 2 CANNOT COMPARE. A comparator that cannot prove both sides
  read the same input reports CANNOT COMPARE — an EVIDENCE fault, never "decode
  paths differ". `real_difference()` raises unless handed the `video_sha16`
  proven on both sides.
* **Verification (laptop, no box needed):**
      python3 working/video/probe/test_artifact_identity_sites.py   # 21 call-site controls
      python3 working/video/probe/artifact_identity.py --self-test  # 21 selector controls
  Both must print PASS. They reproduce the exact stale-Corner layout and
  null-control every verdict.
* `GATE3_RUN_ID=probe_20260823_110344` is **VOID** — it asserts agreement on
  ami_full that was measured on Corner.
* Examined and SOUND, do not "fix": `gate3_triage.py` pairs records by video NAME
  with an explicit missing-arm branch; `resultio.latest()` sorts a fixed-width UTC
  stamp, so lexicographic IS chronological there.

### B7 and B8 — DONE (relayed 2026-08-23)
* **B7:** gate 3 armed on **`GATE3_RUN_ID=probe_20260823_122005`** — ES2009a, 93
  frames, both arms confirmed on the same sha, EXACT agreement. (The earlier
  `probe_20260823_110344` stays VOID.) NOTE: the re-run line this file carried
  said `corpus/ami/video/ES2009a.avi`; the box's identity line read
  `.../corpus/ami/full/ES2009a.avi`. **The ami_full corpus is at
  `corpus/ami/full`** (relayed) — `corpus/ami/video` is the Corner-era location
  and is what killed step 0. ASK if the absolute prefix matters.
* **B8:** golden re-written for ami_full; "golden compared identical at 13
  chunks"; smoke PASS 0 failures.

### CORRECTIONS THAT MUST SURVIVE — about a teammate's work, nearly published wrong
1. **Her detect threshold is TOP-LEVEL, not nested.**
   `{"profile":"rfdetr","threshold":0.3}`. It IS silently discarded
   (`ai/common/config.py:196` reads only `connConfig[profile]`). The EFFECT is
   identical **only because** the rfdetr profile carries its own
   `"threshold": 0.3` (`nodes/detect/services.json:40`). Correct statement:
   *different shape, identical effective sensitivity, both 0.3.* Never write
   "correctly nested on both sides".
2. **There is NO OpenCV anywhere.** All three arms shell out to ffmpeg — engine
   `ai/common/avi/reader.py:5,229`, our LI arm `li_video/pipeline.py:104-105`,
   her LangGraph arm `arms/langgraph/workload/frames.py:21-26`. **The
   frame-extraction asymmetry does not exist and must NOT be published** — an
   invented self-penalty is as wrong as an invented advantage.
3. **The four invalidating checks all came back SAME:** engine 3.3.1 (both pin
   extracted-ELF sha `95768e26…9747`), duplication patch applied on both arms,
   pipeline graph identical node-for-node **including input lanes**, threshold
   effectively 0.3 both. Full table: `RR_ARM_CODE_DIFF.md` §9.

### THE CORNER CAMPAIGN IS BANKED — `mainrun_20260823T034243Z`
9/9 legs, all leg gates PASS, 0 errors. Findings that go to Monday:
* **Span vs steady window REVERSE the winner.** LI **8.952** span / **8.491**
  window; RR-parity **9.826** / **7.995**. Span absorbs the drain tail. Leela
  reports span only — a BASIS difference to name up front, not a correction.
* **RR default is 4.1x slower than RR parity.**
* **LI rep spread is 5.4% on span and 21% on the steady window**; RR passes agree
  to 0.3-2.3%. A cross-arm difference under ~5% on the LI arm is not
  distinguishable from repetition noise.
* Cross-configuration determinism: RR default vs parity char totals **568 chars
  apart over 32.5M (0.0017%) at different thread counts**.
* `char_conservation` 0.0208 vs tol 0.02 is the SPLITTER (Recursive vs
  SentenceSplitter, both 4000/200, decision 3) — real, explained, tolerance NOT
  widened; Crossroad 38 band `[0.97374, 0.98963]`, centred, calibrated on this run.
* Gate 3's three diverging frames were DOWNGRADED IN WRITING by Ansh as
  boundary flapping (Crossroad 39 now excludes and COUNTS them).

### THE LAUNCH SEQUENCE (three steps; the first two are new on 2026-08-23)
**Step 1 — pull.** The step-0 fix lives in `fetch_ami_video.py`, `run_plan.sh`,
`driver_video.py`, `smoke_video.py` and the new `corpus_locator.py`. Without the
pull, the relaunch dies the same way.

**Step 2 — stamp the manifest ONCE** — **DONE on the box** (launch 2 passed
step 0 with `DONE verified=170/170`); re-running it is harmless and idempotent (a full sha256 verify — tens of seconds,
the same work as step 0 — that then records the directory in the manifest
meta so run_plan and every tool derive it; meta line only, data rows asserted
byte-identical, old/new manifest sha printed):
    cd ~/parity-bench-video &&     ~/.venv/bin/python working/video/fetch_ami_video.py --stamp-corpus-dir --corpus-dir "$PWD/corpus/ami/full"
Read back: `STAMPED corpus_dir=/.../corpus/ami/full into ami_video_manifest.jsonl
(meta line only; 170 data rows byte-identical)` then `DONE verified=170/170`.
If it prints `NOT DONE` the directory is not where this file says — ASK, do not
guess a path.

**Step 3 — launch** (unchanged numbers; `CORPUS_DIR` is NOT needed — it derives
from the stamp — but may be passed and then MUST agree with it):
    cd ~/parity-bench-video && mkdir -p working/video/results &&     M_TOKENS=16 RR_THREADS_ENV=2 LI_WORKERS=8 LI_THREADS_ENV=4     WARM_N=2 BLAST_C=16 DEFAULT_N=168 PASSES=2 LIVENESS_MIN=0.5     GATE3_RUN_ID=probe_20260823_122005     nohup bash working/video/run_plan.sh > working/video/results/console_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
**~8.5 h**, finishing overnight. First lines to read back, in order:
  1. `corpus: manifest=working/video/ami_video_manifest.jsonl corpus_dir=/.../corpus/ami/full [manifest meta]`
     — if this line is absent the box has not pulled; if it says `NOT DONE`, step 2 was skipped.
  2. step 0: `MANIFEST MODE — VERIFY (sha256; read-only, never fetches): 170 files ... corpus_dir=... [manifest meta]`
     then `DONE verified=170/170`. **Any `fetch [` line = the old code is running. Stop it.**
  3. smoke: `corpus_dir=... [manifest meta]` as its first line; quiet-box `basis` must
     read `instantaneous`; pins line `rr expected 'unset': declared {}` with `{'rr': 16, 'li': 4}`.
  4. the first `AT A GLANCE`.

### ASK — DO NOT INVENT (held by this session, not by the repo)
* **B7/B8 values are RELAYED:** `GATE3_RUN_ID=probe_20260823_122005`, golden 13
  chunks, 170/170 sha. The repo holds none of the probe outputs.
* **Whether the box has pulled the step-0 fix** (entry 15) and whether the stamp
  (launch step 2) has been run — the relaunch is impossible without both.
* **The absolute path of the ami_full corpus** on the box: `corpus/ami/full`
  under the video worktree is relayed; confirm before quoting it anywhere else.
* The exact B1 probe output filenames on the box (unrelayed); the values above
  are relayed.
* Whether Leela was told anything about her threshold shape or the RT-DETR
  fallback — drafted messages live in `team_docs_sent/MESSAGES_2026-08-21.md`;
  whether any were sent, and any replies, is UNKNOWN here.
* Operator rulings are recorded in paraphrase throughout; ASK if verbatim
  wording matters.

---

## ▶ [SUPERSEDED by the 2026-08-23 briefing above] COMPACTION BRIEFING — state as of late 2026-08-21
*(Still accurate for the Corner-corpus era and the rulings it records; where it
conflicts with the 2026-08-23 block — corpus, numbers, WARM_N, gate ids — the
2026-08-23 block is current.)*

**▶▶ TWO CHECKOUTS ON THE BOX — GET THIS RIGHT OR EVERY COMMAND MISSES:**
  `~/parity-bench-video`  ← THE VIDEO WORKTREE. Every campaign/dry-pass/probe
                             command runs here. Branch video-bench.
  `~/parity-bench`        ← Phase 1's checkout. Holds the provisioned
                             `corpus/govdocs1/pdfs` (10k PDFs, gitignored, never
                             from git) that the duplication fixture needs.
                             Symlinked into the video worktree 2026-08-22.
Commands in this file that say `~/parity-bench` mean Phase 1's checkout ON
PURPOSE; everything else is `~/parity-bench-video`.

**▶▶ THE NINE NUMBERS (Crossroads 31/32/34, 2026-08-22):**
  M_TOKENS=16 · RR_THREADS_ENV=2 (PARITY posture; default posture UNSET) ·
  LI_WORKERS=8 · **LI_THREADS_ENV=4** · WARM_N=16 · BLAST_C=16 ·
  GATE3_RUN_ID=probe_20260821_195214 · DEFAULT_N=44 · PASSES=2 (ruled)

**THE LI BUDGET LINE (2026-08-22, ppw=4, relayed) — LI_THREADS_ENV moved 1 → 4:**
  W=4  × T=8  (32)  0.1123 videos/s  cpu 0.612
  W=8  × T=4  (32)  **0.1340**       cpu 0.723   ← knee: the curve TURNS OVER
  W=16 × T=2  (32)  0.1187           cpu 0.474
  W=8  × T=1        0.0871           cpu 0.219   ← what we were about to run
**T=1 was leaving 54% on the table at the same worker count.** Unlike RR's
budget line (monotonic in tokens to M=32), LI's has a real interior maximum.
LI_WORKERS=8 confirmed. (Note: this W=8/T=1 point reads 0.0871; the earlier
matched-load relay recorded 0.0882 at the same cpu 0.219 — a 1.3% relay
discrepancy that moves no decision. The box JSON is authoritative.)
**READ-BACK CAVEAT — the number is MEASURED but its configuration is
UNVERIFIED.** `probe_li_workers` set the six env vars on the container and
recorded NOTHING about what the workers got, so the three budget JSONs cannot
prove T=4 landed in all 8 workers (`wait_li_ready` returned only warm_workers
and one arbitrary pid). **Same gap found in `probe_concurrency`, which set
M_TOKENS=16 AND the parity T=2.** Both FIXED as a class (register entry 12
addendum): `li_worker_thread_readback()` (every LI worker's in-process torch
count) and `probe_rr.verify_task_thread_env()` (every RR task process's own
`/proc/<pid>/environ`), each REFUSING the point rather than recording it at an
unknown configuration, each null-controlled. Confirm with the 2-minute check
in the box-command block before the number is set.

**IF THE LI READ-BACK RETURNS MISMATCH — cost, and what else is suspect:**
- **Re-running the three budget points ≈ 18–20 min** (batch walls implied by
  the relayed throughputs at ppw=4: 16/0.1123 = 143 s, 32/0.1340 = 239 s,
  64/0.1187 = 539 s ≈ 15.3 min, plus three container starts + warms + the new
  read-backs). **But a re-run is worthless until the mechanism is fixed** — the
  same flags through the same path reproduce the same failure, so the first
  cost is DIAGNOSIS (does the service sanitise its env? does torch import
  before the env is set? does uvicorn spawn workers with a stripped
  environment?), and the 20 minutes is only the re-measurement after it.
- **Is the earlier W=8/T=1 point suspect too? Formally yes — same probe, same
  gap. But the records already in hand argue strongly that the flags DO land**
  (entry 11's method — check the benign explanation against points already
  held). At the SAME W=8, the declared T=1 run measured cpu_util 0.219 (7.0 of
  32 cores ≈ the 8 declared threads) and the declared T=4 run measured 0.723
  (23.1 cores ≈ 32 declared threads): **3.3× the CPU and 54% more throughput
  from changing nothing but the declared thread env.** If the flags never
  reached the workers, both runs would have been the same configuration and
  would have measured the same. They did not. Also: had T=1 failed to land,
  8 workers × torch's default (~16 on this host) = 128 threads on 32 cores
  would have pegged utilisation near 1.0, not 0.219. The read-back still runs —
  it converts a strong inference into proof for 2 minutes of box time.

**[SUPERSEDED 2026-08-23 — the LI variance floor is NOT 1.3%. The completed
campaign measured pass-1 vs pass-2 on the LI arm at 5.4% on span and 21% on the
steady window (8.491 vs 7.025 frames/s); RR passes agree to 0.3-2.3%. USE:
a cross-arm difference under ~5% on the LI arm is not distinguishable from
repetition noise on this evidence, and the steady window on that arm is far
noisier than the span. The two probe reps below remain a real datum; they were
never a variance FLOOR for a full leg.]**
**RESOLVED 2026-08-22 — TWO REPS, NOT A SLIP.** The enumeration found the W=8
T=1 ppw=4 point in TWO files: `probe_li_workers_T1_ppw4.json` **0.0871** and
`probe_li_workers_..._w16.json` **0.0882**, both at cpu_util 0.219. These are
**two independent repetitions 1.3% apart** — record them as a rep spread, never
as one number with an erratum. **This is the only rep-spread datum the LI arm
has**, so it is also the campaign's rough variance floor: a cross-arm
difference of the same order as 1.3% is not distinguishable from repetition
noise on this evidence. (PASSES=2 will give the campaign its own spread; until
then this is what we have, from n=2.)
[HISTORY — the question that produced it:]
**THE 0.0871 vs 0.0882 DISCREPANCY — name ONE number before the campaign.**
Both are relays of the SAME quantity: the W=8 point at threads_env=1, ppw=4,
`throughput_videos_per_s` — recorded here as 0.0882 (compaction briefing) and
relayed as 0.0871 twice (once before that briefing, once in the budget-line
message as the T=1 comparison row). Candidate files: the matched-load recheck
`probe_li_workers_T1_ppw4.json`, and — UNKNOWN, filename never relayed — the
W=16 extension run, which may ALSO carry a W=8 point. Resolve by listing every
point in every file (box, probe dir):
  cd ~/parity-bench-video/working/video/probe && for f in probe_li_workers*.json; do
    python3 - "$f" <<'PYEOF'
  import json, sys
  d = json.load(open(sys.argv[1]))
  for p in d.get('points', []):
      print(f"{sys.argv[1]:42s} T={d.get('threads_env')} ppw={p.get('posts_per_worker')} "
            f"W={p.get('W')} thr={p.get('throughput_videos_per_s')} cpu={p.get('cpu_util_of_32')}")
  PYEOF
  done
ONE matching point → the other value was a transcription slip; the record takes
the file's value and drops the other. TWO matching points with different values
→ they are two REPS, 1.3% apart, and that is the only rep-spread datum the LI
arm has — keep it as that, do not average or discard. Either way the record
then names one number with its file.
  **LIVENESS_MIN — NOT LANDED.** run_plan requires it (gate 5, probe-derived,
  the driver refuses to default it). It is absent from the repo. A DRY pass may
  omit it (gate 5 = NOT RUN; allowed only under DRY_PASS=1 since this commit);
  the REAL run refuses without it. Derive it on the box from measured
  non-empty-frame fractions (recipe below) — Ansh sets the number.
**Crossroad 30 result:** M=32 × T=1 = 0.1602 videos/s, cpu 0.875, **idle
10.04 cores (31%)**; M=16 × T=1 = 0.1345 (T=1 is past the useful floor).
16→32 buys +3.3% for double the tokens and double the idle.
**Crossroad 31:** M_TOKENS=16, parity T=2. **M=32 is measurably faster and we
DECLINED it** — 3.3% does not justify 31% of the box idle and 32 model stacks.
Full curve published: `working/video/RR_PARITY_CURVE.md` (the run_manifest
`decisions` block points at it). That sentence travels with every parity number.
**Crossroad 32:** WARM_N=16, 44 measured retained. A warm row MAY cover more
than one token; the invariant is warm-vs-MEASURED disjointness, and the driver
gates every instance observed serving (it always did). IMPLEMENTED: the
`len(warm) < tokens` refusal is now a recorded note; the top-up loop re-sends
warm rows (bounded 2×max(instances, rows)) until covered; run_plan's WARM_N
refusal is a note. PASSES=2 so the C=16 blast has real waves.
**BOX ORDER (2026-08-22): (1) node md5 fingerprint → (2) derived layer →
(3) LI thread read-back check → (4) dry pass at PASSES=2. Keep-alive OFF
throughout; fresh containers (`docker rm -f rr li_video` first).**

**(3) LI THREAD READ-BACK — 2 minutes, confirms LI_THREADS_ENV=4 landed:**
  docker rm -f li_video; docker run -d --name li_video --memory 58g \
    -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 \
    -e VECLIB_MAXIMUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TORCH_NUM_THREADS=4 \
    -e WS1V_WORKERS=8 --network host li:video
  ~/.venv-floor/bin/python working/video/probe/wait_ready.py --arm li --port 8802 \
    --workers 8 --container li_video --thread-readback --expect-threads 4
  → verdict OK (8/8 pids answered, every one torch_num_threads=4) sets the
  number. MISMATCH = the -e flags never reached the workers and the 0.1340
  was measured at some OTHER thread count → LI_THREADS_ENV is NOT set until
  re-measured. INCOMPLETE = fewer than 8 distinct pids answered. rc=1 on
  anything but OK. Then `docker rm -f li_video` before the dry pass.

**(4) DRY PASS (the composition has never completed), box, repo root:**
  cd ~/parity-bench-video && git pull --ff-only origin video-bench && git rev-parse HEAD
  DRY_PASS=1 M_TOKENS=16 RR_THREADS_ENV=2 LI_WORKERS=8 LI_THREADS_ENV=4 \
    WARM_N=16 BLAST_C=16 GATE3_RUN_ID=probe_20260821_195214 DEFAULT_N=44 \
    bash working/video/run_plan.sh 2>&1 | tee working/video/dry_console_$(date -u +%Y%m%dT%H%M%SZ).log; \
    echo "run_plan rc=${PIPESTATUS[0]}"
  (LIVENESS_MIN omitted → gate 5 NOT RUN on every dry leg, by design. PASSES
  defaults to 2 under DRY_PASS=1 so the pass mechanism is exercised.)
**LIVENESS_MIN — THIN FROM THE DRY PASS ALONE, and that matters.** DRY_PASS=1
clamps every leg to n=1, so the dry records hold ONE video per leg (the first
manifest row, the same file on every leg) — one video's non-empty-frame
fraction is a sample of size one for a gate that must hold across a 6× duration
spread and 44 videos. Compute it from EVERY record available (dry-pass records
AND the probe/gate-3 staged outputs, which carry per-frame detections for
ES2002a on both arms), take the MINIMUM observed, and set the threshold below
it with margin — then the black-fixture null control must still FAIL the gate,
or the threshold is decorative. If the only data is one video, say so in the
export: a threshold from n=1 is a stated assumption, not a measurement.

**LIVENESS_MIN recipe (box; from any records jsonl — dry-pass records give one
video per leg; the gate-3 staged run's records give ES2002a both arms):**
  for f in working/video/results/mainrun_*/records_*.jsonl; do ~/.venv/bin/python - "$f" <<'EOF'
  import json, sys
  for l in open(sys.argv[1]):
      r = json.loads(l); d = r.get('detections_per_frame') or []
      if d: print(sys.argv[1].rsplit('/',1)[-1], r.get('video'), f'{sum(1 for x in d if x > 0)/len(d):.3f}', len(d))
  EOF
  done
  → the fraction of frames with ≥1 detection per video; the threshold sits
  below the minimum observed with a margin (Corner view is dense — expect ~1.0)
  and the black-fixture null must still FAIL it. Ansh's number, not mine.
**▶ FIRST LEG FAILURE (2026-08-22) — THE COLLECTOR'S PATHS, FIXED.** The dry
pass's smoke PASSED (0 failures) and the driver died right after preflight with
rc=1. Cause, found by `find`: `ProcessCollector` starts its child with
`cwd=<repo>/working` and passed the (relative) out-dir string; the child
resolved it there and wrote **`working/working/video/results/.../collector_*.ready`**
— it started, sampled and published readiness — while the parent polled the
same relative string from the repo root and timed out. **The child succeeded;
the parent watched the wrong path.** Phase 1 never hit it because its drivers
ran FROM `working/`, so both cwds agreed (entry 3's shape: nothing changed, the
conditions moved). FIXED in `ProcessCollector.__init__` — `Path(out_path).resolve()`
before either side uses it, so correctness cannot depend on the caller's cwd
(fixing it by changing the driver's cwd would have encoded the bug). Both
failure messages now name the resolved path and the child's cwd, so the next
one is diagnosable from the traceback alone. Reproduced and verified locally:
pre-fix the child's target was byte-identical to the stray file on the box.
**AUDIT (ordered with the fix): in the video path this was the ONLY relative
path crossing a boundary.** Every `docker exec` path is absolute in-container
(`/proc/…`, `/sys/fs/cgroup/…`); every `use(filepath=)` in the video tree is
ROOT-derived; the driver's own constants are all ROOT-derived. Two sites
FLAGGED, not changed: `working/handoff/tree_collector.py:617` is a Phase 1 copy
of the same `cwd=root` pattern (not on the video path), and
`bake_rr_video.sh` passes `filepath='working/video/…pipe'` relative to the SDK
— resolved client-side, proven working by every bake, but the same class.
**BOX CLEANUP (look before deleting):**
  cd ~/parity-bench-video && find working/working -type f | head -20   # expect ONLY collector_* from the failed dry pass
  rm -rf working/working                                          # only if that is all it holds
**ALSO FIXED with it:** the LI arm's provenance no longer carries
`threads_note: "unset -> engine CONST_DEFAULT_MAX_THREADS=64 (constants.py:48)"`
— an RR constant with an RR source citation inside a LlamaIndex record. The
posture block is arm-aware: RR keeps threads_config/threads_note; LI reports
`declared_workers` + the measured per-worker torch and states plainly that
those RR fields do not exist on that arm. `Posture.label()` likewise renders
`workers[declared_workers=8]` instead of RR vocabulary.
**AND:** `--no-collector` is now LOUD — `collector_status` is a first-class
export field (`DISABLED` / `ERROR` / `EMPTY` / `ok`), a WARNING line is printed,
and the status rides in `at_a_glance` (`| COLLECTOR ok`). A null summary beside
nine passing gates was the last silent degradation of its kind.

**▶ THE GATE WOULD HAVE ABORTED THE CAMPAIGN AT LEG 2 — found answering the
settle question, fixed 2026-08-22.** `load1` is a ~60 s exponentially-damped
average, so it reports HISTORY, and our own history dominates it: a blast leg
runs the box at ~23 of 32 cores, and after it ends load1 needs **~150 s** to
fall under the 2.0 threshold (23·e^(−t/60)) while the next leg's preflight
reads it **~15 s** later with a 90 s settle budget. Legs 2–9 would each have
failed a gate whose purpose is catching someone ELSE's hog. **No dry pass could
ever have caught this** — a dry pass clamps every leg to n=1 and an n=1 leg
leaves no tail; the failure needs exactly what a rehearsal removes.
**FIXED — the gated number is now INSTANTANEOUS:** host busy cores (/proc/stat
over the same window) − our containers' cgroup rate − our own process tree's
rate. No history, no decay, no self-inflicted failure. `foreign_by_load1` is
still computed and recorded beside it (it is what Phase 1 published and what
caught the 18-Aug hog) and becomes the gate only where /proc/stat is unreadable
(macOS syntax checks). Verified both paths: fallback on this laptop, and the
/proc/stat arithmetic against injected ticks (planted 8.0 cores → measured
7.97). Register entry 13 DRAFTED for Ansh's ruling.
**ANSWER TO THE SETTLE QUESTION, therefore: NO.** The first leg does NOT
systematically eat 30–60 s. Step 0's full-corpus sha256 has EXITED by the time
the smoke reads, so it contributes nothing to an instantaneous measure — and
neither does the previous leg's tail. If a quiet-box check settles now,
something is burning CPU *at that moment*; the trend says whether it is a
transient (DECAYING) or a hog (SUSTAINED). Noted in run_plan step 0 so nobody
reads a settle as normal at 2 a.m.

**RULING ANSWERED (2026-08-22) — THE GATE SUBTRACTED ONLY CONTAINERS, AND THAT
WAS WRONG.** Answer to the question as asked: the driver was **NOT** attributed.
`attributed = sum(container_idle_cores(c))` and nothing else, so the driver, the
smoke, every `docker` CLI call, the console tee, the operator's shell **and
run_plan's own step 0 (`fetch_ami_video.py --verify` — a FULL-CORPUS sha256,
~1 core for tens of seconds, finishing shortly before the first leg reads
load1)** all counted as FOREIGN. The effective threshold was therefore tighter
than 2.0 during real legs, exactly as suspected — and the harness was charging
its own tail to a hog. FIXED: `driver_video.quiet_box()`, one reader for driver
and smoke, computes **foreign = load1 − our containers − our own process tree**
(`own_cores_recent()`, self+children rusage over load1's own ~60 s window,
labelled a lower bound since load1 also counts uninterruptible sleep).
**And a snapshot cannot tell a tail from a hog, so it no longer takes one:** a
first reading over threshold triggers a bounded re-read loop (default 90 s,
never overshooting) and the record carries the SEQUENCE plus a `trend` —
DECAYING / SUSTAINED / RISING. Null-controlled (own CPU attributed, gate can
still fail, settle loop re-reads).
**ARITHMETIC ON THE 2.35, worth stating before Ansh diagnoses:** load1 is a
~60 s-time-constant average, so a keep-alive killed **40 minutes** earlier
contributes e^(−40) ≈ 10⁻¹⁸ — **decay from 40 min ago cannot explain 2.35.**
The plausible contributors are the ones now attributed (step-0 sha256 tail, the
smoke's own subprocesses) plus the enumeration shell — or a real hog. The
re-read trend will say which without an argument.

**LIVENESS_MIN — one command, all artifacts (2026-08-22):**
  ~/.venv/bin/python working/video/probe/liveness_from_records.py \
    working/video/results/mainrun_*/records_*.jsonl \
    working/video/probe/probe_rr_t*.json working/video/probe/probe_li_floor_t*.json
  Handles THREE schemas by TYPE, never by key name: LI records carry
  `detections_per_frame` as a LIST; RR records carry `frame_label_multisets`
  (the RR arm cannot recover n_detections client-side, so the multiset length
  is the count); and `probe_li_floor_t*.json` carries `detections_per_frame`
  as a FLOAT AVERAGE (probe_li_floor.py:151) — a name-based reader iterates it
  and computes garbage silently, so it is refused, and the refusal is one of
  the two null controls the script fires (the other: an all-zero black-fixture
  video must read 0.000). Prints per-video fractions, the MINIMUM, and n —
  and says plainly when n is small that the threshold is an assumption.
  Expect ~1.0 on Corner (~26 det/frame); ~0.5 sits far below anything real and
  still fails the black clip. The value is Ansh's ruling.

**CAMPAIGN SCHEDULE — estimates, with each anchor named (2026-08-22).** Basis:
44 measured videos × mean ~127 frames ≈ **5,590 frames**; 16 warm rows;
measured aggregate rates RR parity 16×2 = **12.87 frames/s** (0.1551 videos/s ×
83) and LI 8×4 = **11.12 frames/s** (0.1340 × 83); RR single-stream t8 = 4.83
f/s, t32 = 2.31 f/s (probe_rr steady sends).
| leg | warm | measured leg | anchor |
|---|---|---|---|
| setup: rr + li up, smoke | — | 6–8 min | dry-pass readiness 5.0 s / 15.0 s |
| LI sequential (5 + repeat) | 3.1 | 4–5 min | LI single-request ~0.35 s/frame |
| LI blast ×2 (44, C=16) | 3.1 ea | 8.4 min ea → **23 min** | 11.12 f/s MEASURED |
| RR default seq (5 + repeat) | 1.0 | 3–6 min | bracketed, see below |
| **RR default blast ×2 (44)** | 1.0 ea | **20–41 min ea → 40–82 min** | **UNMEASURED — see below** |
| RR parity seq (5 + repeat) | 2.6 | 5–8.5 min + 3 min for 16×use() + 1.5 min terminate | T=2 single-stream UNMEASURED |
| RR parity blast ×2 (44, C=16) | 2.6 ea | 7.2 min ea → **29 min** incl. use()/terminate | 12.87 f/s MEASURED |
| cross gates | — | ~1 min | |
**TOTAL ≈ 2.2–2.9 h.** Two honest gaps in that number:
- **The default posture's thread count was never characterised.** It runs the
  engine default (torch resolves to 16 on this host — first measured in the
  failed dry pass) and the M=1 curve measured only 1/8/32, so its rate is
  BRACKETED between t8 (4.83 f/s) and t32 (2.31 f/s). That single unknown is
  ±20 min per pass and dominates the schedule (Ticket 5 open question 3).
- **The parity SEQUENTIAL leg runs at T=2, below the knee** — single-stream
  cost there is uncharacterised too (t1 = 0.93 f/s, t8 = 4.83; T=2 interpolates
  to ~1.5–2.5). Aggregate parity throughput is unaffected; this is the per-stream
  latency leg only.
**SHARPEN BOTH FROM THE DRY PASS before launching** — it ran every leg at n=1,
so it measured exactly these configurations once:
  cd ~/parity-bench-video && for f in working/video/results/mainrun_*/records_*.jsonl; do \
    python3 -c "
  import json,sys
  for line in open(sys.argv[1]):
      r=json.loads(line)
      if 'error' in r: continue
      fo=r.get('frames_observed') or 0; w=r.get('wall_s') or 0
      if fo and w: print(f\"{sys.argv[1].split('/')[-1]:50s} frames={fo:4d} wall={w:7.1f}s -> {fo/w:5.2f} f/s\")
  " "$f"; done
  → multiply each leg's f/s by 5,590 for that leg's blast wall. One video is
  n=1 (label it), but it replaces a 2× bracket with a measurement.
**SCHEDULE OPTION, not a ruling:** PASSES=2 was ruled so the C=16 blast has
real waves — but the DEFAULT posture has ONE token, so it has no waves and its
steady window is degenerate at any pass count. A second default-posture pass
buys rep/determinism evidence, not window depth; running the default at
PASSES=1 would save **20–41 min**. run_plan applies PASSES to all blast legs,
so this needs a one-line change (a separate DEFAULT_PASSES) — Ansh's call, not
made.

**REAL RUN (after a green dry pass), nohup so an SSH drop cannot kill a
measured leg; NO keep-alive (Crossroad 21 forbids it during measured legs):**
  cd ~/parity-bench-video && mkdir -p working/video/results && \
  M_TOKENS=16 RR_THREADS_ENV=2 LI_WORKERS=8 LI_THREADS_ENV=4 WARM_N=16 BLAST_C=16 \
  GATE3_RUN_ID=probe_20260821_195214 DEFAULT_N=44 PASSES=2 LIVENESS_MIN=<ASK> \
  nohup bash working/video/run_plan.sh > working/video/results/console_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
  then: tail -f working/video/results/console_*.log ; at the end:
  grep -n "AT A GLANCE\|NOT DONE\|STEP FAILED\|GATES FAILED\|CROSS GATES\|completed" working/video/results/console_*.log
**Sent-samples correction:** drafted as message #5 in
`team_docs_sent/MESSAGES_2026-08-21.md` — CONDITIONAL on Ansh confirming the
JSONs went out; unsent. Both .md files and the Shashi message WERE sent (relayed).

**DRY PASS #1 — FAILED, rc=1 (late 2026-08-21), diagnosis PENDING the log tail
+ the rr image's `Config.Env`.** Relayed: `rr declared thread env (expected
unset): ` (empty — correct for unset) then rc=1. The echo printed, so `docker
run` and `docker inspect` both succeeded; the NEXT step is `wait_ready.py
--arm rr`, whose three failure signatures are: `needs the rocketride SDK, not
importable in this interpreter` (the ~/.venv interpreter; immediate),
`NetworkMode` from assert_host_network (immediate), or `never became
SDK-connectable … within 1800s` (30 min). The `run` wrapper prints `STEP
FAILED rc=N: …wait_ready.py …` either way. Do NOT diagnose from the two
relayed lines (register entry 9).

**PASSES=2 DEFECT — FIXED (same evening):** the driver resumed pass 2 from
pass 1's records and measured nothing; the dry pass clamped PASSES to 1 and
was green while broken. Now `--pass N` suffixes every per-leg artifact with
`_pN` (records, export, collector, docker log, preflight — collector and
docker-log names also gained the posture; they were overwritten between
postures before), run_plan passes it in all three blast loops, step 4 pairs
RR and LI files of the same pass suffix, and the DRY pass runs PASSES=2.

**LI BUDGET-LINE REFINE (ruled; before the campaign; ~30–40 min; box, probe
dir, floor venv; arms one at a time — `docker rm -f rr li_video` first):**
  ~/.venv-floor/bin/python probe_li_workers.py --video media/ES2002a.Corner.avi --sweep 4  --image li:video --threads-env 8 --posts-per-worker 4 --out probe_li_workers_T8_ppw4.json
  ~/.venv-floor/bin/python probe_li_workers.py --video media/ES2002a.Corner.avi --sweep 8  --image li:video --threads-env 4 --posts-per-worker 4 --out probe_li_workers_T4_ppw4.json
  ~/.venv-floor/bin/python probe_li_workers.py --video media/ES2002a.Corner.avi --sweep 16 --image li:video --threads-env 2 --posts-per-worker 4 --out probe_li_workers_T2_ppw4.json
  Compare against the existing W=8×T=1 ppw=4 point (0.0882). Same shape as
  the RR budget line (W×T=32). If 16×2 is still climbing, W=32×T=1 is the
  fourth point (C30's lesson; the memory-ascent guard decides if it runs).
  Outcome either confirms LI_WORKERS=8 / LI_THREADS_ENV=1 or moves them.
**LI out-of-box leg:** operator leans best-to-best only on LI with the
asymmetry stated; agent concurs with conditions (chat, 2026-08-21 late):
LlamaIndex is a library — an "out-of-box" LI leg would measure OUR serving
scaffold's defaults, not LlamaIndex's; the default posture is an RR-internal
ratio (C27), never a cross-arm headline. Pending Ansh.
**Monday disclosure (Phase 1 tuning symmetry):** PHASE1_CARRYOVER.md
Correction #3 — first-person, stated first. Operator approved "send as written".

**DRY PASS #1 — REACHED THE SMOKE (wait_ready PASSED: rr 5.0s, li 15.0s,
warm_workers 8). Two smoke failures, both instructive:**
1. Quiet-box gate fired: FOREIGN load 10.11 > 2.0 — Ansh's keep-alive during
   the smoke. The gate did its job. Killed; load 1.14. **Standing rule
   reaffirmed: keep-alive OFF for anything that measures (Crossroad 21).**
2. **`FAIL RR task process cannot import rfdetr (None)` — a DEFECT IN OUR
   INSTRUMENT, now fixed.** The field was None, not False: the env_probe node
   that ran emitted an OLD field set (env + torch present — pins passed at
   torch=16 — but rfdetr_import_ok and python_version ABSENT; both are
   2026-08-20 node additions). Leading hypothesis: **a STALE env_probe node
   baked into rr:patched-video** (the bake commits whatever rr:patched carried;
   nothing checked the node). Ansh proved rfdetr imports in the engine
   interpreter — consistent: the package is fine, the NODE is old.
   **CLASS FIX (2026-08-22): absence of a read-back is now distinct from a
   negative one, everywhere env_probe reports.** Node emits `env_probe_schema`
   (=2); `driver_video.assert_envprobe_complete()` asserts every required field
   is PRESENT and schema >= 2 BEFORE any value is read, raising a loud
   stale-node "rebuild" verdict — so `rfdetr_import_ok is not True` now only
   fires for a REAL import failure (present-and-False). Driver + smoke both
   call it; null control fires (3 stale/empty/low-schema raise, complete +
   present-negative pass). Structural prevention: the bake now refuses to ship
   an image whose env_probe md5 != the repo (read-back (d), self-updating).
   **STALE CONFIRMED FROM GIT (2026-08-22), not from behaviour:** the observed
   field set (env ✓, torch_num_threads ✓ =16, rfdetr_import_ok ✗,
   python_version ✗) is EXACTLY and ONLY the 2026-08-10 node a41e241; both
   missing fields were added 2026-08-20 (56ee341 rfdetr, 2b1e969
   python_version). Node md5 by revision — the DISCRIMINATING box test:
     cba71b3595a173132c15b22624ab3c66  a41e241  2026-08-10  (stale: diagnosis right)
     00676b0eb8a16050cdf2a727a7e47035  2b1e969  2026-08-20  (then the None came from the RESPONSE PATH, diagnosis wrong)
     0a2850a0da3201ca741c74b59b1fcf92  b1efe1b  2026-08-22  (today, schema=2)
   `docker run --rm rr:patched-video md5sum /opt/rocketride/engine/nodes/env_probe/IInstance.py`
   (`grep -c env_probe_schema` returns 0 for BOTH stale candidates and cannot
   tell them apart; the md5 can.)

   **BOX ACTION — DERIVED LAYER, NOT A REBUILD (see the invalidation answer
   below).** env_probe is NOT in the measured pipe (benchmark_video_detect.pipe
   = webhook, frame_grabber, detect, preprocessor_langchain,
   embedding_transformer, response_documents) — it is the INSTRUMENT, loaded
   only by the generated envprobe pipe. It also has no requirements.txt, so
   replacing it cannot touch the engine's constraints-cache key (keyed on
   requirements files' path:size:mtime, Dockerfile:192).
     docker tag rr:patched-video rr:patched-video.pre-node-fix   # preserve FIRST (entry 7)
     docker build -t rr:patched-video -f - . <<'EOF'
     FROM rr:patched-video.pre-node-fix
     COPY working/nodes/env_probe /opt/rocketride/engine/nodes/env_probe
     RUN rm -rf /opt/rocketride/engine/nodes/env_probe/__pycache__
     EOF
   Verify: node md5 = 0a2850a…; `grep -c env_probe_schema` = 1; labels still
   duplication_patch_applied=1; and the PROOF that nothing beneath moved —
     diff <(docker inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' rr:patched-video.pre-node-fix) \
          <(docker inspect -f '{{range .RootFS.Layers}}{{println .}}{{end}}' rr:patched-video)
   → the old layer list must be a strict PREFIX (only 1–2 ADDED lines at the
   end, nothing changed above). Record in provenance: this image is
   "Dockerfile + one documented layer", a deviation to be retired by the
   re-baseline. NOTE: rr:patched keeps the stale node; the bake's new
   read-back (d) will REFUSE the next bake until rr:patched is rebuilt —
   correct fail-closed behaviour, and the re-baseline's to-do.

   **▶ THE INVALIDATION ANSWER (asked before rebuilding, answered before
   rebuilding).** A full rebuild of rr:patched CANNOT be assumed byte-identical
   in what the engine executes. Pinned and safe: the engine ELF (double
   sha-pinned — tarball ENGINE_SHA256 + extracted ENGINE_BIN_SHA256, verified
   with `sha256sum -c`, Dockerfile:64,65,79 — it is identical or the build
   FAILS); the onnx and duplication patches (deterministic, guarded);
   pypdf==6.15.0; rocketride==1.3.0 (apt python3.10 — the engine's node code
   runs on the EMBEDDED CPython 3.12, so SDK dep drift is off the measured
   path). **NOT pinned — three vectors into the execution path:**
   (1) `FROM ubuntu:22.04` (Dockerfile:38) is a FLOATING tag → glibc/libc++/
   libunwind can change, and the file's own header lists them as the engine
   ELF's DT_NEEDED; (2) `apt-get install libc++1 libc++abi1 libunwind8 …`
   (:46-49) is unpinned; (3) the bootcheck **constraints cache is COPYed into
   the final image** (:226) and the Dockerfile itself says this "freezes
   dependency RESOLUTION at image-build time… first-boot resolution floats with
   PyPI state" — a rebuild re-resolves against TODAY's PyPI. Cache subtlety:
   the node COPY at :176 invalidates everything below it, so **even a warm
   build cache re-runs the bootcheck stage and re-resolves constraints**;
   vectors 1–2 survive on a warm cache but Crossroad 19 had build cache being
   reclaimed for disk, so it may be cold.
   **What a changed image would invalidate — all measured on the CURRENT
   rr:patched-video:** Ticket 5's thread curve (t1/t8/t32, two runs); Ticket 4's
   idle curve M=1…16 and the 0.26 cores/token slope; the M×T refine (4×8, 8×4,
   16×2, 32×1) and therefore **Crossroad 31's M_TOKENS=16 / T=2**;
   measured_dpf 25.95 and chars-per-det 230.4 (the manifest's est columns);
   gate 4's PNG frame-identity probe; and most sharply **GATE3_RUN_ID=
   probe_20260821_195214** — gate 3 is STRICT zero-tolerance and armed by that
   run id, so if anything in the detect path moves, the arming evidence
   describes an image that no longer exists and gate 3 must be RE-STAGED.
   Unaffected either way: the LI arm (li:video untouched), corpus sha pins,
   `expected_frames_measured` (host-side ffmpeg at manifest build), the gates.
   Partial guard if a rebuild does happen: the bake's read-back (b) compares the
   vision stack against engine_pins.txt and (c) the rf-detr md5 — a drifted
   resolution FAILS the bake rather than shipping silently (fail-closed, but it
   can cost the night).
   **RE-BASELINE (PATH B) — after the campaign, deliberately, never at 11pm.**
   Preserve + fingerprint BEFORE (`docker tag` both images aside, then capture
   engine ELF sha256, dpkg versions of libc6/libc++1/libc++abi1/libunwind8/
   libgcc-s1, every site-packages dist-info listing, the constraints-cache file
   count, node md5), `docker build -f docker/Dockerfile.rocketride -t rr:patched .`,
   `bash working/video/bake_rr_video.sh`, capture the same fingerprint AFTER,
   and `diff`. Any difference outside the node line = the probe numbers and the
   gate-3 arming were taken on a different image; re-take them or run the
   campaign on the preserved tag. Doing this on purpose retires a real unknown:
   nobody currently knows what a rebuild of this Dockerfile produces.
3. **First measurement of the default posture's unset thread count: torch
   resolves to 16 on this host** (`cross-arm in-process torch {'rr': 16}`) —
   Ticket 5 open question 3, the point the M=1 curve never measured. Type bug
   caught alongside: rr was int 16, li was string '1' — cross_arm_values
   preferred the declared env string when present. FIXED: cross_arm_values is
   now the MEASURED torch count, int, both arms (null control asserts int
   consistency).

**cross_default labeling (approved, done):** `--cross-label` stamps a `basis`
into every cross file; run_plan gives the default posture "equal-work gates
ONLY … not a cross-arm performance comparison (Crossroad 27)", parity gets the
comparison label. So a reader cannot mistake a default-posture gates file for
a performance claim.

**▶ TICKET 4 ANSWERED — RR concurrency sweep, T=8 (landed late 2026-08-21;
RELAYED values — the box JSON, `probe_concurrency_T8.json` per the invocation,
is authoritative and its `ticket4_idle_answer` key holds the fitted verdict):**
  M=1   0.0688 videos/s   wall  14.5 s   cpu_util_of_32 0.262   idle 1.28 cores
  M=2   0.1006            wall  19.9 s   0.477                   idle 1.54   (1→2 marginal 0.73)
  M=4   0.1179            wall  33.9 s   0.853                   idle 2.02   (2→4 marginal 0.59)
  M=8   0.0246            wall 325.6 s   0.976                   idle 3.04   (4→8 COLLAPSES 4.8×)
  M=16  0.0187            wall 856.8 s   0.985                   idle 5.25   (8→16 marginal 0.38)
**Verdict: PARTIAL, ≈0.26 cores/token.** Least-squares over the five relayed
points: slope 0.264, intercept 0.99 — the fit's intercept IS the 1.002-core
single-engine measurement; per-step marginals 0.26/0.24/0.26/0.28, linear. Not
PER-SERVER (flat ~1.0), not PER-TOKEN (~1.0 each). At M=4 that is 2.02 idle
cores = **6.3% of the 32-core box burned before any work**; at M=16, 16.4%.
Ticket 4 updated with the curve. The driver now measures the same quantity per
leg (idle cores with every instance live, same cgroup reader, both arms) and
every export's `efficiency` block carries it BESIDE the CPU figures — reported,
never subtracted (additivity under load is unmeasured).
**The M=8 collapse is a DIFFERENT failure from t32 (Ticket 5).** There the box
was IDLE while wall grew (util 0.46 → 0.18: lock contention). Here CPU is
PEGGED (0.976) while wall grows 9.6×: M×T oversubscription — 8 tokens × 8
intra-op threads = 64 threads on 32 cores. CPU-s per video from the relayed
values (util × 32 × wall ÷ M): 122 · 152 · 231 · 1,271 · 1,688 — identical work
costing 5.5× the CPU at M=8 vs M=4. (Whether that becomes a Ticket 6 is
Ansh's call; not drafted.)

**THE CROSS-ARM SENTENCE — worth its own line in the report:** both stacks
degrade past their knee, and they degrade DIFFERENTLY. LlamaIndex at W=16 goes
wall-up / CPU-DOWN (0.219 → 0.177) with all 16 workers alive — STARVED.
RocketRide at M=8 goes wall-up / CPU-PEGGED (0.976) — OVERSUBSCRIBED. Same box,
two ceilings, two mechanisms. That is a better finding than either arm's peak
throughput. (Note on the "shared substrate" line in the LI-curve paragraph
below: it matched LI W=16 against RR's THREAD axis — t32, util falling. The RR
TOKEN axis fails by the opposite signature on the same box, so "shared
substrate" is one hypothesis, not a finding; the sentence above is the measured
statement.)

**CROSSROAD 29 (2026-08-21) — REFINE LANDED, CURVE STILL CLIMBING.** Both
sweeps had held the other axis at a value chosen before the interaction was
visible. The budget-32 points (M×T = 32 threads on 32 cores), relayed,
MONOTONIC IN TOKENS:
  M=4  × T=8   0.1179 videos/s   cpu 0.853
  M=8  × T=4   0.1417            cpu 0.863
  M=16 × T=2   0.1551            cpu 0.867   idle 5.24 cores   ← best yet, +9.5% over 8×4
Tokens parallelize where threads queue behind the device lock. Idle at M=16
is 5.24 at T=2 vs 5.25 at T=8: the per-token spin is T-independent (in Ticket 4).
**CROSSROAD 30: test M=32 × T=1 before setting M_TOKENS** — stopping at the
last point we happened to test is the error the refine just caught. Ansh is
running `--sweep 16 32 --threads-env 1`. The trade is no longer free: 5.24
idle cores at M=16 = 16.4% of the box; M=32 PROJECTS to ~9.4–9.9 cores (29–31%,
by the fit's 0.26/token or the last marginal 0.28) — a projection, to be
MEASURED by that sweep before it is quoted. **RULING: set M_TOKENS on measured
throughput and report the idle burden BESIDE it — reported, never subtracted.**
A config that wins on throughput while burning a third of the box idle is
still the honest production answer if that is what the engine does;
concealing the cost is the dishonest part. Built: `at_a_glance` is the FIRST
key of every export and the driver's last stdout line — throughput, service
CPU, idle burden with instances live, thread env expected/measured, gate
counts, on one line (shared function, sample and box agree by construction).

**RULING 1 (2026-08-21) — PER-POSTURE THREAD ENV, IMPLEMENTED:** the DEFAULT
posture runs the ENGINE DEFAULT — the six BLAS/OMP vars NOT declared on the
container ("what a user actually gets"); the PARITY posture runs the measured
optimum (`RR_THREADS_ENV`, set with M by C29/C30). run_plan now starts `rr`
TWICE (`start_rr unset` for steps 1–2, `stop_arm rr default`, `start_rr
"$RR_THREADS_ENV"` for step 3, `stop_arm rr parity` — per-lifetime docker
logs), every RR leg states `--rr-threads-env <int|unset>` (REQUIRED, never
implied by the posture), and the driver/smoke read it back declared (docker
inspect) and in-process (envprobe) through `gates_shared.thread_pins_by_arm(
expected_by_arm=…)`: value mode = all six declared == expected == measured;
**unset mode = none of the six declared AND none present in-process (a leaked
in-process value is #37's class and FAILS), torch's own count still REQUIRED
and agreed — recorded as the out-of-box value.** Null controls for both modes
(`thread_pins_self_test`, 8 cases) fire at every preflight and in the smoke.
Interpretation recorded: "threads unset" = the six env vars absent; on this
host class the library default resolves to ~16 intra-op threads (Ticket 5
OQ3 — the ONE point the M=1 curve never measured), so the default posture's
thread count is characterised for the first time by the campaign's own
read-back; `use(threads=)` stays unset (engine 64) as before.

**RULING 2 (2026-08-21) — THE SENT SAMPLES:** no JSON lives in
`team_docs_sent/` (three .md files). But `METRICS_AND_GATES.md` lines 3–4
address "Shashi, Leela — reviewing `sample_export_blast.json` and
`sample_cross_gates.json`", so if the JSONs went out beside it they went out
as the 08-20 versions (bb7f426 / e0d6f4b), which carry **84** on ES2002a
(`n_frames: 84`, `frames: 84` — the regenerated files say 83). The message to
Shashi (#3) states "ffmpeg emits 83 where it predicts 84" in prose, so the
prose teaches the right number and the JSON, if sent, the deleted formula.
Whether the JSONs were sent is NOT in the repo — ASK; if yes, the one-line
correction is owed now.

**[SUPERSEDED by the ▶▶ block above — all eight ruled (C31/C32); LIVENESS_MIN is the open ninth.]**
**THE RUN-PLAN NUMBERS — two landed, one ruled constant, the rest open:**
- `GATE3_RUN_ID = probe_20260821_195214` — LANDED (the ORIGINAL probe run, artifacts intact)
- `LI_WORKERS = 8` — LANDED (matched-load curve below; W=16 is past the knee)
- DEFAULT-posture RR thread env = **UNSET, by ruling** (Ruling 1 above). The
  earlier "`RR_THREADS_ENV = 8` LANDED for the default posture" is SUPERSEDED:
  `RR_THREADS_ENV` now means the PARITY posture's T only, set WITH M_TOKENS.
- `M_TOKENS` + parity T — **OPEN pending Crossroad 30** (M=32 × T=1 in flight).
  Provisional leader M=16 × T=2 (0.1551). Set on measured throughput; idle
  burden beside it. (The earlier "M_TOKENS = 4 provisional at T=8" is superseded.)
- OPEN: `LI_THREADS_ENV` (refine at W=8 with --threads-env {2,4}), `WARM_N`
  (≥ max(M, 8) plus margin, drawn from the 16 warm rows — **FLAG: with M=16
  the 16 rows give ZERO margin and with M=32 they cannot cover the tokens at
  all; the driver refuses a parity leg with len(warm) < tokens. C26's rule
  and the 44/16 re-cut collide above M=16 — Ansh's call: re-cut (e.g. 36
  warm / 24 measured), or rule that a warm row may cover more than one token**),
  `BLAST_C` (wave arithmetic; at M=16–32 a 44-video blast is 1–3 waves and the
  steady window thins — PASSES=2 is the existing remedy in run_plan),
  `DEFAULT_N` (ruled = 44 at this scale; not yet exported).

**THE LI CURVE (T=1, matched-load ppw=4 — the JSON on the box is authoritative;
an earlier relay read W=8 as 0.0871):**
  W=4  0.0459 videos/s  serving 4/4   cpu_util_of_32 0.110
  W=8  0.0882           serving 8/8   cpu_util 0.219   marginal 4→8 = 0.95
  W=16 0.0704           serving 16/16 cpu_util 0.177   batch wall 363 s → 909 s
**W=16 is past the knee: every worker alive, throughput DOWN, CPU DOWN, wall
2.5×.** That is the same contention signature RR showed at t32 (same work,
doubled wall, utilisation falling) — **two independent stacks exhibiting it
points at the shared substrate (host/BLAS/kernel scheduling), not at either
framework.** Worth its own line in the Monday material. Standard curve (ppw=1)
for the record: W=1 0.0131 (in-process baseline) · 2 0.0259 · 4 0.0480 ·
8 0.0554 with 6/8 serving — the 6/8 resolved to routing luck (outcome a) once
4× posts were offered; routing is NOT iid (W=4 served 4/4 where iid expects
~2.7 — register entry 11).

**ARCHITECTURE FACTS THAT CHANGE HOW NUMBERS ARE READ:**
- uvicorn `--workers 1` serves IN-PROCESS (tree = pid 1 only; health pid 1);
  `--workers ≥2` spawns `spawn_main` children. Two topologies from one flag →
  **W=1 is EXCLUDED from the knee** (reported as the in-process baseline;
  knee over W≥2 only; efficiency rebased to W=2 per-worker; a W2<W1 finding
  keeps W=1 in the LI_WORKERS decision).
- **The LI serving census is INVERTED — no argv predicate anywhere**: serving
  = processes that burned CPU during the batch, anchored by response pids ⊆
  burners (non-trivial; ATTRIBUTION BLIND otherwise, rc=2, full /proc tree
  recorded). argv predicates were retired after being wrong in two shapes the
  same day (`uvicorn` matches only the master; `spawn_main` children miss
  W=1). RR's census keeps its argv pattern — execution-verified at its
  configuration, and RR responses carry no pid to anchor an inversion.
- python:3.12-slim has no procps — never `docker exec ps` in the LI image;
  read /proc.

**RULINGS SINCE THE LAST BRIEFING (all in the rulings list below, one line each):**
C22 host networking + wait_ready; C23 measured frame column (formula deleted);
C24 t32 recheck (reproduced); C25 docs to the team; C26 warm-up value rule;
**C27** DEFAULT_N: default posture runs a stated subset ≥500 above ~1000
videos, manifest-order prefix, 44 now (wired, validated); **C28** all three
tracks run the full AMI corpus and THE RR ARM MUST BE IDENTICAL across them —
alignment is a PREREQUISITE to full-corpus runs; tonight's 44-video campaign
still banks real numbers first.

**THE ALIGNMENT — governing posture (Ansh): WE ARE THE JUNIOR ARM. FOLLOW or
VERIFY; never assume newer-instrument = better.** `RR_ARM_ALIGNMENT.md` sits
under Shashi's own three-track contract and his §15 checklist (PASS 7 /
CHANGE 8 / CONTESTED 3). **The eight FOLLOW changes are sized but
deliberately NOT implemented** pending Ansh's negotiation (his field names,
TTFR+basis, coverage summary, INSUFFICIENT_REPS label, his bands as gates,
detection_ratio + Jaccard, his frame_law value beside ours, the corpus). The
three CONTESTED rows (split_overlap — two seniors' contradictory byte-level
claims, we contribute seam evidence + a two-minute check, we do NOT
adjudicate; omp_num_threads — we measured 2.3→8.5 cores across BLAS 1→8 and
can FOLLOW OMP=1 reporting both; frame_law — 83 measured vs 84 predicted)
each carry a minutes-long check and no verdict.

**ASK — DO NOT INVENT (held by this session, not by the repo):**
- The RR concurrency sweep (T=8) HAS RUN — the five points above are RELAYED;
  the JSON is expected at `probe_concurrency_T8.json` per the invocation
  (filename unconfirmed). NOT relayed: the JSON's own fitted
  `ticket4_idle_answer` (verify the slope against 0.26) and the per-process
  attribution `idle_cores_per_process` (eaas server vs task subprocesses —
  Ticket 4 open question 1). ASK before citing the split.
- C29/C30 LANDED (relayed): 8×4 0.1417 · 16×2 0.1551 (idle 5.24) · 16×1
  0.1345 · 32×1 0.1602 (idle 10.04, cpu 0.875). M_TOKENS=16, T=2 ruled (C31).
  JSON filenames for the T=4/T=2/T=1 refines unrelayed — ASK before citing
  anything beyond `RR_PARITY_CURVE.md`.
- **LIVENESS_MIN is not landed** — the real run cannot start without it. ASK.
- Whether the 08-20 sample JSONs (84 on ES2002a) were SENT beside
  METRICS_AND_GATES.md is not in the repo — the sent doc addresses reviewers
  of those two files by name. ASK; if sent, the one-line correction is owed.
- The default posture's thread env is now UNSET by ruling — the campaign's
  first default leg is the first measurement of torch's own count on this
  host (~16 expected from Ticket 5's read-back). Read it from the export's
  `threads_env_in_process_torch`; do not quote "16" before then.
- W=16 raw JSON and the LI refine-pass results live on the box (filenames
  unrelayed); the numbers above are relayed values. ASK before citing beyond them.
- Messages to Leela/Shashi: the approved texts are preserved in
  `team_docs_sent/MESSAGES_2026-08-21.md`; whether they were sent verbatim and
  ANY REPLIES are unknown here. ASK.
- The alignment negotiation has not happened. ASK for its outcome before
  implementing any FOLLOW change.
- Operator rulings are recorded in paraphrase; ASK if verbatim wording is needed.
- Box state (relayed, late 2026-08-21): W=16 done, RR T=8 sweep done, C29
  refine (M∈{4,8} × T=4) in flight, then the LI refine pass, the dry pass, and
  the ~62-min campaign. Verify, don't assume.

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
- **Crossroad 29 (2026-08-21): REFINE IS MANDATORY BEFORE EITHER NUMBER IS
  SET.** The RR concurrency sweep at T=8 gave M_TOKENS=4 (2→4 marginal 0.59,
  4→8 collapse 4.8× with CPU pegged at 0.976 — M×T oversubscription, 64 threads
  on 32 cores; a different failure from t32's idle-box lock contention). But
  4×8 = 32 is exactly saturated and 8×4 = 32 may scale better, and each sweep
  held the other axis at a value chosen before the interaction was visible.
  Ansh runs `--sweep 4 8 --threads-env 4`; the winning M×T product sets BOTH
  M_TOKENS and the parity thread env. Ticket 4 answered by the same sweep:
  PARTIAL, ≈0.26 cores/token on top of the ~1.0-core server spin (M=4 idles
  2.02 cores = 6.3% of the box before any work); the driver carries the
  measured idle burden in every export's `efficiency` block, beside the CPU
  figures, never subtracted. Open flag: one container thread env serves both
  postures in run_plan (see the briefing) — RESOLVED by Ruling 1 below.
- **Crossroad 30 (2026-08-21): TEST M=32 × T=1 BEFORE SETTING M_TOKENS.** The
  C29 refine showed the budget-32 curve still climbing in tokens (4×8 0.1179 →
  8×4 0.1417 → 16×2 0.1551, cpu ~0.86 flat); stopping at the last point we
  happened to test is the error the refine just caught. `--sweep 16 32
  --threads-env 1` runs. RULING with it: M_TOKENS is set on MEASURED
  THROUGHPUT; the idle burden (5.24 cores = 16.4% at M=16; M=32 projected
  ~30%) is reported BESIDE it, never subtracted, legible at a glance in the
  export (`at_a_glance`, first key + last stdout line).
- **Ruling 1 (2026-08-21): per-posture thread env — IMPLEMENTED.** Default
  posture = engine default (six vars undeclared; torch's count read back);
  parity = the measured optimum (`RR_THREADS_ENV`). rr restarted between
  postures; `--rr-threads-env <int|unset>` required per RR leg; declared +
  in-process read-backs fail-closed; null controls both modes. Before the
  campaign, as ruled.
- **Ruling 2 (2026-08-21): the stale sample JSONs were possibly SENT** —
  answer in the briefing (no JSON in team_docs_sent; the sent doc names the
  files; 08-20 versions carry 84; whether they went out is an ASK). Correction
  drafted as message #5 (conditional, unsent).
- **Crossroad 31 (2026-08-21): M_TOKENS = 16, RR_THREADS_ENV = 2 (parity).**
  M=32×T=1 = 0.1602 (idle 10.04 cores = 31%), M=16×T=2 = 0.1551 (idle 5.24):
  16→32 buys 3.3% for double the tokens and double the idle; M=16×T=1 = 0.1345
  (T=1 past the useful floor). We DECLINE the faster configuration and say so:
  full curve in `working/video/RR_PARITY_CURVE.md`, pointed at by the
  run_manifest `decisions` block.
- **Crossroad 32 (2026-08-21): WARM_N = 16, 44 measured retained; PASSES = 2.**
  A warm row may cover more than one token provided every token is observed
  serving (the driver's existing gate); the disjointness that matters is
  warm-vs-measured. Refusals relaxed to that condition (driver + run_plan);
  warm top-up re-sends rows, bounded.
- **Crossroad 33 (2026-08-22): DERIVED LAYER APPROVED, full rebuild DEFERRED
  deliberately.** The invalidation analysis stands: a rebuild re-resolves the
  floating `ubuntu:22.04`, the unpinned apt `libc++`/`libunwind` the engine ELF
  links, and the bootcheck constraints cache — and the node COPY above the
  bootcheck stage re-runs it even on a warm cache — replacing the image every
  RR number and **gate 3's arming run** were measured on. The image is
  "Dockerfile plus one documented layer" and that goes in the run provenance
  VERBATIM: `--image-lineage` (driver) recorded beside the measured image id,
  layer count and labels in `provenance_video.image`; run_plan supplies
  `RR_IMAGE_LINEAGE` / `LI_IMAGE_LINEAGE` on every leg. PATH B after the
  campaign, fingerprints both sides.
- **Crossroad 34 (2026-08-22): LI_THREADS_ENV = 4, LI_WORKERS = 8 confirmed**
  — from the LI budget line (see the briefing). The tuning-symmetry audit paid
  for itself inside our own arm: T=1 was 54% below the LI arm's measured
  optimum at the same worker count. **Register entry 12** records why (the
  Phase 1 asymmetry was reproducing in Phase 2 while we drafted the argument
  against it; audits are scheduled, not suspicion-triggered) and ships the
  per-worker thread read-back that the sweep lacked.
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

## Exact box state (as relayed; PHASE 1 era, paths relative to ~/parity-bench — the VIDEO worktree is ~/parity-bench-video, see the briefing)

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
curve lands.**

**Crossroad 27 (2026-08-21): above ~1000 videos the DEFAULT posture runs a
STATED SUBSET (proposed >=500, or the full set when smaller — the
out-of-box finding is a ratio); parity always runs the full set. WIRED:
DEFAULT_N required+validated in run_plan (<= MEASURED_N; dry pass clamps to
1; recorded in run_manifest), default-posture blast uses it. cross_gates
pairs on the video-name intersection and reports n_paired — a subset
compares honestly. At 44-scale set DEFAULT_N=44.** Schedule estimate at
M=W=C=8 (anchors: 0.207 s/frame RR t8, 0.295 LI floor t8, mean ~127
frames): total ≈ 75 min wall, dominated by the RR default legs (~38 min
incl. two 7-min conc-1 warm-ups); parity+LI legs ~5 min each; the 48-min
video is a ~40 s (RR) / ~57 s (LI) service item whose drain tail costs the
SPAN ~15–20 s and is excluded from the steady window by construction
(window_n ≈ 33–36 at C=8). Corpus-swap cost memo:
**working/video/CORPUS_SWAP_COST.md** (what travels, what re-derives, the
three silent-if-skipped values: dpf/chars-per-det, LIVENESS_MIN, GATE3 id).

**LI CURVE LANDED (2026-08-21, T=1; census caught a real one):** W=1
0.0131 (in-process baseline, serving 1) · W=2 0.0259 (2) · W=4 0.0480 (4)
· **W=8 0.0554, serving 6 of 8 → STOP**. W≥2-rule numbers (the emitted
knee_W is old-rule — recompute from points): per-worker 0.0130/0.0120/
0.0069, marginals 1.00/0.93/0.53 → **KNEE AT 4, PROVISIONAL**. cpu_util
0.137 at W=8 — 86% idle while throughput stalls: not a CPU limit.
**[SUPERSEDED — see the compaction briefing at the top: LI_WORKERS = 8.]
LI_WORKERS = 4 PENDING the W=8 recheck.** Routing arithmetic that makes
the recheck genuine, not a formality: 6/8 at 8 posts ≈ iid-routing
expectation (~5.25 occupied), but W=4's 4/4 at 4 posts CONTRADICTS iid
(~2.7 expected) — routing is not iid, so "benign scheduling" is not a safe
default. distinct_response_pids=6 says the two never ANSWERED (not
attribution blindness). **Discriminator landed: --posts-per-worker** (posts
= W×ppw; P(worker draws zero of 32 offered) ≈ 1.4%). MATCHED-LOAD rule:
marginals only between points at the same ppw. Recheck invocation:
  ~/.venv-floor/bin/python probe_li_workers.py \
    --video media/ES2002a.Corner.avi --sweep 4 8 --image li:video \
    --threads-env 1 --posts-per-worker 4 --out probe_li_workers_T1_ppw4.json
Outcomes: (a) serving 8/8 AND 4→8 matched marginal ≥0.7 → knee moves to 8,
LI_WORKERS=8; (b) serving 8/8 but marginal still <0.7 → knee 4 stands
(saturation is real and NOT CPU — lock/IO territory, report); (c) serving
<8 at 32 posts → two workers genuinely dead → defect finding. EITHER WAY
the finding goes to Shashi (he published "15 of 32 pids served" as
scaling; our gate refuses it) — draft after the recheck lands.
**WARM RULING LANDED:** min(WARM_N, 2×instances) per leg + coverage top-up
one row at a time (RR round-robin covers by construction; LI routing may
hide a worker — teeth kept; executed contracts: default 2 rows (was 16),
parity/LI-8 unchanged 16, W=4-with-hidden-worker tops up). **DEFAULT_N
ruling marked RULED in run_plan.**

**Register entry 11 (2026-08-21, operator-ruled):** check the benign
explanation against the points already in hand — iid routing predicted
5.25-of-8 AND 2.7-of-4; W=4's measured 4-of-4 falsified it at zero cost.
**Ticket-4 headline LANDED in probe_concurrency:** idle-vs-M slope fitted
over the sweep points, verdict PER-TOKEN (>=0.7 c/tok) / PER-SERVER
(<=0.15) / PARTIAL, printed as a banner AND as the FIRST key of the report
JSON with the consequence spelled out (per-token at M=8 = ~8 cores burned
doing nothing — it changes what the parity posture means). Classifier
executed on all three synthetic curve shapes.

**SHASHI MESSAGE FRAME (send the moment the recheck lands, outcome slotted;
Ansh's voice):** our W=8 measured 6/8 serving — same shape as your
"15 of 32 pids served"; our gate refuses to emit a number in that state; we
ran a 4x-posts discriminator (a worker drawing zero of 32 offered ≈ 1.4%
under any routing that offers it work). Result: [OUTCOME a/b/c]. AND — this
holds regardless of our outcome — **entry 11 applied to HIS number: iid
routing at 50 posts on 32 workers expects ~25.5 occupied (32×(1−(31/32)^50));
he observed 15, far BELOW routing luck** — so "scheduling" cannot explain
his 15/32 either: it is non-iid pile-up (async multi-accept behind long
videos) or workers dead in rotation. The 5-minute check on his rig: post
4× worker count, count distinct serving pids. Outcome inserts staged:
(a) all-8 + marginal recovers → ours was small-batch starvation, knee→8;
(b) all-8 but marginal <0.7 → knee 4 real, non-CPU bottleneck (86% idle),
per-worker stage_s next; (c) <8 at 32 posts → dead-in-rotation, defect.

**RECHECK OUTCOME (a) — 8/8 SERVING at 32 posts (2026-08-21):** matched-load
W=4 0.0459 (4/4) · W=8 0.0871 (8/8), marginal 0.95, cpu 0.219. The two
missing workers were routing luck; **KNEE NOT AT 4 — LI_WORKERS = 8, W=16
extension running** (8 didn't saturate, CPU 22% of 32). Entry-11 paid
twice: refused the assumption, then delivered the same conclusion as proof.
Shashi message ASSEMBLED AND HANDED OVER (outcome a + his-15/32 iid
arithmetic: 50 posts on 32 workers expects ~25.5 occupied; he saw 15 —
below routing luck; the 4×-posts check transfers).

**CROSSROAD 28 (2026-08-21, Ansh's ruling): all three tracks run the full
AMI corpus and THE ROCKETRIDE ARM MUST BE IDENTICAL ACROSS ALL THREE — the
ordering inverts: alignment before full-corpus runs.** Their new docs read
(Leela RESULTS + SETUP_AND_RUN; Shashi VIDEO-BENCHMARK-SETUP with his OWN
three-track contract in Part II — Tier A/B/C + checklist §15). Deliverable:
**working/video/RR_ARM_ALIGNMENT.md** — blocking-first: B1 BLAS axis (their
Tier B pins OMP=1 everywhere; our measured curve 2.3→8.5 cores is the knob
neither swept), B2 threshold nesting (config.py:196 discard; ours nested,
theirs unshown, pipe shas can't adjudicate — project_id churn), B3 corpus
view (both teammates Closeup-first — the ×8 dpf hypothesis now covers all
three datasets; C28 rules we adopt their corpus, framing per-row), B4 the
CHUNK-OVERLAP CONTRADICTION (Leela 4000/0 "byte-exact" vs Shashi 4000/200
"langchain defaults" vs our MEASURED seam-200 — two byte-level evidence
chains that can't both be true; discriminator = captured chunks through our
seam counter), B5 SDK version (his Tier A says 1.2.0; Leela + our md5'd
wheel say 1.3.0), B6 posture/submission (their native send_files batch vs
our per-video; our C=BLAST_C driver answers his open c<N> question).
Aligned already: engine+patches, 15 s sampling, rfdetr 1.5.2 thr 0.3,
miniLM, V-suite vocabulary. Swap re-priced both ways in CORPUS_SWAP_COST
§C28 (~1–2 h either manifest; their two corpora differ from EACH OTHER —
Tier A currently violated between them; Ansh's negotiation).

**GOVERNING STANCE FOR THE ALIGNMENT (Ansh, 2026-08-21): WE ARE THE JUNIOR
ARM.** Where Leela or Shashi have a setup or a finding, we FOLLOW it or
VERIFY it — never assume ours is better because the instrument is newer.
Consequences applied: RR_ARM_ALIGNMENT.md RESTRUCTURED under Shashi's own
contract (Tier A/B/C) and his §15 checklist as THE verification artifact —
per box: PASS 7 / CHANGE 8 (all small, additive: his field names, TTFR +
basis, coverage summary, INSUFFICIENT_REPS label, his bands as gates, the
corpus) / CONTESTED 3 (split_overlap, omp_num_threads, frame_law) — each
contested row in the one permitted voice: "we measured X; here is the
check; one of us has something configured differently" — never a verdict
on anyone's conclusion. B4 (overlap) says exactly: two seniors hold
contradictory byte-level claims; we are NOT adjudicating; we contribute a
measurement (seam duplication in our responses) and a two-minute check to a
disagreement that is already theirs. B1 (BLAS): we can FOLLOW OMP=1 (two
lines) and report both configurations; the check is one BLAS=8 video per
rig so the contract picks its value with the curve in view. Shashi message
EDITED: the closing line about FULL50's figures dividing by the wrong W is
REMOVED — the arithmetic implies it; he draws it himself.

**[SUPERSEDED — W=16 landed (LI_WORKERS=8); RR T=8 sweep landed (Ticket 4
PARTIAL ≈0.26 cores/token; M_TOKENS=4 provisional); Crossroad 29 refine
(M∈{4,8} × T=4) in flight — see the briefing at the top.]**
NEXT: W=16 extension lands → refine pass at knee W with --threads-env {2,4}
→ RR concurrency sweep (threads-env 8; **the Ticket-4 idle-vs-M banner is
the headline the operator wants FIRST when it lands**) → DRY PASS →
**44-video campaign TONIGHT (DEFAULT_N=44, ~62 min — banked before the
corpus question resolves)** → alignment negotiation (Ansh, using Shashi's
checklist as the artifact).

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

**[SUPERSEDED NEXT — manifest adjudicated (abbreviation, values correct, no
re-cut); LI sweep done; the RR sweep invocation below is still the live one.]
NEXT (2026-08-21 late): adjudicate the manifest meta dump (targeted dump +
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

## ▶ SETUP STEPS THE DRY PASS SKIPPED (2026-08-22) — both one-time, both blocking

The campaign stopped at the smoke in 40.8 s, two failures, no legs run. Both are
setup artifacts that have never been created, and the dry pass structurally
could not have caught either: it passes `--skip-fixture` and writes a THROWAWAY
golden to `mainrun_<ts>/dry_golden.json`.

**1. THE PDF FIXTURE — the documents are NOT gone.** All five content-pinned
files are in the laptop corpus (`corpus/` is gitignored — provisioned per box,
never from git, which is why the box lacks them):
  d2a4eb9c41a0fabd  000_000159.pdf  expect 164 chunks   4,051,537 B
  2d6b5053716f4037  000_000595.pdf  expect 276          4,090,732 B
  bc44bd5e4103696b  000_000674.pdf  expect 1872         2,285,075 B
  f51fc895ceac979f  000_000762.pdf  expect 132          2,393,778 B
  f1c250fa02fa8e74  000_000887.pdf  expect 344          1,307,071 B
  total 14,128,193 B (13.5 MB). Expected counts: scripts/smoke_phase2.py:65.
FIRST check the box for the whole corpus (`ls ~/parity-bench/corpus/govdocs1/pdfs
| wc -l`); if present elsewhere, pass `--pdf-corpus <dir>` and copy nothing.
WITHOUT the fixture, section A proves ONLY that the label reads "1" — and
labels INHERIT through a derived build, so today's `rr:patched-video` carries a
label set two builds ago with nothing re-verifying the patch. The campaign's
video legs do carry `self_duplication_any` + `duplication_trigger` (a real
measured detector on the real workload), but they fire DURING a leg, have no
expected-count anchor, and NOT RUN is not a pass. `--skip-fixture` on a real
run is refused (operator, 2026-08-22).

**2. THE GOLDEN — sequencing matters more than the command.** It pins the
measured pipe's ENTIRE output for one video: `video_sha16`, `n_chunks`,
`frames_observed`, and the ORDERED `chunk_sha256` list, compared by exact
equality. Video: auto-selected as the SHORTEST measured manifest row
(smoke_video.py:451-456), so the smoke stays fast.
INVALIDATED BY: a different video file (sha16-checked, named explicitly);
anything altering the measured pipe's output — engine bytes on the
frames/detect/chunk path, model weights, the pipe file, ffmpeg/torch/rfdetr
versions; and PLAUSIBLY the thread configuration, since intra-op thread count
changes BLAS reduction order, which can flip a borderline detection, which
changes chunk text and therefore hashes.
NOT invalidated by today's derived layer: it replaced only
`working/nodes/env_probe/`, which is absent from the measured pipe, and every
layer beneath is byte-identical (RootFS-prefix proven). **A golden written now
is valid for this campaign.** PATH B (the full rebuild) WOULD invalidate it —
re-write it after any re-baseline.
SEQUENCING RULE: write it under the SAME container state the smoke will later
compare it under. run_plan's step 1 does `start_rr unset`, so the golden must be
written against an rr container started with NO thread env (torch 16, the
default posture). A golden written against a T=2 parity container is a latent
mismatch.
HARDENED before first write (2026-08-22): the golden now records
`written_under` = image_id, image_tag, declared_thread_env — so a future
mismatch reports whether the CONDITIONS moved (re-write) or did not (a genuine
REGRESSION), instead of leaving that ambiguous.

## ▶ THE FIXTURE INVERSION (2026-08-22) — OURS, Phase 2 only, and it failed CLOSED

All five fixture documents came back at EXACTLY half the constant, five for five
(82/138/936/66/172 vs 164/276/1872/132/344). **The constants are STOCK counts and
this smoke read them as patched ones.** Evidence, five independent ways:
1. The constant's own docstring (`scripts/smoke_phase2.py:63-64`): "The five
   documents measured as duplicating on stock 3.3.1 ... the chunk count
   observed, **for context only; the assertion is on repeat_factor**."
2. `PHASE1_CARRYOVER.md:224`: "five hard-coded PDF sha256 prefixes that
   **duplicated on the stock engine**."
3. Phase 1's gate (`smoke_phase2.py:147`) is `want = 1 if EXPECT_PATCH else 2`
   on **repeat_factor**; the count is stored as `chunks_when_measured` and
   never asserted.
4. MEASURED: 164 is the **rocketride_pdf** arm's count in
   `results/smoke50_parser_in__20260815T050721Z__7df4f23c86b7.json`
   (`data/arms/rocketride_pdf/records[32]`), a run dated 2026-08-15 — two days
   BEFORE the patch commit `61295e0` (2026-08-17). The llamaindex arm gave 75.
5. The bug emits the whole list twice, so patched == stock/2 exactly; observed
   exactly, five for five, all five stock counts even.

**PHASE 1 IS UNAFFECTED — its smoke was never inverted.** It gated on
repeat_factor in both directions (EXPECT_PATCH=0 wants 2, =1 wants 1) and never
compared counts, so no Phase 1 run ever passed because the engine was unpatched.
The inversion existed only in `working/video/smoke_video.py`, from the day it was
written, and **it has never passed** — it blocked the campaign rather than
certifying a wrong image. Failed closed, which is the safe direction, and it is
the reason the constants were NOT edited on the strength of the pattern alone.

**FIXED (smoke_video.py):** imports as `FIXTURE_STOCK_CHUNKS`, asserts
`2 * measured == stock`, and splits the two findings that used to share one
message — WHOLE-LIST DOUBLING means the patch regressed; an off-half count with
doubling ABSENT means the document or chunker moved, NOT a patch regression.
Nothing else in the tree asserted these values (only smoke_phase2 itself, which
is correct, and PHASE1_CARRYOVER's prose, which is correct).

**STOCK CONTROL — available, NOT required tonight.** Phase 1's tool already does
it: `EXPECT_PATCH=0 SMOKE_EXTERNAL=1 python3 working/scripts/smoke_phase2.py`
against a stock container expects repeat_factor 2 and reports a non-duplicating
result as a BROKEN FIXTURE, not as a needless patch. It needs a stock image:
`docker build -f docker/Dockerfile.rocketride --build-arg RR_DUP_PATCH=0
-t rr:stock .` — a FULL build (engine fetch + apt + pip + bootcheck constraints
compile, 10-30 min per the Dockerfile's own note) ≈ 25-45 min and several GB; no
vision bake needed, since the fixture uses the PDF pipe. Deferred to the PATH B
re-baseline, because the exact 2x relation against pre-patch measured counts
already discriminates "patch works" from "fixture broken": a broken fixture
would give arbitrary counts, not exactly half of five recorded stock values.

## ▶ CROSSROAD 34 (2026-08-22): ADOPT LEELA'S CORPUS — Closeup1, full scenario set

**Interference ruling for a fetch DURING a measured campaign — PARTLY confirmed,
binding constraint is different.** CPU reasoning holds: the quiet-box gate reads
`/proc/stat` busy = total − (idle **+ iowait**), so a network-blocked download is
invisible to it, and curl/TLS is a fraction of a core. **But the driver evicts
the corpus page cache before EVERY leg** (`drop_cache_fadvise`, fail-closed), so
each leg re-reads ~13 GB from EBS — a concurrent multi-GB write competes for the
same volume throughput, inflating read latency INSIDE the measured span, where
no CPU-based gate can see it. And the fetch's CPU phases (sha256 ≈1 core, ffmpeg
mux, and the 12 s/video frame decode ≈28 min of a core at 140 videos) WOULD
register as foreign load and can trip the next leg's preflight.
**SPLIT: Phase A (network only, rate-capped) is safe now; Phase B (verify, mux,
decode, manifest, probes) waits for the campaign to finish.**

**Prefer her STAGED files over re-fetching+re-muxing.** Her raw Closeup1 AVI is
video-only; `fetch_ami.sh:4-11` stream-copy muxes `Mix-Headset.wav` in. If we
re-mux ourselves the bytes may not match hers — different shas, different
manifest, and the alignment we are buying is exactly identical bytes across all
three arms. Pull her staged corpus; our manifest then sha-pins HER bytes.

**Code landed for the swap:** `fetch_ami_video.py --view Closeup1` (the view rule
is no longer hardcoded; Closeup1 is the only view in ES **and** IS **and** TS, so
it is the one that reaches the full set) and `--staged` (files named
`<meeting>.avi`, already muxed, **never downloaded** — an absent staged file is
a skip, never a silently-substituted raw camera file). `run_plan.sh` no longer
computes `MEASURED_N=$((60 - WARM_N))`: both counts now come from the manifest,
and WARM_N must match the manifest's warm rows or the run refuses.

**The nine numbers at ~140 (124 measured + 16 warm):** M_TOKENS=16 ·
RR_THREADS_ENV=2 · LI_WORKERS=8 · LI_THREADS_ENV=4 · WARM_N=16 · BLAST_C=16 ·
PASSES=2 · DEFAULT_N **and** LIVENESS_MIN + GATE3_RUN_ID re-derived. BLAST_C
stays 16 (124/16 = 7.75 waves, ample window depth). **DEFAULT_N: the LETTER of
Crossroad 27 says the full 124 (the subset rule triggers above ~1000 videos),
but its REASON argues for 44** — the default posture is ~3.5x slower than parity,
so 124 costs ~75 min/pass against parity's ~20, i.e. ~1.7 h extra for a finding
that is a RATIO. Recommend DEFAULT_N=44 (directly comparable to tonight's).
Ansh's call.

**LI ARM IS OURS ALONE — its budget line re-runs on Closeup1, not carried.**
And by register entry 12 the RR side gets the SAME treatment or we repeat the
asymmetry we just audited: spot-check the RR budget line on Closeup1 too
(~25 min) and re-run only if a point moves.

## ▶ CAMPAIGN COMPLETE (2026-08-23) — the three findings that go to Monday

**1. SPAN vs STEADY WINDOW REVERSES THE WINNER.** Same run, same records:
  span:          LI 8.952  RR-parity 9.826   -> RR +10%
  steady window: LI 8.491  RR-parity 7.995   -> LI +6%
Span absorbs the drain tail; the window measures the saturated interval. Leela
reports span only (`v_metrics.py:22-42`), so this is a BASIS DIFFERENCE to name
up front, not a correction to anyone. Three people otherwise compare three
different quantities and reconcile nothing.

**2. LI REPETITION NOISE IS LARGE.** pass1 vs pass2 on the LI arm: **5.4% on
span, 21% on the steady window** (8.491 vs 7.025 frames/s). RR passes agree to
0.3-2.3%. **A cross-arm difference under ~5% on the LI arm is not
distinguishable from repetition noise on this evidence** — and the steady window
is the noisier statistic on that arm, which is exactly where a reader would
reach for precision. This supersedes the 1.3% probe-rep figure recorded earlier.

**3. char_conservation 0.0208 vs tol 0.02 — REAL, EXPLAINED, NOT AN ARTIFACT.**
Diagnosed from code, ruling out every serialization candidate:
* `_to_detection` is byte-identical on both arms — same conversions, same key
  order, same centroid arithmetic (`engine/.../detection.py:69-77` vs
  `li_video/pipeline.py:70-76`), both serialized by `json.dumps` with defaults.
* Neither arm skips empty frames (RR `nodes/detect/IInstance.py:76-77`
  unconditional; LI `pipeline.py:186-193` unconditional).
* No resize on either side: `resize_for_inference` is a documented NO-OP below
  the 560 edge and our frames are 352x288, so coordinates are never scaled or
  mapped back.
* **The source text is identical in length by construction.** The engine
  accumulates `self.text += text + '\n'` per frame and splits ONCE in
  `closing()` (`preprocessor_langchain/IInstance.py:82-88`) = sum + n_frames;
  our LI arm does `'\n'.join(per_frame_json) + '\n'` = sum + n_frames.
**What remains is the SPLITTER, and the difference is deliberate.** Both are
nominally 4000/200 (`li_video/service.py:39-40`; RR falls to LangChain defaults
per Ticket 3), but RR runs `RecursiveCharacterTextSplitter` and the LI arm runs
LlamaIndex-native `SentenceSplitter` — approved decision 3, because forcing
LangChain's splitter onto the LI arm would benchmark our port rather than the
framework. Two native splitters on byte-identical input produce different chunk
boundaries: **the 24% chunk excess and the 1.8% char difference are the same
phenomenon, not two.** The gate is reporting a real, chosen difference.
**DO NOT widen the tolerance.** State it in the report. Confirm the mechanism in
one command (chunk-size distributions should be bimodal on RR, packed near 4000
on LI):
  cd ~/parity-bench-video && ~/.venv/bin/python -c "
  import json,glob,statistics as st
  for f in sorted(glob.glob('working/video/results/mainrun_*/records_*blast*.jsonl')):
      cs=[c for l in open(f) for c in (json.loads(l).get('chunk_chars') or [])]
      if cs: print(f\"{f.split('/')[-1]:52s} n={len(cs):5d} mean={st.mean(cs):7.1f} median={st.median(cs):7.1f} min={min(cs):5d} max={max(cs):5d}\")
  "
RESIDUAL, stated: gate 3 compares label multisets only, so score/box float reprs
are not proven equal by it. If the splitter accounts for less than the full
1.8%, the remainder is float repr and the same command's char totals bound it.

## ▶ CROSSROAD 38 + gate-3 triage + Phase B sharpening (2026-08-23)

**CROSSROAD 38 — the video band is MEASURED and CENTRED, not widened.**
`working/video/probe/char_band_from_records.py`. Anchoring at 1.0 was already
wrong once the splitters differ: the ratio has a SYSTEMATIC offset (~0.982) that
is a splitter property, not content loss, so a band around 1.0 spends its whole
width measuring the offset. The band is therefore centred on the MEASURED median
ratio with a half-width of `margin x worst per-video deviation FROM THAT CENTRE`
— never a number chosen to make a known result pass. The tool refuses to propose
a band when fewer than 5 videos pair, and **refuses outright if the resulting
band could not notice several whole frames going missing** ("the band is wrong").
It prints the sensitivity it buys in chars, detections and frames, and the
export must name the calibrating run beside the band. PDF band stays 2%.
Command (after the campaign's records):
  cd ~/parity-bench-video && ~/.venv/bin/python working/video/probe/char_band_from_records.py \
    working/video/results/mainrun_<ts>/records_rocketride_video_parity_blast.jsonl \
    working/video/results/mainrun_<ts>/records_llamaindex_video_workers_blast.jsonl \
    --dpf 25.95 --chars-per-det 230.4 --run-id mainrun_<ts>
On a shape matching the campaign (median 0.982, per-video spread 0.0066) it
yields a band of ~[0.9766, 0.9872] that still trips on **~0.7 frames** of lost
content per video — strictly MORE sensitive than the old +/-2% around 1.0, which
would have needed 2.34% and only caught ~2.9 frames.

**GATE 3 — why the grep found nothing, and the exact extraction.**
`diverging_frames` is nested at `.cross_detection_agreement.per_video.<video>`
and `json.dumps(indent=1)` puts the list on the FOLLOWING lines, so a line-based
grep cannot see it. Also: `.cross_detection_agreement.score_triage_first_failure`
is ALREADY COMPUTED in the file, for the first failing video only.
`working/video/probe/gate3_triage.py` answers the real question — score_triage
compares only frames whose detection COUNTS match, so a flapped frame is excluded
from its paired deltas and merely counted, which never says WHICH detection or at
what score. The tool prints, per diverging frame, the label-multiset symmetric
difference and the scores present on one arm only, with each score's distance to
the 0.3 threshold. Exercised on a planted 0.301 flap: reported NEAR-THRESHOLD at
distance 0.001. DIAGNOSTIC ONLY — gate 3 stays FAILED until a human downgrades
it in writing, and the first hypothesis remains a real difference.
  cd ~/parity-bench-video && ~/.venv/bin/python working/video/probe/gate3_triage.py \
    working/video/results/mainrun_<ts>/cross_parity_blast.json \
    working/video/results/mainrun_<ts>/records_rocketride_video_parity_blast.jsonl \
    working/video/results/mainrun_<ts>/records_llamaindex_video_workers_blast.jsonl

**DETERMINISM, stronger than the repeat gate produces:** RR default vs parity
char totals 32,539,271 vs 32,539,839 — **568 chars apart over 10,417 chunks
(0.0017%) at DIFFERENT thread counts**. That is a cross-configuration
determinism result the repeat gate cannot produce, and it belongs in the report.

**PHASE B SHARPENING — collapse the 170-video RR-default bracket from the
campaign's own records:**
  cd ~/parity-bench-video && ~/.venv/bin/python -c "
  import json, glob
  for f in sorted(glob.glob('working/video/results/mainrun_*/records_rocketride_video_default_blast*.jsonl')):
      fr = w = 0
      for l in open(f):
          r = json.loads(l)
          if 'error' in r: continue
          fr += r.get('frames_observed') or 0; w += r.get('wall_s') or 0
      if w: print(f\"{f.split('/')[-1]:56s} frames={fr:6d} sum_wall={w:8.1f}s -> {fr/w:5.2f} f/s\")
  "
Then: **170-video default blast wall = 23,691 / (that f/s) seconds per pass**,
x2 passes. The bracket was 2.31-4.83 f/s = 164-342 min for two passes; this
replaces it with one number. NOTE the sum-of-wall form measures SERVICE rate at
the leg's concurrency, which is what the next leg will reproduce.

## ▶ CROSSROADS 38 + 39 CLOSED (2026-08-23), and the sharpening command was WRONG

**HUMAN DOWNGRADE, RECORDED AS REQUIRED.** *The three diverging frames in
`mainrun_20260823T034243Z` `cross_default_blast` are float reduction-order
flapping at the 0.3 detection threshold — evidenced by one 'chair' each, lowest
unmatched scores 0.3000 / 0.3001 / 0.3227, and PARITY passing clean at torch=2
while DEFAULT fails at torch=16. Downgraded by Ansh, 23 Aug 2026.*
The posture split is the proof: same arms, same videos, same model, same
corpus — only the thread count differs. More BLAS reduction partitions, more
summation-order variance, and a detection sitting at 0.3000 crosses the cut.
Three frames in ~5,600 (0.054%), and only at high thread count.

**CROSSROAD 39 — BOUNDARY EXCLUSION, NOT TOLERANCE. LANDED.**
`gates_shared.label_multiset_agreement` now excludes frames whose ONLY
divergence is attributable to detections within +/-0.001 of the threshold, and
COUNTS them; the multiset comparison stays EXACT. A model swap moves scores far
from 0.3 and still fails; DRIFT fails too — exclusions above 0.5% of frames FAIL
the gate with "that is DRIFT, not flapping". The count is surfaced at the top of
the cross file (`boundary_exclusions_total`) and in `at_a_glance`, so it can
never be silent. **No general tolerance was added.** Five controls fired: 3
flaps/1000 frames passes with 3 counted; the same 3 at 0.87 FAIL; 20 flaps/1000
FAIL as drift; 0.3011 (just outside eps) FAILS; absent scores preserve the exact
comparison.
IMPLEMENTED AT FRAME LEVEL, deliberately: records carry labels SORTED and scores
in ORIGINAL order, so they are not index-paired, and per-detection exclusion
would need a new field on both arms — i.e. an `li:video` REBUILD, whose serving
stack is UNPINNED at build. Changing the LI substrate hours before the
full-corpus run costs more than the marginal precision. A frame is excluded only
when EVERY unmatched score on BOTH arms is within eps, so a frame carrying a real
difference alongside a flap still fails. Add `frame_dets` (paired label+score)
at the next natural LI rebuild.

**gate3_triage.py CORRECTED — its verdict line was wrong about its own data.**
When counts differ, the multiset difference of the SCORE lists returns every
unpaired score in the frame, most belonging to detections both arms agree on.
Judging on all of them printed "NOT all near threshold" for a genuine flap. The
verdict now uses the score CLOSEST to the threshold — the only candidate for the
detection that crossed it — and reports BOUNDARY FLAP at <=0.001. Re-exercised
on the campaign's shape (one 'chair', 0.3001): "BOUNDARY FLAP — within 0.001".

**CROSSROAD 38 — BAND ACCEPTED: [0.97374, 0.98963]**, centred, calibrated on
`mainrun_20260823T034243Z`, catching ~1.0 frame of content loss where anchoring
at 1.0 would have needed 2.63% and caught only 3.3 frames. The export names the
calibrating run beside the band. PDF band unchanged at 2%.

**THE SHARPENING COMMAND I GAVE WAS WRONG — my error.** Summing per-video
`wall_s` across a C=16 blast counts overlapping wall clock up to 16 times, which
is why it read 0.16 f/s against the leg's own AT A GLANCE of 2.402 — a ~15x gap
that is the concurrency, not a measurement. **Use the leg's SPAN rate**
(`throughput.total_frames_per_s` in the export, i.e. frames / leg_wall_s):
  cd ~/parity-bench-video && ~/.venv/bin/python -c "
  import json, glob
  for f in sorted(glob.glob('working/video/results/mainrun_*/export_rocketride_video_default_blast*.json')):
      d = json.load(open(f)); t = d['throughput']
      print(f\"{f.split('/')[-1]:56s} frames={t['total_frames']:6d} span={d['leg_wall_s']:8.1f}s -> {t['total_frames_per_s']:5.3f} f/s\")
  "
**Arithmetic confirmed at 2.402 f/s:** 23,691 / 2.402 = 9,863 s = **2.74 h per
default pass, 5.48 h for two**. Campaign total: LI blast x2 71 min + RR parity
blast x2 61 min + RR default x2 329 min + sequential/warm/setup ~50 min =
**~8.5 h**. DEFAULT_N=168, no shortcuts, launched tonight, finishing overnight.

## ▶ THREE CORRECTIONS BEFORE LAUNCH (2026-08-23) — relayed summaries that do not match the code

Recorded because two of them would enter Monday's report as false statements
about a teammate's setup, which is the class of error that costs trust.

**1. THE THRESHOLD IS *NOT* NESTED ON BOTH SIDES.** Hers is at TOP LEVEL:
`{"profile":"rfdetr","threshold":0.3}` (`aws_videobench/pipe/benchmark_video_detect.pipe`);
ours is nested. Her key IS silently discarded — `ai/common/config.py:196` reads
only `connConfig[profile]`. The EFFECT is identical only because the rfdetr
profile carries its own `"threshold": 0.3` (`nodes/detect/services.json:40`).
**Correct statement: different shape, identical effective sensitivity, both
0.3.** Saying "correctly nested on both sides" would be false about her pipe and
would also hide the real hazard — a NON-default top-level value silently reverts.

**2. THERE IS NO OpenCV ANYWHERE — the frame-extraction asymmetry as described
does not exist.** All three arms shell out to ffmpeg: the engine via
`imageio_ffmpeg.get_ffmpeg_exe()` (`ai/common/avi/reader.py:5,229`), our LI arm
via the same call (`li_video/pipeline.py:104-105`), and HER LangGraph arm via
`shutil.which("ffmpeg")` falling back to `imageio_ffmpeg.get_ffmpeg_exe()`
(`arms/langgraph/workload/frames.py:21-26`). Our LI arm pays no spawn/pipe cost
that her arms do not. **Do not publish a self-penalising caveat that the code
does not support.**
A REAL and different observation, stated neutrally: her LangGraph container
apt-installs the distro ffmpeg (`arms/langgraph/Dockerfile:6-8`) and prefers
`shutil.which`, so HER two arms may resolve different ffmpeg builds, while OUR
two arms both resolve imageio-ffmpeg's bundled static build. That is a caveat on
cross-arm frame identity within her pair, not within ours.

**3. WARM_N=32 WILL NOT LAUNCH — the accepted value is 2.** `run_plan.sh:260-265`
REQUIRES `WARM_N == the manifest's warm row count`, and ami_full's split is
168/2, so WARM_N=32 exits immediately with "the manifest carries 2 warm rows".
The 16-token coverage concern is real and is already solved by Crossroad 32 in
the DRIVER, not by WARM_N: with 2 warm rows and 16 tokens the driver sends
`first_batch = warm[:min(2, 32)]` = 2, then RE-SENDS rows cyclically under a
budget of `2*max(16,2) = 32` until every token has served — 14 top-ups, well
inside budget, and the coverage assert still fails closed if any token is unseen.
**WARM_N is the size of the warm SET, not the number of warm SENDS.**

**LI W=16 STARVATION — SECOND INSTANCE, recorded so it is not rediscovered.**
Closeup1 W=16/T=2: serving 15/16, throughput 0.1473 -> 0.0913, **CPU FELL
0.858 -> 0.358 while wall went 217s -> 701s**. Corner's 6-of-8 at W=8 resolved to
routing luck under a bigger batch and showed NO CPU collapse; this one does.
"A worker fails to draw work at high W" has now appeared TWICE on the LI arm,
and only the high-W instance carries the starved signature (wall up, CPU down,
all workers alive). Not blocking: W=8 is the chosen point and served 8/8 clean.

## ▶ B7 STAGED ON THE WRONG VIDEO (2026-08-23) — cause, fix, and DO NOT USE probe_20260823_110344

**The `VIDEO=` override DID work** (`probe_run.sh:16`, `VIDEO="${VIDEO:-…}"` —
verified by reading the file back). The probe steps ran on the Closeup1 video.
**The GATE-3 COMPARISON did not.** It selected its inputs with
`sorted(glob.glob('probe_rr_t*.json'))[-1]` — a LEXICOGRAPHIC sort, so with
`t1/t2/t32/t8` on disk from the Corner probe it returns **`t8`**. The fresh
`t2` Closeup1 artifacts were written and then ignored; the block compared two
stale Corner files and reported 83 frames on ES2002a. The banner also HARDCODED
"on ES2002a", so it agreed with itself.

**`GATE3_RUN_ID=probe_20260823_110344` IS VOID.** It would assert the arms
agreed on ami_full when they agreed on Corner. Do not use it.

**FIXED, three ways:**
1. Inputs are named from the matrix point this run produced
   (`LAST_T` = last value of `$MATRIX`), never a glob.
2. **Both arms must record the SAME video, and it must be the one this run was
   pointed at** — the comparison recomputes the sha16 of `$VIDEO` and refuses on
   mismatch: *"STALE ARTIFACT — an arming id from it would assert agreement on
   the wrong corpus."* `probe_li_floor.py` now records `video` + `video_sha16`
   (it recorded neither, which is why nothing could catch this).
3. The banner prints the ACTUAL video basename and the thread point.
Behaviourally verified: correct pairing passes; a t8 pair from another video is
REFUSED with rc=1; a missing matrix point is refused rather than silently
globbed.

**B7, RE-RUN (floor venv):**
  cd ~/parity-bench-video/working/video/probe && \
    VIDEO=~/parity-bench-video/corpus/ami/video/ES2009a.avi PROBE_MATRIX=2 ./probe_run.sh
Read back BOTH lines before using the id:
  `GATE-3 STAGED CONFIRMATION: cross-arm label multisets on ES2009a.avi (t=2)`
  `gate-3 staging: both arms confirmed on ES2009a.avi (sha16 …, t=2)`
  then `EXACT agreement on N frames` with **N ≈ 93** (not 83 — 83 is Corner).
The run id is the log stem `probe_YYYYMMDD_HHMMSS` printed at the top.

## ▶ GATE 4 FAILED ON A STALE COMPARATOR (2026-08-23) — three defects, all fixed

Your root cause is exactly right, and there was a third defect underneath it.

1. **`probe_frame_identity.py:71` used the SAME lexicographic glob** —
   `sorted(glob('probe_li_floor_t*.json'))[-1]` returns **t8**, so it loaded a
   two-day-old Corner floor (83 frames of ES2002a) and compared it against 93
   fresh ES2009a engine hashes. It reported a gate-4 FAILURE for a decode that
   was correct.
2. **It never checked WHICH VIDEO produced the floor it loaded.** Nothing could
   have caught this: `probe_li_floor.py` recorded no `video` field at all until
   today's fix, so the comparator had nothing to assert against.
3. **The post-matrix compare step the deferred branch PROMISES did not exist.**
   `probe_frame_identity` is invoked exactly once (`probe_run.sh:65`), before the
   matrix; its `deferred` reason says "the post-matrix compare step finishes gate
   4 from this file without a resend" — there was no such step, so a deferred
   gate 4 could never complete.

**FIXED:**
* The identity step now selects a floor **by video identity, not by sort order**:
  only a floor whose recorded `video_sha16` equals THIS video's is usable. Others
  are NAMED and rejected (`floor_rejected` in the report, incl. `ABSENT
  (pre-2026-08-23 floor)` for files with no video field). With `--no-floor-ok` it
  DEFERS instead of comparing — which is what the flag always claimed to mean.
  Without it, it refuses with the named mismatch.
* **The post-matrix gate-4 compare now exists** (`probe_run.sh`, before the
  gate-3 block): it finishes gate 4 from the early file's saved engine hashes
  plus today's matching floor, **without a resend**, and refuses if either side
  carries a different video sha. Writes `probe_frame_identity_final.json`.
* Ordering concern answered by the defer, so the early step still runs first and
  can still catch a decode problem before the matrix is spent.

Behaviourally verified: stale Corner floor → REFUSED rc=1 with the two shas
named; today's matching floor → PASS on 93 frames, no resend; selection picks
the matching floor where the lexicographic last would have picked t8.

**B7 RE-RUN (floor venv). This is the invocation that produces a usable id:**
  cd ~/parity-bench-video/working/video/probe && \
    VIDEO=~/parity-bench-video/corpus/ami/video/ES2009a.avi PROBE_MATRIX=2 ./probe_run.sh
**Four lines to read back before the id is used:**
  1. `GATE-4 POST-MATRIX COMPARE: engine vs LI floor, both on ES2009a.avi`
  2. `gate-4 compare: PASS — 93 frames byte-identical`
  3. `GATE-3 STAGED CONFIRMATION: ... on ES2009a.avi (t=2)`
  4. `gate-3 staging: both arms confirmed on ES2009a.avi (sha16 …, t=2)`
     then `EXACT agreement on N frames`, **N = 93**.
Any line naming ES2002a or 83 frames means a stale artifact was reached again —
do not arm. The id is the log stem `probe_YYYYMMDD_HHMMSS`.
NOTE: the existing `probe_li_floor_t2.json` (today, 11:08, wrong video) and
`t8` (Corner) both predate the `video_sha16` field, so both are now REJECTED by
name rather than silently used; `preserve()` moves the t2 file aside before the
re-run writes its own.
