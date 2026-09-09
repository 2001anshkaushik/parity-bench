#!/usr/bin/env python3
"""Fetch exactly the AMI comparison-arm artifacts needed to RECOMPUTE peak memory,
identify each cell BY CONTENTS, and hand them to `ami_li_memory_recompute.py`.

Laptop-side, read-only, no box. Nothing is written into the repository: the fetch
lands in a scratch directory and the derived report is a separate landing decision.

IDENTIFICATION IS BY CONTENTS, NOT BY DIRECTORY NAME — the rule
`results/AMI_LANDING.md` already had to learn once, when an in-repo run-dir name
turned out to carry a dry pass. Every export in the archive is read and matched
on its own recorded `throughput.total_frames_per_s` against the banked cells:

    balanced 8x4 (headline)   12.745 / 12.733
    default W=8               9.267 / 8.714
    default W=16              8.793

A cell with no match is reported as unmatched; a value matching two exports is
reported as ambiguous. Only matched legs' tick streams are pulled.

Usage:
  fetch_ami_li_memory.py [--out DIR] [--profile rocketride] [--dry-run]

Fail-closed: refuses up front if the SSO token is not live, naming the login
command, rather than half-fetching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PREFIX = 's3://rocketride-benchmark-data/ansh/video-ami-20260826/'
TARGETS = {  # cell -> the banked span f/s values, per pass
    'LI balanced 8x4 (headline)': ['12.745', '12.733'],
    'LI default W=8': ['9.267', '8.714'],
    'LI default W=16': ['8.793'],
}
DEFAULT_OUT = Path('/private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/'
                   'c0f68317-4ce1-4c17-9f8a-c77198cc48e1/scratchpad/ami_li_fetch')


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--profile', default='rocketride')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    out = Path(a.out)
    prof = ['--profile', a.profile]

    probe = run(['aws', 's3', 'ls', PREFIX] + prof)
    if probe.returncode != 0:
        print('NOT DONE — the archive is not readable with this profile. Nothing fetched.\n'
              f'  aws said: {(probe.stderr or probe.stdout).strip().splitlines()[-1] if (probe.stderr or probe.stdout).strip() else "no output"}\n'
              f'  fix: aws sso login --profile {a.profile}   (browser, one time; the token lasts ~8 h)',
              file=sys.stderr)
        return 1

    listing = run(['aws', 's3', 'ls', PREFIX, '--recursive'] + prof)
    if listing.returncode != 0:
        print(f'NOT DONE — recursive listing failed: {listing.stderr.strip()}', file=sys.stderr)
        return 1
    keys = []
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            keys.append((int(parts[2]), parts[3]))
    exports = [(sz, k) for sz, k in keys if Path(k).name.startswith('export_')]
    li_exports = [(sz, k) for sz, k in exports if 'llamaindex' in Path(k).name]
    print(f'archive: {len(keys)} objects, {len(exports)} exports, {len(li_exports)} comparison-arm exports')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'archive_listing.txt').write_text(listing.stdout)
    if a.dry_run:
        for sz, k in li_exports:
            print(f'  would fetch  {sz:>12,}  {k}')
        return 0

    bucket = PREFIX.split('/')[2]
    fetched = {}

    def pull(key: str) -> Path:
        dest = out / Path(key).relative_to(Path(key).parts[0] + '/' + Path(key).parts[1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            r = run(['aws', 's3', 'cp', f's3://{bucket}/{key}', str(dest), '--quiet'] + prof)
            if r.returncode != 0:
                raise SystemExit(f'NOT DONE — fetch failed for {key}: {r.stderr.strip()}')
        fetched[key] = {'local': str(dest), 'sha256': sha256(dest), 'bytes': dest.stat().st_size}
        return dest

    # every comparison-arm export first: identification needs their contents
    by_fs = {}
    for _sz, k in li_exports:
        p = pull(k)
        try:
            fs = (json.loads(p.read_text()).get('throughput') or {}).get('total_frames_per_s')
        except json.JSONDecodeError:
            print(f'  WARNING unreadable export {k}')
            continue
        by_fs.setdefault(f'{fs:.3f}' if isinstance(fs, (int, float)) else str(fs), []).append(k)

    matched, unmatched = {}, {}
    for cell, values in TARGETS.items():
        for v in values:
            hits = by_fs.get(v, [])
            if len(hits) == 1:
                matched[f'{cell} @ {v}'] = hits[0]
            elif not hits:
                unmatched[f'{cell} @ {v}'] = 'no export in the archive carries this f/s'
            else:
                unmatched[f'{cell} @ {v}'] = f'AMBIGUOUS — {len(hits)} exports carry it: {hits}'

    # only matched legs' streams
    for label, key in sorted(matched.items()):
        stem = Path(key).name[len('export_'):-len('.json')]
        d = str(Path(key).parent)
        for name in (f'collector_{stem}.jsonl', f'collector_{stem}.summary.json'):
            k2 = f'{d}/{name}'
            if any(k2 == k for _s, k in keys):
                pull(k2)
            else:
                print(f'  note: {name} absent from the archive for {label}')

    manifest = {'prefix': PREFIX, 'matched_cells': matched, 'unmatched_cells': unmatched,
                'f_per_s_index': by_fs, 'fetched': fetched}
    (out / 'fetch_manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'\nmatched {len(matched)} leg(s); unmatched {len(unmatched)}')
    for lbl, k in sorted(matched.items()):
        print(f'  MATCH  {lbl:34s} {k}')
    for lbl, why in sorted(unmatched.items()):
        print(f'  MISS   {lbl:34s} {why}')
    print(f'\nfetched {len(fetched)} file(s) into {out}; manifest with sha256 at {out}/fetch_manifest.json')
    print('next: python3 working/video/probe/ami_li_memory_recompute.py --dir '
          f'{out} --out {out}/ami_li_memory_recomputed.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
