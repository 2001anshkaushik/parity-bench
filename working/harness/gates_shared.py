"""Correctness gates in BOTH teammates' dialects, plus their union.

Adopted 2026-08-15 from a code reading of the two repos at:
  Shashi  c8b4b2b3  branch benchmark/shared-pipe-engine-3.3.1
  Leela   2cc0ccad  main

WHAT "LOAD-BEARING" MEANS HERE, established from the code and not from prose:

  Leela  — `gate_verdict(census, structure, determinism)` -> `m0_PASS` -> `overall_PASS`
           -> `sys.exit(0 if overall_PASS else 1)` (smoke2_report.py:46,117,142).
           So exactly THREE checks can fail her run. `ground_truth_match()` and
           `parity_fixture()` are defined and unit-tested in `m0_correctness.py` but have
           **zero call sites** in any report or runner — they cannot fail anything today.
  Shashi — every gate is a bare `assert` in `bench.py`, so each one kills the run:
           both arms produced chunks (:333-334), chunk-config parity across arms (:337),
           workload ratio inside 0.4-2.5 (:356), multi-process serving (:370),
           census present and ok (:389-390), structure present with docs_checked>0 and
           norm_ok (:399-403), DUPLICATION present and ok (:413-414), structure ok
           (:431), determinism ok (:800).

We run BOTH sets over the SAME records and report three verdicts — Shashi's, Leela's, and
the union — so neither of them has to re-derive ours. Where the two genuinely disagree on
the same check, both are implemented and labelled; nothing is silently chosen.

THE TWO REAL CONFLICTS, both implemented:

  determinism / corpus asymmetry
      Shashi compares the INTERSECTION only and is silent about documents present in one
      run and not the other (`correctness.py:440-469`) — deliberate, because his blast
      phase is n documents and his sequential phase is seq_n. Leela FAILS on
      `only_in_a`/`only_in_b` (`m0_correctness.py:150-158`) — also deliberate, because her
      two passes are the same corpus and asymmetry means a document went missing.
      Both are right for their own harness. Ours runs the same corpus in both modes, so
      Leela's is the stricter and more appropriate reading — but we report both.

  census shape
      Shashi keys on document NAMES and gates duplicates / missing / unexpected /
      non-allowlisted empty (`correctness.py:406-437`). Leela keys on offered COUNT and
      gates records==offered, no duplicates, no unexpected failures, and (with a manifest)
      no missing/unexpected docs (`m0_correctness.py:53-100`). Different denominators;
      both computable from our records.

NOT a conflict, checked: both use `NORM_TOL = 1e-3` absolute per vector
(`correctness.py:36`, `m0_correctness.py:17`) and both use 384 dims.

This module contains NO metric definitions. `metrics_shared.py` and its settled decisions
are untouched.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set

NORM_TOL = 1e-3          # both teammates, absolute, per vector
EMBED_DIM_DEFAULT = 384  # overridden by the probed dim at call time
NEAR_DUP_FACTOR = 1.9    # Shashi correctness.py — reported, never gated
_MAX_LISTED = 15

# Leela m0_correctness.py:29-32 — fields that must be PRESENT and exactly True per arm.
# RR proves vector finiteness upstream (folded into vector_dim), LG emits explicit flags.
REQUIRED_TRUE = {
    "rr": ("identity_ok",),
    "lg": ("identity_ok", "sha_header_ok", "vectors_finite"),
}
# Leela m0_correctness.py:23 — the only reason an allowlisted doc may legitimately fail.
EMPTY_FAIL_REASONS = frozenset({"no_documents"})


# --------------------------------------------------------------- Shashi: duplication

def chunk_hash(text) -> Optional[str]:
    if not isinstance(text, str):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repeat_factor(hashes: Sequence[Optional[str]]) -> int:
    """Shashi correctness.py:111-134, ported verbatim in behaviour.

    How many times a document's chunk list is EXACTLY the same block repeated. 1 = none,
    2 = BUG_CHUNK_DUPLICATION. Reference-free: the duplication happens downstream of
    parse, so any reference derived from the returned chunks doubles with them and
    cancels — chunks and characters both double and a per-character yield sees nothing.
    Only the SHAPE of the list shows it.

    Fails closed: an unhashable chunk anywhere makes the list unproven, so it reports 1
    (no claim) rather than guessing a period across a hole.
    """
    hashes = list(hashes or [])
    k = len(hashes)
    if k < 2 or any(h is None for h in hashes):
        return 1
    for r in range(k, 1, -1):          # largest repeat first: [a,a,a,a] is 4x, not 2x
        if k % r:
            continue
        period = k // r
        if hashes == hashes[:period] * r:
            return r
    return 1


def self_duplication(rows: List[Dict]) -> Dict[str, Any]:
    """Leela m0_correctness.py:311-353 (`a5c3b5d`), adopted verbatim in behaviour.

    A SINGLE-ARM check: does this arm emit the same document list more than once? It needs no
    second arm, so it survives a RocketRide upgrade and fires on any run rather than only on
    runs that happen to include a comparison arm.

    WHY THIS AND NOT ONLY `duplication_verdict`. Ours reports `over_chunk_trigger` at >= 64
    chunks — mechanically correct, since the engine flushes at maxDocuments=64 — but that
    predicate is a claim about the CAUSE. This one asks only about the SHAPE of the list and
    fires on any document with more than one chunk. It is the sensitive detector, and it is
    what proves the duplication patch worked: after RR_DUP_PATCH=1 it must read 0 duplicated
    documents, and a threshold that never looked below 64 chunks could not prove that.

    Measured before the patch: Leela 51/987 at factor 2, LangGraph 0/987; ours 5/199 at
    factor 2.
    """
    ok = [r for r in (rows or []) if r.get("ok")]
    dup: Dict[str, int] = {}
    for r in ok:
        h = r.get("chunk_sha256")
        if isinstance(h, list) and len(h) > 1:
            k = repeat_factor(h)
            if k > 1:
                dup[r["doc"]] = k
    return {
        "checked": len(ok),
        "duplicated_docs": len(dup),
        "factors": sorted(set(dup.values())),
        "docs": dict(sorted(dup.items())[:20]),
        "duplicated_frac": round(len(dup) / len(ok), 5) if ok else None,
        # Vacuous is not a pass: zero documents checked proves nothing about duplication.
        "PASS": (len(dup) == 0) if ok else False,
        "vacuous": not ok,
    }


def derived(value, *, basis: str, measured: bool = False) -> Dict[str, Any]:
    """Shashi's basis-field pattern (`rr_app.py:175-188`), generalised.

    Any number that was not directly observed travels with the sentence explaining what it
    actually is. He applies it to `time_to_first_result_s`, where a batch API has no first
    result and the honest value is the whole batch wall time — so he reports `wall_s` and says
    so in `time_to_first_result_basis` rather than letting a derived number pass as measured.

    Use this for every value the batched arm cannot observe directly. A derived number is not a
    problem; a derived number that looks measured is.
    """
    return {"value": value, "basis": basis, "measured": bool(measured)}


def duplication_verdict(hashes: Sequence[Optional[str]],
                        lengths: Sequence[int]) -> Dict[str, Any]:
    """Shashi correctness.py:138-176.

    repeat_factor   — same list emitted N times. Exact, unambiguous, HARD.
    dup_char_factor — total chars over DISTINCT chars. Catches the same text chunked
                      twice where a seam chunk differs so the list is not an exact
                      repeat. Named, never gated.

    TRIGGER, corrected 2026-08-15: Shashi root-caused this in
    ENGINE-ISSUE-3.3.1-chunk-duplication-2026-08-15.md — the predicate is **>= 64 chunks**
    (`embedding_transformer/IInstance.py` flushes at maxDocuments=64 without
    `preventDefault()`, so the engine also forwards the original event). Our own
    "~239,800 chars" was a proxy for it: 64 chunks x ~3750 chars. Both are reported;
    the chunk count is the real one.
    """
    hashes, lengths = list(hashes or []), list(lengths or [])
    seen, chars_unique, kept = set(), 0, 0
    for hsh, n in zip(hashes, lengths):
        if hsh is not None:
            if hsh in seen:
                continue
            seen.add(hsh)
        kept += 1
        chars_unique += n
    chars = sum(lengths)
    r = repeat_factor(hashes)
    factor = round(chars / chars_unique, 4) if chars_unique else None
    return {
        "chunks": len(hashes),
        "distinct_chunks": kept,
        "chars": chars,
        "chars_unique": chars_unique,
        "repeat_factor": r,
        "dup_char_factor": factor,
        "duplicated": r >= 2,
        "near_duplicate": r < 2 and factor is not None and factor >= NEAR_DUP_FACTOR,
        "over_chunk_trigger": len(hashes) >= 64,      # the real predicate
        "over_char_proxy": chars_unique >= 239_800,   # our original empirical proxy
    }


# --------------------------------------------------------------- shared per-doc check

def l2_norm(emb) -> Optional[float]:
    try:
        return sum(float(x) * float(x) for x in emb) ** 0.5
    except Exception:
        return None


def check_document(chunk_texts: List[str], vectors: List[Sequence[float]],
                   expected_dim: int) -> Dict[str, Any]:
    """One document's per-chunk verdict, carrying everything BOTH dialects need.

    Includes Shashi's identical-vector check (correctness.py:242-246): a stuck or
    broadcast embedder emits perfectly valid vectors that are all the SAME vector — unit
    norm, right width, finite, and useless. Invisible to every other check here.
    """
    reasons: List[str] = []
    hashes = [chunk_hash(t) for t in chunk_texts]
    lengths = [len(t) if isinstance(t, str) else 0 for t in chunk_texts]
    if any(not isinstance(t, str) or not t for t in chunk_texts):
        reasons.append("chunk_text_missing")

    n_min = n_max = None
    seen_vectors = []
    finite = True
    for v in vectors:
        if v is None or len(v) != expected_dim:
            reasons.append(f"vector_dim={None if v is None else len(v)}")
            continue
        nrm = l2_norm(v)
        if nrm is None or nrm != nrm or nrm in (float("inf"), float("-inf")):
            reasons.append("vector_non_finite")
            finite = False
            continue
        n_min = nrm if n_min is None else min(n_min, nrm)
        n_max = nrm if n_max is None else max(n_max, nrm)
        if abs(nrm - 1.0) > NORM_TOL:
            reasons.append("l2_norm_out_of_tolerance")
        seen_vectors.append(tuple(v))
    if len(seen_vectors) > 1 and len(set(seen_vectors)) == 1:
        reasons.append("vectors_not_distinct")

    dup = duplication_verdict(hashes, lengths)
    if dup["duplicated"]:
        reasons.append("chunk_list_duplicated")

    return {
        "n_chunks": len(chunk_texts),
        "chunk_sha256": hashes,
        "duplication": dup,
        "vector_dim": (len(vectors[0]) if vectors and vectors[0] is not None else None),
        "l2_norms_minmax": [n_min, n_max] if n_min is not None else None,
        "vectors_finite": finite,
        "n_bad": len(reasons),
        "bad": sorted(set(reasons)),
    }


# --------------------------------------------------------------- Leela's dialect

def leela_census(rows: List[Dict], offered: int,
                 expected_docs: Optional[Set[str]] = None,
                 expected_empty: Set[str] = frozenset()) -> Dict[str, Any]:
    """Leela m0_correctness.py:53-100. Keys on offered COUNT."""
    docs = [r["doc"] for r in rows]
    counts = Counter(docs)
    duplicates = sorted(d for d, n in counts.items() if n > 1)
    ok = [r for r in rows if r.get("ok")]
    fails = [r for r in rows if not r.get("ok")]
    by_reason: Dict[str, List[str]] = {}
    for r in fails:
        bucket = r.get("reason") or (str(r.get("error_class") or "unknown").split(":", 1)[0])
        by_reason.setdefault(bucket, []).append(r["doc"])
    unexpected = [d for reason, ds in by_reason.items() for d in ds
                  if not (reason in EMPTY_FAIL_REASONS and d in expected_empty)]
    missing = unexpected_docs = None
    if expected_docs is not None:
        seen = set(docs)
        missing = sorted(set(expected_docs) - seen)
        unexpected_docs = sorted(seen - set(expected_docs))
    return {
        "offered": offered, "records": len(rows), "silent": offered - len(rows),
        "duplicate_docs": duplicates, "missing_docs": missing,
        "unexpected_docs": unexpected_docs, "completed": len(ok),
        "failed_by_reason": {k: len(v) for k, v in by_reason.items()},
        "unexpected_failures": len(unexpected),
        "unexpected_failure_docs": sorted(unexpected)[:_MAX_LISTED],
        "PASS": (len(rows) == offered and not duplicates and not unexpected
                 and not missing and not unexpected_docs),
    }


def leela_structure(rows: List[Dict], arm: str,
                    expected_dim: int = EMBED_DIM_DEFAULT,
                    expected_empty: Set[str] = frozenset()) -> Dict[str, Any]:
    """Leela m0_correctness.py:103-142. Fail-closed per-arm field contract.

    `arm` must be a key of REQUIRED_TRUE — an unknown arm raises rather than defaulting
    to "no required fields", which would make the gate vacuous.
    """
    if arm not in REQUIRED_TRUE:
        raise ValueError(f"unknown arm {arm!r}: no record contract defined")
    required = REQUIRED_TRUE[arm]
    bad: Dict[str, List[str]] = {}
    empty: List[str] = []
    for r in [x for x in rows if x.get("ok")]:
        doc = r["doc"]
        violations = [f"{f}={r.get(f)!r}" for f in required if r.get(f) is not True]
        n = r.get("n_chunks")
        if n == 0:
            if doc not in expected_empty:
                violations.append("empty_not_allowlisted")
            (bad.setdefault(doc, violations) if violations else empty.append(doc))
            continue
        if not isinstance(n, int) or n < 1:
            violations.append(f"n_chunks={n!r}")
        if r.get("vector_dim") != expected_dim:
            violations.append(f"vector_dim={r.get('vector_dim')!r}")
        norms = r.get("l2_norms_minmax")
        if (not isinstance(norms, (list, tuple)) or len(norms) != 2
                or not all(isinstance(x, (int, float)) for x in norms)
                or abs(norms[0] - 1) >= NORM_TOL or abs(norms[1] - 1) >= NORM_TOL):
            violations.append(f"l2_norms={norms!r}")
        hashes = r.get("chunk_sha256")
        if not isinstance(hashes, list) or (isinstance(n, int) and len(hashes) != n):
            violations.append(
                f"chunk_hashes={'missing' if hashes is None else len(hashes)}/{n}")
        if violations:
            bad[doc] = violations
    return {"bad_docs": bad, "completed_empty": empty, "PASS": not bad}


def leela_determinism(rows_a: List[Dict], rows_b: List[Dict]) -> Dict[str, Any]:
    """Leela m0_correctness.py:144-158. Asymmetry between runs is a FAILURE."""
    a = {r["doc"]: r.get("chunk_sha256") for r in rows_a if r.get("ok")}
    b = {r["doc"]: r.get("chunk_sha256") for r in rows_b if r.get("ok")}
    both = sorted(set(a) & set(b))
    mismatch = [d for d in both if a[d] is None or b[d] is None or a[d] != b[d]]
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    return {"compared": len(both), "mismatch_docs": mismatch[:_MAX_LISTED],
            "n_mismatch": len(mismatch),
            "only_in_a": only_a[:_MAX_LISTED], "only_in_b": only_b[:_MAX_LISTED],
            "PASS": bool(both) and not mismatch and not only_a and not only_b}


def parity_fixture(vec_a: Optional[List[float]], vec_b: Optional[List[float]],
                   atol: float = 1e-5) -> Dict[str, Any]:
    """Leela m0_correctness.py:186-192 — elementwise cross-arm vector comparison.

    NOTE: this is DEFINED in her repo but has zero call sites, so it is not load-bearing
    for her today. Adopted because a dimension check only proves both sides emitted 384
    numbers; this proves they emitted the SAME numbers.
    """
    if not (isinstance(vec_a, list) and isinstance(vec_b, list)
            and len(vec_a) == len(vec_b) and vec_a):
        return {"PASS": False, "error": "vector missing or length mismatch"}
    worst = max(abs(x - y) for x, y in zip(vec_a, vec_b))
    return {"max_abs_diff": worst, "atol": atol, "PASS": worst < atol}


def gate_verdict(*checks: Optional[Dict[str, Any]]) -> bool:
    """Leela m0_correctness.py:194-197, verbatim semantics.

    True only when every check has PASS exactly True. None, a missing check, or any
    truthy placeholder fails closed.
    """
    return all(isinstance(c, dict) and c.get("PASS") is True for c in checks)


# --------------------------------------------------------------- Shashi's dialect

def shashi_census(expected_names: Sequence[str], seen_names: Sequence[str],
                  expected_empty: Sequence[str] = (),
                  zero_chunk_names: Sequence[str] = ()) -> Dict[str, Any]:
    """Shashi correctness.py:406-437. Keys on document NAMES.

    `seen_names` is a LIST, not a set — duplicates are only detectable with repeats intact.
    """
    exp, seen = list(expected_names or []), list(seen_names or [])
    allow = set(expected_empty or ())
    counts = Counter(seen)
    dupes = sorted(n for n, c in counts.items() if c > 1)
    missing = sorted(set(exp) - set(seen))
    unexpected = sorted(set(seen) - set(exp))
    empty_bad = sorted(n for n in (zero_chunk_names or []) if n not in allow)
    return {
        "expected": len(exp), "recorded": len(seen),
        "n_missing": len(missing), "missing": missing[:_MAX_LISTED],
        "n_duplicates": len(dupes), "duplicates": dupes[:_MAX_LISTED],
        "n_unexpected": len(unexpected), "unexpected": unexpected[:_MAX_LISTED],
        "n_silent_empty": len(empty_bad), "silent_empty": empty_bad[:_MAX_LISTED],
        "PASS": (bool(exp) and len(exp) == len(seen)
                 and not missing and not dupes and not unexpected and not empty_bad),
    }


def shashi_structure(rows: List[Dict], expected_dim: int = EMBED_DIM_DEFAULT
                     ) -> Dict[str, Any]:
    """Aggregate of Shashi's per-document check_chunks (correctness.py:210-266) plus the
    three things bench.py asserts on separately: docs_checked > 0 (:400), norm_ok (:403)
    and the duplication verdict (:413-414).

    docs_checked == 0 is a FAIL, not a pass — a structure verdict over zero documents is
    vacuous, and bench.py refuses it explicitly.
    """
    checked = [r for r in rows if r.get("ok")]
    n_bad = sum(r.get("n_bad", 0) for r in checked)
    reasons = sorted({b for r in checked for b in (r.get("bad") or [])})
    dup_docs = [r["doc"] for r in checked
                if (r.get("duplication") or {}).get("duplicated")]
    max_rf = max([(r.get("duplication") or {}).get("repeat_factor", 1)
                  for r in checked] or [1])
    norms = [r.get("l2_norms_minmax") for r in checked if r.get("l2_norms_minmax")]
    flat = [x for pair in norms for x in pair]
    norm_ok = bool(flat) and all(abs(x - 1.0) <= NORM_TOL for x in flat)
    over_trigger = sum(1 for r in checked
                       if (r.get("duplication") or {}).get("over_chunk_trigger"))
    return {
        "docs_checked": len(checked), "n_bad": n_bad, "reasons": reasons,
        "expected_dim": expected_dim,
        "norm_ok": norm_ok,
        "duplication": {
            "n_duplicated": len(dup_docs), "duplicated_docs": dup_docs[:_MAX_LISTED],
            "max_repeat_factor": max_rf, "n_over_chunk_trigger": over_trigger,
            "PASS": not dup_docs},
        # bench.py asserts docs_checked, norm_ok, duplication.ok and structure.ok
        # separately; PASS here is the conjunction so one boolean carries all four.
        "PASS": bool(checked) and n_bad == 0 and norm_ok and not dup_docs,
    }


def shashi_determinism(a: Dict[str, Any], b: Dict[str, Any],
                       label_a: str = "run_a", label_b: str = "run_b") -> Dict[str, Any]:
    """Shashi correctness.py:440-469. INTERSECTION only — silent on asymmetry.

    Fails closed twice over: a None digest on either side is UNPROVEN (never "equal by
    both being absent"), and an empty intersection is vacuous, not a pass.
    """
    a, b = a or {}, b or {}
    common = sorted(set(a) & set(b))
    identical, mismatched, unproven = [], [], []
    for k in common:
        da, db = a.get(k), b.get(k)
        if da is None or db is None:
            unproven.append(k)
        elif da == db:
            identical.append(k)
        else:
            mismatched.append(k)
    return {
        "label_a": label_a, "label_b": label_b, "compared": len(common),
        "identical": len(identical),
        "n_mismatched": len(mismatched), "mismatched": mismatched[:_MAX_LISTED],
        "n_unproven": len(unproven), "unproven": unproven[:_MAX_LISTED],
        "PASS": bool(common) and not mismatched and not unproven,
    }


def workload_ratio_gate(chunks_a: Optional[int], chunks_b: Optional[int]
                        ) -> Dict[str, Any]:
    """Shashi bench.py:356 — HARD band 0.4-2.5 (structural breakage: dropped or
    duplicated documents), with the 0.8-1.25 advisory band logged, never gated."""
    if not (chunks_a and chunks_b):
        return {"ratio": None, "PASS": False, "why": "a side produced no chunks"}
    ratio = chunks_a / chunks_b
    return {"ratio": round(ratio, 4), "hard_band": [0.4, 2.5],
            "advisory_band": [0.8, 1.25],
            "workload_asymmetry": not (0.8 <= ratio <= 1.25),
            "PASS": 0.4 <= ratio <= 2.5}


def chunk_config_parity(cfg_a, cfg_b) -> Dict[str, Any]:
    """Shashi bench.py:337 — both arms must have been given the SAME splitter config.
    A byte-identical pipe does not make the workloads identical if the competing
    framework was configured from a different chunk size."""
    return {"a": cfg_a, "b": cfg_b, "PASS": bool(cfg_a) and cfg_a == cfg_b}


def normalization_parity(struct_a: Dict, struct_b: Dict) -> Dict[str, Any]:
    """Shashi bench.py:431 / correctness.normalization_parity — both arms must agree on
    whether vectors are unit-normalised. One normalised and one not is not a comparison."""
    na, nb = (struct_a or {}).get("norm_ok"), (struct_b or {}).get("norm_ok")
    return {"a_norm_ok": na, "b_norm_ok": nb,
            "PASS": na is True and nb is True}


# --------------------------------------------------------------- adapter + legacy path
#
# THE ADAPTER IS WHERE THE 2026-08-15 CONTRADICTION LIVED. The gate functions above are
# faithful ports; the bug was in how the smoke built rows for them, inline and untested,
# so the legacy per-arm block and the gate table disagreed on identical records:
#
#   legacy: census 200 = 198 + 2 + 0 PASS   |  gates: census FAIL, both arms, BOTH rules
#   legacy: determinism 200/200 identical   |  gates: determinism FAIL under the symmetric rule
#
# Reproduced on the real 200-document records. Two adapter defects, one design note:
#
# 1. EXPECTED-EMPTY WAS NEVER PLUMBED. Two documents (000_000164, 000_000357) return zero
#    chunks legitimately; the legacy block counts them in its `expected` bucket. The adapter
#    passed no allowlist and labelled them with OUR vocabulary (`completed_empty`), which is
#    not in Leela's EMPTY_FAIL_REASONS ({"no_documents"}). So Leela's census called them
#    unexpected failures and Shashi's called them silent empties. Both FAIL, both arms —
#    which is the signature of a harness defect, not a real one.
#
# 2. THE TWO LEGS CLASSIFIED THE SAME DOCUMENT DIFFERENTLY. Sequentially those docs are
#    outcome="expected" so the adapter set ok=False; in the blast leg the send returned, so
#    ok=True with zero chunks. The symmetric rule then reports only_in_b for documents that
#    BOTH legs processed. The asymmetry was manufactured by the adapter, not observed.
#    `classify_ok` is now the single rule applied to both legs.
#
# 3. NOT A DEFECT: structure legitimately differs between the two rules. The A-side folds
#    duplication into structure (`chunk_list_duplicated` counts toward n_bad); the B-side has
#    no duplication concept at all. On the RR arm's 5 duplicated documents A fails structure
#    and B passes. Tolerance and dimension are identical between them — they are simply not
#    the only inputs. Divergence here is the suites disagreeing, which is the point of
#    reporting both.


def classify_ok(n_chunks, errored: bool) -> bool:
    """The ONE success rule, applied identically to every leg.

    A document that returns zero chunks is not a success — it is an expected empty. Applying
    this in one leg and not the other is what manufactured the phantom only_in_b.
    """
    return (not errored) and isinstance(n_chunks, int) and n_chunks > 0


def expected_empty_docs(rows: List[Dict]) -> Set[str]:
    """Documents that legitimately produced no content. Both censuses need this allowlist;
    neither can infer it."""
    return {r["doc"] for r in rows if r.get("n_chunks") == 0 and not r.get("errored")}


def to_leela_reason(error_class: Optional[str]) -> Optional[str]:
    """Map OUR failure vocabulary onto Leela's at the boundary rather than editing her
    constant. `completed_empty` is our name for what she calls `no_documents`."""
    return "no_documents" if error_class == "completed_empty" else error_class


def legacy_verdicts(rows: List[Dict], n_offered: int,
                    blast_rows: List[Dict]) -> Dict[str, bool]:
    """The pre-gates per-arm block, as a function so it can be compared against the gate
    suites instead of drifting from them. Census: every offered document accounted for,
    unique, none unexpected. Determinism: no document whose chunk hashes differ between the
    two legs."""
    docs = [r["doc"] for r in rows]
    census = (len(rows) == n_offered and len(set(docs)) == len(docs)
              and not [r for r in rows if r.get("errored")])
    b = {r["doc"]: r.get("chunk_sha256") for r in blast_rows}
    drift = [r["doc"] for r in rows
             if r["doc"] in b and b[r["doc"]] != r.get("chunk_sha256")]
    return {"census": census, "determinism": not drift, "drift_docs": drift}


# --------------------------------------------------------------- three verdicts

def not_run(gate: str, offered: Optional[int] = None, reason: str = "") -> Dict[str, Any]:
    """A gate that evaluated ZERO records reports NOT RUN with its denominator — never FAIL.

    Defect #38: under SMOKE_LEGS=blast the verdict path read the (legitimately empty)
    sequential record set and every fail-closed gate emitted FAIL over zero records —
    "offered 9975 = successful 0 + expected 0 + unexpected 0 -> FAIL" on both arms, while
    9,975 real records sat in the blast JSONLs. A fail-closed verdict over an empty input is
    indistinguishable from a real failure, and that is how a false product finding ships.

    The boundary, stated: NOT RUN is for a gate whose input LEG never executed. A leg that
    ran and produced zero records is a genuine catastrophic FAIL and must stay one —
    Leela's vacuous-is-not-a-pass rule is about that case and is untouched.
    """
    return {"verdict": "NOT RUN", "PASS": None, "records": 0, "offered": offered,
            "reason": reason or "the leg this gate evaluates did not run"}


def three_verdicts(shashi_checks: Dict[str, Dict], leela_checks: Dict[str, Dict]
                   ) -> Dict[str, Any]:
    """Same records, three verdicts. The union is the conjunction — a run is union-clean
    only if it satisfies BOTH suites. Nothing is hidden: every component verdict is kept
    alongside so a reader can see which suite failed and on what.

    Checks with PASS=None (NOT RUN, from `not_run`) are EXCLUDED from each suite's
    conjunction and counted separately: an unexecuted gate neither passes nor fails a suite,
    and folding it into fail-closed gate_verdict() would reintroduce defect #38. A suite
    whose every check is NOT RUN reports PASS=None, not True — no records, no verdict.
    """
    def suite(checks: Dict[str, Dict]):
        ran = {k: v for k, v in checks.items() if not (isinstance(v, dict)
                                                       and v.get("PASS") is None
                                                       and v.get("verdict") == "NOT RUN")}
        skipped = sorted(set(checks) - set(ran))
        verdict = gate_verdict(*ran.values()) if ran else None
        return verdict, skipped

    s, s_skip = suite(shashi_checks)
    lv, l_skip = suite(leela_checks)
    union = (s and lv) if (s is not None and lv is not None) else None
    return {
        "shashi": {"PASS": s, "checks": shashi_checks, "not_run": s_skip},
        "leela": {"PASS": lv, "checks": leela_checks, "not_run": l_skip},
        "union": {"PASS": union,
                  "not_run": sorted(set(s_skip) | set(l_skip)),
                  "note": "conjunction of both suites over identical records; NOT-RUN "
                          "gates are excluded from the conjunction and listed, never "
                          "counted as failures"},
    }


# =============================================================================
# Phase 2 (video) extensions — approved 2026-08-20.
#
# WHAT CHANGED AND WHY (the reuse rule requires this note):
#   * chunk_config_parity is RETIRED for Phase 2 (it asserted config as
#     evidence — the class this project keeps catching). Its replacement is
#     char_conservation_parity below: a MEASURED workload-parity gate on the
#     sum of chunk characters per document, both arms. Tolerance 2% covers
#     each splitter's own separator stripping (measured: RecursiveCharacter
#     drops ~1 whitespace char per chunk seam, ~0.2% of a detect-JSON blob).
#   * frames_census: the per-video emitted-unit census for the video phase.
#     Records are many-per-input, so Phase 1's one-record-per-item censuses
#     do not carry; the frame count is manifest-derivable and exact.
#   * thread_pin_parity: defect #37's fix as ONE function fed by both arms —
#     absence fails BEFORE agreement is checked, always.
#   * chunk_count_ratio: REPORTED, never gated in the first runs (approved) —
#     the two arms use different splitter algorithms by design, so the
#     natural spread must be observed before a band is proposed.
# Nothing above this block changed.
# =============================================================================


def char_conservation_parity(pairs: Sequence[Dict[str, Any]],
                             tol: float = 0.02) -> Dict[str, Any]:
    """Measured workload parity: per-document sum-of-chunk-characters ratio.

    `pairs` rows: {"video": str, "rr_chars": int|None, "li_chars": int|None}.
    A missing side is an ABSENCE failure for that row (absence fails before
    agreement); zero rows is the caller's NOT-RUN case (use not_run()).
    Gate input is sum(chunk lengths) on BOTH arms — not the pre-split blob —
    so both splitters' separator losses sit inside the tolerance symmetrically.
    """
    if not pairs:
        return {"PASS": False, "reason": "zero pairs — if the leg did not run, "
                                         "report not_run() instead", "tol": tol}
    rows, worst = [], 0.0
    ok = True
    for p in pairs:
        rr, li = p.get("rr_chars"), p.get("li_chars")
        if not rr or not li:  # None or 0 — a zero-char document cannot pass parity
            rows.append({"video": p.get("video"), "PASS": False,
                         "reason": f"absent side rr={rr!r} li={li!r}"})
            ok = False
            continue
        ratio = rr / li
        dev = abs(ratio - 1.0)
        worst = max(worst, dev)
        row_ok = dev <= tol
        ok = ok and row_ok
        rows.append({"video": p.get("video"), "PASS": row_ok,
                     "ratio_rr_over_li": round(ratio, 4)})
    return {"PASS": ok is True, "tol": tol, "n_pairs": len(pairs),
            "worst_abs_deviation": round(worst, 4), "rows": rows}


def frames_census(records: Sequence[Dict[str, Any]],
                  expected_by_video: Dict[str, int],
                  arm: str) -> Dict[str, Any]:
    """Per-video frame census: observed (read back from the arm's own records)
    vs expected (manifest-derived, exact). Absence of an observed count FAILS
    the row — an arm that cannot report what it extracted cannot pass a census.
    Empty `records` returns PASS=False (a leg that ran and produced zero is a
    FAIL); a leg that did not run is the caller's not_run() case (#38 rule).
    """
    if not records:
        return {"PASS": False, "arm": arm, "reason": "zero records"}
    rows, ok = [], True
    seen = set()
    for r in records:
        vid, obs = r.get("video"), r.get("frames_observed")
        seen.add(vid)
        exp = expected_by_video.get(vid)
        if obs is None or exp is None:
            rows.append({"video": vid, "PASS": False,
                         "reason": f"absent observed={obs!r} expected={exp!r}"})
            ok = False
        elif obs != exp:
            rows.append({"video": vid, "PASS": False, "observed": obs, "expected": exp})
            ok = False
        else:
            rows.append({"video": vid, "PASS": True, "frames": obs})
    missing = sorted(set(expected_by_video) - seen)
    if missing:
        ok = False
    return {"PASS": ok is True, "arm": arm, "n_records": len(records),
            "missing_videos": missing or None, "rows": rows}


def thread_pin_parity(readbacks: Dict[str, Dict[str, Any]],
                      keys: Sequence[str] = ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                             "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                                             "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS")) -> Dict[str, Any]:
    """One check, both arms (#24/#25/#37 class): every reader (RR task process,
    each LI worker) must report ALL six variables plus torch_num_threads, and
    every reported value must agree across readers. ABSENCE FAILS FIRST: a
    missing reader, variable, or torch count fails before any agreement is
    examined — two unpinned arms agreeing is exactly the defect.
    """
    if not readbacks:
        return {"PASS": False, "reason": "no readbacks — absent fails before agreement"}
    absent = []
    for label, rb in readbacks.items():
        env = (rb or {}).get("env") or {}
        for k in keys:
            if env.get(k) in (None, ""):
                absent.append(f"{label}:{k}")
        if (rb or {}).get("torch_num_threads") is None:
            absent.append(f"{label}:torch_num_threads")
    if absent:
        return {"PASS": False, "absent": absent,
                "reason": "absent pins fail before agreement is checked"}
    values = {k: {label: rb["env"][k] for label, rb in readbacks.items()} for k in keys}
    values["torch_num_threads"] = {label: rb["torch_num_threads"]
                                   for label, rb in readbacks.items()}
    disagree = {k: v for k, v in values.items() if len(set(v.values())) > 1}
    return {"PASS": not disagree, "readers": sorted(readbacks),
            "disagreements": disagree or None, "values_agreed":
                {k: next(iter(v.values())) for k, v in values.items()} if not disagree else None}


def chunk_count_ratio(rr_records: Sequence[Dict[str, Any]],
                      li_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """REPORTED, not gated (approved 2026-08-20): the arms split with different
    native algorithms, so the count ratio measures splitter semantics, not
    loss. A gated band gets proposed from the observed spread, not assumed.
    """
    rr = {r.get("video"): r.get("n_chunks") for r in rr_records}
    li = {r.get("video"): r.get("n_chunks") for r in li_records}
    ratios = {v: round(rr[v] / li[v], 3) for v in rr
              if v in li and rr[v] and li[v]}
    vals = sorted(ratios.values())
    return {"gated": False, "n_pairs": len(vals),
            "ratio_min_median_max": ([vals[0], vals[len(vals) // 2], vals[-1]]
                                     if vals else None),
            "per_video": ratios or None}


def whole_list_doubled(hashes: Sequence[str]) -> Optional[bool]:
    """The stock-engine flush-defect signature: the ENTIRE chunk list emitted
    twice ([A..Z,A..Z], repeat_factor 2 over the whole record).

    Returns None — indeterminate, never a verdict — when the list is too
    uniform to carry the signature: if every hash in the half is identical,
    [A,A] == [A,A] holds for organic reasons (a fully static scene can emit
    identical detection JSON per frame), and doubling cannot be distinguished
    from content. Callers report None as 'indeterminate' and lean on the
    trigger-eligibility count; they never fold None into a FAIL or a PASS.
    Discovered by a driver self-test on uniform synthetic chunks, 2026-08-20.
    """
    n = len(hashes)
    if n == 0 or n % 2:
        return False
    half = hashes[:n // 2]
    if list(half) != list(hashes[n // 2:]):
        return False
    if len(set(half)) < 2:
        return None
    return True
