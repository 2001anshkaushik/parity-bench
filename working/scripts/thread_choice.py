#!/usr/bin/env python3
"""STEP 1 — establish each arm's BEST thread setting at concurrency 1 sequential.

"Default" is the absence of a configuration, not a configuration, and two stacks' defaults are not
matched by construction. So the matched setting has to be chosen on evidence: for each arm, which
setting is faster at the concurrency we will actually run?

RocketRide already has this measured (reanchor, concurrency 1): pinned 25.78 /s vs default
46.92 /s at 400 tokens — default wins by 1.82x. This script supplies the missing half for
LlamaIndex, on the ACTUAL corpus rather than synthetic text, interleaved and repeated.

Throughput on this host is not quotable in absolute terms (open item A13). That does not block this
decision: we are comparing one arm against ITSELF, back to back in one session, on identical
documents. A within-session self-comparison is the one thing this host can still answer.
"""
import json, os, statistics, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 40
REPS = 3

RUNNER = r'''
import sys, os, time, json
sys.path.insert(0, %r); sys.path.insert(0, %r)
import pypdf
from ws1.pipeline import LlamaIndexPipeline
import torch
p = LlamaIndexPipeline(model_name="sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
                       chunk_size=4000, chunk_overlap=200, device="cpu")
p.warm()
pdfs = sorted((__import__("pathlib").Path(%r)).glob("*.pdf"))[:%d]
texts = []
for f in pdfs:
    try:
        r = pypdf.PdfReader(str(f)); t = "\n".join((x.extract_text() or "") for x in r.pages)
        if t.strip(): texts.append(t)
    except Exception: pass
p.process(texts[0])                      # warm the encode path
t0 = time.time(); n = 0
for t in texts:
    p.process(t); n += 1
el = time.time() - t0
print(json.dumps({"threads": torch.get_num_threads(), "docs": n, "sec": el, "rate": n/el}))
''' % (str(ROOT), str(ROOT / "working"), str(ROOT / "corpus" / "govdocs1" / "pdfs"), N_DOCS)

def run(pinned: bool):
    env = dict(os.environ)
    keys = ["OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS","TORCH_NUM_THREADS"]
    for k in keys: env.pop(k, None)
    if pinned:
        for k in keys: env[k] = "1"
    out = subprocess.run([str(ROOT.parent/".venv"/"bin"/"python"), "-c", RUNNER],
                         capture_output=True, text=True, env=env, cwd=str(ROOT))
    for ln in out.stdout.splitlines():
        if ln.startswith("{"):
            return json.loads(ln)
    raise RuntimeError(out.stdout[-300:] + out.stderr[-300:])

print(f"LlamaIndex, concurrency 1 sequential, {N_DOCS} real GovDocs PDFs, interleaved pinned/unpinned")
res = {"pinned": [], "unpinned": []}
for i in range(REPS):
    for kind in (("pinned","unpinned") if i % 2 == 0 else ("unpinned","pinned")):
        r = run(kind == "pinned")
        res[kind].append(r)
        print(f"  rep{i} {kind:9s} torch_threads={r['threads']:2d} {r['docs']} docs in {r['sec']:6.1f}s = {r['rate']:.3f} docs/s")
for k in res:
    v = [x["rate"] for x in res[k]]
    sp = (max(v)-min(v))/max(v)
    print(f"\n  {k:9s} median {statistics.median(v):.3f} docs/s  spread {sp*100:.1f}%  "
          f"threads={res[k][0]['threads']}  {'GATE OK' if sp<=0.10 else 'GATE FAIL'}")
mp = statistics.median([x["rate"] for x in res["pinned"]])
mu = statistics.median([x["rate"] for x in res["unpinned"]])
print(f"\n  unpinned / pinned = {mu/mp:.2f}x  ->  BEST SETTING AT CONCURRENCY 1: "
      f"{'UNPINNED (default threads)' if mu > mp else 'PINNED (1 thread)'}")
sys.path.insert(0, str(ROOT/"working"))
from harness.resultio import write_result
print(f"  written -> {write_result('thread_choice_llamaindex', res).name}")
