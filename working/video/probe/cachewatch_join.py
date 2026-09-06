#!/usr/bin/env python3
"""cachewatch_join — join the once-a-minute /proc/meminfo sampler Ansh runs
beside the lifetimes run (~/logs/cachewatch.log: Cached, MemFree, Dirty,
Writeback, iowait) against each leg's boundaries and per-film walls, for the
THIRD pre-registered mechanism (page cache; FACT 2, 2026-09-06).

CLOCKS — the whole join is one anchor per leg:
  * records carry CLOCK_MONOTONIC ns (enqueue_ns / admit_ns / done_ns);
  * the cachewatch log carries wall-clock UTC (the box clock);
  * the leg's fsstream_<stem>.jsonl row 0 carries BOTH: utc (time.gmtime on
    the same box clock) and t (seconds since the sampler started). The sampler
    starts after the leg_start reading and before the CPU bracket and the first
    enqueue, so  anchor_utc = utc(row0) - t(row0)  is the leg start within ~1 s.
  * utc(x_ns) = anchor_utc + (x_ns - min(enqueue_ns)) / 1e9 ;
    leg_end_utc = anchor_utc + export.leg_wall_s ;
    collector rows: utc = mtime(collector_<stem>.ready) + t.
  The 60 s cadence of the sampler dominates the join error.

LOG FORMAT, auto-detected per line (unrecognised lines are COUNTED, never
silently dropped):
  (a) '<ISO-8601 UTC> Cached=.. MemFree=.. Dirty=.. Writeback=.. iowait=..'
      (values in kB unless suffixed kB/MB/GB; iowait in percent; or a raw
      'cpu <ticks...>' /proc/stat line which is differenced for iowait)
  (b) CSV with a header naming utc/ts/time and those fields
  (c) a timestamp line followed by raw /proc/meminfo lines ('Cached: 123 kB')
      and/or a raw 'cpu ...' line, until the next timestamp

READING (pre-registered): PAGE CACHE if per-film cost correlates with iowait
(Spearman rho >= 0.3) AND iowait itself moves through the leg
(rho(iowait, position) >= 0.3); where cost and iowait both trend with
position they are confounded and the correlation of their detrended
residuals is printed to split them; iowait should move only in the rising
legs. PROCESS / FILESYSTEM if cost rises with position (rho >= 0.3) while
iowait is flat (a constant series reads as rho 0, never "undefined") or
uncorrelated (|rho| < 0.3). Printed per leg beside the frames-basis cost
quartiles.

  --run-dir DIR --cachewatch FILE [--manifest FILE] [--passes 3,4]
  --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve()
ARMS = {'rr': 'rocketride_video_parity', 'li': 'llamaindex_video_workers'}
FIELDS = ('Cached', 'MemFree', 'Dirty', 'Writeback')


def parse_utc(s: str) -> Optional[float]:
    s = s.strip().replace('Z', '+00:00')
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.timestamp()


def _kb(v) -> Optional[float]:
    if v is None:
        return None
    m = re.match(r'^\s*([\d.]+)\s*(kB|KB|kb|MB|mb|GB|gb|B)?\s*$', str(v))
    if not m:
        return None
    x = float(m.group(1)); u = (m.group(2) or 'kB').lower()
    return x * {'b': 1 / 1024, 'kb': 1, 'mb': 1024, 'gb': 1024 * 1024}[u]


def _num(v) -> Optional[float]:
    try:
        return float(str(v).rstrip('%'))
    except (TypeError, ValueError):
        return None


def parse_cachewatch(path: Path) -> Tuple[List[dict], dict]:
    rows: List[dict] = []
    stats = {'lines': 0, 'unrecognised': 0, 'format': None}
    cur = None
    header = None
    for line in path.read_text().splitlines():
        stats['lines'] += 1
        s = line.strip()
        if not s:
            continue
        if header is None and ',' in s and re.search(r'(?i)\b(utc|ts|time|timestamp)\b', s) and 'Cached' in s:
            header = [h.strip() for h in s.split(',')]
            stats['format'] = 'csv'
            continue
        if header:
            vals = [v.strip() for v in s.split(',')]
            if len(vals) == len(header):
                d = dict(zip(header, vals))
                tkey = next(k for k in header if k.lower() in ('utc', 'ts', 'time', 'timestamp'))
                t = parse_utc(d[tkey])
                if t is None:
                    stats['unrecognised'] += 1
                    continue
                row = {'t': t, **{f: _kb(d.get(f)) for f in FIELDS},
                       'iowait': _num(d.get('iowait') if d.get('iowait') is not None else d.get('iowait_pct')), 'cpu': None}
                rows.append(row)
                continue
            stats['unrecognised'] += 1
            continue
        m = re.match(r'^(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s*(.*)$', s)
        if m and parse_utc(m.group(1)) is not None:
            cur = {'t': parse_utc(m.group(1)), **{f: None for f in FIELDS}, 'iowait': None, 'cpu': None}
            rows.append(cur)
            rest = m.group(2)
            stats['format'] = stats['format'] or ('kv' if '=' in rest else 'blocks')
            for k, v in re.findall(r'(\w+)=([^\s,]+)', rest):
                if k in FIELDS:
                    cur[k] = _kb(v)
                elif k.lower() in ('iowait', 'iowait_pct'):
                    cur['iowait'] = _num(v)
            mc = re.search(r'\bcpu\s+(\d+(?:\s+\d+){3,})', rest)
            if mc:
                cur['cpu'] = _cpu_ticks(mc.group(1))
            continue
        if cur is not None:
            mm = re.match(r'^(Cached|MemFree|Dirty|Writeback):\s+(\d+)\s*kB', s)
            if mm:
                cur[mm.group(1)] = float(mm.group(2))
                continue
            mc = re.match(r'^cpu\s+(\d+(?:\s+\d+){3,})$', s)
            if mc:
                cur['cpu'] = _cpu_ticks(mc.group(1))
                continue
            mi = re.match(r'^(?:iowait|iowait_pct)\s*[:=]\s*([\d.]+)', s, re.I)
            if mi:
                cur['iowait'] = float(mi.group(1))
                continue
        stats['unrecognised'] += 1
    prev = None
    for r in rows:                      # iowait from raw ticks, differenced
        if r.get('cpu') and prev and prev.get('cpu') and r['iowait'] is None:
            dtot = r['cpu'][2] - prev['cpu'][2]
            dio = r['cpu'][1] - prev['cpu'][1]
            if dtot > 0:
                r['iowait'] = 100.0 * dio / dtot
        prev = r
    rows.sort(key=lambda r: r['t'])
    return rows, stats


def _cpu_ticks(s: str):
    f = [int(x) for x in s.split()]
    return (f[3], f[4], sum(f)) if len(f) >= 5 else None   # (idle, iowait, total)


# ---- run side ---------------------------------------------------------------

def stem(arm: str, p: int) -> str:
    return f'{ARMS[arm]}_blast' + ('' if p == 1 else f'_p{p}')


def leg_anchor(run_dir: Path, s: str) -> Tuple[Optional[float], str]:
    fs = run_dir / f'fsstream_{s}.jsonl'
    if not fs.exists():
        return None, f'unavailable: no {fs.name}'
    lines = [l for l in fs.read_text().splitlines() if l.strip()]
    if not lines:
        return None, f'unavailable: {fs.name} empty'
    row0 = json.loads(lines[0])
    t = parse_utc(row0.get('utc', ''))
    if t is None:
        return None, f'unavailable: {fs.name} row0 has no utc'
    return t - float(row0.get('t', 0.0)), 'fsstream row0 utc - t'


def leg_records(run_dir: Path, s: str) -> List[dict]:
    p = run_dir / f'records_{s}.jsonl'
    if not p.exists():
        return []
    last = {}
    for l in p.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            if 'video' in r:
                last[r['video']] = r
    ok = [r for r in last.values() if 'error' not in r and r.get('enqueue_ns') and r.get('admit_ns') and r.get('done_ns')]
    return sorted(ok, key=lambda r: r['enqueue_ns'])


def frames_minutes(manifest: Path) -> Dict[str, float]:
    fm = {}
    for l in manifest.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            if 'file' in r:
                fm[r['file']] = r['expected_frames_measured'] * 15.0 / 60.0
    return fm


def window_mean(cw: List[dict], key: str, t0: float, t1: float, slack: float = 60.0) -> Optional[float]:
    vals = [r[key] for r in cw if t0 - slack <= r['t'] <= t1 + slack and r.get(key) is not None]
    return st.mean(vals) if vals else None


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 3 or len(x) != len(y):
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                rk[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return rk
    rx, ry = ranks(x), ranks(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def join_leg(run_dir: Path, arm: str, p: int, cw: List[dict], fm: Dict[str, float]) -> dict:
    s = stem(arm, p)
    anchor, how = leg_anchor(run_dir, s)
    rows = leg_records(run_dir, s)
    out = {'leg': s, 'anchor_utc': anchor, 'anchor_basis': how, 'n_films': len(rows)}
    if anchor is None or not rows:
        out['state'] = 'unavailable'
        return out
    exp = run_dir / f'export_{s}.json'
    leg_wall = json.loads(exp.read_text()).get('leg_wall_s') if exp.exists() else None
    m0 = min(r['enqueue_ns'] for r in rows)
    films = []
    for i, r in enumerate(rows):
        a = anchor + (r['admit_ns'] - m0) / 1e9
        d = anchor + (r['done_ns'] - m0) / 1e9
        cost = r['wall_s'] / fm[r['video']] if fm.get(r['video']) else None
        films.append({'i': i, 'video': r['video'], 'admit_utc': a, 'done_utc': d, 'cost': cost,
                      'iowait': window_mean(cw, 'iowait', a, d), 'Cached': window_mean(cw, 'Cached', a, d),
                      'Dirty': window_mean(cw, 'Dirty', a, d)})
    t_end = anchor + (leg_wall if leg_wall else (max(f['done_utc'] for f in films) - anchor))
    out['leg_end_utc'] = t_end
    out['cw_rows_in_leg'] = sum(1 for r in cw if anchor <= r['t'] <= t_end)
    n = len(films)
    q = lambda key, sl: (st.mean([f[key] for f in sl if f.get(key) is not None]) if any(f.get(key) is not None for f in sl) else None)
    out['quartiles'] = {}
    for key in ('cost', 'iowait', 'Cached', 'Dirty'):
        out['quartiles'][key] = [q(key, films[k * n // 4:(k + 1) * n // 4]) for k in range(4)]
    pairs = [(f['cost'], f['iowait'], f['i']) for f in films if f['cost'] is not None and f['iowait'] is not None]
    costs = [f['cost'] for f in films if f['cost'] is not None]
    out['rho_cost_position'] = spearman(costs, list(range(len(costs))))
    out['films'] = films
    out['state'] = 'measured'
    if not pairs:
        out.update(rho_cost_iowait=None, rho_iowait_position=None, rho_residual=None,
                   reading='no iowait in the log window: page-cache read unavailable')
        return out
    c = [p_[0] for p_ in pairs]
    io = [p_[1] for p_ in pairs]
    pos = [float(p_[2]) for p_ in pairs]
    io_flat = (max(io) - min(io)) < 1e-9           # a constant series is FLAT, not "undefined"
    ri = 0.0 if io_flat else spearman(c, io)
    rio = 0.0 if io_flat else spearman(io, pos)
    out['rho_cost_iowait'], out['rho_iowait_position'] = ri, rio
    # where cost and iowait both trend with position they are confounded;
    # the residual correlation after a linear fit on position splits them
    out['rho_residual'] = None if io_flat else spearman(_detrend(c, pos), _detrend(io, pos))
    rp = out['rho_cost_position'] or 0.0
    if ri is not None and ri >= 0.3 and (rio or 0.0) >= 0.3:
        res = out['rho_residual']
        out['reading'] = ('PAGE CACHE side: cost tracks iowait and iowait itself moves through the leg'
                          + (f' (co-trend with position; detrended residual rho {res:.2f})' if res is not None else ''))
    elif rp >= 0.3 and (ri is None or abs(ri) < 0.3):
        out['reading'] = 'PROCESS/FILESYSTEM side: cost rises with position while iowait is flat or uncorrelated'
    else:
        out['reading'] = 'indeterminate (weak or mixed correlations)'
    return out


def _detrend(y: List[float], x: List[float]) -> List[float]:
    """Residuals of y after a least-squares linear fit on x."""
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = (sum((a - mx) * (v - my) for a, v in zip(x, y)) / sxx) if sxx else 0.0
    return [v - (my + b * (a - mx)) for a, v in zip(x, y)]


def fmt(v, scale=1.0, nd=2):
    return '-' if v is None else f'{v / scale:.{nd}f}'


def report(run_dir: Path, cw_path: Path, manifest: Path, passes: List[int]) -> int:
    cw, stats = parse_cachewatch(cw_path)
    print(f'cachewatch: {len(cw)} rows, format {stats["format"]}, unrecognised lines {stats["unrecognised"]}/{stats["lines"]}'
          + (f'; span {dt.datetime.fromtimestamp(cw[0]["t"], dt.timezone.utc):%Y-%m-%dT%H:%M}Z..'
             f'{dt.datetime.fromtimestamp(cw[-1]["t"], dt.timezone.utc):%H:%M}Z' if cw else ''))
    fm = frames_minutes(manifest)
    rc = 0
    for arm in ('rr', 'li'):
        for p in passes:
            j = join_leg(run_dir, arm, p, cw, fm)
            if j.get('state') != 'measured':
                print(f'{j["leg"]}: {j.get("state")} ({j.get("anchor_basis")}); films {j["n_films"]}')
                continue
            a = dt.datetime.fromtimestamp(j['anchor_utc'], dt.timezone.utc)
            e = dt.datetime.fromtimestamp(j['leg_end_utc'], dt.timezone.utc)
            print(f'{j["leg"]}: leg {a:%H:%M:%S}Z..{e:%H:%M:%S}Z ({j["anchor_basis"]}); {j["n_films"]} films; '
                  f'{j["cw_rows_in_leg"]} cachewatch rows inside')
            Q = j['quartiles']
            print(f'   cost s/foot-min Q {[fmt(x) for x in Q["cost"]]} | iowait % Q {[fmt(x) for x in Q["iowait"]]} | '
                  f'Cached GiB Q {[fmt(x, 2**20, 1) for x in Q["Cached"]]} | Dirty MiB Q {[fmt(x, 1024, 0) for x in Q["Dirty"]]}')
            print(f'   rho(cost,iowait) {fmt(j["rho_cost_iowait"])} | rho(cost,position) {fmt(j["rho_cost_position"])} | '
                  f'rho(iowait,position) {fmt(j["rho_iowait_position"])} | detrended residual rho '
                  f'{fmt(j.get("rho_residual"))} -> {j["reading"]}')
    return rc


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        t0 = parse_utc('2026-09-06T10:00:00Z')
        s = stem('rr', 3)
        (d / f'fsstream_{s}.jsonl').write_text(json.dumps({'t': 0.4, 'utc': '2026-09-06T10:00:00Z'}) + '\n')
        (d / f'export_{s}.json').write_text(json.dumps({'leg_wall_s': 1200.0}))
        m0 = 5_000_000_000_000
        recs, fm = [], {}
        for i in range(12):
            a = m0 + i * 90 * 10**9
            recs.append({'video': f'v{i}.mp4', 'enqueue_ns': a - 10**9, 'admit_ns': a, 'done_ns': a + 100 * 10**9,
                         'wall_s': 100.0 + i * 5.0})
            fm[f'v{i}.mp4'] = 10.0
        (d / f'records_{s}.jsonl').write_text('\n'.join(json.dumps(r) for r in recs) + '\n')
        # format (a): iowait rising with time
        lines = [f'2026-09-06T{10 + m // 60:02d}:{m % 60:02d}:00Z Cached={40_000_000 - m * 100_000} MemFree=2000000 Dirty=50000 Writeback=0 iowait={m * 0.5:.1f}'
                 for m in range(0, 25)]
        (d / 'cw_a.log').write_text('\n'.join(lines) + '\njunk line here\n')
        cw, stats = parse_cachewatch(d / 'cw_a.log')
        check('format (a) parsed: 25 rows, 1 unrecognised, kv', len(cw) == 25 and stats['unrecognised'] == 1 and stats['format'] == 'kv')
        j = join_leg(d, 'rr', 3, cw, fm)
        check('anchor = fsstream utc - t (0.4 s before 10:00:00Z)', abs(j['anchor_utc'] - (t0 - 0.4)) < 1e-6)
        check('leg end = anchor + leg_wall_s', abs(j['leg_end_utc'] - (t0 - 0.4 + 1200.0)) < 1e-6)
        check('per-film windows carry iowait means; rising cost tracks rising iowait -> PAGE CACHE side',
              j['films'][0]['iowait'] is not None and j['rho_cost_iowait'] > 0.9 and 'PAGE CACHE' in j['reading'])
        # flat iowait, rising cost -> process/fs side
        flat = [dict(r, iowait=1.0) for r in cw]
        j2 = join_leg(d, 'rr', 3, flat, fm)
        check('flat iowait under a position rise -> PROCESS/FILESYSTEM side', 'PROCESS/FILESYSTEM' in j2['reading'])
        # format (c): timestamp blocks with raw meminfo + cpu ticks, iowait by differencing
        blk = []
        tot = 1_000_000
        for m in range(0, 5):
            blk += [f'2026-09-06 10:{m:02d}:00', f'Cached:  {30_000_000} kB', 'MemFree:  1000000 kB', 'Dirty:  10 kB',
                    'Writeback: 0 kB', f'cpu {tot} 0 {tot // 2} {tot * 4} {m * 6000} 0 0 0 0 0']
            tot += 100_000
        (d / 'cw_c.log').write_text('\n'.join(blk) + '\n')
        cwc, sc = parse_cachewatch(d / 'cw_c.log')
        check('format (c) parsed: 5 blocks, Cached from meminfo lines, iowait differenced from cpu ticks',
              len(cwc) == 5 and cwc[1]['Cached'] == 30_000_000 and cwc[1]['iowait'] is not None and cwc[0]['iowait'] is None
              and sc['unrecognised'] == 0)
        # format (b): csv
        (d / 'cw_b.csv').write_text('utc,Cached,MemFree,Dirty,Writeback,iowait\n2026-09-06T10:00:00Z,1000,2000,3,0,4.5\n')
        cwb, sb = parse_cachewatch(d / 'cw_b.csv')
        check('format (b) csv parsed', len(cwb) == 1 and cwb[0]['iowait'] == 4.5 and cwb[0]['Cached'] == 1000 and sb['format'] == 'csv')
        check('missing fsstream -> unavailable, no join', join_leg(d, 'li', 3, cw, fm).get('state') == 'unavailable')
        check('spearman: monotone +1, reversed -1', spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0 and spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0)
    sys.path.insert(0, str(HERE.parents[2]))
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--run-dir', default=None)
    ap.add_argument('--cachewatch', default=os.path.expanduser('~/logs/cachewatch.log'))
    ap.add_argument('--manifest', default=str(HERE.parents[1] / 'films500_video_manifest.jsonl'))
    ap.add_argument('--passes', default='3,4')
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.run_dir:
        ap.error('--run-dir required (or --self-test)')
    return report(Path(a.run_dir), Path(a.cachewatch), Path(a.manifest), [int(x) for x in a.passes.split(',')])


if __name__ == '__main__':
    sys.exit(main())
