#!/usr/bin/env python3
"""(g) How many corpus documents actually contain a NUL in their EXTRACTED text?

One document is an anecdote; a few percent is a product issue. Scanning raw PDF bytes would be
meaningless — every PDF contains NULs in its binary streams. What matters is the text pypdf hands
to the pipeline.

A random sample rather than all 10,000: extraction is the expensive step, and a 1,000-document
sample bounds the prevalence tightly enough to answer "anecdote or product issue". The Wilson
interval is reported so the precision is explicit rather than implied.
"""
import json, math, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pypdf
from harness.resultio import write_result

ROOT = Path(__file__).resolve().parent.parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob("*.pdf"))
random.Random(20260810).shuffle(pdfs)
sample = pdfs[:N]

nul_docs, parsed, failed, empty = [], 0, 0, 0
printable_ratios = []
for i, f in enumerate(sample):
    try:
        r = pypdf.PdfReader(str(f))
        t = "\n".join((p.extract_text() or "") for p in r.pages)
    except Exception:
        failed += 1
        continue
    if not t.strip():
        empty += 1
        continue
    parsed += 1
    pr = sum(1 for c in t if c.isprintable() or c.isspace()) / max(1, len(t))
    printable_ratios.append((pr, f.name))
    if "\x00" in t:
        nul_docs.append({"name": f.name, "chars": len(t), "first_nul": t.index("\x00"),
                         "n_nul": t.count("\x00"), "printable_ratio": round(pr, 4),
                         "lost_frac": round(1 - t.index("\x00") / len(t), 4)})
    if (i + 1) % 200 == 0:
        print(f"  {i+1}/{len(sample)} scanned, {len(nul_docs)} with NUL", flush=True)

def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (max(0, c-h), min(1, c+h))

lo, hi = wilson(len(nul_docs), parsed)
res = {"sampled": len(sample), "parsed_with_text": parsed, "parse_failed": failed,
       "empty_extraction": empty, "docs_with_nul": len(nul_docs),
       "prevalence": round(len(nul_docs)/max(1,parsed), 5),
       "wilson95": [round(lo,5), round(hi,5)],
       "examples": nul_docs[:15],
       "printable_ratio_percentiles": {}}
pr = sorted(x for x,_ in printable_ratios)
for q in (0.001, 0.01, 0.05, 0.25, 0.5):
    res["printable_ratio_percentiles"][f"p{q*100:g}"] = round(pr[int(len(pr)*q)], 4)
res["lowest_printable_ratio_docs"] = [{"name": n, "printable_ratio": round(p,4)}
                                       for p, n in sorted(printable_ratios)[:10]]
p = write_result("nul_prevalence", res)
print(f"\n  sampled {len(sample)}, parsed-with-text {parsed}")
print(f"  documents containing NUL in extracted text: {len(nul_docs)} "
      f"({res['prevalence']*100:.2f}%, Wilson95 {lo*100:.2f}-{hi*100:.2f}%)")
print(f"  printable-ratio percentiles: {res['printable_ratio_percentiles']}")
print(f"  written -> {p.name}")
