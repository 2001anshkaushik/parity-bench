"""P0 per-leg records: the session a leg ran in, D0 instance accounting from outside the processes,
and the H2 profiler controller.

WHY THIS EXISTS (register 46). The same RocketRide docs cell moved 15.4% across one box stop/start.
So every P0 comparison is interleaved ABAB inside ONE box session, and every leg records the facts
that identify that session and its hardware state, rather than trusting that it ran where the
chain meant it to:

  boot_id           /proc/sys/kernel/random/boot_id — changes on every boot, so two legs with
                    different boot ids were measured in different sessions and are never compared
  steal             /proc/stat aggregate steal ticks over the leg's window, as a share of all
                    ticks and in cores; a hypervisor taking cycles is a confounder, not a result
  cpu model / MHz   /proc/cpuinfo, sampled at window open and close and every D0 sample between
  placement         IMDSv2, whatever it exposes (host-id answers only on dedicated hosts; a 404
                    is recorded as such, never as a value)

D0 FROM OUTSIDE. Every few seconds inside the window, each process in the arm's cgroup with its
name, command and thread count. For RocketRide a TASK INSTANCE is a process named `engine` whose
command runs ai/node.py (the task process); the server (`./engine ai/eaas.py`) and one-thread
forked helpers are listed but are not task instances. The mandate expects exactly one. The
in-process half of D0 (loaded models) is env_probe schema 3, read on the measured token.

H2 PROFILER (as amended, preregistration_amendment_1.json). On the HOST as root against the task
process's host pid — the arm's own container is not given SYS_PTRACE, so nothing about the arm
changes:
  giltrace  bpftrace uprobes on CPython 3.12's take_gil / drop_gil in the engine binary (local
          symbols in its .symtab): per thread, time inside take_gil is time WAITING for the lock,
          and take_gil's return to the next drop_gil is time HOLDING it.
  gil     `py-spy record --gil --threads --nonblocking` — only the GIL holder's stack each tick,
          without pausing the process; its stacks are the functions that hold the lock.
Plus a /proc sampler of every OS thread in the task process (state and CPU ticks per thread,
Python or not: the JVM and any torch/OpenMP threads appear only here). The pre-registered
recorder N (py-spy --native, blocking) aborts on this binary (UNW_EBADREG) and is not run. Every
H2 leg is labelled DIAGNOSTIC: uprobes perturb what they measure, so absolute times are never
figures.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PYSPY = os.environ.get("P0_PYSPY", str(Path.home() / "p0venv" / "bin" / "py-spy"))
IMDS = "http://169.254.169.254/latest"


def boot_id() -> Optional[str]:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def cpu_identity() -> Dict[str, Any]:
    models, mhz = set(), []
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                models.add(line.split(":", 1)[1].strip())
            elif line.startswith("cpu MHz"):
                mhz.append(float(line.split(":", 1)[1]))
    except OSError:
        pass
    return {"model": sorted(models), "mhz_mean": round(sum(mhz) / len(mhz), 1) if mhz else None,
            "mhz_min": min(mhz) if mhz else None, "mhz_max": max(mhz) if mhz else None,
            "n": len(mhz)}


def stat_aggregate() -> Dict[str, int]:
    """The aggregate `cpu` line of /proc/stat: user nice system idle iowait irq softirq steal."""
    names = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest",
             "guest_nice")
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("cpu "):
            vals = [int(x) for x in line.split()[1:]]
            return dict(zip(names, vals))
    return {}


def imds_placement(timeout: float = 2.0) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        req = urllib.request.Request(f"{IMDS}/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"})
        tok = urllib.request.urlopen(req, timeout=timeout).read().decode()
    except Exception as e:                                   # no IMDS: recorded, not invented
        return {"error": f"IMDSv2 token: {type(e).__name__}: {e}"}
    for key in ("instance-id", "instance-type", "placement/availability-zone",
                "placement/availability-zone-id", "placement/host-id",
                "placement/partition-number", "placement/group-name"):
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                f"{IMDS}/meta-data/{key}", headers={"X-aws-ec2-metadata-token": tok}),
                timeout=timeout)
            out[key] = r.read().decode()
        except urllib.error.HTTPError as e:
            out[key] = f"<not exposed: HTTP {e.code}>"
        except Exception as e:
            out[key] = f"<error: {type(e).__name__}>"
    return out


def _cgroup_procs(cg: Path) -> List[Dict[str, Any]]:
    out = []
    try:
        pids = [int(x) for x in (cg / "cgroup.procs").read_text().split()]
    except (OSError, ValueError):
        return out
    for pid in pids:
        try:
            st = Path(f"/proc/{pid}/status").read_text()
            f = dict(l.split(":", 1) for l in st.splitlines() if ":" in l)
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
                errors="replace").strip()
            out.append({"pid": pid, "name": f.get("Name", "").strip(),
                        "threads": int(f.get("Threads", "0").strip()), "cmd": cmd[:160]})
        except (OSError, ValueError):
            continue
    return out


def is_rr_task(p: Dict[str, Any]) -> bool:
    return p["name"] == "engine" and "ai/node.py" in p["cmd"]


def rr_task_pids(cg: Path) -> List[int]:
    return [p["pid"] for p in _cgroup_procs(cg) if is_rr_task(p)]


def is_li_worker(p: Dict[str, Any]) -> bool:
    """A process that serves requests: uvicorn's own process when it runs one worker in-process,
    or a multiprocessing child when it forks several (the supervisor is then not a worker)."""
    return "python" in p["name"] or "uvicorn" in p["cmd"]


class LegSession:
    """Open at the leg's window open, close at its window close. Samples D0 every `every_s`."""

    def __init__(self, arm: str, cg: Path, out_jsonl: Path, every_s: float = 5.0):
        self.arm, self.cg, self.out, self.every = arm, cg, out_jsonl, every_s
        self._stop = threading.Event()
        self._samples: List[Dict[str, Any]] = []
        self._t: Optional[threading.Thread] = None
        self.rec: Dict[str, Any] = {}

    def _sample(self) -> Dict[str, Any]:
        procs = _cgroup_procs(self.cg)
        s = {"t": time.time(), "procs": procs, "mhz_mean": cpu_identity()["mhz_mean"]}
        if self.arm == "rr":
            s["task_instances"] = sum(1 for p in procs if is_rr_task(p))
        self._samples.append(s)
        with open(self.out, "a") as f:
            f.write(json.dumps(s) + "\n")
        return s

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            try:
                self._sample()
            except Exception as e:                       # a failed sample is recorded, not fatal
                self._samples.append({"t": time.time(), "error": f"{type(e).__name__}: {e}"})

    def open(self) -> None:
        self.rec["boot_id"] = boot_id()
        self.rec["cpu_open"] = cpu_identity()
        self._stat0 = stat_aggregate()
        self._sample()
        self._t = threading.Thread(target=self._loop, daemon=True, name="p0-d0-sampler")
        self._t.start()

    def close(self) -> Dict[str, Any]:
        self._stop.set()
        if self._t:
            self._t.join(timeout=10)
        self._sample()
        stat1 = stat_aggregate()
        d = {k: stat1.get(k, 0) - self._stat0.get(k, 0) for k in stat1}
        # guest ticks are already counted inside user; summing them again double counts
        total = sum(v for k, v in d.items() if k not in ("guest", "guest_nice"))
        ncpu = os.cpu_count() or 1
        good = [s for s in self._samples if "procs" in s]
        by_name: Dict[str, int] = {}
        for s in good:
            for p in s["procs"]:
                key = f"{p['name']}|{'task' if (self.arm == 'rr' and is_rr_task(p)) else p['cmd'][:48]}"
                by_name[key] = max(by_name.get(key, 0), p["threads"])
        mhz = [s["mhz_mean"] for s in good if s.get("mhz_mean")]
        self.rec.update({
            "boot_id_close": boot_id(),
            "cpu_close": cpu_identity(),
            "steal": {"ticks": d.get("steal", 0), "total_ticks": total,
                      "share": round(d.get("steal", 0) / total, 6) if total else None,
                      "cores": round(ncpu * d.get("steal", 0) / total, 4) if total else None,
                      "basis": "/proc/stat aggregate line, window open to close"},
            "mhz_over_window": {"mean_of_samples": round(sum(mhz) / len(mhz), 1) if mhz else None,
                                "min": min(mhz) if mhz else None, "max": max(mhz) if mhz else None,
                                "n": len(mhz)},
            "d0_external": {
                "samples": len(good), "every_s": self.every,
                "n_processes_max": max((len(s["procs"]) for s in good), default=None),
                "task_instances_max": (max((s.get("task_instances", 0) for s in good), default=None)
                                       if self.arm == "rr" else None),
                "task_instances_min": (min((s.get("task_instances", 0) for s in good), default=None)
                                       if self.arm == "rr" else None),
                "li_worker_processes_max": (max((sum(1 for p in s["procs"] if is_li_worker(p))
                                                 for s in good), default=None)
                                            if self.arm == "li" else None),
                "max_threads_by_process": by_name,
                "definition": ("RocketRide task instance = a process named 'engine' running "
                               "ai/node.py; the eaas server and one-thread forked helpers are "
                               "listed, not counted" if self.arm == "rr" else
                               "every process in the service container, with thread counts"),
            },
        })
        # the task's own command line (160 chars): shows --debug_port when the debugger is attached
        self.rec["task_cmdlines"] = (sorted({p["cmd"] for s in good for p in s["procs"] if is_rr_task(p)})
                                     if self.arm == "rr" else None)
        self.rec["same_session"] = self.rec["boot_id"] == self.rec["boot_id_close"]
        return self.rec


GIL_BT = """// P0 H2 GIL tracer (amendment 1): uprobes on CPython 3.12's take_gil / drop_gil in the engine
// binary (local symbols, present in its .symtab). Per thread: time inside take_gil = WAITING for
// the lock (an uncontended take returns at once); take_gil return -> next drop_gil = HOLDING it.
uprobe:BIN:take_gil /pid == PID/ { @t0[tid] = nsecs; }
uretprobe:BIN:take_gil /pid == PID && @t0[tid]/ {
  $w = nsecs - @t0[tid]; delete(@t0[tid]);
  @wait_ns[tid] = sum($w); @takes[tid] = count(); @h0[tid] = nsecs;
  @wait_by_s[nsecs / 1000000000] = sum($w); @wait_hist = hist($w);
  if (@tfirst == 0) { @tfirst = nsecs; }
  @tlast = nsecs;
}
uprobe:BIN:drop_gil /pid == PID && @h0[tid]/ {
  $h = nsecs - @h0[tid]; delete(@h0[tid]);
  @hold_ns[tid] = sum($h); @hold_by_s[nsecs / 1000000000] = sum($h);
}
"""
# No BEGIN/END blocks: Ubuntu 22.04's bpftrace 0.14 binary is stripped, and BEGIN/END are uprobes on
# its own BEGIN_trigger symbol ("Could not resolve symbol: /proc/self/exe:BEGIN_trigger", tooling
# leg tool_gil 09:26Z). The tracer's window is its first to last traced acquisition (@tfirst..@tlast;
# bpftrace 0.14 does not print a min() map, tooling leg tool_gil2).


class H2Profiler:
    """py-spy's GIL recorder + a bpftrace GIL tracer (host, root) against one task process, plus
    a /proc thread sampler. py-spy's blocking native recorder was dropped by amendment 1: on the
    engine binary it aborts at once (UNW_EBADREG, tooling leg 2026-09-23 08:36Z)."""

    def __init__(self, pid: int, run_dir: Path, leg: str, native_rate: int = 20,
                 gil_rate: int = 100, proc_hz: float = 5.0):
        self.pid, self.dir, self.leg = pid, run_dir, leg
        self.native_rate, self.gil_rate, self.proc_hz = native_rate, gil_rate, proc_hz
        self.procs: Dict[str, subprocess.Popen] = {}
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self.files = {"gil": run_dir / f"pyspy_gil_{leg}.txt",
                      "giltrace": run_dir / f"giltrace_{leg}.json",
                      "threads": run_dir / f"threadstate_{leg}.jsonl"}
        self.started: Dict[str, Any] = {}

    def _spawn(self, key: str, extra: List[str]) -> None:
        cmd = ["sudo", "-n", PYSPY, "record", "--pid", str(self.pid), "--format", "raw",
               "--threads", "--output", str(self.files[key])] + extra
        log = open(self.dir / f"pyspy_{key}_{self.leg}.log", "w")
        self.procs[key] = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        self.started[key] = {"cmd": " ".join(cmd), "t": time.time()}

    def _spawn_bpftrace(self) -> None:
        binp = f"/proc/{self.pid}/root/opt/rocketride/engine/engine"
        script = self.dir / f"giltrace_{self.leg}.bt"
        script.write_text(GIL_BT.replace("BIN", binp).replace("PID", str(self.pid)))
        cmd = ["sudo", "-n", "bpftrace", "-f", "json", "-o", str(self.files["giltrace"]),
               str(script)]
        log = open(self.dir / f"giltrace_{self.leg}.log", "w")
        self.procs["giltrace"] = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        self.started["giltrace"] = {"cmd": " ".join(cmd), "t": time.time(), "binary": binp}

    def _thread_sampler(self) -> None:
        """Every OS thread of the task: comm, state, cumulative utime+stime ticks."""
        tdir = Path(f"/proc/{self.pid}/task")
        period = 1.0 / self.proc_hz
        with open(self.files["threads"], "a") as f:
            while not self._stop.wait(period):
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
                    # comm is parenthesised and may contain spaces; split after the last ')'
                    lp, rp = raw.index("("), raw.rindex(")")
                    rest = raw[rp + 2:].split()
                    snap.append([int(tid), raw[lp + 1:rp], rest[0],
                                 int(rest[11]) + int(rest[12])])
                f.write(json.dumps({"t": time.time(), "th": snap}) + "\n")

    def start(self) -> None:
        self._spawn_bpftrace()
        self._spawn("gil", ["--gil", "--nonblocking", "--rate", str(self.gil_rate)])
        self._thr = threading.Thread(target=self._thread_sampler, daemon=True,
                                     name="p0-thread-sampler")
        self._thr.start()

    @staticmethod
    def _tool_pids(pattern: str, comm: str) -> List[int]:
        """The ROOT tool process itself (comm py-spy / bpftrace) whose command line carries this
        leg's unique output path — never the sudo parent or sudo's pty monitor. The tooling legs
        showed SIGINT to sudo reaching py-spy only after the post-window probe had run."""
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        out = []
        for x in r.stdout.split():
            try:
                if Path(f"/proc/{x}/comm").read_text().strip() == comm:
                    out.append(int(x))
            except OSError:
                continue
        return out

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        # SIGINT to the ROOT child, as root: a signal to the sudo process was not relayed in the
        # tooling leg (py-spy ran on 3 minutes after the window and was killed without writing).
        self.stopped_utc = time.time()
        for key, p in self.procs.items():
            if p.poll() is None:
                comm = "bpftrace" if key == "giltrace" else "py-spy"
                pids = self._tool_pids(str(self.files[key]), comm)
                self.started[key]["signalled_pids"] = pids
                if pids:
                    subprocess.run(["sudo", "-n", "kill", "-INT"] + [str(k) for k in pids],
                                   capture_output=True)
                else:                                  # recorded, never silent
                    self.started[key]["signal_note"] = f"no {comm} process found for {self.files[key]}"
        out: Dict[str, Any] = {}
        for key, p in self.procs.items():
            try:
                rc = p.wait(timeout=180)
            except subprocess.TimeoutExpired:
                p.kill()
                rc = "killed after 180 s"
            f = self.files[key]
            logf = self.dir / (f"giltrace_{self.leg}.log" if key == "giltrace"
                               else f"pyspy_{key}_{self.leg}.log")
            out[key] = {"rc": rc, **self.started[key],
                        "bytes": f.stat().st_size if f.exists() else 0,
                        "log_tail": logf.read_text()[-600:] if logf.exists() else None}
        if self._thr:
            self._thr.join(timeout=10)
        out["stop_signalled_at_utc"] = getattr(self, "stopped_utc", None)
        out["threads"] = {"file": self.files["threads"].name, "hz": self.proc_hz,
                          "bytes": self.files["threads"].stat().st_size
                          if self.files["threads"].exists() else 0}
        out["label"] = ("DIAGNOSTIC — uprobes on the GIL and a sampling profiler perturb what "
                        "they measure; shares and rankings from this leg are evidence, its "
                        "absolute times are never figures")
        return out
