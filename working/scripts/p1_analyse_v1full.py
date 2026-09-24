#!/usr/bin/env python3
"""P1-D (preregistration.json P1_D_V1_confirmation_168): 168 videos, RR one token vs LI one instance, T=4.

    p1_analyse_v1full.py <campaign_dir> <p0_campaign_dir>  -> analysis_v1full168.json
gap = LI frames/s / RR frames/s - 1 (frames/s = export total_frames / total_span_s). CONFIRMED iff
gap - max(0.82%, P0 V1's larger pair spread) >= 10 points; REFUTED iff gap <= that noise; otherwise
PRESENT BUT SMALLER. Determinism: each arm's per-video outputs equal P0 V1's (same arm, T=4) on every
video both ran."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_analyse_video import FLOOR, identity, load, session_facts, spread  # noqa: E402


def leg(camp: Path, name: str):
    for suf in ("", "_r1", "_r2"):
        d = camp / f"{name}{suf}"
        if d.is_dir() and list(d.glob("export_*.json")):
            g = load(d)
            g["session"] = session_facts(d)
            s = d / "memstat.jsonl.summary.json"
            g["memstat"] = json.loads(s.read_text()) if s.exists() else None
            return g
    return None


def main() -> int:
    camp, p0 = Path(sys.argv[1]), Path(sys.argv[2])
    rr, li = leg(camp, "v1full_rr_t4"), leg(camp, "v1full_li_t4")
    out = {"label": "P1-D 168-video V1 confirmation", "rr": None, "li": None}
    p0v = {k: load(p0 / k) for k in ("v1_rr_t4_a", "v1_rr_t4_b", "v1_li_t4_a", "v1_li_t4_b")}
    noise = max(FLOOR, spread(p0v["v1_rr_t4_a"]["frames_per_s"], p0v["v1_rr_t4_b"]["frames_per_s"]),
                spread(p0v["v1_li_t4_a"]["frames_per_s"], p0v["v1_li_t4_b"]["frames_per_s"]))
    for arm, g, ref in (("rr", rr, "v1_rr_t4_a"), ("li", li, "v1_li_t4_a")):
        if g:
            out[arm] = {k: g.get(k) for k in ("dir", "videos", "errors", "frames", "frames_per_s", "cpu_s_per_frame",
                                               "engine_cores", "boot_id", "session", "memstat", "p0", "task_census",
                                               "container_procs")}
            out[arm]["determinism_vs_p0_v1"] = identity(g, p0v[ref])
    if not (rr and li):
        out["gap"] = {"verdict": "NOT RUN", "why": ("the LlamaIndex 168-video leg did not run: the chain's per-leg check "
                                                    "found the P1 11-hour budget passed (chain_video_v1full_done.json: "
                                                    "v1full_li_t4:NOT_RUN_budget); one arm has no comparison") if rr else "neither arm ran"}
    if rr and li:
        gap = li["frames_per_s"] / rr["frames_per_s"] - 1
        margin = gap - noise
        out["gap"] = {"li_over_rr_minus_1": gap, "noise": noise, "margin_pp": margin,
                      "p0_v1_gap_16_videos": p0v["v1_li_t4_a"]["frames_per_s"] and
                      ((p0v["v1_li_t4_a"]["frames_per_s"] + p0v["v1_li_t4_b"]["frames_per_s"]) /
                       (p0v["v1_rr_t4_a"]["frames_per_s"] + p0v["v1_rr_t4_b"]["frames_per_s"]) - 1),
                      "verdict": "CONFIRMED" if margin >= 0.10 else ("REFUTED" if gap <= noise else "PRESENT BUT SMALLER"),
                      "same_session": rr["boot_id"] == li["boot_id"]}
    (camp / "analysis_v1full168.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out.get("gap"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
