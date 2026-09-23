#!/usr/bin/env python3
"""P1-A E2 tracer controller (DIAGNOSTIC): attach to ONE process for exactly the measured window.

    p1_tracer.py --arm rr|li --container <name> --leg-dir <L> --leg <name>

The driver (P1_SYNC_DIR=<L>) writes <L>/.warm_done after its warm-up and waits for <L>/.tracer_ready;
it writes <L>/.window_closed when the leg's CPU bracket closes. Between those marks this attaches:
  * bpftrace (root): GIL waits by uprobes on PyEval_RestoreThread — exported by BOTH arms' Python
    (RocketRide's engine binary; LlamaIndex's libpython, whose .symtab is stripped so take_gil is
    not reachable there) — per thread, plus sparse 10 ms buckets of waits > 20 us; on RocketRide
    also P0's take_gil / drop_gil probes; and per-thread scheduler accounting from sched_switch /
    sched_wakeup: on-CPU, runnable-but-waiting (run queue) and sleeping nanoseconds.
  * py-spy --gil --nonblocking (which Python functions hold the GIL).
  * a 5 Hz /proc sampler of every thread: comm, state, utime, stime, last CPU, and its affinity
    (Cpus_allowed_list, read at first sight and every 30 s).
Clock pairs (time.time, time.monotonic_ns) are written at attach and detach: bpftrace's nsecs and
the stamped copies' *_mono fields are CLOCK_MONOTONIC.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.p0_session import PYSPY, H2Profiler, _cgroup_procs, is_rr_task  # noqa: E402

GIL_RT = """uprobe:BIN:PyEval_RestoreThread /pid == PID/ { @r0[tid] = nsecs; }
uretprobe:BIN:PyEval_RestoreThread /pid == PID && @r0[tid]/ {
  $w = nsecs - @r0[tid]; delete(@r0[tid]);
  @rt_ns[tid] = sum($w); @rt_n[tid] = count();
  if ($w > 20000) { @rt_b[tid, nsecs / 10000000] = sum($w); }
  if (@tfirst == 0) { @tfirst = nsecs; }
  @tlast = nsecs;
}
"""
GIL_TAKE = """uprobe:BIN:take_gil /pid == PID/ { @t0[tid] = nsecs; }
uretprobe:BIN:take_gil /pid == PID && @t0[tid]/ {
  $w = nsecs - @t0[tid]; delete(@t0[tid]);
  @wait_ns[tid] = sum($w); @takes[tid] = count(); @h0[tid] = nsecs;
}
uprobe:BIN:drop_gil /pid == PID && @h0[tid]/ {
  $h = nsecs - @h0[tid]; delete(@h0[tid]); @hold_ns[tid] = sum($h);
}
"""
SCHED = """tracepoint:sched:sched_switch {
  if (pid == PID) {
    $p = args->prev_pid;
    @mine[$p] = 1;
    if (@on0[$p]) { @oncpu_ns[$p] = sum(nsecs - @on0[$p]); delete(@on0[$p]); }
    @off0[$p] = nsecs;
    if (args->prev_state == 0) { @offr[$p] = 1; } else { @offr[$p] = 0; }
  }
  $n = args->next_pid;
  if (@mine[$n]) {
    if (@off0[$n]) {
      if (@offr[$n]) { @runq_ns[$n] = sum(nsecs - @off0[$n]); }
      else {
        if (@wk[$n]) { @sleep_ns[$n] = sum(@wk[$n] - @off0[$n]); @runq_ns[$n] = sum(nsecs - @wk[$n]); }
        else { @sleep_ns[$n] = sum(nsecs - @off0[$n]); }
      }
      delete(@off0[$n]);
    }
    if (@wk[$n]) { delete(@wk[$n]); }
    @on0[$n] = nsecs;
    @nsw[$n] = count();
  }
}
tracepoint:sched:sched_wakeup /@mine[args->pid]/ { @wk[args->pid] = nsecs; }
"""
# No BEGIN/END: the box's bpftrace 0.14 binary is stripped (P0 amendment 3).


def target_pid(arm: str, container: str) -> int:
    root = subprocess.run(["docker", "inspect", "-f", "{{.State.Pid}}", container], capture_output=True,
                          text=True, check=True).stdout.strip()
    if arm == "li":
        return int(root)
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", container], capture_output=True,
                         text=True, check=True).stdout.strip()
    cg = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope")
    tasks = [p["pid"] for p in _cgroup_procs(cg) if is_rr_task(p)]
    if len(tasks) != 1:
        raise SystemExit(f"p1_tracer: expected ONE RocketRide task process in {container}, found {tasks}")
    return tasks[0]


def uprobe_binary(arm: str, pid: int) -> str:
    if arm == "rr":
        return f"/proc/{pid}/root/opt/rocketride/engine/engine"
    # a container's maps are not readable by the unprivileged launch user; the tracer runs under launch
    maps = subprocess.run(["sudo", "-n", "cat", f"/proc/{pid}/maps"], capture_output=True, text=True).stdout
    for ln in maps.splitlines():
        parts = ln.split()
        if len(parts) >= 6 and "libpython3" in parts[5] and parts[5].endswith(".so.1.0"):
            return f"/proc/{pid}/root{parts[5]}"
    raise SystemExit(f"p1_tracer: no libpython mapped by pid {pid}")


class Sampler(threading.Thread):
    def __init__(self, pid: int, out: Path, hz: float = 5.0):
        super().__init__(daemon=True, name="p1-thread-sampler")
        self.pid, self.out, self.period = pid, out, 1.0 / hz
        self.stop_ev = threading.Event()
        self.aff: Dict[int, List[Any]] = {}

    def affinity(self, tid: str) -> str:
        try:
            st = Path(f"/proc/{self.pid}/task/{tid}/status").read_text()
            return next((ln.split(":", 1)[1].strip() for ln in st.splitlines() if ln.startswith("Cpus_allowed_list")), "")
        except OSError:
            return ""

    def run(self) -> None:
        tdir = Path(f"/proc/{self.pid}/task")
        with open(self.out, "a") as f:
            while not self.stop_ev.wait(self.period):
                now, mono = time.time(), time.monotonic()
                snap = []
                try:
                    tids = os.listdir(tdir)
                except OSError:
                    break
                for tid in tids:
                    try:
                        raw = (tdir / tid / "stat").read_text()
                    except OSError:
                        continue
                    lp, rp = raw.index("("), raw.rindex(")")
                    rest = raw[rp + 2:].split()
                    t = int(tid)
                    a = self.aff.get(t)
                    if a is None or now - a[0] > 30:
                        self.aff[t] = a = [now, self.affinity(tid)]
                    snap.append([t, raw[lp + 1:rp], rest[0], int(rest[11]), int(rest[12]), int(rest[36]), a[1]])
                f.write(json.dumps({"t": now, "t_mono": mono, "th": snap}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("rr", "li"), required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--leg-dir", type=Path, required=True)
    ap.add_argument("--leg", required=True)
    ap.add_argument("--warm-timeout-s", type=float, default=3 * 3600)
    ap.add_argument("--window-timeout-s", type=float, default=8 * 3600)
    ap.add_argument("--pid", type=int, default=None, help="TOOLING TESTS ONLY: attach to this pid")
    a = ap.parse_args()
    L = a.leg_dir
    meta: Dict[str, Any] = {"label": "DIAGNOSTIC (P1-A E2): uprobes, scheduler tracepoints and a sampling "
                                     "profiler perturb what they measure; the tracer-off legs are the null control",
                            "arm": a.arm, "container": a.container}
    t_end = time.monotonic() + a.warm_timeout_s
    while not (L / ".warm_done").exists():
        if time.monotonic() > t_end:
            meta["error"] = "no .warm_done"
            (L / "tracer_meta.json").write_text(json.dumps(meta, indent=1))
            return 3
        time.sleep(0.5)
    pid = a.pid if a.pid else target_pid(a.arm, a.container)
    binp = uprobe_binary(a.arm, pid)
    meta.update({"pid": pid, "uprobe_binary": binp})
    script = GIL_RT + (GIL_TAKE if a.arm == "rr" else "") + SCHED
    bt = L / f"e2trace_{a.leg}.bt"
    bt.write_text(script.replace("BIN", binp).replace("PID", str(pid)))
    btout, btlog = L / f"e2trace_{a.leg}.json", L / f"e2trace_{a.leg}.log"
    procs: Dict[str, subprocess.Popen] = {}
    procs["bpftrace"] = subprocess.Popen(
        ["sudo", "-n", "env", "BPFTRACE_MAP_KEYS_MAX=4000000", "bpftrace", "-f", "json", "-o", str(btout), str(bt)],
        stdout=open(btlog, "w"), stderr=subprocess.STDOUT)
    t_att = time.monotonic() + 180
    attached = False
    while time.monotonic() < t_att and procs["bpftrace"].poll() is None:
        if btlog.exists() and "Attaching" in btlog.read_text(errors="replace"):
            attached = True
            break
        head = btout.read_text(errors="replace")[:4000] if btout.exists() else ""
        if "Attaching" in head or "attached_probes" in head:           # -f json reports it as attached_probes
            attached = True
            break
        time.sleep(0.5)
    meta["bpftrace_attached"] = attached
    gil = L / f"pyspy_gil_{a.leg}.txt"
    procs["pyspy"] = subprocess.Popen(
        ["sudo", "-n", PYSPY, "record", "--pid", str(pid), "--format", "raw", "--threads", "--gil",
         "--nonblocking", "--rate", "100", "--output", str(gil)],
        stdout=open(L / f"pyspy_gil_{a.leg}.log", "w"), stderr=subprocess.STDOUT)
    samp = Sampler(pid, L / f"threadstate_{a.leg}.jsonl")
    samp.start()
    time.sleep(1.0)
    meta["clock_at_ready"] = {"time": time.time(), "monotonic_ns": time.monotonic_ns()}
    meta["pyspy_running_at_ready"] = procs["pyspy"].poll() is None
    (L / ".tracer_ready").write_text(json.dumps(meta["clock_at_ready"]))
    t_end = time.monotonic() + a.window_timeout_s
    while not (L / ".window_closed").exists() and time.monotonic() < t_end:
        time.sleep(0.5)
    meta["clock_at_close"] = {"time": time.time(), "monotonic_ns": time.monotonic_ns()}
    samp.stop_ev.set()
    for key, p in procs.items():
        if p.poll() is None:
            comm = "bpftrace" if key == "bpftrace" else "py-spy"
            pids = H2Profiler._tool_pids(str(btout if key == "bpftrace" else gil), comm)
            meta[f"{key}_signalled_pids"] = pids
            if pids:
                subprocess.run(["sudo", "-n", "kill", "-INT"] + [str(k) for k in pids], capture_output=True)
    for key, p in procs.items():
        try:
            meta[f"{key}_rc"] = p.wait(timeout=240)
        except subprocess.TimeoutExpired:
            p.kill()
            meta[f"{key}_rc"] = "killed after 240 s"
    samp.join(timeout=10)
    meta["files"] = {f.name: f.stat().st_size for f in (btout, gil, L / f"threadstate_{a.leg}.jsonl") if f.exists()}
    meta["bpftrace_log_tail"] = btlog.read_text(errors="replace")[-800:] if btlog.exists() else None
    (L / "tracer_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: meta[k] for k in ("pid", "bpftrace_attached", "files") if k in meta}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
