"""S5-B correctness PRE-CHECK: is RF-DETR's batched forward pass bit-identical to one frame at a time?

Run INSIDE a throwaway container of the UNMODIFIED image, under the engine's own embedded
interpreter — the same torch, the same oneDNN/MKL build, the same baked weights the detect node
loads — so the numerics are the ones a patched node would actually get:

    docker run --rm --network none -v <video_dir>:/v:ro -v <this_dir>:/probe:ro \
        -w /opt/rocketride/engine rr:patched-video \
        /opt/rocketride/engine/engine /probe/s5b_batch_identity_probe.py /v/<video> 24

The argument may be a VIDEO (frames extracted inside the container at the campaign's own 15 s
interval, into the container's /tmp, so nothing is written on the host) or a directory of frames.

WHY FIRST. The engine never passes the detector more than one frame, but rfdetr's predict()
already accepts a list, resizes each image to one square resolution, torch.stacks them and runs
ONE forward pass. Whether frame i of a batch comes out bit-identical to frame i alone is the
entire S5-B question, and it is not a given: on CPU a GEMM whose batch dimension changes may be
blocked differently, which changes the summation order. The Stage 5 ruling makes bit-identity the
gate (labels, scores, counts, ordered per-frame hashes) — a batch that differs is a different
measurement, not an optimisation, and the sweep stops. So this runs BEFORE any node is patched or
any image is built: a failure here saves the whole build.

THE FRAMES are pre-downscaled exactly as Detector.detect does (resize_for_inference to the
backend's infer_edge, 560), because that is the image the backend would be handed either way.

NULL CONTROLS, both must behave before any comparison is believed (register entry 2):
  N1  single vs single, same frames, twice — must be BIT-IDENTICAL. If one frame at a time is not
      even reproducible, "batched differs" would be noise, and the probe reports INSTRUMENT
      NON-DETERMINISTIC instead of a verdict.
  N2  the comparator must SEE a difference where one exists: frame 0's detections against frame
      1's must compare DIFFERENT. A comparator that calls two different frames identical proves
      nothing when it calls batched and single identical.

Prints one JSON object on stdout and its own sha256 on stderr.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import types
from pathlib import Path


def canon(det) -> list:
    """The raw rfdetr outputs, as exact bytes, per frame: boxes, scores, class ids."""
    import numpy as np
    xyxy = getattr(det, "xyxy", None)
    conf = getattr(det, "confidence", None)
    cid = getattr(det, "class_id", None)
    return [np.asarray(x) if x is not None else None for x in (xyxy, conf, cid)]


def frame_hash(det) -> str:
    h = hashlib.sha256()
    for a in canon(det):
        h.update(b"None" if a is None else (str(a.dtype) + str(a.shape)).encode() + a.tobytes())
    return h.hexdigest()


def max_abs(a, b) -> float | None:
    import numpy as np
    ca, cb = canon(a), canon(b)
    worst = 0.0
    for x, y in zip(ca, cb):
        if x is None or y is None:
            if (x is None) != (y is None):
                return float("inf")
            continue
        if x.shape != y.shape:
            return float("inf")
        if x.size:
            worst = max(worst, float(np.max(np.abs(x.astype("float64") - y.astype("float64")))))
    return worst


def main() -> int:
    print(f"s5b_batch_identity_probe.py sha256: "
          f"{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}", file=sys.stderr)
    src, n = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 24
    if src.is_file():
        import subprocess
        import tempfile
        import imageio_ffmpeg
        frames_dir = Path(tempfile.mkdtemp(prefix="s5b_frames_"))
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(src),
                            "-vf", "fps=1/15", "-frames:v", str(n), str(frames_dir / "f_%05d.png")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(json.dumps({"verdict": "NOT RUN", "reason": f"ffmpeg rc={r.returncode}: {r.stderr[:300]}"}))
            return 2
    else:
        frames_dir = src
    sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
    import torch
    from PIL import Image
    from ai.common.models.vision.detection import Detector, BACKENDS
    from ai.common.image.dense_resize import resize_for_inference

    det = Detector(backend="rfdetr", device=None, threshold=0.3, prompt=None)
    backend = det._bundle["detector"]
    model, thr = backend._model, backend.threshold
    edge = BACKENDS["rfdetr"].infer_edge
    paths = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in (".png", ".jpg"))[:n]
    if len(paths) < 8:
        print(json.dumps({"verdict": "NOT RUN", "reason": f"only {len(paths)} frames"}))
        return 2
    smalls = [resize_for_inference(Image.open(p).convert("RGB"), edge)[0] for p in paths]

    out = {"source": str(src), "frames": len(smalls), "infer_edge": edge, "threshold": thr,
           "torch": torch.__version__, "torch_num_threads": torch.get_num_threads(),
           "torch_num_interop_threads": torch.get_num_interop_threads(),
           "backend_impl": backend._impl, "model_resolution": getattr(model.model, "resolution", None)}

    t = time.perf_counter()
    single_a = [model.predict(s, threshold=thr) for s in smalls]
    out["single_seconds"] = round(time.perf_counter() - t, 3)
    single_b = [model.predict(s, threshold=thr) for s in smalls]
    ha, hb = [frame_hash(d) for d in single_a], [frame_hash(d) for d in single_b]
    n1 = ha == hb
    out["null_N1_single_is_reproducible"] = n1
    n2 = frame_hash(single_a[0]) != frame_hash(single_a[1])
    out["null_N2_comparator_sees_a_different_frame"] = n2
    if not n1:
        out["verdict"] = "INSTRUMENT NON-DETERMINISTIC — single-frame inference is not reproducible; no identity verdict is possible"
        print(json.dumps(out, indent=1)); return 3
    if not n2:
        out["verdict"] = "COMPARATOR BLIND — two different frames compared identical; no identity verdict is possible"
        print(json.dumps(out, indent=1)); return 3

    per_b = {}
    for B in (2, 4, 8):
        t = time.perf_counter()
        batched = []
        for i in range(0, len(smalls), B):
            r = model.predict(smalls[i:i + B], threshold=thr)
            batched.extend(r if isinstance(r, list) else [r])
        secs = round(time.perf_counter() - t, 3)
        diffs = [i for i, d in enumerate(batched) if frame_hash(d) != ha[i]]
        per_b[str(B)] = {
            "seconds": secs, "frames": len(batched),
            "bit_identical_frames": len(batched) - len(diffs),
            "differing_frames": diffs[:10],
            "max_abs_difference": (max(max_abs(batched[i], single_a[i]) for i in diffs)
                                   if diffs else 0.0),
            "detection_counts_equal": all(len(canon(batched[i])[1] if canon(batched[i])[1] is not None else [])
                                          == len(canon(single_a[i])[1] if canon(single_a[i])[1] is not None else [])
                                          for i in range(len(batched))),
            "BIT_IDENTICAL": not diffs}
    out["by_batch_size"] = per_b
    all_ok = all(v["BIT_IDENTICAL"] for v in per_b.values())
    out["verdict"] = ("PASS — every batch size bit-identical to one frame at a time; S5-B may proceed "
                      "to the node patch and the end-to-end control" if all_ok else
                      "FAIL — batched inference is NOT bit-identical to single-frame inference; per the "
                      "Stage 5 ruling B>1 is a different measurement, not an optimisation, and the "
                      "S5-B sweep stops here")
    print(json.dumps(out, indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
