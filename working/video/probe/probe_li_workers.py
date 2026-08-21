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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_rr import cgroup_snapshot, proc_cpu_ticks  # noqa: E402
from wait_ready import assert_host_network, wait_li_ready  # noqa: E402
from argtypes import positive_int  # noqa: E402 — register entry 8

CONTAINER = 'liconc'
PORT = 8802
MEM_LIMIT_BYTES = 58 * (1 << 30)   # the --memory value below; ONE constant, both uses


def sh(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def worker_census(container: str) -> list[dict]:
    """ALL container processes via /proc directly (python:3.12-slim ships no
    procps — `docker exec ps` returned empty and read as zero serving,
    2026-08-21). NO SERVING PREDICATE LIVES HERE ANY MORE. The argv pattern
    was wrong twice in two shapes the same day: 'uvicorn' matches only the
    non-serving master at W>=2, and the replacement pinned against the W=2
    tree ('spawn_main' children of pid 1) was wrong at W=1, where the
    response pid IS 1 — one configuration's measurement is not a predicate
    for all configurations (register entry 10 addendum). Serving is now
    defined by MEASURED BEHAVIOR in measure_w: processes that burned CPU
    during the batch, anchored by the ground truth that every RESPONSE pid
    must appear among the burners. argv is recorded per process as
    attribution text only, never as a predicate."""
    raw = sh(['docker', 'exec', container, 'sh', '-c',
              'for d in /proc/[0-9]*; do s=$(cat "$d/stat" 2>/dev/null) || continue; '
              'c=$(tr "\\0" " " < "$d/cmdline" 2>/dev/null); '
              'printf "%s\\t%s\\n" "$s" "$c"; done']).stdout
    all_procs = []
    for line in raw.splitlines():
        stat_part, _, cmd = line.partition('\t')
        head, sep, tail = stat_part.rpartition(')')
        if not sep:
            continue
        try:
            pid = int(stat_part.split(' ', 1)[0])
            f = tail.split()          # fields from `state` onward
            ppid = int(f[1])
            rss_kb = int(f[21]) * 4   # rss pages -> KiB at 4096-byte pages
        except (ValueError, IndexError):
            continue
        all_procs.append({'pid': pid, 'ppid': ppid, 'rss_kb': rss_kb,
                          'args': cmd.strip()[:200]})
    return all_procs


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
    r = sh(['docker', 'run', '-d', '--name', CONTAINER,
            '--memory', f'{MEM_LIMIT_BYTES >> 30}g',
            *env_args, '-e', f'WS1V_WORKERS={workers}',
            '--network', 'host', image])
    if r.returncode != 0:
        raise SystemExit(f'docker run failed: {r.stderr}')
    net = assert_host_network(CONTAINER)
    # Warm deadline scales with W (2026-08-21, never-run instrument hardening):
    # the arithmetic says W=16 cold warms in ~2-4 min (concurrent CPU-bound
    # model loads; disk reads share the page cache at a measured 558 MB/s
    # cold), so 900 s should hold — but the payoff is asymmetric: a generous
    # deadline costs nothing when healthy (returns at warm), a short one
    # aborts the sweep's last point after the investment. NOTE: if W nears
    # the 58g ceiling no deadline saves it — read memory_peak at W=8 before
    # waiting on W=16.
    ready = wait_li_ready(port=PORT, deadline_s=max(900.0, 150.0 * workers),
                          workers=workers, container=CONTAINER)
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
    all_procs = worker_census(CONTAINER)
    pids = [p['pid'] for p in all_procs]   # sample EVERYTHING; behavior decides

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
    # SERVING = MEASURED BEHAVIOR, anchored by ground truth (2026-08-21,
    # inversion ruling): serving processes are the CPU BURNERS during the
    # batch — no argv predicate — and every RESPONSE pid must appear among
    # them. The membership check is deliberately against the BURNER set, not
    # the all-procs set (which would be trivially true): a responder that the
    # attribution cannot see burning is an instrument failure — threshold or
    # tick sampling — and must never present as a serving result.
    resp_pids = {r['pid'] for r in ok if r.get('pid') is not None}
    blind = sorted(resp_pids - set(serving_cpu))
    return {
        'W': w,
        'declared_workers': w,
        'n_container_procs': len(all_procs),
        'response_pids': sorted(resp_pids),
        'cpu_burner_pids': serving_cpu,
        'census_blind_pids': blind or None,
        'census_all_procs': all_procs,
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
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--video', required=True)
    ap.add_argument('--sweep', type=positive_int('sweep', 256), nargs='+',
                    default=[1, 2, 4, 8, 16])
    ap.add_argument('--image', default='li:video')
    ap.add_argument('--threads-env', type=positive_int('threads-env', 256), default=1,
                    help='the six vars on the LI container for this sweep (its own matrix)')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'probe_li_workers_out.json'))
    ap.add_argument('--allow-memory-overshoot', action='store_true',
                    help='override the memory-ascent stop; the override is recorded')
    args = ap.parse_args()

    blob = Path(args.video).read_bytes()
    points, knee, census_blind, mem_stop = [], None, False, None
    for w in args.sweep:
        # MEMORY ASCENT GUARD (2026-08-21): W=1 peaked at 2.34 GB -> W=16
        # projects ~37 GB against the 58 GiB limit — survivable but tight,
        # and an OOM at the top of the ascent kills a worker mid-batch and
        # hangs the point to its deadline. A human watching numbers scroll is
        # not a check (register entries 9/10). Linear projection from the
        # LAST MEASURED point; an estimate from measured inputs (entry 5),
        # so it REFUSES loudly rather than deciding — override is recorded.
        if points and not args.allow_memory_overshoot:
            last = points[-1]
            peak = last.get('memory_peak_bytes') or 0
            projected = peak * (w / last['W'])
            if projected > 0.9 * MEM_LIMIT_BYTES:
                mem_stop = {'before_W': w, 'measured_W': last['W'],
                            'measured_peak_bytes': peak,
                            'projected_bytes': int(projected),
                            'limit_bytes': MEM_LIMIT_BYTES}
                print(f'MEMORY ASCENT STOP before W={w}: peak at W={last["W"]} = '
                      f'{peak / 2**30:.1f} GiB; linear projection for W={w} = '
                      f'{projected / 2**30:.1f} GiB > 0.9 x {MEM_LIMIT_BYTES >> 30} GiB '
                      f'container limit. Override with --allow-memory-overshoot '
                      f'(recorded).', flush=True)
                break
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
        if point.get('census_blind_pids'):
            print(f'ATTRIBUTION BLIND at W={w}: response pid(s) '
                  f'{point["census_blind_pids"]} answered but do not appear among the '
                  f'CPU burners {point["cpu_burner_pids"]} — the per-process '
                  f'attribution (threshold or tick sampling) cannot see a process that '
                  f'demonstrably served. Full /proc tree + per-process CPU recorded in '
                  f'the point. Instrument failure, NOT a serving result.', flush=True)
            census_blind = True
            break
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
              'memory_ascent_stop': mem_stop,
              'memory_overshoot_override': args.allow_memory_overshoot or None,
              'rule': 'LI_WORKERS sits AT the knee, never past it — measured the same way '
                      'M_TOKENS is (no handicaps, no derived values)'}
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f'wrote {args.out}')
    return 2 if census_blind else 0   # 2 = instrument blindness, distinct from findings


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
