#!/usr/bin/env python3
"""Batch-size sweep on documents — RocketRide at ONE token against LlamaIndex, same K grid.

THE QUESTION. RocketRide is held at its out-of-the-box posture: one `use()`, one token, one task
subprocess, `threads=` NOT passed. More tokens are known to buy throughput (the video campaign's
5.21x); this experiment asks what SUBMISSION BATCH SIZE buys instead, with tokens fixed at 1.

WHAT "BATCH SIZE K" MEANS HERE, stated before any number exists — it is the only definition that
exists on both arms without patching either:

  rocketride   one `send_files([K files], token)` per batch; the next batch is sent when the
               previous one returns. K=1 goes through `send_files` too, so K is the ONLY thing
               that changes between legs (not the API).
  llamaindex   the service has no multi-document endpoint (working/ws1/service.py: /process_pdf
               takes one PDF body). A batch of K is K concurrent POSTs with a barrier: the next
               wave starts when all K have returned. Same offered shape as the engine sees.

WHAT IT IS NOT. It is not the embedding batch. That one is hardcoded on the engine
(embedding_transformer maxDocuments=64, encode() at the sentence-transformers default) and
unset on the LlamaIndex service (LlamaIndex default 10). Neither is reachable without changing
an arm, so neither is swept; the asymmetry is recorded in the export as a SOURCE reading
(register entry 1: a source trace is not a measurement).

THE REFERENCE LEG. `--reference-c C` adds the banked submission shape on the same documents:
continuous per-document submission at C in flight, no barrier (`send` on the engine, POST on the
service — smoke50_parser_in.py blast legs). Without it the sweep can only ever answer "which K
is least bad"; with it, "is batching the optimum at all" is answerable. DOCS_HANDOFF §3.5 found
per-document ~45% faster than one atomic batch — under load contamination, so it is re-asked
here rather than assumed.

CPU ALLOCATION (Ruling A, 2026-09-20). Every arm runs UNCONSTRAINED across all host vCPUs: no
cpuset, no --cpus. A cgroup that BINDS is refused, not recorded — the Stage 3 docs legs ran on a
real `--cpuset-cpus 0-23` (their exports carry cpuset_effective 24), so their utilisation cannot
be restated against 32 by division; it has to be re-measured, which is what this posture is for.
The denominator for every utilisation and idle-core figure is the host's own cpu count.

THREE CPU NUMBERS, never one (Ruling A). engine-container (its cgroup cpu.stat), harness/driver
(getrusage self+children), host total (per-core /proc/stat over every cpu). They answer different
questions and their gaps are the finding: host minus container minus driver is work neither owns.
The engine's IDLE SPIN is measured in this posture per leg — token open, pipeline loaded, nothing
submitted — and reported beside every idle-core figure rather than taken from a table measured on
another posture (AUTOMATION_CONTRACT §4: a posture not in the table measures its own).

BOX HYGIENE (Ruling C). Before every measured leg: no container but this arm's, no process
outside the arm and the driver above 0.5 cores, and the host idle baseline recorded INTO the leg.
A prior campaign lost a pass pair to an environmental anomaly nothing was instrumented to see.

BOTH ARMS, ONE METHOD (register entry 12): same documents in the same order, same K grid, same
warm-up rule, same preflight, same cost source (the arm container's cgroup cpu.stat, read at the
leg's own t0/t1), same per-core sampler. One arm per invocation; the other arm's container is
expected to be stopped, and the quiet-box check refuses the leg if anything foreign is busy.

Every condition the comparison depends on is read back and written into the export (register
entry 30): image id, cpuset, NanoCpus, the six thread variables, threads_requested, the slice
sha, the script sha.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures as cf
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import gates_shared as gs                          # noqa: E402
from harness import memory_sources as msrc                      # noqa: E402
from harness.jsonl_stream import JsonlWriter                    # noqa: E402
from harness.percore_sampler import PerCoreSampler              # noqa: E402
from harness.resultio import write_result                       # noqa: E402
from harness.rr_credentials import RR_TTL_S                     # noqa: E402

EXPECTED_IMAGE = {
    "rr": "sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90",  # rr:patched
    "li": "sha256:3d2f1f436a4620698dfd975b048053cce87637611ae78c3e862fe16163e6e00f",  # ws1-llamaindex:x86_64
}
THREAD_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS")
CONTAINER = {"rr": os.environ.get("SMOKE_RR_CONTAINER", "rr"),
             "li": os.environ.get("SMOKE_LI_CONTAINER", "li")}
LI_PORT = int(os.environ.get("SMOKE_PORT", "8801"))
RR_VERSION_URL = os.environ.get("SMOKE_RR_URL", "http://127.0.0.1:5565").rstrip("/") + "/version"
QUIET_MAX_FOREIGN = float(os.environ.get("BSZ_QUIET_MAX_FOREIGN", "2.0"))   # contract §4
BATCH_TIMEOUT_S = int(os.environ.get("BSZ_BATCH_TIMEOUT_S", "1800"))
DOC_TIMEOUT_S = int(os.environ.get("BSZ_DOC_TIMEOUT_S", "1800"))
BREAKER_K = 3
STRAY_CORE_LIMIT = float(os.environ.get("BSZ_STRAY_CORE_LIMIT", "0.5"))   # Ruling C
IDLE_SPIN_WINDOW_S = float(os.environ.get("BSZ_IDLE_SPIN_WINDOW_S", "6.0"))
DROP_CACHES = os.environ.get("BSZ_DROP_CACHES", "") not in ("", "0")   # G5(a)
PREWARM = os.environ.get("BSZ_PREWARM", "") not in ("", "0")
ENVPROBE_SCHEMA_MIN = 2                      # driver_video.py:679, same contract
ENVPROBE_REQUIRED = ("env_probe_schema", "env", "torch_num_threads", "python_version")
DOCUMENT_OUTCOMES = ("no_documents", "empty_extraction", "parse_failed")
PIPE = ROOT / "working" / "pipes" / "product_pdf.pipe"


def say(m: str) -> None:
    print(m, flush=True)


def self_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


# ------------------------------------------------------------------ read-backs

def docker_inspect(name: str) -> Dict[str, Any]:
    r = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"REFUSED: container '{name}' not inspectable: {r.stderr.strip()}")
    return json.loads(r.stdout)[0]


def container_facts(arm: str, expect_thread_env: Optional[str] = "1") -> Dict[str, Any]:
    """Everything the comparison depends on, read from the RUNNING container. A mismatch with
    the posture this script claims is a refusal, not a warning."""
    d = docker_inspect(CONTAINER[arm])
    env = dict(e.split("=", 1) for e in d["Config"]["Env"] if "=" in e)
    pid = d["State"]["Pid"]
    facts = {
        "container": CONTAINER[arm], "running": d["State"]["Running"], "pid": pid,
        "image_id": d["Image"], "image_expected": EXPECTED_IMAGE[arm],
        "cpuset_declared": d["HostConfig"]["CpusetCpus"], "nano_cpus": d["HostConfig"]["NanoCpus"],
        "memory_limit": d["HostConfig"]["Memory"],
        "thread_env": {v: env.get(v) for v in THREAD_VARS},
        "ws1_workers": env.get("WS1_WORKERS"),
        "started_at": d["State"]["StartedAt"],
    }
    problems = []
    if not facts["running"] or not pid:
        problems.append("container is not running")
    if facts["image_id"] != EXPECTED_IMAGE[arm]:
        problems.append(f"image id {facts['image_id']} != expected {EXPECTED_IMAGE[arm]}")
    if facts["nano_cpus"]:
        problems.append("NanoCpus set — a CFS quota and a cpuset are different limiters "
                        "(PHASE1_CARRYOVER: --cpuset-cpus, never --cpus)")
    # The DECLARED thread posture is compared with the container's own env: "1" is the banked
    # docs posture on both arms; None means the six variables must be ABSENT (engine default).
    wrong = [v for v, x in facts["thread_env"].items() if x != expect_thread_env]
    facts["thread_env_expected"] = expect_thread_env if expect_thread_env else "unset"
    if wrong:
        problems.append(f"thread variables differ from the declared posture "
                        f"({facts['thread_env_expected']}): {wrong} (defect #37: omitted once, "
                        "the engine ran at torch=16 against LI at 1, unrecorded)")
    cg = msrc.cgroup_path_for_pid(pid) if pid else None
    facts["cgroup"] = str(cg) if cg else None
    cs = msrc.cgroup_cpuset_count(cg) if cg else {"cpus": None, "raw": None, "source": "no cgroup"}
    facts["cpuset_effective"] = cs
    facts["host_nproc"] = host_nproc()
    # Ruling A: the arm may not be confined. A cgroup that binds is refused rather than recorded,
    # because a figure divided by a denominator the leg did not have is defect #34 either way up.
    if cg is not None:
        try:
            facts["cpu_max"] = (cg / "cpu.max").read_text().strip()
        except OSError:
            facts["cpu_max"] = None
        if facts["cpu_max"] and not facts["cpu_max"].startswith("max"):
            problems.append(f"cpu.max={facts['cpu_max']} — a CFS quota binds this arm (Ruling A: "
                            "unconstrained across every vCPU)")
    if not cs.get("cpus"):
        problems.append(f"no effective cpuset readable: {cs.get('source')}")
    elif cs["cpus"] < facts["host_nproc"]:
        problems.append(f"cpuset {cs['raw']} gives {cs['cpus']} of {facts['host_nproc']} cpus — "
                        "a cpuset binds this arm (Ruling A). Start it with no --cpuset-cpus; the "
                        "Stage 3 docs legs ran at 0-23 and CANNOT be restated against 32.")
    if problems:
        raise SystemExit("REFUSED (posture read-back):\n  - " + "\n  - ".join(problems))
    return facts


def cpus_from_spec(spec: str) -> List[int]:
    out: List[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out += list(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def cgroup_usage_usec(cg: Path) -> int:
    for line in (cg / "cpu.stat").read_text().splitlines():
        if line.startswith("usage_usec"):
            return int(line.split()[1])
    raise RuntimeError(f"no usage_usec in {cg}/cpu.stat")


def _host_ticks() -> Tuple[int, int]:
    v = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return sum(v[:8]), v[3] + v[4]


def host_nproc() -> int:
    """The kernel's cpu count — the Ruling A denominator. os.cpu_count() would answer the
    driver's affinity if the driver were ever pinned; /proc/stat lines are the machine."""
    return sum(1 for line in Path("/proc/stat").read_text().splitlines()
               if line.startswith("cpu") and not line.startswith("cpu "))


def _proc_cpu_snapshot() -> Dict[int, Tuple[float, str]]:
    out: Dict[int, Tuple[float, str]] = {}
    hz = os.sysconf("SC_CLK_TCK")
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            st = (d / "stat").read_text()
            comm_end = st.rindex(")")
            f = st[comm_end + 2:].split()
            out[int(d.name)] = ((int(f[11]) + int(f[12])) / hz, st[st.index("(") + 1:comm_end])
        except (OSError, ValueError, IndexError):
            continue
    return out


def stray_processes(cg: Path, window_s: float = 4.0) -> Dict[str, Any]:
    """Ruling C: anything outside the arm's cgroup and our own process tree burning more than
    STRAY_CORE_LIMIT cores. Named, not merely counted — 'the box was busy' is not a diagnosis."""
    try:
        ours = {int(x) for x in (cg / "cgroup.procs").read_text().split()}
    except (OSError, ValueError):
        ours = set()
    mine = {os.getpid(), os.getppid()}
    a = _proc_cpu_snapshot()
    time.sleep(window_s)
    b = _proc_cpu_snapshot()
    found = []
    for pid, (cpu_b, comm) in b.items():
        if pid in ours or pid in mine:
            continue
        cpu_a = a.get(pid, (cpu_b, comm))[0]
        cores = (cpu_b - cpu_a) / window_s
        if cores > STRAY_CORE_LIMIT:
            found.append({"pid": pid, "comm": comm, "cores": round(cores, 3)})
    found.sort(key=lambda x: -x["cores"])
    return {"limit_cores": STRAY_CORE_LIMIT, "window_s": window_s, "strays": found[:10],
            "clean": not found,
            "basis": "per-process /proc/<pid>/stat utime+stime delta, excluding the arm's "
                     "cgroup.procs and the driver itself"}


def drop_caches() -> Dict[str, Any]:
    """G5(a): the 384-document slice is ~267 MB and the box has 61 GiB, so an ascending K grid
    re-reads a corpus the page cache already holds. Dropping the caches makes ONE leg pay the
    cold read the first leg of a fresh campaign would. Reported as an attempted action with its
    return code: a silent no-op here would look exactly like 'caching does not matter'."""
    r = subprocess.run(["sudo", "sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"],
                       capture_output=True, text=True)
    free = subprocess.run(["free", "-m"], capture_output=True, text=True).stdout.splitlines()
    return {"attempted": True, "rc": r.returncode, "stderr": r.stderr.strip()[:200] or None,
            "free_after": free[1] if len(free) > 1 else None,
            "note": "dropped before the warm-up, so the measured slice is read cold; the "
                    "warm-up's own 25 disjoint documents re-warm only themselves"}


def prewarm_corpus(paths: List[Path]) -> Dict[str, Any]:
    """Read every file the leg will send into the page cache BEFORE the measured window.

    WHY, measured not assumed (G5a): a cold cache cost the service arm 20.9% at K=128 and 3.5%
    at C=32 — the penalty tracks how many files the driver reads AT ONCE, because the service
    arm reads K files in K threads while the engine arm hands paths to the SDK. Without this,
    the first leg of a 10k campaign pays a 6.3 GB cold read and every later leg does not, so the
    LEG ORDER would decide part of the answer. Warming every leg identically removes the
    ordering effect and states the basis: these are steady-state, warm-cache figures.
    """
    t0, n = time.perf_counter(), 0
    for p_ in paths:
        try:
            with open(p_, "rb") as fh:
                while fh.read(1 << 20):
                    n += 1
        except OSError:
            continue
    return {"attempted": True, "files": len(paths), "seconds": round(time.perf_counter() - t0, 2),
            "basis": "every measured and warm-up file read once; the leg then starts warm"}


def measure_idle_spin(cg: Path, window_s: float = IDLE_SPIN_WINDOW_S) -> Dict[str, Any]:
    """The arm's CPU with everything loaded and NOTHING submitted, in THIS posture. Never read
    from the contract's table: that table was measured on cpuset 0-23 with the six thread
    variables at 1, and a posture not in the table has no expected_idle (AUTOMATION_CONTRACT §4)."""
    t0, u0 = time.perf_counter(), cgroup_usage_usec(cg)
    time.sleep(window_s)
    t1, u1 = time.perf_counter(), cgroup_usage_usec(cg)
    return {"cores": round((u1 - u0) / 1e6 / (t1 - t0), 3), "window_s": round(t1 - t0, 2),
            "basis": "arm cgroup cpu.stat with the pipeline loaded and nothing submitted"}


def quiet_box(cg: Path, window_s: float = 4.0) -> Dict[str, Any]:
    """Foreign busy cores = host busy (/proc/stat) − the arm container's own cgroup rate, over
    one window. The arm's idle spin is excluded by MEASUREMENT, in the same window, rather than
    from the contract's table — so it holds for the LlamaIndex arm, which has no table."""
    ncpu = os.cpu_count() or 1
    t0, (tot0, idle0), u0 = time.perf_counter(), _host_ticks(), cgroup_usage_usec(cg)
    time.sleep(window_s)
    t1, (tot1, idle1), u1 = time.perf_counter(), _host_ticks(), cgroup_usage_usec(cg)
    host_busy = (1.0 - (idle1 - idle0) / max(1, tot1 - tot0)) * ncpu
    arm_idle = (u1 - u0) / 1e6 / (t1 - t0)
    foreign = host_busy - arm_idle
    return {"host_busy_cores": round(host_busy, 3), "arm_idle_cores": round(arm_idle, 3),
            "foreign_busy_cores": round(foreign, 3), "max_foreign": QUIET_MAX_FOREIGN,
            "quiet": foreign <= QUIET_MAX_FOREIGN, "load1": os.getloadavg()[0],
            "window_s": window_s,
            "basis": "/proc/stat aggregate busy − arm cgroup usage_usec rate, one window"}


def _assert_envprobe_complete(info: Any) -> None:
    """Absence fails before any value is read (driver_video.py:683). A stale baked node emits an
    older field set; `.get()` would collapse 'the instrument did not report' into 'the value is
    None', and None reads as unpinned exactly where unpinned is the thing being tested."""
    if not isinstance(info, dict) or not info:
        raise SystemExit("REFUSED: env_probe parsed to no data — the payload under the lane key "
                         "was not a JSON object.")
    missing = [k for k in ENVPROBE_REQUIRED if k not in info]
    ver = info.get("env_probe_schema")
    if missing or not (isinstance(ver, int) and ver >= ENVPROBE_SCHEMA_MIN):
        raise SystemExit(f"REFUSED: env_probe is a STALE INSTRUMENT, not a negative read-back — "
                         f"missing {missing or 'no keys'}, schema {ver!r} (need >= "
                         f"{ENVPROBE_SCHEMA_MIN}). The node inside the image predates these "
                         "fields: docker cp working/nodes/env_probe <container>:"
                         "/opt/rocketride/engine/nodes/ and restart, then re-run.")


async def rr_inprocess_readback(threads: Optional[int]) -> Dict[str, Any]:
    """G2: the six variables and torch's EFFECTIVE intra-op count, read from inside a task
    process running THE MEASURED PIPELINE — env_probe appended to product_pdf.pipe, the
    a3_env_torch pattern (driver_video.py:654). Probing a different pipe would be a different
    task process: the one-armed check, register entry 33."""
    from rocketride import RocketRideClient
    pipe = json.loads(PIPE.read_text())
    pipe["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bszenv-{os.getpid()}-{time.time()}"))
    pipe["components"].append({"id": "envprobe_1", "provider": "env_probe", "config": {},
                               "input": [{"lane": "text", "from": "webhook_1"}]})
    pipe["components"].append({"id": "resp_env", "provider": "response_text",
                               "config": {"laneName": "envprobe"},
                               "input": [{"lane": "text", "from": "envprobe_1"}]})
    pp = ROOT / "working" / "pipes" / "generated" / f"bszenv_{os.getpid()}.pipe"
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(pipe))
    c = RocketRideClient()
    await c.connect(timeout=60000)
    kw: Dict[str, Any] = dict(filepath=str(pp.relative_to(ROOT)), ttl=RR_TTL_S)
    if threads is not None:
        kw["threads"] = threads
    tok = (await c.use(**kw))["token"]
    try:
        out = await asyncio.wait_for(c.send(tok, "readback probe", mimetype="text/plain"),
                                     timeout=300)
        # THE RESPONSE KEY IS THE LANE NAME, not "text" (driver_video.py:723). response_text
        # with config laneName='envprobe' returns {'envprobe': [...]}; reading out['text']
        # found nothing and reported it as "the node did not run" — the instrument was fine and
        # the reader was wrong, which is why the md5 fix changed nothing.
        texts = (out or {}).get("envprobe") or []
        if not texts:
            raise SystemExit(
                "REFUSED: env_probe returned nothing under the lane key 'envprobe'. Keys the "
                f"engine actually returned: {sorted((out or {}).keys())}. The response is keyed "
                "by response_text's config.laneName — check the READER first (register entry "
                "37), then whether the node ran at all.")
        info = json.loads(texts[0])
        _assert_envprobe_complete(info)
        return {"source": "env_probe node appended to product_pdf.pipe (same task process as "
                          "the measured nodes)", **info}
    finally:
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=120)
        except Exception:
            pass
        await c.disconnect()


def li_inprocess_readback() -> Dict[str, Any]:
    """G2 for the service arm: /health answers from INSIDE a uvicorn worker (its own torch and
    its own environ), and /proc/<pid>/environ is read inside the container for every worker
    process, so the declared container env is never the evidence."""
    with urllib.request.urlopen(f"http://127.0.0.1:{LI_PORT}/health", timeout=30) as r:
        h = json.loads(r.read().decode())
    out: Dict[str, Any] = {"source": "GET /health answered inside a uvicorn worker, plus "
                                     "/proc/<pid>/environ per worker read in the container",
                           "health_torch_threads": h.get("torch_threads"),
                           "health_thread_env": h.get("thread_env"),
                           "warm_workers": h.get("warm_workers")}
    ps = subprocess.run(["docker", "exec", CONTAINER["li"], "sh", "-c",
                         "for p in /proc/[0-9]*; do [ -r $p/environ ] && "
                         "echo \"$(basename $p) $(tr '\\0' '\\n' < $p/environ | "
                         "grep -E '^(OMP|MKL|OPENBLAS|VECLIB|NUMEXPR|TORCH)_' | tr '\\n' ' ')\"; "
                         "done"], capture_output=True, text=True)
    per_proc = {}
    for line in ps.stdout.splitlines():
        parts = line.split()
        if len(parts) > 1:
            per_proc[parts[0]] = dict(x.split("=", 1) for x in parts[1:] if "=" in x)
    out["worker_environ"] = per_proc
    vals = {tuple(sorted(v.items())) for v in per_proc.values()}
    out["all_workers_agree"] = len(vals) <= 1
    out["n_worker_processes_read"] = len(per_proc)
    return out


def service_ready(arm: str) -> Dict[str, Any]:
    if arm == "li":
        with urllib.request.urlopen(f"http://127.0.0.1:{LI_PORT}/health", timeout=10) as r:
            h = json.loads(r.read().decode())
        return {"health": {k: h.get(k) for k in ("ok", "warm_workers", "torch_threads")}}
    with urllib.request.urlopen(RR_VERSION_URL, timeout=10) as r:
        return {"version": r.read().decode()[:200]}


# ------------------------------------------------------------------ slice

def load_slice(path: Path, corpus_dir: Path) -> Tuple[Dict[str, Any], List[Path], List[Path]]:
    s = json.loads(path.read_text())
    man = {}
    for line in (ROOT / "working" / "results" / "corpus_manifest.jsonl").read_text().splitlines():
        if line.strip():
            m = json.loads(line)
            man[m["file"]] = m["sha256"]
    bad = []
    for name in s["measured"] + s["warm_docs"]:
        p = corpus_dir / name
        if not p.is_file():
            bad.append(f"{name}: missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != man.get(name):
            bad.append(f"{name}: sha256 differs from the manifest")
    if bad:
        raise SystemExit(f"REFUSED (corpus): {len(bad)} slice documents fail the manifest — "
                         f"{bad[:5]}")
    return (s, [corpus_dir / n for n in s["measured"]], [corpus_dir / n for n in s["warm_docs"]])


def batches(items: List[Any], k: int) -> List[List[Any]]:
    return [items[i:i + k] for i in range(0, len(items), k)]


# ------------------------------------------------------------------ rocketride

def documents_from(result: Any) -> List[Dict[str, Any]]:
    """Unwrap the engine's nested response shapes — exp_batched_blast.py:74 (Leela
    rr_driver.py:46-65), kept verbatim."""
    if isinstance(result, dict):
        docs = result.get("documents")
        if isinstance(docs, list) and all(isinstance(d, dict) for d in docs):
            return docs
        for k in ("result", "data", "output"):
            if k in result:
                got = documents_from(result[k])
                if got:
                    return got
        return []
    if isinstance(result, list):
        out: List[Dict[str, Any]] = []
        for item in result:
            out.extend(documents_from(item))
        return out
    return []


def rr_batch_records(files: List[Path], out: Any, bi: int, t0_ns: int, t1_ns: int,
                     err: Optional[str]) -> List[Dict[str, Any]]:
    """Attribution by BASENAME, never list position (Leela rr_driver.py:91-93). A submitted file
    with no response is a failure row, never a dropped one."""
    by_name: Dict[str, Any] = {}
    for it in (out if isinstance(out, list) else [out] if out else []):
        if isinstance(it, dict) and isinstance(it.get("filepath"), str):
            by_name.setdefault(Path(it["filepath"]).name, it)
    recs = []
    for p in files:
        rec: Dict[str, Any] = {"doc": p.name, "batch": bi, "submit_ns": t0_ns,
                               "completion_ns": t1_ns,
                               "timing_source": "batch submit/return (MEASURED per batch; "
                                                "per-document instants do not exist)"}
        it = by_name.get(p.name)
        if err or it is None:
            rec.update(ok=False, n_chunks=0, chunk_sha256=[],
                       reason=err or "no_response_for_file")
        else:
            docs = documents_from(it)
            texts = [d.get("page_content", "") for d in docs]
            ut = it.get("upload_time")
            rec.update(ok=bool(docs), n_chunks=len(docs),
                       chunk_sha256=[gs.chunk_hash(t) for t in texts],
                       upload_time_s=ut if isinstance(ut, (int, float)) else None,
                       reason="completed" if docs else "no_documents")
        recs.append(rec)
    return recs


async def rr_open(threads: Optional[int]):
    from rocketride import RocketRideClient
    pipe = json.loads(PIPE.read_text())
    pipe["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bsz-{os.getpid()}-{time.time()}"))
    pp = ROOT / "working" / "pipes" / "generated" / f"bsz_{os.getpid()}.pipe"
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(pipe))
    c = RocketRideClient()
    await c.connect(timeout=60000)
    kw: Dict[str, Any] = dict(filepath=str(pp.relative_to(ROOT)), ttl=RR_TTL_S)
    if threads is not None:                  # out of the box = NOT PASSED, never passed as None
        kw["threads"] = threads
    tok = (await c.use(**kw))["token"]       # exactly ONE use(): one token, one task
    return c, tok


async def rr_close(c, tok) -> Optional[str]:
    leaked = None
    try:
        await asyncio.wait_for(c.terminate(tok), timeout=120)
    except Exception as e:                   # a leaked task idles at ~0.25 core in the cgroup
        leaked = f"terminate failed: {type(e).__name__} — the next leg's quiet-box check sees it"
    try:
        await c.disconnect()
    except Exception:
        pass
    return leaked


async def rr_send_batches(c, tok, groups: List[List[Path]], w: Optional[JsonlWriter]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    consecutive = 0
    for bi, files in enumerate(groups):
        t0 = time.time_ns()
        out, err = None, None
        try:
            out = await asyncio.wait_for(c.send_files([str(p) for p in files], tok),
                                         timeout=BATCH_TIMEOUT_S)
        except Exception as e:
            err = f"batch_error:{type(e).__name__}"
        rows = rr_batch_records(files, out, bi, t0, time.time_ns(), err)
        for r in rows:
            if w:
                w.write(r)
        recs += rows
        consecutive = consecutive + 1 if err else 0
        if consecutive >= BREAKER_K:
            say(f"  !! breaker: {BREAKER_K} consecutive failed batches — leg aborted")
            break
    return recs


async def rr_send_continuous(c, tok, files: List[Path], conc: int, w: Optional[JsonlWriter]) -> List[Dict[str, Any]]:
    """The banked per-document shape (smoke50_parser_in.py blast_rocket): `send`, C in flight."""
    sem = asyncio.Semaphore(conc)
    recs: List[Dict[str, Any]] = []

    async def one(p: Path):
        b = p.read_bytes()
        async with sem:
            row: Dict[str, Any] = {"doc": p.name, "batch": None, "submit_ns": time.time_ns(),
                                   "timing_source": "per-document submit/return (MEASURED)"}
            try:
                o = await asyncio.wait_for(c.send(tok, b, mimetype="application/pdf"),
                                           timeout=DOC_TIMEOUT_S)
                texts = [d.get("page_content", "") for d in documents_from(o)]
                row.update(completion_ns=time.time_ns(), ok=bool(texts), n_chunks=len(texts),
                           chunk_sha256=[gs.chunk_hash(t) for t in texts],
                           reason="completed" if texts else "no_documents")
            except Exception as e:
                row.update(completion_ns=time.time_ns(), ok=False, n_chunks=0, chunk_sha256=[],
                           reason=f"error:{type(e).__name__}")
        recs.append(row)
        if w:
            w.write(row)
    await asyncio.gather(*(one(p) for p in files))
    return recs


# ------------------------------------------------------------------ llamaindex

def li_post(p: Path, bi: Optional[int]) -> Dict[str, Any]:
    b = p.read_bytes()
    row: Dict[str, Any] = {"doc": p.name, "batch": bi, "submit_ns": time.time_ns(),
                           "timing_source": "per-document submit/return (MEASURED)"}
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{LI_PORT}/process_pdf", data=b,
            headers={"Content-Type": "application/pdf", "X-Doc-Id": f"bsz-{p.name}"})
        with urllib.request.urlopen(req, timeout=DOC_TIMEOUT_S) as r:
            out = json.loads(r.read().decode())
        texts = [c.get("text", "") for c in out.get("chunks", [])] if out.get("ok") else []
        row.update(completion_ns=time.time_ns(), ok=bool(texts), n_chunks=len(texts),
                   chunk_sha256=[gs.chunk_hash(t) for t in texts],
                   reason="completed" if texts else (out.get("error_class") or "no_documents"))
    except Exception as e:
        row.update(completion_ns=time.time_ns(), ok=False, n_chunks=0, chunk_sha256=[],
                   reason=f"error:{type(e).__name__}")
    return row


def li_send_batches(groups: List[List[Path]], k: int, w: Optional[JsonlWriter]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    consecutive = 0
    with cf.ThreadPoolExecutor(max_workers=k) as ex:
        for bi, files in enumerate(groups):
            rows = list(ex.map(lambda p, _bi=bi: li_post(p, _bi), files))   # barrier per wave
            for r in rows:
                if w:
                    w.write(r)
            recs += rows
            wave_dead = all(str(r["reason"]).startswith("error:") for r in rows)
            consecutive = consecutive + 1 if wave_dead else 0
            if consecutive >= BREAKER_K:
                say(f"  !! breaker: {BREAKER_K} consecutive dead waves — leg aborted")
                break
    return recs


def li_send_continuous(files: List[Path], conc: int, w: Optional[JsonlWriter]) -> List[Dict[str, Any]]:
    recs = []
    with cf.ThreadPoolExecutor(max_workers=conc) as ex:
        for r in ex.map(lambda p: li_post(p, None), files):
            if w:
                w.write(r)
            recs.append(r)
    return recs


# ------------------------------------------------------------------ one leg

def run_leg(arm: str, leg: str, k: Optional[int], conc: Optional[int], measured: List[Path],
            warm: List[Path], run_dir: Path, facts: Dict[str, Any], threads: Optional[int],
            allow_noisy: bool) -> Dict[str, Any]:
    cg = Path(facts["cgroup"])
    ncpu_host = facts["host_nproc"]
    cpus = cpus_from_spec(facts["cpuset_effective"]["raw"]) or list(range(ncpu_host))
    say(f"\n=== {arm} {leg} — {len(measured)} documents, warm {len(warm)} ===")
    shape = (lambda docs: batches(docs, k)) if k else None

    # Ruling C, in this order: the box carries this leg and nothing else, and the baseline the
    # claim rests on is recorded INTO the leg rather than remembered.
    others = [c for c in subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                        capture_output=True, text=True).stdout.split()
              if c != CONTAINER[arm]]
    strays = stray_processes(cg)
    pre = quiet_box(cg)
    say(f"  quiet box: host busy {pre['host_busy_cores']}  arm idle {pre['arm_idle_cores']}  "
        f"foreign {pre['foreign_busy_cores']} (max {QUIET_MAX_FOREIGN})  load1 {pre['load1']:.2f}"
        f"  other containers {others or 'none'}  strays {strays['strays'] or 'none'}")
    hygiene = {"other_containers": others, "stray_processes": strays,
               "host_idle_baseline_cores": round(ncpu_host - pre["host_busy_cores"], 3),
               "ruling": "C — one workload on the box; the leg records the baseline it assumed"}
    blockers = []
    if others:
        blockers.append(f"containers other than this arm are running: {others}")
    if not strays["clean"]:
        blockers.append(f"processes above {STRAY_CORE_LIMIT} cores outside the arm: "
                        f"{strays['strays']}")
    if not pre["quiet"]:
        blockers.append(f"foreign busy {pre['foreign_busy_cores']} > {QUIET_MAX_FOREIGN} cores")
    if blockers and not allow_noisy:
        return {"arm": arm, "leg": leg, "k": k, "reference_c": conc, "verdict": "REFUSED",
                "reason": "; ".join(blockers), "quiet_box": pre, "box_hygiene": hygiene}

    perdoc = run_dir / f"perdoc_{arm}_{leg}.jsonl"
    percore = run_dir / f"percore_{arm}_{leg}.jsonl"
    if perdoc.exists() or percore.exists():
        raise SystemExit(f"REFUSED: {perdoc.name} exists — results are append-only")

    leaked = None
    state: Dict[str, Any] = {}

    def driver_cpu_s() -> float:
        r = resource.getrusage(resource.RUSAGE_SELF)
        ch = resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime + ch.ru_utime + ch.ru_stime

    def open_window() -> None:
        state["sampler"] = PerCoreSampler(cpus, interval_s=1.0, out_path=percore)
        state["sampler"].start()
        state["d0"] = driver_cpu_s()
        state["u0"], state["t0_ns"], state["p0"] = (cgroup_usage_usec(cg), time.time_ns(),
                                                    time.perf_counter())

    def close_window() -> None:
        state["p1"], state["t1_ns"], state["u1"] = (time.perf_counter(), time.time_ns(),
                                                    cgroup_usage_usec(cg))
        state["d1"] = driver_cpu_s()
        state["percore"] = state["sampler"].stop()

    state["caches"] = drop_caches() if DROP_CACHES else {"attempted": False}
    if DROP_CACHES:
        say(f"  caches dropped: rc={state['caches']['rc']}  {state['caches']['free_after']}")
    # Prewarm AFTER any drop: the two are opposites and a leg that asked for both would be
    # measuring neither. Refused rather than silently ordered.
    if PREWARM and DROP_CACHES:
        raise SystemExit("REFUSED: BSZ_PREWARM and BSZ_DROP_CACHES are contradictory")
    state["prewarm"] = prewarm_corpus(measured + warm) if PREWARM else {"attempted": False}
    if PREWARM:
        say(f"  corpus prewarmed: {state['prewarm']['files']} files in "
            f"{state['prewarm']['seconds']}s")
    tw = time.perf_counter()
    if arm == "rr":
        async def go():
            nonlocal leaked
            c, tok = await rr_open(threads)
            try:
                if warm:      # same submission shape as the measured leg, excluded from everything
                    if k:
                        await rr_send_batches(c, tok, shape(warm), None)
                    else:
                        await rr_send_continuous(c, tok, warm, conc, None)
                state["warm_s"] = round(time.perf_counter() - tw, 2)
                state["idle_spin"] = measure_idle_spin(cg)   # loaded, nothing submitted
                with JsonlWriter(perdoc) as w:
                    open_window()
                    recs = (await rr_send_batches(c, tok, shape(measured), w) if k
                            else await rr_send_continuous(c, tok, measured, conc, w))
                    close_window()
                return recs
            finally:
                leaked = await rr_close(c, tok)
        recs = asyncio.run(go())
    else:
        if warm:
            li_send_batches(shape(warm), k, None) if k else li_send_continuous(warm, conc, None)
        state["warm_s"] = round(time.perf_counter() - tw, 2)
        state["idle_spin"] = measure_idle_spin(cg)
        with JsonlWriter(perdoc) as w:
            open_window()
            recs = (li_send_batches(shape(measured), k, w) if k
                    else li_send_continuous(measured, conc, w))
            close_window()

    span = state["p1"] - state["p0"]
    cpu_s = (state["u1"] - state["u0"]) / 1e6
    driver_s = state["d1"] - state["d0"]
    pc = state["percore"]
    host_s = (pc["mean_busy_cores"] * span) if pc.get("mean_busy_cores") is not None else None
    spin = (state.get("idle_spin") or {}).get("cores")
    ok = [r for r in recs if r.get("ok")]
    empties = [r["doc"] for r in recs if r.get("reason") == "no_documents"]
    # A document the arm's own parser cannot read is a CONTENT outcome — deterministic, the same
    # at every K, already in the corpus manifest (parse_error) — not a degraded leg. Hard means
    # the work was LOST: transport errors, timeouts, a file with no response. (First pass labelled
    # every LlamaIndex leg DEGRADED over one PdfReadError document that pypdf never could read.)
    hard = [r for r in recs if not r.get("ok") and r.get("reason") not in DOCUMENT_OUTCOMES]
    chunks = sum(r["n_chunks"] for r in ok)
    ncpu = ncpu_host                      # Ruling A: the denominator is the host's cpu count
    eff = cpu_s / span if span > 0 else None
    util = eff / ncpu if eff is not None else None
    bwalls: List[float] = []
    if k:
        by_b: Dict[int, List[Dict[str, Any]]] = {}
        for r in recs:
            by_b.setdefault(r["batch"], []).append(r)
        bwalls = sorted((max(x["completion_ns"] for x in v) - min(x["submit_ns"] for x in v)) / 1e9
                        for v in by_b.values())
    out = {
        "arm": arm, "leg": leg, "k": k, "reference_c": conc,
        "verdict": "OK" if len(recs) == len(measured) and not hard else "DEGRADED",
        "submission_shape": (f"{'send_files' if arm == 'rr' else 'K concurrent POST /process_pdf'}"
                             f", K={k}, one batch in flight, barrier between batches" if k else
                             f"{'send' if arm == 'rr' else 'POST /process_pdf'} per document, "
                             f"C={conc} in flight, no barrier (the banked blast shape)"),
        "documents": {"submitted": len(measured), "recorded": len(recs), "ok": len(ok),
                      "empty": len(empties), "hard_failures": len(hard),
                      "hard_failure_reasons": sorted({str(r.get('reason')) for r in hard})},
        "throughput": {"span_s": round(span, 3),
                       "docs_per_s": round(len(ok) / span, 4) if span > 0 else None,
                       "chunks": chunks,
                       "chunks_per_s": round(chunks / span, 4) if span > 0 else None,
                       "basis": "MEASURED — first submit to last return, one clock"},
        "batches": ({"n": len(bwalls), "wall_s_min": round(bwalls[0], 3),
                     "wall_s_p50": round(bwalls[len(bwalls) // 2], 3),
                     "wall_s_max": round(bwalls[-1], 3)} if bwalls else None),
        # THREE SOURCES, never merged (Ruling A). Their gaps are the finding: host minus engine
        # minus driver is work neither owns — docker-proxy, kernel threads, the sampler itself.
        "cost": {"cpu_s": round(cpu_s, 3), "effective_cores": round(eff, 3) if eff else None,
                 "cpu_utilization": round(util, 4) if util is not None else None,
                 "cpu_utilization_valid": (util is not None and util <= 1.0),
                 "cpu_s_per_doc": round(cpu_s / len(ok), 4) if ok else None,
                 "available_cpus": ncpu,
                 "available_cpus_source": f"host nproc (Ruling A); arm cgroup reports "
                                          f"{facts['cpuset_effective']['raw']!r} via "
                                          f"{facts['cpuset_effective']['source']}",
                 "engine_container_cpu_s": round(cpu_s, 3),
                 "engine_container_cores": round(eff, 3) if eff else None,
                 "driver_cpu_s": round(driver_s, 3),
                 "driver_cores": round(driver_s / span, 3) if span > 0 else None,
                 "host_total_cpu_s": round(host_s, 3) if host_s is not None else None,
                 "host_total_cores": pc.get("mean_busy_cores"),
                 "unattributed_cores": (round(pc["mean_busy_cores"] - eff - driver_s / span, 3)
                                        if host_s is not None and eff is not None and span > 0
                                        else None),
                 "idle_spin_measured": state.get("idle_spin"),
                 "engine_cores_net_of_idle_spin": (round(eff - spin, 3)
                                                   if eff is not None and spin is not None
                                                   else None),
                 "idle_core_equivalents_arm": round(ncpu - eff, 3) if eff is not None else None,
                 "basis": "engine: arm cgroup cpu.stat at the leg's t0/t1; driver: getrusage "
                          "self+children over the same window; host: per-core /proc/stat"},
        # Idle capacity two ways. RAW is what the cores did. NET-OF-SPIN adds back the engine's
        # measured do-nothing burn, because a core spinning on an idle pipeline is not capacity
        # the workload used — it is capacity the posture consumed before a document arrived.
        "percore_host": {**pc,
                         "idle_core_equivalents_net_of_spin": (
                             round(pc["idle_core_equivalents"] + spin, 3)
                             if pc.get("idle_core_equivalents") is not None and spin is not None
                             else None),
                         "idle_spin_cores_subtracted": spin,
                         "net_of_spin_basis": "raw idle + measured idle spin: the spin is busy "
                                              "CPU doing no work, so it is unused capacity"},
        "box_hygiene": hygiene,
        "page_cache": state["caches"],
        "prewarm": state["prewarm"],
        "warm_up": {"docs": len(warm), "seconds": state.get("warm_s"),
                    "disjoint_from_measured": True, "same_shape_as_leg": True},
        "quiet_box_before": pre,
        "window": {"t0_ns": state["t0_ns"], "t1_ns": state["t1_ns"]},
        "leaked_task": leaked,
    }
    t = out["throughput"]
    say(f"  docs/s={t['docs_per_s']}  ok={len(ok)}/{len(measured)} (empty {len(empties)}, hard "
        f"{len(hard)})  span={t['span_s']}s  eff_cores={out['cost']['effective_cores']}  "
        f"util={out['cost']['cpu_utilization']} of {ncpu}  engine/driver/host cores="
        f"{out['cost']['engine_container_cores']}/{out['cost']['driver_cores']}/"
        f"{out['cost']['host_total_cores']}  spin={spin}  idle: count "
        f"{pc.get('idle_core_count_mean')} / equiv {pc.get('idle_core_equivalents')} "
        f"(net of spin {out['percore_host']['idle_core_equivalents_net_of_spin']})")
    (run_dir / f"leg_{arm}_{leg}.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=("rr", "li"))
    ap.add_argument("--slice", required=True, type=Path)
    ap.add_argument("--k", required=True, help="comma list, e.g. 1,8,16,32,64,128; '' for none")
    ap.add_argument("--reference-c", type=int, default=None,
                    help="one continuous-submission reference leg at this C")
    ap.add_argument("--continuous", default="",
                    help="comma list of C for a continuous-submission sweep (G3a), e.g. 4,8,16,32,64")
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--corpus-dir", type=Path,
                    default=Path(os.environ.get("BSZ_CORPUS_DIR",
                                                ROOT / "corpus" / "govdocs1" / "pdfs")))
    ap.add_argument("--rr-threads", default="unset",
                    help="'unset' (out of the box: threads= not passed) or an int")
    ap.add_argument("--thread-env", default="1",
                    help="declared container thread posture, read back: an int, or 'unset'")
    ap.add_argument("--label", default="", help="suffix for leg names, e.g. 'rev' for a replicate")
    ap.add_argument("--allow-noisy-box", action="store_true")
    a = ap.parse_args()

    say(f"exp_batchsize_sweep.py sha256: {self_sha()}")
    threads = None if a.rr_threads == "unset" else int(a.rr_threads)
    ks = [int(x) for x in a.k.split(",") if x.strip()]
    cs = [int(x) for x in a.continuous.split(",") if x.strip()]
    a.run_dir.mkdir(parents=True, exist_ok=True)

    facts = container_facts(a.arm, None if a.thread_env == "unset" else a.thread_env)
    facts["ready"] = service_ready(a.arm)
    other = "li" if a.arm == "rr" else "rr"
    o = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER[other]],
                       capture_output=True, text=True)
    facts["other_arm_running"] = o.stdout.strip() == "true"
    if facts["other_arm_running"]:
        raise SystemExit(f"REFUSED: the other arm's container '{CONTAINER[other]}' is running — "
                         "its idle spin would be charged to this arm's cores")
    say(f"  posture read-back: image {facts['image_id'][:19]}…  cpuset "
        f"{facts['cpuset_effective']['raw']} of {facts['host_nproc']} host cpus (Ruling A: "
        f"unconstrained)  cpu.max={facts.get('cpu_max')}  declared thread env "
        f"{facts['thread_env_expected']}  threads_requested="
        f"{'NOT PASSED' if threads is None else threads}")
    # G2: the DECLARED posture above is the container's; this is the one the work actually ran in.
    facts["in_process_readback"] = (asyncio.run(rr_inprocess_readback(threads)) if a.arm == "rr"
                                    else li_inprocess_readback())
    ipr = facts["in_process_readback"]
    say(f"  in-process read-back: torch intra-op="
        f"{ipr.get('torch_num_threads', ipr.get('health_torch_threads'))}  six vars="
        f"{ipr.get('env', ipr.get('health_thread_env'))}"
        + (f"  workers read={ipr.get('n_worker_processes_read')} agree="
           f"{ipr.get('all_workers_agree')}" if a.arm == "li" else ""))

    sl, measured, warm = load_slice(a.slice, a.corpus_dir)
    say(f"  slice {sl['slice_sha256'][:16]}  n={len(measured)}  warm={len(warm)}  manifest-verified")

    sfx = f"_{a.label}" if a.label else ""
    legs = [run_leg(a.arm, f"k{k}{sfx}", k, None, measured, warm, a.run_dir, facts, threads,
                    a.allow_noisy_box) for k in ks]
    for c in ([a.reference_c] if a.reference_c else []) + cs:
        legs.append(run_leg(a.arm, f"refc{c}{sfx}", None, c, measured,
                            warm, a.run_dir, facts, threads, a.allow_noisy_box))

    ranked = sorted((g for g in legs if g.get("verdict") == "OK" and g.get("k")),
                    key=lambda g: g["throughput"]["docs_per_s"] or 0, reverse=True)
    out = {
        "experiment": "batchsize_sweep_docs", "arm": a.arm, "label": a.label or None,
        "script_sha256": self_sha(),
        "posture": {**facts,
                    "rr_tokens": 1 if a.arm == "rr" else None,
                    "rr_threads_requested": ("NOT PASSED (out of the box)" if threads is None
                                             else threads) if a.arm == "rr" else None,
                    "rr_threads_observed": None},
        "slice": {k: sl[k] for k in sl if k not in ("measured", "warm_docs")},
        "k_grid": ks, "reference_c": a.reference_c, "continuous_grid": cs,
        "rulings": {"A": "unconstrained on every vCPU; denominator = host nproc; engine, driver "
                         "and host CPU reported separately; idle spin measured in this posture",
                    "C": "one workload on the box; each leg records containers, strays and the "
                         "host idle baseline it assumed"},
        "legs": legs,
        "best_k_by_docs_per_s": ranked[0]["k"] if ranked else None,
        "ranking": [{"k": g["k"], "docs_per_s": g["throughput"]["docs_per_s"]} for g in ranked],
        "not_swept": {
            "embedding_batch": ("SOURCE READING, not measured: engine embedding_transformer buffers "
                                "maxDocuments=64 and calls encode() at the sentence-transformers "
                                "default; the LlamaIndex service never sets embed_batch_size "
                                "(LlamaIndex default 10). Neither is reachable without changing "
                                "an arm, so neither was swept."),
        },
        "scope_note": ("A smoke-sized slice ranks K; its absolute docs/s must not sit in a table "
                       "beside a 10k figure (DOCS_HANDOFF §3.4: wave count biases short runs)."
                       if len(measured) < 5000 else None),
        "run_dir": str(a.run_dir),
    }
    p = write_result(f"exp_batchsize_sweep_{a.arm}", out)
    say(f"\nRANKING ({a.arm}): " + "  ".join(f"K={r['k']}:{r['docs_per_s']}" for r in out["ranking"]))
    say(f"export: {p}")
    bad = [g for g in legs if g.get("verdict") != "OK"]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
