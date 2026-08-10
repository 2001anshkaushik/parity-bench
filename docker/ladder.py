#!/usr/bin/env python3
"""Container ladder run: 100 -> 1,000 -> 10,000 PDFs, checkpointed.

This is a STABILITY, WIRING and MEMORY-ENDURANCE demo. It is NOT a speed test: throughput from
this host is invalid because ascending-load measurements here profile a machine in a low-power
state (open item A13), so docs/sec is recorded for completeness and must not be quoted.

What it does establish:
  * goodput — every document really produced non-empty chunks and unit-norm 384-d vectors,
    asserted per document. A PDF path with no reader registered returns {} silently and would
    otherwise yield 10,000 HTTP 200s with flat memory and zero work.
  * memory endurance — peak RSS and the RSS-over-time slope, which is the axis A13 does not touch
    and the one leadership actually asked about.
  * fault isolation — malformed PDFs are CLASSIFIED, not filtered. GovDocs1 is genuinely messy;
    the failures are part of the corpus, not noise to remove.

Checkpoints after every rung and every 250 documents, so a failure at document 8,000 costs
minutes rather than the whole run.
"""
from __future__ import annotations

import json, os, resource, sys, time, traceback
from pathlib import Path

sys.path.insert(0, "/app")
from harness.goodput import check_document, GoodputFailure   # noqa: E402

CORPUS = Path(os.environ.get("LADDER_CORPUS", "/corpus"))
OUT = Path(os.environ.get("LADDER_OUT", "/app/out"))
RUNGS = [int(x) for x in os.environ.get("LADDER_RUNGS", "100,1000,10000").split(",")]
ARM = os.environ.get("LADDER_ARM", "llamaindex")
SAMPLE_EVERY = 25


def rss_mb() -> float:
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return kb / 1024.0            # linux reports kB


def cur_rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for ln in f:
                if ln.startswith("VmRSS:"):
                    return int(ln.split()[1]) / 1024.0
    except Exception:
        pass
    return rss_mb()


def cgroup_limit_mb() -> float:
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = Path(p).read_text().strip()
            if v.isdigit():
                return int(v) / 1e6
        except Exception:
            pass
    return -1.0


def main() -> int:
    import platform
    # ARCH ASSERTION 3 — refuse to produce numbers under emulation
    if platform.machine() != "aarch64":
        sys.stderr.write(f"ARCH ASSERT FAILED at runtime: {platform.machine()}\n")
        return 3
    OUT.mkdir(parents=True, exist_ok=True)

    from ws1.pipeline import LlamaIndexPipeline
    import pypdf

    env = {k: os.environ.get(k) for k in
           ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "TORCH_NUM_THREADS", "WS1_DEVICE")}
    import torch
    # DECLARED != MEASURED: report what torch actually got inside the quota
    meta = {"arch": platform.machine(), "python": platform.python_version(),
            "env_declared": env, "torch_intra": torch.get_num_threads(),
            "torch_interop": torch.get_num_interop_threads(),
            "os_cpu_count": os.cpu_count(),
            "cgroup_mem_limit_mb": cgroup_limit_mb(),
            "image_digest": os.environ.get("IMAGE_DIGEST", "unset"), "arm": ARM}
    print(json.dumps(meta), flush=True)

    pipe = LlamaIndexPipeline(model_name="sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
                         chunk_size=4000, chunk_overlap=200, device="cpu")
    pipe.warm()
    print(f"[warm] rss={cur_rss_mb():.0f}MB", flush=True)

    pdfs = sorted(CORPUS.glob("*.pdf"))
    if not pdfs:
        sys.stderr.write(f"NO PDFS in {CORPUS}\n")
        return 4
    print(f"[corpus] {len(pdfs)} distinct pdfs available", flush=True)

    results = {"meta": meta, "distinct_pdfs": len(pdfs), "rungs": {}}
    faults = {}
    evidence = []
    rss_series = []
    t_start = time.time()
    processed = 0

    for rung in RUNGS:
        r0 = time.time()
        while processed < rung:
            src = pdfs[processed % len(pdfs)]     # cycle if the corpus is smaller than the rung
            doc_id = f"{processed:06d}_{src.name}"
            try:
                reader = pypdf.PdfReader(str(src))
                text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
            except Exception as e:
                faults[f"parse:{type(e).__name__}"] = faults.get(f"parse:{type(e).__name__}", 0) + 1
                processed += 1
                continue
            if not text.strip():
                faults["empty_extraction"] = faults.get("empty_extraction", 0) + 1
                processed += 1
                continue
            try:
                res = pipe.process(text)
                ev = check_document(doc_id, res.chunks, res.embeddings)
                evidence.append(ev)
            except GoodputFailure as e:
                # LOUD: goodput failure aborts the run. A run with a failed document is not a run.
                sys.stderr.write(f"GOODPUT FAILURE at {doc_id}: {e}\n")
                results["goodput_failure"] = str(e)
                (OUT / f"ladder_{ARM}_FAILED.json").write_text(json.dumps(results, indent=1))
                return 5
            except Exception as e:
                faults[f"embed:{type(e).__name__}"] = faults.get(f"embed:{type(e).__name__}", 0) + 1
            processed += 1
            if processed % SAMPLE_EVERY == 0:
                rss_series.append({"n": processed, "t": round(time.time() - t_start, 1),
                                   "rss_mb": round(cur_rss_mb(), 1)})
            if processed % 250 == 0:
                (OUT / f"ladder_{ARM}_checkpoint.json").write_text(json.dumps(
                    {**results, "processed": processed, "rss_series": rss_series,
                     "faults": faults}, indent=1))
                print(f"[ckpt] n={processed} rss={cur_rss_mb():.0f}MB "
                      f"peak={rss_mb():.0f}MB faults={sum(faults.values())}", flush=True)
        el = time.time() - r0
        ok = len(evidence)
        results["rungs"][str(rung)] = {
            "documents": rung, "elapsed_s": round(el, 1),
            "docs_per_s_DO_NOT_QUOTE": round(rung / el, 2) if el else None,
            "goodput_docs": ok, "faults": dict(faults),
            "fault_rate": round(sum(faults.values()) / rung, 5),
            "peak_rss_mb": round(rss_mb(), 1), "rss_end_mb": round(cur_rss_mb(), 1),
            "chunks_total": sum(e["n_chunks"] for e in evidence),
        }
        print(f"[rung {rung}] {el:.0f}s  goodput={ok}  faults={sum(faults.values())}  "
              f"peak_rss={rss_mb():.0f}MB", flush=True)
        (OUT / f"ladder_{ARM}_rung{rung}.json").write_text(json.dumps(results, indent=1))

    # leak slope over the last 60% of the run: a flat slope is the endurance claim
    tail = rss_series[int(len(rss_series) * 0.4):]
    if len(tail) > 2:
        n0, n1 = tail[0]["n"], tail[-1]["n"]
        slope = (tail[-1]["rss_mb"] - tail[0]["rss_mb"]) / max(1, (n1 - n0)) * 1000
        results["leak_slope_mb_per_1000_docs"] = round(slope, 2)
    results["rss_series"] = rss_series
    results["faults"] = faults
    results["wall_s"] = round(time.time() - t_start, 1)
    (OUT / f"ladder_{ARM}_final.json").write_text(json.dumps(results, indent=1))
    print(json.dumps({k: v for k, v in results.items() if k != "rss_series"}, indent=1)[:1400],
          flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MemoryError:
        sys.stderr.write("MemoryError — container hit its limit\n"); sys.exit(6)
    except Exception:
        traceback.print_exc(); sys.exit(1)
