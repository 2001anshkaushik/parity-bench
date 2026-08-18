#!/usr/bin/env python3
"""Re-derive gates, verdicts and metrics from per-document records already on disk.

WHY. Defect #38: the 10k per-document blast completed (rc=0), its metrics computed correctly
from perdoc_{li,rr}_blast.jsonl — and the gate path read the empty SEQUENTIAL record set,
shipping "offered 9975 = successful 0 + ... -> FAIL" on both arms. The 9,975 records per arm
are durable; nothing about the gates requires re-running the leg. This tool is the general
answer: gates and verdicts are pure functions over the records, so any run directory can be
re-judged after a verdict-path fix without touching a service.

WHAT IT CAN AND CANNOT RE-DERIVE, stated up front:
  CAN     census (both dialects), self_duplication, duplication counts, workload ratio,
          determinism (when BOTH legs' records exist), throughput and latency metrics,
          corrected batch-position latency (see below)
  CANNOT  structure gates from blast records (no identity or vector fields are persisted)
          and cost/CPU (the sampler anchor is not recoverable post-hoc) — these report
          NOT RUN with the reason, never FAIL and never a guess.

DEFECT #39 CORRECTION, applied here for records written before the per-arm stamp fix: both
arms' rows carried ONE enqueue_ns taken before the first leg, so the second arm's
batch-position latency absorbed the first arm's entire leg. The corrected batch open is
min(admit_ns) over the arm's own rows — the first admission IS the batch start under a
client-pool blast — labelled derived, with the stale-stamp gap reported.

    python3 working/scripts/rederive_gates.py working/results/run10k_p2_blast_v2 --offered 9975
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import gates_shared as gs               # noqa: E402
from harness import metrics_shared as ms             # noqa: E402
from harness.jsonl_stream import read_completed      # noqa: E402
from harness.resultio import write_result            # noqa: E402

say = lambda m: print(m, flush=True)                 # noqa: E731


def load_leg(run_dir: Path, tag: str, leg: str):
    p = run_dir / f"perdoc_{tag}_{leg}.jsonl"
    if not p.exists():
        return None, f"{p.name} absent"
    rows, _done, torn = read_completed(p)
    return rows, (torn or f"{len(rows)} records")


def gate_rows_from(rows, arm_key: str):
    out, seen = [], []
    for b in rows:
        errored = not b.get("ok")
        row = {"doc": b["doc"], "errored": errored,
               "identity_ok": b.get("returned_doc_id") is not None or arm_key == "rr",
               "sha_header_ok": True,
               "reason": gs.to_leela_reason(b.get("error_class")),
               "n_chunks": b.get("n_chunks"), "chunk_sha256": b.get("chunk_sha256")}
        row["ok"] = gs.classify_ok(row.get("n_chunks"), errored)
        out.append(row)
        seen.append(b["doc"])
    return out, seen


def corrected_batchpos(rows):
    """Rows with the #39-corrected batch-open stamp, plus the correction's own evidence."""
    admits = [r["admit_ns"] for r in rows if r.get("admit_ns")]
    enqs = {r.get("enqueue_ns") for r in rows if r.get("enqueue_ns")}
    if not admits:
        return None, {"note": "no admit_ns on any row — pre-#29 records; nothing to correct"}
    t0 = min(admits)
    stale_gap_s = (t0 - min(enqs)) / 1e9 if enqs else None
    fixed = [{**r, "submit_ns": t0} for r in rows]
    return fixed, {
        "corrected_batch_open": "min(admit_ns) over this arm's own rows",
        "stale_stamp_gap_s": round(stale_gap_s, 1) if stale_gap_s is not None else None,
        "basis": ("DERIVED (defect #39): the recorded enqueue_ns predates this arm's leg "
                  "by stale_stamp_gap_s — under a client-pool blast the first admission IS "
                  "the batch open, so min(admit_ns) replaces it. Batch-position latency "
                  "includes in-batch queue wait by definition; comparable with Leela's "
                  "derived column only."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--offered", type=int, required=True,
                    help="documents offered per arm (the census denominator)")
    ap.add_argument("--warm-n", type=int, nargs="+", default=[0, 64])
    a = ap.parse_args()

    out = {"experiment": "rederive_gates", "run_dir": str(a.run_dir), "offered": a.offered,
           "source_note": ("pure re-derivation from per-document JSONL already on disk; "
                           "no service was contacted"), "arms": {}}
    overall_fail = []
    for tag, arm_name in (("li", "llamaindex_http_pdf"), ("rr", "rocketride_pdf")):
        arm_key = "lg" if tag == "li" else "rr"
        seq, seq_note = load_leg(a.run_dir, tag, "sequential")
        bl, bl_note = load_leg(a.run_dir, tag, "blast")
        say(f"\n{arm_name}: sequential={seq_note}; blast={bl_note}")
        arm: dict = {"legs": {"sequential": seq_note, "blast": bl_note}}

        basis_rows, basis = (seq, "sequential") if seq else (bl, "blast") if bl else (None,
                                                                                     "none")
        arm["gate_basis"] = basis
        if basis_rows is None:
            arm["gates"] = {"all": gs.not_run("all", a.offered, "no leg records on disk")}
            out["arms"][arm_name] = arm
            continue

        rows, seen = gate_rows_from(basis_rows, arm_key)
        exp_empty = gs.expected_empty_docs(rows)
        both = bool(seq) and bool(bl)
        leela = {
            "census": gs.leela_census(rows, a.offered, expected_empty=exp_empty),
            "structure": gs.not_run("structure", a.offered,
                                    "identity and vector fields are not persisted in "
                                    "per-doc JSONL"),
            "determinism": (gs.leela_determinism(*(gate_rows_from(seq, arm_key)[0],
                                                   gate_rows_from(bl, arm_key)[0]))
                            if both else gs.not_run("determinism", a.offered,
                                                    "requires both legs' records")),
        }
        shashi = {
            "census": gs.shashi_census(sorted({r["doc"] for r in rows}), seen,
                                       expected_empty=exp_empty),
            "structure": gs.not_run("structure", a.offered,
                                    "vector fields are not persisted in per-doc JSONL"),
            "determinism": (gs.shashi_determinism(
                {r["doc"]: r.get("chunk_sha256") for r in gate_rows_from(seq, arm_key)[0]
                 if r["ok"]},
                {r["doc"]: r.get("chunk_sha256") for r in gate_rows_from(bl, arm_key)[0]
                 if r["ok"]}, "sequential", "blast")
                if both else gs.not_run("determinism", a.offered,
                                        "requires both legs' records")),
        }
        arm["self_duplication"] = gs.self_duplication(rows)
        arm["gate_verdicts"] = gs.three_verdicts(shashi, leela)
        v = arm["gate_verdicts"]
        say(f"  verdicts: shashi={v['shashi']['PASS']} leela={v['leela']['PASS']} "
            f"union={v['union']['PASS']}  not_run={v['union']['not_run']}")
        sd = arm["self_duplication"]
        say(f"  self_duplication: {sd['duplicated_docs']}/{sd['checked']} "
            f"factors={sd['factors']}")
        for suite in ("shashi", "leela"):
            if v[suite]["PASS"] is False:
                overall_fail.append(f"{arm_name}: {suite} suite FAIL")

        # metrics: closed-loop from admit stamps, plus the #39-corrected batch-position.
        arm["metrics"] = {}
        for leg_name, leg_rows in (("sequential", seq), ("blast", bl)):
            if not leg_rows:
                continue
            for wn in a.warm_n:
                arm["metrics"][f"{leg_name}_warm{wn}"] = ms.derive_side(
                    leg_rows, None, warm_n=wn, available_cpus=None, mode="closed-loop")
        if bl:
            fixed, corr = corrected_batchpos(bl)
            arm["batchpos_correction"] = corr
            if fixed:
                for wn in a.warm_n:
                    d = ms.derive_side(fixed, None, warm_n=wn, available_cpus=None,
                                       mode="open-loop-blast")
                    d["basis"] = corr["basis"]
                    arm["metrics"][f"blast_batchpos_corrected_warm{wn}"] = d
                say(f"  batchpos corrected: stale stamp gap "
                    f"{corr.get('stale_stamp_gap_s')}s removed")
        out["arms"][arm_name] = arm

    out["PASS"] = not overall_fail
    out["failed"] = overall_fail
    p = write_result("rederive_gates", out)
    say(f"\nwritten -> {p}")
    say("VERDICT: " + ("PASS" if not overall_fail else "FAIL: " + "; ".join(overall_fail)))
    return 0 if not overall_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
