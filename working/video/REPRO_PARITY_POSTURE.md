# Reproduction spec — RocketRide PARITY posture on ami_full

**For: Leela. From: Ansh's WS-1 harness (branch `video-bench`).**
Purpose: reproduce, on your own harness, the multi-token result that recovers
RocketRide from the ~6-core ceiling your Run C measured. Your RR blast number
and our default posture agree to 0.1% on the byte-identical corpus (your 2.44
f/s, our 2.443 [RELAYED]) — this spec is the delta that turns that number into
~12.7 f/s on the same box, same corpus, same engine.

Evidence discipline: every value is tagged **[SOURCE file:line]**, **[COMMIT
sha]**, or **[RELAYED]** (read off our box by the operator; the run's exports
are NOT on the machine this spec was written on — re-derive them from the
export files named in §1 before quoting anything as measured). Anything about
YOUR harness that we inferred rather than read is flagged **[INFERRED]**.

---

## THE DELTA AT A GLANCE — exactly two knobs differ from the default posture

| knob | default posture | parity posture | where it lives |
|---|---|---|---|
| **1. tokens** | 1 × `use()` | **16 × `use()`, each with a DISTINCT `project_id`** | client (16 calls) + pipe json (fresh `project_id` per token) |
| **2. six-var BLAS/OMP env** | **unset** (engine default) | **all six = 2** | container `docker run -e` |

Everything else is IDENTICAL between the two legs: same engine, same image,
same corpus and order, same `ttl=0`, same `use()` shape (no `threads=` in
either — see §2), same C=16 client concurrency, same chunked 1 MiB writes,
same warm-up policy, same cache eviction. The 5.2× is those two knobs.
Per-token the engine still holds ~6 cores; sixteen tokens hold ~29 of 32
[RELAYED: service CPU 91.6%/92.1%].

---

## 1. The claim, precisely stated

On ami_full (168 measured + 2 warm, your set file, byte-identical corpus,
170/170 sha-verified), n=168, client concurrency C=16, chunked 1 MiB writes,
one pass = one full corpus:

| leg | frames/s span (p1 / p2) | service CPU of 32 |
|---|---|---|
| RR default (1 token, env unset) | **2.443 / 2.446** [RELAYED] | 18.8% [RELAYED] |
| RR parity (16 tokens, six-var=2) | **12.729 / 12.753** [RELAYED] | 91.6% / 92.1% [RELAYED] |

Steady-window parity: 12.755 / 12.796 [RELAYED]. **UNVERIFIED at write time:**
these numbers were relayed from the box console; the authoritative values are
in `working/video/results/mainrun_20260824T025550Z/export_rocketride_video_{default,parity}_blast_pass{1,2}.json`
(key `at_a_glance`, and `throughput.span` / `throughput.steady_window`). Extract with:

    python3 -c "import json,glob; [print(json.load(open(f))['at_a_glance']) for f in sorted(glob.glob('working/video/results/mainrun_20260824T025550Z/export_rocketride_*.json'))]"

What varies between the two legs: §THE DELTA (two knobs). What is held
constant: engine 3.3.1 patched (extracted-ELF sha `95768e26…9747`, verified
identical to yours — `RR_ARM_CODE_DIFF.md` §9), image `rr:patched-video`
[lineage string travels in every export as `image.lineage_declared`], corpus +
order (your `ami_full.txt`, positional split 168+2), interval 1 frame/15 s,
RF-DETR thr 0.3, 4000-char chunks, C=16, `ttl=0`, chunked writes, warm-up,
cache eviction, box (c7i.8xlarge-class, 32 vCPU).

## 2. The config delta, exhaustively

Per-parameter, with where each is set:

| parameter | default leg | parity leg | set on |
|---|---|---|---|
| token count | 1 | 16 | client — 16 `use()` calls [SOURCE driver_video.py, RRArm.start] |
| `project_id` | 1 fresh | **16 fresh, distinct** (uuid5 over tag+pid+time_ns, stamped into a per-token copy of the pipe json) [SOURCE driver_video.py `generate_task_pipe` / probe_rr.fresh_project_pipe] | pipe json |
| `use()` args | `filepath=<pipe>, ttl=0` | `filepath=<per-token pipe>, ttl=0` — **`threads=` NOT passed in either leg** (`--threads` defaults unset; `kwargs['threads']` only when explicitly given) [SOURCE driver_video.py RRArm.start: `kwargs = dict(filepath=str(path), ttl=0)`] | client |
| OMP_NUM_THREADS, MKL_NUM_THREADS, OPENBLAS_NUM_THREADS, VECLIB_MAXIMUM_THREADS, NUMEXPR_NUM_THREADS, TORCH_NUM_THREADS | **absent** | **all = 2** | container `-e` [SOURCE run_plan.sh `thread_env_args`] |
| in-process torch (read back per leg, fail-closed) | 16 [RELAYED] | 2 [RELAYED] | measured, not set — env_probe node in the task process |
| blast concurrency | C=16 semaphore | C=16 semaphore | client [SOURCE driver_video.py run_leg] |
| ttl | 0 ("run until explicitly stopped"; terminate in `finally`, retried) | same | client `use()` [COMMIT Crossroad 43] |
| write path | chunked 1 MiB per `pipe.write` | same | client [COMMIT 58f2bb3] |
| warm-up | 2 warm rows re-sent round-robin across tokens until every token served (default: trivially 1) | same policy, 16 tokens covered by construction (driver-addressed round-robin) | driver [SOURCE run_warmup] |
| cache eviction | corpus evicted via `posix_fadvise(DONTNEED)` + behavioral proof before the leg | same | driver preflight [SOURCE driver_video.py "settled decision 4" block] |
| container run flags | `--memory 58g --log-opt max-size=200m --network host` | same **plus** the six `-e` vars | docker |

Copy-pasteable, exactly as our overnight ran them [SOURCE overnight_rr.sh]:

**Default leg:**

    docker run -d --name rr --memory 58g --log-opt max-size=200m --network host rr:patched-video
    python3 working/video/driver_video.py --arm rocketride --posture default --leg blast \
        --n 168 --blast-concurrency 16 --rr-threads-env unset --pass 1 \
        --image-lineage "<verbatim from banked export>" --out-dir <run dir>

**Parity leg:**

    docker run -d --name rr --memory 58g \
        -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
        -e VECLIB_MAXIMUM_THREADS=2 -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2 \
        --log-opt max-size=200m --network host rr:patched-video
    python3 working/video/driver_video.py --arm rocketride --posture parity --leg blast \
        --n 168 --blast-concurrency 16 --tokens 16 --rr-threads-env 2 --pass 1 \
        --image-lineage "<verbatim from banked export>" --out-dir <run dir>

(`--rr-threads-env` is the DECLARED expectation the driver reads back
fail-closed from the task process; it does not set anything.)

## 3. What to change on YOUR harness (`aws_videobench/bench/bench_video.py`, branch `aws-bench`)

Your current shape [SOURCE, your repo @ the aws-bench head we cloned
2026-08-24]: one client (line 256), one `use(filepath, use_existing=True,
ttl=RR_PIPE_TTL_S)` (lines 259-262), blast = one `send_files` over the whole
corpus (line 294).

**The `use_existing=True` trap — this is the part that will silently void the
run.** The engine derives the task token from `(userId, project_id, source)`
[SOURCE engine task_server.py:1073-1080] and `useExisting` makes a second
`use()` with the same identity **return the existing task** instead of
creating one [SOURCE task_server.py:1120-1129; SDK default is
`use_existing=None`→False, mixins/execution.py:101,253-254]. Your pipe file
has one fixed `project_id`, so 16 `use(use_existing=True)` calls = **16
handles onto ONE task process** — the default posture wearing a parity label,
and it would REPRODUCE 2.44, not 12.7.

M=16 for you, minimally:
1. Build 16 copies of your pipe json, each with a **distinct `project_id`**
   (any fresh uuid per copy).
2. 16 × `use(filepath=<copy_i>, ttl=<yours>)` — **drop `use_existing`** (or
   pass False). Collect 16 tokens.
3. Distribute sends across tokens round-robin. Your `c<N>` mode (line ~318,
   `sem = asyncio.Semaphore(offered)`) is the natural host: `mode=c16`, and
   inside `one(video)` pick `token = tokens[i % 16]` instead of the single
   token. One `send_files` per video per token (your existing per-item call at
   line ~327) keeps your write path unchanged. Blast-mode `send_files(all,
   one_token)` cannot express M=16 without splitting the corpus 16 ways —
   the c16 route is smaller and matches our C=16 shape exactly.
4. Container: add the six `-e` vars =2 to your RR `docker run`.
5. ttl: yours (93,600) is fine for one pass; our ttl=0 is not required for
   the result [the ttl class matters only past your sizing — your own
   2026-08-23 preflight note already covers it].

## 4. Code changes we made — and why they do NOT explain the gain

- **[COMMIT 4ea3e41]** read-residency: our driver had read each 248 MB payload
  synchronously on the event loop before the admission semaphore; fixed to
  read inside the semaphore via a worker thread, ≤C blobs resident. Fixes a
  CLIENT-side loop-starvation defect; changes when bytes are read, not what is
  measured (admit→done stamps unchanged). **Your equivalent:** your blast mode
  never reads payloads on the loop during the span — `send_files` streams
  1 MiB reads inside the SDK, and your per-doc `sha256(video.read_bytes())`
  happens in `records_from_batch` after the span [SOURCE your bench_video.py:
  base_record line ~76, called post-span in blast]. Your `c<N>` mode DOES call
  `base_record` (full read+sha) inside `one()` on the loop [SOURCE line ~322]
  — same class we fixed; at your payloads it has not visibly bitten
  [INFERRED from your clean runs, not measured].
- **[COMMIT 58f2bb3]** chunked writes: our `send()` previously wrote each
  video as ONE ~248 MB DAP message; 16 concurrent jumbo frames killed the
  shared websocket. Now N × 1 MiB `pipe.write` requests — **your
  `send_files` shape, which already chunks at exactly this size** [SOURCE SDK
  mixins/data.py:551]. This adds ~237-238 request/response round-trips per
  248 MB video *inside* our wall_s — **overhead direction: against
  RocketRide**. Neither commit adds parallelism, tokens, or thread
  configuration; both remove client-side failure modes. The 5.2× is §THE
  DELTA, not these.

## 5. Verification read-backs (what makes the result checkable)

1. **16 distinct task processes** (not 16 handles onto one):
   `docker exec rr ps -eo pid,ppid,rss,args | grep -c node.py` → **16** on the
   parity leg, **1** on default [mechanism: one task subprocess per token,
   SOURCE probe_rr.task_process_census + engine task_engine.py:1561]. Also
   assert 16 DISTINCT `project_id`s in your 16 `use()` results.
2. **Six-var env reached each task process, in-process:**
   `docker exec rr sh -c 'for p in $(pgrep -f node.py); do tr "\0" "\n" </proc/$p/environ | grep -E "^(OMP|MKL|OPENBLAS|VECLIB|NUMEXPR|TORCH)_"; done'`
   → every process shows all six =2. (Environ proves delivery; our driver
   additionally reads `torch.get_num_threads()` in-process via a probe node —
   env is necessary, the in-process read is sufficient.)
3. **Chunked write path active** (ours): console line `RR write path: chunked
   1 MiB per write request`, and every record carries
   `write_path: "chunked-1MiB x N"` (N≈237-238 for 248 MB). Yours: inherent
   to `send_files`.
4. **Blob residency ≤ C** (ours): console line `blob residency: max <=16
   concurrent resident (cap = 16)`. Yours: not applicable in blast
   (SDK streams); in c16, note item 4 above.
5. **Cold cache:** console line `cache eviction: rc=0 ...` before each leg
   [SOURCE driver preflight; fadvise(DONTNEED) + behavioral proof, no sudo].

## 6. Known caveats — carry these verbatim next to any quoted number

- **LI worker count was never fully swept.** Our LlamaIndex arm's W=8/T=4 is
  the best of a 3-point W×T=32 budget line (4×8: 0.0989, 8×4: 0.1473, 16×2:
  0.0913 with 15/16 serving) plus a T sweep at W=8 — not an established
  global optimum. Our LI ran at ~40% CPU. The 1.37× parity-over-LI figure
  carries this qualification. (Does not touch the RR default↔parity delta.)
- **Per-core efficiency favours LlamaIndex ~1.6×** (span basis, derived:
  ~0.71 vs 0.434 f/s per effective core) — parity buys throughput with cores,
  not per-core efficiency; idle burden is reported beside every parity
  number, never subtracted.
- **p1 stale rows:** pass-1 records files in this run dir predate some fixes
  and were resumed (errored rows re-run; completed rows kept). Treat p2 as
  the clean-provenance pass; reconcile p1 row-by-row via each record's
  `write_path`/`read_s` fields before quoting p1 alone.
- **n=2 passes,** no 3-rep envelope — same "sizing evidence" grade as your
  Run C by your own criterion; the matched enveloped campaign remains open on
  both sides.
