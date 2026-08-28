#!/usr/bin/env python3
"""fetch_films_subset — build and pin OUR films subset manifest from Leela's
frozen archive_films_v2 corpus (Rulings E/F, 2026-08-28).

The subset is a stated function of her sealed manifest: title-dedup (exact
key + prefix/duration merge, RULING E's ratified splits applied IN the rule,
the [waterfront] flag left merged until ruled), duration x bytes terciles,
k per stratum in (bytes desc, doc asc) order capped by cell size, envelope
film forced in if absent — all imported ONE-COPY from
probe/films_strata_report.py, so the report and this builder can never
disagree about the selection.

Per selected film, fail-closed at every step:
  fetch    aws s3 cp from her v2 prefix if absent (sequential; resumable —
           a present file is verified, never re-fetched)
  verify   sha256 + bytes against HER manifest row — a mismatch aborts the
           build naming the film (corpus_pin discipline, on arrival)
  measure  expected_frames_measured through OUR arms' own binary
           (imageio-ffmpeg resolved in this venv — the floor venv is pinned
           to the arms' resolution) at fps=1/15, FILE input, the argv the
           parity probe certified byte-equal across engine/LI/file/pipe.
           The PNG stream is counted by BOTH split algorithms (engine IEND
           walk + LI signature scan, imported from probe_frame_parity);
           disagreement or a nonzero ffmpeg exit REFUSES the row.
           Explicitly NOT her `frames_counted` (a native-rate null-mux
           count — adopting it would be register entry 6's twin-provenance
           bug); hers is recorded per row as her_frames_counted, labelled.

Manifest meta records: her manifest sha (verified against the Ruling's
expected value), the FULL selection-rule string incl. ratified splits and
k, the strata cuts and per-cell picks, the ffmpeg provenance (path, sha256,
version), interval, and the corpus-dir stamp under corpus_locator's
META_KEY ('corpus_dir') earned by the build's own N/N sha verification —
entry 15: no corpus-naming defaults; --corpus-dir is REQUIRED.

Warm split: UNRULED for films legs. Every row is role='measured' and the
meta carries warm_note saying so — a warm-gated leg must not run off this
manifest until the split is ruled.

Run (box):
  ~/.venv-floor/bin/python3 working/video/fetch_films_subset.py \
      --corpus-dir ~/films_corpus/subset \
      [--her-manifest ~/films_manifest/corpus_manifest.json] [--k 4]
Self-test (laptop; no aws, no ffmpeg): --self-test
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))            # working/video
sys.path.insert(0, str(Path(__file__).resolve().parent / 'probe'))  # probe/
from argtypes import positive_int          # noqa: E402 — register entry 8
from corpus_locator import META_KEY        # noqa: E402 — one key, one locator
from films_strata_report import (          # noqa: E402 — ONE COPY of the rule
    RATIFIED_SPLITS, UNRATIFIED_FLAGS, dedup_titles, load_rows, select_subset)
from probe_frame_parity import IendWalk, SigScan  # noqa: E402 — both splitters

HER_MANIFEST_SHA_RULED = \
    'bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1'
S3_PREFIX_DEFAULT = 's3://rocketride-benchmark-data/leela/corpus/archive_films_v2'
UTC = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


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


def ffmpeg_provenance():
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    ver = subprocess.run([ff, '-version'], capture_output=True, text=True)
    return {'path': ff, 'sha256': sha256_file(Path(ff))[0],
            'version': (ver.stdout or ver.stderr).splitlines()[0],
            'resolved_by': 'imageio_ffmpeg.get_ffmpeg_exe() in this venv '
                           "(the arms' own resolution)"}


def measure_expected_frames(ff: str, video_path: Path, interval_s: int) -> int:
    """fps=1/interval, FILE input, PNG stream counted by BOTH split
    algorithms — they must agree and ffmpeg must exit 0, else REFUSE.
    (Crossroad 23: the expectation is measured, never arithmetic; the argv
    is the parity-probe-certified family.)"""
    cmd = [ff, '-nostdin', '-loglevel', 'error', '-i', str(video_path),
           '-vf', f'fps=1/{interval_s}', '-f', 'image2pipe',
           '-fps_mode', 'passthrough', '-vcodec', 'png', '-']
    iend, sig = IendWalk(), SigScan()
    n_iend = n_sig = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    stderr_tail = b''
    while True:
        b = proc.stdout.read(1 << 20)
        if not b:
            break
        n_iend += len(iend.feed(b))
        n_sig += len(sig.feed(b))
    n_iend += len(iend.finish())
    n_sig += len(sig.finish())
    stderr_tail = proc.stderr.read()[-400:]
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f'NOT DONE — ffmpeg rc={rc} on {video_path.name}: '
                         f'{stderr_tail.decode("utf-8", "replace")}')
    if n_iend != n_sig:
        raise SystemExit(f'NOT DONE — splitter disagreement on '
                         f'{video_path.name}: IEND {n_iend} vs SIG {n_sig}; '
                         'refusing to record an ambiguous expectation')
    return n_iend


def fetch_via_aws(s3_prefix: str, doc: str, dest: Path, aws: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run([aws, 's3', 'cp', f'{s3_prefix}/{doc}', str(dest),
                         '--quiet']).returncode
    if rc != 0 or not dest.is_file():
        raise SystemExit(f'NOT DONE — fetch failed for {doc} (rc={rc})')


def selection_rule_string(k: int, smeta: dict) -> str:
    splits = sorted(tuple(sorted(s)) for s in RATIFIED_SPLITS)
    return (
        'archive_films_v2 subset: title-dedup (exact normalized key + '
        'prefix>=8 merge gated by 10% duration proximity; RULING E ratified '
        f'splits {splits} applied in-rule; unratified flags '
        f'{sorted(UNRATIFIED_FLAGS)} left merged), keep largest-bytes '
        'transcode per title (tie doc asc); duration terciles '
        f'{smeta["duration_tercile_cuts_s"]} x bytes terciles '
        f'{smeta["bytes_tercile_cuts"]}; k={k} per stratum in (bytes desc, '
        'doc asc) order capped by cell size; envelope film '
        f'{smeta["envelope_film"]} forced if absent (forced='
        f'{smeta["envelope_forced"]}). RULING F 2026-08-28.')


def build_manifest(her_manifest: dict, her_sha: str, corpus_dir: Path,
                   k: int, out: Path, s3_prefix: str, interval_s: int,
                   fetch_fn, measure_fn, ff_prov: dict) -> dict:
    rows_all = load_rows(her_manifest)
    kept, clusters = dedup_titles(rows_all)
    selected, smeta = select_subset(kept, k)
    print(f'selection: N={smeta["n_selected"]} (k={k}; '
          f'{len(rows_all)} docs -> {len(kept)} titles -> {len(selected)} selected)')

    out_rows = []
    for i, r in enumerate(selected, 1):
        doc = r['doc']
        dest = corpus_dir / doc
        if not dest.is_file():
            print(f'  [{i}/{len(selected)}] fetching {doc} '
                  f'({r["bytes"] / 1e9:.2f} GB) ...')
            fetch_fn(s3_prefix, doc, dest)
        sha, nbytes = sha256_file(dest)
        if sha != r['sha256'] or nbytes != r['bytes']:
            raise SystemExit(f'NOT DONE — {doc} FAILED arrival verification: '
                             f'sha {sha} vs {r["sha256"]}, bytes {nbytes} vs '
                             f'{r["bytes"]}. Fail-closed; nothing written.')
        n_frames = measure_fn(dest)
        vfp = (her_manifest.get('video_fps_probe') or {}).get(doc) or {}
        out_rows.append({
            'file': doc,
            'url': f'{s3_prefix}/{doc}',
            'bytes': nbytes,
            'sha256': sha,
            'video_s': r['video_duration_s'],
            'duration_s': r['duration_s'],
            'nominal_fps': vfp.get('nominal_fps'),
            'her_frames_counted': vfp.get('frames_counted'),
            'her_frames_counted_note': 'HER native-rate null-mux count — '
                                       'NEVER the gate-1 expectation',
            'expected_frames_measured': n_frames,
            'role': 'measured',
        })
        print(f'  [{i}/{len(selected)}] {doc}: verified sha, '
              f'expected_frames_measured={n_frames}')

    meta = {'_meta': {
        'built_utc': UTC,
        'source': 'leela archive_films_v2 (frozen)',
        'source_manifest_sha256': her_sha,
        'selection_rule': selection_rule_string(k, smeta),
        'strata': smeta,
        'ratified_splits': sorted(tuple(sorted(s)) for s in RATIFIED_SPLITS),
        'unratified_flags': sorted(UNRATIFIED_FLAGS),
        'n_measured': len(out_rows),
        'n_warm': 0,
        'warm_note': 'warm split for films legs is UNRULED — every row is '
                     'measured; a warm-gated leg must not run off this '
                     'manifest until the split is ruled',
        META_KEY: str(corpus_dir.resolve()),
        'corpus_dir_stamped': {'utc': UTC,
                               'proof': f'sha256 verify {len(out_rows)}/'
                                        f'{len(out_rows)} against this '
                                        'directory at build'},
        'expected_frames_method': ('MEASURED at build (Crossroad 23): '
                                   f'fps=1/{interval_s}, FILE input, both '
                                   'PNG splitters agree (parity-probe-'
                                   'certified argv family); never her '
                                   'frames_counted'),
        'interval_s': interval_s,
        'ffmpeg': ff_prov,
    }}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as fh:
        fh.write(json.dumps(meta) + '\n')
        for row in out_rows:
            fh.write(json.dumps(row) + '\n')
    return {'n': len(out_rows), 'meta': meta['_meta']}


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    docs = {f'f{i:02d}.mp4': (3600 + i * 300, 200_000 + i * 7_000)
            for i in range(12)}
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        corpus = d / 'corpus'
        corpus.mkdir()
        sha_by = {}
        for doc, (dur, nb) in docs.items():
            body = doc.encode() * (nb // len(doc) + 1)
            body = body[:nb]
            (corpus / doc).write_bytes(body)
            sha_by[doc] = hashlib.sha256(body).hexdigest()
        man = {'duration_s': {doc: v[0] for doc, v in docs.items()},
               'video_duration_s': {doc: v[0] - 1 for doc, v in docs.items()},
               'video_fps_probe': {doc: {'frames_counted': 99, 'nominal_fps': 24}
                                   for doc in docs},
               'sha256': {doc: {'sha256': sha_by[doc], 'bytes': v[1]}
                          for doc, v in docs.items()}}
        out = d / 'manifest.jsonl'

        def no_fetch(*a):
            raise AssertionError('fetch called but every file exists')

        res = build_manifest(man, 'ff' * 32, corpus, 2, out,
                             's3://example/prefix', 15,
                             fetch_fn=no_fetch,
                             measure_fn=lambda p: 123,
                             ff_prov={'path': 'stub', 'sha256': '0' * 64,
                                      'version': 'stub'})
        lines = out.read_text().splitlines()
        meta = json.loads(lines[0])['_meta']
        rows = [json.loads(l) for l in lines[1:]]
        check('meta carries the locator key, source sha, selection rule, '
              'ratified splits, warm note',
              meta.get(META_KEY) == str(corpus.resolve())
              and meta['source_manifest_sha256'] == 'ff' * 32
              and 'RULING F' in meta['selection_rule']
              and meta['ratified_splits']
              and 'UNRULED' in meta['warm_note'])
        check('rows carry the driver schema fields + the labelled her-count',
              all({'file', 'bytes', 'sha256', 'video_s', 'role',
                   'expected_frames_measured', 'her_frames_counted'}
                  <= set(r) for r in rows)
              and all(r['role'] == 'measured' for r in rows)
              and all(r['expected_frames_measured'] == 123 for r in rows))
        check('N equals the selection (k=2 over the synthetic strata)',
              res['n'] == len(rows) == meta['n_measured'])

        # Fail-closed: corrupt one selected file -> the build aborts.
        victim = rows[0]['file']
        (corpus / victim).write_bytes(b'CORRUPT')
        try:
            build_manifest(man, 'ff' * 32, corpus, 2, d / 'm2.jsonl',
                           's3://example/prefix', 15,
                           fetch_fn=lambda *a: None,
                           measure_fn=lambda p: 123,
                           ff_prov={'path': 'stub', 'sha256': '0' * 64,
                                    'version': 'stub'})
            check('arrival verification refuses a corrupted film', False)
        except SystemExit as e:
            check('arrival verification refuses a corrupted film',
                  'FAILED arrival verification' in str(e) and victim in str(e))
        check('the refused build wrote nothing', not (d / 'm2.jsonl').exists())

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--her-manifest',
                    default=str(Path.home() / 'films_manifest/corpus_manifest.json'))
    ap.add_argument('--her-manifest-sha-expected', default=HER_MANIFEST_SHA_RULED)
    ap.add_argument('--corpus-dir', default=None,
                    help='REQUIRED — no corpus-naming defaults (entry 15)')
    ap.add_argument('--k', type=positive_int('k', 50), default=4)
    ap.add_argument('--out',
                    default=str(Path(__file__).resolve().parent
                                / 'films_video_manifest.jsonl'))
    ap.add_argument('--s3-prefix', default=S3_PREFIX_DEFAULT)
    ap.add_argument('--interval-s', type=positive_int('interval-s', 3600),
                    default=15)
    ap.add_argument('--aws', default='aws',
                    help='aws binary (absolute path under nohup — her trap #8)')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.corpus_dir:
        ap.error('--corpus-dir is required (entry 15: no corpus-naming defaults)')
    if not re.fullmatch(r'[0-9a-f]{64}', args.her_manifest_sha_expected):
        ap.error('--her-manifest-sha-expected must be 64 lowercase hex chars')

    her_path = Path(args.her_manifest).expanduser()
    if not her_path.is_file():
        raise SystemExit(f'NOT DONE — her manifest not found: {her_path}')
    data = her_path.read_bytes()
    her_sha = hashlib.sha256(data).hexdigest()
    if her_sha != args.her_manifest_sha_expected:
        raise SystemExit(f'NOT DONE — her manifest sha {her_sha} != expected '
                         f'{args.her_manifest_sha_expected}. Refusing to '
                         'select from an unverified corpus definition.')
    print(f'her manifest verified: {her_sha}')

    ff_prov = ffmpeg_provenance()
    print(f'expectation ffmpeg: {ff_prov["version"]} (sha {ff_prov["sha256"][:16]}…)')
    corpus_dir = Path(args.corpus_dir).expanduser()
    out = Path(args.out)

    res = build_manifest(
        json.loads(data), her_sha, corpus_dir, args.k, out,
        args.s3_prefix, args.interval_s,
        fetch_fn=lambda pfx, doc, dest: fetch_via_aws(pfx, doc, dest, args.aws),
        measure_fn=lambda p: measure_expected_frames(ff_prov['path'], p,
                                                     args.interval_s),
        ff_prov=ff_prov)

    rb = [json.loads(l) for l in out.read_text().splitlines()]  # entry 22
    man_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f'wrote {out} — {res["n"]} measured rows + meta '
          f'(read back: {len(rb)} lines)')
    print(f'FILMS SUBSET MANIFEST sha256: {man_sha}')
    print('entry 26: the artifact bundle after this is a STOP-AND-LAND step — '
          'nothing else pushes until it is fetched and ls-remote confirms.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
