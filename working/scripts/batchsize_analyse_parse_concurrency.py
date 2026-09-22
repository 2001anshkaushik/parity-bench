#!/usr/bin/env python3
"""Parse concurrency inside one RocketRide token, from the EXISTING S5-D stamps (laptop only).

    batchsize_analyse_parse_concurrency.py <s5d_leg_dir> [--out report.json]

POST-HOC: defined 2026-09-22, after S5-D ran, to test Ansh's hypothesis that parse is effectively
bounded per token and that small documents wait behind large ones INSIDE parse (evidence: 13 of
the 15 holds over 300 s sit in parse; admission is at most 0.45% of latency).

WHAT THE STAMPS CAN AND CANNOT SAY, stated before any number. The stamp node after parse opens
when the document's pipeline instance opens (admission) and records the first output that reaches
it. Tika emits a document's text as ONE event (n_events is 1 for almost every document), so a
document's time "in parse" is [after_parse.open_t, after_parse.first_t]: waiting for a parse slot
PLUS being parsed. The stamps cannot split those two — so a flat, high count of documents in
parse fits a bound (many waiting behind few being parsed) and also fits many parsing slowly in
parallel. The stamps measure occupancy and overlap; what bounds parse is a SOURCE question, traced
separately and labelled so.

  in_parse(t)      documents inside [open_t, first_t] at time t — time-weighted max, p50, p95,
                   over the measured window
  in_pipeline(t)   documents inside [open_t, the embed stamp's last output] — the C=32 context
  small vs large   for every small document (< the first page tercile edge), the seconds of its
                   parse interval that overlapped ANY document of 1,000+ pages being in parse;
                   and small documents' parse time with and without such overlap
"""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
BIG_PAGES = 1000


def weighted_stats(intervals: List[Tuple[float, float]], lo: float, hi: float) -> Dict[str, Any]:
    ev = sorted([(a, 1) for a, b in intervals if b > a] + [(b, -1) for a, b in intervals if b > a])
    level, t_prev, dur = 0, lo, {}
    for t, d in ev:
        t_c = min(max(t, lo), hi)
        if t_c > t_prev:
            dur[level] = dur.get(level, 0.0) + (t_c - t_prev)
            t_prev = t_c
        level += d
    if hi > t_prev:
        dur[level] = dur.get(level, 0.0) + (hi - t_prev)
    total = sum(dur.values())
    def q(p: float) -> int:
        acc = 0.0
        for lvl in sorted(dur):
            acc += dur[lvl]
            if acc >= p * total:
                return lvl
        return max(dur)
    return {"max": max(dur), "p50": q(0.50), "p95": q(0.95), "mean": round(sum(k * v for k, v in dur.items()) / total, 2),
            "seconds_by_level_top": {str(k): round(v, 1) for k, v in sorted(dur.items(), key=lambda kv: -kv[1])[:6]}}


def union(iv: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def overlap(a: float, b: float, u: List[Tuple[float, float]], starts: List[float]) -> float:
    i = max(0, bisect.bisect_right(starts, a) - 1)
    s = 0.0
    while i < len(u) and u[i][0] < b:
        s += max(0.0, min(b, u[i][1]) - max(a, u[i][0]))
        i += 1
    return s


def long_holds(docs: Dict[str, Any], perdoc: List[Dict[str, Any]], st: Dict[str, Any], man: Dict[str, Any],
               over_s: float = 300.0) -> List[Dict[str, Any]]:
    """Every measured document in parse for over 300 s: how many OTHER documents entered and left parse
    entirely inside its interval (a single serialising lock would make that zero), which documents
    sat in parse beside it the longest, and — from the committed Stage 4 legs — how long the same
    document took in RocketRide's leg 1 and on LlamaIndex (a document-intrinsic cost reproduces)."""
    s4 = ROOT / "working/results/batchsize_s4_20260921T013303Z"
    def held(f: Path) -> Dict[str, float]:
        out = {}
        for x in f.read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                out[r["doc"]] = round((r["completion_ns"] - r["submit_ns"]) / 1e9, 1)
        return out
    rr1 = held(sorted((s4 / "p1_rr_cont32").glob("perdoc_rr_refc32_*.jsonl"))[0])
    li = held(sorted((s4 / "p2_li_cont").glob("perdoc_li_refc32_*.jsonl"))[0])
    rows = []
    for k, x in docs.items():
        a, b = x["parse"]
        if not x["measured"] or b - a <= over_s:
            continue
        inside = sum(1 for j, y in docs.items() if j != k and y["parse"][0] >= a and y["parse"][1] <= b)
        beside = sorted(((j, min(b, y["parse"][1]) - max(a, y["parse"][0])) for j, y in docs.items()
                         if j != k and y["parse"][0] < b and y["parse"][1] > a), key=lambda t: -t[1])[:5]
        rows.append({"doc": k, "pages": x["pages"], "bytes": (man.get(k) or {}).get("bytes"), "parse_s": round(b - a, 1),
                     "documents_through_parse_inside_its_interval": inside,
                     "longest_beside_in_parse": [{"doc": j, "pages": docs[j]["pages"], "overlap_s": round(o, 1)} for j, o in beside],
                     "stage4_leg1_rr_end_to_end_s": rr1.get(k), "stage4_li_c32_end_to_end_s": li.get(k)})
    return sorted(rows, key=lambda r: -r["parse_s"])


def thread_structure(d: Path) -> Dict[str, Any]:
    """Which threads carried the stamps (MEASURED): distinct threads per stage, whether one thread
    carries a document through every stage, and how many distinct threads held a document in parse
    at the same instant (sampled at every 25th admission)."""
    by: Dict[str, List[Dict[str, Any]]] = {}
    for line in (d / "stamp_probe.jsonl").read_text().splitlines():
        if line.strip():
            s = json.loads(line)
            if s.get("stage"):
                by.setdefault(s["stage"], []).append(s)
    emb = {(s["doc"], s["tid"]) for s in by.get("after_embed", [])}
    parse = sorted(by.get("after_parse", []), key=lambda r: r["open_t"])
    iv = [(r["open_t"], r.get("first_t") or r.get("close_t"), r["tid"]) for r in parse]
    samples = sorted(len({t for (x, y, t) in iv if x <= a < y}) for a, _, _ in iv[::25])
    return {"processes": sorted({s["pid"] for rs in by.values() for s in rs}),
            "distinct_threads_by_stage": {k: len({s["tid"] for s in rs}) for k, rs in by.items()},
            "documents_whose_parse_and_embed_ran_on_one_thread": sum(1 for s in parse if (s["doc"], s["tid"]) in emb),
            "documents_with_a_parse_stamp": len(parse),
            "distinct_threads_holding_a_document_in_parse": {"max": samples[-1], "p50": samples[len(samples) // 2],
                                                             "p95": samples[int(0.95 * len(samples))]} if samples else None}


def pct(v: List[float], p: float) -> float:
    v = sorted(v)
    return round(v[min(len(v) - 1, int(p * len(v)))], 2) if v else None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    d = Path(sys.argv[1])
    perdoc = [json.loads(x) for x in sorted(d.glob("perdoc_rr_refc32_*.jsonl"))[0].read_text().splitlines() if x.strip()]
    measured = {r["doc"] for r in perdoc}
    lo = min(r["submit_ns"] for r in perdoc) / 1e9
    hi = max(r["completion_ns"] for r in perdoc) / 1e9
    st: Dict[str, Dict[str, Any]] = {}
    for line in (d / "stamp_probe.jsonl").read_text().splitlines():
        if line.strip():
            s = json.loads(line)
            if s.get("stage"):
                st.setdefault(s["doc"], {})[s["stage"]] = s
    man = {json.loads(l)["file"]: json.loads(l) for l in
           (ROOT / "working/results/corpus_manifest.jsonl").read_text().splitlines() if l.strip()}
    v = sorted(m.get("pages") or 0 for m in man.values())
    small_edge = v[len(v) // 3]
    parse_iv, pipe_iv, docs = [], [], {}
    n_events_multi = 0
    for doc, s in st.items():
        p = s.get("after_parse")
        if not p:
            continue
        end = p.get("first_t") or p.get("close_t")
        if (p.get("n_events") or 0) > 1:
            n_events_multi += 1
        e = s.get("after_embed") or {}
        pend = e.get("last_t") or e.get("close_t") or p.get("close_t")
        parse_iv.append((p["open_t"], end))
        pipe_iv.append((p["open_t"], pend))
        docs[doc] = {"pages": (man.get(doc) or {}).get("pages") or 0, "parse": (p["open_t"], end), "measured": doc in measured}
    big = [x["parse"] for x in docs.values() if x["pages"] >= BIG_PAGES]
    ub = union(big)
    starts = [a for a, _ in ub]
    small = {k: x for k, x in docs.items() if x["measured"] and x["pages"] < small_edge}
    ov = {k: overlap(x["parse"][0], x["parse"][1], ub, starts) for k, x in small.items()}
    dur = {k: x["parse"][1] - x["parse"][0] for k, x in small.items()}
    with_ov = [dur[k] for k in small if ov[k] > 0]
    without = [dur[k] for k in small if ov[k] == 0]
    rep = {
        "label": "POST-HOC — defined 2026-09-22 after S5-D ran; occupancy and overlap from the stamps, not a parse-slot measurement",
        "leg_dir": str(d), "measured_window_s": round(hi - lo, 1), "documents_with_parse_stamp": len(docs),
        "documents_with_more_than_one_parse_event": n_events_multi,
        "in_parse_documents": weighted_stats(parse_iv, lo, hi),
        "in_pipeline_documents": weighted_stats(pipe_iv, lo, hi),
        "big_documents": {"pages_at_least": BIG_PAGES, "n": len(big),
                          "seconds_with_any_in_parse": round(sum(b - a for a, b in ub), 1),
                          "share_of_window": round(sum(b - a for a, b in ub) / (hi - lo), 4)},
        "small_documents": {"pages_below": small_edge, "n": len(small),
                            "n_overlapping_a_big_parse": len(with_ov),
                            "overlap_seconds_total": round(sum(ov.values()), 1),
                            "share_of_small_parse_time_overlapping": round(sum(ov.values()) / sum(dur.values()), 4) if dur else None,
                            "parse_s_with_overlap": {"p50": pct(with_ov, 0.5), "p95": pct(with_ov, 0.95), "max": pct(with_ov, 1.0)},
                            "parse_s_without_overlap": {"p50": pct(without, 0.5), "p95": pct(without, 0.95), "max": pct(without, 1.0)},
                            "held_over_300s": sorted(({"doc": k, "pages": small[k]["pages"], "parse_s": round(dur[k], 1),
                                                       "overlap_with_big_parse_s": round(ov[k], 1)}
                                                      for k in small if dur[k] > 300), key=lambda r: -r["parse_s"])},
        "long_parse_holds": long_holds(docs, perdoc, st, man),
        "big_documents_by_stage": sorted(({"doc": k, "pages": x["pages"], "parse_s": round(x["parse"][1] - x["parse"][0], 1),
                                           "split_end_to_embed_end_s": round((st[k].get("after_embed", {}).get("last_t") or 0)
                                                                             - (st[k].get("after_split", {}).get("last_t") or 0), 1)}
                                          for k, x in docs.items() if x["pages"] >= BIG_PAGES), key=lambda r: -r["pages"]),
        "threads_measured": thread_structure(d),
        "SOURCE_not_measurement": {
            "per_token_processing_bound": (
                "engine/ai/modules/data/data_conn.py:737 runs each pipe's close — where the document's pipeline "
                "executes (pipe.close(), data_conn.py:711) — via asyncio.to_thread, i.e. asyncio's DEFAULT executor; "
                "engine/ai sets no other executor, so CPython's default applies: min(32, os.cpu_count() + 4) = 32 on "
                "this 32-vCPU box. Pipes are admitted under asyncio.Semaphore(threadCount=64) (data_conn.py:138,477). "
                "So one token processes at most 32 documents at once, whatever K or C above 32."),
            "parse_itself": (
                "the parse provider is a native node (engine/nodes/core/services.parse.json:3, protocol parse://) "
                "running Tika 3.2.3 (engine/java/lib/tika-*-3.2.3.jar) in a JVM hosted inside the engine process "
                "(no standalone java process in S5-C's snapshots; engine/java/jre ships with the bundle). The C++ "
                "binding is compiled into the engine binary and is NOT in this bundle, so a lock inside it cannot "
                "be read here — the stamps below bound it instead."),
            "tika_config": (
                "engine/java/tika-config.xml:12 excludes OCR; :29 sets PDFParser sortByPosition=true and :30-32 turn "
                "on AcroForm, annotation and bookmark extraction — a candidate for the document-intrinsic slow parses "
                "(HYPOTHESIS from source, not measured).")},
        "cannot_say": ("whether a document in parse was WAITING for a slot or BEING parsed: Tika emits its text as one "
                       "event, so the stamp marks only when parsing ended; that split needs the engine's own parse start, "
                       "which no stamp records"),
    }
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
