"""Fault-isolation metrics. Shashi's scoreboard, Leela's classifier. Nothing invented here.

PROVENANCE, field by field:

  batch_survived        Shashi bench.py:568 — the batch call completed rather than hanging
  good_docs_ok          Shashi bench.py:536 — good documents that still produced chunks
  collateral_failures   Shashi bench.py:536 — good documents lost to the poison. THE metric
  service_alive_after   Shashi bench.py:558-562 — health endpoint answers after the batch
  recovery_ok           Shashi bench.py:563-573 — a clean document processes afterwards
  surfacing             Shashi bench.py:574-576 + Leela m4_m5_faults.py:57-66 — did the SERVICE
                        report the failure, or did only our proof layer catch it?
  time_to_next_success  Leela m4_m5_faults.py:33-40, with the 60 s attribution window at :30-32

THE POINT OF `surfacing`, in Shashi's words (bench.py:614-619): "failure_only_inferred_by_client
counts success-shaped responses caught only by the driver's proof layer. The second number is
the finding: it measures how much a caller would have to verify itself to notice the framework
did no work." A success-shaped empty response scores 0.

The poison document is a CONTROL failure and is EXPECTED to fail. What is measured is whether
the server said so, and whether anything else broke.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ATTRIBUTION_WINDOW_S = 60.0        # Leela m4_m5_faults.py:13


def ok_records(rows: List[Dict]) -> List[Dict]:
    return [r for r in (rows or []) if r.get("ok")]


def by_completion(rows: List[Dict]) -> List[Dict]:
    return sorted((r for r in (rows or []) if r.get("completion_ns") is not None),
                  key=lambda r: r["completion_ns"])


def server_surfaced(r: Dict) -> bool:
    """Leela m4_m5_faults.py:57-66, lifted verbatim — including the ordering, which matters.

    `no_documents` is checked BEFORE the generic error test precisely so a success-shaped empty
    response cannot be talked into counting as surfaced by an error field set elsewhere.
    """
    if r.get("http_status") and r["http_status"] >= 400:
        return True
    if r.get("reason") in ("no_documents",):
        return False                      # success-shaped empty: silent from the server
    if r.get("reason") in ("transport_error",):
        return True
    return bool(r.get("error")) and r.get("reason") not in ("completed", None)


def surfacing(rows: List[Dict], fault_docs: List[str]) -> Dict[str, Any]:
    """M5 surfacing, restricted to the documents we deliberately broke."""
    fault_set = set(fault_docs)
    failed = [r for r in rows if r["doc"] in fault_set and not r.get("ok")]
    surf = {r["doc"]: server_surfaced(r) for r in failed}
    return {
        "error_surfaced_by_server": surf,
        "failure_only_inferred_by_client": {d: (not v) for d, v in surf.items()},
        "all_errors_surfaced": all(surf.values()) if surf else None,
        "fault_docs_that_failed": len(failed),
        "fault_docs_total": len(fault_set),
        # A poison document that SUCCEEDS is its own finding: the parser accepted 64 KB of
        # noise. Never silently folded into the failure counts.
        "poison_unexpectedly_succeeded": [
            r["doc"] for r in rows if r["doc"] in fault_set and r.get("ok")],
    }


def blast_radius(rows: List[Dict], fault_docs: List[str],
                 window_s: float = ATTRIBUTION_WINDOW_S) -> Dict[str, Any]:
    """Leela m4_m5_faults.py:13-45.

    Collateral = UNRELATED documents whose FAILURE completes within `window_s` of the fault
    document's outcome. A wedge shows up as a long unbroken failure run and is counted fully.
    `time_to_next_success_s` has no window: it answers "how long until the service did useful
    work again", and truncating it at 60 s would report a wedge as a fast recovery.
    """
    fault_set = set(fault_docs)
    done = by_completion(rows)
    per: Dict[str, Any] = {}
    for fd in fault_docs:
        frec = next((r for r in done if r["doc"] == fd), None)
        if frec is None:
            per[fd] = {"error": "fault doc has no record"}
            continue
        t = frec["completion_ns"]
        collateral = [r["doc"] for r in done
                      if r["doc"] not in fault_set and not r.get("ok")
                      and 0 <= (r["completion_ns"] - t) / 1e9 <= window_s]
        nxt = next((r for r in done if r["completion_ns"] > t
                    and r.get("ok") and r["doc"] not in fault_set), None)
        per[fd] = {
            "fault_outcome": frec.get("reason") or ("ok" if frec.get("ok") else "failed"),
            "collateral_count": len(collateral),
            "collateral_docs": collateral[:20],
            "time_to_next_success_s":
                round((nxt["completion_ns"] - t) / 1e9, 2) if nxt else None,
            "no_success_after_fault": nxt is None,
        }
    total = sum(v.get("collateral_count", 0) for v in per.values() if isinstance(v, dict))
    return {"per_fault": per, "total_collateral": total, "window_s": window_s,
            "PASS_zero_blast": total == 0}


def score_arm(rows: List[Dict], fault_docs: List[str], batch_survived: bool,
              alive_after: bool, recovery_rows: Optional[List[Dict]]) -> Dict[str, Any]:
    """One arm's full scoreboard, in Shashi's field names.

    `collateral_failures` is the count of GOOD documents that did not succeed. It is deliberately
    a raw count of failures rather than the windowed figure: Shashi's metric asks how many good
    documents were lost to the poison at all, and a document lost 61 s later is still lost. The
    windowed attribution from Leela is reported alongside, never instead.
    """
    fault_set = set(fault_docs)
    good = [r for r in rows if r["doc"] not in fault_set]
    good_ok = ok_records(good)
    br = blast_radius(rows, fault_docs)
    rec_ok = None
    if recovery_rows is not None:
        rec_ok = bool(recovery_rows) and all(r.get("ok") for r in recovery_rows)
    return {
        "batch_survived": bool(batch_survived),
        "good_docs_total": len(good),
        "good_docs_ok": len(good_ok),
        "collateral_failures": len(good) - len(good_ok),      # THE metric
        "service_alive_after": bool(alive_after),
        "recovery_ok": rec_ok,
        "recovery_docs": len(recovery_rows or []),
        "surfacing": surfacing(rows, fault_docs),
        "blast_radius": br,
        "chunks_from_batch": sum(r.get("n_chunks") or 0 for r in good_ok),
        "good_doc_reasons": {r["doc"]: r.get("reason") for r in good if not r.get("ok")},
    }


def arm_pass(score: Dict[str, Any]) -> tuple:
    """PASS requires all five of Shashi's conditions. Returns (passed, reasons_failed).

    Surfacing is reported but NOT gated: whether the server announces a bad document is a
    product characteristic we want measured, and turning it into a pass/fail would make the
    experiment argue rather than observe. `collateral_failures > 0` is the failure that matters.
    """
    fails = []
    if not score["batch_survived"]:
        fails.append("batch did not survive the poison document")
    if score["collateral_failures"] > 0:
        fails.append(f"{score['collateral_failures']} good document(s) lost to the poison "
                     f"({score['good_docs_ok']}/{score['good_docs_total']} ok)")
    if not score["service_alive_after"]:
        fails.append("service not alive after the batch")
    if score["recovery_ok"] is False:
        fails.append("a clean document did not process after the fault")
    if score["blast_radius"]["per_fault"] and any(
            v.get("no_success_after_fault") for v in score["blast_radius"]["per_fault"].values()
            if isinstance(v, dict)):
        fails.append("no successful document at all after the fault (possible wedge)")
    return (not fails), fails
