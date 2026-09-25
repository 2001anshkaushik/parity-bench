#!/usr/bin/env python3
"""P3-B analysis (preregistration.json P3_B_video_discriminator), from raw leg files only.

    p3_analyse_b.py <campaign_dir>  -> analysis_p3b.json

Frame identity first: the bare cells' per-frame sha256 must equal p3b_frames_manifest.json (same set, same order); the
engine cell's frame count must equal the manifest's. Per leg: F (mean forward wall per measured frame), cores busy
during the forward (sum process CPU / sum forward wall), caller on-CPU share (sum calling-thread CPU / sum forward wall),
the measured frame count, the torch threads read back. Per cell (a, b, c): mean of two legs, replicate spread. Then the
pre-registered pairwise relations (x ~= y iff |F_x/F_y - 1| <= max(spread_x, spread_y)) and the reading; the (1)
inspection (OpenMP / BLAS / TBB runtimes mapped by each detector process) and its reading.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import load, spread  # noqa: E402
from p1_analyse_e2 import forward_block, measured_frames  # noqa: E402

FLOOR = 0.0082
FAMILIES = {"openmp": ("libgomp", "libiomp", "libomp"), "blas": ("libmkl", "libopenblas", "libblas", "libcblas", "libflexiblas"),
            "tbb": ("libtbb",)}


def leg_dir(camp: Path, name: str, need: str) -> Optional[Path]:
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and (d / need).exists():
            return d
    return None


def fam_of(path: str) -> Optional[str]:
    b = path.rsplit("/", 1)[-1]
    for f, pats in FAMILIES.items():
        if any(b.startswith(p) for p in pats):
            return f"{f}:{next(p for p in pats if b.startswith(p))}"
    return None


def runtime_set(paths: List[str]) -> Dict[str, Any]:
    fams: Dict[str, List[str]] = {}
    for p in paths:
        f = fam_of(p)
        if f:
            fams.setdefault(f, []).append(p)
    omp = sorted({p for f, ps in fams.items() if f.startswith("openmp") for p in ps})
    return {"families": {k: sorted(v) for k, v in sorted(fams.items())}, "openmp_files": omp, "all": sorted(paths)}


def parse_maps(f: Path) -> List[Dict[str, Any]]:
    procs, cur = [], None
    for line in f.read_text(errors="replace").splitlines():
        if line.startswith("PID "):
            parts = line.split(" ", 3)
            cur = {"pid": int(parts[1]), "comm": parts[2] if len(parts) > 2 else "", "cmdline": parts[3] if len(parts) > 3 else "", "libs": []}
            procs.append(cur)
        elif cur is not None and line.startswith("/"):
            cur["libs"].append(line.strip())
    return procs


def bare_leg(d: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    b = json.loads((d / "bench.json").read_text())
    rows = b["rows"]
    man = [(r["frame"], r["sha256"]) for r in manifest["frames"]]
    got = [(r["frame"], r["frame_sha256"]) for r in rows]
    meas = [r for r in rows if r.get("forward")]
    sw = sum(r["forward"] for r in meas)
    rb = b["readback"]
    return {"leg": d.name, "frames_identical_to_manifest": got == man, "n_frames": len(rows), "measured": len(meas),
            "F_s": sw / len(meas) if meas else None, "cores_in_forward": sum(r["fw_proc_cpu"] for r in meas) / sw if sw else None,
            "caller_cpu_ratio": sum(r["fw_thread_cpu"] for r in meas) / sw if sw else None,
            "callers": sorted({r["tid"] for r in rows}), "one_model_instance": b.get("one_model_instance"),
            "rfdetr_models": rb.get("rfdetr_models_after_build"), "torch_threads": rb["torch"]["num_threads"],
            "torch_interop": rb["torch"]["num_interop_threads"], "torch_version": rb["torch"]["version"], "torch_file": rb["torch"]["file"],
            "numpy": rb["numpy"], "rfdetr": rb["rfdetr"], "python": rb["python"].split()[0], "executable": rb["executable"],
            "env": rb["env"], "os_threads_at_end": len(rb["os_threads_at_end"]),
            "runtimes": runtime_set(rb["loaded_runtimes"] if isinstance(rb["loaded_runtimes"], list) else []),
            "dets_sha256": [r["dets_sha256"] for r in rows]}


def svc_leg(d: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    g = load(d)
    fr = measured_frames(d, g["frames"]) if (d / "p1_stamps.jsonl").exists() else []
    fb = forward_block(fr) if fr else {}
    rb = json.loads((d / "p1_readback.json").read_text()) if (d / "p1_readback.json").exists() else {}
    maps = parse_maps(d / "runtime_maps.txt") if (d / "runtime_maps.txt").exists() else []
    return {"leg": d.name, "frames_observed": g["frames"], "manifest_frames": manifest["n_frames"],
            "frame_count_equals_manifest": g["frames"] == manifest["n_frames"], "errors": g["errors"], "videos": g["videos"],
            "frames_per_s": g["frames_per_s"], "F_s": fb.get("forward_mean_s"), "cores_in_forward": fb.get("cores_in_forward"),
            "caller_cpu_ratio": fb.get("caller_cpu_ratio"), "callers": fb.get("callers"), "measured": fb.get("frames"),
            "torch_threads": (rb.get("torch") or {}).get("num_threads") if isinstance(rb.get("torch"), dict) else None,
            "p0": {k: ((g.get("p0") or {}).get(k) or {}).get("pid") for k in ("d0_pre", "d0_post")},
            "maps_processes": [{"pid": p["pid"], "comm": p["comm"], "cmdline": p["cmdline"], "runtimes": runtime_set(p["libs"])} for p in maps]}


def rel(x: Dict[str, Any], y: Dict[str, Any]) -> Dict[str, Any]:
    d = x["mean"] / y["mean"] - 1
    thr = max(x["spread"], y["spread"])
    return {"ratio_minus_1": d, "threshold": thr, "approx_equal": abs(d) <= thr, "less": d < -thr, "greater": d > thr,
            "beyond_floor_0_82pct": abs(d) > FLOOR}


def read_cells(cells: Dict[str, Any], frames_ok: bool) -> Dict[str, Any]:
    reading: Dict[str, Any] = {"approx_rule": "x ~= y iff |F_x/F_y - 1| <= max(spread_x, spread_y)"}
    if len(cells) == 3 and frames_ok:
        ab, ac, bc = rel(cells["a"], cells["b"]), rel(cells["a"], cells["c"]), rel(cells["b"], cells["c"])
        reading.update({"a_vs_b": ab, "a_vs_c": ac, "b_vs_c": bc})
        if ab["approx_equal"] and ac["less"] and bc["less"]:
            v = "a ~= b < c: the ENGINE PROCESS ENVIRONMENT owns the gap"
        elif ac["approx_equal"] and ab["greater"] and bc["less"]:          # a ~= c, a > b, c > b (b < c)
            v = "a ~= c > b: the INTERPRETER OR RUNTIME BUILD owns it"
        elif ab["approx_equal"] and ac["approx_equal"] and bc["approx_equal"]:
            v = "a ~= b ~= c: the gap lives in PIPELINE-LEVEL SCHEDULING"
        else:
            v = "NO PRE-REGISTERED READING MATCHES (the three relations are reported)"
        reading["verdict"] = v
    else:
        reading["verdict"] = "NOT EVALUABLE (" + ("a cell lacks two legs" if len(cells) < 3 else "the bare frame set differs from the manifest") + ")"
    return reading


def main() -> int:
    camp = Path(sys.argv[1])
    manifest = json.loads((camp / "p3b_frames_manifest.json").read_text())
    legs: Dict[str, Any] = {}
    for n in ("p3b_a_1", "p3b_a_2", "p3b_b_1", "p3b_b_2"):
        d = leg_dir(camp, n, "bench.json")
        legs[n] = bare_leg(d, manifest) if d else None
    for n in ("p3b_c_1", "p3b_c_2", "p3b_d_1"):
        d = leg_dir(camp, n, "p1_stamps.jsonl")
        legs[n] = svc_leg(d, manifest) if d else None
    cells: Dict[str, Any] = {}
    for c, ns in (("a", ("p3b_a_1", "p3b_a_2")), ("b", ("p3b_b_1", "p3b_b_2")), ("c", ("p3b_c_1", "p3b_c_2"))):
        v = [legs[n]["F_s"] for n in ns if legs.get(n) and legs[n].get("F_s")]
        if len(v) == 2:
            cells[c] = {"legs": list(ns), "F_s": v, "mean": statistics.mean(v), "spread": spread(*v),
                        "cores_in_forward": [legs[n]["cores_in_forward"] for n in ns],
                        "caller_cpu_ratio": [legs[n]["caller_cpu_ratio"] for n in ns]}
    ident = {"bare_frames_identical_to_manifest": all(legs[n]["frames_identical_to_manifest"] for n in ("p3b_a_1", "p3b_a_2", "p3b_b_1", "p3b_b_2") if legs.get(n)),
             "engine_frame_count_equals_manifest": all(legs[n]["frame_count_equals_manifest"] for n in ("p3b_c_1", "p3b_c_2") if legs.get(n)),
             "bare_one_model_instance": all(legs[n]["one_model_instance"] for n in ("p3b_a_1", "p3b_a_2", "p3b_b_1", "p3b_b_2") if legs.get(n)),
             "torch_threads": {n: legs[n].get("torch_threads") for n in legs if legs.get(n)}}
    ident["detections_a_vs_b_identical_per_frame"] = (
        legs["p3b_a_1"]["dets_sha256"] == legs["p3b_b_1"]["dets_sha256"]) if legs.get("p3b_a_1") and legs.get("p3b_b_1") else None
    reading = read_cells(cells, ident["bare_frames_identical_to_manifest"])
    # (1) the inspection
    insp: Dict[str, Any] = {}
    rr_task = [p for n in ("p3b_c_1", "p3b_c_2") if legs.get(n) for p in legs[n]["maps_processes"] if "node.py" in p["cmdline"]]
    li_proc = [p for p in (legs.get("p3b_d_1") or {}).get("maps_processes", [])]
    if rr_task and li_proc:
        rr_fams = set().union(*(set(p["runtimes"]["families"]) for p in rr_task))
        li_fams = set().union(*(set(p["runtimes"]["families"]) for p in li_proc))
        rr_omp = sorted(set().union(*(set(p["runtimes"]["openmp_files"]) for p in rr_task)))
        only_rr = sorted(rr_fams - li_fams)
        per_proc_omp = [len(p["runtimes"]["openmp_files"]) for p in rr_task]
        supported = any(n >= 2 for n in per_proc_omp) or bool(only_rr)
        insp = {"rr_task_processes": rr_task, "li_detector_processes": li_proc, "rr_families": sorted(rr_fams), "li_families": sorted(li_fams),
                "families_only_in_rr": only_rr, "families_only_in_li": sorted(li_fams - rr_fams), "rr_openmp_files": rr_omp,
                "rr_openmp_files_per_process": per_proc_omp,
                "bare_a_families": sorted(legs["p3b_a_1"]["runtimes"]["families"]) if legs.get("p3b_a_1") else None,
                "bare_b_families": sorted(legs["p3b_b_1"]["runtimes"]["families"]) if legs.get("p3b_b_1") else None,
                "reading": "SUPPORTED" if supported else "NOT SUPPORTED",
                "rule": "SUPPORTED iff the RR task process maps two or more distinct OpenMP runtime files, OR maps an OpenMP, BLAS or TBB family that LlamaIndex's detector process does not"}
    else:
        insp = {"reading": "NOT EVALUABLE (the RR task process or the LlamaIndex detector process was not inspected)",
                "rr_task_found": bool(rr_task), "li_found": bool(li_proc)}
    out = {"label": "P3-B video discriminator (preregistration.json P3_B)", "frames": {k: manifest[k] for k in ("videos", "n_frames", "set_sha256", "argv")},
           "identity": ident, "legs": legs, "cells": cells, "reading": reading, "inspection_1": insp,
           "boot_ids": sorted({(Path(camp / n / "boot_id.txt").read_text().strip() if (camp / n / "boot_id.txt").exists() else None) for n in legs if legs.get(n)} - {None})}
    for n, x in out["legs"].items():
        if x and "dets_sha256" in x:
            x["dets_sha256"] = f"{len(x['dets_sha256'])} per-frame hashes (bench.json)"
    (camp / "analysis_p3b.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p3b.json: (2) {reading['verdict']}; (1) {insp.get('reading')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
