#!/usr/bin/env python3
"""P1-A E2 analysis (preregistration.json P1_A_E2 + amendment 1), from raw leg files only.

    p1_analyse_e2.py <campaign_dir>  -> analysis_e2.json

Per leg: export (frames/s = total_frames / total_span_s), records (per-video outputs), p1_stamps.jsonl
(measured frames = the last N frame rows by t_wall, N = the export's total_frames), p1_readback.json;
ON legs also e2trace_<leg>.json (bpftrace maps), threadstate_<leg>.jsonl, pyspy_gil_<leg>.txt,
tracer_meta.json. Readings are computed from the pre-registered rules; nothing is tuned here.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import FLOOR, cell, identity, load, metric_set, rows, session_facts, spread  # noqa: E402

T = 4
BUCKET_S = 0.05                       # amendment 1: 50 ms buckets of GIL waits > 50 us
LEGS = {"rr": {"on": ["e2_rr_on_a", "e2_rr_on_b"], "off": ["e2_rr_off_a", "e2_rr_off_b"]},
        "li": {"on": ["e2_li_on_a", "e2_li_on_b"], "off": ["e2_li_off_a", "e2_li_off_b"]}}


def leg_dir(camp: Path, name: str) -> Optional[Path]:
    """The leg's directory: the first clean attempt, else its retry (<leg>_r1, <leg>_r2)."""
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and list(d.glob("export_*.json")):
            return d
    return None


def measured_frames(d: Path, n: int) -> List[Dict[str, Any]]:
    fr = [r for r in rows(d / "p1_stamps.jsonl") if r.get("kind", "frame") == "frame"]
    fr.sort(key=lambda r: r["t_wall"])
    return fr[-n:] if len(fr) >= n else fr


def bpf(d: Path, leg: str) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    f = d / f"e2trace_{leg}.json"
    if not f.exists():
        return out
    for line in f.read_text(errors="replace").splitlines():
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if j.get("type") == "map":
            for k, v in (j.get("data") or {}).items():
                out[k] = v if isinstance(v, dict) else {"": v}
    return out


def forward_block(fr: List[Dict[str, Any]]) -> Dict[str, Any]:
    fw = [r["forward"] for r in fr if r.get("forward") is not None]
    tc = [r["fw_thread_cpu"] for r in fr if r.get("fw_thread_cpu") is not None and r.get("forward")]
    pc = [r["fw_proc_cpu"] for r in fr if r.get("fw_proc_cpu") is not None and r.get("forward")]
    swall = sum(r["forward"] for r in fr if r.get("forward") and r.get("fw_thread_cpu") is not None)
    return {"frames": len(fr), "forward": metric_set(fw), "forward_mean_s": statistics.mean(fw) if fw else None,
            "caller_cpu_ratio": (sum(tc) / swall) if swall else None,
            "cores_in_forward": (sum(pc) / swall) if swall else None,
            "callers": sorted({r["tid"] for r in fr if r.get("tid") is not None})}


def gil_in_forward(fr: List[Dict[str, Any]], buckets: Dict[str, int]) -> Dict[str, Any]:
    """Per frame: the calling thread's GIL-wait buckets overlapping [fw0_mono, fw1_mono], pro rata."""
    by_tid: Dict[int, Dict[int, int]] = {}
    for k, v in buckets.items():
        tid, b = (int(x) for x in k.split(","))
        by_tid.setdefault(tid, {})[b] = v
    per = []
    for r in fr:
        a, e, tid = r.get("fw0_mono"), r.get("fw1_mono"), r.get("tid")
        if a is None or e is None or tid is None:
            continue
        bs = by_tid.get(tid, {})
        s = 0.0
        for b in range(int(a / BUCKET_S), int(e / BUCKET_S) + 1):
            if b in bs:
                lo, hi = b * BUCKET_S, (b + 1) * BUCKET_S
                ov = max(0.0, min(e, hi) - max(a, lo))
                s += bs[b] / 1e9 * (ov / BUCKET_S)
        per.append(s)
    return {"frames": len(per), "mean_s": statistics.mean(per) if per else None, "metric_set": metric_set(per)}


def thread_names(d: Path, leg: str) -> Dict[int, str]:
    names: Dict[int, str] = {}
    f = d / f"threadstate_{leg}.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            for th in json.loads(line)["th"]:
                names[int(th[0])] = th[1]
    return names


def affinity_of(d: Path, leg: str, tids: List[int]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    f = d / f"threadstate_{leg}.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            for th in json.loads(line)["th"]:
                if int(th[0]) in tids:
                    out[int(th[0])] = th[6]
    return out


def pyspy_top(d: Path, leg: str, k: int = 10) -> Dict[str, Any]:
    f = d / f"pyspy_gil_{leg}.txt"
    if not f.exists() or not f.stat().st_size:
        return {"status": "NO FILE"}
    c, tot = Counter(), 0
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(?P<stack>.*) (?P<n>\d+)$", line.strip())
        if not m:
            continue
        n = int(m.group("n"))
        c[re.sub(r":\d+\)$", ")", m.group("stack").split(";")[-1])] += n
        tot += n
    return {"samples": tot, "top": [{"function": a, "share": b / tot} for a, b in c.most_common(k)]}


def ns_to_host(d: Path, leg: str, fr: List[Dict[str, Any]], m: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """The stamps carry thread ids in the CONTAINER's pid namespace (threading.get_native_id() inside
    it); bpftrace and the /proc sampler carry HOST ids. Ids are handed out in creation order in both
    namespaces, so host = container + k, where k can only grow (by ids other host processes take
    between thread creations). The N forward callers (N = distinct stamp tids) are the process's N
    busiest GIL re-acquirers (every forward pass releases and re-takes the GIL at each torch op), so the
    sorted callers are paired with those N host threads sorted by id — ACCEPTED only if the offsets never
    decrease and drift by at most 50 in total; the offsets are reported."""
    callers = sorted({r["tid"] for r in fr if r.get("tid") is not None})
    rtn = {int(k): v for k, v in (m.get("@rt_n") or {}).items() if v > 0}
    heavy = sorted(sorted(rtn, key=lambda h: -rtn[h])[:len(callers)])
    if len(heavy) != len(callers):
        return {"map": {}, "error": f"{len(heavy)} host Python threads for {len(callers)} callers"}
    ks = [h - c for c, h in zip(callers, heavy)]
    ok = all(b >= a for a, b in zip(ks, ks[1:])) and ks[-1] - ks[0] <= 50 and ks[0] >= 0
    out = {"offsets": ks, "offset_min": min(ks), "offset_max": max(ks), "accepted": ok,
           "gil_reacquisitions_mapped": sum(rtn[h] for h in heavy), "gil_reacquisitions_all": sum(rtn.values()),
           "next_busiest_after_callers": sorted(rtn.values(), reverse=True)[len(callers)] if len(rtn) > len(callers) else None,
           "least_busy_caller": min(rtn[h] for h in heavy)}
    out["map"] = {str(c): h for c, h in zip(callers, heavy)} if ok else {}
    if not ok:
        out["error"] = "offsets decrease or drift beyond 50: mapping refused"
    return out


def on_leg(d: Path, leg: str, fr: List[Dict[str, Any]], window_s: Optional[float]) -> Dict[str, Any]:
    m = bpf(d, leg)
    idmap = ns_to_host(d, leg, fr, m)
    mp = {int(a): b for a, b in (idmap.get("map") or {}).items()}
    fr = [dict(r, tid=mp.get(r["tid"])) for r in fr]
    callers = sorted({r["tid"] for r in fr if r.get("tid") is not None})
    on = {int(k): v for k, v in (m.get("@oncpu_ns") or {}).items()}
    rq = {int(k): v for k, v in (m.get("@runq_ns") or {}).items()}
    sl = {int(k): v for k, v in (m.get("@sleep_ns") or {}).items()}
    workers = [t for t, _ in sorted(on.items(), key=lambda x: -x[1]) if t not in callers][:T - 1]
    compute = sorted(set(callers) | set(workers))
    nfr = len(fr) or 1
    names = thread_names(d, leg)
    busy = [t for t in workers if window_s and on.get(t, 0) / 1e9 >= 0.5 * window_s]
    rt = {int(k): v for k, v in (m.get("@rt_ns") or {}).items()}
    # POST-HOC (not pre-registered; never used by a reading): threads by class. Callers = the mapped
    # forward callers; native = threads that never re-took the GIL (the OMP worker pools live here);
    # other Python = the rest. Per class: count, and on-CPU / run-queue / sleep seconds per frame.
    rtn = {int(k2): v for k2, v in (m.get("@rt_n") or {}).items() if v > 0}
    classes: Dict[str, List[int]] = {"callers": callers,
                                     "native_busy": [t for t in on if t not in rtn and t not in callers and on[t] > 1e9],
                                     "other_python": [t for t in rtn if t not in callers]}
    posthoc = {cls: {"threads": len(ts), "oncpu_per_frame_s": sum(on.get(t, 0) for t in ts) / 1e9 / nfr,
                     "runq_per_frame_s": sum(rq.get(t, 0) for t in ts) / 1e9 / nfr,
                     "sleep_per_frame_s": sum(sl.get(t, 0) for t in ts) / 1e9 / nfr,
                     "top": sorted(((t, names.get(t), round(on.get(t, 0) / 1e9, 1)) for t in ts), key=lambda x: -x[2])[:5]}
               for cls, ts in classes.items()}
    return {"window_s": window_s, "tid_map_container_to_host": idmap,
            "posthoc_thread_classes": posthoc,
            "callers": callers, "omp_workers": [{"tid": t, "name": names.get(t), "oncpu_s": on.get(t, 0) / 1e9,
                                                 "runq_s": rq.get(t, 0) / 1e9, "sleep_s": sl.get(t, 0) / 1e9}
                                                for t in workers],
            "busy_workers": len(busy),
            "R_runq_per_frame_s": sum(rq.get(t, 0) for t in compute) / 1e9 / nfr,
            "compute_threads_per_frame_s": {"oncpu": sum(on.get(t, 0) for t in compute) / 1e9 / nfr,
                                            "runq": sum(rq.get(t, 0) for t in compute) / 1e9 / nfr,
                                            "sleep": sum(sl.get(t, 0) for t in compute) / 1e9 / nfr},
            "callers_gil_wait_total_per_frame_s": sum(rt.get(t, 0) for t in callers) / 1e9 / nfr,
            "G_gil_wait_in_forward": gil_in_forward(fr, m.get("@rt_b") or {}),
            "process_threads_top_oncpu": [{"tid": t, "name": names.get(t), "oncpu_s": v / 1e9}
                                          for t, v in sorted(on.items(), key=lambda x: -x[1])[:12]],
            "affinity_compute_threads": affinity_of(d, leg, compute),
            "gil_take_rr": ({"wait_s": sum((m.get("@wait_ns") or {}).values()) / 1e9,
                             "hold_s": sum((m.get("@hold_ns") or {}).values()) / 1e9} if m.get("@wait_ns") else None),
            "pyspy_gil": pyspy_top(d, leg)}


def main() -> int:
    camp = Path(sys.argv[1])
    out: Dict[str, Any] = {"label": "P1-A E2 (DIAGNOSTIC tracer on the ON legs; OFF legs are the null control)", "arms": {}}
    rb: Dict[str, Any] = {}
    for arm, sets in LEGS.items():
        A: Dict[str, Any] = {}
        for state, names in sets.items():
            legs = []
            for nm in names:
                d = leg_dir(camp, nm)
                if not d:
                    legs.append({"leg": nm, "status": "MISSING"})
                    continue
                g = load(d)
                fr = measured_frames(d, g["frames"])
                rec = {"leg": d.name, "dir": d.name, "frames_per_s": g["frames_per_s"], "summary": g,
                       "session": session_facts(d), "forward": forward_block(fr),
                       "memstat": json.loads((d / "memstat.jsonl.summary.json").read_text())
                       if (d / "memstat.jsonl.summary.json").exists() else None,
                       "idle_cores": ((json.loads(next(d.glob("export_*.json")).read_text()).get("efficiency") or {})
                                      .get("idle_burden") or {}).get("idle_cores_with_instances_live")}
                if (d / "p1_readback.json").exists():
                    rb.setdefault(arm, json.loads((d / "p1_readback.json").read_text()))
                    rec["readback"] = json.loads((d / "p1_readback.json").read_text())
                if state == "on":
                    tm = json.loads((d / "tracer_meta.json").read_text()) if (d / "tracer_meta.json").exists() else {}
                    w = ((tm.get("clock_at_close") or {}).get("monotonic_ns", 0) -
                         (tm.get("clock_at_ready") or {}).get("monotonic_ns", 0)) / 1e9 or None
                    rec["tracer_meta"] = {k: tm.get(k) for k in ("pid", "bpftrace_attached", "bpftrace_rc", "pyspy_rc", "files")}
                    rec["trace"] = on_leg(d, nm, fr, w)
                legs.append(rec)
            A[state] = legs
        ok = {s: [x for x in A[s] if "frames_per_s" in x] for s in A}
        nc: Dict[str, Any] = {}
        if len(ok["on"]) == 2 and len(ok["off"]) == 2:
            con, coff = cell([x["summary"] for x in ok["on"]]), cell([x["summary"] for x in ok["off"]])
            delta = con["mean"] / coff["mean"] - 1
            thr = max(FLOOR, con["spread"], coff["spread"])
            ident = [identity(ok["on"][i]["summary"], ok["off"][i]["summary"]) for i in (0, 1)]
            nc = {"on": con, "off": coff, "delta_on_over_off": delta, "threshold": thr,
                  "within": abs(delta) <= thr, "output_identity": ident,
                  "pass": abs(delta) <= thr and all(x["identical"] for x in ident)}
        A["null_control"] = nc
        for s in ("on", "off"):
            fwm = [x["forward"]["forward_mean_s"] for x in ok[s] if x["forward"]["forward_mean_s"] is not None]
            A[f"F_{s}"] = statistics.mean(fwm) if fwm else None
            A[f"F_{s}_spread"] = spread(*fwm) if len(fwm) == 2 else None
            A[f"caller_cpu_ratio_{s}"] = statistics.mean(x["forward"]["caller_cpu_ratio"] for x in ok[s]) if ok[s] else None
            A[f"cores_in_forward_{s}"] = statistics.mean(x["forward"]["cores_in_forward"] for x in ok[s]) if ok[s] else None
        if arm == "rr" and ok["off"]:
            A["cores_in_forward_off_net_of_idle"] = statistics.mean(
                x["forward"]["cores_in_forward"] - (x["idle_cores"] or 0) for x in ok["off"])
        tr = [x["trace"] for x in ok["on"] if x.get("trace")]
        if tr:
            A["G_on"] = statistics.mean(t["G_gil_wait_in_forward"]["mean_s"] or 0 for t in tr)
            A["R_on"] = statistics.mean(t["R_runq_per_frame_s"] for t in tr)
            A["busy_workers_on"] = [t["busy_workers"] for t in tr]
        out["arms"][arm] = A
    rr, li = out["arms"].get("rr", {}), out["arms"].get("li", {})
    D = (rr.get("F_off") - li.get("F_off")) if (rr.get("F_off") and li.get("F_off")) else None
    D_on = (rr.get("F_on") - li.get("F_on")) if (rr.get("F_on") and li.get("F_on")) else None
    diffs = []
    if rb.get("rr") and rb.get("li"):
        a, b = rb["rr"], rb["li"]
        for key in ("num_threads", "num_interop_threads", "cpu_capability", "mkldnn_enabled", "default_dtype",
                    "float32_matmul_precision", "parallel_info"):
            va, vb = (a.get("torch") or {}).get(key), (b.get("torch") or {}).get(key)
            if va != vb:
                diffs.append({"field": f"torch.{key}", "rr": va, "li": vb})
        for key in ("forward_mode", "switch_interval_s", "process_affinity"):
            if a.get(key) != b.get(key):
                diffs.append({"field": key, "rr": a.get(key), "li": b.get(key)})
        ea = {k: v for k, v in (a.get("env") or {}).items() if k.startswith(("OMP_", "MKL_", "KMP_", "GOMP_"))}
        eb = {k: v for k, v in (b.get("env") or {}).items() if k.startswith(("OMP_", "MKL_", "KMP_", "GOMP_"))}
        if ea != eb:
            diffs.append({"field": "OMP/MKL/KMP/GOMP env", "rr": ea, "li": eb})
    nc_ok = bool((rr.get("null_control") or {}).get("pass") and (li.get("null_control") or {}).get("pass"))
    read: Dict[str, Any] = {"D_off_s": D, "D_on_s": D_on, "null_control_both_arms_pass": nc_ok}
    if D_on and rr.get("G_on") is not None and li.get("G_on") is not None:
        read["a_GIL"] = {"G_rr_minus_G_li_s": rr["G_on"] - li["G_on"], "bar_s": 0.5 * D_on,
                         "supported": (rr["G_on"] - li["G_on"]) >= 0.5 * D_on}
    if D_on and rr.get("R_on") is not None and li.get("R_on") is not None:
        read["c_CPU_contention"] = {"R_rr_minus_R_li_s": rr["R_on"] - li["R_on"], "bar_s": 0.5 * D_on,
                                    "supported": (rr["R_on"] - li["R_on"]) >= 0.5 * D_on}
    bw_rr, bw_li = rr.get("busy_workers_on"), li.get("busy_workers_on")
    fewer = bool(bw_rr and bw_li and statistics.mean(bw_rr) < statistics.mean(bw_li))
    read["b_pool_or_affinity"] = {"readback_differences": diffs, "busy_workers_rr": bw_rr, "busy_workers_li": bw_li,
                                  "supported": bool(diffs) and fewer,
                                  "note": ("read back, not shown to cause" if diffs and not fewer else None)}
    sup = [k for k in ("a_GIL", "b_pool_or_affinity", "c_CPU_contention") if (read.get(k) or {}).get("supported")]
    read["supported"] = sup or ["none"]
    read["readable"] = nc_ok
    out["reading"] = read
    (camp / "analysis_e2.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(read, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
