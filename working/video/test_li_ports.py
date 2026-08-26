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

    print('\nCONSUMED-ARG SENTINEL + SITE LINT (class fix 2026-08-26)')
    sent = drv._ConsumedContainerArg()
    for op, fn in (('str', lambda: str(sent)), ('format', lambda: f'{sent}'),
                   ('eq', lambda: sent == 'li_video'), ('bool', lambda: bool(sent)),
                   ('hash', lambda: hash(sent))):
        try:
            fn(); check(f'sentinel: {op} raises', False, 'no raise')
        except RuntimeError as e:
            check(f'sentinel: {op} raises with the pointer to _svc_containers',
                  '_svc_containers' in str(e))
    src = Path(drv.__file__).read_text()
    cut = src.index('args.rr_container = args.li_container = _ConsumedContainerArg()')
    below = src[cut + 60:]
    raw = [l.strip() for l in below.splitlines()
           if ('args.li_container' in l or 'args.rr_container' in l)
           and 'li_containers' not in l and '#' != l.strip()[:1]]
    check('LINT: zero raw args container reads below the sentinel line', not raw, str(raw[:4]))

    orig_md5 = drv.rfdetr_checkpoint_md5
    drv.rfdetr_checkpoint_md5 = lambda c, p: {'li_bal_0': 'GOOD', 'li_bal_1': 'BAD'}.get(c)
    got = drv.containers_rfdetr_md5(['li_bal_0', 'li_bal_1'], '/x')
    check('md5 checked per instance, mixed set visible by name',
          got == {'li_bal_0': 'GOOD', 'li_bal_1': 'BAD'})
    drv.rfdetr_checkpoint_md5 = orig_md5

    orig_dt = drv.container_declared_threads
    drv.container_declared_threads = lambda c: {'OMP': '4'} if c != 'li_bal_9' else {'OMP': '2'}
    check('declared threads agree -> single value',
          drv.containers_declared_threads(['a', 'b']) == {'OMP': '4'})
    try:
        drv.containers_declared_threads(['a', 'li_bal_9'])
        check('mixed declared env REFUSED naming instances', False, 'no raise')
    except SystemExit as e:
        check('mixed declared env REFUSED naming instances', 'DISAGREES' in str(e) and 'li_bal_9' in str(e))
    drv.container_declared_threads = orig_dt

    print('\nSCHEMA <-> SERVICE AGREEMENT (the 18/18-500 class, 2026-08-26)')
    import ast as _ast
    import re as _re
    svc_src = (HERE / 'li_video' / 'service.py').read_text()
    start = svc_src.index('ProcessVideoResponse(')
    open_i = svc_src.index('(', start)
    depth = 0
    for i in range(open_i, len(svc_src)):
        depth += svc_src[i] == '('
        depth -= svc_src[i] == ')'
        if depth == 0:
            call = svc_src[start:i + 1]
            break
    else:
        raise AssertionError('unbalanced ProcessVideoResponse call')
    provided = set(_re.findall(r'(\w+)=', call))
    sch_src = (HERE / 'li_video' / 'schema.py').read_text()
    cls = sch_src[sch_src.index('class ProcessVideoResponse'):]
    nxt = cls.find('\nclass ', 1)
    cls = cls if nxt < 0 else cls[:nxt]
    required = set()
    for line in cls.splitlines():
        m = _re.match(r'\s{4}(\w+):\s*[^=]+$', line.rstrip())
        if m and '=' not in line:
            required.add(m.group(1))
    missing = required - provided
    check('every REQUIRED response field is supplied by the service call',
          not missing, f'missing from service kwargs: {sorted(missing)}')
    check('chunk_sha256 is GONE from the schema (dropped, not optional)',
          'chunk_sha256:' not in cls)

    print(f'\nli-ports controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0

if __name__ == '__main__':
    sys.exit(main())
