#!/usr/bin/env python3
"""P6 gates, computed exactly as preregistration.json states them; the chain decides from these exit codes. Every gate has a
positive and a null control run WHOLE on the box before launch (p6_gate_controls.py). P5's gates are reused unchanged
(alone, memstat, d0, canary, correct); P6 adds:

    p6_gates.py cell   <camp> <leg> stock|p5|li <K> <T> <n> <image_id> [unset]
                       P5's G_cell; with 'unset' the six thread variables must be ABSENT from the detector's environment
                       (the out-of-box posture) while torch still reads back T threads in-process
    p6_gates.py warm   <camp> <leg> <sends> <concurrency>
                       G_warm: the leg's warm-up ledger declares and shows exactly that warm set, every send served
    p6_gates.py smoke  <camp>
                       G_smoke_P6B: correctness in both rounds AND Q1 in round 1 AND round 2 AND pooled

Exit 0 = pass / clean / fired, 1 = fail / not fired, 2 = evidence missing. Records go to <camp>/gates/<gate>.json, create-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p5_gates  # noqa: E402
from p4_gates import record  # noqa: E402

SIX = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS")


def cell(camp: Path, leg: str, fl: str, k: int, t: int, n: int, image_id: str, unset: bool) -> int:
    if not unset:
        return p5_gates.cell(camp, leg, fl, k, t, n, image_id)
    # the out-of-box posture: run P5's checks, then replace the env clause (OMP_NUM_THREADS == T) with 'the six vars absent'
    rc = p5_gates.cell(camp, leg, fl, k, t, n, image_id)
    f = camp / "gates" / f"G_cell_{leg}.json"
    rec = json.loads(f.read_text()) if f.exists() else None
    if rec is None:
        return rc
    rbf = camp / leg / ("p5_readback.json" if fl == "p5" else "p1_readback.json")
    env = (json.loads(rbf.read_text()).get("env") or {}) if rbf.exists() else {}
    checks = dict(rec["checks"])
    checks.pop("env_OMP_NUM_THREADS_eq_T", None)
    checks["six_thread_vars_absent"] = rbf.exists() and not any(v in env for v in SIX)
    present = rec["outcome"] != "EVIDENCE MISSING"
    passed = present and all(checks.values())
    f.unlink()                                   # the P5 record is replaced by the P6 decision on the same evidence (same run)
    record(camp, f"G_cell_{leg}", {**{k2: v for k2, v in rec.items() if k2 not in ("gate", "decided_utc", "checks", "outcome", "rule")},
                                   "checks": checks, "posture": "out of box: the six thread variables unset",
                                   "env_seen": {v: env.get(v) for v in SIX}, "rule": "preregistration.json gates.G_cell (unset form)",
                                   "outcome": "PASS" if passed else ("FAIL" if present else "EVIDENCE MISSING")})
    return 0 if passed else (1 if present else 2)


def warm(camp: Path, leg: str, sends: int, conc: int) -> int:
    d = camp / leg
    wf = sorted(d.glob("warmup_*.json"))
    w = json.loads(wf[0].read_text()) if wf else None
    c = {"ledger_present": w is not None,
         "declared_sends": (w or {}).get("warm_sends_declared") == sends,
         "declared_concurrency": (w or {}).get("warm_concurrency_declared") == conc,
         "sends_in_ledger": len((w or {}).get("sends") or []) == sends,
         "every_send_served": bool((w or {}).get("sends")) and all(e.get("error") is None for e in w["sends"]),
         "policy_is_p6": "P6 warm symmetry" in ((w or {}).get("policy") or "")}
    passed = all(c.values())
    record(camp, f"G_warm_{leg}", {"leg": leg, "declared": {"sends": sends, "concurrency": conc}, "checks": c,
                                   "policy": (w or {}).get("policy"),
                                   "outcome": "PASS" if passed else ("FAIL" if w is not None else "EVIDENCE MISSING")})
    return 0 if passed else (1 if w is not None else 2)


def smoke(camp: Path) -> int:
    from p6_analyse import analyse_a  # noqa: E402  (the same code the report uses)
    a = analyse_a(camp)
    q1 = (a.get("readings") or {}).get("Q1") or {}
    corr = (a.get("correctness") or {}).get("gate_pass")
    parts = {k: (q1.get(k) or {}).get("holds") for k in ("round_1", "round_2", "pooled")}
    evaluable = corr is not None and None not in parts.values()
    fired = bool(evaluable and corr and all(parts.values()))
    record(camp, "G_smoke_P6B", {"rule": "fires iff correctness holds in both rounds AND Q1 (P5 f/s / LI f/s >= 0.95) holds in round 1 AND round 2 AND pooled",
                                 "correctness_both_rounds": corr, "Q1": q1, "Q2_reported_not_gating": (a.get("readings") or {}).get("Q2"),
                                 "outcome": "FIRED" if fired else ("NOT FIRED" if evaluable else "NOT EVALUABLE")})
    return 0 if fired else (1 if evaluable else 2)


def main() -> int:
    a = sys.argv[1:]
    try:
        if a[0] == "cell" and a[3] in ("stock", "p5", "li"):
            return cell(Path(a[1]), a[2], a[3], int(a[4]), int(a[5]), int(a[6]), a[7], len(a) > 8 and a[8] == "unset")
        if a[0] == "warm":
            return warm(Path(a[1]), a[2], int(a[3]), int(a[4]))
        if a[0] == "smoke":
            return smoke(Path(a[1]))
        if a[0] in ("alone", "memstat", "d0", "canary", "correct"):
            sys.argv = [sys.argv[0]] + a
            return p5_gates.main()
    except FileExistsError as e:
        print(f"REFUSED: this gate was already decided ({e})")
        return 2
    except IndexError:
        pass
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
