#!/usr/bin/env python3
"""TRANSPORT COST PROBE (Task 3, 2026-08-25): what chunked 1 MiB writes cost
RocketRide versus whole-frame, same video, same container, same token, C=1 —
the only regime where whole-frame survives (the sequential legs proved it).

Design: strictly interleaved A/B pairs (whole, chunked, whole, chunked, ...)
so drift affects both modes equally; N pairs (default 4); per-send wall from
send-start to pipeline result. The inference inside is identical work, so the
mode DELTA is the transport cost. Reports mean/min/max per mode, the pairwise
deltas, and refuses to summarize if the spread swamps the delta.

    ~/.venv/bin/python working/video/probe/probe_transport_cost.py \
        --video ~/parity-bench-video/corpus/ami/full/EN2001a.avi [--pairs 4]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from argtypes import positive_int          # noqa: E402
from probe_rr import fresh_project_pipe    # noqa: E402

PIPE_PATH = Path(__file__).resolve().parent.parent / 'benchmark_video_detect.pipe'
CHUNK = 1024 * 1024


async def send_whole(client, token, blob, name):
    return await client.send(token, blob, objinfo={'name': name},
                             mimetype='video/x-msvideo')


async def send_chunked(client, token, blob, name):
    pipe = await client.pipe(token, {'name': name, 'size': len(blob)}, 'video/x-msvideo')
    await pipe.open()
    try:
        for off in range(0, len(blob), CHUNK):
            await pipe.write(blob[off:off + CHUNK])
        return await pipe.close()
    except Exception:
        if pipe.is_opened:
            try:
                await pipe.close()
            except Exception:  # noqa: BLE001
                pass
        raise


async def amain() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--video', required=True)
    ap.add_argument('--port', type=positive_int('port', 65535), default=5565)
    ap.add_argument('--pairs', type=positive_int('pairs', 32), default=4)
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_transport_cost_out.json'))
    args = ap.parse_args()

    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{args.port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    blob = Path(args.video).read_bytes()
    n_chunks = (len(blob) + CHUNK - 1) // CHUNK
    print(f'{Path(args.video).name}: {len(blob)/1e6:.1f} MB = 1 whole frame vs {n_chunks} chunks')

    client = RocketRideClient()
    await client.connect(timeout=60000)
    cfg = fresh_project_pipe(PIPE_PATH, 'transport-cost')
    gen = Path(__file__).parent / f'transport_cost_{os.getpid()}.pipe'
    gen.write_text(json.dumps(cfg, indent=1))
    tok = (await client.use(filepath=str(gen), ttl=0))['token']
    rows = []
    try:
        # one unmeasured warm send so neither mode pays first-inference cost
        await send_whole(client, tok, blob, 'warm.avi')
        for i in range(args.pairs):
            for mode, fn in (('whole', send_whole), ('chunked', send_chunked)):
                t0 = time.monotonic()
                r = await fn(client, tok, blob, f'{mode}_{i}.avi')
                wall = round(time.monotonic() - t0, 2)
                ndocs = len((r or {}).get('documents') or [])
                rows.append({'i': i, 'mode': mode, 'wall_s': wall, 'n_docs': ndocs})
                print(f'  pair {i} {mode:8s} wall {wall:7.2f}s  docs {ndocs}')
    finally:
        for attempt in (1, 2):
            try:
                await asyncio.wait_for(client.terminate(tok), timeout=300)
                break
            except Exception as exc:  # noqa: BLE001
                print(f'terminate attempt {attempt}: {exc!r}')
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    w = [r['wall_s'] for r in rows if r['mode'] == 'whole']
    c = [r['wall_s'] for r in rows if r['mode'] == 'chunked']
    deltas = [b - a for a, b in zip(w, c)]
    doc = {'video': args.video, 'bytes': len(blob), 'n_chunks': n_chunks, 'rows': rows,
           'whole_mean_s': round(statistics.mean(w), 2), 'chunked_mean_s': round(statistics.mean(c), 2),
           'pairwise_delta_s': [round(d, 2) for d in deltas],
           'mean_delta_s': round(statistics.mean(deltas), 2),
           'delta_pct_of_whole': round(100 * statistics.mean(deltas) / statistics.mean(w), 2)}
    Path(args.out).write_text(json.dumps(doc, indent=1))
    spread = max(w) - min(w)
    print(f"\nwhole {doc['whole_mean_s']}s  chunked {doc['chunked_mean_s']}s  "
          f"delta {doc['mean_delta_s']}s = {doc['delta_pct_of_whole']}% of whole")
    if abs(doc['mean_delta_s']) < spread:
        print(f'INCONCLUSIVE: |mean delta| {abs(doc["mean_delta_s"])}s < same-mode spread '
              f'{spread:.2f}s — raise --pairs; do NOT quote this delta.')
        return 2
    print('CONCLUSIVE at this spread; wrote ' + args.out)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
