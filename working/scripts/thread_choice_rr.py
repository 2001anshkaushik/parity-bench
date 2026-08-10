#!/usr/bin/env python3
"""STEP 1, RocketRide half — same method as thread_choice.py, on the same corpus.

Existing evidence for RocketRide (reanchor: 46.92 /s default vs 25.78 /s pinned at concurrency 1)
was measured on 400-token synthetic text. Citing that while measuring LlamaIndex fresh would
reintroduce exactly the asymmetry this run exists to remove, so it is re-measured here on the
GovDocs corpus with the same interleaving and repetition.
"""
import json, os, statistics, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"working"))
N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
REPS = 3
KEYS = ["OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS","TORCH_NUM_THREADS"]

def restart(pinned: bool) -> int:
    subprocess.run(["bash", str(ROOT/"working"/"scripts"/"stop_engine.sh")], capture_output=True)
    time.sleep(3)
    env = dict(os.environ); env["CPU_PROBE_ITERS"]="235000"
    for k in KEYS: env.pop(k, None)
    if pinned:
        for k in KEYS: env[k]="1"
    r = subprocess.run(["bash", str(ROOT/"working"/"scripts"/"start_engine.sh")],
                       capture_output=True, env=env, text=True)
    if "healthy" not in r.stdout: raise RuntimeError(r.stdout[-300:])
    time.sleep(2)
    # DECLARED != MEASURED
    q = subprocess.run([str(ROOT.parent/".venv"/"bin"/"python"),
                        str(ROOT/"working"/"scripts"/"probe_env.py"), f"tc{int(time.time())}"],
                       capture_output=True, text=True, cwd=str(ROOT))
    got = json.loads(q.stdout)["torch_num_threads"]
    want = 1 if pinned else 10
    if got != want: raise RuntimeError(f"thread gate: wanted {want}, task process reports {got}")
    return got

def measure(n_docs):
    import asyncio, uuid, pypdf
    from rocketride import RocketRideClient
    pdfs = sorted((ROOT/"corpus"/"govdocs1"/"pdfs").glob("*.pdf"))[:n_docs]
    texts=[]
    for f in pdfs:
        try:
            r=pypdf.PdfReader(str(f)); t="\n".join((x.extract_text() or "") for x in r.pages)
            if t.strip(): texts.append(t)
        except Exception: pass
    async def go():
        base=json.loads((ROOT/"working"/"pipes"/"embed_probe.pipe").read_text())
        base["project_id"]=str(uuid.uuid5(uuid.NAMESPACE_DNS,f"tc-{os.getpid()}-{time.time()}"))
        p=ROOT/"working"/"pipes"/"generated"/f"tc_{os.getpid()}.pipe"; p.write_text(json.dumps(base))
        c=RocketRideClient(); await c.connect(timeout=60000)
        tok=(await c.use(filepath=str(p.relative_to(ROOT))))["token"]
        await asyncio.wait_for(c.send(tok,texts[0],mimetype="text/plain"),timeout=600)  # warm
        t0=time.time(); n=0
        for t in texts:
            await asyncio.wait_for(c.send(tok,t,mimetype="text/plain"),timeout=1800); n+=1
        el=time.time()-t0
        try: await asyncio.wait_for(c.terminate(tok),timeout=60)
        except Exception: pass
        await c.disconnect()
        return {"docs":n,"sec":el,"rate":n/el}
    return asyncio.run(go())

print(f"RocketRide, concurrency 1 sequential, {N_DOCS} real GovDocs PDFs, interleaved")
res={"pinned":[],"unpinned":[]}
for i in range(REPS):
    for kind in (("pinned","unpinned") if i%2==0 else ("unpinned","pinned")):
        th=restart(kind=="pinned")
        r=measure(N_DOCS); r["threads"]=th; res[kind].append(r)
        print(f"  rep{i} {kind:9s} torch_threads={th:2d} {r['docs']} docs in {r['sec']:6.1f}s = {r['rate']:.3f} docs/s",flush=True)
for k in res:
    v=[x["rate"] for x in res[k]]; sp=(max(v)-min(v))/max(v)
    print(f"\n  {k:9s} median {statistics.median(v):.3f} docs/s  spread {sp*100:.1f}%  "
          f"{'GATE OK' if sp<=0.10 else 'GATE FAIL'}")
mp=statistics.median([x["rate"] for x in res["pinned"]]); mu=statistics.median([x["rate"] for x in res["unpinned"]])
print(f"\n  unpinned / pinned = {mu/mp:.2f}x  ->  BEST AT CONCURRENCY 1: "
      f"{'UNPINNED (default threads)' if mu>mp else 'PINNED'}")
from harness.resultio import write_result
print(f"  written -> {write_result('thread_choice_rocketride',res).name}")
