#!/usr/bin/env python3
"""P4 gates, computed exactly as preregistration.json (P4_A_video_concurrency.gates) states them; the chain decides from
these exit codes. Every gate has a positive and a null control run WHOLE on the box before launch (p4_gate_controls.py).

    p4_gates.py alone                                          G_alone: exit 1 iff any container exists
    p4_gates.py memstat <camp> <leg>                           G_memstat: the leg's memstat.jsonl has >= 1 row
    p4_gates.py d0      <camp> <leg> rr|li                     G_d0: the leg's own D0 read-back is present and clean
    p4_gates.py cell    <camp> <leg> rr|li <K> <T> ACTIVE|unset <n>
                                                               G_cell: the leg measured the cell it names
    p4_gates.py correct <camp> <name> <legA> <legB> [<legA> <legB> ...]
                                                               G_correct: every pair output-identical on 16/16 videos

Legs are directories <camp>/<leg>. Exit 0 = pass / clean, 1 = fail / violation, 2 = evidence missing; the chain treats
any non-zero as FAIL. Records go to <camp>/gates/<gate>.json, create-only (a gate is decided once).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import container_procs, identity, load  # noqa: E402
import p2_gates  # noqa: E402

VIDEOS = 16


def record(camp: Path, gate: str, out: Dict[str, Any]) -> None:
    g = camp / "gates"
    g.mkdir(exist_ok=True)
    out = {"gate": gate, "decided_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **out}
    with open(g / f"{gate}.json", "x") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else "…") for k, v in out.items()}))


def rows(p: Path) -> List[Dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def alone() -> int:
    out = subprocess.run(["docker", "ps", "-aq"], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"docker ps failed: {out.stderr.strip()}")
        return 2
    n = len([x for x in out.stdout.split() if x.strip()])
    print(f"containers present: {n}")
    return 0 if n == 0 else 1


# ------------------------------------------------------------------ G_d0
def d0(camp: Path, leg: str, arm: str) -> int:
    d = camp / leg
    ev: Dict[str, Any] = {"leg": leg, "arm": arm}
    if arm == "rr":
        viol_file = (d / "MANDATE_VIOLATION.json").exists()
        exp = sorted(d.glob("export_*.json"))
        e = json.loads(exp[0].read_text()) if exp else {}
        p0 = e.get("p0") or (e.get("provenance_video") or {}).get("p0") or {}   # the driver's post-leg record
        m = p0.get("mandate") if isinstance(p0.get("mandate"), dict) else None
        pre_ok, post_ok = isinstance(p0.get("d0_pre"), dict), isinstance(p0.get("d0_post"), dict)   # 'unavailable: ...' is a string
        present = bool(exp) and pre_ok and post_ok and m is not None
        clean = present and not viol_file and m.get("mandate_violation") is False
        ev.update({"rule": "no MANDATE_VIOLATION.json AND the export's p0 block (the driver's post-leg record) holds d0_pre and "
                           "d0_post read-backs and a mandate with mandate_violation false (absence fails)",
                   "mandate_violation_file": viol_file, "export": exp[0].name if exp else None,
                   "d0_pre_present": pre_ok, "d0_post_present": post_ok,
                   "mandate": m, "task_pids": [p0.get("probe_pid"), p0.get("post_pid")]})
    else:
        exp = sorted(d.glob("export_*.json"))
        cp = container_procs(json.loads(exp[0].read_text())) if exp else {"containers": {}}
        cs = cp.get("containers") or {}
        checks = []
        for c, x in cs.items():
            for when in ("leg_start", "leg_end"):
                w = x.get(when) or {}
                checks.append({"container": c, "when": when, "n": w.get("n"), "workers_1": "--workers 1" in (w.get("top_cmd") or "")})
        present = bool(exp) and bool(cs)
        clean = (present and len(cs) == 1 and len(checks) == 2
                 and all(k["n"] == 1 and k["workers_1"] for k in checks))
        ev.update({"rule": "the export's lifetime_state shows exactly ONE container at leg start and leg end, ONE process "
                           "each time, whose command line carries '--workers 1' (absence fails)",
                   "export": exp[0].name if exp else None, "containers": sorted(cs), "checks": checks,
                   "service_peak_process_count": cp.get("service_peak_process_count")})
    ev["evidence_present"] = present
    ev["outcome"] = "CLEAN" if clean else ("VIOLATION" if present else "EVIDENCE MISSING")
    record(camp, f"G_d0_{leg}", ev)
    return 0 if clean else (1 if present else 2)


# ------------------------------------------------------------------ G_cell
def max_in_flight(rs: List[Dict[str, Any]]) -> int:
    ev = []
    for r in rs:
        if r.get("admit_ns") is not None and r.get("done_ns") is not None:
            ev.append((r["admit_ns"], 1))
            ev.append((r["done_ns"], -1))
    ev.sort(key=lambda x: (x[0], x[1]))          # a video done at the same ns as another's admit is not overlapping
    c = m = 0
    for _, dl in ev:
        c += dl
        m = max(m, c)
    return m


def cell(camp: Path, leg: str, arm: str, k: int, t: int, omp: str, n: int) -> int:
    d = camp / leg
    rbf = d / "p1_readback.json"
    rb = json.loads(rbf.read_text()) if rbf.exists() else None
    rec = sorted(d.glob("records_*.jsonl"))
    meas = [r for r in rows(rec[0]) if r.get("role") == "measured"] if rec else []
    last: Dict[str, Dict[str, Any]] = {}
    for r in meas:                                  # the driver's rule: the LAST record per video
        last[r["video"]] = r
    ok = [r for r in last.values() if "error" not in r]
    frames = sum(r.get("frames_observed") or 0 for r in ok)
    st = [r for r in rows(d / "p1_stamps.jsonl") if r.get("kind", "frame") == "frame"]
    st.sort(key=lambda r: r["t_wall"])
    tail = st[-frames:] if frames and len(st) >= frames else []
    env = (rb or {}).get("env") or {}
    torch_t = (rb or {}).get("torch", {}).get("num_threads") if isinstance((rb or {}).get("torch"), dict) else None
    mif = max_in_flight(list(last.values()))
    c = {"readback_present": rb is not None,
         "torch_num_threads_eq_T": torch_t == t,
         "env_OMP_NUM_THREADS_eq_T": env.get("OMP_NUM_THREADS") == str(t),
         "omp_wait_policy_as_declared": (env.get("OMP_WAIT_POLICY") == "ACTIVE") if omp == "ACTIVE" else ("OMP_WAIT_POLICY" not in env),
         "videos_eq_n": len(last) == n,
         "max_in_flight_eq_K": mif == k,
         "stamps_cover_measured_frames": bool(tail) and len(tail) == frames,
         "every_measured_frame_has_forward": bool(tail) and all(r.get("forward") is not None for r in tail)}
    present = rb is not None and bool(rec) and bool(st)
    passed = present and all(c.values())
    record(camp, f"G_cell_{leg}", {
        "leg": leg, "declared": {"arm": arm, "K": k, "T": t, "OMP_WAIT_POLICY": omp, "videos": n},
        "read_back": {"torch_num_threads": torch_t, "OMP_NUM_THREADS": env.get("OMP_NUM_THREADS"),
                      "OMP_WAIT_POLICY": env.get("OMP_WAIT_POLICY", "ABSENT"), "detector_pid": (rb or {}).get("pid"),
                      "videos": len(last), "videos_without_error": len(ok), "max_in_flight": mif,
                      "measured_frames": frames, "stamp_frame_rows": len(st)},
        "checks": c, "rule": "preregistration.json P4_A_video_concurrency.gates.G_cell",
        "outcome": "PASS" if passed else ("FAIL" if present else "EVIDENCE MISSING")})
    return 0 if passed else (1 if present else 2)


# ------------------------------------------------------------------ G_correct
def correct(camp: Path, name: str, pairs: List[List[str]]) -> int:
    res, missing = [], []
    for a, b in pairs:
        la, lb = load(camp / a), load(camp / b)
        if la is None or lb is None:
            missing.append([a, b])
            continue
        i = identity(la, lb)
        i["videos_eq_16"] = i["videos_compared"] == VIDEOS
        i["pass"] = i["identical"] and i["videos_eq_16"]
        res.append(i)
    ok = bool(res) and not missing and all(x["pass"] for x in res)
    record(camp, name, {"pairs": res, "missing": missing,
                        "rule": "every pair output-identical (per-video chunk sha256 AND frame scores) with videos_compared == 16",
                        "outcome": "PASS" if ok else ("FAIL" if res and not missing else "EVIDENCE MISSING")})
    return 0 if ok else (1 if res and not missing else 2)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    a = sys.argv[1:]
    try:
        if a[0] == "alone":
            return alone()
        if a[0] == "memstat":
            return p2_gates.memstat(Path(a[1]), a[2])
        if a[0] == "d0" and a[3] in ("rr", "li"):
            return d0(Path(a[1]), a[2], a[3])
        if a[0] == "cell" and a[3] in ("rr", "li") and a[6] in ("ACTIVE", "unset"):
            return cell(Path(a[1]), a[2], a[3], int(a[4]), int(a[5]), a[6], int(a[7]))
        if a[0] == "correct" and len(a) >= 5 and len(a[3:]) % 2 == 0:
            return correct(Path(a[1]), a[2], [a[3:][i:i + 2] for i in range(0, len(a[3:]), 2)])
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    except IndexError:
        pass
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
