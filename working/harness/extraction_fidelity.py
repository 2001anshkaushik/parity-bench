"""Cross-arm extraction fidelity — a REPORTED METRIC, never a pass/fail gate.

Under the "Parser IN" topology each arm parses PDFs with its own parser (engine: Tika 3.2.3 via the
stock `parse` node; LlamaIndex: pypdf). Their extracted text differs **by construction**, so any
equality check would fire on every document with no defect present. This module measures how far
apart they are and reports it. It does not gate.

The per-arm correctness gate is `harness.chunk_hash`, which compares each arm against a reference
built from THAT arm's own extracted text. That one stays hard.

THREE MEASURES, BECAUSE ONE IS MISLEADING ON ITS OWN
----------------------------------------------------
* `char_ratio`   len(a)/len(b) — volume only. Leela measured median 0.994 (p10 0.971, p90 1.030)
                 across 140 real GovDocs PDFs; ours agrees at 1.007 on a 10-document sample.
* `seq_similarity` difflib ratio on whitespace-normalised text — **order-sensitive**.
* `word_jaccard` multiset word overlap — **order-insensitive**.

The pair is the point. Documents where `word_jaccard` is high while `seq_similarity` is low contain
the *same words in a different order* — Tika and pypdf disagree on reading order for multi-column
pages and tables. Measured here: doc `000_000013.pdf` scores jaccard 0.994 against seqmatch 0.395.
A single order-sensitive number would have called that a catastrophic mismatch; a single
order-insensitive number would have called it perfect. Both are wrong alone.

⚠️ `difflib.SequenceMatcher` MUST be constructed with `autojunk=False`. The default `autojunk=True`
treats elements appearing in >1% of a sequence longer than 200 as junk — which for natural language
is the common words. Measured: two strings differing in 1% of their words score **0.0000** with
autojunk on and **0.9930** with it off. An identical-string null control passes under BOTH settings,
so it does not catch this; the near-identical case is what exposes it.
"""

from __future__ import annotations

import difflib
from collections import Counter


def _norm(s: str) -> str:
    """Whitespace-collapse and lowercase. Deliberately does NOT strip punctuation: a parser that
    drops punctuation is a real difference we want to see."""
    return " ".join(s.split()).lower()


def word_jaccard(a: str, b: str) -> float:
    """Multiset word overlap — insensitive to ordering, sensitive to content loss."""
    A, B = Counter(_norm(a).split()), Counter(_norm(b).split())
    union = sum((A | B).values())
    return (sum((A & B).values()) / union) if union else 1.0


def seq_similarity(a: str, b: str, cap: int = 200_000) -> float:
    """difflib ratio on normalised text — sensitive to ordering.

    autojunk=False is not optional; see the module docstring. `cap` bounds a quadratic-ish
    comparison on pathological documents.
    """
    return difflib.SequenceMatcher(None, _norm(a)[:cap], _norm(b)[:cap], autojunk=False).ratio()


def fidelity(text_a: str, text_b: str, name_a: str = "a", name_b: str = "b") -> dict:
    """All three measures for one document. Reported, not gated."""
    la, lb = len(text_a), len(text_b)
    out = {
        "chars_" + name_a: la,
        "chars_" + name_b: lb,
        "char_ratio": round(la / lb, 4) if lb else None,
        "seq_similarity": round(seq_similarity(text_a, text_b), 4),
        "word_jaccard": round(word_jaccard(text_a, text_b), 4),
    }
    # The interpretation, attached to the row so a reader cannot take one number alone.
    j, s = out["word_jaccard"], out["seq_similarity"]
    if j >= 0.95 and s >= 0.95:
        out["reading"] = "agree"
    elif j >= 0.95 and s < 0.95:
        out["reading"] = "same words, different order (multi-column / table reading order)"
    elif j < 0.95 and (out["char_ratio"] or 1) > 1.1:
        out["reading"] = "one parser extracted materially more content"
    else:
        out["reading"] = "content differs"
    return out


def summarise(rows: list[dict]) -> dict:
    """Corpus-level summary. Any threshold must be DERIVED from this, not chosen in advance."""
    import statistics as st

    def q(key):
        v = [r[key] for r in rows if r.get(key) is not None]
        if not v:
            return None
        v.sort()
        return {"median": round(st.median(v), 4), "min": round(v[0], 4), "max": round(v[-1], 4),
                "p10": round(v[max(0, int(0.10 * len(v)) - 1)], 4),
                "p90": round(v[min(len(v) - 1, int(0.90 * len(v)))], 4), "n": len(v)}

    return {"char_ratio": q("char_ratio"), "seq_similarity": q("seq_similarity"),
            "word_jaccard": q("word_jaccard"), "n_docs": len(rows),
            "note": "REPORTED METRIC — no pass/fail threshold. Parsers differ by construction "
                    "under Parser IN; see harness/chunk_hash.py for the per-arm hard gate."}
