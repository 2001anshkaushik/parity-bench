#!/usr/bin/env python3
"""FAULT ISOLATION — Shashi's protocol (bench.py:526, wired at :662). Not our own.

PROTOCOL, copied rather than designed:

  1 poison document  b"%PDF-1.7\\n" + os.urandom(65536)
                     Claims to be a PDF and is not one, so it exercises the PARSER failure path
                     rather than upload validation. 64 KB of noise defeats magic-bytes-only
                     sniffing (Shashi bench.py:546-549).
  6 good documents   FAULT_GOOD = 6 (bench.py:540), from the pinned corpus.
  blast mode         the whole batch offered at once (bench.py:556).
  separate run       "exception paths and retries change timing, so a poisoned batch measures
                     resilience, not speed — mixing them contaminates both numbers"
                     (bench.py:527-529).
  engine restarted   bench.py:554, before the batch. Opt-in here — see EXP_RESTART below.
  recovery probe     a clean document afterwards (bench.py:563-566).

SCORED, in his field names: batch_survived, good_docs_ok, collateral_failures (THE metric),
service_alive_after, recovery_ok, surfacing. Plus Leela's time_to_next_success_s with the 60 s
attribution window (m4_m5_faults.py:13-45). A success-shaped empty response scores 0 for
surfacing — that is the whole point of the field.

TWO DEVIATIONS, both recorded in the result rather than hidden:

  * SEND SHAPE. Shashi and Leela both issue ONE batched `send_files` carrying the whole list;
    our client shape is N individual sends under a concurrency cap, so "blast" here means
    C = len(batch). The distinction matters for a fault run: a single batched call can fail as
    one unit, whereas N sends can fail individually, and per-request isolation is what
    production would need. Recorded as `send_shape`.
  * ENGINE RESTART. `EXP_RESTART=1` restarts the container first, matching the protocol.
    Default is 0 because the box is shared and a restart during another leg would destroy it.
    Not restarting is a real deviation and is recorded in `protocol_deviations`, never assumed
    harmless.

    SMOKE_EXTERNAL=1 python3 working/scripts/exp_fault_isolation.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness import experiment_common as ec          # noqa: E402  (also loads credentials)
from harness import fault_metrics as fm              # noqa: E402
from harness.resultio import write_result            # noqa: E402

FAULT_GOOD = int(os.environ.get("EXP_FAULT_GOOD", "6"))        # Shashi bench.py:540
POISON_BYTES = int(os.environ.get("EXP_POISON_BYTES", "65536"))
RESTART = os.environ.get("EXP_RESTART", "0") not in ("", "0")
RECOVERY_DOCS = int(os.environ.get("EXP_RECOVERY_DOCS", "1"))
say = ec.say


def poison() -> bytes:
    """Valid header, random body. os.urandom, not a fixed pattern: a fixed body could be cached
    or special-cased by a parser, and we want the ordinary failure path."""
    return b"%PDF-1.7\n" + os.urandom(POISON_BYTES)


def build_batch(good: list) -> list:
    """(name, bytes) pairs. The poison sits in the MIDDLE of the batch, not at the end.

    At the end, a framework that processes in order could finish every good document before
    ever touching it, and the run would report perfect isolation it never demonstrated.
    """
    items = [(p.name, p.read_bytes()) for p in good]
    items.insert(len(items) // 2, ("poison-x.pdf", poison()))
    return items


def run_llamaindex(items, concurrency):
    """Blocking urllib, so threads are the concurrency primitive — same as the smoke's blast."""
    import concurrent.futures as cf
    from weekend_worker import LlamaHttpPdfArm
    arm = LlamaHttpPdfArm(port=ec.PORT)

    def one(item):
        name, blob = item
        rec = ec.record(name, time.time_ns())
        try:
            chunks, vecs = arm.process(blob)
            # The service answers 200 with ok:false for a parse fault; that IS the service
            # reporting it, and it must not be flattened into `no_documents`.
            last = getattr(arm, "last", {}) or {}
            if not last.get("ok") and last.get("error_class"):
                rec["completion_ns"] = time.time_ns()
                rec.update(ok=False, reason="service_error", n_chunks=0, chunk_sha256=[],
                           error=str(last.get("error_class"))[:250],
                           error_class=str(last.get("error_class")))
                return rec
            return ec.finish_ok(rec, chunks, vecs)
        except Exception as e:
            return ec.finish_err(rec, e)

    survived = True
    try:
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            rows = list(ex.map(one, items))
    except Exception as e:
        # The batch call itself died rather than returning per-document outcomes.
        say(f"  !! llamaindex batch raised {type(e).__name__}: {e}")
        rows, survived = [], False
    finally:
        try:
            arm.close()
        except Exception:
            pass
    return rows, survived


def run_rocketride(items, concurrency):
    """One asyncio loop, C concurrent sends. Driving the arm from a thread pool would call
    run_until_complete on one loop from several threads and silently abandon coroutines — that
    bug alone once produced 7 of 8 false 'drift' results."""
    import asyncio
    import json as _j
    import uuid as _u
    from rocketride import RocketRideClient

    async def go():
        base = _j.loads((ROOT / "working" / "pipes" / ec.PIPE).read_text())
        base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                          f"fault-{os.getpid()}-{time.time()}"))
        pp = ROOT / "working" / "pipes" / "generated" / f"fault_{os.getpid()}.pipe"
        pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_text(_j.dumps(base))
        c = RocketRideClient()
        await c.connect(timeout=60000)
        tok = (await c.use(filepath=str(pp.relative_to(ROOT))))["token"]
        sem = asyncio.Semaphore(concurrency)
        rows = []

        async def one(name, blob):
            rec = ec.record(name, 0)
            async with sem:
                rec["submit_ns"] = time.time_ns()
                try:
                    out = await asyncio.wait_for(
                        c.send(tok, blob, mimetype="application/pdf"), timeout=900)
                    docs = out.get("documents") or []
                    rows.append(ec.finish_ok(rec,
                                             [d.get("page_content", "") for d in docs],
                                             [d.get("embedding") or [] for d in docs]))
                except Exception as e:
                    rows.append(ec.finish_err(rec, e))

        await asyncio.gather(*(one(n, b) for n, b in items))
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=60)
        except Exception:
            pass
        await c.disconnect()
        return rows

    try:
        return asyncio.run(go()), True
    except Exception as e:
        say(f"  !! rocketride batch raised {type(e).__name__}: {e}")
        return [], False


def recovery(arm_name: str, docs) -> list:
    """Shashi bench.py:563-566 — a CLEAN document after the fault. Sequential, concurrency 1:
    this asks whether the service still works at all, not how fast it is."""
    items = [(p.name, p.read_bytes()) for p in docs]
    runner = run_llamaindex if arm_name == "llamaindex_http_pdf" else run_rocketride
    rows, _ = runner(items, 1)
    return rows


def main() -> int:
    n_needed = FAULT_GOOD + RECOVERY_DOCS
    pdfs = ec.corpus(n_needed)
    good, clean = pdfs[:FAULT_GOOD], pdfs[FAULT_GOOD:FAULT_GOOD + RECOVERY_DOCS]
    items = build_batch(good)
    fault_docs = ["poison-x.pdf"]
    concurrency = len(items)                      # blast: the whole batch offered at once

    say("FAULT ISOLATION — Shashi's protocol (bench.py:526), separate run")
    say(f"  {FAULT_GOOD} good + 1 poison (%PDF-1.7 header + {POISON_BYTES} random bytes), "
        f"blast C={concurrency}")
    say(f"  poison at batch position {len(items) // 2} of {len(items)} (middle, not last)")
    say(f"  recovery probe: {len(clean)} clean document(s) after")
    say(f"  corpus sha256 = {ec.corpus_sha(pdfs)[:16]}  glob={ec.CORPUS_GLOB}")

    deviations = [
        "send shape: N individual sends at C=len(batch); Shashi and Leela both issue ONE "
        "batched send_files. A batched call can fail as one unit where N sends fail "
        "individually."]
    restarts = {}
    if RESTART and ec.EXTERNAL:
        for role, name in (("llamaindex", ec.LI_CONTAINER), ("rocketride", ec.RR_CONTAINER)):
            say(f"  restarting container {name} (EXP_RESTART=1)")
            restarts[role] = ec.restart_container(name)
            if not restarts[role].get("restarted"):
                say(f"  !! BLOCKER: could not restart {name}: {restarts[role].get('error')}")
                return 3
        time.sleep(15)                            # let the services bind before probing
    else:
        deviations.append(
            "engine NOT restarted before the batch (Shashi bench.py:554 restart_engine()). "
            "Residue from an earlier phase is inside this measurement. Set EXP_RESTART=1 to "
            "match the protocol.")

    out = {"experiment": "fault_isolation",
           "method_source": "Shashi bench.py:526 (protocol, scoreboard); "
                            "Leela m4_m5_faults.py:13-66 (blast radius, surfacing classifier)",
           "protocol": {"good_docs": FAULT_GOOD, "poison_docs": 1,
                        "poison": f"valid %PDF-1.7 header, {POISON_BYTES}B random body",
                        "poison_position": len(items) // 2,
                        "send_mode": "blast", "concurrency": concurrency,
                        "recovery_docs": len(clean),
                        "attribution_window_s": fm.ATTRIBUTION_WINDOW_S},
           "protocol_deviations": deviations,
           "container_restarts": restarts or None,
           "corpus": {"source": "govdocs1", "glob": ec.CORPUS_GLOB,
                      "rule": f"sorted({ec.CORPUS_GLOB})[:{n_needed}]",
                      "good": [p.name for p in good], "recovery": [p.name for p in clean],
                      "sha256": ec.corpus_sha(pdfs)},
           "provenance": ec.provenance(),
           "arms": {}}

    all_pass, failures = True, []
    for arm_name, runner, alive_fn in (
            ("llamaindex_http_pdf", run_llamaindex, ec.li_alive),
            ("rocketride_pdf", run_rocketride, ec.rr_alive)):
        say(f"\n{arm_name}: sending the poisoned batch")
        rows, survived = runner(items, concurrency)
        alive = alive_fn()
        say(f"  batch_survived={survived}  service_alive_after={alive}")
        rec_rows = recovery(arm_name, clean) if alive else None
        if rec_rows is None:
            say("  recovery probe SKIPPED — service not alive; recovery_ok records as None, "
                "never as False-by-omission")
        score = fm.score_arm(rows, fault_docs, survived, alive, rec_rows)
        passed, fails = fm.arm_pass(score)
        score["PASS"] = passed
        score["failed_checks"] = fails
        score["records"] = rows
        score["recovery_records"] = rec_rows
        out["arms"][arm_name] = score
        say(f"  good_docs_ok={score['good_docs_ok']}/{score['good_docs_total']}  "
            f"COLLATERAL_FAILURES={score['collateral_failures']}  "
            f"recovery_ok={score['recovery_ok']}")
        say(f"  surfacing: server reported "
            f"{sum(1 for v in score['surfacing']['error_surfaced_by_server'].values() if v)}"
            f"/{score['surfacing']['fault_docs_that_failed']} fault failures; "
            f"client-only inferred "
            f"{sum(1 for v in score['surfacing']['failure_only_inferred_by_client'].values() if v)}")
        for fd, v in score["blast_radius"]["per_fault"].items():
            if isinstance(v, dict) and "error" not in v:
                say(f"  {fd}: outcome={v['fault_outcome']}  collateral(60s)="
                    f"{v['collateral_count']}  time_to_next_success="
                    f"{v['time_to_next_success_s']}s")
        if score["surfacing"]["poison_unexpectedly_succeeded"]:
            say("  !! the poison document SUCCEEDED — the parser accepted 64KB of noise. "
                "That is a finding, not a pass.")
        if not passed:
            all_pass = False
            failures += [f"{arm_name}: {f}" for f in fails]

    out["all_arms_pass"] = all_pass
    return ec.verdict_exit(all_pass, write_result("exp_fault_isolation", out), failures)


if __name__ == "__main__":
    raise SystemExit(main())
