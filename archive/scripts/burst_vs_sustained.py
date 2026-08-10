#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

produced the 31% sustained-decay artifact (n=1, no control arm, failures swallowed and never counted)

Archived 2026-08-09. Preserved because the correction history is an asset: this script is the
evidence for how the corresponding number was produced and why it was withdrawn. It is NOT a
working instrument and its output must not be used.

Replacement, if you need this measurement: see publishable/STATE.md and publishable/README.md.
"""
import sys

sys.stderr.write(__doc__ + "\n")
sys.stderr.write("REFUSING TO RUN: this harness is deprecated and its results were withdrawn.\n")
sys.exit(2)

# ----------------------------------------------------------------------------------
# ORIGINAL SOURCE PRESERVED BELOW THIS LINE, UNREACHABLE. Do not remove the guard above.
# ----------------------------------------------------------------------------------

# #!/usr/bin/env python3
# """Resolve the fresh-task vs persistent-task contradiction.

# Two harness variants disagree on DIRECTION at every token level:
#     fresh task per repetition  -> RocketRide 1.32-1.66x FASTER
#     one task, many bursts      -> RocketRide 1.06-1.38x SLOWER

# The engine is ~1.5x slower in the persistent variant at every level. Hypothesis: the fresh-task
# variant measures BURST capacity (a short window right after a quiet period, on a freshly-spawned
# task), while the persistent variant measures SUSTAINED throughput through one long-lived task.

# Test: on ONE task, measure a sequence of bursts and report the rate of each. If throughput decays
# across bursts, sustained-vs-burst is confirmed and the persistent number is the honest one for
# steady-state serving. If it is flat, the difference lies in task creation itself and the
# hypothesis is refuted.
# """
# from __future__ import annotations
# import asyncio, json, os, statistics, sys, time, uuid
# from pathlib import Path
# ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
# from harness import engine_ops as eo

# UNIT = "The quick brown fox jumps over the lazy dog. "
# DOC = UNIT * 80          # ~800 tokens
# BURSTS = 10
# PER_BURST = 60
# CONC = 4

# async def main():
#     from rocketride import RocketRideClient
#     base = json.loads((ROOT/"pipes"/"embed_probe.pipe").read_text())
#     base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, "burstsustained"))
#     p = ROOT/"pipes"/"generated"/"burst.pipe"; p.parent.mkdir(parents=True, exist_ok=True)
#     p.write_text(json.dumps(base))
#     c = RocketRideClient(); await c.connect(timeout=30000)
#     r = await c.use(filepath=str(p.relative_to(ROOT))); tok = r["token"]
#     await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
#     sem = asyncio.Semaphore(CONC)
#     async def burst(n):
#         async def one(i):
#             async with sem:
#                 try:
#                     await asyncio.wait_for(c.send(tok, DOC, mimetype="text/plain"), timeout=600)
#                     return True
#                 except Exception: return None
#         t0=time.perf_counter()
#         res=await asyncio.gather(*(one(i) for i in range(n)), return_exceptions=True)
#         w=time.perf_counter()-t0
#         return sum(1 for x in res if x is True)/w if w else 0
#     print("  ONE task, 10 consecutive bursts of 60 requests (~800 tokens each):")
#     rates=[]
#     for b in range(BURSTS):
#         rt = await burst(PER_BURST); rates.append(rt)
#         print(f"    burst {b+1:2d}: {rt:7.2f}/s", flush=True)
#     try: await asyncio.wait_for(c.terminate(tok), timeout=120)
#     except Exception: pass
#     await c.disconnect()
#     first3=statistics.median(rates[:3]); last3=statistics.median(rates[-3:])
#     print(f"\n  median of first 3 bursts: {first3:.2f}/s")
#     print(f"  median of last 3 bursts : {last3:.2f}/s")
#     print(f"  decay across the run    : {(1-last3/first3)*100:+.1f}%")
#     verdict=("SUSTAINED DECAY confirmed — burst capacity exceeds steady state"
#              if last3 < first3*0.9 else
#              "NO sustained decay — the difference is in task creation, hypothesis REFUTED")
#     print(f"  VERDICT: {verdict}")
#     json.dump({"rates":rates,"first3":first3,"last3":last3,"verdict":verdict},
#               open("results/burst_vs_sustained.json","w"), indent=1)

# if __name__=="__main__":
#     eo.preflight("burst-sustained"); asyncio.run(main()); eo.postflight("burst-sustained")
