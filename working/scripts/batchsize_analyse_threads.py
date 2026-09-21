#!/usr/bin/env python3
"""S5-A analysis: intra-op thread width T at one RocketRide token, video — TUNED POSTURE.

    batchsize_analyse_threads.py <s5a_out_dir> <default_leg_dir> <default_rep_leg_dir> <anchor_li_leg_dir> [--out f]

<s5a_out_dir>/rr_k16_T{1,2,4,8,16}/ are the sweep legs (unmodified video driver; the six variables
at T, read back in-process by the driver's preflight). The two default legs are the Stage 3
out-of-the-box K=16 cells on the same 16 videos (six variables UNSET; they read torch=16). The
anchor is one LlamaIndex instance at K=16 — the G4 comparator, never the tuned 8x4 cell.

  APPLIED, NOT DECLARED  each leg's in-process torch_num_threads must equal its T, else the leg
                         did not run the posture it names and is excluded, named.
  KNEE                   the smallest T whose frames/s is within G5(b)'s replicate spread (9.76%)
                         of the best T; SATURATION the best T.
  T=16 vs DEFAULT        the ruling: T=16 must reproduce the default cell within G5(b)'s spread or
                         the equivalence of "unset" and "16" is not established. Tested two ways:
                         throughput within the spread of the default mean, and — stronger — chunk
                         hashes identical on every video (the same computation, not just the same
                         speed). Both results are stated.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batchsize_analyse_video as bav  # noqa: E402

G5B_SPREAD = 0.0976


def recs(leg: Path) -> Dict[str, Dict[str, Any]]:
    fs = sorted(glob.glob(str(leg / "records_*.jsonl")))
    return ({r["video"]: r for r in (json.loads(l) for l in Path(fs[0]).read_text().splitlines() if l.strip())
             if r.get("role") == "measured"} if fs else {})


def in_process_torch(leg: Path):
    fs = sorted(glob.glob(str(leg / "preflight_*.json")))
    if not fs:
        return None
    d = json.loads(Path(fs[0]).read_text())
    return ((d.get("readbacks") or {}).get("rr_task") or {}).get("torch_num_threads")


def cpu_s_per_frame(leg: Path):
    fs = sorted(glob.glob(str(leg / "export_*.json")))
    if not fs:
        return None
    e = json.loads(Path(fs[0]).read_text()); e = e.get("data", e)
    return (e.get("efficiency") or {}).get("cpu_s_per_frame")


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__); return 2
    out_dir, d1, d2, anchor = (Path(x) for x in sys.argv[1:5])
    rows, excluded = {}, []
    for leg in sorted(out_dir.glob("rr_k16_T*"), key=lambda p: int(p.name.rsplit("_T", 1)[1])):
        T = int(leg.name.rsplit("_T", 1)[1])
        r = bav.leg_row(leg)
        torch_t = in_process_torch(leg)
        if torch_t != T:
            excluded.append({"T": T, "in_process_torch": torch_t,
                             "why": "the leg did not run the posture it names"})
            continue
        pc = r.get("percore_host") or {}
        rows[T] = {"frames_per_s": r.get("frames_per_s"), "effective_cores": r.get("effective_cores"),
                   "cpu_util_of_box": r.get("cpu_util_of_box"), "idle_core_equivalents": pc.get("idle_core_equivalents"),
                   "cpu_s_per_frame": cpu_s_per_frame(leg), "in_process_torch": torch_t, "leg": str(leg)}
    rep: Dict[str, Any] = {"label": "TUNED POSTURE — image unchanged, thread configuration set; not out-of-the-box",
                           "by_T": rows, "excluded": excluded}
    if rows:
        best = max(rows, key=lambda t: rows[t]["frames_per_s"] or 0)
        within = sorted(t for t in rows if (rows[t]["frames_per_s"] or 0) >= rows[best]["frames_per_s"] * (1 - G5B_SPREAD))
        rep["saturation_T"] = best
        rep["knee_T"] = within[0]
        rep["knee_rule"] = f"smallest T within G5(b)'s {G5B_SPREAD:.2%} spread of the best T"
    dA, dB = bav.leg_row(d1), bav.leg_row(d2)
    dmean = (dA["frames_per_s"] + dB["frames_per_s"]) / 2
    t16 = rows.get(16)
    eq: Dict[str, Any] = {"default_cells_frames_per_s": [dA["frames_per_s"], dB["frames_per_s"]],
                          "default_mean": round(dmean, 4), "tolerance": G5B_SPREAD}
    if t16:
        eq["T16_frames_per_s"] = t16["frames_per_s"]
        eq["relative"] = round(t16["frames_per_s"] / dmean - 1, 4)
        eq["throughput_within_spread"] = abs(eq["relative"]) <= G5B_SPREAD
        a, b = recs(d1), recs(Path(t16["leg"]))
        common = sorted(set(a) & set(b))
        eq["chunk_hash_identical_videos"] = f"{sum(1 for v in common if a[v]['chunk_sha256'] == b[v]['chunk_sha256'])}/{len(common)}"
        same = len(common) > 0 and all(a[v]["chunk_sha256"] == b[v]["chunk_sha256"] for v in common)
        eq["verdict"] = ("ESTABLISHED — T=16 reproduces the default cell within the spread AND produces "
                         "chunk-identical output" if eq["throughput_within_spread"] and same else
                         "ESTABLISHED FOR THROUGHPUT ONLY — within the spread, but the output differs"
                         if eq["throughput_within_spread"] else
                         "NOT ESTABLISHED — T=16 falls outside G5(b)'s spread of the default cell")
    else:
        eq["verdict"] = "NOT RUN — no valid T=16 leg"
    rep["T16_vs_default"] = eq
    an = bav.leg_row(anchor)
    rep["comparator_G4_anchor"] = {"what": "one LlamaIndex instance, K=16, the same 16 videos",
                                   "frames_per_s": an.get("frames_per_s"), "effective_cores": an.get("effective_cores")}
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
