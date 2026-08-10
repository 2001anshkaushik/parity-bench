#!/usr/bin/env python3
"""STEP 2a — characterize the REAL mt10k corpus, and verify we have the right one.

The parity result was measured on a single synthetic ~1.6 KB document that produces exactly one
chunk. That is not the mt10k distribution, and per-request overhead dominates at one chunk — which
plausibly favours the service with the cheaper request path (mine). Before that number goes
anywhere, the actual corpus shape has to be known.

Rule 2 (declared != measured) applies to the corpus itself: rather than trusting that
`fetch_20newsgroups(subset="train", remove=(), shuffle=False)` reproduces Leela's dataset, every
rebuilt document is hashed and compared against the `sha256_text` recorded in her
`data/mt10k/manifest.jsonl`. If the corpus does not match, nothing downstream is comparable to her
reference vectors.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MANIFEST = ROOT.parent / "benchmark (Leela)" / "data" / "mt10k" / "manifest.jsonl"
OUT_DIR = ROOT / "data" / "mt10k"
OUT = ROOT / "results" / "corpus_characterization.json"
N_DOCS = 10_000


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- manifest (Leela's ground truth) -------------------------------
    manifest = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    print(f"manifest: {len(manifest)} docs")
    m_bytes = sorted(m["n_bytes"] for m in manifest)
    n_empty = sum(1 for m in manifest if m["is_empty"])

    # ---- rebuild from sklearn, VERIFY against the manifest hashes -------
    from sklearn.datasets import fetch_20newsgroups
    print("fetching 20newsgroups (deterministic: subset=train, remove=(), shuffle=False) ...")
    bunch = fetch_20newsgroups(subset="train", remove=(), shuffle=False)
    docs = bunch.data[:N_DOCS]
    print(f"rebuilt: {len(docs)} docs")

    matches = mismatches = 0
    bad_examples = []
    for m, text in zip(manifest, docs):
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h == m["sha256_text"]:
            matches += 1
        else:
            mismatches += 1
            if len(bad_examples) < 3:
                bad_examples.append({"doc_id": m["doc_id"], "expected": m["sha256_text"][:16],
                                     "got": h[:16], "manifest_bytes": m["n_bytes"],
                                     "rebuilt_bytes": len(text.encode())})
    corpus_verified = mismatches == 0
    print(f"  sha256 match against Leela's manifest: {matches}/{len(manifest)}  "
          f"{'VERIFIED — same corpus' if corpus_verified else 'MISMATCH'}")
    for b in bad_examples:
        print(f"    {b}")

    # ---- chunk-count distribution under the contract splitter ----------
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200,
                                              length_function=len)
    chunk_counts = []
    for text in docs:
        prepared = text + "\n"          # the canonical transform
        chunk_counts.append(0 if not prepared.strip() else len(splitter.split_text(prepared)))
    cc = sorted(chunk_counts)
    bytes_sorted = sorted(len(d.encode()) for d in docs)

    hist: dict[str, int] = {}
    for c in chunk_counts:
        k = str(c) if c <= 5 else ("6-10" if c <= 10 else ("11-20" if c <= 20 else "21+"))
        hist[k] = hist.get(k, 0) + 1

    report = {
        "corpus_verified_against_leela_manifest": corpus_verified,
        "sha256_matches": matches, "sha256_mismatches": mismatches,
        "n_docs": len(docs), "n_empty_in_manifest": n_empty,
        "bytes": {"min": bytes_sorted[0], "p10": pct(bytes_sorted, .10),
                  "p25": pct(bytes_sorted, .25), "median": pct(bytes_sorted, .50),
                  "p75": pct(bytes_sorted, .75), "p90": pct(bytes_sorted, .90),
                  "p99": pct(bytes_sorted, .99), "max": bytes_sorted[-1],
                  "mean": round(statistics.mean(bytes_sorted), 1)},
        "manifest_bytes_median": pct(m_bytes, .50),
        "chunks": {"min": cc[0], "p25": pct(cc, .25), "median": pct(cc, .50),
                   "p75": pct(cc, .75), "p90": pct(cc, .90), "p99": pct(cc, .99),
                   "max": cc[-1], "mean": round(statistics.mean(cc), 3)},
        "chunk_count_histogram": hist,
        "pct_single_chunk": round(100.0 * sum(1 for c in chunk_counts if c == 1) / len(cc), 2),
        "pct_zero_chunk": round(100.0 * sum(1 for c in chunk_counts if c == 0) / len(cc), 2),
        "pct_multi_chunk": round(100.0 * sum(1 for c in chunk_counts if c > 1) / len(cc), 2),
    }

    print(f"\n  document bytes: median={report['bytes']['median']} "
          f"p90={report['bytes']['p90']} p99={report['bytes']['p99']} max={report['bytes']['max']}")
    print(f"  chunks/doc    : median={report['chunks']['median']} mean={report['chunks']['mean']} "
          f"p90={report['chunks']['p90']} p99={report['chunks']['p99']} max={report['chunks']['max']}")
    print(f"  histogram     : {hist}")
    print(f"  single-chunk docs: {report['pct_single_chunk']}%   "
          f"multi-chunk: {report['pct_multi_chunk']}%   zero-chunk: {report['pct_zero_chunk']}%")

    # ---- write a sampled corpus for the parity run ----------------------
    # Stratified by chunk count so the parity sample reflects the real distribution rather than
    # a convenient slice of it.
    sample = []
    for i, (text, c) in enumerate(zip(docs, chunk_counts)):
        sample.append({"doc_id": manifest[i]["doc_id"], "text": text, "n_chunks": c})
    (OUT_DIR / "mt10k_sample.json").write_text(json.dumps(sample[:2000]))
    print(f"\n  wrote first 2000 docs -> {OUT_DIR / 'mt10k_sample.json'}")

    OUT.write_text(json.dumps(report, indent=2))
    print(f"  written -> {OUT}")
    return 0 if corpus_verified else 1


if __name__ == "__main__":
    sys.exit(main())
