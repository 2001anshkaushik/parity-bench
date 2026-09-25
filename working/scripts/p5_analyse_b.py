#!/usr/bin/env python3
"""P5-B 168-video block-interleaved confirmation (preregistration.json P5_B), from raw block legs only.

    p5_analyse_b.py <campaign_dir>  -> analysis_p5b.json

Per block and arm: frames/s (export total_frames / total_span_s), frames, span, videos, errors, the gate records (D0, cell),
the paused other container's cgroup CPU over the block. Per arm: total frames/s = sum of frames / sum of spans over the
blocks it ran. The ratio RR/LI of the totals; the per-block ratio distribution (min, p50 = true median, max) over blocks
both arms ran. Correctness: RR P5 per video (the LAST measured record per video without error) against the banked P1-D
stock RR T=4 168-video leg (chunk sha256 AND frame scores); every differing video named.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import load  # noqa: E402

P1D = Path(__file__).resolve().parents[2] / "working" / "results" / "parity_p1_20260923T184000Z" / "v1full_rr_t4"
BLOCKS = range(1, 12)


def gate(camp: Path, name: str) -> Optional[str]:
    f = camp / "gates" / f"{name}.json"
    return json.loads(f.read_text()).get("outcome") if f.exists() else None


def block(camp: Path, name: str) -> Optional[Dict[str, Any]]:
    d = camp / name
    g = load(d) if d.is_dir() else None
    if not g:
        return None
    oc = json.loads((d / "other_container_cpu.json").read_text()) if (d / "other_container_cpu.json").exists() else {}
    try:
        other_cpu_s = (int(oc["cpu_usage_usec_after"]) - int(oc["cpu_usage_usec_before"])) / 1e6
    except (KeyError, ValueError, TypeError):
        other_cpu_s = None
    st = (d / "other_container_state.txt").read_text().strip() if (d / "other_container_state.txt").exists() else None
    return {"dir": name, "videos": g["videos"], "errors": g["errors"], "frames": g["frames"], "span_s": g["span_s"],
            "frames_per_s": g["frames_per_s"], "cpu_s_per_frame": g["cpu_s_per_frame"], "boot_id": g["boot_id"],
            "session": g["session"], "d0": gate(camp, f"G_d0_{name}"), "cell": gate(camp, f"G_cell_{name}"),
            "other_container": oc.get("other"), "other_container_state_at_start": st, "other_container_cpu_s_during_block": other_cpu_s,
            "_by_video": g["by_video"]}


def main() -> int:
    camp = Path(sys.argv[1])
    blocks: Dict[str, Any] = {}
    for b in BLOCKS:
        for arm in ("rr", "li"):
            n = f"p5b_{arm}_b{b:02d}"
            blocks[n] = block(camp, n)
    per_arm = {}
    for arm in ("rr", "li"):
        xs = [x for n, x in blocks.items() if x and n.startswith(f"p5b_{arm}_")]
        fr, sp = sum(x["frames"] for x in xs), sum(x["span_s"] for x in xs)
        per_arm[arm] = {"blocks": len(xs), "videos": sum(x["videos"] for x in xs), "errors": sum(x["errors"] for x in xs),
                        "frames": fr, "span_s": sp, "total_frames_per_s": fr / sp if sp else None}
    both = [b for b in BLOCKS if blocks.get(f"p5b_rr_b{b:02d}") and blocks.get(f"p5b_li_b{b:02d}")]
    ratios = {b: blocks[f"p5b_rr_b{b:02d}"]["frames_per_s"] / blocks[f"p5b_li_b{b:02d}"]["frames_per_s"] for b in both}
    rv = sorted(ratios.values())
    dist = {"blocks": len(rv), "min": rv[0] if rv else None, "p50": statistics.median(rv) if rv else None, "max": rv[-1] if rv else None,
            "per_block": {str(b): r for b, r in ratios.items()}}
    ratio_total = (per_arm["rr"]["total_frames_per_s"] / per_arm["li"]["total_frames_per_s"]
                   if per_arm["rr"]["total_frames_per_s"] and per_arm["li"]["total_frames_per_s"] else None)
    # correctness against the banked P1-D stock RR T=4 168-video output
    ref = load(P1D)
    mine: Dict[str, Any] = {}
    for n, x in blocks.items():
        if x and n.startswith("p5b_rr_"):
            mine.update(x["_by_video"])
    differ, same = [], 0
    for v, o in sorted(mine.items()):
        r = (ref or {}).get("by_video", {}).get(v)
        if r is None:
            differ.append({"video": v, "why": "absent from the P1-D reference"})
        elif r["chunk_sha256"] != o["chunk_sha256"] or r["frame_scores"] != o["frame_scores"]:
            differ.append({"video": v, "chunk_hash_differs": r["chunk_sha256"] != o["chunk_sha256"],
                           "frame_scores_differ": r["frame_scores"] != o["frame_scores"]})
        else:
            same += 1
    corr = {"reference": "parity_p1_20260923T184000Z/v1full_rr_t4 (stock rr:patched-video, T=4, K=16, 168 videos)",
            "videos_compared": len(mine), "identical": same, "differ": differ,
            "pass": bool(mine) and not differ and len(mine) == 168}
    for x in blocks.values():
        if x:
            x["_by_video"] = f"{len(x['_by_video'])} videos"
    out = {"label": "P5-B 168-video block-interleaved confirmation (preregistration.json P5_B)", "blocks": blocks, "per_arm": per_arm,
           "ratio_rr_over_li_totals": ratio_total, "per_block_ratio_distribution": dist, "correctness_vs_p1d": corr,
           "blocks_not_run": [n for n, x in blocks.items() if x is None],
           "canary": {n: (json.loads((camp / n / "bench.json").read_text()) if (camp / n / "bench.json").exists() else None) and
                      statistics.mean(r["forward"] for r in json.loads((camp / n / "bench.json").read_text())["rows"] if r.get("forward"))
                      for n in ("p5c_can_b0", "p5c_can_bmid")},
           "sessions": sorted({x["boot_id"] for x in blocks.values() if x and x.get("boot_id")})}
    (camp / "analysis_p5b.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote analysis_p5b.json: blocks run {sum(1 for x in blocks.values() if x)}/22; ratio {ratio_total}; correctness {corr['pass']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
