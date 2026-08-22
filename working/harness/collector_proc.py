"""Out-of-process collector — the sampler runs in its own interpreter.

Running the sampler as a thread inside the harness was measured slowing the harness 100x, and
biased: it throttles in-process frameworks (LangGraph, CrewAI) while leaving an external engine
(RocketRide) alone. Any comparison drawn that way is instrumentation artefact, not architecture.

Role specifications are declarative so they survive the process boundary — no callables:

    {"harness": {"pids": [123]},                    # this PID and its whole descendant tree
     "engine":  {"pattern": "dist/server/engine"}}  # any process whose cmdline matches

Both forms expand to full process trees inside the child, so `ProcessPoolExecutor` workers and
RocketRide's per-task `node.py` trees are picked up without the parent tracking them.

Run directly for a standalone sample:
    python -m harness.collector_proc --out s.jsonl --roles '{"h":{"pids":[123]}}'
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .collector import TreeCollector, pids_matching


def _roles_from_spec(spec: dict) -> dict:
    roles = {}
    for name, s in spec.items():
        if "pattern" in s:
            roles[name] = pids_matching(s["pattern"])
        else:
            pids = list(s.get("pids", []))
            roles[name] = (lambda p=pids: p)
    return roles


def child_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--roles", required=True, help="JSON role spec")
    ap.add_argument("--interval", type=float, default=0.10)
    ap.add_argument("--discovery-interval", type=float, default=1.0)
    ap.add_argument("--ceiling-bytes", type=int, default=0)
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--want-uss", action="store_true",
                    help="also collect USS and PSS (smaps; decimated). PSS is the\nonly per-process figure that sums correctly across forked workers.")
    ap.add_argument("--summary", required=True)
    ap.add_argument("--ready", required=True)
    args = ap.parse_args(argv)

    collector = TreeCollector(
        out_path=Path(args.out),
        roles=_roles_from_spec(json.loads(args.roles)),
        interval_s=args.interval,
        discovery_interval_s=args.discovery_interval,
        rss_ceiling_bytes=args.ceiling_bytes or None,
        enforce_ceiling=args.enforce,
        want_uss=args.want_uss,
    )

    stopping = {"v": False}

    def _handle(signum, frame):
        stopping["v"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    collector.start()
    # Readiness is published only after the handlers are installed and sampling has begun. The
    # parent used to infer readiness from the samples file being non-empty, which a *stale* file
    # from a previous run satisfied instantly — so the parent raced ahead and SIGTERM could land
    # while this process was still importing psutil, killing it under the default handler before
    # any summary was written. The run then silently reported 0 MB and 0 CPU seconds.
    Path(args.ready).write_text(str(os.getpid()))
    try:
        while not stopping["v"]:
            time.sleep(0.05)
    finally:
        collector.stop()
        Path(args.summary).write_text(json.dumps(collector.summary(), indent=2))
    return 0


class ProcessCollector:
    """Parent-side handle for an out-of-process collector.

    Use this for every real benchmark run. `TreeCollector` remains available for unit tests and
    for measuring processes that are not competing with the harness for a GIL.
    """

    def __init__(
        self,
        out_path: Path,
        roles_spec: dict,
        interval_s: float = 0.10,
        discovery_interval_s: float = 1.0,
        rss_ceiling_bytes: int | None = None,
        enforce_ceiling: bool = False,
        want_uss: bool = False,
        python: str | None = None,
    ):
        # ABSOLUTE, resolved HERE, before either side uses them (2026-08-22).
        # start() runs the child with cwd=<repo>/working, and these paths are
        # passed to it as strings. A RELATIVE out_path therefore resolved
        # against a different directory in each process: the child wrote
        # working/working/video/results/.../collector_*.ready and sampled
        # happily, while the parent polled the same relative string from the
        # repo root and timed out after 30s. The child had succeeded; the
        # parent was watching the wrong path — a readiness timeout that meant
        # "your paths disagree", not "the child is dead", which is why raising
        # the timeout would have been precisely the wrong fix. Phase 1 never
        # hit it because its drivers ran FROM working/, so both cwds agreed;
        # the video driver runs from the repo root. Entry 3 exactly: nothing
        # about the collector changed, the conditions moved out from under it.
        # Resolving here makes correctness independent of the caller's cwd —
        # fixing it by changing the caller's cwd would encode the bug.
        self.out_path = Path(out_path).resolve()
        self.summary_path = self.out_path.with_suffix(".summary.json")
        self.ready_path = self.out_path.with_suffix(".ready")
        self.roles_spec = roles_spec
        self.interval_s = interval_s
        self.discovery_interval_s = discovery_interval_s
        self.rss_ceiling_bytes = rss_ceiling_bytes
        self.enforce_ceiling = enforce_ceiling
        self.want_uss = want_uss
        self.python = python or sys.executable
        self._proc: subprocess.Popen | None = None
        self._summary: dict | None = None

    def __enter__(self) -> "ProcessCollector":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove artefacts of any previous run, so nothing stale can be mistaken for this run's
        # output — neither by the readiness handshake nor by a later reader of the results.
        for p in (self.out_path, self.summary_path, self.ready_path):
            p.unlink(missing_ok=True)
        cmd = [
            self.python, "-m", "harness.collector_proc",
            "--out", str(self.out_path),
            "--summary", str(self.summary_path),
            "--ready", str(self.ready_path),
            "--roles", json.dumps(self.roles_spec),
            "--interval", str(self.interval_s),
            "--discovery-interval", str(self.discovery_interval_s),
        ]
        if self.rss_ceiling_bytes:
            cmd += ["--ceiling-bytes", str(self.rss_ceiling_bytes)]
        if self.enforce_ceiling:
            cmd.append("--enforce")
        if self.want_uss:
            cmd.append("--want-uss")
        env = dict(os.environ)
        root = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        self._proc = subprocess.Popen(cmd, cwd=root, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Block until the child publishes readiness — signal handlers installed and sampling
        # started — so the workload's ramp-up is captured and stop() cannot race the child's
        # startup. Failing loudly here is correct: a run with no resource data is worthless for
        # a suite whose top priority is memory.
        deadline = time.perf_counter() + 30.0
        while time.perf_counter() < deadline:
            if self.ready_path.exists():
                return
            if self._proc.poll() is not None:
                err = (self._proc.stderr.read() or b"").decode()[-800:]
                raise RuntimeError(
                    f"collector process died on startup (watching {self.ready_path}, "
                    f"child cwd {root}): {err}")
            time.sleep(0.02)
        self._proc.kill()
        # The watched path goes in the message: when this fired for real, the
        # child was alive and writing — to a different absolute path — and the
        # traceback said only "within 30s", which is diagnosable only by
        # finding the stray file. Name what we watched and where the child ran.
        raise RuntimeError(
            f"collector process did not become ready within 30s (watching "
            f"{self.ready_path}; child cwd {root}, out {self.out_path}). If that file "
            f"exists somewhere else on disk, the parent and child resolved a relative "
            f"path against different directories.")

    def stop(self, timeout: float = 15.0) -> dict:
        if self._proc is None:
            return self._summary or {}
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        if self.summary_path.exists():
            try:
                self._summary = json.loads(self.summary_path.read_text())
            except json.JSONDecodeError:
                self._summary = {"roles": {}, "system": {}, "error": "summary unparseable"}
        else:
            err = ""
            if self._proc.stderr:
                try:
                    err = (self._proc.stderr.read() or b"").decode()[-800:]
                except Exception:
                    pass
            self._summary = {"roles": {}, "system": {}, "error": f"no summary written. {err}"}
        self._proc = None
        return self._summary

    def summary(self) -> dict:
        return self._summary or {"roles": {}, "system": {}}


if __name__ == "__main__":
    sys.exit(child_main())
