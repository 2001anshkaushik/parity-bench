#!/usr/bin/env python3
"""S5-B analysis — correctness FIRST, timing only for a batch size that passed.

    batchsize_analyse_s5b.py <s5b_out_dir> <stock_leg_dir> [--out report.json]

<s5b_out_dir>/rr_k16_B{1,2,4,8}/ are the patched-image legs (records_*.jsonl from the unmodified
video driver, s5b_tap.jsonl from the patched node, engine_memory.json, export_*.json).
<stock_leg_dir> is a stock rr:patched-video leg on the SAME 16 videos (its records' chunk hashes
are the reference; the stock pipeline was measured deterministic across runs and across K).

ORDER, from the ruling:
  NULL CONTROL  patched B=1 vs stock: chunk_sha256 identical on every video. B=1 goes through the
                patch's NEW batched code path, so this tests the patch itself. If it fails, the
                patch changed the output before any batching happened, and S5-B STOPS.
  TIER 1        B>1 vs patched B=1: chunk_sha256 identical on every video -> PASS (bit-identical).
  TIER 2        otherwise, per frame from the taps: identical label multisets and counts OUTSIDE
                +/-0.001 of the 0.3 threshold, max |score delta| <= 1e-5, max box delta <= 1e-3 px
                (the tap's boxes are already in OUTPUT pixels) -> PASS labelled NUMERICALLY
                EQUIVALENT. Else that B is a different measurement, not an optimisation.
  TIMING        reported ONLY for a B that passed; every figure labelled PATCHED-ENGINE.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batchsize_analyse_video as bav  # noqa: E402

THR, BAND, MAX_SCORE, MAX_BOX = 0.3, 0.001, 1e-5, 1e-3
LABEL = "PATCHED-ENGINE, NOT OUT-OF-THE-BOX"


def records(leg: Path) -> Dict[str, Dict[str, Any]]:
    fs = sorted(glob.glob(str(leg / "records_*.jsonl")))
    if not fs:
        return {}
    return {r["video"]: r for r in (json.loads(l) for l in Path(fs[0]).read_text().splitlines() if l.strip())
            if r.get("role") == "measured"}


def taps(leg: Path) -> Dict[tuple, List[Dict[str, Any]]]:
    f = leg / "s5b_tap.jsonl"
    if not f.exists():
        return {}
    return {(r["video"], r["frame"]): r["dets"] for r in (json.loads(l) for l in f.read_text().splitlines() if l.strip())}


def tier2_frame(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    A = [d for d in a if abs(d["score"] - THR) > BAND]
    B = [d for d in b if abs(d["score"] - THR) > BAND]
    if sorted(d["label"] for d in A) != sorted(d["label"] for d in B):
        return {"ok": False, "why": "label multiset or count differs outside the threshold band"}
    pool, ws, wb = list(B), 0.0, 0.0
    for d in A:
        k = lambda x: max(abs(x["box"][c] - d["box"][c]) for c in ("x1", "y1", "x2", "y2"))  # noqa: E731
        m = min((x for x in pool if x["label"] == d["label"]), key=k)
        pool.remove(m)
        ws, wb = max(ws, abs(m["score"] - d["score"])), max(wb, k(m))
    return {"ok": ws <= MAX_SCORE and wb <= MAX_BOX, "max_score_delta": ws, "max_box_delta_px": wb}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out_dir, stock = Path(sys.argv[1]), Path(sys.argv[2])
    ref = records(stock)
    legs = {int(p.name.rsplit("_B", 1)[1]): p for p in out_dir.glob("rr_k16_B*") if p.is_dir()}
    rep: Dict[str, Any] = {"label": LABEL, "stock_reference": str(stock), "batch_sizes": sorted(legs)}
    if 1 not in legs or not ref:
        rep["verdict"] = "NOT RUN — the B=1 leg or the stock reference is missing"
        print(json.dumps(rep, indent=1)); return 3
    b1 = records(legs[1])
    common = sorted(set(ref) & set(b1))
    same = [v for v in common if ref[v]["chunk_sha256"] == b1[v]["chunk_sha256"]]
    rep["null_control_patched_B1_vs_stock"] = {"videos": len(common), "chunk_identical": len(same),
                                               "PASS": len(common) > 0 and len(same) == len(common)}
    if not rep["null_control_patched_B1_vs_stock"]["PASS"]:
        rep["verdict"] = ("STOP S5-B — the patch changed the output at B=1, before any batching; no B>1 "
                          "comparison can isolate batching")
        print(json.dumps(rep, indent=1)); return 1
    t1 = taps(legs[1])
    per_b: Dict[str, Any] = {}
    for B in sorted(legs):
        if B == 1:
            continue
        rb = records(legs[B])
        cv = sorted(set(b1) & set(rb))
        tier1 = len(cv) > 0 and all(b1[v]["chunk_sha256"] == rb[v]["chunk_sha256"] for v in cv)
        row: Dict[str, Any] = {"videos": len(cv), "tier1_bit_identical": tier1}
        if tier1:
            row["tier"] = "TIER 1 — BIT-IDENTICAL"
        else:
            tb = taps(legs[B])
            keys = sorted(set(t1) | set(tb))
            missing = [k for k in keys if k not in t1 or k not in tb]
            res = [tier2_frame(t1[k], tb[k]) for k in keys if k in t1 and k in tb]
            fails = [r for r in res if not r["ok"]]
            row.update(frames_compared=len(res), frames_missing_on_one_side=len(missing),
                       tier2_failing_frames=len(fails),
                       max_score_delta=max((r.get("max_score_delta", 0.0) for r in res), default=None),
                       max_box_delta_px=max((r.get("max_box_delta_px", 0.0) for r in res), default=None),
                       first_failure=fails[0] if fails else None)
            row["tier"] = ("TIER 2 — NUMERICALLY EQUIVALENT" if res and not fails and not missing
                           else "NEITHER — a different measurement, not an optimisation")
        per_b[str(B)] = row
    rep["correctness_by_b"] = per_b
    passing = [1] + [int(b) for b, r in per_b.items() if not r["tier"].startswith("NEITHER")]
    timing = {}
    for B in passing:
        row = bav.leg_row(legs[B])
        mem = {}
        mf = legs[B] / "engine_memory.json"
        if mf.exists():
            try:
                m = json.loads(mf.read_text())
                mem = {k: (round(v / 1048576, 1) if isinstance(v, int) else None) for k, v in m.items()}
            except json.JSONDecodeError:
                mem = {"note": "engine_memory.json unreadable"}
        pc = row.get("percore_host") or {}
        timing[str(B)] = {"LABEL": LABEL, "frames_per_s": row.get("frames_per_s"), "span_s": row.get("span_s"),
                          "effective_cores": row.get("effective_cores"), "cpu_util_of_box": row.get("cpu_util_of_box"),
                          "idle_core_equivalents": pc.get("idle_core_equivalents"),
                          "engine_memory_mb": mem}
    rep["timing_only_for_passing_b"] = timing
    rep["not_reported"] = [int(b) for b, r in per_b.items() if r["tier"].startswith("NEITHER")]
    rep["verdict"] = ("every B passed correctness" if not rep["not_reported"] else
                      f"B={rep['not_reported']} failed correctness and carry no timing")
    text = json.dumps(rep, indent=1)
    if "--out" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--out") + 1])
        if p.exists():
            print(f"REFUSED: {p} exists — append-only"); return 3
        p.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
