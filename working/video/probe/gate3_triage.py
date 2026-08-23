#!/usr/bin/env python3
"""Gate 3 divergence triage — the actual question, not the aggregate.

When `cross_detection_agreement` fails, `gates_shared.score_triage` reports
aggregate score deltas over frames whose detection COUNTS match. At a diverging
frame the counts usually differ by exactly the flapped detection, so that frame
is excluded from the paired deltas and lands in `n_frames_count_mismatch` — the
aggregate says "counts differ" without saying WHICH detection or at what score.

This prints, per diverging frame, the symmetric difference of the two label
multisets and the SCORES of the detections that appear on one arm only. That
distinguishes the two hypotheses directly:

  * NEAR-THRESHOLD FLAP — the extra/missing detection's score sits within a few
    thousandths of the configured threshold (0.3). Float reduction-order
    differences move a borderline detection across the cut.
  * WHOLESALE DIFFERENCE — the differing detection scores far from the
    threshold, or many labels differ. First hypothesis stays a REAL difference
    (model swap, resize path, version drift), per the standing ruling.

DIAGNOSTIC ONLY. This never produces a verdict and never feeds a gate; only a
human downgrades gate 3, in writing, with the reason.

Usage:
  gate3_triage.py <cross_*.json> <records_rocketride_*.jsonl> <records_llamaindex_*.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_records(path: Path) -> dict:
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
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    cross = json.loads(Path(sys.argv[1]).read_text())
    rr = load_records(Path(sys.argv[2]))
    li = load_records(Path(sys.argv[3]))

    agree = cross.get('cross_detection_agreement') or {}
    failing = agree.get('failing') or []
    print(f"gate 3: PASS={agree.get('PASS')}  armed_by={agree.get('armed_by_probe_run')}  "
          f"n_videos={agree.get('n_videos')}  failing={len(failing)}")
    if not failing:
        print('no failing videos in this cross file')
        return 0

    threshold = 0.3          # the configured detect threshold, both arms
    for video in failing:
        pv = (agree.get('per_video') or {}).get(video) or {}
        idx = pv.get('diverging_frames') or []
        print(f"\n=== {video}: {pv.get('n_diverging')} of {pv.get('n_frames')} frames diverge "
              f"({(pv.get('n_diverging') or 0) / max(1, pv.get('n_frames') or 1):.3%})")
        if pv.get('reason'):
            print(f"    reason: {pv['reason']}")
        r, m = rr.get(video), li.get(video)
        if not r or not m:
            print('    records missing for this video on one arm — cannot triage')
            continue
        ra, ma = r.get('frame_label_multisets') or [], m.get('frame_label_multisets') or []
        rs, ms = r.get('frame_scores') or [], m.get('frame_scores') or []
        for i in idx:
            if i >= len(ra) or i >= len(ma):
                print(f"    frame {i}: index beyond one arm's frame list")
                continue
            ca, cb = Counter(ra[i]), Counter(ma[i])
            only_rr, only_li = ca - cb, cb - ca
            sa = sorted(rs[i]) if i < len(rs) else []
            sb = sorted(ms[i]) if i < len(ms) else []
            # the scores present on one side only, by multiset difference
            da, db = Counter(sa) - Counter(sb), Counter(sb) - Counter(sa)
            odd = sorted([s for s in da.elements()] + [s for s in db.elements()])
            near = [s for s in odd if abs(s - threshold) <= 0.02]
            print(f"    frame {i:4d}: rr={len(ra[i])} dets, li={len(ma[i])} dets")
            print(f"        only on RR: {dict(only_rr) or '-'}    only on LI: {dict(only_li) or '-'}")
            if odd:
                print(f"        unmatched scores: {[round(s, 4) for s in odd]}")
                print(f"        distance to threshold {threshold}: "
                      f"{[round(abs(s - threshold), 4) for s in odd]}")
                print(f"        -> {'NEAR-THRESHOLD (within 0.02)' if near and len(near) == len(odd) else 'NOT all near threshold'}")
            else:
                print('        scores identical on both arms — labels differ with equal scores, '
                      'which is NOT a threshold flap')
    print('\nDIAGNOSTIC ONLY — gate 3 stays FAILED until a human downgrades it in writing.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
