#!/usr/bin/env python3
"""P5 gates, computed exactly as preregistration.json states them; the chain decides from these exit codes. Every gate has a
positive and a null control run WHOLE on the box before launch (p5_gate_controls.py).

    p5_gates.py alone                                              G_alone: exit 1 iff any container exists
    p5_gates.py memstat <camp> <leg>                               G_memstat: memstat.jsonl has >= 1 row
    p5_gates.py d0      <camp> <leg> rr|li                         G_d0: D0 present and clean; RR: exactly ONE LWDETR, pre and post
    p5_gates.py cell    <camp> <leg> stock|p5|li <K> <T> <n> <image_id>
                                                                   G_cell: the leg measured the cell it names
    p5_gates.py canary  <camp> <leg> <manifest.json> <prefix>      G_canary: the canary ran on exactly the manifest's frames
    p5_gates.py correct <camp> <name> <legA> <legB> [...]          G_correct: every pair output-identical, 16/16 (or --n N)
    p5_gates.py smoke   <camp>                                     G_smoke_P5B: S1 AND S2 (pooled) with correctness passed

Legs are directories <camp>/<leg> (a pair member may also be an absolute path to a committed leg). Exit 0 = pass /
clean / fired, 1 = fail / violation / not fired, 2 = evidence missing. Records go to <camp>/gates/<gate>.json, create-only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import identity, load  # noqa: E402
import p4_gates  # noqa: E402
from p4_gates import max_in_flight, record, rows  # noqa: E402

VIDEOS = 16


# ------------------------------------------------------------------ G_d0 (P4's, plus exactly one LWDETR for RR)
def d0(camp: Path, leg: str, arm: str) -> int:
    d = camp / leg
    if arm == "li":
        return p4_gates.d0(camp, leg, "li")
    viol_file = (d / "MANDATE_VIOLATION.json").exists()
    exp = sorted(d.glob("export_*.json"))
    e = json.loads(exp[0].read_text()) if exp else {}
    p0 = e.get("p0") or (e.get("provenance_video") or {}).get("p0") or {}
    m = p0.get("mandate") if isinstance(p0.get("mandate"), dict) else None
    counts = {}
    for k in ("d0_pre", "d0_post"):
        x = p0.get(k)
        roots = (x.get("root_modules_with_params") or {}) if isinstance(x, dict) else None
        counts[k] = None if roots is None else {c: r.get("count") for c, r in roots.items() if "LWDETR" in c}
    present = bool(exp) and all(isinstance(p0.get(k), dict) for k in ("d0_pre", "d0_post")) and m is not None
    one = present and all(v is not None and len(v) == 1 and list(v.values())[0] == 1 for v in counts.values())
    clean = present and not viol_file and m.get("mandate_violation") is False and one
    record(camp, f"G_d0_{leg}", {"leg": leg, "arm": arm,
                                 "rule": "no MANDATE_VIOLATION.json AND the export's p0 block holds d0_pre and d0_post (dicts) and a mandate with "
                                         "mandate_violation false AND exactly ONE LWDETR root module in both (absence fails)",
                                 "mandate_violation_file": viol_file, "mandate": m, "lwdetr_counts": counts,
                                 "evidence_present": present, "outcome": "CLEAN" if clean else ("VIOLATION" if present else "EVIDENCE MISSING")})
    return 0 if clean else (1 if present else 2)


# ------------------------------------------------------------------ G_cell
def cell(camp: Path, leg: str, flavour: str, k: int, t: int, n: int, image_id: str) -> int:
    d = camp / leg
    stamp_f, rb_f = (("p5_stamps.jsonl", "p5_readback.json") if flavour == "p5" else ("p1_stamps.jsonl", "p1_readback.json"))
    rb = json.loads((d / rb_f).read_text()) if (d / rb_f).exists() else None
    rec = sorted(d.glob("records_*.jsonl"))
    meas = [r for r in rows(rec[0]) if r.get("role") == "measured"] if rec else []
    last: Dict[str, Dict[str, Any]] = {}
    for r in meas:
        last[r["video"]] = r
    ok = [r for r in last.values() if "error" not in r]
    frames = sum(r.get("frames_observed") or 0 for r in ok)
    st = [r for r in rows(d / stamp_f) if r.get("kind", "frame") == "frame"]
    st.sort(key=lambda r: r["t_wall"])
    tail = st[-frames:] if frames and len(st) >= frames else []
    env = (rb or {}).get("env") or {}
    torch_t = (rb or {}).get("torch", {}).get("num_threads") if isinstance((rb or {}).get("torch"), dict) else None
    img = (d / "container_image_id.txt").read_text().strip() if (d / "container_image_id.txt").exists() else None
    c = {"readback_present": rb is not None,
         "torch_num_threads_eq_T": torch_t == t,
         "env_OMP_NUM_THREADS_eq_T": env.get("OMP_NUM_THREADS") == str(t),
         "omp_wait_policy_absent": "OMP_WAIT_POLICY" not in env,
         "container_image_as_declared": img == image_id,
         "videos_eq_n": len(last) == n,
         "max_in_flight_eq_K": max_in_flight(list(last.values())) == min(k, n),
         "stamps_cover_measured_frames": bool(tail) and len(tail) == frames,
         "every_measured_frame_has_forward": bool(tail) and all(r.get("forward") is not None for r in tail)}
    if flavour == "p5":
        c["node_is_p5_stamped"] = (rb or {}).get("node") == "p5-infer stamped"
        c["threads_read_on_the_inference_thread"] = ((rb or {}).get("readback_thread") or {}).get("name") == "detect-infer"
        c["one_inference_thread_ran_every_forward"] = bool(tail) and len({r.get("infer_tid") for r in tail}) == 1
    present = rb is not None and bool(rec) and bool(st)
    passed = present and all(c.values())
    record(camp, f"G_cell_{leg}", {"leg": leg, "declared": {"flavour": flavour, "K": k, "T": t, "videos": n, "image_id": image_id},
                                   "read_back": {"torch_num_threads": torch_t, "OMP_NUM_THREADS": env.get("OMP_NUM_THREADS"),
                                                 "OMP_WAIT_POLICY": env.get("OMP_WAIT_POLICY", "ABSENT"), "container_image_id": img,
                                                 "videos": len(last), "max_in_flight": max_in_flight(list(last.values())),
                                                 "measured_frames": frames, "stamp_frame_rows": len(st),
                                                 "node": (rb or {}).get("node"), "readback_thread": (rb or {}).get("readback_thread"),
                                                 "infer_tids": sorted({r.get("infer_tid") for r in tail if r.get("infer_tid") is not None})},
                                   "checks": c, "rule": "preregistration.json gates.G_cell",
                                   "outcome": "PASS" if passed else ("FAIL" if present else "EVIDENCE MISSING")})
    return 0 if passed else (1 if present else 2)


# ------------------------------------------------------------------ G_canary
def canary(camp: Path, leg: str, manifest: Path, prefix: str) -> int:
    d = camp / leg
    b = json.loads((d / "bench.json").read_text()) if (d / "bench.json").exists() else None
    man = [(r["frame"], r["sha256"]) for r in json.loads(manifest.read_text())["frames"] if r["frame"].startswith(prefix + "/")]
    got = [(r["frame"], r["frame_sha256"]) for r in (b or {}).get("rows", [])]
    rb = (b or {}).get("readback") or {}
    c = {"bench_present": b is not None, "frames_identical_to_manifest_subset": bool(man) and got == man,
         "one_model_instance": (b or {}).get("one_model_instance") is True,
         "torch_num_threads_eq_4": (rb.get("torch") or {}).get("num_threads") == 4,
         "every_frame_measured": bool(got) and all(r.get("forward") for r in (b or {}).get("rows", []))}
    passed = all(c.values())
    record(camp, f"G_canary_{leg}", {"leg": leg, "manifest_subset": prefix, "frames_expected": len(man), "frames_got": len(got),
                                     "checks": c, "outcome": "PASS" if passed else ("FAIL" if b is not None else "EVIDENCE MISSING")})
    return 0 if passed else (1 if b is not None else 2)


# ------------------------------------------------------------------ G_correct
def correct(camp: Path, name: str, pairs: List[List[str]], n: int = VIDEOS) -> int:
    res, missing = [], []
    for a, b in pairs:
        pa, pb = (Path(a) if a.startswith("/") else camp / a), (Path(b) if b.startswith("/") else camp / b)
        la, lb = load(pa), load(pb)
        if la is None or lb is None:
            missing.append([a, b])
            continue
        i = identity(la, lb)
        i["videos_eq_n"] = i["videos_compared"] == n
        i["pass"] = i["identical"] and i["videos_eq_n"]
        res.append(i)
    ok = bool(res) and not missing and all(x["pass"] for x in res)
    record(camp, name, {"pairs": res, "missing": missing, "n": n,
                        "rule": f"every pair output-identical (per-video chunk sha256 AND frame scores) with videos_compared == {n}",
                        "outcome": "PASS" if ok else ("FAIL" if res and not missing else "EVIDENCE MISSING")})
    return 0 if ok else (1 if res and not missing else 2)


# ------------------------------------------------------------------ G_smoke_P5B
def smoke(camp: Path) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from p5_analyse_a import analyse  # noqa: E402  (the same code the report uses)
    a = analyse(camp)
    r = a["readings"]
    corr = (a.get("correctness") or {}).get("gate_pass")
    s1, s2 = (r.get("S1") or {}).get("pooled", {}).get("holds"), (r.get("S2") or {}).get("pooled", {}).get("holds")
    evaluable = s1 is not None and s2 is not None and corr is not None
    fired = bool(evaluable and corr and s1 and s2)
    record(camp, "G_smoke_P5B", {"rule": "fires iff the correctness gate passed AND S1 holds AND S2 holds (pooled; per round reported beside)",
                                 "correctness_gate": corr, "S1": r.get("S1"), "S2": r.get("S2"),
                                 "outcome": "FIRED" if fired else ("NOT FIRED" if evaluable else "NOT EVALUABLE")})
    return 0 if fired else (1 if evaluable else 2)


def main() -> int:
    a = sys.argv[1:]
    try:
        if a[0] == "alone":
            return p4_gates.alone()
        if a[0] == "memstat":
            return p4_gates.p2_gates.memstat(Path(a[1]), a[2])
        if a[0] == "d0" and a[3] in ("rr", "li"):
            return d0(Path(a[1]), a[2], a[3])
        if a[0] == "cell" and a[3] in ("stock", "p5", "li"):
            return cell(Path(a[1]), a[2], a[3], int(a[4]), int(a[5]), int(a[6]), a[7])
        if a[0] == "canary":
            return canary(Path(a[1]), a[2], Path(a[3]), a[4])
        if a[0] == "correct" and len(a) >= 5:
            n = VIDEOS
            rest = a[3:]
            if rest[:1] == ["--n"]:
                n, rest = int(rest[1]), rest[2:]
            if rest and len(rest) % 2 == 0:
                return correct(Path(a[1]), a[2], [rest[i:i + 2] for i in range(0, len(rest), 2)], n)
        if a[0] == "smoke":
            return smoke(Path(a[1]))
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    except IndexError:
        pass
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
