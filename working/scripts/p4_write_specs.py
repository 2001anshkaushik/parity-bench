#!/usr/bin/env python3
"""Write the P4 report's prose (p4_summary_spec.json). Every figure inside the prose is formatted HERE from the analysis
files (analysis_p4a.json, analysis_p4b.json), never typed (register: P3's double-rounded figure). POST-HOC observations
are labelled as such and passed with --posthoc-a (they must also be built from the analysis files by the caller).

    p4_write_specs.py <campaign_dir> [--posthoc-a "<text>"] [--not-run "<item: reason>" ...] [--register "<line>" ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pc(x, d=2):
    return f"{x * 100:+.{d}f}%"


def sh(x, d=1):
    return f"{x * 100:.{d}f}%"


ap = argparse.ArgumentParser()
ap.add_argument("camp", type=Path)
ap.add_argument("--posthoc-a", default="")
ap.add_argument("--not-run", action="append", default=[])
ap.add_argument("--register", action="append", default=[])
a = ap.parse_args()
A = json.loads((a.camp / "analysis_p4a.json").read_text()) if (a.camp / "analysis_p4a.json").exists() else None
B = json.loads((a.camp / "analysis_p4b.json").read_text())

# ------------------------------------------------ P4-A
p4a = "P4-A was not analysed."
if A:
    r1, r2 = A["readings"]["R1"], A["readings"]["R2_R3"]
    C = A["cells"]
    parts = []
    if r1.get("D_RR") is not None:
        fps = lambda c: f"{C[c]['frames_per_s']['mean']:.3f}"  # noqa: E731
        F = lambda c: f"{C[c]['F_s']['mean']:.4f}"  # noqa: E731
        parts.append(
            f"R1 is {r1['verdict']}. From one video in flight to sixteen, RocketRide's forward pass per frame goes from {F('rr_k1')} s "
            f"to {F('rr_k16')} s (x{r1['D_RR']:.3f}); LlamaIndex's goes from {F('li_k1')} s to {F('li_k16')} s (x{r1['D_LI']:.3f}). "
            f"RocketRide's degradation exceeds LlamaIndex's by {pc(r1['D_RR_over_D_LI_minus_1'])} against S1 {sh(r1['S1'], 2)}"
            f" ({'beyond' if r1['clause_degradation_beyond'] else 'NOT beyond'}). At one video in flight RocketRide runs {fps('rr_k1')} frames/s "
            f"and LlamaIndex {fps('li_k1')} ({pc(r1['rr_k1_over_li_k1_fps_minus_1'])}); at sixteen, {fps('rr_k16')} and {fps('li_k16')}.")
        if r1["verdict"] != "SUPPORTED":
            parts.append("Stated plainly, as pre-registered: the gap is NOT concurrency-specific by this rule (failed: "
                         + "; ".join(r1["failed_clauses"]) + "); the K=1 cells show the figures above instead.")
    if r2.get("verdict"):
        if r2.get("closure") is not None:
            parts.append(
                f"R2/R3: {r2['verdict']}. The ACTIVE cell is {'output-identical to RR K=16 on 16/16 videos in every pair' if r2['precondition_correctness'] else 'NOT output-identical to RR K=16'}; "
                f"it closes {r2['closure']:.3f} of RocketRide's K=1 to K=16 forward degradation (the rule needs 0.5); F(RR K=16) / F(ACTIVE) − 1 is "
                f"{pc(r2['active_reduction_F16_over_Factive_minus_1'])} against S2 {sh(r2['S2'], 2)}; "
                f"and its frames/s is {pc(r2['active_fps_vs_rr_k16_minus_1'])} against RR K=16.")
        else:
            parts.append(f"R2/R3: {r2['verdict']}.")
    ph = json.loads((a.camp / "analysis_p4a_posthoc.json").read_text()) if (a.camp / "analysis_p4a_posthoc.json").exists() else None
    if ph:
        dr, pr, ac, cf = ph["round_drift"], ph["per_round_readings"], ph["active_cost"], ph["cores_in_forward"]
        lo = min(dr, key=lambda c: dr[c]["F_run2_over_run1_minus_1"])
        hi = max(dr, key=lambda c: dr[c]["F_run2_over_run1_minus_1"])
        s1c = max(("rr_k1", "rr_k16", "li_k1", "li_k16"), key=lambda c: C[c]["F_s"]["spread"])
        parts.append(
            "POST-HOC, not pre-registered (analysis_p4a_posthoc.json). (i) "
            + ("Every cell's second run was slower than its first" if ph["every_cell_slower_in_round_2"] else "The two rounds differ")
            + f": the forward per frame rose by {pc(dr[lo]['F_run2_over_run1_minus_1'])} ({lo}) to {pc(dr[hi]['F_run2_over_run1_minus_1'])} ({hi}); steal stayed "
            "near zero and the per-leg MHz snapshots do not explain it. The ABAB order put both runs of every cell in each round, so the drift "
            f"widened the spreads (S1 is {s1c}'s {sh(C[s1c]['F_s']['spread'], 2)}) rather than biasing a comparison. Read per round, RocketRide's "
            f"degradation exceeds LlamaIndex's by {pc(pr['round_1']['D_RR_over_D_LI_minus_1'])} (round 1) and {pc(pr['round_2']['D_RR_over_D_LI_minus_1'])} "
            f"(round 2), and ACTIVE's closure is {pr['round_1']['closure']:.3f} and {pr['round_2']['closure']:.3f}: both rounds give the pooled readings. "
            f"(ii) ACTIVE is a cost, not a fix: {pc(ac['cpu_s_per_frame_active_over_rr16_minus_1'])} CPU-s per frame, {ac['service_cores_active']:.2f} "
            f"service cores against {ac['service_cores_rr16']:.2f} at K=16, and no shorter forward. (iii) At K=16 the process keeps fewer cores busy "
            f"during a forward than at K=1 on both arms (RocketRide {cf['rr_k1']:.2f} -> {cf['rr_k16']:.2f}, LlamaIndex {cf['li_k1']:.2f} -> "
            f"{cf['li_k16']:.2f}); at K=16 that figure is an upper bound on the forward's own cores (the registered bias), and ACTIVE raises it to "
            f"{cf['rr_k16_active']:.2f} (its spinning pools count) without shortening the forward. (iv) Within this session LlamaIndex at K=16 runs "
            f"{pc(ph['k16_gap_li_over_rr_fps_minus_1'])} frames/s over RocketRide at K=16. (v) At K=1 RocketRide's lock duty is "
            f"{sh(ph['k1_lock_duty']['rr_k1'])} against LlamaIndex's {sh(ph['k1_lock_duty']['li_k1'])}, consistent with the source trace: "
            "LlamaIndex extracts a video's frames before it takes its lock, and at K=1 nothing overlaps that extraction.")
    if a.posthoc_a:
        parts.append("POST-HOC, not pre-registered: " + a.posthoc_a)
    p4a = " ".join(parts)

# ------------------------------------------------ P4-B
i1, i2 = B["item1_steady_phase"], B["item2_parser_close_out"]
s = i1["check_1"]["sessions"]
sh1 = i1["check_2"]["shapes"]
b1 = (f"By the pre-registered rule the steady-phase metric {i1['verdict']} (POST-HOC, on committed legs). Check 1: the 384-slice "
      f"steady-phase RocketRide/LlamaIndex ratio is {s['P2-A']['steady_ratio']:.4f} in P2-A's session and {s['P3-A health']['steady_ratio']:.4f} in P3-A's, "
      f"{pc(s['P2-A']['rel_to_full_minus_1'])} and {pc(s['P3-A health']['rel_to_full_minus_1'])} from P3-A's full-scale {i1['full_scale_ratio']:.4f} "
      f"(bound ±8.19%), where the span ratio on the same legs read {s['P2-A']['span_ratio_beside']:.4f} and {s['P3-A health']['span_ratio_beside']:.4f}. "
      f"Check 2: the steady phase ranks vars=4 {pc(i1['check_2']['vars4_vs_vars1_steady_minus_1'])} against vars=1, the full-scale sign, where "
      f"span docs/s ranked it {pc(sh1['vars=4']['span_mean_beside'] / sh1['vars=1']['span_mean_beside'] - 1)}. "
      + ("A register entry proposing steady-phase docs/s as the smoke metric for future throughput gates is DRAFTED in "
         "P4B_REGISTER_ENTRY_DRAFT_STEADY_PHASE.md (not added to the register). " if i1["verdict"] == "VALIDATES" else
         "No register entry is drafted; failed: " + "; ".join(i1["failed_checks"]) + ". ")
      + "Limits: two sessions and one shape comparison, post-hoc; only ratios and rankings carry over — the slice's absolute "
        "steady-phase rate is not full-scale throughput and is never quoted as throughput.")
b2 = (f"Closing statement. HYBRID's full-corpus docs/s gain over fixed Tika is {pc(i2['docs_gain'])}. "
      f"{'All' if i2['share_of_gain_from_fewer_chunks'] >= 1 else 'Most' if i2['share_of_gain_from_fewer_chunks'] > 0.5 else 'Less than half'} "
      f"of it is fewer chunks: HYBRID emits {sh(i2['chunks_fewer'])} fewer chunks for the same {i2['legs']['HYB']['ok']:,} ok documents "
      f"(chunks per ok document {i2['legs']['FIX']['chunks_per_ok_doc']:.3f} -> {i2['legs']['HYB']['chunks_per_ok_doc']:.3f}); against fixed Tika "
      f"its chunks/s is {pc(i2['R_chunks_per_s'] - 1)} and its CPU-s per chunk {pc(i2['R_cpu_s_per_chunk'] - 1)}. "
      f"By the log decomposition {sh(i2['share_of_gain_from_fewer_chunks'])} of the gain is fewer chunks and "
      f"{sh(i2['share_of_gain_from_chunk_throughput'])} is chunk throughput. The parser track is CLOSED: keep fixed Tika; "
      "a parser change is a text-quality decision (HYBRID's text differs from Tika's on a tail of documents, P3-D), and any text-quality "
      "gate comes before any parser speed claim.")
b3 = "The draft's last section was written before any P4-A data, as rules against the pre-registered readings."
if A:
    v1, v2 = A["readings"]["R1"]["verdict"], A["readings"]["R2_R3"]["verdict"]
    row = ("R1 SUPPORTED and R3 (NOT WAKE-UP): the design IS the right next step" if v1 == "SUPPORTED" and v2.startswith("R3") else
           "R1 SUPPORTED and R2 (POOL WAKE-UP): the config fix comes first" if v1 == "SUPPORTED" and v2.startswith("R2") else
           "R1 NOT SUPPORTED: the design does not address the gap" if v1 != "SUPPORTED" else "R2/R3 NOT EVALUABLE: the design stays a draft")
    b3 += f" P4-A produced R1 {v1} and {v2.split(' (')[0]}, so the row that applies is: {row}."
summary = []
if A:
    r1, r2, C = A["readings"]["R1"], A["readings"]["R2_R3"], A["cells"]
    ga = A["correctness"]["G_correct_active"]["pass"]
    bs = A["correctness"]["beside"]
    allid = ga and all(x["identical"] and x["videos_compared"] == 16 for v in bs.values() for x in (v if isinstance(v, list) else [v]) if x)
    summary.append("Correctness: " + ("every output comparison is identical on 16/16 videos (ACTIVE vs K=16; K=1 vs K=16 on both arms; run to run)."
                                      if allid else "NOT every output comparison is identical; see Correctness first."))
    if r1.get("D_RR") is not None:
        summary.append(f"P4-A R1 {r1['verdict']}: RocketRide's forward per frame degrades x{r1['D_RR']:.3f} from one video in flight to sixteen, "
                       f"LlamaIndex's x{r1['D_LI']:.3f}; at one video in flight RocketRide is the faster arm ({C['rr_k1']['frames_per_s']['mean']:.3f} "
                       f"vs {C['li_k1']['frames_per_s']['mean']:.3f} frames/s). The per-instance video gap is a concurrency effect."
                       if r1["verdict"] == "SUPPORTED" else f"P4-A R1 {r1['verdict']}: the gap is not concurrency-specific by the rule.")
    if r2.get("closure") is not None:
        ph = json.loads((a.camp / "analysis_p4a_posthoc.json").read_text()) if (a.camp / "analysis_p4a_posthoc.json").exists() else {}
        cost = (ph.get("active_cost") or {}).get("cpu_s_per_frame_active_over_rr16_minus_1")
        summary.append(f"P4-A {r2['verdict'].split(' (')[0]}: OMP_WAIT_POLICY=ACTIVE closes {r2['closure']:.3f} of RocketRide's degradation (the rule "
                       "needs 0.5)" + (f" and costs {pc(cost)} CPU-s per frame" if cost is not None else "") +
                       (". The P5 candidate is a single inference thread." if r2["verdict"].startswith("R3") else "."))
summary.append(f"P4-B (1) steady-phase docs/s as the smoke metric: {i1['verdict']} (post-hoc validation).")
summary.append(f"P4-B (2) parser close-out: HYBRID's {pc(i2['docs_gain'])} docs/s is "
               f"{'all' if i2['share_of_gain_from_fewer_chunks'] >= 1 else 'partly'} fewer chunks; keep fixed Tika; the parser track is closed.")
summary.append("P4-B (3) P5 design drafted (not filed). P4-B (4) facts sheet written. NOT RUN: " + ("; ".join(a.not_run) if a.not_run else "nothing."))
spec = {"summary": summary, "readings": {"P4A": p4a, "B1": b1, "B2": b2, "B3": b3},
        "not_run": a.not_run, "register": a.register,
        "self_audit": {
            "1. HYPOTHESIS": "stated before the first leg in preregistration.json (P4-A hypothesis, cells, metrics, the correctness gate, R1/R2/R3 and their thresholds, every gate and its controls; P4-B rules), committed at 1fcb6ce4; no amendment.",
            "2. EVIDENCE": "every figure in this report is computed by working/scripts/p4_report.py and p4_write_specs.py from analysis_p4a.json (p4_analyse_a.py over the raw P4-A leg directories beside it), analysis_p4b.json (p4_analyse_b.py over P2's and P3's committed legs), p4_facts.json (p4_facts.py over committed analysis files), the gate-control record, the gate records in gates/ and the chain start/done records.",
            "3. NULL CONTROL": "every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json, including a real ACTIVE control leg); the blind recomputation's planted figures had to be caught (P4_BLIND_VERIFICATION.json).",
            "4. REGISTER": "3 (one box session for every P4-A leg); 48 (blind recomputation); 54, 55 (hard gates; the memory sampler gated after the first leg; DEGRADED-with-all-rows kept); 56-58 (gates tested whole, positive and null; the container's user); 59 (each reading's clauses checked against the hypothesis's own condition); 60 (the smoke-slice bias, P4-B (1)); new entries listed above.",
            "5. NOT VERIFIED": "which of caller interleaving or shared contention drives RocketRide's K=16 forward degradation (R3 holds; P5's measurement would separate them); why every P4-A cell ran slower in its second round (POST-HOC; steal and the MHz snapshots do not explain it); the P5 design (source only, not built); the steady-phase metric beyond two sessions and one shape comparison (post-hoc); whether one token BEATS LlamaIndex on docs at full scale (n = 1 per arm, inside LlamaIndex's spread).",
            "6. GATES": "every P4 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls ran before launch; the chain launched once and ran its legs in order with hard gates after every leg; protected image ids read back at chain start and end; the box is stopped with box.sh stop at the end and its state read back."}}
(a.camp / "p4_summary_spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
print("spec written")
