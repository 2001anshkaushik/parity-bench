#!/usr/bin/env python3
"""DIAG_M1_BLAST fix, proven against the REAL run_leg — no box, no docker.

Asserts the four requirements: (1) reads+sha happen off the event loop (the
loop keeps ticking while a slow read runs); (2) at most C blobs resident —
a row owns a semaphore slot before it owns bytes; (3) submission order is
manifest order (enqueue_ns monotonic over rows); (4) wall_s still measures
admit->done only — read time is recorded BESIDE it (read_s), never inside it.

Run:  python3 working/video/test_read_residency.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import driver_video as drv                       # noqa: E402
from harness.jsonl_stream import JsonlWriter     # noqa: E402

FAILS: list[str] = []


def check(name, cond, detail=''):
    if not cond:
        FAILS.append(name)
    print(f'  {"ok  " if cond else "FAIL"} {name}' + (f'\n       {detail}' if not cond else ''))


class GaugeArm:
    """Counts concurrent process() calls; sleeps to hold C slots open."""
    name = 'rocketride_video'

    def __init__(self):
        self.in_flight = self.max_in_flight = 0

    async def process(self, blob, name):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.15)
        self.in_flight -= 1
        return {'n_chunks': 1, 'total_chars': len(blob)}


async def loop_heartbeat(samples: list, stop: asyncio.Event):
    """If reads ran ON the loop, gaps between beats would show it."""
    prev = time.monotonic()
    while not stop.is_set():
        await asyncio.sleep(0.01)
        now = time.monotonic()
        samples.append(now - prev)
        prev = now


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus = d / 'corpus'
        corpus.mkdir()
        rows = []
        for k in range(12):
            f = f'v{k:02d}.avi'
            (corpus / f).write_bytes(bytes([k]) * 3_000_000)   # 3MB — real read, fast test
            rows.append({'file': f, 'role': 'measured', 'video_s': 1.0,
                         'expected_frames_measured': 1})
        arm = GaugeArm()
        beats: list = []
        stop = asyncio.Event()

        async def go():
            hb = asyncio.create_task(loop_heartbeat(beats, stop))
            with JsonlWriter(d / 'records.jsonl') as writer:
                out = await drv.run_leg(arm, rows, 'blast', 4, corpus, writer, set(), 15)
            stop.set()
            await hb
            return out

        out = asyncio.run(go())
        recs = [json.loads(l) for l in (d / 'records.jsonl').read_text().splitlines()]

        check('(2) max resident blobs <= C=4, returned by run_leg',
              out.get('max_resident_blobs') is not None and out['max_resident_blobs'] <= 4,
              str(out))
        check('    ...and concurrency actually happened (max > 1, arm saw 4 in flight)',
              out['max_resident_blobs'] > 1 and arm.max_in_flight == 4,
              f'resident={out["max_resident_blobs"]} arm={arm.max_in_flight}')
        check('(3) submission order preserved: enqueue_ns monotonic in manifest order',
              [r['video'] for r in sorted(recs, key=lambda r: r['enqueue_ns'])]
              == [r['file'] for r in rows])
        check('(4) every record carries read_s BESIDE wall_s; admit stamped after read',
              all('read_s' in r and r['admit_ns'] > r['enqueue_ns'] for r in recs))
        check('    ...wall_s measures the arm only (~0.15s sleep, not read+sleep)',
              all(0.10 <= r['wall_s'] <= 0.60 for r in recs),
              str(sorted(r['wall_s'] for r in recs)))
        check('(1) event loop kept beating during reads (max gap far under one read train)',
              beats and max(beats) < 0.25, f'max gap {max(beats):.3f}s over {len(beats)} beats')
        check('12/12 records, 0 errors',
              len(recs) == 12 and not any('error' in r for r in recs))

        # NULL CONTROL: the gauge must be capable of exceeding a smaller cap —
        # rerun at C=8 and require max_resident > 4, so "<=4" above is a
        # measurement, not a constant the gauge can never violate.
        async def go2():
            with JsonlWriter(d / 'records2.jsonl') as writer2:
                return await drv.run_leg(GaugeArm(), rows, 'blast', 8, corpus,
                                         writer2, set(), 15)
        out2 = asyncio.run(go2())
        check('NULL CONTROL: at C=8 residency exceeds 4 (the gauge can move)',
              out2['max_resident_blobs'] > 4, str(out2))

    print(f'\nread-residency controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
