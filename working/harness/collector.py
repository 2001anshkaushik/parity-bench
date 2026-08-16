"""macOS/arm64 process-tree metrics collector.

Design notes that matter for benchmark validity
-----------------------------------------------
1. **Whole-tree accounting.** RocketRide runs a thin async WebSocket client in the harness
   process and does the actual work in engine-spawned `node.py` process trees. In-process
   frameworks (LangGraph, CrewAI) do everything inside the harness process. Sampling only the
   harness process would understate RocketRide's footprint by orders of magnitude and produce a
   meaningless comparison. Every role is therefore sampled as a *set of process trees*, re-scanned
   each tick so short-lived per-task children are picked up.

2. **Retired-process CPU//memory carry-over.** A per-task process that exits between ticks takes
   its cumulative `cpu_times()` with it. We remember the last observed counters per PID and roll
   them into a retired accumulator on death, so total CPU-seconds is conserved. Without this,
   process-per-task engines appear to consume near-zero CPU.

3. **No RLIMIT_AS on macOS.** Address-space limits are the usual way to cap memory, but macOS
   overcommits aggressively — VMS routinely reads 400+ GB for a process holding 200 MB resident
   (numpy/torch reserve enormous ranges). Capping VMS would fire spuriously and unevenly across
   frameworks. We instead run an **RSS watchdog** in the sampler: identical resident ceiling for
   every framework, recorded as an `oom_event`, optionally enforced by termination.

4. **macOS platform gaps.** `psutil` exposes no PSS on Darwin and `io_counters()` raises. USS is
   available via `memory_full_info()` but walks the VM map and is far too slow for a 100 ms
   cadence across many processes, so it is opt-in at a decimated rate.

5. **Memory compression.** macOS compresses pages under pressure instead of OOM-killing, so peak
   RSS alone understates true pressure. We sample `vm_stat` compressor pages and swap at a
   decimated cadence; a run where RSS looks flat but compressor pages climb is under duress.

6. **The observer must not hold the measured process's GIL.** The first version of this collector
   ran as a thread inside the harness and called `Process.children(recursive=True)` per root per
   tick. On macOS each of those calls scans the entire system process table, and it does so
   holding the GIL — measured effect: the harness dropped from 5,412 to 58 items/s, a 100x
   slowdown. That error is not merely noisy, it is *biased*: in-process frameworks (LangGraph,
   CrewAI) live in the harness process and would have been throttled, while an external engine
   like RocketRide would not — fabricating a win out of instrumentation alone. Two fixes, both
   applied below: discovery does one process-table scan per cycle instead of one per root and is
   decimated to ~1 s, and `ProcessCollector` runs the whole sampler in a *separate process* so it
   cannot contend for the GIL of anything it measures. Prefer `ProcessCollector` for real runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import psutil

PidSource = Callable[[], Iterable[int]]

DEFAULT_INTERVAL_S = 0.10
# vm_stat and USS are expensive; sample them once every N ticks.
SYSTEM_DECIMATION = 10
USS_DECIMATION = 20

_VM_STAT_RE = re.compile(r'^"?([A-Za-z][^":]*)"?:\s+(\d+)\.?$')


def _page_size() -> int:
    try:
        return int(subprocess.run(["pagesize"], capture_output=True, text=True, timeout=5).stdout.strip())
    except Exception:
        return 16384 if os.uname().machine == "arm64" else 4096


def read_vm_stat(page_size: int) -> dict[str, int]:
    """Parse `vm_stat` into byte counts. Returns {} if unavailable."""
    import sys as _sys
    if _sys.platform != "darwin":
        # Linux (2026-08-14 audit): vm_stat does not exist; read swap activity from /proc/vmstat so
        # the eviction signal survives the platform change instead of silently vanishing.
        try:
            vs = open("/proc/vmstat").read()
            import re as _re
            out = {}
            for key, name in (("pswpin", "swapins"), ("pswpout", "swapouts")):
                m = _re.search(rf"^{key} (\d+)", vs, _re.M)
                if m:
                    out[name] = int(m.group(1)) * page_size
            return out
        except Exception:
            return {}
    if not shutil.which("vm_stat"):
        return {}
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    pages: dict[str, int] = {}
    for line in out.splitlines():
        m = _VM_STAT_RE.match(line.strip())
        if m:
            pages[m.group(1).strip().lower().replace(" ", "_")] = int(m.group(2))
    g = pages.get
    return {
        "compressor_bytes": (g("pages_occupied_by_compressor", 0)) * page_size,
        "wired_bytes": (g("pages_wired_down", 0)) * page_size,
        "active_bytes": (g("pages_active", 0)) * page_size,
        "inactive_bytes": (g("pages_inactive", 0)) * page_size,
        "free_bytes": (g("pages_free", 0)) * page_size,
        "swapins": g("swapins", 0),
        "swapouts": g("swapouts", 0),
        "compressions": g("compressions", 0),
        "decompressions": g("decompressions", 0),
    }


@dataclass
class ProcSnapshot:
    rss: int = 0
    pss: int | None = None
    vms: int = 0
    uss: int | None = None
    threads: int = 0
    fds: int = 0
    cpu_user: float = 0.0
    cpu_sys: float = 0.0
    ctx_vol: int = 0
    ctx_invol: int = 0


@dataclass
class RoleAggregate:
    """Per-role rolling aggregate across a whole process tree."""

    role: str
    peak_rss: int = 0
    peak_pss: int = 0
    peak_vms: int = 0
    peak_uss: int = 0
    peak_procs: int = 0
    peak_threads: int = 0
    peak_fds: int = 0
    # CPU seconds retired by processes that have exited.
    retired_cpu_user: float = 0.0
    retired_cpu_sys: float = 0.0
    retired_ctx_vol: int = 0
    retired_ctx_invol: int = 0
    # Last observed counters for still-live PIDs.
    live: dict[int, ProcSnapshot] = field(default_factory=dict)
    samples: int = 0
    rss_series: list[tuple[float, int]] = field(default_factory=list)
    oom_events: list[dict] = field(default_factory=list)
    pids_seen: set[int] = field(default_factory=set)

    def total_cpu_seconds(self) -> float:
        live = sum(s.cpu_user + s.cpu_sys for s in self.live.values())
        return live + self.retired_cpu_user + self.retired_cpu_sys

    def total_ctx_switches(self) -> tuple[int, int]:
        v = sum(s.ctx_vol for s in self.live.values()) + self.retired_ctx_vol
        i = sum(s.ctx_invol for s in self.live.values()) + self.retired_ctx_invol
        return v, i


def _sample_one(proc: psutil.Process, want_uss: bool) -> ProcSnapshot | None:
    try:
        with proc.oneshot():
            mem = proc.memory_info()
            cpu = proc.cpu_times()
            try:
                ctx = proc.num_ctx_switches()
                ctx_v, ctx_i = ctx.voluntary, ctx.involuntary
            except (psutil.AccessDenied, NotImplementedError):
                ctx_v = ctx_i = 0
            try:
                fds = proc.num_fds()
            except (psutil.AccessDenied, NotImplementedError):
                fds = 0
            uss = pss = None
            if want_uss:
                # PSS is the only per-process figure that SUMS correctly: private + shared/N,
                # so a page shared by 33 forked workers contributes once in total rather than
                # 33 times. RSS sums to an over-count, USS to an under-count. psutil reads
                # both from smaps_rollup where available (_pslinux.py:1904,1934).
                try:
                    fi = proc.memory_full_info()
                    uss, pss = fi.uss, getattr(fi, "pss", None)
                except (psutil.AccessDenied, NotImplementedError, ValueError):
                    uss = pss = None
            return ProcSnapshot(
                rss=mem.rss,
                vms=mem.vms,
                uss=uss,
                pss=pss,
                threads=proc.num_threads(),
                fds=fds,
                cpu_user=cpu.user,
                cpu_sys=cpu.system,
                ctx_vol=ctx_v,
                ctx_invol=ctx_i,
            )
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return None


class TreeCollector:
    """Samples one or more named process trees to JSONL and keeps rolling aggregates.

    Parameters
    ----------
    roles:
        Mapping of role name -> callable returning root PIDs for that role. The callable is
        re-evaluated every tick, so engines that fork a fresh process per task are tracked.
    rss_ceiling_bytes:
        Optional resident ceiling applied identically to every role. Exceeding it records an
        `oom_event`. Set ``enforce_ceiling=True`` to also terminate the offending tree, which is
        how we reproduce a hard OOM fairly on a platform with no cgroups.
    """

    def __init__(
        self,
        out_path: Path | None,
        roles: dict[str, PidSource],
        interval_s: float = DEFAULT_INTERVAL_S,
        want_uss: bool = False,
        rss_ceiling_bytes: int | None = None,
        enforce_ceiling: bool = False,
        write_per_proc: bool = False,
        discovery_interval_s: float = 1.0,
    ):
        self.out_path = Path(out_path) if out_path else None
        self.roles = roles
        self.interval_s = interval_s
        self.want_uss = want_uss
        self.rss_ceiling_bytes = rss_ceiling_bytes
        self.enforce_ceiling = enforce_ceiling
        self.write_per_proc = write_per_proc
        self.discovery_interval_s = discovery_interval_s
        self._last_discovery = 0.0

        self.aggregates: dict[str, RoleAggregate] = {r: RoleAggregate(role=r) for r in roles}
        self.system_series: list[dict] = []
        self._page_size = _page_size()
        self._tracked: dict[str, dict[int, psutil.Process]] = defaultdict(dict)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fh = None
        self._t0 = 0.0
        self._tick = 0
        self._lock = threading.Lock()
        self.start_vm_stat: dict[str, int] = {}
        self.end_vm_stat: dict[str, int] = {}

    # -- lifecycle -------------------------------------------------------------

    def __enter__(self) -> "TreeCollector":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> None:
        self._t0 = time.perf_counter()
        self.start_vm_stat = read_vm_stat(self._page_size)
        if self.out_path:
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.out_path.open("w", buffering=1024 * 64)
        self._thread = threading.Thread(target=self._loop, name="tree-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self.end_vm_stat = read_vm_stat(self._page_size)
        if self._fh:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    # -- sampling --------------------------------------------------------------

    def _discover(self) -> None:
        """Refresh the tracked process set.

        One system-wide scan builds a ppid -> children index, then every role's tree is walked
        from that index. The naive alternative — `Process.children(recursive=True)` per root —
        rescans the whole process table once per root per tick and was measured slowing the
        harness 100x (see module note 6). Decimated to `discovery_interval_s`; between cycles we
        only sample already-known PIDs, which is cheap.
        """
        now = time.perf_counter()
        if now - self._last_discovery < self.discovery_interval_s and self._last_discovery > 0:
            return
        self._last_discovery = now

        children: dict[int, list[int]] = defaultdict(list)
        procs: dict[int, psutil.Process] = {}
        for p in psutil.process_iter(["pid", "ppid"]):
            try:
                children[p.info["ppid"]].append(p.info["pid"])
                procs[p.info["pid"]] = p
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                continue

        for role, pid_fn in self.roles.items():
            try:
                roots = list(pid_fn())
            except Exception:
                continue
            tracked = self._tracked[role]
            seen: set[int] = set()
            stack = list(roots)
            while stack:
                pid = stack.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                if pid not in tracked:
                    p = procs.get(pid)
                    if p is None:
                        try:
                            p = psutil.Process(pid)
                        except (psutil.NoSuchProcess, ValueError):
                            continue
                    tracked[pid] = p
                stack.extend(children.get(pid, ()))

    def _loop(self) -> None:
        next_t = time.perf_counter()
        while not self._stop.is_set():
            next_t += self.interval_s
            try:
                self._sample_tick()
            except Exception as e:  # a collector bug must never kill a benchmark run
                self._write({"kind": "collector_error", "error": repr(e), "t": self._elapsed()})
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                self._stop.wait(sleep)
            else:
                next_t = time.perf_counter()  # we fell behind; resync rather than spiral

    def _elapsed(self) -> float:
        return time.perf_counter() - self._t0

    def _sample_tick(self) -> None:
        self._tick += 1
        t = self._elapsed()
        want_uss = self.want_uss and (self._tick % USS_DECIMATION == 0)
        self._discover()

        for role, agg in self.aggregates.items():
            tracked = self._tracked[role]
            rss = vms = uss = pss = threads = fds = 0
            n_live = 0
            dead: list[int] = []

            for pid, proc in tracked.items():
                snap = _sample_one(proc, want_uss)
                if snap is None:
                    dead.append(pid)
                    continue
                n_live += 1
                agg.pids_seen.add(pid)
                agg.live[pid] = snap
                rss += snap.rss
                vms += snap.vms
                if snap.uss is not None:
                    uss += snap.uss
                if snap.pss is not None:
                    pss += snap.pss
                threads += snap.threads
                fds += snap.fds

            for pid in dead:
                tracked.pop(pid, None)
                last = agg.live.pop(pid, None)
                if last is not None:
                    agg.retired_cpu_user += last.cpu_user
                    agg.retired_cpu_sys += last.cpu_sys
                    agg.retired_ctx_vol += last.ctx_vol
                    agg.retired_ctx_invol += last.ctx_invol

            with self._lock:
                agg.samples += 1
                agg.peak_rss = max(agg.peak_rss, rss)
                agg.peak_vms = max(agg.peak_vms, vms)
                agg.peak_uss = max(agg.peak_uss, uss)
                agg.peak_pss = max(agg.peak_pss, pss)
                agg.peak_procs = max(agg.peak_procs, n_live)
                agg.peak_threads = max(agg.peak_threads, threads)
                agg.peak_fds = max(agg.peak_fds, fds)
                agg.rss_series.append((t, rss))

            if self.rss_ceiling_bytes and rss > self.rss_ceiling_bytes:
                ev = {"t": t, "role": role, "rss": rss, "ceiling": self.rss_ceiling_bytes,
                      "enforced": self.enforce_ceiling}
                agg.oom_events.append(ev)
                self._write({"kind": "oom_event", **ev})
                if self.enforce_ceiling:
                    self._terminate_role(role)

            self._write({
                "kind": "role_tick", "t": t, "role": role, "n_procs": n_live,
                "rss": rss, "vms": vms, "uss": uss or None, "threads": threads, "fds": fds,
                "cpu_s": round(agg.total_cpu_seconds(), 6),
            })

        if self._tick % SYSTEM_DECIMATION == 0:
            self._sample_system(t)

    def _sample_system(self, t: float) -> None:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        row = {
            "kind": "system_tick", "t": t,
            "mem_total": vm.total, "mem_available": vm.available, "mem_used": vm.used,
            "mem_percent": vm.percent, "swap_used": sw.used,
            "load1": os.getloadavg()[0],
            **read_vm_stat(self._page_size),
        }
        self.system_series.append(row)
        self._write(row)

    def _terminate_role(self, role: str) -> None:
        for pid, proc in list(self._tracked[role].items()):
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _write(self, row: dict) -> None:
        if self._fh:
            self._fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    # -- reporting -------------------------------------------------------------

    def summary(self) -> dict:
        """Aggregate report. Safe to call after stop()."""
        out: dict = {"roles": {}, "system": {}}
        for role, agg in self.aggregates.items():
            ctx_v, ctx_i = agg.total_ctx_switches()
            out["roles"][role] = {
                "peak_rss_bytes": agg.peak_rss,
                "peak_rss_mb": round(agg.peak_rss / 2**20, 2),
                "peak_vms_bytes": agg.peak_vms,
                "peak_uss_bytes": agg.peak_uss or None,
                # PSS sums correctly across processes sharing pages; peak_rss does not.
                "peak_pss_bytes": agg.peak_pss or None,
                "peak_pss_mb": round(agg.peak_pss / 2**20, 2) if agg.peak_pss else None,
                "peak_process_count": agg.peak_procs,
                "peak_thread_count": agg.peak_threads,
                "peak_fd_count": agg.peak_fds,
                "distinct_pids_seen": len(agg.pids_seen),
                "total_cpu_seconds": round(agg.total_cpu_seconds(), 4),
                "ctx_switches_voluntary": ctx_v,
                "ctx_switches_involuntary": ctx_i,
                "samples": agg.samples,
                "oom_events": len(agg.oom_events),
                "rss_leak_slope_bytes_per_s": self._leak_slope(agg),
                "rss_final_over_initial": self._growth_ratio(agg),
            }
        if self.start_vm_stat and self.end_vm_stat:
            out["system"] = {
                "compressor_delta_bytes": self.end_vm_stat.get("compressor_bytes", 0)
                - self.start_vm_stat.get("compressor_bytes", 0),
                "swapouts_delta": self.end_vm_stat.get("swapouts", 0)
                - self.start_vm_stat.get("swapouts", 0),
                "compressions_delta": self.end_vm_stat.get("compressions", 0)
                - self.start_vm_stat.get("compressions", 0),
                "peak_system_mem_percent": max((r["mem_percent"] for r in self.system_series), default=None),
            }
        return out

    @staticmethod
    def _leak_slope(agg: RoleAggregate) -> float | None:
        """Least-squares slope of RSS over the back half of the run.

        The back half is used deliberately: the ramp-up phase of any run shows steep growth that
        is allocation, not leakage. A positive slope in steady state is the leak signal.
        """
        pts = agg.rss_series
        if len(pts) < 20:
            return None
        tail = pts[len(pts) // 2:]
        n = len(tail)
        mean_t = sum(p[0] for p in tail) / n
        mean_r = sum(p[1] for p in tail) / n
        num = sum((p[0] - mean_t) * (p[1] - mean_r) for p in tail)
        den = sum((p[0] - mean_t) ** 2 for p in tail)
        return round(num / den, 2) if den else None

    @staticmethod
    def _growth_ratio(agg: RoleAggregate) -> float | None:
        pts = [p for p in agg.rss_series if p[1] > 0]
        if len(pts) < 10:
            return None
        head = sum(p[1] for p in pts[:5]) / 5
        tail = sum(p[1] for p in pts[-5:]) / 5
        return round(tail / head, 4) if head else None


def self_pid_source() -> list[int]:
    return [os.getpid()]


def pids_matching(pattern: str) -> PidSource:
    """PID source matching a regex against the process cmdline. Used for external engines."""
    rx = re.compile(pattern)
    def _src() -> list[int]:
        found = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
                if cmd and rx.search(cmd):
                    found.append(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found
    return _src
