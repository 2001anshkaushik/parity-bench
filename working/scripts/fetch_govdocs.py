#!/usr/bin/env python3
"""Fetch a GovDocs1 sample and extract the PDFs.

GovDocs1 (digitalcorpora.org) is public-domain US government material, bulk-downloadable, and
genuinely messy — which is the point. It is distributed as ~1,000-file zips of MIXED type, so PDFs
have to be sieved out. Chosen over arXiv (3 s API rate limit, per-paper licence mix) and over any
blend of sources (an anomaly in a blended corpus is unattributable).
"""
import io, sys, time, zipfile, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "corpus" / "govdocs1" / "pdfs"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles"
target = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0

have = len(list(OUT.glob("*.pdf")))
for i in range(start, 1000):
    if have >= target:
        break
    url = f"{BASE}/{i:03d}.zip"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            blob = r.read()
    except Exception as e:
        print(f"  {i:03d}.zip FAILED {type(e).__name__}", flush=True)
        continue
    n = 0
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for nm in z.namelist():
                if not nm.lower().endswith(".pdf"):
                    continue
                if have + n >= target:
                    break
                try:
                    data = z.read(nm)
                except Exception:
                    continue          # corrupt member: that is corpus data, not an error
                (OUT / f"{i:03d}_{Path(nm).name}").write_bytes(data)
                n += 1
    except Exception as e:
        print(f"  {i:03d}.zip UNZIP FAILED {type(e).__name__}", flush=True)
        continue
    have += n
    print(f"  {i:03d}.zip  +{n:4d} pdfs  total={have:6d}  "
          f"({len(blob)/1e6:.0f} MB in {time.time()-t0:.0f}s)", flush=True)
print(f"DONE total_pdfs={have}")
