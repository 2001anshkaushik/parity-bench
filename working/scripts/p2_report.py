#!/usr/bin/env python3
"""P2 report: every figure is read from the committed P2 files (analysis_p2docs.json, analysis_p2b.json,
master_gates.jsonl, gates/*.json, p2c_build.json, the pre-registration and its amendments); readings, the NOT RUN
reasons' prose, the CloudTrail finding and the self-audit are prose from p2_summary_spec.json.

    p2_report.py <campaign_dir> --out-md <md> --out-json <json>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_report import INPUTS, STAGE_HEAD, load, n, pct, share, stage_rows, table  # noqa: E402

ORDER = ["admission", "parse_bracket", "split", "embed", "return"]


def mb(x: Optional[float]) -> str:
    return "—" if x is None else f"{x / 1e6:,.0f} MB"


def f4(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.4f}"


def f3(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.3f}"


def gates_dir(c: Path) -> Dict[str, Any]:
    out = {}
    for p in sorted((c / "gates").glob("*.json")) if (c / "gates").is_dir() else []:
        INPUTS[f"gates/{p.name}"] = __import__("hashlib").sha256(p.read_bytes()).hexdigest()[:16]
        out[p.stem] = json.loads(p.read_text())
    return out


def master_gates(c: Path) -> List[Dict[str, Any]]:
    f = c / "master_gates.jsonl"
    if not f.exists():
        return []
    INPUTS["master_gates.jsonl"] = __import__("hashlib").sha256(f.read_bytes()).hexdigest()[:16]
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]


def mem_peak(m: Optional[Dict[str, Any]]) -> str:
    if not m or "peak_bytes" not in m:
        return (m or {}).get("status", "—") if m else "—"
    return mb(m["peak_bytes"].get("total"))


# ------------------------------------------------------------------ gate table
def gate_rows(A: Dict[str, Any], G: Dict[str, Any], MG: List[Dict[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for k, v in G.items():
        if k.startswith("G_memstat_"):
            rows.append([f"G_memstat ({v['leg']})", "≥ 1 row in the first leg's memstat.jsonl", n(v.get("rows")), v["outcome"], "—"])
    viol = [g for g in MG if g.get("gate") == "MASTER" and "mandate" in (g.get("detail") or "")]
    legs = (A["docs"] or {}).get("legs") or {}
    nviol = sum(1 for x in legs.values() if ((x or {}).get("mandate") or {}).get("mandate_violation"))
    rows.append(["G_mandate (D0, every RocketRide docs cell)", "no violation", f"{n(nviol)} violations in {n(len(legs))} docs legs",
                 "STOPPED" if viol else ("PASS" if nviol == 0 else "VIOLATION"), "—"])
    sa = ((A["docs"] or {}).get("P2_A") or {}).get("smoke_gate") or {}
    if "ratio_rr_over_li" in sa:
        rows.append(["G_smoke_A (P2-A)", "mean RR / mean LI span docs/s ≥ 0.85 (384 slice)",
                     f"{f4(sa['ratio_rr_over_li'])} (RR {f4(sa['rr_mean'])}, LI {f4(sa['li_mean'])} docs/s; spreads RR {share(sa['spreads']['rr'], 2)}, "
                     f"LI {share(sa['spreads']['li'], 2)}; floors RR 0.82%, LI 9.87%)",
                     "FIRED" if sa["fired"] else "NOT FIRED", sa.get("known_bias", "")])
    else:
        rows.append(["G_smoke_A (P2-A)", "ratio ≥ 0.85", "—", "NOT EVALUABLE", ""])
    C = (A["docs"] or {}).get("P2_C") or {}
    b = C.get("build") or {}
    rows.append(["G_build_C (rr:p2-pdfium)", "build + in-image import-and-parse check pass, base ids unchanged",
                 (f"check ok={((b.get('in_image_check') or {}).get('ok'))}, chars {n((b.get('in_image_check') or {}).get('chars'))}, "
                  f"pypdfium2 {((b.get('in_image_check') or {}).get('pypdfium2'))}, rc {b.get('in_image_check_rc')}") if b.get("image") else "no build record",
                 "PASS" if b.get("gate_G_build_C_pass") else ("FAIL" if b.get("image") else "NOT RUN"), "—"])
    for v in ("hybrid", "pure"):
        g = G.get(f"G_node_C_{v}")
        if g:
            cc = g.get("counters") or {}
            rows.append([f"G_node_C ({v}, {g['leg']})", "node counters: docs ≥ 1 and text ≥ 1",
                         f"docs {n(cc.get('docs'))}, text {n(cc.get('text'))}, fallback {n(cc.get('fallback'))}, errors {n(cc.get('errors'))}",
                         g["outcome"].split(" —")[0], "—"])
    sg = C.get("smoke_gate") or {}
    for v, pv in (sg.get("per_variant") or {}).items():
        a, bb = pv.get("a") or {}, pv.get("b") or {}
        if "relative_reduction" in a:
            rows.append([f"G_smoke_C ({v}) (a) SPEED", "(T − V)/T > spread_T (p50 parse bracket over the eleven, C=1)",
                         f"(T − V)/T = {pct(a['relative_reduction'])} vs spread_T {share(a['spread_T'], 2)} (T {f3(a['T_mean_s'])} s, V {f3(a['V_mean_s'])} s)",
                         "HOLDS" if a["holds"] else "FAILS", "the eleven tail documents at C=1; HYBRID pays both parsers on fallbacks"])
        else:
            rows.append([f"G_smoke_C ({v}) (a) SPEED", "(T − V)/T > spread_T", a.get("status", "—"), "FAILS", ""])
        if "L_V" in bb:
            rows.append([f"G_smoke_C ({v}) (b) COVERAGE", "empty on 0 documents fixed Tika extracts (384 slice)",
                         f"{n(len(bb['L_V']))} documents{': ' + ', '.join(bb['L_V'][:12]) if bb['L_V'] else ''}",
                         "HOLDS" if bb["holds"] else "FAILS", "decided on the 384 slice, which holds none of the eleven"])
        else:
            rows.append([f"G_smoke_C ({v}) (b) COVERAGE", "0 documents", bb.get("status", "—"), "FAILS", ""])
        rows.append([f"G_smoke_C ({v}) → full run", "(a) AND (b)", "—", "FIRED" if pv.get("fired") else "NOT FIRED", ""])
    for k, v in G.items():
        if k.startswith("G_manip_B_"):
            rows.append([f"G_manip_B ({v['leg']}, {v['cell']})", v["rule"],
                         f"debugger loaded {n(v.get('debugger_loaded'))}; MALLOC_ARENA_MAX {v.get('malloc_arena_max_in_detector_process') or 'unset'}; "
                         f"detector OS threads {n(v.get('detector_process_os_threads'))}", v["outcome"].split(" —")[0], "—"])
    cg = (A["video"] or {}).get("correctness_gate")
    if cg:
        rows.append(["P2-B correctness (COMBINED vs baseline)", "chunk-identical 16/16 in both pairs",
                     "; ".join(f"{p['a']} vs {p['b']}: {p['videos_compared']} compared, chunk differ {len(p['chunk_hash_differs'])}, scores differ {len(p['frame_scores_differ'])}"
                               for p in cg.get("pairs", [])), cg["outcome"].split(" —")[0], "—"])
    for g in MG:
        if g.get("gate") == "BUDGET":
            rows.append(["budget", "8 h from the first leg", g.get("detail", ""), g.get("status", ""), "—"])
        if g.get("gate") == "PROTECTED_IDS":
            rows.append(["protected image ids (rr:patched, rr:patched-video)", "unchanged start → end", g.get("detail", ""), g.get("status", ""), "—"])
    return rows


# ------------------------------------------------------------------ sections
def leg_rows(L: Dict[str, Any], names: List[str]) -> List[List[str]]:
    rows = []
    for nm in names:
        x = L.get(nm)
        if not x:
            rows.append([nm, "NOT RUN / absent"] + ["—"] * 9)
            continue
        rows.append([x["dir"], f4(x["span"]["docs_per_s"]), f4(x["excluded_straggler"]["docs_per_s"]), n(x["span"]["ok"]) + "/" + n(x["n"]),
                     f3(x.get("cpu_s_per_doc")), f3(x.get("engine_cores")), share(x.get("utilisation")), f3(x.get("idle_cores")),
                     f3(x.get("idle_spin_cores")), mem_peak(x.get("memory")), f"steal {share(x.get('steal_share'), 2)}, {f3(x.get('mhz_mean'))} MHz"])
    return rows


LEG_HEAD = ["leg", "span docs/s", "excl. eleven docs/s", "ok/rows", "CPU-s/doc", "service cores", "utilisation (of 32)",
            "idle cores", "idle spin cores", "sampled memory peak", "steal, MHz"]


def sec_p2a(A: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    d = A["docs"] or {}
    P = d.get("P2_A") or {}
    L = d.get("legs") or {}
    out = ["## P2-A — the docs headline: one RocketRide token vs LlamaIndex's 24-worker optimum", ""]
    out += ["**Correctness first.** rr:p1-tikafix's output was decided in P1-B (chunk-identical to rr:patched on the 384 gate slice, and over "
            "the full corpus as context); P2-A changes no cell. Within this session:"]
    det = P.get("rr_within_session_determinism")
    if det:
        out[-1] += (f" RocketRide's two 384 runs agree on {n(det['documents_ok_in_both'])} documents ok in both, chunk lists differ on "
                    f"{n(len(det['chunk_lists_differ']))}, lost {n(len(det['lost_by_b']))}.")
    out += [""]
    sg = P.get("smoke_gate") or {}
    out += ["### Smoke (1): the 384 slice, C=32, ABAB two runs each", ""] + table(LEG_HEAD, leg_rows(L, ["p2a_rr_a", "p2a_li_a", "p2a_rr_b", "p2a_li_b"]))
    if "ratio_rr_over_li" in sg:
        out += [f"**Gate G_smoke_A:** mean RocketRide {f4(sg['rr_mean'])} vs mean LlamaIndex {f4(sg['li_mean'])} docs/s → ratio **{f4(sg['ratio_rr_over_li'])}** "
                f"against 0.85 → **{'FIRED' if sg['fired'] else 'NOT FIRED'}**. Beside it: within-session spreads RocketRide {share(sg['spreads']['rr'], 2)}, "
                f"LlamaIndex {share(sg['spreads']['li'], 2)}; noise floors RocketRide 0.82%, LlamaIndex 9.87%. Known bias (recorded before data): {sg['known_bias']}. "
                f"Recomputed here from the raw legs; agrees with the chain's record: {n(sg.get('agrees_with_chain_record'))}.", ""]
    an = P.get("anchor_96_c8") or {}
    out += ["### Smoke (2): the per-unit anchor, 96 slice, C=8 (no gate)", ""] + table(LEG_HEAD, leg_rows(L, ["p2a_an_rr_a", "p2a_an_li_a", "p2a_an_rr_b", "p2a_an_li_b"]))
    if an.get("rr_one_token_vs_li_one_worker"):
        c = an["rr_one_token_vs_li_one_worker"]
        out += [f"One RocketRide token {f4(c['b_mean'])} vs one LlamaIndex worker {f4(c['a_mean'])} docs/s → ratio {f3(an['ratio_rr_over_li'])} "
                f"({pct(c['delta_b_vs_a'])}) against max(9.87%, spreads) = {share(c['threshold'], 2)} → {'readable' if c['readable'] else 'UNREADABLE'}. "
                + notes.get("anchor", ""), ""]
    fu = P.get("full") or {}
    out += ["### Full run (9,975, one run each)", ""]
    if fu.get("rr"):
        out += table(LEG_HEAD, leg_rows(L, ["p2a_rr_full", "p2a_li_full"]))
        out += [f"**Verdict (pre-registered): {fu['verdict']}.** RocketRide one token {f4(fu['rr_docs_per_s'])} vs LlamaIndex 24 workers "
                f"{f4(fu['li_docs_per_s'])} docs/s → {pct(fu['delta_rr_vs_li'])} against ±9.87%. **Does one token match the 24-worker optimum at full "
                f"scale? {fu['one_token_matches_24_worker_optimum_at_full_scale']}.** Excluded-straggler view: {f4(fu['excluded_straggler']['rr'])} vs "
                f"{f4(fu['excluded_straggler']['li'])} docs/s ({pct(fu['excluded_straggler']['delta_rr_vs_li'])}).", ""]
        e = fu["empty_documents"]
        out += [f"Lost documents: RocketRide {n(fu['per_arm']['rr']['lost_documents']['n'])} ({', '.join(fu['per_arm']['rr']['lost_documents']['docs'][:10]) or 'none'}), "
                f"LlamaIndex {n(fu['per_arm']['li']['lost_documents']['n'])} ({', '.join(fu['per_arm']['li']['lost_documents']['docs'][:10]) or 'none'}). "
                f"Empty documents (not ok or zero chunks): RocketRide {n(e['rr'])}, LlamaIndex {n(e['li'])}; RocketRide-only {n(len(e['rr_only']))} "
                f"({', '.join(e['rr_only'][:20]) or 'none'}); LlamaIndex-only {n(len(e['li_only']))} ({', '.join(e['li_only'][:20]) or 'none'}).", ""]
    else:
        out += [f"**NOT RUN** — {notes.get('A_full_not_run', 'see the gate table and master_gates.jsonl')}", ""]
    return out


def sec_p2c(A: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    d = A["docs"] or {}
    C = d.get("P2_C") or {}
    L = d.get("legs") or {}
    out = ["## P2-C — the native parser rerun (pypdfium2; PURE and HYBRID)", ""]
    b = C.get("build") or {}
    if b.get("image"):
        chk = b.get("in_image_check") or {}
        out += [f"**Build (p2c_build.json):** {b['image']} `{str(b.get('image_id'))[:19]}` FROM {b.get('from')}; wheel installed by its RECORD "
                f"({', '.join(b.get('wheel_record_top_level') or [])}); in-image check (the engine's own Python): ok={chk.get('ok')}, pypdfium2 "
                f"{chk.get('pypdfium2')}, pypdfium2_cfg imported from {chk.get('pypdfium2_cfg')}, {n(chk.get('pages'))} page(s) / {n(chk.get('chars'))} "
                f"characters from 002_002489.pdf, node flags {chk.get('pdfium_pure')} / {chk.get('pdfium_hybrid')}; base ids before and after: "
                f"{b.get('base_ids_before_and_after')}. **G_build_C: {'PASS' if b.get('gate_G_build_C_pass') else 'FAIL'}.**", ""]
    else:
        out += ["**Build: NOT RUN or no record.**", ""]
    ng = C.get("node_gates") or {}
    if any(ng.values()):
        out += ["**G_node_C (the prototype actually ran):** " + "; ".join(
            f"{v}: {g['outcome'].split(' —')[0]} (docs {n((g.get('counters') or {}).get('docs'))}, text {n((g.get('counters') or {}).get('text'))}, "
            f"fallback {n((g.get('counters') or {}).get('fallback'))}, errors {n((g.get('counters') or {}).get('errors'))})" for v, g in ng.items() if g) + ".", ""]
    cor = C.get("correctness_384") or {}
    if cor:
        out += ["### Correctness first (384 slice; each variant run against the fixed-Tika run of the same pair)", ""]
        rows = []
        for k, v in cor.items():
            rows.append([k, n(v["documents"]), n(v["empty"]["reference"]), n(v["empty"]["candidate"]), n(v["n_loses"]),
                         ", ".join(v["candidate_empty_where_reference_recovers"][:8]) or "—", n(len(v["candidate_recovers_where_reference_empty"])),
                         f"{f3(v['char_ratio'].get('p5'))} / {f3(v['char_ratio'].get('p50'))} / {f3(v['char_ratio'].get('p95'))}",
                         f"{f3(v['dice'].get('min'))} / {f3(v['dice'].get('p5'))} / {f3(v['dice'].get('p50'))}"])
        out += table(["variant_run", "documents", "empty (Tika)", "empty (variant)", "variant empty where Tika recovers", "named",
                      "variant recovers where Tika empty", "char ratio p5 / p50 / p95", "Dice min / p5 / p50"], rows)
    sg = C.get("smoke_gate") or {}
    out += ["### Smoke (i): the eleven at C=1 — p50 parse bracket per leg", ""]
    ed = C.get("eleven_detail") or {}
    rows = [[x["leg"], n(x["documents"]), f3(x["p50_s"]), ", ".join(x["not_ok"]) or "—", n(x["incomplete_stamps"])] for arm in ("fix", "hyb", "pure") for x in ed.get(arm, [])]
    out += table(["leg", "of the eleven with all stamps", "p50 parse bracket (s)", "not ok", "incomplete stamps"], rows)
    out += [f"**Gate G_smoke_C:** fired variants {sg.get('fired_variants')} (recomputed here; agrees with the chain's record: {n(sg.get('agrees_with_chain_record'))}). "
            f"Known bias (recorded before data): {sg.get('known_bias', '')}", ""]
    spd = C.get("speed_384") or {}
    if spd:
        out += ["### Speed, 384 slice ABAB (typical documents; ungated)", ""] + table(LEG_HEAD, leg_rows(L, ["p2c_fix_a", "p2c_hyb_a", "p2c_pure_a", "p2c_fix_b", "p2c_hyb_b", "p2c_pure_b"]))
        for v, s in spd.items():
            out += [f"- {v} vs fixed Tika: {f4(s['a_mean'])} → {f4(s['b_mean'])} docs/s = {pct(s['delta_b_vs_a'])} against max(0.82%, spreads) "
                    f"{share(s['threshold'], 2)} → {'readable' if s['readable'] else 'UNREADABLE'}; parse share fixed {[share(x) for x in s['parse_share']['fix']]} vs "
                    f"{v} {[share(x) for x in s['parse_share'][v]]}."]
        out += [""]
    full = C.get("full") or {}
    out += ["### Full runs (per fired variant; correctness first)", ""]
    for v, x in full.items():
        if x.get("status"):
            out += [f"- **{v}: {x['status']}** — {notes.get(f'C_full_{v}', x.get('reason', ''))}"]
            continue
        cc = x.get("correctness") or {}
        if cc.get("documents"):
            out += [f"- **{v} correctness vs {cc['reference']}:** {n(cc['documents'])} documents; empty Tika {n(cc['empty']['reference'])} vs {v} "
                    f"{n(cc['empty']['candidate'])}; {v} empty where Tika recovers {n(cc['n_loses'])} ({', '.join(cc['candidate_empty_where_reference_recovers'][:15]) or 'none'}); "
                    f"recovers where Tika empty {n(len(cc['candidate_recovers_where_reference_empty']))}; char ratio p5/p50/p95 {f3(cc['char_ratio'].get('p5'))}/"
                    f"{f3(cc['char_ratio'].get('p50'))}/{f3(cc['char_ratio'].get('p95'))}; Dice min/p5/p50 {f3(cc['dice'].get('min'))}/{f3(cc['dice'].get('p5'))}/"
                    f"{f3(cc['dice'].get('p50'))}; failures {n(len(cc['failures']))} → **{'ADOPTABLE' if cc['adoptable'] else 'NOT ADOPTABLE'}**."]
        else:
            out += [f"- **{v} correctness:** {cc.get('status', '—')}"]
        sp = x.get("speed")
        if sp:
            out += [f"  - speed: {f4(sp['comparator_docs_per_s'])} → {f4(sp['variant_docs_per_s'])} docs/s = {pct(sp['delta'])} against 0.82% "
                    f"({'readable' if sp['readable'] else 'UNREADABLE'}); excluded-straggler {pct(sp['excluded_straggler_delta'])}; parse share "
                    f"{share((x.get('parse_share') or {}).get('comparator'))} → {share((x.get('parse_share') or {}).get('variant'))}; sampled memory peak "
                    f"{mem_peak((x.get('memory') or {}).get('comparator'))} → {mem_peak((x.get('memory') or {}).get('variant'))}."]
    vd = C.get("verdict") or {}
    out += ["", f"**P2-C verdict (pre-registered): the hypothesis 'a native parser gains little' is {vd.get('hypothesis_gains_little')}** "
            f"(bar {pct(vd.get('little_bar'))}; adoptable variants faster than the bar at full scale: {vd.get('variants_adoptable_and_faster_than_bar') or 'none'}). "
            + notes.get("P2C", ""), ""]
    return out


def sec_p2b(A: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    v = A["video"] or {}
    out = ["## P2-B — video configuration suspects, untraced (16 videos, K=16, T=4)", ""]
    if not v:
        return out + [f"**NOT RUN** — {notes.get('B_not_run', 'see master_gates.jsonl')}", ""]
    rows = []
    for nm, x in (v.get("legs") or {}).items():
        if not x:
            rows.append([nm, "NOT RUN"] + ["—"] * 7)
            continue
        rb, fw = x.get("readback") or {}, x.get("forward") or {}
        rows.append([x["dir"], f4(x["frames_per_s"]), f4(x["records_frames_per_s"]), n(x["errors"]),
                     f4(fw.get("forward_mean_s")), f3(fw.get("caller_cpu_ratio")),
                     f"pydevd {rb.get('pydevd_loaded')}, tools {rb.get('monitoring_tools_detector')}", str(rb.get("malloc_env_detector") or "unset"),
                     n(rb.get("os_threads_detector"))])
    out += table(["leg", "frames/s (export)", "frames/s (records)", "errors", "forward per frame (s)", "caller on-CPU / forward",
                  "debugger (env_probe; detector sys.monitoring)", "malloc env (detector)", "detector OS threads"], rows)
    cg = v.get("correctness_gate") or {}
    out += [f"**Correctness first:** COMBINED vs baseline — " + "; ".join(
        f"{p['a']} vs {p['b']}: {p['videos_compared']} videos, chunk hashes differ {len(p['chunk_hash_differs'])}, frame scores differ {len(p['frame_scores_differ'])}"
        for p in cg.get("pairs", [])) + f" → **{cg.get('outcome')}**.", ""]
    ctx = v.get("determinism_context") or {}
    if ctx:
        out += ["Determinism (context): " + "; ".join(f"{k}: {'identical' if x['identical'] else 'DIFFERS'} ({x['videos_compared']} videos)" for k, x in ctx.items()) + ".", ""]
    C = v.get("cells") or {}
    if C:
        out += table(["cell", "legs", "frames/s", "mean", "spread"],
                     [[c, ", ".join(x["legs"]), ", ".join(f4(y) for y in x["frames_per_s"]), f4(x["mean"]), share(x["spread"], 2)] for c, x in C.items()])
    rd = v.get("reading") or {}
    if rd.get("gap"):
        g, cb = rd["gap"], rd["combined"]
        out += [f"**Reading (pre-registered, PRIMARY frames/s):** gap LlamaIndex over RocketRide baseline {pct(g['li_over_base_minus_1'])} against "
                f"{share(g['threshold'], 2)} → {'reproduced' if g['reproduced_in_session'] else 'NOT reproduced'} in session; COMBINED over baseline "
                f"{pct(cb['comb_over_base_minus_1'])} against {share(cb['threshold'], 2)} ({'beyond' if cb['beyond_spread'] else 'within'} the replicate spread); "
                f"closure {f3(cb['closure'])} of the gap (bar 0.5). **Verdict: {rd.get('verdict')}.**", ""]
    else:
        out += [f"**Verdict: {rd.get('verdict')}**", ""]
    sf = rd.get("secondary_F")
    if sf:
        out += [f"Mechanism (secondary, reported beside): forward per frame baseline {f4(sf['F_base_s'])} s, COMBINED {f4(sf['F_comb_s'])} s, "
                f"LlamaIndex {f4(sf['F_li_s'])} s → COMBINED {pct(sf['comb_over_base_minus_1'])} vs baseline; closure on F {f3(sf['closure_on_F'])}.", ""]
    df = v.get("readback_differences_comb_vs_li")
    if df:
        keep = {k: x for k, x in df.items() if k != "thread_name_counts"}
        out += ["Read-back differences that remain between RocketRide COMBINED and LlamaIndex (detector process): "
                + "; ".join(f"{k}: {json.dumps(x)[:220]}" for k, x in keep.items()) + ".", ""]
    if notes.get("P2B"):
        out += [notes["P2B"], ""]
    return out


def sec_p2d(c: Path, notes: Dict[str, str]) -> List[str]:
    out = ["## P2-D — laptop, from source", ""]
    out += [f"- **Embedding trace:** [P2D_EMBEDDING_TRACE.md](P2D_EMBEDDING_TRACE.md). {notes.get('P2D_embedding', '')}",
            f"- **Wrapper product-fix ticket (DRAFT, not filed):** [P2D_WRAPPER_TICKET_DRAFT.md](P2D_WRAPPER_TICKET_DRAFT.md). {notes.get('P2D_ticket', '')}", ""]
    return out


def verdict_rows(A: Dict[str, Any], notes: Dict[str, str]) -> List[List[str]]:
    d = A["docs"] or {}
    P, C = d.get("P2_A") or {}, d.get("P2_C") or {}
    sg, fu = P.get("smoke_gate") or {}, P.get("full") or {}
    a_meas = (f"smoke ratio {f4(sg.get('ratio_rr_over_li'))} (gate 0.85: {'FIRED' if sg.get('fired') else 'NOT FIRED'})"
              + (f"; full {f4(fu['rr_docs_per_s'])} vs {f4(fu['li_docs_per_s'])} docs/s = {pct(fu['delta_rr_vs_li'])}" if fu.get("rr") else "; full NOT RUN"))
    a_ver = (f"{fu['verdict']} — matches at full scale: {fu['one_token_matches_24_worker_optimum_at_full_scale']}" if fu.get("rr")
             else ("NOT RUN at full scale" + (" (gate not fired)" if sg.get("fired") is False else "")))
    rd = (A["video"] or {}).get("reading") or {}
    cb = rd.get("combined") or {}
    b_meas = (f"closure {f3(cb.get('closure'))}; COMBINED {pct(cb.get('comb_over_base_minus_1'))} vs baseline; gap {pct((rd.get('gap') or {}).get('li_over_base_minus_1'))}"
              if cb else "—")
    vd = C.get("verdict") or {}
    c_meas = f"fired variants {((C.get('smoke_gate') or {}).get('fired_variants'))}; build {'PASS' if (C.get('build') or {}).get('gate_G_build_C_pass') else 'FAIL/NOT RUN'}"
    return [["P2-A docs headline", a_ver, a_meas, notes.get("P2A", "")],
            ["P2-B video configuration", str(rd.get("verdict") or "NOT RUN"), b_meas, notes.get("P2B_short", "")],
            ["P2-C native parser", f"'gains little': {vd.get('hypothesis_gains_little', '—')}", c_meas, notes.get("P2C_short", "")],
            ["P2-D source (laptop)", "done (source; no measurement)", "—", notes.get("P2D_short", "")]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.campaign
    A = {"docs": load(c, "analysis_p2docs.json"), "video": load(c, "analysis_p2b.json"), "summary": load(c, "p2_summary_spec.json"),
         "prereg": load(c, "preregistration.json"), "bv": load(c, "P2_BLIND_VERIFICATION.json")}
    G, MG = gates_dir(c), master_gates(c)
    summ = A["summary"] or {}
    notes = summ.get("readings") or {}
    head = ["# P2 — docs headline, parser rerun, video configuration suspects, and the source traces", "",
            f"Campaign `{c.name}`, branch feat/parity-p2 (cut from the P1 deliverable d367c99). Generated "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from committed analysis and gate files; every figure is computed from raw "
            "records and rounded only here. Every comparison is ABAB inside one box session (see Session); banked P0/P1/Stage-4 figures appear only "
            "as context.", ""]
    if A["bv"]:
        vs = (A["bv"].get("verifiers") or {}).values()
        head += [f"**Blind recomputation (P2_BLIND_VERIFICATION.json):** {A['bv'].get('outcome')} — "
                 f"{n(sum(v.get('figures_checked') or 0 for v in vs))} figures checked by {len(vs)} verifiers; plants caught "
                 f"{sum(1 for v in vs if v.get('plant_caught'))} of {len(vs)}; other mismatches {sum(len(v.get('other_mismatches') or []) for v in vs)}.", ""]
    head += ["## Verdicts", ""] + table(["experiment", "verdict", "measured (from the analysis files)", "reading"], verdict_rows(A, notes))
    head += ["## Gate table", "", "Every threshold was committed in preregistration.json before its stage ran; each gate's record is in gates/ and "
             "master_gates.jsonl.", ""] + table(["gate", "threshold", "measured", "outcome", "known bias (recorded before data)"], gate_rows(A, G, MG))
    if summ.get("not_run"):
        head += ["## NOT RUN", ""] + [f"- {x}" for x in summ["not_run"]] + [""]
    if summ.get("cloudtrail"):
        head += ["## The 08:18Z stop (CloudTrail, read-only)", "", summ["cloudtrail"], ""]
    if summ.get("recommendation"):
        head += ["## Recommendation", "", summ["recommendation"], ""]
    body = sec_p2a(A, notes) + sec_p2c(A, notes) + sec_p2b(A, notes) + sec_p2d(c, notes)
    am = sorted(c.glob("preregistration_amendment_*.json"))
    body += ["## Amendments to the pre-registration", ""] + [f"- {p.name}: {json.loads(p.read_text()).get('label')}" for p in am] + [""]
    sess = set(((A["docs"] or {}).get("session") or {}).get("boot_ids") or []) | set((A["video"] or {}).get("boot_ids") or [])
    body += ["## Session", "", f"Box boot ids across every P2 leg in this report: {sorted(sess)} "
             f"({'one session' if len(sess) == 1 else 'MORE THAN ONE SESSION'}).", ""]
    if summ.get("register"):
        body += ["## Register entries added", ""] + [f"- {x}" for x in summ["register"]] + [""]
    if summ.get("self_audit"):
        body += ["## SELF-AUDIT", ""] + [f"- **{k}:** {v}" for k, v in summ["self_audit"].items()] + [""]
    a.out_md.write_text("\n".join(head + body) + "\n")
    a.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS}, indent=1))
    print(f"wrote {a.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
