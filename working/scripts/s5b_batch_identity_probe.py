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


# PRE-REGISTERED CRITERION (Ansh, 2026-09-21), fixed before the probe runs and copied into
# every output so the verdict can be checked against the rule that produced it.
CRITERION = {
    "tier1": "every frame bit-identical (boxes, scores, class ids, dtype, shape) -> PASS",
    "tier2": ("PASS labelled NUMERICALLY EQUIVALENT only if, PER FRAME: identical label sets and "
              "detection counts OUTSIDE a +/-0.001 band around the 0.3 threshold; max |score delta| "
              "<= 1e-5; max box delta <= 1e-3 px"),
    "else": "STOP S5-B",
    "band": 0.001, "threshold": 0.3, "max_score_delta": 1e-5, "max_box_delta_px": 1e-3,
    "box_space": ("OUTPUT pixels — the detector's boxes (downscaled-image space) multiplied by the "
                  "per-frame rescale factor the pipeline applies (_rescale_to_original), because "
                  "that is what reaches the emitted text; the downscaled-space delta is recorded too"),
    "hypothesis": "batched GEMM on CPU changes summation order, so Tier 1 fails and Tier 2 decides",
    "note": ("the pipeline emits scores and boxes at full float precision (_to_detection does not "
             "round), so even a Tier 2 pass changes the emitted text and its chunk hashes"),
}


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


def tier2_frame(single, batched, fx: float, fy: float) -> dict:
    """Tier 2 for ONE frame. Detections inside the +/-band around the threshold may legitimately
    appear or vanish; everything outside it must match by label and count, then pair up (same
    label, nearest box) within the score and box tolerances."""
    import numpy as np
    thr, band = CRITERION["threshold"], CRITERION["band"]

    def rows(det):
        xyxy, conf, cid = canon(det)
        if conf is None or not len(conf):
            return []
        return [(int(cid[i]) if cid is not None else -1, float(conf[i]),
                 [float(v) for v in xyxy[i]]) for i in range(len(conf))]

    a = [r for r in rows(single) if abs(r[1] - thr) > band]
    b = [r for r in rows(batched) if abs(r[1] - thr) > band]
    res = {"count_single_outside_band": len(a), "count_batched_outside_band": len(b)}
    if sorted(x[0] for x in a) != sorted(x[0] for x in b):
        res.update(ok=False, why="label multiset or count differs outside the threshold band")
        return res
    worst_s = worst_small = worst_out = 0.0
    pool = list(b)
    for cls, sc, box in a:
        cand = [x for x in pool if x[0] == cls]
        best = min(cand, key=lambda x: max(abs(x[2][j] - box[j]) for j in range(4)))
        pool.remove(best)
        worst_s = max(worst_s, abs(best[1] - sc))
        d_small = [abs(best[2][j] - box[j]) for j in range(4)]
        worst_small = max(worst_small, max(d_small))
        worst_out = max(worst_out, max(d_small[0] * fx, d_small[1] * fy, d_small[2] * fx, d_small[3] * fy))
    ok = worst_s <= CRITERION["max_score_delta"] and worst_out <= CRITERION["max_box_delta_px"]
    res.update(ok=ok, max_score_delta=worst_s, max_box_delta_small_px=worst_small,
               max_box_delta_output_px=worst_out,
               why=None if ok else "score or box delta exceeds the pre-registered tolerance")
    return res


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
    # The engine's own packages (ai/) live at the engine ROOT; a script run from /probe gets /probe
    # at sys.path[0], not the root, so the root is put on the path explicitly — the binary's own
    # directory, the image's WORKDIR, and the literal path — before any engine import.
    import os
    for root in (str(Path(sys.executable).resolve().parent), os.getcwd(), "/opt/rocketride/engine"):
        if root not in sys.path:
            sys.path.insert(0, root)
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
    smalls, factors = [], []
    for pth in paths:
        small, (ow, oh) = resize_for_inference(Image.open(pth).convert("RGB"), edge)
        smalls.append(small)
        factors.append((ow / small.size[0], oh / small.size[1]))

    out = {"criterion_preregistered": CRITERION, "source": str(src), "frames": len(smalls), "infer_edge": edge, "threshold": thr,
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
        t2 = [tier2_frame(single_a[i], batched[i], *factors[i]) for i in range(len(batched))]
        fails = [i for i, r in enumerate(t2) if not r["ok"]]
        per_b[str(B)].update(
            tier2_all_frames_ok=not fails, tier2_failing_frames=fails[:10],
            tier2_first_failure=(t2[fails[0]] if fails else None),
            tier2_max_score_delta=max((r.get("max_score_delta") or 0.0) for r in t2),
            tier2_max_box_delta_output_px=max((r.get("max_box_delta_output_px") or 0.0) for r in t2),
            tier=("TIER 1 — BIT-IDENTICAL" if not diffs else
                  "TIER 2 — NUMERICALLY EQUIVALENT" if not fails else "NEITHER"))
    out["by_batch_size"] = per_b
    tiers = {b: v["tier"] for b, v in per_b.items()}
    if all(t.startswith("TIER 1") for t in tiers.values()):
        verdict, rc = "PASS (TIER 1 — BIT-IDENTICAL at every B)", 0
    elif all(t != "NEITHER" for t in tiers.values()):
        verdict, rc = ("PASS labelled NUMERICALLY EQUIVALENT (TIER 2) — within the pre-registered "
                       "tolerances at every B, but NOT bit-identical; the emitted text and its chunk "
                       "hashes will differ from B=1"), 0
    else:
        verdict, rc = ("STOP S5-B — at least one B is neither bit-identical nor within the "
                       "pre-registered tolerances; per the ruling B>1 is a different measurement, "
                       "not an optimisation"), 1
    out["tiers_by_b"] = tiers
    out["verdict"] = verdict
    print(json.dumps(out, indent=1))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
