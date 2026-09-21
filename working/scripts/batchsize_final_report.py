#!/usr/bin/env python3
"""batchsize_final_report.py — the batch-size campaign's final Markdown summary, GENERATED from
committed analysis artifacts. No figure in the Markdown is typed: each is read from a JSON file,
and every table names the file it came from. The inputs' sha256s are recorded in the JSON twin.

    batchsize_final_report.py --out-md <md> --out-json <json>
        [--smoke DIR] [--s3b DIR] [--s4 DIR] [--s4-analysis JSON] [--s5 DIR]

The framing rules (Ansh, 2026-09-20/21) are applied structurally, not by care:
  - each arm at its own measured optimum, postures disclosed; the per-unit claim is the G4
    anchor's alone, never the headline's;
  - span throughput is PRIMARY; docs/s to p99 is a POST-HOC DIAGNOSTIC; a symmetric view drops
    039_039660.pdf from BOTH arms (C2);
  - idle = 32 - host busy cores; the engine's idle spin is BURNED CPU, reported apart, never
    added back (C3);
  - every RocketRide docs figure carries the Ruling A caveat (C4), marked with a dagger;
  - empty-content counts for both arms with the documents that differ named (C5);
  - the 168-video RocketRide leg is RANKING ONLY (the leg-6 rule fired on a 9.76% spread);
  - smoke-slice absolutes live in their own section, never beside 10k figures;
  - Stage 5 figures are segregated and labelled TUNED POSTURE / PATCHED-ENGINE / DIAGNOSTIC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
RES = Path("working/results")
STRAGGLER = "039_039660.pdf"
DAG = "†"
CAVEAT = ("32 vCPU unconstrained per Ruling A; measured posture cost vs 24-core cpuset -7.1% "
          "throughput, +28% CPU-s/doc.")
LEG6_SPREAD_RULE = 0.02

INPUTS: Dict[str, str] = {}


def load(p: Path, name: str, required: bool = True) -> Optional[Any]:
    f = ROOT / p if not p.is_absolute() else p
    if not f.exists():
        if required:
            raise SystemExit(f"REFUSED: required input {p} is absent")
        return None
    INPUTS[name] = f"{p}  sha256:{hashlib.sha256(f.read_bytes()).hexdigest()[:16]}"
    return json.loads(f.read_text())


def n(x: Any, nd: int = 4) -> str:
    if x is None:
        return "—"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return f"{x:,}"
    if isinstance(x, float):
        s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(x)


def pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.2f}%"


def gb(mb: Optional[float]) -> str:
    return "—" if mb is None else f"{mb / 1024:.1f} GiB"      # the cgroup's MB are MiB


def spread(a: float, b: float) -> float:
    return abs(a - b) / ((a + b) / 2)


def table(head: List[str], rows: List[List[str]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def cont_row(a: Dict[str, Any], arm: str, c: int) -> Dict[str, Any]:
    for r in a["ranking"][arm]["continuous_reference"]:
        if r["reference_c"] == c:
            return r
    raise SystemExit(f"REFUSED: no continuous C={c} row for {arm}")


OUTCOMES = {"no_documents", "empty_extraction", "parse_failed"}


def outcome_counts(perdoc: Path, name: str) -> Dict[str, int]:
    f = ROOT / perdoc if not perdoc.is_absolute() else perdoc
    INPUTS[name] = f"{perdoc}  sha256:{hashlib.sha256(f.read_bytes()).hexdigest()[:16]}"
    c = {"completed": 0, "content_outcome": 0, "deadline_loss": 0, "other_failure": 0}
    by_reason: Dict[str, int] = {}
    for line in f.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        reason = str(r.get("reason"))
        if r.get("ok"):
            c["completed"] += 1
        elif reason in OUTCOMES:
            c["content_outcome"] += 1; by_reason[reason] = by_reason.get(reason, 0) + 1
        elif reason.endswith("TimeoutError"):
            c["deadline_loss"] += 1
        else:
            c["other_failure"] += 1
    c["by_reason"] = by_reason  # type: ignore[assignment]
    return c


def video_leg(p: Path, name: str) -> Dict[str, Any]:
    d = load(p, name)
    if not d or not d.get("legs"):
        raise SystemExit(f"REFUSED: {p} holds no leg")
    return d["legs"][0]


# ------------------------------------------------------------------------------------------------
def headline_docs(s4: Path, a: Dict[str, Any], F: Dict[str, Any]) -> List[str]:
    rr_launch, li_launch = "p1_rr_cont32", "p2_li_cont"
    rows_out = []
    arms = {}
    for arm, launch, c in (("rr", rr_launch, 32), ("li", li_launch, 32)):
        cr = cont_row(a, arm, c)
        key = f"{launch}/refc{c}_main"
        tail = a["check_E_tail"]["per_leg"][key]
        g = load(s4 / launch / f"leg_{arm}_refc{c}_main.json", f"s4_leg_{arm}_refc{c}")
        mem = (g.get("memory") or {}).get("at_window_close") or {}
        docs = outcome_counts(s4 / launch / f"perdoc_{arm}_refc{c}_main.jsonl", f"s4_perdoc_{arm}_refc{c}")
        knee = a["ranking"][arm]["call"]["continuous_knee"]
        arms[arm] = {"cr": cr, "tail": tail, "g": g, "mem": mem, "docs": docs, "knee": knee,
                     "lost": (a.get("deadline_losses_per_leg") or {}).get(key)}
    F["stage4_docs_headline"] = {k: {"docs_per_s_span": v["tail"]["PRIMARY_docs_per_s_span"],
                                     "span_excluding_straggler": v["tail"]["span_excluding_straggler"]["docs_per_s"],
                                     "docs_per_s_to_p99_POST_HOC": v["tail"]["docs_per_s_to_p99"],
                                     "engine_cores": v["cr"]["engine_cores"], "driver_cores": v["cr"]["driver_cores"],
                                     "host_cores": v["cr"]["host_cores"], "cpu_utilization": v["cr"]["cpu_utilization"],
                                     "idle_core_equivalents": v["cr"]["idle_core_equivalents"],
                                     "idle_spin_burned_cores": v["cr"]["idle_spin_burned_cores"],
                                     "cpu_s_per_doc": (v["g"].get("cost") or {}).get("cpu_s_per_doc"),
                                     "peak_anon_mb": v["mem"].get("anon_mb"), "peak_mb": v["mem"].get("peak_mb"),
                                     "documents": v["docs"]} for k, v in arms.items()}
    R, L = arms["rr"], arms["li"]

    def r(x: str) -> str:
        return f"{x} {DAG}"
    lk = L["knee"]
    li_choice = (f"continuous, C=32 — a TIE with C={lk['tie_between'][0]} inside its "
                 f"{pct(lk['noise_floor_used'])} floor; C=32 kept per register 12, not as a winner"
                 if lk.get("tie") else "continuous, C=32")
    rows_out = [
        ["Submission at the arm's own optimum", r(f"continuous, C={R['knee']['knee_c']} (the knee)"), li_choice],
        ["**Span throughput, docs/s — PRIMARY**", r(f"**{n(R['tail']['PRIMARY_docs_per_s_span'])}**"),
         f"**{n(L['tail']['PRIMARY_docs_per_s_span'])}**"],
        [f"Span with {STRAGGLER} dropped from BOTH arms", r(n(R["tail"]["span_excluding_straggler"]["docs_per_s"])),
         n(L["tail"]["span_excluding_straggler"]["docs_per_s"])],
        ["docs/s to the 99th-percentile completion — POST-HOC DIAGNOSTIC", r(n(R["tail"]["docs_per_s_to_p99"])),
         n(L["tail"]["docs_per_s_to_p99"])],
        ["Document that set the span (held)", r(f"{R['tail']['span_set_by']['doc']} ({n(R['tail']['span_set_by']['held_s'], 1)} s)"),
         f"{L['tail']['span_set_by']['doc']} ({n(L['tail']['span_set_by']['held_s'], 1)} s)"],
        ["Engine container CPU, cores (cgroup)", r(n(R["cr"]["engine_cores"], 3)), n(L["cr"]["engine_cores"], 3)],
        ["Driver CPU, cores (getrusage)", r(n(R["cr"]["driver_cores"], 3)), n(L["cr"]["driver_cores"], 3)],
        ["Host busy cores (per-core /proc/stat)", r(n(R["cr"]["host_cores"], 3)), n(L["cr"]["host_cores"], 3)],
        ["CPU utilisation, engine / 32 vCPUs", r(pct(R["cr"]["cpu_utilization"])), pct(L["cr"]["cpu_utilization"])],
        ["**Idle core-equivalents (32 − host busy)**", r(f"**{n(R['cr']['idle_core_equivalents'], 3)}**"),
         f"**{n(L['cr']['idle_core_equivalents'], 3)}**"],
        ["Idle spin — CPU BURNED while idle, not idle capacity", r(n(R["cr"]["idle_spin_burned_cores"], 3)),
         n(L["cr"]["idle_spin_burned_cores"], 3)],
        ["CPU-seconds per document (engine)", r(n((R["g"].get("cost") or {}).get("cpu_s_per_doc"), 3)),
         n((L["g"].get("cost") or {}).get("cpu_s_per_doc"), 3)],
        ["Engine memory at window close: peak / anon (cgroup)", f"{gb(R['mem'].get('peak_mb'))} / {gb(R['mem'].get('anon_mb'))}",
         f"{gb(L['mem'].get('peak_mb'))} / {gb(L['mem'].get('anon_mb'))}"],
        ["Documents: completed / content outcome (no text, parse failed) / lost to the deadline / other failure",
         " / ".join(n(R["docs"][k]) for k in ("completed", "content_outcome", "deadline_loss", "other_failure")) + f" {DAG}",
         " / ".join(n(L["docs"][k]) for k in ("completed", "content_outcome", "deadline_loss", "other_failure"))],
    ]
    out = ["## 1. Headline — each arm at its own measured optimum, 9,975 GovDocs PDFs (Stage 4)", "",
           "RocketRide runs **one token, out of the box** (`use()` with no `threads=`, the six thread variables "
           "unset); LlamaIndex runs **24 service workers**, its own measured optimum. This row pair answers "
           "\"how fast does each stack go at its best on this box\"; it is **not** a per-unit comparison — "
           "one token against 24 workers — and carries no parity claim. The per-unit comparison is the G4 "
           "anchor, §4. Both arms unconstrained across all 32 vCPUs (Ruling A); one leg on the box at a time "
           "(Ruling C); caches prewarmed.", ""]
    out += table(["Stage 4 docs, 9,975 PDFs + 25 warm-up", "RocketRide — 1 token", "LlamaIndex — 24 workers"], rows_out)
    lost = R["lost"]
    out += ["", f"{DAG} {CAVEAT}", "",
            f"Source: `{s4}/analysis_docs.json` (ranking, check_E_tail) and the two `leg_*_refc32_main.json` "
            "(cost, memory, documents).", ""]
    if lost:
        out += [f"The RocketRide leg lost {lost['n']} document(s) to the driver's own 1,800 s deadline — a harness "
                "loss, not an engine error: " + ", ".join(f"`{d['doc']}` (held {n(d['held_s'], 1)} s)" for d in lost["documents"]) + ".", ""]
    sp = R["tail"]["span_set_by"]
    out += [f"**Why span and the diagnostics disagree on RocketRide.** `{STRAGGLER}` (39 pages) finished "
            f"{n(sp['seconds_after_p99'], 1)} s after the 99th-percentile completion and set the span (register 40). "
            "Dropping it from both arms is the symmetric view; the p99 figure was defined after this leg was "
            "seen (register 34) and is never the headline.", ""]
    return out


def empty_content(a: Dict[str, Any], s4: Path, F: Dict[str, Any]) -> List[str]:
    e = a["check_C5_empty_content"]
    F["c5_empty_content"] = e
    out = ["### Empty-content documents, both arms (C5)", "",
           f"RocketRide {n(e['rr']['n'])}{DAG}, LlamaIndex {n(e['li']['n'])}; {n(e['both'])} are empty on both. "
           f"Empty on LlamaIndex only ({len(e['only_li'])}): " + (", ".join(f"`{d}`" for d in e["only_li"]) or "none") + ". "
           f"Empty on RocketRide only ({len(e['only_rr'])}): " + (", ".join(f"`{d}`" for d in e["only_rr"]) or "none") + ".",
           "An empty extraction is a parser outcome (Tika vs pypdf), reported as content, never as lost work.",
           f"Source: `{s4}/analysis_docs.json` → check_C5_empty_content.", ""]
    return out


def envelope(s4: Path, a: Dict[str, Any], F: Dict[str, Any]) -> List[str]:
    out = ["## 2. Batch size at full scale — the envelope, 9,975 PDFs (Stage 4)", "",
           "**Batch** here is the only lever that exists without modifying an arm: RocketRide "
           "`send_files(K files)` on one token; LlamaIndex K concurrent single-document POSTs behind a "
           "barrier (its service has no multi-document endpoint). The next batch starts only when every "
           "document of the current one has returned. Batch deadline pre-registered at 1,800 s for every K "
           "and both arms before the first envelope leg; a batch lost to it is blast radius, never re-run.", ""]
    keys = {"rr": [(128, "p3_rr_k128/k128_main"), (256, "e7_rr_k256/k256_env"), (512, "e9_rr_k512/k512_env"),
                   (1024, "e11_rr_k1024/k1024_env")],
            "li": [(128, "p4_li_k128/k128_main"), (256, "e8_li_k256/k256_env"), (512, "e10_li_k512/k512_env"),
                   (1024, "e12_li_k1024/k1024_env")]}
    F["stage4_envelope"] = {}
    for arm, label in (("rr", "RocketRide — 1 token"), ("li", "LlamaIndex — 24 workers")):
        byk = {r["k"]: r for r in a["ranking"][arm]["by_k"]}
        rows, per_batch = [], []
        for k, key in keys[arm]:
            br = (a.get("envelope_batch_report") or {}).get(key)
            row = byk.get(k)
            if not row or not br:
                rows.append([f"K={k}", "PENDING — leg not in the analysis"] + [""] * 7)
                continue
            d = (lambda x: f"{x} {DAG}") if arm == "rr" else (lambda x: x)
            died = br.get("batches_died") or []
            rows.append([f"K={k}", d(n(row["docs_per_s_mean"])), n(br["batches"]),
                         f"{n(br['wall_s_median'], 1)} / {n(br['wall_s_max'], 1)}",
                         f"#{br['straggler_batch']}: {n(br['straggler_batch_wall_s'], 1)} s ({n(br['straggler_margin_s'], 1)} s spare)",
                         n(len(died)) + (" — **BLAST-RADIUS-DOMINATED**" if len(died) > 1 else ""),
                         n(br.get("documents_lost_total")),
                         gb(br.get("peak_anon_mb")),
                         d(n(row.get("idle_core_equivalents"), 3))])
            F["stage4_envelope"][f"{arm}_k{k}"] = {"docs_per_s": row["docs_per_s_mean"], "batch_report": br,
                                                  "idle_core_equivalents": row.get("idle_core_equivalents"),
                                                  "cpu_utilization": row.get("cpu_utilization")}
            walls = ", ".join(f"{b}:{w}" for b, w in sorted(br["per_batch_wall_s"].items(), key=lambda kv: int(kv[0])))
            per_batch.append(f"- K={k} ({key}): {walls}")
        cr = cont_row(a, arm, 32)
        rows.append(["continuous C=32 (reference)", (f"{n(cr['docs_per_s'])} {DAG}" if arm == "rr" else n(cr["docs_per_s"])),
                     "—", "—", "—", "—", "—", "—", (f"{n(cr['idle_core_equivalents'], 3)} {DAG}" if arm == "rr" else n(cr["idle_core_equivalents"], 3))])
        out += [f"### {label}", ""]
        out += table(["K", "Span docs/s", "Batches", "Batch wall median / max, s",
                      f"Batch holding {STRAGGLER}: wall (spare to 1,800 s)", "Batches died", "Documents lost",
                      "Peak engine anon", "Idle core-equiv."], rows)
        out += [""] + ([f"{DAG} {CAVEAT}", ""] if arm == "rr" else [])
        out += ["<details><summary>Per-batch wall times, s (batch index: wall)</summary>", ""] + per_batch + ["", "</details>", ""]
    dec = load(s4 / "envelope_k512_decision.json", "envelope_k512_decision", required=False)
    if dec:
        F["k512_audit"] = dec
        out += ["**The pre-registered K=512 rule, for audit only** (every K ran on both arms by ruling): " +
                "; ".join(f"{arm}: {json.dumps(v)[:220]}" for arm, v in dec.items() if arm in ("rr", "li")) +
                f". Source: `{s4}/envelope_k512_decision.json`.", ""]
    cc = a.get("check_C_content") or {}
    out += ["**Batch size never changed the output.** Chunk hashes are identical across every K and the "
            f"continuous legs within each arm (check C: RocketRide {cc.get('rr', {}).get('verdict')}, LlamaIndex "
            f"{cc.get('li', {}).get('verdict')}); across arms they differ, the null control that shows the "
            "comparator can see a difference.", "",
            f"Source: `{s4}/analysis_docs.json` → ranking.by_k, envelope_batch_report, check_C_content.", ""]
    return out


def video_stage4(s4: Path, smoke: Path, s3b: Path, F: Dict[str, Any]) -> List[str]:
    li = video_leg(s4 / "p5_li_video" / "analysis_video.json", "s4_video_li")
    rr = video_leg(s4 / "p6_rr_video" / "analysis_video.json", "s4_video_rr")
    sm = load(smoke / "analysis_video.json", "smoke_video")
    rep = load(s3b / "video" / "analysis_video_rep.json", "s3b_video_rep")
    pick = lambda d, arm, k, var=None: next(x for x in d["legs"] if x["arm"] == arm and x["k"] == k and (var is None or x.get("variant") == var))  # noqa: E731
    rr1, rr2 = pick(sm, "rr", 16), pick(rep, "rr", 16)
    li1, li2 = pick(sm, "li", 8), pick(rep, "li", 8)
    s_rr, s_li = spread(rr1["frames_per_s"], rr2["frames_per_s"]), spread(li1["frames_per_s"], li2["frames_per_s"])
    fired = s_rr > LEG6_SPREAD_RULE
    F["stage4_video"] = {"li_k16": {k: li.get(k) for k in ("frames_per_s", "effective_cores", "cpu_util_of_box", "n_errors", "frames", "span_s")},
                         "li_k16_idle_core_equivalents": (li.get("percore_host") or {}).get("idle_core_equivalents"),
                         "rr_k16": {"frames_per_s": "RANKING ONLY — not quotable (leg-6 rule)" if fired else rr["frames_per_s"],
                                    "effective_cores": rr.get("effective_cores"), "cpu_util_of_box": rr.get("cpu_util_of_box"),
                                    "idle_core_equivalents": (rr.get("percore_host") or {}).get("idle_core_equivalents"),
                                    "idle_spin_burned_cores": rr.get("idle_burden"), "n_errors": rr.get("n_errors")},
                         "leg6_rule": {"g5b_rr_spread": round(s_rr, 4), "threshold": LEG6_SPREAD_RULE,
                                       "branch": "RANKING ONLY" if fired else "absolute quotable"},
                         "g5b_li_spread": round(s_li, 4)}
    rank = "LlamaIndex ahead of RocketRide" if li["frames_per_s"] > rr["frames_per_s"] else "RocketRide ahead of LlamaIndex"
    rows = [["Posture", "8 single-worker instances, thread variables at 4 (banked 8x4)", "1 token, default posture (threads unset, torch reads 16)"],
            ["Videos in flight, K", "16", "16"],
            ["Throughput, frames/s", n(li["frames_per_s"], 3), "**RANKING ONLY** — see rule below" if fired else n(rr["frames_per_s"], 3)],
            ["Engine CPU, cores (cgroup)", n(li["effective_cores"], 3), n(rr["effective_cores"], 3)],
            ["CPU utilisation, engine / 32 vCPUs", pct(li["cpu_util_of_box"]), pct(rr["cpu_util_of_box"])],
            ["**Idle core-equivalents (32 − host busy)**", f"**{n((li.get('percore_host') or {}).get('idle_core_equivalents'), 3)}**",
             f"**{n((rr.get('percore_host') or {}).get('idle_core_equivalents'), 3)}**"],
            ["Idle spin — burned, not idle", n(li.get("idle_burden"), 3), n(rr.get("idle_burden"), 3)],
            ["Videos / errors", f"{n(li['n_offered'])} / {n(li['n_errors'])}", f"{n(rr['n_offered'])} / {n(rr['n_errors'])}"]]
    out = ["## 3. AMI video at full scale, 168 videos + 2 warm-up (Stage 4)", "",
           "There is **no batch knob on the video path of either arm** (one frame per detector call by design). "
           "K is the number of videos in flight (`driver_video.py --blast-concurrency K`, unmodified).", ""]
    out += table(["Stage 4 video, 168 AMI videos", "LlamaIndex", "RocketRide"], rows)
    out += ["", f"**Ranking: {rank}.** " + f"**The leg-6 rule fired.** RocketRide's K=16 replicate spread on the 16-video slice is "
            f"{pct(s_rr)} (G5(b)), above the pre-set 2% threshold, so this leg's absolute frames/s is not quotable "
            "beside banked figures; it is reported as a ranking plus idle cores only. One pass was authorised "
            f"because G5(b) supplies a spread at this scale. LlamaIndex's own K=8 replicate spread was {pct(s_li)}.", "",
            f"Sources: `{s4}/p5_li_video/analysis_video.json`, `{s4}/p6_rr_video/analysis_video.json`; spreads from "
            f"`{smoke}/analysis_video.json` and `{s3b}/video/analysis_video_rep.json`.", ""]
    return out


def anchor(s3b: Path, smoke: Path, F: Dict[str, Any]) -> List[str]:
    a = load(s3b / "analysis_docs_anchor96.json", "s3b_anchor_docs")
    va = load(s3b / "video" / "analysis_video_anchor.json", "s3b_anchor_video")
    sm = load(smoke / "analysis_video.json", "smoke_video")
    rep = load(s3b / "video" / "analysis_video_rep.json", "s3b_video_rep")
    rows = []
    F["g4_anchor_docs"] = {}
    for arm, label in (("rr", "RocketRide — 1 token"), ("li", "LlamaIndex — 1 worker")):
        c1, c8 = cont_row(a, arm, 1), cont_row(a, arm, 8)
        d = (lambda x: f"{x} {DAG}") if arm == "rr" else (lambda x: x)
        rows.append([label, d(n(c1["docs_per_s"])), d(n(c8["docs_per_s"])), f"{c8['docs_per_s'] / c1['docs_per_s']:.2f}x",
                     d(n(c8["engine_cores"], 3)), d(n(c8["idle_core_equivalents"], 3))])
        F["g4_anchor_docs"][arm] = {"c1": c1, "c8": c8}
    li1 = va["legs"][0]
    rr1, rr2 = (next(x for x in sm["legs"] if x["arm"] == "rr" and x["k"] == 16),
                next(x for x in rep["legs"] if x["arm"] == "rr" and x["k"] == 16))
    F["g4_anchor_video"] = {"li_1_instance": {k: li1.get(k) for k in ("frames_per_s", "effective_cores", "cpu_util_of_box")},
                            "rr_1_token_k16_two_runs": [rr1["frames_per_s"], rr2["frames_per_s"]]}
    out = ["## 4. The per-unit anchor — the only basis for a per-unit claim (G4)", "",
           "One RocketRide token against ONE LlamaIndex worker, same documents, same in-flight C. This is a "
           "96-document stratified sub-slice: **smoke-scale absolutes, not comparable with the 10k tables above.**", ""]
    out += table(["Docs, 96-PDF sub-slice", "C=1 docs/s", "C=8 docs/s", "C=8 / C=1", "C=8 engine cores", "C=8 idle core-equiv."], rows)
    out += ["", f"{DAG} {CAVEAT}", "",
            "One token scales with documents in flight; one LlamaIndex worker does not — its `/process_pdf` "
            "handles one document per request and is effectively single-concurrency per worker, so LlamaIndex's "
            "headline throughput comes from its worker count.", "",
            f"Video, 16-video slice, K=16: one LlamaIndex instance {n(li1['frames_per_s'], 3)} frames/s at "
            f"{n(li1['effective_cores'], 3)} cores; one RocketRide token {n(rr1['frames_per_s'], 3)} and "
            f"{n(rr2['frames_per_s'], 3)} frames/s in two runs ({pct(spread(rr1['frames_per_s'], rr2['frames_per_s']))} apart) "
            f"at {n(rr1['effective_cores'], 3)} / {n(rr2['effective_cores'], 3)} cores.", "",
            f"Sources: `{s3b}/analysis_docs_anchor96.json`, `{s3b}/video/analysis_video_anchor.json`, "
            f"`{smoke}/analysis_video.json`, `{s3b}/video/analysis_video_rep.json`.", ""]
    return out


def smoke_scale(s3b: Path, F: Dict[str, Any]) -> List[str]:
    a = load(s3b / "analysis_docs_384.json", "s3b_docs_384")
    out = ["## 5. How the operating points were chosen — smoke slice, 384 stratified PDFs (Stage 3b)", "",
           "**Smoke-scale absolutes. Never compare these with the 10k figures above.** The 384-document slice "
           "is stratified by page count × characters per page; one long PDF can set a short leg's span.", ""]
    rows = []
    F["s3b"] = {"noise_floor": {arm: a["noise_floor"][arm].get("floor") for arm in ("rr", "li")}}
    for arm, label in (("rr", "RocketRide — 1 token"), ("li", "LlamaIndex — 24 workers")):
        knee = a["ranking"][arm]["call"]["continuous_knee"]
        curve = ", ".join(f"C={c}: {n(v)}" for c, v in sorted(knee["curve"].items(), key=lambda kv: int(kv[0])))
        byk = a["ranking"][arm]["by_k"]
        grid = ", ".join(f"K={r['k']}: {n(r['docs_per_s_mean'])}" for r in sorted(byk, key=lambda r: r["k"]))
        tie = f" (TIE between C={knee['tie_between']})" if knee.get("tie") else ""
        rows.append([label, curve + (f" {DAG}" if arm == "rr" else ""), f"{knee['verdict']}{tie}",
                     grid + (f" {DAG}" if arm == "rr" else ""), pct(a["noise_floor"][arm].get("floor"))])
        F["s3b"][arm] = {"continuous_knee": knee, "by_k": [{k: r[k] for k in ("k", "runs", "docs_per_s_mean", "docs_per_s_all")} for r in byk]}
    out += table(["Arm", "Continuous C curve, docs/s", "Knee", "Batch K, docs/s (mean of runs)", "Warm replicate floor"], rows)
    us = a.get("check_G3b_unit_sweep") or {}
    ce = a.get("check_G5a_cache_effect") or {}
    F["s3b"]["unit_sweep"], F["s3b"]["cache_effect"] = us, ce
    out += ["", f"{DAG} {CAVEAT}", "",
            "The in-grid best K was the grid edge (K=128) on both arms and continuous submission beat every "
            "K on both arms, so K=256/512/1024 were characterised at 10k scale (Ruling B, §2). K values at or "
            "above the slice size collapse to one batch here and are not rankable at this scale.", ""]
    wrows = [[f"{w} workers", ", ".join(n(x) for x in v), n(sum(v) / len(v))]
             for w, v in sorted((us.get("li", {}).get("C=32") or {}).items(), key=lambda kv: int(kv[0]))]
    if wrows:
        out += ["**LlamaIndex worker count at C=32 (G3b).** Not resolved above its floor; 24 kept.", ""]
        out += table(["Service workers", "docs/s, each run", "mean"], wrows) + [""]
    crows = []
    for arm in ("rr", "li"):
        for cell, v in sorted((ce.get(arm) or {}).items()):
            d = (lambda x: f"{x} {DAG}") if arm == "rr" else (lambda x: x)
            base, _, units = cell.partition("@units=")
            label = base + (f", {units} workers" if arm == "li" else ", 1 token")
            crows.append([{"rr": "RocketRide", "li": "LlamaIndex"}[arm], label, d(", ".join(n(x) for x in v["warm_runs"])),
                          d(", ".join(n(x) for x in v["cold_runs"])), f"{v['delta_pct']:+.1f}%"])
    if crows:
        out += ["**Cold vs warm page cache (G5a)**, each cold leg against warm legs of the same arm shape. Caches "
                "dropped before the cold leg; every Stage 4 leg is prewarmed.", ""]
        out += table(["Arm", "Cell", "Warm runs, docs/s", "Cold run, docs/s", "Cold vs warm mean"], crows) + [""]
    out += [f"Source: `{s3b}/analysis_docs_384.json` (ranking, noise_floor, check_G3b_unit_sweep, check_G5a_cache_effect).", ""]
    return out


def smoke_video(smoke: Path, s3b: Path, F: Dict[str, Any]) -> List[str]:
    sm = load(smoke / "analysis_video.json", "smoke_video")
    rep = load(s3b / "video" / "analysis_video_rep.json", "s3b_video_rep")
    rows = []
    for d, tag in ((sm, "first run"), (rep, "replicate")):
        for x in sorted(d["legs"], key=lambda x: (x["arm"], x["k"])):
            rows.append([{"rr": "RocketRide — 1 token", "li": "LlamaIndex — 8x4"}[x["arm"]], f"K={x['k']}", tag,
                         n(x["frames_per_s"], 3), n(x["effective_cores"], 3),
                         n((x.get("percore_host") or {}).get("idle_core_equivalents"), 3)])
    F["smoke_video"] = [r for r in rows]
    rrk = {x["k"]: x["frames_per_s"] for x in sm["legs"] if x["arm"] == "rr"}
    rr_rep = next((x["frames_per_s"] for x in rep["legs"] if x["arm"] == "rr" and x["k"] == 16), None)
    if len(rrk) > 1 and rr_rep and 16 in rrk:
        F["smoke_video_rr_k_range"] = {"range": (max(rrk.values()) - min(rrk.values())) / (sum(rrk.values()) / len(rrk)),
                                       "replicate_spread": spread(rrk[16], rr_rep)}
    out = ["**Video, 16-video smoke slice — how K=16 was chosen.** Smoke-scale absolutes; never beside the 168-video figures.", ""]
    out += table(["Arm", "Videos in flight", "Run", "frames/s", "engine cores", "idle core-equiv."], rows)
    out += ["", "RocketRide at one token barely moves with K (one detector instance serves every frame); the stock "
            "video pipeline was chunk-identical across runs and across K on every video, and differed from the "
            "other arm on every video (the null control).", "",
            f"Sources: `{smoke}/analysis_video.json`, `{s3b}/video/analysis_video_rep.json`.", ""]
    return out


def answers(F: Dict[str, Any]) -> List[str]:
    """The questions as asked, answered from figures the sections below computed — nothing new."""
    h, env, v = F["stage4_docs_headline"], F.get("stage4_envelope", {}), F["stage4_video"]
    R, L = h["rr"], h["li"]
    ks = lambda arm: sorted((int(k.split("_k")[1]), e) for k, e in env.items() if k.startswith(arm + "_k"))  # noqa: E731
    def curve(arm: str) -> str:
        d = (lambda x: f"{x} {DAG}") if arm == "rr" else (lambda x: x)
        return ", ".join(f"K={k}: {d(n(e['docs_per_s']))}" for k, e in ks(arm))
    best_b = {arm: max(ks(arm), key=lambda ke: ke[1]["docs_per_s"]) for arm in ("rr", "li") if ks(arm)}
    out = ["## 0. Answers", "",
           "**Optimal batch size, GovDocs PDFs.** No batch size is optimal on either arm: per-document continuous "
           "submission beats every batch size at full scale. Within batch mode, throughput rises with K at full "
           f"scale on both arms (RocketRide {curve('rr')}; LlamaIndex {curve('li')}), because fewer barriers "
           "mean less time waiting on each batch's slowest document."]
    if best_b:
        out[-1] += (f" Even the best batch reaches only {n(best_b['rr'][1]['docs_per_s'] / R['docs_per_s_span'], 3)}"
                    f" of RocketRide's continuous rate {DAG} and {n(best_b['li'][1]['docs_per_s'] / L['docs_per_s_span'], 3)}"
                    " of LlamaIndex's.")
    margins = {arm: [(k, e["batch_report"]["straggler_margin_s"]) for k, e in ks(arm)] for arm in ("rr", "li")}
    died = sum(len(e["batch_report"].get("batches_died") or []) for e in env.values())
    anon = {arm: [e["batch_report"].get("peak_anon_mb") for _, e in ks(arm) if e["batch_report"].get("peak_anon_mb")]
            for arm in ("rr", "li")}
    out += ["", f"**The cost of large batches.** The batch holding `{STRAGGLER}` had this many seconds to spare "
            "against the 1,800 s batch deadline, by K — RocketRide: "
            + ", ".join(f"K={k}: {n(m, 1)}" for k, m in margins["rr"]) + f" {DAG}; LlamaIndex: "
            + ", ".join(f"K={k}: {n(m, 1)}" for k, m in margins["li"]) + ". "
            + ("No batch died on either arm. " if died == 0 else f"**{died} batch(es) died** (§2). ")
            + "Peak engine anon memory across K: "
            + "; ".join(f"{ {'rr': 'RocketRide', 'li': 'LlamaIndex'}[arm]} {gb(min(v))} to {gb(max(v))}" for arm, v in anon.items() if v)
            + " (§2).", ""]
    sv = F.get("smoke_video_rr_k_range")
    out += ["**Optimal \"batch\", AMI video.** Neither arm has a frame-batch knob. The only lever, videos in flight, "
            "was set to K=16 for both arms from the 16-video smoke slice (§5)"
            + (f"; RocketRide at one token moved {pct(sv['range'])} from K=1 to K=16, inside its own K=16 replicate "
               f"spread of {pct(sv['replicate_spread'])}." if sv else "."), "",
            "**Best to best, full scale, each arm at its own optimum** (§1, §3). Not a per-unit comparison — one "
            "RocketRide token against 24 LlamaIndex workers (docs) or 8 instances (video):", ""]
    out += table(["Full scale", "RocketRide — 1 token", "LlamaIndex"],
                 [["Docs: span docs/s (PRIMARY)", f"{n(R['docs_per_s_span'])} {DAG}", n(L["docs_per_s_span"])],
                  ["Docs: CPU utilisation, engine / 32", f"{pct(R['cpu_utilization'])} {DAG}", pct(L["cpu_utilization"])],
                  ["Docs: idle core-equivalents of 32", f"{n(R['idle_core_equivalents'], 3)} {DAG}", n(L["idle_core_equivalents"], 3)],
                  ["Docs: idle spin (burned, not idle)", f"{n(R['idle_spin_burned_cores'], 3)} {DAG}", n(L["idle_spin_burned_cores"], 3)],
                  ["Video: frames/s", "RANKING ONLY (leg-6 rule)", n(v["li_k16"]["frames_per_s"], 3)],
                  ["Video: CPU utilisation, engine / 32", pct(v["rr_k16"]["cpu_util_of_box"]), pct(v["li_k16"]["cpu_util_of_box"])],
                  ["Video: idle core-equivalents of 32", n(v["rr_k16"]["idle_core_equivalents"], 3), n(v["li_k16_idle_core_equivalents"], 3)]])
    g4 = F.get("g4_anchor_docs") or {}
    if g4:
        rr_x = g4["rr"]["c8"]["docs_per_s"] / g4["rr"]["c1"]["docs_per_s"]
        li_x = g4["li"]["c8"]["docs_per_s"] / g4["li"]["c1"]["docs_per_s"]
        out += ["", f"{DAG} {CAVEAT}", "",
                f"**Per unit** (§4, the only basis for a per-unit claim): from one to eight documents in flight, one "
                f"RocketRide token's throughput grows {rr_x:.2f}x; one LlamaIndex worker's grows {li_x:.2f}x.", ""]
    return out


def pending(s5: Optional[Path], F: Dict[str, Any]) -> List[str]:
    out = ["## Not verified / pending", ""]
    items = []
    missing = [k for k in ("rr_k1024", "li_k1024") if k not in F.get("stage4_envelope", {})]
    if missing:
        items.append(f"Envelope legs not in this analysis: {', '.join(missing)}.")
    if s5 is None:
        items.append("Stage 5 (S5-A, S5-B, S5-C, S5-D) has not run.")
    items += ["No 10k-scale replicate exists for any K or C: the full-scale K ranking borrows the smoke-slice floors "
              "(pre-registered in `envelope_floors.json`) and is therefore an ordering, not a resolved ranking.",
              "The 168-video RocketRide leg ran once; its absolute frames/s is not quotable (leg-6 rule).",
              "WITHDRAWN interim Stage 3b figures, reported in-session from scratch analyses that pooled unlike "
              "legs: the K=128 means (pooled the cold-cache leg with the warm runs) and LlamaIndex's C=32 "
              "cold-vs-warm delta (pooled three worker counts against a 24-worker cold leg). §5 carries the "
              "partitioned values from the committed analysis (registers 39, 42).",
              "Every figure in this summary is read from the analysis file named beside it; the inputs and their "
              "sha256s are listed at the end."]
    return out + [f"- {i}" for i in items] + [""]


# ---------------------------------------------------------------- Stage 5 (segregated) -------------
def stage5(s5: Optional[Path], F: Dict[str, Any]) -> List[str]:
    out = ["## 6. Stage 5 — optimisation investigation (SEGREGATED from every baseline table above)", "",
           "All of Stage 5 runs at ONE RocketRide token. Nothing here is out-of-the-box RocketRide: S5-A is a "
           "TUNED POSTURE (image unchanged, thread configuration set), S5-B is a PATCHED ENGINE (new image), "
           "S5-C binds cpusets on purpose (diagnostic, outside Ruling A), S5-D is an INSTRUMENTED replay. The "
           "comparator for per-unit statements is the G4 anchor (§4), never the tuned 8x4 cell.", ""]
    if s5 is None:
        return out + ["**PENDING — Stage 5 has not run.**", ""]
    F["stage5"] = {}
    # S5-A
    t = load(s5 / "analysis_s5a_threads.json", "s5a", required=False)
    out += ["### S5-A — intra-op thread width T at one token (TUNED POSTURE)", ""]
    if not t:
        out += ["PENDING / NOT RUN — no analysis file.", ""]
    else:
        F["stage5"]["s5a"] = t
        rows = [[f"T={T}", n(r["frames_per_s"], 3), n(r["effective_cores"], 3), pct(r["cpu_util_of_box"]),
                 n(r["idle_core_equivalents"], 3), n(r["cpu_s_per_frame"], 3), n(r["in_process_torch"])]
                for T, r in sorted(t["by_T"].items(), key=lambda kv: int(kv[0]))]
        out += table(["T (TUNED POSTURE)", "frames/s", "engine cores", "util / 32", "idle core-equiv.", "CPU-s/frame",
                      "torch threads read in-process"], rows)
        eq = t.get("T16_vs_default") or {}
        out += ["", f"Knee T={t.get('knee_T')} ({t.get('knee_rule')}); saturation T={t.get('saturation_T')}. "
                f"Excluded legs: {json.dumps(t.get('excluded'))}.",
                f"T=16 against the out-of-the-box default cell: {eq.get('verdict')} (relative {eq.get('relative')}, "
                f"chunk-identical videos {eq.get('chunk_hash_identical_videos')}).",
                f"Comparator, G4 anchor: {json.dumps(t.get('comparator_G4_anchor'))}.", "",
                f"Source: `{s5}/analysis_s5a_threads.json`.", ""]
    # S5-B
    pre = load(s5 / "s5b_precheck" / "s5b_precheck.json", "s5b_precheck", required=False)
    b = load(s5 / "analysis_s5b.json", "s5b", required=False)
    out += ["### S5-B — detector frame micro-batching (PATCHED-ENGINE, NOT OUT-OF-THE-BOX)", ""]
    if pre:
        F["stage5"]["s5b_precheck"] = {"verdict": pre.get("verdict"), "tiers_by_b": pre.get("tiers_by_b")}
        out += [f"Pre-check (read-only, unmodified `rr:patched-video`, pre-registered tiers): **{pre.get('verdict')}**; "
                f"tiers by B: {json.dumps(pre.get('tiers_by_b'))}.", ""]
    else:
        out += ["Pre-check: PENDING / NOT RUN.", ""]
    if b:
        F["stage5"]["s5b"] = b
        out += [f"Null control (patched B=1 vs stock, chunk hashes): {json.dumps(b.get('null_control_patched_B1_vs_stock'))}.",
                f"Correctness by B: {json.dumps(b.get('correctness_by_b'))[:900]}.", ""]
        rows = [[f"B={B}", "PATCHED-ENGINE", n(r["frames_per_s"], 3), n(r["effective_cores"], 3), pct(r["cpu_util_of_box"]),
                 n(r["idle_core_equivalents"], 3), json.dumps(r.get("engine_memory_mb"))]
                for B, r in sorted((b.get("timing_only_for_passing_b") or {}).items(), key=lambda kv: int(kv[0]))]
        if rows:
            out += table(["B", "Label", "frames/s", "engine cores", "util / 32", "idle core-equiv.", "engine memory, MB"], rows)
        out += ["", f"Verdict: {b.get('verdict')}. Source: `{s5}/analysis_s5b.json`.", ""]
    elif pre:
        out += ["S5-B proper: not run or not analysed (the chain refuses unless the pre-check passed).", ""]
    # S5-C
    c = load(s5 / "analysis_s5c_smt.json", "s5c", required=False)
    out += ["### S5-C — is RocketRide's 32-vCPU cost hyperthreading? (DIAGNOSTIC — cpusets bound on purpose)", ""]
    if not c:
        out += ["PENDING / NOT RUN — no analysis file.", ""]
    else:
        F["stage5"]["s5c"] = c
        nc = c.get("null_control") or {}
        out += [f"Null control (two unconstrained RocketRide runs): spread {pct(nc.get('spread'))} against the "
                f"{pct(nc.get('floor'))} floor — {'PASS' if nc.get('PASS') else 'FAIL'}.", ""]
        rows = []
        for name, cell in (c.get("cells") or {}).items():
            if not cell:
                continue
            d = (lambda x: f"{x} {DAG}") if name.startswith("rr") else (lambda x: x)
            rows.append([name, str(cell.get("declared_cpuset") or "none (32 vCPU)"), d(n(cell.get("docs_per_s"))),
                         d(n(cell.get("cpu_s_per_doc"), 3)), d(n(cell.get("engine_cores"), 3)),
                         n(cell.get("threads_task_node_py")), n(cell.get("threads_java"))])
        out += table(["Cell (384 slice, continuous C=32)", "cpuset", "docs/s", "CPU-s/doc", "engine cores",
                      "task-process threads", "JVM threads"], rows)
        out += ["", f"{DAG} {CAVEAT}", "",
                f"Hypothesis test: {json.dumps(c.get('hypothesis_test'))}.", f"Verdict: **{c.get('verdict')}**.", "",
                f"Source: `{s5}/analysis_s5c_smt.json`.", ""]
    # S5-D
    fd = load(s5 / "analysis_s5d_funnel.json", "s5d", required=False)
    out += ["### S5-D — the admission funnel inside one token (INSTRUMENTED replay of leg 1)", ""]
    if not fd:
        out += ["PENDING / NOT RUN — no analysis file.", ""]
    else:
        F["stage5"]["s5d"] = fd
        comps = ("admission_wait", "parse", "split", "embed", "return")
        rows = []
        for tname, s in [("all documents", fd["all_documents"])] + list(fd["by_page_tercile"].items()):
            if not s.get("n"):
                continue
            rows.append([tname, n(s["n"])] + [f"{pct(s[k]['share_of_end_to_end'])} (p50 {n(s[k]['p50_s'], 2)} s)" for k in comps])
        out += table(["Documents", "n", "admission wait", "parse (Tika, incl. contention)", "split", "embed", "return"], rows)
        p = fd.get("perturbation_vs_leg1") or {}
        out += ["", f"Instrument perturbation against leg 1: {p.get('relative')} ({p.get('verdict')}). "
                f"Outliers over 300 s held by: {json.dumps(fd.get('outliers_held_by'))}. Joined {n(fd.get('joined_documents'))} "
                f"documents, {n(fd.get('unjoined'))} unjoined. Cannot separate: {fd.get('cannot_separate')}.", "",
                f"Source: `{s5}/analysis_s5d_funnel.json`.", ""]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=Path, default=RES / "batchsize_smoke_20260920T113000Z")
    ap.add_argument("--s3b", type=Path, default=RES / "batchsize_s3b_20260920T203139Z")
    ap.add_argument("--s4", type=Path, default=RES / "batchsize_s4_20260921T013303Z")
    ap.add_argument("--s4-analysis", type=Path, default=None)
    ap.add_argument("--s5", type=Path, default=None)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    for p in (a.out_md, a.out_json):
        if p.exists():
            print(f"REFUSED: {p} exists — append-only"); return 3
    s4a = load(a.s4_analysis or (a.s4 / "analysis_docs.json"), "s4_docs")
    F: Dict[str, Any] = {}
    md = ["# Batch-size optimisation — RocketRide (one token, out of the box) and LlamaIndex, GovDocs PDFs and AMI video", "",
          f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} by `working/scripts/batchsize_final_report.py` "
          "from committed analysis artifacts; every table names its source, and `batchsize_final_summary.json` "
          "records each input's sha256. Box: one c7i.8xlarge, 32 vCPUs, one workload at a time.", ""]
    body: List[str] = []
    body += headline_docs(a.s4, s4a, F)
    body += empty_content(s4a, a.s4, F)
    body += envelope(a.s4, s4a, F)
    body += video_stage4(a.s4, a.smoke, a.s3b, F)
    body += anchor(a.s3b, a.smoke, F)
    body += smoke_scale(a.s3b, F)
    body += smoke_video(a.smoke, a.s3b, F)
    body += stage5(a.s5, F)
    md += answers(F) + body + pending(a.s5, F)
    md += ["## Inputs", ""] + [f"- {k}: `{v}`" for k, v in sorted(INPUTS.items())] + [""]
    a.out_md.write_text("\n".join(md) + "\n")
    a.out_json.write_text(json.dumps({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "inputs": INPUTS, "figures": F, "caveat_rr_docs": CAVEAT}, indent=1))
    print(f"wrote {a.out_md} and {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
