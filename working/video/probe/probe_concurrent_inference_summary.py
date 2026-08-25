#!/usr/bin/env python3
"""Summarize probe_concurrent_inference.sh ticks: distribution of
simultaneously-busy task processes. Usage: summary.py <out.tsv> <M_expected>"""
import sys
from collections import Counter, defaultdict

BUSY_TICKS = 30           # >=0.3 cores within a ~1 s tick (USER_HZ=100)
rows = [l.split() for l in open(sys.argv[1]) if l.strip()]
m_expected = int(sys.argv[2])
by_pid = defaultdict(dict)
for tick, fname, ticks in rows:
    pid = fname.split('/')[2] if '/' in fname else fname
    by_pid[pid][int(tick)] = int(ticks)
busy_per_tick = Counter()
ticks_all = sorted({t for d in by_pid.values() for t in d})
for i in range(1, len(ticks_all)):
    t0, t1 = ticks_all[i - 1], ticks_all[i]
    dt = max(1, t1 - t0)
    n_busy = sum(1 for d in by_pid.values()
                 if t0 in d and t1 in d and (d[t1] - d[t0]) / dt >= BUSY_TICKS)
    busy_per_tick[n_busy] += 1
print(f'task processes observed: {len(by_pid)} (expected {m_expected})')
print('simultaneously-busy distribution (busy = >=0.3 cores/tick):')
for k in sorted(busy_per_tick):
    print(f'  {k:2d} busy: {busy_per_tick[k]:4d} tick(s)')
mx = max(busy_per_tick) if busy_per_tick else 0
print(f'max simultaneous: {mx}/{m_expected}')
print('VERDICT:', 'CONCURRENT — multiple task processes infer at once'
      if mx >= min(m_expected, 2) and m_expected > 1 else
      ('SERIALIZED across processes — investigate' if m_expected > 1 else
       f'null control: max {mx} (must be 1)'))
