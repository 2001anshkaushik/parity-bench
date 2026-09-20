#!/usr/bin/env python3
"""Analyse the AMI in-flight-videos sweep: one row per (arm, K) from the UNMODIFIED driver's own
exports, with idle cores from the per-core sidecar windowed to the leg.

    batchsize_analyse_video.py <out_dir> [--out report.json]

<out_dir>/<arm>_k<K>/ holds export_*.json, records_*.jsonl (driver_video.py) and percore.jsonl
(harness/percore_sampler.py sidecar). The sidecar outlives the leg on both sides — container
preflight before, teardown after — so its stream is cut to [first measured admit, last measured
done] on CLOCK_MONOTONIC, the clock both files carry. A leg whose window holds no sample reports
idle cores as NOT MEASURED, never 0.

Throughput, effective cores and utilisation are READ from the driver's export, not recomputed:
they are the same fields every banked AMI number used (throughput.total_frames_per_s,
efficiency.effective_cores, efficiency.cpu_util_of_box). Check B below is the one independent
angle: the host's per-core busy sum against the arm's cgroup-derived effective cores.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.percore_sampler import summarise          # noqa: E402


def leg_row(d: Path) -> Dict[str, Any]:
    arm, k = d.name.split("_k")
    row: Dict[str, Any] = {"arm": arm, "k": int(k), "dir": d.name}
    exports = sorted(d.glob("export_*.json"))
    if not exports:
        return {**row, "verdict": "NO EXPORT", "driver_log_tail":
                (d / "driver.log").read_text().splitlines()[-6:] if (d / "driver.log").exists() else None}
    e = json.loads(exports[0].read_text())
    e = e.get("data", e)
    tp, ef = e.get("throughput", {}), e.get("efficiency", {})
    row.update(
        verdict="OK" if not e.get("n_errors") and not e.get("aborted_by_breaker") else "DEGRADED",
        posture=e.get("posture"), n_offered=e.get("n_offered"), n_errors=e.get("n_errors"),
        span_s=tp.get("total_span_s"), frames=tp.get("total_frames"),
        frames_per_s=tp.get("total_frames_per_s"),
        videos_per_s=(round(e["n_offered"] / tp["total_span_s"], 5)
                      if e.get("n_offered") and tp.get("total_span_s") else None),
        effective_cores=ef.get("effective_cores"), cpu_util_of_box=ef.get("cpu_util_of_box"),
        box_cpus=ef.get("box_cpus"), efficiency_valid=ef.get("valid"),
        idle_burden=(ef.get("idle_burden") or {}).get("idle_cores_with_instances_live"),
        driver_share_of_box=(e.get("driver_cpu") or {}).get("share_of_box"),
        preleg_foreign_excess=e.get("preleg_foreign_excess"))
    recs: List[Dict[str, Any]] = []
    for rj in d.glob("records_*.jsonl"):
        recs += [json.loads(x) for x in rj.read_text().splitlines() if x.strip()]
    meas = [r for r in recs if r.get("role") == "measured" and r.get("admit_ns") and r.get("done_ns")]
    pc = d / "percore.jsonl"
    if meas and pc.exists():
        t0, t1 = min(r["admit_ns"] for r in meas), max(r["done_ns"] for r in meas)
        ivs = []
        for line in pc.read_text().splitlines():
            s = json.loads(line)
            if t0 <= s.get("mono_ns", -1) <= t1:
                ivs.append({int(c): v for c, v in s["busy"].items()})
        cpus = sorted(ivs[0]) if ivs else list(range(row.get("box_cpus") or 32))
        pcs = summarise(ivs, cpus)
        row["percore_host"] = {k2: v for k2, v in pcs.items() if k2 != "per_core_mean_busy"}
        row["percore_window_s"] = round((t1 - t0) / 1e9, 1)
        if pcs.get("mean_busy_cores") is not None and row["effective_cores"] is not None:
            row["check_B_host_minus_cgroup_cores"] = round(pcs["mean_busy_cores"] - row["effective_cores"], 3)
    else:
        row["percore_host"] = {"idle_core_count_mean": None, "idle_core_equivalents": None,
                               "note": "NOT MEASURED — no measured records or no sidecar stream"}
    return row


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1])
    rows = [leg_row(d) for d in sorted(out_dir.glob("*_k*")) if d.is_dir()]
    if not rows:
        print(f"REFUSED: no <arm>_k<K> directories under {out_dir}")
        return 3
    rep: Dict[str, Any] = {"out_dir": str(out_dir), "legs": rows, "by_arm": {}}
    for arm in sorted({r["arm"] for r in rows}):
        ok = sorted((r for r in rows if r["arm"] == arm and r.get("frames_per_s")),
                    key=lambda r: r["frames_per_s"], reverse=True)
        call: Dict[str, Any] = {"best_k": ok[0]["k"] if ok else None}
        if len(ok) > 1:
            call.update(runner_up_k=ok[1]["k"],
                        lead_over_runner_up=round(ok[0]["frames_per_s"] / ok[1]["frames_per_s"] - 1, 4),
                        spread_across_all_k=round(ok[0]["frames_per_s"] / ok[-1]["frames_per_s"] - 1, 4),
                        verdict="UNRESOLVED without a replicate — single run per K")
        rep["by_arm"][arm] = {"ranking": [(r["k"], r["frames_per_s"]) for r in ok], "call": call}
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
