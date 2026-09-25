"""P5 in-image check (G_build_A), run WHOLE under the engine's own Python inside the image:

    docker run --rm --network none -v <frame.png>:/x/frame.png:ro -v <this file>:/x/check.py:ro \
        --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine <image> /x/check.py '<expected md5 json>'

1. node identity: the image's engine/nodes/detect files carry the md5s of working/nodes/p5_infer_src (expected, argv[1]);
2. the node files compile under the engine's Python;
3. the worker module shipped in the image loads, and ONE frame goes end to end through it with a Detector built
   exactly as the node's IGlobal builds it (rfdetr, device None, threshold 0.3), on the worker's own thread;
4. its detections equal a direct detect() of the same frame, and exactly ONE LWDETR model instance exists.
Prints one line `P5_CHECK <json>`; exit 0 iff every step passed, 1 otherwise (identity failure stops at step 1).
"""
import gc
import hashlib
import importlib.util
import json
import os
import py_compile
import sys
import threading

NODE = "/opt/rocketride/engine/nodes/detect"
out = {"ok": False}


def done(rc):
    print("P5_CHECK " + json.dumps(out, default=str))
    sys.exit(rc)


try:
    expect = json.loads(sys.argv[1])
    got = {}
    for f in expect:
        p = os.path.join(NODE, f)
        got[f] = hashlib.md5(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
    out["node_md5"] = got
    out["identity_ok"] = all(got[f] == expect[f] for f in expect)
    if not out["identity_ok"]:
        out["why"] = "node identity: the image's detect node is not the P5 source"
        done(1)
    for f in expect:
        if f.endswith(".py"):
            py_compile.compile(os.path.join(NODE, f), cfile=f"/tmp/{f}c", doraise=True)
    out["compiled"] = True
    sys.path.insert(0, "/opt/rocketride/engine")
    spec = importlib.util.spec_from_file_location("p5_infer_worker", os.path.join(NODE, "infer_worker.py"))
    iw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(iw)
    from ai.common.image import ImageProcessor
    from ai.common.models.vision.detection import DEFAULT_BACKEND, DEFAULT_THRESHOLD, Detector

    det = Detector(backend=DEFAULT_BACKEND, device=None, threshold=DEFAULT_THRESHOLD, prompt=None, revision=None)
    img = ImageProcessor.load_image_from_bytes(open("/x/frame.png", "rb").read())
    seen = {}
    orig = det.detect

    def spy(image, *a, **k):
        seen["thread"] = threading.current_thread().name
        return orig(image, *a, **k)

    det.detect = spy
    w = iw.InferenceWorker(det, maxsize=4)
    r = w.detect(img, timeout=600)
    det.detect = orig
    direct = det.detect(img)
    out.update({"frame_end_to_end": True, "n_dets": len(r), "detect_ran_on": seen.get("thread"),
                "infer_thread": w.thread.name, "same_as_direct": json.dumps(r, sort_keys=True) == json.dumps(direct, sort_keys=True)})
    w.close()
    import torch

    out["torch_num_threads"] = torch.get_num_threads()
    out["lwdetr_instances"] = sum(1 for o in gc.get_objects() if isinstance(o, torch.nn.Module) and type(o).__name__ == "LWDETR")
    out["ok"] = bool(out["identity_ok"] and out["same_as_direct"] and out["lwdetr_instances"] == 1
                     and out["detect_ran_on"] == out["infer_thread"] and out["n_dets"] >= 1)
    done(0 if out["ok"] else 1)
except SystemExit:
    raise
except BaseException as e:  # noqa: BLE001
    out["error"] = f"{type(e).__name__}: {e}"
    done(1)
