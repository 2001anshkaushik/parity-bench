#!/usr/bin/env python3
"""Flatten probe_rr_t*.json into the RR thread curve — and print the two
probe-measured inputs the Crossroad-23 manifest re-cut requires.

Exists because the first attempt to read the curve queried keys that do not
exist in probe_rr's schema (total_s / send1_s / cpu_cores / peak_anon_mb) and
got None for everything — which read as "the runs produced nothing" while the
same files were simultaneously PASSING gate-3 staging. The real schema:

    report.sends[i].label                      'first-load' | 'steady-state'
    report.sends[i].wall_s                     per-send wall seconds
    report.sends[i].documents.n_chunks         chunks in the response
    report.sends[i].documents.total_chars      chars entering the splitter
    report.sends[i].documents.frames_from_chunks / frames_rawdecode
    report.sends[i].cgroup.cpu_s               container CPU-seconds this send
    report.sends[i].cgroup.cpu_util_of_32      cores-of-32 utilisation
    report.sends[i].cgroup.memory_peak_bytes / anon_bytes_after

Run from the probe dir (box):  ~/.venv-floor/bin/python summarize_probe_rr.py

2026-08-23 — IT POOLED ACROSS VIDEOS SILENTLY. It globbed probe_rr_t*.json and
summed steady-state frames/detections/chars over whatever was on disk, with no
check of which video produced each file. That is not only a wrong curve: the two
lines it prints, --measured-dpf and --measured-chars-per-det, are the inputs to
the Crossroad-23 manifest re-cut, so a stale file from another corpus silently
re-cuts the manifest. Pooling several videos is legitimate (B1 pooled 3 Closeup1
videos deliberately) — pooling them WITHOUT SAYING SO is not. Files are now
grouped by recorded video identity, the grouping is always printed, and more
than one video refuses unless --all-videos makes the pooling explicit.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from artifact_identity import ABSENT, RC_CANNOT_COMPARE, cannot_compare


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    ap.add_argument('dir', nargs='?', default='.', help='directory of probe_rr_t*.json')
    ap.add_argument('--all-videos', action='store_true',
                    help='pool every video present — an EXPLICIT choice, printed in the output')
    args = ap.parse_args()

    where = Path(args.dir)
    groups: dict = defaultdict(list)
    for f in sorted(where.glob('probe_rr_t*.json')):
        try:
            doc = json.loads(f.read_text())
        except Exception:                     # noqa: BLE001 — unreadable is named, not skipped
            groups['UNREADABLE'].append((f, {}))
            continue
        groups[doc.get('video_sha16') or ABSENT].append((f, doc))
    if not groups:
        print(f'NOT DONE — no probe_rr_t*.json in {where} (pass the directory as arg 1)')
        return 1

    print('== artifacts by recorded video identity ==')
    for sha, items in sorted(groups.items()):
        name = next((d.get('video') for _, d in items if d.get('video')), '?')
        print(f'  {sha}  {Path(str(name)).name}  <- {[f.name for f, _ in items]}')
    usable = {k: v for k, v in groups.items() if k not in (ABSENT, 'UNREADABLE')}
    for bad in (ABSENT, 'UNREADABLE'):
        if bad in groups:
            print(f'  EXCLUDED ({bad}): {[f.name for f, _ in groups[bad]]} — cannot prove '
                  'which video produced these; re-run with the current probes')
    if not usable:
        print(cannot_compare('thread curve', 'no artifact can prove which video produced it'))
        return RC_CANNOT_COMPARE
    if len(usable) > 1 and not args.all_videos:
        print(cannot_compare(
            'thread curve', f'{len(usable)} DIFFERENT videos are present and pooling them would '
            'blend corpora into one curve — and into --measured-dpf / --measured-chars-per-det, '
            'which re-cut the manifest. Move the stale files aside, or pass --all-videos to pool '
            'them deliberately'))
        return RC_CANNOT_COMPARE
    pooled = sorted({next((str(d.get('video')) for _, d in v if d.get('video')), '?')
                     for v in usable.values()})
    print(f'\n== curve over {len(pooled)} video(s), pooling DECLARED: '
          f'{[Path(x).name for x in pooled]} ==')

    files = [f for v in usable.values() for f, _ in v]
    docs = {f: d for v in usable.values() for f, d in v}
    tot_frames = tot_dets = tot_chars = 0
    for f in sorted(files):
        r = docs[f]
        print(f'\n== {Path(f).name}  (tokens={r.get("tokens")}, rc={r.get("rc")})')
        for s in r.get('sends', []):
            d = s.get('documents') or {}
            cg = s.get('cgroup') or {}
            mult = d.get('frame_label_multisets') or []
            dets = sum(len(m) for m in mult)
            print(f"  {s.get('label', '?'):12} wall_s={s.get('wall_s')} "
                  f"n_chunks={d.get('n_chunks')} total_chars={d.get('total_chars')} "
                  f"frames={d.get('frames_from_chunks')}/{d.get('frames_rawdecode')} "
                  f"(bracket/rawdecode) dets={dets} "
                  f"cpu_s={cg.get('cpu_s')} cores_of_32={cg.get('cpu_util_of_32')} "
                  f"peak_mb={round((cg.get('memory_peak_bytes') or 0) / 1048576)} "
                  f"anon_mb={round((cg.get('anon_bytes_after') or 0) / 1048576)} "
                  f"doubled={d.get('whole_list_doubled')}")
            if s.get('label') == 'steady-state' and d.get('frames_rawdecode'):
                tot_frames += d['frames_rawdecode']
                tot_dets += dets
                tot_chars += d.get('total_chars') or 0
    if tot_frames and tot_dets:
        print('\n== Crossroad-23 re-cut inputs (steady-state sends, probe-measured) ==')
        print(f'  pooled over: {[Path(x).name for x in pooled]}')
        print(f'  --measured-dpf {tot_dets / tot_frames:.2f}   '
              f'(detections/frame over {tot_frames} frames)')
        print(f'  --measured-chars-per-det {tot_chars / tot_dets:.1f}   '
              f'(chars entering the splitter / detection)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
