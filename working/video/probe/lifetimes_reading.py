#!/usr/bin/env python3
"""lifetimes_reading — the PRE-REGISTERED reading of the films-500
lifetime-controlled passes, committed BEFORE the run (ruling 2026-09-06).
The bands below are the ones in run_films500_lifetimes.sh's header and in
its run_manifest.pre_registered; this tool applies them, it does not
choose them after the fact.

BASIS: per-film wall_s per footage-minute, footage = measured frames x 15 s
(frames basis — keeps TheSheik.mp4, manifest video_s 0.0); position =
enqueue order (== manifest order; verified per leg); quartile and
first/last-20% means are frames-weighted; cross-pass comparisons are
PAIRED per film (mean log-ratio, SE).

  --campaign DIR                 the p1/p2 run (null control: must
                                 reproduce the campaign figures baked here)
  --lifetimes DIR                the p3/p4 run: applies every pre-registered
                                 case and prints CONFIRMS / REFUTES /
                                 INDETERMINATE per case, plus the
                                 lifetime_state readings from the exports
  --self-test                    synthetic records through the same code
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve()
MANIFEST = HERE.parents[1] / 'films500_video_manifest.jsonl'
ARMS = {'rr': 'rocketride_video_parity', 'li': 'llamaindex_video_workers'}

# ---- pre-registered constants (frames basis) --------------------------------
BANDS = {
    'rr_p3_drift': (0.01, 0.06),      # first->last-20% of RR pass 3
    'li_p3_drift': (-0.13, -0.06),    # of LI pass 3
    'p4_flat_abs': 0.025,             # |first->last-20%| of pass 4
    'flat_refutes_abs': 0.01,         # |drift| below this on p3 = REFUTES (flat first pass)
    'rr_p3_q1_process_max': 5.13,     # RR p3 opening quartile <= this: process side
    'rr_p3_q1_fs_min': 5.20,          # >= this: filesystem side
    'plateau_same_abs': 0.02,         # |paired log-ratio p4 vs campaign p2| <= : same level
    'plateau_diff_abs': 0.03,         # >= : different level
}
# the campaign's own figures on this basis (null control reproduces them)
CAMPAIGN = {'rr': {'p1_q1': 5.026, 'p1_drift': 0.036, 'p2_level': 5.375, 'p2_drift': -0.002},
            'li': {'p1_q1': 5.143, 'p1_drift': -0.098, 'p2_level': 4.804, 'p2_drift': -0.018}}


def frames_minutes(manifest: Path) -> Dict[str, float]:
    fm = {}
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if 'file' in r:
            fm[r['file']] = r['expected_frames_measured'] * 15.0 / 60.0
    return fm


def manifest_order(manifest: Path) -> List[str]:
    return [json.loads(l)['file'] for l in manifest.read_text().splitlines()
            if l.strip() and '"file"' in l]


def leg_rows(path: Path) -> List[dict]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    last = {}
    for r in rows:                      # last record per video wins (resume discipline)
        if 'video' in r:
            last[r['video']] = r
    ok = [r for r in last.values() if 'error' not in r and r.get('enqueue_ns') and r.get('wall_s') is not None]
    return sorted(ok, key=lambda r: r['enqueue_ns'])


def level(rows: List[dict], fm: Dict[str, float]) -> float:
    return sum(r['wall_s'] for r in rows) / sum(fm[r['video']] for r in rows)


def profile(rows: List[dict], fm: Dict[str, float], order: Optional[List[str]] = None) -> dict:
    n = len(rows)
    q = [level(rows[i * n // 4:(i + 1) * n // 4], fm) for i in range(4)]
    f20, l20 = level(rows[:n // 5], fm), level(rows[-(n // 5):], fm)
    out = {'n': n, 'q': [round(x, 3) for x in q], 'first20': round(f20, 3), 'last20': round(l20, 3),
           'drift': round(l20 / f20 - 1, 4), 'level': round(level(rows, fm), 3)}
    if order is not None:
        present = set(r['video'] for r in rows)
        out['order_is_manifest'] = [r['video'] for r in rows] == [v for v in order if v in present]
    return out


def paired(rows_a: List[dict], rows_b: List[dict], fm: Dict[str, float]) -> dict:
    ca = {r['video']: r['wall_s'] / fm[r['video']] for r in rows_a}
    cb = {r['video']: r['wall_s'] / fm[r['video']] for r in rows_b}
    lr = [math.log(cb[v] / ca[v]) for v in ca if v in cb]
    if len(lr) < 2:
        return {'n': len(lr), 'state': 'unavailable'}
    mu, sd = st.mean(lr), st.stdev(lr)
    return {'n': len(lr), 'mean_log_ratio': round(mu, 4), 'ratio_pct': round((math.exp(mu) - 1) * 100, 2),
            'se_pct': round(sd / math.sqrt(len(lr)) * 100, 2)}


def stem(arm: str, p: int) -> str:
    return f'{ARMS[arm]}_blast' + ('' if p == 1 else f'_p{p}')


def read_run(run_dir: Path, passes: List[int], fm, order) -> dict:
    out = {}
    for arm in ARMS:
        for p in passes:
            rec = run_dir / f'records_{stem(arm, p)}.jsonl'
            if not rec.exists():
                out[(arm, p)] = None
                continue
            rows = leg_rows(rec)
            out[(arm, p)] = {'rows': rows, 'profile': profile(rows, fm, order)}
    return out


def export_state(run_dir: Path, arm: str, p: int) -> dict:
    path = run_dir / f'export_{stem(arm, p)}.json'
    if not path.exists():
        return {'state': 'unavailable: no export'}
    e = json.loads(path.read_text())
    ls = e.get('lifetime_state') or {}
    cl = (e.get('provenance_video') or {}).get('container_lifetime') or {}

    def frag(ph):
        mb = (((ls.get(ph) or {}).get('host') or {}).get('frag') or {}).get('mb_groups') or {}
        return ({'avg_free_extent_kb': mb.get('avg_free_extent_kb'),
                 'ge_4mib_share': mb.get('free_share_in_extents_ge_4mib_lower_bound'),
                 'free_fragments': mb.get('free_fragments')} if mb.get('state') == 'measured'
                else {'state': mb.get('state')})

    def disk(ph):
        d = ((ls.get(ph) or {}).get('host') or {}).get('diskstats') or {}
        return d.get('sectors_written') if d.get('state') == 'measured' else None

    def spool_end():
        res = {}
        for c, rec in ((ls.get('leg_end') or {}).get('containers') or {}).items():
            for pth, sp in (rec.get('spool') or {}).items():
                res[c] = {'du_kb': sp.get('du_kb'), 'n_files': sp.get('n_files')}
        return res

    def procs(ph):
        res = {}
        for c, rec in ((ls.get(ph) or {}).get('containers') or {}).items():
            pr = rec.get('procs') or {}
            res[c] = {'n': pr.get('n'), 'vmrss_gib': round((pr.get('vmrss_kb') or 0) / 2**20, 2),
                      'rssanon_gib': round((pr.get('rssanon_kb') or 0) / 2**20, 2) if pr.get('rssanon_kb') else None,
                      'top': [(x.get('cmd', '')[:40], round(x.get('vmrss', 0) / 2**20, 2)) for x in (pr.get('top_by_rss') or [])[:3]]}
        return res
    ws, we = disk('leg_start'), disk('leg_end')
    traj = ls.get('service_memory_trajectory') or {}
    fs = (ls.get('fs_stream') or {}).get('paths') or {}
    return {'container_age_at_leg_start_s': cl.get('age_at_leg_start_s'), 'pass_in_lifetime': cl.get('pass_in_lifetime'),
            'frag_start': frag('leg_start'), 'frag_end': frag('leg_end'),
            'churn_written_gib': round((we - ws) * 512 / 2**30, 1) if ws is not None and we is not None else None,
            'spool_at_leg_end': spool_end(),
            'fs_stream_max_used_minus_start_gib': {k: round(v.get('max_used_minus_start', 0) / 2**30, 2)
                                                   for k, v in fs.items() if v.get('state') == 'measured'},
            'service_rss_gib_first_last_max': ([round(traj['rss'][k] / 2**30, 2) for k in ('first_mean', 'last_mean', 'max')]
                                               if traj.get('rss') else traj.get('state')),
            'cg_anon_gib_first_last': ([round(traj['cg_anon'][k] / 2**30, 2) for k in ('first_mean', 'last_mean')]
                                       if traj.get('cg_anon') else None),
            'procs_start': procs('leg_start'), 'procs_end': procs('leg_end')}


def within(x: float, lo: float, hi: float) -> bool:
    return lo <= x <= hi


def verdicts(camp: dict, life: dict, fm) -> List[str]:
    lines = []
    for arm in ('rr', 'li'):
        p3, p4 = life.get((arm, 3)), life.get((arm, 4))
        if not p3:
            lines.append(f'{arm.upper()}: p3 records absent — no reading')
            continue
        d3 = p3['profile']['drift']
        band = BANDS[f'{arm}_p3_drift']
        if abs(d3) < BANDS['flat_refutes_abs']:
            v3 = 'REFUTES (flat first pass)'
        elif (d3 > 0) != (band[0] > 0):
            v3 = 'REFUTES (reversed sign)'
        elif within(d3, *band):
            v3 = 'CONFIRMS'
        else:
            v3 = 'INDETERMINATE (right sign, outside the band)'
        lines.append(f'{arm.upper()} p3 drift {d3 * 100:+.1f}% (band {band[0] * 100:+.0f}..{band[1] * 100:+.0f}%) -> {v3}')
        if p4:
            d4 = p4['profile']['drift']
            same_dir = (d4 > 0) == (band[0] > 0)
            if abs(d4) <= BANDS['p4_flat_abs']:
                v4 = 'CONFIRMS (flat)'
            elif same_dir:
                v4 = 'REFUTES (p4 still drifting: continuous degradation/improvement)'
            else:
                v4 = 'INDETERMINATE (p4 drifts against the p3 direction)'
            lines.append(f'{arm.upper()} p4 drift {d4 * 100:+.1f}% (flat if |d| <= {BANDS["p4_flat_abs"] * 100:.1f}%) -> {v4}; '
                         f'p4 level {p4["profile"]["level"]:.3f} vs p3 last20 {p3["profile"]["last20"]:.3f} '
                         f'({(p4["profile"]["level"] / p3["profile"]["last20"] - 1) * 100:+.1f}%)')
            c2 = camp.get((arm, 2))
            if c2:
                pr = paired(c2['rows'], p4['rows'], fm)
                r = pr.get('ratio_pct')
                if r is None:
                    pl = 'unavailable'
                elif abs(r) <= BANDS['plateau_same_abs'] * 100:
                    pl = 'SAME LEVEL: reproducible steady state (plateau pair quotable at n=2)'
                elif abs(r) >= BANDS['plateau_diff_abs'] * 100:
                    pl = 'DIFFERENT LEVEL: lifetime-specific plateau — no stable production number; the claim changes'
                else:
                    pl = 'UNRESOLVED at one pair of lifetimes — no plateau claim either way'
                lines.append(f'{arm.upper()} plateau level p4 vs campaign p2: {r:+.2f}% (SE {pr["se_pct"]}%, n={pr["n"]}) -> {pl}')
    rr3 = life.get(('rr', 3))
    if rr3:
        q1 = rr3['profile']['q'][0]
        if q1 <= BANDS['rr_p3_q1_process_max']:
            m = 'PROCESS side (fresh server starts fast)'
        elif q1 >= BANDS['rr_p3_q1_fs_min']:
            m = 'FILESYSTEM side (fresh container on the dirty fs starts slow)'
        else:
            m = 'INDETERMINATE at n=1 (between the bands)'
        lines.append(f'MECHANISM READ: RR p3 opening quartile {q1:.3f} vs campaign p1 Q1 {CAMPAIGN["rr"]["p1_q1"]:.3f} '
                     f'(<= {BANDS["rr_p3_q1_process_max"]} process / >= {BANDS["rr_p3_q1_fs_min"]} fs) -> {m}')
        li3 = life.get(('li', 3))
        if li3:
            lines.append(f'  corroboration: LI p3 opening quartile {li3["profile"]["q"][0]:.3f} vs campaign LI p1 Q1 '
                         f'{CAMPAIGN["li"]["p1_q1"]:.3f} ({(li3["profile"]["q"][0] / CAMPAIGN["li"]["p1_q1"] - 1) * 100:+.1f}%)')
    return lines


def null_control(camp: dict) -> bool:
    ok = True
    for arm in ('rr', 'li'):
        p1, p2 = camp.get((arm, 1)), camp.get((arm, 2))
        if not (p1 and p2):
            print(f'  FAIL  {arm}: campaign records missing')
            return False
        got = {'p1_q1': p1['profile']['q'][0], 'p1_drift': p1['profile']['drift'],
               'p2_level': p2['profile']['level'], 'p2_drift': p2['profile']['drift']}
        for k, want in CAMPAIGN[arm].items():
            good = abs(got[k] - want) <= 0.0015
            ok = ok and good
            print(f'  {"PASS" if good else "FAIL"}  null control {arm} {k}: {got[k]} vs baked {want}')
        good = p1['profile'].get('order_is_manifest') and p2['profile'].get('order_is_manifest')
        ok = ok and bool(good)
        print(f'  {"PASS" if good else "FAIL"}  {arm}: enqueue order == manifest order in p1 and p2')
    return ok


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond
    fm = {f'v{i}': 10.0 for i in range(100)}
    order = [f'v{i}' for i in range(100)]
    rows_up = [{'video': f'v{i}', 'enqueue_ns': i, 'wall_s': 50.0 + i * 0.025} for i in range(100)]     # rising ~+4%
    rows_flat = [{'video': f'v{i}', 'enqueue_ns': i, 'wall_s': 55.0} for i in range(100)]
    pu, pf = profile(rows_up, fm, order), profile(rows_flat, fm, order)
    check('profile: rising leg drifts up (~+4%), flat leg 0, order verified',
          0.03 < pu['drift'] < 0.05 and pf['drift'] == 0 and pu['order_is_manifest'])
    pr = paired(rows_up, rows_flat, fm)
    check('paired log-ratio computed with SE', pr['n'] == 100 and pr['se_pct'] > 0)
    fake_life = {('rr', 3): {'rows': rows_up, 'profile': dict(pu, q=[5.0, 5.05, 5.1, 5.2])},
                 ('rr', 4): {'rows': rows_flat, 'profile': pf},
                 ('li', 3): {'rows': [dict(r, wall_s=60 - i * 0.06) for i, r in enumerate(rows_up)], 'profile': None},
                 ('li', 4): {'rows': rows_flat, 'profile': pf}}
    fake_life[('li', 3)]['profile'] = profile(fake_life[('li', 3)]['rows'], fm, order)
    camp = {('rr', 2): {'rows': rows_flat, 'profile': pf}, ('li', 2): {'rows': rows_flat, 'profile': pf}}
    v = verdicts(camp, fake_life, fm)
    check('verdict lines: RR p3 CONFIRMS band, p4 flat CONFIRMS, plateau SAME LEVEL, mechanism PROCESS',
          any('RR p3' in l and 'CONFIRMS' in l for l in v) and any('RR p4' in l and 'CONFIRMS (flat)' in l for l in v)
          and any('RR plateau' in l and 'SAME LEVEL' in l for l in v) and any('PROCESS side' in l for l in v))
    fake_life[('rr', 3)]['profile']['q'][0] = 5.3
    check('mechanism read flips to FILESYSTEM side at q1 >= 5.20', any('FILESYSTEM side' in l for l in verdicts(camp, fake_life, fm)))
    check('records with an error row are dropped, last record per video wins',
          len(leg_rows_from([{'video': 'a', 'enqueue_ns': 1, 'wall_s': 1, 'error': 'x'},
                             {'video': 'a', 'enqueue_ns': 2, 'wall_s': 2}, {'video': 'b', 'enqueue_ns': 3, 'wall_s': 3}])) == 2)
    sys.path.insert(0, str(HERE.parents[2]))
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def leg_rows_from(rows: List[dict]) -> List[dict]:
    last = {}
    for r in rows:
        last[r['video']] = r
    return sorted([r for r in last.values() if 'error' not in r], key=lambda r: r['enqueue_ns'])


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--campaign', default=str(HERE.parents[1] / 'results' / 'films500_mainrun_20260904T204852Z'))
    ap.add_argument('--lifetimes', default=None)
    ap.add_argument('--manifest', default=str(MANIFEST))
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    fm, order = frames_minutes(Path(args.manifest)), manifest_order(Path(args.manifest))
    camp = read_run(Path(args.campaign), [1, 2], fm, order)
    print('=== campaign p1/p2 on the pre-registered basis (frames) ===')
    for (arm, p), v in sorted(camp.items()):
        if v:
            pr = v['profile']
            print(f'  {arm} p{p}: n={pr["n"]} Q {pr["q"]} first20 {pr["first20"]} last20 {pr["last20"]} drift {pr["drift"] * 100:+.1f}% '
                  f'level {pr["level"]} order==manifest {pr.get("order_is_manifest")}')
    print('=== null control ===')
    nc = null_control(camp)
    if not args.lifetimes:
        print('null control:', 'PASS' if nc else 'FAIL', '(no --lifetimes given: nothing read)')
        return 0 if nc else 3
    if not nc:
        print('NOT DONE — null control failed; the reading tool does not reproduce the campaign; no verdicts')
        return 3
    life = read_run(Path(args.lifetimes), [3, 4], fm, order)
    print('=== lifetimes p3/p4 ===')
    for (arm, p), v in sorted(life.items()):
        if v:
            pr = v['profile']
            print(f'  {arm} p{p}: n={pr["n"]} Q {pr["q"]} first20 {pr["first20"]} last20 {pr["last20"]} drift {pr["drift"] * 100:+.1f}% '
                  f'level {pr["level"]} order==manifest {pr.get("order_is_manifest")}')
            print('     export:', json.dumps(export_state(Path(args.lifetimes), arm, p)))
        else:
            print(f'  {arm} p{p}: records absent')
    print('=== PRE-REGISTERED VERDICTS ===')
    for line in verdicts(camp, life, fm):
        print('  ' + line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
