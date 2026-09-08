#!/usr/bin/env python3
"""probe_idle_spin_docs — SWEEP POINT ZERO for the docs re-run: is the engine's idle spin
per-SERVER or per-TOKEN? (DOCS_HANDOFF.md §6.1; Ticket 4 left it open for the docs posture.)

Not a measured leg. Nothing is sent. The docs posture is reproduced exactly (PHASE1_CARRYOVER
§docker run): `rr:patched`, `--cpuset-cpus 0-23 --memory 58g`, the six BLAS/OMP variables at 1,
`-p 5565:5565`. M tokens are opened on the docs pipeline (product_pdf.pipe, one FRESH
project_id per token so the engine spawns one task subprocess each), NO work is sent, the
container settles, and CPU is sampled as /proc/<pid>/stat deltas for EVERY process in the
container over >= 5 s windows, plus the container cgroup's cpu.stat as the cross-check. M in
{0, 1, 2, 4, 8, 16}: M=0 is the server floor, M=1 the null control.

PRE-REGISTERED (printed before any sample is taken, and written into the output first):
  H_server : idle cores ~ 1.0 at every M — the spin lives in the serving process.
  H_token  : idle cores ~ M — every task subprocess spins; at M=16 half the box burns before a
             document is read, and the quiet-box preflight cannot exclude a floor that scales.
  NULL CONTROL: M=1 must reproduce ~1.004 cores (the one-token reading in §6.1) — band
  [0.85, 1.20]. Outside the band the probe is measuring something else; it STOPS after M=1 and
  the sweep is not run, per the ruling.
  PRIOR (not a prediction, context only): Ticket 4 measured 0.99 + 0.26*M cores at threads=8
  on the video pipe — neither hypothesis cleanly.

Every reading is per-process (pid, ppid, threads, rss, cores, argv) — which process holds the
spin matters as much as how much — and the sum, and the cgroup delta. Runs ON THE BOX from the
video-bench worktree (the helpers live in working/video/probe):
  ~/.venv/bin/python working/scripts/probe_idle_spin_docs.py --out <path.json>
It prints its own sha256 first (entry 25). --self-test exercises the arithmetic and the
verdict logic on canned /proc/stat shapes (register 27: producer-built fixtures), no docker.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / 'working' / 'video' / 'probe'))
sys.path.insert(0, str(ROOT / 'working' / 'video'))

CONTAINER = 'rr_idleprobe'
IMAGE = 'rr:patched'
CPUSET = '0-23'
PIPE = ROOT / 'working' / 'pipes' / 'product_pdf.pipe'
THREAD_ENV_KEYS = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                   'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS')
CLK_TCK = 100  # Linux USER_HZ on x86_64; read back from getconf on the box and recorded

PREREG = {
    'H_server': 'idle cores ~ 1.0 at every M (the spin lives in the serving process)',
    'H_token': 'idle cores ~ M (every task subprocess spins)',
    'null_control': {'M': 1, 'expect_cores': 1.004, 'band': [0.85, 1.20],
                     'rule': 'outside the band: the probe measures something else; stop after M=1, do not run the sweep'},
    'prior_not_prediction': 'Ticket 4 (video pipe, threads=8): 0.99 + 0.26*M cores',
    'decision_rule': ('per-server if max over M of (sum_cores - sum_cores[M=0]) < 0.5 and per-process shows the '
                      'spin in the serving process; per-token if sum_cores grows by >= 0.5 per added token on '
                      'average and per-process shows it in the task subprocesses; otherwise MIXED — report the slope'),
}


def sha256_self() -> str:
    return hashlib.sha256(HERE.read_bytes()).hexdigest()


def sh(cmd: list[str], timeout: int = 600) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout if r.returncode == 0 else f'<failed rc={r.returncode}: {r.stderr.strip()[:200]}>'


# ---------------------------------------------------------------- measurement (pure)
def parse_stat_ticks(stat_line: str):
    """utime+stime from a /proc/<pid>/stat line (fields after the ')' of comm)."""
    try:
        f = stat_line.rsplit(')', 1)[1].split()
        return int(f[11]) + int(f[12])
    except Exception:
        return None


def cores_from_ticks(t0: int, t1: int, elapsed_s: float, clk_tck: int = CLK_TCK) -> float:
    return round((t1 - t0) / clk_tck / elapsed_s, 3)


def classify(points: list[dict]) -> dict:
    """points: [{'M': m, 'sum_cores': x, 'server_cores': s, 'task_cores': t}] with M=0 first.
    Applies PREREG['decision_rule'] mechanically."""
    by_m = {p['M']: p for p in points}
    if 0 not in by_m or len(points) < 2:
        return {'verdict': 'INSUFFICIENT', 'reason': 'need M=0 and at least one M>0 point'}
    base = by_m[0]['sum_cores']
    growth = {m: round(p['sum_cores'] - base, 3) for m, p in by_m.items() if m > 0}
    max_growth = max(growth.values())
    mmax = max(growth)
    slope = round(growth[mmax] / mmax, 3) if mmax else 0.0
    task_share_at_max = (by_m[mmax]['task_cores'] / by_m[mmax]['sum_cores']) if by_m[mmax]['sum_cores'] else 0.0
    if max_growth < 0.5 and task_share_at_max < 0.5:
        verdict = 'PER_SERVER'
    elif slope >= 0.5 and task_share_at_max >= 0.5:
        verdict = 'PER_TOKEN'
    else:
        verdict = 'MIXED'
    return {'verdict': verdict, 'server_floor_M0': base, 'growth_over_M0': growth,
            'slope_cores_per_token_to_Mmax': slope, 'task_share_at_Mmax': round(task_share_at_max, 3),
            'rule': PREREG['decision_rule']}


def null_control_verdict(m1_sum: float) -> dict:
    lo, hi = PREREG['null_control']['band']
    ok = lo <= m1_sum <= hi
    return {'M1_sum_cores': m1_sum, 'band': [lo, hi], 'expect': PREREG['null_control']['expect_cores'],
            'PASS': ok, 'note': 'reproduces the one-token reading' if ok else 'does NOT reproduce ~1.004 — sweep not interpretable, stopped'}


# ---------------------------------------------------------------- container plumbing
def census(container: str) -> list[dict]:
    raw = sh(['docker', 'exec', container, 'ps', '-eo', 'pid,ppid,nlwp,rss,args'])
    out = []
    for line in raw.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, ppid, nlwp, rss, args = parts
        try:
            out.append({'pid': int(pid), 'ppid': int(ppid), 'threads': int(nlwp), 'rss_kb': int(rss), 'args': args[:160]})
        except ValueError:
            continue
    return out


def ticks(container: str, pid: int):
    return parse_stat_ticks(sh(['docker', 'exec', container, 'cat', f'/proc/{pid}/stat']))


def cgroup_usage_usec(container: str):
    raw = sh(['docker', 'exec', container, 'cat', '/sys/fs/cgroup/cpu.stat'])
    try:
        return int([l for l in raw.splitlines() if l.startswith('usage_usec')][0].split()[1])
    except Exception:
        return None


def role_of(p: dict) -> str:
    a = p['args']
    if p['pid'] == 1 or 'eaas.py' in a:
        return 'server'
    if 'node.py' in a or 'task' in a.lower():
        return 'task'
    if 'java' in a or 'tika' in a.lower():
        return 'java'
    if a.startswith('ps ') or a.startswith('cat '):
        return 'probe-exec'
    return 'other'


def sample_window(container: str, window_s: float, clk_tck: int) -> dict:
    procs = census(container)
    procs = [p for p in procs if role_of(p) != 'probe-exec']
    t0 = {p['pid']: ticks(container, p['pid']) for p in procs}
    cg0 = cgroup_usage_usec(container)
    w0 = time.monotonic()
    time.sleep(window_s)
    elapsed = time.monotonic() - w0
    t1 = {p['pid']: ticks(container, p['pid']) for p in procs}
    cg1 = cgroup_usage_usec(container)
    per = []
    for p in procs:
        a, b = t0.get(p['pid']), t1.get(p['pid'])
        c = cores_from_ticks(a, b, elapsed, clk_tck) if a is not None and b is not None else None
        per.append({**p, 'role': role_of(p), 'cores': c})
    valid = [p['cores'] for p in per if p['cores'] is not None]
    by_role = {}
    for p in per:
        if p['cores'] is not None:
            by_role[p['role']] = round(by_role.get(p['role'], 0.0) + p['cores'], 3)
    return {'window_s': round(elapsed, 2), 'n_processes': len(per), 'per_process': per,
            'sum_cores': round(sum(valid), 3), 'by_role': by_role,
            'cgroup_cores': (round((cg1 - cg0) / 1e6 / elapsed, 3) if cg0 is not None and cg1 is not None else None)}


def container_up(image: str, cpuset: str) -> dict:
    existing = sh(['docker', 'ps', '-a', '--filter', f'name=^{CONTAINER}$', '--format', '{{.Names}}']).strip()
    if existing:
        raise SystemExit(f'NOT DONE — a container named {CONTAINER} already exists; it must be removed by a human decision, not by this probe')
    env = []
    for k in THREAD_ENV_KEYS:
        env += ['-e', f'{k}=1']
    r = subprocess.run(['docker', 'run', '-d', '--name', CONTAINER, '--cpuset-cpus', cpuset, '--memory', '58g',
                        *env, '-p', '5565:5565', image], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'docker run failed: {r.stderr.strip()[:300]}')
    inspect = json.loads(sh(['docker', 'inspect', CONTAINER]))[0]
    return {'container_id': inspect['Id'], 'image_id': inspect['Image'],
            'cpuset_readback': inspect['HostConfig'].get('CpusetCpus'),
            'nano_cpus_readback': inspect['HostConfig'].get('NanoCpus'),
            'memory_readback': inspect['HostConfig'].get('Memory'),
            'env_readback': [e for e in inspect['Config'].get('Env', []) if e.split('=')[0] in THREAD_ENV_KEYS],
            'image_labels': json.loads(sh(['docker', 'image', 'inspect', image, '--format', '{{json .Config.Labels}}']) or '{}')}


def container_down():
    print(sh(['docker', 'stop', '-t', '20', CONTAINER]).strip())
    print(sh(['docker', 'rm', CONTAINER]).strip())


async def open_tokens(client, n_new: int, tag: str, ttl: int = 3600) -> list[str]:
    import uuid
    toks = []
    gen = ROOT / 'working' / 'pipes' / 'generated'
    gen.mkdir(parents=True, exist_ok=True)
    for i in range(n_new):
        base = json.loads(PIPE.read_text())
        base['project_id'] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f'idlespin-{tag}-{i}-{os.getpid()}-{time.time_ns()}'))
        gp = gen / f'idlespin_{tag}_{i}.pipe'
        gp.write_text(json.dumps(base))
        r = await client.use(filepath=str(gp.relative_to(ROOT)), ttl=ttl)
        toks.append(r['token'])
    return toks


async def amain(args) -> int:
    out: dict = {'probe': HERE.name, 'probe_sha256': sha256_self(), 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                 'preregistered': PREREG, 'posture': {'image': args.image, 'cpuset': args.cpuset, 'thread_env': {k: '1' for k in THREAD_ENV_KEYS},
                                                       'pipe': str(PIPE.relative_to(ROOT)), 'work_sent': False,
                                                       'settle_s': args.settle, 'window_s': args.window, 'sweep': args.sweep}}
    print(json.dumps({'PREREGISTERED_BEFORE_ANY_SAMPLE': PREREG, 'probe_sha256': out['probe_sha256']}, indent=1), flush=True)
    clk = sh(['getconf', 'CLK_TCK']).strip()
    clk_tck = int(clk) if clk.isdigit() else CLK_TCK
    out['clk_tck'] = clk_tck
    load1 = float(Path('/proc/loadavg').read_text().split()[0]) if Path('/proc/loadavg').exists() else None
    out['host_load1_before'] = load1
    if load1 is not None and load1 > args.max_load1:
        out['verdict'] = 'NOT RUN'; out['reason'] = f'host load1 {load1} > {args.max_load1}: not a quiet box'
        print(json.dumps(out, indent=1)); return 2
    out['container'] = container_up(args.image, args.cpuset)
    print(json.dumps({'container': out['container']}, indent=1), flush=True)
    try:
        from wait_ready import wait_rr_ready
        out['ready'] = await wait_rr_ready(port=5565, deadline_s=900, container=CONTAINER)
        os.environ['ROCKETRIDE_URI'] = 'http://127.0.0.1:5565'
        os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
        from rocketride import RocketRideClient
        client = RocketRideClient()
        await client.connect(timeout=60000)
        tokens: list[str] = []
        points = []
        try:
            for m in [0] + list(args.sweep):
                need = m - len(tokens)
                if need > 0:
                    t0 = time.monotonic()
                    tokens += await open_tokens(client, need, f'm{m}')
                    use_wall = round(time.monotonic() - t0, 1)
                else:
                    use_wall = 0.0
                print(f'M={m}: {len(tokens)} token(s) open (use() wall {use_wall}s); settling {args.settle}s', flush=True)
                time.sleep(args.settle)
                w1 = sample_window(CONTAINER, args.window, clk_tck)
                w2 = sample_window(CONTAINER, args.window, clk_tck)
                pt = {'M': m, 'tokens_open': len(tokens), 'use_wall_s': use_wall, 'windows': [w1, w2],
                      'sum_cores': w2['sum_cores'], 'cgroup_cores': w2['cgroup_cores'],
                      'server_cores': w2['by_role'].get('server', 0.0), 'task_cores': w2['by_role'].get('task', 0.0),
                      'java_cores': w2['by_role'].get('java', 0.0), 'other_cores': w2['by_role'].get('other', 0.0)}
                points.append(pt)
                print(json.dumps({'POINT': {k: v for k, v in pt.items() if k != 'windows'},
                                  'per_process_window2': [{k: p[k] for k in ('pid', 'ppid', 'role', 'threads', 'rss_kb', 'cores')} | {'args': p['args'][:70]} for p in w2['per_process']]}, indent=1), flush=True)
                if m == 1:
                    nc = null_control_verdict(pt['sum_cores'])
                    out['null_control'] = nc
                    print(json.dumps({'NULL_CONTROL': nc}, indent=1), flush=True)
                    if not nc['PASS']:
                        out['points'] = points; out['verdict'] = 'STOPPED_NULL_CONTROL_FAILED'
                        return 3
            out['points'] = points
            out['classification'] = classify([{'M': p['M'], 'sum_cores': p['sum_cores'], 'server_cores': p['server_cores'], 'task_cores': p['task_cores']} for p in points])
            out['verdict'] = out['classification']['verdict']
            print(json.dumps({'CLASSIFICATION': out['classification']}, indent=1), flush=True)
            return 0
        finally:
            for tok in tokens:
                try:
                    await asyncio.wait_for(client.terminate(tok), timeout=60)
                except Exception as exc:  # noqa: BLE001
                    print(f'terminate {str(tok)[:14]}: {exc!r} (recorded)')
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
    finally:
        if args.out:
            Path(args.out).write_text(json.dumps(out, indent=1))
            print(f'wrote {args.out}')
        print(json.dumps({'FINAL': {k: out.get(k) for k in ('verdict', 'null_control', 'classification')}}, indent=1), flush=True)
        if not args.keep:
            container_down()


def self_test() -> int:
    ok = 0; bad = 0
    def chk(name, cond):
        nonlocal ok, bad
        print(f'  {"PASS" if cond else "FAIL"}  {name}'); ok += cond; bad += (not cond)
    # producer-built fixture: a real /proc/<pid>/stat shape
    line = '4242 (python3) S 1 4242 4242 0 -1 4194560 100 0 0 0 150 50 0 0 20 0 5 0 1000 123456 789 18446744073709551615 0 0 0 0 0 0 0 0 0 0 0 0 17 3 0 0 0 0 0'
    chk('parse utime+stime from a stat line', parse_stat_ticks(line) == 200)
    chk('comm with spaces/parentheses does not break the parse', parse_stat_ticks('7 (engine (x) y) R 1 ' + line.split(') S 1 ', 1)[1]) == 200)
    chk('unparseable stat -> None', parse_stat_ticks('<failed rc=1>') is None)
    chk('cores arithmetic: 600 ticks over 6 s at 100 Hz = 1.0 core', cores_from_ticks(1000, 1600, 6.0, 100) == 1.0)
    chk('null control passes at 1.004', null_control_verdict(1.004)['PASS'] is True)
    chk('null control passes at 1.18 (inside band)', null_control_verdict(1.18)['PASS'] is True)
    chk('null control FAILS at 1.3', null_control_verdict(1.3)['PASS'] is False)
    chk('null control FAILS at 0.5', null_control_verdict(0.5)['PASS'] is False)
    server = [{'M': m, 'sum_cores': 1.0 + 0.02 * m, 'server_cores': 1.0, 'task_cores': 0.02 * m} for m in (0, 1, 2, 4, 8, 16)]
    chk('classify: flat ~1.0 with the spin in the server -> PER_SERVER', classify(server)['verdict'] == 'PER_SERVER')
    token = [{'M': m, 'sum_cores': 1.0 + 1.0 * m, 'server_cores': 1.0, 'task_cores': 1.0 * m} for m in (0, 1, 2, 4, 8, 16)]
    chk('classify: +1 core per token in the tasks -> PER_TOKEN', classify(token)['verdict'] == 'PER_TOKEN')
    mixed = [{'M': m, 'sum_cores': 0.99 + 0.26 * m, 'server_cores': 0.99, 'task_cores': 0.26 * m} for m in (0, 1, 2, 4, 8, 16)]
    chk('classify: Ticket-4 shape (0.99 + 0.26*M) -> MIXED, slope reported', classify(mixed)['verdict'] == 'MIXED' and abs(classify(mixed)['slope_cores_per_token_to_Mmax'] - 0.26) < 0.01)
    chk('classify: without M=0 -> INSUFFICIENT', classify(token[1:])['verdict'] == 'INSUFFICIENT')
    chk('role: pid 1 is the server', role_of({'pid': 1, 'args': 'x'}) == 'server')
    chk('role: node.py is a task', role_of({'pid': 9, 'args': '/opt/x/python ai/node.py t1'}) == 'task')
    chk('preregistration is written before sampling (it is a module constant, printed first)', 'H_server' in PREREG and 'H_token' in PREREG and PREREG['null_control']['band'] == [0.85, 1.20])
    chk('sha256 of self is printed', len(sha256_self()) == 64)
    print(f'self-test: {ok} pass, {bad} fail')
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--cpuset', default=CPUSET)
    ap.add_argument('--sweep', type=int, nargs='+', default=[1, 2, 4, 8, 16])
    ap.add_argument('--settle', type=float, default=25.0, help='seconds after the last use() before sampling')
    ap.add_argument('--window', type=float, default=6.0, help='sample window seconds (>= 5)')
    ap.add_argument('--max-load1', type=float, default=2.0)
    ap.add_argument('--out', default=None)
    ap.add_argument('--keep', action='store_true', help='leave the container running (default: stop and rm)')
    a = ap.parse_args()
    print(f'probe_idle_spin_docs sha256: {sha256_self()}', flush=True)
    if a.self_test:
        return self_test()
    if a.window < 5:
        raise SystemExit('window must be >= 5 s')
    if not PIPE.exists():
        raise SystemExit(f'NOT DONE — {PIPE} missing')
    return asyncio.run(amain(a))


if __name__ == '__main__':
    sys.exit(main())
