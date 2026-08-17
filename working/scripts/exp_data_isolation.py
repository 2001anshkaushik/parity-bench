#!/usr/bin/env python3
"""DATA ISOLATION — does one tenant's content reach another tenant's response?

Ours. Neither teammate has anything for this: no code, no definition, no run. Checked at Leela
`a5c3b5d` and Shashi `d2b210d`.

THE SETUP. Two tenants send DISJOINT halves of the pinned corpus CONCURRENTLY — A gets
`sorted(*.pdf)[0:N]`, B gets `[N:2N]`. Disjoint is what makes the test readable: no document is
legitimately in both, so a chunk of B's appearing in A's response has only one explanation.

WHAT A "TENANT" IS ON EACH ARM, and why they are not the same thing:

  RocketRide   an explicit per-task boundary. Two clients, two `project_id`s, two tokens. The
               engine knows they are separate. This measures whether that boundary HOLDS.
  LlamaIndex   there is NO tenancy concept in the FastAPI service — one process pool, one model,
               no token, no session. Inventing a fake token here would fabricate a boundary the
               product does not have and would make the arms look comparable when they are not.
               So we do not. Two clients send concurrently and we measure whether concurrent
               requests leak into each other's responses. THAT is the question the service's
               design actually poses, and a clean result means "no cross-request contamination
               under concurrency", NOT "tenant isolation verified".

That asymmetry is the finding, not a flaw in the experiment. It is recorded in the result so the
two numbers are never read as answering the same question.

THE DETECTOR. Per document we already record ordered `chunk_sha256` and a rounded
`vector_sha256`. Tenant A's returned hashes are intersected with tenant B's. Because the corpora
are disjoint, any intersection is either a leak or content two different PDFs genuinely share
(an empty page, a common government header). Those are separated, never merged:

  cross_tenant_chunks    hashes in A's responses that only ONE B document produced and no other
                         A document produced — a leak candidate with a single owner
  cross_tenant_docs      distinct A documents whose response carried such a chunk
  cross_tenant_vectors   the same test on embedding fingerprints, so a vector can be caught
                         leaking even if its text did not
  ambiguous_shared       hashes produced by SEVERAL documents on both sides — boilerplate.
                         Reported, excluded from the leak count, never quietly dropped

THE NULL CONTROL IS MANDATORY AND IS NOT OPTIONAL DECORATION. A detector that reports zero
because it cannot see anything is indistinguishable from a clean result. `--null-control` runs
both tenants over the SAME corpus, where every hash is legitimately shared, and requires the
overlap to be near total. If it is not, the instrument is blind, the main result is meaningless,
and this script exits non-zero and says so. A high overlap in the null control is a PASS of the
instrument, NOT a leak — the two are labelled distinctly everywhere they are printed.

    SMOKE_EXTERNAL=1 python3 working/scripts/exp_data_isolation.py
    SMOKE_EXTERNAL=1 python3 working/scripts/exp_data_isolation.py --null-control
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import experiment_common as ec          # noqa: E402
from harness.resultio import write_result            # noqa: E402

TENANT_N = int(os.environ.get("EXP_TENANT_N", "100"))
# The null control must recover nearly all of the shared content. 0.90 rather than 1.0 leaves
# room for a document that genuinely fails on one side and succeeds on the other; anything
# below this and the detector is not seeing what it is supposed to see.
NULL_MIN_OVERLAP = float(os.environ.get("EXP_NULL_MIN_OVERLAP", "0.90"))
say = ec.say


# ------------------------------------------------------------------ senders

def send_llamaindex(tenant: str, items: List[tuple], out: List[Dict]) -> None:
    """One tenant's stream against the shared service. No token — the service has no tenancy."""
    from weekend_worker import LlamaHttpPdfArm
    arm = LlamaHttpPdfArm(port=ec.PORT)
    try:
        for name, blob in items:
            rec = ec.record(name, time.time_ns())
            rec["tenant"] = tenant
            try:
                chunks, vecs = arm.process(blob)
                out.append(ec.finish_ok(rec, chunks, vecs))
            except Exception as e:
                out.append(ec.finish_err(rec, e))
    finally:
        try:
            arm.close()
        except Exception:
            pass


def run_llamaindex(a_items, b_items) -> List[Dict]:
    """Both tenants in flight at once. Threads, because the arm's transport is blocking."""
    import threading
    rows_a: List[Dict] = []
    rows_b: List[Dict] = []
    ta = threading.Thread(target=send_llamaindex, args=("A", a_items, rows_a))
    tb = threading.Thread(target=send_llamaindex, args=("B", b_items, rows_b))
    ta.start(); tb.start(); ta.join(); tb.join()
    return rows_a + rows_b


def run_rocketride(a_items, b_items) -> List[Dict]:
    """TWO tokens with TWO project_ids — the boundary under test — on one event loop.

    `use_existing` is deliberately NOT passed: each tenant must get its own pipeline instance,
    which is exactly the isolation claim being checked. Sends from the two tenants are
    interleaved by `gather`, so both are genuinely in flight rather than one draining first.
    """
    import asyncio
    import json as _j
    import uuid as _u
    from rocketride import RocketRideClient

    async def tenant(tag: str, items, rows):
        base = _j.loads((ROOT / "working" / "pipes" / ec.PIPE).read_text())
        base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                          f"isolation-{tag}-{os.getpid()}-{time.time()}"))
        pp = ROOT / "working" / "pipes" / "generated" / f"iso_{tag}_{os.getpid()}.pipe"
        pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_text(_j.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=60000)
        tok = (await c.use(filepath=str(pp.relative_to(ROOT))))["token"]
        rows.append({"kind": "tenant_meta", "tenant": tag,
                     "project_id": base["project_id"], "token": str(tok)[:12] + "..."})
        try:
            for name, blob in items:
                rec = ec.record(name, time.time_ns())
                rec["tenant"] = tag
                try:
                    o = await asyncio.wait_for(
                        c.send(tok, blob, mimetype="application/pdf"), timeout=900)
                    docs = o.get("documents") or []
                    rows.append(ec.finish_ok(rec,
                                             [d.get("page_content", "") for d in docs],
                                             [d.get("embedding") or [] for d in docs]))
                except Exception as e:
                    rows.append(ec.finish_err(rec, e))
        finally:
            try:
                await asyncio.wait_for(c.terminate(tok), timeout=60)
            except Exception:
                pass
            try:
                await c.disconnect()
            except Exception:
                pass

    async def go():
        ra: List[Dict] = []
        rb: List[Dict] = []
        await asyncio.gather(tenant("A", a_items, ra), tenant("B", b_items, rb))
        return ra + rb

    return asyncio.run(go())


# ------------------------------------------------------------------ detector

def detect(rows: List[Dict]) -> Dict[str, Any]:
    """Cross-tenant content, with boilerplate separated from leaks.

    Every count here is derived from hashes we already record per document, so the detector adds
    no new measurement path that could itself be wrong in a way the smoke would not catch.
    """
    docs = [r for r in rows if r.get("kind") != "tenant_meta"]
    ok = [r for r in docs if r.get("ok")]
    owners_chunk: Dict[str, set] = defaultdict(set)     # hash -> {(tenant, doc)}
    owners_vec: Dict[str, set] = defaultdict(set)
    for r in ok:
        for hh in r.get("chunk_sha256") or []:
            owners_chunk[hh].add((r["tenant"], r["doc"]))
        for vh in r.get("vector_sha256") or []:
            if vh:
                owners_vec[vh].add((r["tenant"], r["doc"]))

    def analyse(owners: Dict[str, set]) -> Dict[str, Any]:
        a_h = {k for k, v in owners.items() if any(t == "A" for t, _ in v)}
        b_h = {k for k, v in owners.items() if any(t == "B" for t, _ in v)}
        overlap = a_h & b_h
        leaks, ambiguous = [], []
        for hsh in overlap:
            a_docs = {d for t, d in owners[hsh] if t == "A"}
            b_docs = {d for t, d in owners[hsh] if t == "B"}
            # A single owner on each side is a leak candidate; many owners is shared
            # boilerplate that two unrelated PDFs both contain.
            (leaks if len(a_docs) == 1 and len(b_docs) == 1 else ambiguous).append(
                {"hash": hsh[:16], "a_docs": sorted(a_docs)[:3],
                 "b_docs": sorted(b_docs)[:3],
                 "n_a_docs": len(a_docs), "n_b_docs": len(b_docs)})
        return {
            "a_distinct": len(a_h), "b_distinct": len(b_h),
            "overlap_raw": len(overlap),
            "overlap_frac_of_a": round(len(overlap) / len(a_h), 4) if a_h else None,
            "leak_candidates": len(leaks),
            "ambiguous_shared": len(ambiguous),
            "leak_examples": sorted(leaks, key=lambda x: x["hash"])[:10],
            "ambiguous_examples": sorted(ambiguous, key=lambda x: -x["n_a_docs"])[:5],
        }

    ch, vec = analyse(owners_chunk), analyse(owners_vec)
    leak_docs = {d for e in ch["leak_examples"] for d in e["a_docs"]}
    return {
        "chunks": ch,
        "vectors": vec,
        "cross_tenant_chunks": ch["leak_candidates"],
        "cross_tenant_docs": len(leak_docs),
        "cross_tenant_vectors": vec["leak_candidates"],
        "docs_ok": len(ok), "docs_total": len(docs),
        "docs_failed": [{"doc": r["doc"], "tenant": r.get("tenant"), "reason": r.get("reason")}
                        for r in docs if not r.get("ok")][:20],
    }


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--null-control", action="store_true",
                    help="both tenants send the SAME corpus; the detector must then see a near-"
                         "total overlap. Proves the detector is not blind.")
    a = ap.parse_args()
    null = a.null_control

    pool = ec.corpus(TENANT_N * 2)
    if null:
        a_docs = b_docs = pool[:TENANT_N]
    else:
        a_docs, b_docs = pool[:TENANT_N], pool[TENANT_N:TENANT_N * 2]
    assert null or not (set(p.name for p in a_docs) & set(p.name for p in b_docs)), \
        "halves must be disjoint outside the null control"

    a_items = [(p.name, p.read_bytes()) for p in a_docs]
    b_items = [(p.name, p.read_bytes()) for p in b_docs]

    say("DATA ISOLATION" + ("  [NULL CONTROL — both tenants send the SAME corpus]" if null
                            else "  [disjoint halves]"))
    say(f"  tenant A: {len(a_docs)} docs {a_docs[0].name}..{a_docs[-1].name}")
    say(f"  tenant B: {len(b_docs)} docs {b_docs[0].name}..{b_docs[-1].name}")
    if null:
        say("  a HIGH overlap here is the instrument PASSING, not a leak.")

    out: Dict[str, Any] = {
        "experiment": "data_isolation",
        "mode": "null_control" if null else "disjoint",
        "method_source": "ours — neither Leela (a5c3b5d) nor Shashi (d2b210d) has any data-"
                         "isolation code, definition or run",
        "tenancy": {
            "rocketride_pdf": "REAL boundary: two clients, two project_ids, two tokens; "
                              "use_existing NOT passed, so each tenant gets its own pipeline "
                              "instance. Measures whether that boundary holds.",
            "llamaindex_http_pdf": "NO tenancy concept exists in the FastAPI service — one "
                                   "pool, one model, no token, no session. No fake token was "
                                   "invented. Measures whether CONCURRENT REQUESTS leak into "
                                   "each other's responses. A clean result here means no "
                                   "cross-request contamination, NOT tenant isolation.",
            "comparability": "the two arms answer DIFFERENT questions and their numbers must "
                             "not be placed in one column.",
        },
        "protocol": {"tenant_docs": TENANT_N, "concurrent": True,
                     "null_min_overlap_frac": NULL_MIN_OVERLAP if null else None},
        "corpus": {"source": "govdocs1", "glob": ec.CORPUS_GLOB,
                   "rule": f"A=sorted[:{TENANT_N}], B=sorted[{TENANT_N}:{TENANT_N * 2}]"
                           + (" (NULL CONTROL: B=A)" if null else ""),
                   "disjoint": not null,
                   "a_sha256": ec.corpus_sha(a_docs), "b_sha256": ec.corpus_sha(b_docs)},
        "provenance": ec.provenance(),
        "arms": {}}

    all_pass, failures = True, []
    for arm_name, runner in (("llamaindex_http_pdf", run_llamaindex),
                             ("rocketride_pdf", run_rocketride)):
        say(f"\n{arm_name}: both tenants concurrently")
        t0 = time.time()
        try:
            rows = runner(a_items, b_items)
        except Exception as e:
            say(f"  !! run raised {type(e).__name__}: {e}")
            out["arms"][arm_name] = {"error": f"{type(e).__name__}: {e}"[:250], "PASS": False}
            all_pass = False
            failures.append(f"{arm_name}: run raised {type(e).__name__}")
            continue
        d = detect(rows)
        d["wall_s"] = round(time.time() - t0, 1)
        d["records"] = rows

        if null:
            frac = d["chunks"]["overlap_frac_of_a"]
            ok = frac is not None and frac >= NULL_MIN_OVERLAP
            d["null_control_pass"] = ok
            d["PASS"] = ok
            say(f"  overlap {d['chunks']['overlap_raw']}/{d['chunks']['a_distinct']} "
                f"= {frac} of A's hashes (need >= {NULL_MIN_OVERLAP})")
            if not ok:
                all_pass = False
                failures.append(
                    f"{arm_name}: NULL CONTROL FAILED — overlap {frac} < {NULL_MIN_OVERLAP} on "
                    "identical corpora. The detector cannot see shared content, so a zero from "
                    "the disjoint run would prove nothing.")
            else:
                say("  detector CAN see shared content — instrument validated")
        else:
            ok = d["cross_tenant_chunks"] == 0 and d["cross_tenant_vectors"] == 0
            d["PASS"] = ok
            say(f"  cross_tenant_chunks={d['cross_tenant_chunks']}  "
                f"cross_tenant_docs={d['cross_tenant_docs']}  "
                f"cross_tenant_vectors={d['cross_tenant_vectors']}")
            say(f"  (ambiguous shared boilerplate, excluded: "
                f"{d['chunks']['ambiguous_shared']} chunk hashes)")
            if not ok:
                all_pass = False
                failures.append(f"{arm_name}: {d['cross_tenant_chunks']} cross-tenant chunk(s) "
                                f"across {d['cross_tenant_docs']} document(s), "
                                f"{d['cross_tenant_vectors']} vector(s)")
        say(f"  {d['docs_ok']}/{d['docs_total']} documents ok, {d['wall_s']}s")
        out["arms"][arm_name] = d

    out["all_arms_pass"] = all_pass
    if not null:
        out["null_control_required"] = (
            "This result is only interpretable alongside a --null-control run of the same "
            "commit. A zero from a blind detector is indistinguishable from clean isolation.")
    return ec.verdict_exit(all_pass, write_result("exp_data_isolation", out), failures)


if __name__ == "__main__":
    raise SystemExit(main())
