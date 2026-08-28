#!/usr/bin/env python3
"""Reader-equivalence proof — proof layer 1 for the LI streaming refactor
(Ruling B, 2026-08-27). Floor venv, no service, no containers.

Question it settles, per video: does the refactored reader (spooled file ->
`-f image2` frames ON DISK, li_video/pipeline.py at HEAD) produce
BYTE-IDENTICAL frames — and, with --with-detect, identical label multisets
and scores — versus the pre-refactor reader (whole-bytes -> pipe:0 ->
image2pipe -> in-memory signature split, pipeline.py:149-163 @ 7204a28,
carried here VERBATIM as the frozen reference)?

This probe is a GATE, not a survey: Ruling B — if image2 bytes differ from
image2pipe, STOP and report; that is a real finding, never a reason to
loosen the comparison. Exit codes: 0 = ran and EQUAL (proof passes) /
2 = ran and DIVERGENT (stop the refactor, report) / 1 = machinery or guard
failure / 3 = a null control failed to fire / 4 = --self-test failure.

Null controls, all three fired every run (comparator-level, no extra
decode): a pre-hash byte-flip on one new-path frame must fail the
comparator; dropping the last new-path frame must be reported as a count
mismatch; and --interval-null re-extracts at interval 14 and requires a
DIFFERENT count (the comparator sees real change, one extra decode).

Binds: video sha256 (--sha-expected refuses a mismatch), the imageio-ffmpeg
binary sha256 + -version, sha256 of the refactored pipeline.py source, the
frozen legacy source pin (7204a28), git HEAD. Artifacts .prev_-preserved.

Run (box):
  ~/.venv-floor/bin/python3 working/video/probe/probe_reader_equivalence.py \
      --video ~/films_probe/flight_to_nowhere.mp4 --with-detect \
      [--sha-expected <sha256>] [--interval-null]
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
from argtypes import positive_int          # noqa: E402 — register entry 8

UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
INTERVAL_S = 15

# ----------------------------------------------------------- frozen reference
# VERBATIM pre-refactor reader: li_video/pipeline.py:149-163 at 7204a28
# (PNG_SIG from :49; argv :150-152; subprocess.run :153; split loop :154-163).
# Deliberately NOT imported — the refactor deleted it; this frozen copy IS
# the reference implementation, pinned by the sha above.
PNG_SIG = b'\x89PNG\r\n\x1a\n'
LEGACY_SOURCE_PIN = '7204a284269f7dc2769db3e0a106b6e5adbcb0a6'


def legacy_extract(ffmpeg: str, video: bytes, interval_s: int) -> list:
    cmd = [ffmpeg, '-nostdin', '-loglevel', 'error', '-i', 'pipe:0',
           '-vf', f'fps=1/{interval_s}', '-f', 'image2pipe',
           '-fps_mode', 'passthrough', '-vcodec', 'png', '-']
    raw = subprocess.run(cmd, input=video, check=True, capture_output=True).stdout
    frames, i = [], 0
    while True:
        j = raw.find(PNG_SIG, i + 1)
        if j == -1:
            if i < len(raw):
                frames.append(raw[i:])
            break
        frames.append(raw[i:j])
        i = j
    return [f for f in frames if f.startswith(PNG_SIG)]


# ------------------------------------------------------------------- helpers

def sha256_file(path: Path, chunk: int = 1 << 20):
    h, n = hashlib.sha256(), 0
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def preserve(path: Path):
    """Entry 7: a re-run must not destroy prior evidence."""
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


def compare_sha_lists(a: list, b: list) -> dict:
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    if first is None and len(a) != len(b):
        first = min(len(a), len(b))
    return {'equal': len(a) == len(b) and first is None,
            'n_a': len(a), 'n_b': len(b), 'first_mismatch_index': first}


def new_pipeline():
    """The refactored reader, imported — one copy (entries 6/14). warm() is
    NOT called: the floor venv deliberately lacks llama_index (engine-pin
    scope); only the ffmpeg handle is set, resolved exactly as warm() does
    (pipeline.py warm(): imageio_ffmpeg.get_ffmpeg_exe())."""
    from li_video.pipeline import LlamaIndexVideoPipeline
    import imageio_ffmpeg
    p = LlamaIndexVideoPipeline(interval_s=INTERVAL_S)
    p._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    return p


def load_detector():
    """The detector, loaded the way warm() loads it (pipeline.py warm():
    matplotlib stub + RFDETRBase; cited, minimal copy because warm() also
    needs llama_index which the floor venv deliberately lacks)."""
    import types
    sys.modules.setdefault('matplotlib.pyplot', types.ModuleType('matplotlib.pyplot'))
    from rfdetr import RFDETRBase
    det = RFDETRBase()
    return det, getattr(det, 'class_names', None) or {}


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    import struct
    import zlib

    def mk_png(payload: bytes) -> bytes:
        def chunk(ctype, data):
            return (struct.pack('>I', len(data)) + ctype + data
                    + struct.pack('>I', zlib.crc32(ctype + data) & 0xFFFFFFFF))
        ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 0, 0, 0, 0)
        return (PNG_SIG + chunk(b'IHDR', ihdr) + chunk(b'IDAT', payload)
                + chunk(b'IEND', b''))

    pngs = [mk_png(bytes([i]) * (5 + i)) for i in range(3)]

    # The frozen legacy splitter on a synthetic stream (no ffmpeg needed):
    # feed the split loop the concatenation directly.
    raw = b''.join(pngs)
    frames, i = [], 0
    while True:
        j = raw.find(PNG_SIG, i + 1)
        if j == -1:
            if i < len(raw):
                frames.append(raw[i:])
            break
        frames.append(raw[i:j])
        i = j
    frames = [f for f in frames if f.startswith(PNG_SIG)]
    check('frozen legacy splitter: 3 frames, byte-exact spans', frames == pngs)

    ha = [hashlib.sha256(p).hexdigest() for p in pngs]
    check('comparator: equal lists compare equal',
          compare_sha_lists(ha, list(ha))['equal'])
    flipped = bytearray(pngs[0])
    flipped[len(flipped) // 2] ^= 0xFF
    hf = [hashlib.sha256(bytes(flipped)).hexdigest()] + ha[1:]
    c = compare_sha_lists(ha, hf)
    check('null-flip machinery: mismatch at index 0',
          not c['equal'] and c['first_mismatch_index'] == 0)
    c2 = compare_sha_lists(ha, ha[:-1])
    check('drop-last machinery: count mismatch at index 2',
          not c2['equal'] and c2['first_mismatch_index'] == 2)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--video')
    ap.add_argument('--sha-expected', default=None)
    ap.add_argument('--with-detect', action='store_true',
                    help='also prove label multisets + scores equal (torch=2, '
                         'the measured zero-flap regime)')
    ap.add_argument('--interval-null', action='store_true',
                    help='control: re-extract at interval 14 — the count MUST '
                         'differ (one extra decode)')
    ap.add_argument('--detect-cap', type=positive_int('detect-cap', 100000),
                    default=0, help='detect only the first N frames (0 = all)')
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.video:
        ap.error('--video is required (unless --self-test)')
    if args.sha_expected and not re.fullmatch(r'[0-9a-f]{64}', args.sha_expected):
        ap.error('--sha-expected must be 64 lowercase hex chars')

    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f'NOT DONE — video not found: {video}')
    print(f'hashing {video.name} ...')
    vid_sha, vid_bytes = sha256_file(video)
    if args.sha_expected and vid_sha != args.sha_expected:
        raise SystemExit(f'NOT DONE — video sha mismatch: measured {vid_sha}, '
                         f'expected {args.sha_expected}.')

    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit('NOT DONE — imageio_ffmpeg not importable; run under '
                         'the floor venv (~/.venv-floor/bin/python3).')
    ff_sha, _ = sha256_file(Path(ff))
    ver = subprocess.run([ff, '-version'], capture_output=True, text=True)
    pipeline_src = Path(__file__).resolve().parents[1] / 'li_video' / 'pipeline.py'
    repo = Path(__file__).resolve().parents[3]
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()

    artifact = {
        'probe': 'reader_equivalence', 'created_utc': UTC, 'git_head': head,
        'video': {'path': str(video), 'name': video.name,
                  'bytes': vid_bytes, 'sha256': vid_sha},
        'interval_s': INTERVAL_S,
        'ffmpeg': {'path': ff, 'sha256': ff_sha,
                   'version': (ver.stdout or ver.stderr).splitlines()[0]},
        'legacy_source_pin': f'pipeline.py:149-163 @ {LEGACY_SOURCE_PIN} (frozen verbatim here)',
        'new_source_sha256': hashlib.sha256(pipeline_src.read_bytes()).hexdigest(),
    }
    out = Path(args.out) if args.out else \
        Path(__file__).parent / f'probe_reader_equivalence_{video.stem}.json'

    # --- legacy (reference) -------------------------------------------------
    print('legacy reader (buffered pipe, frozen @ 7204a28) ...')
    t0 = time.monotonic()
    legacy_frames = legacy_extract(ff, video.read_bytes(), INTERVAL_S)
    legacy_shas = [hashlib.sha256(f).hexdigest() for f in legacy_frames]
    artifact['legacy'] = {'n_frames': len(legacy_frames),
                          'wall_s': round(time.monotonic() - t0, 2)}

    # --- new (refactored, imported) -----------------------------------------
    print('new reader (spooled file, frames on disk, imported from HEAD) ...')
    p = new_pipeline()
    t0 = time.monotonic()
    frames_dir, paths = p._extract_frames(str(video))
    new_wall = round(time.monotonic() - t0, 2)
    detect_result = None
    try:
        new_shas = [sha256_file(Path(fp))[0] for fp in paths]
        artifact['new'] = {'n_frames': len(paths), 'wall_s': new_wall,
                           'frames_dir_bytes': sum(Path(fp).stat().st_size
                                                   for fp in paths)}

        cmp_ = compare_sha_lists(legacy_shas, new_shas)
        artifact['frames_equal'] = cmp_

        # Null controls (comparator-level, always run).
        controls_ok = True
        first = Path(paths[0]).read_bytes() if paths else b''
        if first:
            fl = bytearray(first)
            fl[len(fl) // 2] ^= 0xFF
            flip = compare_sha_lists(
                legacy_shas, [hashlib.sha256(bytes(fl)).hexdigest()] + new_shas[1:])
            controls_ok &= not flip['equal']
        drop = compare_sha_lists(legacy_shas, new_shas[:-1]) if paths else {'equal': True}
        controls_ok &= not drop['equal']
        artifact['null_controls'] = {'flip_fired': bool(first) and not flip['equal'],
                                     'drop_last_fired': not drop['equal']}
        if args.interval_null:
            # interval is an instance attribute — a second pipeline at 14
            from li_video.pipeline import LlamaIndexVideoPipeline
            p14 = LlamaIndexVideoPipeline(interval_s=14)
            p14._ffmpeg = ff
            d2, p2 = p14._extract_frames(str(video))
            try:
                differs = len(p2) != len(paths)
            finally:
                shutil.rmtree(d2, ignore_errors=True)
            artifact['null_controls']['interval_14_count'] = len(p2)
            artifact['null_controls']['interval_null_fired'] = differs
            controls_ok &= differs

        # --- detect layer ---------------------------------------------------
        if args.with_detect and paths:
            import io as _io

            import torch
            torch.set_num_threads(2)     # measured zero-flap regime (parity era)
            det, class_names = load_detector()
            p._detector, p._class_names = det, class_names
            from PIL import Image
            n = args.detect_cap or len(paths)
            legacy_labels, legacy_scores, new_labels, new_scores = [], [], [], []
            for k in range(min(n, len(paths))):
                img_old = Image.open(_io.BytesIO(legacy_frames[k])).convert('RGB')
                d_old = p._detect_frame(img_old)
                legacy_labels.append(sorted(d['label'] for d in d_old))
                legacy_scores.append([d['score'] for d in d_old])
                d_new = p._detect_frame(p._load_frame(paths[k]))
                new_labels.append(sorted(d['label'] for d in d_new))
                new_scores.append([d['score'] for d in d_new])
            detect_result = {
                'n_frames_detected': min(n, len(paths)),
                'torch_num_threads': torch.get_num_threads(),
                'labels_equal': legacy_labels == new_labels,
                'scores_equal': legacy_scores == new_scores,
                'first_label_divergence': next(
                    (i for i, (a, b) in enumerate(zip(legacy_labels, new_labels))
                     if a != b), None),
            }
            artifact['detect_equivalence'] = detect_result
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back, then report
    eq = rb['frames_equal']
    det_ok = (detect_result is None
              or (detect_result['labels_equal'] and detect_result['scores_equal']))
    print(f'wrote {out}')
    print(f"READER EQUIVALENCE — {rb['video']['name']}: legacy {eq['n_a']} vs "
          f"new {eq['n_b']} frames; bytes {'EQUAL' if eq['equal'] else 'DIVERGENT (first at %s)' % eq['first_mismatch_index']}"
          + ('' if detect_result is None else
             f"; detect labels {'EQUAL' if detect_result['labels_equal'] else 'DIVERGENT'}"
             f", scores {'EQUAL' if detect_result['scores_equal'] else 'DIVERGENT'}"))
    if not controls_ok:
        print('NULL CONTROL FAILED TO FIRE — the comparator cannot fail; '
              'fix before trusting any EQUAL verdict')
        return 3
    if not eq['equal'] or not det_ok:
        print('STOP (Ruling B): the refactored reader diverges from the '
              'reference — report, do not loosen the comparison.')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
