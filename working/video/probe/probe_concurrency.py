#!/usr/bin/env python3
"""Token-concurrency sweep — the knee must appear HERE, not inside a measured run.

For each M in the sweep (default 1 2 4 8 16): fresh rr container (tokens from a
prior M would pollute the census — task subprocesses live for ttl), M x use(),
M concurrent sends of the probe video (one per token), then:

  * throughput(M) = M / batch_wall — videos per second at M instances;
  * scaling efficiency vs M=1: eff(M) = throughput(M) / (M * throughput(1));
  * instances SERVING proven by per-process CPU deltas (probe_rr census —
    config is never the evidence);
  * container cgroup anon + memory.peak per M — the RAM ceiling that bounds
    the parity posture on BOTH arms symmetrically.

KNEE RULE (reported, and it blocks the run plan): the first M whose marginal
efficiency  [throughput(M)/throughput(prev_M)] / [M/prev_M]  falls below 0.7
is flagged. If a knee exists at M <= the LI worker count, the parity posture's
M sits AT the knee, not past it, and the finding (RR instance scaling stops at
M=k) is published either way.

If serving < M at any point, §4's risk fired: tokens share a hidden
serialization below the python layer. That is a FINDING — the sweep stops,
reports, and exits non-zero so nothing downstream runs on a wrong model.

Usage (box):
    python3 probe_concurrency.py --video media/ES2002a.Corner.avi \
        [--sweep 1 2 4 8 16] [--image rr:patched] [--threads-env 8]
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_rr import (cgroup_snapshot, cleanup_tokens, fresh_project_pipe,  # noqa: E402
                      one_send, proc_cpu_ticks, task_process_census)
from sdk_identity import assert_unique_project_ids  # noqa: E402

CONTAINER = 'rrconc'


def sh(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def start_container(image: str, threads_env: int) -> None:
    sh(['docker', 'rm', '-f', CONTAINER])
    env_args = []
    for k in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS']:
        env_args += ['-e', f'{k}={threads_env}']
    r = sh(['docker', 'run', '-d', '--name', CONTAINER, '--memory', '58g',
            *env_args, '-p', '5565:5565', image])
    if r.returncode != 0:
        raise SystemExit(f'docker run failed: {r.stderr}')
    import socket
    for _ in range(360):
        try:
            socket.create_connection(('127.0.0.1', 5565), 2).close()
            return
        except OSError:
            time.sleep(5)
    raise SystemExit('engine never listened on 5565')


async def measure_m(m: int, blob: bytes, pipe: str, threads: int | None) -> dict:
    # Measured surface (Phase 1 + installed-wheel paste, 2026-08-22):
    # RocketRideClient bare, credentials via env, connect(timeout=60000).
    import os
    os.environ.setdefault('ROCKETRIDE_URI', 'http://127.0.0.1:5565')
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    client = RocketRideClient()
    await client.connect(timeout=60000)
    tokens, project_ids = [], []
    t0 = time.monotonic()
    try:
        for i in range(m):
            # D3: one fresh project_id per token — the engine derives the task
            # token from it; M use() on one id would be ONE task, and this
            # sweep would measure a queue at every M.
            cfg = fresh_project_pipe(pipe, f'conc-m{m}-tok{i}')
            gp = Path(__file__).parent / f'generated_conc_m{m}_tok{i}.pipe'
            gp.write_text(json.dumps(cfg, indent=1))
            project_ids.append(cfg['project_id'])
            kwargs = dict(filepath=str(gp), ttl=7200)
            if threads is not None:
                kwargs['threads'] = threads
            tokens.append((await client.use(**kwargs))['token'])
        assert_unique_project_ids([(f'tok{i}', p) for i, p in enumerate(project_ids)])
    except BaseException:
        await cleanup_tokens(client, tokens)
        raise
    use_wall = time.monotonic() - t0

    census = task_process_census(CONTAINER)
    pids = [p['pid'] for p in census]

    # IDLE-AT-M (2026-08-21): the engine burns ~1.002 cores doing nothing —
    # measure whether that spin SCALES PER TOKEN. Sample the container cgroup
    # AND per-process ticks over a quiet window AFTER use() x M, BEFORE any
    # work. If idle cores ~ M, the parity posture is structurally broken
    # (M=16 burns half the box on nothing) — a finding that reshapes the run
    # plan, not a nuisance. Per-process deltas attribute the spin: eaas
    # server vs task subprocesses.
    idle_window_s = 6.0
    cg_i0 = cgroup_snapshot(CONTAINER)
    ticks_i0 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    await asyncio.sleep(idle_window_s)
    cg_i1 = cgroup_snapshot(CONTAINER)
    ticks_i1 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    idle_cores = (round((cg_i1['usage_usec'] - cg_i0['usage_usec']) / 1e6 / idle_window_s, 3)
                  if cg_i0['usage_usec'] is not None and cg_i1['usage_usec'] is not None else None)
    idle_per_proc = {pid: round(((ticks_i1.get(pid) or 0) - (ticks_i0.get(pid) or 0)) / 100
                                / idle_window_s, 3)
                     for pid in pids if ticks_i0.get(pid) is not None}

    ticks0 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    cg0 = cgroup_snapshot(CONTAINER)

    # Warm each token once so measurement is steady-state, not first-inference.
    try:
        await asyncio.gather(*[one_send(client, tok, blob, f'warm_{i}')
                               for i, tok in enumerate(tokens)])
    except BaseException:
        await cleanup_tokens(client, tokens)   # warm failure must not leak M tokens
        raise

    cg1 = cgroup_snapshot(CONTAINER)
    t0 = time.monotonic()
    results = await asyncio.gather(*[one_send(client, tok, blob, f'm{m}_{i}')
                                     for i, tok in enumerate(tokens)],
                                   return_exceptions=True)
    batch_wall = time.monotonic() - t0
    cg2 = cgroup_snapshot(CONTAINER)
    ticks1 = {pid: proc_cpu_ticks(CONTAINER, pid) for pid in pids}
    await cleanup_tokens(client, tokens)

    errors = [repr(r) for r in results if isinstance(r, Exception)]
    walls = [round(r[0], 1) for r in results if not isinstance(r, Exception)]
    per_proc = {pid: round(((ticks1.get(pid) or 0) - (ticks0.get(pid) or 0)) / 100, 1)
                for pid in pids if ticks0.get(pid) is not None}
    serving = sorted(pid for pid, s in per_proc.items() if s > 5.0)
    return {
        'M': m,
        'project_ids': project_ids,
        'use_wall_s': round(use_wall, 1),
        'idle_cores_after_use': idle_cores,
        'idle_cores_per_process': idle_per_proc,
        'task_processes': len(census),
        'serving_count': len(serving),
        'per_process_cpu_s': per_proc,
        'batch_wall_s': round(batch_wall, 1),
        'per_send_wall_s': walls,
        'errors': errors or None,
        'throughput_videos_per_s': round(m / batch_wall, 4) if batch_wall and not errors else None,
        'cpu_util_of_32': (round((cg2['usage_usec'] - cg1['usage_usec']) / 1e6 / batch_wall / 32, 3)
                           if cg1['usage_usec'] is not None and cg2['usage_usec'] is not None else None),
        'anon_bytes_after_warm': cg1['anon_bytes'],
        'memory_peak_bytes': cg2['memory_peak_bytes'],
    }


async def amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--pipe', default=str(Path(__file__).parent.parent / 'benchmark_video_detect.pipe'))
    ap.add_argument('--sweep', type=int, nargs='+', default=[1, 2, 4, 8, 16])
    ap.add_argument('--image', default='rr:patched-video',
                    help='Crossroad 18: the BAKED image — a fresh container per M with the unbaked image reinstalls 3-4.5GB each')
    ap.add_argument('--threads-env', type=int, default=1,
                    help='the six BLAS/OMP vars on the container (same value the LI arm gets)')
    ap.add_argument('--threads', type=int, default=None,
                    help='use(threads=) per token; default unset (engine default 64)')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_concurrency_out.json'))
    args = ap.parse_args()

    blob = Path(args.video).read_bytes()
    points, knee, hidden_serialization = [], None, False
    for m in args.sweep:
        print(f'== M={m}: fresh container ==', flush=True)
        start_container(args.image, args.threads_env)
        point = await measure_m(m, blob, args.pipe, args.threads)
        points.append(point)
        print(json.dumps({k: point[k] for k in
                          ('M', 'serving_count', 'idle_cores_after_use', 'batch_wall_s',
                           'throughput_videos_per_s', 'cpu_util_of_32')}), flush=True)
        if point['idle_cores_after_use'] is not None and point['idle_cores_after_use'] > m * 0.8 + 1.5:
            print(f'IDLE SPIN SCALES WITH M: {point["idle_cores_after_use"]} cores at idle '
                  f'with M={m} tokens — parity posture structurally suspect; '
                  f'per-process attribution: {point["idle_cores_per_process"]}', flush=True)
        if point['errors'] or point['serving_count'] < m:
            hidden_serialization = point['serving_count'] < m
            print(f'STOP at M={m}: serving={point["serving_count"]} errors={point["errors"]}'
                  f'{" — HIDDEN SERIALIZATION (§4 risk fired): tokens are not independent" if hidden_serialization else ""}',
                  flush=True)
            break
        if len(points) >= 2 and points[-2]['throughput_videos_per_s'] and point['throughput_videos_per_s']:
            marginal = ((point['throughput_videos_per_s'] / points[-2]['throughput_videos_per_s'])
                        / (m / points[-2]['M']))
            point['marginal_efficiency'] = round(marginal, 3)
            if knee is None and marginal < 0.7:
                knee = m
                print(f'KNEE at M={m}: marginal efficiency {marginal:.2f} < 0.7', flush=True)
    sh(['docker', 'rm', '-f', CONTAINER])

    base = points[0]['throughput_videos_per_s'] if points else None
    for p in points:
        if base and p['throughput_videos_per_s']:
            p['efficiency_vs_linear'] = round(p['throughput_videos_per_s'] / (p['M'] * base), 3)
    report = {'sweep': args.sweep, 'threads_env': args.threads_env,
              'use_threads': args.threads, 'points': points,
              'idle_cores_by_M': {p['M']: p.get('idle_cores_after_use') for p in points},
              'knee_M': knee, 'hidden_serialization': hidden_serialization,
              'rule': 'parity posture M sits AT the knee, never past it; '
                      'serving<M anywhere is a finding and blocks the run plan'}
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f'wrote {args.out}')
    return 1 if hidden_serialization else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
