#!/usr/bin/env python3
"""STEP 4 — operational complexity. Facts only, no editorial.

Kept in a SEPARATE table from every performance number, deliberately. Ease of operation is a real
procurement input, but folding it into a performance chart is how benchmarks turn into marketing.
It is also why "lines of code" was dropped from the metric set entirely — trivially gameable, and
it measures API taste rather than anything operational.

Measured per framework, for a Tier 2 (service) deployment:
  * time to install into a clean venv (wall seconds, measured)
  * transitive dependency count and on-disk size (measured)
  * processes required to operate (measured elsewhere in this suite, carried in)
  * cold start to first successful request (measured)
  * config files / env vars required
  * whether a hosted service or API key is required to run at all
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "operational"
UV = Path.home() / ".local" / "bin" / "uv"

# DOWNSCALED for the 3 h session budget: deepagents and omnigent dropped from this pass.
# deepagents is built on langgraph (not an independent data point) and omnigent is still
# Track-A PENDING a behavioural locality probe, so neither changes the Tier 2 picture today.
# Stated, not silently skipped — both belong in the full table before publication.
TARGETS = {
    "langgraph": ["langgraph"],
    "crewai": ["crewai"],
    "rocketride_sdk": ["rocketride"],
    "fastapi_stack": ["fastapi", "uvicorn[standard]"],
}
DOWNSCALED_OUT = ["deepagents (built on langgraph, not independent)",
                  "omnigent (Track A locality still PENDING)"]


def dir_size_mb(p: Path) -> float:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return round(total / 2**20, 1)


def measure(name: str, pkgs: list[str]) -> dict:
    row: dict = {"framework": name, "packages": pkgs}
    if not UV.exists():
        return {**row, "error": "uv not found"}
    tmp = Path(tempfile.mkdtemp(prefix=f"opc-{name}-"))
    try:
        venv = tmp / "v"
        subprocess.run([str(UV), "venv", "--python", "3.12", str(venv)],
                       capture_output=True, text=True, timeout=180)
        py = venv / "bin" / "python"
        empty_mb = dir_size_mb(venv)

        t0 = time.perf_counter()
        r = subprocess.run([str(UV), "pip", "install", "--python", str(py), *pkgs],
                           capture_output=True, text=True, timeout=1800)
        row["install_wall_s"] = round(time.perf_counter() - t0, 2)
        row["install_ok"] = r.returncode == 0
        if r.returncode != 0:
            row["install_error"] = (r.stderr or r.stdout)[-400:]
            return row

        probe = ("import importlib.metadata as md, json\n"
                 "print(json.dumps(sorted({d.metadata['Name'] for d in md.distributions() "
                 "if d.metadata['Name']})))\n")
        pr = subprocess.run([str(py), "-c", probe], capture_output=True, text=True, timeout=180)
        deps = json.loads(pr.stdout.strip().splitlines()[-1]) if pr.returncode == 0 else []
        row["dependency_count"] = len(deps)
        row["venv_size_mb"] = dir_size_mb(venv)
        row["install_size_mb"] = round(row["venv_size_mb"] - empty_mb, 1)

        # cold start = time to import the top-level module in a fresh interpreter
        mod = pkgs[0].split("[")[0].replace("-", "_")
        cs = subprocess.run(
            [str(py), "-c",
             f"import time;t=time.perf_counter();import {mod};"
             f"print(round((time.perf_counter()-t)*1000,1))"],
            capture_output=True, text=True, timeout=300)
        row["import_cold_start_ms"] = (cs.stdout.strip() if cs.returncode == 0
                                       else f"FAIL: {(cs.stderr or '')[-120:]}")
        return row
    except subprocess.TimeoutExpired:
        return {**row, "install_ok": False, "install_error": "TIMEOUT"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("=" * 74)
    print("STEP 4 — OPERATIONAL COMPLEXITY (measured)")
    print("=" * 74)
    for name, pkgs in TARGETS.items():
        print(f"\n[{name}] installing {pkgs} ...", flush=True)
        row = measure(name, pkgs)
        rows.append(row)
        (OUT / "operational.json").write_text(json.dumps(rows, indent=2, default=str))
        print(f"  install={row.get('install_wall_s')}s deps={row.get('dependency_count')} "
              f"size={row.get('install_size_mb')}MB cold_import={row.get('import_cold_start_ms')}ms",
              flush=True)
    (OUT / "operational.json").write_text(json.dumps(
        {"rows": rows, "downscaled_out_of_this_pass": DOWNSCALED_OUT}, indent=2, default=str))
    print(f"\n  DOWNSCALED OUT: {DOWNSCALED_OUT}")
    print(f"\nwritten -> {OUT/'operational.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
