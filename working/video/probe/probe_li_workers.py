#!/usr/bin/env python3
"""LlamaIndex worker sweep — LI_WORKERS gets MEASURED the same way M_TOKENS is.

Ruling (2026-08-21): deriving LI_WORKERS from floor-curve + memory arithmetic
is a derived-not-measured value — the class this campaign keeps catching.
Same shape as probe_concurrency, per W in the sweep:

  * fresh li container with WS1V_WORKERS=W (a prior W's workers would pollute
    the census), wait until /health reports warm_workers == W;
  * IDLE-AT-W: container cgroup over a quiet window after warm, before work —
    the symmetric twin of the RR idle-at-M measurement;
  * W concurrent /process_video posts of the probe video; serving census =
    distinct response pids (every response carries its worker's pid) PLUS
    per-process CPU deltas inside the container — config is never the evidence;
  * throughput, marginal efficiency, knee at <0.7 (same rule), cgroup anon +
    memory.peak per W (the RAM ceiling, symmetric with the RR sweep).

Note on distinct pids: kernel accept routing is not round-robin (#21), so
distinct_pids < W on ONE batch is scheduling, not a defect — the CPU-delta
census is the serving proof; distinct pids are reported alongside.

Runs AFTER the RR sweep (box order). Uses the floor venv (requests via
urllib, no SDK needed — but the venv contract stays uniform).

Usage:
    python3 probe_li_workers.py --video media/ES2002a.Corner.avi \
        [--sweep 1 2 4 8 16] [--image li:video] [--threads-env 1]
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_rr import cgroup_snapshot, proc_cpu_ticks  # noqa: E402
from wait_ready import assert_host_network, wait_li_ready  # noqa: E402

CONTAINER = 'liconc'
PORT = 8802


def sh(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def worker_census(container: str) -> list[dict]:
    raw = sh(['docker', 'exec', container, 'ps', '-eo', 'pid,ppid,rss,args']).stdout
    procs = []
    for line in raw.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) == 4 and 'uvicorn' in parts[3]:
            procs.append({'pid': int(parts[0]), 'ppid': int(parts[1]),
                          'rss_kb': int(parts[2])})
    return procs


def start_container(image: str, workers: int, threads_env: int) -> dict:
    sh(['docker', 'rm', '-f', CONTAINER])
    env_args = []
    for k in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS']:
        env_args += ['-e', f'{k}={threads_env}']
    # Crossroad 22: --network host both arms; the warm_workers==W predicate was
    # already the real one — it moves into the shared helper unchanged, and the
    # network mode becomes a read-back, not an implied flag. Under host mode
    # the service must bind 8802 itself (PORT stays 8802, no mapping).
    r = sh(['docker', 'run', '-d', '--name', CONTAINER, '--memory', '58g',
            *env_args, '-e', f'WS1V_WORKERS={workers}',
            '--network', 'host', image])
    if r.returncode != 0:
        raise SystemExit(f'docker run failed: {r.stderr}')
    net = assert_host_network(CONTAINER)
    ready = wait_li_ready(port=PORT, deadline_s=900, workers=workers,
                          container=CONTAINER)
    return {'network_mode': net, **ready}


def post_video(blob: bytes) -> dict:
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/process_video', data=blob,
                                 method='POST',
                                 headers={'Content-Type': 'application/octet-stream'})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=7200) as resp:
        body = json.load(resp)
    if 'error' in body:
        raise RuntimeError(f'service error: {body}')
    return {'wall_s': round(time.monotonic() - t0, 1), 'pid': body.get('pid'),
            'n_frames': body.get('n_frames'), 'n_chunks': body.get('n_chunks')}


async def measure_w(w: int, blob: bytes) -> dict:
    census = worker_census(CONTAINER)
    pids = [p['pid'] for p in census]

    idle_window_s = 6.0
    cg0 = cgroup_snapshot(CONTAINER)
    ticks0 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    await asyncio.sleep(idle_window_s)
    cg1 = cgroup_snapshot(CONTAINER)
    ticks1 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    idle_cores = (round((cg1['usage_usec'] - cg0['usage_usec']) / 1e6 / idle_window_s, 3)
                  if cg0['usage_usec'] is not None and cg1['usage_usec'] is not None else None)
    idle_per_proc = {pid: round(((ticks1.get(pid) or 0) - (ticks0.get(pid) or 0)) / 100
                                / idle_window_s, 3)
                     for pid in pids if ticks0.get(pid) is not None}

    # warm round: one post per worker slot so measurement is steady-state
    await asyncio.gather(*[asyncio.to_thread(post_video, blob) for _ in range(w)],
                         return_exceptions=True)

    ticks_b0 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    cg_b0 = cgroup_snapshot(CONTAINER)
    t0 = time.monotonic()
    results = await asyncio.gather(*[asyncio.to_thread(post_video, blob) for _ in range(w)],
                                   return_exceptions=True)
    batch_wall = time.monotonic() - t0
    cg_b1 = cgroup_snapshot(CONTAINER)
    ticks_b1 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}

    ok = [r for r in results if not isinstance(r, Exception)]
    errors = [repr(r) for r in results if isinstance(r, Exception)]
    per_proc = {pid: round(((ticks_b1.get(pid) or 0) - (ticks_b0.get(pid) or 0)) / 100, 1)
                for pid in pids if ticks_b0.get(pid) is not None}
    serving_cpu = sorted(pid for pid, s in per_proc.items() if s > 5.0)
    return {
        'W': w,
        'declared_workers': w,
        'worker_processes': len(census),
        'idle_cores_after_warm_workers': idle_cores,
        'idle_cores_per_process': idle_per_proc,
        'distinct_response_pids': len({r['pid'] for r in ok}),
        'serving_by_cpu_delta': len(serving_cpu),
        'per_process_cpu_s': per_proc,
        'batch_wall_s': round(batch_wall, 1),
        'per_post_wall_s': sorted(r['wall_s'] for r in ok),
        'frames_check': sorted({r['n_frames'] for r in ok}),
        'errors': errors or None,
        'throughput_videos_per_s': round(w / batch_wall, 4) if batch_wall and not errors else None,
        'cpu_util_of_32': (round((cg_b1['usage_usec'] - cg_b0['usage_usec']) / 1e6 / batch_wall / 32, 3)
                           if cg_b0['usage_usec'] is not None and cg_b1['usage_usec'] is not None else None),
        'anon_bytes_after_warm': cg_b0['anon_bytes'],
        'memory_peak_bytes': cg_b1['memory_peak_bytes'],
    }


async def amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--sweep', type=int, nargs='+', default=[1, 2, 4, 8, 16])
    ap.add_argument('--image', default='li:video')
    ap.add_argument('--threads-env', type=int, default=1,
                    help='the six vars on the LI container for this sweep (its own matrix)')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_li_workers_out.json'))
    args = ap.parse_args()

    blob = Path(args.video).read_bytes()
    points, knee = [], None
    for w in args.sweep:
        print(f'== W={w}: fresh container ==', flush=True)
        start_info = start_container(args.image, w, args.threads_env)
        point = await measure_w(w, blob)
        point['network_mode'] = start_info['network_mode']
        point['ready_wall_s'] = start_info['wall_s']
        points.append(point)
        print(json.dumps({k: point[k] for k in
                          ('W', 'serving_by_cpu_delta', 'distinct_response_pids',
                           'idle_cores_after_warm_workers', 'batch_wall_s',
                           'throughput_videos_per_s', 'cpu_util_of_32')}), flush=True)
        if point['errors'] or point['serving_by_cpu_delta'] < w:
            print(f'STOP at W={w}: serving={point["serving_by_cpu_delta"]} '
                  f'errors={point["errors"]} — investigate before going wider', flush=True)
            break
        if len(points) >= 2 and points[-2]['throughput_videos_per_s'] and point['throughput_videos_per_s']:
            marginal = ((point['throughput_videos_per_s'] / points[-2]['throughput_videos_per_s'])
                        / (w / points[-2]['W']))
            point['marginal_efficiency'] = round(marginal, 3)
            if knee is None and marginal < 0.7:
                knee = w
                print(f'KNEE at W={w}: marginal efficiency {marginal:.2f} < 0.7', flush=True)
    sh(['docker', 'rm', '-f', CONTAINER])

    base = points[0]['throughput_videos_per_s'] if points else None
    for p in points:
        if base and p['throughput_videos_per_s']:
            p['efficiency_vs_linear'] = round(p['throughput_videos_per_s'] / (p['W'] * base), 3)
    report = {'sweep': args.sweep, 'threads_env': args.threads_env, 'points': points,
              'idle_cores_by_W': {p['W']: p.get('idle_cores_after_warm_workers') for p in points},
              'knee_W': knee,
              'rule': 'LI_WORKERS sits AT the knee, never past it — measured the same way '
                      'M_TOKENS is (no handicaps, no derived values)'}
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
