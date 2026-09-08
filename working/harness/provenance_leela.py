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
  * `duplication_patch_applied` is READ from the image label
    `benchmark.rocketride.duplication_patch_applied` (written by docker/Dockerfile.rocketride),
    the same mechanism `experiment_common._engine_patch_state()` uses. It is load-bearing: a
    patched result is not comparable with an unpatched one, and this field is the only thing
    in the block that says which one produced the numbers.

    HISTORY (2026-09-07, DOCS_HANDOFF.md §2.4 / §10.1): from 17 Aug to 7 Sep this file
    hardcoded `"duplication_patch_applied": False` as a literal. Every measured docs export in
    that window carries a false record — including the 18-Aug 10k runs, which ran on
    `rr:patched` (image digest sha256:073b43d8…, label_raw "1" in the same day's
    smoke_phase2 exports) — and the field read False on the LlamaIndex arm too, which has no
    engine to patch. A field that fires identically on an arm that cannot have the property
    carries no information. An unreadable label is recorded as None, NEVER False: None fails
    the check as missing (correct for an unknown); False asserts a fact we did not measure.
    The corrected 18-Aug blocks are re-emitted in the `provenance_correction_20260818` result;
    the original exports are untouched.
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


PATCH_LABEL = "benchmark.rocketride.duplication_patch_applied"
PATCH_ID_LABEL = "benchmark.rocketride.duplication_patch_id"
# The marker an arm with NO RocketRide image carries in `duplication_patch_source`
# (Advisor ruling R2, 2026-09-08). The patch fields are None on such an arm — never False,
# never a fabricated value — and check() exempts them BY SCOPE, listing the exemption.
NOT_APPLICABLE = "not_applicable_no_engine"
PATCH_FIELDS = ("duplication_patch_applied", "duplication_patch_id")


def is_rocketride_arm(arm: Optional[str]) -> bool:
    """The arm naming convention across both campaigns: `rocketride_pdf`, `rocketride_batched`,
    `rocketride_video_parity`, … versus `llamaindex_http_pdf`, `llamaindex_video_workers`."""
    return bool(arm) and arm.startswith("rocketride")


def _docker_label(container: str, key: str) -> Optional[str]:
    """One image label of a running container, or None when docker/the container/the label
    cannot be read. Module-level so a test can substitute it without a docker daemon."""
    out = _run(["docker", "inspect", "-f", "{{index .Config.Labels \"%s\"}}" % key, container])
    if out in (None, "", "<no value>"):
        return None
    return out


def _patch_state(container: Optional[str]) -> Dict[str, Any]:
    """`duplication_patch_applied` / `duplication_patch_id`, READ from the image label.

    Contract (DOCS_HANDOFF.md §10.1): label "1" -> True with the id label; label "0" -> False;
    anything else — no container, docker unreachable, label absent (the LlamaIndex image, or
    an engine image that predates the patch build), or several containers disagreeing — is
    None on BOTH fields, never False. `duplication_patch_source` says how the value was
    obtained so a reader can tell "measured stock" from "could not read".

    `container` may be a comma-joined list (the video driver passes every service container);
    every named container is read and the value is used only when they all agree.
    """
    if not container:
        return {"duplication_patch_applied": None, "duplication_patch_id": None,
                "duplication_patch_source": "no container to inspect (driver-managed mode) — UNKNOWN"}
    names = [c.strip() for c in container.split(",") if c.strip()]
    raws = {c: _docker_label(c, PATCH_LABEL) for c in names}
    seen = {v for v in raws.values() if v is not None}
    if not seen:
        return {"duplication_patch_applied": None, "duplication_patch_id": None,
                "duplication_patch_source": (f"label {PATCH_LABEL} unreadable or absent on "
                                             f"{names} — UNKNOWN, not the same as unpatched")}
    if len(seen) > 1:
        return {"duplication_patch_applied": None, "duplication_patch_id": None,
                "duplication_patch_source": (f"label {PATCH_LABEL} disagrees across {raws} — "
                                             "ambiguous, recorded as UNKNOWN")}
    raw = seen.pop()
    holder = next(c for c, v in raws.items() if v == raw)
    if raw == "1":
        return {"duplication_patch_applied": True,
                "duplication_patch_id": _docker_label(holder, PATCH_ID_LABEL),
                "duplication_patch_source": f"label {PATCH_LABEL}={raw!r} on {holder!r}"}
    if raw == "0":
        return {"duplication_patch_applied": False, "duplication_patch_id": None,
                "duplication_patch_source": f"label {PATCH_LABEL}={raw!r} on {holder!r}"}
    return {"duplication_patch_applied": None, "duplication_patch_id": None,
            "duplication_patch_source": (f"label {PATCH_LABEL}={raw!r} on {holder!r} is neither "
                                         "'0' nor '1' — UNKNOWN")}


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
        # READ from the image label (see module docstring, HISTORY). Never a literal: the
        # literal False this line carried from 17 Aug to 7 Sep 2026 mis-recorded every
        # measured docs export, patched engine and LlamaIndex arm alike. An arm with no
        # RocketRide image has nothing to read: None on both fields, marked not applicable.
        **(_patch_state(container) if is_rocketride_arm(arm) else
           {"duplication_patch_applied": None, "duplication_patch_id": None,
            "duplication_patch_source": NOT_APPLICABLE}),
        "rocketride_sdk_version": _pkg("rocketride"),
        "embedding_model": embedding_model,
        "offered_concurrency": offered_concurrency,
        "configured_concurrency": configured_concurrency,
        "warmup_policy": warmup_policy,
        "timeout_s": timeout_s,
        "mode": mode,
    }
    return block


def check(record: Dict[str, Any], *, arm: Optional[str] = None) -> Dict[str, Any]:
    """His `check()` semantics, reproduced: None / missing / "" all count as absent.

    Two SCOPED exemptions, both listed in the output under `exempted` with a reason in
    `exemption_reasons`, so a reader sees what was not required and why:

    * `duplication_patch_id` is legitimately None on a stock build, so a naive port would
      mark every honest stock run unpublishable. Exempted ONLY when
      `duplication_patch_applied` is explicitly False (a label READ as "0"); an unset flag
      (None: label unreadable) still fails on both fields — the intended outcome for an
      unknown on a RocketRide arm.
    * Both patch fields are exempted for an arm with NO RocketRide image (Advisor R2,
      2026-09-08): the property does not exist there, so requiring it measures nothing.
      The arm is identified by `arm=` when the caller knows it, else by the record's own
      `duplication_patch_source == "not_applicable_no_engine"` marker, which build() writes
      only for non-RocketRide arms. An explicit RocketRide `arm=` always wins over the
      marker: a RocketRide block can never talk its way out of the requirement.
    Never a fabricated value to make the check pass — the requirement is scoped instead.
    """
    exempt: Dict[str, str] = {}
    if arm is not None:
        no_engine = not is_rocketride_arm(arm)
    else:
        no_engine = record.get("duplication_patch_source") == NOT_APPLICABLE
    if no_engine:
        for k in PATCH_FIELDS:
            exempt[k] = (f"arm has no RocketRide image ({NOT_APPLICABLE}); the duplication "
                         "patch property does not exist on it")
    elif record.get("duplication_patch_applied") is False:
        exempt["duplication_patch_id"] = "no patch id on a build whose label was READ as stock (False)"
    gaps = [k for k in REQUIRED
            if k not in exempt
            and (k not in record or record[k] is None or record[k] == "")]
    return {"PASS": not gaps, "missing_fields": gaps,
            "exempted": sorted(exempt), "exemption_reasons": exempt,
            "note": ("complete" if not gaps else
                     "INCOMPLETE PROVENANCE — run is not publishable")}
