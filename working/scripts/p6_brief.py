#!/usr/bin/env python3
"""P6-D (1) CTO brief DRAFT (one page), updated from P5's: generated strictly from the P4 facts sheet (cited [Fnn]), the Stage 4
analysis (cited by file and key) and the P6 analysis (analysis_p6.json, cited by key). Every figure is read here, never
typed. Draft only: not sent, posted or filed.

    p6_brief.py <p6_campaign_dir>  -> P6_CTO_BRIEF_DRAFT.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RES = Path(__file__).resolve().parents[2] / "working" / "results"
P4 = RES / "parity_p4_20260925T092942Z"
S4 = RES / "batchsize_s4_20260921T013303Z" / "p5_li_video" / "analysis_video.json"
S4X = RES / "batchsize_s4_20260921T013303Z" / "p5_li_video" / "li_k16" / "export_llamaindex_video_workers_blast.json"


def main() -> int:
    camp = Path(sys.argv[1])
    F = {f["id"]: f for f in json.loads((P4 / "p4_facts.json").read_text())["facts"]}
    b4 = json.loads((P4 / "analysis_p4b.json").read_text())
    s4 = json.loads(S4.read_text())["legs"][0]
    s4t = json.loads(S4X.read_text())["provenance_video"]["posture"]["threads_env_in_process_torch"]
    s4w = int(s4["posture"].split("declared_workers=")[1].rstrip("]"))
    A6 = json.loads((camp / "analysis_p6.json").read_text())
    a, b, c = A6["P6_A"], A6.get("P6_B"), A6.get("P6_C")

    def f(i):
        return f"{F[i]['value']} [{i}]"
    s_p3h = b4["item1_steady_phase"]["check_1"]["sessions"]["P3-A health"]["steady_ratio"]
    L = ["# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)", "",
         "Figures cite the P4 facts sheet [Fnn] (parity_p4_20260925T092942Z/P4_FACTS_SHEET.md), the Stage 4 analysis, or the P6 analysis "
         "(parity_p6_20260925T175225Z/analysis_p6.json) by key.", "",
         "**What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against "
         "ONE LlamaIndex instance.", "",
         "## Documents (one token vs LlamaIndex's 24-worker optimum)", "",
         f"- **Matches, not beats.** {f('F01')} vs {f('F02')} docs/s on the full corpus: {f('F03')}, one run per arm, inside LlamaIndex's "
         f"replicate spread; the steady-phase ABAB ratios on the 384 slice agree in two sessions: {f('F27')} and {s_p3h:.3f} "
         "[analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].",
         f"- **Needs an unshipped fix.** Stock {f('F15')} docs/s; with the Tika wrapper fix {f('F17')} ({f('F18')}), {f('F20')} chunk lists "
         "changed. The fix measured is a one-byte patch that turns inline-image extraction off for every pipeline, which breaks image "
         "pipelines; the shippable form is the source change in parity_p2_20260924T160106Z/P2D_WRAPPER_TICKET_DRAFT.md:12.",
         f"- **Costs.** CPU per document {f('F05')} vs {f('F06')} s; sampled memory peak {f('F11')} vs {f('F12')} MB; idle spin {f('F09')} vs {f('F10')} cores.",
         f"- **Out of the box** (stock image): {f('F15')} docs/s at {f('F16')} CPU-s per document; no same-session LlamaIndex run, no ratio.",
         "", "## Video (one token vs ONE LlamaIndex instance)", "",
         f"- **Stock.** One LlamaIndex instance runs {f('F28')} more frames/s than one stock RocketRide token at 16 videos in flight (T=4); "
         f"out of the box RocketRide runs {f('F31')} frames/s at {f('F34')} CPU-s per frame.",
         f"- **Mechanism (P4).** From one video in flight to sixteen RocketRide's forward slows x{f('F58')}, LlamaIndex's x{f('F59')}: 16 caller "
         "threads take turns at the model frame by frame."]
    corr = a["correctness"]["gate_pass"]
    rd, C = a["readings"], a["cells"]
    if corr is False:
        L.append("- **P6 (single inference thread): OUTPUT-CHANGING** against stock — no speed reading [P6_A.correctness.gate_pass].")
    elif (rd.get("Q1") or {}).get("pooled"):
        q1, q2 = rd["Q1"], rd["Q2"]
        L.append(f"- **The single inference thread (rr:p5-infer, a benchmark prototype, not shipped), output identical to stock on 16/16 in both "
                 f"rounds** [P6_A.correctness.gate_pass]: {C['p5_k16']['frames_per_s']['mean']:.3f} frames/s [P6_A.cells.p5_k16.frames_per_s.mean] "
                 f"vs one LlamaIndex instance {C['li_k16']['frames_per_s']['mean']:.3f} [P6_A.cells.li_k16.frames_per_s.mean] and stock "
                 f"{C['stock_k16']['frames_per_s']['mean']:.3f} [P6_A.cells.stock_k16.frames_per_s.mean]: parity {q1['pooled']['ratio']:.3f} "
                 f"[P6_A.readings.Q1.pooled.ratio] (Q1 >= 0.95: {q1['verdict']}), speedup {q2['pooled']['ratio']:.3f}x [P6_A.readings.Q2.pooled.ratio] "
                 f"(Q2 >= 1.20: {q2['verdict']}).")
        d = a.get("descriptive_forward_degradation")
        if d:
            L.append(f"- **Known residual (descriptive, cross-session).** Its forward at 16 in flight is {d['F_over_ref_minus_1'] * 100:+.1f}% "
                     f"over one video in flight [P6_A.descriptive_forward_degradation.F_over_ref_minus_1]: median {d['p50_over_ref_minus_1'] * 100:+.1f}%, "
                     f"p99 {d['p99_over_ref_minus_1'] * 100:+.1f}% [..p50_over_ref_minus_1, ..p99_over_ref_minus_1] — a tail.")
    if b and not b.get("complete_168") and (b.get("paired_blocks") or {}).get("ratio_rr_over_li") is not None:
        pb, dist = b["paired_blocks"], b["per_block_ratio_distribution"]
        L.append(f"- **Block-interleaved confirmation, INCOMPLETE (the budget):** {len(pb['blocks'])} of 11 blocks ran on both arms "
                 f"({pb['per_arm']['rr']['videos']} of 168 videos) [P6_B.paired_blocks]: RocketRide {pb['per_arm']['rr']['total_frames_per_s']:.3f} vs one LlamaIndex "
                 f"instance {pb['per_arm']['li']['total_frames_per_s']:.3f} frames/s, ratio {pb['ratio_rr_over_li']:.3f} [P6_B.paired_blocks.ratio_rr_over_li] against 0.95; "
                 f"per block {dist['min']:.3f} to {dist['max']:.3f} (median {dist['p50']:.3f}) [P6_B.per_block_ratio_distribution]; output vs the banked stock run: "
                 f"{b['correctness_vs_p1d']['identical']} of {b['correctness_vs_p1d']['videos_compared']} videos identical [P6_B.correctness_vs_p1d].")
    elif b:
        dist = b["per_block_ratio_distribution"]
        L.append(f"- **168 videos, block-interleaved:** RocketRide {b['per_arm']['rr']['total_frames_per_s']:.3f} vs LlamaIndex "
                 f"{b['per_arm']['li']['total_frames_per_s']:.3f} frames/s [P6_B.per_arm.*.total_frames_per_s], ratio {b['ratio_rr_over_li_totals']:.3f} "
                 f"[P6_B.ratio_rr_over_li_totals] against 0.95; per block {dist['min']:.3f} to {dist['max']:.3f} (median {dist['p50']:.3f}) "
                 f"[P6_B.per_block_ratio_distribution]; output vs the banked stock run: "
                 f"{'identical on all ' + str(b['correctness_vs_p1d']['videos_compared']) if b['correctness_vs_p1d']['all_compared_identical'] else str(b['correctness_vs_p1d']['identical']) + ' of ' + str(b['correctness_vs_p1d']['videos_compared']) + ' identical; ' + ', '.join(x['video'] for x in b['correctness_vs_p1d']['differ']) + ' differ — cause not established (stock never replicated on them)'} "
                 "[P6_B.correctness_vs_p1d].")
    else:
        gf = camp / "gates" / "G_smoke_P6B.json"
        go = json.loads(gf.read_text()).get("outcome") if gf.exists() else None
        L.append(f"- **168-video confirmation: NOT RUN**" + (f" — its gate {go} [gates/G_smoke_P6B.json]." if go else "."))
    if c and (c.get("readings") or {}).get("pooled", {}).get("F_t16_over_F_t4") is not None and c["correctness"]["gate_pass"]:
        rp = c["readings"]["pooled"]
        L.append(f"- **Out-of-box threads (T=16) with the single inference thread:** forward {rp['F_t16_over_F_t4']:.3f}x the T=4 forward "
                 f"[P6_C.readings.pooled.F_t16_over_F_t4] ({c['readings'].get('verdict_forward')}); frames/s vs one LlamaIndex instance at T=16 "
                 f"{rp['fps_p5_t16_over_li_t16']:.3f} [P6_C.readings.pooled.fps_p5_t16_over_li_t16] (reported against 0.95); cross-stage, not ABAB.")
    elif c and c["correctness"]["gate_pass"] and (c.get("readings") or {}).get("round_1", {}).get("F_t16_over_F_t4") is not None:
        r1 = c["readings"]["round_1"]
        L.append(f"- **Out-of-box threads (T=16) with the single inference thread, one round (the second was cut by the budget):** forward "
                 f"{r1['F_t16_over_F_t4']:.3f}x the T=4 forward [P6_C.readings.round_1.F_t16_over_F_t4] — slower, not faster; frames/s vs one LlamaIndex "
                 f"instance at T=16 {r1['fps_p5_t16_over_li_t16']:.3f} [P6_C.readings.round_1.fps_p5_t16_over_li_t16]; T=4 remains the posture to use.")
    elif c and c["correctness"]["gate_pass"] is False:
        L.append("- **Out-of-box threads (T=16): OUTPUT-CHANGING** against the out-of-box reference — no speed reading [P6_C.correctness.gate_pass].")
    else:
        L.append("- **Out-of-box threads (T=16): NOT RUN or incomplete.**")
    L += [f"- **Context, not the comparison:** LlamaIndex's multi-instance video configuration — {s4w} instances x {s4t} threads — runs "
          f"{s4['frames_per_s']:.2f} frames/s on the 168 videos (Stage 4) [batchsize_s4_20260921T013303Z/p5_li_video/analysis_video.json legs.0.frames_per_s; "
          f"posture {s4['posture']}; threads: li_k16/export_llamaindex_video_workers_blast.json provenance_video.posture.threads_env_in_process_torch]. "
          f"That is {s4w} model instances; the comparisons above hold RocketRide to one token and LlamaIndex to one instance.",
          "", "## What is not claimed", "",
          "- That RocketRide BEATS LlamaIndex on documents (one run per arm, inside the spread).",
          "- Any figure from an unshipped fix or prototype as shipped behaviour.",
          "- Any cross-session ratio as a comparison."]
    (camp / "P6_CTO_BRIEF_DRAFT.md").write_text("\n".join(L) + "\n")
    print(f"wrote P6_CTO_BRIEF_DRAFT.md ({len(L)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
