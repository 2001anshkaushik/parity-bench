#!/usr/bin/env python3
"""Balanced-mode LIArm: port round-robin, aggregate health, single-worker
assert, (port,pid) identity. No sockets — urllib patched at the module level."""
from __future__ import annotations

import asyncio
import io
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import driver_video as drv   # noqa: E402

FAILS = []
def check(n, c, d=''):
    if not c: FAILS.append(n)
    print(f'  {"ok  " if c else "FAIL"} {n}' + (f'\n       {d}' if not c else ''))

CALLS = []
def fake_urlopen(req, timeout=None):
    url = req if isinstance(req, str) else req.full_url
    port = int(url.split(':')[2].split('/')[0])
    CALLS.append((url.rsplit('/', 1)[-1], port))
    if url.endswith('/health'):
        body = {'pid': 1, 'warm_workers': 1, 'declared_workers': 1,
                'detect_impl': 'rfdetr'}
    else:
        body = {'pid': 1, 'n_frames': 2, 'stage_s': {'detect': 1.0},
                'stage_s_semantics': 'device_only', 'frame_labels': [[], []],
                'frame_scores': [[], []], 'chunk_chars': [10], 'chunk_sha256': ['x'],
                'n_chunks': 1, 'total_chars': 10, 'detections_per_frame': [0, 0],
                'n_detections': 0, 'embedding_norms': [], 'embed_dim': 0,
                'frame_png_sha16': ['a', 'b']}
    return io.BytesIO(json.dumps(body).encode())

def main():
    urllib.request.urlopen = fake_urlopen
    arm = drv.LIArm(list(range(8802, 8810)))
    asyncio.run(arm.start())
    check('aggregate: declared_workers = 8 over 8 single-worker instances',
          arm.declared_workers == 8)
    CALLS.clear()
    recs = [asyncio.run(arm.process(b'x', f'v{i}')) for i in range(16)]
    ports = [p for _, p in CALLS]
    check('round-robin: 16 sends cycle ports 8802-8809 twice, in order',
          ports == list(range(8802, 8810)) * 2, str(ports))
    check('records carry serving_port and (port,pid) identity is distinct x8',
          len({(r['serving_port'], r['serving_pid']) for r in recs}) == 8
          and all(r['serving_pid'] == 1 for r in recs))
    check('records carry stage_s_semantics from the service',
          all(r.get('stage_s_semantics') == 'device_only' for r in recs))

    # single-port compat: same code path, one port
    CALLS.clear()
    solo = drv.LIArm(8802)
    asyncio.run(solo.start())
    check('single-port mode unchanged: declared from the one instance',
          solo.declared_workers == 1 and [p for _, p in CALLS] == [8802])

    # NULL CONTROL: an instance declaring 8 workers must be REFUSED in balanced mode
    def fat_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        return io.BytesIO(json.dumps({'pid': 1, 'warm_workers': 8,
                                      'declared_workers': 8}).encode())
    urllib.request.urlopen = fat_urlopen
    bad = drv.LIArm([8802, 8803])
    try:
        asyncio.run(bad.start())
        check('balanced mode REFUSES multi-worker instances', False, 'no raise')
    except SystemExit as e:
        check('balanced mode REFUSES multi-worker instances (8 ports x W=8 trap)',
              'SINGLE-worker' in str(e))
    print(f'\nli-ports controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0

if __name__ == '__main__':
    sys.exit(main())
