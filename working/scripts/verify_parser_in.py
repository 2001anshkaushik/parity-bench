import asyncio, json, os, sys, time, uuid, statistics as st
from pathlib import Path
ROOT = Path("/Users/ansh/RocketRide/Benchmarking/benchmark-A")
os.chdir(ROOT); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"working"))
from weekend_worker import RocketPdfArm, LlamaHttpPdfArm
from harness import ws1_service as ws
from harness.chunk_hash import check_chunks, ChunkHashMismatch
from harness.extraction_fidelity import fidelity, summarise
from harness.goodput import check_document, GoodputFailure
from rocketride import RocketRideClient

async def engine_extract(pdf: Path) -> str:
    base = json.loads((ROOT/"working"/"pipes"/"extract_only.pipe").read_text())
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ex-{os.getpid()}-{time.time()}"))
    p = ROOT/"working"/"pipes"/"generated"/"verify_extract.pipe"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(base))
    c = RocketRideClient(); await c.connect(timeout=60000)
    tok = (await c.use(filepath=str(p.relative_to(ROOT))))["token"]
    try:
        out = await asyncio.wait_for(c.send(tok, pdf.read_bytes(), mimetype="application/pdf"), timeout=300)
        t = out.get("text")
        return ("\n".join(map(str, t)) if isinstance(t, list) else t) or ""
    finally:
        try: await asyncio.wait_for(c.terminate(tok), timeout=60)
        except Exception: pass
        await c.disconnect()

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
pdfs = sorted((ROOT/"corpus"/"govdocs1"/"pdfs").glob("*.pdf"))[:N]
print(f"docs: {len(pdfs)}")

h = ws.start(workers=1, port=8811, threads=10); ws.wait_warm(h, timeout=900)
thr = sorted(set(h.measured_threads.values()))
print(f"service warm: {len(h.warm_pids)}/1  torch={thr}")
li = LlamaHttpPdfArm(port=8811)
rr = RocketPdfArm("verify")
res = {"li": {"ok":0,"gate_fail":0,"faults":{}}, "rr": {"ok":0,"gate_fail":0,"faults":{}}}
fid_rows = []
try:
    for f in pdfs:
        b = f.read_bytes()
        # ---- LlamaIndex arm
        try:
            ch, em = li.process(b)
            out = getattr(li, "last", {}) or {}
            if not out.get("ok"):
                k = out.get("error_class", "unknown"); res["li"]["faults"][k] = res["li"]["faults"].get(k,0)+1
            else:
                check_document(f.name, ch, em)
                check_chunks(f.name, ch, out.get("extracted_text",""))   # PER-ARM reference
                res["li"]["ok"] += 1
        except ChunkHashMismatch as e:
            res["li"]["gate_fail"] += 1; print(f"  LI hash-gate {f.name}: {str(e)[:90]}")
        except GoodputFailure as e:
            k=f"goodput"; res["li"]["faults"][k]=res["li"]["faults"].get(k,0)+1
        except Exception as e:
            k=f"err:{type(e).__name__}"; res["li"]["faults"][k]=res["li"]["faults"].get(k,0)+1
        # ---- RocketRide arm
        try:
            ch, em = rr.process(b)
            if not ch:
                res["rr"]["faults"]["no_documents"] = res["rr"]["faults"].get("no_documents",0)+1
            else:
                check_document(f.name, ch, em)
                eng_text = asyncio.run(engine_extract(f))              # PER-ARM reference
                check_chunks(f.name, ch, eng_text)
                res["rr"]["ok"] += 1
                py_text = (getattr(li,"last",{}) or {}).get("extracted_text","")
                if py_text: fid_rows.append(fidelity(eng_text, py_text, "engine", "pypdf"))
        except ChunkHashMismatch as e:
            res["rr"]["gate_fail"] += 1; print(f"  RR hash-gate {f.name}: {str(e)[:110]}")
        except GoodputFailure as e:
            res["rr"]["faults"]["goodput"]=res["rr"]["faults"].get("goodput",0)+1
        except Exception as e:
            k=f"err:{type(e).__name__}"; res["rr"]["faults"][k]=res["rr"]["faults"].get(k,0)+1
finally:
    li.close(); rr.close(); ws.stop(h)

print(f"\nLlamaIndex-pdf : ok={res['li']['ok']} hash-gate-fail={res['li']['gate_fail']} faults={res['li']['faults']}")
print(f"RocketRide-pdf : ok={res['rr']['ok']} hash-gate-fail={res['rr']['gate_fail']} faults={res['rr']['faults']}")
if fid_rows:
    s = summarise(fid_rows)
    print(f"\nCROSS-ARM EXTRACTION FIDELITY (reported, not gated), n={s['n_docs']}")
    for k in ("char_ratio","seq_similarity","word_jaccard"):
        q=s[k]; print(f"  {k:16s} median {q['median']:.4f}  p10 {q['p10']:.4f}  p90 {q['p90']:.4f}  min {q['min']:.4f}")
    from collections import Counter
    print("  readings:", dict(Counter(r["reading"] for r in fid_rows)))
