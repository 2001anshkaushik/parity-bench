#!/usr/bin/env python3
"""probe_idle_spin_docs — SWEEP POINT ZERO for the docs re-run: what does the engine burn idle,
and how does it scale with the number of loaded pipelines (tokens)? (DOCS_HANDOFF.md §6.1;
Ticket 4.)

Not a measured leg. Nothing is sent. The docs posture is reproduced exactly (PHASE1_CARRYOVER
§docker run): `rr:patched`, `--cpuset-cpus 0-23 --memory 58g`, the six BLAS/OMP variables at 1,
`-p 5565:5565`. M tokens are opened on the docs pipeline (product_pdf.pipe, one FRESH
project_id per token so the engine spawns one task subprocess each), NO work is sent, the
container settles, and CPU is sampled as /proc/<pid>/stat deltas for EVERY process in the
container over >= 5 s windows, plus the container cgroup's cpu.stat as the cross-check.
M in {0, 1, 2, 4, 8, 16}.

PRE-REGISTRATION v2 (2026-09-08, Advisor R9/R10) — printed before any sample and written into
the output first. It SUPERSEDES ON THE RECORD the v1 pre-registration carried by
working/results/probe_idle_spin_docs__20260908T090314Z (probe sha 4d5721a9…), which is left
untouched: v1's null control asked M=1 to reproduce the ~1.0 one-token figure and refused a
reading of 1.253 — the control worked; the HYPOTHESIS was malformed (the ~1.0 figure is the
M=0 server floor, and v1's two hypotheses — flat ~1.0 at every M, or ~M cores — were both
wrong). v1's readings: M=0 sum 1.013 (server 1.013), M=1 sum 1.253 (server 1.023, task 0.230).
  model      idle_cores = A + B*M,  A ~ 1.02 (serving process, fixed),  B ~ 0.23 (per task subprocess)
  point      M=16 predicted 4.70; ACCEPT if within [4.2, 5.2]; REFUTED outside
  shape      server_cores stays flat across all M — within +-10% of 1.02 at every M; if the server
             term grows with M the two-term model is wrong even if the sum fits
  linearity  B computed pairwise between adjacent M (delta sum / delta M); roughly constant means
             every pairwise B within [0.115, 0.345] (0.23 +-50%); otherwise the model is wrong
             even if the endpoints fit
  null       M=0 must reproduce 1.013 within [0.85, 1.20] — the control, on the M=0 reading
  out-of-sample  the films campaign held 16 tokens and read ~4.65-4.66 idle cores (different
             corpus, campaign, instrumentation); the model predicts 4.70 there — stated so the
             comparison is fixed before the sweep, not chosen after
  If the null control fails: STOP after M=0, report, never widen a band. If M=16 lands outside
  [4.2, 5.2]: the model is REFUTED and reported as such — no fitting to it.

Every reading is per-process (pid, ppid, threads, rss, cores, argv) — which process holds the
burden matters as much as how much — and the sum, and the cgroup delta. A and B are fitted by
least squares over all points AFTER the rules are applied, with the residual at every point.
Runs ON THE BOX from the video-bench worktree:
  ~/.venv/bin/python working/scripts/probe_idle_spin_docs.py --out <path.json>
It prints its own sha256 first (entry 25). --self-test exercises the arithmetic and the
verdict logic on canned shapes (register 27: producer-built fixtures), no docker.
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
    'version': 2,
    'supersedes': {'artifact': 'working/results/probe_idle_spin_docs__20260908T090314Z',
                   'probe_sha256': '4d5721a94740eaf5d0f5db77f0c64ca0f446b26724200e516b5fe3d12c760fd5',
                   'why': ('v1 asked M=1 to reproduce the ~1.0 one-token figure within [0.85, 1.20] and refused 1.253. '
                           'The control worked; the hypothesis was malformed: ~1.0 is the M=0 server floor (v1 read '
                           '1.013 at M=0), and neither v1 hypothesis (flat ~1.0, or ~M cores) matches v1\'s own two '
                           'points. Superseded on the record, never amended.')},
    'model': 'idle_cores = A + B*M; A ~ 1.02 (serving process, fixed); B ~ 0.23 (per task subprocess)',
    'A_expected': 1.02, 'B_expected': 0.23,
    'point': {'M': 16, 'predicted_cores': 4.70, 'accept_band': [4.2, 5.2], 'outside': 'REFUTED — do not fit to it'},
    'shape': {'rule': 'server_cores within +-10% of 1.02 at every M', 'band': [0.918, 1.122],
              'outside': 'two-term model wrong even if the sum fits'},
    'linearity': {'rule': 'pairwise B = (sum[M2]-sum[M1])/(M2-M1) between adjacent M within [0.115, 0.345] (0.23 +-50%)',
                  'band': [0.115, 0.345], 'outside': 'model wrong even if the endpoints fit'},
    'null_control': {'M': 0, 'expect_cores': 1.013, 'band': [0.85, 1.20],
                     'rule': 'outside the band: the probe measures something else; stop after M=0, never widen a band'},
    'out_of_sample': {'films_16_tokens_idle_cores': [4.65, 4.66], 'model_predicts': 4.70,
                      'note': 'films campaign, different corpus/campaign/instrumentation; fixed here before the sweep'},
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


def fit_ab(points: list[dict]) -> dict:
    """Least squares of sum_cores on M over every point; residual per point."""
    ms = [p['M'] for p in points]; ys = [p['sum_cores'] for p in points]
    n = len(ms); mx = sum(ms) / n; my = sum(ys) / n
    sxx = sum((m - mx) ** 2 for m in ms)
    b = sum((m - mx) * (y - my) for m, y in zip(ms, ys)) / sxx if sxx else float('nan')
    a = my - b * mx
    return {'A': round(a, 3), 'B': round(b, 3),
            'residuals': {p['M']: round(p['sum_cores'] - (a + b * p['M']), 3) for p in points}}


def evaluate(points: list[dict]) -> dict:
    """Apply PREREG v2 mechanically. points: [{'M', 'sum_cores', 'server_cores', 'task_cores'}], M=0 first."""
    by_m = {p['M']: p for p in points}
    out: dict = {'preregistration_version': PREREG['version']}
    if 0 not in by_m:
        return {**out, 'verdict': 'INSUFFICIENT', 'reason': 'no M=0 point'}
    nc = null_control_verdict(by_m[0]['sum_cores'])
    out['null_control'] = nc
    if not nc['PASS']:
        return {**out, 'verdict': 'STOPPED_NULL_CONTROL_FAILED'}
    ms = sorted(by_m)
    lo, hi = PREREG['shape']['band']
    shape = {m: by_m[m]['server_cores'] for m in ms}
    shape_ok = all(lo <= v <= hi for v in shape.values())
    out['shape'] = {'server_cores_by_M': shape, 'band': [lo, hi], 'PASS': shape_ok}
    pw = {}
    for m1, m2 in zip(ms, ms[1:]):
        pw[f'{m1}->{m2}'] = round((by_m[m2]['sum_cores'] - by_m[m1]['sum_cores']) / (m2 - m1), 3)
    blo, bhi = PREREG['linearity']['band']
    lin_ok = bool(pw) and all(blo <= v <= bhi for v in pw.values())
    out['linearity'] = {'pairwise_B': pw, 'band': [blo, bhi], 'PASS': lin_ok}
    pt = PREREG['point']
    if pt['M'] in by_m:
        v = by_m[pt['M']]['sum_cores']; plo, phi = pt['accept_band']
        out['point'] = {'M': pt['M'], 'predicted': pt['predicted_cores'], 'measured': v, 'band': [plo, phi], 'PASS': plo <= v <= phi}
    else:
        out['point'] = {'M': pt['M'], 'PASS': None, 'reason': 'M=16 not measured'}
    out['fit'] = fit_ab(points)
    if pt['M'] in by_m:
        ofs = PREREG['out_of_sample']
        out['out_of_sample'] = {'films_16_tokens': ofs['films_16_tokens_idle_cores'], 'measured_M16': by_m[pt['M']]['sum_cores'],
                                'reproduced': (ofs['films_16_tokens_idle_cores'][0] - 0.25) <= by_m[pt['M']]['sum_cores'] <= (ofs['films_16_tokens_idle_cores'][1] + 0.25),
                                'note': 'reproduced = M=16 within 0.25 core of the films reading; a statement, not a rule'}
    if out['point']['PASS'] is None:
        out['verdict'] = 'INCOMPLETE'
    elif out['point']['PASS'] and shape_ok and lin_ok:
        out['verdict'] = 'MODEL_ACCEPTED'
    else:
        failed = [k for k, ok in (('point', out['point']['PASS']), ('shape', shape_ok), ('linearity', lin_ok)) if not ok]
        out['verdict'] = 'MODEL_REFUTED'; out['failed_rules'] = failed
    return out


def null_control_verdict(m0_sum: float) -> dict:
    lo, hi = PREREG['null_control']['band']
    ok = lo <= m0_sum <= hi
    return {'M0_sum_cores': m0_sum, 'band': [lo, hi], 'expect': PREREG['null_control']['expect_cores'],
            'PASS': ok, 'note': 'reproduces the M=0 reading' if ok else 'does NOT reproduce 1.013 at M=0 — stopped, band not widened'}


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
                if m == 0:
                    nc = null_control_verdict(pt['sum_cores'])
                    out['null_control'] = nc
                    print(json.dumps({'NULL_CONTROL': nc}, indent=1), flush=True)
                    if not nc['PASS']:
                        out['points'] = points; out['verdict'] = 'STOPPED_NULL_CONTROL_FAILED'
                        return 3
            out['points'] = points
            out['evaluation'] = evaluate([{'M': p['M'], 'sum_cores': p['sum_cores'], 'server_cores': p['server_cores'], 'task_cores': p['task_cores']} for p in points])
            out['verdict'] = out['evaluation']['verdict']
            print(json.dumps({'EVALUATION': out['evaluation']}, indent=1), flush=True)
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
        print(json.dumps({'FINAL': {k: out.get(k) for k in ('verdict', 'null_control', 'evaluation')}}, indent=1), flush=True)
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
    chk('null control passes at 1.013 (M=0)', null_control_verdict(1.013)['PASS'] is True)
    chk('null control FAILS at 1.253 (the v1 M=1 reading is not an M=0 reading)', null_control_verdict(1.253)['PASS'] is False)
    chk('null control FAILS at 0.5', null_control_verdict(0.5)['PASS'] is False)
    model = [{'M': m, 'sum_cores': round(1.02 + 0.23 * m, 3), 'server_cores': 1.02, 'task_cores': round(0.23 * m, 3)} for m in (0, 1, 2, 4, 8, 16)]
    ev = evaluate(model)
    chk('evaluate: the model shape -> MODEL_ACCEPTED, A~1.02 B~0.23', ev['verdict'] == 'MODEL_ACCEPTED' and abs(ev['fit']['A'] - 1.02) < 0.01 and abs(ev['fit']['B'] - 0.23) < 0.01)
    chk('evaluate: films out-of-sample reproduced at 4.70', ev['out_of_sample']['reproduced'] is True)
    flat = [{'M': m, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0} for m in (0, 1, 2, 4, 8, 16)]
    chk('evaluate: flat ~1.0 (v1 H_server) -> MODEL_REFUTED on point and linearity', evaluate(flat)['verdict'] == 'MODEL_REFUTED' and set(evaluate(flat)['failed_rules']) == {'point', 'linearity'})
    per_token = [{'M': m, 'sum_cores': 1.0 + 1.0 * m, 'server_cores': 1.0, 'task_cores': 1.0 * m} for m in (0, 1, 2, 4, 8, 16)]
    chk('evaluate: ~M cores (v1 H_token) -> MODEL_REFUTED', evaluate(per_token)['verdict'] == 'MODEL_REFUTED')
    grow = [{'M': m, 'sum_cores': round(1.02 + 0.23 * m, 3), 'server_cores': round(1.02 + 0.23 * m, 3), 'task_cores': 0.0} for m in (0, 1, 2, 4, 8, 16)]
    chk('evaluate: sum fits but the SERVER term grows -> MODEL_REFUTED on shape', evaluate(grow)['verdict'] == 'MODEL_REFUTED' and 'shape' in evaluate(grow)['failed_rules'])
    bent = [{'M': 0, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0}, {'M': 1, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0},
            {'M': 2, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0}, {'M': 4, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0},
            {'M': 8, 'sum_cores': 1.02, 'server_cores': 1.02, 'task_cores': 0.0}, {'M': 16, 'sum_cores': 4.70, 'server_cores': 1.02, 'task_cores': 3.68}]
    chk('evaluate: endpoints fit but B is not constant -> MODEL_REFUTED on linearity', evaluate(bent)['verdict'] == 'MODEL_REFUTED' and 'linearity' in evaluate(bent)['failed_rules'])
    chk('evaluate: null control failure at M=0 -> STOPPED', evaluate([{'M': 0, 'sum_cores': 1.5, 'server_cores': 1.5, 'task_cores': 0.0}])['verdict'] == 'STOPPED_NULL_CONTROL_FAILED')
    chk('evaluate: without M=16 -> INCOMPLETE', evaluate(model[:-1])['verdict'] == 'INCOMPLETE')
    chk('prereg v2 names the superseded artifact and its probe sha', PREREG['supersedes']['artifact'].endswith('090314Z') and PREREG['supersedes']['probe_sha256'].startswith('4d5721a9'))
    chk('prereg v2 point band and null band are the ruled ones', PREREG['point']['accept_band'] == [4.2, 5.2] and PREREG['null_control']['band'] == [0.85, 1.20] and PREREG['null_control']['M'] == 0)
    chk('role: pid 1 is the server', role_of({'pid': 1, 'args': 'x'}) == 'server')
    chk('role: node.py is a task', role_of({'pid': 9, 'args': '/opt/x/python ai/node.py t1'}) == 'task')
    chk('preregistration is written before sampling (module constant, printed first)', PREREG['version'] == 2 and 'model' in PREREG)
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
