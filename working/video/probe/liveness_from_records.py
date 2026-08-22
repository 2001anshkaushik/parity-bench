#!/usr/bin/env python3
"""LIVENESS_MIN from every record we hold — gate 5's threshold, derived.

Gate 5 (`detection_liveness`) refuses to invent its own threshold: the fraction
of frames carrying >=1 detection is a property of the corpus and the view, so
it is MEASURED and supplied. This reads every artifact that carries per-frame
detection data, prints the fraction per video, and reports the minimum with the
sample size — because a threshold from n=1 is an assumption, not a measurement,
and the export has to say which it is.

THREE SCHEMAS, one quantity (each verified in the tree, 2026-08-22):
  * driver records, LI arm   — 'detections_per_frame': LIST of ints per frame
  * driver records, RR arm   — 'frame_label_multisets': LIST of per-frame label
                               lists (the RR arm cannot recover n_detections
                               client-side; the multiset length is the count)
  * probe_rr_t*.json         — the same multisets, nested under 'sends'
  * probe_li_floor_t*.json   — 'frame_label_multisets' as above, BUT its
                               'detections_per_frame' is a FLOAT AVERAGE, not a
                               list (probe_li_floor.py:151). A reader that takes
                               that key by name and iterates it computes
                               garbage silently — so every source here is
                               type-checked before it is used, never by key
                               name alone.

Usage (box, repo root):
  ~/.venv/bin/python working/video/probe/liveness_from_records.py \
      working/video/results/mainrun_*/records_*.jsonl \
      working/video/probe/probe_rr_t*.json \
      working/video/probe/probe_li_floor_t*.json

Exit 0 always: this reports, it does not gate. The number is Ansh's ruling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _counts_from(obj) -> list | None:
    """Per-frame detection counts from one record-shaped dict, or None.
    TYPE-CHECKED, never taken on the key's name (see the module docstring)."""
    if not isinstance(obj, dict):
        return None
    dpf = obj.get('detections_per_frame')
    if isinstance(dpf, list) and dpf and all(isinstance(x, (int, float)) for x in dpf):
        return [int(x) for x in dpf]
    fls = obj.get('frame_label_multisets')
    if isinstance(fls, list) and fls and all(isinstance(x, list) for x in fls):
        return [len(x) for x in fls]
    return None


def _walk(obj, out: list, label: str) -> None:
    """Depth-first: any dict anywhere that carries per-frame counts contributes.
    Keeps this reader working across the probe/report shapes without hardcoding
    a path into each one."""
    counts = _counts_from(obj)
    if counts:
        name = (obj.get('video') or obj.get('file') or obj.get('name')
                or obj.get('tag') or label)
        out.append((name, counts))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, out, f'{label}:{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, out, f'{label}[{i}]')


def load(path: Path) -> list:
    out: list = []
    try:
        if path.suffix == '.jsonl':
            for i, line in enumerate(path.read_text().splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue           # torn last line: tolerated, reported below
                if isinstance(rec, dict) and 'error' in rec:
                    continue
                _walk(rec, out, f'{path.name}#{i}')
        else:
            _walk(json.loads(path.read_text()), out, path.name)
    except Exception as exc:  # noqa: BLE001 — a bad file is reported, never fatal
        print(f'  !! {path.name}: unreadable ({exc!r})')
    return out


def main() -> int:
    args = [Path(p) for p in sys.argv[1:]]
    if not args:
        print(__doc__)
        return 0
    rows = []
    for path in args:
        if not path.exists():
            print(f'  -- {path} (absent)')
            continue
        found = load(path)
        print(f'  {path.name}: {len(found)} video(s) with per-frame data')
        for name, counts in found:
            frac = sum(1 for c in counts if c > 0) / len(counts)
            rows.append({'source': path.name, 'video': str(name),
                         'frames': len(counts), 'nonempty_fraction': frac,
                         'mean_det_per_frame': sum(counts) / len(counts)})
    if not rows:
        print('\nNO per-frame detection data found in the given files. Gate 5 stays '
              'NOT RUN (a first-class verdict) until a source exists.')
        return 0

    print(f'\n{"source":36s} {"video":28s} {"frames":>7s} {"nonempty":>9s} {"det/frame":>10s}')
    for r in sorted(rows, key=lambda r: r['nonempty_fraction']):
        print(f'{r["source"][:36]:36s} {r["video"][-28:]:28s} {r["frames"]:7d} '
              f'{r["nonempty_fraction"]:9.3f} {r["mean_det_per_frame"]:10.2f}')

    fracs = [r['nonempty_fraction'] for r in rows]
    lo, n = min(fracs), len(fracs)
    print(f'\nMINIMUM non-empty fraction: {lo:.3f} over n={n} video-observation(s)')

    # NULL CONTROL: a dead detector (the black fixture) produces zero detections
    # on every frame. It must read 0.000 here and must FAIL any threshold worth
    # setting — a control that cannot fail is not a control.
    black = _counts_from({'detections_per_frame': [0] * 60})
    assert black is not None and sum(1 for c in black if c > 0) / len(black) == 0.0
    # And the float-average trap must NOT be mistaken for per-frame data.
    assert _counts_from({'detections_per_frame': 25.95}) is None, \
        'the probe_li_floor float average was read as per-frame counts'
    print('null control fired: an all-zero (black-fixture) video reads 0.000, and a '
          'float detections_per_frame average is refused as a source')

    if n < 3:
        print(f'\n*** SAMPLE OF {n}. A threshold from this is an ASSUMPTION, not a '
              'measurement — state it as one in the export (a dry pass clamps every '
              'leg to n=1, so add the probe/gate-3 artifacts before deciding).')
    if lo >= 0.9:
        print(f'\nHeadroom is wide (min {lo:.3f}). A threshold at 0.50 sits far below '
              'anything measured and still fails the black fixture (0.000).')
    else:
        print(f'\nMinimum observed is {lo:.3f} — NOT wide headroom. Do not pick a '
              'threshold from this without more videos; a gate set near the observed '
              'minimum fails on ordinary variation, and one set far below it stops '
              'detecting anything.')
    print('The value is Ansh\'s ruling: it must sit below the minimum observed with '
          'margin AND above what a dead detector produces (0.000).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
