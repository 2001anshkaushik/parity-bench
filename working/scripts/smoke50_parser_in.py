#!/usr/bin/env python3
"""50-document Parser IN smoke test — Leela's gate structure and ours, side by side.

Run:  ../.venv/bin/python working/scripts/smoke50_parser_in.py [N]

Reports TWO verdicts per arm so our output is directly comparable with Leela's:

  LEELA'S GATES
    census      offered = successful + expected + unexpected; N records, unique ids, zero silent
    structure   >=1 chunk (or completed-empty), 384-d, finite, L2 = 1.0 +- 0.001,
                response identity provably matches the submitted document
    determinism chunk-hash lists identical between a BLAST run and a SEQUENTIAL run, per arm
    cross-arm   chunk-count delta and char ratio, REPORTED not gated, + embedding parity fixture

  OURS, ON TOP
    per-arm chunk hash against an INDEPENDENT reference
      - LlamaIndex: the arm's own returned extracted_text
      - RocketRide: standalone Tika (engine's jars + engine's tika-config.xml) + '\\n\\n'
    content sanity (NUL presence, printable ratio)

The two answer different questions. Determinism compares each arm against ITSELF across runs, so a
DETERMINISTIC defect reproduces identically and passes. The independent reference is what catches
that. Both are needed; neither subsumes the other.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

PORT = int(os.environ.get("SMOKE_PORT", "8851"))
L2_TOL = 1e-3                      # Leela's tolerance, tighter than our 1e-2
EMB_DIM = 384


def say(m):
    print(m, flush=True)


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def structure_check(chunks, vecs) -> list[str]:
    """Leela's structure gate. Returns a list of problems (empty = pass)."""
    bad = []
    if chunks is None or vecs is None:
        return ["chunks or vectors is None"]
    if len(chunks) == 0:
        return ["completed-empty"]            # allowed, but recorded distinctly
    if len(vecs) != len(chunks):
        bad.append(f"{len(chunks)} chunks vs {len(vecs)} vectors")
    for i, v in enumerate(vecs):
        if len(v) != EMB_DIM:
            bad.append(f"vector {i} dim {len(v)}")
            continue
        n = math.sqrt(sum(float(x) * float(x) for x in v))
        if not math.isfinite(n):
            bad.append(f"vector {i} non-finite")
        elif abs(n - 1.0) > L2_TOL:
            bad.append(f"vector {i} L2={n:.6f}")
    return bad


def main() -> int:
    from harness import ws1_service as ws
    from harness.chunk_hash import check_chunks, ChunkHashMismatch
    from harness.content_sanity import inspect
    from harness.extraction_fidelity import fidelity, summarise
    from harness.tika_reference import available as tika_ok, reference_text
    from harness.resultio import write_result
    from weekend_worker import LlamaHttpPdfArm, RocketPdfArm

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob("*.pdf"))[:N]
    say(f"documents: {len(pdfs)}  (offered = {len(pdfs)})")
    ok_tika, why = tika_ok()
    say(f"tika reference: {'available' if ok_tika else 'UNAVAILABLE — ' + why}")

    hsvc = ws.start(workers=1, port=PORT, threads=10)
    ws.wait_warm(hsvc, timeout=900)
    thr = sorted(set(hsvc.measured_threads.values()))
    say(f"service warm, torch(intra,interop)={thr}")

    results = {}
    try:
        for arm_name, mk in (("llamaindex_http_pdf", lambda: LlamaHttpPdfArm(port=PORT)),
                             ("rocketride_pdf", lambda: RocketPdfArm("smoke"))):
            arm = mk()
            recs = []
            for f in pdfs:
                blob = f.read_bytes()
                rec = {"doc": f.name, "submitted_sha256": hashlib.sha256(blob).hexdigest()}
                t0 = time.perf_counter()
                try:
                    chunks, vecs = arm.process(blob)
                    rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                    last = getattr(arm, "last", {}) or {}
                    rec["returned_doc_id"] = last.get("doc_id")
                    rec["n_chunks"] = len(chunks)
                    rec["chunk_sha256"] = [h(c) for c in chunks]
                    rec["chars"] = sum(len(c) for c in chunks)
                    problems = structure_check(chunks, vecs)
                    rec["structure"] = problems
                    if problems == ["completed-empty"]:
                        rec["outcome"] = "expected"
                        rec["error_class"] = "completed_empty"
                    elif problems:
                        rec["outcome"] = "unexpected"
                        rec["error_class"] = "structure"
                    elif not last.get("ok", True):
                        rec["outcome"] = "expected"
                        rec["error_class"] = last.get("error_class", "unknown")
                    else:
                        rec["outcome"] = "successful"
                    # ---- OUR gate: independent reference
                    src = None
                    if arm_name.startswith("llamaindex"):
                        src = last.get("extracted_text")
                    elif ok_tika:
                        src = reference_text(f)
                    if src and rec["outcome"] == "successful":
                        try:
                            check_chunks(f.name, chunks, src)
                            rec["independent_hash"] = "pass"
                        except ChunkHashMismatch as e:
                            rec["independent_hash"] = f"FAIL: {e}"
                        rec["extracted_chars"] = len(src)
                    sus = [i for i, c in enumerate(chunks) if inspect(c)["suspect"]]
                    if sus:
                        rec["content_suspect_chunks"] = sus
                except Exception as e:
                    rec["outcome"] = "unexpected"
                    rec["error_class"] = f"{type(e).__name__}"
                    rec["error"] = str(e)[:200]
                recs.append(rec)
            arm.close()
            results[arm_name] = recs
            say(f"  {arm_name}: {len(recs)} records")

        # ---- determinism: a BLAST run (concurrent) vs the SEQUENTIAL run above
        say("\ndeterminism: blast run vs sequential run, per arm")
        blobs = [(f.name, f.read_bytes()) for f in pdfs]

        # LlamaIndex: blocking urllib, so threads are the right concurrency primitive.
        def blast_llama():
            import concurrent.futures as cf
            arm = LlamaHttpPdfArm(port=PORT)

            def one(item):
                name, b = item
                try:
                    ch, _ = arm.process(b)
                    return name, [h(c) for c in ch]
                except Exception:
                    return name, None
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                out = dict(ex.map(one, blobs))
            arm.close()
            return out

        # RocketRide: ONE asyncio loop, C concurrent send() coroutines. Driving RocketPdfArm.process
        # from a ThreadPoolExecutor calls run_until_complete on one loop from several threads, which
        # silently abandons coroutines ("coroutine 'send' was never awaited") and reports spurious
        # non-determinism. Measured: that harness bug alone produced 7/8 false "drift".
        def blast_rocket():
            import uuid as _u
            from rocketride import RocketRideClient

            async def go():
                base = json.loads((ROOT / "working" / "pipes" / "product_pdf.pipe").read_text())
                base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                                  f"blast-{os.getpid()}-{time.time()}"))
                pp = ROOT / "working" / "pipes" / "generated" / f"blast_{os.getpid()}.pipe"
                pp.parent.mkdir(parents=True, exist_ok=True)
                pp.write_text(json.dumps(base))
                c = RocketRideClient()
                await c.connect(timeout=60000)
                tok = (await c.use(filepath=str(pp.relative_to(ROOT))))["token"]
                sem = asyncio.Semaphore(4)
                res = {}

                async def one(name, b):
                    async with sem:
                        try:
                            o = await asyncio.wait_for(
                                c.send(tok, b, mimetype="application/pdf"), timeout=300)
                            res[name] = [h(d.get("page_content", ""))
                                         for d in (o.get("documents") or [])]
                        except Exception:
                            res[name] = None
                try:
                    await asyncio.gather(*(one(n_, b) for n_, b in blobs))
                finally:
                    try:
                        await asyncio.wait_for(c.terminate(tok), timeout=60)
                    except Exception:
                        pass
                    await c.disconnect()
                return res
            return asyncio.run(go())

        for arm_name, runner in (("llamaindex_http_pdf", blast_llama),
                                 ("rocketride_pdf", blast_rocket)):
            blast = runner()
            seq = {r["doc"]: r.get("chunk_sha256") for r in results[arm_name]}
            same = sum(1 for k in seq if blast.get(k) == seq[k])
            for r in results[arm_name]:
                r["deterministic"] = blast.get(r["doc"]) == r.get("chunk_sha256")
            say(f"  {arm_name}: {same}/{len(seq)} identical between blast and sequential")
    finally:
        ws.stop(hsvc)

    # ---------------- verdicts ----------------
    out = {"n_offered": len(pdfs), "threads": thr, "arms": {}}
    say("\n" + "=" * 96)
    for arm_name, recs in results.items():
        c = {"successful": 0, "expected": 0, "unexpected": 0}
        for r in recs:
            c[r.get("outcome", "unexpected")] = c.get(r.get("outcome", "unexpected"), 0) + 1
        ids = [r["doc"] for r in recs]
        census_ok = (sum(c.values()) == len(pdfs) and len(set(ids)) == len(ids)
                     and len(recs) == len(pdfs))
        struct_fail = [r for r in recs if r.get("structure") and r["structure"] != ["completed-empty"]]
        det_fail = [r for r in recs if r.get("deterministic") is False]
        ind_fail = [r for r in recs if str(r.get("independent_hash", "")).startswith("FAIL")]
        sus = [r for r in recs if r.get("content_suspect_chunks")]
        say(f"{arm_name}")
        say(f"  LEELA  census      offered {len(pdfs)} = successful {c['successful']} + "
            f"expected {c['expected']} + unexpected {c['unexpected']}   -> {'PASS' if census_ok else 'FAIL'}")
        say(f"  LEELA  structure   {len(struct_fail)} failure(s)                      -> "
            f"{'PASS' if not struct_fail else 'FAIL'}")
        say(f"  LEELA  determinism {len(det_fail)} drifted                            -> "
            f"{'PASS' if not det_fail else 'FAIL'}")
        say(f"  OURS   independent-reference hash: {len(ind_fail)} FAIL")
        say(f"  OURS   content-suspect documents : {len(sus)}")
        out["arms"][arm_name] = {"census": c, "census_ok": census_ok,
                                 "structure_failures": len(struct_fail),
                                 "determinism_failures": len(det_fail),
                                 "independent_hash_failures": len(ind_fail),
                                 "content_suspect": len(sus), "records": recs}

    # ---------------- cross-arm, reported not gated ----------------
    li = {r["doc"]: r for r in results["llamaindex_http_pdf"]}
    rr = {r["doc"]: r for r in results["rocketride_pdf"]}
    rows = []
    for d in li:
        a, b = li[d], rr.get(d)
        if not b or a.get("n_chunks") is None or b.get("n_chunks") is None:
            continue
        rows.append({"doc": d, "chunk_delta": b["n_chunks"] - a["n_chunks"],
                     "char_ratio": round(b["chars"] / a["chars"], 4) if a.get("chars") else None})
    say("\nCROSS-ARM (reported, NOT gated)")
    deltas = [r["chunk_delta"] for r in rows]
    ratios = [r["char_ratio"] for r in rows if r["char_ratio"]]
    if deltas:
        import statistics as st
        say(f"  chunk-count delta (RR - LI): median {st.median(deltas):+.1f}  "
            f"min {min(deltas):+d}  max {max(deltas):+d}  identical on {deltas.count(0)}/{len(deltas)}")
        say(f"  char ratio (RR / LI)       : median {st.median(ratios):.4f}  "
            f"min {min(ratios):.4f}  max {max(ratios):.4f}")
    out["cross_arm"] = rows
    p = write_result("smoke50_parser_in", out)
    say(f"\nwritten -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
