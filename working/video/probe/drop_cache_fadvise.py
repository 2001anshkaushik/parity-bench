#!/usr/bin/env python3
"""Page-cache eviction WITHOUT sudo: posix_fadvise(POSIX_FADV_DONTNEED) per file,
with a read-back that PROVES eviction instead of asserting it.

Why this exists: settled decision 4 drops the page cache before each arm, but
ssm-user's passwordless sudo is unverified on the box. drop_caches needs root;
fadvise(DONTNEED) evicts a specific file's clean pages as the owning user —
which is exactly the scope we need (the corpus), and it leaves the rest of the
machine's cache alone (arguably better than `echo 3`, which also evicts the
engine's own pages).

READ-BACK (two, independent):
  1. /proc/meminfo Cached before/after — the system-level delta.
  2. Behavioral, per sampled file: time a sequential 8 MiB read; page-cache reads
     run at memory speed (>~1.5 GB/s), device reads at device speed. A sampled
     file still reading hot after DONTNEED = eviction did NOT take -> exit 1.
     (The sample read itself re-caches 8 MiB of up to 3 files — negligible
     against a multi-GB corpus, and stated here rather than hidden.)

Usage:
    python3 drop_cache_fadvise.py FILE [FILE...]        # evict + prove
    python3 drop_cache_fadvise.py --check-only FILE...  # residency probe only
Exit 0 = evicted and proven cold; 1 = a sampled file still reads hot; 2 = usage.
"""

import argparse
import json
import os
import sys
import time

HOT_BYTES_PER_S = 1.5e9   # above this, an 8 MiB read came from page cache
SAMPLE_BYTES = 8 * 1024 * 1024


def meminfo_cached_kb() -> int | None:
    try:
        with open('/proc/meminfo') as fh:
            for line in fh:
                if line.startswith('Cached:'):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def sample_read_speed(path: str) -> float:
    """Bytes/s over the first 8 MiB, O_DIRECT-less — cache-speed detector."""
    fd = os.open(path, os.O_RDONLY)
    try:
        t0 = time.monotonic()
        got = 0
        while got < SAMPLE_BYTES:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            got += len(block)
        wall = time.monotonic() - t0
        return got / wall if wall > 0 else float('inf')
    finally:
        os.close(fd)


def evict(paths: list[str]) -> dict:
    report = {'cached_kb_before': meminfo_cached_kb(), 'files': len(paths), 'errors': []}
    total = 0
    for p in paths:
        try:
            fd = os.open(p, os.O_RDONLY)
            try:
                os.fsync(fd)  # flush any dirty pages so DONTNEED can drop them
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                total += os.fstat(fd).st_size
            finally:
                os.close(fd)
        except OSError as e:
            report['errors'].append(f'{p}: {e}')
    report['bytes_advised'] = total
    report['cached_kb_after'] = meminfo_cached_kb()
    if report['cached_kb_before'] and report['cached_kb_after']:
        report['cached_delta_mb'] = round(
            (report['cached_kb_before'] - report['cached_kb_after']) / 1024, 1)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--check-only', action='store_true')
    ap.add_argument('--samples', type=int, default=3,
                    help='files to behaviorally verify (first, middle, last)')
    args = ap.parse_args()
    paths = [p for p in args.paths if os.path.isfile(p)]
    if not paths:
        print('no files exist among arguments', file=sys.stderr)
        return 2
    if not args.check_only and not hasattr(os, 'posix_fadvise'):
        print('posix_fadvise unavailable on this platform (Linux-only tool)', file=sys.stderr)
        return 2

    report = {'mode': 'check-only'} if args.check_only else evict(paths)

    idx = sorted({0, len(paths) // 2, len(paths) - 1})[:args.samples]
    hot = []
    speeds = {}
    for i in idx:
        s = sample_read_speed(paths[i])
        speeds[os.path.basename(paths[i])] = f'{s / 1e6:.0f} MB/s'
        if s > HOT_BYTES_PER_S:
            hot.append(os.path.basename(paths[i]))
    report['sample_read_speeds'] = speeds
    report['still_hot'] = hot or None
    print(json.dumps(report, indent=1))
    if not args.check_only and hot:
        print(f'EVICTION NOT PROVEN — {hot} still read at cache speed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
