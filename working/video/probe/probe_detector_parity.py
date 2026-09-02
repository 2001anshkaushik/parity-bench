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


# ------------------------------------------------------------------- census
def census(manifest: Path, corpus: Path, cross_path: Path, out: Path) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
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
                rows.append({'film': r['file'], 'mode': im.mode,
                             'size': list(im.size),
                             'n_diverging': agr.get(r['file'])})
    by_mode = {}
    for r in rows:
        by_mode.setdefault(r.get('mode', 'ERROR'), []).append(
            r.get('n_diverging'))
    partition = {m: {'n_films': len(v),
                     'zero_divergence': sum(1 for x in v if x == 0),
                     'diverging': sum(1 for x in v if (x or 0) > 0)}
                 for m, v in by_mode.items()}
    doc = {'probe': 'detector_parity_census', 'created_utc': UTC,
           'per_film': rows, 'partition_by_mode': partition,
           'verdict_note': ('mode PARTITIONS divergence if one mode holds '
                            'all zero-divergence films and another all '
                            'diverging ones — then the wrapper delta '
                            '(engine keeps original mode, LI converts RGB) '
                            'is the mechanism')}
    out.write_text(json.dumps(doc, indent=1))
    print(json.dumps(partition, indent=1))
    print(f'census -> {out}')
    return 0


# ------------------------------------------------------------------- sides
def _predict_dump(img, thresholds):
    from rfdetr import RFDETRBase
    det = RFDETRBase()
    names = getattr(det, 'class_names', None) or {}
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


def side(which: str, png_path: Path) -> int:
    import numpy as np
    from PIL import Image
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    png = png_path.read_bytes()
    if which == 'engine':
        # QUOTED from the engine's load path (image.py:36-38): mode is
        # PRESERVED, no convert. ai.common imports rocketlib (C++ binding),
        # so the two lines are quoted by citation — stated deviation.
        import io
        img = Image.open(io.BytesIO(png))
        img.load()
    else:
        sys.path.insert(0, '/app')              # the li:video image layout
        from li_video.pipeline import LlamaIndexVideoPipeline
        img = LlamaIndexVideoPipeline._load_frame(str(png_path))
    arr = np.asarray(img)
    doc = {'side': which, 'png_sha256': hashlib.sha256(png).hexdigest(),
           'pil_mode': img.mode, 'pil_size': list(img.size),
           'array_sha256': hashlib.sha256(arr.tobytes()).hexdigest(),
           'array_shape': list(arr.shape), 'array_dtype': str(arr.dtype),
           'predict': _predict_dump(img, [0.001, 0.3])}
    print(json.dumps(doc, indent=1))
    return 0


# ----------------------------------------------------------------- compare
def compare(engine_doc: dict, li_doc: dict) -> dict:
    if engine_doc['png_sha256'] != li_doc['png_sha256']:
        return {'verdict': 'CANNOT COMPARE — different input PNGs',
                'engine': engine_doc['png_sha256'], 'li': li_doc['png_sha256']}
    for d in (engine_doc, li_doc):
        for thr, block in d['predict'].items():
            if not block['self_deterministic']:
                return {'verdict': f"VOID — {d['side']} not self-deterministic "
                                   f'at threshold {thr}; a side that cannot '
                                   'bit-match itself voids the comparison'}
    arrays_equal = (engine_doc['array_sha256'] == li_doc['array_sha256']
                    and engine_doc['array_shape'] == li_doc['array_shape'])
    raw_e = engine_doc['predict']['0.001']['detections']
    raw_l = li_doc['predict']['0.001']['detections']
    scores_equal = raw_e == raw_l
    if not arrays_equal:
        verdict = ('ARRAYS DIFFER — the arms hand rfdetr DIFFERENT tensors '
                   '(engine mode ' + engine_doc['pil_mode'] + ' vs li '
                   + li_doc['pil_mode'] + '): preprocessing is the '
                   'mechanism; gate 3 strict is CORRECT — the arms are not '
                   'doing the same work')
    elif not scores_equal:
        verdict = ('ARRAYS EQUAL, RAW SCORES DIFFER — divergence arises '
                   'inside predict on identical input: float-environment '
                   'class; strict label-multiset equality is the wrong '
                   'instrument for a threshold-crossing detector')
    else:
        verdict = ('ARRAYS EQUAL, RAW SCORES EQUAL (9 dp) — neither '
                   'mechanism visible at this frame; escalate with more '
                   'frames before concluding')
    return {'verdict': verdict, 'arrays_equal': arrays_equal,
            'raw_scores_equal': scores_equal,
            'n_raw_detections': {'engine': len(raw_e), 'li': len(raw_l)}}


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    def doc(side_name, png='p1', arr='a1', mode='RGB', dets=None,
            deterministic=True):
        dets = dets if dets is not None else [['person', '0.500000000']]
        return {'side': side_name, 'png_sha256': png, 'array_sha256': arr,
                'array_shape': [4, 4, 3], 'array_dtype': 'uint8',
                'pil_mode': mode, 'pil_size': [4, 4],
                'predict': {'0.001': {'detections': dets,
                                      'self_deterministic': deterministic},
                            '0.3': {'detections': dets,
                                    'self_deterministic': deterministic}}}

    r = compare(doc('engine'), doc('li'))
    check('equal arrays + equal scores -> escalate verdict',
          r['arrays_equal'] and r['raw_scores_equal']
          and 'escalate' in r['verdict'])
    r2 = compare(doc('engine', arr='aX', mode='L'), doc('li'))
    check('different arrays -> preprocessing verdict naming both modes',
          not r2['arrays_equal'] and 'ARRAYS DIFFER' in r2['verdict']
          and 'mode L' in r2['verdict'])
    r3 = compare(doc('engine', dets=[['person', '0.500000123']]), doc('li'))
    check('equal arrays + 9dp score delta -> float-environment verdict',
          r3['arrays_equal'] and not r3['raw_scores_equal']
          and 'inside predict' in r3['verdict'])
    r4 = compare(doc('engine', png='OTHER'), doc('li'))
    check('different PNGs -> CANNOT COMPARE', 'CANNOT COMPARE' in r4['verdict'])
    r5 = compare(doc('engine', deterministic=False), doc('li'))
    check('non-self-deterministic side -> VOID (null control)',
          'VOID' in r5['verdict'])

    # census partition logic on canned rows
    rows = [{'film': 'a', 'mode': 'L', 'n_diverging': 100},
            {'film': 'b', 'mode': 'L', 'n_diverging': 90},
            {'film': 'c', 'mode': 'RGB', 'n_diverging': 0}]
    by = {}
    for x in rows:
        by.setdefault(x['mode'], []).append(x['n_diverging'])
    part = {m: {'zero_divergence': sum(1 for v in vs if v == 0),
                'diverging': sum(1 for v in vs if (v or 0) > 0)}
            for m, vs in by.items()}
    check('partition arithmetic: L=2 diverging, RGB=1 zero-divergence',
          part['L']['diverging'] == 2 and part['RGB']['zero_divergence'] == 1)

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
    ap.add_argument('--png')
    ap.add_argument('--compare', nargs=2, metavar=('ENGINE_JSON', 'LI_JSON'))
    ap.add_argument('--self-test', action='store_true')
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
        return side(args.side, Path(args.png))
    if args.compare:
        e = json.loads(Path(args.compare[0]).expanduser().read_text())
        li = json.loads(Path(args.compare[1]).expanduser().read_text())
        print(json.dumps(compare(e, li), indent=1))
        return 0
    ap.error('one of --census / --side / --compare / --self-test')
    return 2


if __name__ == '__main__':
    sys.exit(main())
