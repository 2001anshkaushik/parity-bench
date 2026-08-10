"""Shared engine health, cleanup and watchdog helpers.

Every probe calls `preflight()` before and `postflight()` after. The standing rules exist because
a livelocked engine and a few hundred orphaned `node.py` processes silently corrupt every
subsequent measurement — and they land on the user's actual desktop, not a disposable CI box.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
URI = os.environ.get("ROCKETRIDE_URI", "http://127.0.0.1:5565")
UID = os.getuid()
NODE_MARK = "benchmark-A/engine/ai/node.py"
ENGINE_MARK = "eaas.py"
PROC_CEILING = 750          # standing rule: never leave the table above this
WATCHDOG_S = 90.0           # standing rule: unresponsive beyond this = livelock


def engine_version(timeout: float = 8.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{URI}/version", timeout=timeout) as r:
            return json.loads(r.read().decode()).get("data")
    except Exception:
        return None


def healthy(timeout: float = 8.0) -> bool:
    return engine_version(timeout) is not None


def counts() -> dict:
    total = node = 0
    eng = {"pid": None, "cpu": None, "rss_mb": None, "status": None, "threads": None}
    for p in psutil.process_iter(["uids", "cmdline", "pid"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            total += 1
            cmd = " ".join(p.info["cmdline"] or ())
            if NODE_MARK in cmd:
                node += 1
            elif ENGINE_MARK in cmd and "5565" in cmd:
                eng["pid"] = p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if eng["pid"]:
        try:
            pr = psutil.Process(eng["pid"])
            pr.cpu_percent(None)
            time.sleep(0.35)
            eng.update(cpu=pr.cpu_percent(None), status=pr.status(),
                       rss_mb=round(pr.memory_info().rss / 2**20, 1),
                       threads=pr.num_threads())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"uid_procs": total, "node_procs": node, "engine": eng}


def kill_orphans(grace: float = 3.0) -> int:
    victims = []
    for p in psutil.process_iter(["cmdline", "pid"]):
        try:
            if NODE_MARK in " ".join(p.info["cmdline"] or ()):
                victims.append(psutil.Process(p.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    for p in victims:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if victims:
        time.sleep(grace)
        for p in victims:
            try:
                if p.is_running():
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(1.0)
    return len(victims)


def restart_engine(reason: str = "") -> bool:
    print(f"  [engine] restarting ({reason})", flush=True)
    subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")],
                   capture_output=True, text=True, timeout=120)
    kill_orphans()
    r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
                       capture_output=True, text=True, timeout=900)
    ok = healthy(15)
    print(f"  [engine] restart {'OK' if ok else 'FAILED'} :: {(r.stdout or '')[-120:].strip()}",
          flush=True)
    return ok


def preflight(tag: str) -> dict:
    c = counts()
    orph = 0
    if c["node_procs"] > 3 or c["uid_procs"] > PROC_CEILING:
        orph = kill_orphans()
        c = counts()
    if not healthy():
        restart_engine(f"unhealthy at preflight of {tag}")
        c = counts()
    print(f"  [preflight {tag}] uid={c['uid_procs']} node={c['node_procs']} "
          f"orphans_killed={orph} healthy=True", flush=True)
    return c


def postflight(tag: str) -> dict:
    c = counts()
    orph = 0
    if c["node_procs"] > 3 or c["uid_procs"] > PROC_CEILING:
        orph = kill_orphans()
        c = counts()
    h = healthy()
    if not h:
        restart_engine(f"unhealthy at postflight of {tag}")
        c = counts()
    print(f"  [postflight {tag}] uid={c['uid_procs']} node={c['node_procs']} "
          f"orphans_killed={orph} healthy_before_restart={h}", flush=True)
    return {**c, "healthy_after_probe": h, "orphans_killed": orph}


@dataclass
class LivelockEvidence:
    detected: bool = False
    at: str = ""
    engine_cpu: float | None = None
    engine_status: str | None = None
    engine_rss_mb: float | None = None
    node_procs: int | None = None
    recovery_s: float | None = None
    sample: str = ""


def capture_livelock(at: str) -> LivelockEvidence:
    """Evidence bundle for a hung engine, then clean up and restart."""
    c = counts()
    ev = LivelockEvidence(detected=True, at=at, engine_cpu=c["engine"]["cpu"],
                          engine_status=c["engine"]["status"],
                          engine_rss_mb=c["engine"]["rss_mb"],
                          node_procs=c["node_procs"])
    pid = c["engine"]["pid"]
    if pid:
        try:
            r = subprocess.run(["sample", str(pid), "1", "-mayDie"],
                               capture_output=True, text=True, timeout=45)
            ev.sample = (r.stdout or "")[:4000]
        except Exception as e:
            ev.sample = f"sample failed: {type(e).__name__}"
    t0 = time.perf_counter()
    restart_engine(f"livelock at {at}")
    ev.recovery_s = round(time.perf_counter() - t0, 2)
    return ev


async def guarded(coro, timeout: float = WATCHDOG_S):
    """Await with the standing-rule watchdog. Returns (result, error_str)."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout), None
    except asyncio.TimeoutError:
        return None, f"WATCHDOG_TIMEOUT>{timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:200]
