"""Leela's REQUIRED provenance block, emitted under HIS field names.

`aws_bench/metrics/provenance.py:16-27` lists 24 fields and `check()` marks a run **not
publishable** if any is missing, null or empty. Our results already carry most of that
information — under our own names, in `pipeline` / `corpus` / `pinned` / `_meta`. A consumer
running his `check()` against our export fails us on 23 of 24 anyway, because the check is by
key name.

So this emits a `provenance_leela` block with his exact keys, ALONGSIDE our own blocks rather
than replacing them. Cheap, and it removes a whole class of "your run is not publishable"
before it can be raised.

RULES FOLLOWED HERE:
  * a field we cannot determine is `None`, never a plausible-looking guess. His check treats
    None as missing, which is the correct outcome — an unknown field must fail, not pass.
  * `duplication_patch_applied` is False for us and that is load-bearing: he builds patched by
    default (`RR_DUP_PATCH=1`), we build stock, and a patched result is not comparable with an
    unpatched one.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent

REQUIRED = (
    "run_id", "timestamp_utc",
    "git_commit", "image_digest", "framework_version",
    "instance_type", "architecture", "cpu_count", "ram_gb",
    "corpus_manifest_sha256", "corpus_n_docs",
    "parser", "parser_config_hash", "chunk_config",
    "rocketride_engine_version", "duplication_patch_applied",
    "duplication_patch_id", "rocketride_sdk_version",
    "embedding_model",
    "offered_concurrency", "configured_concurrency",
    "warmup_policy", "timeout_s",
    "mode",
)


def _run(cmd, timeout=15) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def _git_commit() -> Optional[str]:
    sha = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if sha and _run(["git", "-C", str(ROOT), "status", "--porcelain"]):
        return f"{sha}-dirty"        # a dirty tree is not the commit; say so
    return sha


def _ram_gb() -> Optional[float]:
    try:
        import psutil
        return round(psutil.virtual_memory().total / 2 ** 30, 1)
    except Exception:
        try:                          # Linux without psutil
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1048576, 1)
        except Exception:
            return None
    return None


def _instance_type() -> Optional[str]:
    """EC2 IMDSv2. Absent off EC2, which is the honest answer rather than 'unknown'."""
    tok = _run(["curl", "-sf", "-X", "PUT", "http://169.254.169.254/latest/api/token",
                "-H", "X-aws-ec2-metadata-token-ttl-seconds: 60"], timeout=3)
    if not tok:
        return None
    return _run(["curl", "-sf", "-H", f"X-aws-ec2-metadata-token: {tok}",
                 "http://169.254.169.254/latest/meta-data/instance-type"], timeout=3)


def _pkg(name: str) -> Optional[str]:
    try:
        import importlib.metadata as md
        return md.version(name)
    except Exception:
        return None


def _image_digest(container: Optional[str]) -> Optional[str]:
    if not container:
        return None
    return _run(["docker", "inspect", "-f", "{{.Image}}", container])


def build(*, arm: str, mode: str, corpus_sha: str, corpus_n: int,
          offered_concurrency: Optional[int], configured_concurrency: Optional[int],
          warmup_policy: str, timeout_s: Optional[float],
          parser: str, chunk_size: int, chunk_overlap: int,
          embedding_model: str, container: Optional[str] = None,
          run_id: Optional[str] = None,
          splitter: str = "RecursiveCharacterTextSplitter") -> Dict[str, Any]:
    """One arm's block. `arm` selects which framework_version is meaningful.

    Phase 2 (video) extension, 2026-08-20: `splitter` is a parameter because the
    LlamaIndex video arm uses its native SentenceSplitter (approved decision) —
    hardcoding RecursiveCharacterTextSplitter here would be confidently wrong
    provenance for that arm, the exact defect class this field survived once
    already. Default preserves every Phase 1 call site byte-for-byte.
    """
    chunk_config = {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap,
                    "splitter": splitter,
                    "input_transform": "text + '\\n'"}
    block: Dict[str, Any] = {
        "run_id": run_id or f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "image_digest": _image_digest(container),
        "framework_version": (_pkg("llama-index-core") if arm.startswith("llamaindex")
                              else _pkg("rocketride")),
        "instance_type": _instance_type(),
        "architecture": f"{platform.system()}/{platform.machine()}",
        "cpu_count": os.cpu_count(),
        "ram_gb": _ram_gb(),
        "corpus_manifest_sha256": corpus_sha,
        "corpus_n_docs": corpus_n,
        "parser": parser,
        "parser_config_hash": hashlib.sha256(
            json.dumps({"parser": parser}, sort_keys=True).encode()).hexdigest()[:16],
        "chunk_config": chunk_config,
        "rocketride_engine_version": "3.3.1",
        # STOCK. Leela builds patched by default (RR_DUP_PATCH=1). Measured exposure on our
        # corpus: 5/199 documents at repeat_factor 2. A patched result is not comparable
        # with this one, and this field is the only thing in the file that says so.
        "duplication_patch_applied": False,
        "duplication_patch_id": None,
        "rocketride_sdk_version": _pkg("rocketride"),
        "embedding_model": embedding_model,
        "offered_concurrency": offered_concurrency,
        "configured_concurrency": configured_concurrency,
        "warmup_policy": warmup_policy,
        "timeout_s": timeout_s,
        "mode": mode,
    }
    return block


def check(record: Dict[str, Any]) -> Dict[str, Any]:
    """His `check()` semantics, reproduced: None / missing / "" all count as absent.

    `duplication_patch_id` is legitimately None on a stock build, so a naive port of his check
    would mark every honest stock run unpublishable. It is exempted ONLY when
    `duplication_patch_applied` is explicitly False — an unset patch flag still fails.
    """
    exempt = set()
    if record.get("duplication_patch_applied") is False:
        exempt.add("duplication_patch_id")
    gaps = [k for k in REQUIRED
            if k not in exempt
            and (k not in record or record[k] is None or record[k] == "")]
    return {"PASS": not gaps, "missing_fields": gaps,
            "exempted": sorted(exempt),
            "note": ("complete" if not gaps else
                     "INCOMPLETE PROVENANCE — run is not publishable")}
