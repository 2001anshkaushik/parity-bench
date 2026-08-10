# Weekend Run — what is running, how to check it, how to stop it

**Launched 2026-08-07 22:42 local. Unattended. No agent supervising.**

---

## One-line status check

```bash
cat "$(git rev-parse --show-toplevel)"/status.txt
```

Written every 60 seconds, **before and after each document**. A document can take minutes (the
corpus has files up to 1,000 pages), so a heartbeat that only fired between documents would look
frozen — it fires on both sides for exactly that reason.

Reading it:

```
phase=p2_llamaindex arm=llamaindex doc=1840/10000 elapsed=4210s rss=1180MB pid=75838 updated=... 
```

* `updated` **more than ~3 minutes old** → something is wrong, see §5.
* `updated` fresh but `doc` unchanged → a genuinely large document. Normal.

## What is running

| | |
| --- | --- |
| `caffeinate -ims` | PID **75675** — prevents idle, disk **and** system sleep (`-i` alone would only stop idle sleep) |
| `weekend_runner.sh` | PID **75673** — phase orchestrator |
| `weekend_worker.py` | PID **75838** — the current phase's worker; changes each phase |

## ⚠️ Both arms run NATIVELY, not in containers — and why

`server-v3.3.1` ships **darwin-arm64, linux-x64 and win64. There is no linux-arm64 build**, and
the repo's own Docker workflow targets `linux/amd64` only. Containerising RocketRide on this arm64
host would require x86 emulation, which `DOCKER_ARCHITECTURE.md` §1 forbids precisely because
emulation would silently change every number and look like a framework difference. Running one arm
containerised and the other native would be asymmetric, which is worse than neither.

**So: both native, symmetric, no emulation.** The LlamaIndex container demo is a separate,
already-delivered artifact (`DOCKER_DEMO_RESULTS.md`).

**Disclose with any result from this run:** there is no cgroup enforcing the memory ceiling. The
worker enforces a **soft** 12 GB limit and records a breach as a result. That detects a breach; it
does **not** prove the process would have been killed at that point under a hard limit.

## Phase schedule

Every phase has a hard wall-clock cap. On expiry the worker checkpoints and the runner **advances**
— a long phase can never eat the phases behind it.

| phase | arm | cap | target | purpose |
| --- | --- | ---: | ---: | --- |
| `p0_insurance` | LlamaIndex | 90 min | 200 | insurance deliverable — small, fast, both arms |
| `p0_insurance_rr` | RocketRide | 90 min | 200 | same |
| `p1_fetch` | — | 6 h | 10,000 | corpus top-up; **skipped, corpus already at 10,000** |
| `p2_llamaindex` | LlamaIndex | 16 h | 10,000 | full-corpus endurance |
| `p3_rocketride` | RocketRide | 16 h | 10,000 | full-corpus endurance, **sequential — never concurrent with p2** |
| `p4_simultaneous` | both | 60 min | — | shared-envelope proof; **throughput from it is void** |
| `p5_summary` | — | — | — | rolls every checkpoint into `WEEKEND_RESULTS.md` |

Worst case ≈ 42 h. Phases run in order; each is skipped if already marked done.

## Where results land

| what | where |
| --- | --- |
| rolling summary | `publishable/WEEKEND_RESULTS.md` (written by p5; safe to regenerate any time) |
| per-phase checkpoints | `weekend_state/<phase>_<arm>.json` — resume state, RSS series, faults |
| archived results | `working/results/weekend_<phase>_<arm>__<UTC>__<hash>.json` — **cannot collide** |
| per-phase logs | `weekend_logs/<phase>_<arm>.log` — **files, never pipes** |
| orchestrator log | `weekend_logs/runner.log` |

Regenerate the summary at any time without touching the run:

```bash
cd "$(git rev-parse --show-toplevel)" && ../.venv/bin/python weekend_summarise.py
```

## Stopping and resuming

**Stop safely** (checkpoints are already on disk; nothing is lost):

```bash
pkill -f weekend_runner.sh; pkill -f weekend_worker.py; pkill -f "caffeinate -ims"
```

**Resume** — idempotent, picks up from the last checkpoint, never restarts a phase from zero:

```bash
cd "$(git rev-parse --show-toplevel)"
nohup caffeinate -ims ./weekend_runner.sh > weekend_run.log 2>&1 &
```

**To force a phase to re-run from scratch**, delete its checkpoint *and* its done-marker:

```bash
find weekend_state -name 'p2_llamaindex*' -delete
```

> Use `find -delete`, not `rm weekend_state/*.json`. In zsh a glob that matches nothing aborts the
> whole command line — that is how a "cleared" state directory silently kept 11 stale files and
> caused a contaminated launch earlier tonight.

## 5. If a phase looks stuck

1. **Check the heartbeat age.** Fresh `updated` = alive. Stale by >3 min = investigate.
2. **Check the phase log**: `tail -20 weekend_logs/<phase>_<arm>.log`.
3. **RocketRide phases**: confirm the engine answers —
   `curl -s http://127.0.0.1:5565/version`. Cold start is ~60 s and happens outside every measured
   region; if it never comes up, that phase fails and the runner advances.
4. **`"Pipeline is already running"`** in a RocketRide log means two phases claimed one
   `project_id`. This was fixed before launch (the id is now unique per phase + pid + timestamp),
   but it is the failure to look for first if a RocketRide phase dies at startup.
5. **A phase that failed is not fatal.** The runner logs `FAILED rc=N — advancing` and moves on.
   `rc=10` cap reached, `rc=11` memory ceiling breached (a valid result, curve preserved), `rc=1`
   error.

## What was proven before launch

An unattended script nobody has watched fail is untested. All five demonstrated:

| proof | result |
| --- | --- |
| checkpoints land and are readable | ✅ `[ckpt] n=200`, JSON parsed back |
| heartbeat updates | ✅ and improved mid-dry-run to fire *before* each document too |
| a phase cap fires and advances | ✅ all six phases advanced on 40-second caps |
| a simulated OOM is caught and recorded | ✅ exit 11, `memory_limit_exceeded`, index + document + RSS curve preserved |
| kill mid-phase, relaunch, resume | ✅ killed at index 200, resumed at 200, advanced to 304 |

Two real defects were found by the dry run and fixed before launch: the heartbeat could stall on a
single large document, and an OOM before the first periodic RSS sample left an empty curve.

## Throughput from this run is invalid

Rates on this host are unusable (open item A13 — ascending-load measurement profiles a machine in a
low-power state). **This run measures stability, goodput and memory.** `docs_per_s` is not reported
by the summariser at all.
