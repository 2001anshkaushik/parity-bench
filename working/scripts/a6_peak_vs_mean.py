#!/usr/bin/env python3
"""
!! NUMBERS IN THIS DOCSTRING ARE HISTORICAL CONTEXT, NOT LIVE CLAIMS. Several were later
!! withdrawn or superseded — see publishable/STATE.md section 5 before quoting any of them.
OPEN ITEM A6 — reconcile finding 7 (`cores_busy 9.29`) with session 7's 1.45 cores.

Both numbers are for "the engine embedding one document", and they differ 6x. One of them is
wrong, or they measure different things. This matters because 9.29 is what made us believe the
engine was CPU-hungry.

Hypothesis: they measure different STATISTICS of the same signal.
  * session 7 computed a TIME-AVERAGE: total CPU-seconds over an 8 s window divided by wall time.
    At concurrency 1 the engine is idle between requests, and the average includes that idle.
  * finding 7 plausibly captured an INSTANTANEOUS sample during a forward pass, which with
    torch_num_threads=10 (measured directly this session) can legitimately reach ~9-10 cores.

If so, both are correct and neither is a bug — but they are not interchangeable, and only the
average belongs in a cost-per-request calculation.

Method: during a single-concurrency embed load, sample instantaneous system CPU at 100 ms and
report the peak, the 95th percentile, and the mean over the same window. If peak ~= 9-10 while
mean ~= 1.5, the discrepancy is resolved as peak-vs-mean.
"""
import subprocess, sys, time, statistics
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent.parent
NC = psutil.cpu_count()
conc = int(sys.argv[1]) if len(sys.argv) > 1 else 1
secs = 10.0

psutil.cpu_percent(None)
time.sleep(1.0)
idle = []
for _ in range(10):
    idle.append(psutil.cpu_percent(None) / 100.0 * NC)
    time.sleep(0.1)
idle_mean = statistics.mean(idle)

t_start = psutil.cpu_times()
w0 = time.time()
d = subprocess.Popen([str(ROOT.parent / ".venv" / "bin" / "python"),
                      str(ROOT / "scripts" / "a3_load.py"),
                      "pipes/single_node.pipe", str(conc), f"a6c{conc}", str(secs)],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT))
time.sleep(1.5)
samples = []
psutil.cpu_percent(None)
while d.poll() is None:
    samples.append(psutil.cpu_percent(None) / 100.0 * NC)
    time.sleep(0.1)
out, _ = d.communicate()
t_end = psutil.cpu_times()
wall = time.time() - w0
cpu_sec = ((t_end.user - t_start.user) + (t_end.system - t_start.system)
           + (getattr(t_end, "nice", 0) - getattr(t_start, "nice", 0)))
rate = next((float(l.split()[1]) for l in out.decode().splitlines()
             if l.startswith("RATE")), 0.0)

s = sorted(x for x in samples if x > 0)
print(f"  concurrency          {conc}")
print(f"  rate                 {rate:.2f} req/s")
print(f"  idle baseline        {idle_mean:.2f} cores")
print(f"  TIME-AVERAGE         {cpu_sec / wall - idle_mean:.2f} cores net   "
      f"(the session-7 statistic)")
print(f"  instantaneous mean   {statistics.mean(s) - idle_mean:.2f} cores net")
print(f"  instantaneous p95    {s[int(len(s) * 0.95)] - idle_mean:.2f} cores net")
print(f"  instantaneous PEAK   {max(s) - idle_mean:.2f} cores net   "
      f"(the finding-7-style statistic)")
print(f"  samples              {len(s)} of {NC} cores")
