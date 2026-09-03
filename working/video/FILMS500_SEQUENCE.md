# FILMS-500 — the prep-to-run sequence (2026-09-03; no legs run yet)

Every box action goes through `working/harness/box.sh` (sha printed each
run); **the wrapper transcript (`~/.rocketride_box/transcript_<day>.log`)
is the evidence surface** — figures are quoted from it. All scripts are
committed with self-printed sha256 (entry 25). Ansh's scope ruling for
the run itself (cells, passes, arming) arrives separately — nothing below
starts a leg.

| # | step | how | mark |
|---|---|---|---|
| 0 | Box up + repo current | `box.sh run --start 'git -C ~/parity-bench-video pull --ff-only'` | **STOP** — read the printed HEAD; must be this commit |
| 1 | Fetch the 500 (~252 GB; ~35 reused by hardlink) | `box.sh launch fetch500 'bash ~/parity-bench-video/working/video/probe/fetch_films500.sh'` then `box.sh tail fetch500` | safe-to-chain into 2 only after its census line reads `verified=N/N … MISMATCHED=0`; **WALK-AWAY POINT** (hours; detached; nothing else pending) |
| 2 | Cut the 500 manifest (decode pass, P=12; null control = the 35 knowns must reproduce the committed subset manifest EXACTLY or it refuses) | `box.sh launch manifest500 'bash ~/parity-bench-video/working/video/probe/build_films500_manifest.sh'` then `box.sh tail manifest500` | **STOP** — read the census (n=500, total_frames, footage h) and the null-control line; **WALK-AWAY POINT** (~0.5–2.5 h, self-calibrating timing lines) |
| 3 | Land the manifest | box commits `films500_video_manifest.jsonl` → entry-26 bundle → laptop lands | **STOP** — laptop verifies (census re-read from the landed file) |
| 4 | LI ceiling | already LANDED laptop-side this round: `LI_HTTP_TIMEOUT_S = 43200` (driver_video.py, both the urlopen call and the provenance record; sizing math in the constant's comment) — reaches the box via step 0's pull | done |
| 5 | Scope ruling | Ansh rules cells / passes / arming / liveness basis | **STOP** by definition |
| 6 | Build `run_plan_films500.sh` to the ruling (+ staging analog per the §10.4 arming lesson: the staged same-frames set must span BOTH sides of 560px) | laptop build round after the ruling | **STOP** before first paste |
| 7 | Campaign, with the mirror beside it | `box.sh launch mirror500 'bash …/probe/mirror_films500.sh <run_dir>'` then the plan; mirror syncs records/exports/consoles every 300 s to `s3://…/ansh/films500-live-<stamp>/`, corpora never | run-round rules apply |

**Sizing facts this sequence stands on** (sources: Leela's committed
films500 per_doc @3967d9f4; our landed films-35 records; box reads via the
wrapper 2026-09-03):

- Corpus: 500 files, 281.4 GB, 674.75 h footage; longest film 11,314 s
  (188.6 min), largest file 2.19 GB. Box disk measured: 969 GB volume,
  **839 GB available** before fetch → ~587 GB after, with worst-case C=16
  spool transients (~60 GB: 16 × spooled video + 16 × on-disk frame dirs)
  comfortably inside. 32 cores, idle.
- Per-film walls, measured on films-35 (max s per film-minute): LI 16×2
  **11.7**, RR 16×2 **8.2**, RR default **27.5**. Her LG c32 max wall on
  the 500 was 2,332 s. Projected worst single film: LI 16×2 ≈ 2.2 ks;
  RR default ≈ 5.2 ks; an LI-DEFAULT queued blast can approach leg span
  (~6.4 h pessimistic) — hence `LI_HTTP_TIMEOUT_S = 43200` (2× that,
  ~20× the 16×2 worst, half her 86,400 whole-run envelope).
- Decode pass: one measured anchor (House: 3,719 s footage in 26.75 s =
  ~139× realtime, single process) → ~25–40 min at P=12, envelope
  0.5–2.5 h for slower 1080p prints; the script's per-film timing lines
  calibrate it live.
- OOM class: her LG died at 97/498 from whole-film frames in RAM +
  buffered uploads (post-mortem, her commit 2d7533b). Our LI lane is
  immune BY MECHANISM: frames on disk with k=1 bounded residency
  (pipeline.py:77, :176, :206-207, :249-253), streamed uploads with
  file-object body + Content-Length (driver_video.py Ruling-4 block),
  service spools via request.stream(). No path on our LI lane holds a
  whole film's frames in memory; the whole-film footprint is DISK
  (spool + frame dirs), counted in the headroom above. The engine side
  parses frames streaming (frame.py iend_walk; parser_max_buffer ≈ one
  frame, parity artifacts) and caches video to disk.
