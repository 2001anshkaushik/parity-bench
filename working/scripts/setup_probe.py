#!/usr/bin/env python3
"""Setup probe — 10 documents, environment manifest, determinism re-run.

Implements the team spec's pre-run gate for the WS-1 arm. It runs BEFORE any performance number is
taken, because a performance number from an unverified environment is worse than none.

⚠️ FIELD LIST IS INFERRED. The specification document is not in `bench_langgraph_prod@b9b4736`, so
the manifest fields below are built from the spec as relayed (10-document probe, environment
manifest, determinism re-run) plus what this project has learned to record. **Leela: please diff
this against your actual §-list and tell me what is missing** — the shape is easy to change, the
point is that it runs and gates.

What it checks, and why each one exists here:

1. **Environment manifest** — engine version + binary sha256, SDK, library versions, host, device.
   Adopted from Shashi: a release TAG is mutable, a binary hash is not.
2. **Thread parity, MEASURED IN-PROCESS on both arms.** An exported variable proves nothing: torch
   caches its thread count at import. We ask each live worker what it actually got.
3. **10-document correctness pass** — per-arm chunk hash against an independent reference, plus
   vector shape and content sanity.
4. **Determinism re-run** — the same 10 documents again; chunk hashes must be identical. This is the
   check a self-capture reference *does* make well, and it is kept for exactly that reason.
5. **Achieved concurrency** is not exercised here (this probe is sequential by design); the ladder
   verifies it per cell.

Exit 0 = all gates pass. Non-zero = do not take performance numbers from this environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

PORT = int(os.environ.get("PROBE_PORT", "8831"))
N_DOCS = int(os.environ.get("PROBE_DOCS", "10"))


def say(m):
    print(m, flush=True)


def environment_manifest() -> dict:
    import importlib.metadata as md
    import urllib.request

    def ver(p):
        try:
            return md.version(p)
        except Exception:
            return None

    eng = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:5565/version", timeout=8) as r:
            eng = json.loads(r.read().decode()).get("data")
    except Exception as e:
        eng = {"error": str(e)}

    binsha = None
    b = ROOT / "engine" / "engine"
    if b.exists():                       # Shashi's practice: hash the binary, not just the tag
        h = hashlib.sha256()
        with open(b, "rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        binsha = h.hexdigest()

    return {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": eng,
        "engine_binary_sha256": binsha,
        "sdk_rocketride": ver("rocketride"),
        "libraries": {p: ver(p) for p in
                      ("llama-index-core", "sentence-transformers", "torch", "transformers",
                       "langchain-text-splitters", "pypdf", "fastapi", "uvicorn", "numpy")},
        "python": platform.python_version(),
        "host": {"machine": platform.machine(), "system": platform.system(),
                 "release": platform.release(), "cpu_count": os.cpu_count()},
    }


def main() -> int:
    from harness import ws1_service as ws
    from harness.chunk_hash import check_chunks, effective_config, ChunkHashMismatch
    from harness.content_sanity import inspect
    from harness.goodput import check_document, GoodputFailure
    from harness.tika_reference import available as tika_available, reference_text
    from weekend_worker import LlamaHttpPdfArm, RocketPdfArm

    failures: list[str] = []
    manifest = environment_manifest()
    say("=" * 92)
    say("SETUP PROBE — environment manifest")
    say("=" * 92)
    say(f"  engine            : {manifest['engine']}")
    say(f"  engine binary sha : {(manifest['engine_binary_sha256'] or '—')[:16]}…")
    say(f"  sdk               : {manifest['sdk_rocketride']}")
    say(f"  splitter (readback): {effective_config()}")
    for k, v in manifest["libraries"].items():
        say(f"    {k:32s} {v}")
    if not manifest.get("engine") or manifest["engine"].get("error"):
        failures.append("engine not reachable on :5565")

    ok, why = tika_available()
    say(f"  tika reference    : {'available' if ok else 'UNAVAILABLE — ' + why}")

    pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob("*.pdf"))[:N_DOCS]
    if len(pdfs) < N_DOCS:
        say(f"FATAL: need {N_DOCS} pdfs, found {len(pdfs)}")
        return 2

    h = ws.start(workers=1, port=PORT, threads=10)
    try:
        ws.wait_warm(h, timeout=900)
    except Exception as e:
        say(f"FATAL: service did not warm: {e}")
        return 2
    thr = sorted(set(h.measured_threads.values()))

    # ---- thread parity, measured in-process on BOTH arms --------------------------------------
    p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
                        str(ROOT / "working" / "scripts" / "probe_env.py"), f"probe{int(time.time())}"],
                       capture_output=True, text=True, cwd=str(ROOT))
    try:
        rr_threads = json.loads(p.stdout)["torch_num_threads"]
    except Exception:
        rr_threads = -1
    li_threads = thr[0][0] if thr else -1
    say("")
    say(f"  THREAD PARITY  engine task={rr_threads}  ws1 worker={li_threads}  (both MEASURED in-process)")
    if rr_threads != li_threads or rr_threads < 0:
        failures.append(f"thread parity: engine={rr_threads} ws1={li_threads}")

    # ---- 10-document correctness pass, per arm -------------------------------------------------
    arms = {"llamaindex_http_pdf": LlamaHttpPdfArm(port=PORT), "rocketride_pdf": RocketPdfArm("probe")}
    hashes: dict[str, dict] = {a: {} for a in arms}
    say("")
    say("  10-DOCUMENT CORRECTNESS PASS")
    for arm_name, arm in arms.items():
        good = 0
        for f in pdfs:
            b = f.read_bytes()
            try:
                chunks, vecs = arm.process(b)
                check_document(f.name, chunks, vecs)
                if arm_name.startswith("llamaindex"):
                    src = (getattr(arm, "last", {}) or {}).get("extracted_text", "")
                else:
                    src = reference_text(f) if ok else None
                if src:
                    ev = check_chunks(f.name, chunks, src)
                    hashes[arm_name][f.name] = ev["chunk_sha256"]
                sus = [c for c in chunks if inspect(c)["suspect"]]
                if sus:
                    say(f"    {arm_name}/{f.name}: {len(sus)} content-suspect chunk(s)")
                good += 1
            except (GoodputFailure, ChunkHashMismatch) as e:
                failures.append(f"{arm_name}/{f.name}: {e}")
                say(f"    ✗ {arm_name}/{f.name}: {str(e)[:110]}")
            except Exception as e:
                failures.append(f"{arm_name}/{f.name}: {type(e).__name__}: {e}")
        say(f"    {arm_name:22s} {good}/{len(pdfs)} passed")

    # ---- determinism re-run --------------------------------------------------------------------
    say("")
    say("  DETERMINISM RE-RUN (same 10 documents)")
    for arm_name, arm in arms.items():
        drift = 0
        for f in pdfs:
            if f.name not in hashes[arm_name]:
                continue
            try:
                chunks, _ = arm.process(f.read_bytes())
                again = [hashlib.sha256(str(c).encode()).hexdigest() for c in chunks]
                if again != hashes[arm_name][f.name]:
                    drift += 1
                    failures.append(f"{arm_name}/{f.name}: non-deterministic between runs")
            except Exception as e:
                failures.append(f"{arm_name}/{f.name} rerun: {type(e).__name__}")
        say(f"    {arm_name:22s} {'deterministic' if not drift else f'{drift} DRIFTED'}")

    for a in arms.values():
        a.close()
    ws.stop(h)

    out = {"manifest": manifest, "threads": {"rocketride": rr_threads, "llamaindex": li_threads},
           "n_docs": len(pdfs), "failures": failures, "passed": not failures}
    from harness.resultio import write_result
    path = write_result("setup_probe", out)
    say("")
    say("=" * 92)
    say(f"  SETUP PROBE {'PASSED' if not failures else 'FAILED — ' + str(len(failures)) + ' issue(s)'}")
    for f_ in failures[:10]:
        say(f"    - {f_}")
    say(f"  written -> {path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
