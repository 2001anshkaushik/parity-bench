# Benchmark Setup — building the same thing

**For Leela.** This is how the WS-1 harness works and, more usefully, the things that went wrong
while building it. If you only read one section, read §7 — it is the part that would have saved us
the most time.

---

## 1. What this is and what it measures

A two-arm comparison of the **RocketRide engine** and a **LlamaIndex FastAPI service** running an
identical document pipeline: PDF → text → chunks (4000/200) → 384-d embeddings
(`sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, CPU).

**What it can measure on a laptop:** memory, goodput, fault classes, functional equivalence,
stability.

**What it cannot:** throughput. On this host an ascending concurrency sweep reads 101 /s where a
descending one reads 241 /s — a **2.2× swing from measurement order alone**, because the machine
is in a low-power state at the start of a cold sweep. No configuration fixes it. Every rate in this
repo is labelled run cost, never a benchmark.

## 2. Engine lifecycle

```bash
bash working/scripts/start_engine.sh      # ~60 s cold, ~1 s warm
curl -s http://127.0.0.1:5565/version     # readiness + identity in one call
bash working/scripts/stop_engine.sh       # teardown by pidfile
```

**Use `GET /version`, not `/ping`.** `/ping` is auth-gated and answers `401`, so a naive health
check reports a healthy engine as down — or, worse, a shell `||` fallback turns `000` into
`000000` and a dead engine passes (see §7).

**The ~60 s cold start must sit outside every timed region.** The runner starts the engine, polls
`/version` until it answers, and only then begins measuring. If a task is created inside the
measured window it pays a model load too — that cost is real but belongs in a warm-up, not a
result.

**One live task per `project_id`.** A fixed id makes the second phase fail with *"Pipeline is
already running"*. Our runners derive a unique id per phase, per pid, per timestamp; a fixed id
cost us an entire arm of one weekend run.

## 3. Thread parity — and why the config value is not the answer

Thread count is the single largest configuration lever we found: pinning changes concurrency
scaling from 1.43× to 3.04×, and at concurrency 1 it costs **3.07×** on real documents.

Setting it is easy:

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 TORCH_NUM_THREADS=1 \
  bash working/scripts/start_engine.sh
```

**Verifying it is the part that matters.** An exported variable proves nothing: torch caches its
thread count at import, so a variable set after import has no effect, and a variable exported to
the engine parent does not guarantee the *task process* inherited it. So we ask the task process
directly, via a node that reports its own state:

```bash
../.venv/bin/python working/scripts/probe_env.py check
# {"torch_num_threads": 10, "torch_num_interop_threads": 14, "env": {...}, "pid": 35229}
```

`matched_replication.py` reads this from **both** arms before measuring and **refuses to start if
they differ**:

```
CONFIG GATE  engine task process torch threads = 10 | LlamaIndex process torch threads = 10
CONFIG GATE PASSED — both arms matched at 10 intra-op threads, unpinned
```

We added that assertion *after* a full 10,000-document comparison ran with RocketRide on 1 thread
and LlamaIndex on 10 and nothing detected it. Note also that `TORCH_NUM_THREADS=1` does **not**
reach `torch_num_interop_threads`, which stays at 14 — the pin is partial, and only measurement
reveals that.

**"Default" is not a matched setting.** Two stacks' defaults are unrelated. We chose per arm by
measuring each against itself: unpinned beats pinned by 3.07× (RocketRide) and 3.26× (LlamaIndex)
at concurrency 1, so unpinned is each arm's own best and they happen to coincide at 10 threads.

## 4. The 10 % variance gate

A cell is reportable only if repeated measurements agree within 10 %.

* **Barrier-synchronised fixed-duration windows.** Every driver process waits on a barrier, then
  measures for a fixed wall-clock window. Per-burst boundaries across unsynchronised drivers
  produced 12–58 % spreads that looked like engine noise and were entirely our own harness.
* **Warm-up excluded.** The first 50 documents of a block are processed but dropped before any
  median or slope. Including them once produced a "+1,505 MB per 1,000 documents leak" that was
  the warm-up ramp plus endpoint luck.
* **The gate refuses n=1.** A single block has zero spread by construction and would pass
  trivially. A gate that cannot fail is worse than no gate, so it requires n ≥ 3.
* **"Direction only"** means the arms differ consistently but the point estimate is not reportable
  because a gate failed. Quote the direction and the range; never a decimal.

A worked example: our matched memory ratio is **direction only** because RocketRide's spread is
24 %. That 24 % turned out to be **bimodality, not drift** — four of six blocks at 2,055–2,112 MB
and two excursions to ~2,700 — which is a different operational statement from "it degrades".

## 5. Goodput and content sanity — shape is not enough

`llama_index.core` maps `.pdf → PDFReader` from `llama-index-readers-file`. **When that package is
absent it warns and returns `{}`** — no exception, no error status. A 10,000-document run in that
state produces 10,000 successes with flat memory and zero embeddings.

So every document is asserted, and failure is loud:

1. `n_chunks > 0` · 2. every chunk non-empty after strip · 3. one vector per chunk ·
4. every vector exactly 384-d · 5. every vector L2-normalised to 1.0 ± 0.01 ·
6. vectors not identical across distinct chunks

Check 5 is the one people skip. A zero vector passes a dimension check and fails this.

**But shape is not meaning.** The gate happily passed 39,803 characters of binary control codes as
eleven confident unit-norm vectors, because garbage embeds as cleanly as prose. So there is a
second, separate check:

* **`has_nul`** — exact, catches the truncation defect (§7).
* **printable ratio < 0.90** — catches garbage extraction.

**The 0.90 threshold was derived, not chosen.** On a 991-document sample legitimate documents have
p1 = 0.9944 and a second-lowest of 0.9757; the two known-garbage extractions sit at 0.679 and
0.700. 0.90 is the midpoint of an empty band, and it flags 0 of 40 legitimate documents.

**The two checks do not substitute for each other**: two of three NUL-containing documents had
printable ratios of 0.9923 and 0.9884, indistinguishable from clean ones — and one of them would
lose 98.9 % of its text.

## 6. Reproducing the matched replication

```bash
# provision first — engine bundle and corpus are not in the repo
cat publishable/PROVISIONING.md

bash working/scripts/start_engine.sh          # unpinned: export no thread vars
../.venv/bin/python matched_replication.py --docs 2000 --blocks 3 --prewarm 25
```

**Runtime ~90 min** (six 2,000-document blocks plus pre-warm). Dry-run first with
`--docs 10 --blocks 2 --prewarm 3 --dry-run`.

What to check, in order:

1. `CONFIG GATE PASSED` with the same thread count on both arms. If it refuses, it is doing its job.
2. `plan:` alternates arms.
3. Per-arm spread and gate status; a gate-failing arm yields direction only.
4. Goodput identical across blocks — ours is 1,972 (LlamaIndex) and 1,965 (RocketRide) every time.

Results land in `working/results/matched_replication__<UTC>__<hash>.json`; progress in
`repl_status.txt`.

## 7. Pitfalls that cost us weeks

Each line is the symptom you will actually see.

| pitfall | symptom |
| --- | --- |
| **`setsid` does not exist on macOS** | `nohup setsid ...` exits instantly with *"setsid: No such file or directory"*; the job looks launched and never ran. Cost two hours once, then recurred. Verify every detached launch **by PID**. |
| **`/health` is answered by one worker** | The service reports ready while 7 of 8 workers are still loading the model, so the first measurements are on a half-warm service. Count `warm in` lines instead, one per worker. |
| **`os.cpu_count()` reports HOST cores inside a container quota** | 14 inside a `--cpus 4` container. torch and BLAS size their pools from it, so a container spawns 14 threads into 4 cores — the exact oversubscription you containerised to avoid. Pin explicitly; read `/sys/fs/cgroup/cpu.max` for the real quota. |
| **Declared ≠ measured thread counts** | Everything looks configured; the arms silently run at 1 vs 10 threads for an entire 10,000-document comparison. Only an in-process probe catches it. |
| **Hardcoded result paths clobber silently** | Three scripts wrote to `results/isolated_profile_llamaindex.json`; the third overwrote the first two. No error, no warning, data gone. Ours now embed a UTC stamp and a payload hash and refuse to overwrite. |
| **Ascending concurrency sweeps profile a low-power machine** | Ascending-cold reads 101 /s where descending reads 241 /s on the same service. Pre-warm before every measurement, or measure descending. |
| **`sentence-transformers` silently selects `mps`** | No error, ~3× the throughput, ~10× the run-to-run spread, and every cross-service number invalid. Set `device` explicitly and **assert the resolved device**, refusing to start on a mismatch. |
| **llama-index returns `{}` for PDFs when the reader package is absent** | Warns, returns empty, reports success. Ten thousand green results that embedded nothing. |
| **`.gitignore` has no trailing comments** | `engine/    # 1.2 GB` is parsed as a literal pattern including the comment and matches nothing. We nearly staged 7.4 GB. Comments go on their own line. |
| **`str.replace("", x)` inserts between every character** | A 7 KB file became 263 KB. Guard any programmatic edit against an empty pattern. |
| **`psutil.net_connections()` needs root on macOS** | Returns nothing without it, so a PID lookup silently falls back to matching by name — and then counts an unrelated five-day-old engine. Use `lsof`. |
| **A launcher path that is relative to a directory you later move** | `run_service.sh` resolved its interpreter as `$ROOT/../.venv/bin/python`, correct while `ws1/` sat at the clone root. Restructuring into `working/ws1/` silently changed what `$ROOT` meant, and the service then died at launch for **every** caller — undetected for days because by then nothing needed it. Anchor on a marker you control (`git rev-parse --show-toplevel`), and make the launcher assert its interpreter exists rather than letting the shell report a missing file from the middle of an exec line. |
| **Cosine similarity cannot see a chunk's tail** | The embedder truncates at **512 tokens** while chunks are ~4,000 chars, so two chunks differing only past ~2,000–2,500 characters embed **identically** (cos = 1.0000). Every vector-shape check can pass on wrong content. Verify content by **hashing chunk text against a reference computed outside both frameworks** — `harness/chunk_hash.py`. Approach adopted from Leela's `bench_langgraph_prod`; the 512-token finding is hers. |
| **Matching processes by name** | `pgrep -f mything` also matches your own monitoring shell, so a finished run looks alive. Match by PID. |
| **A match string containing the clone's directory name** | Our engine-node match embedded `benchmark-A/` in the path, so a clone named anything else matched **nothing** — `counts()` reported 0 node processes and `kill_orphans()` reported a clean teardown while leaving every orphan running. Zero is indistinguishable from a healthy idle engine, so nothing looked wrong. Any name-based match needs a way to tell *no matches* from *nothing to match*: compare the pattern against a broader detector in the same snapshot and raise when they disagree. Ours is `RR_NODE_MARK` + `NodeMarkStale`. |
| **`grep -q` inside a `--msg-filter` eats the message** | `grep -q` exits the moment it decides, leaving the rest of stdin unread — and in a `git filter-branch --msg-filter` stdin *is* the commit message. Every commit the pattern did not match got an **empty** message, because the `cat` after it had nothing left to read. This emptied 18 of 19 messages here. Read stdin **fully into a variable first**, then decide. Test the filter standalone against one commit before pointing it at history. |
| **`gc --prune=now` after a filter-branch destroys the only undo** | `filter-branch` leaves three recovery paths — `.git/refs/original/`, the reflog, and the old commits as dangling objects. `git reflog expire --expire=now --all && git gc --prune=now` removes all three at once, and a `rm -rf .git/refs/original` beforehand removes the fourth. That sequence is routinely recommended as "cleanup"; it is what made the above unrecoverable. **Back up the whole directory including `.git` before any history rewrite, and leave the reflog alone until the result is verified.** |

## 8. Where to look

| | |
| --- | --- |
| current findings | `publishable/MEETING_2026-08-10.md` |
| durable state + full supersession history | `publishable/STATE.md` (§5 is every withdrawn number) |
| comparison basis, canonical pipeline | `publishable/FAIRNESS_BASIS.md` |
| the NUL data-loss bug, filing-ready | `publishable/BUG_NUL_TRUNCATION.md` |
| what a fresh clone lacks | `publishable/PROVISIONING.md` |
| regression suite | `working/scripts/regression_selftest.py` — one test per defect that produced a wrong number |

**Run the regression suite first:** `../.venv/bin/python working/scripts/regression_selftest.py`
— one test per defect that produced a wrong number here.

**It is not an environment check**, despite the obvious temptation to use it as one. Measured
by tracing its imports: it loads only `psutil` of the fourteen pinned packages, so it passes
just as happily on a venv where torch or llama-index is broken. Verify the stack separately:

```bash
../.venv/bin/python -c "import torch,sentence_transformers,llama_index.core,sklearn,pypdf,fastapi;print('stack ok')"
```
