#!/usr/bin/env python3
"""STEP 4 — native-vs-native memory over MATCHED windows, post-warm-up, contamination excluded.

Prior comparisons mixed windows: RocketRide's 267 documents against LlamaIndex's 10,000. This
compares only ranges both arms actually covered, drops the warm-up ramp, and states direction and
magnitude separately with their own labels.

Contamination note: the weekend-run RocketRide series counted a 5-day-old unrelated engine
(104 MB). The endurance run (session 14) resolves the engine by PID via lsof and does not. Both
are reported so the correction is visible rather than assumed.
"""
import json, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
S = ROOT / "weekend_state"
STALE_MB = 104.0        # measured: tree-by-name 215 MB vs tree-by-PID 111 MB

def load(n):
    p = S / f"{n}.json"
    return json.loads(p.read_text()) if p.exists() else None

def window(series, lo, hi, ramp=50):
    return [x for x in series if ramp <= x["n"] <= hi and x["n"] >= lo]

def stats(v):
    if not v: return None
    r = [x["rss_mb"] for x in v]
    return {"n": len(r), "median": statistics.median(r), "min": min(r), "max": max(r),
            "amplitude": max(r) - min(r)}

li = load("p2_llamaindex_llamaindex")
rr_old = load("p3_rocketride_rocketride")
rr_new = load("endurance_rocketride")
if not rr_new:
    print("endurance checkpoint not present yet"); sys.exit(0)

cover = rr_new["next_index"]
print("=" * 100)
print(f"MATCHED-WINDOW MEMORY — both arms native, post-warm-up (n>=50), RocketRide covered {cover} docs")
print("=" * 100)
for hi, label in ((267, "0-267 (the old RocketRide ceiling)"), (min(cover, li["next_index"]), f"0-{min(cover, li['next_index'])} (full overlap)")):
    a = stats(window(li["rss_series"], 0, hi)); b = stats(window(rr_new["rss_series"], 0, hi))
    if not a or not b: continue
    print(f"\n  window {label}")
    print(f"    LlamaIndex  median {a['median']:7.0f} MB  band {a['min']:.0f}-{a['max']:.0f}  amplitude {a['amplitude']:.0f}  (n={a['n']})")
    print(f"    RocketRide  median {b['median']:7.0f} MB  band {b['min']:.0f}-{b['max']:.0f}  amplitude {b['amplitude']:.0f}  (n={b['n']})")
    print(f"    ratio median RR/LI = {b['median']/a['median']:.2f}x")
    print(f"    ratio, LlamaIndex amplitude as a fraction of the gap: "
          f"{a['amplitude']/max(1,(b['median']-a['median']))*100:.0f}%")

# n=3 for RocketRide over the common 0-200 window: p0, p3, endurance
print("\n" + "=" * 100)
print("REPRODUCIBILITY — three independent RocketRide runs over the SAME first 200 documents")
print("=" * 100)
runs = [("p0_insurance_rr_rocketride", load("p0_insurance_rr_rocketride"), True),
        ("p3_rocketride_rocketride", rr_old, True),
        ("endurance_rocketride", rr_new, False)]
meds = []
for nm, d, contaminated in runs:
    if not d: continue
    st = stats(window(d["rss_series"], 0, 200))
    if not st: continue
    corr = st["median"] - (STALE_MB if contaminated else 0)
    meds.append(corr)
    print(f"  {nm:32s} median {st['median']:7.0f} MB  band {st['min']:.0f}-{st['max']:.0f}"
          f"  {'(-104 stale engine -> ' + format(corr,'.0f') + ')' if contaminated else '(PID-matched, clean)'}")
if len(meds) >= 3:
    print(f"\n  n=3 corrected medians: {[round(m) for m in meds]}")
    print(f"  spread {max(meds)-min(meds):.0f} MB  ({(max(meds)-min(meds))/statistics.median(meds)*100:.0f}% of median)")
liw = stats(window(li["rss_series"], 0, 200))
if liw and meds:
    print(f"\n  LlamaIndex same window: median {liw['median']:.0f} MB")
    print(f"  ratio range across the 3 RocketRide runs: "
          f"{min(meds)/liw['median']:.2f}x - {max(meds)/liw['median']:.2f}x")
