#!/usr/bin/env python3
"""Recompute a leg's service memory peak from the RAW collector tick stream, on
three labelled bases, and settle which sampler produced it BY MEASUREMENT.

WHY RECOMPUTE. `collector_summary.roles.service.peak_rss_mb` is a stored
maximum. The 2026-08-25 collector defect (`7c1cd81`) sampled ONE container of N
in a multi-instance posture, so a stored peak can be one-Nth of the service
with no field name saying so. The per-tick stream carries the evidence for what
was actually sampled, so it answers for itself instead of us inferring from a
commit date.

WHAT THE STREAM ACTUALLY CARRIES (verified against the landed films streams):
rows are `{"kind":"role_tick","t":…,"role":"service"|"driver","n_procs":N,
"rss":…,"cg_anon":…,"cg_current":…,"cg_pids_tasks":…}`. There are NO container
names in the stream — a role tick is already aggregated across whatever process
trees the role resolved. So the sampler is identified from two measured
quantities instead:

  n_procs        processes tracked across every resolved container tree. One
                 single-worker instance contributes 1; the defective sampler
                 therefore reads ~1 where the fixed one reads N.
  cg_pids_tasks  TASKS in the ONE cgroup the collector resolved per role
                 (`collector.py::_sample_cgroup` caches a single path) — the
                 tell for the cgroup bases being one instance's, always.

and cross-checked against the container NAMES, which live in the export:
`preleg_container_idle_cores` carries every resolved container since `7c1cd81`
(1 key on a defective multi-instance leg, N keys on a fixed one).

THREE BASES, never mixed (the AMI cross-team table's format):
  cgroup-cache  max cg_current — cgroup memory.current, INCLUDES page cache
  anon          max cg_anon    — anonymous only
  RSS-sum       max rss        — summed per-process RSS across tracked trees;
                                 double-counts pages shared between processes

Usage:
  ami_li_memory_recompute.py --selftest
      Validate the method on the LANDED films artifacts, where the answer is
      known (LI = 16 instances, RR = 1), plus a synthetic null control that
      must classify as one-of-N. No network.
  ami_li_memory_recompute.py --dir <fetched> [--out report.json]
      Recompute every leg in a directory tree of fetched run dirs (each holding
      export_*.json and collector_*.jsonl).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

MiB = 2 ** 20
GiB = 2 ** 30
ROOT = Path(__file__).resolve().parents[3]
LANDED = ROOT / 'working' / 'video' / 'results'


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def stream_stats(jsonl: Path, role: str = 'service') -> dict:
    """Peaks and tracked-process census, recomputed tick by tick."""
    peak = {'rss': 0, 'cg_anon': 0, 'cg_current': 0}
    nprocs, tasks, ts, n_rows, bad = [], [], [], 0, 0
    with jsonl.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if r.get('kind') != 'role_tick' or r.get('role') != role:
                continue
            n_rows += 1
            for k in peak:
                v = r.get(k)
                if isinstance(v, (int, float)):
                    peak[k] = max(peak[k], v)
            if isinstance(r.get('n_procs'), int):
                nprocs.append(r['n_procs'])
            if isinstance(r.get('cg_pids_tasks'), int):
                tasks.append(r['cg_pids_tasks'])
            if isinstance(r.get('t'), (int, float)):
                ts.append(r['t'])
    if not n_rows:
        return {'ticks': 0, 'error': f'no {role} role_tick rows in {jsonl.name}'}
    return {
        'ticks': n_rows, 'malformed_lines': bad,
        'span_s': round(max(ts) - min(ts), 1) if ts else None,
        'peak_rss_bytes': peak['rss'], 'peak_cg_anon_bytes': peak['cg_anon'],
        'peak_cg_current_bytes': peak['cg_current'],
        'n_procs_min': min(nprocs) if nprocs else None,
        'n_procs_median': int(statistics.median(nprocs)) if nprocs else None,
        'n_procs_max': max(nprocs) if nprocs else None,
        'cg_pids_tasks_min': min(tasks) if tasks else None,
        'cg_pids_tasks_max': max(tasks) if tasks else None,
    }


def declared_instances(export: dict) -> dict:
    """What the leg SAID it was. CONTAINERS and WORKERS are different counts and
    conflating them is how a single-container posture looks like a defect:
    RocketRide runs 16 TOKENS in ONE container, and the comparison arm's default
    posture runs 8 or 16 WORKERS in one container, while its balanced posture
    runs one worker per container. So the expected CONTAINER count comes from a
    per-container read-back where the export era has one, never from `instances`."""
    pv = export.get('provenance_video') or {}
    pre = export.get('preleg_container_idle_cores') or {}
    census = pv.get('task_census') or {}
    idle = ((export.get('efficiency') or {}).get('idle_burden') or {})
    posture = pv.get('posture') or {}
    li = ((pv.get('identity_readback') or {}).get('li') or {})
    kind = idle.get('instance_kind')

    exp, src = None, 'none — this export era carries no per-container read-back'
    if kind == 'rr_tokens' or (export.get('arm') or '').startswith('rocketride'):
        exp, src = 1, 'the RocketRide arm is one engine container (tokens are in-container)'
    else:
        md5s = li.get('rfdetr_checkpoint_md5_by_container') or {}
        per_worker = ((li.get('chunk_config_readback') or {}).get('per_worker') or {})
        ports_declared = posture.get('li_ports') or pv.get('li_ports') or posture.get('ports')
        if md5s:
            exp, src = len(md5s), 'per-container checkpoint read-back (`rfdetr_checkpoint_md5_by_container`)'
        elif per_worker:
            ports = {k.split('_')[2] for k in per_worker if len(k.split('_')) > 2}
            if ports:
                exp, src = len(ports), 'distinct ports in the per-worker chunk read-back'
        elif isinstance(ports_declared, list):
            exp, src = len(ports_declared), 'declared port list'
        elif isinstance(ports_declared, int):
            exp, src = ports_declared, 'declared port count'
    return {
        'container_names_in_export': sorted(pre), 'n_container_names': len(pre),
        'expected_containers': exp, 'expected_containers_source': src,
        'instances_declared': idle.get('instances'), 'instance_kind': kind,
        'declared_workers': posture.get('declared_workers') or census.get('declared_workers'),
        'declared_tokens': posture.get('tokens') or census.get('declared_tokens'),
        'census_after': census.get('census_after'), 'posture': export.get('posture'),
    }


def classify(stats: dict, decl: dict) -> dict:
    """Which sampler ran — measured from the artifacts, not inferred from a date.

    Evidence, in order: the export's container-name census (the fix made
    `preleg_container_idle_cores` carry every resolved container); the expected
    container count from a per-container read-back; and the stream's tracked
    process count, which separates "one of N single-worker instances" (~1
    process) from "one container running W workers" (~W processes)."""
    n_names, exp = decl['n_container_names'], decl['expected_containers']
    procs, workers = stats.get('n_procs_median'), decl.get('declared_workers')
    why = [f"export names {n_names} container(s)"
           + (f"; expected {exp} from {decl['expected_containers_source']}" if exp else
              f"; expected count unavailable ({decl['expected_containers_source']})")]
    if procs is not None:
        why.append(f'stream tracks {procs} process(es) per service tick'
                   + (f' against {workers} declared worker(s)' if workers else ''))
    if stats.get('cg_pids_tasks_max') is not None:
        why.append(f"one cgroup sampled per role, peak {stats['cg_pids_tasks_max']} tasks in it")

    if exp == 1:
        verdict = 'SINGLE-CONTAINER POSTURE — one sample IS the whole service'
    elif exp and n_names == exp and exp > 1:
        verdict = f'FIXED SAMPLER — all {exp} containers resolved'
    elif exp and n_names == 1 and exp > 1:
        verdict = f'DEFECTIVE SAMPLER — one container of {exp}'
    elif exp is None and n_names > 1:
        verdict = f'FIXED SAMPLER — {n_names} containers named (expected count unavailable)'
    elif exp is None and n_names == 1 and workers and procs is not None and procs >= max(2, workers - 1):
        verdict = ('SINGLE-CONTAINER POSTURE (inferred) — one name, and the stream tracks '
                   f'{procs} processes for {workers} declared workers, so the workers are in it')
    elif exp is None and n_names == 1 and procs == 1 and (workers or 0) > 1:
        verdict = (f'DEFECTIVE SAMPLER (inferred) — one name and one tracked process for '
                   f'{workers} declared workers')
    else:
        verdict = 'INDETERMINATE — refusing to guess'
    whole = verdict.startswith(('FIXED', 'SINGLE'))
    return {'sampler_verdict': verdict, 'basis': why,
            'rss_basis_scope': ('whole service — summed per-process RSS across every tracked tree'
                                if whole else 'ONE CONTAINER — a LOWER BOUND on one instance, '
                                              'NOT the arm peak'),
            'cgroup_basis_scope': ('whole service' if exp == 1 or (exp is None and n_names == 1 and whole)
                                   else f'ONE CONTAINER of {exp or n_names} — the collector caches one '
                                        'cgroup per role, so anon and cache are one instance even when '
                                        'the RSS sum is complete')}


def do_leg(export_path: Path, jsonl_path: Path | None) -> dict:
    e = json.loads(export_path.read_text())
    svc = ((e.get('collector_summary') or {}).get('roles') or {}).get('service') or {}
    decl = declared_instances(e)
    out = {
        'export': str(export_path), 'export_sha256': sha256(export_path),
        'arm': e.get('arm'), 'leg': e.get('leg'), 'pass': e.get('pass'),
        'span_frames_per_s': (e.get('throughput') or {}).get('total_frames_per_s'),
        'declared': decl,
        'stored': {'peak_rss_mb': svc.get('peak_rss_mb'), 'peak_cgroup_anon_mb': svc.get('peak_cgroup_anon_mb'),
                   'peak_cgroup_current_mb': svc.get('peak_cgroup_current_mb'),
                   'cgroup_path': svc.get('cgroup_path'), 'peak_cgroup_tasks': svc.get('peak_cgroup_tasks')},
    }
    if jsonl_path is None or not jsonl_path.exists():
        out['recomputed'] = None
        out['note'] = 'no raw tick stream beside this export — nothing recomputed'
        return out
    s = stream_stats(jsonl_path)
    out['stream'] = {'path': str(jsonl_path), 'sha256': sha256(jsonl_path), **s}
    if s.get('ticks'):
        out['recomputed_GiB'] = {
            'cgroup_cache': round(s['peak_cg_current_bytes'] / GiB, 3),
            'anon': round(s['peak_cg_anon_bytes'] / GiB, 3),
            'rss_sum': round(s['peak_rss_bytes'] / GiB, 3),
        }
        cmp_ = {}
        for a, b, name in (('peak_rss_bytes', 'peak_rss_mb', 'rss_sum'),
                           ('peak_cg_anon_bytes', 'peak_cgroup_anon_mb', 'anon'),
                           ('peak_cg_current_bytes', 'peak_cgroup_current_mb', 'cgroup_cache')):
            stored_mb, mine_mb = out['stored'][b], s[a] / MiB
            cmp_[name] = {'stored_mb': stored_mb, 'recomputed_mb': round(mine_mb, 2),
                          'agrees': (stored_mb is not None and abs(round(mine_mb, 2) - stored_mb) <= 0.02)}
        out['stored_vs_recomputed'] = cmp_
        out.update(classify(s, decl))
    return out


def walk(root: Path) -> list:
    legs = []
    for ex in sorted(root.rglob('export_*.json')):
        stem = ex.name[len('export_'):-len('.json')]
        cands = [ex.parent / f'collector_{stem}.jsonl', ex.parent / f'collector_{stem}.summary.jsonl']
        legs.append(do_leg(ex, next((c for c in cands if c.exists()), None)))
    return legs


def selftest() -> int:
    """Validate the method where the answer is already known. No network."""
    fails = []
    C = LANDED / 'films500_mainrun_20260904T204852Z'
    li = do_leg(C / 'export_llamaindex_video_workers_blast.json',
                C / 'collector_llamaindex_video_workers_blast.jsonl')
    rr = do_leg(C / 'export_rocketride_video_parity_blast.json',
                C / 'collector_rocketride_video_parity_blast.jsonl')

    def ck(label, cond, detail=''):
        print(f'  {"PASS" if cond else "FAIL"}  {label}{"" if cond else "  <-- " + detail}')
        if not cond:
            fails.append(label)

    for name, leg in (('LI', li), ('RR', rr)):
        ck(f'{name}: recomputed RSS peak == stored peak_rss_mb',
           leg['stored_vs_recomputed']['rss_sum']['agrees'], json.dumps(leg['stored_vs_recomputed']['rss_sum']))
        ck(f'{name}: recomputed anon peak == stored', leg['stored_vs_recomputed']['anon']['agrees'],
           json.dumps(leg['stored_vs_recomputed']['anon']))
        ck(f'{name}: recomputed cgroup-cache peak == stored', leg['stored_vs_recomputed']['cgroup_cache']['agrees'],
           json.dumps(leg['stored_vs_recomputed']['cgroup_cache']))
    ck('LI: export names all 16 containers', li['declared']['n_container_names'] == 16,
       str(li['declared']['n_container_names']))
    ck('LI: verdict is FIXED', li['sampler_verdict'].startswith('FIXED'), li['sampler_verdict'])
    ck('LI: cgroup basis labelled one container of 16', 'ONE CONTAINER of 16' in li['cgroup_basis_scope'],
       li['cgroup_basis_scope'])
    ck('LI: the cgroup tell — cache peak is one instance cap (3.0 GiB)',
       abs(li['recomputed_GiB']['cgroup_cache'] - 3.0) < 0.01, str(li['recomputed_GiB']))
    ck('RR: single-container posture', rr['sampler_verdict'].startswith('SINGLE'), rr['sampler_verdict'])
    ck('RR: expected container count is 1, from the arm not from token count',
       rr['declared']['expected_containers'] == 1 and rr['declared']['instances_declared'] == 16,
       str(rr['declared']['expected_containers']))
    ck('RR: cgroup bases labelled whole service', rr['cgroup_basis_scope'] == 'whole service',
       rr['cgroup_basis_scope'])
    ck('RR: three bases within 1.3x of each other (one container, all whole-service)',
       max(rr['recomputed_GiB'].values()) / min(rr['recomputed_GiB'].values()) < 1.3, str(rr['recomputed_GiB']))

    # NULL CONTROL: a synthetic stream from a one-of-8 sampler must classify as DEFECTIVE
    # and its RSS must be labelled a lower bound, never the arm's peak.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        j = Path(d) / 'collector_null.jsonl'
        j.write_text('\n'.join(json.dumps(
            {'kind': 'role_tick', 't': i * 0.5, 'role': 'service', 'n_procs': 1,
             'rss': 1_500_000_000, 'cg_anon': 900_000_000, 'cg_current': 3_221_225_472,
             'cg_pids_tasks': 13}) for i in range(20)) + '\n')
        ex = Path(d) / 'export_null_leg.json'
        ex.write_text(json.dumps({
            'arm': 'llamaindex_video', 'leg': 'null', 'throughput': {'total_frames_per_s': 1.0},
            'preleg_container_idle_cores': {'li_bal_0': 0.01},
            'efficiency': {'idle_burden': {'instances': 8, 'instance_kind': 'li_workers'}},
            'provenance_video': {'posture': {'declared_workers': 8},
                                 'identity_readback': {'li': {'rfdetr_checkpoint_md5_by_container':
                                                              {f'li_bal_{i}': 'x' for i in range(8)}}}},
            'collector_summary': {'roles': {'service': {'peak_rss_mb': 1430.51}}}}))
        n = do_leg(ex, j)
    ck('null control: one-of-8 stream classifies DEFECTIVE', n['sampler_verdict'].startswith('DEFECTIVE'),
       n['sampler_verdict'])
    ck('null control: verdict names the missing seven', 'one container of 8' in n['sampler_verdict'],
       n['sampler_verdict'])
    ck('null control: RSS labelled a lower bound, not the arm peak',
       'lower bound' in n['rss_basis_scope'].lower(), n['rss_basis_scope'])
    print(f'\nselftest: {"PASS" if not fails else "FAIL " + str(fails)}')
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir'), ap.add_argument('--out'), ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.dir:
        ap.error('--dir <fetched artifacts> or --selftest')
    legs = walk(Path(a.dir))
    if not legs:
        print(f'NOT DONE — no export_*.json under {a.dir}', file=sys.stderr)
        return 2
    rows = []
    for lg in legs:
        r = lg.get('recomputed_GiB')
        rows.append(f"{Path(lg['export']).parent.name:34s} {(lg.get('leg') or '')[:34]:34s} "
                    f"{str(lg.get('span_frames_per_s')):>8s} "
                    f"{lg['declared']['n_container_names']:>4d} "
                    f"{str((lg.get('stream') or {}).get('n_procs_median')):>6s} "
                    + (f"{r['cgroup_cache']:>8.3f} {r['anon']:>8.3f} {r['rss_sum']:>8.3f}  " if r else
                       f"{'—':>8s} {'—':>8s} {'—':>8s}  ")
                    + lg.get('sampler_verdict', 'no stream'))
    print(f"{'run dir':34s} {'leg':34s} {'f/s':>8s} {'names':>4s} {'procs':>6s} "
          f"{'cg-cache':>8s} {'anon':>8s} {'RSS-sum':>8s}  verdict")
    print('\n'.join(rows))
    if a.out:
        Path(a.out).write_text(json.dumps({'legs': legs}, indent=1) + '\n')
        print(f'\nwritten: {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
