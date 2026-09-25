#!/usr/bin/env python3
"""P6 report: every figure is read from the committed P6 files (analysis_p6.json, gate_controls*.json, gates/*.json,
chain_p6_*_start/done.json, the pre-registration and its addendum); prose from p6_summary_spec.json (figures formatted there
from the same analysis); the two drafts embedded from their files.

    p6_report.py <campaign_dir> --out-md <md> --out-json <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_report import INPUTS, load, n, pct, share, table  # noqa: E402

PROT = {"rr:patched": "sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90",
        "rr:patched-video": "sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de"}


def f(x, d=3):
    return "—" if x is None else f"{x:.{d}f}"


def mb(x):
    return "—" if x is None else f"{x / 1e6:,.0f} MB"


def gates_of(c: Path) -> Dict[str, Any]:
    out = {}
    for p in sorted((c / "gates").glob("*.json")) if (c / "gates").exists() else []:
        INPUTS[f"gates/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        out[p.stem] = json.loads(p.read_text())
    return out


def controls(c: Path) -> List[Dict[str, Any]]:
    runs = []
    for p in [c / "gate_controls.json"] + sorted(c.glob("gate_controls_run*.json"), key=lambda q: int(q.stem.split("run")[-1])):
        if p.exists():
            INPUTS[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            runs.append(dict(json.loads(p.read_text()), file=p.name))
    return runs


def cell_rows(C, order):
    rows = []
    for c, lab in order:
        x = C.get(c) or {}
        def rr(k, d=3, s=False):
            v = x.get(k) or {}
            fm = (lambda z: share(z, 2)) if s else (lambda z: f(z, d))
            return f"{fm(v.get('round_1'))} / {fm(v.get('round_2'))}; {fm(v.get('mean'))} ({share(v.get('spread'), 2)})"
        rows.append([lab, rr("frames_per_s"), rr("F_s", 4), rr("forward_p50", 4), rr("forward_p99", 4), rr("duty", s=True), rr("cores_in_forward", 2), rr("cpu_s_per_frame"),
                     f"{mb((x.get('memory_peak_total_bytes') or {}).get('round_1'))} / {mb((x.get('memory_peak_total_bytes') or {}).get('round_2'))}"])
    return table(["cell", "frames/s", "forward F s", "forward p50 s", "forward p99 s", "inference duty", "cores busy in the forward", "CPU-s/frame",
                  "sampled memory peak"], rows)


def leg_rows(legs, names):
    rows = []
    for nm in names:
        x = legs.get(nm)
        if not x:
            rows.append([nm, "NOT RUN / absent"] + ["—"] * 12)
            continue
        m, ss = x["forward_D1"], x.get("session") or {}
        q = (x.get("queue_depth") or {}).get("D1") or {}
        rows.append([x["dir"], n(m["count"]), f(m["mean"], 4), f(m["sd"], 4), f(m["p50"], 4), f(m["p90"], 4), f(m["p99"], 4), f(m["max"], 4),
                     share(x.get("duty"), 2), "—" if not q.get("count") else f"{f(q['mean'], 2)} / {f(q['p50'], 0)} / {f(q['max'], 0)}",
                     f(x["frames_per_s"]), f(x["cpu_s_per_frame"]), f"steal {share(ss.get('steal_share'), 3)}, {f(ss.get('mhz_open_mean'), 0)}→{f(ss.get('mhz_close_mean'), 0)} MHz"])
    return table(["leg", "count", "mean", "sd", "p50", "p90", "p99", "max", "inference duty", "queue depth mean / p50 / max", "frames/s", "CPU-s/frame",
                  "steal, MHz open→close"], rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a_ = ap.parse_args()
    c = a_.camp
    pre, add, AN = load(c, "preregistration.json"), load(c, "preregistration_addendum_1.json"), load(c, "analysis_p6.json")
    summ = load(c, "p6_summary_spec.json") or {}
    start, done, bv = load(c, "chain_p6_run_start.json"), load(c, "chain_p6_run_done.json"), load(c, "P6_BLIND_VERIFICATION.json")
    notes = summ.get("readings", {})
    G, runs = gates_of(c), controls(c)
    A, B, Cc, DR = AN["P6_A"], AN.get("P6_B"), AN.get("P6_C"), AN.get("drift")
    head = ["# P6 — the single inference thread against one LlamaIndex instance; the out-of-box thread count; two drafts", "",
            f"Campaign `{c.name}`, branch feat/parity-p6 (from feat/parity-p5 c76bb99c). Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from "
            "committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison inside a stage is "
            "interleaved ABAB; tolerances are FIXED (register 64); the canary adjusts nothing.", ""]
    if bv:
        head += [f"**Blind recomputation (P6_BLIND_VERIFICATION.json):** {bv.get('outcome')} — {bv.get('summary', '')}", ""]
    body: List[str] = []
    if summ.get("summary"):
        body += ["## Summary", ""] + [f"- {x}" for x in summ["summary"]] + [""]
    body += ["## Step 0 and the recorded statements", ""] + [f"- {k}: {v}" for k, v in pre["step0"].items()] + \
            [f"- {k}: {v}" for k, v in pre["recorded"].items()] + ([f"- addendum 1 (before the first measured leg): {add['drift_note_rule']}"] if add else []) + [""]
    # ---------------- gates
    rows = []
    for kind in ("G_d0", "G_cell", "G_warm", "G_canary"):
        xs = [(k[len(kind) + 1:], v.get("outcome")) for k, v in G.items() if k.startswith(kind + "_")]
        ok = "CLEAN" if kind == "G_d0" else "PASS"
        rows.append([f"{kind} (every leg / block / canary it applies to)", "preregistration.json gates", "; ".join(f"{a}: {b}" for a, b in xs) or "—",
                     f"ALL {ok}" if xs and all(b == ok for _, b in xs) else ("—" if not xs else "SEE ROW")])
    ms = [v for k, v in G.items() if k.startswith("G_memstat_")]
    rows.append(["G_memstat (first leg)", "memstat.jsonl ≥ 1 row", "; ".join(f"{m['leg']}: {n(m['rows'])} rows" for m in ms) or "—", ms[0]["outcome"] if ms else "—"])
    for g_ in ("G_correct_A1", "G_correct_A2", "G_correct_C1"):
        x = G.get(g_)
        rows.append([g_ + " (HARD)", "P5 output identical on 16/16 (A: to stock in the round; C1: to the out-of-box reference P0 v1_rr_def_a)",
                     "; ".join(f"{p['a']} vs {p['b']}: {'identical' if p['identical'] else 'DIFFERS'}, {p['videos_compared']} videos" for p in (x or {}).get("pairs", [])) or "—",
                     (x or {}).get("outcome", "NOT REACHED")])
    sg = G.get("G_smoke_P6B")
    rows.append(["G_smoke_P6B", "correctness both rounds AND Q1 in round 1, round 2 and pooled", "Q1 " + str(((A.get("readings") or {}).get("Q1") or {}).get("verdict")),
                 (sg or {}).get("outcome", "NOT REACHED")])
    ids0, ids1 = (start or {}).get("image_ids_at_start") or {}, (done or {}).get("image_ids_at_end") or {}
    same = all(ids0.get(k) == v and ids1.get(k) == v for k, v in PROT.items()) and ids0.get("rr:p5-infer") == ids1.get("rr:p5-infer")
    rows.append(["image ids", "rr:patched, rr:patched-video unchanged; rr:p5-infer = P5's, not rebuilt",
                 " ".join(f"{k} {ids1.get(k, '—')[:19]}" for k in (*PROT, "rr:p5-infer")), "UNCHANGED" if same else "CHANGED OR UNREAD"])
    dl = (done or {}).get("deadline_epoch")
    rows.append(["budget", "8 h from the run stage's first leg", f"run start {(start or {}).get('stage_start_utc', '—')}; deadline "
                 f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(int(dl))) if dl else '—'}; chain done {(done or {}).get('stage_complete_utc', '—')}",
                 "SEE NOT RUN" if done and any("NOT_RUN_budget" in x for x in done.get("legs", [])) else ("WITHIN" if done else "—")])
    body += ["## Gates", ""] + table(["gate", "rule", "measured", "outcome"], rows)
    body += ["### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)", ""]
    for r in runs:
        body += [f"**{r['file']}** (run {r.get('run', 1)}, boot {str(r.get('boot_id'))[:8]}): {n(r['n_pass'])} of {n(r['n'])} controls as expected → all_pass **{r['all_pass']}**.", ""]
    if runs:
        by: Dict[str, Dict[str, List[str]]] = {}
        for x in runs[-1]["controls"]:
            k = "positive" if x["control"].startswith("positive") else "null"
            by.setdefault(x["gate"], {"positive": [], "null": []})[k].append(f"{x['control'].split(': ', 1)[-1]} → {'as expected' if x['pass'] else 'NOT AS EXPECTED'} ({x['got']})")
        body += table(["gate", "positive control(s) (must PASS)", "null control(s) (must FAIL)"], [[g, "<br>".join(v["positive"]) or "—", "<br>".join(v["null"]) or "—"] for g, v in by.items()])
    # ---------------- P6-A
    body += ["## P6-A — smoke, T=4, 16 videos, K=16, two ABAB rounds", "", "### Correctness first", ""]
    corr = A["correctness"]
    body += table(["P5 vs stock (same round)", "videos compared", "identical"], [[f"{p['a']} vs {p['b']}", n(p["videos_compared"]), "yes" if p["identical"] else "NO"] for p in corr["pairs"]])
    body += [f"**CORRECTNESS (hard): {'PASS' if corr['gate_pass'] else ('FAIL — OUTPUT-CHANGING; no speed reading' if corr['gate_pass'] is False else 'NOT EVALUABLE')}.**", ""]
    body += ["Beside:", ""] + table(["comparison", "legs", "videos", "identical"], [[k.replace("_", " "), f"{x['a']} vs {x['b']}", n(x["videos_compared"]), "yes" if x["identical"] else "NO"]
                                                                                  for k, x in corr["beside"].items() if x])
    body += ["### Per cell (round 1 / round 2; mean (spread of the two ABAB runs))", ""]
    body += cell_rows(A["cells"], [("stock_k16", "RR stock K=16"), ("p5_k16", "RR P5 K=16"), ("li_k16", "LlamaIndex K=16")])
    body += ["### Per leg", ""] + leg_rows(A["legs"], ["p6a_stock16_1", "p6a_p5k16_1", "p6a_li16_1", "p6a_stock16_2", "p6a_p5k16_2", "p6a_li16_2"])
    rd = A["readings"]
    body += ["### Q1 and Q2 (fixed tolerances), per round and pooled", ""]
    if (rd.get("Q1") or {}).get("pooled"):
        body += table(["", "Q1: fps(P5) / fps(LI)", "≥ 0.95", "Q2: fps(P5) / fps(stock)", "≥ 1.20"],
                      [[k.replace("_", " "), f(rd["Q1"][k]["ratio"]), "HOLDS" if rd["Q1"][k]["holds"] else "does not hold", f(rd["Q2"][k]["ratio"]),
                        "HOLDS" if rd["Q2"][k]["holds"] else "does not hold"] for k in ("round_1", "round_2", "pooled")])
    body += [f"**Q1: {rd.get('Q1', {}).get('verdict')}. Q2: {rd.get('Q2', {}).get('verdict')}.**", ""]
    d = A.get("descriptive_forward_degradation")
    if d:
        body += ["**Forward degradation (DESCRIPTIVE ONLY, never gated; the one-video reference is P5's committed K=1 legs, another session):** "
                 f"mean {pct(d['F_over_ref_minus_1'])} (P5 K=16 {f(A['cells']['p5_k16']['F_s']['mean'], 4)} s vs {f(d['ref_F_s'], 4)} s), "
                 f"p50 {pct(d['p50_over_ref_minus_1'])} ({f(A['cells']['p5_k16']['forward_p50']['mean'], 4)} vs {f(d['ref_p50'], 4)} s), "
                 f"p99 {pct(d['p99_over_ref_minus_1'])} ({f(A['cells']['p5_k16']['forward_p99']['mean'], 4)} vs {f(d['ref_p99'], 4)} s).", ""]
    if notes.get("A"):
        body += [notes["A"], ""]
    # ---------------- P6-B
    body += ["## P6-B — 168 videos, block-interleaved, warm-symmetric", ""]
    if not B:
        body += [notes.get("B_not_run") or "NOT RUN.", ""]
    else:
        rows = [[k, n(x["videos"]), n(x["errors"]), n(x["frames"]), f(x["span_s"], 1), f(x["frames_per_s"]), x.get("d0") or "—", x.get("cell") or "—", x.get("warm") or "—",
                 f"{x.get('other_container')}: {x.get('other_container_state_at_start')}, {f(x.get('other_container_cpu_s_during_block'), 3)} CPU-s"] if x else [k, "NOT RUN"] + ["—"] * 8
                for k, x in B["blocks"].items()]
        body += table(["block leg", "videos", "errors", "frames", "span s", "frames/s", "D0", "cell", "warm", "paused arm (state, CPU during block)"], rows)
        pa, dist = B["per_arm"], B["per_block_ratio_distribution"]
        body += table(["arm", "blocks", "videos", "errors", "frames", "Σ span s", "total frames/s"],
                      [[k, n(v["blocks"]), n(v["videos"]), n(v["errors"]), n(v["frames"]), f(v["span_s"], 1), f(v["total_frames_per_s"])] for k, v in pa.items()])
        pb = B.get("paired_blocks") or {}
        if pb:
            body += table(["arm, over the blocks BOTH arms ran", "blocks", "videos", "frames", "Σ span s", "total frames/s"],
                          [[k, n(v["blocks"]), n(v["videos"]), n(v["frames"]), f(v["span_s"], 1), f(v["total_frames_per_s"])] for k, v in pb["per_arm"].items()])
            body += [f"All 168 videos on both arms: **{'yes' if B.get('complete_168') else 'NO (the budget; see NOT RUN)'}**. Over the {n(len(pb['blocks']))} blocks both arms ran "
                     f"(beside the pre-registered totals, so both arms cover the same videos): RR/LI **{f(pb['ratio_rr_over_li'])}** "
                     f"({'meets' if pb['meets_q1_bar'] else 'does not meet'} 0.95).", ""]
        body += [f"RR/LI of the totals: **{f(B['ratio_rr_over_li_totals'])}** against Q1's 0.95 ({'meets' if B['ratio_meets_q1_bar'] else 'does not meet'}); "
                 f"per-block ratio over {n(dist['blocks'])} blocks: min {f(dist['min'])}, p50 {f(dist['p50'])}, max {f(dist['max'])}. Start warms: "
                 + ", ".join(f"{k}: {v}" for k, v in B["start_warm"].items()) + ".", ""]
        cr = B["correctness_vs_p1d"]
        body += [f"**Correctness vs the banked P1-D stock output:** {n(cr['identical'])} of {n(cr['videos_compared'])} videos identical; "
                 + ("none differ." if not cr["differ"] else "differ: " + ", ".join(x["video"] for x in cr["differ"]) + "."), ""]
        if notes.get("B"):
            body += [notes["B"], ""]
    # ---------------- P6-C
    body += ["## P6-C — the out-of-box thread count (T=16), smoke", ""]
    if not Cc:
        body += [notes.get("C_not_run") or "NOT RUN.", ""]
    else:
        cc = Cc["correctness"]
        body += table(["P5 T=16 vs the out-of-box reference", "videos compared", "identical"], [[f"{p['a']} vs {p['b']}", n(p["videos_compared"]), "yes" if p["identical"] else "NO"] for p in cc["pairs"]])
        body += [f"**CORRECTNESS: {'PASS' if cc['gate_pass'] else ('FAIL — OUTPUT-CHANGING; no speed reading' if cc['gate_pass'] is False else 'NOT EVALUABLE')}.**", ""]
        body += cell_rows(Cc["cells"], [("p5_t16", "RR P5 T=16 (six vars unset)"), ("li_t16", "LlamaIndex T=16")])
        body += leg_rows(Cc["legs"], ["p6c_p5t16_1", "p6c_lit16_1", "p6c_p5t16_2", "p6c_lit16_2"])
        r = Cc["readings"]
        body += table(["", "F(P5 T=16) / F(P5 T=4, P6-A)", "≤ 0.95 (faster by ≥ 5%)", "fps(P5 T=16) / fps(LI T=16)", "against 0.95"],
                      [[k.replace("_", " "), f(r[k]["F_t16_over_F_t4"]), {True: "yes", False: "no", None: "—"}[r[k]["faster_by_at_least_5pct"]], f(r[k]["fps_p5_t16_over_li_t16"]),
                        "—" if r[k]["fps_p5_t16_over_li_t16"] is None else ("≥ 0.95" if r[k]["fps_p5_t16_over_li_t16"] >= 0.95 else "< 0.95")] for k in ("round_1", "round_2", "pooled")])
        body += [f"**P6-C: {r.get('verdict_forward', 'NOT EVALUABLE')}.** {Cc['not_interleaved_note']}.", ""]
        if notes.get("C"):
            body += [notes["C"], ""]
    # ---------------- drift
    body += ["## Canary drift note", ""]
    if DR:
        body += table(["canary (time order)", "mean forward s", "vs the first canary"], [[k, f(v, 4), pct(DR["canary_vs_first"].get(k))] for k, v in DR["canary_F_s_in_time_order"].items()])
        body += table(["", "value"], [["canary change, P6-A round 2 / round 1 − 1", pct(DR.get("canary_change_a2_over_a1"))],
                                      ["P6-A cells' forward change, round 2 / round 1 − 1", "; ".join(f"{k} {pct(v)}" for k, v in DR["p6a_cells_F_change_round2_over_round1"].items())],
                                      ["their median", pct(DR.get("p6a_cells_median_change"))]])
        body += [f"**Reading (addendum 1's rule): {DR['reading']}.** No figure is adjusted.", ""]
    for fn, title in (("P6_CTO_BRIEF_DRAFT.md", "## P6-D (1) — CTO brief draft (not sent, posted or filed)"),
                      ("P6_UPSTREAM_PATCH_DRAFT.md", "## P6-D (2) — upstream patch description draft (not filed, posted or sent)")):
        p = c / fn
        body += [title, "", f"Embedded from `{fn}`.", ""]
        if p.exists():
            INPUTS[fn] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            body += ["> " + ln if ln.strip() else ">" for ln in p.read_text().splitlines()] + [""]
    body += ["## NOT RUN", ""] + ([f"- {x}" for x in summ.get("not_run", [])] or ["- nothing."]) + [""]
    if summ.get("register"):
        body += ["## Methodology register", ""] + [f"- {x}" for x in summ["register"]] + [""]
    if summ.get("self_audit"):
        body += ["## SELF-AUDIT", ""] + [f"- **{k}:** {v}" for k, v in summ["self_audit"].items()] + [""]
    a_.out_md.write_text("\n".join(head + body) + "\n")
    a_.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS}, indent=1) + "\n")
    print(f"wrote {a_.out_md.name} ({len(head + body)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
