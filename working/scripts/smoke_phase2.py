#!/usr/bin/env python3
"""Phase-2 pre-flight. Under 5 minutes, and nothing long runs until it passes.

THREE CHECKS, each answering a question a 10k run cannot afford to answer late:

  A. DUPLICATION FIXTURE — does the patch do what we say it does?
     Five documents we have already measured as duplicating. On rr:stock every one must report
     repeat_factor 2; on rr:patched every one must report 1. **Keyed on sha256, not filename**:
     the same bytes are `000_000159.pdf` here and `000159.pdf` under Shashi's naming, and a
     fixture keyed on a name breaks the moment anyone renames a corpus.

     THE CONTROL DIRECTION MATTERS. If stock does NOT duplicate, the conclusion is that the
     FIXTURE is broken — wrong documents, wrong engine, wrong image — not that the patch is
     unnecessary. A patched-looking stock build is the one result that must never be read as
     good news, so it exits non-zero with that spelled out.

  B. GOLDEN RECORD — 25 documents whose chunk hashes we already hold, re-sent and asserted
     hash for hash, attributed by basename (Leela rr_driver.py:100: position-based zip
     silently mis-credits work if the engine reorders).

  C. READ-BACKS — cpuset actually in effect, worker count, thread pins INSIDE the task
     processes, corpus verified against the manifest. Every one of these is a config value we
     have previously believed and been wrong about.

    SMOKE_EXTERNAL=1 python3 working/scripts/smoke_phase2.py
    EXPECT_PATCH=1 SMOKE_EXTERNAL=1 python3 working/scripts/smoke_phase2.py   # against rr:patched
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import experiment_common as ec          # noqa: E402  (loads credentials)
from harness import gates_shared as gs               # noqa: E402
from harness.resultio import write_result            # noqa: E402

CORPUS = ROOT / "corpus" / "govdocs1" / "pdfs"
MANIFEST = ROOT / "working" / "results" / "corpus_manifest.jsonl"
EXPECT_PATCH = os.environ.get("EXPECT_PATCH", "0") not in ("", "0")
GOLDEN_N = int(os.environ.get("SMOKE_GOLDEN_N", "25"))
say = ec.say

# The five documents measured as duplicating on stock 3.3.1, pinned by CONTENT.
# sha256 -> the chunk count observed, for context only; the assertion is on repeat_factor.
FIXTURE_SHA = {
    "d2a4eb9c41a0fabd": 164,
    "2d6b5053716f4037": 276,
    "bc44bd5e4103696b": 1872,
    "f51fc895ceac979f": 132,
    "f1c250fa02fa8e74": 344,
}

_fails: list[str] = []


def fail(msg: str) -> None:
    say(f"  FAIL  {msg}")
    _fails.append(msg)


def sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def by_content() -> dict[str, Path]:
    """sha256[:16] -> path, over the corpus. Built once; the fixture never names a file."""
    out = {}
    for p in sorted(CORPUS.glob("*.pdf")):
        out[sha16(p.read_bytes())] = p
    return out


# ------------------------------------------------------------------ A. duplication fixture

def check_duplication(index: dict[str, Path]) -> dict:
    say(f"\nA. duplication fixture — expecting {'repeat_factor 1 (PATCHED)' if EXPECT_PATCH else 'repeat_factor 2 (STOCK)'}")
    from weekend_worker import RocketPdfArm
    missing = [s for s in FIXTURE_SHA if s not in index]
    if missing:
        fail(f"fixture documents absent from the corpus by sha256: {missing}. The fixture is "
             "pinned to CONTENT, so this means the corpus changed, not that the patch works.")
        return {"error": "fixture documents missing", "missing_sha": missing}

    arm = RocketPdfArm("dupfix")
    rows, factors = [], {}
    try:
        for s, expect_chunks in FIXTURE_SHA.items():
            p = index[s]
            chunks, _ = arm.process(p.read_bytes())
            hs = [gs.chunk_hash(c) for c in chunks]
            k = gs.repeat_factor(hs)
            factors[s] = k
            rows.append({"doc": p.name, "sha256_16": s, "ok": bool(chunks),
                         "n_chunks": len(chunks), "chunk_sha256": hs, "repeat_factor": k,
                         "chunks_when_measured": expect_chunks})
            say(f"    {p.name:<20} sha={s}  chunks={len(chunks):>5}  repeat_factor={k}")
    finally:
        try:
            arm.close()
        except Exception:
            pass

    want = 1 if EXPECT_PATCH else 2
    wrong = {s: k for s, k in factors.items() if k != want}
    if wrong:
        if not EXPECT_PATCH:
            fail(f"STOCK build did NOT duplicate {len(wrong)}/{len(FIXTURE_SHA)} fixture "
                 f"documents (got {sorted(set(wrong.values()))}, wanted 2). **Read this as a "
                 "BROKEN FIXTURE, not as a patch that is unnecessary** — wrong image, wrong "
                 "engine build, or these documents no longer duplicate. Do not build on it.")
        else:
            fail(f"PATCHED build still duplicates {len(wrong)}/{len(FIXTURE_SHA)} documents "
                 f"({wrong}). The patch did not take — check the build log for "
                 "'BUG_CHUNK_DUPLICATION patch applied'.")
    else:
        say(f"  PASS  all {len(FIXTURE_SHA)} fixture documents report repeat_factor {want}")

    # The sensitive detector, on the same records — this is the number we will quote.
    sd = gs.self_duplication(rows)
    say(f"  self_duplication: {sd['duplicated_docs']}/{sd['checked']} duplicated, "
        f"factors={sd['factors']}")
    return {"expect_patch": EXPECT_PATCH, "want_repeat_factor": want,
            "factors": factors, "wrong": wrong, "self_duplication": sd, "records": rows}


# ------------------------------------------------------------------ B. golden record

def check_golden(index: dict[str, Path]) -> dict:
    say(f"\nB. golden record — {GOLDEN_N} documents, every chunk hash asserted")
    gold_path = ROOT / "working" / "results" / "golden_chunk_hashes.json"
    if not gold_path.exists():
        fail(f"no golden file at {gold_path}. Build it from a prior run's per-doc JSONL with "
             "--build-golden BEFORE trusting any Phase-2 chunk comparison; an absent reference "
             "is UNVERIFIED, never a pass.")
        return {"error": "no golden reference", "path": str(gold_path)}

    gold = json.loads(gold_path.read_text())        # {sha256_16: [chunk hashes]}
    usable = [s for s in gold if s in index][:GOLDEN_N]
    if len(usable) < GOLDEN_N:
        fail(f"only {len(usable)}/{GOLDEN_N} golden documents are present in the corpus by "
             "sha256 — the reference and the corpus disagree.")
    from weekend_worker import RocketPdfArm
    arm = RocketPdfArm("golden")
    same = diff = 0
    mismatches = []
    try:
        for s in usable:
            p = index[s]
            chunks, _ = arm.process(p.read_bytes())
            got = [gs.chunk_hash(c) for c in chunks]
            if got == gold[s]:
                same += 1
            else:
                diff += 1
                mismatches.append({"sha256_16": s, "doc": p.name,
                                   "expected_n": len(gold[s]), "got_n": len(got)})
    finally:
        try:
            arm.close()
        except Exception:
            pass
    say(f"  {same}/{len(usable)} byte-identical to the golden reference")
    if diff:
        fail(f"{diff} document(s) differ from the golden chunk hashes: {mismatches[:5]}")
    return {"compared": len(usable), "identical": same, "differing": diff,
            "mismatches": mismatches[:10]}


# ------------------------------------------------------------------ C. read-backs

def check_readbacks() -> dict:
    say("\nC. read-backs — measured, never trusted from config")
    out: dict = {}

    aff = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    out["driver_affinity"] = {"cpus": aff, "n": len(aff), "host_cpu_count": os.cpu_count()}
    say(f"  driver affinity: {len(aff)} cpus {aff[:4]}{'..' if len(aff) > 4 else ''} "
        f"(host reports {os.cpu_count()})")
    if aff and len(aff) == os.cpu_count():
        fail("driver affinity equals the host CPU count — `taskset -c 24-31` did not take, so "
             "the driver is competing with the arm it is measuring.")

    for role, container in (("llamaindex", ec.LI_CONTAINER), ("rocketride", ec.RR_CONTAINER)):
        if not ec.EXTERNAL:
            continue
        cs = ec._run_docker(container, "{{.HostConfig.CpusetCpus}}")
        nano = ec._run_docker(container, "{{.HostConfig.NanoCpus}}")
        out[f"{role}_cpuset"] = cs
        out[f"{role}_nano_cpus"] = nano
        say(f"  {role:<11} cpuset={cs!r}  nano_cpus={nano!r}")
        if not cs:
            fail(f"{role}: no cpuset in effect — the arm is not pinned.")
        if nano and nano not in ("0", "<no value>"):
            fail(f"{role}: --cpus is still set (NanoCpus={nano}). A CFS quota alongside a "
                 "cpuset is two different limiters; remove --cpus.")

    if ec.EXTERNAL:
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{ec.PORT}/health", timeout=15) as r:
                h = json.loads(r.read().decode())
            out["li_health"] = h
            say(f"  llamaindex workers: declared={h.get('declared_workers')} "
                f"warm={h.get('warm_workers')} valid={h.get('warm_count_valid')}")
            say(f"  llamaindex threads INSIDE the worker: torch={h.get('torch_threads')} "
                f"interop={h.get('torch_interop')} env={h.get('thread_env')}")
            if h.get("warm_count_valid") is False:
                fail("warm_count_valid=false — the readiness census exceeds the population.")
            if h.get("torch_threads") not in (1, None):
                fail(f"llamaindex torch_threads={h.get('torch_threads')}, expected 1.")
        except Exception as e:
            fail(f"llamaindex /health unreachable: {type(e).__name__}: {e}")

    say("  corpus: verifying against the manifest ...")
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    bad = [r["file"] for r in rows if not (CORPUS / r["file"]).exists()
           or (CORPUS / r["file"]).stat().st_size != r["bytes"]][:5]
    out["corpus"] = {"manifest_docs": len(rows), "missing_or_wrong_size": bad}
    if bad:
        fail(f"corpus does not match the manifest: {bad}")
    else:
        say(f"  PASS  {len(rows)} documents match the manifest by name and size")
    return out


def build_golden(perdoc: Path, index: dict[str, Path]) -> int:
    """Write the golden reference from a prior run's per-document JSONL.

    KEYED ON CONTENT. The records name documents as `000_000159.pdf`; the reference is stored
    under sha256[:16] so it survives any renaming or corpus rebuild. A record whose bytes are no
    longer in the corpus is skipped and counted, never silently dropped.
    """
    by_name = {p.name: s for s, p in index.items()}
    gold, skipped = {}, 0
    for line in perdoc.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not r.get("ok") or not isinstance(r.get("chunk_sha256"), list):
            continue
        s = by_name.get(r.get("doc"))
        if s is None:
            skipped += 1
            continue
        gold[s] = r["chunk_sha256"]
    out = ROOT / "working" / "results" / "golden_chunk_hashes.json"
    out.write_text(json.dumps(gold, indent=0, sort_keys=True))
    say(f"golden reference: {len(gold)} documents -> {out}"
        + (f"  ({skipped} records skipped — bytes not in the corpus)" if skipped else ""))
    return 0


def main() -> int:
    if "--build-golden" in sys.argv:
        src = Path(sys.argv[sys.argv.index("--build-golden") + 1])
        if not src.exists():
            say(f"BLOCKER: {src} does not exist")
            return 2
        return build_golden(src, by_content())
    t0 = time.time()
    say(f"PHASE-2 SMOKE  (expect_patch={EXPECT_PATCH}, external={ec.EXTERNAL})")
    index = by_content()
    say(f"corpus indexed by content: {len(index)} documents")

    out = {"experiment": "smoke_phase2", "expect_patch": EXPECT_PATCH,
           "provenance": ec.provenance(),
           "duplication_fixture": check_duplication(index),
           "golden_record": check_golden(index),
           "read_backs": check_readbacks()}
    out["wall_s"] = round(time.time() - t0, 1)
    out["PASS"] = not _fails
    out["failed_checks"] = _fails
    say(f"\nelapsed {out['wall_s']}s")
    return ec.verdict_exit(not _fails, write_result("smoke_phase2", out), _fails)


if __name__ == "__main__":
    raise SystemExit(main())
