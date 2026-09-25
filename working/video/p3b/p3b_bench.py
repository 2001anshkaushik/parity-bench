"""P3-B BARE MICROBENCHMARK (benchmark-only). preregistration.json P3_B (2).

One RF-DETR model, constructed as the engine and the LlamaIndex arm both construct it (RFDETRBase() with the
weights' directory as the working directory — engine/ai/common/models/vision/detection.py RFDetrLoader.load;
working/video/li_video/pipeline.py), runs predict(image, threshold=0.3) on ONE fixed set of PNG frames, one at a
time, from ONE caller thread (the main thread). Runs as a bare script under an image's own interpreter:
  (a) rr:patched-video's embedded Python  (/opt/rocketride/engine/engine p3b_bench.py ...)
  (b) li:video's Python                   (python p3b_bench.py ...)
Nothing else runs in the process: no engine, no server, no pool; exactly ONE model instance exists (counted with
gc after construction and at the end; more than one refuses).

Per measured frame: the forward pass of the model's root torch module (forward pre/post hooks, CLOCK_MONOTONIC),
the calling thread's CPU across it (time.thread_time) and the process's CPU across it (time.process_time) — the
same three quantities the P1 stamped copies record in the engine and the LlamaIndex service — plus the predict
wall and a hash of the detections. Read-back: interpreter, torch / numpy / rfdetr versions and file paths, torch
threads, parallel_info, the thread environment, and the process's loaded OpenMP / BLAS / threading runtimes from
/proc/self/maps (P3-B (1)).

    p3b_bench.py --frames DIR --weights-dir DIR --out FILE.json [--warmup 10] [--null-two-models]
The thread count is the environment's (the six variables, set by docker run -e); the script never calls
set_num_threads, as neither the engine nor the LlamaIndex arm does.
"""
import argparse
import gc
import hashlib
import json
import os
import sys
import threading
import time
import types

RUNTIME_PATTERNS = ("libgomp", "libiomp", "libomp", "libmkl", "libopenblas", "libblas", "liblapack", "libtbb",
                    "libgfortran", "libtorch", "libc10", "libnuma", "_multiarray_umath", "libcblas", "libflexiblas")


def loaded_runtimes():
    libs = set()
    try:
        with open("/proc/self/maps") as f:
            for line in f:
                p = line.split()[-1] if len(line.split()) >= 6 else ""
                if p.startswith("/") and any(k in os.path.basename(p) for k in RUNTIME_PATTERNS):
                    libs.add(p)
    except OSError as e:
        return {"error": str(e)}
    return sorted(libs)


def model_roots(torch):
    """Distinct root models of the RF-DETR kind: nn.Modules that carry parameters and are not a child of another."""
    mods = [o for o in gc.get_objects() if isinstance(o, torch.nn.Module)]
    child = set()
    for m in mods:
        for c in m.children():
            child.add(id(c))
    roots = [m for m in mods if id(m) not in child and any(True for _ in m.parameters())]
    by_cls = {}
    for r in roots:
        by_cls.setdefault(type(r).__name__, 0)
        by_cls[type(r).__name__] += 1
    return by_cls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--weights-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--warmup", type=int, default=10, help="frames of a pre-pass before the measured pass")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--null-two-models", action="store_true", help="gate null control: construct a second model")
    a = ap.parse_args()
    t_start = time.time()
    # the engine stubs pyplot before importing rfdetr (detection.py RFDetrLoader.load); done in both cells so the
    # two interpreters run the same code
    sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
    import numpy
    import torch
    from PIL import Image
    import rfdetr
    from rfdetr import RFDETRBase
    cwd = os.getcwd()
    os.chdir(a.weights_dir)             # contextlib.chdir is 3.11+; the engine's own code uses it (3.12)
    try:
        model = RFDETRBase()
        extra = RFDETRBase() if a.null_two_models else None
    finally:
        os.chdir(cwd)
    root = getattr(getattr(model, "model", None), "model", None)
    if not isinstance(root, torch.nn.Module):
        raise SystemExit("REFUSED: the RF-DETR root torch module is not where the stamped copies hook it (model.model.model)")
    root_cls = type(root).__name__
    roots_after_build = model_roots(torch)
    n_models = roots_after_build.get(root_cls, 0)     # instances of the model's own root class (the mandate count)
    st = {}

    def pre(*_):
        st["fw0"] = time.monotonic(); st["t0"] = time.thread_time(); st["p0"] = time.process_time()

    def post(*_):
        st["t1"] = time.thread_time(); st["p1"] = time.process_time(); st["fw1"] = time.monotonic()
    root.register_forward_pre_hook(pre)
    root.register_forward_hook(post)
    frames = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(a.frames) for f in fs if f.endswith(".png"))
    if len(frames) <= a.warmup:
        raise SystemExit(f"REFUSED: {len(frames)} frames, warm-up {a.warmup}")
    # warm-up: a pre-pass over the first W frames (not recorded); then EVERY frame is measured, in order — the same
    # frame set the engine cell measures (its own warm-up runs on the manifest's disjoint warm rows)
    for fp in frames[:a.warmup]:
        with Image.open(fp) as im:
            model.predict(im.convert("RGB").copy(), threshold=a.threshold)
    rows = []
    caller = threading.get_native_id()
    for i, fp in enumerate(frames):
        with open(fp, "rb") as fh:
            raw = fh.read()
        with Image.open(fp) as im:
            img = im.convert("RGB").copy()
        st.clear()
        w0 = time.monotonic()
        preds = model.predict(img, threshold=a.threshold)
        w1 = time.monotonic()
        det = [(int(preds.class_id[k]), round(float(preds.confidence[k]), 5), [round(float(v), 2) for v in preds.xyxy[k]])
               for k in range(len(preds))]
        rows.append({"i": i, "frame": os.path.relpath(fp, a.frames), "frame_sha256": hashlib.sha256(raw).hexdigest(),
                     "tid": threading.get_native_id(),
                     "forward": (st["fw1"] - st["fw0"]) if "fw1" in st else None,
                     "fw_thread_cpu": (st["t1"] - st["t0"]) if "t1" in st else None,
                     "fw_proc_cpu": (st["p1"] - st["p0"]) if "p1" in st else None,
                     "predict_wall": w1 - w0, "n_dets": len(det),
                     "dets_sha256": hashlib.sha256(json.dumps(det).encode()).hexdigest()})
    roots_end = model_roots(torch)
    th = []
    for tid in sorted(os.listdir("/proc/self/task"), key=int):
        try:
            with open(f"/proc/self/task/{tid}/comm") as f:
                th.append([int(tid), f.read().strip()])
        except OSError:
            continue
    rb = {"python": sys.version, "executable": sys.executable, "pid": os.getpid(),
          "torch": {"version": torch.__version__, "file": torch.__file__, "num_threads": torch.get_num_threads(),
                    "num_interop_threads": torch.get_num_interop_threads(),
                    "parallel_info": torch.__config__.parallel_info(),
                    "cpu_capability": torch.backends.cpu.get_cpu_capability(), "grad_enabled": torch.is_grad_enabled()},
          "numpy": {"version": numpy.__version__, "file": numpy.__file__},
          "rfdetr": {"version": getattr(rfdetr, "__version__", None), "file": rfdetr.__file__},
          "env": {k: v for k, v in os.environ.items() if k.startswith(("OMP_", "MKL_", "KMP_", "GOMP_", "OPENBLAS_", "VECLIB_",
                                                                         "NUMEXPR_", "TORCH_", "MALLOC_", "LD_PRELOAD", "PYTORCH_"))},
          "process_affinity": sorted(os.sched_getaffinity(0)), "os_threads_at_end": th,
          "loaded_runtimes": loaded_runtimes(),
          "model_roots_after_build": roots_after_build, "model_roots_at_end": roots_end,
          "rfdetr_models_after_build": n_models, "root_class": root_cls, "caller_native_tid": caller}
    out = {"kind": "p3b_bench", "t_start": t_start, "t_end": time.time(), "frames_dir": a.frames, "n_frames": len(frames),
           "warmup": a.warmup, "threshold": a.threshold, "null_two_models": a.null_two_models,
           "one_model_instance": n_models == 1, "readback": rb, "rows": rows}
    with open(a.out, "w") as f:
        json.dump(out, f)
    meas = [r for r in rows if r["forward"]]
    fw = sum(r["forward"] for r in meas)
    print("P3B_BENCH " + json.dumps({"out": a.out, "measured_frames": len(meas), "one_model_instance": n_models == 1,
                                     "rfdetr_models": n_models, "forward_mean_s": fw / len(meas) if meas else None,
                                     "cores_in_forward": (sum(r["fw_proc_cpu"] for r in meas) / fw) if fw else None,
                                     "torch_threads": torch.get_num_threads()}))
    if n_models != 1:
        sys.exit(3)                     # the mandate: exactly one model instance
    del extra


if __name__ == "__main__":
    main()
