#!/usr/bin/env python3
"""P7-D drafts (laptop), every figure read from committed files and cited, never typed:
  (1) P7_UPSTREAM_PATCH_DRAFT.md — P6's patch description updated with P7-A/B: exactly what the 168-video correctness claim is
      and on what evidence; the patch keeps today's default thread count and is presented as output-identical at matched threads
  (2) P7_THREAD_TICKET_DRAFT.md — a SEPARATE ticket, 'default intra-op thread count for the detect node', from P6-C/P7-C and
      S5-A — written only if P6-C's pooled reading is readable; otherwise the file records why not
  (3) P7_CTO_BRIEF_DRAFT.md — P6's one-page brief updated with P7
Drafts only: nothing is sent, posted or filed.

    p7_drafts.py <p7_campaign_dir>
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "working" / "results"
P4, P5, P6 = RES / "parity_p4_20260925T092942Z", RES / "parity_p5_20260925T141647Z", RES / "parity_p6_20260925T175225Z"
S4 = RES / "batchsize_s4_20260921T013303Z" / "p5_li_video"
S5 = RES / "batchsize_s5_20260921T205917Z" / "analysis_output_shift.json"
SRC, BASE = ROOT / "working" / "nodes" / "p5_infer_src", ROOT / "engine" / "nodes" / "detect"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def diffstat(a: Path, b: Path):
    plus = minus = 0
    for ln in difflib.unified_diff(a.read_text().splitlines(), b.read_text().splitlines(), lineterm=""):
        if ln.startswith("+") and not ln.startswith("+++"):
            plus += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            minus += 1
    return plus, minus


def runs(groups, pred):
    return [g for g in groups if any(pred(r) for r in g["runs"])]


def main() -> int:
    camp = Path(sys.argv[1])
    A7 = json.loads((camp / "analysis_p7.json").read_text())
    PA = json.loads((camp / "p7a_frames.json").read_text())
    A6 = json.loads((P6 / "analysis_p6.json").read_text())
    p5a = json.loads((P5 / "analysis_p5a.json").read_text())
    build = json.loads((P5 / "p5a_build.json").read_text())
    F = {f["id"]: f for f in json.loads((P4 / "p4_facts.json").read_text())["facts"]}
    b4 = json.loads((P4 / "analysis_p4b.json").read_text())
    s4 = json.loads((S4 / "analysis_video.json").read_text())["legs"][0]
    s4t = json.loads((S4 / "li_k16" / "export_llamaindex_video_workers_blast.json").read_text())["provenance_video"]["posture"]["threads_env_in_process_torch"]
    s4w = int(s4["posture"].split("declared_workers=")[1].rstrip("]"))
    s5 = json.loads(S5.read_text())["s5a_thread_width_vs_default"]
    T1, PC = A7["P7_B_tier1"], A7.get("P7_C")
    a6, b6 = A6["P6_A"], A6["P6_B"]
    C = a6["cells"]
    m = lambda cell, k: C[cell][k]["mean"]  # noqa: E731
    per = T1["per_frame"]
    gIN, gTS = per["IN1002.avi#58"]["post_hoc_distinct_outputs"], per["TS3010a.avi#56"]["post_hoc_distinct_outputs"]
    is_stock = lambda r: "stock" in r  # noqa: E731
    is_proto = lambda r: "p5" in r or "prototype" in r  # noqa: E731
    frames168 = b6["per_arm"]["rr"]["frames"]
    diffv = [x["video"] for x in b6["correctness_vs_p1d"]["differ"]]
    pooled_ok = bool(PC) and PC["readings"]["pooled"]["F_t16_over_F_t4"] is not None and (PC.get("correctness_C2") or {}).get("pass") is True

    # ------------------------------------------------------------------ (1) patch description
    st = {f: diffstat(BASE / f, SRC / f) for f in ("IGlobal.py", "IInstance.py")} if BASE.exists() else {}
    base_img = {x.split()[1]: x.split()[0] for x in build["base_node"] if not x.startswith("UNKNOWN")}
    d = a6.get("descriptive_forward_degradation") or {}
    L = ["# DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)", "",
         "Updated in P7 (parity_p7_20260926T091049Z). Figures cite analysis_p5a.json, analysis_p6.json, p7a_frames.json and analysis_p7.json by key.", "",
         "## What changed", "",
         f"- `nodes/detect/IGlobal.py` (+{st.get('IGlobal.py', ('?', '?'))[0]} / -{st.get('IGlobal.py', ('?', '?'))[1]} lines): after building the one `Detector`, it starts an "
         "`InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of `make_device_lock()`; `endGlobal` stops the worker first.",
         f"- `nodes/detect/IInstance.py` (+{st.get('IInstance.py', ('?', '?'))[0]} / -{st.get('IInstance.py', ('?', '?'))[1]} lines): the locked `detector.detect(image)` becomes "
         "`self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.",
         f"- `nodes/detect/infer_worker.py` (new, {len((SRC / 'infer_worker.py').read_text().splitlines())} lines): each caller has at most one frame outstanding and blocks on its "
         "own `Future`, so a video's frames stay in order and each result returns to its caller.",
         f"- Base files: IInstance.py md5 {md5(BASE / 'IInstance.py') if BASE.exists() else '—'}, IGlobal.py md5 {md5(BASE / 'IGlobal.py') if BASE.exists() else '—'} — "
         + ("equal to the image's own node files [parity_p5 p5a_build.json base_node]" if BASE.exists() and base_img == {f: md5(BASE / f) for f in base_img} else "NOT checked against the image")
         + " (the local engine bundle, 3.3.1.35 per parity_p5_20260925T141647Z/PROGRESS_LOG.md:5, not in the repository). Patched: "
         + ", ".join(f"{k} {v}" for k, v in build["expected_p5_md5"].items()) + ".",
         "- **The thread count is not changed.** The patch keeps today's default; every identity claim below compares it with the current node AT THE SAME thread count.", "",
         "## Output identity — exactly what is claimed, and on what evidence", "",
         f"- **16 videos, matched threads (T=4), 16 in flight:** identical to the current node (per-video chunk sha256 AND frame scores) on 16/16 in every ABAB comparison "
         f"[analysis_p5a.json correctness.gate_pass = {p5a['correctness']['gate_pass']}; analysis_p6.json P6_A.correctness.gate_pass = {a6['correctness']['gate_pass']}].",
         f"- **16 videos, the out-of-box thread count (the six variables unset):** identical on 16/16 to the current node's committed out-of-box output "
         f"[analysis_p6.json P6_C.correctness.gate_pass = {A6['P6_C']['correctness']['gate_pass']}"
         + (f"; analysis_p7.json P7_C.correctness_C2.pass = {PC['correctness_C2']['pass']}]." if PC and PC.get("correctness_C2") else "]."),
         f"- **168 videos ({frames168:,} frames):** {b6['correctness_vs_p1d']['identical']} of {b6['correctness_vs_p1d']['videos_compared']} videos identical to ONE banked run of the "
         f"current node from another session [P6_B.correctness_vs_p1d]; {', '.join(diffv)} differ on one frame each. P7 re-ran those videos (two runs of each node, one session):",
         f"  - TS3010a.avi frame 56: the CURRENT node gives {len(runs(gTS, is_stock))} different outputs across sessions (the banked run, and two runs today that match every "
         "prototype run) [analysis_p7.json P7_B_tier1.per_frame.TS3010a.avi#56.post_hoc_distinct_outputs]. The difference does not need the patch.",
         f"  - IN1002.avi frame 58: the current node gave {len(runs(gIN, is_stock))} output in its {sum(sum(1 for r in g['runs'] if is_stock(r)) for g in gIN)} runs; the prototype gave "
         f"{len(runs(gIN, is_proto))} different outputs in its {sum(sum(1 for r in g['runs'] if is_proto(r)) for g in gIN)} runs, one of them equal to the current node's "
         "[..IN1002.avi#58.post_hoc_distinct_outputs]. On this frame the prototype varies run to run where the current node has not been seen to; the cause is not established.",
         f"  - Each of these changes moves the whole frame — every score (up to {max(x['max_rank_paired_score_delta'] for x in PA['frames'].values()):.4f} in P6-B vs the banked run "
         "[p7a_frames.json frames.*.max_rank_paired_score_delta]) — not a detection on the 0.3 threshold [p7a_frames.json reading: "
         f"{PA['reading']['reading']}]; every other frame of these videos agreed in all four P7 runs "
         f"[P7_B_tier1.other_frames.*.other_frames_where_any_two_of_the_four_runs_disagree: {sum(len(o['other_frames_where_any_two_of_the_four_runs_disagree']) for o in T1['other_frames'].values())} frames].",
         f"- **So the claim is:** output-identical to the current node at matched threads on every video compared, except {len(diffv)} frames of {frames168:,} where a single run is "
         "not a reference: on one (TS3010a.avi frame 56) the current node itself changed output across sessions; on the other (IN1002.avi frame 58) the prototype varied run to "
         "run where the current node has not (three runs each). On that frame the prototype is not shown output-identical.", "",
         "## Mandate compliance", "",
         "- One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector`; the on-token D0 read exactly one LWDETR before and after every measured leg (P5, P6, P7 gate records G_d0).",
         "- Threads only: one extra thread (`detect-infer`) per task process.", "",
         "## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB) [analysis_p6.json P6_A.cells.*]", "",
         f"- Frames/s: {m('p5_k16', 'frames_per_s'):.3f} vs {m('stock_k16', 'frames_per_s'):.3f} ({m('p5_k16', 'frames_per_s') / m('stock_k16', 'frames_per_s') - 1:+.1%}); one "
         f"LlamaIndex instance {m('li_k16', 'frames_per_s'):.3f}. 168 videos, block-interleaved: {b6['per_arm']['rr']['total_frames_per_s']:.3f} vs one LlamaIndex instance "
         f"{b6['per_arm']['li']['total_frames_per_s']:.3f} [P6_B.per_arm].",
         f"- CPU-s per frame: {m('p5_k16', 'cpu_s_per_frame'):.3f} vs {m('stock_k16', 'cpu_s_per_frame'):.3f} ({m('p5_k16', 'cpu_s_per_frame') / m('stock_k16', 'cpu_s_per_frame') - 1:+.1%}); "
         f"sampled memory peak {m('p5_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB vs {m('stock_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB.",
         "", "## Known residual", "",
         (f"- With 16 videos in flight the forward pass is {d['F_over_ref_minus_1']:+.1%} longer than with one (median {d['p50_over_ref_minus_1']:+.1%}, p99 {d['p99_over_ref_minus_1']:+.1%}) "
          "[P6_A.descriptive_forward_degradation; cross-session reference] — a tail; its cause was not measured." if d else "- Not measured."),
         "- The run-to-run variation on IN1002.avi frame 58 above.", "",
         "## What a reviewer should test", "",
         "- Output identity at the SAME thread count, on your own videos, at 1 and many in flight — and first the current node against ITSELF, several runs, so a mismatch can be attributed. "
         "Start with IN1002.avi frame 58 (run each node three or more times) and TS3010a.avi frame 56 (the current node alone changed output across sessions).",
         "- Teardown with frames queued; a frame whose detect raises; model-server (proxy) mode, where `make_device_lock()` was a no-op; the queue bound at very high concurrency.",
         "- Other code that used `IGlobal.device_lock` (none in the detect node itself)."]
    (camp / "P7_UPSTREAM_PATCH_DRAFT.md").write_text("\n".join(L) + "\n")

    # ------------------------------------------------------------------ (2) thread-count ticket
    if pooled_ok:
        rr = PC["readings"]
        pp = rr["pooled"]
        fps4 = m("p5_k16", "frames_per_s")
        T = ["# DRAFT — ticket: default intra-op thread count for the detect node (not filed, posted or sent)", "",
             "Figures cite analysis_p7.json P7_C (P6-C round 1 + P7-C round 2), analysis_p6.json P6_A and S5-A's analysis_output_shift.json by key.", "",
             "## What", "",
             "The detect node leaves the six thread variables unset, so torch runs its default intra-op pool (16 threads on the benchmark box, read back in-process "
             "[parity_p7 gates/G_cell_p7c_p5t16_2.json]). This ticket asks whether that "
             "default should change. It is separate from the single-inference-thread patch, which keeps today's default.", "",
             "## Speed at 4 vs 16 threads (with the single inference thread; 16 videos, 16 in flight; one LlamaIndex instance beside)", "",
             f"- The forward pass takes {pp['F_t16_over_F_t4']:.3f}x as long at 16 threads as at 4 (pooled over two rounds) [P7_C.readings.pooled.F_t16_over_F_t4] — "
             f"{'faster' if pp['F_t16_over_F_t4'] < 1 else 'SLOWER'}; per round {rr['round_1']['F_t16_over_F_t4']:.3f} and {rr['round_2']['F_t16_over_F_t4']:.3f} [..round_1, ..round_2].",
             f"- Frames/s: {pp['fps_p5_t16_mean']:.3f} at 16 threads [..pooled.fps_p5_t16_mean] vs {fps4:.3f} at 4 threads [analysis_p6.json P6_A.cells.p5_k16.frames_per_s.mean]; "
             f"one LlamaIndex instance at 16 threads {pp['fps_li_t16_mean']:.3f} [..pooled.fps_li_t16_mean].",
             "- Caveat: the 16-thread rounds and the 4-thread reference are in different stages and sessions (not ABAB); the canaries are reported beside in the P7 report and adjust nothing.", "",
             "## Output effect, stated plainly (S5-A, 16 videos, the current node) [batchsize_s5 analysis_output_shift.json s5a_thread_width_vs_default]", "",
             f"- At 4 threads vs today's default: labels identical on {s5['4']['frames_label_multiset_identical']:,} of {s5['4']['frames']:,} frames, but scores shift (by at least "
             f"{s5['4']['max_abs_score_delta_at_least']:.2e}) and {s5['4']['chunk_identical_videos']} of {s5['4']['videos']} videos are chunk-identical.",
             f"- Only unset / 16 threads reproduces today's default output: {s5['16']['chunk_identical_videos']} of {s5['16']['videos']} videos chunk-identical, score shift "
             f"{s5['16']['max_abs_score_delta_at_least']:.1f}.",
             "- So changing the default changes every downstream score (not the labels, on this set); consumers that store or compare scores would see a one-time shift.", "",
             "## Asked", "",
             "- Decide whether a speed gain justifies a one-time output change; measure it at matched concurrency on your own hardware first (the reading above is one box type).",
             "- Whatever the default, record the thread count with every output so runs can be compared."]
    else:
        why = ("P7-C did not run" if not PC else "P7-C's output was not identical to the out-of-box reference (G_correct_C2)"
               if not (PC.get("correctness_C2") or {}).get("pass") else "the pooled reading could not be computed")
        T = ["# Ticket draft: default intra-op thread count for the detect node — NOT DRAFTED", "", f"P6-C's pooled reading is not readable: {why}. Pre-registered: the ticket is drafted only if it is."]
    (camp / "P7_THREAD_TICKET_DRAFT.md").write_text("\n".join(T) + "\n")

    # ------------------------------------------------------------------ (3) CTO brief (one page)
    def f_(i):
        return f"{F[i]['value']} [{i}]"
    s_p3h = b4["item1_steady_phase"]["check_1"]["sessions"]["P3-A health"]["steady_ratio"]
    q1, q2 = a6["readings"]["Q1"], a6["readings"]["Q2"]
    B = ["# DRAFT — CTO brief: RocketRide vs LlamaIndex, single instance (not sent, posted or filed)", "",
         "Figures cite the P4 facts sheet [Fnn], the Stage 4 analysis, analysis_p6.json or analysis_p7.json by key.", "",
         "**What is compared.** Documents: ONE RocketRide token against LlamaIndex's 24-worker optimum. Video: ONE RocketRide token against ONE LlamaIndex instance.", "",
         "## Documents (one token vs LlamaIndex's 24-worker optimum)", "",
         f"- **Matches, not beats.** {f_('F01')} vs {f_('F02')} docs/s: {f_('F03')}, one run per arm, inside LlamaIndex's replicate spread; steady-phase ABAB ratios {f_('F27')} and "
         f"{s_p3h:.3f} [analysis_p4b.json item1_steady_phase.check_1.sessions.P3-A health.steady_ratio].",
         f"- **Needs an unshipped fix.** Stock {f_('F15')} docs/s; with the Tika wrapper fix {f_('F17')} ({f_('F18')}), {f_('F20')} chunk lists changed; the measured fix disables "
         "inline-image extraction for every pipeline (breaks image pipelines) — the shippable form is the source change in parity_p2 P2D_WRAPPER_TICKET_DRAFT.md:12.",
         f"- **Costs.** CPU per document {f_('F05')} vs {f_('F06')} s; memory peak {f_('F11')} vs {f_('F12')} MB; idle spin {f_('F09')} vs {f_('F10')} cores. "
         f"**Out of the box:** {f_('F15')} docs/s, {f_('F16')} CPU-s per document.", "",
         "## Video (one token vs ONE LlamaIndex instance)", "",
         f"- **Stock.** One LlamaIndex instance runs {f_('F28')} more frames/s than one stock token at 16 in flight (T=4); out of the box {f_('F31')} frames/s at {f_('F34')} CPU-s per frame. "
         f"Cause (P4): at 16 in flight RocketRide's forward slows x{f_('F58')}, LlamaIndex's x{f_('F59')}.",
         f"- **The single inference thread (a prototype, not shipped):** {m('p5_k16', 'frames_per_s'):.3f} vs one LlamaIndex instance {m('li_k16', 'frames_per_s'):.3f} frames/s — "
         f"parity {q1['pooled']['ratio']:.3f} [P6_A.readings.Q1.pooled.ratio], {q2['pooled']['ratio']:.3f}x stock [..Q2.pooled.ratio]; 168 videos block-interleaved "
         f"{b6['ratio_rr_over_li_totals']:.3f} [P6_B.ratio_rr_over_li_totals].",
         f"- **Output (P7).** Identical to stock at matched threads on every 16-video comparison; on 168 videos {b6['correctness_vs_p1d']['identical']} of 168 matched one banked stock run "
         f"[P6_B.correctness_vs_p1d]. The two misses are single frames where one run is not a reference: stock itself changed output across sessions on one "
         f"[P7_B_tier1 TS3010a.avi#56], and the prototype varied run to run on the other where stock did not in three runs [P7_B_tier1 IN1002.avi#58]. Not a threshold artifact "
         f"[p7a_frames.json: {PA['reading']['reading']}].",
         (f"- **Thread count.** With the single inference thread, the forward takes {PC['readings']['pooled']['F_t16_over_F_t4']:.2f}x as long at 16 threads as at 4 "
          f"[P7_C.readings.pooled.F_t16_over_F_t4] ({PC['readings'].get('verdict_forward')}; cross-session); T=4 stays the posture. Changing the default thread count changes scores "
          "(S5-A) — a separate ticket, drafted." if pooled_ok else "- **Thread count.** P6-C's pooled reading not readable; see the P7 report."),
         f"- **Context, not the comparison:** LlamaIndex's multi-instance configuration — {s4w} instances x {s4t} threads — runs {s4['frames_per_s']:.2f} frames/s (Stage 4) "
         f"[batchsize_s4 p5_li_video/analysis_video.json legs.0.frames_per_s; posture {s4['posture']}; threads li_k16 export provenance_video.posture.threads_env_in_process_torch].", "",
         "## Not claimed", "",
         "- That RocketRide BEATS LlamaIndex on documents; any unshipped fix or prototype figure as shipped behaviour; any cross-session ratio as a comparison; output identity on the two non-reproducible frames."]
    (camp / "P7_CTO_BRIEF_DRAFT.md").write_text("\n".join(B) + "\n")
    print(f"wrote P7_UPSTREAM_PATCH_DRAFT.md ({len(L)}), P7_THREAD_TICKET_DRAFT.md ({'drafted' if pooled_ok else 'NOT DRAFTED'}), P7_CTO_BRIEF_DRAFT.md ({len(B)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
