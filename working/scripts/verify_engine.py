#!/usr/bin/env python3
"""Engine liveness + environment gate.

`/ping` returning 401 proves only that something is bound to the port. This gate layers four
independent checks so a disagreement between them cannot pass silently:

  1. binary on disk     `./engine --version`         — what we provisioned
  2. HTTP /version      unauthenticated, returns 200 — what is actually *running*
  3. DAP protocol       authenticated connect + rrext_public_probe — the wire works
  4. documented SDK     RocketRideClient.get_server_info() — expected to FAIL, see below

Check 2 is the authoritative one for attribution: the binary on disk and the process serving
requests are not necessarily the same build if an older engine is already listening.

Known SDK 1.3.0 defect (check 4)
--------------------------------
`get_server_info()` is documented as an unauthenticated probe. It constructs
`RocketRideClient(..., public=True)`, but `_public` is written at `client.py:242` and **never read
anywhere else in the SDK**; `connect()` sets `_desired_state='authenticated'` and calls
`_internal_login()` unconditionally, which sends `auth: ''`. The engine answers
"No authorization provided" and the call raises. The `public` kwarg is accepted and silently
ignored — the same failure shape as the `_filter_kwargs_for` splitter bug Leela's team documented
in `findings/stage1_findings.md`. We run it anyway and record the failure as evidence rather than
routing around it quietly.

Second defect: even over an authenticated connection, `rrext_public_probe` returns
`platform`, `capabilities` and `apps` but **no `version` field**, though the docstring promises
one. Protocol-reported version is therefore UNVERIFIED, and we fall back to HTTP /version.

Also captures the host facts every run manifest references, including `ulimit -n` as seen from
*inside* a Python process — the shell's limit is not necessarily the one the benchmark runs
under, and at 10k concurrency an fd ceiling looks exactly like a framework failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = os.environ.get("RR_EXPECTED_VERSION", "3.3.1")
HOST = os.environ.get("RR_HOST", "127.0.0.1")
PORT = os.environ.get("RR_PORT", "5565")
URI = f"http://{HOST}:{PORT}"
APIKEY = os.environ.get("ROCKETRIDE_APIKEY", "MYAPIKEY")


def _sh(cmd: list[str], timeout: float = 15.0, cwd: str | None = None) -> str | None:
    if not shutil.which(cmd[0]) and not Path(cmd[0]).exists():
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return (r.stdout or "").strip() or None
    except Exception:
        return None


def on_ac_power() -> str:
    """Battery vs AC changes CPU frequency policy on Apple Silicon; a run on battery is not
    comparable to one on mains."""
    out = _sh(["pmset", "-g", "ps"])
    if not out:
        return "UNVERIFIED"
    low = out.lower()
    if "ac power" in low:
        return "AC"
    if "battery power" in low:
        return "BATTERY"
    return f"UNVERIFIED ({out.splitlines()[0][:60]})"


def host_facts() -> dict:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    total = None
    try:
        import psutil
        total = psutil.virtual_memory().total
    except Exception:
        pass
    return {
        "macos_product_version": _sh(["sw_vers", "-productVersion"]),
        "macos_build": _sh(["sw_vers", "-buildVersion"]),
        "darwin": platform.release(),
        "arch": platform.machine(),
        "cpu_brand": _sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "cpu_logical": os.cpu_count(),
        "cpu_performance_cores": _sh(["sysctl", "-n", "hw.perflevel0.logicalcpu"]),
        "cpu_efficiency_cores": _sh(["sysctl", "-n", "hw.perflevel1.logicalcpu"]),
        "ram_total_bytes": total,
        "ram_total_gib": round(total / 2**30, 2) if total else None,
        "power_source": on_ac_power(),
        "python": sys.version.split()[0],
        "ulimit_n_soft_in_python": soft,
        "ulimit_n_hard_in_python": hard,
        "ulimit_nproc": list(resource.getrlimit(resource.RLIMIT_NPROC)),
    }


def http_version() -> dict | None:
    try:
        with urllib.request.urlopen(f"{URI}/version", timeout=10) as r:
            return json.loads(r.read().decode()).get("data")
    except Exception:
        return None


def binary_version() -> str | None:
    eng = ROOT / "engine" / "engine"
    if not eng.exists():
        return None
    return _sh([str(eng), "--version"], cwd=str(ROOT / "engine"))


async def dap_probe() -> tuple[dict | None, str | None]:
    """Authenticated DAP probe. Returns (body, error)."""
    from rocketride import RocketRideClient

    c = RocketRideClient(uri=URI, auth=APIKEY, persist=False)
    try:
        await c.connect(timeout=20000)
        r = await c.request(c.build_request("rrext_public_probe", arguments={}), timeout=20000)
        return r.get("body", {}), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    finally:
        try:
            await c.disconnect()
        except Exception:
            pass


async def documented_probe() -> tuple[dict | None, str | None]:
    """The documented unauthenticated path. Expected to fail on SDK 1.3.0 — see module docstring."""
    from rocketride import RocketRideClient

    try:
        info = await RocketRideClient.get_server_info(URI, timeout=15000)
        return dict(info), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def main() -> int:
    print("=" * 72)
    print("benchmark-A engine + environment gate")
    print("=" * 72)

    facts = host_facts()
    print("\n[host]")
    for k, v in facts.items():
        print(f"  {k:28s} {v}")

    findings: dict = {"host": facts, "expected_version": EXPECTED_VERSION, "uri": URI}
    unverified: list[str] = []

    print("\n[1] binary on disk — ./engine --version")
    bin_v = binary_version()
    print(f"  {bin_v or 'NOT FOUND'}")
    findings["binary_version_raw"] = bin_v

    print(f"\n[2] HTTP {URI}/version (unauthenticated)")
    hv = http_version()
    if hv:
        print(f"  version={hv.get('version')}  hash={hv.get('hash')}  stamp={hv.get('stamp')}")
    else:
        print("  NO RESPONSE — engine not serving")
    findings["http_version"] = hv

    print("\n[3] DAP protocol — authenticated connect + rrext_public_probe")
    body, err = asyncio.run(dap_probe())
    if body is not None:
        print(f"  OK  platform={body.get('platform')}  capabilities={body.get('capabilities')}  "
              f"apps={len(body.get('apps', []))}")
        if "version" not in body:
            print("  NOTE: probe body carries no 'version' field despite the SDK docstring "
                  "promising one -> protocol-reported version is UNVERIFIED")
            unverified.append("engine version over DAP protocol (probe omits the field)")
    else:
        print(f"  FAILED: {err}")
        unverified.append(f"DAP protocol liveness ({err})")
    findings["dap_probe"] = body
    findings["dap_probe_error"] = err

    print("\n[4] documented SDK path — RocketRideClient.get_server_info()")
    info, derr = asyncio.run(documented_probe())
    if info is not None:
        print(f"  unexpectedly OK: {json.dumps(info, default=str)[:200]}")
    else:
        print(f"  FAILED (expected on SDK 1.3.0): {derr}")
        print("  cause: `public=True` is stored at client.py:242 and never read; connect() "
              "always runs the auth handshake with an empty key.")
    findings["get_server_info"] = info
    findings["get_server_info_error"] = derr

    # ---- verdict ----------------------------------------------------------
    print("\n" + "-" * 72)
    running = (hv or {}).get("version")
    if not running:
        print("RESULT: FAIL — no running engine answered /version.")
        return 2

    if not running.startswith(EXPECTED_VERSION):
        print(f"RESULT: MISMATCH — running engine reports {running}, provisioned "
              f"{EXPECTED_VERSION}. Stopping: runs would be attributed to the wrong build.")
        return 4

    if bin_v and (hv.get("hash") or "") not in bin_v:
        print(f"RESULT: MISMATCH — binary on disk ({bin_v}) is not the process serving "
              f"requests (hash {hv.get('hash')}). A different engine is listening on {PORT}.")
        return 5

    print(f"RESULT: OK — running engine {running} (hash {hv.get('hash')}) matches provisioned "
          f"{EXPECTED_VERSION}, and matches the binary on disk.")
    if unverified:
        print("\nUNVERIFIED (recorded, not guessed):")
        for u in unverified:
            print(f"  - {u}")
    findings["unverified"] = unverified

    out = ROOT / "results" / "engine_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
