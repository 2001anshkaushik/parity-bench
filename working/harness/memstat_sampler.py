#!/usr/bin/env python3
"""P1 memory sampler: a container's cgroup v2 memory.stat (anon, file) and memory.current, at 1 Hz,
until a marker file appears. The P1 memory figure is the SAMPLED peak from these rows; the cgroup's
memory.peak (a high-water mark over the container's whole lifetime, warm-up included) is written
beside it as context only.

    memstat_sampler.py --container rr --out <leg>/memstat.jsonl --until <leg>/.leg_done
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional


def cgroup_dir(container: str) -> Path:
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", container], capture_output=True,
                         text=True, check=True).stdout.strip()
    for cand in (Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope"), Path(f"/sys/fs/cgroup/docker/{cid}")):
        if (cand / "memory.stat").exists():
            return cand
    hits = [p.parent for p in Path("/sys/fs/cgroup").rglob("memory.stat") if cid in str(p)]
    if hits:
        return hits[0]
    raise SystemExit(f"memstat_sampler: no cgroup v2 memory.stat for container {container} ({cid[:12]})")


def read(cg: Path) -> Dict[str, int]:
    st = dict(ln.split() for ln in (cg / "memory.stat").read_text().splitlines() if ln.strip())
    return {"anon": int(st.get("anon", 0)), "file": int(st.get("file", 0)),
            "total": int((cg / "memory.current").read_text().strip())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--until", type=Path, required=True)
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--max-s", type=float, default=6 * 3600)
    a = ap.parse_args()
    cg = cgroup_dir(a.container)
    period, t_end = 1.0 / a.hz, time.monotonic() + a.max_s
    peak: Dict[str, int] = {}
    n = 0
    with open(a.out, "a") as f:
        while not a.until.exists() and time.monotonic() < t_end:
            try:
                r = read(cg)
            except OSError:
                break                                      # the container is gone
            f.write(json.dumps({"t": time.time(), "t_mono": time.monotonic(), **r}) + "\n")
            f.flush()
            n += 1
            for k, v in r.items():
                peak[k] = max(peak.get(k, 0), v)
            peak["anon_plus_file"] = max(peak.get("anon_plus_file", 0), r["anon"] + r["file"])
            time.sleep(period)
    lifetime_peak: Optional[int] = None
    try:
        lifetime_peak = int((cg / "memory.peak").read_text().strip())
    except (OSError, ValueError):
        pass
    summ = {"container": a.container, "cgroup": str(cg), "hz": a.hz, "samples": n,
            "sampled_peak_bytes": peak,
            "memory_peak_lifetime_context_only": lifetime_peak,
            "note": "sampled peaks are the P1 figure; memory.peak spans the container's whole "
                    "lifetime (warm-up included) and is context only"}
    Path(str(a.out) + ".summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
