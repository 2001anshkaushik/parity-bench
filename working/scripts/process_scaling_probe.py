#!/usr/bin/env python3
"""STEP 0 — process scaling probe. Gates all of Phase 2.

Question: can this box reach 10,000 concurrent tasks, given RLIMIT_NPROC and RocketRide's
process model?

Two candidate concurrency models are measured separately, because they have completely different
process costs and the answer decides the whole sweep range:

  Model A — N concurrent *pipelines*: N `client.use()` calls, each spawning its own task process
            tree. This is what "RocketRide spawns a process tree per task" implies.
  Model B — N concurrent *sends through one pipeline*: one `use()`, N in-flight `send()` calls
            served by the engine's work-stealing thread pool. This is what Leela's 10k-document
            run actually did.

Safety
------
721 of this uid's processes are the user's live desktop session. Exhausting RLIMIT_NPROC would
make their applications fail to fork — a real consequence for a measurement we can get another
way. So we do NOT drive to the ceiling: we measure per-unit process cost at safe concurrency,
extrapolate arithmetically, and observe the *failure mode* separately inside a child process
given an artificially lowered RLIMIT_NPROC. ABORT_THRESHOLD leaves a wide margin.
"""

from __future__ import annotations

import asyncio
import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # SDK reads .env from cwd

UID = os.getuid()
PIPE = "pipes/probe_minimal.pipe"
ABORT_THRESHOLD = 5500      # hard stop; ~2,500 processes of headroom for the desktop
OUT = ROOT / "results" / "process_scaling"


def count_procs() -> tuple[int, int]:
    """(processes owned by this uid, of which look like RocketRide engine/node processes)."""
    total = 0
    engine = 0
    for p in psutil.process_iter(["uids", "cmdline"]):
        try:
            u = p.info["uids"]
            if not u or u.real != UID:
                continue
            total += 1
            cmd = " ".join(p.info["cmdline"] or ())
            if "eaas.py" in cmd or "node.py" in cmd or "/engine" in cmd:
                engine += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total, engine


class PeakSampler:
    """Tracks peak uid-wide process count during a window."""

    def __init__(self, interval: float = 0.15):
        self.interval = interval
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.peak_total = 0
        self.peak_engine = 0
        self.aborted = False
        self.series: list[tuple[float, int, int]] = []

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=3)

    def _loop(self):
        while not self._stop.is_set():
            tot, eng = count_procs()
            self.peak_total = max(self.peak_total, tot)
            self.peak_engine = max(self.peak_engine, eng)
            self.series.append((round(time.perf_counter() - self._t0, 3), tot, eng))
            if tot > ABORT_THRESHOLD:
                self.aborted = True
                self._stop.set()
                return
            self._stop.wait(self.interval)


async def _client():
    from rocketride import RocketRideClient
    c = RocketRideClient()
    await c.connect(timeout=30000)
    return c


# --------------------------------------------------------------------------- Model B
async def probe_model_b(levels: list[int]) -> list[dict]:
    """One pipeline, N concurrent sends. Setup is done before sampling starts."""
    from rocketride import RocketRideClient

    rows = []
    c = await _client()
    try:
        r = await c.use(filepath=PIPE)
        token = r["token"]
        await c.send(token, "warm", mimetype="text/plain")  # warm the task
        base_total, base_engine = count_procs()
        print(f"  [model B] after use()+warm: uid_procs={base_total} engine_procs={base_engine}")

        for n in levels:
            with PeakSampler() as s:
                t0 = time.perf_counter()
                results = await asyncio.gather(
                    *(c.send(token, f"item-{i}", mimetype="text/plain") for i in range(n)),
                    return_exceptions=True,
                )
                wall = time.perf_counter() - t0
            errs = [r for r in results if isinstance(r, BaseException)]
            rows.append({
                "model": "B", "concurrency": n, "wall_s": round(wall, 3),
                "peak_uid_procs": s.peak_total, "peak_engine_procs": s.peak_engine,
                "delta_vs_base": s.peak_total - base_total,
                "errors": len(errs),
                "error_sample": repr(errs[0])[:160] if errs else None,
                "throughput_per_s": round(n / wall, 1) if wall else None,
                "aborted": s.aborted,
            })
            print(f"  [model B] n={n:5d}  peak_uid={s.peak_total:5d} (+{s.peak_total-base_total:4d})"
                  f"  engine={s.peak_engine:3d}  {wall:6.2f}s  err={len(errs)}")
            if s.aborted:
                print("  ABORT threshold hit — stopping model B")
                break
        await c.terminate(token)
    finally:
        await c.disconnect()
    return rows


# --------------------------------------------------------------------------- Model A
def _make_pipes(n: int, tmp: Path) -> list[str]:
    """N pipeline files with distinct project_ids.

    The engine enforces one live task per pipeline identity: concurrent `use()` calls on the same
    file return "Pipeline is already running." So N concurrent *tasks* requires N distinct
    `project_id` GUIDs, not N calls against one file. Worth recording — it means a deployment
    serving many concurrent requests is Model B by construction, and Model A only arises if you
    genuinely deploy N different pipelines.
    """
    import uuid
    tmp.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / PIPE).read_text())
    paths = []
    for i in range(n):
        spec = dict(base)
        spec["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"benchmark-a-probe-{i}"))
        p = tmp / f"probe_{i:05d}.pipe"
        p.write_text(json.dumps(spec, indent=1))
        paths.append(str(p.relative_to(ROOT)))
    return paths


async def probe_model_a(levels: list[int]) -> list[dict]:
    """N concurrent pipelines — N `use()` calls, each its own task process tree."""
    rows = []
    tmp = ROOT / "pipes" / "generated"
    for n in levels:
        pipe_paths = _make_pipes(n, tmp)
        c = await _client()
        tokens: list[str] = []
        base_total, base_engine = count_procs()
        try:
            with PeakSampler() as s:
                t0 = time.perf_counter()
                res = await asyncio.gather(*(c.use(filepath=p) for p in pipe_paths),
                                           return_exceptions=True)
                setup_wall = time.perf_counter() - t0
                tokens = [r["token"] for r in res if isinstance(r, dict) and "token" in r]
                errs = [r for r in res if isinstance(r, BaseException)]
                # one send per task so every tree is genuinely live
                sends = await asyncio.gather(
                    *(c.send(t, "x", mimetype="text/plain") for t in tokens),
                    return_exceptions=True)
                send_errs = [r for r in sends if isinstance(r, BaseException)]
                time.sleep(0.5)  # let the sampler see steady state
            rows.append({
                "model": "A", "concurrency": n, "tasks_created": len(tokens),
                "setup_wall_s": round(setup_wall, 3),
                "peak_uid_procs": s.peak_total, "peak_engine_procs": s.peak_engine,
                "delta_vs_base": s.peak_total - base_total,
                "procs_per_task": round((s.peak_total - base_total) / max(1, len(tokens)), 3),
                "use_errors": len(errs), "send_errors": len(send_errs),
                "error_sample": repr(errs[0])[:200] if errs else None,
                "aborted": s.aborted,
            })
            print(f"  [model A] n={n:4d}  tasks={len(tokens):4d}  peak_uid={s.peak_total:5d} "
                  f"(+{s.peak_total-base_total:4d})  engine={s.peak_engine:4d}  "
                  f"per_task={(s.peak_total-base_total)/max(1,len(tokens)):.2f}  "
                  f"setup={setup_wall:6.2f}s  err={len(errs)}")
            if s.aborted:
                print("  ABORT threshold hit — stopping model A")
                break
        finally:
            for t in tokens:
                try:
                    await c.terminate(t)
                except Exception:
                    pass
            await c.disconnect()
            await asyncio.sleep(1.0)  # let the engine reap trees before the next level
    return rows


# --------------------------------------------------------------------------- baselines
def probe_baselines(levels: list[int]) -> list[dict]:
    """Process cost per unit of concurrency for the Python baselines."""
    import concurrent.futures as cf
    import multiprocessing as mp

    rows = []
    base, _ = count_procs()

    # asyncio: coroutines are objects, not processes — expect zero growth.
    async def _aio(n):
        await asyncio.gather(*(asyncio.sleep(0.4) for _ in range(n)))

    def _run_aio(n):
        # probe_baselines() is called from inside a running loop, so asyncio.run() would raise.
        # A dedicated thread gets its own loop without disturbing the caller's.
        box = {}
        def _t():
            box["r"] = asyncio.new_event_loop().run_until_complete(_aio(n))
        th = threading.Thread(target=_t); th.start(); th.join()

    for n in levels:
        with PeakSampler() as s:
            _run_aio(n)
        rows.append({"adapter": "asyncio", "concurrency": n, "peak_uid_procs": s.peak_total,
                     "delta_vs_base": s.peak_total - base, "procs_per_unit": 0.0})
        print(f"  [asyncio]     n={n:5d}  peak_uid={s.peak_total:5d} (+{s.peak_total-base:3d})")

    for n in levels:
        with PeakSampler() as s:
            with cf.ThreadPoolExecutor(max_workers=min(n, 512)) as ex:
                list(ex.map(lambda _: time.sleep(0.3), range(n)))
        rows.append({"adapter": "threadpool", "concurrency": n, "peak_uid_procs": s.peak_total,
                     "delta_vs_base": s.peak_total - base, "procs_per_unit": 0.0,
                     "note": "threads, not processes — capped at 512 workers"})
        print(f"  [threadpool]  n={n:5d}  peak_uid={s.peak_total:5d} (+{s.peak_total-base:3d})")

    # process pool: 1 process per WORKER, not per task — workers are capped at core count.
    for w in (4, 10, 14, 28):
        with PeakSampler() as s:
            ctx = mp.get_context("spawn")
            with cf.ProcessPoolExecutor(max_workers=w, mp_context=ctx) as ex:
                list(ex.map(time.sleep, [0.3] * w))
                time.sleep(0.4)
        rows.append({"adapter": "processpool", "workers": w, "peak_uid_procs": s.peak_total,
                     "delta_vs_base": s.peak_total - base,
                     "procs_per_unit": round((s.peak_total - base) / w, 2)})
        print(f"  [processpool] workers={w:3d}  peak_uid={s.peak_total:5d} "
              f"(+{s.peak_total-base:3d})  per_worker={(s.peak_total-base)/w:.2f}")
    return rows


# --------------------------------------------------------------------------- failure mode
def probe_failure_mode() -> dict:
    """Observe behaviour at the NPROC ceiling *safely*, in a child with a lowered soft limit.

    Driving the real ceiling would starve the user's desktop of processes. A child that sets its
    own RLIMIT_NPROC just above the current uid count hits an identical EAGAIN from fork() while
    the rest of the system is untouched.
    """
    script = r'''
import os, resource, sys, time
cur = int(sys.argv[1]); headroom = int(sys.argv[2])
soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
target = cur + headroom
try:
    resource.setrlimit(resource.RLIMIT_NPROC, (target, hard))
except Exception as e:
    print(f"SETRLIMIT_FAIL {type(e).__name__}: {e}"); sys.exit(3)
got = resource.getrlimit(resource.RLIMIT_NPROC)
print(f"child limit now {got}")
import multiprocessing as mp
ctx = mp.get_context("spawn")
procs, err = [], None
t0 = time.perf_counter()
for i in range(headroom + 60):
    try:
        p = ctx.Process(target=time.sleep, args=(20,)); p.start(); procs.append(p)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"FAILED_AT n={i} after {time.perf_counter()-t0:.2f}s -> {err}")
        break
else:
    print(f"NO_FAILURE after {len(procs)} spawns")
print(f"spawned={len(procs)}")
for p in procs:
    p.terminate()
for p in procs:
    p.join(timeout=5)
print("cleaned")
'''
    cur, _ = count_procs()
    print(f"  current uid procs = {cur}; child will be limited to cur+40")
    r = subprocess.run([sys.executable, "-c", script, str(cur), "40"],
                       capture_output=True, text=True, timeout=300)
    print("  " + (r.stdout or "").replace("\n", "\n  ").rstrip())
    if r.stderr.strip():
        print("  stderr: " + r.stderr.strip()[-400:])
    return {"stdout": r.stdout, "stderr": r.stderr[-2000:], "returncode": r.returncode}


# --------------------------------------------------------------------------- main
async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 76)
    print("STEP 0 — process scaling probe")
    print("=" * 76)

    soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
    maxproc = subprocess.run(["sysctl", "-n", "kern.maxproc"], capture_output=True,
                             text=True).stdout.strip()
    maxperuid = subprocess.run(["sysctl", "-n", "kern.maxprocperuid"], capture_output=True,
                               text=True).stdout.strip()
    idle_total, idle_engine = count_procs()

    print(f"\n[limits] RLIMIT_NPROC soft={soft} hard={hard}")
    print(f"[limits] kern.maxproc={maxproc}  kern.maxprocperuid={maxperuid}")
    print(f"[baseline] uid {UID} owns {idle_total} processes ({idle_engine} engine-related)")
    print(f"[safety] abort threshold {ABORT_THRESHOLD}")

    findings: dict = {
        "limits": {"rlimit_nproc_soft": soft, "rlimit_nproc_hard": hard,
                   "kern_maxproc": maxproc, "kern_maxprocperuid": maxperuid},
        "baseline_uid_procs": idle_total, "baseline_engine_procs": idle_engine,
        "abort_threshold": ABORT_THRESHOLD,
    }

    print("\n[MODEL B] one pipeline, N concurrent sends")
    findings["model_b"] = await probe_model_b([1, 10, 50, 100, 250, 500, 1000])

    print("\n[MODEL A] N concurrent pipelines (use() per task)")
    findings["model_a"] = await probe_model_a([1, 10, 50, 100, 250])

    print("\n[BASELINES] process cost per unit of concurrency")
    findings["baselines"] = probe_baselines([100, 1000])

    print("\n[FAILURE MODE] controlled NPROC exhaustion in a child")
    findings["failure_mode"] = probe_failure_mode()

    (OUT / "process_scaling.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nwritten -> {OUT / 'process_scaling.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
