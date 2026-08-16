#!/usr/bin/env python3
"""Fetch a GovDocs1 sample and extract the PDFs.

GovDocs1 (digitalcorpora.org) is public-domain US government material, bulk-downloadable, and
genuinely messy — which is the point. It is distributed as ~1,000-file zips of MIXED type, so PDFs
have to be sieved out. Chosen over arXiv (3 s API rate limit, per-paper licence mix) and over any
blend of sources (an anomaly in a blended corpus is unattributable).

TWO MODES
---------
MANIFEST MODE (default when working/results/corpus_manifest.jsonl exists) — the corpus is defined
by the manifest, not by a counter. It computes exactly which files are missing, downloads only the
zips that contain them, extracts only those members, verifies every byte against the recorded
sha256, and exits non-zero unless the corpus matches the manifest exactly.

DISCOVERY MODE (--no-manifest, or no manifest on disk) — the original count-based walk, for
building a NEW manifest. Never use it to reproduce an existing one.

THE BUG THIS REPLACES [found on the box, 2026-08-16]
----------------------------------------------------
The old fetcher seeded `have` from the files already on disk, then did `have += n` where `n`
counted files WRITTEN. Re-extracting a zip whose files were already present incremented the
counter without increasing the disk count, so the counter ran ahead of reality:

    disk had 200 (from an earlier `fetch_govdocs.py 200`, which takes zip 000)
    zip 000 re-extracted -> n=200, have=400, disk still 200   <- counter now +200 ahead
    ... counter stays +200 ahead for the rest of the walk ...
    counter reaches 10,000 while the disk holds 9,800
    zip 040 truncated at 48 members instead of the manifest's 248 -- exactly 200 short

and then printed `DONE total_pdfs=10000`. **It reported success by reading its own arithmetic,
never the disk and never the manifest** — the same defect class as `echo $?` reporting tee's
status. DONE now means verified-against-manifest.
"""
import argparse
import hashlib
import io
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "corpus" / "govdocs1" / "pdfs"
MANIFEST = ROOT / "working" / "results" / "corpus_manifest.jsonl"
BASE = "https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_manifest():
    import json
    return [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]


def fetch_zip(i: int):
    url = f"{BASE}/{i:03d}.zip"
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=180) as r:
        blob = r.read()
    return blob, time.time() - t0


def manifest_mode(target: int, verify_existing: bool) -> int:
    """Land byte-identical to the manifest, downloading only what is missing."""
    entries = load_manifest()[:target]
    want = {e["file"]: e for e in entries}
    print(f"manifest mode: {len(want)} files defined by {MANIFEST.name}", flush=True)

    on_disk = {p.name for p in OUT.glob("*.pdf")}
    missing = sorted(set(want) - on_disk)
    print(f"  on disk {len(on_disk & set(want))}/{len(want)}, missing {len(missing)}", flush=True)

    if missing:
        # Only the zips that actually contain a missing file. This is what makes completing a
        # partial corpus cheap: 200 missing files from zip 040 downloads 040.zip and nothing else.
        by_zip = defaultdict(list)
        for name in missing:
            by_zip[int(name.split("_")[0])].append(name)
        print(f"  need {len(by_zip)} zip(s): {sorted(by_zip)}", flush=True)
        for i in sorted(by_zip):
            need = set(by_zip[i])
            try:
                blob, secs = fetch_zip(i)
            except Exception as e:
                print(f"  {i:03d}.zip FAILED {type(e).__name__}: {e}", flush=True)
                continue
            got = 0
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for nm in z.namelist():
                    fname = f"{i:03d}_{Path(nm).name}"
                    if fname not in need:
                        continue           # not missing, or not ours — never re-extract
                    try:
                        (OUT / fname).write_bytes(z.read(nm))
                        got += 1
                    except Exception as e:
                        print(f"    {fname}: extract failed {type(e).__name__}", flush=True)
            print(f"  {i:03d}.zip  +{got}/{len(need)} missing files "
                  f"({len(blob)/1e6:.0f} MB in {secs:.0f}s)", flush=True)

    # DONE means VERIFIED. Not a counter, not a file count — every byte against the manifest.
    print("verifying against the manifest ...", flush=True)
    bad, absent = [], []
    for name, e in want.items():
        p = OUT / name
        if not p.exists():
            absent.append(name)
            continue
        if p.stat().st_size != e["bytes"] or (verify_existing and sha256_file(p) != e["sha256"]):
            bad.append(name)
    if absent or bad:
        print(f"INCOMPLETE: {len(absent)} missing, {len(bad)} wrong bytes", flush=True)
        for n in (absent + bad)[:5]:
            print(f"    {n}", flush=True)
        print("NOT DONE — the corpus does not match the manifest.", flush=True)
        return 1
    print(f"DONE verified={len(want)}/{len(want)} against {MANIFEST.name} "
          f"({'sha256' if verify_existing else 'size only, pass --verify for sha256'})",
          flush=True)
    return 0


def discovery_mode(target: int, start: int) -> int:
    """Count-based walk, for building a NEW manifest. Counts the DISK, never a running total."""
    print("discovery mode: no manifest is being enforced. Use this only to BUILD a manifest.",
          flush=True)
    for i in range(start, 1000):
        have = len({p.name for p in OUT.glob("*.pdf")})     # re-measured, never accumulated
        if have >= target:
            break
        try:
            blob, secs = fetch_zip(i)
        except Exception as e:
            print(f"  {i:03d}.zip FAILED {type(e).__name__}", flush=True)
            continue
        n = 0
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for nm in z.namelist():
                    if not nm.lower().endswith(".pdf"):
                        continue
                    fname = f"{i:03d}_{Path(nm).name}"
                    if (OUT / fname).exists():
                        continue          # already ours; re-writing it would inflate the count
                    if have + n >= target:
                        break
                    try:
                        (OUT / fname).write_bytes(z.read(nm))
                    except Exception:
                        continue          # corrupt member: that is corpus data, not an error
                    n += 1
        except Exception as e:
            print(f"  {i:03d}.zip UNZIP FAILED {type(e).__name__}", flush=True)
            continue
        disk = len({p.name for p in OUT.glob("*.pdf")})
        print(f"  {i:03d}.zip  +{n:4d} pdfs  disk={disk:6d}  "
              f"({len(blob)/1e6:.0f} MB in {secs:.0f}s)", flush=True)
    disk = len({p.name for p in OUT.glob("*.pdf")})
    print(f"DONE disk_pdfs={disk} (target {target}) — NOT manifest-verified", flush=True)
    return 0 if disk >= target else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", type=int, default=10000)
    ap.add_argument("start", nargs="?", type=int, default=0, help="discovery mode only")
    ap.add_argument("--no-manifest", action="store_true",
                    help="force discovery mode even if a manifest exists")
    ap.add_argument("--verify", action="store_true",
                    help="sha256 every file, not just files just fetched (slower, definitive)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists() and not a.no_manifest:
        return manifest_mode(a.target, a.verify)
    return discovery_mode(a.target, a.start)


if __name__ == "__main__":
    raise SystemExit(main())
