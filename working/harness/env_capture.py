"""Environment fingerprint, captured with every run.

A benchmark number without its environment is an anecdote. This block is what lets someone else
tell whether their re-run is comparable — and lets us discard our own runs retroactively when we
discover the host was not quiet.
"""

from __future__ import annotations

import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time


def _sh(cmd: list[str], timeout: float = 5.0) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or None
    except Exception:
        return None


def _sysctl(key: str) -> str | None:
    return _sh(["sysctl", "-n", key])


def thermal_state() -> dict:
    """Apple Silicon throttles under sustained load. A run that thermally throttled partway is
    not comparable to one that did not, so we record pressure before and after every run."""
    return {
        "thermal_pressure": _sh(["pmset", "-g", "therm"]),
        "load_avg": os.getloadavg(),
    }


def capture() -> dict:
    import psutil

    vm = psutil.virtual_memory()
    env = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": _sysctl("machdep.cpu.brand_string"),
            "python": sys.version,
            "python_impl": platform.python_implementation(),
        },
        "cpu": {
            "logical": psutil.cpu_count(logical=True),
            "physical": psutil.cpu_count(logical=False),
            "performance_cores": _sysctl("hw.perflevel0.logicalcpu"),
            "efficiency_cores": _sysctl("hw.perflevel1.logicalcpu"),
        },
        "memory": {
            "total_bytes": vm.total,
            "total_gib": round(vm.total / 2**30, 2),
            "available_bytes": vm.available,
        },
        "limits": {
            "RLIMIT_NOFILE": resource.getrlimit(resource.RLIMIT_NOFILE),
            "RLIMIT_NPROC": resource.getrlimit(resource.RLIMIT_NPROC),
            "RLIMIT_AS": resource.getrlimit(resource.RLIMIT_AS),
        },
        "thermal_before": thermal_state(),
        # Threading libraries silently oversubscribe: numpy/BLAS will start one thread per core
        # inside *every* process of a process pool. Left unset, a 14-worker pool can create ~200
        # threads and the result measures thread thrash rather than the framework. We record
        # what was actually set so this is auditable after the fact.
        "thread_env": {
            k: os.environ.get(k)
            for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                      "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TOKENIZERS_PARALLELISM")
        },
        "host_quiet_check": _host_load(),
    }
    return env


def _host_load() -> dict:
    """Top CPU consumers other than us — evidence for or against a quiet host."""
    import psutil

    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            procs.append((p.info["cpu_percent"] or 0.0, p.info["name"], p.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(reverse=True)
    return {
        "load_avg": os.getloadavg(),
        "top_processes": [{"name": n, "pid": pid, "cpu_percent": c} for c, n, pid in procs[:8]],
    }


def package_versions(names: list[str]) -> dict[str, str | None]:
    import importlib.metadata as md

    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = md.version(n)
        except md.PackageNotFoundError:
            out[n] = None
    return out


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2, default=str))
