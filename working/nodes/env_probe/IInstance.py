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


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        import sys
        info = {
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
        self.instance.writeText(json.dumps(info))

    def close(self):
        self.buf = ""
