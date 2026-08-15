#!/usr/bin/env python3
"""Unit tests for gates_shared — exact values, and a mutation test per gate.

Mutation testing is the discipline Shashi flagged as missing on both sides
(REVIEW-ansh-metrics §7): for each gate, break the thing it exists to catch and confirm
it FAILS. A gate that cannot fail is worse than no gate.

Run:  ../.venv/bin/python working/harness/test_gates_shared.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import gates_shared as g  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name:52} got={got!r}" + ("" if ok else f" want={want!r}"))
    if not ok:
        FAILED.append(name)


def doc(name, n=2, dim=384, norm=1.0, ok=True, hashes=None, distinct=True):
    """One-hot unit vectors: L2 == 1.0 and, with distinct=True, genuinely different
    vectors. An earlier version set index 0 on every chunk, which made them identical and
    tripped the vectors_not_distinct check — the fixture was broken, not the gate."""
    vecs = []
    for i in range(n):
        v = [0.0] * dim
        v[i % dim if distinct else 0] = norm
        vecs.append(v)
    r = g.check_document([f"{name}-chunk{i}" if distinct else "same" for i in range(n)],
                         vecs, dim)
    r.update(doc=name, ok=ok, identity_ok=True, sha_header_ok=True)
    if hashes is not None:
        r["chunk_sha256"] = hashes
    return r


print("Shashi: repeat_factor (correctness.py:111-134)")
check("no repetition -> 1", g.repeat_factor(["a", "b", "c"]), 1)
check("whole list twice -> 2", g.repeat_factor(["a", "b", "a", "b"]), 2)
check("four times -> 4 (largest first)", g.repeat_factor(["a", "a", "a", "a"]), 4)
check("single chunk -> 1", g.repeat_factor(["a"]), 1)
check("None anywhere -> 1 (fails closed)", g.repeat_factor(["a", None, "a", None]), 1)
check("odd length, no period -> 1", g.repeat_factor(["a", "b", "a"]), 1)

print("Shashi: duplication_verdict + the corrected >=64-chunk trigger")
d = g.duplication_verdict(["a", "b", "a", "b"], [10, 10, 10, 10])
check("duplicated flag", d["duplicated"], True)
check("distinct chunks 2 of 4", d["distinct_chunks"], 2)
check("dup_char_factor 40/20 -> 2.0", d["dup_char_factor"], 2.0)
d = g.duplication_verdict([f"h{i}" for i in range(64)], [1] * 64)
check("64 chunks -> over_chunk_trigger", d["over_chunk_trigger"], True)
check("64 distinct chunks NOT duplicated", d["duplicated"], False)
d = g.duplication_verdict([f"h{i}" for i in range(63)], [1] * 63)
check("63 chunks -> under trigger", d["over_chunk_trigger"], False)

print("Shashi: identical-vector check (correctness.py:242-246)")
r = g.check_document(["a", "b"], [[1.0] + [0.0] * 383, [1.0] + [0.0] * 383], 384)
check("all vectors identical -> flagged", "vectors_not_distinct" in r["bad"], True)
r = g.check_document(["a", "b"], [[1.0] + [0.0] * 383, [0.0, 1.0] + [0.0] * 382], 384)
check("distinct vectors -> clean", r["bad"], [])
r = g.check_document(["a"], [[1.0] + [0.0] * 383], 384)
check("single vector -> not flagged (n<2)", "vectors_not_distinct" in r["bad"], False)

print("Shashi: per-document structure defects")
r = g.check_document(["a"], [[1.0] * 384], 384)
check("L2 = 19.6 -> out of tolerance", "l2_norm_out_of_tolerance" in r["bad"], True)
r = g.check_document(["a"], [[1.0] + [0.0] * 100], 384)
check("wrong dim -> flagged", any("vector_dim" in b for b in r["bad"]), True)
r = g.check_document([""], [[1.0] + [0.0] * 383], 384)
check("empty chunk text -> flagged", "chunk_text_missing" in r["bad"], True)

print("Leela: gate_verdict fail-closed (m0_correctness.py:194-197)")
check("all True -> True", g.gate_verdict({"PASS": True}, {"PASS": True}), True)
check("one False -> False", g.gate_verdict({"PASS": True}, {"PASS": False}), False)
check("None member -> False", g.gate_verdict({"PASS": True}, None), False)
check("missing PASS key -> False", g.gate_verdict({"PASS": True}, {}), False)
check("truthy placeholder -> False", g.gate_verdict({"PASS": "PENDING"}), False)
check("PASS=1 is not True -> False", g.gate_verdict({"PASS": 1}), False)
check("no checks at all -> True (vacuous; callers must pass checks)",
      g.gate_verdict(), True)

print("Leela: census (m0_correctness.py:53-100)")
rows = [doc("a"), doc("b")]
check("2 of 2 -> PASS", g.leela_census(rows, 2)["PASS"], True)
check("1 record of 2 offered -> FAIL (silent drop)", g.leela_census(rows[:1], 2)["PASS"], False)
check("silent count", g.leela_census(rows[:1], 2)["silent"], 1)
dupr = [doc("a"), doc("a")]
check("duplicate doc -> FAIL", g.leela_census(dupr, 2)["PASS"], False)
badr = [doc("a"), dict(doc("b"), ok=False, reason="boom")]
check("unexpected failure -> FAIL", g.leela_census(badr, 2)["PASS"], False)
okempty = [doc("a"), dict(doc("b"), ok=False, reason="no_documents")]
check("allowlisted no_documents -> PASS",
      g.leela_census(okempty, 2, expected_empty={"b"})["PASS"], True)
check("manifest mismatch -> FAIL",
      g.leela_census(rows, 2, expected_docs={"a", "zzz"})["PASS"], False)

def raises_valueerror(f) -> bool:
    try:
        f()
        return False
    except ValueError:
        return True


print("Leela: per-arm REQUIRED_TRUE contract (m0_correctness.py:29-32)")
check("unknown arm raises, never vacuous",
      raises_valueerror(lambda: g.leela_structure([], "nope")), True)
lg_row = dict(doc("a"), vectors_finite=True)
check("lg arm, all flags -> PASS", g.leela_structure([lg_row], "lg")["PASS"], True)
lg_missing = dict(doc("a"))
lg_missing.pop("vectors_finite")
check("lg arm missing vectors_finite -> FAIL",
      g.leela_structure([lg_missing], "lg")["PASS"], False)
check("rr arm does NOT require vectors_finite -> PASS",
      g.leela_structure([lg_missing], "rr")["PASS"], True)
zero = dict(doc("z", n=0), n_chunks=0)
check("zero-chunk not allowlisted -> FAIL", g.leela_structure([zero], "rr")["PASS"], False)
check("zero-chunk allowlisted -> PASS",
      g.leela_structure([zero], "rr", expected_empty={"z"})["PASS"], True)

print("CONFLICT: determinism — asymmetry (Leela fails, Shashi is silent)")
a = [doc("x"), doc("y")]
b = [doc("x")]
check("Leela: only_in_a -> FAIL", g.leela_determinism(a, b)["PASS"], False)
sd = g.shashi_determinism({r["doc"]: r["chunk_sha256"] for r in a},
                          {r["doc"]: r["chunk_sha256"] for r in b})
check("Shashi: same asymmetry -> PASS (intersection only)", sd["PASS"], True)
check("both agree on a real mismatch",
      (g.leela_determinism(a, [doc("x", n=3), doc("y")])["PASS"],
       g.shashi_determinism({"x": ["h1"]}, {"x": ["h2"]})["PASS"]), (False, False))
check("Shashi: empty intersection is vacuous -> FAIL",
      g.shashi_determinism({"x": ["h"]}, {"y": ["h"]})["PASS"], False)
check("Shashi: None digest -> unproven -> FAIL",
      g.shashi_determinism({"x": None}, {"x": None})["PASS"], False)

print("Shashi: structure aggregate refuses vacuous coverage (bench.py:400)")
check("zero docs checked -> FAIL", g.shashi_structure([])["PASS"], False)
check("clean doc -> PASS", g.shashi_structure([doc("a")])["PASS"], True)
dupdoc = doc("d", hashes=["a", "b", "a", "b"])
dupdoc["duplication"] = g.duplication_verdict(["a", "b", "a", "b"], [1, 1, 1, 1])
check("duplicated doc -> structure FAIL", g.shashi_structure([dupdoc])["PASS"], False)
check("duplication sub-verdict FAIL",
      g.shashi_structure([dupdoc])["duplication"]["PASS"], False)

print("Shashi: cross-arm gates (bench.py:337,356,431)")
check("workload ratio 1.0 -> PASS", g.workload_ratio_gate(100, 100)["PASS"], True)
check("ratio 1.5 -> PASS but asymmetry flagged",
      (g.workload_ratio_gate(150, 100)["PASS"],
       g.workload_ratio_gate(150, 100)["workload_asymmetry"]), (True, True))
check("ratio 3.0 -> FAIL (outside hard band)", g.workload_ratio_gate(300, 100)["PASS"], False)
check("ratio 0.3 -> FAIL", g.workload_ratio_gate(30, 100)["PASS"], False)
check("a side with 0 chunks -> FAIL", g.workload_ratio_gate(0, 100)["PASS"], False)
check("chunk config match -> PASS",
      g.chunk_config_parity((4000, 200), (4000, 200))["PASS"], True)
check("chunk config differs -> FAIL",
      g.chunk_config_parity((4000, 200), (512, 50))["PASS"], False)
check("normalization both ok -> PASS",
      g.normalization_parity({"norm_ok": True}, {"norm_ok": True})["PASS"], True)
check("one arm unnormalised -> FAIL",
      g.normalization_parity({"norm_ok": True}, {"norm_ok": False})["PASS"], False)

print("Leela: parity_fixture (defined in her repo, zero call sites there)")
v = [0.1] * 384
check("identical vectors -> PASS", g.parity_fixture(v, v)["PASS"], True)
check("1e-9 apart -> PASS", g.parity_fixture(v, [x + 1e-9 for x in v])["PASS"], True)
check("1e-3 apart -> FAIL", g.parity_fixture(v, [x + 1e-3 for x in v])["PASS"], False)
check("length mismatch -> FAIL", g.parity_fixture(v, v[:100])["PASS"], False)
check("missing vector -> FAIL", g.parity_fixture(None, v)["PASS"], False)

print("Three verdicts")
tv = g.three_verdicts({"census": {"PASS": True}}, {"census": {"PASS": True}})
check("both clean -> union PASS", tv["union"]["PASS"], True)
tv = g.three_verdicts({"census": {"PASS": True}}, {"census": {"PASS": False}})
check("Leela fails -> union FAIL, Shashi still reported PASS",
      (tv["union"]["PASS"], tv["shashi"]["PASS"], tv["leela"]["PASS"]),
      (False, True, False))
tv = g.three_verdicts({"dup": {"PASS": False}}, {"census": {"PASS": True}})
check("Shashi fails -> union FAIL, Leela still reported PASS",
      (tv["union"]["PASS"], tv["shashi"]["PASS"], tv["leela"]["PASS"]),
      (False, False, True))

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("ALL PASS")
