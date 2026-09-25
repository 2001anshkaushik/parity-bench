#!/usr/bin/env python3
"""P4 report: every figure is read from the committed P4 files (analysis_p4a.json, analysis_p4b.json, p4_facts.json,
gate_controls*.json, gates/*.json, chain_p4a_*_start/done.json, the pre-registration); readings, NOT RUN prose, the
register lines and the self-audit are prose from p4_summary_spec.json; the P5 design draft and the facts sheet are
embedded from their files.

    p4_report.py <campaign_dir> --out-md <md> --out-json <json>
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

CELL_ORDER = [("rr_k1", "RocketRide K=1"), ("rr_k16", "RocketRide K=16"), ("li_k1", "LlamaIndex K=1"),
              ("li_k16", "LlamaIndex K=16"), ("rr_k16_active", "RocketRide K=16, OMP_WAIT_POLICY=ACTIVE")]
LEG_ORDER = ["p4a_rr16_1", "p4a_li16_1", "p4a_rr1_1", "p4a_li1_1", "p4a_act_1",
             "p4a_rr16_2", "p4a_li16_2", "p4a_rr1_2", "p4a_li1_2", "p4a_act_2"]


def f(x, d=3):
    return "—" if x is None else f"{x:.{d}f}"


def mb(x):
    return "—" if x is None else f"{x / 1e6:,.0f} MB"


def readtxt(c: Path, name: str) -> Optional[str]:
    p = c / name
    if not p.exists():
        return None
    INPUTS[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return p.read_text()


def controls(c: Path) -> List[Dict[str, Any]]:
    runs = []
    for p in [c / "gate_controls.json"] + sorted(c.glob("gate_controls_run*.json"), key=lambda q: int(q.stem.split("run")[-1])):
        if p.exists():
            INPUTS[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            runs.append(dict(json.loads(p.read_text()), file=p.name))
    return runs


def gates(c: Path) -> Dict[str, Any]:
    out = {}
    for p in sorted((c / "gates").glob("*.json")) if (c / "gates").exists() else []:
        INPUTS[f"gates/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        out[p.stem] = json.loads(p.read_text())
    return out


def sec_gates(A: Dict[str, Any], G: Dict[str, Any], runs: List[Dict[str, Any]], start: Optional[Dict[str, Any]],
              done: Optional[Dict[str, Any]], pre: Dict[str, Any]) -> List[str]:
    out = ["## Gates", ""]
    rows = []
    legs = (A or {}).get("gated_legs") or {}
    d0 = [f"{k}: {G.get('G_d0_' + v, {}).get('outcome', '—')}" for k, v in legs.items()]
    cl = [f"{k}: {G.get('G_cell_' + v, {}).get('outcome', '—')}" for k, v in legs.items()]
    rows.append(["G_d0 (every leg)", "RR: export p0 d0_pre, d0_post, mandate clean; LI: one container, one process, --workers 1",
                 "; ".join(d0) or "—", "CLEAN" if d0 and all(x.endswith("CLEAN") for x in d0) else "SEE ROW"])
    rows.append(["G_cell (every leg)", "read-back T=4, OMP_WAIT_POLICY as declared, 16 videos, max in flight = K, stamps on every measured frame",
                 "; ".join(cl) or "—", "PASS" if cl and all(x.endswith("PASS") for x in cl) else "SEE ROW"])
    ms = [v for k, v in G.items() if k.startswith("G_memstat_")]
    rows.append(["G_memstat (first leg)", "memstat.jsonl ≥ 1 row", "; ".join(f"{m['leg']}: {n(m['rows'])} rows" for m in ms) or "—",
                 ms[0]["outcome"] if ms else "—"])
    gc = G.get("G_correct_active")
    rows.append(["G_correct_active (end of chain)", "every (ACTIVE, RR K=16) pair identical on 16/16 videos",
                 "; ".join(f"{p['a']} vs {p['b']}: {'identical' if p['identical'] else 'DIFFERS'}, {p['videos_compared']} videos" for p in (gc or {}).get("pairs", [])) or "—",
                 (gc or {}).get("outcome", "—")])
    ids0 = (start or {}).get("image_ids_at_start") or {}
    ids1 = (done or {}).get("image_ids_at_end") or {}
    prot = pre["carried_rules"]["protected_ids"]
    same = all(ids0.get(k) == v and ids1.get(k) == v for k, v in prot.items())
    rows.append(["protected image ids", "rr:patched, rr:patched-video unchanged start → end",
                 " ".join(f"{k} {ids1.get(k, '—')[:19]}" for k in prot), "UNCHANGED" if same else "CHANGED OR UNREAD"])
    dl = (done or {}).get("deadline_epoch")
    dls = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(dl))) if dl else "—"
    rows.append(["budget", "5 h from the first leg (deadline set as the chain enters its first leg)", f"run stage start {((start or {}).get('stage_start_utc') or '—')}; deadline {dls}; chain done {((done or {}).get('stage_complete_utc') or '—')}",
                 "WITHIN" if done and not any("NOT_RUN_budget" in x for x in done.get("legs", [])) else "SEE NOT RUN"])
    out += table(["gate", "rule", "measured", "outcome"], rows)
    out += ["### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)", ""]
    for r in runs:
        out += [f"**{r['file']}** (run {r.get('run', 1)}, boot {str(r.get('boot_id'))[:8]}): {n(r['n_pass'])} of {n(r['n'])} controls as expected → all_pass **{r['all_pass']}**.", ""]
    if runs:
        by: Dict[str, Dict[str, List[str]]] = {}
        for x in runs[-1]["controls"]:
            k = "positive" if x["control"].startswith("positive") else "null"
            by.setdefault(x["gate"], {"positive": [], "null": []})[k].append(
                f"{x['control'].split(': ', 1)[-1]} → {'as expected' if x['pass'] else 'NOT AS EXPECTED'} ({x['got']})")
        out += table(["gate", "positive control(s) (must PASS)", "null control(s) (must FAIL)"],
                     [[g, "<br>".join(v["positive"]) or "—", "<br>".join(v["null"]) or "—"] for g, v in by.items()])
    return out


def sec_p4a(A: Optional[Dict[str, Any]], notes: Dict[str, str]) -> List[str]:
    out = ["## P4-A — video concurrency (one session, ABAB, T=4, 16 videos, every leg alone)", ""]
    if not A:
        return out + ["NOT RUN or not analysed.", ""]
    corr = A["correctness"]
    ga = corr["G_correct_active"]
    out += ["### Correctness first", ""]
    rows = [[f"{p['a']} vs {p['b']}", n(p["videos_compared"]), "yes" if p["identical"] else "NO",
             ", ".join(p["chunk_hash_differs"]) or "none", ", ".join(p["frame_scores_differ"]) or "none"] for p in ga["pairs"]]
    out += table(["ACTIVE vs RR K=16", "videos compared", "identical", "chunk hash differs", "frame scores differ"], rows)
    out += [f"**CORRECTNESS GATE (ACTIVE vs RR K=16, 16/16): {'PASS' if ga['pass'] else 'FAIL — the ACTIVE cell is OUTPUT-CHANGING; no speed reading'}.**", ""]
    bs = []
    for k, v in corr["beside"].items():
        for x in (v if isinstance(v, list) else [v]):
            if x:
                bs.append([k.replace("_", " "), f"{x['a']} vs {x['b']}", n(x["videos_compared"]), "yes" if x["identical"] else "NO"])
    out += ["Beside (context: K should not change output):", ""] + table(["comparison", "legs", "videos", "identical"], bs)

    out += ["### Per cell (mean of two legs; spread = |a − b| / mean)", ""]
    rows = []
    for c, lab in CELL_ORDER:
        x = A["cells"].get(c)
        if not x:
            rows.append([lab] + ["NOT RUN"] + ["—"] * 7)
            continue
        rows.append([lab, f"{f(x['frames_per_s']['mean'])} ({share(x['frames_per_s']['spread'], 2)})",
                     f"{f(x['F_s']['mean'], 4)} ({share(x['F_s']['spread'], 2)})",
                     f"{f(x['forward_p50']['mean'], 4)} / {f(x['forward_p95']['mean'], 4)}",
                     share(x["lock_duty"]["mean"]), f(x["cores_in_forward"]["mean"], 2), f(x["cpu_s_per_frame"]["mean"]),
                     f(x["caller_switch_rate"]["mean"]), "/".join(str(t) for t in x["caller_threads"])])
    out += table(["cell", "frames/s (spread)", "forward s/frame F (spread)", "forward p50 / p95 s", "lock duty",
                  "cores busy in the forward", "CPU-s/frame", "caller switch rate", "caller threads (per leg)"], rows)

    out += ["### Per leg", ""]
    rows = []
    for nm in LEG_ORDER:
        d = (A.get("gated_legs") or {}).get(nm)
        x = (A.get("legs") or {}).get(nm)
        if not x:
            rows.append([nm, "NOT RUN / absent"] + ["—"] * 10)
            continue
        ss = x.get("session") or {}
        rows.append([d, f(x["frames_per_s"]), n(x["frames"]), f(x["F_s"], 4), share(x["lock_duty"]), f(x["cores_in_forward"], 2),
                     f(x["caller_cpu_ratio"], 3), f(x["cpu_s_per_frame"]), f(x["caller_switch"]["rate"]), mb(x["memory_peak_total_bytes"]),
                     f"{x['readback']['torch_num_threads']} / {x['readback']['OMP_WAIT_POLICY']}",
                     f"steal {share(ss.get('steal_share'), 3)}, {f(ss.get('mhz_open_mean'), 0)}→{f(ss.get('mhz_close_mean'), 0)} MHz"])
    out += table(["leg", "frames/s", "frames", "F s", "lock duty", "cores in fwd", "caller on-CPU", "CPU-s/frame", "switch rate",
                  "sampled mem peak", "torch T / OMP_WAIT_POLICY", "steal, MHz open→close"], rows)
    cpu = sorted({(x.get("session") or {}).get("cpu_model") for x in (A.get("legs") or {}).values() if x} - {None})
    out += [f"CPU model on every leg: {', '.join(cpu) or '—'}; sessions: {', '.join(s[:8] for s in A.get('sessions', []))}.", ""]

    out += ["### Forward pass per frame, full D1 metric set (per leg, seconds)", ""]
    rows = []
    for nm in LEG_ORDER:
        x = (A.get("legs") or {}).get(nm)
        if not x or not x.get("forward_D1"):
            continue
        m = x["forward_D1"]
        rows.append([x["dir"], n(m["count"]), f(m["mean"], 4), f(m["sd"], 4), f(m["min"], 4), f(m["p50"], 4), f(m["p90"], 4), f(m["p95"], 4),
                     f(m["p99"], 4), f(m["max"], 4), f(m["mean_over_p50"], 3)])
    out += table(["leg", "count", "mean", "sd", "min", "p50", "p90", "p95", "p99", "max", "mean/p50"], rows)

    rd = A["readings"]
    out += ["### Readings (pre-registered)", ""]
    r1 = rd["R1"]
    if r1.get("D_RR") is not None:
        out += table(["quantity", "value"], [
            ["D_RR = F(RR K=16) / F(RR K=1)", f(r1["D_RR"])], ["D_LI = F(LI K=16) / F(LI K=1)", f(r1["D_LI"])],
            ["D_RR / D_LI − 1", pct(r1["D_RR_over_D_LI_minus_1"])], ["S1 = the largest F spread of the four cells", share(r1["S1"], 2)],
            ["clause 1: RR degrades more than LI beyond S1", "yes" if r1["clause_degradation_beyond"] else "no"],
            ["RR K=1 frames/s vs LI K=1 frames/s", f"{f(r1['rr_k1_fps'])} vs {f(r1['li_k1_fps'])} ({pct(r1['rr_k1_over_li_k1_fps_minus_1'])})"],
            ["clause 2: RR K=1 f/s ≥ LI K=1 f/s", "yes" if r1["clause_rr_k1_fps_ge_li_k1"] else "no"],
            ["beside: sum of the four F spreads (context, not the rule)", share(r1["sum_of_four_F_spreads_context"], 2)]])
    out += [f"**R1 (CONCURRENCY-SPECIFIC): {r1['verdict']}**" + (f" — failed: {'; '.join(r1['failed_clauses'])}" if r1.get("failed_clauses") else "") + ".", ""]
    r2 = rd["R2_R3"]
    if r2.get("closure") is not None or r2.get("rr_degradation_minus_1") is not None:
        out += table(["quantity", "value"], [
            ["RR degradation F(K=16)/F(K=1) − 1", pct(r2.get("rr_degradation_minus_1"))],
            ["its threshold max(spread RR K=1, RR K=16)", share(r2.get("degradation_threshold"), 2)],
            ["precondition: degradation beyond its spreads", "yes" if r2.get("precondition_degradation_beyond") else "no"],
            ["precondition: correctness gate", "PASS" if r2.get("precondition_correctness") else "FAIL"],
            ["closure c = (F16 − F_ACTIVE) / (F16 − F1)", f(r2.get("closure"))],
            ["ACTIVE's reduction F16 / F_ACTIVE − 1", pct(r2.get("active_reduction_F16_over_Factive_minus_1"))],
            ["S2 = max(spread RR K=16, spread ACTIVE)", share(r2.get("S2"), 2)],
            ["beside: ACTIVE frames/s vs RR K=16", pct(r2.get("active_fps_vs_rr_k16_minus_1"))]])
    out += [f"**R2 / R3: {r2['verdict']}.**", ""]
    if notes.get("P4A"):
        out += [notes["P4A"], ""]
    return out


def sec_b1(B: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    i = B["item1_steady_phase"]
    out = ["## P4-B (1) — steady-phase docs/s as the smoke metric (POST-HOC VALIDATION on committed legs)", "",
           f"Definition: {i['definition']}. Full-scale reference: P3-A's RR/LI span ratio {f(i['full_scale_ratio'], 4)}; agreement bound ±{share(i['agree_bound'], 2)}.", ""]
    rows = [[k, n(v["ok"]) + "/" + n(v["rows"]), f(v["span_docs_per_s"], 4), f(v["steady_docs_per_s"], 4), share(v["drain_share_of_span"])]
            for k, v in i["legs"].items()]
    out += table(["leg (384 slice)", "ok/rows", "span docs/s", "steady-phase docs/s", "drain share of span"], rows)
    c1 = i["check_1"]["sessions"]
    out += table(["session", "steady RR/LI", "vs full-scale − 1", "agrees (±8.19%)", "span RR/LI (beside)"],
                 [[k, f(v["steady_ratio"], 4), pct(v["rel_to_full_minus_1"]), "yes" if v["agrees"] else "NO", f(v["span_ratio_beside"], 4)] for k, v in c1.items()])
    c2 = i["check_2"]
    out += table(["shape (P3-C smoke)", "steady mean", "steady spread", "span mean (beside)", "span spread (beside)"],
                 [[k, f(v["steady_mean"], 4), share(v["steady_spread"], 2), f(v["span_mean_beside"], 4), share(v["span_spread_beside"], 2)] for k, v in c2["shapes"].items()])
    out += [f"Check 1 (both sessions agree): **{'PASS' if i['check_1']['pass'] else 'FAIL'}**. Check 2 (vars=4 slower than vars=1 on the steady phase; "
            f"{pct(c2['vars4_vs_vars1_steady_minus_1'])}; reported beside, not the rule: the threshold max(0.82% floor, the vars=1 and vars=4 steady spreads) = {share(c2['threshold_beside'], 2)}): **{'PASS' if c2['pass'] else 'FAIL'}**.", "",
            f"**Verdict: {i['verdict']}**" + (f" — failed: {'; '.join(i['failed_checks'])}" if i["failed_checks"] else "") + ".", ""]
    if notes.get("B1"):
        out += [notes["B1"], ""]
    return out


def sec_b2(B: Dict[str, Any], notes: Dict[str, str]) -> List[str]:
    j = B["item2_parser_close_out"]
    L = j["legs"]
    out = ["## P4-B (2) — parser track close-out (P3's committed full legs, same session)", ""]
    rows = [[f"{k} ({v['leg']})", n(v["ok"]) + "/" + n(v["rows"]), f(v["span_s"], 1), f(v["docs_per_s"], 4), n(v["chunks"]),
             f(v["chunks_per_s"], 2), n(v["cpu_s"], 1), f(v["cpu_s_per_chunk"], 4), f(v["chunks_per_ok_doc"], 3)] for k, v in L.items()]
    out += table(["arm", "ok/rows", "span s", "docs/s", "chunks", "chunks/s", "CPU-s", "CPU-s per chunk", "chunks per ok doc"], rows)
    out += table(["ratio (HYBRID / fixed Tika)", "value"], [
        ["docs/s, R_docs", f(j["R_docs"], 4)], ["chunks per ok document, R_cpd", f(j["R_chunks_per_ok_doc"], 4)],
        ["chunks/s, R_chunks", f(j["R_chunks_per_s"], 4)], ["CPU-s per chunk", f(j["R_cpu_s_per_chunk"], 4)],
        ["check: R_chunks / R_cpd (= R_docs)", f(j["identity_check_R_docs_eq_R_chunks_over_R_cpd"], 4)],
        ["share of the docs/s gain that is fewer chunks, ln(1/R_cpd) / ln(R_docs)", share(j["share_of_gain_from_fewer_chunks"])],
        ["share from chunk throughput, ln(R_chunks) / ln(R_docs)", share(j["share_of_gain_from_chunk_throughput"])]])
    if notes.get("B2"):
        out += [notes["B2"], ""]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.camp
    pre = load(c, "preregistration.json")
    A = load(c, "analysis_p4a.json")
    B = load(c, "analysis_p4b.json")
    summ = load(c, "p4_summary_spec.json") or {}
    notes = summ.get("readings", {})
    start, done = load(c, "chain_p4a_run_start.json"), load(c, "chain_p4a_run_done.json")
    bv = load(c, "P4_BLIND_VERIFICATION.json")
    G = gates(c)
    runs = controls(c)
    head = ["# P4 — video concurrency; the smoke metric, the parser close-out, the P5 design and the facts sheet", "",
            f"Campaign `{c.name}`, branch feat/parity-p4 (from feat/parity-p3 f9f1efe7). Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            "from committed analysis and gate files; every figure is computed from raw records and rounded only here. Every P4-A comparison is ABAB inside "
            "one box session; figures from earlier sessions appear only as context and are labelled so.", ""]
    if bv:
        head += [f"**Blind recomputation (P4_BLIND_VERIFICATION.json):** {bv.get('outcome')} — {bv.get('summary', '')}", ""]
    body: List[str] = []
    if summ.get("summary"):
        body += ["## Summary", ""] + [f"- {x}" for x in summ["summary"]] + [""]
    body += ["## Step 0 and the recorded correction", "", f"- {pre['step0']['sso']}", f"- autoland self-test: {pre['step0']['autoland_self_test']}",
             f"- {pre['step0']['origin']}", f"- **Recorded correction ({pre['recorded_correction']['who']}):** {pre['recorded_correction']['text']}", ""]
    body += sec_gates(A, G, runs, start, done, pre)
    body += sec_p4a(A, notes)
    body += sec_b1(B, notes)
    body += sec_b2(B, notes)
    d5 = readtxt(c, "P4B_P5_DESIGN_SINGLE_INFERENCE_THREAD.md")
    body += ["## P4-B (3) — P5 design draft (not filed)", "", "Embedded from `P4B_P5_DESIGN_SINGLE_INFERENCE_THREAD.md`.", ""]
    if notes.get("B3"):
        body += [notes["B3"], ""]
    body += ["> " + ln if ln.strip() else ">" for ln in (d5 or "ABSENT").splitlines()] + [""]
    fs = readtxt(c, "P4_FACTS_SHEET.md")
    body += ["## P4-B (4) — CTO facts sheet", "", "Embedded from `P4_FACTS_SHEET.md` (generated by `working/scripts/p4_facts.py`).", ""]
    body += [ln for ln in (fs or "ABSENT").splitlines()[2:]] + [""]
    body += ["## NOT RUN", ""] + ([f"- {x}" for x in summ.get("not_run", [])] or ["- nothing: every pre-registered leg and item ran."]) + [""]
    if summ.get("register"):
        body += ["## Methodology register", ""] + [f"- {x}" for x in summ["register"]] + [""]
    if summ.get("self_audit"):
        body += ["## SELF-AUDIT", ""] + [f"- **{k}:** {v}" for k, v in summ["self_audit"].items()] + [""]
    a.out_md.write_text("\n".join(head + body) + "\n")
    a.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS}, indent=1) + "\n")
    print(f"wrote {a.out_md.name} ({len(head + body)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
