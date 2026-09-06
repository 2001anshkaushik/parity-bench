#!/usr/bin/env python3
"""WRAPPER-RESIZE PARITY (V-D, designed 2026-09-06) — DO NOT RUN UNTIL THE
LIFETIMES RUN HAS LANDED AND ANSH RULES. `--side` runs INSIDE the rr
container with the engine's own python (rfdetr 1.5.2, Pillow 10.4.0, torch
2.10.0) at the campaign thread condition (six BLAS/OMP vars = 2 -> intraop 2).

THE MECHANISM IT CONFIRMS OR REFUTES (located in the engine source 2026-09-06):
  engine/nodes/detect/IGlobal.py:74     detector = Detector(backend='rfdetr', ...)
  engine/nodes/detect/IInstance.py:107  self.IGlobal.detector.detect(image)   # the FACADE
  engine/ai/common/models/vision/detection.py
      :60   BACKENDS['rfdetr'] = BackendSpec(..., infer_edge=560, ...)
      :466  self._infer_max_edge = ...infer_edge
      Detector.detect (:~490-550): small, (w, h) = resize_for_inference(image,
            self._infer_max_edge); DetectorLoader.preprocess(bundle, [small]) ->
            inference -> _rescale_to_original(dets, small.size, w, h)
  engine/ai/common/image/dense_resize.py:resize_for_inference — NO-OP when
      max(w, h) <= max_edge; else image.resize((floor(w*s), floor(h*s)),
      Image.LANCZOS), s = max_edge / max(w, h).
  LlamaIndex (li_video/pipeline.py:215) and the Ruling-Y probe
  (probe_detector_parity.py:36-75) call RFDETRBase().predict on the RAW frame:
  the probe replicated the BACKEND's detect (detection.py:172, "passes the
  image untouched"), never the facade's (register entry 33).

PRE-REGISTERED, on frame 10 of HouseOnBareMountain.mp4 (714x480, PNG sha256
83a02b923d8c1aea..., the Ruling-Y campaign-diverging frame, landed at
results/detector-parity-y-20260902/frame10.png):
  V-D CONFIRMS : predict(resize_for_inference(frame, 560) -> 560x376) reproduces
                 the CAMPAIGN RR output for this frame EXACTLY (35-film records,
                 both passes): labels {bottle x2, chair x3, person}, scores
                 0.946473300 0.935210288 0.856113911 0.449365526 0.384643406
                 0.318114191 (9 dp) — while predict(frame) reproduces the
                 campaign LI output (5 detections: 0.953240395 0.934387743
                 0.862633228 0.489725053 0.432809502 — also the Ruling-Y probe,
                 both sides, intraop 2). The mechanism is then NAMED and
                 REPRODUCED outside the serving context.
  V-D REFUTES  : the resized frame does NOT reproduce the campaign RR output
                 (the pre-downscale is not the whole story).
  CANNOT COMPARE: intraop != 2 (thread 16 vs 2 moves the 7th decimal — the Y
                 artifacts show 0.953240275 vs 0.953240395; a 1e-7 disagreement
                 is the thread condition, not the mechanism); frame sha
                 mismatch; a side that cannot bit-match itself; or the RAW frame
                 failing to reproduce LI (the known baseline).
  CONTROL      : a <=560 frame (derived here from frame 10 at 357x240) must be a
                 NO-OP through resize_for_inference and predict identically both
                 ways. Every predict is run TWICE (self-determinism null).
  WORKLOAD (TASK 3, 2026-09-06): alongside the verdict, record on EACH path the
                 detector-visible pixel count — (i) the pixels handed to
                 rfdetr.predict (raw 714x480 = 342,720; facade 560x376 = 210,560,
                 x0.614) and (ii) the tensor the MODEL actually consumes, captured
                 by a hook on the model's inference entry point during every
                 predict. rfdetr 1.5.2 predict (held copy detr_li.py == detr_engine.py,
                 byte-identical from both containers) does F.to_tensor -> F.normalize ->
                 F.resize(img, (resolution, resolution)) (detr.py:379) before
                 inference, so the pre-registered expectation is [1, 3, 560, 560] on
                 BOTH paths = the model does the same work per frame on both arms;
                 the facade changes the pixels rfdetr's resize starts from, not the
                 model's input. The facade's LANCZOS pass is timed (median of 5) so
                 the RR-side extra preprocessing has a measured number too.

Modes: --side --frame frame10.png --out side_vd.json  (inside rr)
       --compare side_vd.json                          (laptop or box)
       --self-test                                     (laptop; no torch/PIL needed)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

INFER_EDGE = 560
SIX = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
       'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS')
FRAME10_SHA16 = '83a02b923d8c1aea'
ENGINE_HELPER = '/opt/rocketride/engine/ai/common/image/dense_resize.py'   # in the rr image ($ENGINE_DIR)

# campaign outputs for frame 10 (results/films_mainrun_20260901T204015Z records,
# frame index 10 of HouseOnBareMountain.mp4; identical in pass 1 and pass 2)
EXPECTED_RR = {'labels': ['bottle', 'bottle', 'chair', 'chair', 'chair', 'person'],
               'scores': ['0.946473300', '0.935210288', '0.856113911', '0.449365526',
                          '0.384643406', '0.318114191']}
EXPECTED_LI = {'labels': ['bottle', 'bottle', 'chair', 'chair', 'person'],
               'scores': ['0.953240395', '0.934387743', '0.862633228', '0.489725053',
                          '0.432809502']}


def engine_resize_size(w: int, h: int, max_edge: int = INFER_EDGE) -> Tuple[int, int]:
    """dense_resize.resize_for_inference's size rule, verbatim: no-op at
    max(w,h) <= max_edge (clamped to [256, 4096]); else floor(x * max_edge/max)."""
    max_edge = max(256, min(4096, int(max_edge)))
    if max(w, h) <= max_edge:
        return w, h
    s = max_edge / float(max(w, h))
    return max(1, int(w * s)), max(1, int(h * s))


def engine_resize(image, max_edge: int = INFER_EDGE):
    """Port of resize_for_inference (PIL LANCZOS). Returns (image_or_resized, noop)."""
    from PIL import Image
    w, h = image.size
    nw, nh = engine_resize_size(w, h, max_edge)
    if (nw, nh) == (w, h):
        return image, True
    return image.resize((nw, nh), resample=Image.LANCZOS), False


def engine_helper_check(image) -> dict:
    """If the engine's own dense_resize.py is present (inside the rr image),
    import it BY PATH (its package __init__ pulls rocketlib) and prove the
    port agrees on size and pixels. Absence is recorded, never assumed."""
    if not os.path.exists(ENGINE_HELPER):
        return {'state': f'unavailable: {ENGINE_HELPER} not present'}
    try:
        spec = importlib.util.spec_from_file_location('dense_resize_by_path', ENGINE_HELPER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        theirs, orig = mod.resize_for_inference(image, INFER_EDGE)
        mine, _ = engine_resize(image, INFER_EDGE)
        return {'state': 'measured', 'size_theirs': list(theirs.size), 'size_port': list(mine.size),
                'pixels_equal': _array_sha(theirs) == _array_sha(mine), 'orig': list(orig)}
    except Exception as exc:
        return {'state': f'unavailable: {exc!r}'}


def _array_sha(image) -> str:
    import numpy as np
    return hashlib.sha256(np.ascontiguousarray(np.asarray(image)).tobytes()).hexdigest()


def _detections(preds) -> List[List[str]]:
    """[label, score@9dp] sorted by score desc — the Ruling-Y probe's shape."""
    try:
        from rfdetr.util.coco_classes import COCO_CLASSES
        names = [COCO_CLASSES[int(c)] for c in preds.class_id]
    except Exception:
        names = [str(c) for c in getattr(preds, 'class_id', [])]
    scores = [float(s) for s in getattr(preds, 'confidence', [])]
    rows = sorted(zip(names, scores), key=lambda r: -r[1])
    return [[n, f'{s:.9f}'] for n, s in rows]


def _install_shape_hook(det) -> dict:
    """Wrap the rfdetr model's inference entry points (eager `inference`,
    optimized `inference_model`) so every predict records the tensor shape the
    MODEL consumes — the detector-visible pixel count at the model. Absence of
    a hookable target is recorded, never assumed away."""
    rec = {'shapes': [], 'targets': [], 'resolution': getattr(getattr(det, 'model', None), 'resolution', None)}
    m = getattr(det, 'model', None)

    def _shape(x):
        try:
            return list(x.shape)
        except Exception:
            return 'unshaped'
    # eager path (held detr.py:407): predictions = self.model.model(batch_tensor)
    mm = getattr(m, 'model', None)
    if mm is not None and hasattr(mm, 'register_forward_pre_hook'):
        mm.register_forward_pre_hook(lambda mod, args: rec['shapes'].append(_shape(args[0]) if args else 'no-args'))
        rec['targets'].append('model.model forward pre-hook (eager path, detr.py:407)')
    # optimized path (detr.py:405): self.model.inference_model(...) — None unless optimize_for_inference() ran
    fn = getattr(m, 'inference_model', None)
    if callable(fn):
        def wrapped(x, *a, _fn=fn, **k):
            rec['shapes'].append(_shape(x))
            return _fn(x, *a, **k)
        m.inference_model = wrapped
        rec['targets'].append('model.inference_model wrapper (optimized path, detr.py:405)')
    rec['state'] = 'measured' if rec['targets'] else 'unavailable: neither model.model (module) nor inference_model to hook'
    return rec


def _take_shapes(hook: dict) -> List:
    """Unique shapes recorded since the last take, in order; then clear."""
    seen, out = set(), []
    for s in hook['shapes']:
        key = json.dumps(s)
        if key not in seen:
            seen.add(key)
            out.append(s)
    hook['shapes'].clear()
    return out


def workload_symmetric(wl: dict) -> Optional[bool]:
    """True when the model consumed identical tensor shapes on the raw and the
    facade-resized path; None when either side is unmeasured."""
    a, b = wl.get('model_input_shapes_raw'), wl.get('model_input_shapes_resized')
    if not a or not b:
        return None
    return a == b


def _runs(det, image, thresholds=(0.3, 0.001)) -> dict:
    out = {}
    for thr in thresholds:
        a = _detections(det.predict(image, threshold=thr))
        b = _detections(det.predict(image, threshold=thr))
        out[str(thr)] = {'detections': a, 'self_deterministic': a == b}
    return out


def side(frame_path: str, out_path: str) -> int:
    import torch
    from PIL import Image
    from rfdetr import RFDETRBase
    threads = {'intraop': torch.get_num_threads(), 'interop': torch.get_num_interop_threads(),
               'captured': 'after model construction, before first predict'}
    env = {k: os.environ.get(k) for k in SIX}
    raw = Path(frame_path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if not sha.startswith(FRAME10_SHA16):
        print(f'NOT DONE — frame sha {sha[:16]} != pinned {FRAME10_SHA16}; nothing predicted')
        return 2
    img = Image.open(io.BytesIO(raw))
    img.load()                                   # the engine's load path (image.py:36-38)
    det = RFDETRBase()
    threads = {'intraop': torch.get_num_threads(), 'interop': torch.get_num_interop_threads(),
               'captured': 'after model construction, before first predict'}
    hook = _install_shape_hook(det)
    import inspect
    import time
    try:
        src = inspect.getsource(type(det).predict).splitlines()
        resize_lines = [l.strip() for l in src if 'resize' in l.lower() or 'resolution' in l.lower()]
    except Exception as exc:
        resize_lines = [f'unavailable: {exc!r}']
    lanczos_ms = []
    for _ in range(5):
        t0 = time.perf_counter()
        small, noop = engine_resize(img)
        lanczos_ms.append((time.perf_counter() - t0) * 1000)
    control = img.resize((357, 240), resample=Image.LANCZOS)   # <=560: must be a no-op through the wrapper
    c_small, c_noop = engine_resize(control)
    raw_runs = _runs(det, img)
    shapes_raw = _take_shapes(hook)
    resized_runs = _runs(det, small)
    shapes_resized = _take_shapes(hook)
    rec = {
        'design': 'V-D wrapper-resize parity (2026-09-06); see module docstring',
        'libs': {'rfdetr': _ver('rfdetr'), 'torch': torch.__version__, 'torchvision': _ver('torchvision'),
                 'pillow': _ver('PIL')},
        'torch_threads': threads, 'thread_env': env,
        'frame': {'png': os.path.basename(frame_path), 'png_sha256': sha, 'size': list(img.size), 'mode': img.mode,
                  'engine_resized_size': list(small.size), 'engine_resize_noop': noop,
                  'engine_resized_array_sha256': _array_sha(small), 'raw_array_sha256': _array_sha(img),
                  'engine_helper': engine_helper_check(img),
                  'raw': raw_runs, 'resized': resized_runs,
                  # TASK 3 (2026-09-06): the detector-visible pixel count on each path
                  'workload': {
                      'pixels_to_predict_raw': img.size[0] * img.size[1],
                      'pixels_to_predict_resized': small.size[0] * small.size[1],
                      'ratio': round(small.size[0] * small.size[1] / (img.size[0] * img.size[1]), 4),
                      'model_input_shapes_raw': shapes_raw,
                      'model_input_shapes_resized': shapes_resized,
                      'model_resolution': hook.get('resolution'),
                      'hook_state': hook['state'], 'hook_targets': hook['targets'],
                      'facade_lanczos_ms_median_of_5': round(sorted(lanczos_ms)[2], 2),
                      'predict_resize_source_lines': resize_lines[:8],
                      'basis': 'pixels_to_predict = the PIL image handed to rfdetr.predict; model_input_shapes = '
                               'tensor shapes seen by the hooked model inference entry point during the two '
                               'predicts per threshold (unique, in order); rfdetr resizes every input to '
                               '(resolution, resolution) before inference (detr.py:379 in the held copy)'}},
        'control': {'size': list(control.size), 'engine_resize_noop': c_noop,
                    'raw': _runs(det, control), 'resized': _runs(det, c_small)},
    }
    Path(out_path).write_text(json.dumps(rec, indent=1))
    print(f'wrote {out_path}: frame {img.size} -> {small.size} (noop={noop}); intraop {threads["intraop"]}; '
          f'resized@0.3 {rec["frame"]["resized"]["0.3"]["detections"]}')
    return 0


def _ver(mod: str) -> Optional[str]:
    try:
        return __import__(mod).__version__
    except Exception:
        return None


def _match(det_rows: List[List[str]], expected: dict) -> Tuple[bool, str]:
    labels = sorted(r[0] for r in det_rows)
    scores = [r[1] for r in det_rows]
    if labels != sorted(expected['labels']):
        return False, f'labels {labels} != {sorted(expected["labels"])}'
    if scores == expected['scores']:
        return True, 'labels + scores bit-equal at 9 dp'
    try:
        deltas = [abs(float(a) - float(b)) for a, b in zip(scores, expected['scores'])]
        if len(scores) == len(expected['scores']) and max(deltas) < 1e-6:
            return True, f'labels equal; scores within 1e-6 (max delta {max(deltas):.1e} — thread-condition noise class)'
        return False, f'scores {scores} != {expected["scores"]} (max delta {max(deltas) if deltas else "n/a"})'
    except ValueError:
        return False, 'scores unparsable'


def compare(side_json: str) -> int:
    d = json.loads(Path(side_json).read_text())
    fr, ct = d['frame'], d['control']
    refusals = []
    if not str(fr.get('png_sha256', '')).startswith(FRAME10_SHA16):
        refusals.append(f"frame sha {str(fr.get('png_sha256'))[:16]} != {FRAME10_SHA16}")
    if d.get('torch_threads', {}).get('intraop') != 2:
        refusals.append(f"intraop {d.get('torch_threads', {}).get('intraop')} != 2 (campaign condition)")
    for name, blk in (('frame.raw', fr['raw']), ('frame.resized', fr['resized']),
                      ('control.raw', ct['raw']), ('control.resized', ct['resized'])):
        for thr, v in blk.items():
            if not v.get('self_deterministic'):
                refusals.append(f'{name}@{thr} not self-deterministic')
    ok_li, why_li = _match(fr['raw']['0.3']['detections'], EXPECTED_LI)
    if not ok_li:
        refusals.append(f'RAW frame does not reproduce the campaign LI / Ruling-Y baseline: {why_li}')
    if refusals:
        print('CANNOT COMPARE — ' + '; '.join(refusals))
        print('  (no verdict: the same-input / same-condition gate refused; nothing below is a finding)')
        return 3
    ok_rr, why_rr = _match(fr['resized']['0.3']['detections'], EXPECTED_RR)
    ctrl_ok = ct['engine_resize_noop'] and ct['raw'] == ct['resized']
    helper = fr.get('engine_helper', {})
    print(f"frame {fr['size']} -> engine-resized {fr['engine_resized_size']} (noop={fr['engine_resize_noop']}); "
          f"engine helper: {helper.get('state')}"
          + (f", pixels_equal={helper.get('pixels_equal')}" if helper.get('state') == 'measured' else ''))
    print(f'raw     vs campaign LI : {why_li}')
    print(f'resized vs campaign RR : {why_rr}')
    print(f"control (<=560) no-op both ways: {'PASS' if ctrl_ok else 'FAIL'}")
    wl = fr.get('workload') or {}
    if wl:
        sym = workload_symmetric(wl)
        print(f"WORKLOAD (TASK 3): pixels handed to predict raw {wl.get('pixels_to_predict_raw')} vs facade "
              f"{wl.get('pixels_to_predict_resized')} (x{wl.get('ratio')}); model-consumed tensor shapes raw "
              f"{wl.get('model_input_shapes_raw')} vs resized {wl.get('model_input_shapes_resized')} -> "
              f"{'SYMMETRIC at the model (same work per frame on both arms)' if sym else ('ASYMMETRIC at the model' if sym is False else 'unmeasured (' + str(wl.get('hook_state')) + ')')}; "
              f"model resolution {wl.get('model_resolution')}; facade LANCZOS {wl.get('facade_lanczos_ms_median_of_5')} ms")
    else:
        print('WORKLOAD (TASK 3): unavailable — side artifact predates the workload clause')
    if ok_rr and ctrl_ok:
        print('VERDICT: V-D CONFIRMS — the engine facade\'s LANCZOS pre-downscale to infer_edge=560 reproduces '
              'the campaign RR output on the diverging frame; the raw frame reproduces LI. Mechanism NAMED and '
              'REPRODUCED outside the serving context.')
        return 0
    print('VERDICT: V-D REFUTES (or control failed) — the pre-downscale does not account for the campaign RR '
          'output; the serving context still holds something. Record and re-rule.')
    return 1


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond
    check('size rule: 714x480 -> 560x376 (House frame 10)', engine_resize_size(714, 480) == (560, 376))
    check('size rule: 640x480 -> 560x420 (381 films)', engine_resize_size(640, 480) == (560, 420))
    check('size rule: 624x480 -> 560x430 (Ansh\'s 624x480 case, diverging)', engine_resize_size(624, 480) == (560, 430))
    check('size rule: 560x380 is a NO-OP (JailBait — the exactly-560 film, clean)', engine_resize_size(560, 380) == (560, 380))
    check('size rule: 352x288 no-op (AMI); 357x240 no-op (control)',
          engine_resize_size(352, 288) == (352, 288) and engine_resize_size(357, 240) == (357, 240))
    wl_sym = {'pixels_to_predict_raw': 342720, 'pixels_to_predict_resized': 210560, 'ratio': 0.6144,
              'model_input_shapes_raw': [[1, 3, 560, 560]], 'model_input_shapes_resized': [[1, 3, 560, 560]],
              'model_resolution': 560, 'hook_state': 'measured', 'facade_lanczos_ms_median_of_5': 4.2}
    check('workload: identical model-consumed shapes -> SYMMETRIC', workload_symmetric(wl_sym) is True)
    check('workload: different shapes -> ASYMMETRIC; unmeasured -> None',
          workload_symmetric(dict(wl_sym, model_input_shapes_resized=[[1, 3, 560, 376]])) is False
          and workload_symmetric(dict(wl_sym, model_input_shapes_raw=[])) is None)
    check('pixels handed to predict on the House frame: 342,720 raw vs 210,560 facade (x0.614)',
          714 * 480 == 342720 and 560 * 376 == 210560 and round(210560 / 342720, 3) == 0.614)
    good = {'torch_threads': {'intraop': 2},
            'frame': {'png_sha256': FRAME10_SHA16 + 'x' * 48, 'size': [714, 480], 'engine_resized_size': [560, 376],
                      'engine_resize_noop': False, 'engine_helper': {'state': 'unavailable: test'}, 'workload': wl_sym,
                      'raw': {'0.3': {'detections': [[l, s] for l, s in zip(['person', 'chair', 'bottle', 'chair', 'bottle'], EXPECTED_LI['scores'])], 'self_deterministic': True}},
                      'resized': {'0.3': {'detections': [[l, s] for l, s in zip(['bottle', 'bottle', 'chair', 'chair', 'chair', 'person'], EXPECTED_RR['scores'])], 'self_deterministic': True}}},
            'control': {'engine_resize_noop': True, 'raw': {'0.3': {'detections': [], 'self_deterministic': True}},
                        'resized': {'0.3': {'detections': [], 'self_deterministic': True}}}}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 's.json'
        p.write_text(json.dumps(good))
        check('compare: CONFIRMS on the pre-registered outputs', compare(str(p)) == 0)
        bad = json.loads(json.dumps(good)); bad['frame']['resized']['0.3']['detections'][0][1] = '0.900000000'
        p.write_text(json.dumps(bad))
        check('compare: REFUTES when resized != campaign RR', compare(str(p)) == 1)
        t16 = json.loads(json.dumps(good)); t16['torch_threads']['intraop'] = 16
        p.write_text(json.dumps(t16))
        check('compare: CANNOT COMPARE at intraop 16 (thread condition), no verdict', compare(str(p)) == 3)
        nd = json.loads(json.dumps(good)); nd['frame']['raw']['0.3']['self_deterministic'] = False
        p.write_text(json.dumps(nd))
        check('compare: CANNOT COMPARE when a side cannot bit-match itself', compare(str(p)) == 3)
        sh = json.loads(json.dumps(good)); sh['frame']['png_sha256'] = 'deadbeef' * 8
        p.write_text(json.dumps(sh))
        check('compare: CANNOT COMPARE on frame sha mismatch (entry 14: refuse, return)', compare(str(p)) == 3)
        nl = json.loads(json.dumps(good)); nl['frame']['raw']['0.3']['detections'][0][1] = '0.500000000'
        p.write_text(json.dumps(nl))
        check('compare: CANNOT COMPARE when the raw frame fails the LI baseline', compare(str(p)) == 3)
    try:
        from PIL import Image
        im = Image.new('RGB', (714, 480), (10, 20, 30))
        small, noop = engine_resize(im)
        check('PIL port: 714x480 LANCZOS -> 560x376, not a no-op', small.size == (560, 376) and not noop)
    except ImportError:
        print('  SKIP  PIL not installed here (the port runs inside the rr image; size rule tested above)')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--side', action='store_true')
    ap.add_argument('--frame', default='frame10.png')
    ap.add_argument('--out', default='side_vd.json')
    ap.add_argument('--compare', default=None)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.compare:
        return compare(a.compare)
    if a.side:
        return side(a.frame, a.out)
    ap.error('one of --side / --compare / --self-test')
    return 2


if __name__ == '__main__':
    sys.exit(main())
