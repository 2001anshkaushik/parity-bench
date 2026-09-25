#!/usr/bin/env python3
"""P5-A single-inference-thread smoke analysis (preregistration.json P5_A), from raw leg files only. Also imported by
p5_gates.py smoke (G_smoke_P5B decides from exactly this code).

    p5_analyse_a.py <campaign_dir>  -> analysis_p5a.json

Per leg: frames/s (export total_frames / total_span_s); measured frames (the LAST measured record per video without
error); the forward pass per frame over the measured stamp rows (the last N frame rows of the leg's stamp file by
t_wall) with the full D1 metric set; the inference duty (stock RR: P0 V2's lock duty; P5: the inference thread's held
time over the same kind of window; LlamaIndex: P0 V2's per-video lock duty); cores busy during the forward; CPU-s/frame;
the queue depth distribution (P5 only); the sampled memory peak; session facts; the canary per round. Per cell: each
round's value, the mean and the replicate spread of the two ABAB runs. Then correctness first, and S1 / S2 per round
and pooled.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import identity, load, metric_set, spread  # noqa: E402

CELLS = {"stock_k16": ("p5a_stock16_1", "p5a_stock16_2", "stock"), "p5_k16": ("p5a_p5k16_1", "p5a_p5k16_2", "p5"),
         "p5_k1": ("p5a_p5k1_1", "p5a_p5k1_2", "p5"), "li_k16": ("p5a_li16_1", "p5a_li16_2", "li")}
CANARY = ("p5c_can_1", "p5c_can_2")
P4_STOCK_K1 = Path(__file__).resolve().parents[2] / "working" / "results" / "parity_p4_20260925T092942Z" / "p4a_rr1_1"
PARITY = 0.95


def rows(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def spread0(a: float, b: float) -> float:
    return 0.0 if a == b else spread(a, b)


def gated(camp: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in ("chain_p5_smoke_done.json",):
        p = camp / f
        if p.exists():
            for x in json.loads(p.read_text()).get("legs", []):
                d, _, st = x.partition(":")
                if st in ("rc=0", "DEGRADED_all_rows"):
                    base = d[:-3] if d[-3:] in ("_r1", "_r2") else d
                    out.setdefault(base, d)
    if not out:                                   # mid-chain (the in-chain gate): the first attempt with a leg record
        for c in CELLS.values():
            for n in c[:2]:
                for suf in ("", "_r1", "_r2"):
                    if list((camp / f"{n}{suf}").glob("export_*.json")):
                        out[n] = f"{n}{suf}"
                        break
    return out


def leg(camp: Path, name: str, flavour: str) -> Optional[Dict[str, Any]]:
    d = camp / name
    g = load(d) if d.is_dir() else None
    if not g:
        return None
    sf = "p5_stamps.jsonl" if flavour == "p5" else "p1_stamps.jsonl"
    st_all = rows(d / sf)
    fr = sorted((r for r in st_all if r.get("kind", "frame") == "frame"), key=lambda r: r["t_wall"])
    fr = fr[-g["frames"]:] if len(fr) >= g["frames"] else fr
    fw = [r["forward"] for r in fr if r.get("forward") is not None]
    both = [r for r in fr if r.get("forward") and r.get("fw_proc_cpu") is not None]
    sw = sum(r["forward"] for r in both)
    out = {k: g[k] for k in ("dir", "videos", "errors", "frames", "span_s", "frames_per_s", "cpu_s_per_frame", "engine_cores",
                             "boot_id", "session")}
    out.update({"flavour": flavour, "stamp_frames_measured": len(fr), "F_s": statistics.mean(fw) if fw else None,
                "forward_D1": metric_set(fw), "cores_in_forward": (sum(r["fw_proc_cpu"] for r in both) / sw) if sw else None})
    if flavour == "stock":
        per = [sum(x or 0 for x in (r.get("decode"), r.get("lock_wait"), r.get("lock_held"), r.get("emit"))) for r in fr]
        held = sum(r.get("lock_held") or 0 for r in fr)
        t0, t1 = min(r["t_wall"] for r in fr), max(r["t_wall"] + p for r, p in zip(fr, per))
        out["duty"] = held / (t1 - t0) if t1 > t0 else None
        out["duty_kind"] = "device-lock held / window (P0 V2)"
    elif flavour == "p5":
        per = [sum(x or 0 for x in (r.get("decode"), r.get("queue_wait"), r.get("infer_held"), r.get("handoff"), r.get("emit"))) for r in fr]
        held = sum(r.get("infer_held") or 0 for r in fr)
        t0, t1 = min(r["t_wall"] for r in fr), max(r["t_wall"] + p for r, p in zip(fr, per))
        out["duty"] = held / (t1 - t0) if t1 > t0 else None
        out["duty_kind"] = "inference thread busy / window"
        q = [r.get("qdepth") for r in fr if r.get("qdepth") is not None]
        hist: Dict[str, int] = {}
        for x in q:
            hist[str(x)] = hist.get(str(x), 0) + 1
        out["queue_depth"] = {"D1": metric_set([float(x) for x in q]), "histogram": dict(sorted(hist.items(), key=lambda kv: int(kv[0])))}
        out["infer_threads"] = sorted({r.get("infer_tid") for r in fr if r.get("infer_tid") is not None})
        out["queue_wait_D1"] = metric_set([r.get("queue_wait") for r in fr])
    else:
        t_first = fr[0]["t_wall"] if fr else None
        vids = [r for r in st_all if r.get("kind") == "video" and t_first is not None and r["t_wall_release"] >= t_first]
        t1 = max(r["t_wall_release"] for r in vids) if vids else None
        out["duty"] = (sum(r.get("lock_held") or 0 for r in vids) / (t1 - t_first)) if (t1 and t1 > t_first) else None
        out["duty_kind"] = "per-video lock held / window (P0 V2)"
    ms = [r.get("total") for r in rows(d / "memstat.jsonl") if r.get("total") is not None]
    out["memory_peak_total_bytes"] = max(ms) if ms else None
    out["_by_video"] = g["by_video"]
    return out


def canary_leg(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    f = camp / name / "bench.json"
    if not f.exists():
        return None
    b = json.loads(f.read_text())
    fw = [r["forward"] for r in b["rows"] if r.get("forward")]
    return {"leg": name, "frames": len(b["rows"]), "F_s": statistics.mean(fw) if fw else None, "forward_D1": metric_set(fw),
            "boot_id": (camp / name / "boot_id.txt").read_text().strip() if (camp / name / "boot_id.txt").exists() else None}


def analyse(camp: Path) -> Dict[str, Any]:
    gl = gated(camp)
    legs: Dict[str, Any] = {}
    for c, (a, b, fl) in CELLS.items():
        for n in (a, b):
            legs[n] = leg(camp, gl[n], fl) if gl.get(n) else None
    cells: Dict[str, Any] = {}
    for c, (a, b, fl) in CELLS.items():
        L = [legs[a], legs[b]]
        def pv(k, sub=None):
            v = [(x.get(k) if sub is None else (x.get(k) or {}).get(sub)) if x else None for x in L]
            full = None not in v
            return {"round_1": v[0], "round_2": v[1], "mean": statistics.mean(v) if full else None, "spread": spread0(*v) if full else None}
        cells[c] = {"legs": [x["dir"] if x else None for x in L], "complete": None not in L,
                    "frames_per_s": pv("frames_per_s"), "F_s": pv("F_s"), "duty": pv("duty"), "cores_in_forward": pv("cores_in_forward"),
                    "cpu_s_per_frame": pv("cpu_s_per_frame"), "memory_peak_total_bytes": pv("memory_peak_total_bytes"),
                    "forward_p50": pv("forward_D1", "p50"), "forward_p95": pv("forward_D1", "p95"), "engine_cores": pv("engine_cores")}
    # ---------------- correctness first
    def ident(x, y, n=16):
        if not x or not y:
            return None
        i = identity({"dir": x["dir"], "by_video": x["_by_video"]}, {"dir": y["dir"], "by_video": y["_by_video"]})
        i["videos_eq_16"] = i["videos_compared"] == n
        return i
    p4k1 = load(P4_STOCK_K1)
    p4 = {"dir": "P4 p4a_rr1_1 (stock, K=1, committed)", "_by_video": p4k1["by_video"]} if p4k1 else None
    gate_pairs = []
    for r in (0, 1):
        s16, p16, p1 = legs[CELLS["stock_k16"][r]], legs[CELLS["p5_k16"][r]], legs[CELLS["p5_k1"][r]]
        gate_pairs += [x for x in (ident(p16, s16), ident(p1, s16), ident(p1, p4)) if x]
    gate_pass = (bool(gate_pairs) and all(x["identical"] and x["videos_eq_16"] for x in gate_pairs)) if gate_pairs else None
    beside = {"stock_k16_run_to_run": ident(legs[CELLS["stock_k16"][0]], legs[CELLS["stock_k16"][1]]),
              "p5_k16_run_to_run": ident(legs[CELLS["p5_k16"][0]], legs[CELLS["p5_k16"][1]]),
              "p5_k1_vs_p5_k16_round_1": ident(legs[CELLS["p5_k1"][0]], legs[CELLS["p5_k16"][0]]),
              "li_k16_run_to_run": ident(legs[CELLS["li_k16"][0]], legs[CELLS["li_k16"][1]])}
    # ---------------- readings
    rd: Dict[str, Any] = {}
    need = ("stock_k16", "p5_k16", "p5_k1", "li_k16")
    if all(cells[c]["complete"] for c in need):
        C = cells
        thrA = max(C["p5_k16"]["F_s"]["spread"], C["p5_k1"]["F_s"]["spread"])
        thrB = max(C["p5_k16"]["frames_per_s"]["spread"], C["stock_k16"]["frames_per_s"]["spread"])

        def s1(key):
            fa = C["p5_k16"]["F_s"][key] / C["p5_k1"]["F_s"][key] - 1
            fb = C["p5_k16"]["frames_per_s"][key] / C["stock_k16"]["frames_per_s"][key] - 1
            return {"F_p5k16_over_p5k1_minus_1": fa, "clause_forward_within": abs(fa) <= thrA,
                    "fps_p5k16_over_stock_k16_minus_1": fb, "clause_fps_beyond": fb > thrB, "holds": abs(fa) <= thrA and fb > thrB}

        def s2(key):
            ratio = C["p5_k16"]["frames_per_s"][key] / C["li_k16"]["frames_per_s"][key]
            return {"fps_p5k16_over_li_k16": ratio, "holds": ratio >= PARITY}
        rd["S1"] = {"threshold_forward": thrA, "threshold_fps": thrB, "pooled": s1("mean"), "round_1": s1("round_1"), "round_2": s1("round_2")}
        rd["S2"] = {"bar": PARITY, "pooled": s2("mean"), "round_1": s2("round_1"), "round_2": s2("round_2")}
        for s in ("S1", "S2"):
            rd[s]["verdict"] = ("HOLDS" if rd[s]["pooled"]["holds"] else "DOES NOT HOLD") + " (pooled); round 1 " + (
                "holds" if rd[s]["round_1"]["holds"] else "does not") + ", round 2 " + ("holds" if rd[s]["round_2"]["holds"] else "does not")
    else:
        rd["S1"] = rd["S2"] = {"verdict": "NOT EVALUABLE", "missing_cells": [c for c in need if not cells[c]["complete"]]}
    can = {n: canary_leg(camp, n) for n in CANARY}
    for x in legs.values():
        if x:
            x["_by_video"] = f"{len(x['_by_video'])} videos (records file)"
    return {"label": "P5-A single inference thread smoke (preregistration.json P5_A)", "gated_legs": gl, "legs": legs, "cells": cells,
            "correctness": {"gate_pairs": gate_pairs, "gate_pass": gate_pass, "beside": beside,
                            "rule": "per round: P5 K=16 vs stock K=16, P5 K=1 vs stock K=16, P5 K=1 vs P4's committed stock K=1 — all identical on 16/16"},
            "readings": rd, "canary": can,
            "sessions": sorted({x["boot_id"] for x in legs.values() if x and x.get("boot_id")})}


def main() -> int:
    camp = Path(sys.argv[1])
    out = analyse(camp)
    (camp / "analysis_p5a.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p5a.json: correctness {out['correctness']['gate_pass']}; S1 {out['readings']['S1'].get('verdict')}; S2 {out['readings']['S2'].get('verdict')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
