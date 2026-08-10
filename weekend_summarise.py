#!/usr/bin/env python3
"""Roll every weekend checkpoint into a markdown summary. Safe to run at any time."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
S = ROOT / "weekend_state"
def slope(series):
    """Post-ramp slope, or None when the window is too short to mean anything.

    WITHDRAWN 2026-08-09: the naive version of this fitted endpoints across the warm-up ramp and
    reported +1,505 MB/1k docs for a 267-document RocketRide window against a 10,000-document
    LlamaIndex window. Excluding the ramp, BOTH arms went negative — proof the fit was measuring
    oscillation, not trend. See publishable/WEEKEND_FORENSICS.md section 2.
    """
    post = [x for x in series if x["n"] >= 50]          # drop the warm-up ramp
    if len(post) < 20:
        return None                                     # window shorter than the oscillation
    span = post[-1]["n"] - post[0]["n"]
    if span < 500:
        return None                                     # too short to distinguish trend from noise
    return round((post[-1]["rss_mb"] - post[0]["rss_mb"]) / max(1, span) * 1000, 1)
rows = []
for f in sorted(S.glob("*.json")):
    try: d = json.loads(f.read_text())
    except Exception: continue
    rows.append((f.stem, d))
L = ["# Weekend Run — rolling results", "",
     f"_Generated {time.strftime('%Y-%m-%dT%H:%M:%S')} from {len(rows)} checkpoints._", "",
     "**Both arms ran NATIVELY, not containerised.** `server-v3.3.1` ships darwin-arm64, "
     "linux-x64 and win64 — there is no linux-arm64 build — so containerising RocketRide on this "
     "host would need x86 emulation, which would corrupt exactly the numbers being measured. "
     "Running one arm containerised and one native would be asymmetric, which is worse. The memory "
     "ceiling is therefore a SOFT limit enforced by the worker, not a cgroup: a breach is detected "
     "and recorded, but it is not proof the process would have been killed at that point.", "",
     "**Throughput is not reported.** Rates from this host are invalid (open item A13).", "",
     "**Slope is reported only where the window is long enough to mean anything** (>=500 documents "
     "after the warm-up ramp). A slope fitted across a shorter window measures oscillation, not "
     "trend: the withdrawn +1,505 MB/1k figure came from exactly that mistake. "
     "See `WEEKEND_FORENSICS.md` section 2.", "",
     "| phase / arm | status | docs | goodput | faults | peak RSS | post-ramp slope /1k | elapsed |",
     "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
for name, d in rows:
    sl = slope(d.get("rss_series", []))
    L.append(f"| `{name}` | {d.get('status','?')} | {d.get('next_index',0)} | "
             f"{d.get('goodput',0)} | {sum(d.get('faults',{}).values())} | "
             f"{d.get('peak_rss_mb',0):.0f} MB | {('+' + str(sl) + ' MB') if sl is not None else '—'} | "
             f"{d.get('elapsed_s',0)/3600:.2f} h |")
L += ["", "## Fault classes", ""]
for name, d in rows:
    if d.get("faults"):
        L.append(f"* `{name}`: " + ", ".join(f"{k}={v}" for k, v in sorted(d["faults"].items())))
for name, d in rows:
    if d.get("status") in ("memory_limit_exceeded", "memory_error"):
        L += ["", f"## ⚠️ MEMORY CEILING BREACH — `{name}`", "",
              f"* triggered at document index **{d.get('oom_at_index')}** (`{d.get('oom_doc')}`)",
              f"* RSS at breach: **{d.get('oom_rss_mb')} MB**",
              "* the full RSS curve up to the breach is preserved in the checkpoint"]
(ROOT / "publishable" / "WEEKEND_RESULTS.md").write_text("\n".join(L) + "\n")
print(f"wrote publishable/WEEKEND_RESULTS.md from {len(rows)} checkpoints")
