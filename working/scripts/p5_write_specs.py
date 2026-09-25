#!/usr/bin/env python3
"""Write the P5 report's prose (p5_summary_spec.json). Every figure inside the prose is formatted HERE from the analysis files
(analysis_p5a.json, analysis_p5b.json, analysis_p5_drift.json), never typed. POST-HOC observations are labelled.

    p5_write_specs.py <campaign_dir> [--not-run "<item: reason>" ...] [--register "<line>" ...] [--posthoc "<text built by the caller from the analysis>"]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pc(x, d=2):
    return "—" if x is None else f"{x * 100:+.{d}f}%"


def sh(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


ap = argparse.ArgumentParser()
ap.add_argument("camp", type=Path)
ap.add_argument("--not-run", action="append", default=[])
ap.add_argument("--register", action="append", default=[])
ap.add_argument("--posthoc", default="")
a = ap.parse_args()
J = lambda n: json.loads((a.camp / n).read_text()) if (a.camp / n).exists() else None  # noqa: E731
A, B, DR = J("analysis_p5a.json"), J("analysis_p5b.json"), J("analysis_p5_drift.json")
summary, R = [], {}
if A:
    corr, rd, C = A["correctness"], A["readings"], A["cells"]
    if corr["gate_pass"] is False:
        summary.append("Correctness: rr:p5-infer is OUTPUT-CHANGING against stock — no speed reading; P5-A and P5-B stopped.")
        R["A"] = "The hard correctness gate failed: " + "; ".join(f"{p['a']} vs {p['b']}: differs on {len(p['chunk_hash_differs'])} videos (chunks), {len(p['frame_scores_differ'])} (scores)" for p in corr["gate_pairs"] if not p["identical"]) + "."
    else:
        n_pairs = len(corr["gate_pairs"])
        summary.append(f"Correctness: rr:p5-infer's output is identical to stock rr:patched-video on 16/16 videos in all {n_pairs} gate comparisons (K=16 and K=1, both rounds, and against P4's committed stock K=1 leg).")
        if rd.get("S1", {}).get("pooled"):
            s1, s2 = rd["S1"], rd["S2"]
            fmt = lambda k: f"{C[k]['frames_per_s']['mean']:.3f}"  # noqa: E731
            summary.append(f"S1 (fix works): {s1['verdict']}. With 16 videos in flight the P5 forward is {pc(s1['pooled']['F_p5k16_over_p5k1_minus_1'])} "
                           f"against one in flight (within {sh(s1['threshold_forward'], 2)} is the rule), and P5 runs {fmt('p5_k16')} frames/s against stock's "
                           f"{fmt('stock_k16')} ({pc(s1['pooled']['fps_p5k16_over_stock_k16_minus_1'])}; beyond {sh(s1['threshold_fps'], 2)} is the rule).")
            summary.append(f"S2 (parity >= 0.95): {s2['verdict']}. P5 at 16 in flight / LlamaIndex at 16 in flight = {s2['pooled']['fps_p5k16_over_li_k16']:.3f} "
                           f"pooled ({s2['round_1']['fps_p5k16_over_li_k16']:.3f} in round 1, {s2['round_2']['fps_p5k16_over_li_k16']:.3f} in round 2); LlamaIndex ran {fmt('li_k16')} frames/s.")
            R["A"] = (f"Stated plainly, per round and pooled. S1: round 1 {'holds' if s1['round_1']['holds'] else 'does not hold'} "
                      f"(forward {pc(s1['round_1']['F_p5k16_over_p5k1_minus_1'])}, frames/s vs stock {pc(s1['round_1']['fps_p5k16_over_stock_k16_minus_1'])}); "
                      f"round 2 {'holds' if s1['round_2']['holds'] else 'does not hold'} (forward {pc(s1['round_2']['F_p5k16_over_p5k1_minus_1'])}, "
                      f"frames/s vs stock {pc(s1['round_2']['fps_p5k16_over_stock_k16_minus_1'])}); pooled {'HOLDS' if s1['pooled']['holds'] else 'DOES NOT HOLD'}. "
                      f"S2: round 1 {s2['round_1']['fps_p5k16_over_li_k16']:.3f}, round 2 {s2['round_2']['fps_p5k16_over_li_k16']:.3f}, pooled "
                      f"{s2['pooled']['fps_p5k16_over_li_k16']:.3f} against 0.95 — {'HOLDS' if s2['pooled']['holds'] else 'DOES NOT HOLD'} pooled.")
        else:
            summary.append(f"S1 / S2: {rd.get('S1', {}).get('verdict')}.")
            R["A"] = f"S1 and S2 are not evaluable: {rd.get('S1')}."
    if corr["gate_pass"] and rd.get("S1", {}).get("pooled"):
        m = lambda c, k: C[c][k]["mean"]  # noqa: E731
        ph = A["legs"]
        qd = [ph[n]["queue_depth"]["D1"] for n in ("p5a_p5k16_1", "p5a_p5k16_2") if (ph.get(n) or {}).get("queue_depth")]
        stock_deg = m("stock_k16", "F_s") / m("p5_k1", "F_s") - 1
        p5_deg = m("p5_k16", "F_s") / m("p5_k1", "F_s") - 1
        R["A"] += (" POST-HOC, not pre-registered (from analysis_p5a.json). (i) Against the same one-video forward, stock's forward at 16 in flight is "
                   f"{pc(stock_deg)} and P5's {pc(p5_deg)}: P5 removes {sh(1 - p5_deg / stock_deg)} of the slowdown, not all of it, and the residual is beyond "
                   "this session's replicate spread, which is why S1 does not hold. (ii) The inference thread is busy for "
                   f"{sh(m('p5_k16', 'duty'), 2)} of the window at 16 in flight and keeps {m('p5_k16', 'cores_in_forward'):.2f} cores busy during a forward "
                   f"(stock at 16: {m('stock_k16', 'cores_in_forward'):.2f}; P5 at one in flight: {m('p5_k1', 'cores_in_forward'):.2f}); the queue's median depth "
                   f"is {qd[0]['p50']:.0f} and {qd[1]['p50']:.0f} in the two runs — with 16 callers and one frame in the forward, that is every other caller's frame "
                   f"waiting: the one thread is the bottleneck. (iii) P5 at 16 in flight runs {pc(m('p5_k16', 'frames_per_s') / m('p5_k1', 'frames_per_s') - 1)} frames/s over P5 at one in flight "
                   "(decoding overlaps the forward). (iv) Cost: CPU-s per frame "
                   f"{m('p5_k16', 'cpu_s_per_frame'):.3f} vs stock {m('stock_k16', 'cpu_s_per_frame'):.3f} ({pc(m('p5_k16', 'cpu_s_per_frame') / m('stock_k16', 'cpu_s_per_frame') - 1)}) "
                   f"and LlamaIndex {m('li_k16', 'cpu_s_per_frame'):.3f}; sampled memory peak {m('p5_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB vs stock "
                   f"{m('stock_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB and LlamaIndex {m('li_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB (means of two runs). "
                   f"(v) The residual sits in the tail: the median forward (mean of the two runs' p50) is {m('p5_k16', 'forward_p50') * 1000:.1f} ms at 16 in flight "
                   f"against {m('p5_k1', 'forward_p50') * 1000:.1f} ms at one ({pc(m('p5_k16', 'forward_p50') / m('p5_k1', 'forward_p50') - 1)}), while the p99 is "
                   f"{ph['p5a_p5k16_1']['forward_D1']['p99'] * 1000:.0f} and {ph['p5a_p5k16_2']['forward_D1']['p99'] * 1000:.0f} ms against "
                   f"{ph['p5a_p5k1_1']['forward_D1']['p99'] * 1000:.0f} and {ph['p5a_p5k1_2']['forward_D1']['p99'] * 1000:.0f} ms. "
                   "What the residual forward penalty at 16 in flight is made of was not measured.")
    if a.posthoc:
        R["A"] = (R.get("A", "") + " POST-HOC, not pre-registered: " + a.posthoc).strip()
else:
    summary.append("P5-A: NOT RUN or not analysed.")
if B:
    pa, dist, cr = B["per_arm"], B["per_block_ratio_distribution"], B["correctness_vs_p1d"]
    summary.append(f"P5-B (168 videos, block-interleaved): RocketRide P5 {pa['rr']['total_frames_per_s']:.3f} vs LlamaIndex {pa['li']['total_frames_per_s']:.3f} "
                   f"frames/s, ratio {B['ratio_rr_over_li_totals']:.3f}; per block {dist['min']:.3f} to {dist['max']:.3f} (median {dist['p50']:.3f}); "
                   f"output vs the banked stock run: {'identical on all ' + str(cr['videos_compared']) if cr['pass'] else str(len(cr['differ'])) + ' of ' + str(cr['videos_compared']) + ' differ'}.")
    R["B"] = (f"{pa['rr']['blocks']} RocketRide blocks and {pa['li']['blocks']} LlamaIndex blocks ran ({pa['rr']['videos']} and {pa['li']['videos']} videos; "
              f"errors {pa['rr']['errors']} and {pa['li']['errors']}). " + ("Blocks NOT RUN: " + ", ".join(B["blocks_not_run"]) + "." if B["blocks_not_run"] else "Every block ran."))
else:
    summary.append("P5-B: NOT RUN" + (" — its gate did not fire." if A and A["correctness"]["gate_pass"] is not False else "."))
    R["B_not_run"] = "NOT RUN: the P5-B gate (correctness AND S1 AND S2, pooled) did not fire, so the 168-video confirmation was not started." if A else "NOT RUN."
if DR:
    summary.append(f"Drift: {DR['reading']} (canary {pc(DR.get('canary_change'))} from round 1 to round 2; P5-A cells' median {pc(DR.get('p5_cells_median_change'))}).")
    R["drift"] = ("The canary is the same bare microbenchmark every round, alone, in rr:patched-video; it measures the box, not either engine. "
                  f"P4, which had no canary, drifted by {pc(min(DR['p4_round_drift_F_change'].values()))} to {pc(max(DR['p4_round_drift_F_change'].values()))} "
                  "between its rounds. No figure in this report is adjusted by the canary.")
summary.append("The CTO brief draft is below; it is not sent, posted or filed.")
spec = {"summary": summary, "readings": R, "not_run": a.not_run, "register": a.register,
        "self_audit": {
            "1. HYPOTHESIS": "stated before the first leg in preregistration.json (P5-A hypothesis, build, the in-image check, the hard correctness gate, S1/S2 per round and pooled, the P5-B gate and block design with its container choice, the P5-C rules including the drift rule), committed at 504cf101; no amendment.",
            "2. EVIDENCE": "every figure is computed by working/scripts/p5_report.py and p5_write_specs.py from analysis_p5a.json (p5_analyse_a.py over the raw smoke legs), "
                           + ("analysis_p5b.json (p5_analyse_b.py over the raw block legs), " if B else "(P5-B did not run, so there is no analysis_p5b.json), ")
                           + "analysis_p5_drift.json, the build record, the gate-control record, the gate records and the chain records; the brief from p4_facts.json and the P5 analysis files.",
            "3. NULL CONTROL": "every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json, real control legs for every G_cell flavour, the in-image check in both images); the laptop worker test has a mis-routing null control; the blind recomputation's planted figures had to be caught.",
            "4. REGISTER": "3 (one session); 48 (blind recomputation); 54, 55 (hard gates, the sampler gated after the first leg); 56-58 (gates tested whole; containers' users); 59 (reading clauses against the hypothesis); 61 (a gate reads the record its writer finalises last: D0 from the export); 62 (ABAB rounds, the canary); 63 (the steady-phase metric).",
            "5. NOT VERIFIED": "whether P5's gain holds on other videos, other T or other hardware; why the box drifts between rounds (the canary describes it, nothing explains it); the P5 node beyond this benchmark's pipeline (source only, not a RocketRide change); the CTO brief is a draft.",
            "6. GATES": "every P5 landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg; protected ids read back before and after the build and at stage start and end; the box stopped with box.sh stop and its state read back."}}
(a.camp / "p5_summary_spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
print("spec written")
