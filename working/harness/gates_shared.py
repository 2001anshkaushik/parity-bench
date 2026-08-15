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


# --------------------------------------------------------------- three verdicts

def three_verdicts(shashi_checks: Dict[str, Dict], leela_checks: Dict[str, Dict]
                   ) -> Dict[str, Any]:
    """Same records, three verdicts. The union is the conjunction — a run is union-clean
    only if it satisfies BOTH suites. Nothing is hidden: every component verdict is kept
    alongside so a reader can see which suite failed and on what."""
    s = gate_verdict(*shashi_checks.values())
    lv = gate_verdict(*leela_checks.values())
    return {
        "shashi": {"PASS": s, "checks": shashi_checks},
        "leela": {"PASS": lv, "checks": leela_checks},
        "union": {"PASS": s and lv,
                  "note": "conjunction of both suites over identical records"},
    }
