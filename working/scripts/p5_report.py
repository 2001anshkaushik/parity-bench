#!/usr/bin/env python3
"""P5 report: every figure is read from the committed P5 files (analysis_p5a.json, analysis_p5b.json, analysis_p5_drift.json,
p5a_build.json, gate_controls*.json, gates/*.json, chain_p5_*_start/done.json, the pre-registration); prose (readings,
NOT RUN, register lines, self-audit) comes from p5_summary_spec.json, whose figures p5_write_specs.py formats from the same
files; the CTO brief draft is embedded from its file.

    p5_report.py <campaign_dir> --out-md <md> --out-json <json>
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

CELL_ORDER = [("stock_k16", "RR stock K=16"), ("p5_k16", "RR P5 K=16"), ("p5_k1", "RR P5 K=1"), ("li_k16", "LlamaIndex K=16")]
LEGS = ["p5a_stock16_1", "p5a_p5k16_1", "p5a_p5k1_1", "p5a_li16_1", "p5a_stock16_2", "p5a_p5k16_2", "p5a_p5k1_2", "p5a_li16_2"]


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


def sec_gates(G, runs, build, start, done, pre) -> List[str]:
    out = ["## Gates", ""]
    rows = []
    bc = (build or {}).get("in_image_check") or {}
    rows.append(["G_build_A (rr:p5-infer)", "node identity, compiles, one frame end to end on the inference thread, same as direct, ONE LWDETR",
                 f"identity {bc.get('identity_ok')}; ran on {bc.get('detect_ran_on')}; same as direct {bc.get('same_as_direct')}; LWDETR {bc.get('lwdetr_instances')}; "
                 f"image {str((build or {}).get('image_id'))[:19]}", "PASS" if (build or {}).get("gate_G_build_A_pass") else "FAIL / absent"])
    for kind, pre_ in (("G_d0", "G_d0_"), ("G_cell", "G_cell_")):
        xs = [(k[len(pre_):], v.get("outcome")) for k, v in G.items() if k.startswith(pre_)]
        rows.append([f"{kind} (every leg and block)", "see the pre-registration", "; ".join(f"{a}: {b}" for a, b in xs) or "—",
                     "ALL " + ("CLEAN" if kind == "G_d0" else "PASS") if xs and all(b in ("CLEAN", "PASS") for _, b in xs) else "SEE ROW"])
    cs = [(k[len("G_canary_"):], v.get("outcome")) for k, v in G.items() if k.startswith("G_canary_")]
    rows.append(["G_canary (every canary)", "the canary ran on exactly v00_EN2001a's 239 manifest frames, one model, T=4",
                 "; ".join(f"{a}: {b}" for a, b in cs) or "—", "PASS" if cs and all(b == "PASS" for _, b in cs) else "SEE ROW"])
    ms = [v for k, v in G.items() if k.startswith("G_memstat_")]
    rows.append(["G_memstat (first measured leg)", "memstat.jsonl ≥ 1 row", "; ".join(f"{m['leg']}: {n(m['rows'])} rows" for m in ms) or "—", ms[0]["outcome"] if ms else "—"])
    for name in ("G_correct_A1", "G_correct_A"):
        gc = G.get(name)
        rows.append([f"{name}" + (" (HARD, after round 1)" if name.endswith("A1") else " (all pairs, recorded)"),
                     "rr:p5-infer output identical to stock on 16/16 at K=16 and K=1",
                     "; ".join(f"{p['a']} vs {p['b']}: {'identical' if p['identical'] else 'DIFFERS'}, {p['videos_compared']} videos" for p in (gc or {}).get("pairs", [])) or "—",
                     (gc or {}).get("outcome", "NOT REACHED")])
    sg = G.get("G_smoke_P5B")
    rows.append(["G_smoke_P5B", "correctness AND S1 AND S2 (pooled)", f"S1 {((sg or {}).get('S1') or {}).get('verdict', '—')}; S2 {((sg or {}).get('S2') or {}).get('verdict', '—')}",
                 (sg or {}).get("outcome", "NOT REACHED")])
    prot = pre["carried_rules"].get("protected_ids") or {"rr:patched": "sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90",
                                                          "rr:patched-video": "sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de"}
    ids0, ids1 = (start or {}).get("image_ids_at_start") or {}, (done or {}).get("image_ids_at_end") or {}
    bb = (build or {}).get("protected_ids_before_and_after") or []
    same = all(ids0.get(k) == v and ids1.get(k) == v for k, v in prot.items()) and all(any(v in x for x in bb) for v in prot.values())
    rows.append(["protected image ids", "rr:patched, rr:patched-video unchanged: before and after the build, at run start and end",
                 " ".join(f"{k} {ids1.get(k, '—')[:19]}" for k in prot), "UNCHANGED" if same else "CHANGED OR UNREAD"])
    dl = (done or {}).get("deadline_epoch")
    rows.append(["budget", "7.5 h from the run stage's first leg", f"run start {(start or {}).get('stage_start_utc', '—')}; deadline "
                 f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(int(dl))) if dl else '—'}; chain done {(done or {}).get('stage_complete_utc', '—')}",
                 "SEE NOT RUN" if done and any("NOT_RUN_budget" in x for x in done.get("legs", [])) else ("WITHIN" if done else "—")])
    out += table(["gate", "rule", "measured", "outcome"], rows)
    out += ["### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL)", ""]
    for r in runs:
        out += [f"**{r['file']}** (run {r.get('run', 1)}, boot {str(r.get('boot_id'))[:8]}): {n(r['n_pass'])} of {n(r['n'])} controls as expected → all_pass **{r['all_pass']}**.", ""]
    if runs:
        by: Dict[str, Dict[str, List[str]]] = {}
        for x in runs[-1]["controls"]:
            k = "positive" if x["control"].startswith("positive") else "null"
            by.setdefault(x["gate"], {"positive": [], "null": []})[k].append(f"{x['control'].split(': ', 1)[-1]} → {'as expected' if x['pass'] else 'NOT AS EXPECTED'} ({x['got']})")
        out += table(["gate", "positive control(s) (must PASS)", "null control(s) (must FAIL)"], [[g, "<br>".join(v["positive"]) or "—", "<br>".join(v["null"]) or "—"] for g, v in by.items()])
    return out


def sec_a(A, notes) -> List[str]:
    out = ["## P5-A — single inference thread, smoke (one session, two ABAB rounds, T=4, 16 videos)", ""]
    if not A:
        return out + ["NOT RUN.", ""]
    corr = A["correctness"]
    out += ["### Correctness first", ""]
    out += table(["pair", "videos compared", "identical"], [[f"{p['a']} vs {p['b']}", n(p["videos_compared"]), "yes" if p["identical"] else "NO"] for p in corr["gate_pairs"]])
    out += [f"**CORRECTNESS GATE: {'PASS' if corr['gate_pass'] else ('FAIL — OUTPUT-CHANGING; no speed reading' if corr['gate_pass'] is False else 'NOT EVALUABLE')}.**", ""]
    bs = [[k.replace("_", " "), f"{x['a']} vs {x['b']}", n(x["videos_compared"]), "yes" if x["identical"] else "NO"] for k, x in corr["beside"].items() if x]
    out += ["Beside:", ""] + table(["comparison", "legs", "videos", "identical"], bs)
    if corr["gate_pass"] is False:
        return out + [notes.get("A", ""), ""]
    out += ["### Per cell (round 1 / round 2; mean; spread of the two ABAB runs)", ""]
    rows = []
    for c, lab in CELL_ORDER:
        x = A["cells"].get(c) or {}
        def rr(k, d=3, s=False):
            v = x.get(k) or {}
            fm = (lambda z: share(z)) if s else (lambda z: f(z, d))
            return f"{fm(v.get('round_1'))} / {fm(v.get('round_2'))}; {fm(v.get('mean'))} ({share(v.get('spread'), 2)})"
        rows.append([lab, rr("frames_per_s"), rr("F_s", 4), rr("duty", s=True), rr("cores_in_forward", 2), rr("cpu_s_per_frame"),
                     f"{mb((x.get('memory_peak_total_bytes') or {}).get('round_1'))} / {mb((x.get('memory_peak_total_bytes') or {}).get('round_2'))}"])
    out += table(["cell", "frames/s", "forward s/frame F", "inference duty", "cores busy in the forward", "CPU-s/frame", "sampled memory peak"], rows)
    out += ["### Per leg: forward D1 metric set (seconds), inference duty, queue depth (P5 legs)", ""]
    rows = []
    for nm in LEGS:
        d = (A.get("gated_legs") or {}).get(nm)
        x = (A.get("legs") or {}).get(nm)
        if not x:
            rows.append([nm, "NOT RUN / absent"] + ["—"] * 13)
            continue
        m, ss = x["forward_D1"], x.get("session") or {}
        q = (x.get("queue_depth") or {}).get("D1") or {}
        rows.append([d, n(m["count"]), f(m["mean"], 4), f(m["sd"], 4), f(m["min"], 4), f(m["p50"], 4), f(m["p90"], 4), f(m["p95"], 4), f(m["p99"], 4),
                     f(m["max"], 4), f(m["mean_over_p50"]), share(x.get("duty")),
                     "—" if not q.get("count") else f"{f(q['mean'], 2)} / {f(q['p50'], 0)} / {f(q['p95'], 0)} / {f(q['max'], 0)}",
                     f(x["frames_per_s"]), f"steal {share(ss.get('steal_share'), 3)}, {f(ss.get('mhz_open_mean'), 0)}→{f(ss.get('mhz_close_mean'), 0)} MHz"])
    out += table(["leg", "count", "mean", "sd", "min", "p50", "p90", "p95", "p99", "max", "mean/p50", "inference duty",
                  "queue depth mean / p50 / p95 / max", "frames/s", "steal, MHz open→close"], rows)
    hist = {nm: (A["legs"][nm] or {}).get("queue_depth", {}).get("histogram") for nm in LEGS if (A["legs"].get(nm) or {}).get("queue_depth")}
    if hist:
        out += ["Queue depth histograms (depth: frames): " + "; ".join(f"{k}: " + ", ".join(f"{a}: {n(b)}" for a, b in v.items()) for k, v in hist.items()) + ".", ""]
    can = A.get("canary") or {}
    out += table(["canary (rr:patched-video bare, v00_EN2001a, T=4)", "frames", "mean forward s", "p50", "p95"],
                 [[k, n((v or {}).get("frames")), f((v or {}).get("F_s"), 4), f(((v or {}).get("forward_D1") or {}).get("p50"), 4), f(((v or {}).get("forward_D1") or {}).get("p95"), 4)] for k, v in can.items()])
    rd = A["readings"]
    out += ["### Readings (pre-registered), per round and pooled", ""]
    if rd.get("S1", {}).get("pooled"):
        rows = []
        for k in ("round_1", "round_2", "pooled"):
            s1, s2 = rd["S1"][k], rd["S2"][k]
            rows.append([k.replace("_", " "), pct(s1["F_p5k16_over_p5k1_minus_1"]), "yes" if s1["clause_forward_within"] else "no",
                         pct(s1["fps_p5k16_over_stock_k16_minus_1"]), "yes" if s1["clause_fps_beyond"] else "no", "HOLDS" if s1["holds"] else "does not hold",
                         f(s2["fps_p5k16_over_li_k16"]), "HOLDS" if s2["holds"] else "does not hold"])
        out += table(["", "F(P5 K=16)/F(P5 K=1) − 1", f"within {share(rd['S1']['threshold_forward'], 2)}", "fps(P5 K=16)/fps(stock K=16) − 1",
                      f"beyond {share(rd['S1']['threshold_fps'], 2)}", "S1 FIX WORKS", "fps(P5 K=16)/fps(LI K=16)", "S2 PARITY (≥ 0.95)"], rows)
    out += [f"**S1: {rd.get('S1', {}).get('verdict')}. S2: {rd.get('S2', {}).get('verdict')}.**", ""]
    if notes.get("A"):
        out += [notes["A"], ""]
    return out


def sec_b(B, notes) -> List[str]:
    out = ["## P5-B — 168 videos, block-interleaved", ""]
    if not B:
        return out + [notes.get("B_not_run") or "NOT RUN.", ""]
    rows = []
    for name, x in B["blocks"].items():
        if x:
            rows.append([name, n(x["videos"]), n(x["errors"]), n(x["frames"]), f(x["span_s"], 1), f(x["frames_per_s"]), x.get("d0") or "—", x.get("cell") or "—",
                         f"{x.get('other_container')}: {x.get('other_container_state_at_start')}, {f(x.get('other_container_cpu_s_during_block'), 3)} CPU-s"])
        else:
            rows.append([name, "NOT RUN"] + ["—"] * 7)
    out += table(["block leg", "videos", "errors", "frames", "span s", "frames/s", "D0", "cell", "other container (state at start, CPU during block)"], rows)
    pa, dist = B["per_arm"], B["per_block_ratio_distribution"]
    out += table(["arm", "blocks", "videos", "errors", "frames", "Σ span s", "total frames/s"],
                 [[a, n(v["blocks"]), n(v["videos"]), n(v["errors"]), n(v["frames"]), f(v["span_s"], 1), f(v["total_frames_per_s"])] for a, v in pa.items()])
    out += [f"RR/LI of the totals: **{f(B['ratio_rr_over_li_totals'])}**; per-block ratio over {n(dist['blocks'])} blocks: min {f(dist['min'])}, p50 {f(dist['p50'])}, max {f(dist['max'])}.", ""]
    cr = B["correctness_vs_p1d"]
    out += [f"**Correctness vs the banked P1-D stock output:** {n(cr['identical'])} of {n(cr['videos_compared'])} videos identical; "
            + ("none differ." if not cr["differ"] else "differ: " + ", ".join(d["video"] for d in cr["differ"]) + "."), ""]
    if notes.get("B"):
        out += [notes["B"], ""]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.camp
    pre, A, B, DR = load(c, "preregistration.json"), load(c, "analysis_p5a.json"), load(c, "analysis_p5b.json"), load(c, "analysis_p5_drift.json")
    build, summ = load(c, "p5a_build.json"), load(c, "p5_summary_spec.json") or {}
    start, done, bv = load(c, "chain_p5_run_start.json"), load(c, "chain_p5_run_done.json"), load(c, "P5_BLIND_VERIFICATION.json")
    notes = summ.get("readings", {})
    G, runs = gates_of(c), controls(c)
    head = ["# P5 — a single inference thread for the detect node; the CTO brief draft", "",
            f"Campaign `{c.name}`, branch feat/parity-p5 (from feat/parity-p4 264872d7). Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from "
            "committed analysis and gate files; every figure is computed from raw records and rounded only here. Every comparison is interleaved ABAB "
            "(register 62); the canary explains drift and adjusts nothing.", ""]
    if bv:
        head += [f"**Blind recomputation (P5_BLIND_VERIFICATION.json):** {bv.get('outcome')} — {bv.get('summary', '')}", ""]
    body: List[str] = []
    if summ.get("summary"):
        body += ["## Summary", ""] + [f"- {x}" for x in summ["summary"]] + [""]
    body += ["## Step 0", ""] + [f"- {k}: {v}" for k, v in pre["step0"].items()] + [""]
    body += sec_gates(G, runs, build, start, done, pre)
    body += sec_a(A, notes)
    body += sec_b(B, notes)
    body += ["## P5-C (2) — canary drift note", ""]
    if DR:
        cf = DR["canary_F_s"]
        body += table(["", "value"], [["canary forward, round 1 / round 2 (s)", f"{f(cf['round_1'], 4)} / {f(cf['round_2'], 4)}"],
                                      ["canary change round 2 / round 1 − 1", pct(DR.get("canary_change"))],
                                      ["P5-A cells' forward change round 2 / round 1 − 1", "; ".join(f"{k} {pct(v)}" for k, v in DR["p5_cells_F_change_round2_over_round1"].items())],
                                      ["their median", pct(DR.get("p5_cells_median_change"))],
                                      ["P4's round drift (forward, round 2 / round 1 − 1; no canary then)", "; ".join(f"{k} {pct(v)}" for k, v in DR["p4_round_drift_F_change"].items())]])
        body += [f"**Reading (rule fixed in the pre-registration): {DR['reading']}.** No figure is adjusted.", ""]
        if notes.get("drift"):
            body += [notes["drift"], ""]
    else:
        body += ["NOT RUN or not analysed.", ""]
    br = (c / "P5_CTO_BRIEF_DRAFT.md")
    body += ["## P5-C (1) — CTO brief draft (not sent, posted or filed)", "", "Embedded from `P5_CTO_BRIEF_DRAFT.md` (generated by `working/scripts/p5_brief.py`).", ""]
    if br.exists():
        INPUTS[br.name] = hashlib.sha256(br.read_bytes()).hexdigest()[:16]
        body += ["> " + ln if ln.strip() else ">" for ln in br.read_text().splitlines()] + [""]
    body += ["## NOT RUN", ""] + ([f"- {x}" for x in summ.get("not_run", [])] or ["- nothing."]) + [""]
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
