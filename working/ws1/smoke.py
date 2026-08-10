#!/usr/bin/env python3
"""Smoke test for the WS-1 LlamaIndex service. Exits non-zero on any failure.

Referenced by RUNBOOK_LLAMAINDEX.md §3.4. Checks the things that would silently invalidate a
measurement rather than obviously break the service:
  * device declared == device resolved  (a service computing on a different device than it reports)
  * effective_concurrency is the MEASURED value, not the worker count
  * embeddings are 384-dim and unit-normalised
  * multi-chunk output matches a reference RecursiveCharacterTextSplitter byte-for-byte
  * empty document -> ok:true with 0 chunks, not an error
  * an injected fault returns HTTP 200 + ok:false + the right error_class

Usage:  ../.venv/bin/python ws1/smoke.py [--port 8801]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read().decode())


def post(base: str, path: str, obj: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    print(f"WS-1 LlamaIndex smoke test -> {base}")

    print("\n[health]")
    try:
        h = get(base, "/health")
    except Exception as e:
        print(f"  cannot reach service: {e}")
        print("  is it running?  WS1_DEVICE=cpu WS1_WORKERS=8 bash ws1/run_service.sh")
        return 2
    check("status ok", h.get("status") == "ok", str(h.get("status")))
    check("model_loaded", h.get("model_loaded") is True)

    print("\n[manifest]")
    m = get(base, "/manifest")
    check("device declared == resolved", m["device"] == m["resolved_device"].split(":")[0],
          f"declared={m['device']} resolved={m['resolved_device']}")
    check("device is cpu (parity requirement)", m["device"] == "cpu", m["device"])
    check("splitter is RecursiveCharacterTextSplitter",
          m["splitter"] == "RecursiveCharacterTextSplitter", m["splitter"])
    check("chunk 4000/200", m["chunk_size"] == 4000 and m["chunk_overlap"] == 200)
    check("384 dims, normalized", m["embedding_dim"] == 384 and m["normalized"] is True)
    check("effective_concurrency is MEASURED not worker count",
          "MEASURED" in m.get("concurrency_source", ""),
          f"eff={m['effective_concurrency']} declared_workers={m['declared_workers']}")

    print("\n[single chunk]")
    r = post(base, "/process", {"doc_id": "smoke-1",
                                "text": "Machine learning systems require careful evaluation.",
                                "trace": True})
    check("ok + 1 chunk", r["ok"] and r["n_chunks"] == 1, f"n_chunks={r['n_chunks']}")
    v = r["chunks"][0]["embedding"]
    check("384 dims", len(v) == 384, str(len(v)))
    norm = math.sqrt(sum(x * x for x in v))
    check("unit norm", abs(norm - 1.0) < 1e-3, f"L2={norm:.6f}")
    check("timing present with trace=true", "timing_ms" in r, str(r.get("timing_ms")))

    print("\n[multi chunk vs reference splitter]")
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        long_text = "The quick brown fox jumps over the lazy dog. " * 700
        ref = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200,
                                             length_function=len).split_text(long_text + "\n")
        r2 = post(base, "/process", {"doc_id": "smoke-2", "text": long_text})
        svc = [c["text"] for c in r2["chunks"]]
        check("chunk count matches reference", len(svc) == len(ref), f"{len(svc)} vs {len(ref)}")
        check("chunk text matches reference byte-for-byte", svc == ref)
    except ImportError:
        check("langchain-text-splitters available for reference check", False, "not installed")

    print("\n[empty document]")
    r3 = post(base, "/process", {"doc_id": "smoke-3", "text": ""})
    check("empty -> ok:true, 0 chunks", r3["ok"] and r3["n_chunks"] == 0,
          f"ok={r3['ok']} n={r3['n_chunks']}")

    print("\n[fault path]")
    r4 = post(base, "/process", {"doc_id": "smoke-4", "text": "FAULT:raise|x"})
    check("injected fault -> HTTP 200 + ok:false + embed_failed",
          r4["ok"] is False and r4.get("error_class") == "embed_failed",
          f"ok={r4['ok']} class={r4.get('error_class')}")
    r5 = post(base, "/process", {"doc_id": "smoke-5", "text": "FAULT:malformed|x"})
    check("malformed -> malformed_input", r5.get("error_class") == "malformed_input",
          str(r5.get("error_class")))

    print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
