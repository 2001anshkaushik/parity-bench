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
    if not cs.get("cpus"):
        problems.append(f"no effective cpuset readable: {cs.get('source')}")
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
    cpus = cpus_from_spec(facts["cpuset_effective"]["raw"])
    say(f"\n=== {arm} {leg} — {len(measured)} documents, warm {len(warm)} ===")
    shape = (lambda docs: batches(docs, k)) if k else None

    pre = quiet_box(cg)
    say(f"  quiet box: host busy {pre['host_busy_cores']}  arm idle {pre['arm_idle_cores']}  "
        f"foreign {pre['foreign_busy_cores']} (max {QUIET_MAX_FOREIGN})  load1 {pre['load1']:.2f}")
    if not pre["quiet"] and not allow_noisy:
        return {"arm": arm, "leg": leg, "k": k, "reference_c": conc, "verdict": "REFUSED",
                "reason": "box not quiet", "quiet_box": pre}

    perdoc = run_dir / f"perdoc_{arm}_{leg}.jsonl"
    percore = run_dir / f"percore_{arm}_{leg}.jsonl"
    if perdoc.exists() or percore.exists():
        raise SystemExit(f"REFUSED: {perdoc.name} exists — results are append-only")

    leaked = None
    state: Dict[str, Any] = {}

    def open_window() -> None:
        state["sampler"] = PerCoreSampler(cpus, interval_s=1.0, out_path=percore)
        state["sampler"].start()
        state["u0"], state["t0_ns"], state["p0"] = (cgroup_usage_usec(cg), time.time_ns(),
                                                    time.perf_counter())

    def close_window() -> None:
        state["p1"], state["t1_ns"], state["u1"] = (time.perf_counter(), time.time_ns(),
                                                    cgroup_usage_usec(cg))
        state["percore"] = state["sampler"].stop()

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
        with JsonlWriter(perdoc) as w:
            open_window()
            recs = (li_send_batches(shape(measured), k, w) if k
                    else li_send_continuous(measured, conc, w))
            close_window()

    span = state["p1"] - state["p0"]
    cpu_s = (state["u1"] - state["u0"]) / 1e6
    ok = [r for r in recs if r.get("ok")]
    empties = [r["doc"] for r in recs if r.get("reason") == "no_documents"]
    # A document the arm's own parser cannot read is a CONTENT outcome — deterministic, the same
    # at every K, already in the corpus manifest (parse_error) — not a degraded leg. Hard means
    # the work was LOST: transport errors, timeouts, a file with no response. (First pass labelled
    # every LlamaIndex leg DEGRADED over one PdfReadError document that pypdf never could read.)
    hard = [r for r in recs if not r.get("ok") and r.get("reason") not in DOCUMENT_OUTCOMES]
    chunks = sum(r["n_chunks"] for r in ok)
    ncpu = len(cpus)
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
        "cost": {"cpu_s": round(cpu_s, 3), "effective_cores": round(eff, 3) if eff else None,
                 "cpu_utilization": round(util, 4) if util is not None else None,
                 "cpu_utilization_valid": (util is not None and util <= 1.0),
                 "cpu_s_per_doc": round(cpu_s / len(ok), 4) if ok else None,
                 "available_cpus": ncpu, "available_cpus_source": facts["cpuset_effective"]["source"],
                 "idle_core_equivalents_arm": round(ncpu - eff, 3) if eff is not None else None,
                 "basis": "arm container cgroup cpu.stat usage_usec, read at the leg's t0 and t1"},
        "percore_host": state["percore"],
        "warm_up": {"docs": len(warm), "seconds": state.get("warm_s"),
                    "disjoint_from_measured": True, "same_shape_as_leg": True},
        "quiet_box_before": pre,
        "window": {"t0_ns": state["t0_ns"], "t1_ns": state["t1_ns"]},
        "leaked_task": leaked,
    }
    t = out["throughput"]
    say(f"  docs/s={t['docs_per_s']}  ok={len(ok)}/{len(measured)} (empty {len(empties)}, hard "
        f"{len(hard)})  span={t['span_s']}s  eff_cores={out['cost']['effective_cores']}  "
        f"util={out['cost']['cpu_utilization']}  idle cores: mean count "
        f"{state['percore'].get('idle_core_count_mean')} / equivalents "
        f"{state['percore'].get('idle_core_equivalents')} of {ncpu}")
    (run_dir / f"leg_{arm}_{leg}.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=("rr", "li"))
    ap.add_argument("--slice", required=True, type=Path)
    ap.add_argument("--k", required=True, help="comma list, e.g. 1,8,16,32,64,128; '' for none")
    ap.add_argument("--reference-c", type=int, default=None)
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
        f"{facts['cpuset_effective']['raw']}  thread env {facts['thread_env_expected']}  "
        f"threads_requested={'NOT PASSED' if threads is None else threads}")

    sl, measured, warm = load_slice(a.slice, a.corpus_dir)
    say(f"  slice {sl['slice_sha256'][:16]}  n={len(measured)}  warm={len(warm)}  manifest-verified")

    sfx = f"_{a.label}" if a.label else ""
    legs = [run_leg(a.arm, f"k{k}{sfx}", k, None, measured, warm, a.run_dir, facts, threads,
                    a.allow_noisy_box) for k in ks]
    if a.reference_c:
        legs.append(run_leg(a.arm, f"refc{a.reference_c}{sfx}", None, a.reference_c, measured,
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
        "k_grid": ks, "reference_c": a.reference_c,
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
