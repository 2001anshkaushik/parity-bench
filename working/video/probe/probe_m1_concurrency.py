#!/usr/bin/env python3
"""THE M=1 CONCURRENCY DISCRIMINATOR (2026-08-24) — one token, N concurrent
send(), the TRUE exception captured before the SDK discards it.

Why this exists: three RR default-blast failures printed
ConnectionError('Could not send request'). That string is minted at
dap_client.py:229 inside `except Exception:` — the ORIGINAL exception is
swallowed, so the records cannot distinguish a websockets concurrency error
from a ping starvation from a server rejection. This probe patches, at class
level, BOTH layers under that line:

    DAPClient._send          -> logs repr + type + traceback of the real error
    TransportWebSocket.send  -> same, at the wire layer

then runs a matrix over ONE token (ttl=0, terminated unconditionally):

    C=1  big blob   NULL CONTROL — the sequential leg proved this works;
                    if this fails, the environment is broken, stop reading
    C=2  big blob   the smallest concurrency
    C=16 big blob   the shape that failed three times
    C=16 small blob (--small-video) — Corner's default blast PASSED at C=16
                    with ~this size, so this cell discriminates SIZE from
                    CONCURRENCY: if it passes where big-C16 fails, the story
                    is size x concurrency, not "one token cannot serve
                    concurrent sends" (which Corner already falsified)

Fresh client + fresh token PER POINT: a connection killed by point N must not
fail point N+1 by inheritance. Failure answers in seconds; a fully passing
matrix costs minutes (the engine serializes inference behind one device lock).

Run (box, Phase 1 venv, engine already serving on --port):
    ~/.venv/bin/python working/video/probe/probe_m1_concurrency.py \
        --video ~/parity-bench-video/corpus/ami/full/EN2001a.avi \
        --small-video <a Corner-sized file, optional> [--points 1 2 16]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from argtypes import positive_int          # noqa: E402
from probe_rr import fresh_project_pipe    # noqa: E402

PIPE_PATH = Path(__file__).resolve().parent.parent / 'benchmark_video_detect.pipe'
TRUTH: list[dict] = []      # every real exception, in arrival order


def _install_truth_taps() -> list[str]:
    """Class-level wraps on the layers whose errors dap_client.py:229 swallows.
    Returns what was actually patched — if the installed wheel's names differ
    from the pinned source, SAY SO rather than silently probing unpatched."""
    patched = []

    def wrap(cls, name, layer):
        orig = getattr(cls, name, None)
        if orig is None:
            return False

        async def tapped(self, *a, **kw):
            try:
                return await orig(self, *a, **kw)
            except BaseException as e:
                TRUTH.append({'layer': layer, 'type': type(e).__name__, 'repr': repr(e),
                              'when': time.monotonic(),
                              'traceback': traceback.format_exc(limit=6)})
                raise
        setattr(cls, name, tapped)
        return True

    try:
        from rocketride.core.dap_client import DAPClient
        if wrap(DAPClient, '_send', 'dap_client._send'):
            patched.append('DAPClient._send')
    except Exception as e:  # noqa: BLE001
        print(f'tap NOT installed on DAPClient._send: {e!r}')
    try:
        from rocketride.core.transport_websocket import TransportWebSocket
        if wrap(TransportWebSocket, 'send', 'transport_websocket.send'):
            patched.append('TransportWebSocket.send')
    except Exception as e:  # noqa: BLE001
        print(f'tap NOT installed on TransportWebSocket.send: {e!r}')
    return patched


async def run_point(label: str, blob: bytes, conc: int, port: int) -> dict:
    """Fresh client, fresh ttl=0 token, `conc` concurrent send()s, everything
    recorded. Terminate + disconnect unconditionally (Crossroad 43)."""
    from rocketride import RocketRideClient
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    client = RocketRideClient()
    truth_mark = len(TRUTH)
    point = {'point': label, 'concurrency': conc, 'blob_bytes': len(blob),
             'sends': [], 'true_exceptions': None}
    await client.connect(timeout=60000)
    tok = None
    try:
        cfg = fresh_project_pipe(PIPE_PATH, f'm1conc-{label}')
        gen = Path(__file__).parent / f'm1conc_{label}_{os.getpid()}.pipe'
        gen.write_text(json.dumps(cfg, indent=1))
        tok = (await client.use(filepath=str(gen), ttl=0))['token']

        async def one(i: int) -> dict:
            t0 = time.monotonic()
            rec = {'i': i, 'ok': False, 'wall_s': None, 'error': None}
            try:
                await client.send(tok, blob, objinfo={'name': f'{label}_{i}.avi'},
                                  mimetype='video/x-msvideo')
                rec['ok'] = True
            except Exception as exc:  # noqa: BLE001
                rec['error'] = repr(exc)
            rec['wall_s'] = round(time.monotonic() - t0, 2)
            return rec

        point['sends'] = list(await asyncio.gather(*[one(i) for i in range(conc)]))
    finally:
        if tok is not None:
            for attempt in (1, 2):   # ttl=0: nothing reaps a leaked token (C43)
                try:
                    await asyncio.wait_for(client.terminate(tok), timeout=300)
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f'  terminate attempt {attempt}: {exc!r}')
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    point['true_exceptions'] = TRUTH[truth_mark:] or None
    ok = sum(1 for s in point['sends'] if s['ok'])
    print(f"  {label}: {ok}/{conc} ok; walls {[s['wall_s'] for s in point['sends']]}")
    if point['true_exceptions']:
        for t in point['true_exceptions']:
            print(f"    TRUE EXCEPTION [{t['layer']}] {t['type']}: {t['repr']}")
    return point


async def amain() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--video', required=True, help='the big (ami_full-sized) video')
    ap.add_argument('--small-video', default=None,
                    help='a Corner-sized video for the size-vs-concurrency cell')
    ap.add_argument('--port', type=positive_int('port', 65535), default=5565)
    ap.add_argument('--points', nargs='+', type=positive_int('points', 64), default=[1, 2, 16])
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_m1_concurrency_out.json'))
    args = ap.parse_args()

    import websockets
    patched = _install_truth_taps()
    print(f'taps installed: {patched or "NONE — results carry no true exceptions"}')
    print(f'websockets {getattr(websockets, "__version__", "?")}  '
          f'(ping_interval=15 ping_timeout=300 socket_timeout=180 per pinned constants)')

    big = Path(args.video).read_bytes()
    print(f'big blob: {Path(args.video).name} {len(big)/1e6:.1f} MB')
    points = []
    for c in args.points:
        points.append(await run_point(f'C{c}_big', big, c, args.port))
    if args.small_video:
        small = Path(args.small_video).read_bytes()
        print(f'small blob: {Path(args.small_video).name} {len(small)/1e6:.1f} MB')
        points.append(await run_point('C16_small', small, 16, args.port))

    doc = {'video': args.video, 'small_video': args.small_video,
           'websockets_version': getattr(websockets, '__version__', None),
           'taps': patched, 'points': points}
    Path(args.out).write_text(json.dumps(doc, indent=1))
    print(f'wrote {args.out}')

    c1 = next((p for p in points if p['point'] == 'C1_big'), None)
    if c1 and any(not s['ok'] for s in c1['sends']):
        print('NULL CONTROL FAILED — C=1 on the big blob failed; the environment is broken '
              'and nothing else in this file may be interpreted.')
        return 2
    verdicts = {p['point']: f"{sum(1 for s in p['sends'] if s['ok'])}/{p['concurrency']}"
                for p in points}
    print(f'VERDICT MATRIX: {verdicts}')
    print('Read the TRUE EXCEPTION lines above — that is the fact the campaign records '
          'never contained.')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
