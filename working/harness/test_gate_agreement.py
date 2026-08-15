#!/usr/bin/env python3
"""Golden-record regression: the legacy path and the gate suites must agree.

WHY THIS EXISTS. On 2026-08-15 the 200-document box run produced two verdicts over ONE set
of records that contradicted each other:

    legacy per-arm block : census 200 = 198 + 2 + 0 PASS, determinism 200/200 identical
    gates_shared table   : census FAIL both arms under BOTH rules,
                           determinism FAIL under the symmetric rule

A gate that fails identically on both arms under both rule sets is a harness defect, and it
was: the adapter that built rows for the gate suites lived inline in the smoke and was never
tested against the legacy path it was supposed to reproduce.

This test pins the two paths together on REAL records — the committed 200-document result,
which contains the exact shape that broke it: 198 successful plus two legitimately empty
documents (000_000164.pdf, 000_000357.pdf). Synthetic rows would not have caught it, because
the defect only appears when a document is neither a success nor a failure.

Run:  ../.venv/bin/python working/harness/test_gate_agreement.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "working"))

from harness import gates_shared as gs  # noqa: E402

GOLDEN = ROOT / "working" / "results" / \
    "smoke50_parser_in__20260815T053227Z__c79e799b3baa.json"
RUN_DIR = ROOT / "working" / "results" / "smoke_metrics_20260815T051154Z"
EXPECTED_EMPTY = {"000_000164.pdf", "000_000357.pdf"}

FAILED = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name:58} got={got!r}"
          + ("" if ok else f" want={want!r}"))
    if not ok:
        FAILED.append(name)


def build(recs, arm_key, blast_raw):
    """The adapter, exactly as the smoke must use it."""
    rows, blast = [], []
    for r in recs:
        errored = r.get("outcome") == "unexpected"
        rows.append({
            "doc": r["doc"],
            "errored": errored,
            "ok": gs.classify_ok(r.get("n_chunks"), errored),
            "identity_ok": r.get("returned_doc_id") is not None or arm_key == "rr",
            "sha_header_ok": True,
            "vectors_finite": True,
            "reason": gs.to_leela_reason(r.get("error_class")),
            "n_chunks": r.get("n_chunks"),
            "chunk_sha256": r.get("chunk_sha256"),
            "vector_dim": 384,
            "l2_norms_minmax": [1.0, 1.0],
        })
    for b in blast_raw:
        errored = not b.get("ok")
        blast.append({"doc": b["doc"], "errored": errored,
                      "ok": gs.classify_ok(b.get("n_chunks"), errored),
                      "chunk_sha256": b.get("chunk_sha256")})
    return rows, blast


if not GOLDEN.exists():
    print(f"FATAL: golden record missing at {GOLDEN}")
    sys.exit(2)

data = json.load(open(GOLDEN))["data"]
n_offered = data["n_offered"]
check("golden record is the 200-document run", n_offered, 200)

for arm, a in data["arms"].items():
    arm_key = "lg" if arm.startswith("llamaindex") else "rr"
    tag = "li" if arm_key == "lg" else "rr"
    blast_raw = [json.loads(l) for l in
                 open(RUN_DIR / f"perdoc_{tag}_blast.jsonl")]
    rows, blast = build(a["records"], arm_key, blast_raw)

    print(f"\n{arm}")
    check("legacy census PASS (from the stored verdict)",
          a["census"]["unexpected"] == 0 and
          sum(a["census"].values()) == n_offered, True)

    legacy = gs.legacy_verdicts(rows, n_offered, blast)
    ee = gs.expected_empty_docs(rows)
    check("expected-empty allowlist found the two known docs", ee, EXPECTED_EMPTY)

    lc = gs.leela_census(rows, n_offered, expected_empty=ee)
    sc = gs.shashi_census([r["doc"] for r in rows], [r["doc"] for r in rows],
                          expected_empty=ee,
                          zero_chunk_names=[r["doc"] for r in rows
                                            if r.get("n_chunks") == 0])
    # THE AGREEMENT ASSERTION. These three compute census three ways over one record set.
    check("census: legacy == count-keyed rule", legacy["census"], lc["PASS"])
    check("census: legacy == name-keyed rule", legacy["census"], sc["PASS"])
    check("census: all three PASS", (legacy["census"], lc["PASS"], sc["PASS"]),
          (True, True, True))

    ld = gs.leela_determinism(rows, blast)
    sd = gs.shashi_determinism(
        {r["doc"]: r["chunk_sha256"] for r in rows if r["ok"]},
        {b["doc"]: b["chunk_sha256"] for b in blast if b["ok"]})

    # NO PHANTOMS. Every asymmetry must be explained by a leg that actually errored on that
    # document. An asymmetry with no failure behind it is the adapter inventing one, which is
    # what the expected-empty bug did. A REAL asymmetry is allowed and must be reported:
    # 000_000344.pdf succeeds sequentially and times out in blast, so it is only_in_a here.
    errored_in_blast = {b["doc"] for b in blast if b["errored"]}
    errored_in_seq = {r["doc"] for r in rows if r["errored"] or not r["ok"]}
    check("determinism: every only_in_a is a real blast-side failure",
          [d for d in ld["only_in_a"] if d not in errored_in_blast], [])
    check("determinism: every only_in_b is a real sequential-side failure",
          [d for d in ld["only_in_b"] if d not in errored_in_seq], [])
    check("determinism: no CHUNK-HASH drift on documents both legs completed",
          ld["mismatch_docs"], [])

    # The two whole-corpus rules must always agree: legacy and the symmetric rule both treat a
    # document missing from one leg as a failure. The intersection rule is ALLOWED to differ —
    # it deliberately ignores documents absent from one side. That is the documented conflict.
    check("determinism: legacy == symmetric rule (both whole-corpus)",
          legacy["determinism"], ld["PASS"])
    if legacy["determinism"] != sd["PASS"]:
        check("determinism: intersection differs ONLY via a real asymmetry",
              bool(ld["only_in_a"] or ld["only_in_b"]), True)

# Structure is ALLOWED to differ between the two rules — the A-side folds duplication in and
# the B-side has no duplication concept. Pinned as intended behaviour so a future reader does
# not "fix" it into agreement.
print("\nstructure divergence is BY DESIGN, not a defect")
rr = data["arms"]["rocketride_pdf"]["records"]
dup = [r["doc"] for r in rr
       if r.get("chunk_sha256") and gs.repeat_factor(r["chunk_sha256"]) >= 2]
check("RR arm carries duplicated documents", len(dup), 5)
check("LI arm carries none",
      len([r for r in data["arms"]["llamaindex_http_pdf"]["records"]
           if r.get("chunk_sha256") and gs.repeat_factor(r["chunk_sha256"]) >= 2]), 0)
check("duplication is an A-side gate only (B has no such check)",
      hasattr(gs, "duplication_verdict") and "duplication" not in
      gs.leela_structure([], "rr"), True)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("ALL PASS")
