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
             'container, matched by reading /proc/*/cmdline directly '
             '(uvicorn|python, the probe shell excluded) — NO procps: the '
             'li image is python:3.12-slim which ships no pgrep (register '
             'entry 10 measured exactly this absence; the 2026-08-27 '
             'mem_watch silently reported nothing because of it). Polled, '
             'so a peak between ticks can be missed',
    'vmhwm_states': "vmhwm_state per tick: 'measured' (N matching processes "
                    "read) / 'zero-matching' (the scan RAN — MATCHED 0 with "
                    "a SCANNED count — and found no uvicorn/python process: "
                    'a recorded observation, NOT an unavailable field) / '
                    "'matched-but-unreadable' (processes matched, status "
                    "unreadable) / 'unavailable' (the probe section itself "
                    'is missing — exec or shell failure). The silent-gap '
                    'class this distinguishes: a null that means "found '
                    'nothing" must never look like "could not look".',
    'spool_used': 'df -B1 used bytes of the spool path filesystem inside '
                  'the container',
}

# sh probe, no procps dependency (see BASIS['vmhwm']); @SEP@/@SPOOL@ are
# replaced, not str.format — the sh needs its own $ and {} untouched.
_PROBE_SH_TEMPLATE = (
    "cat /sys/fs/cgroup/memory.current 2>/dev/null; echo @SEP@; "
    "cat /sys/fs/cgroup/memory.peak 2>/dev/null; echo @SEP@; "
    "grep -E '^(anon|file) ' /sys/fs/cgroup/memory.stat 2>/dev/null; echo @SEP@; "
    "n=0; for d in /proc/[0-9]*; do "
    "[ \"$d\" = \"/proc/$$\" ] && continue; "
    "c=$(tr '\\0' ' ' < \"$d/cmdline\" 2>/dev/null) || continue; "
    "case \"$c\" in *uvicorn*|*python*) n=$((n+1)); "
    "grep VmHWM \"$d/status\" 2>/dev/null || echo 'VmHWM: UNREADABLE';; esac; "
    "done; echo MATCHED $n; echo SCANNED $(ls -d /proc/[0-9]* 2>/dev/null | wc -l); "
    "echo @SEP@; "
    "df -B1 @SPOOL@ 2>/dev/null | tail -1"
)


def parse_probe(text: str) -> dict:
    """Parse one container probe output. Absent kernel fields stay None; the
    VmHWM section carries an explicit vmhwm_state so "found nothing" can
    never be mistaken for "could not look" (the silent-gap class)."""
    parts = text.split(SEP)
    parts += [''] * (5 - len(parts))
    out = {'memory_current': None, 'memory_peak': None, 'anon': None,
           'file': None, 'vmhwm_kb_sum': None, 'vmhwm_kb_max': None,
           'n_procs': None, 'procs_scanned': None, 'vmhwm_unreadable': 0,
           'vmhwm_state': 'unavailable',
           'spool_used_bytes': None, 'spool_avail_bytes': None}
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
    sect = parts[3]
    matched = re.search(r'^MATCHED (\d+)\s*$', sect, re.M)
    scanned = re.search(r'^SCANNED (\d+)\s*$', sect, re.M)
    hwms = [int(m.group(1)) for line in sect.splitlines()
            for m in [re.search(r'VmHWM:\s*(\d+)\s*kB', line)] if m]
    out['vmhwm_unreadable'] = sum(1 for line in sect.splitlines()
                                  if line.strip() == 'VmHWM: UNREADABLE')
    if matched:
        out['n_procs'] = int(matched.group(1))
        out['procs_scanned'] = int(scanned.group(1)) if scanned else None
        if out['n_procs'] == 0:
            out['vmhwm_state'] = 'zero-matching'   # the scan ran; nothing matched
        elif hwms:
            out['vmhwm_state'] = 'measured'
            out['vmhwm_kb_sum'] = sum(hwms)
            out['vmhwm_kb_max'] = max(hwms)
        else:
            out['vmhwm_state'] = 'matched-but-unreadable'
    # else: the section never ran -> 'unavailable' (exec/shell failure)
    df = parts[4].split()
    # df -B1 tail -1: Filesystem 1B-blocks Used Available Use% Mounted
    if len(df) >= 4 and df[2].isdigit() and df[3].isdigit():
        out['spool_used_bytes'] = int(df[2])
        out['spool_avail_bytes'] = int(df[3])
    return out


def sample(container: str, spool: str, timeout: int = 20) -> dict:
    sh = _PROBE_SH_TEMPLATE.replace('@SEP@', SEP).replace('@SPOOL@', spool)
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
        states = [r.get('vmhwm_state') for r in rows]
        summary['containers'][c] = {
            'n_samples': len(rows),
            'max_memory_current_bytes': mx('memory_current'),
            'max_memory_peak_bytes': mx('memory_peak'),
            'max_anon_bytes': mx('anon'),
            'max_file_bytes': mx('file'),
            'max_vmhwm_kb_sum': mx('vmhwm_kb_sum'),
            'max_vmhwm_kb_single': mx('vmhwm_kb_max'),
            'vmhwm_states_seen': sorted({s for s in states if s}),
            'n_ticks_vmhwm_measured': states.count('measured'),
            'n_ticks_vmhwm_zero_matching': states.count('zero-matching'),
            'n_ticks_vmhwm_unavailable': states.count('unavailable'),
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
              f'VmHWM:     500 kB\nVmHWM:     700 kB\nMATCHED 2\nSCANNED 57\n{SEP}\n'
              '/dev/x 100 40 60 40% /tmp')
    r = parse_probe(canned)
    check('memory.current parsed', r['memory_current'] == 123456)
    check('memory.peak parsed', r['memory_peak'] == 234567)
    check('anon/file parsed', r['anon'] == 111 and r['file'] == 222)
    check("VmHWM measured: sum+max over 2 procs, 57 scanned, state 'measured'",
          r['vmhwm_kb_sum'] == 1200 and r['vmhwm_kb_max'] == 700
          and r['n_procs'] == 2 and r['procs_scanned'] == 57
          and r['vmhwm_state'] == 'measured')
    check('df used/avail parsed',
          r['spool_used_bytes'] == 40 and r['spool_avail_bytes'] == 60)

    # THE SILENT-GAP DISCRIMINATOR (the 2026-08-27 defect: pgrep absent from
    # the slim image, every tick reported nothing, nothing said so).
    zero = parse_probe(f'1\n{SEP}\n2\n{SEP}\n{SEP}\nMATCHED 0\nSCANNED 41\n{SEP}\n')
    check("zero-matching is an EXPLICIT state: n_procs==0, scanned recorded",
          zero['n_procs'] == 0 and zero['procs_scanned'] == 41
          and zero['vmhwm_state'] == 'zero-matching')
    empty = parse_probe('')
    check("...and is DISTINGUISHABLE from 'unavailable' (section never ran)",
          empty['vmhwm_state'] == 'unavailable' and empty['n_procs'] is None
          and zero['vmhwm_state'] != empty['vmhwm_state'])
    check('absent kernel fields stay None (never 0)',
          empty['memory_current'] is None and empty['memory_peak'] is None)
    unread = parse_probe(f'1\n{SEP}\n2\n{SEP}\n{SEP}\n'
                         f'VmHWM: UNREADABLE\nMATCHED 1\nSCANNED 9\n{SEP}\n')
    check("matched-but-unreadable is its own state (1 matched, 0 readable)",
          unread['vmhwm_state'] == 'matched-but-unreadable'
          and unread['n_procs'] == 1 and unread['vmhwm_unreadable'] == 1)

    s = summarize({'c': [r, dict(r, memory_current=999999, anon=5), zero]})
    check('summary takes maxima per key',
          s['containers']['c']['max_memory_current_bytes'] == 999999
          and s['containers']['c']['max_anon_bytes'] == 111)
    check('summary surfaces the state mix (2 measured, 1 zero-matching tick)',
          s['containers']['c']['n_ticks_vmhwm_measured'] == 2
          and s['containers']['c']['n_ticks_vmhwm_zero_matching'] == 1
          and s['containers']['c']['vmhwm_states_seen'] == ['measured', 'zero-matching'])
    check('every summary number has a named basis (incl. the state vocabulary)',
          set(BASIS) >= {'memory_current', 'memory_peak', 'anon', 'file',
                         'vmhwm', 'vmhwm_states', 'spool_used'})
    check('probe shell no longer depends on procps (reads /proc/*/cmdline)',
          'pgrep' not in _PROBE_SH_TEMPLATE and '/proc/[0-9]*' in _PROBE_SH_TEMPLATE)

    # ENTRY 27 (2026-08-30 sweep kill — a missing `import re` passed
    # py_compile AND a green self-test): every probe self-test scans the
    # video tree for unresolvable names. Lazy import: live paths untouched.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # working/
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)
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
