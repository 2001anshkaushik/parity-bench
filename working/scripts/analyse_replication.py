#!/usr/bin/env python3
"""Analyse the matched replication, with the rule-5 inversion applied.

This result is expected to favour RocketRide, which makes it the one most likely to be wrong and
the one leadership most wants to hear. So the asymmetry ledger below hunts specifically for things
RocketRide GETS that LlamaIndex does not, and each is signed by which arm it favours.
"""
import json, math, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "working"))
S = ROOT / "repl_state"

def boot_ci(vals, n=4000, seed=12345):
    import random
    if len(vals) < 2: return (None, None)
    r = random.Random(seed); out = []
    for _ in range(n):
        s = [r.choice(vals) for _ in vals]
        out.append(statistics.median(s))
    out.sort()
    return round(out[int(n*0.025)], 1), round(out[int(n*0.975)], 1)

def ratio_ci(a, b, n=4000, seed=999):
    import random
    r = random.Random(seed); out = []
    for _ in range(n):
        x = statistics.median([r.choice(a) for _ in a])
        y = statistics.median([r.choice(b) for _ in b])
        if y: out.append(x/y)
    out.sort()
    return round(statistics.median(out),3), round(out[int(len(out)*0.025)],3), round(out[int(len(out)*0.975)],3)

blocks = []
for f in sorted(S.glob("b*.json")):
    d = json.loads(f.read_text())
    if d.get("status") == "completed":
        blocks.append(d)
print(f"completed blocks: {len(blocks)} / 6")
if len(blocks) < 6:
    print("  INCOMPLETE — analysis below is partial and must not be quoted as the result")

order = {b["block"]: i for i, b in enumerate(sorted(blocks, key=lambda x: x.get("elapsed_s", 0)))}
print("\n" + "="*96); print("PER-BLOCK RESULTS"); print("="*96)
print(f"{'block':16s} {'arm':11s} {'docs':>5s} {'good':>5s} {'flt':>4s} {'susp':>5s} "
      f"{'medRSS':>8s} {'peak':>8s} {'min':>7s}")
for b in blocks:
    v = [x["rss_mb"] for x in b["rss"] if x["n"] > 50]
    print(f"{b['block']:16s} {b['arm']:11s} {b['next']:5d} {b['goodput']:5d} "
          f"{sum(b['faults'].values()):4d} {b['content_suspect']:5d} "
          f"{b['median_rss_post_warmup'] or 0:8.0f} {b['peak_rss_mb']:8.0f} {b['elapsed_s']/60:6.1f}m")

print("\n" + "="*96); print("PER-ARM, GATED"); print("="*96)
summ = {}
for arm in ("rocketride", "llamaindex"):
    rows = [b for b in blocks if b["arm"] == arm]
    if not rows: continue
    med = [b["median_rss_post_warmup"] for b in rows if b["median_rss_post_warmup"]]
    if not med: continue
    spread = (max(med)-min(med))/max(med)
    gate = len(med) >= 3 and spread <= 0.10
    lo, hi = boot_ci(med)
    summ[arm] = {"medians": med, "median": statistics.median(med), "spread": spread,
                 "gate": gate, "ci": (lo, hi),
                 "goodput": [b["goodput"] for b in rows],
                 "faults": [b["faults"] for b in rows],
                 "suspect": [b["content_suspect"] for b in rows],
                 "peaks": [b["peak_rss_mb"] for b in rows],
                 "mins": [b["elapsed_s"]/60 for b in rows]}
    print(f"  {arm:11s} n={len(med)} medians={[round(m) for m in med]} -> {statistics.median(med):.0f} MB")
    print(f"              spread {spread*100:5.1f}%  {'GATE OK' if gate else 'GATE FAIL'}   "
          f"median CI95 [{lo}, {hi}] MB")
    print(f"              peaks {[round(p) for p in summ[arm]['peaks']]}  "
          f"goodput {summ[arm]['goodput']}  content-suspect {summ[arm]['suspect']}")

if len(summ) == 2:
    r, l = summ["rocketride"], summ["llamaindex"]
    pt, lo, hi = ratio_ci(r["medians"], l["medians"])
    both = r["gate"] and l["gate"]
    print("\n" + "="*96)
    print(f"MATCHED MEMORY RATIO  RocketRide / LlamaIndex = {pt} [{lo}, {hi}]")
    print(f"  both gates pass: {both}  ->  {'QUOTABLE POINT ESTIMATE' if both else 'DIRECTION ONLY'}")
    print("="*96)
    # run cost, explicitly not a benchmark
    print(f"\nRUN COST (NOT a throughput benchmark — A13):")
    print(f"  RocketRide {statistics.median(r['mins']):.1f} min/2000 docs   "
          f"LlamaIndex {statistics.median(l['mins']):.1f} min/2000 docs")
    print(f"  direction: {'RocketRide faster' if statistics.median(r['mins'])<statistics.median(l['mins']) else 'LlamaIndex faster'} "
          f"by {max(statistics.median(r['mins']),statistics.median(l['mins']))/min(statistics.median(r['mins']),statistics.median(l['mins'])):.2f}x")
    print(f"  ^ reported as run cost only. Not quotable: A13 is a property of this host.")
