#!/usr/bin/env python3
"""P1 report: every figure is read from the committed analysis files of the P1 campaign (analysis_e2.json,
analysis_p1docs.json, analysis_v1full168.json, p1b_build.json, p1c_build.json, the P1-B gate files);
readings, ROI items and the self-audit are prose from p1_summary_spec.json / p1_roi_spec.json.

    p1_report.py <campaign_dir> --out-md <md> --out-json <json>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_report import INPUTS, STAGE_HEAD, load, n, pct, pts, share, stage_rows, table  # noqa: E402

ORDER = ["admission", "parse_bracket", "split", "embed", "return"]
SCOPE_RANK = {"CONFIG": 0, "THREADING": 0, "PATCH": 1, "PYTHON": 2, "CPP": 3}


def mb(x: Optional[int]) -> str:
    return "—" if x is None else f"{x / 1e6:,.0f} MB"


def verdict_rows(A: Dict[str, Any], notes: Dict[str, str]) -> List[List[str]]:
    e2, d, v = A["e2"] or {}, A["docs"] or {}, A["v1full"] or {}
    rows = []
    r = e2.get("reading") or {}
    rows.append(["P1-A E2 (video thread stall)",
                 ("READABLE — " if r.get("readable") else "UNREADABLE (null control) — ") + ", ".join(r.get("supported") or ["—"])
                 if r else "NOT RUN",
                 f"D (OFF legs) {n(r.get('D_off_s'))} s per frame; D (ON legs) {n(r.get('D_on_s'))} s" if r else "—",
                 notes.get("E2", "")])
    b = d.get("p1b") or {}
    rows.append(["P1-B Tika wrapper fix", b.get("verdict") or "NOT RUN",
                 (f"correctness {'PASS' if (b.get('correctness') or {}).get('pass') else 'FAIL'}; smoke "
                  f"{n((b.get('smoke') or {}).get('speed_ratio'), 1)}x at p50 on the 11, exec census drop "
                  f"{share((b.get('smoke') or {}).get('exec_census_drop'), 1)}; "
                  f"384 ABAB {pct((b.get('speed_384') or {}).get('delta_b_vs_a'))} vs {share((b.get('speed_384') or {}).get('threshold'), 2)}")
                 if b else "—", notes.get("P1B", "")])
    c = d.get("p1c") or {}
    ch, cp = c.get("correctness_hybrid") or {}, c.get("correctness_pure") or {}
    rows.append(["P1-C native parser", c.get("verdict") or "NOT RUN",
                 (f"HYBRID {'ADOPTABLE' if ch.get('adoptable') else 'NOT ADOPTABLE'} (loses {n(ch.get('n_loses'))}); "
                  f"PURE {'ADOPTABLE' if cp.get('adoptable') else 'NOT ADOPTABLE'} (loses {n(cp.get('n_loses'))}); "
                  f"HYBRID vs fixed Tika 384 {pct(((c.get('speed_384') or {}).get('hybrid_vs_fix') or {}).get('delta_b_vs_a'))}")
                 if c else "—", notes.get("P1C", "")])
    g = v.get("gap") or {}
    rows.append(["P1-D V1 at 168 videos", g.get("verdict") or "NOT RUN",
                 (f"LI/RR − 1 {pct(g.get('li_over_rr_minus_1'), 1)} (P0, 16 videos: {pct(g.get('p0_v1_gap_16_videos'), 1)}); "
                  f"margin {pts(g.get('margin_pp'))} vs +10 points") if g else "—", notes.get("P1D", "")])
    return rows


def gate_rows(A: Dict[str, Any]) -> List[List[str]]:
    d, e2, v = A["docs"] or {}, A["e2"] or {}, A["v1full"] or {}
    b, c = d.get("p1b") or {}, d.get("p1c") or {}
    rows = []
    for arm in ("rr", "li"):
        nc = ((e2.get("arms") or {}).get(arm) or {}).get("null_control") or {}
        rows.append([f"E2 null control ({arm})", "tracer ON vs OFF within max(0.82%, spreads) and identical output",
                     f"{pct(nc.get('delta_on_over_off'))} vs {share(nc.get('threshold'), 2)}; identical "
                     f"{[x.get('identical') for x in nc.get('output_identity', [])]}" if nc else "—",
                     ("PASS" if nc.get("pass") else "FAIL") if nc else "NOT RUN"])
    co = b.get("correctness") or {}
    rows.append(["P1-B correctness", "384 slice chunk-identical, no document lost",
                 f"{n(co.get('documents_ok_in_both'))} documents; {n(len(co.get('chunk_lists_differ') or []))} differ; "
                 f"{n(len(co.get('lost_by_b') or []))} lost" if co else "—",
                 ("PASS" if co.get("pass") else "FAIL — OUTPUT-CHANGING") if co else "NOT RUN"])
    sm = b.get("smoke") or {}
    rows.append(["P1-B smoke (full runs)", "≥ 10x at p50 on the 11 AND exec census drop ≥ 90%",
                 f"{n(sm.get('speed_ratio'), 1)}x; drop {share(sm.get('exec_census_drop'), 2)}" if sm else "—",
                 ("FIRED" if sm.get("fired") else "not fired") if sm else "NOT RUN"])
    for lab in ("hybrid", "pure"):
        x = c.get(f"correctness_{lab}") or {}
        rows.append([f"P1-C {lab.upper()} adoptable", "empty on no document the fixed-Tika full run recovers",
                     f"loses {n(x.get('n_loses'))}" if x.get("adoptable") is not None else (x.get("status") or "—"),
                     ("ADOPTABLE" if x.get("adoptable") else "NOT ADOPTABLE") if x.get("adoptable") is not None else "NOT RUN"])
    g = v.get("gap") or {}
    rows.append(["P1-D confirmation", "gap − max(0.82%, P0 V1 spreads) ≥ +10 points",
                 pts(g.get("margin_pp")) if g else "—", g.get("verdict") or "NOT RUN"])
    return rows


def docs_leg_rows(L: Dict[str, Any], names: List[str]) -> List[List[str]]:
    rows = []
    for nm in names:
        x = L.get(nm)
        if not x:
            rows.append([nm, "NOT RUN"] + ["—"] * 8)
            continue
        m = x.get("memory") or {}
        pk = m.get("peak_bytes") or {}
        rows.append([x["dir"], n(x["span"]["docs_per_s"], 4), n(x["excluded_straggler"]["docs_per_s"], 4),
                     n(x.get("engine_cores"), 2), n(x.get("idle_spin_cores"), 3), mb(pk.get("total")),
                     mb(pk.get("anon")), n((x.get("lost_documents") or {}).get("n")), share(x.get("parse_share")),
                     f"{share(x.get('steal_share'), 3)} / {n(x.get('mhz_mean'), 0)}"])
    return rows


LEG_HEAD = ["leg", "span docs/s", "docs/s without the 11", "engine cores", "idle spin cores",
            "memory peak (total, sampled 1 Hz in window)", "anon peak", "lost docs", "parse share of run total",
            "steal / MHz"]


def sec_e2(e2: Optional[Dict[str, Any]], notes: Dict[str, str]) -> List[str]:
    out = ["## P1-A — E2: the video thread stall (DIAGNOSTIC tracer; OFF legs are the null control)", ""]
    if not e2:
        return out + ["NOT RUN.", ""]
    rows = []
    for arm in ("rr", "li"):
        A = (e2.get("arms") or {}).get(arm) or {}
        for st in ("on", "off"):
            for x in A.get(st) or []:
                if "frames_per_s" not in x:
                    rows.append([x.get("leg"), "MISSING"] + ["—"] * 6)
                    continue
                f = x["forward"]
                rows.append([x["leg"], n(x["frames_per_s"]), n(f.get("forward_mean_s")), n(f.get("caller_cpu_ratio"), 2),
                             n(f.get("cores_in_forward"), 2), n(x.get("idle_cores"), 3),
                             mb(((x.get("memstat") or {}).get("sampled_peak_bytes") or {}).get("total")),
                             f"{share((x.get('session') or {}).get('steal_share'), 3)} / {n((x.get('session') or {}).get('mhz_open_mean'), 0)}"])
    out += table(["leg", "frames/s", "forward s per frame", "caller CPU / forward wall", "process cores in forward",
                  "idle cores (engine, before work)", "memory peak (sampled)", "steal / MHz"], rows)
    r = e2.get("reading") or {}
    out.append(f"**Readings (pre-registered rules; readable only if both null controls pass: "
               f"{'yes' if r.get('readable') else 'NO'}).** D = F_rr − F_li: OFF legs {n(r.get('D_off_s'))} s, ON legs {n(r.get('D_on_s'))} s per frame.")
    out.append("")
    a, c, b = r.get("a_GIL") or {}, r.get("c_CPU_contention") or {}, r.get("b_pool_or_affinity") or {}
    out += table(["candidate", "measured", "bar (0.5 × D_on)", "reading"], [
        ["(a) GIL contention", f"G_rr − G_li = {n(a.get('G_rr_minus_G_li_s'))} s per frame", n(a.get("bar_s")),
         "SUPPORTED" if a.get("supported") else "not supported"],
        ["(c) CPU contention", f"R_rr − R_li = {n(c.get('R_rr_minus_R_li_s'))} s per frame", n(c.get("bar_s")),
         "SUPPORTED" if c.get("supported") else "not supported"],
        ["(b) pool / affinity", f"{len(b.get('readback_differences') or [])} read-back difference(s); busy OMP workers "
                                f"RR {b.get('busy_workers_rr')} vs LI {b.get('busy_workers_li')}", "difference AND fewer busy workers",
         "SUPPORTED" if b.get("supported") else (b.get("note") or "not supported")]])
    for dff in b.get("readback_differences") or []:
        out.append(f"- read-back difference `{dff['field']}`: RocketRide `{json.dumps(dff['rr'])[:300]}` vs LlamaIndex `{json.dumps(dff['li'])[:300]}`")
    out.append("")
    out.append(f"**Supported:** {', '.join(r.get('supported') or ['—'])}. {notes.get('E2_detail', '')}")
    out.append("")
    for arm in ("rr", "li"):
        for x in ((e2.get("arms") or {}).get(arm) or {}).get("on") or []:
            t = x.get("trace") or {}
            if not t:
                continue
            ct = t.get("compute_threads_per_frame_s") or {}
            out.append(f"### {x['leg']} — compute threads per frame: on-CPU {n(ct.get('oncpu'))} s, run queue {n(ct.get('runq'))} s, "
                       f"sleep {n(ct.get('sleep'))} s; callers' total GIL wait {n(t.get('callers_gil_wait_total_per_frame_s'))} s per frame; "
                       f"G (in forward) {n((t.get('G_gil_wait_in_forward') or {}).get('mean_s'))} s")
            out.append("")
            out += table(["thread (top by on-CPU)", "name", "on-CPU s"],
                         [[str(y["tid"]), str(y.get("name")), n(y["oncpu_s"], 1)] for y in t.get("process_threads_top_oncpu", [])[:8]])
            ps = t.get("pyspy_gil") or {}
            if ps.get("top"):
                out.append("GIL holders (py-spy --gil, innermost frame): " + "; ".join(
                    f"{y['function'][:70]} {share(y['share'])}" for y in ps["top"][:5]))
                out.append("")
    return out


def sec_docs(d: Optional[Dict[str, Any]], b1: Optional[Dict[str, Any]], c1: Optional[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    L = (d or {}).get("legs") or {}
    b = (d or {}).get("p1b") or {}
    out += ["## P1-B — the Tika wrapper fix", ""]
    if b1:
        out.append(f"**Build (p1b_build.json):** rr:p1-tikafix `{b1.get('image_id', '')[:19]}` FROM rr:patched; "
                   f"{(b1.get('scope') or {}).get('inline_image_extraction')}; {(b1.get('scope') or {}).get('external_tool_probes')}. "
                   f"Protected image ids before and after: {b1.get('protected_ids_before_and_after')}.")
        out.append("")
    co = b.get("correctness") or {}
    out.append("**Correctness first (384 slice, C=32):** " + (
        f"{n(co.get('documents_ok_in_both'))} documents ok in both; chunk lists differ on {n(len(co.get('chunk_lists_differ') or []))}; "
        f"lost by the fix {n(len(co.get('lost_by_b') or []))}; gained {n(len(co.get('gained_by_b') or []))} → "
        f"**{'PASS (pure win)' if co.get('pass') else 'FAIL — OUTPUT-CHANGING'}**" if co else "NOT RUN") + ".")
    out.append("")
    cf = b.get("correctness_full_corpus_context") or {}
    if cf:
        out.append(f"**Context — chunk identity over the full 9,975 (not the gate; the eleven stragglers are only here):** "
                   f"{n(cf.get('documents_ok_in_both'))} documents ok in both; differ {n(len(cf.get('chunk_lists_differ') or []))} "
                   f"({(cf.get('chunk_lists_differ') or [])[:10]}); lost by the fix {n(len(cf.get('lost_by_b') or []))}; gained "
                   f"{n(len(cf.get('gained_by_b') or []))}; stragglers ok in both {n(len(cf.get('stragglers_ok_in_both') or []))}, of which differ "
                   f"{n(len(cf.get('stragglers_differ') or []))}.")
        out.append("")
    sm = b.get("smoke") or {}
    if sm:
        out.append(f"**Smoke (E1's engine path on the 11, this session):** p50 baseline {n(sm['base']['p50_wall_s'], 1)} s vs fixed "
                   f"{n(sm['fix']['p50_wall_s'], 2)} s → {n(sm.get('speed_ratio'), 1)}x; exec census {n(sm['base']['exec_census_total'])} → "
                   f"{n(sm['fix']['exec_census_total'])} (drop {share(sm.get('exec_census_drop'), 2)}) → **{'FIRED' if sm.get('fired') else 'not fired'}**.")
        out.append("")
        out += table(["document", "baseline s", "fixed s"], [[k, n(v, 1), n(sm["fix"]["per_doc"].get(k), 2)]
                                                              for k, v in sorted(sm["base"]["per_doc"].items())])
    sp = b.get("speed_384") or {}
    if sp:
        out.append(f"**Speed, 384 slice ABAB:** baseline {sp['a_docs_per_s']} vs fixed {sp['b_docs_per_s']} docs/s → "
                   f"{pct(sp['delta_b_vs_a'])} against {share(sp['threshold'], 2)} → {'readable' if sp['readable'] else 'UNREADABLE'}.")
        out.append("")
    fu = b.get("full")
    if fu:
        out.append(f"**Full 9,975, one run each:** baseline {n(fu['a_docs_per_s'], 4)} vs fixed {n(fu['b_docs_per_s'], 4)} docs/s → "
                   f"{pct(fu['delta_b_vs_a'])} against {share(fu['threshold'], 2)}; without the 11: {pct(fu['excluded_straggler']['delta_b_vs_a'])}.")
        out.append("")
    out += table(LEG_HEAD, docs_leg_rows(L, ["p1b_base_a", "p1b_fix_a", "p1b_base_b", "p1b_fix_b", "p1b_base_full", "p1b_fix_full"]))
    for nm in ("p1b_base_full", "p1b_fix_full"):
        x = L.get(nm) or {}
        d1 = x.get("d1") or {}
        if d1:
            out.append(f"### {x['dir']} — stages (PROFILE; {d1.get('docs_with_complete_stamps')} documents with a complete stamp set)")
            out.append("")
            out += table(STAGE_HEAD, stage_rows(d1["stages"], ORDER))
    c = (d or {}).get("p1c") or {}
    out += ["## P1-C — native parser prototype (pypdfium2; PURE and HYBRID)", ""]
    if c1:
        out.append(f"**Build (p1c_build.json):** rr:p1-pdfium `{(c1.get('image_id') or '')[:19]}` FROM rr:p1-tikafix; in-image check "
                   f"{json.dumps(c1.get('in_image_check'))[:300]}. PyMuPDF/MuPDF is AGPL-3.0: out of scope for an MIT product; pypdf excluded (slower than Tika in H6).")
        out.append("")
    for lab in ("hybrid", "pure"):
        x = c.get(f"correctness_{lab}") or {}
        if x.get("adoptable") is None:
            out.append(f"**Correctness {lab.upper()}:** {x.get('status') or 'NOT RUN'}.")
            out.append("")
            continue
        cr, di = x.get("char_ratio") or {}, x.get("dice") or {}
        out.append(f"**Correctness {lab.upper()} vs the fixed-Tika full run ({x['documents']} documents):** empty — fixed Tika "
                   f"{n(x['empty']['reference'])}, {lab} {n(x['empty']['candidate'])}; {lab} empty where Tika recovers: "
                   f"{n(x['n_loses'])} {x['candidate_empty_where_reference_recovers'][:20]}; recovers where Tika is empty: "
                   f"{n(len(x['candidate_recovers_where_reference_empty']))}; character ratio p5/p50/p95 {n(cr.get('p5'), 3)} / "
                   f"{n(cr.get('p50'), 3)} / {n(cr.get('p95'), 3)}; Dice p5/p50/p95 {n(di.get('p5'), 3)} / {n(di.get('p50'), 3)} / "
                   f"{n(di.get('p95'), 3)}; failures {n(len(x.get('failures') or []))} → **{'ADOPTABLE' if x['adoptable'] else 'NOT ADOPTABLE'}**.")
        out.append("")
    for k in ("hybrid_vs_fix", "pure_vs_fix"):
        sp = (c.get("speed_384") or {}).get(k) or {}
        if sp:
            out.append(f"**384 ABAB, {k.replace('_', ' ')}:** {sp['a_docs_per_s']} vs {sp['b_docs_per_s']} docs/s → "
                       f"{pct(sp['delta_b_vs_a'])} against {share(sp['threshold'], 2)} → {'readable' if sp['readable'] else 'UNREADABLE'}.")
            out.append("")
    for k in ("full_hybrid_vs_fix", "full_pure_vs_fix"):
        fu = c.get(k)
        if fu:
            out.append(f"**Full 9,975, {k[5:].replace('_', ' ')}:** {n(fu['a_docs_per_s'], 4)} vs {n(fu['b_docs_per_s'], 4)} docs/s → "
                       f"{pct(fu['delta_b_vs_a'])} (one run each; readable iff beyond {share(fu['threshold'], 2)}).")
            out.append("")
    out += table(LEG_HEAD, docs_leg_rows(L, ["p1c_hyb_full", "p1c_pure_full", "p1c_fix_a", "p1c_hyb_a", "p1c_pure_a",
                                              "p1c_fix_b", "p1c_hyb_b", "p1c_pure_b"]))
    out.append(f"**Verdict (pre-registered):** {c.get('verdict') or 'NOT RUN'}.")
    out.append("")
    return out


def sec_v1full(v: Optional[Dict[str, Any]]) -> List[str]:
    out = ["## P1-D — V1 at 168 videos", ""]
    if not v or not (v.get("rr") or v.get("li")):
        return out + ["NOT RUN (see NOT RUN).", ""]
    rows = []
    for arm in ("rr", "li"):
        x = v.get(arm)
        if x:
            dt = x.get("determinism_vs_p0_v1") or {}
            rows.append([arm, x["dir"], n(x.get("videos")), n(x.get("errors")), n(x.get("frames")), n(x.get("frames_per_s")),
                         n(x.get("cpu_s_per_frame")), mb(((x.get("memstat") or {}).get("sampled_peak_bytes") or {}).get("total")),
                         f"{dt.get('videos_compared')} videos, identical {n(dt.get('identical'))}"])
    out += table(["arm", "leg", "videos", "errors", "frames", "frames/s", "CPU-s per frame", "memory peak (sampled)",
                  "determinism vs P0 V1"], rows)
    g = v.get("gap") or {}
    if g:
        out.append(f"**Gap:** LI/RR − 1 = {pct(g['li_over_rr_minus_1'], 1)} (P0, 16 videos: {pct(g.get('p0_v1_gap_16_videos'), 1)}); noise "
                   f"max(0.82%, P0 spreads) {share(g['noise'], 2)}; margin {pts(g['margin_pp'])} → **{g['verdict']}**; same session {n(g.get('same_session'))}.")
        out.append("")
    return out


def roi(items: List[Dict[str, Any]], shares: Dict[str, Optional[float]]) -> List[str]:
    items = [dict(x, share=shares.get(x.get("share_key"))) for x in items]
    items = sorted(items, key=lambda x: (SCOPE_RANK.get(x["scope"], 9), -(x.get("share") or 0)))
    rows = []
    for i, x in enumerate(items, 1):
        sh = x.get("share")
        rows.append([str(i), x["bottleneck"], x["fix"], share(sh), f"{1 / (1 - sh):.2f}x" if sh is not None and sh < 1 else "—",
                     x["scope"], x.get("evidence", "")])
    return table(["rank", "bottleneck", "in-bounds single-instance fix", "(a) share of run total (D1, this session)",
                  "(b) 1/(1 − share)", "(c) scope", "evidence"], rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.campaign
    A = {"e2": load(c, "analysis_e2.json"), "docs": load(c, "analysis_p1docs.json"),
         "v1full": load(c, "analysis_v1full168.json"), "b1": load(c, "p1b_build.json"), "c1": load(c, "p1c_build.json"),
         "roi": load(c, "p1_roi_spec.json"), "summary": load(c, "p1_summary_spec.json"),
         "bv": load(c, "P1_BLIND_VERIFICATION.json")}
    summ = A["summary"] or {}
    notes = summ.get("readings") or {}
    head = ["# P1 — the first engine changes under the single-instance mandate", "",
            f"Campaign `{c.name}`, branch feat/parity-p1 (cut from the P0 deliverable fb211c2). Generated "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from committed analysis files; every figure is computed from raw "
            "records and rounded only here. Every comparison is ABAB inside one box session (see Session); banked P0 figures appear only as context.", ""]
    if A["bv"]:
        vs = (A["bv"].get("verifiers") or {}).values()
        head += [f"**Blind recomputation (P1_BLIND_VERIFICATION.json):** {A['bv'].get('outcome')} — "
                 f"{n(sum(v.get('figures_checked') or 0 for v in vs))} figures checked by {len(vs)} verifiers; plants caught "
                 f"{sum(1 for v in vs if v.get('plant_caught'))} of {len(vs)}; other mismatches {sum(len(v.get('other_mismatches') or []) for v in vs)}.", ""]
    head += ["## Verdicts", ""] + table(["experiment", "verdict", "measured (from the analysis files)", "reading"], verdict_rows(A, notes))
    head += ["## Gates", ""] + table(["gate", "threshold", "measured", "outcome"], gate_rows(A))
    rec = summ.get("recommendation")
    if rec:
        head += ["## P1-B vs P1-C recommendation", "", rec, ""]
    if notes.get("E2_cause"):
        head += ["## The E2 cause", "", notes["E2_cause"], ""]
    R = A["roi"] or {}
    if R:
        L = ((A["docs"] or {}).get("legs") or {})
        shares = {}
        for k in ("parse_bracket", "embed", "return", "split", "admission"):
            v = [((L.get(nm) or {}).get("d1") or {}).get("stages", {}).get(k, {}).get("share_of_run_total")
                 for nm in ("p1b_fix_a", "p1b_fix_b")]
            v = [x for x in v if x is not None]
            shares[f"docs_fixed:{k}"] = sum(v) / len(v) if v else None
            v = [((L.get(nm) or {}).get("d1") or {}).get("stages", {}).get(k, {}).get("share_of_run_total")
                 for nm in ("p1b_base_a", "p1b_base_b")]
            v = [x for x in v if x is not None]
            shares[f"docs_base:{k}"] = sum(v) / len(v) if v else None
        head += ["## Bottlenecks and in-bounds fixes, ranked by ROI (P0's three columns; scope first, then share)", "",
                 "(a) is the mean share of run total over this session's two stamped legs named by the item (P1-B's 384-slice "
                 "legs: baseline for the wrapper item, fixed for the rest). Scope rank, fixed before the P1 data: CONFIG and "
                 "THREADING, then PATCH, then PYTHON, then CPP.", ""] + roi(R.get("items", []), shares)
        for key, title in (("out_of_bounds", "Out of bounds (recorded, not proposed)"), ("not_run", "NOT RUN"),
                           ("register", "Register entries added")):
            if R.get(key):
                head += [f"### {title}", ""] + [f"- {x}" for x in R[key]] + [""]
    body = sec_e2(A["e2"], notes) + sec_docs(A["docs"], A["b1"], A["c1"]) + sec_v1full(A["v1full"])
    am = sorted(c.glob("preregistration_amendment_*.json"))
    body += ["## Amendments to the pre-registration", ""] + [f"- {p.name}: {json.loads(p.read_text()).get('label')}" for p in am] + [""]
    sess = set()
    for x in ((A["docs"] or {}).get("sessions") or []):
        sess.add(x)
    for arm in ("rr", "li"):
        for st in ("on", "off"):
            for x in (((A["e2"] or {}).get("arms") or {}).get(arm) or {}).get(st) or []:
                if x.get("summary"):
                    sess.add(x["summary"].get("boot_id"))
    for arm in ("rr", "li"):
        x = (A["v1full"] or {}).get(arm)
        if x:
            sess.add(x.get("boot_id"))
    body += ["## Session", "", f"Box boot ids across every P1 leg in this report: {sorted(s for s in sess if s)} "
             f"({'one session' if len({s for s in sess if s}) == 1 else 'MORE THAN ONE SESSION'}).", ""]
    if summ.get("self_audit"):
        body += ["## SELF-AUDIT", ""] + [f"- **{k}:** {v}" for k, v in summ["self_audit"].items()] + [""]
    md = "\n".join(head + body) + "\n"
    a.out_md.write_text(md)
    a.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS}, indent=1))
    print(f"wrote {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
