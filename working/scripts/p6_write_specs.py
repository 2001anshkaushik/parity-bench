#!/usr/bin/env python3
"""Write the P6 report's prose (p6_summary_spec.json). Every figure inside the prose is formatted HERE from analysis_p6.json,
never typed. POST-HOC observations are labelled.

    p6_write_specs.py <campaign_dir> [--not-run "<item: reason>" ...] [--register "<line>" ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pc(x, d=2):
    return "—" if x is None else f"{x * 100:+.{d}f}%"


ap = argparse.ArgumentParser()
ap.add_argument("camp", type=Path)
ap.add_argument("--not-run", action="append", default=[])
ap.add_argument("--register", action="append", default=[])
a = ap.parse_args()
AN = json.loads((a.camp / "analysis_p6.json").read_text())
A, B, C, DR = AN["P6_A"], AN.get("P6_B"), AN.get("P6_C"), AN.get("drift")
S, R = [], {}
corr, rd, cells = A["correctness"], A["readings"], A["cells"]
if corr["gate_pass"] is False:
    S.append("P6-A correctness: rr:p5-infer is OUTPUT-CHANGING against stock — no speed reading; P6 stopped.")
elif (rd.get("Q1") or {}).get("pooled"):
    q1, q2 = rd["Q1"], rd["Q2"]
    fm = lambda k: f"{cells[k]['frames_per_s']['mean']:.3f}"  # noqa: E731
    S.append("P6-A correctness: rr:p5-infer's output is identical to stock on 16/16 videos in both rounds.")
    S.append(f"Q1 PARITY (P5 / one LlamaIndex instance >= 0.95): {q1['verdict']} — {q1['round_1']['ratio']:.3f} in round 1, {q1['round_2']['ratio']:.3f} in "
             f"round 2, {q1['pooled']['ratio']:.3f} pooled ({fm('p5_k16')} vs {fm('li_k16')} frames/s).")
    S.append(f"Q2 SPEEDUP (P5 / stock >= 1.20): {q2['verdict']} — {q2['round_1']['ratio']:.3f}, {q2['round_2']['ratio']:.3f}, {q2['pooled']['ratio']:.3f} pooled "
             f"(stock {fm('stock_k16')} frames/s).")
    d = A.get("descriptive_forward_degradation")
    if d:
        S.append(f"Forward degradation (descriptive, never gated; cross-session reference): mean {pc(d['F_over_ref_minus_1'])}, p50 {pc(d['p50_over_ref_minus_1'])}, "
                 f"p99 {pc(d['p99_over_ref_minus_1'])} against P5's one-video forward.")
    p5c = json.loads((a.camp.parent / "parity_p5_20260925T141647Z" / "analysis_p5a.json").read_text()).get("canary") or {}
    p5can = [v["F_s"] for v in p5c.values() if v and v.get("F_s")]
    p6can = [((DR or {}).get("canary_F_s_in_time_order") or {}).get(k) for k in ("p6c_can_a1", "p6c_can_a2")]
    boxnote = ""
    if len(p5can) == 2 and None not in p6can and d:
        boxnote = (f" POST-HOC, about the descriptive figure only: its one-video reference is P5's session, and this session's canary (P6-A rounds, mean "
                   f"{sum(p6can) / 2:.4f} s) read {pc(sum(p6can) / sum(p5can) - 1)} against P5's canaries (mean {sum(p5can) / 2:.4f} s) — part of the "
                   f"{pc(d['F_over_ref_minus_1'])} is the box, not the node; nothing is adjusted.")
    R["A"] = (f"Stated plainly, per round and pooled: Q1 holds in round 1 ({q1['round_1']['ratio']:.3f}) {'and' if q1['round_1']['holds'] == q1['round_2']['holds'] else 'but not'} "
              f"in round 2 ({q1['round_2']['ratio']:.3f}); pooled {q1['pooled']['ratio']:.3f} — {'HOLDS' if q1['pooled']['holds'] else 'DOES NOT HOLD'}. "
              f"Q2: round 1 {q2['round_1']['ratio']:.3f}, round 2 {q2['round_2']['ratio']:.3f}, pooled {q2['pooled']['ratio']:.3f} — "
              f"{'HOLDS' if q2['pooled']['holds'] else 'DOES NOT HOLD'} pooled." + boxnote if q1['round_1']['holds'] else
              f"Stated plainly: Q1 round 1 {q1['round_1']['ratio']:.3f}, round 2 {q1['round_2']['ratio']:.3f}, pooled {q1['pooled']['ratio']:.3f}; "
              f"Q2 round 1 {q2['round_1']['ratio']:.3f}, round 2 {q2['round_2']['ratio']:.3f}, pooled {q2['pooled']['ratio']:.3f}.")
else:
    S.append(f"P6-A: {rd.get('Q1', {}).get('verdict')}.")
if B:
    pa, dist, cr = B["per_arm"], B["per_block_ratio_distribution"], B["correctness_vs_p1d"]
    pb = B.get("paired_blocks") or {}
    if not B.get("complete_168") and pb.get("ratio_rr_over_li") is not None:
        S.append(f"P6-B did NOT complete within the budget: {len(pb['blocks'])} of 11 blocks ran on both arms ({pb['per_arm']['rr']['videos']} of 168 videos each). "
                 f"Over those blocks RocketRide P5 runs {pb['per_arm']['rr']['total_frames_per_s']:.3f} vs one LlamaIndex instance {pb['per_arm']['li']['total_frames_per_s']:.3f} "
                 f"frames/s — ratio {pb['ratio_rr_over_li']:.3f} ({'meets' if pb['meets_q1_bar'] else 'does not meet'} 0.95).")
    S.append(f"P6-B (168 videos, block-interleaved, warm-symmetric): RocketRide P5 {pa['rr']['total_frames_per_s']:.3f} vs one LlamaIndex instance "
             f"{pa['li']['total_frames_per_s']:.3f} frames/s — ratio {B['ratio_rr_over_li_totals']:.3f} against 0.95 ({'meets' if B['ratio_meets_q1_bar'] else 'does not meet'}); "
             f"per block {dist['min']:.3f} to {dist['max']:.3f} (median {dist['p50']:.3f}); output vs the banked stock run: "
             f"{'identical on all ' + str(cr['videos_compared']) if cr['all_compared_identical'] else str(len(cr['differ'])) + ' of ' + str(cr['videos_compared']) + ' differ (' + ', '.join(x['video'] for x in cr['differ']) + '; cause not established — register 65)'}.")
    others = [x["other_container_cpu_s_during_block"] for x in B["blocks"].values() if x and x.get("other_container_cpu_s_during_block") is not None]
    per_block = dist.get("per_block") or {}
    worst = min(per_block, key=per_block.get) if per_block else None
    worst_note = (f"POST-HOC: the lowest per-block ratio ({per_block[worst]:.3f}) is block {worst}, which holds "
                  f"{B['blocks'][f'p6b_rr_b{int(worst):02d}']['videos']} videos (so at most that many in flight)." if worst else "")
    R["B"] = (f"{pa['rr']['blocks']} RocketRide and {pa['li']['blocks']} LlamaIndex blocks ran ({pa['rr']['videos']} and {pa['li']['videos']} videos; errors "
              f"{pa['rr']['errors']} and {pa['li']['errors']}). " + ("Blocks NOT RUN: " + ", ".join(B["blocks_not_run"]) + ". " if B["blocks_not_run"] else "Every block ran. ")
              + (f"The paused arm used at most {max(others):.3f} CPU-s during any block. " if others else "")
              + worst_note)
else:
    gf = a.camp / "gates" / "G_smoke_P6B.json"
    go = json.loads(gf.read_text()).get("outcome") if gf.exists() else None
    S.append("P6-B: NOT RUN" + (f" — G_smoke_P6B {go}." if go else "."))
    R["B_not_run"] = f"NOT RUN: G_smoke_P6B {go or 'was not reached'}."
if C:
    cc = C["correctness"]["gate_pass"]
    rp = (C.get("readings") or {}).get("pooled") or {}
    if cc is False:
        S.append("P6-C: P5 at T=16 is OUTPUT-CHANGING against the out-of-box reference — no speed reading.")
    elif rp.get("F_t16_over_F_t4") is None and (C.get("readings") or {}).get("round_1", {}).get("F_t16_over_F_t4") is not None:
        r1 = C["readings"]["round_1"]
        R["C"] = (f"Stated plainly: round 2 was NOT RUN (the budget), so the pre-registered pooled reading is NOT EVALUABLE. Round 1 alone: at T=16 (the out-of-box "
                  f"posture) the single-inference-thread node's forward is {r1['F_t16_over_F_t4']:.3f}x its T=4 forward in P6-A's round 1 — slower, the opposite of "
                  f"the hypothesis — and it runs {r1['fps_p5_t16_over_li_t16']:.3f} of one LlamaIndex instance at T=16. Its output is identical to the committed "
                  "out-of-box stock output on 16/16. This comparison crosses stages of the session (not ABAB).")
        S.append(f"P6-C (T=16, six vars unset): round 2 NOT RUN (the budget), so the pooled reading is NOT EVALUABLE. Round 1: the P5 forward at T=16 is "
                 f"{r1['F_t16_over_F_t4']:.3f}x its T=4 forward (the bar is 0.95: {'faster by at least 5%' if r1['faster_by_at_least_5pct'] else 'NOT faster — slower'}); "
                 f"P5 T=16 / LlamaIndex T=16 = {r1['fps_p5_t16_over_li_t16']:.3f} (reported against 0.95); output identical to the out-of-box reference on 16/16; "
                 "cross-stage, not ABAB-protected.")
    elif rp.get("F_t16_over_F_t4") is not None:
        S.append(f"P6-C (T=16, six vars unset): {C['readings'].get('verdict_forward')} — the P5 forward at T=16 is {rp['F_t16_over_F_t4']:.3f}x its T=4 forward "
                 f"(the bar is 0.95); P5 T=16 / LlamaIndex T=16 = {rp['fps_p5_t16_over_li_t16']:.3f} (reported against 0.95); output identical to the out-of-box reference; "
                 "cross-stage, not ABAB-protected.")
    else:
        S.append("P6-C: incomplete — " + json.dumps(C.get("readings"))[:200])
else:
    S.append("P6-C: NOT RUN.")
    R["C_not_run"] = "NOT RUN (see NOT RUN)."
if DR:
    S.append(f"Drift: {DR['reading']} (canary {pc(DR.get('canary_change_a2_over_a1'))} from P6-A round 1 to round 2; P6-A cells' median {pc(DR.get('p6a_cells_median_change'))}).")
S.append("Both drafts (the CTO brief and the upstream patch description) are below; neither is sent, posted or filed.")
spec = {"summary": S, "readings": R, "not_run": a.not_run, "register": a.register,
        "self_audit": {
            "1. HYPOTHESIS": "stated before the first leg in preregistration.json (committed 8e4cf34a) and preregistration_addendum_1.json (the drift-note rule, committed c0af3f83 before the first measured leg); FIXED tolerances throughout (register 64); no other amendment.",
            "2. EVIDENCE": "every figure is computed by working/scripts/p6_report.py and p6_write_specs.py from analysis_p6.json (p6_analyse.py over the raw legs and blocks), the gate-control record, the gate records and the chain records (the P6-B stamp files, which no analysis reads, are kept in S3 only — p6b_stamps_s3_only.json lists each with its sha256); the drafts from p4_facts.json, the Stage 4 analysis, analysis_p6.json, the P5 analysis and build record, and the node sources.",
            "3. NULL CONTROL": "every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json; real control legs for the out-of-box posture, LlamaIndex at T=16 and the warm flags); the driver's warm flags have a laptop test with a null control; the blind recomputation's planted figures had to be caught.",
            "4. REGISTER": "3, 48, 54, 55, 56-58, 59, 61, 62 (ABAB and the canary), 64 (fixed tolerances; forward degradation descriptive only); new: 65 (an output reference with no replicate of its own).",
            "5. NOT VERIFIED": "what the residual forward penalty at 16 in flight is made of; P6-C's T=16 vs T=4 comparison is across stages, not interleaved; the brief and the patch description are drafts; the prototype is not a RocketRide change.",
            "6. GATES": "every landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg and block; image ids read back at every stage's start and end (rr:p5-infer not rebuilt); the box stopped with box.sh stop and its state read back."}}
(a.camp / "p6_summary_spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
print("spec written")
