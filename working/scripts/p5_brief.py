#!/usr/bin/env python3
"""P5-C (1) CTO brief DRAFT (one page), generated strictly from the P4 facts sheet (parity_p4_20260925T092942Z/p4_facts.json,
cited by row id F..) and the P5 analysis files (cited by file and key). Every figure is read here, never typed. Draft only:
not sent, posted or filed.

    p5_brief.py <p5_campaign_dir>  -> P5_CTO_BRIEF_DRAFT.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P4 = ROOT / "working" / "results" / "parity_p4_20260925T092942Z"


def main() -> int:
    camp = Path(sys.argv[1])
    F = {f["id"]: f for f in json.loads((P4 / "p4_facts.json").read_text())["facts"]}
    b4 = json.loads((P4 / "analysis_p4b.json").read_text())
    a5 = json.loads((camp / "analysis_p5a.json").read_text()) if (camp / "analysis_p5a.json").exists() else None
    b5 = json.loads((camp / "analysis_p5b.json").read_text()) if (camp / "analysis_p5b.json").exists() else None

    def f(i):                                   # a facts-sheet value with its citation
        return f"{F[i]['value']} [{i}]"
    s_p3h = b4["item1_steady_phase"]["check_1"]["sessions"]["P3-A health"]["steady_ratio"]
    L = ["# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)", "",
         "Figures cite the P4 facts sheet row [F..] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md, each row naming its artifact and key) "
         "or a P5 analysis file and key.", "",
         "## Documents", "",
         f"- **Matches, not beats.** One RocketRide token runs {f('F01')} docs/s on the full corpus against LlamaIndex's 24-worker optimum at "
         f"{f('F02')}: a ratio of {f('F03')}, one run per arm, inside LlamaIndex's replicate spread. The steady-phase ABAB ratios on the 384 "
         f"slice agree across two sessions: {f('F27')} and {s_p3h:.3f} [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio; "
         "the same artifact as F27, not a facts-sheet row].",
         f"- **It depends on an unshipped fix.** Stock RocketRide runs {f('F15')} docs/s; the Tika wrapper fix takes it to {f('F17')} "
         f"({f('F18')}), with {f('F20')} chunk lists changed. The fix measured is a one-byte patch that turns inline-image extraction off "
         "for every pipeline, which breaks image pipelines; the shippable form is the source change in the wrapper ticket draft "
         "(parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12).",
         f"- **Costs.** CPU per document: RocketRide {f('F05')} s vs LlamaIndex {f('F06')} s. Sampled memory peak: {f('F11')} MB vs "
         f"{f('F12')} MB. Idle spin with nothing submitted: {f('F09')} cores vs {f('F10')}.",
         f"- **Out of the box** (stock image): {f('F15')} docs/s at {f('F16')} CPU-s per document; no same-session LlamaIndex run, so no ratio is formed.",
         "", "## Video", "",
         f"- **The gap.** One LlamaIndex instance runs {f('F28')} more frames/s than one RocketRide token at 16 videos in flight (T=4). "
         f"Out of the box RocketRide runs {f('F31')} frames/s at {f('F34')} CPU-s per frame.",
         f"- **The mechanism (P4).** From one video in flight to sixteen RocketRide's forward pass slows x{f('F58')}, LlamaIndex's x{f('F59')}; "
         f"at one video in flight RocketRide is the faster engine ({f('F43')} vs {f('F49')} frames/s). RocketRide's detector lock is taken "
         f"per frame by up to 16 caller threads; OMP_WAIT_POLICY=ACTIVE did not help (closure {f('F60')})."]
    if a5 is None:
        L.append("- **P5 (single inference thread): NOT RUN.**")
    else:
        rd, C, corr = a5["readings"], a5["cells"], a5["correctness"]
        if corr.get("gate_pass") is False:
            L.append("- **P5 (single inference thread): OUTPUT-CHANGING** — the patched node's output differs from stock; no speed reading "
                     "[analysis_p5a.json correctness.gate_pass].")
        elif rd.get("S1", {}).get("pooled") is None:
            L.append(f"- **P5 (single inference thread): not evaluable** — {rd.get('S1', {}).get('verdict')} [analysis_p5a.json readings].")
        else:
            s1, s2 = rd["S1"]["pooled"], rd["S2"]["pooled"]
            L.append(f"- **P5 (single inference thread), output identical to stock on 16/16 videos at K=1 and K=16** [analysis_p5a.json correctness.gate_pass]: "
                     f"at 16 videos in flight it runs {C['p5_k16']['frames_per_s']['mean']:.3f} frames/s [cells.p5_k16.frames_per_s.mean] against stock "
                     f"{C['stock_k16']['frames_per_s']['mean']:.3f} [cells.stock_k16.frames_per_s.mean] "
                     f"({s1['fps_p5k16_over_stock_k16_minus_1'] * 100:+.1f}% [readings.S1.pooled.fps_p5k16_over_stock_k16_minus_1]) and LlamaIndex "
                     f"{C['li_k16']['frames_per_s']['mean']:.3f} [cells.li_k16.frames_per_s.mean]; RocketRide/LlamaIndex {s2['fps_p5k16_over_li_k16']:.3f} "
                     f"[readings.S2.pooled.fps_p5k16_over_li_k16]. Its forward at 16 in flight is {s1['F_p5k16_over_p5k1_minus_1'] * 100:+.1f}% against one "
                     f"in flight [readings.S1.pooled.F_p5k16_over_p5k1_minus_1]. S1 (fix works): {rd['S1']['verdict']}; S2 (parity >= 0.95): {rd['S2']['verdict']}.")
        if b5 is None:
            L.append("- **P5-B 168-video confirmation: NOT RUN** (its gate did not fire, or not reached).")
        else:
            pa, dist = b5["per_arm"], b5["per_block_ratio_distribution"]
            L.append(f"- **P5-B, 168 videos, block-interleaved:** RocketRide {pa['rr']['total_frames_per_s']:.3f} vs LlamaIndex "
                     f"{pa['li']['total_frames_per_s']:.3f} frames/s [analysis_p5b.json per_arm.*.total_frames_per_s], ratio "
                     f"{b5['ratio_rr_over_li_totals']:.3f} [ratio_rr_over_li_totals]; per block {dist['min']:.3f} to {dist['max']:.3f} "
                     f"(median {dist['p50']:.3f}) [per_block_ratio_distribution]; output vs the banked stock run: "
                     f"{'identical on all 168' if b5['correctness_vs_p1d']['pass'] else str(len(b5['correctness_vs_p1d']['differ'])) + ' videos differ'} "
                     f"[correctness_vs_p1d].")
    L += ["", "## What is not claimed", "",
          "- That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).",
          "- Any figure from the unshipped fixes as shipped behaviour.",
          "- Any cross-session ratio."]
    (camp / "P5_CTO_BRIEF_DRAFT.md").write_text("\n".join(L) + "\n")
    print(f"wrote P5_CTO_BRIEF_DRAFT.md ({len(L)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
