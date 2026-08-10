#!/usr/bin/env python3
"""Find the concurrency at which Model A (N concurrent pipelines) breaks the engine.

The first probe run drove Model A to n=250 and the engine entered a 100% CPU spin: process alive,
port no longer accepting connections, 81 `node.py` task processes orphaned, no recovery after 27
minutes. That is a headline-grade finding either way, so it needs a *number* and a reproduction
rather than one anecdote.

This bisect steps upward, and after every level checks that the engine is still serving before
continuing. On the first failure it stops, records the level, and cleans up — so a repeat of the
27-minute spin is impossible.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

UID = os.getuid()
URI = "http://127.0.0.1:5565"
OUT = ROOT / "results" / "process_scaling"
LEVELS = [25, 50, 100, 150, 200, 250, 300]
REPS = 1


def engine_healthy(timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(f"{URI}/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def count_procs() -> tuple[int, int]:
    total = node = 0
    for p in psutil.process_iter(["uids", "cmdline"]):
        try:
            if not p.info["uids"] or p.info["uids"].real != UID:
                continue
            total += 1
            if "benchmark-A/engine/ai/node.py" in " ".join(p.info["cmdline"] or ()):
                node += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total, node


def engine_cpu() -> float | None:
    for p in psutil.process_iter(["cmdline"]):
        try:
            if "eaas.py" in " ".join(p.info["cmdline"] or ()) and "5565" in " ".join(p.info["cmdline"] or ()):
                p.cpu_percent(None)
                time.sleep(0.5)
                return p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def make_pipes(n: int, tag: str) -> list[str]:
    import uuid
    tmp = ROOT / "pipes" / "generated"
    tmp.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / "pipes" / "probe_minimal.pipe").read_text())
    out = []
    for i in range(n):
        spec = dict(base)
        spec["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bisect-{tag}-{i}"))
        p = tmp / f"bisect_{tag}_{i:04d}.pipe"
        p.write_text(json.dumps(spec, indent=1))
        out.append(str(p.relative_to(ROOT)))
    return out


def cleanup_leaked() -> int:
    killed = 0
    for p in psutil.process_iter(["cmdline", "pid"]):
        try:
            if "benchmark-A/engine/ai/node.py" in " ".join(p.info["cmdline"] or ()):
                p.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        time.sleep(3)
        for p in psutil.process_iter(["cmdline"]):
            try:
                if "benchmark-A/engine/ai/node.py" in " ".join(p.info["cmdline"] or ()):
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return killed


async def one_level(n: int, tag: str) -> dict:
    from rocketride import RocketRideClient

    pipes = make_pipes(n, tag)
    base_total, base_node = count_procs()
    c = RocketRideClient()
    await c.connect(timeout=30000)
    tokens: list[str] = []
    row: dict = {"concurrency": n, "rep": tag}
    try:
        t0 = time.perf_counter()
        res = await asyncio.gather(*(c.use(filepath=p) for p in pipes), return_exceptions=True)
        row["setup_s"] = round(time.perf_counter() - t0, 3)
        tokens = [r["token"] for r in res if isinstance(r, dict) and "token" in r]
        errs = [r for r in res if isinstance(r, BaseException)]
        row["tasks_created"] = len(tokens)
        row["use_errors"] = len(errs)
        row["use_error_sample"] = repr(errs[0])[:180] if errs else None

        peak_total, peak_node = count_procs()
        row["peak_uid_procs"] = peak_total
        row["node_procs"] = peak_node
        row["procs_per_task"] = round((peak_total - base_total) / max(1, len(tokens)), 3)

        t0 = time.perf_counter()
        sends = await asyncio.gather(*(c.send(t, "x", mimetype="text/plain") for t in tokens),
                                     return_exceptions=True)
        row["send_s"] = round(time.perf_counter() - t0, 3)
        row["send_errors"] = sum(1 for s in sends if isinstance(s, BaseException))
    except Exception as e:
        row["level_exception"] = f"{type(e).__name__}: {e}"[:200]
    finally:
        # terminate() costs ~5.5 s per task but parallelises (measured: 1 task 5.6 s, 2 tasks
        # concurrently 5.17 s). The first version of this loop terminated sequentially, so
        # cleanup alone was 5.5 s x N and the bisect appeared to hang at n=25. Teardown cost is
        # a real property worth reporting, but it must not be mistaken for an engine stall.
        t_term = time.perf_counter()
        await asyncio.gather(*(asyncio.wait_for(c.terminate(t), timeout=30) for t in tokens),
                             return_exceptions=True)
        row["terminate_s"] = round(time.perf_counter() - t_term, 3)
        try:
            await c.disconnect()
        except Exception:
            pass
    return row


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("Model A bisect — where does N concurrent pipelines break the engine?")
    print("=" * 72)
    if not engine_healthy():
        print("engine not healthy at start; run scripts/start_engine.sh first")
        return 1

    rows: list[dict] = []
    broke_at = None
    for n in LEVELS:
        for rep in range(REPS):
            tag = f"{n}r{rep}"
            print(f"\n[level n={n} rep={rep}]")
            row = await one_level(n, tag)
            await asyncio.sleep(2.0)
            healthy = engine_healthy()
            cpu = engine_cpu()
            tot, node = count_procs()
            row.update({"engine_healthy_after": healthy, "engine_cpu_after": cpu,
                        "uid_procs_after": tot, "node_procs_after": node})
            rows.append(row)
            print(f"  tasks={row.get('tasks_created')}/{n} use_err={row.get('use_errors')} "
                  f"setup={row.get('setup_s')}s procs/task={row.get('procs_per_task')} "
                  f"node_procs={row.get('node_procs')}")
            print(f"  after: healthy={healthy} engine_cpu={cpu} uid_procs={tot} "
                  f"orphaned_node={node}")
            if not healthy:
                broke_at = n
                print(f"\n*** ENGINE STOPPED SERVING at n={n} (rep {rep}) ***")
                break
            if node > 5:
                print(f"  warning: {node} node processes outlived their tasks")
        if broke_at:
            break

    print("\n[cleanup]")
    k = cleanup_leaked()
    print(f"  terminated {k} leftover node processes")

    result = {"levels": LEVELS, "reps": REPS, "rows": rows, "broke_at": broke_at,
              "engine_healthy_at_end": engine_healthy()}
    (OUT / "model_a_bisect.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"\nbroke_at = {broke_at}")
    print(f"written -> {OUT / 'model_a_bisect.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
