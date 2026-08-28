#!/usr/bin/env python3
"""Streaming-refactor residency contract, proven against the REAL run_leg —
no box, no docker. (Successor to the DIAG_M1_BLAST-era test; rewritten
deliberately for Ruling 4, 2026-08-27 — the old contract asserted "at most C
blobs resident", the new one asserts NO whole blob exists at all.)

Asserts: (1) the sha pass runs off the event loop (the loop keeps beating);
(2) at most C in-flight streams hold a slot, and NO code path reads a whole
file into memory (Path.read_bytes is tripwired for the leg's duration);
(3) submission order is manifest order; (4) wall_s still measures
admit->done only — the sha pass is recorded BESIDE it as read_s with its
basis named; (5) arms receive a PATH, never bytes; (6) RRArm streams the
file as exact 1 MiB writes with stat-sized objinfo.

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
    """Counts concurrent process() calls; sleeps to hold C slots open.
    Contract check: process() must receive a PATH, never bytes."""
    name = 'rocketride_video'

    def __init__(self):
        self.in_flight = self.max_in_flight = 0
        self.got_bytes = False

    async def process(self, path, name):
        if isinstance(path, (bytes, bytearray)):
            self.got_bytes = True
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.15)
        self.in_flight -= 1
        return {'n_chunks': 1, 'total_chars': Path(path).stat().st_size}


async def loop_heartbeat(samples: list, stop: asyncio.Event):
    """If the sha passes ran ON the loop, gaps between beats would show it."""
    prev = time.monotonic()
    while not stop.is_set():
        await asyncio.sleep(0.01)
        now = time.monotonic()
        samples.append(now - prev)
        prev = now


class ReadBytesTripwire:
    """Whole-file reads are the failure the refactor removes: any
    Path.read_bytes during the leg turns into an error in a record."""

    def __enter__(self):
        self._orig = Path.read_bytes
        def boom(p):  # noqa: ANN001
            raise AssertionError(f'whole-file read_bytes({p}) — the streaming '
                                 'refactor forbids whole-blob reads')
        Path.read_bytes = boom
        return self

    def __exit__(self, *a):
        Path.read_bytes = self._orig


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus = d / 'corpus'
        corpus.mkdir()
        rows = []
        for k in range(12):
            f = f'v{k:02d}.avi'
            (corpus / f).write_bytes(bytes([k]) * 3_000_000)   # 3MB — real sha pass, fast test
            rows.append({'file': f, 'role': 'measured', 'video_s': 1.0,
                         'expected_frames_measured': 1})
        arm = GaugeArm()
        beats: list = []
        stop = asyncio.Event()

        async def go():
            hb = asyncio.create_task(loop_heartbeat(beats, stop))
            with JsonlWriter(d / 'records.jsonl') as writer:
                with ReadBytesTripwire():
                    out = await drv.run_leg(arm, rows, 'blast', 4, corpus, writer, set(), 15)
            stop.set()
            await hb
            return out

        out = asyncio.run(go())
        recs = [json.loads(l) for l in (d / 'records.jsonl').read_text().splitlines()]

        check('(2) max in-flight streams <= C=4, returned by run_leg',
              out.get('max_inflight_streams') is not None and out['max_inflight_streams'] <= 4,
              str(out))
        check('    ...and concurrency actually happened (max > 1, arm saw 4 in flight)',
              out['max_inflight_streams'] > 1 and arm.max_in_flight == 4,
              f'inflight={out["max_inflight_streams"]} arm={arm.max_in_flight}')
        check('(2b) NO whole-file read anywhere in the leg (read_bytes tripwired) '
              'and 12/12 records, 0 errors',
              len(recs) == 12 and not any('error' in r for r in recs),
              str([r.get('error') for r in recs if 'error' in r][:2]))
        check('(5) arms received PATHS, never bytes', arm.got_bytes is False)
        check('(3) submission order preserved: enqueue_ns monotonic in manifest order',
              [r['video'] for r in sorted(recs, key=lambda r: r['enqueue_ns'])]
              == [r['file'] for r in rows])
        check('(4) every record carries read_s + its basis BESIDE wall_s; admit after sha',
              all('read_s' in r and 'read_s_basis' in r
                  and r['admit_ns'] > r['enqueue_ns'] for r in recs))
        check('    ...wall_s measures the arm only (~0.15s sleep, not sha+sleep)',
              all(0.10 <= r['wall_s'] <= 0.60 for r in recs),
              str(sorted(r['wall_s'] for r in recs)))
        check('    ...bytes recorded from stat (3MB each)',
              all(r['bytes'] == 3_000_000 for r in recs))
        check('(1) event loop kept beating during sha passes (max gap far under one pass train)',
              beats and max(beats) < 0.25, f'max gap {max(beats):.3f}s over {len(beats)} beats')

        # NULL CONTROL: the gauge must be capable of exceeding a smaller cap —
        # rerun at C=8 and require max > 4, so "<=4" above is a measurement,
        # not a constant the gauge can never violate.
        async def go2():
            with JsonlWriter(d / 'records2.jsonl') as writer2:
                with ReadBytesTripwire():
                    return await drv.run_leg(GaugeArm(), rows, 'blast', 8, corpus,
                                             writer2, set(), 15)
        out2 = asyncio.run(go2())
        check('NULL CONTROL: at C=8 in-flight exceeds 4 (the gauge can move)',
              out2['max_inflight_streams'] > 4, str(out2))

    print('\nCHUNKED WRITE PATH (RRArm.process streaming a real temp file into a fake pipe)')

    class FakePipe:
        def __init__(self, fail_at=None):
            self.writes, self.opened, self.closes, self.fail_at = [], False, 0, fail_at

        @property
        def is_opened(self):
            return self.opened and not self.closes

        async def open(self):
            self.opened = True

        async def write(self, buf):
            if self.fail_at is not None and len(self.writes) == self.fail_at:
                raise ConnectionError('injected mid-stream failure')
            self.writes.append(len(buf))

        async def close(self):
            self.closes += 1
            return {'documents': [{'page_content': 'x' * 10,
                                   'metadata': {'chunkId': 0, 'time_stamp': 0}}]}

    class FakeClient:
        def __init__(self, pipe):
            self._p = pipe
            self.args = None

        async def pipe(self, token, objinfo, mimetype):
            self.args = (token, dict(objinfo), mimetype)
            return self._p

    def mk_arm(pipe):
        arm = drv.RRArm.__new__(drv.RRArm)
        arm.client = FakeClient(pipe)
        arm.tokens, arm.project_ids, arm._rr = ['tokA'], ['p'], 0
        return arm

    MB = 1024 * 1024
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        big = d / 'v.avi'
        big.write_bytes(b'z' * (2 * MB + 5))
        fp = FakePipe()
        rec = asyncio.run(mk_arm(fp).process(big, 'v.avi'))
        check('file streamed at exactly 1 MiB with a partial tail, in order',
              fp.writes == [MB, MB, 5], str(fp.writes))
        check('record carries write_path/upload_source/token_index; result via record_from_rr',
              rec.get('write_path') == 'chunked-1MiB x 3'
              and rec.get('upload_source') == 'file-streamed'
              and rec.get('token_index') == 0 and rec.get('n_chunks') == 1,
              str({k: rec.get(k) for k in ('write_path', 'upload_source', 'token_index', 'n_chunks')}))
        check('close() called exactly once on success', fp.closes == 1)

        big3 = d / 'v3.avi'
        big3.write_bytes(b'z' * (3 * MB))
        fp2 = FakePipe(fail_at=1)
        try:
            asyncio.run(mk_arm(fp2).process(big3, 'v3.avi'))
            check('mid-stream failure propagates', False, 'no raise')
        except ConnectionError:
            check('mid-stream failure propagates after cleanup close',
                  fp2.closes == 1 and fp2.writes == [MB], f'closes={fp2.closes} writes={fp2.writes}')

        small = d / 'small.avi'
        small.write_bytes(b'q' * 100)
        arm3 = mk_arm(FakePipe())
        asyncio.run(arm3.process(small, 'small.avi'))
        check('objinfo = {name, size-from-stat}, mimetype video/x-msvideo (send()-identical surface)',
              arm3.client.args == ('tokA', {'name': 'small.avi', 'size': 100}, 'video/x-msvideo'),
              str(arm3.client.args))

    print(f'\nstreaming-residency controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
