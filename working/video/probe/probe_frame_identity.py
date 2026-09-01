#!/usr/bin/env python3
"""Gates 2c + 4 at probe depth: engine-side frame indices and PNG bytes.

QUARANTINE NOTE (2026-08-31, entry 29): this probe still uses client.send()
whole-blob and is the instrument that DISCOVERED the 250 MiB ceiling by dying
on it (entry 24). It is superseded on films by probe_detect_text (chunked)
and probe_frame_parity; kept as the discovery artifact. DO NOT run it on any
item over ~250 MiB — it will measure the refusal, not the frames.

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
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from artifact_identity import (video_sha16, select_by_video, cannot_compare,
                               RC_CANNOT_COMPARE)

PIPE_SRC = Path(__file__).resolve().parent.parent / 'benchmark_video_detect.pipe'

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_rr import fresh_project_pipe  # noqa: E402
from argtypes import positive_int  # noqa: E402 — register entry 8


def generate_pipe() -> Path:
    # Fresh project_id (D3): the engine derives the task token from it, so a
    # copied id would collide with any live measured-pipe task on this engine.
    base = fresh_project_pipe(PIPE_SRC, 'frame-identity')
    base['components'].append({
        'id': 'resp_frames', 'provider': 'response_documents',
        'config': {'laneName': 'frames'},
        'input': [{'lane': 'documents', 'from': 'frame_grabber_1'}]})
    out = PIPE_SRC.parent / 'probe' / f'generated_frame_identity_{os.getpid()}.pipe'
    out.write_text(json.dumps(base, indent=1))
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--video', required=True)
    ap.add_argument('--floor-json', default=None,
                    help='LI floor output with frame_png_sha16 (default: newest probe_li_floor_t*.json)')
    ap.add_argument('--port', type=positive_int('port', 65535), default=5565)
    ap.add_argument('--null-flip', action='store_true',
                    help="control: corrupt one engine PNG before hashing — comparison MUST fail")
    ap.add_argument('--no-floor-ok', action='store_true',
                    help='early load-proof mode: run gate 2c + save engine hashes even when no '
                         'LI floor json exists yet; gate 4 comparison defers to the post-matrix step')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_frame_identity_out.json'))
    args = ap.parse_args()

    # A COMPARATOR MUST PROVE ITS COMPARATOR (2026-08-23). This used to take
    # `sorted(glob(...))[-1]` — lexicographic, so t8 beats t32/t2/t1 — and load
    # it with no check of WHICH VIDEO produced it. On a fresh video the identity
    # step runs BEFORE any matching floor exists, so it reached for a two-day-old
    # Corner file and reported 93 engine frames against 83 floor frames as a gate
    # FAILURE. That is a comparator that can fail (or pass) for the wrong reason.
    # Now: only a floor whose recorded video_sha16 EQUALS this video's is usable;
    # everything else is named and rejected, and gate 4 defers rather than
    # comparing against whatever is lying around.
    want_sha = video_sha16(args.video)
    sel = select_by_video(want_sha, ['probe_li_floor_t*.json'],
                          where=Path(__file__).parent, explicit=args.floor_json)
    floor_path, floor = sel.path, sel.doc
    rejected = sel.rejected_json() or []
    if not sel.ok and not args.no_floor_ok:
        print(cannot_compare('gate 4', sel.why_not(Path(args.video).name) +
                             '. Run the matrix on this video first, or pass --no-floor-ok '
                             'for the early load-proof'))
        return RC_CANNOT_COMPARE
    li_hashes = floor.get('frame_png_sha16') or []

    # Measured surface (Phase 1 + installed-wheel paste, 2026-08-21).
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{args.port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    pipe = generate_pipe()
    client = RocketRideClient()
    await client.connect(timeout=60000)
    token = None
    try:
        started = await client.use(filepath=str(pipe), ttl=3600)
        token = started['token']
        t0 = time.monotonic()
        result = await client.send(token, Path(args.video).read_bytes(),
                                   objinfo={'name': Path(args.video).name},
                                   mimetype='video/x-msvideo')
        wall = time.monotonic() - t0
    finally:
        if token:
            try:  # terminate BEFORE disconnect (Ticket 4: a leaked token idle-spins)
                await asyncio.wait_for(client.terminate(token), timeout=60)
            except Exception as exc:  # noqa: BLE001
                print(f'terminate: {exc!r} (recorded; ttl reaps)')
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
                 'rejected_floors': rejected or None,
                 'video_sha16': want_sha,
                 'reason': ('no floor json from THIS video yet — engine hashes saved; the '
                            'post-matrix compare step finishes gate 4 from this file '
                            'without a resend. Floors from other videos are NEVER used')}
        match, mismatches = None, []
    else:
        match = engine_hashes == li_hashes
        mismatches = [i for i, (a, b) in enumerate(zip(engine_hashes, li_hashes)) if a != b]
        gate4 = {'PASS': match and len(engine_hashes) == len(li_hashes),
                 'n_engine': len(engine_hashes), 'n_li': len(li_hashes),
                 'first_mismatches': mismatches[:5] or None}
    report = {
        'video': args.video, 'wall_s': round(wall, 1),
        'floor_json': floor_path, 'floor_rejected': rejected or None,
        'video_sha16': want_sha, 'null_flip': args.null_flip,
        'gate2c_index_completeness': {'PASS': bool(idx_ok), 'n': len(indices),
                                      'gaps': gaps or None, 'duplicates': dupes or None,
                                      'first': indices[0] if indices else None},
        'gate4_decode_identity': gate4,
        'same_input_proven': bool(floor_path),
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
