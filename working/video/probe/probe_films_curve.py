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
its posture is not quoted), and so is the LI chunk-config read-back
(RULING L: 4000/0/chars from /health on EVERY instance — a stale li:video
image is refused, never silently measured at the wrong workload). Per point: batch span, total frames (per-film
observed vs expected_frames_measured, mismatches flagged per film),
frames/s, realtime factor, service CPU cores/util (cgroup delta, idle
lanes included — the envelope), probe ru_maxrss, per-film rows with errors
recorded never masked.

--summarize DIR computes and prints, from the measured points only:
  * the per-posture curve table (span, f/s, realtime, inflight, CPU, max
    anon, memory.peak, spool high-water, probe rss, errors), chains grouped
    by (label, BATCH) — a chain never spans batches (different workloads);
  * marginal efficiency per C step, probe_concurrency's rule verbatim
    ([throughput(C)/throughput(prev)] / [C/prev], probe_concurrency.py:15-17)
    with the first step below 0.7 flagged as the knee — computed ONLY
    between points that realized their requested C (inflight_max >= C);
    an unrealized step reports MARG NOT MEASURED and blocks the knee to
    NOT DETERMINED (2026-08-31: C=16/32 on the 9-film heads batch were
    the same experiment twice at inflight 9);
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
import re
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
from driver_video import EXPECTED_LI_CHUNK, frames_from_chunks  # noqa: E402

PIPE_SRC = Path(__file__).resolve().parents[1] / 'benchmark_video_detect.pipe'
UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
KNEE_THRESHOLD = 0.7   # probe_concurrency.py:15-17, adopted verbatim

# RULING L (2026-08-30) expectation — ONE copy, imported from driver_video
# (Ruling T item 3, 2026-08-31, moved there so the LEG preflight and this
# sweep probe consult the same object; the import edge already ran
# probe -> driver, so the constant lives at the importee).


def check_li_chunk_config(ports, fetch=None):
    """Fail-closed chunk-config read-back on EVERY LI instance (entry 12:
    a value that sets a run parameter has a read-back before it is
    quotable, and the read-back is half of the measurement). Reads /health
    — the values the serving process LOADED, not the image's declaration.
    `fetch` is injectable for the null-controlled self-test. An absent
    field is an ABSENCE failure, never treated as agreement."""
    if fetch is None:
        import urllib.request

        def fetch(p):
            with urllib.request.urlopen(
                    f'http://127.0.0.1:{p}/health', timeout=30) as r:
                return json.load(r)
    got, bad = {}, {}
    for p in ports:
        h = fetch(p)                       # one GET per instance
        vals = {k: h.get(k) for k in EXPECTED_LI_CHUNK}
        got[p] = vals
        if vals != EXPECTED_LI_CHUNK:
            bad[p] = vals
    if bad:
        raise SystemExit(
            f'NOT DONE — LI chunk-config read-back does not match RULING L '
            f'(expected {EXPECTED_LI_CHUNK}): {bad}. A 4000/200 read-back '
            f'means a stale li:video image — rebuild and verify per '
            f'probe/run_ruling_l_box.sh before any posture point.')
    return {'expected': EXPECTED_LI_CHUNK, 'per_port': got}


def preserve(path: Path):
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


def load_batch(manifest_path: Path, corpus_dir_arg, batch_mode: str = 'heads'):
    """The sweep batch, deterministic from OUR manifest:
      'heads'    — head doc of every strata cell (the RULING-I C-sweep
                   batch: 9 films, ~12.6 h footage);
      'measured' — every role='measured' row in manifest row order (the
                   RULING-K posture-sweep batch: the full 35, ~49.3 h — a
                   9-film batch cannot saturate M>=16 lanes).
    Warm rows are excluded STRUCTURALLY in both modes (role guard).
    Films are size-verified against their rows — the full sha verification
    is the build's job, already stamped."""
    lines = [json.loads(l) for l in manifest_path.read_text().splitlines()]
    meta = lines[0]['_meta']
    rows = {r['file']: r for r in lines[1:]}
    corpus_dir, src = resolve_corpus_dir(corpus_dir_arg, meta, manifest_path)
    if batch_mode == 'measured':
        batch_docs = [r['file'] for r in lines[1:] if r.get('role') == 'measured']
    else:
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

def build_point_artifact(*, head, label, concurrency, batch_mode, lanes,
                         env_n, posture, containers, chunk_config_readback,
                         oom, manifest_sha256, batch, inflight_max,
                         per_film, metrics, probe_ru_maxrss_kb):
    """The ONE success-artifact shape — main() writes through this and the
    self-test builds its summarize fixtures through it (entry 27 addendum,
    2026-08-30): --summarize died on its FIRST real artifacts because
    _point_row read a top-level 'n_films' the producer NEVER wrote — the
    reader was born disagreeing with the writer at d73f445, and the 21c6ff2
    fixture was hand-shaped to the READER's expectation, so 23 green checks
    certified the bug. A hand-written fixture is the author's memory of the
    schema sampled against the author's code (entry 2, inside the test);
    a producer-built fixture makes that class unwritable."""
    return {
        'probe': 'films_curve', 'created_utc': UTC, 'git_head': head,
        'cell': label, 'label': label, 'concurrency': concurrency,
        'batch_mode': batch_mode, 'lanes': lanes,
        'spend_threads': (lanes * env_n) if env_n else None,
        'posture': posture, 'containers': containers,
        'chunk_config_readback': chunk_config_readback,
        'oom': oom,
        'manifest_sha256': manifest_sha256,
        'batch': [{'file': b['file'], 'bytes': b['bytes'],
                   'video_s': b['video_s'],
                   'expected_frames': b['expected_frames']} for b in batch],
        'inflight_max': inflight_max,
        'per_film': sorted(per_film, key=lambda r: r['admit_ns']),
        'metrics': metrics,
        'probe_ru_maxrss_kb': probe_ru_maxrss_kb,
        'memory_note': "anon/memory.peak/spool are mem_watch's, recorded "
                       'beside this artifact by the wrapper',
    }


def build_failed_artifact(*, head, label, concurrency, batch_mode, lanes,
                          posture, containers, chunk_config_readback, oom,
                          exception_chain):
    """The ONE failed-point shape (same rule as build_point_artifact)."""
    return {
        'probe': 'films_curve', 'created_utc': UTC, 'git_head': head,
        'FAILED': {'stage': 'point-execution',
                   'exception_chain': exception_chain},
        'cell': label, 'label': label, 'concurrency': concurrency,
        'batch_mode': batch_mode, 'lanes': lanes, 'posture': posture,
        'containers': containers,
        'chunk_config_readback': chunk_config_readback,
        'oom': oom,
        'note': 'point-level failure (connect/use/gather machinery) — '
                'per-film errors would have been recorded instead; the '
                'oom block above says whether the kernel killed anything; '
                "mem_watch's last ticks carry the anon at failure",
    }


def _c_realized(p) -> bool:
    """Did this point actually RUN at its requested C? False when the batch
    (or anything else) capped in-flight below C — the 2026-08-31 C sweep ran
    C=16/32 on the 9-film heads batch: inflight_max 9 at both, so the two
    points were the same experiment twice and every marginal computed with
    those C values was arithmetic on concurrency that never happened. An
    absent inflight_max is ABSENCE, never realization. (Distinct from the
    'saturated' flag, whose min(C, n_films) asks 'did we reach the batch's
    achievable bound' — TRUE at C=16 on 9 films, which is exactly why it
    could not refuse this.)"""
    return (p.get('inflight_max') is not None
            and p['inflight_max'] >= p['C'])


def curve_rows(points):
    """points: _point_row dicts sorted by C — ONE label, ONE batch (summarize
    groups by both; a chain must never span batches: heads and measured are
    different workloads, so a cross-batch step confounds delta-C with
    delta-content). Marginal columns per probe_concurrency.py:15-17 verbatim,
    computed ONLY between two points that BOTH realized their requested C
    (inflight_max >= C); otherwise the step is NOT MEASURED with the reason —
    the CANNOT-COMPARE discipline (entry 14): a computation that cannot mean
    what it says must not print a number. knee: first MEASURED step below
    KNEE_THRESHOLD; 'NOT DETERMINED' the moment the walk meets an unrealized
    step before any measured knee — the knee cannot be located across
    fictional concurrency."""
    rows, knee_at = [], None
    knee_blocked = False
    for i, p in enumerate(points):
        row = dict(p)
        if i > 0 and points[i - 1].get('frames_per_s') and p.get('frames_per_s'):
            prev = points[i - 1]
            if _c_realized(prev) and _c_realized(p):
                marg = ((p['frames_per_s'] / prev['frames_per_s'])
                        / (p['C'] / prev['C']))
                row['marginal_efficiency'] = round(marg, 3)
                if knee_at is None and not knee_blocked and marg < KNEE_THRESHOLD:
                    knee_at = p['C']
                if (p.get('anon_sum') is not None
                        and prev.get('anon_sum') is not None):
                    row['marginal_gb_per_lane'] = round(
                        (p['anon_sum'] - prev['anon_sum'])
                        / (p['C'] - prev['C']) / 1e9, 3)
            else:
                bad = p if not _c_realized(p) else prev
                row['marginal_not_measured'] = (
                    f"inflight_max {bad.get('inflight_max')} < requested "
                    f"C={bad['C']} (batch n_films {bad.get('n_films')}) — "
                    'this concurrency never happened')
                if knee_at is None:
                    knee_blocked = True
        rows.append(row)
    if knee_at is None and knee_blocked:
        return rows, 'NOT DETERMINED'
    return rows, knee_at


def _point_row(d: dict, out_dir: Path) -> dict:
    label = d.get('label') or d['cell']
    mw_path = out_dir / f'memwatch_{label}_C{d["concurrency"]}.json'
    anon_sum = peak_max = spool_max = per_instance_anon = None
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
    # n_films lives in metrics — the producer's ONLY copy since d73f445;
    # the old top-level read here was born disagreeing with the writer and
    # first executed against real artifacts on 2026-08-30 (KeyError, whole
    # matrix). Absent value -> saturation is NOT KNOWN (None), never
    # computed from a guess.
    n_films = m.get('n_films')
    saturated = (d['inflight_max'] >= min(d['concurrency'], n_films)
                 if n_films is not None and d.get('inflight_max') is not None
                 else None)
    return {
        'label': label, 'C': d['concurrency'],
        'lanes': d.get('lanes'), 'spend_threads': d.get('spend_threads'),
        'batch_mode': d.get('batch_mode'),
        'n_films': n_films, 'inflight_max': d.get('inflight_max'),
        'span_s': m['span_s'], 'frames_per_s': m['frames_per_s'],
        'realtime_factor': m['realtime_factor'],
        'cores': m['service_cpu']['cores'],
        'util_pct': m['service_cpu']['util_pct'],
        'anon_sum': anon_sum, 'anon_max_instance': per_instance_anon,
        'memory_peak_max': peak_max, 'spool_max': spool_max,
        'errors': m['n_errors'],
        'saturated': saturated,
        'probe_ru_maxrss_kb': d.get('probe_ru_maxrss_kb'),
    }


def _sat_flag(saturated) -> str:
    """Three states, printed distinctly: a point that cannot report
    saturation says NOT KNOWN — it is never allowed to read as saturated
    OR as never-saturated."""
    return {True: '', False: ' NEVER-SATURATED'}.get(
        saturated, ' SATURATION-NOT-KNOWN')


def summarize(out_dir: Path) -> int:
    print(f'CURVE SUMMARY over {out_dir} — nothing is picked here: Ansh '
          'rules posture from the cross-posture table (RULING K) and C from '
          f'the per-posture marginal chain (RULING I; knee = first marginal '
          f'efficiency < {KNEE_THRESHOLD}, probe_concurrency.py:15-17 verbatim)')
    by_label = {}
    failed_points = []
    for art in sorted(out_dir.glob('curve_*.json')):
        d = json.loads(art.read_text())
        if 'FAILED' in d:
            failed_points.append(d)
            continue
        row = _point_row(d, out_dir)
        # Chains are per (label, batch): heads and measured are DIFFERENT
        # workloads (9 films/12.59 h vs 35/49.33 h), so a marginal step
        # across them would confound delta-C with delta-content
        # (2026-08-31 ruling round; the probe's fixed-workload contract).
        by_label.setdefault((row['label'], row['batch_mode'] or '?'),
                            []).append(row)
    for d in failed_points:
        print(f"  FAILED POINT (a finding, not a gap): {d.get('label')} "
              f"C={d.get('concurrency')} — oom={json.dumps(d.get('oom'))}; "
              f"chain={d['FAILED'].get('exception_chain')}")
    if not by_label and not failed_points:
        print('no point artifacts found')
        return 1
    if not by_label:
        return 0   # only failed points — reported above, evidence preserved

    all_rows = []
    for label, batch_mode in sorted(by_label):
        points = sorted(by_label[(label, batch_mode)], key=lambda p: p['C'])
        rows, knee_at = curve_rows(points)
        all_rows.extend(rows)
        print(f'\n== {label} [batch {batch_mode}] ==')
        for r in rows:
            flags = ('' if r['errors'] == 0 else f' ERRORS={r["errors"]}') + \
                    _sat_flag(r['saturated'])
            print(f"  C={r['C']}: span {r['span_s']}s | {r['frames_per_s']} f/s "
                  f"| rt x{r['realtime_factor']} | inflight {r['inflight_max']} "
                  f"| {r['cores']} cores "
                  f"({r['util_pct']}%) | anon sum {r['anon_sum']} B "
                  f"(max/inst {r['anon_max_instance']}) | mem.peak "
                  f"{r['memory_peak_max']} | spool {r['spool_max']} "
                  f"| probe rss {r['probe_ru_maxrss_kb']} KB"
                  + (f" | marg-eff {r['marginal_efficiency']}"
                     if 'marginal_efficiency' in r else '')
                  + (f" | marg GB/lane {r['marginal_gb_per_lane']}"
                     if 'marginal_gb_per_lane' in r else '')
                  + (f" | MARG NOT MEASURED: {r['marginal_not_measured']}"
                     if r.get('marginal_not_measured') else '') + flags)
        if len(points) > 1:
            if knee_at == 'NOT DETERMINED':
                print(f'  knee (first marg-eff < {KNEE_THRESHOLD}): NOT '
                      'DETERMINED — the chain contains a point that never '
                      'ran at its requested C at/before the first '
                      'sub-threshold step (see MARG NOT MEASURED rows)')
            else:
                print(f"  knee (first marg-eff < {KNEE_THRESHOLD}): "
                      f"{'C=' + str(knee_at) if knee_at else 'none within swept range'}")

    # Cross-posture table (RULING K / Crossroad 17): the full matrix for BOTH
    # arms, published beside whatever gets chosen — sorted by throughput,
    # spend printed so under/full/over-subscription reads at a glance.
    print('\n== POSTURE MATRIX (all arms, all points; sorted by frames/s; '
          'no winner picked) ==')
    for r in sorted(all_rows, key=lambda x: -(x['frames_per_s'] or 0)):
        print(f"  {r['label']} C={r['C']} [{r.get('batch_mode')}]: "
              f"{r['frames_per_s']} f/s | rt x{r['realtime_factor']} | "
              f"lanes {r['lanes']} x env = spend {r['spend_threads']} threads "
              f"| {r['cores']} cores ({r['util_pct']}%) | anon sum "
              f"{r['anon_sum']} B | mem.peak {r['memory_peak_max']}"
              + ('' if r['errors'] == 0 else f' | ERRORS={r["errors"]}')
              + _sat_flag(r['saturated']))
    return 0


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    pts = [{'C': 1, 'frames_per_s': 10.0, 'anon_sum': 9_000_000_000,
            'inflight_max': 1, 'n_films': 35},
           {'C': 2, 'frames_per_s': 19.0, 'anon_sum': 9_700_000_000,
            'inflight_max': 2, 'n_films': 35},
           {'C': 4, 'frames_per_s': 30.0, 'anon_sum': 11_100_000_000,
            'inflight_max': 4, 'n_films': 35},
           {'C': 8, 'frames_per_s': 33.0, 'anon_sum': 13_900_000_000,
            'inflight_max': 8, 'n_films': 35}]
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

    # 2026-08-31: the C-realization gate. The heads batch capped inflight at
    # 9 while C=16/32 were requested; the old chain divided by concurrency
    # that never happened and printed a fictional knee. NOT MEASURED / NOT
    # DETERMINED, never a number (entry 14's CANNOT-COMPARE discipline).
    pts_u = [{'C': 4, 'frames_per_s': 4.0, 'inflight_max': 4, 'n_films': 9},
             {'C': 8, 'frames_per_s': 6.9, 'inflight_max': 8, 'n_films': 9},
             {'C': 16, 'frames_per_s': 6.64, 'inflight_max': 9, 'n_films': 9},
             {'C': 32, 'frames_per_s': 6.42, 'inflight_max': 9, 'n_films': 9}]
    rows_u, knee_u = curve_rows(pts_u)
    check('unrealized C: marg-eff NOT MEASURED with the full reason, '
          'never a number',
          'marginal_efficiency' not in rows_u[2]
          and 'inflight_max 9 < requested C=16'
              in rows_u[2]['marginal_not_measured']
          and 'n_films 9' in rows_u[2]['marginal_not_measured']
          and 'marginal_efficiency' not in rows_u[3])
    check('knee NOT DETERMINED when an unrealized step precedes any '
          'sub-threshold reading', knee_u == 'NOT DETERMINED')
    pts_k = [{'C': 1, 'frames_per_s': 10.0, 'inflight_max': 1, 'n_films': 9},
             {'C': 2, 'frames_per_s': 11.0, 'inflight_max': 2, 'n_films': 9},
             {'C': 16, 'frames_per_s': 12.0, 'inflight_max': 9, 'n_films': 9}]
    rows_k, knee_k = curve_rows(pts_k)
    check('a knee found on MEASURED steps before the unrealized tail stands',
          knee_k == 2 and rows_k[1]['marginal_efficiency'] == 0.55
          and 'marginal_not_measured' in rows_k[2])
    rows_a, knee_a = curve_rows(
        [{'C': 1, 'frames_per_s': 10.0, 'inflight_max': 1, 'n_films': 9},
         {'C': 2, 'frames_per_s': 19.0, 'n_films': 9}])
    check('ABSENT inflight_max is absence, never realization',
          'marginal_not_measured' in rows_a[1] and knee_a == 'NOT DETERMINED')
    check('cells table still the measured postures (sweep reuses them)',
          CELLS['rr-8x4']['tokens'] == 8 and CELLS['rr-default']['tokens'] == 1
          and CELLS['li-8x4']['instances'] == 8)
    check('knee threshold is probe_concurrency\'s 0.7, verbatim',
          KNEE_THRESHOLD == 0.7)

    # RULING K: dynamic posture resolution + labels.
    from types import SimpleNamespace as NS
    p1, l1 = resolve_posture(NS(cell=None, arm='rr', tokens=16,
                                instances=None, threads_env='2'))
    check("dynamic RR posture: rr_M16xT2, env '2'",
          l1 == 'rr_M16xT2' and p1 == {'arm': 'rr', 'tokens': 16, 'env': '2'})
    p2, l2 = resolve_posture(NS(cell=None, arm='li', tokens=None,
                                instances=16, threads_env='2'))
    check('dynamic LI posture: li_N16xT2',
          l2 == 'li_N16xT2' and p2['instances'] == 16 and p2['env'] == '2')
    p3, l3 = resolve_posture(NS(cell='rr-8x4', arm=None, tokens=None,
                                instances=None, threads_env=None))
    check('legacy named cell still resolves (rr-8x4, 8 tokens)',
          l3 == 'rr-8x4' and p3['tokens'] == 8)
    p4, l4 = resolve_posture(NS(cell=None, arm='rr', tokens=32,
                                instances=None, threads_env='unset'))
    check("threads-env 'unset' -> env None, label T-unset",
          l4 == 'rr_M32xTunset' and p4['env'] is None)

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

        # RULING K batch mode: 'measured' takes every measured row in
        # manifest order and never a warm row.
        (corpus / 'a.mp4').write_bytes(b'y' * 5)
        (corpus / 'z.mp4').write_bytes(b'z' * 7)
        rows2 = [
            {'file': 'a.mp4', 'bytes': 5, 'video_s': 1.0,
             'expected_frames_measured': 1, 'role': 'measured'},
            {'file': 'w.mp4', 'bytes': 10, 'video_s': 1.0,
             'expected_frames_measured': 1, 'role': 'warm'},
            {'file': 'z.mp4', 'bytes': 7, 'video_s': 1.0,
             'expected_frames_measured': 1, 'role': 'measured'},
        ]
        man.write_text(json.dumps(meta) + '\n'
                       + '\n'.join(json.dumps(r) for r in rows2) + '\n')
        batch2, _, _, _ = load_batch(man, None, 'measured')
        check("batch 'measured': all measured rows in order, warm excluded",
              [b['file'] for b in batch2] == ['a.mp4', 'z.mp4'])

        # OOM instrumentation: delta math + FAILED artifacts surfaced, not
        # crashed on (the 32x1 stress-point requirement).
        check('oom_delta: per-container delta and the after-flag',
              oom_delta({'c': {'oomkilled': 'false', 'oom_kill_events': 2}},
                        {'c': {'oomkilled': 'true', 'oom_kill_events': 5}})
              == {'c': {'oomkilled': 'true', 'oom_kill_delta': 3}})
        sweep = d / 'sweep'
        sweep.mkdir()
        # ENTRY 27 addendum (2026-08-30): fixtures come from the PRODUCER
        # chain (point_metrics -> build_point_artifact), never hand-shaped —
        # the --summarize KeyError('n_films') survived 23 green checks
        # because the old fixture was written to the READER's expectation.
        # This block therefore also EXECUTES point_metrics for the first
        # time (it was on the entry-27 never-executed list).
        canned_batch = [
            {'file': 'a.mp4', 'bytes': 5, 'video_s': 600.0,
             'expected_frames': 40},
            {'file': 'z.mp4', 'bytes': 7, 'video_s': 900.0,
             'expected_frames': 60},
        ]
        canned_results = [
            {'file': 'a.mp4', 'token_index': 0, 'admit_ns': 1_000,
             'done_ns': 50_000_000_000, 'wall_s': 50.0, 'n_frames': 40},
            {'file': 'z.mp4', 'token_index': 1, 'admit_ns': 2_000,
             'done_ns': 100_000_000_000, 'wall_s': 100.0, 'n_frames': 60},
        ]
        mets = point_metrics(canned_results, canned_batch, 100.0,
                             {'rr': 0}, {'rr': 2_000_000_000}, ['rr'])
        check('point_metrics on canned rows: n_films/frames/cores clean',
              mets['n_films'] == 2 and mets['total_frames'] == 100
              and mets['frame_expectation_mismatches'] is None
              and mets['service_cpu']['cores'] == 20.0)
        good = build_point_artifact(
            head='selftest', label='rr_M8xT4', concurrency=16,
            batch_mode='measured', lanes=8, env_n=4, posture={'arm': 'rr'},
            containers=['rr'], chunk_config_readback={'arm': 'rr'},
            oom={'rr': {'oomkilled': 'false', 'oom_kill_delta': 0}},
            manifest_sha256='0' * 64, batch=canned_batch, inflight_max=16,
            per_film=canned_results, metrics=mets, probe_ru_maxrss_kb=1234)
        (sweep / 'curve_rr_M8xT4_C16.json').write_text(json.dumps(good))
        failed = build_failed_artifact(
            head='selftest', label='rr_M32xT1', concurrency=35,
            batch_mode='measured', lanes=32, posture={'arm': 'rr'},
            containers=['rr'], chunk_config_readback={'arm': 'rr'},
            oom={'rr': {'oomkilled': 'true', 'oom_kill_delta': 1}},
            exception_chain=['X'])
        (sweep / 'curve_rr_M32xT1_C35.json').write_text(json.dumps(failed))
        check('summarize survives a FAILED point beside a good one (rc 0), '
              'both artifacts producer-built',
              summarize(sweep) == 0)
        row = _point_row(json.loads(
            (sweep / 'curve_rr_M8xT4_C16.json').read_text()), sweep)
        check("saturation from the producer's own metrics.n_films "
              '(inflight 16 >= min(C=16, n_films=2))',
              row['saturated'] is True and row['span_s'] == 100.0
              and row['probe_ru_maxrss_kb'] == 1234)
        nk = dict(good)
        nk['metrics'] = {k: v for k, v in mets.items() if k != 'n_films'}
        check('absent n_films -> saturation NOT KNOWN (None), never guessed',
              _point_row(nk, sweep)['saturated'] is None
              and _sat_flag(None) == ' SATURATION-NOT-KNOWN'
              and _sat_flag(False) == ' NEVER-SATURATED'
              and _sat_flag(True) == '')
        # memwatch sidecar: the REAL mem_watch summary schema (containers ->
        # max_*_bytes, mem_watch.py:141-160) so the anon/peak/spool columns
        # are exercised with the shape the box actually writes.
        (sweep / 'memwatch_rr_M8xT4_C16.json').write_text(json.dumps(
            {'basis': {}, 'containers': {
                'rr': {'max_anon_bytes': 9_000_000_000,
                       'max_memory_peak_bytes': 11_000_000_000,
                       'max_spool_used_bytes': 2_000_000_000}}}))
        row2 = _point_row(good, sweep)
        check('memwatch sidecar read: anon/peak/spool populate from the '
              'real schema', row2['anon_sum'] == 9_000_000_000
              and row2['anon_max_instance'] == 9_000_000_000
              and row2['memory_peak_max'] == 11_000_000_000
              and row2['spool_max'] == 2_000_000_000)

        # 2026-08-31: chains never span batches — the same label at a
        # different batch_mode summarizes as its OWN chain (heads C<=8 and
        # measured high-C are different workloads; a cross-batch marginal
        # step would confound delta-C with delta-content).
        import contextlib
        import io
        good_h = build_point_artifact(
            head='selftest', label='rr_M8xT4', concurrency=32,
            batch_mode='heads', lanes=8, env_n=4, posture={'arm': 'rr'},
            containers=['rr'], chunk_config_readback={'arm': 'rr'},
            oom={'rr': {'oomkilled': 'false', 'oom_kill_delta': 0}},
            manifest_sha256='0' * 64, batch=canned_batch, inflight_max=2,
            per_film=canned_results, metrics=mets, probe_ru_maxrss_kb=1)
        (sweep / 'curve_rr_M8xT4_C32.json').write_text(json.dumps(good_h))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_split = summarize(sweep)
        out_txt = buf.getvalue()
        check('chains split by (label, batch): heads and measured groups '
              'both print, rc 0',
              rc_split == 0 and '[batch measured]' in out_txt
              and '[batch heads]' in out_txt)

    # RULING L chunk-config read-back: null-controlled (entry 12 — the
    # refusal paths must demonstrably fire, or the check checks nothing).
    rb = check_li_chunk_config([8802, 8803],
                               fetch=lambda p: dict(EXPECTED_LI_CHUNK))
    check('chunk read-back: matching /health passes, per-port recorded',
          rb['per_port'][8803] == EXPECTED_LI_CHUNK
          and rb['expected'] == EXPECTED_LI_CHUNK)
    try:
        check_li_chunk_config([8802], fetch=lambda p: {
            'chunk_size': 4000, 'chunk_overlap': 200, 'split_unit': 'chars'})
        check('chunk read-back: a 200 image is REFUSED naming both values',
              False)
    except SystemExit as e:
        check('chunk read-back: a 200 image is REFUSED naming both values',
              "'chunk_overlap': 200" in str(e) and "'chunk_overlap': 0" in str(e))
    try:
        check_li_chunk_config([8802], fetch=lambda p: {'chunk_size': 4000})
        check('chunk read-back: an ABSENT field is refused, never agreement',
              False)
    except SystemExit as e:
        check('chunk read-back: an ABSENT field is refused, never agreement',
              'None' in str(e))

    # ENTRY 27 (2026-08-30): oom_state() killed all 11 sweep points on a
    # missing `import re` — reachable only on a live box, invisible to this
    # suite. The canned runner EXECUTES the body (regex included) on the
    # exact shapes `docker inspect` and `grep oom_kill memory.events` emit.
    def _canned(argv, timeout=30):
        if 'inspect' in argv:
            return 0, 'false', ''
        return 0, 'oom_kill 3\noom_group_kill 0', ''
    check('oom_state: canned docker/memory.events outputs parse (the re '
          'path EXECUTES under self-test)',
          oom_state(['c1'], runner=_canned)
          == {'c1': {'oomkilled': 'false', 'oom_kill_events': 3}})
    check('oom_state: uninspectable container recorded, never raised',
          oom_state(['gone'], runner=lambda a, timeout=30: (1, '', 'no such'))
          ['gone'] == {'oomkilled': 'uninspectable', 'oom_kill_events': None})

    # ENTRY 27, the broad half: a green self-test must include "every name
    # in this tree resolves" — the functions only a live box reaches are
    # exactly the ones a self-test never executes. Lazy import: the live
    # point path is untouched.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # working/
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

def oom_state(containers, runner=None):
    """Per container: docker's OOMKilled flag (container init killed) AND the
    cgroup's memory.events oom_kill counter (child processes killed inside
    the cgroup — the likelier films failure: the kernel kills a task/worker
    process while the container survives). The run_proof_layer2.sh pattern,
    promoted into every point so an OOM is distinguishable in the artifact
    from a timeout or an application error. `runner` is injectable (entry 27:
    this function killed the whole 2026-08-30 sweep with a missing `import
    re` that no self-test could reach — the canned-output self-test now
    EXECUTES this body, docker or no docker)."""
    run = runner or run_text
    out = {}
    for c in containers:
        rc1, killed, _ = run(['docker', 'inspect', '--format',
                              '{{.State.OOMKilled}}', c])
        rc2, ev, _ = run(['docker', 'exec', c, 'sh', '-c',
                          'grep oom_kill /sys/fs/cgroup/memory.events '
                          '2>/dev/null'])
        kills = None
        if rc2 == 0:
            m = re.search(r'^oom_kill (\d+)', ev, re.M)
            kills = int(m.group(1)) if m else None
        out[c] = {'oomkilled': killed if rc1 == 0 else 'uninspectable',
                  'oom_kill_events': kills}
    return out


def oom_delta(before: dict, after: dict) -> dict:
    """Per container: OOMKilled flag after + oom_kill event count delta."""
    out = {}
    for c, a in after.items():
        b = (before.get(c) or {}).get('oom_kill_events')
        d = (a['oom_kill_events'] - b
             if a['oom_kill_events'] is not None and b is not None else None)
        out[c] = {'oomkilled': a['oomkilled'], 'oom_kill_delta': d}
    return out


def run_text(argv, timeout=30):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def resolve_posture(args):
    """Posture from --cell (the three measured named cells) OR the dynamic
    RULING-K grid args (--arm + --tokens/--instances + --threads-env).
    Returns (posture_dict, label). env is a string ('4') or None (unset);
    check_posture_env fail-closes either way."""
    if args.cell:
        return dict(CELLS[args.cell]), args.cell
    if not args.arm:
        raise SystemExit('NOT DONE — give --cell or --arm (with '
                         '--tokens/--instances and --threads-env)')
    env = None if args.threads_env in (None, 'unset') else str(args.threads_env)
    if args.arm == 'rr':
        if not args.tokens:
            raise SystemExit('NOT DONE — --arm rr needs --tokens')
        t = env or 'unset'
        return ({'arm': 'rr', 'tokens': args.tokens, 'env': env},
                f'rr_M{args.tokens}xT{t}')
    if not args.instances:
        raise SystemExit('NOT DONE — --arm li needs --instances')
    t = env or 'unset'
    return ({'arm': 'li', 'instances': args.instances, 'env': env},
            f'li_N{args.instances}xT{t}')


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--cell', choices=sorted(CELLS),
                    help='one of the three measured named cells; OR use the '
                         'dynamic grid args below (Ruling K)')
    ap.add_argument('--arm', choices=['rr', 'li'])
    ap.add_argument('--tokens', type=positive_int('tokens', 64), default=None)
    ap.add_argument('--instances', type=positive_int('instances', 32),
                    default=None)
    ap.add_argument('--threads-env', default=None,
                    help="int or 'unset' — the six BLAS/OMP vars expected on "
                         'the containers (read back fail-closed)')
    ap.add_argument('--batch', choices=['heads', 'measured'], default='heads')
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
    for req in ('concurrency', 'containers'):
        if not getattr(args, req):
            ap.error(f'--{req} is required for a point '
                     '(unless --self-test/--summarize)')
    if (args.threads_env is not None and args.threads_env != 'unset'
            and not args.threads_env.isdigit()):
        ap.error("--threads-env must be an integer or 'unset'")

    cell, label = resolve_posture(args)
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_file():
        raise SystemExit(f'NOT DONE — subset manifest not found: {manifest_path}')
    batch, meta, corpus_dir, src = load_batch(manifest_path, args.corpus_dir,
                                              args.batch)
    lanes = cell.get('tokens') or cell.get('instances') or 1
    if args.concurrency < lanes:
        print(f'WARNING — C={args.concurrency} < lanes={lanes}: this point '
              'cannot saturate the posture (Ruling K requires C >= M for '
              'posture points); recorded, not refused')
    containers = [c.strip() for c in args.containers.split(',') if c.strip()]
    check_posture_env(containers, cell['env'])   # fail-closed, entry 12
    port = args.port or (5565 if cell['arm'] == 'rr' else 8802)
    li_ports = ([8802 + i for i in range(cell['instances'])]
                if cell['arm'] == 'li' else None)
    # RULING L read-back, fail-closed per instance (entry 12): chunk config
    # sets the LI arm's embed workload. RR has no read-back surface for its
    # splitter (inert config, no /health twin) — the honest asymmetry; its
    # evidence is the detect-text/frame-parity probes and
    # CHAR_CONSERVATION_MECHANISM.md.
    chunk_rb = (check_li_chunk_config(li_ports) if cell['arm'] == 'li'
                else {'arm': 'rr', 'note': 'engine splitter inert-config '
                      '(LangChain library defaults); no per-point read-back '
                      'surface exists'})
    out_dir = Path(args.out_dir).expanduser() if args.out_dir \
        else Path.home() / 'films_probe' / 'curve_out'
    out_dir.mkdir(parents=True, exist_ok=True)

    repo = Path(__file__).resolve().parents[3]
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    print(f'point {label} C={args.concurrency}: batch of {len(batch)} films '
          f'({args.batch}), corpus {corpus_dir} [{src}]')

    cpu_before = {c: cpu_usage_usec(c) for c in containers}
    oom_before = oom_state(containers)
    t0 = time.monotonic()
    out_dir_p = out_dir   # single assignment above; alias kept for the writes
    try:
        if cell['arm'] == 'rr':
            results, inflight_max = asyncio.run(
                run_point_rr(cell, batch, args.concurrency, port, args.ttl))
        else:
            results, inflight_max = asyncio.run(
                run_point_li(batch, args.concurrency, li_ports))
    except Exception as exc:   # noqa: BLE001 — a dead point still leaves evidence
        failed = build_failed_artifact(
            head=head, label=label, concurrency=args.concurrency,
            batch_mode=args.batch, lanes=lanes, posture=cell,
            containers=containers, chunk_config_readback=chunk_rb,
            oom=oom_delta(oom_before, oom_state(containers)),
            exception_chain=exc_chain(exc))
        fpath = out_dir_p / f'curve_{label}_C{args.concurrency}.json'
        preserve(fpath)
        fpath.write_text(json.dumps(failed, indent=1))
        print(f'NOT DONE — point {label} C={args.concurrency} FAILED; '
              f'artifact written to {fpath}; oom={failed["oom"]}; '
              f'chain={failed["FAILED"]["exception_chain"]}')
        return 1
    bracket_wall = round(time.monotonic() - t0, 2)
    cpu_after = {c: cpu_usage_usec(c) for c in containers}
    oom = oom_delta(oom_before, oom_state(containers))

    env_n = int(cell['env']) if cell.get('env') else None
    metrics = point_metrics(results, batch, bracket_wall,
                            cpu_before, cpu_after, containers)
    artifact = build_point_artifact(
        head=head, label=label, concurrency=args.concurrency,
        batch_mode=args.batch, lanes=lanes, env_n=env_n, posture=cell,
        containers=containers, chunk_config_readback=chunk_rb, oom=oom,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        batch=batch, inflight_max=inflight_max, per_film=results,
        metrics=metrics,
        probe_ru_maxrss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    out = out_dir_p / f'curve_{label}_C{args.concurrency}.json'
    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back
    m = rb['metrics']
    oom_fired = any(v.get('oomkilled') == 'true' or (v.get('oom_kill_delta') or 0) > 0
                    for v in rb['oom'].values())
    print(f"POINT {label} C={args.concurrency}: span {m['span_s']}s | "
          f"{m['frames_per_s']} f/s | rt x{m['realtime_factor']} | "
          f"{m['service_cpu']['cores']} cores | errors {m['n_errors']} | "
          f"inflight max {rb['inflight_max']}"
          + (f" | OOM FIRED: {json.dumps(rb['oom'])} — A FINDING, read "
             "mem_watch's anon at this point" if oom_fired else '')
          + (' | EXPECTATION MISMATCHES: '
             + json.dumps(m['frame_expectation_mismatches'])
             if m['frame_expectation_mismatches'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
