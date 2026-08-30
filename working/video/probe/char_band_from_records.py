#!/usr/bin/env python3
"""Crossroad 38 — the video char-conservation band, MEASURED from a named run.

Phase 1's +/-2% was calibrated on PDF text where both arms ran the same
splitter. On the video workload they do not: RR runs LangChain's
RecursiveCharacterTextSplitter (library defaults 4000/200, config inert) and
the LI arm runs LlamaIndex-native SentenceSplitter (approved decision 3) —
4000/200 in the AMI era, 4000/0 from RULING L (2026-08-30) on. Two native
splitters on byte-identical input produce different chunk boundaries, so the
cross-arm char ratio has a SYSTEMATIC offset that has nothing to do with
content loss — and the offset is CONFIG-BOUND: a band cut from records at one
overlap config does not carry to the other (the films band is cut from films
records at 4000/0; RULING_L_SPLITTER_EQUIVALENCE.md). A band anchored at 1.0 measures that offset; a band anchored at
the offset measures what the gate is actually for.

So the band is centred on the MEASURED ratio and its width comes from the
observed per-video spread — never from a number picked to make a known result
pass. It prints the sensitivity it buys, in chars, detections and frames,
because a band that cannot detect content loss is not a gate.

Usage:
  char_band_from_records.py <records_rr.jsonl> <records_li.jsonl> \
      [--dpf 25.95] [--chars-per-det 230.4] [--margin 1.5] [--run-id <id>]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path


def load(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and 'error' not in r and r.get('video'):
            out[r['video']] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('rr'); ap.add_argument('li')
    ap.add_argument('--dpf', type=float, default=25.95,
                    help='measured detections/frame for the calibrating corpus')
    ap.add_argument('--chars-per-det', type=float, default=230.4)
    ap.add_argument('--margin', type=float, default=1.5,
                    help='half-width = margin x the worst observed deviation from centre')
    ap.add_argument('--run-id', default=None, help='the calibrating run, named in the export')
    a = ap.parse_args()

    rr, li = load(Path(a.rr)), load(Path(a.li))
    pairs = []
    for v, r in rr.items():
        m = li.get(v)
        if not m:
            continue
        x, y = r.get('sum_chunk_chars'), m.get('sum_chunk_chars')
        if x and y:
            pairs.append((v, x, y, x / y))
    if len(pairs) < 5:
        print(f'NOT DONE — only {len(pairs)} paired videos; a band from this is not a '
              'measurement. Refusing to propose one.')
        return 1

    ratios = sorted(p[3] for p in pairs)
    centre = st.median(ratios)
    dev = [abs(x - centre) for x in ratios]
    worst = max(dev)
    half = worst * a.margin
    lo, hi = centre - half, centre + half

    print(f'paired videos: {len(pairs)}   calibrating run: {a.run_id or "UNNAMED (pass --run-id)"}')
    print(f'ratio rr/li  min {ratios[0]:.5f}  median {centre:.5f}  max {ratios[-1]:.5f}'
          f'   spread {ratios[-1] - ratios[0]:.5f}')
    print(f'deviation from 1.0: median {abs(1 - centre) * 100:.3f}%  worst {max(abs(1 - x) for x in ratios) * 100:.3f}%')
    print(f'deviation from CENTRE: worst {worst * 100:.3f}%  ->  half-width '
          f'{worst * 100:.3f}% x {a.margin} = {half * 100:.3f}%')
    print(f'\nPROPOSED BAND (centred, not anchored at 1.0): [{lo:.5f}, {hi:.5f}]')

    # --- what does it still catch? the only question that makes it a gate -----
    mean_chars = st.mean(p[2] for p in pairs)          # LI side as the reference volume
    loss_chars = half * mean_chars
    loss_dets = loss_chars / a.chars_per_det
    loss_frames = loss_dets / a.dpf
    print(f'\nSENSITIVITY on a mean video of {mean_chars:,.0f} chars:')
    print(f'  smallest content change that still trips the band: {loss_chars:,.0f} chars'
          f'  ~= {loss_dets:,.0f} detections  ~= {loss_frames:,.1f} frames')
    if loss_frames > 5:
        print('  *** THE BAND IS WRONG — it would not notice several whole frames going '
              'missing. Do not adopt it; investigate the spread instead.')
        return 1
    print('  (a band anchored at 1.0 with the same half-width would need '
          f'{(abs(1 - centre) + half) * 100:.2f}% and would catch only '
          f'{((abs(1 - centre) + half) * mean_chars) / a.chars_per_det / a.dpf:,.1f} frames'
          ' — which is why the band is centred)')
    print('\nPDF band unchanged at 2% — this is a VIDEO-workload band, and the export must '
          'name the calibrating run beside it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
