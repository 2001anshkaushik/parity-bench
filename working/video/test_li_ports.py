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
                'frame_scores': [[], []], 'chunk_chars': [10],
                'chunks': ['abcdefghij'], 'hashing_locus': 'driver_post_response',
                'n_chunks': 1, 'total_chars': 10, 'detections_per_frame': [0, 0],
                'n_detections': 0, 'embedding_norms': [], 'embed_dim': 0}
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
    import hashlib
    want_sha = hashlib.sha256(b'abcdefghij').hexdigest()
    check('HASHING LOCUS: chunk_sha256 computed DRIVER-side from returned texts, RR formula',
          all(r['chunk_sha256'] == [want_sha] and r['hashing_locus'] == 'driver_post_response'
              for r in recs))
    old_body_rec = drv.record_from_li({'chunk_sha256': ['legacyhash'], 'chunk_chars': [5],
                                       'n_chunks': 1, 'pid': 9})
    check('old-image response (no chunks) falls back to its in-wall hashes AND says so',
          old_body_rec['chunk_sha256'] == ['legacyhash']
          and old_body_rec['hashing_locus'] == 'in_service_in_wall')
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
    print('\nCOLLECTOR MULTI-INSTANCE (Task-1 blocker, 2026-08-25)')
    names8 = ','.join(f'li_bal_{i}' for i in range(8))
    got = drv.resolve_service_containers('llamaindex', 'rr', 'li_video', names8, 8)
    check('8 ports + 8 containers -> full sample set', got == [f'li_bal_{i}' for i in range(8)])
    for spec, n, why in ((None, 8, 'no --li-containers'), (names8 + ',extra', 8, 'count mismatch'),
                         ('a,a', 2, 'duplicates')):
        try:
            drv.resolve_service_containers('llamaindex', 'rr', 'li_video', spec, n)
            check(f'FAIL-CLOSED: {why} refused', False, 'no raise')
        except SystemExit as e:
            check(f'FAIL-CLOSED: {why} refused', 'NOT DONE' in str(e))
    check('single-port keeps --li-container',
          drv.resolve_service_containers('llamaindex', 'rr', 'li_video', None, 1) == ['li_video'])
    check('rocketride unaffected',
          drv.resolve_service_containers('rocketride', 'rr', 'li_video', None, 8) == ['rr'])

    orig = drv.container_cpu_usage_usec
    drv.container_cpu_usage_usec = lambda c, timeout_s=15: {'a': 100, 'b': 250}.get(c)
    check('cgroup SUM across containers', drv.containers_cpu_usage_usec(['a', 'b']) == 350)
    check('one unreadable member -> None, never a partial sum',
          drv.containers_cpu_usage_usec(['a', 'dead']) is None)
    drv.container_cpu_usage_usec = orig

    print(f'\nli-ports controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0

if __name__ == '__main__':
    sys.exit(main())
