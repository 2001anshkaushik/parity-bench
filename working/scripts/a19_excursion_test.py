#!/usr/bin/env python3
"""A19 — does a LlamaIndex block between two RocketRide blocks trigger the excursion?

RETROSPECTIVE CORRELATION (6/6, but confounded): every RocketRide block that followed a LlamaIndex
block in the same session showed the ~+30 % excursion (2/2); every block that did not showed
baseline (4/4). But the two sessions also differed in wall-clock time and in whether any
LlamaIndex process had ever run, so three variables moved together.

THIS ISOLATES ONE: RO -> LL -> RO, one session, same engine, never restarted.

  RO#2 shows the excursion  -> a neighbouring LlamaIndex block causes it. The excursion is HOST
                               contamination, not a RocketRide property, and the sizing guidance
                               changes: it is an artifact of co-tenancy in our harness.
  RO#2 stays at baseline    -> the LlamaIndex hypothesis is refuted and A19 stays open.

RULE 5: this hypothesis EXONERATES RocketRide, so it gets the hard scrutiny. The null result
(RO#2 at baseline) is the one that leaves the finding against RocketRide standing, and it is
reported just as prominently.

Host-level memory is sampled throughout, so whatever happens is attributable this time.
"""
import json, statistics, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "working"))
from harness.goodput import check_document, GoodputFailure
from harness.resultio import write_result
from weekend_worker import RocketArm, LlamaArm, rss_mb
from leak_vs_plateau import host_state, engine_pid, prewarm, sample   # noqa

N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
WARMUP = 50

def block(arm_name, bid, pdfs, epid):
    import pypdf
    arm = RocketArm(bid) if arm_name == "rocketride" else LlamaArm()
    st = {"block": bid, "arm": arm_name, "rss": [], "host": [], "engine_own": [], "task_tree": [],
          "goodput": 0, "faults": {}, "peak_rss_mb": 0.0}
    t0 = time.time(); i = 0
    try:
        while i < N_DOCS:
            f = pdfs[i]
            try:
                rd = pypdf.PdfReader(str(f)); text = "\n".join((p.extract_text() or "") for p in rd.pages)
            except Exception as e:
                st["faults"][f"parse:{type(e).__name__}"] = st["faults"].get(f"parse:{type(e).__name__}",0)+1
                i += 1; continue
            if not text.strip():
                st["faults"]["empty_extraction"] = st["faults"].get("empty_extraction",0)+1
                i += 1; continue
            try:
                ch, vc = arm.process(text); check_document(f.name, ch, vc); st["goodput"] += 1
            except GoodputFailure as e:
                k=f"goodput:{str(e).split(':')[-1].strip()[:30]}"; st["faults"][k]=st["faults"].get(k,0)+1
            except Exception as e:
                k=f"{arm_name}:{type(e).__name__}"; st["faults"][k]=st["faults"].get(k,0)+1
            i += 1
            if arm_name == "rocketride":
                own, tree, _ = sample(epid); total = own + tree
            else:
                own, tree, total = 0.0, 0.0, rss_mb()
            st["peak_rss_mb"] = max(st["peak_rss_mb"], total)
            if i % 5 == 0:
                st["rss"].append({"n": i, "rss_mb": round(total,1)})
                st["host"].append({"n": i, **host_state()})
                st["engine_own"].append({"n": i, "mb": round(own,1)})
                st["task_tree"].append({"n": i, "mb": round(tree,1)})
            if i % 500 == 0:
                h = host_state()
                print(f"    n={i} arm_total={total:.0f} host_used={h.get('host_used_mb',0):.0f} "
                      f"swap={h.get('swap_used_mb',0):.0f}", flush=True)
    finally:
        try: arm.close()
        except Exception: pass
    post=[x["rss_mb"] for x in st["rss"] if x["n"]>WARMUP]
    st["median"]=round(statistics.median(post),1) if post else None
    hp=[x for x in st["host"] if x["n"]>WARMUP]
    st["median_host_used_mb"]=round(statistics.median([x["host_used_mb"] for x in hp]),1) if hp else None
    st["max_swap_mb"]=round(max(x["swap_used_mb"] for x in hp),1) if hp else None
    st["elapsed_s"]=time.time()-t0
    print(f"  {bid} ({arm_name}): median {st['median']} MB  peak {st['peak_rss_mb']:.0f}  "
          f"host_used {st['median_host_used_mb']}  swap {st['max_swap_mb']}  "
          f"goodput {st['goodput']}  {st['elapsed_s']/60:.1f} min", flush=True)
    return st

def main():
    epid = engine_pid()
    import psutil
    print("="*92)
    print(f"A19 EXCURSION TEST — RO -> LL -> RO, one session, engine pid {epid} "
          f"(uptime {(time.time()-psutil.Process(epid).create_time())/3600:.1f} h, not restarted)")
    print(f"host at start: {host_state()}")
    print("="*92)
    pdfs = sorted((ROOT/"corpus"/"govdocs1"/"pdfs").glob("*.pdf"))
    out=[]
    for arm, bid in (("rocketride","a19_ro1"), ("llamaindex","a19_ll"), ("rocketride","a19_ro2")):
        print(f"--- {bid} ({arm}) ---", flush=True)
        prewarm(25)
        out.append(block(arm, bid, pdfs, epid))
    ro=[b for b in out if b["arm"]=="rocketride"]
    print("\n"+"="*92)
    print(f"  RO#1 (before any LlamaIndex) : {ro[0]['median']} MB")
    print(f"  RO#2 (after a LlamaIndex blk): {ro[1]['median']} MB")
    delta=(ro[1]['median']/ro[0]['median']-1)*100
    print(f"  delta: {delta:+.1f}%")
    baseline_hi = 2150   # the 4-block baseline cluster topped out at 2,112 MB
    verdict = ("EXCURSION REPRODUCED — a neighbouring LlamaIndex block triggers it; "
               "the excursion is host contamination, not a RocketRide property"
               if ro[1]['median'] and ro[1]['median'] > baseline_hi else
               "NO EXCURSION — the LlamaIndex-neighbour hypothesis is REFUTED; A19 stays open")
    print(f"  VERDICT: {verdict}")
    print(f"\n  host_used median: RO#1 {ro[0]['median_host_used_mb']} -> RO#2 {ro[1]['median_host_used_mb']} MB")
    print(f"  max swap:         RO#1 {ro[0]['max_swap_mb']} -> RO#2 {ro[1]['max_swap_mb']} MB")
    p=write_result("a19_excursion_test", {"blocks": out, "delta_pct": round(delta,1),
                                          "verdict": verdict})
    print(f"  written -> {p.name}")

if __name__ == "__main__":
    main()
