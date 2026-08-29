#!/usr/bin/env python3
"""Films concurrency curve — RULING I (2026-08-28): ONE combined sweep that
measures, on the SAME runs, the two unknowns that decide the main run:
(1) the memory slope under real concurrency (the r=0.94/w=0.58 single-lane
decomposition is two equations from two points and ASSUMES linearity through
8x BLAS scratch, allocator contention, coincident embed batches and C x
2.2 GB of spool page-cache pressure), and (2) the throughput knee on Films
content (everything held so far is single-lane; rr-8x4 measuring slower
than rr-default at N=1 is an artifact of 7 idle lanes, not a result).

Shape: a FIXED batch of films — the head of each of the 9 strata cells,
read from OUR subset manifest's own meta (deterministic; spans item sizes,
never one film repeated) — run at concurrency C per point. Fixed workload,
variable C: throughput(C) over identical content, so marginal efficiency
and the memory slope are content-controlled. Films are assigned lanes
round-robin (token i%M on RR; port i%8 on LI) exactly as the leg driver
does; an asyncio semaphore caps in-flight at C, and the point records its
in-flight high-water so "never saturated" is visible, not silent.

One POINT per invocation (the wrapper owns bring-ups and runs mem_watch
beside every point); posture env read-back is fail-closed before anything
runs (imported one-copy from probe_films_sizing — a cell that cannot prove
its posture is not quoted). Per point: batch span, total frames (per-film
observed vs expected_frames_measured, mismatches flagged per film),
frames/s, realtime factor, service CPU cores/util (cgroup delta, idle
lanes included — the envelope), probe ru_maxrss, per-film rows with errors
recorded never masked.

--summarize DIR computes and prints, from the measured points only:
  * the per-posture curve table (span, f/s, realtime, CPU, max anon,
    memory.peak, spool high-water, errors);
  * marginal efficiency per C step, probe_concurrency's rule verbatim
    ([throughput(C)/throughput(prev)] / [C/prev], probe_concurrency.py:15-17)
    with the first step below 0.7 flagged as the knee;
  * marginal GB per active lane between successive points (arm-summed
    anon; per-instance beside it).
It does NOT pick C — Ansh rules from the printed curve (RULING I).

Exit: 0 point/summary completed (per-film errors are recorded results) /
1 machinery, guard, or posture-mismatch refusal / 4 self-test failure.
"""

import argparse
import asyncio
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
sys.path.insert(0, str(Path(__file__).resolve().parent))       # probe/
from argtypes import positive_int          # noqa: E402 — register entry 8
from corpus_locator import resolve_corpus_dir  # noqa: E402 — one locator
# ONE COPY imports (entries 6/14):
from probe_detect_text import exc_chain, upload_chunked  # noqa: E402
from probe_films_sizing import CELLS, check_posture_env, cpu_usage_usec  # noqa: E402
from probe_rr import fresh_project_pipe    # noqa: E402
from driver_video import frames_from_chunks  # noqa: E402

PIPE_SRC = Path(__file__).resolve().parents[1] / 'benchmark_video_detect.pipe'
UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
KNEE_THRESHOLD = 0.7   # probe_concurrency.py:15-17, adopted verbatim


def preserve(path: Path):
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


def load_batch(manifest_path: Path, corpus_dir_arg):
    """The sweep batch: head doc of every strata cell, from OUR manifest's
    own meta (deterministic). Films are size-verified against their rows —
    the full sha verification is the build's job, already stamped."""
    lines = [json.loads(l) for l in manifest_path.read_text().splitlines()]
    meta = lines[0]['_meta']
    rows = {r['file']: r for r in lines[1:]}
    corpus_dir, src = resolve_corpus_dir(corpus_dir_arg, meta, manifest_path)
    per_cell = meta['strata']['per_cell']
    batch_docs = [docs[0] for cell, docs in sorted(per_cell.items())
                  if cell != 'envelope_forced' and docs]
    batch = []
    for doc in batch_docs:
        r = rows.get(doc)
        if r is None:
            raise SystemExit(f'NOT DONE — batch doc {doc} not in manifest rows')
        # STRUCTURAL, not incidental (Ruling J round): the sweep batch is
        # measured rows ONLY — a warm row reaching the batch means the
        # selection meta and the roles disagree, and the probe refuses
        # rather than quietly measuring warm content.
        if r.get('role') != 'measured':
            raise SystemExit(f'NOT DONE — batch doc {doc} has role='
                             f'{r.get("role")!r}; warm rows are never in the '
                             'sweep batch (warmed-never-measured)')
        p = corpus_dir / doc
        if not p.is_file() or p.stat().st_size != r['bytes']:
            raise SystemExit(f'NOT DONE — {doc}: missing or size mismatch in '
                             f'{corpus_dir} (run the build first)')
        batch.append({'file': doc, 'path': p, 'bytes': r['bytes'],
                      'video_s': r['video_s'],
                      'expected_frames': r['expected_frames_measured']})
    return batch, meta, corpus_dir, src


# ------------------------------------------------------------------- points

async def run_point_rr(cell, batch, concurrency, port, ttl):
    import os
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    client = RocketRideClient()
    await client.connect(timeout=60000)
    tokens = []
    try:
        for i in range(cell['tokens']):
            cfg = fresh_project_pipe(PIPE_SRC, f'curve-tok{i}')
            pth = PIPE_SRC.parent / 'probe' / f'generated_curve_tok{i}_{UTC}.pipe'
            pth.write_text(json.dumps(cfg, indent=1))
            started = await client.use(filepath=str(pth), ttl=ttl)
            tokens.append(started['token'])

        sem = asyncio.Semaphore(concurrency)
        inflight = {'now': 0, 'max': 0}
        results = []

        async def one(idx, film):
            async with sem:
                inflight['now'] += 1
                inflight['max'] = max(inflight['max'], inflight['now'])
                rec = {'file': film['file'], 'token_index': idx % len(tokens),
                       'admit_ns': time.monotonic_ns()}
                try:
                    up = await upload_chunked(client, tokens[idx % len(tokens)],
                                              film['path'], film['bytes'])
                    docs = (up['result'] or {}).get('documents') or []
                    contents = [d.get('page_content') or '' for d in docs]
                    rec['n_frames'] = frames_from_chunks(contents) if contents else None
                    rec['upload_wall_s'] = up['upload_wall_s']
                    rec['close_wall_s'] = up['close_wall_s']
                except Exception as exc:   # noqa: BLE001 — recorded, never masked
                    rec['error'] = exc_chain(exc)
                rec['done_ns'] = time.monotonic_ns()
                rec['wall_s'] = round((rec['done_ns'] - rec['admit_ns']) / 1e9, 2)
                inflight['now'] -= 1
                results.append(rec)

        await asyncio.gather(*[one(i, f) for i, f in enumerate(batch)])
        return results, inflight['max']
    finally:
        for tok in tokens:
            try:
                await asyncio.wait_for(client.terminate(tok), timeout=120)
            except Exception as exc:   # noqa: BLE001
                print(f'terminate {str(tok)[:16]}: {exc!r} (recorded; ttl reaps)')
        await client.disconnect()


async def run_point_li(batch, concurrency, ports):
    import urllib.request
    sem = asyncio.Semaphore(concurrency)
    inflight = {'now': 0, 'max': 0}
    results = []

    def post(film, port):
        with open(film['path'], 'rb') as fh:
            req = urllib.request.Request(
                f'http://127.0.0.1:{port}/process_video', data=fh,
                method='POST',
                headers={'Content-Type': 'application/octet-stream',
                         'Content-Length': str(film['bytes'])})
            with urllib.request.urlopen(req, timeout=14400) as resp:
                return json.load(resp)

    async def one(idx, film):
        async with sem:
            inflight['now'] += 1
            inflight['max'] = max(inflight['max'], inflight['now'])
            port = ports[idx % len(ports)]
            rec = {'file': film['file'], 'serving_port': port,
                   'admit_ns': time.monotonic_ns()}
            try:
                body = await asyncio.to_thread(post, film, port)
                if 'error' in body:
                    rec['error'] = [f'LI service error: {body}']
                else:
                    rec['n_frames'] = body.get('n_frames')
                    rec['bytes_spooled'] = body.get('bytes_spooled')
                    rec['frames_dir_bytes'] = body.get('frames_dir_bytes')
            except Exception as exc:   # noqa: BLE001
                rec['error'] = exc_chain(exc)
            rec['done_ns'] = time.monotonic_ns()
            rec['wall_s'] = round((rec['done_ns'] - rec['admit_ns']) / 1e9, 2)
            inflight['now'] -= 1
            results.append(rec)

    await asyncio.gather(*[one(i, f) for i, f in enumerate(batch)])
    return results, inflight['max']


def point_metrics(results, batch, bracket_wall, cpu_before, cpu_after,
                  containers):
    ok = [r for r in results if 'error' not in r]
    errs = [r for r in results if 'error' in r]
    span_s = None
    if results:
        span_s = round((max(r['done_ns'] for r in results)
                        - min(r['admit_ns'] for r in results)) / 1e9, 2)
    exp = {b['file']: b['expected_frames'] for b in batch}
    mismatches = [{'file': r['file'], 'observed': r.get('n_frames'),
                   'expected': exp.get(r['file'])}
                  for r in ok if r.get('n_frames') != exp.get(r['file'])]
    total_frames = sum(r.get('n_frames') or 0 for r in ok)
    footage = sum(b['video_s'] for b in batch
                  if b['file'] in {r['file'] for r in ok})
    deltas = {c: cpu_after[c] - cpu_before[c] for c in containers
              if cpu_before.get(c) is not None and cpu_after.get(c) is not None}
    cores = round(sum(deltas.values()) / 1e6 / bracket_wall, 2) if deltas else None
    return {
        'span_s': span_s,
        'n_films': len(results), 'n_ok': len(ok), 'n_errors': len(errs),
        'total_frames': total_frames,
        'frames_per_s': round(total_frames / span_s, 3) if span_s else None,
        'realtime_factor': round(footage / span_s, 2) if span_s and footage else None,
        'frame_expectation_mismatches': mismatches or None,
        'service_cpu': {'cores': cores,
                        'util_pct': round(100 * cores / 32, 1) if cores else None,
                        'basis': 'cgroup cpu.stat usage_usec delta over the '
                                 f'point wall ({bracket_wall}s), summed over '
                                 f'{len(deltas)}/{len(containers)} containers; '
                                 'idle lanes included; util against 32 vCPU'},
    }


# ---------------------------------------------------------------- summarize

def curve_rows(points):
    """points: list of dicts with C, frames_per_s, anon_sum... sorted by C.
    Returns the marginal columns (probe_concurrency.py:15-17 rule verbatim;
    knee = first step with marginal efficiency < KNEE_THRESHOLD)."""
    rows, knee_at = [], None
    for i, p in enumerate(points):
        row = dict(p)
        if i > 0 and points[i - 1].get('frames_per_s') and p.get('frames_per_s'):
            prev = points[i - 1]
            marg = ((p['frames_per_s'] / prev['frames_per_s'])
                    / (p['C'] / prev['C']))
            row['marginal_efficiency'] = round(marg, 3)
            if knee_at is None and marg < KNEE_THRESHOLD:
                knee_at = p['C']
            if (p.get('anon_sum') is not None
                    and prev.get('anon_sum') is not None):
                row['marginal_gb_per_lane'] = round(
                    (p['anon_sum'] - prev['anon_sum'])
                    / (p['C'] - prev['C']) / 1e9, 3)
        rows.append(row)
    return rows, knee_at


def summarize(out_dir: Path) -> int:
    print(f'CURVE SUMMARY over {out_dir} '
          f'(knee rule: marginal efficiency < {KNEE_THRESHOLD}, '
          'probe_concurrency.py:15-17 verbatim; C is NOT picked here — '
          'Ansh rules from this table, RULING I)')
    any_points = False
    for cell in sorted(CELLS):
        points = []
        for art in sorted(out_dir.glob(f'curve_{cell}_C*.json')):
            d = json.loads(art.read_text())
            mw_path = out_dir / f'memwatch_{cell}_C{d["concurrency"]}.json'
            anon_sum = peak_max = spool_max = None
            per_instance_anon = None
            if mw_path.exists():
                mw = json.loads(mw_path.read_text())['containers']
                anons = [v.get('max_anon_bytes') for v in mw.values()
                         if v.get('max_anon_bytes') is not None]
                peaks = [v.get('max_memory_peak_bytes') for v in mw.values()
                         if v.get('max_memory_peak_bytes') is not None]
                spools = [v.get('max_spool_used_bytes') for v in mw.values()
                          if v.get('max_spool_used_bytes') is not None]
                anon_sum = sum(anons) if anons else None
                per_instance_anon = max(anons) if anons else None
                peak_max = max(peaks) if peaks else None
                spool_max = max(spools) if spools else None
            m = d['metrics']
            points.append({
                'C': d['concurrency'], 'span_s': m['span_s'],
                'frames_per_s': m['frames_per_s'],
                'realtime_factor': m['realtime_factor'],
                'cores': m['service_cpu']['cores'],
                'util_pct': m['service_cpu']['util_pct'],
                'anon_sum': anon_sum,
                'anon_max_instance': per_instance_anon,
                'memory_peak_max': peak_max, 'spool_max': spool_max,
                'errors': m['n_errors'],
                'saturated': d['inflight_max'] >= min(d['concurrency'],
                                                      d['n_films']),
                'probe_ru_maxrss_kb': d.get('probe_ru_maxrss_kb'),
            })
        if not points:
            continue
        any_points = True
        points.sort(key=lambda p: p['C'])
        rows, knee_at = curve_rows(points)
        print(f'\n== {cell} ==')
        for r in rows:
            flags = ('' if r['errors'] == 0 else f' ERRORS={r["errors"]}') + \
                    ('' if r['saturated'] else ' NEVER-SATURATED')
            print(f"  C={r['C']}: span {r['span_s']}s | {r['frames_per_s']} f/s "
                  f"| rt x{r['realtime_factor']} | {r['cores']} cores "
                  f"({r['util_pct']}%) | anon sum {r['anon_sum']} B "
                  f"(max/inst {r['anon_max_instance']}) | mem.peak "
                  f"{r['memory_peak_max']} | spool {r['spool_max']}"
                  + (f" | marg-eff {r['marginal_efficiency']}"
                     if 'marginal_efficiency' in r else '')
                  + (f" | marg GB/lane {r['marginal_gb_per_lane']}"
                     if 'marginal_gb_per_lane' in r else '') + flags)
        print(f"  knee (first marg-eff < {KNEE_THRESHOLD}): "
              f"{'C=' + str(knee_at) if knee_at else 'none within swept range'}")
    if not any_points:
        print('no point artifacts found')
        return 1
    return 0


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    pts = [{'C': 1, 'frames_per_s': 10.0, 'anon_sum': 9_000_000_000},
           {'C': 2, 'frames_per_s': 19.0, 'anon_sum': 9_700_000_000},
           {'C': 4, 'frames_per_s': 30.0, 'anon_sum': 11_100_000_000},
           {'C': 8, 'frames_per_s': 33.0, 'anon_sum': 13_900_000_000}]
    rows, knee = curve_rows(pts)
    check('marginal efficiency: C=2 step = (19/10)/2 = 0.95',
          rows[1]['marginal_efficiency'] == 0.95)
    check('marginal efficiency: C=4 step = (30/19)/2 ~ 0.789',
          rows[2]['marginal_efficiency'] == 0.789)
    check('knee flagged at C=8 ((33/30)/2 = 0.55 < 0.7)',
          rows[3]['marginal_efficiency'] == 0.55 and knee == 8)
    check('marginal GB/lane: C=2 step = 0.7 GB',
          rows[1]['marginal_gb_per_lane'] == 0.7)
    check('marginal GB/lane: C=8 step = (13.9-11.1)/4 = 0.7 GB',
          rows[3]['marginal_gb_per_lane'] == 0.7)
    rows2, knee2 = curve_rows(pts[:2])
    check('no knee within range -> none', knee2 is None)
    check('cells table still the measured postures (sweep reuses them)',
          CELLS['rr-8x4']['tokens'] == 8 and CELLS['rr-default']['tokens'] == 1
          and CELLS['li-8x4']['instances'] == 8)
    check('knee threshold is probe_concurrency\'s 0.7, verbatim',
          KNEE_THRESHOLD == 0.7)

    # STRUCTURAL warm exclusion: a per_cell head with role='warm' is REFUSED.
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus = d / 'corpus'
        corpus.mkdir()
        (corpus / 'w.mp4').write_bytes(b'x' * 10)
        man = d / 'm.jsonl'
        meta = {'_meta': {'corpus_dir': str(corpus.resolve()),
                          'strata': {'per_cell': {'D0xB0': ['w.mp4']}}}}
        row = {'file': 'w.mp4', 'bytes': 10, 'video_s': 1.0,
               'expected_frames_measured': 1, 'role': 'warm'}
        man.write_text(json.dumps(meta) + '\n' + json.dumps(row) + '\n')
        try:
            load_batch(man, None)
            check('warm row in the batch is REFUSED (structural)', False)
        except SystemExit as e:
            check('warm row in the batch is REFUSED (structural)',
                  'warmed-never-measured' in str(e))
        row['role'] = 'measured'
        man.write_text(json.dumps(meta) + '\n' + json.dumps(row) + '\n')
        batch, _, _, _ = load_batch(man, None)
        check('measured row passes the same gate', len(batch) == 1)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--cell', choices=sorted(CELLS))
    ap.add_argument('--concurrency', type=positive_int('concurrency', 64))
    ap.add_argument('--manifest',
                    default=str(Path(__file__).resolve().parents[1]
                                / 'films_video_manifest.jsonl'))
    ap.add_argument('--corpus-dir', default=None,
                    help='must AGREE with the manifest stamp (corpus_locator)')
    ap.add_argument('--containers')
    ap.add_argument('--port', type=positive_int('port', 65535), default=None)
    ap.add_argument('--ttl', type=positive_int('ttl', 86400), default=7200)
    ap.add_argument('--out-dir', default=None)
    ap.add_argument('--summarize', default=None,
                    help='directory of point artifacts — print the curve, '
                         'the marginals, and the knee; no measurement')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.summarize:
        return summarize(Path(args.summarize).expanduser())
    for req in ('cell', 'concurrency', 'containers'):
        if not getattr(args, req):
            ap.error(f'--{req} is required for a point '
                     '(unless --self-test/--summarize)')

    cell = CELLS[args.cell]
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_file():
        raise SystemExit(f'NOT DONE — subset manifest not found: {manifest_path}')
    batch, meta, corpus_dir, src = load_batch(manifest_path, args.corpus_dir)
    containers = [c.strip() for c in args.containers.split(',') if c.strip()]
    check_posture_env(containers, cell['env'])   # fail-closed, entry 12
    port = args.port or (5565 if cell['arm'] == 'rr' else 8802)
    out_dir = Path(args.out_dir).expanduser() if args.out_dir \
        else Path.home() / 'films_probe' / 'curve_out'
    out_dir.mkdir(parents=True, exist_ok=True)

    repo = Path(__file__).resolve().parents[3]
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    print(f'point {args.cell} C={args.concurrency}: batch of {len(batch)} '
          f'films (strata heads), corpus {corpus_dir} [{src}]')

    cpu_before = {c: cpu_usage_usec(c) for c in containers}
    t0 = time.monotonic()
    if cell['arm'] == 'rr':
        results, inflight_max = asyncio.run(
            run_point_rr(cell, batch, args.concurrency, port, args.ttl))
    else:
        ports = [8802 + i for i in range(cell['instances'])]
        results, inflight_max = asyncio.run(
            run_point_li(batch, args.concurrency, ports))
    bracket_wall = round(time.monotonic() - t0, 2)
    cpu_after = {c: cpu_usage_usec(c) for c in containers}

    metrics = point_metrics(results, batch, bracket_wall,
                            cpu_before, cpu_after, containers)
    artifact = {
        'probe': 'films_curve', 'created_utc': UTC, 'git_head': head,
        'cell': args.cell, 'concurrency': args.concurrency,
        'posture': cell, 'containers': containers,
        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'batch': [{'file': b['file'], 'bytes': b['bytes'],
                   'video_s': b['video_s'],
                   'expected_frames': b['expected_frames']} for b in batch],
        'inflight_max': inflight_max,
        'per_film': sorted(results, key=lambda r: r['admit_ns']),
        'metrics': metrics,
        'probe_ru_maxrss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'memory_note': "anon/memory.peak/spool are mem_watch's, recorded "
                       'beside this artifact by the wrapper',
    }
    out = out_dir / f'curve_{args.cell}_C{args.concurrency}.json'
    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back
    m = rb['metrics']
    print(f"POINT {args.cell} C={args.concurrency}: span {m['span_s']}s | "
          f"{m['frames_per_s']} f/s | rt x{m['realtime_factor']} | "
          f"{m['service_cpu']['cores']} cores | errors {m['n_errors']} | "
          f"inflight max {rb['inflight_max']}"
          + (' | EXPECTATION MISMATCHES: '
             + json.dumps(m['frame_expectation_mismatches'])
             if m['frame_expectation_mismatches'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
