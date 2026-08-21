#!/usr/bin/env python3
"""Phase 2 video smoke — five checks on the smoke_phase2 pattern, exit non-zero
on any failure. Run before EVERY long leg. Target wall: ~5 minutes (the golden
send uses the shortest corpus item; the budget is stated per section below).

  0  static gate         static_names over the video working set (#36 class)
  A  image identity      docker patch label (assertion) + the Phase 1 PDF
                         duplication fixture through the RUNNING rr container
                         (measurement): the label says patched, the fixture
                         proves it. Fixture is CONTENT-pinned (FIXTURE_SHA) —
                         absence means the corpus changed, never that the
                         patch works. (Approved: the PDF fixture's only Phase 2
                         job is image identity; the video duplication gate is
                         organic-only.)
  B  golden record       one video through the measured pipe vs a stored golden
                         chunk-hash list (--write-golden creates it once, after
                         the probe has confirmed the pipe; default golden video
                         is the SHORTEST corpus item so the smoke stays fast)
  C  read-backs          container flags (no cpuset, no NanoCpus, patch label),
                         corpus-vs-manifest (size), quiet box (load1 VALUE
                         recorded, not just the verdict)
  D  thread pins         BOTH arms, from inside the running processes; absence
                         fails before agreement (defect #37's fix, via
                         gates_shared.thread_pin_parity)

Reuse, not reimplementation: fixture constants from scripts/smoke_phase2.py,
submission via weekend_worker.RocketPdfArm, read-backs via driver_video's own
preflight functions — one check, one function, fed by both smoke and driver.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'working'))
sys.path.insert(0, str(ROOT / 'working' / 'scripts'))
sys.path.insert(0, str(ROOT / 'working' / 'video'))
sys.path.insert(0, str(ROOT))

from harness import gates_shared as gs                      # noqa: E402
from harness.static_names import check_files                # noqa: E402
import driver_video as drv                                  # noqa: E402

SHA_INDEX_CACHE = ROOT / 'working' / 'results' / '.pdf_fixture_index.json'
_fails: list[str] = []


def say(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    _fails.append(msg)
    say(f'  FAIL  {msg}')


# ------------------------------------------------------------------ 0. static
def check_static() -> dict:
    say('\n0. static gate — undefined names in any branch (#36 class)')
    targets = [ROOT / 'working' / 'video' / n
               for n in ('driver_video.py', 'smoke_video.py', 'fetch_ami_video.py',
                         'query_phase1_chunks.py')]
    targets += sorted((ROOT / 'working' / 'video' / 'probe').glob('*.py'))
    targets += sorted((ROOT / 'working' / 'video' / 'li_video').glob('*.py'))
    targets += [ROOT / 'working' / 'harness' / 'gates_shared.py']
    bad = check_files([str(t) for t in targets])
    bad = {f: v for f, v in bad.items() if v}
    for f, finds in bad.items():
        for x in finds:
            fail(f"undefined name {x['name']!r} in {Path(f).name}")
    if not bad:
        say(f'  PASS  {len(targets)} files, no undefined names')
    return {'files_checked': len(targets), 'findings': {k: len(v) for k, v in bad.items()}}


# ------------------------------------------------------------- A. image identity
def _fixture_index(pdf_corpus: Path, fixture_sha: dict) -> dict[str, Path]:
    """sha16-prefix -> Path for the five fixture PDFs. Cached; cache entries are
    re-hashed on every run (5 files, fast) so a changed file cannot hide."""
    if SHA_INDEX_CACHE.exists():
        cached = {k: Path(v) for k, v in json.loads(SHA_INDEX_CACHE.read_text()).items()}
        if all(k in cached and cached[k].exists()
               and hashlib.sha256(cached[k].read_bytes()).hexdigest()[:16] == k
               for k in fixture_sha):
            return cached
    say('  (building fixture sha index — one-time corpus scan)')
    index: dict[str, Path] = {}
    want = set(fixture_sha)
    for p in sorted(pdf_corpus.glob('*.pdf')):
        h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        if h in want:
            index[h] = p
            if len(index) == len(want):
                break
    SHA_INDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SHA_INDEX_CACHE.write_text(json.dumps({k: str(v) for k, v in index.items()}))
    return index


def check_image_identity(rr_container: str, pdf_corpus: Path) -> dict:
    say('\nA. image identity — label asserts, the PDF fixture MEASURES (~2 min)')
    label = drv.docker_inspect(
        rr_container,
        '{{index .Config.Labels "benchmark.rocketride.duplication_patch_applied"}}')
    if label != '1':
        fail(f'duplication_patch_applied label is {label!r}, not "1" — wrong image; '
             'the fixture below would measure the wrong thing')
        return {'label': label, 'skipped': 'fixture not run against a mislabelled image'}
    from smoke_phase2 import FIXTURE_SHA          # content pins + expected PATCHED counts
    index = _fixture_index(pdf_corpus, FIXTURE_SHA)
    missing = [s for s in FIXTURE_SHA if s not in index]
    if missing:
        fail(f'fixture documents absent by sha256: {missing} — corpus changed, '
             'never evidence the patch works')
        return {'label': label, 'missing_sha': missing}
    from weekend_worker import RocketPdfArm
    arm = RocketPdfArm('vidsmoke')
    rows = {}
    try:
        for s, expect_chunks in FIXTURE_SHA.items():
            chunks, _ = arm.process(index[s].read_bytes())
            hashes = [hashlib.sha256(c.encode()).hexdigest() for c in chunks]
            doubled = gs.whole_list_doubled(hashes)
            rows[s] = {'n_chunks': len(chunks), 'expected_patched': expect_chunks,
                       'whole_list_doubled': doubled}
            if doubled is True:
                fail(f'fixture {s}: WHOLE-LIST DOUBLING on the patched image — '
                     'the label lies or the patch regressed')
            elif len(chunks) != expect_chunks:
                fail(f'fixture {s}: {len(chunks)} chunks vs expected {expect_chunks} '
                     '(patched-behaviour counts, measured on the Phase 1 box)')
    finally:
        arm.close()
    if not _fails:
        say(f'  PASS  label=1 and all {len(FIXTURE_SHA)} fixture documents at '
            'patched counts, no doubling')
    return {'label': label, 'fixture': rows}


# ------------------------------------------------------------- B. golden record
async def _send_video(video: Path, port: int) -> dict:
    from rocketride import RocketRide
    client = RocketRide(uri=f'ws://127.0.0.1:{port}/task/service', apikey='local-dev')
    await client.connect()
    try:
        started = await client.use(filepath=str(drv.PIPE_PATH), ttl=3600)
        result = await client.send(started['token'], video.read_bytes(),
                                   objinfo={'name': video.name}, mimetype='video/x-msvideo')
    finally:
        await client.disconnect()
    return drv.record_from_rr(result)


def check_golden(golden_path: Path, video: Path, port: int, write: bool) -> dict:
    say(f'\nB. golden record — {video.name} through the measured pipe '
        f'({"WRITE mode" if write else "compare"})')
    rec = asyncio.run(_send_video(video, port))
    fresh = {'video': video.name,
             'video_sha16': hashlib.sha256(video.read_bytes()).hexdigest()[:16],
             'n_chunks': rec['n_chunks'], 'chunk_sha256': rec['chunk_sha256'],
             'frames_observed': rec['frames_observed']}
    if write:
        golden_path.write_text(json.dumps(fresh, indent=1))
        say(f'  golden WRITTEN: {golden_path} ({fresh["n_chunks"]} chunks, '
            f'{fresh["frames_observed"]} frames). Write once, after the probe confirms the pipe.')
        return {'written': str(golden_path), 'n_chunks': fresh['n_chunks']}
    if not golden_path.exists():
        fail(f'no golden at {golden_path} — create once with --write-golden after the probe')
        return {'error': 'golden missing'}
    gold = json.loads(golden_path.read_text())
    if gold.get('video_sha16') != fresh['video_sha16']:
        fail('golden was recorded from a DIFFERENT video file (sha mismatch)')
    d = gs.determinism_repeat(gold.get('chunk_sha256') or [], fresh['chunk_sha256'])
    if d['PASS'] is not True:
        fail(f'golden mismatch: {json.dumps({k: v for k, v in d.items() if k != "PASS"})}')
    else:
        say(f'  PASS  {fresh["n_chunks"]} chunks identical to golden')
    return {'golden': str(golden_path), 'determinism': d}


# --------------------------------------------------------------- C. read-backs
def check_readbacks(args) -> dict:
    say('\nC. read-backs — flags, corpus, quiet box')
    problems = drv.preflight_containers(args.rr_container, args.li_container)
    for p in problems:
        fail(p)
    r = subprocess.run([sys.executable, str(ROOT / 'working' / 'video' / 'fetch_ami_video.py'),
                        '--manifest', args.manifest, '--corpus-dir', args.corpus_dir],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail(f'corpus-vs-manifest: {(r.stdout or r.stderr).strip().splitlines()[-1]}')
    else:
        say(f'  PASS  {r.stdout.strip().splitlines()[-1]}')
    load1 = os.getloadavg()[0]
    if load1 > args.max_preleg_load1:
        fail(f'quiet-box: load1={load1:.2f} > {args.max_preleg_load1} — find the hog '
             '(the 18-Aug lesson); the smoke records the VALUE either way')
    else:
        say(f'  PASS  quiet box (load1={load1:.2f})')
    return {'container_problems': problems or None, 'preleg_load1': round(load1, 2)}


# ------------------------------------------------------------- D. thread pins
async def check_pins(args) -> dict:
    say('\nD. thread pins — BOTH arms, in-process; absence fails before agreement')
    readbacks = {}
    info = await drv.rr_readback(args.rr_port)
    readbacks['rr_task'] = {'env': info.get('env') or {},
                            'torch_num_threads': info.get('torch_num_threads')}
    if info.get('rfdetr_import_ok') is not True:
        fail(f'RR task process cannot import rfdetr ({info.get("rfdetr_import_error")!r}) '
             '— the engine would silently serve RT-DETR')
    li = drv.LIArm(args.li_port)
    await li.start()
    per_worker = await drv.li_readbacks(li)
    if len(per_worker) < (li.declared_workers or 1):
        fail(f'only {len(per_worker)}/{li.declared_workers} LI workers answered — '
             'absent workers fail before agreement')
    impls = {v.get('detect_impl') for v in per_worker.values()}
    if impls and impls != {'rfdetr'}:
        fail(f'LI detect_impl read back as {impls}, not rfdetr')
    readbacks.update({k: {'env': v['env'], 'torch_num_threads': v['torch_num_threads']}
                      for k, v in per_worker.items()})
    pins = gs.thread_pin_parity(readbacks)
    if pins['PASS'] is not True:
        fail(f'thread pins: {json.dumps({k: pins[k] for k in pins if k != "PASS"})}')
    else:
        say(f'  PASS  {len(readbacks)} readers agree: '
            f'{pins["values_agreed"]}')
    return {'pins': pins, 'rr_versions': info.get('package_versions'),
            'li_detect_impl': sorted(impls) if impls else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--golden', default=str(ROOT / 'working' / 'video' / 'golden_video_record.json'))
    ap.add_argument('--write-golden', action='store_true',
                    help='create the golden (once, after the probe has confirmed the pipe)')
    ap.add_argument('--golden-video', default=None,
                    help='default: the SHORTEST measured corpus item (keeps the smoke ~5 min)')
    ap.add_argument('--manifest', default=str(drv.MANIFEST_DEFAULT))
    ap.add_argument('--corpus-dir', default=str(ROOT / 'corpus' / 'ami' / 'video'))
    ap.add_argument('--pdf-corpus', default=str(ROOT / 'corpus' / 'govdocs1' / 'pdfs'))
    ap.add_argument('--rr-container', default='rr')
    ap.add_argument('--li-container', default='li_video')
    ap.add_argument('--rr-port', type=int, default=5565)
    ap.add_argument('--li-port', type=int, default=8802)
    ap.add_argument('--max-preleg-load1', type=float, default=2.0)
    ap.add_argument('--skip-fixture', action='store_true',
                    help='wiring tests only — a measured run never skips image identity')
    args = ap.parse_args()

    t0 = time.time()
    out: dict = {}
    out['static'] = check_static()

    if args.skip_fixture:
        say('\nA. image identity — SKIPPED (--skip-fixture: wiring test only)')
        out['image_identity'] = {'skipped': True}
    else:
        out['image_identity'] = check_image_identity(args.rr_container, Path(args.pdf_corpus))

    golden_video = args.golden_video
    if golden_video is None:
        _, rows = drv.load_manifest(Path(args.manifest))
        measured = [r for r in rows if r['role'] == 'measured']
        shortest = min(measured, key=lambda r: r.get('video_s') or 1e9)
        golden_video = str(Path(args.corpus_dir) / shortest['file'])
        say(f'\n(golden video: shortest measured item {shortest["file"]} '
            f'{shortest.get("video_s")}s)')
    out['golden'] = check_golden(Path(args.golden), Path(golden_video),
                                 args.rr_port, args.write_golden)
    out['readbacks'] = check_readbacks(args)
    out['thread_pins'] = asyncio.run(check_pins(args))

    out['wall_s'] = round(time.time() - t0, 1)
    out['PASS'] = not _fails
    out['failed_checks'] = _fails
    out_path = ROOT / 'working' / 'video' / 'results' / \
        f'smoke_video_{time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1))
    say(f'\nelapsed {out["wall_s"]}s — {"PASS" if out["PASS"] else "FAIL"} '
        f'({len(_fails)} failures) -> {out_path}')
    return 0 if out['PASS'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
