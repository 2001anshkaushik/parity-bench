#!/usr/bin/env python3
"""S5-E (thread variables unset vs =1 at one token, docs) and S5-F (the SDK default-5 equivalent).

    batchsize_analyse_s5ef.py <campaign_dir> [--out report.json]

Written, like the pre-registration it follows, BEFORE any of these legs ran (2026-09-22).

  S5-E  per posture: the two runs' docs/s, their spread, the mean; the posture effect is
        mean(unset) / mean(=1) - 1. It is READABLE only if it exceeds every noise measure available:
        the 0.82% Stage 3b floor, each posture pair's own spread, and S5-C's measured null-control
        spread (1.63%, same slice). Torch's intra-op count is read back INSIDE the task process for
        every leg; a leg whose read-back does not match its posture is excluded, named.
  S5-F  C=5 against this launch's own C=32 at the same posture (same session), and against
        Stage 3b's C=4, C=8 and C=32 on the same slice and posture (CROSS-SESSION: an earlier
        harness session, so a ranking context, not a like-for-like delta).
  Both  span docs/s is primary; docs/s to p90 is reported beside it — a diagnostic defined before
        the legs ran, because one 791-page document sets this slice's span.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
FLOOR = 0.0082
S5C_SPREAD_FILE = ROOT / "working/results/batchsize_s5_20260921T205917Z/analysis_s5c_smt.json"
S3B_FILE = ROOT / "working/results/batchsize_s3b_20260920T203139Z/analysis_docs_384.json"
LEGS = {"env1": ["rr_env1_a", "rr_env1_b"], "unset": ["rr_unset_a", "rr_unset_b"], "c5": ["rr_c5_a", "rr_c5_b"]}


def spread(a: float, b: float) -> float:
    return abs(a - b) / ((a + b) / 2)


def leg(d: Path) -> Optional[Dict[str, Any]]:
    gs = sorted(d.glob("leg_rr_refc*_*.json"))
    if not gs:
        return None
    g = json.loads(gs[0].read_text())
    rows = [json.loads(x) for x in sorted(d.glob("perdoc_rr_refc*_*.jsonl"))[0].read_text().splitlines() if x.strip()]
    t0 = min(r["submit_ns"] for r in rows)
    ok = sorted((r for r in rows if r.get("ok")), key=lambda r: r["completion_ns"])
    k90 = int(0.9 * len(ok))
    last = max(rows, key=lambda r: r["completion_ns"])
    ep = d / "export_path.txt"
    exp = None
    if ep.exists():
        name = Path(ep.read_text().strip()).name
        for cand in (d.parent / name, ROOT / "working/results" / name):
            if cand.exists():
                exp = json.loads(cand.read_text())["data"]
                break
    post = (exp or {}).get("posture") or {}
    rb = post.get("in_process_readback") or {}
    return {"verdict": g.get("verdict"), "reference_c": g.get("reference_c"),
            "docs_per_s": g["throughput"]["docs_per_s"], "span_s": g["throughput"]["span_s"],
            "docs_per_s_to_p90": round(k90 / ((ok[k90 - 1]["completion_ns"] - t0) / 1e9), 4),
            "span_set_by": last["doc"], "ok": g["documents"]["ok"],
            "cpu_s_per_doc": g["cost"].get("cpu_s_per_doc"), "engine_cores": g["cost"].get("engine_container_cores"),
            "idle_core_equivalents": (g.get("percore_host") or {}).get("idle_core_equivalents"),
            "thread_env_declared": post.get("thread_env_expected"),
            "thread_env_in_process": rb.get("env"), "torch_threads_in_process": rb.get("torch_num_threads"),
            "export": (ep.read_text().strip() if ep.exists() else None)}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    d = Path(sys.argv[1])
    cells = {k: {n: leg(d / n) for n in names if (d / n).is_dir()} for k, names in LEGS.items()}
    rep: Dict[str, Any] = {"campaign_dir": str(d), "legs": cells,
                           "preregistration": json.loads((d / "preregistration.json").read_text())
                           if (d / "preregistration.json").exists() else None}
    # posture read-back: =1 must read 1 inside the task process; unset must read no variable set
    excluded: List[Dict[str, Any]] = []
    for k in ("env1", "unset", "c5"):
        for n, g in list(cells[k].items()):
            if g is None:
                excluded.append({"leg": n, "why": "no leg file"}); cells[k].pop(n); continue
            want_env1 = k in ("env1", "c5")
            env = g["thread_env_in_process"] or {}
            ok = (all(v == "1" for v in env.values()) and len(env) == 6) if want_env1 else all(v in (None, "") for v in env.values())
            if not ok or g["verdict"] != "OK":
                excluded.append({"leg": n, "why": "posture read-back does not match, or the leg did not complete",
                                 "in_process_env": env, "verdict": g["verdict"]}); cells[k].pop(n)
    rep["excluded"] = excluded
    s5c = json.loads(S5C_SPREAD_FILE.read_text()) if S5C_SPREAD_FILE.exists() else {}
    s5c_spread = (s5c.get("null_control") or {}).get("spread")

    def pair(k: str, metric: str) -> Optional[Dict[str, Any]]:
        v = [g[metric] for g in cells[k].values()]
        if len(v) < 2:
            return None
        return {"runs": v, "mean": round(sum(v) / len(v), 4), "spread": round(spread(v[0], v[1]), 4)}

    s5e: Dict[str, Any] = {}
    for metric in ("docs_per_s", "docs_per_s_to_p90", "cpu_s_per_doc"):
        a, b = pair("env1", metric), pair("unset", metric)
        row: Dict[str, Any] = {"env1": a, "unset": b}
        if a and b:
            eff = b["mean"] / a["mean"] - 1
            tol = max([FLOOR, a["spread"], b["spread"]] + ([s5c_spread] if s5c_spread else []))
            row.update(unset_vs_env1=round(eff, 4), tolerance=round(tol, 4),
                       tolerance_basis="max(0.82% floor, each pair's own spread, S5-C null-control spread)",
                       readable=abs(eff) > tol, vs_0_82_floor=("beyond" if abs(eff) > FLOOR else "within"))
        s5e[metric] = row
    s5e["torch_threads_in_process"] = {k: sorted({g["torch_threads_in_process"] for g in cells[k].values()}, key=str)
                                       for k in ("env1", "unset")}
    rep["s5e"] = s5e

    s3b = json.loads(S3B_FILE.read_text()) if S3B_FILE.exists() else {}
    curve = ((s3b.get("ranking") or {}).get("rr") or {}).get("call", {}).get("continuous_knee", {}).get("curve", {})
    c5 = pair("c5", "docs_per_s")
    e1 = pair("env1", "docs_per_s")
    rep["s5f"] = {"label": "SDK default-5 equivalent (PR #1895 / TypeScript maxConcurrent)",
                  "c5": c5, "c5_to_p90": pair("c5", "docs_per_s_to_p90"),
                  "same_session_c32_env1_mean": e1["mean"] if e1 else None,
                  "c5_over_same_session_c32": (round(c5["mean"] / e1["mean"], 4) if c5 and e1 else None),
                  "cross_session_stage3b_curve": {c: curve.get(c) for c in ("4", "8", "32")},
                  "cross_session_note": "Stage 3b ran in an earlier harness session: a ranking context, not a like-for-like delta"}
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only")
            return 3
        p.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
