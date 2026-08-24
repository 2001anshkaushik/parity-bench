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
    recently active worker (LIFO). Dead pids never serve."""
    name = 'llamaindex'

    def __init__(self, workers=8, dead=()):
        self.declared_workers = workers
        self.pids = [4000 + k for k in range(workers)]
        self.dead = set(dead)
        self.live = [p for p in self.pids if p not in self.dead]
        self.in_flight = 0
        self.hot = self.live[0]
        self.served: list[int] = []

    async def process(self, blob, name):
        self.in_flight += 1
        try:
            await asyncio.sleep(0.001)
            idle_share = min(self.in_flight, len(self.live))
            # concurrent arrivals spread over that many distinct live workers;
            # a lone arrival sticks to the hot one
            k = len(self.served)
            pid = self.live[k % idle_share] if idle_share > 1 else self.hot
            self.hot = pid
            self.served.append(pid)
            await asyncio.sleep(0.002)
            return {'serving_pid': pid, 'token_index': None}
        finally:
            self.in_flight -= 1


class FakeRRArm:
    name = 'rocketride'

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
        check('WARM_N=2, blast leg: coverage 8/8 reached (was 6/8 fatal)',
              doc['unserved_pids'] is None and len(doc['per_pid_send_counts']) == 8,
              json.dumps(doc['per_pid_send_counts']))
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
        check('sequential leg: wave still 16 (2 x workers floor), 8/8 covered',
              doc['unserved_pids'] is None and '16 concurrent' in doc['policy'], doc['policy'])

    print('\nCONTROL — the OLD shape (1-at-a-time) really does starve on this same fake')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8)
        async def old_shape():
            seen = set()
            for k in range(18):     # 2 "concurrent" + 16 sequential, as died on the box
                if k < 2:
                    recs = await asyncio.gather(arm.process(b'', 'w'), arm.process(b'', 'w'))
                    seen |= {r['serving_pid'] for r in recs}
                else:
                    seen.add((await arm.process(b'', 'w'))['serving_pid'])
            return seen
        seen = asyncio.run(old_shape())
        check('18 sends, 2 concurrent + 16 sequential -> coverage FAILS on the same fake '
              f'({len(seen)}/8) — the fix is the distribution, not the arm', len(seen) < 8)

    print('\nDEAD WORKERS — the discriminator: same pids missing at FULL concurrency')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeLIArm(workers=8, dead=(4006, 4007))
        rc, msg = 0, ''
        try:
            run(arm, drv.Posture('workers', 8, None), warm, args_for('llamaindex', corpus=corpus), d)
        except SystemExit as e:
            rc, msg = 1, str(e)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        check('gate FAILS and NAMES the two unserved pids', rc == 1 and '4006' in msg and '4007' in msg, msg)
        check('ledger written BEFORE the verdict, unserved recorded',
              doc['unserved_pids'] == [4006, 4007])
        check('both waves ran (32 sends = 4x workers, the proven load) before failing',
              '2 wave(s)' in doc['policy'] and len(doc['sends']) == 32, doc['policy'])
        check('the message says what this pattern means and forbids the wrong fix',
              'not distribution' in msg and 'do not raise the budget' in msg, msg)

    print('\nRR ARM — Corner-banked arithmetic unchanged, addressed not accepted')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus, warm = setup(d, warm_n=2)
        arm = FakeRRArm(tokens=16)
        run(arm, drv.Posture('parity', 16, 2), warm, args_for('rocketride', corpus=corpus), d)
        doc = json.loads((d / 'warmup_teststem.json').read_text())
        check('M=16, WARM_N=2: 2 first batch + 14 top-up = 16 sends, 16/16 tokens',
              len(doc['sends']) == 16 and doc['tokens_seen'] == list(range(16))
              and '2 first batch + 14 top-up' in doc['policy'], doc['policy'])
        check('RR policy names round-robin as ADDRESSED, kernel accept uninvolved',
              'round-robin' in doc['policy'] and 'addressed' in doc['policy'], doc['policy'])

    print(f'\nwarm-up distribution controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
