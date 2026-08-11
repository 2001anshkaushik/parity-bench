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
# --- engine node process matching -------------------------------------------------------------
# The engine's per-task node processes are found by matching a literal substring against process
# command lines. That string contains the *directory the clone sits in*, so in a clone named
# anything other than `benchmark-A` it matches nothing — and every caller then reports zero node
# processes, zero orphans, and a clean teardown. A silent wrong answer, which is the failure class
# this repo exists to eliminate.
#
# Two defences:
#   1. RR_NODE_MARK overrides the pattern without editing code.
#   2. check_node_mark() compares the DECLARED pattern against the MEASURED process table and
#      raises if the pattern matches nothing while processes that are plainly engine nodes exist.
NODE_MARK_DEFAULT = "benchmark-A/engine/ai/node.py"
NODE_MARK = os.environ.get("RR_NODE_MARK", NODE_MARK_DEFAULT)

# Directory-independent tail of the same path. Used ONLY to detect that NODE_MARK has gone stale,
# never as the match itself — it is deliberately broader and would match a neighbouring tree's
# engine too, which is exactly the confusion NODE_MARK exists to avoid.
NODE_MARK_SUFFIX = "engine/ai/node.py"
ENGINE_MARK = "eaas.py"
PROC_CEILING = 750          # standing rule: never leave the table above this
WATCHDOG_S = 90.0           # standing rule: unresponsive beyond this = livelock


class NodeMarkStale(RuntimeError):
    """NODE_MARK matched nothing while processes that are plainly engine nodes were running.

    Raised instead of returning zero, because zero is indistinguishable from a healthy idle
    engine and every caller would treat it as one.
    """


def _uid_cmdlines():
    for p in psutil.process_iter(["uids", "cmdline", "pid"]):
        try:
            yield p, " ".join(p.info["cmdline"] or ())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def check_node_mark(raise_on_stale: bool = True) -> dict:
    """Declared vs measured: is NODE_MARK still capable of finding this tree's node processes?

    Returns counts either way. Raises NodeMarkStale when the pattern finds nothing but the
    directory-independent suffix finds something — the signature of a renamed clone.

    Cannot detect a stale pattern while the engine is idle: with no node processes at all, both
    counts are zero and there is nothing to compare. That case is reported as `conclusive: False`
    rather than as a pass.
    """
    matched = suffixed = 0
    examples: list[str] = []
    for _p, cmd in _uid_cmdlines():
        if NODE_MARK_SUFFIX in cmd:
            suffixed += 1
            if len(examples) < 3:
                examples.append(cmd[:200])
        if NODE_MARK in cmd:
            matched += 1
    stale = suffixed > 0 and matched == 0
    out = {"pattern": NODE_MARK, "is_default": NODE_MARK == NODE_MARK_DEFAULT,
           "matched": matched, "suffix_matched": suffixed,
           "stale": stale, "conclusive": suffixed > 0, "examples": examples}
    if stale and raise_on_stale:
        raise NodeMarkStale(
            f"\n"
            f"  Engine node processes are running, but the match pattern found NONE of them.\n"
            f"    pattern in use   : {NODE_MARK!r}"
            f"{' (default)' if NODE_MARK == NODE_MARK_DEFAULT else ' (from $RR_NODE_MARK)'}\n"
            f"    processes seen   : {suffixed} matching {NODE_MARK_SUFFIX!r}\n"
            f"    example cmdline  : {examples[0] if examples else '-'}\n"
            f"\n"
            f"  The pattern embeds the directory the clone sits in, so it stops matching when the\n"
            f"  clone is named something else. Every caller would otherwise report zero node\n"
            f"  processes and a clean teardown, silently.\n"
            f"\n"
            f"  Fix: export RR_NODE_MARK to a substring that appears in the cmdline above, e.g.\n"
            f"    export RR_NODE_MARK='{NODE_MARK_SUFFIX}'\n"
            f"  See publishable/PROVISIONING.md §2.")
    return out


def engine_version(timeout: float = 8.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{URI}/version", timeout=timeout) as r:
            return json.loads(r.read().decode()).get("data")
    except Exception:
        return None


def healthy(timeout: float = 8.0) -> bool:
    return engine_version(timeout) is not None


def counts() -> dict:
    total = node = suffixed = 0
    example = None
    eng = {"pid": None, "cpu": None, "rss_mb": None, "status": None, "threads": None}
    for p in psutil.process_iter(["uids", "cmdline", "pid"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            total += 1
            cmd = " ".join(p.info["cmdline"] or ())
            # counted from the SAME snapshot as `node`, so the comparison below cannot be
            # confused by processes starting or exiting between two passes
            if NODE_MARK_SUFFIX in cmd:
                suffixed += 1
                if example is None:
                    example = cmd[:200]
            if NODE_MARK in cmd:
                node += 1
            elif ENGINE_MARK in cmd and "5565" in cmd:
                eng["pid"] = p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if suffixed and not node:
        raise NodeMarkStale(
            f"\n"
            f"  counts() found {suffixed} engine node process(es), but the match pattern found 0.\n"
            f"    pattern in use  : {NODE_MARK!r}"
            f"{' (default)' if NODE_MARK == NODE_MARK_DEFAULT else ' (from $RR_NODE_MARK)'}\n"
            f"    example cmdline : {example}\n"
            f"\n"
            f"  Returning 0 here would look exactly like a healthy idle engine. Set RR_NODE_MARK to\n"
            f"  a substring of the cmdline above — e.g. {NODE_MARK_SUFFIX!r}.\n"
            f"  See publishable/PROVISIONING.md §2.")
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
    suffixed = 0
    example = None
    for p in psutil.process_iter(["cmdline", "pid"]):
        try:
            cmd = " ".join(p.info["cmdline"] or ())
            if NODE_MARK_SUFFIX in cmd:
                suffixed += 1
                if example is None:
                    example = cmd[:200]
            if NODE_MARK in cmd:
                victims.append(psutil.Process(p.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if suffixed and not victims:
        # "killed 0 orphans" and "there were no orphans" must not look the same: the whole point
        # of this function is that leftover node processes corrupt every later measurement.
        raise NodeMarkStale(
            f"\n"
            f"  kill_orphans() saw {suffixed} engine node process(es) but matched NONE, so it would\n"
            f"  have reported a clean teardown while leaving every one of them running.\n"
            f"    pattern in use  : {NODE_MARK!r}"
            f"{' (default)' if NODE_MARK == NODE_MARK_DEFAULT else ' (from $RR_NODE_MARK)'}\n"
            f"    example cmdline : {example}\n"
            f"\n"
            f"  Set RR_NODE_MARK to a substring of the cmdline above — e.g. {NODE_MARK_SUFFIX!r}.\n"
            f"  See publishable/PROVISIONING.md §2.")
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
