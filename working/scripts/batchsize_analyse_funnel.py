#!/usr/bin/env python3
"""S5-D: where one token's latency goes — admission queue vs in-pipeline stages, per document.

    batchsize_analyse_funnel.py <leg_dir> <leg1_leg.json> [--out report.json]

<leg_dir> holds perdoc_rr_refc32_*.jsonl (client submit/completion, time.time_ns) and
stamp_probe.jsonl (engine-side stamps from three pass-through nodes, time.time() — the same host
CLOCK_REALTIME). Per measured document:

    admit      = earliest stamp-node open_t        (the pipeline instance opened: slot held)
    parse_end  = after_parse.last_t                (Tika finished emitting text)
    split_end  = after_split.last_t                (the splitter finished)
    embed_end  = after_embed.last_t                (the embedding node flushed)

    admission_wait = admit - submit                 QUEUE WAIT before the engine takes the doc
    parse          = parse_end - admit              in-pipeline: Tika (engine-built-in, JVM)
    split          = split_end - parse_end          in-pipeline: LangChain splitter (Python)
    embed          = embed_end - split_end          in-pipeline: MiniLM (Python/torch)
    return         = completion - embed_end         response back to the client
    end_to_end     = completion - submit

WHAT THIS CAN AND CANNOT SEPARATE, stated before any number: it separates waiting for ADMISSION
from time INSIDE the pipeline, and inside the pipeline it attributes time to a STAGE. It cannot
split a stage's time into that stage's own work and waiting for a contended resource inside the
stage (a JVM pool, the GIL) — that needs each document's solo stage time, which a C=32 run does
not contain. So "parse" here is parse service PLUS any contention inside parse, and is labelled so.

PERTURBATION: the stamps add three Python nodes. The leg's span throughput is compared with leg 1
(the same work, uninstrumented); a gap beyond the arm's 0.82% floor means the instrument moved
the measurement, and the report says by how much.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
FLOOR_RR = 0.0082


def tercile_edges(pages: List[int]) -> List[int]:
    v = sorted(pages)
    return [v[len(v) // 3], v[(2 * len(v)) // 3]]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    leg_dir, leg1 = Path(sys.argv[1]), Path(sys.argv[2])
    perdoc = sorted(leg_dir.glob("perdoc_rr_refc32_*.jsonl"))
    stamps_f = leg_dir / "stamp_probe.jsonl"
    if not perdoc or not stamps_f.exists():
        print(f"REFUSED: need perdoc_rr_refc32_*.jsonl and stamp_probe.jsonl in {leg_dir}")
        return 3
    client = {r["doc"]: r for r in (json.loads(x) for x in perdoc[0].read_text().splitlines() if x.strip())}
    stamps: Dict[str, Dict[str, Any]] = {}
    for line in stamps_f.read_text().splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        if s.get("doc") in client:
            stamps.setdefault(s["doc"], {})[s.get("stage") or "none"] = s
    man = {json.loads(l)["file"]: json.loads(l) for l in
           (ROOT / "working/results/corpus_manifest.jsonl").read_text().splitlines() if l.strip()}
    edges = tercile_edges([m.get("pages") or 0 for m in man.values()])

    rows, unjoined = [], []
    for d, c in client.items():
        st = stamps.get(d, {})
        if not c.get("ok") or not all(k in st for k in ("after_parse", "after_split", "after_embed")):
            unjoined.append({"doc": d, "ok": c.get("ok"), "stages_seen": sorted(st)})
            continue
        sub, done = c["submit_ns"] / 1e9, c["completion_ns"] / 1e9
        admit = min(v["open_t"] for v in st.values())
        pe, se, ee = (st["after_parse"]["last_t"], st["after_split"]["last_t"], st["after_embed"]["last_t"])
        pages = (man.get(d) or {}).get("pages") or 0
        rows.append({"doc": d, "pages": pages,
                     "tercile": 0 if pages < edges[0] else (1 if pages < edges[1] else 2),
                     "admission_wait": admit - sub, "parse": pe - admit, "split": se - pe,
                     "embed": ee - se, "return": done - ee, "end_to_end": done - sub})
    comps = ("admission_wait", "parse", "split", "embed", "return")

    def summarise(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rs:
            return {"n": 0}
        e2e = sum(r["end_to_end"] for r in rs)
        out: Dict[str, Any] = {"n": len(rs), "end_to_end_s_sum": round(e2e, 1)}
        for k in comps:
            v = sorted(r[k] for r in rs)
            out[k] = {"share_of_end_to_end": round(sum(v) / e2e, 4) if e2e else None,
                      "p50_s": round(v[len(v) // 2], 3), "p99_s": round(v[min(len(v) - 1, int(0.99 * len(v)))], 3),
                      "max_s": round(v[-1], 3)}
        return out

    by_t = {f"tercile_{i} ({['< %d' % edges[0], '%d-%d' % (edges[0], edges[1] - 1), '>= %d' % edges[1]][i]} pages)":
            summarise([r for r in rows if r["tercile"] == i]) for i in range(3)}
    outliers = sorted((r for r in rows if r["end_to_end"] > 300), key=lambda r: -r["end_to_end"])
    for r in outliers:
        r["held_by"] = max(comps, key=lambda k: r[k])

    # The instrument's own cost: this leg against leg 1, same documents, same shape.
    g1 = json.loads(leg1.read_text())
    legs_here = sorted(leg_dir.glob("leg_rr_refc32_*.json"))
    gs = json.loads(legs_here[0].read_text()) if legs_here else {}
    t1, ts = g1["throughput"]["docs_per_s"], (gs.get("throughput") or {}).get("docs_per_s")
    pert = (ts / t1 - 1) if (ts and t1) else None
    rep = {
        "leg_dir": str(leg_dir), "joined_documents": len(rows), "unjoined": len(unjoined),
        "unjoined_examples": unjoined[:10], "page_tercile_edges": edges,
        "all_documents": summarise(rows), "by_page_tercile": by_t,
        "outliers_over_300s": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
                               for r in outliers[:40]],
        "outliers_held_by": {k: sum(1 for r in outliers if r["held_by"] == k) for k in comps},
        "perturbation_vs_leg1": {"leg1_docs_per_s": t1, "instrumented_docs_per_s": ts,
                                 "relative": round(pert, 4) if pert is not None else None,
                                 "floor": FLOOR_RR,
                                 "verdict": (None if pert is None else
                                             "within the floor — the stamps did not measurably move the leg"
                                             if abs(pert) <= FLOOR_RR else
                                             "OUTSIDE the floor — the instrument perturbed the measurement; "
                                             "decomposition shares stand, absolute times carry the offset")},
        "cannot_separate": ("a stage's own work from contention INSIDE that stage (a JVM pool, the GIL): "
                            "that needs each document's solo stage time, which a C=32 run does not contain"),
    }
    # POST-HOC, labelled: defined after the pre-registered span comparison came out beyond the floor
    # (2026-09-21). It does not change that verdict; it shows what the span gap is made of, because on
    # this corpus one document sets every RocketRide continuous span (register 40).
    def view(perdoc_path: Path) -> Dict[str, Any]:
        rows = [json.loads(x) for x in perdoc_path.read_text().splitlines() if x.strip()]
        t0 = min(r["submit_ns"] for r in rows)
        ok = sorted((r for r in rows if r.get("ok")), key=lambda r: r["completion_ns"])
        last = max(rows, key=lambda r: r["completion_ns"])
        to = lambda k: round(k / ((ok[k - 1]["completion_ns"] - t0) / 1e9), 4)  # noqa: E731
        return {"docs_per_s_to_p90": to(int(0.9 * len(ok))), "docs_per_s_to_p99": to(int(0.99 * len(ok))),
                "span_set_by": last["doc"], "held_s": round((last["completion_ns"] - last["submit_ns"]) / 1e9, 1),
                "deadline_losses": [r["doc"] for r in rows if str(r.get("reason", "")).endswith("TimeoutError")]}
    p1 = sorted(leg1.parent.glob("perdoc_rr_refc32_*.jsonl"))
    if p1:
        a, b = view(p1[0]), view(perdoc[0])
        rep["perturbation_vs_leg1"]["POST_HOC_DIAGNOSTIC"] = {
            "label": "defined after the pre-registered comparison fell outside the floor; does not change the verdict",
            "leg1": a, "instrumented": b,
            "to_p90_relative": round(b["docs_per_s_to_p90"] / a["docs_per_s_to_p90"] - 1, 4),
            "to_p99_relative": round(b["docs_per_s_to_p99"] / a["docs_per_s_to_p99"] - 1, 4)}
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
