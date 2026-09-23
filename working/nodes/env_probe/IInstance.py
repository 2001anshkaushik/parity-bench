# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# DECLARED vs MEASURED, for thread pinning.
#
# `OMP_NUM_THREADS=1 bash start_engine.sh` exports a variable into the ENGINE process. It does not
# prove the variable survives into the task process that actually runs node code, and it does not
# prove torch read it — torch caches its thread count at import, so a variable set after import has
# no effect. This node reports what is TRUE INSIDE THE TASK PROCESS at request time.
#
# Every anchor measured with a "pinned" engine is void unless this node reports 1.
import json
import os
import threading

from rocketlib import IInstanceBase

KEYS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS")


def _d0() -> dict:
    """Instance accounting read INSIDE this process (schema 3).

    root_modules_with_params: every torch.nn.Module the garbage collector tracks, reduced to the
    ROOTS (modules that are no other module's child) that own parameters, grouped by class, with
    the number of DISTINCT weight tensors (first parameter's data_ptr) so a second copy of a model
    is visible even when it shares a class with the first. python_threads: threading.enumerate()
    grouped by name with the trailing index removed (asyncio_0..asyncio_31 -> asyncio, count 32).
    proc_threads: every OS thread of the process (/proc/self/status), Python or not.
    """
    import gc
    import re
    from collections import Counter
    import sys
    out: dict = {"d0_schema": 2, "pid": os.getpid(), "ppid": os.getppid()}
    # d0_schema 2 (2026-09-23): is any TRACER installed? Every engine thread starts through
    # pydevd's wrapper (_pydev_bundle/pydev_monkey.py in each stack); an active trace function
    # would run on every Python line of every thread. Read, never changed.
    out["trace"] = {"sys_gettrace_this_thread": repr(sys.gettrace()),
                    "threading_trace_hook": repr(getattr(threading, "_trace_hook", None)),
                    "threading_profile_hook": repr(getattr(threading, "_profile_hook", None)),
                    "sys_getprofile_this_thread": repr(sys.getprofile()),
                    "pydevd_loaded": "pydevd" in sys.modules,
                    "debugpy_loaded": "debugpy" in sys.modules}
    try:
        out["trace"]["sys_monitoring_tools"] = {i: sys.monitoring.get_tool(i) for i in range(6)
                                                if sys.monitoring.get_tool(i)}
    except Exception as e:
        out["trace"]["sys_monitoring_error"] = f"{type(e).__name__}: {e}"
    try:
        with open("/proc/self/status") as f:
            m = re.search(r"^Threads:\s+(\d+)", f.read(), re.M)
        out["proc_threads"] = int(m.group(1)) if m else None
    except OSError as e:
        out["proc_threads_error"] = str(e)
    names = [t.name for t in threading.enumerate()]
    out["python_threads"] = len(names)
    out["python_threads_by_prefix"] = dict(Counter(re.sub(r"[_-]?\d+$", "", n) for n in names))
    idx = [int(n.split("_", 1)[1]) for n in names
           if n.startswith("asyncio_") and n.split("_", 1)[1].isdigit()]
    out["asyncio_executor_threads_alive"] = len(idx)
    out["asyncio_executor_max_index"] = max(idx) if idx else None
    try:
        import torch
        import warnings
        with warnings.catch_warnings():          # isinstance() on deprecated torch aliases warns
            warnings.simplefilter("ignore")
            mods = [o for o in gc.get_objects() if isinstance(o, torch.nn.Module)]
        child = set()
        for m_ in mods:
            for c in m_.children():
                child.add(id(c))
        roots: dict = {}
        for m_ in mods:
            if id(m_) in child:
                continue
            ps = list(m_.parameters())
            if not ps:
                continue
            key = f"{type(m_).__module__}.{type(m_).__qualname__}"
            roots.setdefault(key, []).append((sum(p.numel() for p in ps), ps[0].data_ptr()))
        out["root_modules_with_params"] = {
            k: {"count": len(v), "distinct_weights": len({x[1] for x in v}),
                "params": sorted(x[0] for x in v)} for k, v in roots.items()}
        out["model_instances_total"] = sum(len({x[1] for x in v}) for v in roots.values())
    except Exception as e:                       # torch absent: no models to count
        out["modules_error"] = f"{type(e).__name__}: {e}"
    return out


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        # Answer ONLY a probe (2026-09-23, amendment 4). closing() runs for EVERY pipe instance, so on
        # a measured pipe this node used to build its whole read-back — and, since schema 3, a full
        # garbage-collector scan holding the GIL (~0.1 s) — for every PDF, which never reaches its
        # text lane. A document that sent this node no text gets nothing: no scan, no output.
        if not self.buf:
            return
        import sys
        info = {
            # Schema version (2026-08-22): a STALE baked node emits an older
            # field set; a consumer that reads a missing field with .get()
            # cannot tell absence from a negative value. Every consumer asserts
            # this key is present and >= its required version BEFORE reading any
            # field, so a stale instrument fails loud with "rebuild", never
            # silently as None. Bump when the emitted field set changes.
            "env_probe_schema": 3,
            "pid": os.getpid(),
            "env": {k: os.environ.get(k) for k in KEYS},
            "os_cpu_count": os.cpu_count(),
            "threads_alive": threading.active_count(),
            # Interpreter identity read-back (2026-08-21): the container carries
            # TWO pythons (apt 3.10 on PATH for SDK/bootcheck; CPython embedded
            # in the engine ELF running all node code). This reports the one
            # that MATTERS, from inside it. Cross-arm version goes in
            # provenance as a DECLARED value, never discovered.
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
        }
        # torch is the one that actually matters: it decides intra-op parallelism for the
        # embedding forward pass. Import it the same way the embedding node does.
        try:
            import torch
            info["torch_num_threads"] = torch.get_num_threads()
            info["torch_num_interop_threads"] = torch.get_num_interop_threads()
            info["torch_version"] = torch.__version__
        except Exception as e:
            info["torch_error"] = f"{type(e).__name__}: {e}"

        # Phase 2 (video) extension, 2026-08-20: detect-identity read-back.
        # detection.py:130 falls back to RT-DETR (a DIFFERENT model) when
        # `from rfdetr import RFDETRBase` fails — silently. Attached to the
        # video pipe (a3_env_torch pattern: one pipeline = one task process),
        # this node reports that exact import predicate from INSIDE the process
        # whose detect node already loaded, plus the resolved package versions
        # the parity pins must match. On a pipe without detect, rfdetr is
        # simply not installed and the honest answer is import_error.
        try:
            import sys as _sys
            import types as _types
            _sys.modules.setdefault("matplotlib.pyplot", _types.ModuleType("matplotlib.pyplot"))
            from rfdetr import RFDETRBase  # noqa: F401 — the fallback predicate itself
            info["rfdetr_import_ok"] = True
        except Exception as e:
            info["rfdetr_import_ok"] = False
            info["rfdetr_import_error"] = f"{type(e).__name__}: {e}"
        from importlib.metadata import PackageNotFoundError, version
        pkgs = {}
        for pkg in ("rfdetr", "torchvision", "transformers", "supervision",
                    "timm", "sentence-transformers", "imageio-ffmpeg"):
            try:
                pkgs[pkg] = version(pkg)
            except PackageNotFoundError:
                pkgs[pkg] = None
        info["package_versions"] = pkgs
        # Schema 3 (P0, 2026-09-23): D0 INSTANCE ACCOUNTING from inside the task process. The
        # parity mandate is ONE engine process, ONE pipeline, ONE model instance per model; this
        # counts what is actually loaded here rather than what the pipe declares.
        info["d0"] = _d0()
        self.instance.writeText(json.dumps(info))

    def close(self):
        self.buf = ""
