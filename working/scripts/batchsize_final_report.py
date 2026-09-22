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
DDAG = "‡"
PARA = "¶"
# The ruled caveat (Ansh, 2026-09-22): S5-C's same-harness measurement, replacing a cross-session
# figure (register 46). main() recomputes it from the S5-C analysis and REFUSES if the two differ, so the
# text on every RocketRide docs figure cannot drift from the artifact it cites.
CAVEAT_RULED = ("32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% "
                "CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)")
CAVEAT = CAVEAT_RULED
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


def find_export(camp: Path, launch: str) -> Optional[Path]:
    """A launch's export sits beside it (S3 layout) or one level up (committed layout), named by run_dir."""
    base = camp if camp.is_absolute() else ROOT / camp
    for d, one_up in ((base, False), (base.parent, True)):
        for f in sorted(d.glob("exp_batchsize_sweep_*.json")):
            try:
                parts = (json.loads(f.read_text()).get("data", {}).get("run_dir") or "").rstrip("/").split("/")
            except (OSError, json.JSONDecodeError):
                continue
            if parts[-1] == launch and (not one_up or (len(parts) > 1 and parts[-2] == camp.name)):
                return f
    return None


def docs_posture(camp: Path, launch: str, name: str) -> Dict[str, Any]:
    f = find_export(camp, launch)
    if f is None:
        raise SystemExit(f"REFUSED: no export for {camp}/{launch} — the posture cannot be read back, and is never assumed")
    INPUTS[name] = f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}  sha256:{hashlib.sha256(f.read_bytes()).hexdigest()[:16]}"
    p = json.loads(f.read_text())["data"]["posture"]
    rb = p.get("in_process_readback") or {}
    env = set((p.get("thread_env") or {}).values())
    torch = rb.get("torch_num_threads", rb.get("health_torch_threads"))
    return {"thread_env": sorted(env), "in_process_torch_threads": torch, "ws1_workers": p.get("ws1_workers"),
            "rr_tokens": p.get("rr_tokens"), "rr_threads_requested": p.get("rr_threads_requested"),
            "cpuset_effective": (p.get("cpuset_effective") or {}).get("raw"), "host_nproc": p.get("host_nproc"),
            "image_id": (p.get("image_id") or "")[:19]}


def docs_posture_text(pp: Dict[str, Any], arm: str) -> str:
    env = pp["thread_env"]
    envs = ("six thread variables at " + env[0]) if len(env) == 1 else f"thread variables {env}"
    req = str(pp["rr_threads_requested"])
    unit = (f"{pp['rr_tokens']} token, threads= " + ("not passed" if req.startswith("NOT PASSED") else req) if arm == "rr"
            else f"{pp['ws1_workers']} workers")
    who = "task process" if arm == "rr" else "each worker"
    return (f"{unit}; {envs}; torch threads read in {who}: {pp['in_process_torch_threads']}; "
            f"cpuset {pp['cpuset_effective']} of {pp['host_nproc']}")


def video_posture_text(leg_dir: Path, name: str) -> Dict[str, Any]:
    base = leg_dir if leg_dir.is_absolute() else ROOT / leg_dir
    fs = sorted(base.glob("preflight_*.json"))
    if not fs:
        raise SystemExit(f"REFUSED: no preflight in {leg_dir} — the video posture cannot be read back")
    INPUTS[name] = f"{leg_dir}/{fs[0].name}  sha256:{hashlib.sha256(fs[0].read_bytes()).hexdigest()[:16]}"
    rb = json.loads(fs[0].read_text()).get("readbacks") or {}
    envs = {v for r in rb.values() for v in (r.get("env") or {}).values()}
    torch = sorted({r.get("torch_num_threads") for r in rb.values()})
    env_txt = ("six thread variables unset" if envs == {None} else
               "six thread variables at " + ", ".join(sorted(str(e) for e in envs)))
    return {"processes_read": len(rb), "text": f"{len(rb)} process(es) read back: {env_txt}; torch threads {torch}"}


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
                                     "anon_mb_at_window_close": v["mem"].get("anon_mb"), "memory_peak_mb_total": v["mem"].get("peak_mb"),
                                     "documents": v["docs"]} for k, v in arms.items()}
    R, L = arms["rr"], arms["li"]
    R["posture"] = docs_posture(s4, rr_launch, "s4_export_rr_p1")
    L["posture"] = docs_posture(s4, li_launch, "s4_export_li_p2")
    F["stage4_docs_headline"]["rr"]["posture"] = R["posture"]
    F["stage4_docs_headline"]["li"]["posture"] = L["posture"]

    def r(x: str) -> str:
        return f"{x} {DAG}"
    lk = L["knee"]
    li_choice = (f"continuous, C=32 — a TIE with C={lk['tie_between'][0]} inside its "
                 f"{pct(lk['noise_floor_used'])} floor; C=32 kept per register 12, not as a winner"
                 if lk.get("tie") else "continuous, C=32")
    rows_out = [
        ["Posture — banked docs posture: 1 token, six vars = 1, both arms (read back in-process)",
         r(docs_posture_text(R["posture"], "rr")), docs_posture_text(L["posture"], "li")],
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
        ["Engine memory (cgroup): anon at window close / total high-water memory.peak",
         f"{gb(R['mem'].get('anon_mb'))} / {gb(R['mem'].get('peak_mb'))} {DAG}",
         f"{gb(L['mem'].get('anon_mb'))} / {gb(L['mem'].get('peak_mb'))}"],
        ["Documents: completed / content outcome (no text, parse failed) / lost to the deadline / other failure",
         " / ".join(n(R["docs"][k]) for k in ("completed", "content_outcome", "deadline_loss", "other_failure")) + f" {DAG}",
         " / ".join(n(L["docs"][k]) for k in ("completed", "content_outcome", "deadline_loss", "other_failure"))],
    ]
    out = ["## 1. Headline — each arm at its own measured optimum, 9,975 GovDocs PDFs (Stage 4)", "",
           "Both arms run the **banked docs posture: 1 token, six vars = 1, both arms** — RocketRide one token "
           "(`use()` with no `threads=`), LlamaIndex 24 service workers (its own measured optimum), and the six "
           "BLAS/OpenMP/torch thread variables = 1 on both, read back from inside the running processes (first "
           "row). The six variables at 1 are the campaign's banked docs posture, not RocketRide's out-of-the-box "
           "default (which leaves them unset; S5-E measures the difference). This row pair answers \"how fast does each stack go at its best on this box\"; it is "
           "**not** a per-unit comparison — one token against 24 workers — and carries no parity claim. The "
           "per-unit comparison is the G4 anchor, §4. Both arms unconstrained across all 32 vCPUs (Ruling A); one "
           "leg on the box at a time (Ruling C); caches prewarmed.", ""]
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
           "**Batch K** is the only lever that exists without modifying an arm: RocketRide "
           "`send_files(K files)` on one token; LlamaIndex K concurrent single-document POSTs behind a "
           "barrier (its service has no multi-document endpoint). The next batch starts only when every "
           "document of the current one has returned. Batch deadline pre-registered at 1,800 s for every K "
           "and both arms before the first envelope leg; a batch lost to it is blast radius, never re-run.", "",
           "**What K means inside each arm — SOURCE, not measurement.** RocketRide: the installed SDK (rocketride "
           "1.3.0) opens all K pipes at once, with no client-side bound (`rocketride/mixins/data.py:719-725`); the "
           "engine admits at most 64 pipes per token (`engine/ai/modules/data/data_conn.py:138,477`; threadCount 64 "
           "when `threads=` is not passed, `engine/ai/constants.py:48`, `task_engine.py:247,382`) and runs each "
           "document's pipeline on asyncio's default executor (`data_conn.py:737`), which is 32 threads on this "
           "32-vCPU box. So K is documents per barrier, and at K of 32 or more at most 32 are processed at once. "
           "LlamaIndex: K concurrent POSTs (`working/scripts/exp_batchsize_sweep.py:702`) to 24 single-concurrency "
           "workers, so at most 24 are processed at once. The SDK and engine files cited were hashed on the box "
           "and match the copies read here.", ""]
    keys = {"rr": [(128, "p3_rr_k128/k128_main"), (256, "e7_rr_k256/k256_env"), (512, "e9_rr_k512/k512_env"),
                   (1024, "e11_rr_k1024/k1024_env")],
            "li": [(128, "p4_li_k128/k128_main"), (256, "e8_li_k256/k256_env"), (512, "e10_li_k512/k512_env"),
                   (1024, "e12b_li_k1024/k1024_env")]}   # e12 crashed in OUR driver (EMFILE) and measured nothing; e12b is its re-run (register 44)
    F["stage4_envelope"] = {}
    for arm in ("rr", "li"):
        u = a["ranking"][arm].get("arm_units_ranked")
        label = "RocketRide — 1 token" if arm == "rr" else f"LlamaIndex — {u} workers"
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
            held = (f"#{br['straggler_batch']}: DIED at the deadline ({n(br['straggler_batch_wall_s'], 1)} s)"
                    if br.get("straggler_batch") in died else
                    f"#{br['straggler_batch']}: {n(br['straggler_batch_wall_s'], 1)} s ({n(br['straggler_margin_s'], 1)} s spare)")
            launch, legname = key.split("/")
            oc = outcome_counts(s4 / launch / f"perdoc_{arm}_{legname}.jsonl", f"s4_perdoc_{arm}_{legname}")
            span = ((a.get("check_E_tail") or {}).get("per_leg") or {}).get(key, {}).get("span_s")
            share = (br["straggler_batch_wall_s"] / span) if span and br.get("straggler_batch_wall_s") else None
            returned = oc["completed"] + oc["content_outcome"]
            lost = oc["deadline_loss"] + oc["other_failure"]
            rows.append([f"K={k}" + (" (re-run, register 44)" if key.startswith("e12b") else ""),
                         d(n(row["docs_per_s_mean"])), n(br["batches"]),
                         f"{n(br['wall_s_median'], 1)} / {n(br['wall_s_max'], 1)}", held, pct(share),
                         (n(len(died)) + (" — **BLAST-RADIUS-DOMINATED**" if len(died) > 1 else
                                            f" — batch {died[0]}, blast radius" if died else "")),
                         f"{n(returned)} / {n(lost)} / {n(oc['completed'])}",
                         f"{gb(br.get('anon_mb_at_window_close'))} – {gb(br.get('memory_peak_mb_total'))}",
                         d(n(row.get("idle_core_equivalents"), 3))])
            F["stage4_envelope"][f"{arm}_k{k}"] = {"docs_per_s": row["docs_per_s_mean"], "batch_report": br,
                                                  "idle_core_equivalents": row.get("idle_core_equivalents"),
                                                  "cpu_utilization": row.get("cpu_utilization"),
                                                  "straggler_batch_share_of_span": share, "span_s": span,
                                                  "documents": {"returned": returned, "lost": lost,
                                                                "numerator_with_content": oc["completed"],
                                                                "content_outcome": oc["content_outcome"],
                                                                "by_reason": oc.get("by_reason")}}
            walls = ", ".join(f"{b}:{w}" for b, w in sorted(br["per_batch_wall_s"].items(), key=lambda kv: int(kv[0])))
            per_batch.append(f"- K={k} ({key}): {walls}")
        cr = cont_row(a, arm, 32)
        rows.append(["continuous C=32 (reference)", (f"{n(cr['docs_per_s'])} {DAG}" if arm == "rr" else n(cr["docs_per_s"])),
                     "—", "—", "—", "—", "—", "—", "—", (f"{n(cr['idle_core_equivalents'], 3)} {DAG}" if arm == "rr" else n(cr["idle_core_equivalents"], 3))])
        out += [f"### {label}", ""]
        out += table(["K", "Span docs/s", "Batches", "Batch wall median / max, s",
                      f"Batch holding {STRAGGLER}: wall (spare to 1,800 s)", "That batch's share of the span",
                      "Batches died", "Documents returned / lost / numerator of docs/s §",
                      "Peak engine anon, bracketed ¶", "Idle core-equiv."], rows)
        out += [""] + ([f"{DAG} {CAVEAT}", ""] if arm == "rr" else [])
        out += [f"{PARA} cgroup v2 keeps no anon high-water mark, so peak anon RSS is bracketed, not read: at least the "
                "anon at the window's close, at most the container's total high-water `memory.peak`. No memory was "
                "sampled during a leg, so no statement about how memory moved with K is made.",
                "§ Returned = documents with content + content outcomes (no text, parse failed); lost = deadline losses "
                "+ other failures. docs/s divides the documents WITH CONTENT (the third number) by the span.", ""]
        out += ["<details><summary>Per-batch wall times, s (batch index: wall)</summary>", ""] + per_batch + ["", "</details>", ""]
    k1 = {arm: F["stage4_envelope"].get(f"{arm}_k1024", {}).get("documents") for arm in ("rr", "li")}
    if k1["rr"] and k1["li"]:
        out += [f"**K=1,024, stated plainly.** RocketRide returned {n(k1['rr']['returned'])} documents "
                f"({n(k1['rr']['numerator_with_content'])} with content, {n(k1['rr']['content_outcome'])} content outcomes) and "
                f"lost {n(k1['rr']['lost'])} to the deadline {DAG}; LlamaIndex returned {n(k1['li']['returned'])} "
                f"({n(k1['li']['numerator_with_content'])} with content, {n(k1['li']['content_outcome'])} content outcomes) and lost "
                f"{n(k1['li']['lost'])}. Each arm's docs/s divides its documents with content — "
                f"{n(k1['rr']['numerator_with_content'])} and {n(k1['li']['numerator_with_content'])} — by its span.", ""]
    out += fd_note(s4, F)
    out += straggler_order(s4, a, F)
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


def fd_note(s4: Path, F: Dict[str, Any]) -> List[str]:
    """R6: the two K=1,024 legs ran under different open-file limits; say so, with what each angle shows."""
    e11 = s4 / "e11_rr_k1024" / "perdoc_rr_k1024_env.jsonl"
    emfile = 0
    reasons: Dict[str, int] = {}
    for x in e11.read_text().splitlines():
        if x.strip():
            r = json.loads(x)
            rs = str(r.get("reason"))
            reasons[rs] = reasons.get(rs, 0) + 1
            if "OSError" in rs or "Errno 24" in rs or "Too many open files" in rs:
                emfile += 1
    exp = find_export(s4, "e12b_li_k1024")
    lim = (json.loads(exp.read_text())["data"]["posture"].get("driver_open_files") if exp else None) or {}
    F["fd_note"] = {"e11_open_file_errors": emfile, "e11_reasons": reasons, "e12b_driver_open_files": lim}
    return [f"**The two K=1,024 legs ran under different open-file limits.** RocketRide's e11 ran before the fix "
            "(register 44), at the box's default soft limit of 1,024 descriptors; LlamaIndex's e12b ran at "
            f"{n(lim.get('soft'))} (recorded in its export). No descriptor count was sampled during e11, so its peak is not "
            f"measured. Its records carry {n(emfile)} open-file errors — every loss is `batch_error:TimeoutError`. SOURCE, "
            "not measurement: the SDK opens a file only after the engine grants its pipe (`rocketride/mixins/data.py:651`), "
            "and the engine grants at most 64 per token (`data_conn.py:138,477`), so RocketRide's open files stay near 64 "
            "plus its one websocket, whatever K.", ""]


def straggler_order(s4: Path, a: Dict[str, Any], F: Dict[str, Any]) -> List[str]:
    """R3: where 039_039660.pdf sat in each leg's submission order, and what that order did to the span."""
    legs = [("p1_rr_cont32", "rr", "refc32_main"), ("p2_li_cont", "li", "refc32_main"), ("p3_rr_k128", "rr", "k128_main"),
            ("p4_li_k128", "li", "k128_main"), ("e7_rr_k256", "rr", "k256_env"), ("e8_li_k256", "li", "k256_env"),
            ("e9_rr_k512", "rr", "k512_env"), ("e10_li_k512", "li", "k512_env"), ("e11_rr_k1024", "rr", "k1024_env"),
            ("e12b_li_k1024", "li", "k1024_env")]
    rows, F["straggler_order"] = [], {}
    tail = (a.get("check_E_tail") or {}).get("per_leg") or {}
    for launch, arm, leg in legs:
        f = s4 / launch / f"perdoc_{arm}_{leg}.jsonl"
        rs = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        order = sorted(rs, key=lambda r: (r["submit_ns"], r["doc"]))
        idx = next(i for i, r in enumerate(order) if r["doc"] == STRAGGLER) + 1
        me = next(r for r in rs if r["doc"] == STRAGGLER)
        sb = tail.get(f"{launch}/{leg}", {}).get("span_set_by", {})
        F["straggler_order"][launch] = {"sent_at": idx, "of": len(rs), "batch": me.get("batch"),
                                        "held_s": round((me["completion_ns"] - me["submit_ns"]) / 1e9, 1),
                                        "set_the_span": sb.get("doc") == STRAGGLER}
        d = (lambda x: f"{x} {DAG}") if arm == "rr" else (lambda x: x)
        rows.append([launch, d(f"{n(idx)} of {n(len(rs))}"), "—" if me.get("batch") is None else f"#{me['batch']}",
                     d(n(F["straggler_order"][launch]["held_s"], 1)), "yes" if sb.get("doc") == STRAGGLER else f"no — `{sb.get('doc')}`"])
    out = [f"**Where `{STRAGGLER}` sat in each leg's submission order** (R3). Every leg sends the slice in the same "
           "fixed order (the slice's sha256 order), so the document is sent at the same position in every leg:", ""]
    out += table(["Leg", "Sent at", "Batch", "Held, s", "Set the span?"], rows)
    p1 = F["straggler_order"]["p1_rr_cont32"]
    from_last = p1["of"] - p1["sent_at"] + 1
    out += ["", f"**The span is order-dependent.** `{STRAGGLER}` is the {n(from_last)}th document from the end of the order (position {n(p1['sent_at'])} of "
            f"{n(p1['of'])}); on RocketRide it is then held {n(p1['held_s'], 1)} s {DAG}, so it outlasts the rest of the run and sets "
            "the span of the continuous leg, and on batched legs it is in the last batch at every K. Sent early, that hold "
            "would overlap the bulk of the run and the span would be set by the bulk. The span with it dropped from both arms (§1) and the p99 diagnostic are the "
            "order-robust views; the span itself is a property of this order as much as of the arm.", ""]
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
    lp = video_posture_text(s4 / "p5_li_video" / "li_k16", "s4_video_li_preflight")
    rp = video_posture_text(s4 / "p6_rr_video" / "rr_k16", "s4_video_rr_preflight")
    F["stage4_video"]["posture"] = {"li": lp, "rr": rp}
    rows = [["Posture, read back in-process", f"{li.get('posture')}: {lp['text']}",
             f"out of the box — {rr.get('posture')}: {rp['text']}"],
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
    for arm in ("rr", "li"):
        u = a["ranking"][arm].get("arm_units_ranked")
        label = "RocketRide — 1 token" if arm == "rr" else f"LlamaIndex — {u} workers"
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
    prov = load(s3b / "provenance_check.json", "s3b_provenance", required=False)
    if prov:
        F["provenance_s3b"] = prov
        out += [f"**Provenance of these analyses** (R7): {prov['verdict']}. The misfiled `shake_rr` export names "
                f"`{prov['misfiled_copy']['run_dir_it_names']}` and matched no launch; the check's null control (a planted "
                "export naming another campaign) was rejected. Source: "
                f"`{s3b}/provenance_check.json`.", ""]
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
           "**Optimal batch size, GovDocs PDFs.** No batch size beats continuous submission on either arm: sending "
           "each document as soon as a slot frees was faster than every batch size at full scale. Within batch mode, "
           f"throughput rises with K on both arms (RocketRide {curve('rr')}; LlamaIndex {curve('li')}) — "
           "consistent with the pre-registered hypothesis that each batch barrier costs a wait for that batch's "
           "slowest document, so fewer barriers approach the continuous rate."]
    if best_b:
        out[-1] += (f" Even the best batch reaches only {n(best_b['rr'][1]['docs_per_s'] / R['docs_per_s_span'], 3)}"
                    f" of RocketRide's continuous rate {DAG} and {n(best_b['li'][1]['docs_per_s'] / L['docs_per_s_span'], 3)}"
                    " of LlamaIndex's.")
    def spare(e: Dict[str, Any]) -> str:
        br = e["batch_report"]
        return ("died at the deadline" if br.get("straggler_batch") in (br.get("batches_died") or [])
                else n(br["straggler_margin_s"], 1))
    margins = {arm: [(k, spare(e)) for k, e in ks(arm)] for arm in ("rr", "li")}
    deaths = [(arm, k, e["batch_report"]) for arm in ("rr", "li") for k, e in ks(arm) if e["batch_report"].get("batches_died")]
    died = sum(len(br["batches_died"]) for _, _, br in deaths)
    anon = {arm: [e["batch_report"].get("anon_mb_at_window_close") for _, e in ks(arm)
                  if e["batch_report"].get("anon_mb_at_window_close")] for arm in ("rr", "li")}
    tot = {arm: [e["batch_report"].get("memory_peak_mb_total") for _, e in ks(arm)
                 if e["batch_report"].get("memory_peak_mb_total")] for arm in ("rr", "li")}
    out += ["", f"**The cost of large batches.** The batch holding `{STRAGGLER}` had this many seconds to spare "
            "against the 1,800 s batch deadline, by K — RocketRide: "
            + ", ".join(f"K={k}: {m}" for k, m in margins["rr"]) + f" {DAG}; LlamaIndex: "
            + ", ".join(f"K={k}: {m}" for k, m in margins["li"]) + ". "
            + ("No batch died on either arm. " if died == 0 else
               " ".join(f"**{ {'rr': 'RocketRide', 'li': 'LlamaIndex'}[arm]} K={k} lost {len(br['batches_died'])} batch(es) to the "
                        f"deadline — {n(br['documents_lost_total'])} documents — reported as blast radius, never re-run.**"
                        for arm, k, br in deaths) + " ")
            + "Engine anon memory at each leg's close, across K: "
            + "; ".join(f"{ {'rr': 'RocketRide', 'li': 'LlamaIndex'}[arm]} {gb(min(v))} to {gb(max(v))}" for arm, v in anon.items() if v)
            + "; total high-water `memory.peak`: "
            + "; ".join(f"{ {'rr': 'RocketRide', 'li': 'LlamaIndex'}[arm]} {gb(min(v))} to {gb(max(v))}" for arm, v in tot.items() if v)
            + " — peak anon lies between the two (§2).", ""]
    sv = F.get("smoke_video_rr_k_range")
    out += ["**Optimal \"batch\", AMI video.** Neither arm has a frame-batch knob. The only lever, videos in flight, "
            "was set to K=16 for both arms from the 16-video smoke slice (§5)"
            + (f"; RocketRide at one token moved {pct(sv['range'])} from K=1 to K=16, inside its own K=16 replicate "
               f"spread of {pct(sv['replicate_spread'])}." if sv else "."), "",
            "**Best to best, full scale, each arm at its own optimum** (§1, §3). Not a per-unit comparison — one "
            f"RocketRide token against {L['posture']['ws1_workers']} LlamaIndex workers (docs) or "
            f"{v['posture']['li']['processes_read']} LlamaIndex instances (video):", ""]
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
    s5 = F.get("stage5") or {}
    lines = []
    a = s5.get("s5a")
    if a:
        lines.append(f"S5-A (TUNED POSTURE): intra-op width stops adding throughput at T={a.get('knee_T')}; beyond it only CPU "
                     f"cost rises, and every T other than 16 changes the detection scores. Unset vs 16: "
                     f"{(a.get('T16_vs_default') or {}).get('verdict', '')[:60].split(' — ')[0]}.")
    b = s5.get("s5b")
    if b:
        lines.append("S5-B (PATCHED-ENGINE): " + ("STOPPED — batched detection failed the end-to-end correctness control; "
                                                  "B>1 is a different measurement, not an optimisation."
                                                  if b.get("not_reported") else "every B passed correctness."))
    c = s5.get("s5c")
    if c:
        lines.append(f"S5-C (DIAGNOSTIC): null control {'passed' if (c.get('null_control') or {}).get('PASS') else 'FAILED'}; "
                     f"beyond its spread, {(c.get('hypothesis_test') or {}).get('reading', '').split(' — ')[0]}.")
    d = s5.get("s5d")
    if d:
        lines.append("S5-D (INSTRUMENTED): no admission queue — the time is inside the pipeline, the long holds in parse; "
                     "the parse-concurrency read of the same stamps finds those holds are the documents' own Tika cost, "
                     "not a parse bound (§6).")
    ef = s5.get("s5ef")
    if ef:
        m = (ef.get("s5e") or {}).get("docs_per_s") or {}
        if "readable" in m:
            cpu = (ef.get("s5e") or {}).get("cpu_s_per_doc") or {}
            lines.append("S5-E (thread variables unset vs = 1, docs): " + (
                ("unset is " + ("slower" if m["unset_vs_env1"] < 0 else "faster") + " and costs "
                 + ("more" if (cpu.get("unset_vs_env1") or 0) > 0 else "less") + " CPU per document — READABLE beyond every "
                 "noise measure; the banked docs posture, not the out-of-the-box one, is the faster RocketRide docs posture")
                if m["readable"] else "the difference is NOT readable against the noise") + " (§6).")
        f5 = ef.get("s5f") or {}
        if f5.get("c5") and f5.get("c5_over_same_session_c32") is not None:
            lines.append(f"S5-F (SDK default-5 equivalent, C=5): {n(f5['c5_over_same_session_c32'], 3)} of this session's "
                         f"C=32 rate {DAG} (§6).")
    if lines:
        out += ["**Stage 5, segregated** (§6; no Stage 5 figure appears beside a baseline one):", ""] + [f"- {x}" for x in lines] + [""]
    return out


def checks(s4a: Dict[str, Any], s4: Path, F: Dict[str, Any]) -> List[str]:
    """Every independent angle the full-scale analysis took, with its verdict — and the null
    control that shows the comparator could have failed (register entry 2)."""
    A, B = s4a.get("check_A_clock") or {}, s4a.get("check_B_cpu_source") or {}
    C, T = s4a.get("check_C_content") or {}, (s4a.get("check_E_tail") or {}).get("by_arm") or {}
    H = s4a.get("box_hygiene_per_leg") or {}
    def tally(d: Dict[str, Any]) -> str:
        vs: Dict[str, int] = {}
        for v in d.values():
            vs[v.get("verdict")] = vs.get(v.get("verdict"), 0) + 1
        return ", ".join(f"{k} {c}" for k, c in sorted(vs.items(), key=lambda kv: str(kv[0])))
    dirty = [k for k, v in H.items() if v.get("other_containers") or not (v.get("stray_processes") or {}).get("clean", False)]
    nc = C.get("null_control_cross_arm") or {}
    F["checks"] = {"A": tally(A), "B": tally(B), "C": {k: (C.get(k) or {}).get("verdict") for k in ("rr", "li")},
                   "C_null": nc, "tail": {k: v.get("verdict") for k, v in T.items()}, "hygiene_dirty": dirty}
    rows = [["A. Clock: docs/s from per-document wall stamps vs the export's monotonic span", f"{len(A)} legs: {tally(A)}", "—"],
            ["B. CPU source: engine cgroup cores vs host per-core busy on the same CPUs", f"{len(B)} legs: {tally(B)}", "—"],
            ["C. Content: chunk hashes identical across every K and C within an arm",
             f"RocketRide {F['checks']['C']['rr']}, LlamaIndex {F['checks']['C']['li']}",
             f"cross-arm comparison {nc.get('verdict')}: {n(nc.get('differing'))} of {n(nc.get('common'))} documents differ (different parsers)"],
            ["E. The K ranking is the same by span and by time-to-p90", ", ".join(f"{k}: {v}" for k, v in F["checks"]["tail"].items()), "—"],
            ["Ruling C: no other container, no stray process above 0.5 cores, before each leg",
             f"{len(H)} legs: " + ("all clean" if not dirty else f"NOT clean: {', '.join(dirty)}"), "—"]]
    out = ["## Checks behind the full-scale figures", ""]
    out += table(["Check", "Verdict", "Null control"], rows)
    out += ["", f"Source: `{s4}/analysis_docs.json` → check_A_clock, check_B_cpu_source, check_C_content, check_E_tail, "
            "box_hygiene_per_leg.", ""]
    return out


def jvm_note(c: Dict[str, Any]) -> List[str]:
    """What the process snapshots say about where the JVM runs — read from the analysis, never assumed."""
    procs = [p for n_, cell in (c.get("cells") or {}).items() if cell and n_.startswith("rr")
             for p in (cell.get("processes_top") or [])]
    names = sorted({p.get("name") for p in procs})
    javas = [p for p in procs if p.get("name") in ("java", "jspawnhelper")]
    if javas and all(p.get("name") == "jspawnhelper" for p in javas):
        return ["In every RocketRide cell's snapshot the only JVM process is `jspawnhelper` (1 thread), the JVM's "
                "spawn helper: there is no standalone `java` process, so the JVM runs inside the task process and its "
                f"threads are in the task-process column. Processes seen: {', '.join(f'`{x}`' for x in names)}."]
    return [f"Processes seen in the RocketRide snapshots: {', '.join(f'`{x}`' for x in names)}."]


def register_entries(since: str = "2026-09-20") -> str:
    """The register entries this campaign added, read from their own dated headings."""
    import re
    f = ROOT / "working" / "video" / "METHODOLOGY_REGISTER.md"
    got = [int(m.group(1)) for m in re.finditer(r"^## (\d+)\. .*\(added (\d{4}-\d{2}-\d{2})\)", f.read_text(), re.M)
           if m.group(2) >= since]
    return (f"Entries {min(got)}-{max(got)} were added during this campaign, dated {since} or later"
            if got else f"No register entry is dated {since} or later")


def self_audit(F: Dict[str, Any]) -> List[str]:
    """The contract's closing block, built from the verdicts the analyses recorded — each null control
    with the way it came out, including the ones that failed."""
    s5 = F.get("stage5") or {}
    ch = F.get("checks") or {}
    nulls = [f"content check across arms (Stage 4): {(ch.get('C_null') or {}).get('verdict')}"]
    a = s5.get("s5a")
    if a:
        nc = (a.get("output_vs_default") or {}).get("null_control_default_vs_its_replicate") or {}
        nulls.append(f"S5-A output comparator, default cell against its own replicate: "
                     f"{nc.get('chunk_identical_videos')}/{nc.get('videos')} chunk-identical, score change "
                     f"{nc.get('max_abs_score_delta_at_least')}")
    pre = s5.get("s5b_precheck")
    if pre:
        nulls.append(f"S5-B pre-check N1 (single frame reproducible) {pre.get('null_N1_single_is_reproducible')}, "
                     f"N2 (comparator sees a different frame) {pre.get('null_N2_comparator_sees_a_different_frame')}")
    b = s5.get("s5b")
    if b:
        nulls.append(f"S5-B patched B=1 against stock: {json.dumps(b.get('null_control_patched_B1_vs_stock'))}")
    c = s5.get("s5c")
    if c:
        nc = c.get("null_control") or {}
        nulls.append(f"S5-C two unconstrained RocketRide runs: spread {pct(nc.get('spread'))} against "
                     f"{pct(nc.get('floor'))} — {'PASS' if nc.get('PASS') else 'FAILED'}")
    d = s5.get("s5d")
    if d:
        p = d.get("perturbation_vs_leg1") or {}
        nulls.append(f"S5-D instrument against leg 1: {(p.get('relative') or 0) * 100:+.2f}% — {p.get('verdict')}")
    osf = s5.get("output_shift")
    if osf:
        for name, key in (("output-shift comparator, default vs its replicate", "null_control_default_vs_its_replicate"),
                          ("output-shift comparator, patched B=1 vs default", "null_control_patched_B1_vs_default")):
            c = osf[key]
            nulls.append(f"{name}: {c['chunk_identical_videos']}/{c['videos']} chunk-identical, score shift {c['max_abs_score_delta_at_least']}")
    prov = F.get("provenance_s3b")
    if prov:
        nulls.append(f"Stage 3b provenance: a planted export naming another campaign rejected — "
                     f"{prov.get('null_control', {}).get('planted_export_for_another_campaign_rejected')}")
    ef = s5.get("s5ef")
    if ef:
        nulls.append(f"S5-E/S5-F posture read-back: legs excluded for a read-back that contradicts their posture — "
                     f"{json.dumps([x['leg'] for x in ef.get('excluded') or []])}")
    out = ["## SELF-AUDIT", "",
           "- **HYPOTHESIS.** Pre-registered, per stage: batch barriers cost a wait for each batch's slowest document "
           "(§2); intra-op width can widen one token (S5-A); batched detection is not bit-identical (S5-B); "
           "RocketRide pays an SMT tax the other arm does not (S5-C); one token queues small documents at admission "
           "behind large ones (S5-D).",
           "- **EVIDENCE.** Every figure above is read from the committed analysis named beside it; the inputs and "
           "their sha256s close this document.",
           "- **NULL CONTROLS**, each as it came out:"] + [f"  - {x}" for x in nulls] + [
           f"- **REGISTER.** {register_entries()} (working/video/METHODOLOGY_REGISTER.md).",
           "- **NOT VERIFIED.** Listed in the section above; nothing absent from these tables is claimed.",
           "- **GATES.** Every landing passed autoland's gates with an ls-remote read-back; the commits are on "
           "`feat/batch-size-optimization`.", ""]
    return out


def pending(s5: Optional[Path], F: Dict[str, Any]) -> List[str]:
    out = ["## Not verified / pending", ""]
    items = []
    missing = [k for k in ("rr_k1024", "li_k1024") if k not in F.get("stage4_envelope", {})]
    if missing:
        items.append(f"Envelope legs not in this analysis: {', '.join(missing)}.")
    if s5 is None:
        items.append("Stage 5 (S5-A, S5-B, S5-C, S5-D) has not run.")
    st5 = F.get("stage5") or {}
    for key, name in (("s5a", "S5-A"), ("s5b", "S5-B proper"), ("s5c", "S5-C"), ("s5d", "S5-D")):
        if s5 is not None and key not in st5:
            items.append(f"{name}: no analysis in this summary.")
    a = st5.get("s5a")
    if a:
        changed = [T for T, c in ((a.get("output_vs_default") or {}).get("by_T") or {}).items()
                   if c.get("chunk_identical_videos") != c.get("videos")]
        if changed:
            items.append(f"S5-A: T={', '.join(sorted(changed, key=int))} changed the detector's output against the default "
                         "cell (see its table) — a tuned thread width is not output-neutral, and its throughput is not a "
                         "like-for-like speed-up of the same computation.")
    c = st5.get("s5c")
    if c and not (c.get("null_control") or {}).get("PASS"):
        items.append(f"S5-C's pre-registered null control failed (spread {pct((c.get('null_control') or {}).get('spread'))}); "
                     "only differences beyond that spread are read, and the post-hoc view beside it is labelled as such.")
    d = st5.get("s5d")
    if d and "OUTSIDE" in str((d.get("perturbation_vs_leg1") or {}).get("verdict")):
        items.append("S5-D's instrument moved the leg beyond the floor: its stage SHARES stand; its absolute stage times "
                     "carry the offset.")
    items += ["No 10k-scale replicate exists for any K or C: the full-scale K ranking borrows the smoke-slice floors "
              "(pre-registered in `envelope_floors.json`) and is therefore an ordering, not a resolved ranking.",
              "The 168-video RocketRide leg ran once; its absolute frames/s is not quotable (leg-6 rule).",
              "WITHDRAWN: the earlier RocketRide docs caveat, a posture cost computed ACROSS harness sessions (Stage 3's "
              "24-core cpuset against Stage 3b's 32 vCPU); the caveat now carries S5-C's same-harness figures (register 46).",
              "WITHDRAWN: an in-session statement that engine memory was flat with K. No memory was sampled during a leg; "
              "the cgroup gives a bracket only (§2).",
              "CORRECTED: an earlier statement (in-session and register 45) that one S5-B frame changed its label set. No label "
              "or count changed: one detection's score crossed the edge of Tier 2's threshold band (§6, register 47).",
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
                "Output against the out-of-the-box default cell — a DIAGNOSTIC, not a pre-registered gate for S5-A "
                "(intra-op width changes the floating-point path, as batching does in S5-B):", ""]
        ov = t.get("output_vs_default") or {}
        orow = []
        for name, c in ([("default vs its own replicate (null control)", ov.get("null_control_default_vs_its_replicate") or {})]
                        + [(f"T={T}", c) for T, c in sorted((ov.get("by_T") or {}).items(), key=lambda kv: int(kv[0]))]):
            if c:
                orow.append([name, f"{n(c['chunk_identical_videos'])}/{n(c['videos'])}",
                             f"{n(c['frames_label_multiset_identical'])}/{n(c['frames'])}",
                             f"{n(c['frames_detection_count_identical'])}/{n(c['frames'])}",
                             f"{c['max_abs_score_delta_at_least']:.2e}"])
        if orow:
            out += table(["Leg", "chunk-identical videos", "frames with identical labels", "frames with identical counts",
                          "largest score change (at least)"], orow) + [""]
        out += ["Comparator, the G4 anchor (one LlamaIndex instance, K=16, same videos): "
                f"{n((t.get('comparator_G4_anchor') or {}).get('frames_per_s'), 3)} frames/s at "
                f"{n((t.get('comparator_G4_anchor') or {}).get('effective_cores'), 3)} cores.", "",
                f"Source: `{s5}/analysis_s5a_threads.json`.", ""]
    # S5-B
    pre = load(s5 / "s5b_precheck" / "s5b_precheck.json", "s5b_precheck", required=False)
    b = load(s5 / "analysis_s5b.json", "s5b", required=False)
    out += ["### S5-B — detector frame micro-batching (PATCHED-ENGINE, NOT OUT-OF-THE-BOX)", ""]
    if pre:
        F["stage5"]["s5b_precheck"] = {k: pre.get(k) for k in ("verdict", "tiers_by_b", "frames", "null_N1_single_is_reproducible",
                                                               "null_N2_comparator_sees_a_different_frame", "by_batch_size")}
        out += [f"Pre-check, read-only, in a throwaway container of the unmodified `rr:patched-video` on {n(pre.get('frames'))} "
                f"frames, criterion pre-registered in the artifact: **{pre.get('verdict')}**", "",
                f"Null controls: one frame at a time is bit-reproducible — {pre.get('null_N1_single_is_reproducible')}; "
                f"the comparator sees two different frames as different — {pre.get('null_N2_comparator_sees_a_different_frame')}.", ""]
        prow = [[f"B={b}", f"{n(r.get('bit_identical_frames'))}/{n(r.get('frames'))}",
                 f"{r.get('tier2_max_score_delta', 0):.2e} (limit 1e-05)",
                 f"{r.get('tier2_max_box_delta_output_px', 0):.2e} (limit 1e-03)",
                 str(r.get("detection_counts_equal")), str(r.get("tier"))]
                for b, r in sorted((pre.get("by_batch_size") or {}).items(), key=lambda kv: int(kv[0]))]
        if prow:
            out += table(["Batch", "bit-identical frames", "max score change", "max box change, output px",
                          "detection counts equal", "Tier"], prow) + [""]
    else:
        out += ["Pre-check: PENDING / NOT RUN.", ""]
    if b:
        F["stage5"]["s5b"] = b
        nc = b.get("null_control_patched_B1_vs_stock") or {}
        out += [f"**Null control** (patched B=1, through the new batched code path, against stock by chunk hash): "
                f"{n(nc.get('chunk_identical'))}/{n(nc.get('videos'))} videos identical — {'PASS' if nc.get('PASS') else 'FAILED'}.", ""]
        crow = [[f"B={B}", str(r.get("tier1_bit_identical")), f"{n(r.get('tier2_failing_frames'))}/{n(r.get('frames_compared'))}",
                 f"{(r.get('max_score_delta') or 0):.2e} (limit 1e-05)", f"{(r.get('max_box_delta_px') or 0):.2e} (limit 1e-03)",
                 str(r.get("tier"))]
                for B, r in sorted((b.get("correctness_by_b") or {}).items(), key=lambda kv: int(kv[0]))]
        if crow:
            out += table(["Batch", "Tier 1: every video chunk-identical", "Tier 2: frames failing", "max score change",
                          "max box change, output px", "Result"], crow) + [""]
        stopped = [int(x) for x in b.get("not_reported") or []]
        if stopped and pre:
            out += [f"**S5-B STOPPED by its end-to-end correctness control: B={stopped} is a different measurement, not an "
                    "optimisation (the ruling), and carries no timing.** The pre-check passed Tier 2 on "
                    f"{n(pre.get('frames'))} frames of one video; end to end, over every frame of the 16 videos, the same "
                    "criterion failed — the pre-check licensed the build and the legs, never the claim.", ""]
        osf = load(s5 / "analysis_output_shift.json", "s5_output_shift", required=False)
        if osf:
            F["stage5"]["output_shift"] = osf
            cmp_rows = []
            for name, c in ([("null: default vs its own replicate", osf["null_control_default_vs_its_replicate"]),
                             ("null: patched B=1 vs default", osf["null_control_patched_B1_vs_default"])]
                            + [(f"S5-A T={T} vs default (TUNED POSTURE)", c) for T, c in osf["s5a_thread_width_vs_default"].items()]
                            + [(f"S5-B B={B} vs patched B=1 (PATCHED-ENGINE)", c) for B, c in osf["s5b_batch_vs_patched_B1"].items()]):
                cmp_rows.append([name, f"{n(c['chunk_identical_videos'])}/{n(c['videos'])}",
                                 f"{n(c['frames_label_multiset_identical'])}/{n(c['frames'])}",
                                 f"{c['max_abs_score_delta_at_least']:.2e}"])
            ex = osf.get("s5b_tier2_label_set_failures_explained") or {}
            meas = {B: x["tier2_failing_frames_on_measured_videos"] for B, x in ex.items()}
            warm = {B: x["tier2_failing_frames_on_warm_up_videos"] for B, x in ex.items()}
            lsf = [(B, r) for B, x in ex.items() for r in x["label_set_failures"]]
            changed = [r for _, r in lsf if r["any_label_or_count_changed"]]
            out += ["**The stop, read as a measurement** (item 4). One comparator for every knob — per-frame label multisets "
                    "and scores from the driver's own records, 16 measured videos; scores paired in sorted order, so each "
                    "figure is a lower bound:", ""]
            out += table(["Leg", "chunk-identical videos", "frames with every label kept", "score shift, at least"], cmp_rows) + [""]
            out += ["A thread-width change alone (S5-A) moves scores by at least "
                    f"{min(c['max_abs_score_delta_at_least'] for T, c in osf['s5a_thread_width_vs_default'].items() if c['chunk_identical_videos'] != c['videos']):.1e} "
                    "with every label kept; batching (S5-B) moves them by up to "
                    f"{max(c['max_abs_score_delta_at_least'] for c in osf['s5b_batch_vs_patched_B1'].values()):.1e}, also with every label kept "
                    "on the measured frames. The pre-registered Tier 2 tolerance (1e-05 score, 1e-03 px) sits below both; the stop "
                    "is that criterion's, and it stands.",
                    f"Tier 2 failing frames on the 16 measured videos: {', '.join(f'B={B}: {n(v)}' for B, v in meas.items())}; on the two "
                    f"warm-up videos the taps also cover: {', '.join(f'B={B}: {n(v)}' for B, v in warm.items())}. "
                    + (f"The taps' {len(lsf)} \"label set or count differs\" failure(s) changed no label and no count: "
                       + "; ".join(f"B={B} `{r['video']}` frame {r['frame']}, "
                                   + ", ".join(f"{d_['label']} {d_['score_B1']} → {list(d_.values())[2]}" for d_ in r["detections_crossing_the_band_edge"])
                                   for B, r in lsf)
                       + " — a score crossing the edge of the ±0.001 band around the 0.3 threshold, which the rule filters on each "
                       "side by that side's own scores." if lsf and not changed else ""), "",
                    f"Source: `{s5}/analysis_output_shift.json`.", ""]
        rows = [[f"B={B}", "PATCHED-ENGINE", n(r["frames_per_s"], 3), n(r["effective_cores"], 3), pct(r["cpu_util_of_box"]),
                 n(r["idle_core_equivalents"], 3),
                 ", ".join(f"{k.replace('_bytes', '')} {v / 1024:.1f} GiB" for k, v in (r.get("engine_memory_mb") or {}).items()
                           if isinstance(v, (int, float)))]
                for B, r in sorted((b.get("timing_only_for_passing_b") or {}).items(), key=lambda kv: int(kv[0]))]
        if rows:
            out += table(["B", "Label", "frames/s", "engine cores", "util / 32", "idle core-equiv.",
                          "engine memory: total high-water (peak) and anon at leg end — peak anon lies between"], rows)
        out += ["", f"Verdict: {b.get('verdict')}. Source: `{s5}/analysis_s5b.json`.", ""]
    elif pre:
        out += [("S5-B proper: PENDING — not analysed yet." if str(pre.get("verdict", "")).startswith("PASS")
                 else "S5-B proper: STOPPED by the pre-check, per the ruling."), ""]
    # S5-C
    c = load(s5 / "analysis_s5c_smt.json", "s5c", required=False)
    out += ["### S5-C — is RocketRide's 32-vCPU cost hyperthreading? (DIAGNOSTIC — cpusets bound on purpose)", ""]
    if not c:
        out += ["PENDING / NOT RUN — no analysis file.", ""]
    else:
        F["stage5"]["s5c"] = c
        nc = c.get("null_control") or {}
        out += [f"**Null control, pre-registered** (two unconstrained RocketRide runs, span docs/s): "
                f"{n(nc.get('rr_a1'))} and {n(nc.get('rr_a2'))}, spread {pct(nc.get('spread'))} against the "
                f"{pct(nc.get('floor'))} floor — **{'PASS' if nc.get('PASS') else 'FAILED'}**."
                + ("" if nc.get("PASS") else
                   f" No between-cell difference below {pct(nc.get('spread'))} is interpretable."), ""]
        ph = nc.get("POST_HOC_DIAGNOSTIC")
        if ph:
            sb = ph.get("span_set_by") or {}
            out += [f"POST-HOC DIAGNOSTIC ({ph.get('label')}): the same pair agrees within "
                    f"{pct(ph.get('cpu_s_per_doc_spread'))} on CPU-s/doc — the metric the hypothesis turns on — and "
                    f"{pct(ph.get('docs_per_s_to_p90_spread'))} on docs/s to p90; both spans were set by "
                    + ", ".join(f"`{v.get('span_set_by')}` (held {n(v.get('held_s'), 1)} s)" for v in sb.values() if v)
                    + ", so the span gap is one document's finishing time.", ""]
        comp = []
        for arm, label in (("rocketride", "RocketRide"), ("llamaindex", "LlamaIndex")):
            for cell, v in (c.get(arm) or {}).items():
                comp.append([label, {"b_0-23": "(b) cpuset 0-23", "c_one_per_core": "(c) one vCPU per physical core"}.get(cell, cell),
                             f"{v['cpu_s_per_doc_vs_a'] * 100:+.1f}%", f"{v['docs_per_s_vs_a'] * 100:+.1f}%", n(v.get("cpuset_cpus"))])
        if comp:
            out += table(["Arm", "Cell against (a), unconstrained 32 vCPU", "CPU-s/doc", "docs/s", "CPUs"], comp) + [""]
        rb = (c.get("rocketride") or {}).get("b_0-23")
        if rb:
            out += [f"**The caveat is this row.** RocketRide at cpuset 0-23 against 32 vCPU, same harness: "
                    f"{rb['docs_per_s_vs_a'] * 100:+.1f}% docs/s, {rb['cpu_s_per_doc_vs_a'] * 100:+.1f}% CPU-s/doc — the {DAG} caveat on "
                    "every RocketRide docs figure. It replaces an earlier caveat that compared Stage 3 (24-core cpuset, an "
                    "earlier harness session) with Stage 3b (32 vCPU, a later one); that cross-session figure is WITHDRAWN "
                    "(register 46).", ""]
        rows = []
        for name, cell in (c.get("cells") or {}).items():
            if not cell:
                continue
            # C4's caveat describes the UNCONSTRAINED posture; a cell bound to a cpuset on purpose
            # would be mislabelled by it, so those RocketRide rows carry their own mark.
            mark = (DAG if not cell.get("declared_cpuset") else DDAG) if name.startswith("rr") else ""
            d = (lambda x, m=mark: f"{x} {m}".rstrip())
            rows.append([name, str(cell.get("declared_cpuset") or "none (32 vCPU)"), d(n(cell.get("docs_per_s"))),
                         d(n(cell.get("cpu_s_per_doc"), 3)), d(n(cell.get("engine_cores"), 3)),
                         n(cell.get("threads_task_node_py")), n(cell.get("threads_java"))])
        out += table(["Cell (384 slice, continuous C=32)", "cpuset", "docs/s", "CPU-s/doc", "engine cores",
                      "task-process threads", "JVM threads"], rows)
        out += ["", f"{DAG} {CAVEAT}", f"{DDAG} RocketRide under a declared cpuset — an S5-C diagnostic outside Ruling A, "
                "never a baseline figure.", "",
                f"Hypothesis reading, at the tolerance the failed control leaves ({pct((c.get('hypothesis_test') or {}).get('tolerance_used'))}): "
                f"**{(c.get('hypothesis_test') or {}).get('reading')}**. Analyser verdict: {c.get('verdict')}.", "",
] + jvm_note(c) + ["",
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
        out += table(["Documents (share of end-to-end latency; p50)", "n", "admission wait", "parse (Tika, incl. contention)",
                      "split", "embed", "return"], rows)
        terc = [s for s in fd["by_page_tercile"].values() if s.get("n")]
        adm_max = max(s["admission_wait"]["share_of_end_to_end"] for s in terc) if terc else None
        adm_p99 = max(s["admission_wait"]["p99_s"] for s in terc) if terc else None
        held = fd.get("outliers_held_by") or {}
        n_out = sum(held.values())
        top = max(held, key=lambda k: held[k]) if n_out else None
        out += ["", f"**The lane hypothesis, at admission: not supported.** Waiting for admission is at most "
                f"{pct(adm_max)} of end-to-end latency in any page tercile (p99 at most {n(adm_p99, 2)} s): documents enter "
                "the pipeline as they are sent. The time is spent INSIDE it."
                + (f" Of the {n_out} documents held over 300 s, {held[top]} were held in {top}"
                   + ", ".join([""] + [f"{v} in {k}" for k, v in held.items() if v and k != top]) + "." if n_out else ""),
                f"Joined {n(fd.get('joined_documents'))} documents; {n(fd.get('unjoined'))} unjoined (content outcomes and the "
                f"deadline loss, which never reach every stage). Cannot separate: {fd.get('cannot_separate')}.", ""]
        p = fd.get("perturbation_vs_leg1") or {}
        out += [f"**Instrument perturbation, pre-registered** (span docs/s against leg 1, floor {pct(p.get('floor'))}): "
                f"{n(p.get('instrumented_docs_per_s'))} against {n(p.get('leg1_docs_per_s'))}, "
                f"{(p.get('relative') or 0) * 100:+.2f}% — {p.get('verdict')}.", ""]
        ph = p.get("POST_HOC_DIAGNOSTIC")
        if ph:
            out += [f"POST-HOC DIAGNOSTIC ({ph['label']}): docs/s to p90 {ph['to_p90_relative'] * 100:+.2f}%, to p99 "
                    f"{ph['to_p99_relative'] * 100:+.2f}%; both spans set by `{ph['leg1']['span_set_by']}` (held "
                    f"{n(ph['leg1']['held_s'], 1)} s in leg 1, {n(ph['instrumented']['held_s'], 1)} s instrumented); the same "
                    f"deadline loss in both ({', '.join(f'`{x}`' for x in ph['instrumented']['deadline_losses'])}).", ""]
        out += [f"Source: `{s5}/analysis_s5d_funnel.json`.", ""]
        pc = load(s5 / "analysis_s5d_parse_concurrency.json", "s5d_parse_concurrency", required=False)
        if pc:
            F["stage5"]["s5d_parse"] = pc
            ip, pl, th = pc["in_parse_documents"], pc["in_pipeline_documents"], pc["threads_measured"]
            sm, bd = pc["small_documents"], pc["big_documents"]
            holds = pc["long_parse_holds"]
            dev = [abs(h["parse_s"] / h["stage4_leg1_rr_end_to_end_s"] - 1) for h in holds
                   if h.get("stage4_leg1_rr_end_to_end_s") and h["stage4_leg1_rr_end_to_end_s"] < 1800]
            thru = sorted(h["documents_through_parse_inside_its_interval"] for h in holds)
            li_max = max((h["stage4_li_c32_end_to_end_s"] or 0) for h in holds) if holds else None
            big_parse = max((x["parse_s"] for x in pc["big_documents_by_stage"]), default=None)
            big_embed = [x["split_end_to_embed_end_s"] for x in pc["big_documents_by_stage"]]
            out += ["**Parse concurrency inside one token** (item 5 — POST-HOC on the S5-D stamps; laptop only):", ""]
            out += table(["Measured, time-weighted over the leg", "max", "p50", "p95"],
                         [["documents in parse (waiting or parsing)", n(ip["max"]), n(ip["p50"]), n(ip["p95"])],
                          ["documents in the pipeline", n(pl["max"]), n(pl["p50"]), n(pl["p95"])]]) + [""]
            out += [f"- One process carries every stamp, on {n(th['distinct_threads_by_stage'].get('after_parse'))} threads per stage; "
                    f"{n(th['documents_whose_parse_and_embed_ran_on_one_thread'])} of {n(th['documents_with_a_parse_stamp'])} documents "
                    "ran parse and embed on the same thread (the rest are the content outcomes, which have no embed stamp). "
                    f"Up to {n(th['distinct_threads_holding_a_document_in_parse']['max'])} threads held a document in parse at a "
                    "sampled instant (every 25th admission; a lower bound on the maximum).",
                    f"- The {n(bd['n'])} documents of {n(bd['pages_at_least'])}+ pages spent at most {n(big_parse, 1)} s in parse and "
                    f"{n(min(big_embed), 1)}-{n(max(big_embed), 1)} s in embed; some such document was in parse for "
                    f"{n(bd['seconds_with_any_in_parse'], 1)} s of the leg ({pct(bd['share_of_window'])}).",
                    f"- Of {n(sm['n'])} documents under {n(sm['pages_below'])} pages, {n(sm['n_overlapping_a_big_parse'])} were in parse "
                    f"while a {n(bd['pages_at_least'])}+ page document was — {pct(sm['share_of_small_parse_time_overlapping'])} of their parse time; median parse "
                    f"{n(sm['parse_s_with_overlap']['p50'], 2)} s with overlap, {n(sm['parse_s_without_overlap']['p50'], 2)} s without.",
                    f"- The {n(len(holds))} documents held in parse over 300 s reproduce: each one's parse time here is within "
                    f"{pct(max(dev)) if dev else '—'} of its end-to-end time in Stage 4 leg 1, and each took at most {n(li_max, 1)} s "
                    f"end to end on LlamaIndex. While each sat in parse, between {n(thru[0])} and {n(thru[-1])} other documents "
                    f"entered and left parse; the fewest during `{min(holds, key=lambda h: h['documents_through_parse_inside_its_interval'])['doc']}`'s, "
                    "which is sent near the end of the order.", "",
                    "**The hypothesis — parse effectively bounded per token, small documents waiting behind large ones inside "
                    "parse — is not supported on these stamps.** Thousands of documents pass through parse while a slow one "
                    "sits there, so no lock holds parse for a whole document at a time; the large documents are in embed, not "
                    "parse; and the long "
                    "parse holds are the documents' own Tika cost, repeated run to run and absent on pypdf. What the stamps "
                    f"cannot say: {pc['cannot_say']}.", "",
                    "**SOURCE, not measurement — what bounds concurrency inside one task process:** "
                    + pc["SOURCE_not_measurement"]["per_token_processing_bound"] + " "
                    + pc["SOURCE_not_measurement"]["parse_itself"] + " "
                    + pc["SOURCE_not_measurement"]["tika_config"], "",
                    f"Source: `{s5}/analysis_s5d_parse_concurrency.json`.", ""]
    return out


def stage5ef(d: Optional[Path], F: Dict[str, Any]) -> List[str]:
    out = ["### S5-E — the six thread variables unset against = 1, at one token, docs (384-document slice)", ""]
    if d is None:
        return out + ["PENDING / NOT RUN.", "", "### S5-F — SDK default-5 equivalent (PR #1895 / TypeScript maxConcurrent)", "",
                      "PENDING / NOT RUN.", ""]
    r = load(d / "analysis_s5ef.json", "s5ef", required=False)
    if not r:
        return out + ["PENDING — no analysis file.", ""]
    F["stage5"] = F.get("stage5") or {}
    F["stage5"]["s5ef"] = r
    e = r["s5e"]
    tt = e.get("torch_threads_in_process") or {}
    out += [f"RocketRide, continuous C=32, two runs per posture, interleaved; torch intra-op threads read INSIDE the task "
            f"process: = 1 → {tt.get('env1')}, unset → {tt.get('unset')}. Excluded legs: {json.dumps(r.get('excluded'))}. "
            "Pre-registered in `preregistration.json` before any leg ran.", ""]
    rows = []
    for metric, label in (("docs_per_s", "span docs/s — PRIMARY"), ("docs_per_s_to_p90", "docs/s to p90 — pre-registered diagnostic"),
                          ("cpu_s_per_doc", "CPU-s per document")):
        m = e.get(metric) or {}
        a, b = m.get("env1"), m.get("unset")
        if not a or not b:
            rows.append([label, "—", "—", "—", "—", "—"]); continue
        rows.append([label, f"{', '.join(n(x) for x in a['runs'])} (spread {pct(a['spread'])}) {DAG}",
                     f"{', '.join(n(x) for x in b['runs'])} (spread {pct(b['spread'])}) {DAG}",
                     f"{m['unset_vs_env1'] * 100:+.2f}% {DAG}", pct(m["tolerance"]),
                     ("**readable**" if m["readable"] else "not readable") + f"; {m['vs_0_82_floor']} the 0.82% floor"])
    out += table(["Metric", "= 1: runs (spread)", "unset: runs (spread)", "unset vs = 1", "tolerance ‖", "Reading"], rows)
    out += ["", f"{DAG} {CAVEAT}", "‖ the largest of the 0.82% Stage 3b floor, each posture pair's own spread, and S5-C's "
            "null-control spread (same slice) — an effect is read only beyond all of them.", ""]
    s5c = ((F.get("stage5") or {}).get("s5c") or {}).get("cells") or {}
    a1, a2 = s5c.get("rr_a1"), s5c.get("rr_a2")
    e1 = (e.get("docs_per_s") or {}).get("env1")
    if a1 and a2 and e1:
        prev = (a1["docs_per_s"] + a2["docs_per_s"]) / 2
        F["stage5"]["s5ef_cross_session"] = {"s5c_same_cell_mean": prev, "s5e_env1_mean": e1["mean"], "relative": e1["mean"] / prev - 1}
        out += [f"**Cross-session, labelled so.** S5-C ran the same cell — RocketRide, C=32, = 1, unconstrained, this slice — "
                f"in an earlier session: {n(a1['docs_per_s'])} and {n(a2['docs_per_s'])} docs/s {DAG}. This session's = 1 runs average "
                f"{n(e1['mean'])} {DAG}: {(e1['mean'] / prev - 1) * 100:+.1f}%, after a box restart and with every leg prewarmed. A "
                "difference between sessions this large is why a posture cost measured ACROSS sessions was withdrawn from "
                "the caveat (register 46), and why S5-E compares postures only inside one session.", ""]
    f5 = r["s5f"]
    out += ["### S5-F — SDK default-5 equivalent (PR #1895 / TypeScript maxConcurrent)", "",
            "RocketRide, continuous C=5, the banked docs posture (= 1), two runs, same session as S5-E. Before it ran, the "
            "source it rests on was read and recorded (SOURCE, not measurement): the installed Python SDK's `send_files` "
            "gathers one coroutine per file with no client bound (`rocketride/mixins/data.py:719-725`), each waiting in "
            "`pipe.open()` for the engine (`data.py:635-638`); our continuous driver sends each document with "
            "`client.send()` under `asyncio.Semaphore(C)` (`working/scripts/exp_batchsize_sweep.py:651,656,661`). So C=5 "
            "is the client-side bound the TypeScript SDK's default applies, reproduced with the Python primitive; the "
            "batch-K labels are restated in §2 for the engine's own bound.", ""]
    c5 = f5.get("c5")
    if c5:
        cs = f5.get("cross_session_stage3b_curve") or {}
        out += table(["", "docs/s"],
                      [["C=5, runs (spread)", f"{', '.join(n(x) for x in c5['runs'])} ({pct(c5['spread'])}) {DAG}"],
                       ["C=5, mean", f"{n(c5['mean'])} {DAG}"],
                       ["C=32 at = 1, this session (S5-E), mean", f"{n(f5.get('same_session_c32_env1_mean'))} {DAG}"],
                       ["C=5 / C=32, same session", f"{n(f5.get('c5_over_same_session_c32'), 3)} {DAG}"],
                       ["Stage 3b, C=4 / C=8 / C=32 — CROSS-SESSION, ranking context only",
                        " / ".join(n(cs.get(k)) for k in ("4", "8", "32")) + f" {DAG}"]]) + ["", f"{DAG} {CAVEAT}", ""]
        c5p = f5.get("c5_to_p90") or {}
        out += [f"docs/s to p90 at C=5 (pre-registered diagnostic): {', '.join(n(x) for x in c5p.get('runs', []))}.", ""]
    out += [f"Source: `{d}/analysis_s5ef.json`.", ""]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=Path, default=RES / "batchsize_smoke_20260920T113000Z")
    ap.add_argument("--s3b", type=Path, default=RES / "batchsize_s3b_20260920T203139Z")
    ap.add_argument("--s4", type=Path, default=RES / "batchsize_s4_20260921T013303Z")
    ap.add_argument("--s4-analysis", type=Path, default=None)
    ap.add_argument("--s5", type=Path, default=None)
    ap.add_argument("--s5ef", type=Path, default=None, help="the S5-E/S5-F campaign directory")
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--supersedes", type=Path, default=None,
                    help="an earlier summary directory this one replaces; whether every figure is identical is COMPUTED")
    a = ap.parse_args()
    for p in (a.out_md, a.out_json):
        if p.exists():
            print(f"REFUSED: {p} exists — append-only"); return 3
    global CAVEAT
    if a.s5 is None:
        print("REFUSED: the ruled caveat is computed from S5-C; pass --s5"); return 3
    c5 = load(a.s5 / "analysis_s5c_smt.json", "s5c_for_caveat")
    rb = c5["rocketride"]["b_0-23"]
    sp = c5["null_control"]["spread"]
    computed = (f"32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured {rb['docs_per_s_vs_a'] * 100:+.1f}% "
                f"throughput, {rb['cpu_s_per_doc_vs_a'] * 100:+.1f}% CPU-s/doc (S5-C; its null control failed at {sp * 100:.2f}%, "
                f"so differences under {sp * 100:.2f}% are unreadable)")
    if computed != CAVEAT_RULED:
        print(f"REFUSED: the caveat computed from S5-C differs from the ruled text:\n  computed: {computed}\n  ruled:    {CAVEAT_RULED}")
        return 3
    CAVEAT = computed
    s4a = load(a.s4_analysis or (a.s4 / "analysis_docs.json"), "s4_docs")
    F: Dict[str, Any] = {}
    md = ["# Batch-size optimisation — RocketRide at one token and LlamaIndex, GovDocs PDFs and AMI video", "",
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
    body += checks(s4a, a.s4, F)
    body += stage5(a.s5, F)
    body += stage5ef(a.s5ef, F)
    if a.supersedes:
        prev = load(a.supersedes / "batchsize_final_summary.json", "superseded_summary")
        pf = prev.get("figures") or {}
        same = json.dumps(pf, sort_keys=True) == json.dumps(F, sort_keys=True)
        changed = sorted(k for k in set(pf) | set(F) if json.dumps(pf.get(k), sort_keys=True) != json.dumps(F.get(k), sort_keys=True))
        md[3:3] = ["", f"Supersedes `{a.supersedes}` — every figure identical: **{same}**"
                   + (" (only the generated text around them changed)." if same else
                      f"; the figure groups that differ, computed from the two JSON twins: {', '.join(f'`{k}`' for k in changed)}.")]
    md += answers(F) + body + pending(a.s5, F) + self_audit(F)
    md += ["## Inputs", ""] + [f"- {k}: `{v}`" for k, v in sorted(INPUTS.items())] + [""]
    a.out_md.write_text("\n".join(md) + "\n")
    a.out_json.write_text(json.dumps({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "inputs": INPUTS, "figures": F, "caveat_rr_docs": CAVEAT}, indent=1))
    print(f"wrote {a.out_md} and {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
