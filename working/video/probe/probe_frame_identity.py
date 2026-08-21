#!/usr/bin/env python3
"""Gates 2c + 4 at probe depth: engine-side frame indices and PNG bytes.

Generates a variant of the measured pipe (a3_env_torch pattern — the measured
pipe file is untouched) that ADDS a response on frame_grabber's `documents`
lane, whose Docs carry the frame PNG (base64), `chunkId` = frame_number and
`time_stamp`. One send then yields, from INSIDE the engine:

  gate 2c: the frame index sequence -> gates_shared.index_completeness shape
           (checked here standalone: gapless, duplicate-free, starts at 0)
  gate 4:  per-frame PNG sha256 -> compared byte-for-byte against the LI
           floor's frame_png_sha16 for the same video (identical imageio-ffmpeg
           binary + filter => identical bytes). PROBE SCOPE ONLY — per-record
           hashing at leg scale would distort the measurement it protects.

Null control (--null-flip): flips one byte of one engine-side PNG before
hashing; the comparison MUST then report a mismatch — a comparator that cannot
fail is not a control. Exit 3 if the null control fails to fire.

Usage (box, after probe_run.sh produced probe_li_floor_t*.json):
    python3 probe_frame_identity.py --video media/ES2002a.Corner.avi \
        [--floor-json probe_li_floor_t8.json] [--null-flip]
"""

import argparse
import asyncio
import base64
import glob
import hashlib
import json
import os
import sys
import time
from pathlib import Path

PIPE_SRC = Path(__file__).resolve().parent.parent / 'benchmark_video_detect.pipe'


def generate_pipe() -> Path:
    base = json.loads(PIPE_SRC.read_text())
    base['components'].append({
        'id': 'resp_frames', 'provider': 'response_documents',
        'config': {'laneName': 'frames'},
        'input': [{'lane': 'documents', 'from': 'frame_grabber_1'}]})
    out = PIPE_SRC.parent / 'probe' / f'generated_frame_identity_{os.getpid()}.pipe'
    out.write_text(json.dumps(base, indent=1))
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--floor-json', default=None,
                    help='LI floor output with frame_png_sha16 (default: newest probe_li_floor_t*.json)')
    ap.add_argument('--port', type=int, default=5565)
    ap.add_argument('--null-flip', action='store_true',
                    help="control: corrupt one engine PNG before hashing — comparison MUST fail")
    ap.add_argument('--no-floor-ok', action='store_true',
                    help='early load-proof mode: run gate 2c + save engine hashes even when no '
                         'LI floor json exists yet; gate 4 comparison defers to the post-matrix step')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_frame_identity_out.json'))
    args = ap.parse_args()

    floor_path = args.floor_json or (sorted(glob.glob(str(Path(__file__).parent / 'probe_li_floor_t*.json'))) or [None])[-1]
    if not floor_path and not args.no_floor_ok:
        print('NOT DONE — no LI floor json (run the matrix first, or pass --no-floor-ok '
              'for the early load-proof)')
        return 1
    floor = json.load(open(floor_path)) if floor_path else {}
    li_hashes = floor.get('frame_png_sha16') or []

    from rocketride import RocketRide
    pipe = generate_pipe()
    client = RocketRide(uri=f'ws://127.0.0.1:{args.port}/task/service', apikey='local-dev')
    await client.connect()
    try:
        started = await client.use(filepath=str(pipe), ttl=3600)
        t0 = time.monotonic()
        result = await client.send(started['token'], Path(args.video).read_bytes(),
                                   objinfo={'name': Path(args.video).name},
                                   mimetype='video/x-msvideo')
        wall = time.monotonic() - t0
    finally:
        await client.disconnect()

    frame_docs = (result or {}).get('frames') or []
    if not frame_docs:
        print(f'NOT DONE — no frames lane in response (keys: {sorted((result or {}).keys())})')
        return 1

    indexed = []
    for d in frame_docs:
        md = d.get('metadata') or {}
        try:
            png = base64.b64decode(d.get('page_content') or '')
        except Exception:
            png = b''
        indexed.append((md.get('chunkId'), md.get('time_stamp'), png))
    indexed.sort(key=lambda x: (x[0] if isinstance(x[0], int) else 1 << 30))

    indices = [i for i, _, _ in indexed]
    seen = set()
    dupes = sorted({i for i in indices if i in seen or seen.add(i)})
    gaps = (sorted(set(range(min(indices), max(indices) + 1)) - set(indices))
            if indices and all(isinstance(i, int) for i in indices) else ['non-integer indices'])
    idx_ok = indices and not dupes and not gaps and indices[0] == 0

    engine_pngs = [png for _, _, png in indexed]
    if args.null_flip and engine_pngs:
        b = bytearray(engine_pngs[0])
        b[len(b) // 2] ^= 0xFF
        engine_pngs[0] = bytes(b)
    engine_hashes = [hashlib.sha256(p).hexdigest()[:16] for p in engine_pngs]

    if not li_hashes:
        gate4 = {'PASS': None, 'deferred': True,
                 'reason': 'no floor hashes yet — engine hashes saved; the post-matrix '
                           'compare step finishes gate 4 from this file without a resend'}
        match, mismatches = None, []
    else:
        match = engine_hashes == li_hashes
        mismatches = [i for i, (a, b) in enumerate(zip(engine_hashes, li_hashes)) if a != b]
        gate4 = {'PASS': match and len(engine_hashes) == len(li_hashes),
                 'n_engine': len(engine_hashes), 'n_li': len(li_hashes),
                 'first_mismatches': mismatches[:5] or None}
    report = {
        'video': args.video, 'wall_s': round(wall, 1),
        'floor_json': floor_path, 'null_flip': args.null_flip,
        'gate2c_index_completeness': {'PASS': bool(idx_ok), 'n': len(indices),
                                      'gaps': gaps or None, 'duplicates': dupes or None,
                                      'first': indices[0] if indices else None},
        'gate4_decode_identity': gate4,
        'engine_frame_png_sha16': engine_hashes,
        'timestamps_first_last': [indexed[0][1], indexed[-1][1]] if indexed else None,
    }
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != 'timestamps_first_last'}, indent=1))

    if args.null_flip:
        if report['gate4_decode_identity']['PASS']:
            print('NULL CONTROL FAILED TO FIRE — the comparator cannot fail; fix before trusting any PASS')
            return 3
        print('null control fired: corrupted PNG detected as mismatch')
        return 0
    if report['gate4_decode_identity'].get('deferred'):
        return 0 if idx_ok else 1
    return 0 if (idx_ok and report['gate4_decode_identity']['PASS']) else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
