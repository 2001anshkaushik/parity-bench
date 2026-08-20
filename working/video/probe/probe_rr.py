#!/usr/bin/env python3
"""RocketRide-arm single-video probe. No harness imports. Wall clock at C=1,
plus a token-topology census that PROVES how many detector instances serve.

Usage:
    python3 probe_rr.py --video media/ES2002a.Corner.avi [--container rrprobe]
                        [--pipe ../benchmark_video_detect.pipe] [--sends 2]
                        [--tokens 1] [--out probe_rr_out.json]

Per send it reports: wall seconds; chunks (len(response['documents']));
chunkId monotonicity (accumulate-then-split proof); the stock-defect
duplication signature (whole-list doubling) vs organic exact-duplicate
chunks; cgroup cpu/memory read from the CONTAINER's own cgroup (never the
driver's affinity); driver CPU; frames counted from the detect node's debug
lines when the container log level surfaces them.

--tokens M > 1 runs the topology census: M use() calls -> M task
subprocesses expected; process census inside the container (ps), then M
CONCURRENT sends with per-process CPU deltas -> the count of task processes
that actually burned CPU is the number of detector instances SERVING.
Config is never the evidence.

Requires: pip install rocketride==1.3.0 (the pin the image bakes).
"""

import argparse
import asyncio
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

from rocketride import RocketRide


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:  # noqa: BLE001 - probe reports, never masks
        return f'<failed: {exc!r}>'


def cgroup_snapshot(container: str) -> dict:
    """Read the container's own cgroup v2 counters. None where unreadable."""
    out = {}
    for name, path in [('cpu_stat', '/sys/fs/cgroup/cpu.stat'),
                       ('memory_peak', '/sys/fs/cgroup/memory.peak'),
                       ('memory_stat', '/sys/fs/cgroup/memory.stat'),
                       ('io_stat', '/sys/fs/cgroup/io.stat')]:
        raw = sh(['docker', 'exec', container, 'cat', path])
        out[name] = None if raw.startswith('<failed') else raw
    snap = {'raw': out}
    try:
        snap['usage_usec'] = int([l for l in out['cpu_stat'].splitlines()
                                  if l.startswith('usage_usec')][0].split()[1])
    except Exception:
        snap['usage_usec'] = None
    try:
        snap['memory_peak_bytes'] = int(out['memory_peak'].strip())
    except Exception:
        snap['memory_peak_bytes'] = None
    try:
        snap['anon_bytes'] = int([l for l in out['memory_stat'].splitlines()
                                  if l.split()[0] == 'anon'][0].split()[1])
    except Exception:
        snap['anon_bytes'] = None
    try:
        snap['io_rbytes'] = sum(int(kv.split('=')[1]) for line in out['io_stat'].splitlines()
                                for kv in line.split()[1:] if kv.startswith('rbytes='))
    except Exception:
        snap['io_rbytes'] = None
    return snap


def task_process_census(container: str) -> list[dict]:
    """Task subprocesses inside the container: [{pid, rss_kb, args}]."""
    raw = sh(['docker', 'exec', container, 'ps', '-eo', 'pid,ppid,rss,args'])
    procs = []
    for line in raw.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, rss, args = parts
        # The engine spawns one task subprocess per token (task_engine.py:1561).
        # Its argv carries the task/pipeline arguments; the serving parent is PID 1.
        if 'node.py' in args or 'task' in args.lower():
            procs.append({'pid': int(pid), 'ppid': int(ppid),
                          'rss_kb': int(rss), 'args': args[:200]})
    return procs


def proc_cpu_ticks(container: str, pid: int):
    raw = sh(['docker', 'exec', container, 'cat', f'/proc/{pid}/stat'])
    try:
        f = raw.rsplit(')', 1)[1].split()
        return int(f[11]) + int(f[12])  # utime + stime, post-comm fields
    except Exception:
        return None


def frames_from_logs(container: str, since: str) -> dict:
    """Count detect's per-frame debug lines. Absent lines != absent frames —
    the LI floor's extraction (same ffmpeg, same filter) is the independent count."""
    raw = sh(['docker', 'logs', '--since', since, container])
    lines = [l for l in raw.splitlines() if 'detect:' in l and 'detect=' in l]
    out = {'frame_debug_lines': len(lines) if lines else None}
    if lines:
        try:
            ms = [float(l.split('detect=')[1].split('ms')[0]) for l in lines]
            out['detect_ms_min_mean_max'] = [min(ms), sum(ms) / len(ms), max(ms)]
        except Exception:
            pass
    return out


def analyse_documents(docs: list[dict]) -> dict:
    contents = [d.get('page_content') or '' for d in docs]
    hashes = [hashlib.sha256(c.encode()).hexdigest()[:16] for c in contents]
    n = len(hashes)
    chunk_ids = [(d.get('metadata') or {}).get('chunkId') for d in docs]
    monotone = all(isinstance(c, int) for c in chunk_ids) and chunk_ids == sorted(chunk_ids)
    # Stock-defect signature: the WHOLE list emitted twice.
    doubled = n % 2 == 0 and n > 0 and hashes[: n // 2] == hashes[n // 2:]
    lens = [len(c) for c in contents]
    return {
        'n_chunks': n,
        'chunk_chars_min_mean_max': [min(lens), round(sum(lens) / n, 1), max(lens)] if n else None,
        'total_chars': sum(lens),
        'chunkid_monotone': monotone,
        'chunkid_first_last': [chunk_ids[0], chunk_ids[-1]] if n else None,
        'whole_list_doubled': doubled,           # the defect signature
        'organic_duplicate_chunks': n - len(set(hashes)) if not doubled else None,
        'max_chunk_over_512': max(lens) > 512 if n else None,   # chunking read-back
    }


async def one_send(client, token, blob, name):
    t0 = time.monotonic()
    result = await client.send(token, blob, objinfo={'name': name},
                               mimetype='video/x-msvideo')
    return time.monotonic() - t0, result


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--pipe', default=str(Path(__file__).parent.parent / 'benchmark_video_detect.pipe'))
    ap.add_argument('--container', default='rrprobe')
    ap.add_argument('--sends', type=int, default=2)
    ap.add_argument('--tokens', type=int, default=1)
    ap.add_argument('--port', type=int, default=5565)
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_rr_out.json'))
    args = ap.parse_args()

    blob = Path(args.video).read_bytes()
    report = {'video': args.video, 'video_sha16': hashlib.sha256(blob).hexdigest()[:16],
              'pipe': args.pipe, 'tokens': args.tokens, 'sends': [], 'rc': 0}
    print(f'video {len(blob)} bytes, pipe {args.pipe}')

    client = RocketRide(uri=f'ws://127.0.0.1:{args.port}/task/service', apikey='local-dev')
    await client.connect()

    census_before = task_process_census(args.container)
    tokens = []
    t0 = time.monotonic()
    for i in range(args.tokens):
        started = await client.use(filepath=args.pipe, ttl=7200)
        tokens.append(started['token'])
        print(f'use() #{i + 1}: {time.monotonic() - t0:.1f}s cumulative')
    census_after_use = task_process_census(args.container)
    report['census'] = {
        'task_procs_before_use': len(census_before),
        'task_procs_after_use': len(census_after_use),
        'procs': census_after_use,
    }
    print(f'task processes: {len(census_before)} -> {len(census_after_use)} '
          f'(expected +{args.tokens})')

    if args.tokens == 1:
        # ---- C=1 timing runs: send-1 = first-load, send-2 = steady state ----
        for i in range(1, args.sends + 1):
            label = 'first-load' if i == 1 else 'steady-state'
            since = time.strftime('%Y-%m-%dT%H:%M:%S')
            pre = cgroup_snapshot(args.container)
            dr0 = resource.getrusage(resource.RUSAGE_SELF)
            try:
                wall, result = await one_send(client, tokens[0], blob, Path(args.video).name)
            except Exception as exc:  # noqa: BLE001
                print(f'send {i} ({label}): FAILED: {exc!r}')
                report['sends'].append({'label': label, 'error': repr(exc)})
                report['rc'] = 1
                break
            post = cgroup_snapshot(args.container)
            dr1 = resource.getrusage(resource.RUSAGE_SELF)
            docs = (result or {}).get('documents') or []
            entry = {
                'label': label,
                'wall_s': round(wall, 2),
                'documents': analyse_documents(docs),
                'result_keys': sorted((result or {}).keys()),
                'cgroup': {
                    'cpu_s': (post['usage_usec'] - pre['usage_usec']) / 1e6
                             if pre['usage_usec'] is not None and post['usage_usec'] is not None else None,
                    'cpu_util_of_32': round((post['usage_usec'] - pre['usage_usec']) / 1e6 / wall / 32, 4)
                             if pre['usage_usec'] is not None and post['usage_usec'] is not None else None,
                    'memory_peak_bytes': post['memory_peak_bytes'],
                    'anon_bytes_after': post['anon_bytes'],
                    'io_rbytes_delta': (post['io_rbytes'] - pre['io_rbytes'])
                             if pre['io_rbytes'] is not None and post['io_rbytes'] is not None else None,
                },
                'driver_cpu_s': round((dr1.ru_utime + dr1.ru_stime) - (dr0.ru_utime + dr0.ru_stime), 2),
                'frames': frames_from_logs(args.container, since),
            }
            report['sends'].append(entry)
            print(f'send {i} ({label}): wall={wall:.1f}s '
                  f'chunks={entry["documents"]["n_chunks"]} '
                  f'doubled={entry["documents"]["whole_list_doubled"]} '
                  f'cpu_util={entry["cgroup"]["cpu_util_of_32"]}')
            d = entry['documents']
            if d['n_chunks'] == 0 or not d['chunkid_monotone'] or d['whole_list_doubled']:
                report['rc'] = 1
    else:
        # ---- token-topology census: M concurrent sends, per-process CPU ----
        pids = [p['pid'] for p in census_after_use]
        ticks_before = {pid: proc_cpu_ticks(args.container, pid) for pid in pids}
        t0 = time.monotonic()
        results = await asyncio.gather(
            *[one_send(client, tok, blob, f'census_{k}_{Path(args.video).name}')
              for k, tok in enumerate(tokens)],
            return_exceptions=True)
        batch_wall = time.monotonic() - t0
        ticks_after = {pid: proc_cpu_ticks(args.container, pid) for pid in pids}
        hz = 100  # kernel USER_HZ; fine for a serving/not-serving distinction
        per_proc = {pid: round(((ticks_after[pid] or 0) - (ticks_before[pid] or 0)) / hz, 1)
                    for pid in pids if ticks_before[pid] is not None}
        serving = [pid for pid, s in per_proc.items() if s > 5.0]
        walls = [round(r[0], 1) for r in results if not isinstance(r, Exception)]
        errors = [repr(r) for r in results if isinstance(r, Exception)]
        report['topology'] = {
            'batch_wall_s': round(batch_wall, 1),
            'per_send_wall_s': walls,
            'errors': errors or None,
            'per_process_cpu_s': per_proc,
            'processes_serving': len(serving),
            'serving_pids': serving,
        }
        print(f'topology: {args.tokens} tokens, batch wall {batch_wall:.0f}s, '
              f'{len(serving)} task processes burned >5s CPU (instances serving)')
        if len(serving) < args.tokens or errors:
            report['rc'] = 1

    await client.disconnect()
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f'wrote {args.out}')
    return report['rc']


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
