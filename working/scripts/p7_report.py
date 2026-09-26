#!/usr/bin/env python3
"""P7 report: every figure is read from the committed P7 files (p7a_frames.json, analysis_p7.json, gate_controls*.json,
gates/*.json, chain_p7_*_start/done.json, box_logs/p7_run.log, the pre-registration) and formatted only here; the three
drafts are embedded from their files. Prose sentences carry figures read from the same inputs.

    p7_report.py <campaign_dir> --out-md <md> --out-json <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_report import INPUTS, load, n, pct, share, table  # noqa: E402

RES = Path(__file__).resolve().parents[2] / "working" / "results"
PROT = {"rr:patched": "sha256:073b43d8b5f9a3f26fd0c31b81d8c5f088b8a8dd1480dc9676b2141cb6b4ec90",
        "rr:patched-video": "sha256:b7f51acc95330163c9fa988687d415d399a38ebdc7fee0d84d24ff39b65098de"}
P5ID = "sha256:b42c03b69f1749049d3a2e6334890347a22621e8d1adb0a8984780eab866d6bd"
DRAFTS = (("P7_UPSTREAM_PATCH_DRAFT.md", "## P7-D (1) — upstream patch description draft (not filed, posted or sent)"),
          ("P7_THREAD_TICKET_DRAFT.md", "## P7-D (2) — ticket draft: default intra-op thread count for the detect node (not filed, posted or sent)"),
          ("P7_CTO_BRIEF_DRAFT.md", "## P7-D (3) — CTO brief draft (not sent, posted or filed)"))


def f(x, d=3):
    return "—" if x is None else f"{x:.{d}f}"


def e(x):
    return "—" if x is None else f"{x:.2e}"


def yn(x):
    return {True: "yes", False: "NO", None: "—"}[x]


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


def sess(c: Path, leg: str) -> str:
    d = c / leg
    mc = (d / "microcode.txt").read_text().split(":")[-1].strip() if (d / "microcode.txt").exists() else "—"
    def mhz(fn):
        v = [float(x) for x in re.findall(r"cpu MHz\s*:\s*([0-9.]+)", (d / fn).read_text())] if (d / fn).exists() else []
        return f"{sum(v) / len(v):.0f}" if v else "—"
    return f"microcode {mc}, {mhz('mhz_open.txt')}→{mhz('mhz_close.txt')} MHz"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("camp", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a_ = ap.parse_args()
    c = a_.camp
    pre, PA, AN = load(c, "preregistration.json"), load(c, "p7a_frames.json"), load(c, "analysis_p7.json")
    start, done, bv = load(c, "chain_p7_run_start.json"), load(c, "chain_p7_run_done.json"), load(c, "P7_BLIND_VERIFICATION.json")
    G, runs = gates_of(c), controls(c)
    T1, T2, PC = AN["P7_B_tier1"], AN.get("P7_B_tier2"), AN.get("P7_C")
    legs_done = (done or {}).get("legs", [])
    not_run_budget = [x.split(":")[0] for x in legs_done if "NOT_RUN_budget" in x]
    head = ["# P7 — where the two frames sit; the prototype or stock; the thread count; three drafts", "",
            f"Campaign `{c.name}`, branch feat/parity-p7 (from feat/parity-p6 6f08e6a6). Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from "
            "committed analysis, gate and chain files; every figure is computed from raw records and rounded only here. Tolerances are FIXED; the canary adjusts nothing.", ""]
    if bv:
        head += [f"**Blind recomputation (P7_BLIND_VERIFICATION.json):** {bv.get('outcome')} — {bv.get('summary', '')}", ""]
    body: List[str] = []

    # ---------------- summary
    rd = PA["reading"]
    fr = PA["frames"]
    per = T1.get("per_frame", {})
    S = [f"P7-A (committed exports only): **{rd['reading']}**. "
         + "; ".join(f"{k.split(' ')[0]} {'holds' if v else ('FAILED' if v is False else 'NOT EVALUABLE')}" for k, v in rd["clauses"].items())
         + ". On both frames every detection's score differs between the banked stock run and the prototype ("
         + ", ".join(f"{k}: {len(x['differing_detections'])} of {max(x['n_detections'].values())} detections, largest rank-paired shift {x['max_rank_paired_score_delta']:.4f}" for k, x in fr.items())
         + "); every other frame of both videos is identical in scores and labels. The August 0.3004 figure is not in any committed artifact and is not used."]
    t2_line = ("Tier 2 NOT RUN: G_tier2 did not fire (it fires only on CONDITION-DEPENDENT)" if not T2 else f"Tier 2 read {T2['reading']}")
    refd = {v: o.get("frames_where_stock_run1_disagrees_with_banked_P1D") for v, o in T1["other_frames"].items()}
    S.append(f"P7-B Tier 1 (K=3, T=4, two ABAB runs per image): **{T1['reading']}** — the control IN1009.avi identical in all four runs; stock agrees with itself on both "
             f"frames: {yn(T1['pattern']['stock_stable_both_frames'])}; stock video-identical to the banked P1-D output on both videos: "
             f"{yn(T1['pattern']['stock_identical_to_reference_both_videos'])} (frames where today's stock differs from P1-D: "
             + "; ".join(f"{v} {', '.join(map(str, x)) or 'none'}" for v, x in refd.items()) + f"); the prototype agrees with itself on both frames: "
             f"{yn(T1['pattern']['p5_stable_both_frames'])}. Tier reached: 1. {t2_line}.")
    for k, x in per.items():
        g = x.get("post_hoc_distinct_outputs") or []
        S.append(f"POST-HOC, descriptive: {k} — {len(g)} distinct output{'s' if len(g) != 1 else ''} across the banked P1-D stock run, the banked P6-B prototype run and "
                 "the four Tier 1 runs: " + "; ".join("{" + ", ".join(gr["runs"]) + "}" for gr in g) + ".")
    if PC:
        pp = PC["readings"]["pooled"]
        S.append(f"P6-C pooled reading (P6-C round 1 + P7-C round 2, cross-session): the P5 forward at T=16 is {f(pp['F_t16_over_F_t4'])}x its T=4 forward "
                 f"(the bar: <= 0.95) — {PC['readings'].get('verdict_forward', 'NOT EVALUABLE')}; P5 T=16 / LlamaIndex T=16 frames/s {f(pp['fps_p5_t16_over_li_t16'])} "
                 f"(reported against 0.95); P7-C's output identical to the out-of-box reference: {yn((PC.get('correctness_C2') or {}).get('pass'))}.")
    else:
        S.append("P7-C: NOT RUN — the P6-C pooled reading is not evaluable.")
    S.append("The three drafts (patch description, thread-count ticket, CTO brief) are below; none is sent, posted or filed.")
    body += ["## Summary", ""] + [f"- {x}" for x in S] + [""]
    sr = load(c, "p7_session_record.json") or {}
    body += ["## Step 0 and the recorded statements", ""] + [f"- {k}: {v}" for k, v in pre["step0"].items()] + [f"- {k}: {v}" for k, v in pre["recorded"].items()] + \
            [f"- {k}: {v}" for k, v in sr.items() if k != "label"] + [""]

    # ---------------- gates
    rows = []
    rl = c / "box_logs" / "p7_run.log"
    if rl.exists():
        INPUTS["box_logs/p7_run.log"] = hashlib.sha256(rl.read_bytes()).hexdigest()[:16]
        txt = rl.read_text(errors="replace")
        pres = re.findall(r"^containers present: (\d+)$", txt, re.M)
        na = [x for x in legs_done if "NOT_ALONE" in x]
        rows.append(["G_alone (before every leg and canary)", "no container on the box",
                     f"box_logs/p7_run.log: {len(pres)} checks, containers present = {', '.join(sorted(set(pres))) or '—'}; NOT_ALONE entries in the chain record: {len(na)}",
                     "PASS" if pres and set(pres) == {"0"} and not na else "SEE ROW"])
    for kind in ("G_d0", "G_cell", "G_detcap", "G_warm", "G_canary"):
        xs = [(k[len(kind) + 1:], v.get("outcome")) for k, v in G.items() if k.startswith(kind + "_")]
        if not xs:
            continue
        ok = "CLEAN" if kind == "G_d0" else "PASS"
        rows.append([f"{kind} (every leg it applies to)", "preregistration.json gates", "; ".join(f"{a}: {b}" for a, b in xs),
                     f"ALL {ok}" if all(b == ok for _, b in xs) else "SEE ROW"])
    ms = [v for k, v in G.items() if k.startswith("G_memstat_")]
    rows.append(["G_memstat (first leg)", "memstat.jsonl ≥ 1 row", "; ".join(f"{m['leg']}: {n(m['rows'])} rows" for m in ms) or "—", ms[0]["outcome"] if ms else "—"])
    tg = G.get("G_tier2") or {}
    rows.append(["G_tier2", "fires iff the Tier 1 reading is CONDITION-DEPENDENT", f"reading {tg.get('reading', '—')}", tg.get("outcome", "NOT REACHED")])
    cc = G.get("G_correct_C2") or {}
    rows.append(["G_correct_C2 (HARD for P7-C)", "p7c_p5t16_2 identical on 16/16 to P0 v1_rr_def_a",
                 "; ".join(f"{p['a']} vs {p['b']}: {'identical' if p['identical'] else 'DIFFERS'}, {p['videos_compared']} videos" for p in cc.get("pairs", [])) or "—",
                 cc.get("outcome", "NOT REACHED")])
    ids0, ids1 = (start or {}).get("image_ids_at_start") or {}, (done or {}).get("image_ids_at_end") or {}
    same = all(ids0.get(k) == v and ids1.get(k) == v for k, v in PROT.items()) and ids0.get("rr:p5-infer") == ids1.get("rr:p5-infer") == P5ID
    rows.append(["image ids", "rr:patched, rr:patched-video unchanged; rr:p5-infer = P5's, not rebuilt",
                 " ".join(f"{k} {ids1.get(k, '—')[:19]}" for k in (*PROT, "rr:p5-infer")), "UNCHANGED" if same else "CHANGED OR UNREAD"])
    dl = (done or {}).get("deadline_epoch")
    fl = re.search(r"first leg starts (\S+);", rl.read_text(errors="replace")) if rl.exists() else None
    rows.append(["budget", "3 h from the run stage's first leg", f"run start {(start or {}).get('stage_start_utc', '—')}; first leg {fl.group(1) if fl else '—'}; deadline "
                 f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(int(dl))) if dl else '—'}; chain done {(done or {}).get('stage_complete_utc', '—')}",
                 "SEE NOT RUN" if not_run_budget else ("WITHIN" if done else "—")])
    body += ["## Gates", ""] + table(["gate", "rule", "measured", "outcome"], rows)
    body += ["### Gate controls (every gate whole, in its real runtime; positive must PASS, null must FAIL; G_tier2's must also give their reading)", ""]
    for r in runs:
        body += [f"**{r['file']}** (run {r.get('run', 1)}, boot {str(r.get('boot_id'))[:8]}): {n(r['n_pass'])} of {n(r['n'])} controls as expected → all_pass **{r['all_pass']}**.", ""]
    if runs:
        by: Dict[str, Dict[str, List[str]]] = {}
        for x in runs[-1]["controls"]:
            k = "positive" if x["control"].startswith("positive") else "null"
            by.setdefault(x["gate"], {"positive": [], "null": []})[k].append(f"{x['control'].split(': ', 1)[-1]} → {'as expected' if x['pass'] else 'NOT AS EXPECTED'} ({x['got']})")
        body += table(["gate", "positive control(s) (must PASS)", "null control(s) (must FAIL)"], [[g, "<br>".join(v["positive"]) or "—", "<br>".join(v["null"]) or "—"] for g, v in by.items()])

    # ---------------- P7-A
    body += ["## P7-A — where do the two frames sit? (laptop, committed exports only, before any box time)", ""]
    au, s5 = PA["august_artifact"], PA["s5b_artifact"]
    body += [f"- **August evidence:** {au['status']}. {au['search']}; the only committed mention is {au['committed_mention']}.",
             f"- **S5-B evidence:** committed — {s5['committed_artifact']}.", ""]
    for k, x in fr.items():
        body += [f"### {k} — banked stock ({'parity_p1 v1full_rr_t4'}) vs the prototype ({x['prototype_leg']})", "",
                 f"Detections: {x['n_detections']['banked_stock']} vs {x['n_detections']['prototype']}; label-multiset difference: only in the prototype "
                 f"{x['label_multiset_difference']['only_in_prototype'] or 'none'}, only in banked stock {x['label_multiset_difference']['only_in_banked_stock'] or 'none'}; "
                 f"chunks differing: {len(x['chunks']['differing_chunk_indexes'])} of {x['chunks']['n'][0]} (index {', '.join(map(str, x['chunks']['differing_chunk_indexes']))}).", ""]
        body += table(["rank", "score, banked stock", "score, prototype", "|Δ|", "distance from 0.3 (stock / prototype)", "within ±0.001 in either run", "label", "box"],
                      [[str(d["rank"]), f(d["score_banked_stock"], 4), f(d["score_prototype"], 4),
                        f(abs(d["score_banked_stock"] - d["score_prototype"]), 4) if not d["unpaired"] else "unpaired",
                        f"{f(d['distance_from_threshold']['banked_stock'], 4)} / {f(d['distance_from_threshold']['prototype'], 4)}", yn(d["within_band_in_either_run"]) if d["within_band_in_either_run"] else "no",
                        d["label"] if not d["label"].startswith("not recoverable") else "not recoverable", "not recorded"] for d in x["differing_detections"]])
    body += ["### Every other frame of both videos", ""]
    body += table(["video", "frames compared", "max score delta", "frames with a count or label difference", "max box delta"],
                  [[v, n(o["frames_compared"]), e(o["max_score_delta"]), str(len(o["frames_with_count_or_label_difference"])), "NOT EVALUABLE (no boxes committed)"] for v, o in PA["other_frames"].items()])
    body += ["### Sessions", ""]
    srows = []
    for v, s in PA["sessions"].items():
        for lab, x in (("banked stock", s["banked_stock_P1D"]), ("prototype", s["prototype_P6B"])):
            # MHz from the leg's raw mhz files, rounded ONCE here (p7a_frames.json keeps them rounded to 0.1; rounding that again is a double rounding)
            ld = RES / x["leg"]
            def mz(fn):
                vals = [float(q) for q in re.findall(r"cpu MHz\s*:\s*([0-9.]+)", (ld / fn).read_text())] if (ld / fn).exists() else []
                return f"{sum(vals) / len(vals):.0f}" if vals else "—"
            srows.append([v, lab, x["leg"], x["cpu_model"].split(":")[-1].strip() if x["cpu_model"] else "—", x["microcode"] if isinstance(x["microcode"], str) else ", ".join(x["microcode"]),
                          f"{mz('mhz_open.txt')} → {mz('mhz_close.txt')}", x["boot_id"] or "—"])
    body += table(["video", "run", "leg", "CPU", "microcode", "MHz open → close", "boot"], srows)
    body += table(["clause", "result"], [[k, "holds" if v else ("FAILED" if v is False else "NOT EVALUABLE")] for k, v in rd["clauses"].items()])
    body += [f"**P7-A: {rd['reading']}** — {rd['why']}.", ""]
    body += [f"Stated plainly: the hypothesis was a detection sitting on the 0.3 threshold. That is not what the committed records show. On each frame EVERY detection's score moves "
             f"(up to {max(x['max_rank_paired_score_delta'] for x in fr.values()):.4f}); the only near-threshold detection is IN1002.avi's extra one in the prototype run, "
             f"{min(d['distance_from_threshold']['prototype'] for d in fr['IN1002.avi#58']['differing_detections'] if d['unpaired']):.4f} from 0.3 — outside ±0.001 — and it moves "
             "with the rest of the frame. Every other frame of both videos is identical in scores and labels. The committed records cannot say whether boxes moved.", ""]

    # ---------------- P7-B
    body += ["## P7-B — is it the prototype or stock itself?", "", "### Tier 1 (IN1002.avi, TS3010a.avi, the control IN1009.avi; K=3, T=4; ABAB, two runs each, canary first)", ""]
    lrows = []
    for nm in [x for pair in zip(*T1["legs"].values()) for x in pair]:
        d = c / nm
        ex = sorted(d.glob("export_*.json"))
        th = json.loads(ex[0].read_text()).get("throughput", {}) if ex else {}
        lrows.append([nm, "rr:p5-infer" if "_p5_" in nm else "rr:patched-video", n(th.get("total_frames")), f(th["total_frames"] / th["total_span_s"]) if th.get("total_span_s") else "—",
                      (G.get(f"G_d0_{nm}") or {}).get("outcome", "—"), (G.get(f"G_cell_{nm}") or {}).get("outcome", "—"), (G.get(f"G_detcap_{nm}") or {}).get("outcome", "—"), sess(c, nm)])
    body += table(["leg (run order)", "image", "frames", "frames/s", "D0", "cell", "detcap", "session"], lrows)
    body += [f"Control IN1009.avi identical across all six pairs of runs: **{yn(all(T1['control_identical'].values()))}** "
             f"({sum(1 for x in T1['control_identical'].values() if x)} of {len(T1['control_identical'])} pairs).", ""]
    prow = []
    for k, x in per.items():
        prow.append([k, yn(x["stock_stable"]), yn(x["p5_stable"]), f"{yn(x['p5_vs_stock_round'][0])} / {yn(x['p5_vs_stock_round'][1])}", yn(x["all_four_agree"]),
                     " / ".join(yn(y) for y in (x["stock_video_identical_to_ref"] or [])),
                     " ".join(yn(y) for y in x["vs_banked"]["P1-D stock"]), " ".join(yn(y) for y in x["vs_banked"].get("P6-B prototype", []))])
    body += table(["frame", "stock agrees with itself", "prototype agrees with itself", "prototype agrees with stock (round 1 / 2)", "all four agree",
                   "stock video-identical to P1-D (run 1 / 2)", "agrees with banked P1-D (s1 s2 p1 p2)", "agrees with banked P6-B (s1 s2 p1 p2)"], prow)
    drow = []
    for k, x in per.items():
        for lab, key in (("stock 1 vs stock 2", "deltas_stock_vs_stock"), ("prototype 1 vs prototype 2", "deltas_p5_vs_p5"),
                         ("prototype 1 vs stock 1", "deltas_p5_vs_stock"), ("prototype 2 vs stock 2", "deltas_p5_round2_vs_stock_round2")):
            dd = x.get(key) or {}
            t = dd.get("s5b_tier2") or {}
            drow.append([k, lab, " / ".join(map(str, dd.get("n_detections", []))), f(dd.get("max_rank_paired_score_delta"), 4),
                         e(t.get("max_score_delta")), e(t.get("max_box_delta_px")), {True: "within", False: "OUTSIDE", None: "—"}[t.get("ok")] + (f" ({t['why']})" if t.get("why") else "")])
    body += ["Deltas against S5-B's Tier 2 tolerances (labels outside ±0.001 of 0.3, score ≤ 1e-5, box ≤ 1e-3 px; `batchsize_analyse_s5b.tier2_frame` on the captured detections):", ""]
    body += table(["frame", "pair", "detections", "rank-paired max score Δ (records)", "Tier 2 max score Δ", "Tier 2 max box Δ px", "vs S5-B's tolerances"], drow)
    body += table(["video", "frames", "OTHER frames where any two of the four runs disagree", "frames where stock run 1 disagrees with the banked P1-D run"],
                  [[v, n(o["frames"]), ", ".join(map(str, o["other_frames_where_any_two_of_the_four_runs_disagree"])) or "none",
                    ", ".join(map(str, o["frames_where_stock_run1_disagrees_with_banked_P1D"])) or "none"] for v, o in T1["other_frames"].items()])
    pt = T1["pattern"]
    body += [f"**P7-B Tier 1: {T1['reading']}.** Pattern: stock agrees with itself on both frames: {yn(pt['stock_stable_both_frames'])}; stock video-identical to the banked P1-D output on both "
             f"videos: {yn(pt['stock_identical_to_reference_both_videos'])}; the prototype agrees with itself on both frames: {yn(pt['p5_stable_both_frames'])}; frames where the "
             f"prototype (run 1) disagrees with stock: {', '.join(pt['frames_where_p5_disagrees_with_stock']) or 'none'}. None of STOCK VARIES, PROTOTYPE SHIFTS or CONDITION-DEPENDENT "
             f"describes this pattern. **Tier reached: 1.** {t2_line}.", ""]
    body += ["**POST-HOC, descriptive (added after Tier 1 ran; decides nothing):** the runs grouped by identical output on each named frame.", ""]
    grows = []
    for k, x in per.items():
        for j, gr in enumerate(x.get("post_hoc_distinct_outputs") or []):
            grows.append([k, str(j + 1), ", ".join(gr["runs"]), n(gr["n_detections"]), f(gr["top_score"], 4), f(gr["lowest_score"], 4)])
    body += table(["frame", "output", "runs giving it", "detections", "top score", "lowest score"], grows)
    g1 = per.get("IN1002.avi#58", {}).get("post_hoc_distinct_outputs") or []
    g2 = per.get("TS3010a.avi#56", {}).get("post_hoc_distinct_outputs") or []
    stock_in = lambda g: [gr for gr in g if any(("stock" in r) for r in gr["runs"])]  # noqa: E731
    anyo = sum(len(o["other_frames_where_any_two_of_the_four_runs_disagree"]) for o in T1["other_frames"].values())
    body += [f"Stated plainly: on each frame one of the two images does not give one answer. On TS3010a.avi frame 56 STOCK itself gave {len(stock_in(g2))} different outputs across sessions "
             "(the banked P1-D run, and today's two runs, which match every prototype run); so the P6-B difference on that frame does not need the prototype. On IN1002.avi frame 58 stock "
             f"gave {len(stock_in(g1))} output across its three runs while the prototype gave {len([gr for gr in g1 if any('p5' in r or 'prototype' in r for r in gr['runs'])])} different outputs across its three "
             "(P6-B, today's run 1, today's run 2 — which matches stock); so the prototype varies run to run on that frame where stock has not been seen to. Each change moves the whole "
             "frame (every score, and boxes by up to "
             f"{e(((per.get('IN1002.avi#58') or {}).get('deltas_p5_vs_p5') or {}).get('s5b_tier2', {}).get('max_box_delta_px'))} px on IN1002.avi), far beyond S5-B's tolerances; "
             f"every other frame of the three videos agrees across all four runs ({anyo} other frames disagree). What makes one frame of a video non-reproducible is not measured here.", ""]
    if T2:
        body += ["### Tier 2", "", f"**Tier 2: {T2['reading']}.**", ""]

    # ---------------- P7-C
    body += ["## P7-C — P6-C round 2 (the thread count); P6-C's pooled reading", ""]
    if PC:
        c2 = PC.get("correctness_C2") or {}
        body += [f"**CORRECTNESS (G_correct_C2, hard for P7-C): {'PASS' if c2.get('pass') else 'FAIL' if c2 else 'NOT EVALUABLE'}** — p7c_p5t16_2 vs P0 v1_rr_def_a: "
                 f"{n(c2.get('videos_compared'))} videos, identical {yn(c2.get('identical'))}.", ""]
        lrow = []
        for nm, x in PC["legs"].items():
            if not x:
                lrow.append([nm, "NOT RUN / absent"] + ["—"] * 6)
                continue
            d1 = x.get("forward_D1") or {}
            lrow.append([nm, "P6" if nm.startswith("p6") else "P7", f(x.get("F_s"), 4), f(d1.get("p50"), 4), f(d1.get("p99"), 4), f(x.get("frames_per_s")), f(x.get("cpu_s_per_frame"))])
        body += table(["leg", "session", "forward F s", "p50", "p99", "frames/s", "CPU-s/frame"], lrow)
        rr = PC["readings"]
        body += table(["", "F(P5 T=16) / F(P5 T=4)", "≤ 0.95 (faster by ≥ 5%)", "fps(P5 T=16) / fps(LI T=16)", "against 0.95"],
                      [[k.replace("_", " "), f(rr[k]["F_t16_over_F_t4"]), {True: "yes", False: "no", None: "—"}[rr[k]["faster_by_at_least_5pct"]], f(rr[k]["fps_p5_t16_over_li_t16"]),
                        "—" if rr[k]["fps_p5_t16_over_li_t16"] is None else ("≥ 0.95" if rr[k]["fps_p5_t16_over_li_t16"] >= 0.95 else "< 0.95")] for k in ("round_1", "round_2", "pooled")])
        body += [f"**P6-C pooled (as P6 pre-registered it): {rr.get('verdict_forward', 'NOT EVALUABLE')}; P5 T=16 / LlamaIndex T=16 = {f(rr['pooled']['fps_p5_t16_over_li_t16'])}.** {PC['cross_session']}", ""]
    else:
        body += ["NOT RUN.", ""]
    body += ["### Canaries (P7, and P6's for the cross-session comparison)", ""]
    body += table(["canary", "mean forward s", "frames"], [[k, f((v or {}).get("F_s"), 4), n((v or {}).get("frames"))] for k, v in AN["canaries"].items()])

    # ---------------- drafts
    for fn, title in DRAFTS:
        p = c / fn
        body += [title, "", f"Embedded from `{fn}`.", ""]
        if p.exists():
            INPUTS[fn] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            body += ["> " + ln if ln.strip() else ">" for ln in p.read_text().splitlines()] + [""]
        else:
            body += ["(absent)", ""]
    nr = []
    if not T2:
        nr.append(f"P7-B Tier 2: G_tier2 did not fire — the Tier 1 reading is {T1['reading']}, and Tier 2 was pre-registered to run only on CONDITION-DEPENDENT.")
    nr += [f"{x}: the 3-hour budget had passed." for x in not_run_budget]
    nr += [x.split(":")[0] + ": " + x.split(":", 1)[1] for x in legs_done if "NOT_RUN_correctness" in x]
    body += ["## NOT RUN", ""] + ([f"- {x}" for x in nr] or ["- nothing."]) + [""]
    body += ["## Methodology register", "", "- 65, addendum (P7): the banked stock output is not reproducible on one of the two frames (TS3010a.avi frame 56: the banked P1-D run vs "
             "today's two stock runs) and the prototype is not reproducible run to run on the other (IN1002.avi frame 58); a single run is not a reference for these frames.",
             "- 66 — three readings that did not cover what happened: P7-B's pattern fit none of STOCK VARIES, PROTOTYPE SHIFTS or CONDITION-DEPENDENT; the pre-registered "
             "UNCLASSIFIED branch named it. A classification needs a named residual reading, and 'stable' must say over runs, sessions or both.", ""]
    body += ["## SELF-AUDIT", "",
             "- **1. HYPOTHESIS:** every reading was stated before its data in preregistration.json (committed 06a9d543, before P7-A was computed and before any leg); the look at the two frames' scores before that file is recorded in it; P7-A's reading rule is Ansh's verbatim; the Tier 1 output grouping is POST-HOC and labelled so.",
             "- **2. EVIDENCE:** every figure is computed by working/scripts/p7_report.py from p7a_frames.json (p7_frames.py over committed exports), analysis_p7.json (p7_analyse.py over the raw legs), the gate and gate-control records, the chain records and the box log; the drafts from the same files and the committed P4, P5, P6 and S5 artifacts they cite.",
             "- **3. NULL CONTROL:** every gate ran whole in its real runtime against a positive and a null control before launch (gate_controls.json; G_tier2's controls also had to give their reading); the driver's capture flag has a laptop test with null controls; the blind recomputation's planted figures had to be caught.",
             "- **4. REGISTER:** 3, 48, 54-59, 61, 62 (ABAB and the canary), 64 (fixed tolerances), 65 (and its P7 addendum); new: 66.",
             "- **5. NOT VERIFIED:** what makes one frame of a video non-reproducible; whether boxes moved on the P6-B frames (no committed export records boxes); the cross-session thread-count comparison is not ABAB-protected; the drafts are drafts.",
             "- **6. GATES:** every landing through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the gate controls before launch; hard gates after every leg; image ids read back at each stage's start and end (rr:p5-infer not rebuilt); the box stopped with box.sh stop and its state read back.", ""]
    a_.out_md.write_text("\n".join(head + body) + "\n")
    a_.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS}, indent=1) + "\n")
    print(f"wrote {a_.out_md.name} ({len(head + body)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
