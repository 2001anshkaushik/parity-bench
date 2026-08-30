#!/usr/bin/env python3
"""Films sizing probe — ONE film through one POSTURE per invocation
(Ansh's ruling 2026-08-28: N comes from measurement, not AMI arithmetic —
AMI was 352x288 AVI; Films is h.264 up to 1080p, a different decode regime,
so the AMI rates do not transfer and are not used here).

The three cells and their MEASURED posture values (read from the banked
ami_full exports, not from anyone's description — the description said
"16 tokens, env=2", which the exports show is the 24-Aug 16x2 cell, not
the 26-Aug 8x4 headline):

  rr-default  tokens=1, use(threads=) NOT passed, container env UNSET
              [export_rocketride_video_default_blast.json @
               mainrun_20260824T025550Z: default[tokens=1,threads=unset],
               declared env {} — MEASURED; banked 2.443 span]
  rr-8x4      tokens=8, use(threads=) NOT passed (threads_config null),
              six BLAS/OMP vars = 4 on the container
              [export_rocketride_video_parity_blast{,_p2}.json @
               apples_20260826T041510Z / 052915Z: parity[tokens=8,
               threads=unset], declared env 4x6, in-process torch 4 —
               MEASURED; the banked 11.694/11.571 headline pair]
  li-8x4      8 single-worker instances, six vars = 4
              [export_llamaindex_video_workers_blast @ apples_...074203Z:
               8x W=1, env 4, ports 8802-8809 — MEASURED]

The probe REFUSES a cell whose containers' declared env does not match the
posture (register entry 12: a value that sets a run parameter needs a
read-back before it is quotable). Bring-ups belong to the wrapper script
(run_films_sizing.sh); mem_watch runs beside it and owns the memory and
spool-df numbers — this probe owns wall, frames, CPU bracket, and the
client-side peak.

Per cell it reports: wall_s (upload/close split on RR; stage_s on LI),
n_frames, frames_per_s, realtime_factor (video_duration_s from her frozen
manifest / wall), service CPU cores (cgroup cpu.stat usage_usec delta over
the wall, summed over the posture's containers — idle resident tokens
INCLUDED deliberately: they are the posture's envelope) and utilization
(basis: against the box's 32 vCPU), probe_ru_maxrss_kb (this probe IS the
client; basis stated), and for LI the service-reported bytes_spooled and
frames_dir_bytes. Single-lane note: ONE film exercises ONE lane; the other
lanes idle resident. Projection arithmetic is printed with its assumptions
named (serial upper bound; footage-based with overlap factor stated).

Exit codes: 0 completed / 1 machinery, guard, or env-mismatch refusal /
4 self-test failure.
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
# ONE COPY (entries 6/14): the chunked upload and the frame recovery are the
# proven implementations, imported — never re-typed.
from probe_detect_text import exc_chain, upload_chunked  # noqa: E402
from driver_video import frame_arrays_from_chunks, frames_from_chunks  # noqa: E402
from probe_rr import fresh_project_pipe    # noqa: E402

PIPE_SRC = Path(__file__).resolve().parents[1] / 'benchmark_video_detect.pipe'
UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
THREAD_VARS = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
               'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS')

CELLS = {
    'rr-default': {'arm': 'rr', 'tokens': 1, 'env': None},
    'rr-8x4': {'arm': 'rr', 'tokens': 8, 'env': '4'},
    'li-8x4': {'arm': 'li', 'instances': 8, 'env': '4'},
}


def sha256_file(path: Path, chunk: int = 1 << 20):
    h, n = hashlib.sha256(), 0
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def preserve(path: Path):
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


def run_text(argv, timeout=30):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def container_env(container: str) -> dict:
    rc, out, err = run_text(['docker', 'inspect', '--format',
                             '{{json .Config.Env}}', container])
    if rc != 0:
        raise SystemExit(f'NOT DONE — docker inspect {container!r}: {err[-160:]}')
    env = dict(e.split('=', 1) for e in json.loads(out) if '=' in e)
    return {k: env.get(k) for k in THREAD_VARS}


def check_posture_env(containers, expected):
    """Fail-closed read-back (entry 12): every container's six thread vars
    must equal the posture — all `expected`, or all ABSENT for env=None."""
    bad = {}
    for c in containers:
        got = container_env(c)
        want = {k: expected for k in THREAD_VARS}
        if got != want:
            bad[c] = got
    if bad:
        raise SystemExit(f'NOT DONE — declared env does not match the posture '
                         f'(expected {expected!r} on all six vars): {bad}')
    return {c: expected for c in containers}


def cpu_usage_usec(container: str):
    rc, out, _ = run_text(['docker', 'exec', container, 'cat',
                           '/sys/fs/cgroup/cpu.stat'])
    if rc != 0:
        return None
    m = re.search(r'^usage_usec (\d+)$', out, re.M)
    return int(m.group(1)) if m else None


def video_duration_from_manifest(manifest_path: Path, doc: str) -> float:
    man = json.loads(manifest_path.read_text())
    try:
        return float(man['video_duration_s'][doc])
    except KeyError:
        raise SystemExit(f'NOT DONE — {doc!r} not in the manifest '
                         f'({manifest_path}); the probe film must be one of '
                         "her frozen corpus's docs.")


def projection(per_film_wall_s: float, realtime_factor: float,
               film_footage_s: float) -> dict:
    """The two projection forms, each with its assumption NAMED. Concrete
    N-filled numbers wait for the ruling; the formulas are the report."""
    return {
        'serial_upper_bound':
            f'span >= {per_film_wall_s:.0f}s x N films x passes '
            '(ASSUMPTION: fully serial, zero overlap credit — an upper '
            'bound; blast overlap shortens by up to min(C, lanes))',
        'footage_based':
            f'span ~= subset_footage_s / ({realtime_factor:.2f} x '
            'overlap_factor) per pass (ASSUMPTION: this film\'s realtime '
            f'factor — measured on {film_footage_s:.0f}s of footage, ONE '
            'lane active — transfers to the subset mean; overlap_factor=1 '
            'measured here, >1 under blast up to min(C, lanes))',
    }


# ------------------------------------------------------------------ RR cell

async def run_rr(cell, film: Path, film_bytes: int, port: int, ttl: int):
    import os
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    client = RocketRideClient()
    await client.connect(timeout=60000)
    tokens = []
    try:
        for i in range(cell['tokens']):
            # Fresh project_id per token (D3); use(threads=) NOT passed —
            # the measured posture's threads_config is null on every cell.
            pipe_path, _ = fresh_project_pipe_file(f'sizing-tok{i}')
            started = await client.use(filepath=str(pipe_path), ttl=ttl)
            tokens.append(started['token'])
        t0 = time.monotonic()
        up = await upload_chunked(client, tokens[0], film, film_bytes)
        wall = round(time.monotonic() - t0, 2)
        result = up['result'] or {}
        docs = result.get('documents') or []
        contents = [d.get('page_content') or '' for d in docs]
        n_frames = frames_from_chunks(contents) if contents else None
        arrays = frame_arrays_from_chunks(contents) if contents else None
        agree = (arrays is not None and n_frames is not None
                 and len(arrays) == n_frames)
        return {'wall_s': wall, 'upload_wall_s': up['upload_wall_s'],
                'close_wall_s': up['close_wall_s'], 'n_writes': up['n_writes'],
                'n_frames': n_frames, 'frame_count_methods_agree': agree,
                'n_chunks': len(contents),
                'tokens_resident': len(tokens),
                'lane_note': 'ONE lane active (token 0); the other '
                             f'{len(tokens) - 1} tokens idle resident — '
                             'their burden is inside the CPU bracket'}
    finally:
        for tok in tokens:
            try:
                await asyncio.wait_for(client.terminate(tok), timeout=120)
            except Exception as exc:   # noqa: BLE001
                print(f'terminate {str(tok)[:16]}: {exc!r} (recorded; '
                      f'ttl={ttl} reaps)')
        await client.disconnect()


def fresh_project_pipe_file(tag: str):
    cfg = fresh_project_pipe(PIPE_SRC, tag)
    out = PIPE_SRC.parent / 'probe' / f'generated_sizing_{tag}_{UTC}.pipe'
    out.write_text(json.dumps(cfg, indent=1))
    return out, cfg['project_id']


# ------------------------------------------------------------------ LI cell

def run_li(film: Path, film_bytes: int, port: int):
    import urllib.request
    t0 = time.monotonic()
    with open(film, 'rb') as fh:
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/process_video', data=fh, method='POST',
            headers={'Content-Type': 'application/octet-stream',
                     'Content-Length': str(film_bytes)})
        with urllib.request.urlopen(req, timeout=14400) as resp:
            body = json.load(resp)
    wall = round(time.monotonic() - t0, 2)
    if 'error' in body:
        raise SystemExit(f'NOT DONE — LI service error: {body}')
    return {'wall_s': wall, 'n_frames': body.get('n_frames'),
            'n_chunks': body.get('n_chunks'), 'stage_s': body.get('stage_s'),
            'reader_semantics': body.get('reader_semantics'),
            'bytes_spooled': body.get('bytes_spooled'),
            'frames_dir_bytes': body.get('frames_dir_bytes'),
            'serving_pid': body.get('pid'),
            'lane_note': 'ONE instance receives the film; the other 7 idle '
                         'resident — their burden is inside the CPU bracket'}


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    check('cell table encodes the MEASURED postures (default 1/unset, '
          '8x4 = 8 tokens x env-4, li 8x1 x env-4)',
          CELLS['rr-default'] == {'arm': 'rr', 'tokens': 1, 'env': None}
          and CELLS['rr-8x4'] == {'arm': 'rr', 'tokens': 8, 'env': '4'}
          and CELLS['li-8x4'] == {'arm': 'li', 'instances': 8, 'env': '4'})
    check('no cell passes use(threads=) — threads_config was null on every '
          'measured export', 'threads' not in CELLS['rr-8x4'])
    p = projection(1200.0, 3.5, 14000.0)
    check('projection: serial form carries its assumption',
          '1200s x N films x passes' in p['serial_upper_bound']
          and 'ASSUMPTION' in p['serial_upper_bound'])
    check('projection: footage form names the overlap factor',
          '3.50' in p['footage_based'] and 'overlap_factor' in p['footage_based'])
    env_probe = {k: '4' for k in THREAD_VARS}
    check('env read-back shape: six vars, all-or-refuse',
          set(env_probe) == set(THREAD_VARS))

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


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--cell', choices=sorted(CELLS))
    ap.add_argument('--film')
    ap.add_argument('--film-sha-expected', default=None)
    ap.add_argument('--manifest',
                    default=str(Path.home() / 'films_manifest/corpus_manifest.json'))
    ap.add_argument('--containers',
                    help='comma-separated containers for the CPU bracket and '
                         'the posture env read-back (rr | li_bal_0..7)')
    ap.add_argument('--port', type=positive_int('port', 65535), default=None)
    ap.add_argument('--ttl', type=positive_int('ttl', 86400), default=3600)
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    for req in ('cell', 'film', 'containers'):
        if not getattr(args, req):
            ap.error(f'--{req} is required (unless --self-test)')
    if args.film_sha_expected and not re.fullmatch(r'[0-9a-f]{64}',
                                                   args.film_sha_expected):
        ap.error('--film-sha-expected must be 64 lowercase hex chars')

    cell = CELLS[args.cell]
    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        raise SystemExit(f'NOT DONE — film not found: {film}')
    print(f'hashing {film.name} ...')
    film_sha, film_bytes = sha256_file(film)
    if args.film_sha_expected and film_sha != args.film_sha_expected:
        raise SystemExit(f'NOT DONE — film sha mismatch: measured {film_sha}, '
                         f'expected {args.film_sha_expected}')
    footage_s = video_duration_from_manifest(Path(args.manifest).expanduser(),
                                             film.name)
    containers = [c.strip() for c in args.containers.split(',') if c.strip()]
    declared = check_posture_env(containers, cell['env'])
    port = args.port or (5565 if cell['arm'] == 'rr' else 8802)

    repo = Path(__file__).resolve().parents[3]
    rc, head, _ = run_text(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
    images = {}
    for c in containers:
        rc2, out, _ = run_text(['docker', 'inspect', '--format', '{{.Image}}', c])
        images[c] = out if rc2 == 0 else 'UNAVAILABLE'

    cpu_before = {c: cpu_usage_usec(c) for c in containers}
    t0 = time.monotonic()
    try:
        if cell['arm'] == 'rr':
            r = asyncio.run(run_rr(cell, film, film_bytes, port, args.ttl))
        else:
            r = run_li(film, film_bytes, port)
    except SystemExit:
        raise
    except Exception as exc:   # noqa: BLE001 — recorded with the full chain
        raise SystemExit(f'NOT DONE — cell {args.cell} failed: {exc_chain(exc)}')
    bracket_wall = round(time.monotonic() - t0, 2)
    cpu_after = {c: cpu_usage_usec(c) for c in containers}

    deltas = {c: (cpu_after[c] - cpu_before[c])
              for c in containers
              if cpu_before[c] is not None and cpu_after[c] is not None}
    cores = round(sum(deltas.values()) / 1e6 / bracket_wall, 2) if deltas else None
    util = round(100 * cores / 32, 1) if cores is not None else None

    wall = r['wall_s']
    fps = round(r['n_frames'] / wall, 3) if r.get('n_frames') and wall else None
    rtf = round(footage_s / wall, 2) if wall else None
    artifact = {
        'probe': 'films_sizing', 'created_utc': UTC, 'git_head': head,
        'cell': args.cell,
        'posture': dict(cell, source='MEASURED from the banked ami_full '
                                     'exports; see module docstring'),
        'film': {'name': film.name, 'bytes': film_bytes, 'sha256': film_sha,
                 'video_duration_s': footage_s},
        'containers': containers, 'images': images,
        'declared_env_readback': declared,
        'result': r,
        'frames_per_s': fps, 'realtime_factor': rtf,
        'service_cpu': {'cores': cores, 'util_pct': util,
                        'basis': 'cgroup cpu.stat usage_usec delta over the '
                                 f'cell wall ({bracket_wall}s), summed over '
                                 f'{len(deltas)}/{len(containers)} readable '
                                 'containers; util against the box 32 vCPU; '
                                 'idle resident lanes INCLUDED (the posture '
                                 'envelope)'},
        'probe_ru_maxrss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'probe_ru_maxrss_basis': 'client-side process peak (this probe IS the '
                                 'sender); the leg driver self-reports its own '
                                 'per leg (driver_memory)',
        'memory_and_spool_note': 'peak anon / memory.peak / spool df are '
                                 "mem_watch's numbers, recorded beside this "
                                 'artifact by the wrapper',
        'projection': projection(wall, rtf or 0.0, footage_s),
    }
    out = Path(args.out) if args.out else \
        Path(__file__).parent / f'probe_films_sizing_{args.cell}_{film.stem}.json'
    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back, then report
    print(f'wrote {out}')
    print(f"SIZING {rb['cell']} — {film.name}: wall {wall}s | frames "
          f"{r.get('n_frames')} | {fps} f/s | realtime x{rtf} | service CPU "
          f"{cores} cores ({util}%)")
    for line in rb['projection'].values():
        print(f'  projection: {line}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
