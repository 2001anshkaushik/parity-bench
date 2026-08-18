#!/usr/bin/env python3
"""RocketRide BATCHED arm — one send_files() carrying the whole corpus.

THE THIRD RESULT, not a replacement. Three RocketRide numbers on one box, one harness, one
corpus, so the batch scheduler is isolated as the only variable:

    per-document blast at C=32   (smoke50_parser_in.py, SMOKE_LEGS=blast)
    batched send_files           (this script)
    per-document sequential      (smoke50_parser_in.py, SMOKE_LEGS=sequential)

WHY THE PAIR MATTERS. Shashi measured batched RocketRide on 10k unique GovDocs at 60.1 chunks/s
and 52.9% CPU against Haystack's 124.7 and 72.3%, and root-caused it as STARVATION rather than
slowness: cpu_s per chunk was flat across corpora (0.285 -> 0.281), so the engine was not working
harder per unit of output, it was idle. Head-of-line blocking inside the atomic batch is the
hypothesis. Our per-document arm on the same corpus family reaches 3.993 docs/s at 72.6%
utilisation — the same engine, the same box, a different submission shape. Running both is the
controlled version of his open item #2, and nobody has run it.

WHAT THIS ARM CAN AND CANNOT MEASURE, stated before any number is produced:

  CAN   batch wall time, chunks, chunk hashes, per-document identity, cpu_s over the span,
        achieved parallelism, and the engine's own per-file upload_time
  CANNOT per-document submit or completion instants. `send_files` returns the WHOLE batch at
        once, so there is exactly one submit and one return. Every per-document time here is
        DERIVED from the engine's self-reported upload_time and is labelled as such. Shashi's
        rule (rr_app.py:181-188): "send_files returns the WHOLE batch atomically; first
        observable result IS the batch completion."

ATTRIBUTION IS BY BASENAME, never by list position — Leela rr_driver.py:91-93: "position-based
zip silently mis-credits work if the engine reorders. A file with no matching response is
recorded as a failure, never dropped."
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import experiment_common as ec              # noqa: E402
from harness import gates_shared as gs                   # noqa: E402
from harness import metrics_shared as ms                 # noqa: E402
from harness.collector_proc import ProcessCollector      # noqa: E402
from harness.jsonl_stream import JsonlWriter             # noqa: E402
from harness.resultio import write_result                # noqa: E402
from harness.rr_credentials import RR_TTL_S              # noqa: E402

N = int(os.environ.get("SMOKE_N", "10000"))
WARM_DOCS = int(os.environ.get("SMOKE_WARM_DOCS", "25"))
BATCH_TIMEOUT_S = int(os.environ.get("SMOKE_BATCH_TIMEOUT_S", "36000"))
say = ec.say


def documents_from(result):
    """Unwrap the engine's nested response shapes — Leela rr_driver.py:46-65, adopted verbatim.
    Do not simplify without re-checking a raw capture; the nesting varies by node."""
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
        out = []
        for item in result:
            out.extend(documents_from(item))
        return out
    return []


def records_from_batch(corpus: List[Path], out, t0_ns: int) -> List[Dict[str, Any]]:
    """Per-document records from ONE batched response.

    submit_ns is the batch open instant — TRUE for every file, since every file was submitted
    then. completion_ns is t0 + the engine's own upload_time. Both carry `timing_source` so a
    derived value can never be mistaken for a measured one downstream.
    """
    items = out if isinstance(out, list) else [out]
    by_name: Dict[str, Any] = {}
    for it in items:
        if isinstance(it, dict):
            fp = it.get("filepath")
            if isinstance(fp, str) and fp:
                by_name.setdefault(Path(fp).name, it)

    recs = []
    for pdf in corpus:
        blob = pdf.read_bytes()
        rec: Dict[str, Any] = {
            "doc": pdf.name,
            "input_sha256": hashlib.sha256(blob).hexdigest(),
            "size_bytes": len(blob),
            "submit_ns": t0_ns,
            "timing_source": "batch upload_time (DERIVED, not measured)",
        }
        it = by_name.get(pdf.name)
        if it is None:
            # No response for a submitted file is a FAILURE, never a dropped row.
            rec.update(completion_ns=t0_ns, ok=False, reason="no_response_for_file",
                       n_chunks=0, chunk_sha256=[])
            recs.append(rec)
            continue
        ut = it.get("upload_time")
        rec["upload_time_s"] = ut if isinstance(ut, (int, float)) else None
        rec["completion_ns"] = (t0_ns + int(float(ut) * 1e9)
                                if isinstance(ut, (int, float)) else t0_ns)
        docs = documents_from(it)
        texts = [d.get("page_content", "") for d in docs]
        vecs = [d.get("embedding") or [] for d in docs]
        rec["n_chunks"] = len(docs)
        rec["total_chars"] = sum(len(t) for t in texts)
        rec["chunk_sha256"] = [gs.chunk_hash(t) for t in texts]
        rec["vector_dim"] = len(vecs[0]) if vecs and vecs[0] else None
        rec["ok"] = bool(docs)
        rec["reason"] = "completed" if docs else "no_documents"
        recs.append(rec)
    return recs


async def run(corpus: List[Path], warm: List[Path], pipe_path: Path) -> Dict[str, Any]:
    from rocketride import RocketRideClient

    c = RocketRideClient()
    await c.connect(timeout=60000)
    tok = (await c.use(filepath=str(pipe_path.relative_to(ROOT)), ttl=RR_TTL_S))["token"]
    say(f"  pipeline up, ttl={RR_TTL_S}s")

    # Driver-side warm-up on DISJOINT documents, outside every measured window (Leela WARM=25,
    # rr_driver.py:244 `all_pdfs[n:n + warm_docs]`).
    warm_s = None
    if warm:
        tw = time.perf_counter()
        await asyncio.wait_for(c.send_files([str(p) for p in warm], tok), timeout=BATCH_TIMEOUT_S)
        warm_s = round(time.perf_counter() - tw, 2)
        say(f"  warm-up: {len(warm)} disjoint documents in {warm_s}s (excluded)")

    say(f"  measured batch: ONE send_files carrying {len(corpus)} documents ...")
    t0_ns = time.time_ns()
    t0 = time.perf_counter()
    batch = await asyncio.wait_for(
        c.send_files([str(p) for p in corpus], tok), timeout=BATCH_TIMEOUT_S)
    wall_s = time.perf_counter() - t0
    t1_ns = time.time_ns()
    try:
        await asyncio.wait_for(c.terminate(tok), timeout=60)
    except Exception:
        pass
    await c.disconnect()
    returned = len(batch) if isinstance(batch, list) else 1
    say(f"  batch returned {returned} items for {len(corpus)} files in {wall_s:.1f}s")
    return {"batch": batch, "wall_s": wall_s, "t0_ns": t0_ns, "t1_ns": t1_ns,
            "warm_s": warm_s, "returned": returned}


def main() -> int:
    allp = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob(ec.CORPUS_GLOB))
    corpus, warm = allp[:N], allp[N:N + WARM_DOCS]
    if len(corpus) < N:
        say(f"BLOCKER: need {N} documents matching {ec.CORPUS_GLOB}, found {len(corpus)}")
        return 2
    if WARM_DOCS and len(warm) < WARM_DOCS:
        say(f"BLOCKER: only {len(allp)} documents for N={N}+warm={WARM_DOCS}; warm-up would "
            "REUSE measured documents. Refusing — that is the flaw in the other warm-up policy.")
        return 7

    run_dir = Path(os.environ.get("SMOKE_RUN_DIR",
                                  ROOT / "working" / "results" /
                                  f"batched_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"))
    run_dir.mkdir(parents=True, exist_ok=True)
    say(f"BATCHED BLAST — {len(corpus)} documents, one send_files, warm={len(warm)} disjoint")
    say(f"  corpus sha256 = {ec.corpus_sha(corpus)[:16]}  run_dir={run_dir}")

    pipe = json.loads((ROOT / "working" / "pipes" / ec.PIPE).read_text())
    pipe["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"batched-{os.getpid()}-{time.time()}"))
    pp = ROOT / "working" / "pipes" / "generated" / f"batched_{os.getpid()}.pipe"
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(pipe))

    pid = ec._container_root_pid(ec.RR_CONTAINER) if ec.EXTERNAL else None
    pc = None
    if pid:
        pc = ProcessCollector(run_dir / "sampler_rr_batched.jsonl", {"service": {"pids": [pid]}},
                              interval_s=0.5, want_uss=True)
        pc.start()
        say(f"  cost sampler on container pid {pid}")
    else:
        say("  !! no container pid — cost UNAVAILABLE, never 0")
    anchor = time.time()

    try:
        r = asyncio.run(run(corpus, warm, pp))
    finally:
        if pc:
            pc.stop()

    recs = records_from_batch(corpus, r["batch"], r["t0_ns"])
    with JsonlWriter(run_dir / "perdoc_rr_batched.jsonl") as w:
        for rec in recs:
            w.write(rec)

    ok = [x for x in recs if x.get("ok")]
    chunks = sum(x["n_chunks"] for x in ok)
    wall = r["wall_s"]
    # ACHIEVED PARALLELISM, two independent readings. `engine_side_concurrency` is the engine's
    # OWN account of how much work overlapped: if the batch were fully serialised it lands at
    # ~1.0, and that IS head-of-line blocking. `effective_cores` is what the CPU sampler saw.
    # Two sources with different failure modes, deliberately not merged.
    ut = [x["upload_time_s"] for x in ok if x.get("upload_time_s")]
    cost = ms.cost_window(
        ms.series_from_role_ticks((run_dir / "sampler_rr_batched.jsonl").read_text(),
                                  "service", anchor) if pc else None,
        r["t0_ns"] / 1e9, r["t1_ns"] / 1e9)

    out: Dict[str, Any] = {
        "experiment": "batched_blast",
        "arm": "rocketride_batched",
        "method_source": ("send_files whole-corpus batch (Shashi rr_app.py:179, Leela "
                          "rr_driver.py:331); basename attribution Leela rr_driver.py:91-93; "
                          "basis-field pattern Shashi rr_app.py:181-188"),
        "submission_shape": {
            "calls": 1, "documents": len(corpus),
            "client_concurrency": None,
            "client_concurrency_note": (
                "send_files(files, token) takes no concurrency argument — the SDK docstring says "
                "'Server handles queuing automatically'. C is not a client variable on this arm; "
                "the engine's pool decides and is not observable from here."),
        },
        "corpus": {"source": "govdocs1", "glob": ec.CORPUS_GLOB, "n": len(corpus),
                   "sha256": ec.corpus_sha(corpus),
                   "first": corpus[0].name, "last": corpus[-1].name},
        "warm_up": {"docs": len(warm), "seconds": r["warm_s"], "disjoint_from_measured": True,
                    "policy": "driver-side, 25 disjoint, excluded (Leela WARM=25)"},
        "throughput": {
            "wall_s": round(wall, 3),
            "documents_ok": len(ok), "documents_total": len(recs),
            "chunks": chunks,
            "docs_per_s": round(len(ok) / wall, 4) if wall > 0 else None,
            "chunks_per_s": round(chunks / wall, 4) if wall > 0 else None,
            "basis": "MEASURED — one call, one return, wall clock around it",
        },
        "time_to_first_result": gs.derived(
            round(wall, 3),
            basis=("batch websocket API — send_files returns all documents at once, so the "
                   "first observable result IS the batch completion (Shashi rr_app.py:186-188)"),
            measured=False),
        "latency_per_document": gs.derived(
            None,
            basis=("NOT AVAILABLE. One submit, one return: per-document instants do not exist. "
                   "upload_time is recorded per document and is the engine's own account, not a "
                   "client observation — see perdoc_rr_batched.jsonl timing_source."),
            measured=False),
        "achieved_parallelism": {
            "engine_side_concurrency": gs.derived(
                round(sum(ut) / wall, 3) if ut and wall > 0 else None,
                basis=("sum(engine upload_time) / batch wall. ~1.0 means the batch was processed "
                       "essentially one document at a time — head-of-line blocking. Derived from "
                       "the engine's own per-file timings, so it inherits their accuracy."),
                measured=False),
            "effective_cores": cost and ms.effective_cores(cost["cpu_s"], cost["window_s"]),
            "cpu_s": cost and cost["cpu_s"],
            "cpu_s_per_chunk": (ms.cpu_s_per_chunk(cost["cpu_s"], chunks) if cost else None),
            "cpu_utilization": (ms.cpu_utilization(
                cost["cpu_s"], cost["window_s"],
                len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
                else os.cpu_count()) if cost else None),
            "cost_note": None if cost else "no cost samples resolved to this window",
        },
        "attribution": {
            "method": "filepath basename (Leela rr_driver.py:91-93), never list position",
            "returned_items": r["returned"],
            "attributed": sum(1 for x in recs if x.get("reason") != "no_response_for_file"),
            "unattributed": [x["doc"] for x in recs
                             if x.get("reason") == "no_response_for_file"][:20],
        },
        "gates": {
            "self_duplication": gs.self_duplication(recs),
            "census": gs.leela_census(recs, len(corpus)),
        },
        "provenance": ec.provenance(),
    }
    tp = out["throughput"]
    say(f"\n  docs/s={tp['docs_per_s']}  chunks/s={tp['chunks_per_s']}  "
        f"ok={tp['documents_ok']}/{tp['documents_total']}")
    ap = out["achieved_parallelism"]
    say(f"  engine_side_concurrency={ap['engine_side_concurrency']['value']}  "
        f"effective_cores={ap['effective_cores']}  util={ap['cpu_utilization']}")
    sd = out["gates"]["self_duplication"]
    say(f"  self_duplication: {sd['duplicated_docs']}/{sd['checked']} duplicated "
        f"factors={sd['factors']}")
    if out["attribution"]["unattributed"]:
        say(f"  !! {len(out['attribution']['unattributed'])} submitted files got NO response")

    fails = []
    if not sd["PASS"]:
        fails.append(f"self_duplication: {sd['duplicated_docs']} documents duplicated")
    if out["attribution"]["unattributed"]:
        fails.append(f"{len(out['attribution']['unattributed'])} files unattributed")
    if not out["gates"]["census"].get("PASS", True):
        fails.append("census failed")
    out["PASS"] = not fails
    out["failed_checks"] = fails
    return ec.verdict_exit(not fails, write_result("exp_batched_blast", out), fails)


if __name__ == "__main__":
    raise SystemExit(main())
