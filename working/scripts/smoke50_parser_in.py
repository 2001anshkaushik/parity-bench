#!/usr/bin/env python3
"""50-document Parser IN smoke test — Leela's gate structure and ours, side by side.

Run:  ../.venv/bin/python working/scripts/smoke50_parser_in.py [N]

Reports TWO verdicts per arm so our output is directly comparable with Leela's:

  LEELA'S GATES
    census      offered = successful + expected + unexpected; N records, unique ids, zero silent
    structure   >=1 chunk (or completed-empty), 384-d, finite, L2 = 1.0 +- 0.001,
                response identity provably matches the submitted document
    determinism chunk-hash lists identical between a BLAST run and a SEQUENTIAL run, per arm
    cross-arm   chunk-count delta and char ratio, REPORTED not gated, + embedding parity fixture

  OURS, ON TOP
    per-arm chunk hash against an INDEPENDENT reference
      - LlamaIndex: the arm's own returned extracted_text
      - RocketRide: standalone Tika (engine's jars + engine's tika-config.xml) + '\\n\\n'
    content sanity (NUL presence, printable ratio)

The two answer different questions. Determinism compares each arm against ITSELF across runs, so a
DETERMINISTIC defect reproduces identically and passes. The independent reference is what catches
that. Both are needed; neither subsumes the other.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

PORT = int(os.environ.get("SMOKE_PORT", "8851"))
L2_TOL = 1e-3                      # team standard; goodput.py now matches (1e-3 everywhere)
EMB_DIM = 384

# Cross-team alignment knobs (2026-08-14). Defaults reproduce the macOS 50-doc smoke exactly, so
# nothing local changes; RUN_ON_EC2.md sets them explicitly for the box. Shashi's harness pins
# RR_THREADS == HS_WORKERS on both arms (SHARED-PIPELINE-NOTES §7) — SMOKE_WORKERS/SMOKE_THREADS
# are how we honour that rule without hardcoding a host's core count into the script.
WORKERS = int(os.environ.get("SMOKE_WORKERS", "1"))     # uvicorn workers on the LlamaIndex arm
THREADS = int(os.environ.get("SMOKE_THREADS", "10"))    # OMP/MKL/BLAS per worker; also RR threads
BLAST_C = int(os.environ.get("SMOKE_BLAST_C", "4"))     # in-flight docs during the determinism leg
# Leela's box selection rule is sorted(*.pdf)[:N] over govdocs1 zip 000 (RUN_LOG_20260814 §3).
# Our corpus/govdocs1/pdfs holds all 40 zips prefixed by archive, so the same rule restricted to
# the 000_ prefix yields the identical document set. Verified: zip 000 contributes exactly 200
# PDFs and its first ten match Leela's box corpus name-for-name.
CORPUS_GLOB = os.environ.get("SMOKE_CORPUS_GLOB", "*.pdf")
# EXTERNAL SERVICE MODE. Set when both arms already run as containers on loopback
# (LI http://127.0.0.1:8801, RR ws://127.0.0.1:5565). The driver then NEVER starts a service:
# starting a second one would silently measure whichever process won the port, which is the
# `start_engine.sh` idempotency trap in a new place. Unreachable => hard fail, never a fallback.
EXTERNAL = os.environ.get("SMOKE_EXTERNAL", "") not in ("", "0", "false", "False")
RR_VERSION_URL = os.environ.get("SMOKE_RR_URL", "http://127.0.0.1:5565") + "/version"
# Preflight: prove thread propagation on both arms, print the manifest block, exit. No documents.
PREFLIGHT = os.environ.get("SMOKE_PREFLIGHT", "") not in ("", "0", "false", "False")
# Warm-up exclusion is METRIC-SIDE by completion rank (Leela's perf_window — settled 2026-08-14).
# Primary 64, secondary 25 also emitted; the numbers are computed from the same rows, so changing
# the pick later needs no re-run.
WARM_N_PRIMARY = int(os.environ.get("SMOKE_WARM_N", "64"))
WARM_N_SECONDARY = 25
# CPU sampling: our psutil ProcessCollector (out-of-process, dead-PID roll-forward), 0.5 s,
# service process tree only, driver excluded — identical setup on both arms (settled 2026-08-14).
SAMPLE_INTERVAL_S = 0.5


def say(m):
    print(m, flush=True)


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def wait_external(port: int, want_workers: int, timeout: float = 900.0) -> list[dict]:
    """Readiness for an already-running LlamaIndex container, on loopback.

    `/health` is answered by ONE worker per connection, so a single 200 proves nothing — this
    polls until `want_workers` DISTINCT worker_pids have each reported model_loaded. That is the
    external-mode equivalent of counting 'warm in' lines, which live inside the container.

    Raises on timeout. It must never fall back to starting a local service: two services on one
    port means the run measures whichever one answered, and nothing in the output would say so.
    """
    import urllib.error
    import urllib.request
    seen: dict[int, dict] = {}
    t0 = time.perf_counter()
    last_err = None
    while time.perf_counter() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as r:
                h = json.loads(r.read().decode())
            if h.get("model_loaded"):
                seen[h["worker_pid"]] = h
            if len(seen) >= want_workers:
                return list(seen.values())
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(0.25)
    raise RuntimeError(
        f"LlamaIndex service NOT READY on 127.0.0.1:{port} after {timeout:.0f}s — saw "
        f"{len(seen)}/{want_workers} distinct warm workers"
        + (f" (last error {last_err})" if last_err else "")
        + ". SMOKE_EXTERNAL is set, so the driver will NOT start one. Start the container "
          "and re-run.")


def check_engine(url: str) -> dict:
    """Prove the RocketRide engine is answering before anything is sent to it.

    /version is unauthenticated and carries the running build, so readiness and identity come
    from one call. NOTE the shape of the check: `curl -w '%{http_code}' || echo 000` yields
    `000000` on a refused connection and compares unequal to `000`, reporting a dead engine as
    healthy — this project has already lost time to that.
    """
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            if r.status != 200:
                raise RuntimeError(f"engine {url} returned HTTP {r.status}")
            return json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(
            f"RocketRide engine NOT REACHABLE at {url} ({type(e).__name__}: {str(e)[:120]}). "
            "SMOKE_EXTERNAL is set, so the driver will NOT start one.") from e


def structure_check(chunks, vecs, dim: int = EMB_DIM) -> list[str]:
    """Leela's structure gate. Returns a list of problems (empty = pass).

    `dim` is PROBED from the arm's own loaded model before the measured run (settled
    2026-08-14, Shashi's rationale bench.py:652-655: if model resolution changes, the gate
    follows it instead of silently checking the wrong width). EMB_DIM is only the fallback
    for callers that predate the probe."""
    bad = []
    if chunks is None or vecs is None:
        return ["chunks or vectors is None"]
    if len(chunks) == 0:
        return ["completed-empty"]            # allowed, but recorded distinctly
    if len(vecs) != len(chunks):
        bad.append(f"{len(chunks)} chunks vs {len(vecs)} vectors")
    for i, v in enumerate(vecs):
        if len(v) != dim:
            bad.append(f"vector {i} dim {len(v)}")
            continue
        n = math.sqrt(sum(float(x) * float(x) for x in v))
        if not math.isfinite(n):
            bad.append(f"vector {i} non-finite")
        elif abs(n - 1.0) > L2_TOL:
            bad.append(f"vector {i} L2={n:.6f}")
    return bad


def main() -> int:
    from harness import ws1_service as ws
    from harness import metrics_shared as ms
    from harness.chunk_hash import check_chunks, ChunkHashMismatch
    from harness.collector_proc import ProcessCollector
    from harness.content_sanity import inspect
    from harness.extraction_fidelity import fidelity, summarise
    from harness.tika_reference import available as tika_ok, reference_text
    from harness.resultio import write_result
    from weekend_worker import LlamaHttpPdfArm, RocketPdfArm, RocketArm

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    pdfs = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob(CORPUS_GLOB))[:N]
    say(f"documents: {len(pdfs)}  (offered = {len(pdfs)})  glob={CORPUS_GLOB}")
    if len(pdfs) < N:
        say(f"!! only {len(pdfs)} PDFs match — asked for {N}. Refusing: a short corpus makes the "
            "census gate compare against the wrong denominator.")
        return 2
    # Cross-site comparability: the pipe bytes and the corpus bytes both have to be provable, or a
    # chunk-hash difference between two sites is unattributable. Shashi asks for the pipe hash
    # explicitly (SHARED-PIPELINE-NOTES, "compare pipe hashes before we compare numbers").
    pipe_path = ROOT / "working" / "pipes" / "product_pdf.pipe"
    pipe_raw = hashlib.sha256(pipe_path.read_bytes()).hexdigest()
    _p = json.loads(pipe_path.read_text())
    _p.pop("project_id", None)
    pipe_canon = h(json.dumps(_p, sort_keys=True, separators=(",", ":")))
    corpus_sha = h("".join(f.name + ":" + hashlib.sha256(f.read_bytes()).hexdigest()
                           for f in pdfs))
    say(f"pipe sha256 raw={pipe_raw[:16]}  canonical(project_id stripped)={pipe_canon[:16]}")
    say(f"corpus sha256 (ordered name:sha list over {len(pdfs)} docs) = {corpus_sha[:16]}")
    ok_tika, why = tika_ok()
    say(f"tika reference: {'available' if ok_tika else 'UNAVAILABLE — ' + why}")

    say(f"service: workers={WORKERS} threads={THREADS} blast_concurrency={BLAST_C} "
        f"mode={'EXTERNAL (containers on loopback)' if EXTERNAL else 'driver-managed'}")
    hsvc = None
    if EXTERNAL:
        # Both arms must already be up. Fail loudly; never start one.
        health = wait_external(PORT, WORKERS)
        thr = sorted({(h["torch_threads"], h["torch_interop"]) for h in health})
        li_thread_env = health[0].get("thread_env", {})
        say(f"llamaindex: {len(health)} distinct warm workers on :{PORT}, "
            f"torch(intra,interop)={thr}")
        ver = check_engine(RR_VERSION_URL)
        say(f"engine: {RR_VERSION_URL} -> {json.dumps(ver.get('data', ver))[:120]}")
    else:
        hsvc = ws.start(workers=WORKERS, port=PORT, threads=THREADS)
        ws.wait_warm(hsvc, timeout=900)
        thr = sorted(set(hsvc.measured_threads.values()))
        li_thread_env = None
        say(f"service warm, torch(intra,interop)={thr}")

    # Per-doc JSONL + sampler streams land here so every metric is re-derivable forever
    # (Leela's exfil contract: raw records, not just the report).
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = ROOT / "working" / "results" / f"smoke_metrics_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    def dump_jsonl(name: str, rows: list[dict]):
        (run_dir / name).write_text(
            "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n")

    def service_root_pid(arm_name: str):
        """The root of the SERVICE tree — the driver is never sampled (settled 2026-08-14)."""
        if arm_name.startswith("llamaindex"):
            parent, _workers = ws.serving_pids(PORT)
            return parent
        return RocketArm._engine_pid()

    class CostSpan:
        """psutil ProcessCollector (0.5 s, out-of-process) around one arm+mode span; yields the
        normalized (ts, cpu_s, rss_mb) series the metrics consume. On the box (Docker) the same
        metrics take series_from_cgroup_jsonl instead — sampler pluggable, math identical."""

        def __init__(self, arm_name: str, mode: str):
            self.tag = f"{'li' if arm_name.startswith('llamaindex') else 'rr'}_{mode}"
            self.path = run_dir / f"sampler_{self.tag}.jsonl"
            pid = service_root_pid(arm_name)
            if pid is None:
                raise RuntimeError(f"BLOCKER: no service root pid for {arm_name} — cannot "
                                   "sample cost. Refusing to emit metrics without it.")
            self.pc = ProcessCollector(self.path, {"service": {"pids": [pid]}},
                                       interval_s=SAMPLE_INTERVAL_S)

        def __enter__(self):
            self.pc.start()
            # Child publishes readiness AFTER its collector started: anchor error is the
            # handshake latency (<0.1 s), far under the 0.5 s edge-attribution bound.
            self.epoch_anchor = time.time()
            return self

        def __exit__(self, *exc):
            self.pc.stop()

        def series(self):
            txt = self.path.read_text() if self.path.exists() else ""
            return ms.series_from_role_ticks(txt, "service", self.epoch_anchor)

    cost_series: dict[str, list] = {}   # f"{arm}:{mode}" -> normalized series
    blast_rows: dict[str, list] = {}    # arm -> per-doc rows from the blast leg
    probed_dim: dict[str, int] = {}     # arm -> dim read off the arm's own loaded model

    def rr_thread_readback() -> dict:
        """torch.get_num_threads()/get_num_interop_threads() read INSIDE the engine's task
        process, via the existing env_probe node on a SEPARATE one-shot pipe.

        The measured pipe stays the shared 5-node file byte-for-byte — adding a probe node to it
        would break cross-team pipe parity. Declared != measured: an OMP_NUM_THREADS exported to
        the engine parent does not prove the task process inherited it, and torch caches its
        thread count at import, so a variable set after import has no effect at all.
        """
        import uuid as _u
        from rocketride import RocketRideClient

        async def go():
            base = json.loads((ROOT / "working" / "pipes" / "a3_env.pipe").read_text())
            base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                              f"envprobe-{os.getpid()}-{time.time()}"))
            pp = ROOT / "working" / "pipes" / "generated" / f"envprobe_{os.getpid()}.pipe"
            pp.parent.mkdir(parents=True, exist_ok=True)
            pp.write_text(json.dumps(base))
            c = RocketRideClient()
            await c.connect(timeout=60000)
            tok = (await c.use(filepath=str(pp.relative_to(ROOT))))["token"]
            try:
                o = await asyncio.wait_for(c.send(tok, "probe", mimetype="text/plain"),
                                           timeout=120)
                # response_text returns the `text` lane, which is a LIST of writes, not a
                # string — the engine's lanes are multi-valued. Guessing str here cost a run.
                txt = o.get("text") or (o.get("documents") or [{}])[0].get("page_content", "")
                if isinstance(txt, (list, tuple)):
                    txt = txt[0] if txt else ""
                return json.loads(txt) if txt else {"error": "env_probe returned nothing"}
            finally:
                try:
                    await asyncio.wait_for(c.terminate(tok), timeout=60)
                except Exception:
                    pass
                await c.disconnect()
        try:
            return asyncio.run(go())
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:160]}"}

    rr_threads = rr_thread_readback()
    say(f"engine task process: torch intra={rr_threads.get('torch_num_threads')} "
        f"interop={rr_threads.get('torch_num_interop_threads')} "
        f"env={rr_threads.get('env')}"
        + (f"  !! {rr_threads['error']}" if rr_threads.get("error") else ""))

    threads_measured = {
        "llamaindex_http_pdf": {
            "source": ("/health from each live uvicorn worker (external mode)" if EXTERNAL
                       else "warm line of each uvicorn worker (driver-managed)"),
            "per_worker_intra_interop": [list(t) for t in thr],
            "thread_env_in_worker": li_thread_env},
        "rocketride_pdf": {
            "source": "env_probe node inside the engine task process, separate one-shot pipe "
                      "(a3_env.pipe); measured pipe untouched",
            **rr_threads},
    }

    if PREFLIGHT:
        # Thread propagation, proven on both arms, BEFORE any document is sent. On the box this
        # is the gate: `docker run -e` reaching the container does not prove it reached the
        # uvicorn worker or the engine's task process, and torch caches its count at import.
        say("\npinned.torch_threads_measured =")
        print(json.dumps(threads_measured, indent=2), flush=True)
        want = THREADS
        li_bad = [t for t in thr if t[0] != want]
        rr_intra = rr_threads.get("torch_num_threads")
        rr_bad = rr_intra != want
        say("")
        say(f"  declared BLAS/intra-op threads per worker : {want}")
        say(f"  llamaindex measured intra                 : {[t[0] for t in thr]}"
            f"   -> {'PASS' if not li_bad else 'FAIL'}")
        say(f"  rocketride measured intra                 : {rr_intra}"
            f"   -> {'PASS' if not rr_bad else 'FAIL'}")
        say(f"  interop (left UNSET on both, reported)    : "
            f"LI {[t[1] for t in thr]}  RR {rr_threads.get('torch_num_interop_threads')}")
        if li_bad or rr_bad:
            say("\nPREFLIGHT FAIL — the thread pin did not reach a worker/task process. "
                "Do NOT run the measured smoke: cost numbers from mismatched arms are "
                "not comparable.")
            if hsvc:
                ws.stop(hsvc)
            return 4
        say("\nPREFLIGHT PASS — both arms at the declared pin. Safe to run the 200-doc smoke.")
        if hsvc:
            ws.stop(hsvc)
        return 0

    results = {}
    try:
        for arm_name, mk in (("llamaindex_http_pdf", lambda: LlamaHttpPdfArm(port=PORT)),
                             ("rocketride_pdf", lambda: RocketPdfArm("smoke"))):
            arm = mk()
            # ---- dim probe: one document through the arm BEFORE the measured span. The gate
            # width comes from the deployed model, not a constant (settled; Shashi bench.py:653).
            p_chunks, p_vecs = arm.process(pdfs[0].read_bytes())
            if not p_vecs or not p_vecs[0]:
                say(f"BLOCKER: dim probe on {arm_name} returned no vectors "
                    f"({pdfs[0].name}) — cannot set the structure gate width. Aborting.")
                return 3
            probed_dim[arm_name] = len(p_vecs[0])
            say(f"  {arm_name}: probed dim={probed_dim[arm_name]} "
                f"(from {pdfs[0].name}, excluded from the measured span)")
            recs = []
            chunk_texts: dict[str, list] = {}   # doc -> chunks, for post-loop gates
            li_src: dict[str, str] = {}         # doc -> service-returned extracted text (LI)
            span = CostSpan(arm_name, "sequential")
            with span:
                for f in pdfs:
                    blob = f.read_bytes()
                    rec = {"doc": f.name, "submitted_sha256": hashlib.sha256(blob).hexdigest()}
                    rec["submit_ns"] = time.time_ns()
                    t0 = time.perf_counter()
                    try:
                        chunks, vecs = arm.process(blob)
                        rec["completion_ns"] = time.time_ns()
                        rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                        last = getattr(arm, "last", {}) or {}
                        rec["returned_doc_id"] = last.get("doc_id")
                        rec["n_chunks"] = len(chunks)
                        rec["chunk_sha256"] = [h(c) for c in chunks]
                        rec["chars"] = sum(len(c) for c in chunks)
                        problems = structure_check(chunks, vecs, probed_dim[arm_name])
                        rec["structure"] = problems
                        if problems == ["completed-empty"]:
                            rec["outcome"] = "expected"
                            rec["error_class"] = "completed_empty"
                        elif problems:
                            rec["outcome"] = "unexpected"
                            rec["error_class"] = "structure"
                        elif not last.get("ok", True):
                            rec["outcome"] = "expected"
                            rec["error_class"] = last.get("error_class", "unknown")
                        else:
                            rec["outcome"] = "successful"
                        # OUR gates (independent reference, content sanity) run POST-LOOP:
                        # the RR reference is a standalone Tika JVM per doc, and inside the
                        # loop it lands in the completion-to-completion span — measured this
                        # run as RR seq 0.25 docs/s, an instrument artifact biased AGAINST
                        # RocketRide. Teammates compute all gates post-hoc from records.
                        if rec["outcome"] == "successful":
                            chunk_texts[f.name] = chunks
                            if arm_name.startswith("llamaindex"):
                                li_src[f.name] = last.get("extracted_text")
                    except Exception as e:
                        rec["completion_ns"] = time.time_ns()
                        rec["outcome"] = "unexpected"
                        rec["error_class"] = f"{type(e).__name__}"
                        rec["error"] = str(e)[:200]
                    rec["ok"] = rec.get("outcome") == "successful"
                    recs.append(rec)
            cost_series[f"{arm_name}:sequential"] = span.series()
            arm.close()
            # ---- OUR gates, post-loop, outside the sampled/timed span ----
            for rec in recs:
                chunks = chunk_texts.get(rec["doc"])
                if chunks is None:
                    continue
                src = (li_src.get(rec["doc"]) if arm_name.startswith("llamaindex")
                       else (reference_text(ROOT / "corpus" / "govdocs1" / "pdfs" / rec["doc"])
                             if ok_tika else None))
                if src:
                    try:
                        check_chunks(rec["doc"], chunks, src)
                        rec["independent_hash"] = "pass"
                    except ChunkHashMismatch as e:
                        rec["independent_hash"] = f"FAIL: {e}"
                    rec["extracted_chars"] = len(src)
                sus = [i for i, c in enumerate(chunks) if inspect(c)["suspect"]]
                if sus:
                    rec["content_suspect_chunks"] = sus
            chunk_texts.clear()
            li_src.clear()
            results[arm_name] = recs
            dump_jsonl(f"perdoc_{'li' if arm_name.startswith('llamaindex') else 'rr'}_sequential.jsonl", recs)
            say(f"  {arm_name}: {len(recs)} records")

        # ---- determinism: a BLAST run (concurrent) vs the SEQUENTIAL run above
        say("\ndeterminism: blast run vs sequential run, per arm")
        blobs = [(f.name, f.read_bytes()) for f in pdfs]

        # LlamaIndex: blocking urllib, so threads are the right concurrency primitive.
        # Returns (hashes-by-doc, per-doc rows) — the rows feed metrics_shared; blast latency is
        # batch-position latency under a client cap of BLAST_C, labeled open-loop-blast.
        def blast_llama():
            import concurrent.futures as cf
            arm = LlamaHttpPdfArm(port=PORT)

            def one(item):
                name, b = item
                row = {"doc": name, "submit_ns": time.time_ns()}
                try:
                    ch, _ = arm.process(b)
                    row.update(completion_ns=time.time_ns(), ok=True,
                               n_chunks=len(ch), chunk_sha256=[h(c) for c in ch])
                except Exception as e:
                    row.update(completion_ns=time.time_ns(), ok=False,
                               error_class=type(e).__name__)
                return row
            with cf.ThreadPoolExecutor(max_workers=BLAST_C) as ex:
                rows = list(ex.map(one, blobs))
            arm.close()
            return {r["doc"]: r.get("chunk_sha256") for r in rows}, rows

        # RocketRide: ONE asyncio loop, C concurrent send() coroutines. Driving RocketPdfArm.process
        # from a ThreadPoolExecutor calls run_until_complete on one loop from several threads, which
        # silently abandons coroutines ("coroutine 'send' was never awaited") and reports spurious
        # non-determinism. Measured: that harness bug alone produced 7/8 false "drift".
        def blast_rocket():
            import uuid as _u
            from rocketride import RocketRideClient

            async def go():
                base = json.loads((ROOT / "working" / "pipes" / "product_pdf.pipe").read_text())
                base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                                  f"blast-{os.getpid()}-{time.time()}"))
                pp = ROOT / "working" / "pipes" / "generated" / f"blast_{os.getpid()}.pipe"
                pp.parent.mkdir(parents=True, exist_ok=True)
                pp.write_text(json.dumps(base))
                c = RocketRideClient()
                await c.connect(timeout=60000)
                tok = (await c.use(filepath=str(pp.relative_to(ROOT))))["token"]
                sem = asyncio.Semaphore(BLAST_C)
                rows = []

                async def one(name, b):
                    row = {"doc": name, "submit_ns": time.time_ns()}
                    async with sem:
                        try:
                            o = await asyncio.wait_for(
                                c.send(tok, b, mimetype="application/pdf"), timeout=300)
                            hs = [h(d.get("page_content", ""))
                                  for d in (o.get("documents") or [])]
                            row.update(completion_ns=time.time_ns(), ok=True,
                                       n_chunks=len(hs), chunk_sha256=hs)
                        except Exception as e:
                            row.update(completion_ns=time.time_ns(), ok=False,
                                       error_class=type(e).__name__)
                    rows.append(row)
                try:
                    await asyncio.gather(*(one(n_, b) for n_, b in blobs))
                finally:
                    try:
                        await asyncio.wait_for(c.terminate(tok), timeout=60)
                    except Exception:
                        pass
                    await c.disconnect()
                return {r["doc"]: r.get("chunk_sha256") for r in rows}, rows
            return asyncio.run(go())

        for arm_name, runner in (("llamaindex_http_pdf", blast_llama),
                                 ("rocketride_pdf", blast_rocket)):
            span = CostSpan(arm_name, "blast")
            with span:
                blast, brows = runner()
            cost_series[f"{arm_name}:blast"] = span.series()
            blast_rows[arm_name] = brows
            dump_jsonl(f"perdoc_{'li' if arm_name.startswith('llamaindex') else 'rr'}_blast.jsonl",
                       brows)
            # Unproven ≠ drift (both teammates' semantics: Leela m0_correctness.py:144-158
            # counts a None side as failure; Shashi correctness.py:440-469 names it
            # `unproven` separately). A blast-leg timeout must not read as hash instability.
            same = unproven = 0
            for r in results[arm_name]:
                b = blast.get(r["doc"])
                if b is None:
                    r["deterministic"] = None       # unproven — no blast observation
                    unproven += 1
                elif b == r.get("chunk_sha256"):
                    r["deterministic"] = True
                    same += 1
                else:
                    r["deterministic"] = False
            say(f"  {arm_name}: {same}/{len(results[arm_name])} identical between blast and "
                f"sequential" + (f", {unproven} UNPROVEN (blast leg gave no result)"
                                 if unproven else ""))
    finally:
        # Never tear down a service this driver did not start — in external mode the container
        # is the operator's, and the second arm may still be mid-run against it.
        if hsvc:
            ws.stop(hsvc)

    # ---------------- verdicts ----------------
    out = {"n_offered": len(pdfs), "threads": thr, "arms": {},
           # Provenance block — the fields the three harnesses have to agree on before any
           # cross-site number is comparable. Same keys Shashi exports under `pipeline`/`pinned`.
           "pipeline": {"file": pipe_path.name,
                        "nodes": [c["provider"] for c in _p["components"]],
                        "sha256_raw": pipe_raw, "sha256_canonical": pipe_canon},
           "corpus": {"source": "govdocs1", "glob": CORPUS_GLOB, "rule": "sorted(*.pdf)[:N]",
                      "n": len(pdfs), "sha256": corpus_sha,
                      "first": pdfs[0].name, "last": pdfs[-1].name},
           "pinned": {"workers": WORKERS, "threads": THREADS, "blast_concurrency": BLAST_C,
                      "send_modes": ["sequential", "blast"],
                      "warm_n": {"primary": WARM_N_PRIMARY, "secondary": WARM_N_SECONDARY,
                                 "placement": "metric-side, by completion rank "
                                              "(perf_window; settled 2026-08-14)"},
                      "embedding_dim": {"source": "probed from each arm's loaded model, "
                                                  "one doc pre-span", "per_arm": probed_dim},
                      # DECLARED != MEASURED, both arms, read back in-process.
                      "torch_threads_measured": threads_measured,
                      "service_mode": "external containers" if EXTERNAL else "driver-managed",
                      "cost_sampler": {"source": "psutil ProcessCollector (out-of-process, "
                                                 "dead-PID roll-forward)",
                                       "interval_s": SAMPLE_INTERVAL_S,
                                       "scope": "service process tree only, driver excluded",
                                       "pluggable": "box/Docker mode consumes Leela's "
                                                    "cgroup_sampler JSONL via "
                                                    "metrics_shared.series_from_cgroup_jsonl"},
                      "available_cpus": os.cpu_count(),
                      "raw_records_dir": str(run_dir)}}
    say("\n" + "=" * 96)
    for arm_name, recs in results.items():
        c = {"successful": 0, "expected": 0, "unexpected": 0}
        for r in recs:
            c[r.get("outcome", "unexpected")] = c.get(r.get("outcome", "unexpected"), 0) + 1
        ids = [r["doc"] for r in recs]
        census_ok = (sum(c.values()) == len(pdfs) and len(set(ids)) == len(ids)
                     and len(recs) == len(pdfs))
        struct_fail = [r for r in recs if r.get("structure") and r["structure"] != ["completed-empty"]]
        det_fail = [r for r in recs if r.get("deterministic") is False]
        det_unproven = [r for r in recs if r.get("deterministic") is None]
        ind_fail = [r for r in recs if str(r.get("independent_hash", "")).startswith("FAIL")]
        sus = [r for r in recs if r.get("content_suspect_chunks")]
        say(f"{arm_name}")
        say(f"  LEELA  census      offered {len(pdfs)} = successful {c['successful']} + "
            f"expected {c['expected']} + unexpected {c['unexpected']}   -> {'PASS' if census_ok else 'FAIL'}")
        say(f"  LEELA  structure   {len(struct_fail)} failure(s)                      -> "
            f"{'PASS' if not struct_fail else 'FAIL'}")
        say(f"  LEELA  determinism {len(det_fail)} drifted, {len(det_unproven)} unproven"
            f"            -> {'PASS' if not det_fail and not det_unproven else 'FAIL'}")
        say(f"  OURS   independent-reference hash: {len(ind_fail)} FAIL")
        say(f"  OURS   content-suspect documents : {len(sus)}")
        out["arms"][arm_name] = {"census": c, "census_ok": census_ok,
                                 "structure_failures": len(struct_fail),
                                 "determinism_failures": len(det_fail),
                                 "determinism_unproven": len(det_unproven),
                                 "independent_hash_failures": len(ind_fail),
                                 "content_suspect": len(sus), "records": recs}

    # ---------------- cross-arm, reported not gated ----------------
    li = {r["doc"]: r for r in results["llamaindex_http_pdf"]}
    rr = {r["doc"]: r for r in results["rocketride_pdf"]}
    rows = []
    for d in li:
        a, b = li[d], rr.get(d)
        if not b or a.get("n_chunks") is None or b.get("n_chunks") is None:
            continue
        rows.append({"doc": d, "chunk_delta": b["n_chunks"] - a["n_chunks"],
                     "char_ratio": round(b["chars"] / a["chars"], 4) if a.get("chars") else None})
    say("\nCROSS-ARM (reported, NOT gated)")
    deltas = [r["chunk_delta"] for r in rows]
    ratios = [r["char_ratio"] for r in rows if r["char_ratio"]]
    if deltas:
        import statistics as st
        say(f"  chunk-count delta (RR - LI): median {st.median(deltas):+.1f}  "
            f"min {min(deltas):+d}  max {max(deltas):+d}  identical on {deltas.count(0)}/{len(deltas)}")
        say(f"  char ratio (RR / LI)       : median {st.median(ratios):.4f}  "
            f"min {min(ratios):.4f}  max {max(ratios):.4f}")
    out["cross_arm"] = rows

    # ---------------- metrics (metrics_shared — the arm-agnostic module) ----------------
    # Same functions, same rows contract, both arms, both modes, both warm_n values.
    # macOS numbers: wiring validation only — every performance figure from this laptop is
    # superseded by policy (STATE.md §0a) and must be re-measured on the box.
    say("\nMETRICS (metrics_shared; macOS = wiring validation, numbers NOT publishable)")
    cpus = os.cpu_count()
    out["metrics"] = {"module": "working/harness/metrics_shared.py",
                      "not_publishable_reason": "macOS/arm64 laptop — superseded by policy",
                      "arms": {}}
    for arm_name in results:
        marm = out["metrics"]["arms"].setdefault(arm_name, {})
        for mode, mrows in (("sequential", results[arm_name]),
                            ("blast", blast_rows.get(arm_name, []))):
            series = cost_series.get(f"{arm_name}:{mode}")
            label = "closed-loop" if mode == "sequential" else "open-loop-blast"
            for wn in (WARM_N_PRIMARY, WARM_N_SECONDARY):
                d = ms.derive_side(mrows, series, warm_n=wn, available_cpus=cpus, mode=label)
                marm[f"{mode}_warm{wn}"] = d
                if "error" in d:
                    say(f"  {arm_name:22} {mode:10} warm_n={wn:<3} -> {d['error']}")
                    continue
                lat = d.get("latency") or {}
                say(f"  {arm_name:22} {mode:10} warm_n={wn:<3} "
                    f"docs/s={d['docs_per_s']}  chunks/s={d['chunks_per_s']}  "
                    f"p50={lat.get('p50')}s p95={lat.get('p95')}s [{lat.get('mode', '?')}]  "
                    f"cpu_s={d['cpu_s']}  cpu_s/doc={d['cpu_s_per_doc']}  "
                    f"cores={d['effective_cores']}  util={d['cpu_utilization']}"
                    f"{'' if d.get('cpu_utilization_valid') in (True, None) else ' INVALID'}  "
                    f"peakRSS={d['peak_rss_mb']}MB")

    p = write_result("smoke50_parser_in", out)
    say(f"\nwritten -> {p}")
    say(f"raw per-doc JSONL + sampler streams -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
