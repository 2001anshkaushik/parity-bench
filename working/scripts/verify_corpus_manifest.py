#!/usr/bin/env python3
"""Verify the corpus on disk against the committed per-file sha256 manifest.

The manifest (`working/results/corpus_manifest.jsonl`) is the corpus's identity: one line per file
with sha256, byte size, page count and pypdf-extracted char count. A benchmark on a corpus that
does not match its manifest byte-for-byte is a benchmark on a different corpus — hard fail, in
either direction (missing, extra, or changed files all fail).

SELECTION RULE (deterministic; a stranger executes this and gets a byte-identical corpus):
    GovDocs1 zip archives 000.zip .. 040.zip from
    https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/
    downloaded in ascending numeric order; every member whose name ends .pdf extracted and renamed
    <zip>_<member>; iteration stops when the count reaches 10,000 — which lands PARTWAY through
    040.zip (248 of its PDFs, in zip-namelist order). The sha256 manifest is therefore the
    authoritative cut, not the rule alone: verifying against it removes any dependence on zip
    iteration order.

Run:  ../.venv/bin/python working/scripts/verify_corpus_manifest.py
Exit: 0 = byte-identical corpus. 1 = any mismatch, listed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "working" / "results" / "corpus_manifest.jsonl"
PDFS = ROOT / "corpus" / "govdocs1" / "pdfs"


def main() -> int:
    if not MANIFEST.exists():
        print(f"FATAL: manifest not found at {MANIFEST}")
        return 2
    want = {}
    for line in MANIFEST.read_text().splitlines():
        r = json.loads(line)
        want[r["file"]] = r
    have = {p.name: p for p in PDFS.glob("*.pdf")}

    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = []
    for name, rec in sorted(want.items()):
        p = have.get(name)
        if p is None:
            continue
        if p.stat().st_size != rec["bytes"]:
            changed.append((name, "size"))
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest() != rec["sha256"]:
            changed.append((name, "sha256"))

    ok = not (missing or extra or changed)
    print(f"manifest entries : {len(want)}")
    print(f"files on disk    : {len(have)}")
    print(f"missing          : {len(missing)}" + (f"  e.g. {missing[:3]}" if missing else ""))
    print(f"extra            : {len(extra)}" + (f"  e.g. {extra[:3]}" if extra else ""))
    print(f"changed          : {len(changed)}" + (f"  e.g. {changed[:3]}" if changed else ""))
    print("VERDICT: " + ("MATCH — corpus is byte-identical to the manifest" if ok else "MISMATCH"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
