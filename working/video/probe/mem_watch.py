#!/usr/bin/env python3
"""mem_watch — blocker-1/2 memory instrumentation: measured, never assumed,
with the BASIS stated on every number (ruling 2026-08-27; her 62.6 GB
films500 figure is `cgroup memory.current` max and INCLUDES PAGE CACHE —
anon is what OOM-kills, so this tool reports the split, never a blend).

Samples, per tick, per container (one `docker exec` each):
  * /sys/fs/cgroup/memory.current  — RSS+cache, the her-figure basis
  * /sys/fs/cgroup/memory.peak     — kernel true max, where the kernel has it
  * memory.stat anon / file        — the OOM-relevant vs reclaimable split
  * VmHWM of every uvicorn/python process (pgrep in-container)
  * df -B1 of the spool path       — the streaming refactor's disk high-water
Rows land in <out>.jsonl; a summary with per-container maxima and basis
strings lands in <out>.json at stop (duration elapsed or --stop-file seen).

The driver's own peak is NOT sampled here — it self-reports
(driver_memory.ru_maxrss_kb in every leg export, getrusage basis).

Run (box):
  ~/.venv-floor/bin/python3 working/video/probe/mem_watch.py \
      --containers li_video_0,li_video_1 --spool-path /tmp \
      --duration-s 3600 --out ~/films_probe/memwatch_li
Self-test (laptop, no docker): --self-test
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
from argtypes import bounded_float, positive_int   # noqa: E402 — register entry 8

UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
SEP = '=====MEMWATCH====='

BASIS = {
    'memory_current': 'cgroup memory.current — includes page cache (the '
                      'films500 report basis)',
    'memory_peak': 'cgroup memory.peak — kernel true maximum of '
                   'memory.current, where the kernel provides it',
    'anon': 'cgroup memory.stat anon — the OOM-relevant resident set',
    'file': 'cgroup memory.stat file — page cache, reclaimable',
    'vmhwm': 'per-process VmHWM from /proc/<pid>/status inside the '
             'container, summed and maxed over uvicorn/python processes; '
             'polled, so a peak between ticks can be missed',
    'spool_used': 'df -B1 used bytes of the spool path filesystem inside '
                  'the container',
}

_PROBE_SH = (
    "cat /sys/fs/cgroup/memory.current 2>/dev/null; echo {sep}; "
    "cat /sys/fs/cgroup/memory.peak 2>/dev/null; echo {sep}; "
    "grep -E '^(anon|file) ' /sys/fs/cgroup/memory.stat 2>/dev/null; echo {sep}; "
    "for p in $(pgrep -f '[u]vicorn|[p]ython' 2>/dev/null); do "
    "grep VmHWM /proc/$p/status 2>/dev/null; done; echo {sep}; "
    "df -B1 {spool} 2>/dev/null | tail -1"
)


def parse_probe(text: str) -> dict:
    """Parse one container probe output into numbers (None where absent)."""
    parts = text.split(SEP)
    parts += [''] * (5 - len(parts))
    out = {'memory_current': None, 'memory_peak': None, 'anon': None,
           'file': None, 'vmhwm_kb_sum': None, 'vmhwm_kb_max': None,
           'n_procs': 0, 'spool_used_bytes': None, 'spool_avail_bytes': None}
    cur = parts[0].strip()
    if cur.isdigit():
        out['memory_current'] = int(cur)
    peak = parts[1].strip()
    if peak.isdigit():
        out['memory_peak'] = int(peak)
    for line in parts[2].splitlines():
        m = re.match(r'^(anon|file)\s+(\d+)$', line.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    hwms = [int(m.group(1)) for line in parts[3].splitlines()
            for m in [re.search(r'VmHWM:\s*(\d+)\s*kB', line)] if m]
    if hwms:
        out['vmhwm_kb_sum'] = sum(hwms)
        out['vmhwm_kb_max'] = max(hwms)
        out['n_procs'] = len(hwms)
    df = parts[4].split()
    # df -B1 tail -1: Filesystem 1B-blocks Used Available Use% Mounted
    if len(df) >= 4 and df[2].isdigit() and df[3].isdigit():
        out['spool_used_bytes'] = int(df[2])
        out['spool_avail_bytes'] = int(df[3])
    return out


def sample(container: str, spool: str, timeout: int = 20) -> dict:
    sh = _PROBE_SH.format(sep=SEP, spool=spool)
    p = subprocess.run(['docker', 'exec', container, 'sh', '-c', sh],
                       capture_output=True, text=True, timeout=timeout)
    row = parse_probe(p.stdout if p.returncode == 0 else '')
    row['exec_rc'] = p.returncode
    return row


def summarize(rows_by_container: dict) -> dict:
    summary = {'basis': BASIS, 'containers': {}}
    for c, rows in rows_by_container.items():
        def mx(key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return max(vals) if vals else None
        summary['containers'][c] = {
            'n_samples': len(rows),
            'max_memory_current_bytes': mx('memory_current'),
            'max_memory_peak_bytes': mx('memory_peak'),
            'max_anon_bytes': mx('anon'),
            'max_file_bytes': mx('file'),
            'max_vmhwm_kb_sum': mx('vmhwm_kb_sum'),
            'max_vmhwm_kb_single': mx('vmhwm_kb_max'),
            'max_spool_used_bytes': mx('spool_used_bytes'),
            'min_spool_avail_bytes': (min(v for v in
                                          (r.get('spool_avail_bytes') for r in rows)
                                          if v is not None)
                                      if any(r.get('spool_avail_bytes') is not None
                                             for r in rows) else None),
        }
    return summary


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    canned = (f'123456\n{SEP}\n234567\n{SEP}\nanon 111\nfile 222\n{SEP}\n'
              f'VmHWM:     500 kB\nVmHWM:     700 kB\n{SEP}\n'
              '/dev/x 100 40 60 40% /tmp')
    r = parse_probe(canned)
    check('memory.current parsed', r['memory_current'] == 123456)
    check('memory.peak parsed', r['memory_peak'] == 234567)
    check('anon/file parsed', r['anon'] == 111 and r['file'] == 222)
    check('VmHWM sum+max over 2 procs',
          r['vmhwm_kb_sum'] == 1200 and r['vmhwm_kb_max'] == 700 and r['n_procs'] == 2)
    check('df used/avail parsed',
          r['spool_used_bytes'] == 40 and r['spool_avail_bytes'] == 60)
    empty = parse_probe('')
    check('absent kernel fields stay None (never 0)',
          empty['memory_current'] is None and empty['memory_peak'] is None)
    s = summarize({'c': [r, dict(r, memory_current=999999, anon=5)]})
    check('summary takes maxima per key',
          s['containers']['c']['max_memory_current_bytes'] == 999999
          and s['containers']['c']['max_anon_bytes'] == 111)
    check('every summary number has a named basis',
          set(BASIS) >= {'memory_current', 'memory_peak', 'anon', 'file',
                         'vmhwm', 'spool_used'})
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--containers', help='comma-separated container names')
    ap.add_argument('--spool-path', default='/tmp',
                    help='path (inside each container) whose filesystem df is sampled')
    ap.add_argument('--interval-s', type=bounded_float('interval-s', 1.0, 300.0),
                    default=5.0)
    ap.add_argument('--duration-s', type=positive_int('duration-s', 7 * 86400),
                    default=3600)
    ap.add_argument('--stop-file', default=None,
                    help='stop early when this path exists')
    ap.add_argument('--out', default=None,
                    help='output prefix (default: mem_watch_<utc> beside this file)')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.containers:
        ap.error('--containers is required (unless --self-test)')

    containers = [c.strip() for c in args.containers.split(',') if c.strip()]
    for c in containers:
        rc = subprocess.run(['docker', 'inspect', '--format', '{{.Id}}', c],
                            capture_output=True, text=True)
        if rc.returncode != 0:
            raise SystemExit(f'NOT DONE — container {c!r} not inspectable; '
                             'mem_watch never starts containers.')

    prefix = Path(args.out) if args.out else \
        Path(__file__).parent / f'mem_watch_{UTC}'
    jsonl = Path(f'{prefix}.jsonl')
    summary_path = Path(f'{prefix}.json')
    rows_by = {c: [] for c in containers}
    t_end = time.monotonic() + args.duration_s
    n = 0
    print(f'mem_watch: {containers} every {args.interval_s}s for up to '
          f'{args.duration_s}s -> {jsonl}')
    with open(jsonl, 'a') as fh:
        while time.monotonic() < t_end:
            if args.stop_file and Path(args.stop_file).exists():
                print(f'stop-file {args.stop_file} seen — stopping')
                break
            tick = {'t_utc': time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}
            for c in containers:
                try:
                    row = sample(c, args.spool_path)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    row = {'exec_rc': -1, 'error': repr(exc)}
                tick[c] = row
                if 'error' not in row:
                    rows_by[c].append(row)
            fh.write(json.dumps(tick) + '\n')
            fh.flush()
            n += 1
            if n % max(1, int(60 / args.interval_s)) == 0:
                latest = {c: rows_by[c][-1].get('memory_current')
                          for c in containers if rows_by[c]}
                print(f'  tick {n}: memory.current {latest}')
            time.sleep(args.interval_s)
    summary = summarize(rows_by)
    summary['ticks'] = n
    summary['interval_s'] = args.interval_s
    summary_path.write_text(json.dumps(summary, indent=1))
    rb = json.loads(summary_path.read_text())      # entry 22: read back
    print(f'wrote {summary_path}')
    for c, s in rb['containers'].items():
        cur = s['max_memory_current_bytes']
        anon = s['max_anon_bytes']
        print(f'  {c}: max current {cur} B (incl. page cache) | max anon {anon} B '
              f'| max VmHWM sum {s["max_vmhwm_kb_sum"]} kB | '
              f'spool used max {s["max_spool_used_bytes"]} B')
    return 0


if __name__ == '__main__':
    sys.exit(main())
