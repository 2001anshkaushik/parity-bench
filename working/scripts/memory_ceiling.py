#!/usr/bin/env python3
"""STEP 3 — size the container memory ceiling from evidence, not from a guess.

`DOCKER_ARCHITECTURE.md` §3 proposed 8 GB per service container. That number was chosen, not
measured, and the re-anchor run already shows why it is dangerous: at 1600 tokens / concurrency 32
the LlamaIndex service tree held ~5.8 GB while the engine tree held ~0.2 GB. An 8 GB cap would sit
just above one arm's working set and ~40x above the other's, so the first arm to OOM would OOM for
a limit I picked. That is a benchmark artifact, not a framework result — and PDFs will push the
working set up, not down.

Method:
  * sample RSS of the WHOLE process tree for each arm CONTINUOUSLY during a load window and keep
    the maximum. A between-cell sample (what the re-anchor run does) can miss a transient peak.
  * sample from OUTSIDE the driver process, so the sampler is not on the same interpreter as the
    load. An in-process collector has already biased this project by 100x once.
  * cover the heaviest tokens tested (6400) and the concurrency levels we plan to run.
  * record idle/baseline RSS too: for a worker-per-core service most of the footprint is fixed
    (model + runtime per worker), and a ceiling has to cover the fixed part regardless of load.

Both arms are measured in one interleaved session so a drifting machine cannot make one look
lighter than the other.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from harness import engine_ops as eo   # noqa: E402

OUT = ROOT / "results" / "memory_ceiling.json"
WS1_PORT = 8823
WS1_BASE = f"http://127.0.0.1:{WS1_PORT}"
UNIT = "The quick brown fox jumps over the lazy dog. "
TOKENS = [400, 1600, 6400]
CONCS = [8, 32]


def doc_for(t: int) -> str:
    return UNIT * max(1, t // 10)


def tree_rss_mb(match_name: str | None = None, root_pid: int | None = None) -> float:
    import psutil
    tot, seen = 0.0, set()
    roots = []
    if root_pid:
        try:
            roots = [psutil.Process(root_pid)]
        except Exception:
            return 0.0
    else:
        roots = [p for p in psutil.process_iter(["pid", "name"])
                 if (p.info["name"] or "").lower() == match_name]
    for r in roots:
        try:
            for p in [r] + r.children(recursive=True):
                if p.pid in seen:
                    continue
                seen.add(p.pid)
                tot += p.memory_info().rss / 1e6
        except Exception:
            pass
    return tot


class Sampler(threading.Thread):
    """Continuous peak-RSS sampler. Runs in the orchestrator, never inside a driver."""

    def __init__(self, kind: str, ws1_pid: int):
        super().__init__(daemon=True)
        self.kind, self.ws1_pid = kind, ws1_pid
        self.peak, self.stop_flag, self.n = 0.0, False, 0

    def run(self):
        while not self.stop_flag:
            v = (tree_rss_mb(match_name="engine") if self.kind == "rocketride"
                 else tree_rss_mb(root_pid=self.ws1_pid))
            self.peak = max(self.peak, v)
            self.n += 1
            time.sleep(0.25)


def load(arm: str, tokens: int, conc: int, tag: str, secs: float = 8.0) -> float:
    if arm == "rocketride":
        p = subprocess.Popen([str(ROOT.parent / ".venv" / "bin" / "python"),
                              str(ROOT / "scripts" / "a3_load.py"),
                              "pipes/embed_probe.pipe", str(conc), tag, str(secs)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT))
    else:
        p = subprocess.Popen([str(ROOT.parent / ".venv" / "bin" / "python"),
                              str(ROOT / "scripts" / "li_load.py"),
                              WS1_BASE, str(conc), str(tokens), str(secs)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(ROOT))
    out, _ = p.communicate(timeout=300)
    for ln in out.decode().splitlines():
        if ln.startswith("RATE "):
            return float(ln.split()[1])
    return 0.0


def start_ws1() -> subprocess.Popen:
    env = dict(os.environ)
    env.update(WS1_DEVICE="cpu", WS1_WORKERS="8", WS1_PORT=str(WS1_PORT))
    p = subprocess.Popen(["bash", str(ROOT / "ws1" / "run_service.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    dl = time.perf_counter() + 300
    while time.perf_counter() < dl:
        try:
            with urllib.request.urlopen(f"{WS1_BASE}/manifest", timeout=3) as r:
                json.loads(r.read().decode())
                time.sleep(3)
                return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError("ws1 died")
        time.sleep(3)
    raise RuntimeError("ws1 not ready")


def main() -> int:
    eo.preflight("memory-ceiling")
    ws1 = start_ws1()
    print("=" * 96)
    print("STEP 3 — PEAK RSS, both arms, continuous sampling")
    print("=" * 96)
    res: dict = {"idle": {}, "cells": {}}
    time.sleep(5)
    res["idle"]["rocketride"] = round(tree_rss_mb(match_name="engine"), 1)
    res["idle"]["llamaindex"] = round(tree_rss_mb(root_pid=ws1.pid), 1)
    print(f"  IDLE (no load):  rocketride {res['idle']['rocketride']:9.1f} MB   "
          f"llamaindex {res['idle']['llamaindex']:9.1f} MB")
    print("  (a worker-per-core service carries most of its footprint before any request arrives)\n")
    try:
        for t in TOKENS:
            for c in CONCS:
                for arm in ("rocketride", "llamaindex"):
                    s = Sampler(arm, ws1.pid)
                    s.start()
                    rate = load(arm, t, c, f"mem{t}_{c}", 8.0)
                    s.stop_flag = True
                    s.join(timeout=5)
                    res["cells"][f"{t}|{c}|{arm}"] = {
                        "peak_rss_mb": round(s.peak, 1), "rate": rate, "samples": s.n}
                    print(f"  {t:5d}tok c={c:2d} {arm:11s} peak={s.peak:9.1f} MB  "
                          f"rate={rate:7.2f}/s  ({s.n} samples)", flush=True)
    finally:
        subprocess.run(["pkill", "-f", "uvicorn ws1.service"], capture_output=True)
        eo.postflight("memory-ceiling")
        OUT.write_text(json.dumps(res, indent=1))

    print("\n" + "=" * 96)
    for arm in ("rocketride", "llamaindex"):
        vals = [(v["peak_rss_mb"], k) for k, v in res["cells"].items() if k.endswith(arm)]
        mx = max(vals)
        print(f"  {arm:11s} idle {res['idle'][arm]:8.1f} MB   PEAK {mx[0]:9.1f} MB  at {mx[1]}")
    li = max(v["peak_rss_mb"] for k, v in res["cells"].items() if k.endswith("llamaindex"))
    rr = max(v["peak_rss_mb"] for k, v in res["cells"].items() if k.endswith("rocketride"))
    hi = max(li, rr)
    print(f"\n  highest peak across both arms: {hi:.1f} MB")
    print(f"  recommended ceiling (2x headroom over the heavier arm): "
          f"{max(8, int((hi * 2) / 1000) + 1)} GB")
    print(f"\n  written -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
