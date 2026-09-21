#!/usr/bin/env python3
"""Decide, mechanically, whether the batch envelope needs K=512 — per arm, from the data.

    batchsize_envelope_decide.py <stage4_campaign_dir> <floors.json> <out.json>

THE RULE, fixed before any 10k K=256 figure exists (Stage 4 ruling, leg 11): run K=512 on an arm
only if that arm's full-scale K=128 -> K=256 change exceeds the arm's measured noise floor. A
pair inside its own noise is FLAT, and 512 is skipped with the delta and the floor recorded.

THE FLOOR comes from <floors.json>, the warm replicate spreads measured at smoke scale — the
only replicates that exist, since every full-scale K runs once. It is read from a file written
BEFORE this script runs, so the threshold cannot be chosen after the delta is seen.

THROUGHPUT is judged to the 99th-percentile completion, not on span: at full scale one document
(039_039660.pdf) set the engine arm's span by 1,738 s past p99, so a span delta between two K
would measure where that document landed, not the batch size. Both are recorded; p99 decides.

Prints one line per arm and exits 0; the chain reads the RUN_512 lines. Prints its own sha256.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def p99_throughput(perdoc: Path) -> Optional[Dict[str, float]]:
    rows = [json.loads(x) for x in perdoc.read_text().splitlines() if x.strip()]
    ok = sorted((r for r in rows if r.get("ok")), key=lambda r: r["completion_ns"])
    if len(ok) < 100:
        return None
    t0 = min(r["submit_ns"] for r in rows)
    k99 = int(0.99 * len(ok))
    t99 = (ok[k99 - 1]["completion_ns"] - t0) / 1e9
    span = (max(r["completion_ns"] for r in rows) - t0) / 1e9
    return {"to_p99": round(k99 / t99, 4), "span": round(len(ok) / span, 4)}


def find(d: Path, arm: str, k: int) -> Optional[Path]:
    hits = sorted(d.glob(f"*/perdoc_{arm}_k{k}_*.jsonl"))
    return hits[0] if hits else None


def main() -> int:
    print(f"batchsize_envelope_decide.py sha256: "
          f"{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}", file=sys.stderr)
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    d, floors_path, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    floors = json.loads(floors_path.read_text())
    if out_path.exists():
        print(f"REFUSED: {out_path} exists — append-only", file=sys.stderr)
        return 3
    decision: Dict[str, Any] = {"rule": "run K=512 on an arm iff |K256/K128 - 1| on p99 "
                                        "throughput exceeds that arm's warm replicate floor",
                                "floors_source": str(floors_path), "arms": {}}
    for arm in ("rr", "li"):
        a, b = find(d, arm, 128), find(d, arm, 256)
        floor = floors.get(arm)
        if not a or not b or floor is None:
            decision["arms"][arm] = {"run_512": False, "verdict": "NOT DECIDABLE",
                                     "reason": f"missing: k128={bool(a)} k256={bool(b)} "
                                               f"floor={floor}"}
            print(f"RUN_512 {arm} no NOT_DECIDABLE")
            continue
        ta, tb = p99_throughput(a), p99_throughput(b)
        if not ta or not tb:
            decision["arms"][arm] = {"run_512": False, "verdict": "NOT DECIDABLE",
                                     "reason": "too few completed documents"}
            print(f"RUN_512 {arm} no NOT_DECIDABLE")
            continue
        delta = tb["to_p99"] / ta["to_p99"] - 1
        run = abs(delta) > floor
        decision["arms"][arm] = {
            "k128": ta, "k256": tb, "delta_p99": round(delta, 4), "floor": floor,
            "run_512": run,
            "verdict": ("RUN K=512 — the K=128->256 change exceeds the arm's noise" if run else
                        "SKIP K=512 — the K=128->256 pair is flat within the arm's noise")}
        print(f"RUN_512 {arm} {'yes' if run else 'no'} delta={delta:+.4f} floor={floor}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(decision, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
