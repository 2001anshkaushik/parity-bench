#!/usr/bin/env python3
"""P3 report: every figure is read from the committed P3 files (analysis_p3docs.json, analysis_p3b.json, gate_controls*.json,
gates/*.json, master_done.json, p3d_build.json, the pre-registration and its amendments); readings, NOT RUN prose and the
self-audit are prose from p3_summary_spec.json.

    p3_report.py <campaign_dir> --out-md <md> --out-json <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_report import INPUTS, load, n, pct, share, table  # noqa: E402

LEG_HEAD = ["leg", "span docs/s", "excl. eleven docs/s", "ok/rows", "CPU-s/doc", "service cores", "utilisation (of 32)",
            "idle cores", "idle spin cores", "sampled memory peak", "steal, MHz"]


def f4(x): return "—" if x is None else f"{x:.4f}"
def f3(x): return "—" if x is None else f"{x:.3f}"
def mb(x): return "—" if x is None else f"{x / 1e6:,.0f} MB"


def mem_peak(m):
    if not m or "peak_bytes" not in m:
        return (m or {}).get("status", "—") if m else "—"
    return mb(m["peak_bytes"].get("total"))


def leg_rows(L: Dict[str, Any], names: List[str]) -> List[List[str]]:
    rows = []
    for nm in names:
        x = L.get(nm)
        if not x:
            rows.append([nm, "NOT RUN / absent"] + ["—"] * 9)
            continue
        rows.append([x["dir"], f4(x["span"]["docs_per_s"]), f4(x["excluded_straggler"]["docs_per_s"]), n(x["span"]["ok"]) + "/" + n(x["n"]),
                     f3(x.get("cpu_s_per_doc")), f3(x.get("engine_cores")), share(x.get("utilisation")), f3(x.get("idle_cores")),
                     f3(x.get("idle_spin_cores")), mem_peak(x.get("memory")),
                     f"steal {share(x.get('steal_share'), 2)}, {'—' if x.get('mhz_mean') is None else format(x['mhz_mean'], '.1f')} MHz"])
    return rows


def readj(c: Path, name: str) -> Optional[Any]:
    f = c / name
    if not f.exists():
        return None
    INPUTS[name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    return json.loads(f.read_text())


def controls(c: Path) -> List[Dict[str, Any]]:
    runs = []
    for f in [c / "gate_controls.json"] + sorted(c.glob("gate_controls_run*.json"), key=lambda p: int(p.stem.split("run")[-1])):
        if f.exists():
            INPUTS[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            runs.append(dict(json.loads(f.read_text()), file=f.name))
    return runs


def sec_controls(runs: List[Dict[str, Any]]) -> List[str]:
    out = ["## Gate controls (the P3 rule: every gate whole, in its real runtime, positive must PASS, null must FAIL)", ""]
    if not runs:
        return out + ["No control record.", ""]
    for r in runs:
        out += [f"**{r['file']}** (run {r.get('run', 1)}): {n(r['n_pass'])} of {n(r['n'])} controls as expected → all_pass **{r['all_pass']}** "
                f"({r['seconds']} s, boot {str(r.get('boot_id'))[:8]}).", ""]
    last = runs[-1]
    by: Dict[str, Dict[str, List[str]]] = {}
    for x in last["controls"]:
        k = "positive" if x["control"].startswith("positive") else "null"
        by.setdefault(x["gate"], {"positive": [], "null": []})[k].append(
            f"{x['control'].split(': ', 1)[-1]} → {'as expected' if x['pass'] else 'NOT AS EXPECTED'} (expected {x['expect']}, got {x['got']})")
    out += table(["gate", "positive control (must PASS)", "null control(s) (must FAIL)"],
                 [[g, "; ".join(v["positive"]) or "—", "; ".join(v["null"]) or "—"] for g, v in by.items()])
    return out


def gate_rows(A: Dict[str, Any], G: Dict[str, Any], MG: List[Dict[str, Any]]) -> List[List[str]]:
    rows = []
    for g in MG:
        if g["gate"] in ("G_controls", "BUDGET", "PROTECTED_IDS", "G_build_D", "G_node_D"):
            rows.append([g["gate"], "pre-registered", g.get("detail", ""), g.get("status", ""), g.get("exit_code", "")])
    for k, v in sorted(G.items()):
        if k.startswith("G_memstat_"):
            rows.append([f"G_memstat ({v['leg']})", "≥ 1 row in the first leg's memstat.jsonl", n(v.get("rows")), v["outcome"], "—"])
    d = A["docs"] or {}
    h = (d.get("P3_A") or {}).get("health_gate") or {}
    if h.get("conditions"):
        rows.append(["G_health_A", "all four health conditions", "; ".join(f"{k}: {n(v)}" for k, v in h["conditions"].items()),
                     "FIRED" if h["fired"] else "NOT FIRED", ""])
    sc = (d.get("P3_C") or {}).get("smoke_gate") or {}
    for s, v in (sc.get("per_shape") or {}).items():
        rows.append([f"G_smoke_C (vars={s})", "correctness first; then mean/mean(vars=1) − 1 > max(0.82%, spreads)",
                     f"chunks identical {n(v['correctness']['text_chunks_identical_to_vars1'])}; Δ {pct(v['delta_vs_vars1'])} vs {share(v['threshold'], 2)}",
                     "FIRED" if v["fired"] else "NOT FIRED", ""])
    sd = (d.get("P3_D") or {}).get("smoke_gate") or {}
    for v, pv in (sd.get("per_variant") or {}).items():
        a, b = pv.get("a") or {}, pv.get("b") or {}
        meas = (f"(a) (T−V)/T {pct(a['relative_reduction'])} vs spread_T {share(a['spread_T'], 2)}" if "relative_reduction" in a else f"(a) {a.get('status', '—')}")
        meas += f"; (b) {n(len(b['L_V']))} coverage losses" if "L_V" in b else f"; (b) {b.get('status', '—')}"
        rows.append([f"G_smoke_D ({v})", "(a) AND (b) (P2-C's gate)", meas, "FIRED" if pv.get("fired") else "NOT FIRED", ""])
    return rows


def sec_step0(pre: Dict[str, Any]) -> List[str]:
    s0 = (pre or {}).get("step0") or {}
    return ["## Step 0", "", f"**SSO:** {s0.get('sso', '—')}", "", f"**Harness stop-call search:** {s0.get('harness_stop_search', '—')}", ""]


def sec_p3b(v: Optional[Dict[str, Any]], notes: Dict[str, str]) -> List[str]:
    out = ["## P3-B — the video discriminator", ""]
    if not v:
        return out + [f"**NOT RUN** — {notes.get('B_not_run', '')}", ""]
    fr, idt = v["frames"], v["identity"]
    out += [f"**Frames:** {n(fr['n_frames'])} PNG frames from {', '.join(fr['videos'])} ({fr['argv']}); bare cells' frames identical to the manifest: "
            f"{n(idt['bare_frames_identical_to_manifest'])}; engine frame count equals the manifest's: {n(idt['engine_frame_count_equals_manifest'])}; "
            f"one model instance in every bare leg: {n(idt['bare_one_model_instance'])}; detections identical frame by frame between (a) and (b) (run 1): "
            f"{n(idt.get('detections_a_vs_b_identical_per_frame'))}.", ""]
    rows = []
    for nm, x in v["legs"].items():
        if not x:
            rows.append([nm, "NOT RUN"] + ["—"] * 6)
            continue
        rows.append([x["leg"], n(x.get("measured")), f4(x.get("F_s")), f3(x.get("cores_in_forward")), f3(x.get("caller_cpu_ratio")),
                     n(x.get("torch_threads")), n(len(x.get("callers") or [])), f4(x.get("frames_per_s")) if "frames_per_s" in x else "bare"])
    out += table(["leg", "measured frames", "forward per frame F (s)", "cores busy during the forward", "caller on-CPU / forward",
                  "torch threads", "caller threads", "frames/s (service legs)"], rows)
    cells = v.get("cells") or {}
    if cells:
        out += table(["cell", "legs", "F (s)", "mean", "spread"], [[c, ", ".join(x["legs"]), ", ".join(f4(y) for y in x["F_s"]), f4(x["mean"]), share(x["spread"], 2)]
                                                              for c, x in cells.items()])
    rd = v.get("reading") or {}
    if "a_vs_b" in rd:
        def rl(k, a, b):
            x = rd[k]
            sym = "≈" if x["approx_equal"] else ("<" if x["less"] else ">")
            return f"{a} {sym} {b} ({pct(x['ratio_minus_1'])} against {share(x['threshold'], 2)}; beyond the 0.82% floor: {n(x['beyond_floor_0_82pct'])})"
        out += ["**Relations (F):** " + "; ".join((rl("a_vs_b", "a", "b"), rl("a_vs_c", "a", "c"), rl("b_vs_c", "b", "c"))) + ".", ""]
    out += [f"**(2) Reading (pre-registered): {rd.get('verdict')}.**", ""]
    ins = v.get("inspection_1") or {}
    out += [f"**(1) Runtime inspection: {ins.get('reading')}.** RR task process families: {ins.get('rr_families')}; LlamaIndex detector process families: "
            f"{ins.get('li_families')}; only in RR: {ins.get('families_only_in_rr')}; only in LlamaIndex: {ins.get('families_only_in_li')}; RR OpenMP files: "
            f"{ins.get('rr_openmp_files')}; bare (a) {ins.get('bare_a_families')}, bare (b) {ins.get('bare_b_families')}.", ""]
    if notes.get("P3B"):
        out += [notes["P3B"], ""]
    return out


def sec_p3a(d: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    P, L = d.get("P3_A") or {}, d.get("legs") or {}
    out = ["## P3-A — the docs headline at full scale", "", "### Health smoke (a HEALTH gate by Ansh's ruling — not a performance proxy)", ""]
    out += table(LEG_HEAD, leg_rows(L, ["p3a_rr_h", "p3a_li_h"]))
    h = P.get("health_gate") or {}
    if h.get("conditions"):
        out += ["**G_health_A:** " + "; ".join(f"{k.replace('_', ' ')}: {n(v)}" for k, v in h["conditions"].items())
                + " → **" + ("FIRED" if h["fired"] else "NOT FIRED") + "**. Identity against P2-A's committed legs: "
                + "; ".join(f"{x['reference']}: {n(x['shared_ok_documents'])} shared ok documents, {n(len(x['chunk_lists_differ']))} differ" for x in h["identity"]) + ".", ""]
    fu = P.get("full") or {}
    out += ["### Full run (9,975, one run each)", ""]
    if fu.get("rr"):
        out += table(LEG_HEAD, leg_rows(L, ["p3a_rr_full", "p3a_li_full"]))
        out += [f"**The ratio, plainly: one RocketRide token {f4(fu['rr_docs_per_s'])} docs/s ÷ LlamaIndex 24 workers {f4(fu['li_docs_per_s'])} docs/s = "
                f"{f4(fu['ratio_rr_over_li'])}** (n = 1 per arm). LlamaIndex's smoke-scale replicate spread (8.19%, P2-A) bounds how much of it is readable: "
                f"readably at or above 0.85 needs ≥ {f4(fu['readable_band'][1])}, readably below needs < {f4(fu['readable_band'][0])} → **{fu['verdict']}**. "
                f"Excluded-straggler view: {f4(fu['excluded_straggler']['rr'])} vs {f4(fu['excluded_straggler']['li'])} docs/s = {f4(fu['excluded_straggler']['ratio_rr_over_li'])}.", ""]
        e, pa = fu["empty_documents"], fu["per_arm"]
        out += [f"Lost documents: RocketRide {n(pa['rr']['lost_documents']['n'])} ({', '.join(pa['rr']['lost_documents']['docs'][:10]) or 'none'}), LlamaIndex "
                f"{n(pa['li']['lost_documents']['n'])} ({', '.join(pa['li']['lost_documents']['docs'][:10]) or 'none'}). Empty documents: RocketRide {n(e['rr'])}, "
                f"LlamaIndex {n(e['li'])}; RocketRide-only {n(len(e['rr_only']))} ({', '.join(e['rr_only'][:20]) or 'none'}); LlamaIndex-only {n(len(e['li_only']))} "
                f"({', '.join(e['li_only'][:20]) or 'none'}).", ""]
    else:
        out += [f"**NOT RUN** — {notes.get('A_full_not_run', 'see the gate table')}", ""]
    return out


def sec_p3c(d: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    P, L = d.get("P3_C") or {}, d.get("legs") or {}
    out = ["## P3-C — embedding thread shape (six thread variables in {1, 2, 4})", ""]
    sg = P.get("smoke_gate") or {}
    out += table(LEG_HEAD, leg_rows(L, ["p3c_t1_a", "p3c_t2_a", "p3c_t4_a", "p3c_t1_b", "p3c_t2_b", "p3c_t4_b"]))
    if sg.get("per_shape"):
        v1 = sg["vars1"]
        vd0 = v1.get("vector_max_abs_delta_run_a_vs_b") or {}
        out += [f"**vars=1 (reference):** {f4(v1['mean'])} docs/s, spread {share(v1['spread'], 2)}; vector max |Δ| run a vs run b (determinism reference): "
                f"{vd0.get('max_abs_delta') if vd0.get('max_abs_delta') is not None else vd0.get('status', '—')} over {n(vd0.get('chunks_compared'))} chunks.", ""]
        rows = []
        for s, v in sg["per_shape"].items():
            vds = "; ".join((f"{x.get('max_abs_delta'):.3g} over {n(x.get('chunks_compared'))} chunks" if x.get("max_abs_delta") is not None else str(x.get("status")))
                            for x in v["vector_max_abs_delta_vs_vars1"])
            rows.append([f"vars={s}", n(v["correctness"]["text_chunks_identical_to_vars1"]), vds, f4(v["mean"]), share(v["spread"], 2),
                         pct(v["delta_vs_vars1"]), share(v["threshold"], 2), "FIRED" if v["fired"] else "NOT FIRED"])
        out += ["**Correctness first, then speed:**", ""] + table(["shape", "text chunks identical to vars=1", "embedding max |Δ| vs vars=1 (run a; run b)",
                                                                   "mean docs/s", "spread", "Δ vs vars=1", "threshold", "gate"], rows)
        out += [f"**G_smoke_C:** fired {sg['fired_shapes']}, winner {sg['winner']} (recomputed; agrees with the chain's record: {n(sg.get('agrees_with_chain_record'))}).", ""]
    fu = P.get("full") or {}
    if fu.get("leg"):
        ci = fu["chunk_identity_vs_comparator"]
        out += [f"**Full run:** vars={fu['winner']} {f4(fu['winner_docs_per_s'])} vs {fu['comparator']} {f4(fu['comparator_docs_per_s'])} docs/s = {pct(fu['delta'])} "
                f"({'readable' if fu['readable'] else 'UNREADABLE'} against 0.82%); chunk lists identical on {n(ci['documents_ok_in_both'])} documents ok in both, "
                f"differ {n(len(ci['chunk_lists_differ']))}, lost {n(len(ci['lost_by_b']))}.", ""]
    else:
        out += [f"**Full run: NOT RUN** — {fu.get('reason', '')}", ""]
    if notes.get("P3C"):
        out += [notes["P3C"], ""]
    return out


def sec_p3d(d: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    P, L = d.get("P3_D") or {}, d.get("legs") or {}
    out = ["## P3-D — the parser rerun (P2-C amended; rr:p3-pdfium)", ""]
    b = P.get("build") or {}
    if b.get("image"):
        chk = b.get("in_image_check") or {}
        out += [f"**Build (p3d_build.json):** {b['image']} `{str(b.get('image_id'))[:19]}` FROM {b.get('from')}; in-image check (engine Python): ok={chk.get('ok')}, "
                f"pypdfium2 {chk.get('pypdfium2')}, {n(chk.get('pages'))} page(s) / {n(chk.get('chars'))} characters, node flags {chk.get('pdfium_pure')} / "
                f"{chk.get('pdfium_hybrid')}, rc {b.get('in_image_check_rc')} → **G_build_D {'PASS' if b.get('gate_G_build_C_pass') else 'FAIL'}**.", ""]
    else:
        out += ["**Build: NOT RUN or no record.**", ""]
    ng = P.get("node_gates") or {}
    if any(ng.values()):
        out += ["**G_node_D:** " + "; ".join(f"{v}: {g['outcome'].split(' —')[0]} (docs {n((g.get('counters') or {}).get('docs'))}, text {n((g.get('counters') or {}).get('text'))}, "
                                             f"fallback {n((g.get('counters') or {}).get('fallback'))}, errors {n((g.get('counters') or {}).get('errors'))})"
                                             for v, g in ng.items() if g) + ".", ""]
    cor = P.get("correctness_384") or {}
    if cor:
        rows = [[k, n(v["documents"]), n(v["empty"]["reference"]), n(v["empty"]["candidate"]), n(v["n_loses"]),
                 ", ".join(v["candidate_empty_where_reference_recovers"][:8]) or "—", n(len(v["candidate_recovers_where_reference_empty"])),
                 f"{f3(v['char_ratio'].get('p5'))} / {f3(v['char_ratio'].get('p50'))} / {f3(v['char_ratio'].get('p95'))}",
                 f"{f3(v['dice'].get('min'))} / {f3(v['dice'].get('p5'))} / {f3(v['dice'].get('p50'))}"] for k, v in cor.items()]
        out += ["### Correctness first (384 slice)", ""] + table(["variant_run", "documents", "empty (Tika)", "empty (variant)", "variant empty where Tika recovers",
                                                                  "named", "variant recovers where Tika empty", "char ratio p5 / p50 / p95", "Dice min / p5 / p50"], rows)
    ed = P.get("eleven_detail") or {}
    if any(ed.values()):
        out += ["### The eleven at C=1 — p50 parse bracket per leg", ""] + table(
            ["leg", "of the eleven with all stamps", "p50 parse bracket (s)", "not ok"],
            [[x["leg"], n(x["documents"]), f3(x["p50_s"]), ", ".join(x["not_ok"]) or "—"] for arm in ("fix", "hyb", "pure") for x in ed.get(arm, [])])
    sg = P.get("smoke_gate") or {}
    out += [f"**G_smoke_D:** fired variants {sg.get('fired_variants')} (recomputed; agrees with the chain's record: {n(sg.get('agrees_with_chain_record'))}).", ""]
    spd = P.get("speed_384") or {}
    if spd:
        out += ["### Speed, 384 slice ABAB (typical documents; ungated)", ""] + table(LEG_HEAD, leg_rows(L, ["p3d_fix_a", "p3d_hyb_a", "p3d_pure_a", "p3d_fix_b", "p3d_hyb_b", "p3d_pure_b"]))
        for v, s in spd.items():
            out += [f"- {v} vs fixed Tika: {f4(s['a_mean'])} → {f4(s['b_mean'])} docs/s = {pct(s['delta_b_vs_a'])} against {share(s['threshold'], 2)} → "
                    f"{'readable' if s['readable'] else 'UNREADABLE'}; parse share fixed {[share(x) for x in s['parse_share']['fix']]} vs {v} {[share(x) for x in s['parse_share'][v]]}."]
        out += [""]
    for v, x in (P.get("full") or {}).items():
        if x.get("status"):
            out += [f"- **{v} full: {x['status']}** — {x.get('reason', '')}"]
            continue
        cc, sp = x.get("correctness") or {}, x.get("speed") or {}
        if cc.get("documents"):
            out += [f"- **{v} full correctness vs {cc['reference']}:** empty Tika {n(cc['empty']['reference'])} vs {v} {n(cc['empty']['candidate'])}; {v} empty where Tika recovers "
                    f"{n(cc['n_loses'])} ({', '.join(cc['candidate_empty_where_reference_recovers'][:15]) or 'none'}) → **{'ADOPTABLE' if cc['adoptable'] else 'NOT ADOPTABLE'}**; "
                    f"speed {f4(sp.get('comparator_docs_per_s'))} → {f4(sp.get('variant_docs_per_s'))} docs/s = {pct(sp.get('delta'))}."]
    vd = P.get("verdict") or {}
    out += ["", f"**P3-D verdict (pre-registered): 'a native parser gains little' is {vd.get('hypothesis_gains_little')}.** " + notes.get("P3D", ""), ""]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.campaign
    A = {"docs": load(c, "analysis_p3docs.json"), "video": load(c, "analysis_p3b.json"), "summary": load(c, "p3_summary_spec.json"),
         "prereg": load(c, "preregistration.json"), "bv": load(c, "P3_BLIND_VERIFICATION.json"), "md": readj(c, "master_done.json")}
    G = {}
    if (c / "gates").is_dir():
        for p in sorted((c / "gates").glob("*.json")):
            INPUTS[f"gates/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            G[p.stem] = json.loads(p.read_text())
    MG = (A["md"] or {}).get("gates") or []
    summ = A["summary"] or {}
    notes = summ.get("readings") or {}
    d = A["docs"] or {}
    head = ["# P3 — docs at full scale, the video discriminator, embedding thread shape, the parser rerun, and two drafts", "",
            f"Campaign `{c.name}`, branch feat/parity-p3 (cut from the P2 deliverable eaa65223). Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            "from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison is ABAB inside one box "
            "session (see Session); banked figures from earlier phases appear only as context.", ""]
    if A["bv"]:
        vs = (A["bv"].get("verifiers") or {}).values()
        head += [f"**Blind recomputation (P3_BLIND_VERIFICATION.json):** {A['bv'].get('outcome')} — {n(sum(v.get('figures_checked') or 0 for v in vs))} figures checked by "
                 f"{len(vs)} verifiers; plants caught {sum(1 for v in vs if v.get('plant_caught'))} of {len(vs)}; other mismatches "
                 f"{sum(len(v.get('other_mismatches') or []) for v in vs)}"
                 + (f" (round 1: {A['bv']['round_1']['outcome']} — one real mismatch in the prose, fixed; round 2 re-verified the changed "
                    f"sections: {A['bv']['round_2']['outcome']})" if A["bv"].get("round_1") else "") + ".", ""]
    fu = (d.get("P3_A") or {}).get("full") or {}
    rows = [["P3-A docs full-scale headline", fu.get("verdict", "NOT RUN"),
             (f"RR/LI = {f4(fu['ratio_rr_over_li'])} (n=1 per arm; readable band {f4(fu['readable_band'][0])}–{f4(fu['readable_band'][1])})" if fu.get("rr") else "full runs NOT RUN"),
             notes.get("P3A_short", "")],
            ["P3-B video discriminator", ((A["video"] or {}).get("reading") or {}).get("verdict", "NOT RUN"),
             f"(1) inspection: {((A['video'] or {}).get('inspection_1') or {}).get('reading', '—')}", notes.get("P3B_short", "")],
            ["P3-C embedding thread shape", f"winner {((d.get('P3_C') or {}).get('smoke_gate') or {}).get('winner')}",
             f"fired {((d.get('P3_C') or {}).get('smoke_gate') or {}).get('fired_shapes')}", notes.get("P3C_short", "")],
            ["P3-D parser rerun", f"'gains little': {((d.get('P3_D') or {}).get('verdict') or {}).get('hypothesis_gains_little', '—')}",
             f"fired variants {((d.get('P3_D') or {}).get('smoke_gate') or {}).get('fired_variants')}", notes.get("P3D_short", "")],
            ["P3-E drafts (laptop)", "written (not filed)", "—", notes.get("P3E_short", "")]]
    head += ["## Verdicts", ""] + table(["experiment", "verdict", "measured (from the analysis files)", "reading"], rows)
    head += sec_controls(controls(c))
    head += ["## Gate table (decisions)", "", "Every threshold was committed in preregistration.json before its stage ran; records in gates/ and master_done.json.", ""]
    head += table(["gate", "threshold", "measured", "outcome", "exit"], gate_rows(A, G, MG))
    head += sec_step0(A["prereg"])
    if summ.get("not_run"):
        head += ["## NOT RUN", ""] + [f"- {x}" for x in summ["not_run"]] + [""]
    if summ.get("recommendation"):
        head += ["## Recommendation", "", summ["recommendation"], ""]
    body = sec_p3a(d, notes) + sec_p3b(A["video"], notes) + sec_p3c(d, notes) + sec_p3d(d, notes)
    body += ["## P3-E — drafts (laptop; not filed)", "",
             f"- **Cross-document embedding batching design:** [P3E_DESIGN_CROSS_DOCUMENT_BATCHING.md](P3E_DESIGN_CROSS_DOCUMENT_BATCHING.md). {notes.get('P3E_design', '')}",
             f"- **Ticket draft, noDebug by default + MALLOC_ARENA_MAX=2:** [P3E_TICKET_DRAFT_NODEBUG_MALLOC.md](P3E_TICKET_DRAFT_NODEBUG_MALLOC.md). {notes.get('P3E_ticket', '')}", ""]
    am = sorted(c.glob("preregistration_amendment_*.json"))
    body += ["## Amendments to the pre-registration", ""] + ([f"- {p.name}: {json.loads(p.read_text()).get('label')}" for p in am] or ["- none"]) + [""]
    sess = set((d.get("session") or {}).get("boot_ids") or []) | set((A["video"] or {}).get("boot_ids") or [])
    body += ["## Session", "", f"Box boot ids across every P3 leg in this report: {sorted(sess)} ({'one session' if len(sess) == 1 else 'MORE THAN ONE SESSION'}).", ""]
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
