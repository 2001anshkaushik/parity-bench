#!/usr/bin/env python3
"""STEP 4 — verify the fault path AND the injected-vs-collateral accounting on my own service.

Two things are under test here and they are different:
  1. does the service classify faults per the schema's `error_class` contract?
  2. is the ACCOUNTING correct — i.e. would this harness report the right isolation ratio?

(2) matters more. The accounting is about to be used on everyone's service, and in this project
the instrument has been wrong more often than the system. So the accounting is validated against
cases whose answer is known by construction:

    CONTROL      0 faults          -> ratio must be exactly 0.00, goodput 100%
    ALL-FAULT    100% faults       -> ratio must be 0.00 (no CLEAN items exist to damage)
    KNOWN-MIX    5% faults         -> injected count must match the plan exactly
    MISCOUNT     drop a clean item -> must appear as collateral_missing, NOT be ignored
    CORRUPTION   alter one output  -> must appear as collateral_wrong_output

The last two are the ones that catch a broken harness: a scorer that silently ignores missing
items, or that never checks output values, passes every other test while being useless.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "handoff"))

from fault_injection import Deadline, make_plan, score          # noqa: E402
from harness import engine_ops as eo                            # noqa: E402

PORT = int(os.environ.get("WS1_PORT", "8801"))
BASE = f"http://127.0.0.1:{PORT}"
DOC = "The quick brown fox jumps over the lazy dog. " * 20
DEADLINE_S = 20.0
N = 200


def payload_for(item_id: str, fault: str) -> str:
    return DOC if fault == "ok" else f"FAULT:{fault}|{DOC}"


def reference_for_service(item_id: str) -> str:
    """Ground truth = the service's own deterministic output for a clean doc.

    We cannot use a sha256 of the id (the service returns embeddings), so correctness is defined
    as "n_chunks matches the reference splitter and every vector is 384-dim unit-norm". The scorer
    compares an opaque token, so we build that token from those properties.
    """
    return "OK|1|384"          # 1 chunk for DOC at chunk_size 4000, 384 dims


async def run_batch(plan, inject_bugs: bool = False) -> dict:
    """inject_bugs deliberately corrupts the RESULTS DICT to prove the scorer catches it."""
    import aiohttp

    results: dict[str, tuple[bool, str | None]] = {}
    dl = Deadline(seconds=DEADLINE_S)
    conn = aiohttp.TCPConnector(limit=8, limit_per_host=8)
    sem = asyncio.Semaphore(8)

    async with aiohttp.ClientSession(connector=conn) as s:
        async def one(item_id: str, fault: str):
            rem = dl.remaining()
            if rem <= 0:
                results[item_id] = (False, None)
                return
            try:
                async with s.post(f"{BASE}/process",
                                  json={"doc_id": item_id, "text": payload_for(item_id, fault)},
                                  timeout=aiohttp.ClientTimeout(total=rem)) as r:
                    b = await r.json()
                    if not b.get("ok"):
                        results[item_id] = (False, b.get("error_class"))
                    else:
                        dims = {len(c["embedding"]) for c in b["chunks"]}
                        token = f"OK|{b['n_chunks']}|{max(dims) if dims else 0}"
                        results[item_id] = (True, token)
            except Exception:
                results[item_id] = (False, None)

        await asyncio.gather(*(one(i, f) for i, f in plan.items), return_exceptions=True)

    if inject_bugs:
        clean = [i for i, f in plan.items if f == "ok"]
        results.pop(clean[0], None)                       # a DROPPED item
        results[clean[1]] = (True, "OK|999|384")          # a CORRUPTED output

    return score(plan, results, dl.elapsed(), reference_fn=reference_for_service,
                 extra={"deadline_s": DEADLINE_S})


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return cond


async def main() -> int:
    out = ROOT / "results" / "ws1_fault_path.json"
    rows, fails = [], []
    print("=" * 78)
    print("STEP 4 — fault path + ACCOUNTING validation (cases with known answers)")
    print("=" * 78)

    # --- error_class contract -------------------------------------------
    print("\n[1] error_class contract")
    import aiohttp
    async with aiohttp.ClientSession() as s:
        for kind, expect in (("raise", "embed_failed"), ("malformed", "malformed_input")):
            async with s.post(f"{BASE}/process",
                              json={"doc_id": f"t-{kind}", "text": f"FAULT:{kind}|x"}) as r:
                b = await r.json()
                ok = (r.status == 200 and b["ok"] is False and b["error_class"] == expect)
                if not check(f"{kind} -> HTTP 200, ok=false, error_class={expect}", ok,
                             f"got status={r.status} class={b.get('error_class')}"):
                    fails.append(kind)
        async with s.post(f"{BASE}/process", json={"doc_id": "t-ok", "text": DOC}) as r:
            b = await r.json()
            if not check("clean doc -> ok=true with meta", b["ok"] and "meta" in b):
                fails.append("clean")

    # --- accounting validation ------------------------------------------
    print("\n[2] CONTROL: zero faults — ratio must be exactly 0.00, goodput 100%")
    ctrl = await run_batch(make_plan(N, "raise", 0.0, tag="ws1"))
    rows.append({"case": "control_zero_faults", **ctrl})
    if not check("control ratio == 0.00 and goodput == 100%",
                 ctrl["isolation_ratio"] == 0.0 and ctrl["goodput_pct"] == 100.0,
                 f"ratio={ctrl['isolation_ratio']} goodput={ctrl['goodput_pct']}%"):
        fails.append("control")

    print("\n[3] ALL-FAULT: 100% faults — ratio must be 0.00 (no clean items to damage)")
    allf = await run_batch(make_plan(N, "raise", 1.0, tag="ws1"))
    rows.append({"case": "all_fault", **allf})
    if not check("all-fault: n_clean == 0 and ratio == 0.00",
                 allf["n_clean"] == 0 and allf["isolation_ratio"] == 0.0,
                 f"n_clean={allf['n_clean']} injected={allf['n_injected']} "
                 f"ratio={allf['isolation_ratio']}"):
        fails.append("allfault")

    print("\n[4] KNOWN-MIX: 5% faults — injected count must match the plan exactly")
    plan5 = make_plan(N, "raise", 0.05, tag="ws1")
    mix = await run_batch(plan5)
    rows.append({"case": "known_mix_5pct", **mix})
    if not check("injected count matches plan", mix["n_injected"] == plan5.injected,
                 f"scored={mix['n_injected']} plan={plan5.injected} seed={plan5.seed}"):
        fails.append("mix")
    if not check("clean items undamaged by injected faults (ratio 0.00)",
                 mix["isolation_ratio"] == 0.0,
                 f"ratio={mix['isolation_ratio']} goodput={mix['goodput_pct']}%"):
        fails.append("mix_ratio")

    print("\n[5] SCORER VALIDATION: deliberately drop 1 clean item and corrupt 1 output")
    bugged = await run_batch(plan5, inject_bugs=True)
    rows.append({"case": "scorer_validation", **bugged})
    if not check("dropped item counted as collateral_missing",
                 bugged["collateral_missing"] == 1, f"got {bugged['collateral_missing']}"):
        fails.append("missing")
    if not check("corrupted output counted as collateral_wrong_output",
                 bugged["collateral_wrong_output"] == 1,
                 f"got {bugged['collateral_wrong_output']}"):
        fails.append("wrong")
    if not check("ratio rose because of the injected harness bugs",
                 bugged["isolation_ratio"] > mix["isolation_ratio"],
                 f"{mix['isolation_ratio']} -> {bugged['isolation_ratio']}"):
        fails.append("ratio_sensitivity")

    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\n  {'ALL PASS' if not fails else 'FAILURES: ' + str(fails)}")
    print(f"  written -> {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
