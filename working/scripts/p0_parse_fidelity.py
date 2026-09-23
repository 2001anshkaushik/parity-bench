#!/usr/bin/env python3
"""P0 H6 (c): per-document fidelity of each candidate parser against Tika-as-shipped.

    p0_parse_fidelity.py --texts <dir> --ref <label> --cands <label,label> --docs <slice|names>
                         --out <fidelity.jsonl>

Per document and candidate, both texts read as UTF-8 from <texts>/<label>/<doc>.txt:
  char_ratio   len(candidate) / len(reference), in Unicode code points (None if the reference
               is empty)
  dice         Sorensen-Dice similarity of the two texts' whitespace-token MULTISETS after
               collapsing whitespace: 2*sum(min(count_a, count_b)) / (n_a + n_b). Order-insensitive
               on purpose — parsers order text differently, so this is evidence, not a pass/fail
               gate (pre-registration H6 full_report.c). None when both are empty.
Missing text (the parser raised or timed out) is recorded as missing, never as zero similarity.
Run on the box where the texts are; only this per-document table leaves it.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def read(p: Path):
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def dice(a: str, b: str):
    ca, cb = Counter(a.split()), Counter(b.split())
    na, nb = sum(ca.values()), sum(cb.values())
    if na + nb == 0:
        return None
    return 2 * sum((ca & cb).values()) / (na + nb)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--cands", required=True)
    ap.add_argument("--docs", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    p = Path(a.docs)
    names = (json.loads(p.read_text())["measured"] if p.suffix == ".json"
             else [x.strip() for x in a.docs.split(",") if x.strip()])
    with open(a.out, "x") as f:
        for n in names:
            ref = read(a.texts / a.ref / f"{n}.txt")
            for c in a.cands.split(","):
                t = read(a.texts / c / f"{n}.txt")
                rec = {"doc": n, "ref": a.ref, "cand": c,
                       "ref_chars": len(ref) if ref is not None else None,
                       "cand_chars": len(t) if t is not None else None}
                if ref is None or t is None:
                    rec["missing"] = [x for x, v in (("ref", ref), ("cand", t)) if v is None]
                else:
                    rec["char_ratio"] = (len(t) / len(ref)) if len(ref) else None
                    rec["dice"] = dice(ref, t)
                f.write(json.dumps(rec) + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
