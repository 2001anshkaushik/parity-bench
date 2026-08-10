"""Collision-proof result writing. Use this for EVERY result from now on.

WHY THIS EXISTS
---------------
An audit on 2026-08-10 found that 51 of 51 result writes in this repo used a HARDCODED path with
no variable component, and that SIX output names were claimed by more than one script. Two runs
were silently destroyed by this before it was noticed:

  * `isolated_profile_llamaindex.json` was claimed by three scripts. The pre-warm variant
    overwrote the session-9 ascending profile; only an accidental manual backup preserved it.
  * The descending-order run was overwritten by the pre-warm run. Its numbers survive only in
    `logs/`, not in any result file.

A clobbered result is unrecoverable and silent — strictly worse than a crash. This module makes
that failure mode structurally impossible rather than a thing to remember.

GUARANTEES
----------
1. Every path is unique: `<name>__<UTC-timestamp>__<content-hash>.json`.
2. Writing to an existing path raises `ResultCollision`. There is no overwrite flag; if you truly
   mean to replace a result, delete it by hand and say so in `progress.md`.
3. Every file carries provenance: who wrote it, when, from which git-less working tree, and the
   hash of its own payload.
4. `latest(name)` resolves the most recent run of a given name, so callers never hardcode a path.

    from harness.resultio import write_result, latest
    p = write_result("ladder_llamaindex", {"rung": 10000, ...})
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import socket
import time
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


class ResultCollision(RuntimeError):
    """Raised instead of overwriting an existing result file."""


def _payload_hash(obj) -> str:
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canon).hexdigest()[:12]


def write_result(name: str, data, subdir: str | None = None) -> Path:
    """Write `data` to a unique, provenance-stamped path. Never overwrites."""
    if "/" in name or name.endswith(".json"):
        raise ValueError("name is a bare identifier, not a path or filename")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    h = _payload_hash(data)
    out_dir = RESULTS / subdir if subdir else RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}__{stamp}__{h}.json"
    if path.exists():
        raise ResultCollision(f"refusing to overwrite existing result: {path}")
    envelope = {
        "_meta": {
            "name": name,
            "written_utc": stamp,
            "payload_sha256_12": h,
            "host": socket.gethostname(),
            "user": getpass.getuser(),
            "pid": os.getpid(),
            "schema": "resultio/1",
        },
        "data": data,
    }
    # exclusive create: even a concurrent writer cannot clobber this
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(envelope, f, indent=1, default=str)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def latest(name: str, subdir: str | None = None) -> Path | None:
    """Most recent result for `name`. Callers resolve by name, never by hardcoded path."""
    d = RESULTS / subdir if subdir else RESULTS
    c = sorted(d.glob(f"{name}__*.json"))
    return c[-1] if c else None


def load(name: str, subdir: str | None = None):
    p = latest(name, subdir)
    if not p:
        raise FileNotFoundError(f"no result named {name!r}")
    return json.loads(p.read_text())["data"]
