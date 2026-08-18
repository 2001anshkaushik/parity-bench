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
# THREADS. On a batched call the engine's own pool is the ONLY source of parallelism — the client
# sends one message and waits — so leaving `threads` unset does not measure a default, it measures
# an UNSET PARAMETER, and any low concurrency would then be reported as head-of-line blocking when
# it was our omission. Leela measured ~5.8 effective cores with no threads= against the comparable
# Haystack-suite run's 24.28 WITH it; Shashi passes RR_THREADS=32 (bench.py:47).
# 24 = our cpuset width (0-23). One engine worker per reachable core.
#
# REQUESTED IS NOT ACTIVATED. `use(threads=)` is a request; the engine's realised pool size is not
# observable from the client (Leela records threads_observed: null for exactly this reason). The
# number below is what we ASKED FOR and is recorded as such.
RR_THREADS = int(os.environ.get("SMOKE_RR_THREADS", "24"))
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
            "timing_source": ("batch upload_time (DERIVED, not measured; semantics "
                              "classified post-hoc — see result upload_time_semantics)"),
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


def classify_upload_time(values, wall_s: float, threads: int) -> Dict[str, Any]:
    """What IS upload_time — a per-file duration, or a completion offset from batch open?

    Defect #35, found on the N=1000 probe: engine_side_concurrency printed 281.266, which is
    impossible (it cannot exceed threads_requested=24). The formula sum(upload_time)/wall
    assumed upload_time is a per-file BUSY DURATION. Leela's own records_from_batch derives
    completion_ns = t0 + upload_time — i.e. he treats it as an OFFSET from batch open — and
    the SDK's send_files docstring prints it as seconds ("in {upload_time:.2f}s", data.py).
    For n files completing across a wall of W, sum(offsets)/W lands near n/2, and 281 on 988
    completions is exactly that shape. Sum-over-wall on offsets is a category error, not a
    unit error.

    So classify from the numbers themselves, and let every downstream label follow:
      duration hypothesis  needs max <= wall and sum <= threads*wall  (a file cannot run
                           longer than the batch; total busy cannot exceed the pool)
      offset hypothesis    needs max ~= wall  (the last completion IS the batch return)
    Seconds are tried first — the SDK documents seconds — and milliseconds only if seconds
    fits neither, flagged as contradicting the docstring. Ambiguous or unclassifiable means
    every derived value ships as None with this dict as the reason. Never publish a number
    whose meaning failed classification.
    """
    v = [x for x in (values or []) if isinstance(x, (int, float)) and x >= 0]
    if not v:
        return {"semantics": "unclassifiable", "scale": None,
                "reason": "no upload_time values on any record"}
    out = {"n": len(v)}
    for scale, sname in ((1.0, "seconds (SDK data.py docstring: '{upload_time:.2f}s')"),
                         (1e-3, "milliseconds — CONTRADICTS the SDK docstring, flagged")):
        u = [x * scale for x in v]
        mx, sm = max(u), sum(u)
        duration_ok = mx <= wall_s * 1.10 and sm <= threads * wall_s * 1.10
        offset_ok = wall_s * 0.50 <= mx <= wall_s * 1.10
        ev = {"scale_tried": sname, "max_s": round(mx, 3), "sum_s": round(sm, 1),
              "wall_s": round(wall_s, 1), "sum_over_wall": round(sm / wall_s, 3),
              "max_over_wall": round(mx / wall_s, 3), "threads": threads}
        if duration_ok and not offset_ok:
            return {**out, "semantics": "duration", "scale": scale, "evidence": ev,
                    "reason": f"fits duration only at {sname}"}
        if offset_ok and not duration_ok:
            return {**out, "semantics": "offset", "scale": scale, "evidence": ev,
                    "reason": f"fits offset only at {sname}: max ~= wall (last completion is "
                              "the batch return) while sum exceeds the pool ceiling"}
        if offset_ok and duration_ok:
            return {**out, "semantics": "ambiguous", "scale": scale, "evidence": ev,
                    "reason": f"BOTH hypotheses fit at {sname}; refusing to pick. No derived "
                              "value is published from an ambiguous basis."}
        out[f"rejected_at_{'s' if scale == 1.0 else 'ms'}"] = ev
    return {**out, "semantics": "unclassifiable", "scale": None,
            "reason": "fits neither hypothesis at either scale; see rejected evidence"}


def _upload_time_percentiles(ok_rows) -> Dict[str, Any]:
    """Percentiles over the engine's per-file upload_time. Nearest-rank, the settled method
    (metrics_shared.percentile, Shashi metrics.py:84-93) — same estimator as every other
    percentile we publish, so the only difference from our measured column is the SOURCE."""
    v = [r["upload_time_s"] for r in ok_rows if isinstance(r.get("upload_time_s"), (int, float))]
    if not v:
        return {"n": 0, "note": "no upload_time on any record"}
    out = {"n": len(v), "sum_s": round(sum(v), 3)}
    for q in (50, 90, 95, 99):
        out[f"p{q}"] = round(ms.percentile(v, q), 4)
    out["max"] = round(max(v), 4)
    out["mean"] = round(sum(v) / len(v), 4)
    return out


async def run(corpus: List[Path], warm: List[Path], pipe_path: Path) -> Dict[str, Any]:
    from rocketride import RocketRideClient

    c = RocketRideClient()
    await c.connect(timeout=60000)
    used = await c.use(filepath=str(pipe_path.relative_to(ROOT)), ttl=RR_TTL_S,
                       threads=RR_THREADS)
    tok = used["token"]
    say(f"  pipeline up, ttl={RR_TTL_S}s, threads_requested={RR_THREADS}")

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
    # Defect #34: this denominator used the DRIVER's sched_getaffinity — 8 cpus under
    # `taskset -c 24-31` — while the service ran on cpuset 0-23 (24). util printed 1.58
    # INVALID for a true 52.8%. The denominator now comes from the service container's own
    # cgroup, with the source recorded beside every number it divides.
    svc_cpus, svc_cpus_src = (ec.service_available_cpus(ec.RR_CONTAINER) if ec.EXTERNAL
                              else (len(os.sched_getaffinity(0))
                                    if hasattr(os, "sched_getaffinity") else os.cpu_count(),
                                    "driver affinity (native mode: service is a child of "
                                    "the driver and shares it)"))
    say(f"  available_cpus={svc_cpus}  source: {svc_cpus_src}")
    uts = classify_upload_time(ut, wall, RR_THREADS)
    say(f"  upload_time semantics: {uts['semantics']} — {uts['reason']}")
    cost = ms.cost_window(
        ms.series_from_role_ticks((run_dir / "sampler_rr_batched.jsonl").read_text(),
                                  "service", anchor) if pc else None,
        r["t0_ns"] / 1e9, r["t1_ns"] / 1e9)

    # CENSUS_EMPTY_POLICY (Shashi bench.py:412-435, adopted for GovDocs): on a real-world
    # corpus a fraction of documents genuinely defeats an extractor. Under "report", a
    # success-shaped empty (`no_documents`) is NAMED, COUNTED and EXPORTED rather than
    # aborting the run — the head-to-head then rests on the mutually-extracted subset. Hard
    # loss (no response for a submitted file, transport errors) always fails regardless of
    # policy: "LOST work always fails" is his rule and stays ours. Each empty document is
    # cross-referenced against the manifest's pypdf extraction so "defeats both parsers" and
    # "Tika-side disagreement" are distinguishable without a re-run.
    empty_docs = sorted(x["doc"] for x in recs
                        if not x.get("ok") and x.get("reason") == "no_documents")
    policy = os.environ.get("CENSUS_EMPTY_POLICY", "report")
    pypdf_chars = {}
    mpath = ROOT / "working" / "results" / "corpus_manifest.jsonl"
    if mpath.exists():
        for line in mpath.read_text().splitlines():
            if line.strip():
                try:
                    m = json.loads(line)
                    pypdf_chars[m["file"]] = m.get("extracted_chars_pypdf")
                except (json.JSONDecodeError, KeyError):
                    continue
    empty_annotated = {
        d: ("defeats pypdf too (0 chars in manifest) — empty on both parsers"
            if pypdf_chars.get(d) == 0 else
            f"pypdf extracted {pypdf_chars[d]} chars — Tika-side extraction disagreement"
            if d in pypdf_chars else "not in manifest")
        for d in empty_docs}
    census = gs.leela_census(recs, len(corpus),
                             expected_empty=set(empty_docs) if policy == "report"
                             else frozenset())
    census_policy = {
        "policy": policy,
        "source": "Shashi bench.py:412-435 (CENSUS_EMPTY_POLICY=report for GovDocs)",
        "empty_documents": len(empty_docs),
        "empty_named": empty_annotated,
        "subset_basis": (f"throughput and gates rest on the {len(ok)}-document extracted "
                         f"subset; {len(empty_docs)} empty documents are reported, not "
                         "failures" if policy == "report" and empty_docs else None),
        "hard_loss_note": "no_response_for_file and transport errors fail REGARDLESS of "
                          "policy — lost work always fails",
    }
    if empty_docs:
        say(f"  census: {len(empty_docs)} empty document(s) under policy={policy}: "
            f"{empty_docs[:8]}{'...' if len(empty_docs) > 8 else ''}")

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
        # TWO entries, never one. The client-observed value genuinely does not exist under an
        # atomic call, and saying so is the honest answer — but Leela HAS an upload_time column,
        # and a bare null on our side leaves a hole in the three-way table. So both travel:
        # the null with its reason, and his derived figure with its basis.
        "latency_per_document": {
            "client_observed": gs.derived(
                None,
                basis=("NOT AVAILABLE. One submit, one return: per-document client instants do "
                       "not exist under a batched send."),
                measured=False),
            "upload_time_derived": gs.derived(
                _upload_time_percentiles(ok),
                basis=(("BATCH-POSITION latency: upload_time classified as a completion "
                        "OFFSET from batch open, so these percentiles INCLUDE queue wait "
                        "inside the batch. Comparable with Leela's derived column (his "
                        "completion_ns = t0 + upload_time is the same reading); NOT service "
                        "latency and NOT comparable with the per-document arm's measured "
                        "column.") if uts["semantics"] == "offset" else
                       ("engine per-file processing DURATION (classified): excludes queue "
                        "wait inside the batch and transport. Comparable with Leela's "
                        "column.") if uts["semantics"] == "duration" else
                       (f"UNINTERPRETED: upload_time semantics {uts['semantics']} — "
                        f"{uts['reason']}. Raw percentiles retained for forensics only; "
                        "do not put them in any latency table.")),
                measured=False),
        },
        "achieved_parallelism": {
            # Published ONLY when upload_time classifies as a per-file DURATION. On the
            # N=1000 probe it classifies as an OFFSET (max ~= wall), where sum/wall is a
            # category error that printed an impossible 281.266 (> threads=24). Defect #35.
            "engine_side_concurrency": gs.derived(
                (round(sum(x * uts["scale"] for x in ut) / wall, 3)
                 if uts["semantics"] == "duration" and ut and wall > 0 else None),
                basis=(f"sum(upload_time)/wall, valid ONLY under duration semantics. "
                       f"Classification: {uts['semantics']} — {uts['reason']}"),
                measured=False),
            "upload_time_semantics": uts,
            "effective_cores": cost and ms.effective_cores(cost["cpu_s"], cost["window_s"]),
            "cpu_s": cost and cost["cpu_s"],
            "cpu_s_per_chunk": (ms.cpu_s_per_chunk(cost["cpu_s"], chunks) if cost else None),
            "cpu_utilization": (ms.cpu_utilization(cost["cpu_s"], cost["window_s"], svc_cpus)
                                if cost and svc_cpus else None),
            "available_cpus": svc_cpus,
            "available_cpus_source": svc_cpus_src,
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
            "census": census,
            "census_policy": census_policy,
        },
        "provenance": ec.provenance({
            "threads_requested": RR_THREADS,
            "threads_observed": None,
            "threads_note": ("threads_requested is what use() was ASKED for; the engine's realised "
                             "pool size is not observable from the client. Requested != activated "
                             "!= effective cores — the last of those is measured from the CPU "
                             "sampler and reported under achieved_parallelism."),
            "ttl_s": RR_TTL_S,
            "warm_up_policy_open_question": (
                "OPEN FOR THE GROUP, not resolved here. Leela warms 25 documents taken from "
                "BEYOND the measured set (matched_run.sh WARM=25, rr_driver.py:244 "
                "all_pdfs[n:n+warm_docs]). Shashi warms max(4, 2*threads) for blast and 2 for "
                "sequential, on files[:warm_n] — i.e. the FIRST MEASURED DOCUMENTS, which are "
                "then measured cache-hot while their peers are cold. The policies differ in "
                "COUNT and in DISJOINTNESS. We use Leela's 25 disjoint because disjointness is a "
                "correctness property while the count is a tuning knob, but this is a divergence "
                "neither teammate has flagged and it needs a group decision."),
        }),
    }
    # PROJECTION. There are no partial records under an atomic call: a timeout costs the entire
    # run. So a short batch has to answer "can the long one finish" BEFORE the long one is
    # started. Linear scaling is the optimistic case and is labelled as such — a scheduler that
    # degrades with queue depth will do worse, never better.
    if len(corpus) < 10000:
        per_doc = wall / max(len(ok), 1)
        proj = per_doc * 10000
        out["projection_to_10k"] = gs.derived(
            round(proj, 1),
            basis=(f"linear extrapolation from n={len(corpus)} at {wall:.1f}s "
                   f"({per_doc:.3f}s/doc). OPTIMISTIC: assumes the batch scheduler does not "
                   f"degrade with queue depth. Compare against SMOKE_BATCH_TIMEOUT_S="
                   f"{BATCH_TIMEOUT_S}s."),
            measured=False)
        out["projection_to_10k"]["fits_in_timeout"] = proj < BATCH_TIMEOUT_S
        out["projection_to_10k"]["headroom_x"] = round(BATCH_TIMEOUT_S / proj, 2) if proj else None
        say(f"\n  PROJECTION to 10k: {proj / 3600:.2f} h at {per_doc:.3f}s/doc "
            f"(timeout {BATCH_TIMEOUT_S / 3600:.1f} h, "
            f"headroom {out['projection_to_10k']['headroom_x']}x) "
            f"— LINEAR, optimistic")
        if proj >= BATCH_TIMEOUT_S:
            say("  !! the 10k batch would NOT finish inside the timeout. An atomic call has no "
                "partial records, so that would cost the entire run.")

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
        c = out["gates"]["census"]
        fails.append(f"census failed BEYOND the empty policy: silent={c.get('silent')} "
                     f"duplicates={len(c.get('duplicate_docs') or [])} "
                     f"unexpected_failures={c.get('unexpected_failures')} "
                     f"(policy={policy} already excused {len(empty_docs)} empty docs)")
    out["PASS"] = not fails
    out["failed_checks"] = fails
    return ec.verdict_exit(not fails, write_result("exp_batched_blast", out), fails)


if __name__ == "__main__":
    raise SystemExit(main())
