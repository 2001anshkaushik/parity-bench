"""Content-sanity checks — the blind spot the goodput gate had.

The goodput gate verifies SHAPE: chunk count, vector dimension, L2 norm, cross-chunk distinctness.
It passed 39,803 characters of binary control codes as eleven confident unit-norm vectors, because
garbage embeds exactly as cleanly as prose. These checks verify that the CONTENT was plausibly
text.

TWO INDEPENDENT CHECKS, because one cannot do both jobs. Measured on a 991-document random sample
of GovDocs1:

  * The three NUL-containing documents had printable ratios 0.9923, 0.9884 and 0.6789 — two of them
    sit inside the legitimate range (the ten lowest legitimate ratios span 0.9757-0.9944). A
    printable-ratio threshold therefore CANNOT detect NUL truncation. One of those documents
    (0.9923, indistinguishable by ratio) would lose 98.9 % of its text.
  * Conversely a NUL check cannot detect a broken font encoding that produces no NUL.

So: `has_nul` is the exact detector for the truncation defect; `printable_ratio` is the detector
for garbage extraction. Neither substitutes for the other.

THRESHOLD DERIVATION — from the corpus, not chosen:
    legitimate documents  p50 1.0000  p25 1.0000  p5 0.9992  p1 0.9944
    2nd-lowest of 991                  0.9757
    known-garbage extractions          0.6789 (027_027492) and 0.700 (001_001157, the doc that
                                       surfaced the NUL bug)
    => threshold 0.90 sits in the empty band between 0.9757 and 0.700.
    Measured on the sample: 1 of 991 documents falls below it, and that document is genuinely
    garbage (93 NULs, ratio 0.6789) — a true positive, not a false one.
"""
from __future__ import annotations

PRINTABLE_RATIO_MIN = 0.90          # derived above; see the empty band 0.700-0.9757


def printable_ratio(text: str) -> float:
    """Fraction of characters that are printable or whitespace."""
    if not text:
        return 0.0
    return sum(1 for c in text if c.isprintable() or c.isspace()) / len(text)


def inspect(text: str) -> dict:
    """Content-sanity facts about one extracted document. Never raises."""
    n = text.count("\x00")
    first = text.find("\x00")
    ratio = printable_ratio(text)
    return {
        "chars": len(text),
        "printable_ratio": round(ratio, 4),
        "has_nul": n > 0,
        "n_nul": n,
        "first_nul": first,
        # what a NUL-truncating consumer would lose, as a fraction of the document
        "nul_lost_fraction": round(1 - first / len(text), 4) if (n and len(text)) else 0.0,
        "low_printable": ratio < PRINTABLE_RATIO_MIN,
        "suspect": (n > 0) or (ratio < PRINTABLE_RATIO_MIN),
    }


def classify(text: str) -> str:
    """One-word verdict for reporting."""
    i = inspect(text)
    if i["low_printable"] and i["has_nul"]:
        return "garbage_and_nul"
    if i["low_printable"]:
        return "garbage_encoding"
    if i["has_nul"]:
        return "nul_truncation_risk"
    return "ok"
