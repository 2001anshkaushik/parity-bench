"""Start, warm-gate, measure and stop the WS-1 LlamaIndex service.

Exists because every previous service-mode measurement in this repo got the readiness gate wrong.
`memory_ceiling.py` waited for `/manifest` to answer and then slept 3 s — but `/manifest` is answered
by ONE worker, so the other seven could still be loading their models when the "idle" RSS was taken.
That understates idle memory, and nothing in the artifact recorded how many workers were actually
resident.

Two rules this module enforces:

1. **Warm-gate by counting `[ws1] worker <pid> warm in <s>` lines — one per worker.** Never a
   health/manifest endpoint. `wait_warm()` refuses to return until it has seen `workers` distinct
   worker PIDs.
2. **Resolve PIDs by listening socket, not by name.** Same reason `RocketArm._engine_pid()` does:
   name matching counted an unrelated engine in the weekend run. `lsof -nP -iTCP:<port> -sTCP:LISTEN`
   gives the process actually serving, and its children are the workers.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent          # working/
WARM_RE = re.compile(r"\[ws1\] worker (\d+) warm in ([\d.]+)s")
THREADS_RE = re.compile(r"worker (\d+) warm in .*?torch_threads=(\d+) torch_interop=(\d+)")


class Ws1NotWarm(RuntimeError):
    """The service did not reach the requested worker count within the deadline."""


class Ws1Handle:
    def __init__(self, proc, log_path: Path, port: int, workers: int):
        self.proc, self.log_path, self.port, self.workers = proc, log_path, port, workers
        self.warm_pids: list[int] = []
        self.warm_seconds: list[float] = []
        self.measured_threads: dict[int, tuple[int, int]] = {}   # pid -> (intra, interop)


def start(workers: int, port: int = 8801, device: str = "cpu",
          threads: int | None = None, log_path: Path | None = None) -> Ws1Handle:
    """Launch the service. `threads` sets OMP/MKL/OPENBLAS/VECLIB; None leaves them UNPINNED.

    run_service.sh defaults those to 1. The matched replication ran RocketRide unpinned (10 intra-op
    threads), and thread count is the largest single lever measured in this project (3.07x at
    concurrency 1), so inheriting the launcher's default would mismatch the arms on exactly the
    variable that matters most. Callers must choose explicitly.
    """
    env = dict(os.environ)
    env.update(WS1_DEVICE=device, WS1_WORKERS=str(workers), WS1_PORT=str(port))
    # run_service.sh does `export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"`, so UNSETTING these does
    # NOT give an unpinned service — it gives a 1-thread one. To match RocketRide's unpinned arm the
    # caller must pass the number torch picks by itself on this host (10, measured). Whatever is
    # requested here is DECLARED; wait_warm() reads back what each worker actually got.
    if threads is None:
        raise ValueError("threads must be explicit: run_service.sh defaults these to 1, so "
                         "'unpinned' has to be requested by value (10 on this host), not by omission")
    for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[v] = str(threads)
    log_path = log_path or (ROOT.parent / "logs" / f"ws1_matched_{port}_{workers}w.out")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_path, "w")                    # a FILE, never a pipe — an unread PIPE deadlocks the
    proc = subprocess.Popen(                    # service once 64 KB of warm lines fill the buffer
        ["bash", str(ROOT / "ws1" / "run_service.sh")],
        cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT)
    return Ws1Handle(proc, log_path, port, workers)


def wait_warm(h: Ws1Handle, timeout: float = 600.0) -> Ws1Handle:
    """Block until `h.workers` DISTINCT worker PIDs have each logged a warm line."""
    deadline = time.perf_counter() + timeout
    seen: dict[int, float] = {}
    while time.perf_counter() < deadline:
        if h.proc.poll() is not None:
            raise Ws1NotWarm(f"service exited rc={h.proc.returncode}; see {h.log_path}")
        try:
            for m in WARM_RE.finditer(h.log_path.read_text()):
                seen[int(m.group(1))] = float(m.group(2))
        except FileNotFoundError:
            pass
        if len(seen) >= h.workers:
            h.warm_pids = sorted(seen)
            h.warm_seconds = [seen[p] for p in h.warm_pids]
            txt = h.log_path.read_text()
            h.measured_threads = {int(m.group(1)): (int(m.group(2)), int(m.group(3)))
                                  for m in THREADS_RE.finditer(txt)}
            return h
        time.sleep(0.5)
    raise Ws1NotWarm(
        f"only {len(seen)}/{h.workers} workers warmed within {timeout:.0f}s — "
        f"measuring now would understate idle memory. Log: {h.log_path}")


def serving_pids(port: int) -> tuple[int | None, list[int]]:
    """(parent, workers) resolved by LISTENING SOCKET, never by process name."""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return None, []
    pids = {int(f[1]) for ln in out.splitlines()[1:] if len(f := ln.split()) > 1 and f[1].isdigit()}
    if not pids:
        return None, []
    # uvicorn's parent is the ancestor of the rest; workers inherit the socket
    procs = []
    for p in pids:
        try:
            procs.append(psutil.Process(p))
        except psutil.NoSuchProcess:
            pass
    if not procs:
        return None, []
    parent = min(procs, key=lambda p: p.create_time())
    kids = [k.pid for k in parent.children(recursive=True)]
    return parent.pid, sorted(set(kids) | (pids - {parent.pid}))


def tree_rss_mb(port: int) -> tuple[float, int]:
    """(RSS of uvicorn parent + every worker, process count). Mirrors engine_tree_rss_mb()."""
    parent, workers = serving_pids(port)
    if parent is None:
        return 0.0, 0
    total, n, seen = 0.0, 0, set()
    for pid in [parent, *workers]:
        if pid in seen:
            continue
        seen.add(pid)
        try:
            total += psutil.Process(pid).memory_info().rss / 1e6
            n += 1
        except psutil.NoSuchProcess:
            pass
    return total, n


def stop(h: Ws1Handle, grace: float = 5.0) -> None:
    parent, workers = serving_pids(h.port)
    try:
        h.proc.terminate()
        h.proc.wait(timeout=grace)
    except Exception:
        try:
            h.proc.kill()
        except Exception:
            pass
    for pid in ([parent] if parent else []) + workers:
        try:
            p = psutil.Process(pid)
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    time.sleep(1.0)
    for pid in ([parent] if parent else []) + workers:
        try:
            p = psutil.Process(pid)
            if p.is_running():
                p.kill()
        except psutil.NoSuchProcess:
            pass
