#!/usr/bin/env python3
"""P1 memory watcher (1 Hz): the running container named <name>'s cgroup v2 memory.stat (anon, file) and
memory.current, one JSONL per container id, until a stop file exists or a time limit passes.

    p1_memwatch.py --name rr --out-dir ~/p1_memwatch --stop ~/p1_memwatch/.stop --max-h 9

Why it exists: the docs runner's own sampler (BSZ_MEMSTAT) started before the run directory existed, so its
output redirect failed and it never ran on P1-B's first two legs. The running chain is pinned to its head and
is not edited mid-run; this watcher covers every later docs leg from outside it. One workload runs at a time
(Ruling C), so the container named rr at a moment IS that moment's leg; each leg's peak is taken from the rows
inside the leg's own measured window."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def cid_of(name: str) -> str:
    r = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="rr")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--stop", type=Path, required=True)
    ap.add_argument("--max-h", type=float, default=9.0)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    t_end = time.monotonic() + a.max_h * 3600
    cid, cg, last_check = "", None, 0.0
    while not a.stop.exists() and time.monotonic() < t_end:
        now = time.monotonic()
        if now - last_check >= 5 or cg is None:
            last_check = now
            c = cid_of(a.name)
            if c != cid:
                cid = c
                cg = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope") if cid else None
        if cg is not None:
            try:
                st = dict(ln.split() for ln in (cg / "memory.stat").read_text().splitlines() if ln.strip())
                row = {"t": time.time(), "cid": cid[:12], "anon": int(st.get("anon", 0)), "file": int(st.get("file", 0)),
                       "total": int((cg / "memory.current").read_text().strip())}
                with open(a.out_dir / f"memwatch_{cid[:12]}.jsonl", "a") as f:
                    f.write(json.dumps(row) + "\n")
            except OSError:
                cg = None
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
