#!/usr/bin/env python3
"""Run inventory for the meeting document — read from result JSONs, never from prose.

Every value comes from a file or is UNKNOWN. Run on the laptop it inventories the laptop's
files; run ON THE BOX it fills in the box-only rows the laptop cannot read. The S3 column
records the exact error when credentials are absent rather than guessing.

    python3 working/scripts/build_run_inventory.py          # writes publishable/RUN_INVENTORY.md
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "working" / "results"
OUT = ROOT / "publishable" / "RUN_INVENTORY.md"

# Box artifacts named by the operator in-session; every value UNKNOWN until the JSON is read.
# (source: operator-reported run ids — the files live on the box / S3, not in git)
BOX_REPORTED = [
    ("2026-08-16T03:18Z", "smoke50_parser_in__20260816T031854Z__c362c2816e85.json",
     "10k v1: per-doc blast + sequential (seq died at doc 9,629)",
     "SUPERSEDED: #29 asymmetric blast clock (latency void; throughput stood), #30 memory "
     "table, #32 ttl killed sequential at 9,629; stock engine (duplication uncorrected); "
     "pre-cpuset config"),
    ("2026-08-17", "exp_batched_blast N=1000 probe x2 (ids UNKNOWN)",
     "batched send_files probes",
     "SUPERSEDED: #34 wrong utilisation denominator, #35 impossible concurrency 281, #37 "
     "engine UNPINNED torch=16 — 52.8%/52.9% corroboration VOID pending pinned re-take"),
    ("2026-08-17/18", "run10k_p2_blast_v2 result JSON (id UNKNOWN)",
     "10k v2: per-doc blast, pinned, cpuset 0-23",
     "PARTIALLY QUOTABLE: metrics computed correctly; gates were #38 (empty-leg FAIL) — "
     "re-derive with rederive_gates.py; RR batch-position latency #39 (stale cross-arm "
     "clock) — quotable only from rederive's corrected cells; closed-loop and warm_n=64 "
     "cells unaffected"),
]


def sh(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def g(d, *path, default="UNKNOWN"):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d if d is not None else default


def classify(p: Path, j) -> dict:
    """One row per result JSON — facts only, from the file."""
    data = j.get("data", j) if isinstance(j, dict) else {}
    meta = j.get("_meta", {}) if isinstance(j, dict) else {}
    m = re.search(r"__(\d{8}T\d{6}Z)__", p.name)
    ts = m.group(1) if m else g(meta, "written_utc")
    system = g(data, "metrics", "platform", "system")
    machine = g(data, "metrics", "platform", "machine")
    publishable = g(data, "metrics", "publishable", default=None)
    if publishable == "UNKNOWN":
        publishable = None
    corpus_n = g(data, "corpus", "n")
    corpus_sha = g(data, "corpus", "sha256")
    corpus_sha = corpus_sha[:16] if isinstance(corpus_sha, str) else corpus_sha
    patch = g(data, "provenance", "engine", "duplication_patch_applied", default=None)
    if patch is None:
        patch = g(data, "provenance_leela", default=None) and "see file" or "UNKNOWN"
    pinned = data.get("pinned", {}) if isinstance(data, dict) else {}
    if not isinstance(pinned, dict):        # a legacy schema stores a list here
        pinned = {}
    cfg = ("UNKNOWN" if not pinned else
           f"workers={pinned.get('workers', '?')} threads={pinned.get('threads', '?')} "
           f"C={pinned.get('blast_concurrency', '?')}")
    quotable, why = False, ""
    if system == "Darwin":
        why = "macOS/arm64 — wiring validation only (standing policy)"
    elif system == "Linux" and publishable:
        quotable, why = True, "publishable platform; check per-metric defect flags"
    else:
        why = "platform UNKNOWN (legacy schema, pre-platform-stamp era) — laptop-era probe"
    return {"file": p.name, "ts": ts, "system": f"{system}/{machine}",
            "corpus_n": corpus_n, "corpus_sha": corpus_sha, "patch": patch,
            "config": cfg, "quotable": quotable, "why": why, "data": data}


def family(name: str) -> str:
    return re.sub(r"__\d{8}T\d{6}Z__[0-9a-f]+\.json$", "", name).rstrip("_").split("__")[0]


def headline(data, arm):
    cells = g(data, "metrics", "arms", arm, default={})
    if not isinstance(cells, dict) or not cells:
        return None
    rows = []
    for cell, v in sorted(cells.items()):
        if not isinstance(v, dict) or "error" in v:
            continue
        lat = v.get("latency") or {}
        rows.append((cell, v.get("docs_per_s"), v.get("chunks_per_s"),
                     lat.get("p50"), lat.get("p95"), v.get("cpu_s_per_doc"),
                     v.get("effective_cores"), v.get("cpu_utilization")))
    return rows


def main() -> int:
    files = sorted(RESULTS.glob("*.json"))
    rows = []
    for p in files:
        j = load(p)
        if j is None:
            rows.append({"file": p.name, "ts": "UNKNOWN", "system": "UNPARSEABLE",
                         "corpus_n": "UNKNOWN", "corpus_sha": "UNKNOWN", "patch": "UNKNOWN",
                         "config": "UNKNOWN", "quotable": False,
                         "why": "file does not parse as JSON", "data": {}})
            continue
        rows.append(classify(p, j))

    fams = defaultdict(list)
    for r in rows:
        fams[family(r["file"])].append(r)

    rc, s3 = sh(["aws", "s3", "ls", "s3://rocketride-benchmark-data/ansh/", "--recursive"])
    s3_ok = rc == 0 and "ERROR" not in s3 and "NoCredentials" not in s3

    L = ["# Run inventory — generated from result JSONs, never prose",
         "",
         f"Generated by `working/scripts/build_run_inventory.py` over `working/results/*.json`"
         f" ({len(files)} files). Every value is from a file or UNKNOWN. Regenerate ON THE BOX"
         " to fill the box-only rows.",
         "",
         "## 1. Inventory",
         "",
         "### Local result JSONs (this machine)",
         "",
         "| ts (UTC) | run | n | corpus sha16 | engine patch | config | platform |"
         " quotable | reason |",
         "|---|---|---|---|---|---|---|---|---|"]
    for fam in sorted(fams):
        rs = sorted(fams[fam], key=lambda r: str(r["ts"]))
        # a file with a parsed corpus is worth its own row even if it predates the
        # platform stamp (the 200-doc wiring pair is exactly such a file)
        detailed = [r for r in rs if r["system"].startswith(("Darwin", "Linux"))
                    or isinstance(r["corpus_n"], int)]
        legacy = [r for r in rs if r not in detailed]
        for r in detailed:
            L.append(f"| {r['ts']} | {r['file']} | {r['corpus_n']} | {r['corpus_sha']} | "
                     f"{r['patch']} | {r['config']} | {r['system']} | "
                     f"{'YES' if r['quotable'] else 'no'} | {r['why']} |")
        if legacy:
            span = f"{legacy[0]['ts']}..{legacy[-1]['ts']}" if len(legacy) > 1 \
                else str(legacy[0]["ts"])
            L.append(f"| {span} | {fam} (x{len(legacy)}) | UNKNOWN | UNKNOWN | UNKNOWN | "
                     f"UNKNOWN | pre-stamp | no | {legacy[0]['why']} |")

    L += ["", "### Box / S3 artifacts NOT readable from this machine", "",
          "Named from operator-reported run ids in-session; every metric UNKNOWN until the "
          "JSON is read (regenerate on the box, or `aws login` and sync).", "",
          "| ts | artifact | what | status |", "|---|---|---|---|"]
    for ts, name, what, status in BOX_REPORTED:
        L.append(f"| {ts} | {name} | {what} | {status} |")

    L += ["", "### S3 listing", ""]
    if s3_ok:
        L += ["```", s3[:4000], "```"]
    else:
        L += [f"UNKNOWN — `aws s3 ls` failed from this machine: `{s3.splitlines()[0] if s3 else rc}`.",
              "Run `aws login` (SSO) and regenerate, or regenerate on the box (instance role)."]

    L += ["", "## 2. Headline metrics — quotable runs only", ""]
    quot = [r for r in rows if r["quotable"]]
    if not quot:
        L += ["**No result JSON on this machine is quotable** (every parsed file is "
              "macOS/arm64 wiring validation or a pre-stamp laptop probe). The quotable set "
              "lives on the box; regenerate there. The macOS 200-doc pair is shown below as "
              "WIRING REFERENCE ONLY — never to be quoted:", ""]
        ref = sorted((r for r in rows if isinstance(r["corpus_n"], int)
                      and r["corpus_n"] >= 200), key=lambda r: str(r["ts"]))[-2:]
        for r in ref[:2]:
            L.append(f"### {r['file']}  (NOT QUOTABLE — wiring reference)")
            for arm in ("llamaindex_http_pdf", "rocketride_pdf"):
                hl = headline(r["data"], arm)
                if not hl:
                    continue
                L += ["", f"**{arm}**", "",
                      "| cell | docs/s | chunks/s | p50 | p95 | cpu_s/doc | cores | util |",
                      "|---|---|---|---|---|---|---|---|"]
                for c in hl:
                    L.append("| " + " | ".join(str(x) if x is not None else "UNKNOWN"
                                               for x in c) + " |")
            gv = g(r["data"], "gate_verdicts", default=None)
            L.append("")
            L.append(f"gate_verdicts: {json.dumps({a: {s: v.get('PASS') for s, v in x.items() if isinstance(v, dict)} for a, x in gv.items()}) if isinstance(gv, dict) else 'UNKNOWN (predates three-verdict export)'}")
            L.append("cgroup anon peak: UNKNOWN (macOS has no cgroup; box runs only)")
    else:
        for r in quot:
            L.append(f"### {r['file']}")
            for arm in ("llamaindex_http_pdf", "rocketride_pdf"):
                hl = headline(r["data"], arm)
                if not hl:
                    L.append(f"{arm}: metrics UNKNOWN (not in file)")
                    continue
                L += ["", f"**{arm}**", "",
                      "| cell | docs/s | chunks/s | p50 | p95 | cpu_s/doc | cores | util |",
                      "|---|---|---|---|---|---|---|---|"]
                for c in hl:
                    L.append("| " + " | ".join(str(x) if x is not None else "UNKNOWN"
                                               for x in c) + " |")

    # -------- 3. speedup + parallel efficiency, Shashi's definitions exactly --------
    L += ["", "## 3. Speedup and parallel efficiency", "",
          "`metrics_shared.py` does NOT compute these (verified by grep — no such symbol).",
          "Definitions adopted from Shashi at `83a1512`:", "",
          "* `speedup_blast_over_sequential` = blast **chunks_per_s** / sequential "
          "**chunks_per_s**, same arm, same corpus (`metrics.py:53-59`, fed chunks_per_s at "
          "`:133-134`). His words: \"ratio of ratios — immune to the 'you gave one side more "
          "workers' objection because each side is normalized against itself.\"",
          "* `parallel_efficiency` = speedup / concurrency (`metrics.py:62-66`); the divisor "
          "is `RR_THREADS` for the engine arm and `HS_WORKERS` for the framework arm "
          "(`bench.py:805,1013-1016`). 1.0 = perfect linear scaling.", "",
          "**CHUNKS per second, not docs** — a blast-docs/s-only figure cannot produce this "
          "number; it needs the SEQUENTIAL leg's chunks_per_s from the same corpus.", ""]
    demo = sorted((r for r in rows if isinstance(r["corpus_n"], int)
                   and r["corpus_n"] >= 200), key=lambda r: str(r["ts"]))[-1:]
    for r in demo[:1]:
        L.append(f"Demonstration on the macOS wiring pair ({r['file']} — NOT QUOTABLE):")
        L.append("")
        L.append("| arm | seq chunks/s (warm64) | blast chunks/s (warm64) | speedup | "
                 "divisor | parallel_efficiency |")
        L.append("|---|---|---|---|---|---|")
        for arm, div, divname in (("llamaindex_http_pdf", 14, "WORKERS=14"),
                                  ("rocketride_pdf", "UNKNOWN", "threads not passed (pre-P2)")):
            cells = g(r["data"], "metrics", "arms", arm, default={})
            sq = g(cells, "sequential_warm64", "chunks_per_s", default=None)
            bl = g(cells, "blast_warm64", "chunks_per_s", default=None)
            sp = round(bl / sq, 3) if isinstance(sq, (int, float)) and \
                isinstance(bl, (int, float)) and sq > 0 else "UNKNOWN"
            pe = (round(sp / div, 4) if isinstance(sp, float) and isinstance(div, int)
                  else "UNKNOWN")
            L.append(f"| {arm} | {sq} | {bl} | {sp} | {divname} | {pe} |")
    L += ["", "Box values: UNKNOWN from this machine — regenerate there, or compute as "
          "`blast.chunks_per_s / sequential.chunks_per_s` then `/24` (RR threads) once the "
          "pinned sequential 10k completes. **No pinned quotable pair exists yet**: the v2 "
          "blast is done; its sequential counterpart's result JSON is "
          "not present here (status UNKNOWN)."]

    OUT.write_text("\n".join(L) + "\n")
    print(f"written -> {OUT}  ({len(rows)} local files inventoried, "
          f"{len(quot)} quotable, s3={'listed' if s3_ok else 'UNKNOWN'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
