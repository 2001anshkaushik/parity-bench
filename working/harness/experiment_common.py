"""Shared setup and provenance for the two standalone experiments.

WHY THESE ARE SEPARATE SCRIPTS, not extra legs of the smoke. Shashi's rule, adopted verbatim
(`bench.py:527`): "Fault isolation is a SEPARATE run, never mixed into throughput phases:
exception paths and retries change timing, so a poisoned batch measures resilience, not speed —
mixing them contaminates both numbers." The same argument applies to data isolation, which runs
two tenants concurrently and would distort any throughput figure measured alongside it.

WHAT IS SHARED. Corpus selection, the provenance block, arm construction, service liveness and
result writing — so an experiment result can be laid beside a smoke result and the pipeline
hash, corpus hash and pins can be compared field for field.

BOTH ARMS, SAME MECHANISM. Every discovery and liveness path here is arm-agnostic by
construction: same corpus, same records, same classifier. Defect #24 was a check honoured on one
arm and not the other, and it is the cheapest mistake in this project to make twice.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent

CORPUS_GLOB = os.environ.get("SMOKE_CORPUS_GLOB", "*.pdf")
PORT = int(os.environ.get("SMOKE_PORT", "8801"))
EXTERNAL = os.environ.get("SMOKE_EXTERNAL", "") not in ("", "0")
LI_CONTAINER = os.environ.get("SMOKE_LI_CONTAINER", "li")
RR_CONTAINER = os.environ.get("SMOKE_RR_CONTAINER", "rr")
PIPE = "product_pdf.pipe"


def say(m: str) -> None:
    print(m, flush=True)


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ corpus

def corpus(n: int, offset: int = 0) -> List[Path]:
    """`sorted(*.pdf)[offset:offset+n]` — the smoke's rule, with an offset so two tenants can
    take provably disjoint halves of one corpus."""
    d = ROOT / "corpus" / "govdocs1" / "pdfs"
    pdfs = sorted(d.glob(CORPUS_GLOB))
    if len(pdfs) < offset + n:
        raise SystemExit(
            f"BLOCKER: need {offset + n} PDFs matching {CORPUS_GLOB} in {d}, found {len(pdfs)}. "
            "Run working/scripts/fetch_govdocs.py first — DONE there means manifest-verified.")
    return pdfs[offset:offset + n]


def corpus_sha(pdfs: List[Path]) -> str:
    """Ordered name:sha over the selection — identical construction to the smoke, so the two
    provenance blocks are comparable."""
    return h("".join(f.name + ":" + hashlib.sha256(f.read_bytes()).hexdigest() for f in pdfs))


# ------------------------------------------------------------------ provenance

def provenance(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The block every publishable record must carry.

    Leela made engine version, sha256, SDK version, patch id and image digest REQUIRED fields
    after `a5c3b5d`; a run omitting them is not publishable. We cannot read his image labels, but
    we can record ours and — critically — record that our engine is UNPATCHED for
    BUG_CHUNK_DUPLICATION, because a patched-engine result and an unpatched one are not
    comparable and nothing else in the file would say so.
    """
    pipe_path = ROOT / "working" / "pipes" / PIPE
    raw = hashlib.sha256(pipe_path.read_bytes()).hexdigest()
    cfg = json.loads(pipe_path.read_text())
    cfg.pop("project_id", None)
    canon = h(json.dumps(cfg, sort_keys=True, separators=(",", ":")))
    import platform
    p: Dict[str, Any] = {
        "pipeline": {"file": PIPE,
                     "nodes": [c["provider"] for c in cfg["components"]],
                     "sha256_raw": raw, "sha256_canonical": canon},
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "publishable": platform.system() == "Linux"
                     and platform.machine() == "x86_64"},
        # READ from the image label, never asserted. We now build rr:patched AND rr:stock, so a
        # hardcoded False is a lie half the time — and the whole point of the label is that the
        # artifact says what it is. None means we could not read it, which is not the same as
        # unpatched and must not be recorded as if it were.
        "engine": _engine_patch_state(),
        "mode": {"external": EXTERNAL, "li_container": LI_CONTAINER if EXTERNAL else None,
                 "rr_container": RR_CONTAINER if EXTERNAL else None, "port": PORT},
        "image_digests": _image_digests() if EXTERNAL else None,
    }
    if extra:
        p.update(extra)
    return p


def _engine_patch_state() -> Dict[str, Any]:
    """Is the RocketRide image under test patched for BUG_CHUNK_DUPLICATION?

    From `docker inspect` labels written by docker/Dockerfile.rocketride. A patched-engine result
    and a stock one are not comparable, and this is the only field in the export that says which
    one produced the numbers.
    """
    if not EXTERNAL:
        return {"duplication_patch_applied": None,
                "reason": "not external mode — no container to inspect"}
    applied = _run_docker(RR_CONTAINER,
                          "{{index .Config.Labels \"benchmark.rocketride.duplication_patch_applied\"}}")
    pid_ = _run_docker(RR_CONTAINER,
                       "{{index .Config.Labels \"benchmark.rocketride.duplication_patch_id\"}}")
    if applied in (None, "", "<no value>"):
        return {"duplication_patch_applied": None, "duplication_patch_id": None,
                "reason": ("image carries no duplication_patch_applied label — it predates the "
                           "patch build. UNKNOWN, which is not the same as unpatched.")}
    return {"duplication_patch_applied": applied == "1",
            "duplication_patch_id": pid_ if applied == "1" else None,
            "label_raw": applied,
            "note": ("measured exposure on stock 3.3.1, our corpus: 5/199 documents at "
                     "repeat_factor 2. self_duplication must read 0 on a patched build.")}


def service_available_cpus(container: str) -> Tuple[Optional[int], str]:
    """The SERVICE's CPU allocation, for utilisation denominators. NEVER the driver's affinity.

    Defect #34: the driver runs under `taskset -c 24-31` while the container runs on cpuset
    0-23, so `len(os.sched_getaffinity(0))` in the driver returned 8 where the service had 24 —
    cpu_utilization printed 1.58 INVALID for a true 52.8%. Every utilisation cell sampled while
    the driver is pinned was affected.

    Order: the container's own cgroup `cpuset.cpus.effective` (MEASURED — what the kernel
    granted), then `docker inspect .HostConfig.CpusetCpus` (DECLARED — labelled as such), then
    (None, reason). There is deliberately no affinity fallback: a wrong-process denominator is
    exactly the defect this function exists to prevent, and None keeps utilisation None rather
    than confidently wrong.
    """
    from harness.memory_sources import cgroup_path_for_pid, cgroup_cpuset_count, parse_cpuset
    pid = _container_root_pid(container)
    if pid is not None:
        cg = cgroup_path_for_pid(pid)
        if cg is not None:
            r = cgroup_cpuset_count(cg)
            if r["cpus"]:
                return r["cpus"], (f"{r['source']} of container '{container}' "
                                   f"(pid {pid}) = {r['raw']!r} — MEASURED")
    declared = _run_docker(container, "{{.HostConfig.CpusetCpus}}")
    n = parse_cpuset(declared) if declared and declared != "<no value>" else None
    if n:
        return n, (f"docker inspect CpusetCpus of '{container}' = {declared!r} — DECLARED, "
                   "not measured (cgroup read failed)")
    return None, (f"could not resolve a cpuset for container '{container}' by cgroup or "
                  "docker inspect; utilisation stays None rather than using the driver's "
                  "affinity (defect #34)")


def _container_root_pid(name: str) -> Optional[int]:
    """HOST pid of a container's main process. Delegates to weekend_worker.container_root_pid so
    there is ONE discovery mechanism in the project, used identically on both arms — defect #24
    was a check honoured on one arm and not the other, and this is the same shape of mistake."""
    try:
        from weekend_worker import container_root_pid
        return container_root_pid(name)
    except Exception:
        return None


def _run_docker(container: str, fmt: str) -> Optional[str]:
    """One `docker inspect -f` field, or None. Used for read-backs where a config value must be
    confirmed in EFFECT rather than trusted from the command that set it."""
    try:
        r = subprocess.run(["docker", "inspect", "-f", fmt, container],
                           capture_output=True, text=True, timeout=20)
        return (r.stdout.strip() or None) if r.returncode == 0 else None
    except Exception:
        return None


def _image_digests() -> Dict[str, Any]:
    """Whatever Docker will tell us about the two containers. Best effort — absent is recorded
    as absent, never as an empty string that reads like a value."""
    out: Dict[str, Any] = {}
    for role, name in (("llamaindex", LI_CONTAINER), ("rocketride", RR_CONTAINER)):
        try:
            r = subprocess.run(
                ["docker", "inspect", "-f", "{{.Image}}|{{.Config.Image}}|{{.State.StartedAt}}",
                 name], capture_output=True, text=True, timeout=20)
            out[role] = r.stdout.strip() or None if r.returncode == 0 else None
        except Exception as e:
            out[role] = f"unavailable: {type(e).__name__}"
    return out


# ------------------------------------------------------------------ liveness

def li_alive(timeout: float = 10.0) -> bool:
    """Shashi's `service_alive_after` for the HTTP arm: does the health endpoint answer?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def rr_alive(timeout: float = 20.0) -> bool:
    """Same question for the engine. A fresh connect+use is the only honest liveness proof: the
    engine can hold its port open while every task is dead — exactly the 10k sequential failure,
    where 371 documents were accepted and refused by a container that never restarted.
    """
    try:
        from weekend_worker import RocketPdfArm
    except Exception:
        return False
    arm = None
    try:
        arm = RocketPdfArm(f"alive{os.getpid()}")
        return bool(arm.tok)
    except Exception:
        return False
    finally:
        if arm is not None:
            try:
                arm.close()
            except Exception:
                pass


def restart_container(name: str, wait_s: float = 180.0) -> Dict[str, Any]:
    """`restart_engine()` from Shashi's protocol (bench.py:554), for external/container mode.

    A fault run on an engine that already served a previous phase measures that phase's residue
    as much as the poison document. This is opt-in (EXP_RESTART) because the box is shared and a
    restart while another leg is running would destroy it — but NOT restarting is a documented
    deviation from the protocol we said we would match, so it is recorded either way.
    """
    t0 = time.time()
    try:
        r = subprocess.run(["docker", "restart", name], capture_output=True, text=True,
                           timeout=wait_s)
        if r.returncode != 0:
            return {"restarted": False, "error": (r.stderr or r.stdout).strip()[:200]}
    except Exception as e:
        return {"restarted": False, "error": f"{type(e).__name__}: {e}"[:200]}
    return {"restarted": True, "restart_s": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ records

def record(doc: str, submit_ns: int) -> Dict[str, Any]:
    return {"doc": doc, "submit_ns": submit_ns}


def finish_ok(rec: Dict[str, Any], chunks: List[str], vecs: List[list]) -> Dict[str, Any]:
    """A response arrived. Whether it counts as success is ONE rule for both arms.

    An empty chunk list is `no_documents`, NOT a success — Leela's `_server_surfaced` scores it
    as failure the server never reported, and that number is the finding: how much a caller must
    verify itself to notice the framework did nothing.
    """
    rec["completion_ns"] = time.time_ns()
    rec["n_chunks"] = len(chunks)
    rec["chunk_sha256"] = [h(c) for c in chunks]
    rec["total_chars"] = sum(len(c) for c in chunks)
    rec["vector_sha256"] = [vector_hash(v) for v in vecs]
    if not chunks:
        rec["ok"] = False
        rec["reason"] = "no_documents"
    else:
        rec["ok"] = True
        rec["reason"] = "completed"
    return rec


def finish_err(rec: Dict[str, Any], exc: BaseException) -> Dict[str, Any]:
    """Classify a raised exception into the reasons Leela's `_server_surfaced` understands.

    The distinction that matters: an HTTP status or a transport error means the SERVICE told us
    it failed; anything else means only our own proof layer noticed.
    """
    rec["completion_ns"] = time.time_ns()
    rec["ok"] = False
    rec["error"] = f"{type(exc).__name__}: {exc}"[:250]
    rec["error_class"] = type(exc).__name__
    if isinstance(exc, urllib.error.HTTPError):
        rec["http_status"] = exc.code
        rec["reason"] = "http_error"
    elif isinstance(exc, urllib.error.URLError) or isinstance(exc, (ConnectionError, OSError)):
        rec["reason"] = "transport_error"
    elif type(exc).__name__ in ("TimeoutError", "AsyncTimeoutError"):
        rec["reason"] = "timeout"
    else:
        # An engine-side exception surfaced over the SDK: the service did report it.
        rec["reason"] = "service_error"
    return rec


def vector_hash(v) -> Optional[str]:
    """A stable fingerprint for an embedding.

    Rounded to 6 decimals before hashing: float formatting differs across serialisation paths
    and an unrounded hash would report every vector as distinct, which would make a leak
    undetectable rather than merely noisy.
    """
    if not v:
        return None
    try:
        return h(",".join(f"{float(x):.6f}" for x in v))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ exit

def verdict_exit(ok: bool, path: Path, failures: List[str]) -> int:
    """Non-zero on failure, and say WHICH check failed — an exit code alone has never once been
    enough to act on."""
    say(f"\nwritten -> {path}")
    if ok:
        say("VERDICT: PASS")
        return 0
    say("VERDICT: FAIL")
    for f in failures:
        say(f"  - {f}")
    return 1
