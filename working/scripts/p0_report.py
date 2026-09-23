#!/usr/bin/env python3
"""p0_report.py — the P0 morning deliverable, GENERATED from committed analysis artifacts.

    p0_report.py <campaign_dir> --out-md <md> --out-json <json>

No figure is typed: every number is read from an analysis_*.json in the campaign directory (each
of which is computed from the raw per-document / per-frame / per-parse records) and rounded only
here, at display. A missing analysis prints NOT RUN with the reason the chain or gate recorded.
Rules applied structurally (preregistration.json): PROFILE / DIAGNOSTIC absolutes never sit beside
baseline figures; every gate prints threshold, measured value and fired-or-not; every RocketRide
docs throughput carries the Ruling A caveat (dagger); ROI is three columns, never a score.
"""
from __future__ import annotations

import argparse
import time
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DAG = "†"
CAVEAT = ("32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, "
          "-11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are "
          "unreadable)")
INPUTS: Dict[str, str] = {}


def load(camp: Path, name: str) -> Optional[Any]:
    f = camp / name
    if not f.exists():
        return None
    INPUTS[name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    return json.loads(f.read_text())


def n(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return f"{x:,}"
    return f"{x:,.{nd}f}"


def pct(x: Optional[float], nd: int = 2) -> str:
    return "—" if x is None else f"{100 * x:+.{nd}f}%"


def pts(x: Optional[float], nd: int = 1) -> str:
    """A difference of two percentages, in percentage points."""
    return "—" if x is None else f"{100 * x:+.{nd}f} points"


def share(x: Optional[float], nd: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{nd}f}%"


def table(head: List[str], rows: List[List[str]]) -> List[str]:
    return (["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
            + ["| " + " | ".join(r) + " |" for r in rows] + [""])


def stage_rows(st: Dict[str, Any], order: List[str]) -> List[List[str]]:
    rows = []
    for k in order:
        v = st.get(k) or {}
        occ = v.get("occupancy") or {}
        rows.append([k, n(v.get("count")), share(v.get("share_of_run_total")), n(v.get("min")),
                     n(v.get("mean")), n(v.get("sd")), n(v.get("p50")), n(v.get("p90")),
                     n(v.get("p95")), n(v.get("p99")), n(v.get("max")), n(v.get("mean_over_p50"), 2),
                     f"{n(occ.get('max'), 0)} / {n(occ.get('mean'), 2)} / {n(occ.get('p50'), 0)} / {n(occ.get('p95'), 0)}"
                     if occ else "—", v.get("timed_from", "")])
    return rows


STAGE_HEAD = ["stage", "count", "share of run total", "min s", "mean s", "sd s", "p50 s", "p90 s",
              "p95 s", "p99 s", "max s", "mean/p50", "occupancy max / mean / p50 / p95", "timed from"]


# ----------------------------------------------------------------------------- sections

def sec_d0(docs: Optional[Dict[str, Any]], v1: Optional[Dict[str, Any]], v2: Optional[Dict[str, Any]],
           F: Dict[str, Any]) -> List[str]:
    out = ["## D0 — instance accounting (every cell)", ""]
    rows, viol = [], []
    dirs = (docs or {}).get("leg_dirs") or {}
    for name, leg in sorted(((docs or {}).get("legs") or {}).items()):
        m = leg.get("mandate") or {}
        name = dirs.get(name, name)
        ext = leg.get("d0_external") or {}
        models = leg.get("d0_models_pre") or {}
        mtxt = "; ".join(f"{k.rsplit('.', 1)[-1]} ×{v.get('distinct_weights')}" for k, v in models.items()) or "—"
        rows.append([name, leg.get("arm"), n(ext.get("task_instances_max")) if leg.get("arm") == "rr" else
                     n(ext.get("li_worker_processes_max")), mtxt,
                     n((leg.get("d0_threads_pre") or {}).get("proc_threads")),
                     n(leg.get("torch_threads_pre")), "VIOLATION" if m.get("mandate_violation") else "ok"])
        if m.get("mandate_violation"):
            viol.append((name, m.get("violations")))
    for stage, a in (("v1", v1), ("v2", v2)):
        for name, leg in sorted(((a or {}).get("legs") or {}).items()):
            p0 = leg.get("p0") or {}
            census = leg.get("task_census") or {}
            models = ((p0.get("d0_pre") or {}).get("root_modules_with_params")) or {}
            mtxt = "; ".join(f"{k.rsplit('.', 1)[-1]} ×{v.get('distinct_weights')}" for k, v in models.items()) or "—"
            mv = (p0.get("mandate") or {})
            cp = leg.get("container_procs") or {}
            def wk(x: Dict[str, Any]) -> str:
                m = re.search(r"--workers (\d+)", ((x.get("leg_start") or {}).get("top_cmd") or ""))
                return f", uvicorn --workers {m.group(1)}" if m else ""
            li_n = "; ".join(f"{c}: {(x.get('leg_start') or {}).get('n')} at start, {(x.get('leg_end') or {}).get('n')} at end{wk(x)}"
                             for c, x in (cp.get("containers") or {}).items())
            li_txt = (f"{li_n} (peak {cp.get('service_peak_process_count')} with transient children)" if li_n
                      else "not measured")
            rows.append([name, "rr" if "_rr_" in name else "li",
                         n(len(census.get("new_task_pids") or [])) if census else li_txt,
                         mtxt, n(((p0.get("d0_pre") or {}).get("proc_threads"))), n(p0.get("torch_num_threads")),
                         "VIOLATION" if mv.get("mandate_violation") else "ok"])
            if mv.get("mandate_violation"):
                viol.append((name, mv.get("violations")))
    out += table(["cell", "arm", "task processes (RR) / worker processes (LI)", "loaded models (distinct weights)",
                  "OS threads in the task", "torch threads", "mandate"], rows)
    F["d0_violations"] = viol
    out.append("**Mandate:** " + ("VIOLATED — " + "; ".join(f"{a}: {b}" for a, b in viol) if viol
                                  else "no cell showed more than one RocketRide task process or more than one loaded instance of a model."))
    out.append("")
    return out


def sec_d1_scope_and_gil(h2: Optional[Dict[str, Any]]) -> List[str]:
    out = ["### What is timed from inside and what from outside", "",
           "- **Inside the pipeline, at node boundaries** (RocketRide stamp nodes adjacent to the stage): "
           "split (LangChain splitter, Python) and embed (MiniLM, Python/torch, including the node's "
           "buffered flush).",
           "- **From outside:** admission (client submit to the engine's pipe open), the parse bracket "
           "(pipe open to the parser's last text — the parse node is native C++ in the engine binary, so it "
           "can only be bracketed; the bracket also holds the upload, the wait for an executor thread and "
           "the engine's handling of the parser's output) and return (the embed node's last documents to "
           "the client's completion).",
           "- **LlamaIndex:** extract (pypdf), split and embed are timed inside the service by three "
           "perf_counter stamps; queue = client latency minus service total.",
           "- **Video (V2):** every component is timed inside the detect code of each arm (instrumented "
           "copies, additions only).", ""]
    rows = []
    for name in ("h2f_c32_a", "h2f_c32_b"):
        ps = (((h2 or {}).get("legs") or {}).get(name) or {}).get("pyspy_gil") or {}
        if ps.get("status") != "OK":
            continue
        bs = ps["by_stage"]
        rows.append([name] + [share((bs.get(k) or {}).get("share")) for k in
                              ("embed", "split", "engine glue (data_conn)", "response", "other")])
    if rows:
        out.append("Share of H2's GIL-holding samples by the stage whose code is on the stack "
                   "(DIAGNOSTIC legs; 'other' is mostly the engine's websocket transport and JSON encoding):")
        out.append("")
        out += table(["leg", "embed (Python stage)", "split (Python stage)", "engine glue", "response node",
                      "other"], rows)
        rule = next((((h2 or {}).get("legs") or {}).get(k, {}).get("pyspy_gil") or {}).get("stage_rule")
                    for k in ((h2 or {}).get("legs") or {}))
        if rule:
            out += [f"Attribution rule: {rule}.", ""]
    return out


def sec_d1(docs: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## D1 — node-level telemetry", "",
           "Every table below is from a **PROFILE** leg (stage stamps or a timed service): shares, "
           "rankings and distributions only; its absolute seconds are never set beside a baseline "
           "figure. Quantiles are nearest-rank; the median is the true median. Share of run total = "
           "the stage's summed seconds over the summed end-to-end latency of the same documents. "
           "Occupancy is time-weighted over the leg's measured window.", ""]
    if not docs:
        return out + ["NOT RUN — no docs analysis.", ""]
    ov = docs.get("d1_overhead") or {}
    rows = []
    for k, v in ov.items():
        rows.append([k, " / ".join(n(x, 4) for x in v["a_docs_per_s"]), " / ".join(n(x, 4) for x in v["b_docs_per_s"]),
                     pct(v["overhead"]), share(v["threshold"], 2), "readable" if v["readable"] else "UNREADABLE (within the threshold)",
                     n(v["same_session"])])
    out.append("### Overhead of the telemetry (same session, ABAB, two runs each; span docs/s from the raw records)")
    out.append("")
    out += table(["cell", "uninstrumented legs", "instrumented legs", "overhead", "threshold = max(floor, both spreads)",
                  "reading", "same session"], rows)
    F["d1_overhead"] = {k: v["overhead"] for k, v in ov.items()}
    nc = docs.get("d1_null_control_chunk_identity") or {}
    out.append(f"**Null control (output identity):** {'PASS' if nc.get('pass') else 'FAIL' if nc.get('pass') is False else 'NOT RUN'} — "
               + "; ".join(f"{p['b']} vs {p['a']} ({p['kind']}): {p['identical']}/{p['compared']} documents chunk-identical"
                           for p in nc.get("pairs", [])) + ".")
    out.append("")
    dirs = docs.get("leg_dirs") or {}
    for alias, t in (docs.get("d1_stages") or {}).items():
        if not alias.startswith(("d1_", "an_")):
            continue
        name = dirs.get(alias, alias)
        if t["arm"] == "rr":
            out.append(f"### {name} — RocketRide stages (PROFILE; {t['docs_with_complete_stamps']} documents with a "
                       f"complete stamp set, {t['docs_incomplete_stamps']} without)")
            out.append("")
            out += table(STAGE_HEAD, stage_rows(t["stages"], ["admission", "parse_bracket", "split", "embed", "return"]))
        else:
            out.append(f"### {name} — LlamaIndex stages, one worker (PROFILE; {t['docs_with_service_stamps']} documents)")
            out.append("")
            out += table(STAGE_HEAD, stage_rows(t["stages"], ["queue", "extract", "svc_split", "svc_embed"]))
    return out


def sec_parity(docs: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## Same-session single-instance docs cell (context for the parity target)", ""]
    p = (docs or {}).get("parity_anchor_same_session")
    if not p:
        return out + ["NOT RUN.", ""]
    out += table(["arm", "legs", "span docs/s", "mean", "spread"],
                 [["LlamaIndex, one worker", ", ".join(p["cell_a"]), " / ".join(n(x, 4) for x in p["a_docs_per_s"]),
                   n(p["a_mean"], 4), share(p["a_spread"], 2)],
                  [f"RocketRide, one token{DAG}", ", ".join(p["cell_b"]), " / ".join(n(x, 4) for x in p["b_docs_per_s"]),
                   n(p["b_mean"], 4), share(p["b_spread"], 2)]])
    out.append(f"RocketRide / LlamaIndex − 1 = **{pct(p['delta_b_vs_a'], 1)}**, threshold {share(p['threshold'], 2)} "
               f"(the larger arm floor) → {'readable' if p['readable'] else 'UNREADABLE'}; 96-document anchor slice, "
               "C=8, six thread variables = 1 on both (RocketRide read back in-process before and after each leg; LlamaIndex as its harness sets them, with no in-process read-back in these legs), same box session.")
    out.append("")
    F["parity_docs"] = p["delta_b_vs_a"]
    return out


def sec_h1(docs: Optional[Dict[str, Any]], src: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## H1 — per-process ceiling (executor width)", ""]
    h = (docs or {}).get("h1") or {}
    rows = []
    dirs = (docs or {}).get("leg_dirs") or {}
    for alias in ("h1_c32_a", "h1_c64_a", "h1_c32_b", "h1_c64_b"):
        x = h.get(alias) or {}
        name = dirs.get(alias, alias)
        if "span" not in x:
            rows.append([name, "NOT RUN", "", "", "", ""])
            continue
        ex, op = x["executing_concurrency"], x["engine_open_concurrency"]
        rows.append([name, n(x["executor_threads_seen"]), f"{n(ex.get('max'), 0)} / {n(ex.get('p95'), 0)}",
                     f"{n(op.get('max'), 0)} / {n(op.get('p95'), 0)}", n(x["span"]["docs_per_s"], 4),
                     ", ".join(x.get("thread_names_seen") or [])])
    out += table(["leg (PROFILE)", "executor threads that ran a document", "executing at once: max / p95",
                  "admitted (pipe open) at once: max / p95", "span docs/s (PROFILE)", "thread names"], rows)
    v = h.get("verdict") or {}
    t = v.get("c64_vs_c32_throughput") or {}
    out.append(f"**H1: {v.get('h1') or 'NOT RUN'}** — rule: {v.get('rule', '')}. C=64 vs C=32 span docs/s "
               f"{pct(t.get('delta_b_vs_a'))} against {share(t.get('threshold'), 2)} → "
               f"{'readable' if t.get('readable') else 'unreadable'} (PROFILE legs, compared only with each other).")
    out.append("")
    s = (src or {}).get("H1_executor_ceiling") or {}
    if s:
        out.append("**SOURCE (not measurement):** " + " ".join(s.get("where_pipe_work_runs", [])))
        out.append("")
        out.append("**What would widen it (SOURCE):** " + s.get("what_would_widen_it", ""))
        out.append("")
        out.append("**What binds next (SOURCE):** " + "; ".join(s.get("what_binds_next", [])) + ".")
        out.append("")
    F["h1"] = v.get("h1")
    return out


def sec_h2(h2: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## H2 — the interpreter lock (DIAGNOSTIC legs)", "",
           "Instrument per **preregistration_amendment_1.json**: bpftrace uprobes on the engine binary's "
           "own `take_gil` / `drop_gil` time waiting and holding per Python thread; py-spy's `--gil` "
           "recorder names the holders. The pre-registered py-spy `--native` recorder is **NOT RUN** "
           "(it aborts on the engine binary with UNW_EBADREG, tooling leg 08:36Z). Per "
           "**amendment 3** the legs h2_null_c1 and h2_c32_a/b are VOID (the tracer never wrote: bpftrace "
           "0.14's stripped BEGIN_trigger; py-spy stopped late); per **amendment 4** every first-generation "
           "RocketRide docs leg carried env_probe's per-document instance scan, so tool_gil2 is PERTURBED "
           "(its trace also has no window: bpftrace 0.14 prints no min() map) and h2b_null_c1 was stopped. "
           "The design is carried by **h2f_null_c1 and h2f_c32_a/b**. Shares are of Python-thread time "
           "(n threads × tracer window).", ""]
    if not h2:
        return out + ["NOT RUN.", ""]
    rows = []
    for name, x in (h2.get("legs") or {}).items():
        g = x.get("gil") or {}
        tag = (" (VOID)" if x.get("void_for_h2") else " (PERTURBED)" if name in ("tool_gil2",) else "")
        if x.get("status") == "NOT RUN" or g.get("status") != "OK":
            rows.append([name + tag, x.get("status") or g.get("status") or "—"] + [""] * 7)
            continue
        rows.append([name + tag, n(g["python_threads"]), share(g["waiting_on_gil"]), share(g["holding_gil"]),
                     share(g["native"]), share(g["idle"]), share(g["gil_occupancy"]),
                     n(g["gil_occupancy"] <= 1.0), n(x.get("engine_cores"), 2)])
    out += table(["leg", "Python threads", "waiting on GIL", "holding GIL", "native (running, lock free)",
                  "idle", "lock occupancy (of wall)", "occupancy ≤ 1", "engine cores (DIAGNOSTIC)"], rows)
    nc, gate = h2.get("null_control") or {}, h2.get("gate") or {}
    out.append(f"**Null control (C=1, one document in flight):** waiting {share(nc.get('waiting_on_gil'), 2)} against "
               f"< {share(nc.get('threshold'), 0)} → {'PASS' if nc.get('pass') else 'FAIL — H2 UNREADABLE'}.")
    out.append("")
    out.append(f"**Gate H2:** threshold waiting ≥ {share(gate.get('threshold'), 0)} (mean of the two C=32 smoke runs); "
               f"measured {share(gate.get('measured'))}; **{'FIRED' if gate.get('fired') else 'not fired'}**"
               + ("" if gate.get("evaluable") else " (NOT EVALUABLE: " + str(gate.get("note")) + ")") + ".")
    out.append("")
    for name in ("h2f_c32_a", "h2f_c32_b", "h2_full_c32"):
        x = (h2.get("legs") or {}).get(name) or {}
        ps = x.get("pyspy_gil") or {}
        if ps.get("status") != "OK":
            continue
        out.append(f"### {name} — the lock's holders, top 10 by share of py-spy `--gil` samples ({ps['samples']:,} samples)")
        out.append("")
        out += table(["function (file)", "share of GIL-holding samples"],
                     [[t["function"], share(t["share"])] for t in ps["top10"]])
        out.append("By stage (attribution rule under D1): " + ", ".join(
            f"{k} {share(v['share'])}" for k, v in ps["by_stage"].items()) + ".")
        out.append("")
    F["h2_gate"] = gate
    return out


def sec_h7(docs: Optional[Dict[str, Any]], src: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## H7 — the debugger attached to every production task (preregistration_amendment_2.json)", ""]
    h = (docs or {}).get("h7")
    s = (src or {}).get("H7_attached_debugger") or {}
    if s:
        out.append("**SOURCE:** " + s.get("launch", "") + "; " + s.get("in_the_task_process", "") + ". " + s.get("sdk", ""))
        out.append("")
    if not h:
        return out + ["NOT RUN.", ""]
    c = h["nodebug_vs_debug"]
    alias = {v: k for k, v in ((docs or {}).get("leg_dirs") or {}).items()}   # f-leg dir -> pre-registered name
    cpu = {k: h["cpu_s_per_doc"].get(alias.get(k, k)) for k in list(c["cell_a"]) + list(c["cell_b"])}
    out += table(["cell", "legs", "span docs/s", "mean", "spread", "CPU-s/doc"],
                 [[f"debugger attached (default){DAG}", ", ".join(c["cell_a"]), " / ".join(n(x, 4) for x in c["a_docs_per_s"]),
                   n(c["a_mean"], 4), share(c["a_spread"], 2),
                   " / ".join(n(cpu.get(k), 4) for k in c["cell_a"])],
                  [f"noDebug launch{DAG}", ", ".join(c["cell_b"]), " / ".join(n(x, 4) for x in c["b_docs_per_s"]),
                   n(c["b_mean"], 4), share(c["b_spread"], 2),
                   " / ".join(n(cpu.get(k), 4) for k in c["cell_b"])]])
    out.append(f"noDebug / default − 1 = **{pct(c['delta_b_vs_a'])}**, threshold {share(c['threshold'], 2)} → "
               f"**{h['verdict']}**. Output identity (null control): {'PASS' if h['null_control_pass'] else 'FAIL'}.")
    out.append("")
    cmds = h.get("task_cmdlines") or {}
    out.append("Mechanism read-back — task command lines: " + "; ".join(
        f"{k}: {'--debug_port present' if any('--debug_port' in x for x in (v or [])) else 'no --debug_port'}"
        for k, v in cmds.items()) + ".")
    tr = h.get("trace_readback") or {}
    out.append("Tracer read-back inside the task (env_probe d0.trace): " + "; ".join(
        f"{k}: gettrace={(v or {}).get('sys_gettrace_this_thread')}, monitoring={(v or {}).get('sys_monitoring_tools')}, "
        f"debugpy loaded={(v or {}).get('debugpy_loaded')}" for k, v in tr.items()) + ".")
    out.append("")
    F["h7"] = h["verdict"]
    return out


def sec_h5(h5: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## H5 — Tika's enabled PDF features and the tail (isolated Tika)", "",
           "The engine's own Tika 3.2.3 jars and bundled JRE (from rr:patched, read-only), one document "
           "per fresh JVM after a warm-up parse, each parse timed inside the JVM; the shipped "
           "tika-config.xml or a copy with ONE PDFParser feature switched off.", ""]
    if not h5:
        return out + ["NOT RUN.", ""]
    rows = []
    for d, x in h5["per_document"].items():
        rows.append([d, n(x["shipped_r1_s"], 1), n(x["shipped_r2_s"], 1), share(x["replicate_spread"]),
                     n(x["shipped_chars_r1"]), n(x["in_engine_hold_s_S5D_context"], 1),
                     n(x["in_engine_over_isolated"], 1)])
    out += table(["document", "shipped s (run 1)", "shipped s (run 2)", "replicate spread", "text chars",
                  "in-engine hold s (S5-D, context)", "in-engine / isolated"], rows)
    rows = []
    for lab, f in h5["per_feature"].items():
        tc = [x["time_change"] for x in f["rows"].values() if x["time_change"] is not None]
        lc = [x["length_change"] for x in f["rows"].values() if x["length_change"] is not None]
        rows.append([f["param"] + " = false", n(f["n_passing"]), share(f["median_time_reduction"]),
                     f"{pct(min(tc)) if tc else '—'} … {pct(max(tc)) if tc else '—'}",
                     f"{pct(min(lc)) if lc else '—'} … {pct(max(lc)) if lc else '—'}",
                     ", ".join(f["docs_passing"]) or "none"])
    out += table(["feature switched off", "documents passing (≥50% faster, length within 5%)",
                  "median time reduction over the 11", "time change range", "text-length change range",
                  "passing documents"], rows)
    g = h5["gate"]
    out.append(f"**Gate H5:** threshold {g['threshold']}; measured per feature {g['n_passing_by_feature']}; "
               f"**{'FIRED — best config ' + str(g['best_config']) if g['fired'] else 'not fired'}**.")
    out.append("")
    F["h5_gate"] = g
    return out


def sec_h6(h6s: Optional[Dict[str, Any]], h6f: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## H6 — parser bake-off (read-only: no node, no pipeline change)", "",
           "PyMuPDF / MuPDF is AGPL-3.0 (or a commercial Artifex licence) — incompatible with shipping "
           "inside MIT-licensed RocketRide — so it was substituted by **pypdfium2** (PDFium, C++; "
           "Apache-2.0 / BSD-3-Clause). pypdf is the LlamaIndex image's version and call.", ""]
    for label, a in (("smoke (the 11 for speed; the 384 slice for coverage)", h6s), ("full corpus, 9,975", h6f)):
        if not a:
            out += [f"### {label}: NOT RUN", ""]
            continue
        out.append(f"### {label}")
        out.append("")
        rows = []
        for p, x in a["parsers"].items():
            t, c = x["tail_11"], x["corpus"]
            rows.append([p, n(t["p50_s"], 3), n(t["speed_ratio_vs_tika_shipped"], 2), n(len(t["timeouts"])),
                         n(c["n"]), n(c["empty"]), n(c["n_loses"]), n(c["n_gains"]),
                         n(len(c["timeouts"])), n(len(c["errors"]))])
        out += table(["parser", "p50 parse s on the 11", "speed vs Tika-as-shipped", "timeouts on the 11",
                      "corpus docs", "empty", "empty where Tika extracts", "extracts where Tika empty",
                      "timeouts", "exceptions"], rows)
        for p, x in a["parsers"].items():
            if x["corpus"]["loses_where_tika_extracts"]:
                out.append(f"- {p} returns empty where Tika extracts: " + ", ".join(x["corpus"]["loses_where_tika_extracts"][:40]))
        out.append("")
        g = a.get("gate") or a.get("verdict") or {}
        out.append(f"**{'Gate H6' if 'gate' in a else 'Verdict'}:** {g.get('rule')}; speed pass {g.get('speed_pass')}; "
                   f"speed and coverage pass {g.get('speed_and_coverage_pass')}"
                   + (f"; **{'FIRED' if g.get('fired') else 'not fired'}**; hybrid branch {n(g.get('hybrid_branch'))}"
                      if 'gate' in a else
                      f" → **{'CANDIDATE: ' + ', '.join(g.get('candidates')) if g.get('candidates') else 'NO CANDIDATE'}**"
                      + ("" if g.get("candidates") else " (pre-registered consequence: the hybrid shape the data "
                         "supports is a P1 recommendation, not built in P0)")) + ".")
        out.append("")
        if "gate" not in a:
            # the pre-registered full report: (a) the D1 metric set per parser, corpus-wide and on the 11; (d) failures named
            for scope, key in (("the whole corpus", "corpus"), ("the 11", "tail_11")):
                out.append(f"Parse seconds per document, {scope} (D1 metric set; nearest-rank quantiles):")
                out.append("")
                mrows = []
                for p, x in a["parsers"].items():
                    m = x[key].get("metric_set_s") or {}
                    mrows.append([p, n(m.get("count")), n(m.get("sum"), 1), n(m.get("min")), n(m.get("mean")),
                                  n(m.get("sd")), n(m.get("p50")), n(m.get("p90")), n(m.get("p95")),
                                  n(m.get("p99")), n(m.get("max")), n(m.get("mean_over_p50"), 2)])
                out += table(["parser", "count", "sum s", "min s", "mean s", "sd s", "p50 s", "p90 s", "p95 s",
                              "p99 s", "max s", "mean/p50"], mrows)
            for p, x in a["parsers"].items():
                errs = x["corpus"].get("errors") or {}
                if errs:
                    out.append(f"- {p} exceptions ({len(errs)}): " + "; ".join(
                        f"{d}: {str(e)[:90]}" for d, e in sorted(errs.items())[:20]))
            out.append("")
            hy = a.get("hybrid_candidate_first_tika_on_empty") or {}
            if hy:
                out.append("The hybrid shape (candidate first, Tika-as-shipped on the candidate's empty), computed from "
                           "the same full-run records (isolated parse seconds, 12 workers):")
                out.append("")
                out += table(["candidate", "documents", "fallbacks to Tika", "documents with text (hybrid)",
                              "documents with text (Tika alone)", "parse s (hybrid)", "parse s (Tika alone)"],
                             [[c, n(x["docs"]), n(x["fallbacks"]), n(x["covered"]), n(x["tika_covered"]),
                               n(x["cost_s"], 1), n(x["tika_cost_s"], 1)] for c, x in hy.items()])
            ts, tf = ((h6s or {}).get("parsers") or {}).get("tika_shipped"), (a["parsers"].get("tika_shipped") or {})
            if ts and tf:
                out.append(f"**Disclosure:** Tika-as-shipped's p50 on the 11 was {n(ts['tail_11']['p50_s'])} s in the smoke and "
                           f"{n(tf['tail_11']['p50_s'])} s in the full run; the other parsers' p50s on the 11 moved little "
                           "(tables above). The smoke parsed each of the 11 on its own JVM after one warm-up document; the "
                           "full run parsed them on JVMs that had already parsed hundreds of documents. JIT warm-up is the "
                           "likely reason; it was not measured separately. The smoke gate fired on the cold figure; the "
                           "pre-registered full run decides the verdict.")
                out.append("")
        fd = a.get("fidelity_vs_tika_shipped") or {}
        if fd:
            out += table(["candidate", "char ratio p5 / p50 / p95", "Dice p5 / p50 / p95", "min Dice", "missing"],
                         [[c, f"{n(v['char_ratio'].get('p5'), 3)} / {n(v['char_ratio'].get('p50'), 3)} / {n(v['char_ratio'].get('p95'), 3)}",
                           f"{n(v['dice'].get('p5'), 3)} / {n(v['dice'].get('p50'), 3)} / {n(v['dice'].get('p95'), 3)}",
                           n(v['dice'].get('min'), 3), n(v['missing'])] for c, v in fd.items()])
    F["h6"] = {"smoke": (h6s or {}).get("gate"), "full": (h6f or {}).get("verdict")}
    return out


def sec_v1(v1: Optional[Dict[str, Any]], v1f: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## V1 — matched single instance (video)", "",
           "One RocketRide token on rr:patched-video vs ONE LlamaIndex li_video instance (one worker), "
           "16-video slice, K=16 in flight, fresh container per leg, same session, ABAB. frames/s = the "
           "export's total frames / its leg wall (the definition of every banked video figure).", ""]
    if not v1:
        return out + ["NOT RUN.", ""]
    c = v1.get("cells") or {}
    rows = []
    for k, lab in (("rr_t4", "RocketRide one token, six vars = 4"), ("li_t4", "LlamaIndex one instance, six vars = 4"),
                   ("rr_default", "RocketRide default (vars unset, torch 16) — reference")):
        x = c.get(k)
        if not x:
            rows.append([lab, "NOT RUN", "", "", "", ""])
            continue
        rows.append([lab, ", ".join(x["legs"]), " / ".join(n(v, 3) for v in x["frames_per_s"]), n(x["mean"], 3),
                     share(x["spread"], 2), " / ".join(n(v, 3) for v in x["cpu_s_per_frame"]) + " ; cores " +
                     " / ".join(n(v, 2) for v in x["engine_cores"])])
    out += table(["cell", "legs", "frames/s", "mean", "spread", "CPU-s per frame ; engine cores"], rows)
    g = v1.get("gap") or {}
    out.append(f"**Gate V1:** LlamaIndex / RocketRide − 1 at T=4 = {pct(g.get('li_over_rr_minus_1'), 1)}; threshold "
               f"max(0.82%, spreads) = {share(g.get('threshold'), 2)}; margin {pts(g.get('margin_pp'), 1)} against "
               f"≥ +10 points → **{'FIRED' if g.get('gate_fired') else 'not fired'}**.")
    out.append("")
    for k in ("rr_t4_determinism", "rr_default_determinism", "rr_t4_vs_default_output"):
        x = v1.get(k)
        if x:
            out.append(f"- Output, {k}: {x['videos_compared']} videos, identical = {n(x['identical'])} "
                       f"(chunk-hash differences {len(x['chunk_hash_differs'])}, frame-score differences {len(x['frame_scores_differ'])}).")
    out.append("- Correctness note carried from S5-A: only T=16/unset reproduces default output bit-for-bit; every "
               "other T shifts scores while keeping labels, so no T is recommended on speed alone.")
    out.append("")
    if v1f:
        c = v1f.get("cells") or {}
        out.append("### 168-video confirmation")
        out += table(["cell", "frames/s"], [[k, " / ".join(n(v, 3) for v in (x or {}).get("frames_per_s", []))]
                                            for k, x in c.items() if x])
    F["v1_gap"] = g
    return out


def v2_reading(v2: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The pre-registered V2 reading from the stamped legs: forward-pass time per frame by arm (mean
    over each arm's stamped legs), their difference against max(0.82%, each arm's leg-to-leg spread
    of that mean), the in-lock time that is not the forward pass, and the forward pass's share of the
    lock hold. The pre-registration names no tolerance for 'equal'; the committed video floor and the
    spreads are used and printed beside the difference."""
    def arm(key: str) -> Dict[str, Any]:
        fw, held, nf, fsh, fps = [], [], [], [], []
        for leg, x in ((v2 or {}).get(key) or {}).items():
            c = x.get("components") or {}
            if not (c.get("forward") and c.get("lock_held") and x.get("frames")):
                continue
            fw.append(c["forward"]["mean"]); held.append(c["lock_held"]["mean"])
            nf.append((c["lock_held"]["sum"] - c["forward"]["sum"]) / c["forward"]["count"])
            fsh.append(c["forward"]["sum"] / c["lock_held"]["sum"])
            fps.append((((v2 or {}).get("legs") or {}).get(leg) or {}).get("frames_per_s"))
        if not fw:
            return {}
        m = lambda v: sum(v) / len(v)
        sp = abs(fw[0] - fw[1]) / ((fw[0] + fw[1]) / 2) if len(fw) == 2 else None
        return {"legs": len(fw), "forward_mean_s": m(fw), "forward_spread": sp, "lock_held_mean_s": m(held),
                "in_lock_not_forward_s": m(nf), "forward_share_of_hold": m(fsh),
                "fps_implied_by_hold": 1 / m(held),
                "fps_measured": m(fps) if fps and all(x is not None for x in fps) else None}
    rr, li = arm("rr_components"), arm("li_components")
    if not (rr and li):
        return {"rr": rr, "li": li, "reading": None}
    d = rr["forward_mean_s"] / li["forward_mean_s"] - 1
    tol = max([0.0082] + [x for x in (rr["forward_spread"], li["forward_spread"]) if x is not None])
    dh = rr["lock_held_mean_s"] / li["lock_held_mean_s"] - 1
    if abs(d) > tol:
        reading = ("UNEQUAL forward-pass time at equal T: a model-runtime configuration difference "
                   "(pre-registered reading), named from both images under 'runtime versions'")
    elif dh > tol:
        reading = "equal forward-pass time with a larger lock-held total: overhead inside the lock (in scope)"
    else:
        reading = "equal forward-pass time and equal lock-held total"
    return {"rr": rr, "li": li, "forward_rr_over_li_minus_1": d, "lock_held_rr_over_li_minus_1": dh,
            "tolerance": tol, "reading": reading}


def v2_posthoc_cores(v2: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("rr_components", "li_components"):
        for leg, x in ((v2 or {}).get(key) or {}).items():
            L = ((v2 or {}).get("legs") or {}).get(leg) or {}
            held = ((x.get("components") or {}).get("lock_held") or {}).get("sum")
            idle = (L.get("idle_burden") or {}).get("idle_cores_with_instances_live")
            if not (held and L.get("service_cpu_s") and L.get("span_s") and L.get("frames") and idle is not None):
                continue
            work = L["service_cpu_s"] - idle * L["span_s"]
            out[leg] = {"cpu_s_per_frame": L["service_cpu_s"] / L["frames"], "idle_cores": idle,
                        "work_cpu_s_per_frame": work / L["frames"], "cores_during_hold": work / held}
    return out


def sec_runtime_versions(camp: Path, F: Dict[str, Any]) -> List[str]:
    """V2's naming step: the read-only listing of each image (runtime_versions/<image>.txt)."""
    d = camp / "runtime_versions"
    out = ["### Runtime versions (V2's naming step; read-only listing of each image)", ""]
    if not d.is_dir():
        return out + ["NOT RUN.", ""]
    def facts(f: Path) -> Dict[str, Any]:
        L = f.read_text(errors="replace").splitlines()
        return {"version_lines": sorted({l.strip() for l in L if l.startswith(("__version__", "git_version"))}),
                "dist": sorted({l.split("/")[-1] for l in L if l.startswith("== dist-info:")}),
                "libs": sorted({l.split("/")[-1] for l in L if l.startswith("== lib:")})}
    a, b = d / "rr_patched_video.txt", d / "li_video.txt"
    if a.exists() and b.exists():
        fa, fb = facts(a), facts(b)
        same = {k: fa[k] == fb[k] for k in fa}
        out.append(f"**The two video images (rr:patched-video vs li:video):** torch version and git hash identical: "
                   f"{n(same['version_lines'])}; torch / torchvision / rfdetr / transformers / numpy dist-info identical: "
                   f"{n(same['dist'])}; torch-bundled math libraries identical: {n(same['libs'])}. Both arms build the "
                   "detector as RFDETRBase() with defaults and call predict(image, threshold) on a PIL RGB image "
                   "(RocketRide engine/ai/common/models/vision/detection.py:138 and :172, same bundle basis as V3; "
                   "LlamaIndex working/video/li_video/pipeline.py:141 and :215), so dtype and input size follow the "
                   "same library defaults (SOURCE, not measured).")
        out.append("")
        F["runtime_versions_video_identical"] = same
    for f in sorted(d.glob("*.txt")):
        INPUTS[f"runtime_versions/{f.name}"] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        lines = f.read_text(errors="replace").splitlines()
        ver = [l.strip() for l in lines if l.strip().split(" ")[0] in ("__version__", "git_version", "cuda", "cuda:", "hip", "hip:", "debug")
               or l.startswith("__version__") or l.startswith("git_version")]
        dist = sorted({l.split("/")[-1] for l in lines if l.startswith("== dist-info:")})
        libs = sorted({l.split("/")[-1] for l in lines if l.startswith("== lib:")})
        flags = next((lines[i + 1].strip() for i, l in enumerate(lines) if l.startswith("== cpu flags") and i + 1 < len(lines)), "")
        out.append(f"- **{f.stem}**: torch version file {'; '.join(dict.fromkeys(ver)) or '—'}; "
                   f"dist-info {', '.join(dist) or '—'}; torch-bundled math libraries {', '.join(libs) or 'none'}; "
                   f"CPU flags seen {flags or '—'}")
    out.append("")
    out.append("The docs images are listed as context (V2 concerns video); where the listing found no torch "
               "version file in an image, the row shows —.")
    return out + [""]


def sec_v2(v2: Optional[Dict[str, Any]], src: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## V2 — duty cycle and per-frame decomposition (PROFILE, T=4)", ""]
    if not v2:
        return out + ["NOT RUN.", ""]
    nc = v2.get("null_control") or {}
    if nc:
        st, un = nc.get("stamped") or {}, nc.get("unstamped") or {}
        out.append(f"**Null control:** stamped {', '.join(n(x) for x in st.get('frames_per_s') or [])} vs unstamped "
                   f"{', '.join(n(x) for x in un.get('frames_per_s') or [])} frames/s (pairs a, b; spreads "
                   f"{share(st.get('spread'), 2)} / {share(un.get('spread'), 2)}): "
                   f"stamped vs unstamped RocketRide frames/s {pct(nc.get('delta'))} against "
                   f"{share(nc.get('threshold'), 2)}; output identical {[x['identical'] for x in nc.get('output_identity', [])]} "
                   f"→ **{'PASS' if nc.get('pass') else 'FAIL — V2 UNREADABLE'}**.")
        out.append("")
    r = v2_reading(v2)
    F["v2_reading"] = r
    if r.get("reading"):
        out.append(f"**Reading (pre-registered rule):** forward pass per frame RocketRide {n(r['rr']['forward_mean_s'])} s vs "
                   f"LlamaIndex {n(r['li']['forward_mean_s'])} s → {pct(r['forward_rr_over_li_minus_1'], 1)} against "
                   f"max(0.82%, each arm's leg-to-leg spread of that mean) = {share(r['tolerance'], 2)}; lock held per frame "
                   f"{n(r['rr']['lock_held_mean_s'])} s vs {n(r['li']['lock_held_mean_s'])} s; in-lock time that is not the "
                   f"forward pass {n(1000 * r['rr']['in_lock_not_forward_s'], 1)} ms vs {n(1000 * r['li']['in_lock_not_forward_s'], 1)} ms "
                   f"per frame; the forward pass is {share(r['rr']['forward_share_of_hold'])} / {share(r['li']['forward_share_of_hold'])} "
                   f"of the lock hold → **{r['reading']}**. (Legs per arm: {r['rr']['legs']} / {r['li']['legs']}.)")
        out.append("")
        out.append(f"Frames/s implied by the lock hold alone (1 / mean hold): RocketRide {n(r['rr']['fps_implied_by_hold'])} vs "
                   f"measured {n(r['rr']['fps_measured'])}; LlamaIndex {n(r['li']['fps_implied_by_hold'])} vs measured "
                   f"{n(r['li']['fps_measured'])} (stamped legs, export frames / leg wall).")
        out.append("")
        out.append("With the lock held for nearly the whole window, each arm's frames/s is set by its lock hold per "
                   "frame, not by the frames queued behind it; 'share of run total' below sums every frame's queueing "
                   "behind the lock into the denominator (pre-registered D1 metric set), so the in-lock components' "
                   "shares of the lock hold are the ones that bound throughput here.")
        out.append("")
    ph = v2_posthoc_cores(v2)
    F["v2_posthoc_cores"] = ph
    if ph:
        out.append("**POST-HOC (not pre-registered; never used by a verdict).** Work CPU per frame net of the "
                   "engine's idle spin = (service CPU − idle cores measured with the instance live before any work × "
                   "leg wall) / frames; cores busy during the hold = that work / Σ lock held. It assumes the idle "
                   "spin continues unchanged during work.")
        out.append("")
        out += table(["leg", "CPU-s per frame (gross)", "idle cores (instance live, before work)",
                      "work CPU-s per frame (net)", "cores busy during the lock hold"],
                     [[k, n(x["cpu_s_per_frame"]), n(x["idle_cores"]), n(x["work_cpu_s_per_frame"]),
                       n(x["cores_during_hold"], 2)] for k, x in ph.items()])
    for arm, key, order in (("RocketRide", "rr_components", ["decode", "lock_wait", "resize", "preprocess", "predict_pre",
                                                               "forward", "predict_post", "dict_build", "loader_post",
                                                               "rescale", "inside_other", "lock_held", "emit"]),
                            ("LlamaIndex", "li_components", ["load_decode", "predict_pre", "forward", "predict_post",
                                                              "dict_build", "format", "lock_held"])):
        for leg, x in (v2.get(key) or {}).items():
            if x.get("status") == "NO STAMPS":
                out.append(f"- {arm} {leg}: NO STAMPS")
                continue
            out.append(f"### {arm} {leg} — duty cycle {share(x.get('duty_cycle'))} of the window "
                       f"({x.get('frames')} frames; forward hooks fired on {x.get('forward_hooks_fired')})")
            out.append("")
            out += table(STAGE_HEAD[:12], [r[:12] for r in stage_rows(x["components"], order)])
    return out


def sec_gates(F: Dict[str, Any]) -> List[str]:
    rows = []
    g = F.get("h2_gate") or {}
    rows.append(["H2 (full 9,975 profile)", "waiting on GIL ≥ 15% (mean of 2 smoke runs)", share(g.get("measured")),
                 "FIRED" if g.get("fired") else ("not fired" if g.get("evaluable") else "NOT EVALUABLE")])
    g = F.get("h5_gate") or {}
    rows.append(["H5 (384-slice sweep at best config)", "one feature ≥50% faster on ≥6 of 11, length within 5%",
                 " / ".join(f"{k.replace('h5_no_', '')} {v}" for k, v in (g.get("n_passing_by_feature") or {}).items())
                 + " documents passing", "FIRED" if g.get("fired") else "not fired" if g else "NOT RUN"])
    g = ((F.get("h6") or {}).get("smoke")) or {}
    rows.append(["H6 smoke gate (→ the full 9,975 bake-off)", "≥2x Tika p50 on the 11 AND no coverage loss on 384",
                 f"speed pass {g.get('speed_pass')}; both {g.get('speed_and_coverage_pass')}",
                 "FIRED" if g.get("fired") else ("hybrid branch" if g.get("hybrid_branch") else "not fired") if g else "NOT RUN"])
    g = F.get("v1_gap") or {}
    rows.append(["V1 (168-video confirmation)", "gap − max(0.82%, spreads) ≥ +10 points", pts(g.get("margin_pp"), 1),
                 "FIRED" if g.get("gate_fired") else "not fired" if g else "NOT RUN"])
    return ["## Gates", ""] + table(["gate", "threshold", "measured", "outcome"], rows)


def sec_v3(src: Optional[Dict[str, Any]]) -> List[str]:
    s = (src or {}).get("V3_lock_scope") or {}
    if not s:
        return ["## V3 — lock scope (SOURCE)", "", "NOT RUN.", ""]
    out = ["## V3 — lock scope (SOURCE, not measurement)", ""]
    for arm in ("rocketride", "llamaindex"):
        a = s[arm]
        out.append(f"**{arm}.** Lock: {a['lock']}. Held around: {a['held_around']}.")
        out.append("")
        out.append("Inside the lock and not the forward pass:")
        out += [f"- {x}" for x in a["inside_the_lock_not_the_forward_pass"]]
        out.append("")
        out.append("Outside the lock: " + "; ".join(a["outside_the_lock"]) + ".")
        out.append("")
    out.append("In-bounds candidates (one model instance, threads only): ")
    out += [f"- {x}" for x in s["in_bounds_fix_candidates"]]
    out.append("")
    return out


def sec_verdicts(A: Dict[str, Any], summ: Dict[str, Any]) -> List[str]:
    """Every number in this table is read from an analysis file; the reading text is summary_spec's."""
    d, h2, h5, h6s, h6f, v1, v2, e1 = (A.get(k) or {} for k in ("docs", "h2", "h5", "h6s", "h6f", "v1", "v2", "e1"))
    notes = (summ or {}).get("readings") or {}
    rows = []
    viol = [n for n, l in (d.get("legs") or {}).items() if (l.get("mandate") or {}).get("mandate_violation")]
    nv = sum(len((x or {}).get("legs") or {}) for x in (v1, v2))
    viol += [n for x in (v1, v2) for n, l in ((x or {}).get("legs") or {}).items()
             if ((l.get("p0") or {}).get("mandate") or {}).get("mandate_violation")]
    rows.append(["D0 (mandate)", "no violation" if not viol else "VIOLATION", f"{len(d.get('legs') or {})} docs cells and {nv} video cells checked"
                 + (f"; violations {viol}" if viol else ""), notes.get("D0", "")])
    ov = d.get("d1_overhead") or {}
    nc = (d.get("d1_null_control_chunk_identity") or {}).get("pass")
    rows.append(["D1 (telemetry)", "overhead unreadable" if ov and not any(v["readable"] for v in ov.values()) else "see D1",
                 "; ".join(f"{k} {pct(v['overhead'])} vs {share(v['threshold'], 2)}" for k, v in ov.items())
                 + f"; output identity {'PASS' if nc else 'FAIL'}", notes.get("D1", "")])
    h1v = ((d.get("h1") or {}).get("verdict") or {})
    t = h1v.get("c64_vs_c32_throughput") or {}
    widths = sorted({(d.get("h1") or {}).get(k, {}).get("executor_threads_seen") for k in ("h1_c64_a", "h1_c64_b")} - {None})
    ex = [((d.get("h1") or {}).get(k, {}).get("executing_concurrency") or {}).get("max") for k in ("h1_c64_a", "h1_c64_b")]
    rows.append(["H1 (per-process ceiling)", h1v.get("h1") or "NOT RUN",
                 f"executor threads at C=64: {', '.join(str(w) for w in widths) or '—'}; executing at once max "
                 f"{', '.join(str(x) for x in ex if x is not None) or '—'}; C=64 vs C=32 {pct(t.get('delta_b_vs_a'))} vs "
                 f"{share(t.get('threshold'), 2)}", notes.get("H1", "")])
    g = h2.get("gate") or {}
    rows.append(["H2 (interpreter lock)", "NOT SUPPORTED" if g.get("evaluable") and not g.get("fired") else ("SUPPORTED" if g.get("fired") else "UNREADABLE"),
                 f"GIL waiting {share(g.get('measured'))} vs gate 15%; null control {share((h2.get('null_control') or {}).get('waiting_on_gil'), 2)} vs < 2%",
                 notes.get("H2", "")])
    h7 = d.get("h7") or {}
    c7 = h7.get("nodebug_vs_debug") or {}
    rows.append(["H7 (attached debugger, amendment 2)", h7.get("verdict", "NOT RUN"),
                 f"noDebug vs default {pct(c7.get('delta_b_vs_a'))} vs {share(c7.get('threshold'), 2)}", notes.get("H7", "")])
    g5 = h5.get("gate") or {}
    iso = [x["in_engine_over_isolated"] for x in (h5.get("per_document") or {}).values() if x.get("in_engine_over_isolated")]
    rows.append(["H5 (Tika features)", "NOT SUPPORTED" if g5 and not g5.get("fired") else ("SUPPORTED" if g5.get("fired") else "NOT RUN"),
                 f"documents passing per feature {list((g5.get('n_passing_by_feature') or {}).values())} (gate: ≥ 6 of 11); in-engine holds {n(min(iso), 0) if iso else '—'}x–{n(max(iso), 0) if iso else '—'}x isolated Tika",
                 notes.get("H5", "")])
    pe = e1.get("per_document") or {}
    cen = e1.get("exec_census_box_wide") or {}
    rows.append(["E1 (where the hold lives, amendment 5)", "EXPLORATORY",
                 f"engine --tika {n(min((x['engine_tika_s'] for x in pe.values() if x.get('engine_tika_s')), default=None), 0)}–"
                 f"{n(max((x['engine_tika_s'] for x in pe.values() if x.get('engine_tika_s')), default=None), 0)} s; "
                 f"jspawnhelper execs {n(cen.get('/opt/rocketride/engine/java/jre/lib/jspawnhelper'))}", notes.get("E1", "")])
    g6 = h6s.get("gate") or {}
    v6 = h6f.get("verdict") or {}
    sp = ((h6s.get("parsers") or {}).get("pypdfium2") or {}).get("tail_11") or {}
    rows.append(["H6 (parser bake-off)", ("CANDIDATE: " + ", ".join(v6.get("candidates") or [])) if v6.get("candidates") else
                 ("full run: no candidate" if h6f else ("smoke gate FIRED" if g6.get("fired") else "not fired")),
                 (f"smoke: pypdfium2 {n(sp.get('speed_ratio_vs_tika_shipped'), 2)}x Tika-as-shipped at p50 on the 11"
                  + "".join(f"; full: {p} {n(((x.get('tail_11') or {}).get('speed_ratio_vs_tika_shipped')), 2)}x at p50 on the 11, "
                            f"loses {n((x.get('corpus') or {}).get('n_loses'))} of the documents Tika extracts "
                            f"({n((x.get('corpus') or {}).get('empty'))} empty of {n((x.get('corpus') or {}).get('n'))})"
                            for p, x in sorted((h6f.get("parsers") or {}).items()) if p != "tika_shipped")),
                 notes.get("H6", "")])
    gp = v1.get("gap") or {}
    rows.append(["V1 (matched single instance)", ("SUPPORTED — gate fired" if gp.get("gate_fired") else "see V1") if gp else "NOT RUN",
                 f"LlamaIndex / RocketRide − 1 at T=4 {pct(gp.get('li_over_rr_minus_1'), 1)}; margin {pts(gp.get('margin_pp'), 1)} vs +10 points",
                 notes.get("V1", "")])
    nc2 = (v2.get("null_control") or {})
    r2 = v2_reading(v2) if v2 else {}
    duty = "; ".join(f"{k}: duty {share(x.get('duty_cycle'))}" for k, x in list((v2.get("rr_components") or {}).items())
                     + list((v2.get("li_components") or {}).items()))
    if r2.get("reading"):
        duty = (f"forward pass per frame RR {n(r2['rr']['forward_mean_s'])} s vs LI {n(r2['li']['forward_mean_s'])} s "
                f"({pct(r2['forward_rr_over_li_minus_1'], 1)} vs {share(r2['tolerance'], 2)}); in-lock non-forward "
                f"{n(1000 * r2['rr']['in_lock_not_forward_s'], 1)} / {n(1000 * r2['li']['in_lock_not_forward_s'], 1)} ms per frame; " + duty)
    verdict = "NOT RUN"
    if nc2:
        rd = r2.get("reading") or ""
        # the pre-registered hypothesis: the gap lies in the work AROUND the forward pass, not in it
        verdict = ("UNREADABLE (null control)" if not nc2.get("pass") else
                   "NOT SUPPORTED — unequal forward-pass time at equal T" if rd.startswith("UNEQUAL") else
                   "SUPPORTED — overhead inside the lock" if rd.startswith("equal forward-pass time with a larger") else
                   "NOT SUPPORTED — equal forward pass and equal hold" if rd else "null control PASS")
    rows.append(["V2 (duty cycle)", verdict, duty, notes.get("V2", "")])
    rows.append(["V3 (lock scope)", "SOURCE", "see V3", notes.get("V3", "")])
    return ["## Verdicts", ""] + table(["hypothesis", "verdict", "measured (from the analysis files)", "reading"], rows)


def roi_table(items: List[Dict[str, Any]]) -> List[str]:
    rank = {"CONFIG": 0, "THREADING": 0, "PYTHON": 1, "CPP": 2}
    items = sorted(items, key=lambda x: (rank.get(x["scope"], 9), -(x.get("share") or 0)))
    rows, below = [], []
    for i, x in enumerate(items, 1):
        sh = x.get("share")
        ceiling = (1 / (1 - sh)) if (sh is not None and sh < 1) else None
        if x["scope"] == "CPP" and (sh is None or sh <= 0.15):
            below.append(x)
            continue
        rows.append([str(i), x["bottleneck"], x["fix"], share(sh) if sh is not None else x.get("share_note", "—"),
                     (f"{ceiling:.2f}x" if ceiling else "—"), x["scope"], x.get("evidence", "")])
    out = table(["rank", "bottleneck", "in-bounds single-instance fix", "(a) share of run total (D1)",
                 "(b) ceiling if the stage cost zero = 1/(1 − share)", "(c) scope", "evidence"], rows)
    if below:
        out.append("Measured but not worth rewriting (CPP scope at or below 15% of run total): " +
                   "; ".join(f"{x['bottleneck']} ({share(x.get('share'))})" for x in below) + ".")
        out.append("")
    return out


def sec_session(docs: Optional[Dict[str, Any]], F: Dict[str, Any], vids: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    legs = (docs or {}).get("legs") or {}
    vl = [l for a in (vids or []) if a for l in (a.get("legs") or {}).values()]
    boots = sorted({v.get("boot_id") for v in legs.values() if v.get("boot_id")})
    steal = [((v.get("steal") or {}).get("share")) for v in legs.values() if (v.get("steal") or {}).get("share") is not None]
    mhz = [((v.get("mhz") or {}).get("mean_of_samples")) for v in legs.values() if (v.get("mhz") or {}).get("mean_of_samples")]
    models = sorted({m for v in legs.values() for m in (v.get("cpu_model") or [])})
    boots = sorted(set(boots) | {l.get("boot_id") for l in vl if l.get("boot_id")})
    steal += [(l.get("session") or {}).get("steal_share") for l in vl if (l.get("session") or {}).get("steal_share") is not None]
    F["sessions"] = boots
    return ["## Session", "",
            f"Box sessions seen across the docs and video legs: {', '.join(boots) or '—'} (every comparison above is inside one). "
            f"CPU: {', '.join(models) or '—'}. Steal over the windows: max {share(max(steal), 3) if steal else '—'}. "
            f"Mean core MHz per leg: {n(min(mhz), 0) if mhz else '—'} to {n(max(mhz), 0) if mhz else '—'}. "
            "IMDS placement is recorded per export (host-id is exposed only on dedicated hosts).", ""]


def resolve_share(spec: str, A: Dict[str, Any]) -> Optional[float]:
    """'docs:<leg>+<leg>:<stage>' -> mean share_of_run_total over those PROFILE legs;
    'v2:<leg>+<leg>:<component>' -> mean component share; 'none' -> None."""
    if not spec or spec == "none":
        return None
    src, legs, comp = spec.split(":")
    vals = []
    for leg in legs.split("+"):
        if src == "docs":
            st = (((A.get("docs") or {}).get("d1_stages") or {}).get(leg) or {}).get("stages") or {}
        else:
            v2 = A.get("v2") or {}
            st = ((v2.get("rr_components") or {}).get(leg) or (v2.get("li_components") or {}).get(leg) or {}).get("components") or {}
        parts = [(st.get(c) or {}).get("share_of_run_total") for c in comp.split("|")]
        if parts and all(x is not None for x in parts):
            vals.append(sum(parts))              # 'a|b|c' sums several components of one leg
    return sum(vals) / len(vals) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    a = ap.parse_args()
    c = a.campaign
    A = {"docs": load(c, "analysis_docs_p0.json"), "docs_g1": load(c, "analysis_docs_p0_gen1.json"),
         "e1": load(c, "analysis_e1.json"), "h2": load(c, "analysis_h2.json"),
         "h5": load(c, "analysis_h5.json"), "h6s": load(c, "analysis_h6smoke.json"),
         "h6f": load(c, "analysis_h6full.json"), "v1": load(c, "analysis_v1.json"),
         "v1f": load(c, "analysis_v1full.json"), "v2": load(c, "analysis_v2.json"),
         "src": load(c, "source_traces.json"), "roi": load(c, "roi_spec.json"),
         "summary": load(c, "summary_spec.json")}
    F: Dict[str, Any] = {}
    body: List[str] = []
    body += sec_d0(A["docs"], A["v1"], A["v2"], F)
    body += sec_d1(A["docs"], F)
    body += sec_d1_scope_and_gil(A["h2"])
    body += sec_perturbation(A["docs_g1"], A["docs"], F)
    body += sec_parity(A["docs"], F)
    body += sec_posthoc(A["docs"], A["h2"], F)
    body += sec_h2(A["h2"], F)
    body += sec_h1(A["docs"], A["src"], F)
    body += sec_h7(A["docs"], A["src"], F)
    body += sec_h5(A["h5"], F)
    body += sec_e1(A["e1"])
    body += sec_h6(A["h6s"], A["h6f"], F)
    g6 = load(c, "h6_gate.json")
    if g6:
        body += [f"**Harness disclosure (h6_gate.json):** {g6.get('disclosure')}", ""]
    body += sec_v1(A["v1"], A["v1f"], F)
    body += sec_v2(A["v2"], A["src"], F)
    body += sec_runtime_versions(c, F)
    body += sec_v3(A["src"])
    body += sec_amendments(c)
    head = [f"# P0 — diagnosis under the single-instance mandate", "",
            f"Campaign `{c.name}`, branch feat/parity-p0 (cut from the closeout head 5f4fc02). Generated "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from committed analysis files; every figure is "
            "computed from raw per-document / per-frame / per-parse records and rounded only here.", "",
            f"{DAG} on every RocketRide docs throughput figure: {CAVEAT}.", ""]
    summ = A["summary"] or {}
    head += sec_verdicts(A, summ)
    head += sec_gates(F)
    roi = A["roi"] or {}
    if roi:
        items = [dict(x, share=resolve_share(x.get("share_from", "none"), A)) for x in roi.get("items", [])]
        head += ["## Bottlenecks and in-bounds fixes, ranked by ROI (scope first, then share)", "",
                 "(a) is the mean share of run total over the two PROFILE legs that carry the stage: "
                 "d1f_rr_s1/s2 (384 slice, C=32) for docs items, the two stamped RocketRide V2 legs "
                 "for video items. (b) is the per-document (per-frame) time bound if that stage cost "
                 "nothing. A CPP item is proposed only above 15% of run total. For video items the run total "
                 "includes every frame's queueing behind a lock held nearly the whole window, so (a) and (b) are "
                 "small for in-lock work; V2 gives the lock-hold basis that bounds video throughput (the forward "
                 "pass is nearly all of the hold, and 1/hold matches the measured frames/s).", ""] + roi_table(items)
        if roi.get("context_items"):
            head += ["### Not a separate bottleneck (shown with the pre-registered columns, not ranked)", ""]
            for x in roi["context_items"]:
                sh = resolve_share(x.get("share_from", "none"), A)
                head.append(f"- {x['bottleneck']}: (a) {share(sh)} of run total, (b) by the pre-registered rule "
                            f"{n(1 / (1 - sh), 2) + 'x' if sh is not None and sh < 1 else '—'} — {x['why']}")
            head.append("")
        if roi.get("measured_no_readable_effect"):
            head += ["### Measured, with no readable effect", ""] + [f"- {x}" for x in roi["measured_no_readable_effect"]] + [""]
        if roi.get("measured_source_not_traced"):
            head += ["### Measured, source not traced", ""] + [f"- {x}" for x in roi["measured_source_not_traced"]] + [""]
        head += ["### Out of bounds (recorded, not proposed)", ""] + [f"- {x}" for x in roi.get("out_of_bounds", [])] + [""]
        head += ["### NOT RUN", ""] + [f"- {x}" for x in roi.get("not_run", [])] + [""]
    tail = sec_session(A["docs"], F, [A["v1"], A["v2"], A["v1f"]])
    if summ.get("self_audit"):
        tail += ["## SELF-AUDIT", ""] + [f"- **{k}:** {v}" for k, v in summ["self_audit"].items()] + [""]
    md = "\n".join(head + body + tail) + "\n"
    a.out_md.write_text(md)
    a.out_json.write_text(json.dumps({"inputs_sha256_16": INPUTS, "figures": F}, indent=1, default=str))
    print(f"wrote {a.out_md} and {a.out_json}")
    return 0



def sec_perturbation(g1: Optional[Dict[str, Any]], f: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## The first generation, PERTURBED by my own instrument (amendment 4)", "",
           "env_probe was appended to every P0 measured pipeline for the on-token read-back, and its "
           "closing() runs for every pipe instance: every PDF triggered its garbage-collector instance scan, "
           "holding the GIL inside the window. Every RocketRide docs design was re-run with the probe "
           "answering only its probe document (suffix f); verdicts come from the f legs only. The first "
           "generation, same session, for disclosure — never merged with the f legs:", ""]
    if not (g1 and f):
        return out + ["(analysis missing)", ""]
    rows = []
    for alias in ("d1_rr_u1", "d1_rr_u2", "an_rr_u1", "an_rr_u2", "an_li_u1", "an_li_u2"):
        a, b = (g1["legs"].get(alias) or {}), (f["legs"].get(alias) or {})
        if not a or not b:
            continue
        va, vb = a["span"]["docs_per_s"], b["span"]["docs_per_s"]
        rows.append([f"{alias} → {(f.get('leg_dirs') or {}).get(alias, alias)}", n(va, 4), n(vb, 4), pct(vb / va - 1, 1),
                     "never carried env_probe" if a["arm"] == "li" else "carried the scan"])
    out += table(["uninstrumented leg (first → f)", "first generation span docs/s", "f generation span docs/s",
                  "f / first − 1", "note"], rows)
    return out


def sec_posthoc(docs: Optional[Dict[str, Any]], h2: Optional[Dict[str, Any]], F: Dict[str, Any]) -> List[str]:
    out = ["## POST-HOC DIAGNOSTICS (not pre-registered; never used by a gate)", "",
           "Span throughput counts the DRAIN — the time after the last document was submitted, when "
           "fewer than C documents remain in flight. On the 384 slice a few long documents set it.", ""]
    rows = []
    dirs = (docs or {}).get("leg_dirs") or {}
    for alias in ("d1_rr_u1", "d1_rr_u2", "an_rr_u1", "an_rr_u2", "an_li_u1", "an_li_u2"):
        l = ((docs or {}).get("legs") or {}).get(alias)
        if not l:
            continue
        dr = l.get("drain_posthoc") or {}
        tq = dr.get("time_to_fraction_s") or {}
        rows.append([dirs.get(alias, alias), n(l["span"]["docs_per_s"], 4), share(dr.get("drain_share_of_span")),
                     n(dr.get("steady_docs_per_s"), 3), f"{n(tq.get('50%'), 1)} / {n(tq.get('90%'), 1)} / {n(tq.get('99%'), 1)} / {n(tq.get('100%'), 1)}",
                     n(l.get("cpu_s_per_doc"), 3), n(l.get("engine_cores"), 2)])
    out += table(["leg (uninstrumented)", "span docs/s", "drain share of span", "steady-phase docs/s",
                  "seconds to 50% / 90% / 99% / 100% done", "CPU-s per document (engine cgroup)", "engine cores"], rows)
    rows = []
    for name in ("h2f_c32_a", "h2f_c32_b"):
        x = (((h2 or {}).get("legs") or {}).get(name) or {}).get("steady_vs_drain_posthoc") or {}
        if x.get("status") == "unavailable" or not x:
            continue
        for ph in ("steady", "drain"):
            y = x.get(ph) or {}
            rows.append([name, ph, n(y.get("docs_in_flight_mean"), 1), n(y.get("python_threads_R_mean"), 1),
                         n(y.get("all_threads_R_mean"), 1)])
    if rows:
        out.append("Threads in the run state (R = running or runnable) in the DIAGNOSTIC H2 legs, while every "
                   "document is still being submitted (steady) against after the last submit (drain):")
        out.append("")
        out += table(["leg", "phase", "documents in flight", "Python threads in R", "all task threads in R"], rows)
    return out


def sec_e1(e1: Optional[Dict[str, Any]]) -> List[str]:
    out = ["## E1 — where the long parse holds live (EXPLORATORY DIAGNOSTIC, amendment 5)", ""]
    if not e1:
        return out + ["NOT RUN.", ""]
    rows = []
    for d, x in e1["per_document"].items():
        rows.append([d, n(x["isolated_tika_s"], 2), n(x["engine_tika_s"], 1) + (" (timed out)" if x["engine_timed_out"] else ""),
                     n(x["in_pipeline_s_S5D"], 1), n(x["engine_over_isolated"], 0), n(x["in_pipeline_over_isolated"], 0),
                     n(x["engine_stdout_mb"], 1)])
    out += table(["document", "isolated Tika s (H5, shipped mean)", "engine --tika s (E1)", "in-pipeline parse bracket s (S5-D)",
                  "engine / isolated", "in-pipeline / isolated", "engine stdout MB"], rows)
    out.append("Exec census over the stage (box-wide, nothing else running): " +
               (", ".join(f"{k} ×{v}" for k, v in list(e1.get("exec_census_box_wide", {}).items())[:12]) or "no execs recorded") + ".")
    out.append("")
    out.append("**Reading (with SOURCE, not measurement):** the engine's Tika wrapper "
               "(engine/java/lib/tika.jar, com.rocketride.tika_api.TikaApi) calls "
               "PDFParserConfig.setExtractInlineImages and setExtractUniqueInlineImagesOnly and sends every "
               "embedded image, PNG-encoded, through the JNI callback onWriteImageBuffer; isolated Tika "
               "(the same jars and config, default ParseContext) does not extract inline images. The "
               "product pipeline listens only to the parser's text lane.")
    out.append("")
    return out


def sec_amendments(c: Path) -> List[str]:
    out = ["## Amendments to the pre-registration (each landed before the legs it governs)", ""]
    for f in sorted(c.glob("preregistration_amendment_*.json")):
        j = json.loads(f.read_text())
        what = j.get("amends") or j.get("adds") or ""
        why = (j.get("reason") or j.get("fault") or j.get("why") or j.get("discovery") or "")
        out.append(f"- **{f.name}** ({j.get('written_utc')}): {what}. {why[:400]}{'…' if len(why) > 400 else ''}")
    out.append("")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
