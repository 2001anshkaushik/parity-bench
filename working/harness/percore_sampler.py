"""Per-core busy/idle sampling from /proc/stat — the instrument behind every "idle cores" figure
in the batch-size sweep.

WHY THIS EXISTS. `effective_cores = cpu_s / wall_s` (metrics_shared.py) is an AVERAGE of busy
cores. It cannot say how many cores sat idle: 12 effective cores is 12 cores flat out and 12
asleep, or 24 cores at half load, and those are different findings. Nothing under
working/harness/ or working/scripts/ read per-core counters before this file; the only
/proc/stat readers in the repo (working/video/driver_video.py:819) take the aggregate line.

TWO IDLE FIGURES, NEVER MERGED — they answer different questions and will disagree:

  idle_core_equivalents   ncpus - mean(sum of per-core busy fraction). Capacity left on the
                          table, in cores. Threshold-free. Host-side, so it sees EVERYTHING
                          scheduled on those cores, not just the arm — which is why the
                          driver's quiet-box check runs first.
  idle_core_count         per interval, how many cores were below `idle_threshold` busy;
                          reported as mean / min / max over the leg. This is the literal
                          "how many cores were doing nothing" reading, and it depends on the
                          threshold and the interval, both recorded beside it.

Idle = idle + iowait ticks, the same convention as driver_video.py:_host_cpu_snapshot.

The sampler is a daemon thread reading one small file per interval. The 100x harness slowdown
that moved the process sampler out of process (collector_proc.py:1-5) was a psutil process-tree
walk; this is a single read of /proc/stat, and the driver runs on cores outside the arm's
cpuset. Its own cost is recorded (`sampler_read_s_total`) rather than assumed negligible.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROC_STAT = Path("/proc/stat")


def parse_proc_stat(text: str) -> Dict[int, Tuple[int, int]]:
    """{cpu index: (total ticks, idle+iowait ticks)} from /proc/stat text. Aggregate line skipped."""
    out: Dict[int, Tuple[int, int]] = {}
    for line in text.splitlines():
        if not line.startswith("cpu") or line.startswith("cpu "):
            continue
        parts = line.split()
        try:
            idx = int(parts[0][3:])
            vals = [int(x) for x in parts[1:]]
        except ValueError:
            continue
        if len(vals) < 5:
            continue
        # user nice system idle iowait irq softirq steal [guest guest_nice]; guest is already
        # inside user, so the first eight are the partition of wall time.
        out[idx] = (sum(vals[:8]), vals[3] + vals[4])
    return out


def busy_fractions(a: Dict[int, Tuple[int, int]], b: Dict[int, Tuple[int, int]],
                   cpus: List[int]) -> Optional[Dict[int, float]]:
    """Per-core busy fraction between two snapshots. None if any core did not advance (an
    interval shorter than a tick tells us nothing, and 0.0 would read as 'idle')."""
    out: Dict[int, float] = {}
    for c in cpus:
        if c not in a or c not in b:
            return None
        dt = b[c][0] - a[c][0]
        if dt <= 0:
            return None
        out[c] = min(1.0, max(0.0, 1.0 - (b[c][1] - a[c][1]) / dt))
    return out


def summarise(intervals: List[Dict[int, float]], cpus: List[int],
              idle_threshold: float = 0.10) -> Dict[str, Any]:
    """Reduce per-interval busy fractions to the two idle figures. Empty in -> every figure None
    with the reason, never 0 (0 idle cores is a real finding; 'not measured' is not)."""
    if not intervals:
        return {"n_intervals": 0, "ncpus": len(cpus), "idle_core_equivalents": None,
                "idle_core_count_mean": None, "note": "no usable interval — NOT MEASURED"}
    busy_sum = [sum(iv[c] for c in cpus) for iv in intervals]
    idle_cnt = sorted(sum(1 for c in cpus if iv[c] < idle_threshold) for iv in intervals)
    per_core = {c: sum(iv[c] for iv in intervals) / len(intervals) for c in cpus}
    mean_busy = sum(busy_sum) / len(busy_sum)
    return {
        "n_intervals": len(intervals),
        "ncpus": len(cpus),
        "idle_threshold": idle_threshold,
        "mean_busy_cores": round(mean_busy, 3),
        "idle_core_equivalents": round(len(cpus) - mean_busy, 3),
        "host_util_of_cpuset": round(mean_busy / len(cpus), 4),
        "idle_core_count_mean": round(sum(idle_cnt) / len(idle_cnt), 2),
        "idle_core_count_min": idle_cnt[0],
        "idle_core_count_p50": idle_cnt[len(idle_cnt) // 2],
        "idle_core_count_max": idle_cnt[-1],
        "cores_idle_whole_leg": sum(1 for c in cpus if per_core[c] < idle_threshold),
        "per_core_mean_busy": {str(c): round(per_core[c], 3) for c in cpus},
        "basis": ("host /proc/stat per-cpu lines over the arm's cpuset; idle = idle+iowait; "
                  "sees every process on those cores, not only the arm"),
    }


class PerCoreSampler(threading.Thread):
    def __init__(self, cpus: List[int], interval_s: float = 1.0,
                 out_path: Optional[Path] = None, source: Path = PROC_STAT):
        super().__init__(daemon=True)
        self.cpus, self.interval_s, self.out_path, self.source = cpus, interval_s, out_path, source
        self._halt = threading.Event()
        self.intervals: List[Dict[int, float]] = []
        self.dropped = 0
        self.read_s_total = 0.0

    def run(self) -> None:
        fh = open(self.out_path, "x") if self.out_path else None   # "x": never overwrite
        try:
            prev = parse_proc_stat(self.source.read_text())
            while not self._halt.wait(self.interval_s):
                t = time.perf_counter()
                cur = parse_proc_stat(self.source.read_text())
                self.read_s_total += time.perf_counter() - t
                fr = busy_fractions(prev, cur, self.cpus)
                prev = cur
                if fr is None:
                    self.dropped += 1
                    continue
                self.intervals.append(fr)
                if fh:
                    fh.write(json.dumps({"t": time.time(),
                                         "busy": {str(c): round(v, 4) for c, v in fr.items()}})
                             + "\n")
        finally:
            if fh:
                fh.close()

    def stop(self, idle_threshold: float = 0.10) -> Dict[str, Any]:
        self._halt.set()
        self.join(timeout=self.interval_s * 3 + 2)
        out = summarise(self.intervals, self.cpus, idle_threshold)
        out.update(interval_s=self.interval_s, intervals_dropped=self.dropped,
                   sampler_read_s_total=round(self.read_s_total, 4))
        return out


def main() -> int:
    """Sidecar form, for legs whose driver is not ours to edit (working/video/driver_video.py):
    sample to a JSONL until --duration elapses or the --until file appears; the leg's own
    export window is applied afterwards by the analyser, never guessed here."""
    import argparse
    import hashlib
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpus", required=True, help="kernel list, e.g. 0-31")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--duration", type=float, required=True, help="hard bound in seconds")
    ap.add_argument("--until", type=Path, default=None, help="stop early when this file exists")
    ap.add_argument("--interval", type=float, default=1.0)
    a = ap.parse_args()
    print(f"percore_sampler.py sha256: {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}",
          flush=True)
    cpus: List[int] = []
    for part in a.cpus.split(","):
        lo, _, hi = part.partition("-")
        cpus += list(range(int(lo), int(hi or lo) + 1))
    s = PerCoreSampler(cpus, a.interval, a.out)
    s.start()
    end = time.monotonic() + a.duration          # bounded and self-terminating, always
    while time.monotonic() < end and not (a.until and a.until.exists()):
        time.sleep(1.0)
    print(json.dumps({k: v for k, v in s.stop().items() if k != "per_core_mean_busy"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
