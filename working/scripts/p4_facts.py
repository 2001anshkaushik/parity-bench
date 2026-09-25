#!/usr/bin/env python3
"""P4-B (4) CTO facts sheet: every claimable figure of the parity campaign (P0-P4) with its source artifact (a committed
analysis file and the key inside it), session (boot id), n and one caveat line. Every value is READ from the named
artifact here (never typed), so the sheet traces mechanically; withdrawn figures are not listed.

    p4_facts.py <p4_campaign_dir>  -> P4_FACTS_SHEET.md + p4_facts.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, List

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "working" / "results"
P0, P1 = "parity_p0_20260923T083031Z", "parity_p1_20260923T184000Z"
P2, P3 = "parity_p2_20260924T160106Z", "parity_p3_20260925T035027Z"
_cache: dict = {}
FACTS: List[dict] = []


def J(camp: str, f: str) -> Any:
    k = (camp, f)
    if k not in _cache:
        _cache[k] = json.loads((RES / camp / f).read_text())
    return _cache[k]


def at(camp: str, f: str, path: str) -> Any:
    x = J(camp, f)
    for p in path.split("."):
        x = x[int(p)] if isinstance(x, list) else x[p]
    return x


def fact(area: str, figure: str, value: str, camp: str, f: str, keys: str, session: str, n: str, caveat: str) -> None:
    FACTS.append({"id": f"F{len(FACTS) + 1:02d}", "area": area, "figure": figure, "value": value,
                  "source": f"working/results/{camp}/{f}", "keys": keys, "session": session, "n": n, "caveat": caveat})


def pct(x: float, d: int = 2) -> str:
    return f"{x * 100:+.{d}f}%"


def main() -> int:
    p4 = Path(sys.argv[1])
    P4 = p4.name
    s3 = at(P3, "analysis_p3docs.json", "legs.p3a_rr_full.boot_id")[:8]
    A = "P3_A.full"
    # ------------------------------------------------ docs: parity at full scale (P3-A)
    fact("docs parity", "RocketRide, one token, full corpus (9,975): span docs/s", f"{at(P3, 'analysis_p3docs.json', A + '.rr_docs_per_s'):.4f}",
         P3, "analysis_p3docs.json", A + ".rr_docs_per_s", s3, "1 run",
         "requires the UNSHIPPED P1-B Tika wrapper fix (image rr:p1-tikafix); banked posture (six thread vars = 1)")
    fact("docs parity", "LlamaIndex, 24 workers, full corpus: span docs/s", f"{at(P3, 'analysis_p3docs.json', A + '.li_docs_per_s'):.4f}",
         P3, "analysis_p3docs.json", A + ".li_docs_per_s", s3, "1 run", "LlamaIndex's measured optimum (24 workers, C=32), same session")
    fact("docs parity", "RocketRide / LlamaIndex, full corpus", f"{at(P3, 'analysis_p3docs.json', A + '.ratio_rr_over_li'):.3f}",
         P3, "analysis_p3docs.json", A + ".ratio_rr_over_li", s3, "1 run per arm",
         "MATCHES, NOT BEATS: the margin is inside LlamaIndex's 8.19% replicate spread; needs the unshipped fix")
    fact("docs parity", "the same ratio excluding the eleven pathological PDFs", f"{at(P3, 'analysis_p3docs.json', A + '.excluded_straggler.ratio_rr_over_li'):.3f}",
         P3, "analysis_p3docs.json", A + ".excluded_straggler.ratio_rr_over_li", s3, "1 run per arm", "with the fix the eleven no longer move the ratio")
    for arm, lab in (("rr", "RocketRide"), ("li", "LlamaIndex")):
        pa = f"{A}.per_arm.{arm}"
        fact("docs cost", f"{lab} CPU-s per document (full corpus)", f"{at(P3, 'analysis_p3docs.json', pa + '.cpu_s_per_doc'):.3f}",
             P3, "analysis_p3docs.json", pa + ".cpu_s_per_doc", s3, "1 run", "service container CPU over the leg window / ok documents")
    for arm, lab in (("rr", "RocketRide"), ("li", "LlamaIndex")):
        pa = f"{A}.per_arm.{arm}"
        fact("docs cost", f"{lab} service cores (full corpus)", f"{at(P3, 'analysis_p3docs.json', pa + '.engine_cores'):.2f}",
             P3, "analysis_p3docs.json", pa + ".engine_cores", s3, "1 run", "of 32 vCPU, unconstrained (Ruling A)")
    for arm, lab in (("rr", "RocketRide"), ("li", "LlamaIndex")):
        pa = f"{A}.per_arm.{arm}"
        fact("docs cost", f"{lab} idle spin, cores burned with nothing submitted", f"{at(P3, 'analysis_p3docs.json', pa + '.idle_spin_cores'):.3f}",
             P3, "analysis_p3docs.json", pa + ".idle_spin_cores", s3, "1 run", "measured before the leg; never added back to throughput; source untraced")
    for arm, lab in (("rr", "RocketRide"), ("li", "LlamaIndex")):
        pa = f"{A}.per_arm.{arm}"
        fact("docs cost", f"{lab} sampled memory peak (total), MB", f"{at(P3, 'analysis_p3docs.json', pa + '.memory.peak_bytes.total') / 1e6:,.0f}",
             P3, "analysis_p3docs.json", pa + ".memory.peak_bytes.total", s3, "1 run", "1 Hz sampler over the leg window (MB = bytes / 1e6)")
    for arm, lab in (("rr", "RocketRide"), ("li", "LlamaIndex")):
        pa = f"{A}.per_arm.{arm}"
        fact("docs output", f"{lab} empty documents of 9,975", f"{at(P3, 'analysis_p3docs.json', pa + '.lost_documents.n')}",
             P3, "analysis_p3docs.json", pa + ".lost_documents.n", s3, "1 run", "a document is empty if not ok or zero chunks")
    # ------------------------------------------------ docs: out of box and the fix (P1-B)
    s1 = at(P1, "analysis_p1docs.json", "legs.p1b_base_full.boot_id")[:8]
    fact("docs out of box", "stock rr:patched, one token, full corpus: span docs/s", f"{at(P1, 'analysis_p1docs.json', 'p1b.full.a_docs_per_s'):.4f}",
         P1, "analysis_p1docs.json", "p1b.full.a_docs_per_s", s1, "1 run",
         "the out-of-box baseline; no same-session LlamaIndex full run (cross-session drift 15.4%: form no ratio)")
    fact("docs out of box", "stock rr:patched CPU-s per document (full corpus)", f"{at(P1, 'analysis_p1docs.json', 'legs.p1b_base_full.cpu_s_per_doc'):.3f}",
         P1, "analysis_p1docs.json", "legs.p1b_base_full.cpu_s_per_doc", s1, "1 run", "stock image at the banked posture")
    fact("docs fix", "with the wrapper fix (rr:p1-tikafix), full corpus: span docs/s", f"{at(P1, 'analysis_p1docs.json', 'p1b.full.b_docs_per_s'):.4f}",
         P1, "analysis_p1docs.json", "p1b.full.b_docs_per_s", s1, "1 run", "UNSHIPPED fix (P2-D ticket draft, not filed); chunk-identical to stock")
    fact("docs fix", "wrapper fix vs stock, full corpus", pct(at(P1, "analysis_p1docs.json", "p1b.full.delta_b_vs_a")),
         P1, "analysis_p1docs.json", "p1b.full.delta_b_vs_a", s1, "1 run per arm", "one run each, same session; the gain is the tail of eleven pathological PDFs")
    fact("docs fix", "wrapper fix vs stock, 384 slice (ABAB)", pct(at(P1, "analysis_p1docs.json", "p1b.speed_384.delta_b_vs_a")),
         P1, "analysis_p1docs.json", "p1b.speed_384.delta_b_vs_a", s1, "2 runs per arm", "the slice holds none of the eleven, so it understates the fix")
    fact("docs fix", "chunk lists that differ, fix vs stock, full corpus", f"{len(at(P1, 'analysis_p1docs.json', 'p1b.correctness_full_corpus_context.chunk_lists_differ'))} of {at(P1, 'analysis_p1docs.json', 'p1b.correctness_full_corpus_context.documents_ok_in_both'):,}",
         P1, "analysis_p1docs.json", "p1b.correctness_full_corpus_context", s1, "1 run per arm", "output-neutral: documents ok in both")
    # ------------------------------------------------ docs: what not to adopt
    fact("docs tuning", "thread vars = 4 vs vars = 1, full corpus", pct(at(P3, "analysis_p3docs.json", "P3_C.full.delta")),
         P3, "analysis_p3docs.json", "P3_C.full.delta", s3, "1 run per arm", "DO NOT ADOPT: its gain on the 384 slice came from the slice's idle cores (register 60)")
    fact("docs parser", "HYBRID parser vs fixed Tika, full corpus: docs/s", pct(at(P3, "analysis_p3docs.json", "P3_D.full.hybrid.speed.delta")),
         P3, "analysis_p3docs.json", "P3_D.full.hybrid.speed.delta", s3, "1 run per arm", "a smaller, different output, not a faster parser; parser track closed")
    b2 = f"{P4}"
    fact("docs parser", "HYBRID vs fixed Tika: chunks", pct(-at(b2, "analysis_p4b.json", "item2_parser_close_out.chunks_fewer"), 1),
         b2, "analysis_p4b.json", "item2_parser_close_out.chunks_fewer", s3, "1 run per arm", "fewer chunks for the same documents: its text differs from Tika's")
    fact("docs parser", "HYBRID vs fixed Tika: chunks/s", pct(at(b2, "analysis_p4b.json", "item2_parser_close_out.R_chunks_per_s") - 1),
         b2, "analysis_p4b.json", "item2_parser_close_out.R_chunks_per_s", s3, "1 run per arm", "per chunk HYBRID is not faster: all of its docs/s gain is fewer chunks")
    fact("docs parser", "PURE parser: documents lost that fixed Tika recovers", f"{at(P3, 'analysis_p3docs.json', 'P3_D.full.pure.correctness.n_loses')}",
         P3, "analysis_p3docs.json", "P3_D.full.pure.correctness.n_loses", s3, "1 run", "not adoptable; the five P0's H6 predicted")
    s2d = at(P2, "analysis_p2docs.json", "legs.p2a_rr_a.boot_id")[:8]
    fact("docs method", "384 slice span docs/s ratio RR/LI (P2-A smoke)", f"{at(P2, 'analysis_p2docs.json', 'P2_A.smoke_gate.ratio_rr_over_li'):.3f}",
         P2, "analysis_p2docs.json", "P2_A.smoke_gate.ratio_rr_over_li", s2d, "2 runs per arm",
         "drain-dominated slice: not a parity figure (superseded by P3-A full)")
    fact("docs method", "384 slice STEADY-PHASE ratio RR/LI (P2-A legs)", f"{at(P4, 'analysis_p4b.json', 'item1_steady_phase.check_1.sessions.P2-A.steady_ratio'):.3f}",
         P4, "analysis_p4b.json", "item1_steady_phase.check_1.sessions.P2-A.steady_ratio", s2d, "2 runs per arm",
         "POST-HOC validation of a smoke metric, not a throughput claim")
    # ------------------------------------------------ video
    s0 = at(P0, "analysis_v1.json", "sessions.0")[:8]
    fact("video parity", "one LlamaIndex instance vs one RocketRide token, T=4, 16 videos in flight: LI/RR - 1", pct(at(P0, "analysis_v1.json", "gap.li_over_rr_minus_1"), 1),
         P0, "analysis_v1.json", "gap.li_over_rr_minus_1", s0, "2 runs per arm", "the per-instance video gap at K=16 (P0 V1)")
    for c, lab in (("rr_t4", "RocketRide, T=4"), ("li_t4", "LlamaIndex, T=4"), ("rr_default", "RocketRide, engine default threads (out of box)")):
        fact("video parity" if c != "rr_default" else "video out of box", f"{lab}, 16 videos in flight: frames/s", f"{at(P0, 'analysis_v1.json', f'cells.{c}.mean'):.3f}",
             P0, "analysis_v1.json", f"cells.{c}.mean", s0, "2 runs", "mean of two runs; K=16" + ("; LlamaIndex's cell ran at T=4" if c == "rr_default" else ""))
    for c, lab in (("rr_t4", "RocketRide, T=4"), ("li_t4", "LlamaIndex, T=4"), ("rr_default", "RocketRide, default threads")):
        v = statistics.mean(at(P0, "analysis_v1.json", f"cells.{c}.cpu_s_per_frame"))
        fact("video cost", f"{lab}: CPU-s per frame", f"{v:.3f}", P0, "analysis_v1.json", f"cells.{c}.cpu_s_per_frame (mean of two)", s0, "2 runs", "service container CPU / frames")
    idle = [at(P0, "analysis_v1.json", f"legs.{l}.idle_burden.idle_cores_with_instances_live") for l in ("v1_rr_t4_a", "v1_rr_t4_b")]
    fact("video cost", "RocketRide idle cores with the instance live, nothing submitted", f"{statistics.mean(idle):.2f}",
         P0, "analysis_v1.json", "legs.v1_rr_t4_{a,b}.idle_burden.idle_cores_with_instances_live (mean)", s0, "2 runs", "LlamaIndex's: about zero (same file); source untraced")
    s2 = at(P2, "analysis_p2b.json", "boot_ids.0")[:8]
    fact("video parity", "P2-B reproduction, T=4, K=16: LI/RR - 1", pct(at(P2, "analysis_p2b.json", "reading.gap.li_over_base_minus_1"), 1),
         P2, "analysis_p2b.json", "reading.gap.li_over_base_minus_1", s2, "2 runs per arm", "reproduced in a second session")
    fact("video config", "noDebug + MALLOC_ARENA_MAX=2 vs stock, K=16: frames/s", pct(at(P2, "analysis_p2b.json", "reading.combined.comb_over_base_minus_1")),
         P2, "analysis_p2b.json", "reading.combined.comb_over_base_minus_1", s2, "2 runs per arm", "closes about a quarter of the gap; pair b alone is inside the spreads")
    fact("video config", "noDebug + MALLOC_ARENA_MAX=2: output identical", "16 of 16 videos, both pairs" if at(P2, "analysis_p2b.json", "correctness_gate.pass") else "NO",
         P2, "analysis_p2b.json", "correctness_gate", s2, "2 pairs", "chunk hashes and frame scores")
    ba = statistics.mean([at(P2, "analysis_p2b.json", f"legs.{l}.memstat.sampled_peak_bytes.anon") for l in ("p2b_rr_base_a", "p2b_rr_base_b")])
    ca = statistics.mean([at(P2, "analysis_p2b.json", f"legs.{l}.memstat.sampled_peak_bytes.anon") for l in ("p2b_rr_comb_a", "p2b_rr_comb_b")])
    fact("video config", "noDebug + MALLOC_ARENA_MAX=2: sampled anonymous-memory peak, stock -> combined, MB", f"{ba / 1e6:,.0f} -> {ca / 1e6:,.0f}",
         P2, "analysis_p2b.json", "legs.p2b_rr_{base,comb}_{a,b}.memstat.sampled_peak_bytes.anon (means)", s2, "2 runs per arm", "the UNSHIPPED ticket (P3-E draft, not filed)")
    sb = at(P3, "analysis_p3b.json", "boot_ids.0")[:8]
    cfs = statistics.mean([at(P3, "analysis_p3b.json", f"legs.p3b_c_{i}.frames_per_s") for i in (1, 2)])
    fact("video one in flight", "RocketRide engine, ONE video in flight, T=4: frames/s", f"{cfs:.2f}",
         P3, "analysis_p3b.json", "legs.p3b_c_{1,2}.frames_per_s (mean)", sb, "2 runs", "3-video slice")
    fact("video one in flight", "LlamaIndex service, ONE video in flight, T=4: frames/s", f"{at(P3, 'analysis_p3b.json', 'legs.p3b_d_1.frames_per_s'):.2f}",
         P3, "analysis_p3b.json", "legs.p3b_d_1.frames_per_s", sb, "1 run", "3-video slice; one run (context leg)")
    fact("video one in flight", "forward pass per frame, engine at one video in flight, s", f"{at(P3, 'analysis_p3b.json', 'cells.c.mean'):.3f}",
         P3, "analysis_p3b.json", "cells.c.mean", sb, "2 runs", "within 3% of a bare interpreter (cells.a.mean): the model and libraries are not the gap")
    # ------------------------------------------------ P4-A (this session), if analysed
    fa = p4 / "analysis_p4a.json"
    if fa.exists():
        a = json.loads(fa.read_text())
        s4 = (a.get("sessions") or ["?"])[0][:8]
        for c, lab in (("rr_k1", "RocketRide K=1"), ("rr_k16", "RocketRide K=16"), ("li_k1", "LlamaIndex K=1"), ("li_k16", "LlamaIndex K=16"),
                       ("rr_k16_active", "RocketRide K=16, OMP_WAIT_POLICY=ACTIVE")):
            cc = (a.get("cells") or {}).get(c)
            if not cc or cc.get("n_legs") != 2:
                continue
            fact("video concurrency", f"{lab}, T=4, 16 videos: frames/s", f"{cc['frames_per_s']['mean']:.3f}", P4, "analysis_p4a.json", f"cells.{c}.frames_per_s.mean", s4, "2 runs",
                 f"same session, ABAB; the two runs differ by {cc['frames_per_s']['spread'] * 100:.1f}% (every cell slower in round 2)")
            fact("video concurrency", f"{lab}: forward pass per frame, s", f"{cc['F_s']['mean']:.4f}", P4, "analysis_p4a.json", f"cells.{c}.F_s.mean", s4, "2 runs",
                 f"mean over measured frames; the two runs differ by {cc['F_s']['spread'] * 100:.1f}%")
            fact("video cost", f"{lab}: CPU-s per frame", f"{cc['cpu_s_per_frame']['mean']:.3f}", P4, "analysis_p4a.json", f"cells.{c}.cpu_s_per_frame.mean", s4, "2 runs", "service container CPU / frames")
        r1 = (a.get("readings") or {}).get("R1") or {}
        if r1.get("D_RR") is not None:
            fact("video concurrency", "forward degradation K=1 -> K=16, RocketRide (x)", f"{r1['D_RR']:.3f}", P4, "analysis_p4a.json", "readings.R1.D_RR", s4, "2 runs per cell", f"R1 {r1.get('verdict')}")
            fact("video concurrency", "forward degradation K=1 -> K=16, LlamaIndex (x)", f"{r1['D_LI']:.3f}", P4, "analysis_p4a.json", "readings.R1.D_LI", s4, "2 runs per cell", f"R1 {r1.get('verdict')}")
        r2 = (a.get("readings") or {}).get("R2_R3") or {}
        if r2.get("closure") is not None:
            fact("video concurrency", "share of RocketRide's K=1 -> K=16 forward degradation that ACTIVE closes", f"{r2['closure']:.3f}", P4, "analysis_p4a.json", "readings.R2_R3.closure", s4, "2 runs per cell", r2.get("verdict", "")[:90])
    out = {"label": "P4-B (4) CTO facts sheet", "facts": FACTS}
    (p4 / "p4_facts.json").write_text(json.dumps(out, indent=1) + "\n")
    lines = ["# Parity campaign facts sheet (P0-P4)", "",
             "Every figure is read by working/scripts/p4_facts.py from the named committed artifact at the named key; session = boot id prefix; one caveat line each. Withdrawn figures are not listed.", "",
             "| id | area | figure | value | source (artifact : key) | session | n | caveat |", "|---|---|---|---|---|---|---|---|"]
    for f in FACTS:
        lines.append(f"| {f['id']} | {f['area']} | {f['figure']} | {f['value']} | `{f['source']}` : `{f['keys']}` | {f['session']} | {f['n']} | {f['caveat']} |")
    (p4 / "P4_FACTS_SHEET.md").write_text("\n".join(lines) + "\n")
    print(f"facts: {len(FACTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
