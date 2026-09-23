#!/usr/bin/env python3
"""P0 E1 (amendment 5, exploratory DIAGNOSTIC, no gate): where the long parse holds live.

    p0_analyse_e1.py <campaign_dir>  -> analysis_e1.json

Per document of the 11, three readings side by side, each from its own raw file:
  isolated_tika_s   mean of H5's two shipped-config parses (h5/results_h5.jsonl): the engine's jars,
                    JRE and tika-config.xml through TikaBatch — no inline-image extraction
  engine_tika_s     `engine --tika <doc>` wall seconds (e1_engine_tika/results_e1.jsonl): the engine's
                    own JNI wrapper, outside any pipeline, the 11 run at once
  in_pipeline_s     S5-D's in-pipeline parse bracket (after_parse.last_t - open_t), batch campaign
plus the engine's stdout volume and a box-wide exec census over the stage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ELEVEN = ["011_011464.pdf", "039_039660.pdf", "008_008871.pdf", "011_011730.pdf", "014_014261.pdf",
          "000_000344.pdf", "031_031239.pdf", "002_002489.pdf", "034_034697.pdf", "033_033172.pdf",
          "014_014969.pdf"]


def rows(p: Path):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def main() -> int:
    camp = Path(sys.argv[1])
    h5 = {}
    for r in rows(camp / "h5" / "results_h5.jsonl"):
        if r.get("label") in ("h5_shipped_r1", "h5_shipped_r2") and r.get("wall_s") is not None:
            h5.setdefault(r["doc"], []).append(r["wall_s"])
    e1 = {r["doc"]: r for r in rows(camp / "e1_engine_tika" / "results_e1.jsonl")}
    s5d = {}
    for r in rows(ROOT / "working/results/batchsize_s5_20260921T205917Z/s5d/rr_stamped/stamp_probe.jsonl"):
        if r.get("stage") == "after_parse" and r.get("doc") in ELEVEN and r.get("last_t"):
            s5d[r["doc"]] = r["last_t"] - r["open_t"]
    per = {}
    for d in ELEVEN:
        iso = sum(h5[d]) / len(h5[d]) if h5.get(d) else None
        e = e1.get(d) or {}
        per[d] = {"isolated_tika_s": iso, "engine_tika_s": e.get("wall_s"), "engine_rc": e.get("rc"),
                  "engine_timed_out": e.get("rc") == 124, "engine_stdout_mb": (e.get("stdout_bytes") or 0) / 1e6,
                  "in_pipeline_s_S5D": s5d.get(d),
                  "engine_over_isolated": (e["wall_s"] / iso) if (e.get("wall_s") and iso) else None,
                  "in_pipeline_over_isolated": (s5d[d] / iso) if (d in s5d and iso) else None}
    census = {}
    f = camp / "e1_engine_tika" / "exec_census.json"
    if f.exists():
        for line in f.read_text().splitlines():
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.get("type") == "map":
                census.update((j.get("data") or {}).get("@exec") or {})
    out = {"label": "EXPLORATORY DIAGNOSTIC (amendment 5) — evidence of where the hold lives; no gate",
           "per_document": per,
           "exec_census_box_wide": dict(sorted(census.items(), key=lambda x: -x[1])),
           "note": "engine --tika ran the 11 at once (11 containers on 32 vCPUs); isolated Tika ran "
                   "12 JVMs at once in H5; in-pipeline brackets come from a C=32 leg of 9,975 documents"}
    (camp / "analysis_e1.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(per, indent=1)[:3000])
    print("exec census:", out["exec_census_box_wide"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
