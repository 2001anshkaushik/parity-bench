#!/usr/bin/env python3
"""Deterministic, stratified GovDocs1 slice for the batch-size sweep.

WHY NOT `000_*.pdf`. DOCS_HANDOFF §7.1: a smoke set drawn from zip 000 alone is not
representative of all 40 zips, and that already bit once (200-doc vs 10k figures differed
partly by corpus mix). The docs variance axes are page count and extraction difficulty, so the
slice is stratified over page-count terciles x chars-per-page terciles (9 cells), allocated
proportionally to the corpus, plus a tenth cell for documents the manifest could not
characterise (parse_error / no pages) so they are represented rather than silently dropped.

NO RNG. Within a cell documents are ordered by their content sha256 and the first k taken; the
final list is ordered by sha256 too, so heavy documents land in waves by hash, not by name and
not by anyone's choice. Same manifest in -> same slice out, on the laptop and on the box.

The warm-up set is drawn by the same rule from what the measured slice left behind: disjoint
by construction (Leela's WARM=25 policy, exp_batched_blast.py:221).

Prints its own sha256 (register entry 25).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "working" / "results" / "corpus_manifest.jsonl"


def _tercile_edges(values: List[float]) -> List[float]:
    v = sorted(values)
    return [v[len(v) // 3], v[(2 * len(v)) // 3]]


def _bucket(x: float, edges: List[float]) -> int:
    return 0 if x < edges[0] else (1 if x < edges[1] else 2)


def load_manifest(path: Path = MANIFEST) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cells(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    known = [r for r in rows if r.get("pages") and r.get("extracted_chars_pypdf") is not None]
    p_edges = _tercile_edges([r["pages"] for r in known])
    d_edges = _tercile_edges([r["extracted_chars_pypdf"] / r["pages"] for r in known])
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if r.get("pages") and r.get("extracted_chars_pypdf") is not None:
            key = (f"pages{_bucket(r['pages'], p_edges)}"
                   f"_cpp{_bucket(r['extracted_chars_pypdf'] / r['pages'], d_edges)}")
        else:
            key = "uncharacterised"
        out.setdefault(key, []).append(r)
    for k in out:
        out[k].sort(key=lambda r: r["sha256"])
    return {"cells": out, "page_edges": p_edges, "chars_per_page_edges": d_edges}  # type: ignore[return-value]


def allocate(sizes: Dict[str, int], n: int) -> Dict[str, int]:
    """Largest-remainder proportional allocation; every non-empty cell gets at least one."""
    total = sum(sizes.values())
    raw = {k: n * s / total for k, s in sizes.items()}
    got = {k: max(1, int(raw[k])) for k in sizes}
    order = sorted(sizes, key=lambda k: (raw[k] - int(raw[k])), reverse=True)
    i = 0
    while sum(got.values()) < n:
        got[order[i % len(order)]] += 1
        i += 1
    while sum(got.values()) > n:
        k = max(got, key=lambda c: got[c])
        got[k] -= 1
    return got


def build(n: int, warm: int) -> Dict[str, Any]:
    rows = load_manifest()
    c = cells(rows)
    by_cell = c["cells"]  # type: ignore[index]
    sizes = {k: len(v) for k, v in by_cell.items()}
    take = allocate(sizes, n)
    measured, rest = [], []
    for k, v in by_cell.items():
        measured += v[:take[k]]
        rest += v[take[k]:]
    # Warm-up is not stratified: it is excluded from every figure, so hash order is enough.
    rest.sort(key=lambda r: r["sha256"])
    warm_rows = rest[:warm]
    measured.sort(key=lambda r: r["sha256"])
    m_names = [r["file"] for r in measured]
    w_names = [r["file"] for r in warm_rows]
    assert not set(m_names) & set(w_names), "warm-up overlaps the measured slice"
    assert len(set(m_names)) == n, "duplicate document in the measured slice"
    pages = sorted(r.get("pages") or 0 for r in measured)
    return {
        "kind": "batchsize_slice",
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "n": n, "warm": warm,
        "page_edges": c["page_edges"], "chars_per_page_edges": c["chars_per_page_edges"],  # type: ignore[index]
        "cell_sizes_corpus": sizes, "cell_take": take,
        "pages_min_median_max": [pages[0], pages[len(pages) // 2], pages[-1]],
        "bytes_total": sum(r["bytes"] for r in measured),
        "slice_sha256": hashlib.sha256("\n".join(m_names).encode()).hexdigest(),
        "measured": m_names,
        "warm_docs": w_names,
    }


def main() -> int:
    print(f"batchsize_slice.py sha256: {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}",
          file=sys.stderr)
    if len(sys.argv) < 3:
        print("usage: batchsize_slice.py <n> <warm> [out.json]", file=sys.stderr)
        return 2
    out = build(int(sys.argv[1]), int(sys.argv[2]))
    text = json.dumps(out, indent=1)
    if len(sys.argv) > 3:
        p = Path(sys.argv[3])
        if p.exists():
            print(f"REFUSED: {p} exists — results are append-only", file=sys.stderr)
            return 3
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    summary = {k: out[k] for k in out if k not in ("measured", "warm_docs")}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
