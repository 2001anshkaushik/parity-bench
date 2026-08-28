#!/usr/bin/env python3
"""Crossroad 40, exercised against the REAL run_warmup — no box, no docker.

The fake LI arm reproduces the measured accept behaviour: posts that arrive
CONCURRENTLY spread across idle workers; posts that arrive alone go to the
hottest worker (kernel LIFO accept). Calibration points it must honour, all
measured on the box: 8 concurrent into W=8 -> ~6/8; 1-at-a-time -> concentrates
(the leg-2 death: 18 sends, 6/8); 16+ concurrent -> 8/8. A dead-worker fake
(two pids never serve at ANY concurrency) exercises the discriminator the gate
message names.

Run:  python3 working/video/test_warmup_distribution.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import driver_video as drv    # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=''):
    if not cond:
        FAILS.append(name)
    print(f'  {"ok  " if cond else "FAIL"} {name}' + (f'\n       {detail}' if not cond else ''))


class FakeLIArm:
    """Kernel-ish accept: an arriving post goes to an idle worker if several
    posts are in flight together (the herd wakes everyone), else to the most
    recently active worker (LIFO). `skew_to` reproduces the measured reality —
    /process_video never blocks its event loop, so ONE worker can hoover up
    connections however many are in flight. `warm_markers` is the SERVICE's own
    count (Crossroad 41's instrument), independent of who answers requests."""
    name = 'llamaindex'

    def __init__(self, workers=8, dead=(), skew_to=None, warm_markers=None):
        self.declared_workers = workers
        self.pids = [4000 + k for k in range(workers)]
        self.dead = set(dead)
        self.live = [p for p in self.pids if p not in self.dead]
        self.in_flight = 0
        self.hot = self.live[0]
        self.served: list[int] = []
        self.skew_to = skew_to          # serve only these pids, at any concurrency
        self.warm_markers = workers if warm_markers is None else warm_markers

    async def health(self):
        return {'warm_workers': self.warm_markers, 'declared_workers': self.declared_workers}

    async def process(self, blob, name):
        self.in_flight += 1
        try:
            await asyncio.sleep(0.001)
            pool = self.skew_to if self.skew_to else self.live
            idle_share = min(self.in_flight, len(pool))
            # concurrent arrivals spread over that many distinct live workers;
            # a lone arrival sticks to the hot one
            k = len(self.served)
            pid = pool[k % idle_share] if idle_share > 1 else (
                self.hot if not self.skew_to else pool[0])
            self.hot = pid
            self.served.append(pid)
            await asyncio.sleep(0.002)
            return {'serving_pid': pid, 'token_index': None}
        finally:
            self.in_flight -= 1


class FakeRRArm:
    name = 'rocketride'

    async def health(self):
        raise AssertionError('the RR arm must never be asked for LI warm markers')

    def __init__(self, tokens=16):
        self.declared_workers = None
        self._rr = 0
        self.tokens = tokens
        self.sent = []

    async def process(self, blob, name):
        i = self._rr % self.tokens
        self._rr += 1
        self.sent.append(i)
        await asyncio.sleep(0.001)
        return {'serving_pid': None, 'token_index': i}


def setup(d: Path, warm_n=2):
    corpus = d / 'corpus'
    corpus.mkdir()
    warm = []
    for k in range(warm_n):
        f = f'warm{k}.avi'
        (corpus / f).write_bytes(b'x' * 64)
        warm.append({'file': f, 'role': 'warm'})
    return corpus, warm


def args_for(arm, leg='blast', blast_c=16, corpus=None):
    return SimpleNamespace(skip_warmup=False, corpus_dir=str(corpus),
                           arm=arm, leg=leg, blast_concurrency=blast_c)


def pf_for(arm):
    if arm.name == 'llamaindex':
        return {'readbacks': {f'li_worker_{p}': {} for p in arm.pids}}
    return {'readbacks': {}}


def run(arm, posture, warm, args, out_dir):
    return asyncio.run(drv.run_warmup(args, arm, posture, warm, pf_for(arm), out_dir, 'teststem'))


def main() -> int:
    print('THE LEG-2 DEATH, RE-RUN UNDER CROSSROAD 40 — healthy workers, kernel accept')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        run(arm, drv.Posture('workers', 8, None), warm, args_for('llamaindex', corpus=corpus), d)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        skew = doc['response_pid_distribution']
        check('WARM_N=2, blast leg: 8/8 response pids reached (was 6/8 fatal)',
              skew['unserved_declared_pids'] is None and len(skew['per_pid_send_counts']) == 8,
              json.dumps(skew['per_pid_send_counts']))
        check('...and the gate that PASSES it is the markers, not that count',
              doc['gate']['warm_workers'] == 8, json.dumps(doc['gate']))
        check('wave size = max(2 x 8 workers, C=16) = 16, concurrent',
              '16 concurrent' in doc['policy'] and 'Crossroad 40' in doc['policy'], doc['policy'])
        check('one wave sufficed at 2x-worker concurrency (the W=4 evidence point)',
              '1 wave(s)' in doc['policy'], doc['policy'])
        check('ledger holds every send with pid, row, wall',
              len(doc['sends']) == 16 and all(e['serving_pid'] for e in doc['sends']))

    print('\nSEQUENTIAL LEG — leg concurrency 1 must NOT drop the wave under 2 x workers')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        run(arm, drv.Posture('workers', 8, None), warm,
            args_for('llamaindex', leg='sequential', blast_c=None, corpus=corpus), d)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        check('sequential leg: wave still 16 (2 x workers floor), markers gate passes',
              doc['gate']['warm_workers'] == 8 and '16 concurrent' in doc['policy'], doc['policy'])

    print('\nCONTROL — the OLD shape (1-at-a-time) really does starve on this same fake')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        async def old_shape():
            seen = set()
            for k in range(18):     # 2 "concurrent" + 16 sequential, as died on the box
                if k < 2:
                    recs = await asyncio.gather(arm.process('w.avi', 'w'), arm.process('w.avi', 'w'))
                    seen |= {r['serving_pid'] for r in recs}
                else:
                    seen.add((await arm.process('w.avi', 'w'))['serving_pid'])
            return seen
        seen = asyncio.run(old_shape())
        check('18 sends, 2 concurrent + 16 sequential -> coverage FAILS on the same fake '
              f'({len(seen)}/8) — the fix is the distribution, not the arm', len(seen) < 8)

    print('\nCROSSROAD 41 — the gate is the WARM MARKERS; scheduling skew is reported')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        # attempt 3 reproduced: 6/8 response pids, one worker taking 12 of 32
        arm = FakeLIArm(workers=8, skew_to=[4000, 4001, 4002, 4003, 4004, 4005])
        run(arm, drv.Posture('workers', 8, None), warm, args_for('llamaindex', corpus=corpus), d)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        skew = doc['response_pid_distribution']
        check('severe skew (6/8 response pids) now PASSES — all 8 markers present',
              doc['gate']['warm_workers'] == 8 and doc['gate']['declared_workers'] == 8
              and skew['distinct_response_pids'] < 8, json.dumps(skew))
        check('the gate names its rule as the markers, not the pids',
              'warm markers' in doc['gate']['rule'] and 'Crossroad 41' in doc['gate']['rule'])
        check('skew is EXPORTED: per-pid counts, busiest and quietest',
              skew['busiest_worker_sends'] >= skew['quietest_serving_worker_sends']
              and skew['per_pid_send_counts'], json.dumps(skew))
        check('the export marks the distribution REPORTED, NOT GATED',
              'NOT GATED' in skew['note'] and 'scheduling, not warmth' in skew['note'])
        check('unserved pids still recorded for the record, not fatal',
              'unserved_declared_pids' in skew)

    print('\nNULL CONTROL — a missing warm marker MUST fail')
    for missing in (7, 1, 0):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            corpus, warm = setup(d, warm_n=2)
            arm = FakeLIArm(workers=8, warm_markers=missing)
            rc, msg = 0, ''
            try:
                run(arm, drv.Posture('workers', 8, None), warm,
                    args_for('llamaindex', corpus=corpus), d)
            except SystemExit as e:
                rc, msg = 1, str(e)
            check(f'{missing}/8 warm markers -> NOT DONE, rc=1',
                  rc == 1 and f'{missing}/8 workers have written a warm marker' in msg, msg)
            check(f'{missing}/8: the message distinguishes a missing marker from skew',
                  'not the scheduling skew' in msg and 'genuinely not ready' in msg, msg)
            check(f'{missing}/8: ledger still written before the verdict',
                  (d / 'warmup_teststem.json').exists())

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        async def broken(): raise RuntimeError('connection refused')
        arm.health = lambda: broken()
        rc, msg = 0, ''
        try:
            run(arm, drv.Posture('workers', 8, None), warm, args_for('llamaindex', corpus=corpus), d)
        except SystemExit as e:
            rc, msg = 1, str(e)
        check('/health unreadable -> ABSENCE FAILS, never falls back to response pids',
              rc == 1 and 'Absence of the instrument is not evidence of warmth' in msg, msg)

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        arm.health = lambda: _no_fields()
        async def _no_fields(): return {}
        arm.health = _no_fields
        rc, msg = 0, ''
        try:
            run(arm, drv.Posture('workers', 8, None), warm, args_for('llamaindex', corpus=corpus), d)
        except SystemExit as e:
            rc, msg = 1, str(e)
        check('/health without the fields -> refuses, does not default to a pass',
              rc == 1 and 'cannot be proven' in msg, msg)

    print('\nRR ARM — Corner-banked arithmetic unchanged, addressed not accepted')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeRRArm(tokens=16)
        run(arm, drv.Posture('parity', 16, 2), warm, args_for('rocketride', corpus=corpus), d)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        check('M=16, WARM_N=2: 2 first batch + 14 top-up = 16 sends, 16/16 tokens',
              len(doc['sends']) == 16 and doc['gate']['tokens_seen'] == list(range(16))
              and '2 first batch + 14 top-up' in doc['policy'], doc['policy'])
        check('RR never asked /health for LI warm markers (FakeRRArm raises if it is)',
              doc['gate']['warm_workers'] is None and doc['gate']['declared_workers'] is None,
              json.dumps(doc['gate']))
        check('RR policy names round-robin as ADDRESSED, kernel accept uninvolved',
              'round-robin' in doc['policy'] and 'addressed' in doc['policy'], doc['policy'])

    print(f'\nwarm-up distribution controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
