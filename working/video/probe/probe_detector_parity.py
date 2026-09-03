#!/usr/bin/env python3
"""DETECTOR-INPUT PARITY (designed 2026-09-02) — DO NOT RUN UNTIL ANSH RULES.

The decisive test for the cross-gate divergence, three modes:

  --census   (box, floor venv): one mid-film frame per measured film through
             the SAME imageio-ffmpeg binary (sha e7e7fb30…, the arms' own) ->
             PIL mode/size/bit-depth census, JOINED against each film's
             campaign n_diverging. If PNG mode partitions divergence (the
             three zero-divergence films one mode, the diverging films
             another), the mechanism is the arms' wrapper delta: the engine
             keeps the PNG's ORIGINAL mode (image.py:19-24, 36-38 — the
             docstring says so; no convert) while LI forces .convert('RGB')
             (pipeline.py:210-212) — the ONLY arm-controlled difference
             before rfdetr.predict (detection.py:172 passes the image
             untouched; both stacks run rfdetr 1.5.2 / torch 2.10.0 /
             torchvision 0.25.0). ~3-4 min.

  --side engine|li  (run INSIDE the respective container): loads ONE PNG by
             that arm's exact load path — engine: Image.open(BytesIO).load()
             quoted from image.py:36-38 (rocketlib import makes ai.common
             unimportable standalone; two lines quoted BY CITATION, stated
             deviation) — li: the real li_video.pipeline._load_frame — then
             prints PIL mode/size, np.asarray sha256/shape/dtype, and RAW
             rfdetr predictions at threshold 0.001 and 0.3 (labels + scores
             to 9 dp), each run TWICE (self-determinism null: a side that
             cannot bit-match itself voids the comparison). ~2-3 min/side
             (model load dominates).

  --compare  (laptop or box): the two side outputs -> verdict:
             ARRAYS DIFFER  -> the arms hand rfdetr different tensors:
                               preprocessing is the mechanism; gate 3's
                               strict verdict is CORRECT (the arms are not
                               doing the same work) and the fix is a ruling
                               on the wrapper delta;
             ARRAYS EQUAL + scores differ -> divergence inside predict on
                               identical input: float-environment class;
                               gate 3's strict label-multiset equality is
                               the wrong instrument for a threshold-crossing
                               detector — Ansh re-rules the gate;
             ARRAYS EQUAL + scores equal (9 dp) -> neither mechanism at this
                               frame; escalate with more frames.

Wheel-source companion (one paste, seconds — the installed wheel is the
measured surface, entry 2):
  docker run --rm --entrypoint python li:video -c \
    "import inspect, rfdetr.detr as d; print(inspect.getsource(d.RFDETRBase.predict))"

Frames: HouseOnBareMountain mid-frame (46% diverging) + 20000Leagues
mid-frame (zero-divergence control). Total cost ~8-12 min, no legs touched,
uses the running rr + the li:video image. STATED RISKS (entry 27 — surfaces
a laptop cannot execute): the engine container's standalone python must load
rfdetr's baked weights offline (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 are
set; any fetch attempt is reported and the run exits 2 — never a silent
download); rfdetr.predict's mode handling is read from the wheel, not
assumed.

Exit 0 done / 2 refusal / 4 self-test failure.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())


def reject_glued_flags(argv) -> None:
    """A token like '--census--cross' is argparse-refused loudly (verified
    2026-09-02: exit 2, no artifact — it cannot silently swallow), but the
    refusal is a usage dump; this names the glue and the fix (entry 8's
    missing-space class, at the option token instead of the value)."""
    for tok in argv:
        if tok.startswith('--') and '--' in tok[2:]:
            raise SystemExit(f'NOT DONE — glued flags {tok!r}: two options '
                             'ran together (missing space in the paste?). '
                             'Separate them and re-run.')


# ------------------------------------------------------------------- census
def census(manifest: Path, corpus: Path, cross_path: Path, out: Path) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        import imageio_ffmpeg
    except ImportError:
        raise SystemExit(
            'NOT DONE — this interpreter has no imageio_ffmpeg. The census '
            'runs under the FLOOR venv (~/.venv-floor/bin/python3); the '
            'driver venv (~/.venv) does not carry it — the probe/driver '
            'interpreter split, the entry-15 carryover class (2026-09-02: '
            'this exact trap cost a paste).')
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    import numpy as np
    from PIL import Image
    agr = {}
    if cross_path.is_file():
        c = json.loads(cross_path.read_text())
        agr = {v: g.get('n_diverging')
               for v, g in ((c.get('cross_detection_agreement') or {})
                            .get('per_video') or {}).items()}
    rows = []
    for line in manifest.read_text().splitlines():
        r = json.loads(line)
        if r.get('role') != 'measured':
            continue
        f = corpus / r['file']
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / 'f.png'
            p = subprocess.run(
                [ff, '-nostdin', '-loglevel', 'error',
                 '-ss', str(r['video_s'] / 2), '-i', str(f),
                 '-frames:v', '1', '-vcodec', 'png', str(png)],
                capture_output=True, timeout=120)
            if p.returncode != 0 or not png.exists():
                rows.append({'film': r['file'], 'ERROR': p.stderr[-200:].decode(
                    'utf-8', 'replace'), 'n_diverging': agr.get(r['file'])})
                continue
            with Image.open(png) as im:
                arr = np.asarray(im)
                rows.append({'film': r['file'], 'mode': im.mode,
                             'size': list(im.size),
                             'array_dtype': str(arr.dtype),
                             'array_shape': list(arr.shape),
                             'aspect': round(im.size[0] / im.size[1], 4),
                             'n_diverging': agr.get(r['file'])})
    partition = partition_census(rows)
    doc = {'probe': 'detector_parity_census', 'created_utc': UTC,
           'per_film': rows, **partition,
           'channel_order_note': ('PIL arrays are RGB by construction on '
                                  'both arms (no cv2/BGR anywhere in either '
                                  'load path — pipeline.py:210-212, '
                                  'image.py:36-38); the 560px resize happens '
                                  'INSIDE rfdetr.predict, identical package '
                                  'both arms — its geometry comes from the '
                                  'wheel-source paste, not assumed here'),
           'verdict_note': ('a property PARTITIONS divergence if one class '
                            'holds all zero-divergence films and another '
                            'all diverging ones')}
    out.write_text(json.dumps(doc, indent=1))
    print(json.dumps(partition, indent=1))
    print(f'census -> {out}')
    return 0


def partition_census(rows) -> dict:
    """Partition the clean/diverging split by every recorded property."""
    def split(key):
        by = {}
        for r in rows:
            by.setdefault(str(r.get(key, 'ERROR')), []).append(
                r.get('n_diverging'))
        return {k: {'n_films': len(v),
                    'zero_divergence': sum(1 for x in v if x == 0),
                    'diverging': sum(1 for x in v if (x or 0) > 0)}
                for k, v in by.items()}
    return {'partition_by_mode': split('mode'),
            'partition_by_size': split('size'),
            'partition_by_dtype': split('array_dtype'),
            'partition_by_shape': split('array_shape')}


# ------------------------------------------------------------------- sides
def _lib_identity() -> dict:
    """The libraries doing the work, per side — versions AND file bytes,
    because same version string does not guarantee same bytes (2026-09-02:
    the size partition points INSIDE predict, where the resize lives)."""
    import numpy
    import PIL
    import rfdetr
    import torch
    import torchvision
    import rfdetr.detr as rd
    detr_file = Path(rd.__file__)
    return {
        'pillow': PIL.__version__,
        'torch': torch.__version__,
        'torch_git': getattr(__import__('torch.version', fromlist=['x']),
                             'git_version', None),
        'torch_cuda': getattr(__import__('torch.version', fromlist=['x']),
                              'cuda', None),
        'torchvision': torchvision.__version__,
        'numpy': numpy.__version__,
        'rfdetr_version': getattr(rfdetr, '__version__', None),
        'rfdetr_detr_file': str(detr_file),
        'rfdetr_detr_sha256': hashlib.sha256(
            detr_file.read_bytes()).hexdigest(),
    }


def _predict_dump(det, names, img, thresholds):
    out = {}
    for thr in thresholds:
        runs = []
        for _ in range(2):                      # self-determinism null
            preds = det.predict(img, threshold=thr)
            runs.append([[names.get(int(preds.class_id[k]),
                                    str(int(preds.class_id[k]))),
                          f'{float(preds.confidence[k]):.9f}']
                         for k in range(len(preds))])
        out[str(thr)] = {'detections': runs[0],
                         'self_deterministic': runs[0] == runs[1]}
    return out


def side(which: str, png_paths) -> int:
    """One model load, every frame through it — the block runs each side
    ONCE for both the small-film and large-film frames."""
    import numpy as np
    from PIL import Image
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    if which == 'li':
        sys.path.insert(0, '/app')              # the li:video image layout
        from li_video.pipeline import LlamaIndexVideoPipeline
    from rfdetr import RFDETRBase
    # Ruling Y (2026-09-02): fail-closed weights. RFDETRBase() resolves
    # rf-detr-base.pth from the CWD and silently DOWNLOADS on a miss (the
    # v2 engine side fetched 355M despite the offline env). A probe that
    # fetches is a probe that could fetch something else: refuse instead,
    # and record the md5 of the file actually used so both sides are
    # provably running the same bytes.
    wpth = Path.cwd() / 'rf-detr-base.pth'
    if not wpth.exists():
        print(f'REFUSE: rf-detr-base.pth not in cwd ({Path.cwd()}) — the '
              f'wrapper places the canonical weights beside the run; no '
              f'fetch is permitted', file=sys.stderr)
        raise SystemExit(3)
    weights_md5 = hashlib.md5(wpth.read_bytes()).hexdigest()
    det = RFDETRBase()
    import torch
    # Ruling Y: the v2 side docs omitted the thread state the design
    # called for; it is the leading candidate if scores differ on a
    # diverging frame, so it rides in the doc.
    torch_threads = {'intraop': torch.get_num_threads(),
                     'interop': torch.get_num_interop_threads(),
                     'captured': 'after model construction, '
                                 'before first predict'}
    thread_env = {k: os.environ.get(k) for k in (
        'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS',
        'TORCH_NUM_THREADS')}
    names = getattr(det, 'class_names', None) or {}
    frames = []
    for p in png_paths:
        png_path = Path(p)
        png = png_path.read_bytes()
        if which == 'engine':
            # QUOTED from the engine's load path (image.py:36-38): mode
            # PRESERVED, no convert. ai.common imports rocketlib (C++
            # binding), so the two lines are quoted by citation — stated
            # deviation.
            import io
            img = Image.open(io.BytesIO(png))
            img.load()
        else:
            img = LlamaIndexVideoPipeline._load_frame(str(png_path))
        arr = np.asarray(img)
        frames.append({
            'png': png_path.name,
            'png_sha256': hashlib.sha256(png).hexdigest(),
            'pil_mode': img.mode, 'pil_size': list(img.size),
            'array_sha256': hashlib.sha256(arr.tobytes()).hexdigest(),
            'array_shape': list(arr.shape), 'array_dtype': str(arr.dtype),
            'predict': _predict_dump(det, names, img, [0.001, 0.3])})
    doc = {'side': which, 'libs': _lib_identity(),
           'weights_md5': weights_md5, 'torch_threads': torch_threads,
           'thread_env': thread_env, 'frames': frames}
    return doc


def write_side(which: str, png_paths, out_path: Path) -> int:
    """2026-09-02 Layer-3 lesson (the campaign's FOURTH shape defect): the
    side doc used to travel over STDOUT — a channel the engine's embedded
    interpreter also prints to, so the captured 'JSON' arrived with a
    banner prefix and compare crashed on it. The artifact now goes to an
    EXPLICIT FILE; stdout stays a human channel (entry 9: a shared stream
    is a rendering, not an artifact)."""
    doc = side(which, png_paths)
    out_path.write_text(json.dumps(doc, indent=1))
    rb = json.loads(out_path.read_text())          # entry 22: read back
    print(f"side {which}: {len(rb['frames'])} frame(s) -> {out_path}")
    return 0


# ----------------------------------------------------------------- compare
def _compare_frame(e: dict, li: dict) -> dict:
    if e['png_sha256'] != li['png_sha256']:
        return {'verdict': 'CANNOT COMPARE — different input PNGs',
                'engine': e['png_sha256'], 'li': li['png_sha256']}
    for d, side_name in ((e, 'engine'), (li, 'li')):
        for thr, block in d['predict'].items():
            if not block['self_deterministic']:
                return {'verdict': f'VOID — {side_name} not '
                                   f'self-deterministic at threshold {thr}; '
                                   'a side that cannot bit-match itself '
                                   'voids the comparison'}
    arrays_equal = (e['array_sha256'] == li['array_sha256']
                    and e['array_shape'] == li['array_shape'])
    raw_e = e['predict']['0.001']['detections']
    raw_l = li['predict']['0.001']['detections']
    scores_equal = raw_e == raw_l
    # Score-delta TIERS (2026-09-02): the Leagues staging already measured a
    # ~1e-7 cross-arm background on the clean class, so strict equality
    # cannot discriminate. Sorted-confidence pairing when counts match;
    # <=1e-5 = the known float-noise background (NOT the campaign
    # mechanism); >=1e-3 = the %-scale class the diverging films show.
    max_delta = None
    if len(raw_e) == len(raw_l):
        se = sorted(float(s) for _, s in raw_e)
        sl = sorted(float(s) for _, s in raw_l)
        max_delta = max((abs(a - b) for a, b in zip(se, sl)), default=0.0)
    if not arrays_equal:
        verdict = ('ARRAYS DIFFER — the arms hand rfdetr different tensors '
                   f"(engine mode {e['pil_mode']} vs li {li['pil_mode']}): "
                   'load-path preprocessing is the mechanism')
    elif scores_equal:
        verdict = ('ARRAYS EQUAL, RAW SCORES BIT-EQUAL (9 dp) — no '
                   'divergence at this frame')
    elif max_delta is not None and max_delta <= 1e-5:
        verdict = (f'ARRAYS EQUAL, scores within {max_delta:.2e} — the '
                   'known float-noise background (Leagues staging ~1e-7), '
                   'NOT the campaign mechanism')
    else:
        # The resize lives INSIDE predict, so equal pre-predict arrays with
        # %-scale score deltas (or count changes) point FIRST at the resize
        # implementation the two containers run (Pillow version/build or
        # wheel bytes — libs_identity adjudicates), then at float env.
        delta_txt = (f'max sorted-score delta {max_delta:.2e}'
                     if max_delta is not None else
                     f'detection COUNTS differ ({len(raw_e)} vs {len(raw_l)})')
        verdict = (f'ARRAYS EQUAL, %-SCALE DIVERGENCE INSIDE predict '
                   f'({delta_txt}) on identical input; prime suspect the '
                   'resize implementation (libs_identity: pillow/wheel-bytes '
                   'mismatch = resize class; all-equal libs = deeper bisect)')
    return {'png': e.get('png'), 'pil_size': e.get('pil_size'),
            'verdict': verdict, 'arrays_equal': arrays_equal,
            'raw_scores_equal': scores_equal, 'max_sorted_delta': max_delta,
            'n_raw_detections': {'engine': len(raw_e), 'li': len(raw_l)}}


def compare(engine_doc: dict, li_doc: dict) -> dict:
    """Side docs: {'side', 'libs', 'frames': [...]} — frames paired by
    png sha; the libs identity rides beside every frame verdict."""
    libs_e, libs_l = engine_doc.get('libs') or {}, li_doc.get('libs') or {}
    libs_diff = {k: {'engine': libs_e.get(k), 'li': libs_l.get(k)}
                 for k in sorted(set(libs_e) | set(libs_l))
                 if k != 'rfdetr_detr_file'          # paths differ trivially
                 and libs_e.get(k) != libs_l.get(k)}
    li_by_sha = {f['png_sha256']: f for f in li_doc.get('frames') or []}
    frames = []
    for ef in engine_doc.get('frames') or []:
        lf = li_by_sha.get(ef['png_sha256'])
        frames.append(_compare_frame(ef, lf) if lf else
                      {'png': ef.get('png'),
                       'verdict': 'CANNOT COMPARE — no li frame with this '
                                  'png sha'})
    return {'libs_identical': not libs_diff,
            'libs_diff': libs_diff or None,
            # Ruling Y: thread state and weights identity ride the verdict
            # (None on pre-Y side docs — additive, never breaking).
            'torch_threads': {'engine': engine_doc.get('torch_threads'),
                              'li': li_doc.get('torch_threads')},
            'thread_env': {'engine': engine_doc.get('thread_env'),
                           'li': li_doc.get('thread_env')},
            'weights_md5': {'engine': engine_doc.get('weights_md5'),
                            'li': li_doc.get('weights_md5')},
            'frames': frames}


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    def frame(png='p1', arr='a1', mode='RGB', dets=None, deterministic=True):
        dets = dets if dets is not None else [['person', '0.500000000']]
        return {'png': f'{png}.png', 'png_sha256': png, 'array_sha256': arr,
                'array_shape': [4, 4, 3], 'array_dtype': 'uint8',
                'pil_mode': mode, 'pil_size': [4, 4],
                'predict': {'0.001': {'detections': dets,
                                      'self_deterministic': deterministic},
                            '0.3': {'detections': dets,
                                    'self_deterministic': deterministic}}}

    def sdoc(side_name, frames, pillow='10.4.0'):
        return {'side': side_name, 'frames': frames,
                'libs': {'pillow': pillow, 'torch': '2.10.0',
                         'rfdetr_detr_file': f'/{side_name}/detr.py',
                         'rfdetr_detr_sha256': 'abc'}}

    r = compare(sdoc('engine', [frame()]), sdoc('li', [frame()]))
    check('equal arrays + equal scores + equal libs -> no-divergence frame',
          r['libs_identical'] and r['frames'][0]['arrays_equal']
          and r['frames'][0]['raw_scores_equal']
          and 'no divergence' in r['frames'][0]['verdict'])
    r2 = compare(sdoc('engine', [frame(arr='aX', mode='L')]),
                 sdoc('li', [frame()]))
    check('different arrays -> load-path verdict naming both modes',
          not r2['frames'][0]['arrays_equal']
          and 'ARRAYS DIFFER' in r2['frames'][0]['verdict']
          and 'mode L' in r2['frames'][0]['verdict'])
    r3 = compare(sdoc('engine', [frame(dets=[['person', '0.500000123']])],
                      pillow='9.5.0'),
                 sdoc('li', [frame()]))
    check('1.2e-7 delta -> float-noise tier (NOT the mechanism), and the '
          'pillow build mismatch is surfaced',
          r3['frames'][0]['arrays_equal']
          and 'float-noise background' in r3['frames'][0]['verdict']
          and r3['libs_diff'] == {'pillow': {'engine': '9.5.0',
                                             'li': '10.4.0'}})
    r3b = compare(sdoc('engine', [frame(dets=[['person', '0.480000000']])]),
                  sdoc('li', [frame()]))
    check('2e-2 delta -> %-scale INSIDE-predict tier (resize prime suspect)',
          r3b['frames'][0]['arrays_equal']
          and '%-SCALE DIVERGENCE INSIDE predict'
          in r3b['frames'][0]['verdict'])
    r4 = compare(sdoc('engine', [frame(png='OTHER')]),
                 sdoc('li', [frame()]))
    check('unpaired PNG -> CANNOT COMPARE',
          'CANNOT COMPARE' in r4['frames'][0]['verdict'])
    r5 = compare(sdoc('engine', [frame(deterministic=False)]),
                 sdoc('li', [frame()]))
    check('non-self-deterministic side -> VOID (null control)',
          'VOID' in r5['frames'][0]['verdict'])
    r6 = compare(sdoc('engine', [frame(), frame(png='p2', dets=[
        ['person', '0.400000000']])]),
        sdoc('li', [frame(), frame(png='p2')]))
    check('two frames pair by sha: small clean + large diverging in one '
          'compare (the prediction-test shape)',
          r6['frames'][0]['raw_scores_equal'] is True
          and r6['frames'][1]['raw_scores_equal'] is False)

    # census partition logic on canned rows — every recorded property.
    rows = [{'film': 'a', 'mode': 'RGB', 'size': [640, 480],
             'array_dtype': 'uint8', 'array_shape': [480, 640, 3],
             'n_diverging': 100},
            {'film': 'b', 'mode': 'RGB', 'size': [640, 480],
             'array_dtype': 'uint8', 'array_shape': [480, 640, 3],
             'n_diverging': 90},
            {'film': 'c', 'mode': 'RGB', 'size': [320, 240],
             'array_dtype': 'uint8', 'array_shape': [240, 320, 3],
             'n_diverging': 0}]
    part = partition_census(rows)
    check('partition arithmetic: mode does NOT partition (one class, mixed) '
          'while size DOES (640x480 diverging, 320x240 clean)',
          part['partition_by_mode']['RGB']['diverging'] == 2
          and part['partition_by_mode']['RGB']['zero_divergence'] == 1
          and part['partition_by_size']['[640, 480]']['diverging'] == 2
          and part['partition_by_size']['[320, 240]']['zero_divergence'] == 1)
    try:
        reject_glued_flags(['--census--cross', '/tmp/x'])
        check('glued flags refused naming the glue (entry 8 class)', False)
    except SystemExit as e:
        check('glued flags refused naming the glue (entry 8 class)',
              'glued flags' in str(e) and '--census--cross' in str(e))

    # 2026-09-02 Layer-3 regression controls: side docs travel as FILES;
    # a polluted stdout capture is refused NAMING the file and its prefix.
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        polluted = Path(t) / 'bad.json'
        polluted.write_text('ENGINE BANNER LINE\n{"side": "engine"}')
        import json as _json
        try:
            _json.loads(polluted.read_text())
            parse_fails = False
        except _json.JSONDecodeError:
            parse_fails = True
        check('a banner-polluted capture is indeed non-JSON (the v2 crash '
              'shape reproduced)', parse_fails)
        outp = Path(t) / 'side.json'
        # write_side's file contract without a model: exercise the write+
        # read-back path via a canned doc through the same json round-trip.
        outp.write_text(json.dumps(sdoc('engine', [frame()])))
        rb = json.loads(outp.read_text())
        check('side doc as FILE round-trips clean (the --side-out contract)',
              rb['side'] == 'engine' and rb['frames'][0]['png'] == 'p1.png')

    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--census', action='store_true')
    ap.add_argument('--manifest', default=str(
        Path(__file__).resolve().parents[1] / 'films_video_manifest.jsonl'))
    ap.add_argument('--corpus', default=str(Path.home() / 'films_corpus'
                                            / 'subset'))
    ap.add_argument('--cross', default=None,
                    help='campaign cross_parity_blast.json for the join')
    ap.add_argument('--out', default=str(Path.home() / 'films_probe'
                                         / 'detector_parity'
                                         / f'census_{UTC}.json'))
    ap.add_argument('--side', choices=['engine', 'li'])
    ap.add_argument('--png', nargs='+',
                    help='one or more PNGs — one model load serves all')
    ap.add_argument('--side-out', default=None,
                    help='REQUIRED with --side: file the side doc is written '
                         'to (stdout is a shared, pollutable stream — the '
                         '2026-09-02 Layer-3 crash)')
    ap.add_argument('--compare', nargs=2, metavar=('ENGINE_JSON', 'LI_JSON'))
    ap.add_argument('--self-test', action='store_true')
    reject_glued_flags(sys.argv[1:])
    args = ap.parse_args()
    if args.self_test:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        return self_test()
    if args.census:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        cross = Path(args.cross).expanduser() if args.cross else Path('/nonexistent')
        return census(Path(args.manifest).expanduser(),
                      Path(args.corpus).expanduser(), cross, out)
    if args.side:
        if not args.png:
            ap.error('--side needs --png')
        if not args.side_out:
            ap.error('--side needs --side-out <file> (stdout is a shared, '
                     'pollutable stream — the 2026-09-02 Layer-3 crash)')
        return write_side(args.side, args.png, Path(args.side_out))
    if args.compare:
        docs = []
        for p in args.compare:
            path = Path(p).expanduser()
            text = path.read_text()
            try:
                docs.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f'NOT DONE — {path} is not JSON ({exc}); first 120 '
                    f'chars: {text[:120]!r}. A side doc travels as a FILE '
                    'via --side-out, never a stdout capture (a shared '
                    'stream is a rendering, not an artifact).')
        print(json.dumps(compare(docs[0], docs[1]), indent=1))
        return 0
    ap.error('one of --census / --side / --compare / --self-test')
    return 2


if __name__ == '__main__':
    sys.exit(main())
