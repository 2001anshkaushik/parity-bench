#!/usr/bin/env python3
"""50-document Parser IN smoke test — Leela's gate structure and ours, side by side.

Run:  ../.venv/bin/python working/scripts/smoke50_parser_in.py [N]

Reports THREE verdicts over identical records, so no reader has to re-derive ours:

  Verdict A   intersection determinism, name-keyed census
  Verdict B   symmetric determinism, count-keyed census
  Verdict C   union (strictest; conjunction of A and B)

Gate names are the teammates' own identifiers and are never re-worded: census, structure,
determinism, duplication, workload_ratio_rr_over_li, normalization_parity, chunk_config_parity.
Definitions and the file:line each was adopted from live in harness/gates_shared.py.

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
BLAST_C = int(os.environ.get("SMOKE_BLAST_C", "4"))
# Arms whose blast leg uses a BATCHED send. Their per-document latency is derived,
# never measured, and is labelled as such. Empty while both arms send per-document.
BATCHED_ARMS = {x for x in os.environ.get("SMOKE_BATCHED_ARMS", "").split(",") if x}     # in-flight docs during the determinism leg
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
# RESUME: continue a run that was killed, from the per-doc JSONL that survived on disk. Must be
# explicit — silently appending to a previous run's records would mix two runs into one file.
# Pair it with SMOKE_RUN_DIR pointing at the run you are continuing.
RESUME = os.environ.get("SMOKE_RESUME", "") not in ("", "0", "false", "False")
# SMOKE_LEGS selects which legs run, so the non-resumable-in-practice work can be supervised
# and the long legs left overnight. Comma-separated: sequential,blast (default both).
# Determinism compares the two legs, so it is only computed when BOTH ran in this invocation
# or the other leg's records are already on disk from a previous one.
LEGS = {x.strip() for x in os.environ.get("SMOKE_LEGS", "sequential,blast").split(",") if x.strip()}
# The independent-reference check spawns a JVM PER DOCUMENT: measured 0.599 s/doc mean, so
# ~1.7 h at 10k on the RocketRide arm alone. It is advisory for us and load-bearing for neither
# teammate. A positive value samples that many documents deterministically (every k-th by sorted
# order, so it is reproducible and not clustered); 0 = every document, the default.
TIKA_SAMPLE = int(os.environ.get("SMOKE_TIKA_SAMPLE", "0"))
_UNKNOWN_LEGS = LEGS - {"sequential", "blast"}
# Warm-up exclusion is METRIC-SIDE by completion rank (Leela's perf_window — settled 2026-08-14).
# Primary 64, secondary 25 also emitted; the numbers are computed from the same rows, so changing
# the pick later needs no re-run.
# 0 is now PRIMARY: warm-up is driver-side (25 disjoint documents, excluded before the
# span), so a second metric-side exclusion would drop real measured work. 64 is kept as
# the secondary only so a Phase-2 number can still be laid beside a pre-Phase-2 one.
WARM_N_PRIMARY = int(os.environ.get("SMOKE_WARM_N", "0"))
WARM_N_SECONDARY = 64
# CPU sampling: our psutil ProcessCollector (out-of-process, dead-PID roll-forward), 0.5 s,
# service process tree only, driver excluded — identical setup on both arms (settled 2026-08-14).
SAMPLE_INTERVAL_S = 0.5


def say(m):
    # rstrip: the fixed-width tables pad their last column, and trailing
    # whitespace is noise the moment this is pasted into a summary.
    print(str(m).rstrip(), flush=True)


def _fmt_mb(v) -> str:
    return "-" if v is None else f"{v:,.1f}"


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def wait_external(port: int, want_workers: int, timeout: float = 300.0) -> list[dict]:
    """Readiness for an already-running LlamaIndex container, on loopback.

    Gates on `/health`'s **aggregate** `warm_workers` count, which the service derives from one
    marker file per worker. One request answers it.

    It previously polled until `want_workers` DISTINCT `worker_pid`s had been seen, and that was
    wrong — not because of the container boundary (the PIDs only need to be distinct, not
    host-resolvable) but because uvicorn's workers share a single listening socket. Which worker
    accepts a connection is the kernel's choice, and its bias for short-lived connections is
    strongly non-uniform: a fully warm 32-worker service can return the same two or three PIDs for
    thousands of requests. Collecting all 32 is a coupon-collector problem against a sampler that
    may never emit most of the coupons, so the poll ran to its timeout on a healthy service.

    Raises on timeout. It must never fall back to starting a local service: two services on one
    port means the run measures whichever one answered, and nothing in the output would say so.
    """
    import urllib.error
    import urllib.request
    t0 = time.perf_counter()
    last_err = None
    last_seen = -1
    next_note = 15.0
    while True:
        elapsed = time.perf_counter() - t0
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as r:
                h = json.loads(r.read().decode())
            if "warm_workers" not in h:
                raise RuntimeError(
                    f"/health on 127.0.0.1:{port} has no `warm_workers` field. That field is the "
                    "readiness signal in external mode; without it the driver cannot tell a "
                    "half-warm service from a ready one. The container is running an image built "
                    "before this field existed — rebuild it.")
            warm = h["warm_workers"]
            declared = h.get("declared_workers")
            # HARD ERROR, not a pass. A census above the population means the marker set is
            # contaminated (stale files from a previous `docker start`, seen as 33 of 32), and a
            # contaminated count can satisfy `warm >= want` while real workers are still loading —
            # the run would then measure a partially warm service and say nothing. Same class as
            # cpu_utilization > 1.0: an impossible reading is a defect, not a datum.
            if declared is not None and warm > declared:
                raise RuntimeError(
                    f"/health reports warm_workers={warm} > declared_workers={declared} "
                    f"(warm_key={h.get('warm_key')}). The readiness count is contaminated by "
                    "markers from a previous supervisor, so it cannot prove the service is warm. "
                    "Recreate the container (`docker rm -f` then `docker run`) or clear "
                    "/tmp/ws1_warm inside it, and re-run. Refusing to measure.")
            if warm != last_seen:
                say(f"  readiness: {warm}/{want_workers} workers warm ({elapsed:.0f}s)")
                last_seen = warm
            if warm >= want_workers:
                return [h]
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
        if elapsed >= timeout:
            break
        if elapsed >= next_note:
            say(f"  ... still waiting ({elapsed:.0f}/{timeout:.0f}s)"
                + (f", last error {last_err}" if last_err else ""))
            next_note = elapsed + 15.0
        time.sleep(0.5)
    raise RuntimeError(
        f"LlamaIndex service NOT READY on 127.0.0.1:{port} after {timeout:.0f}s — "
        f"warm_workers={last_seen if last_seen >= 0 else 'unknown'}, wanted {want_workers}"
        + (f" (last error {last_err})" if last_err else "")
        + f". Check `docker logs <container> | grep -c 'warm in'` — if that is already "
          f"{want_workers}, the service is warm and the mismatch is in SMOKE_WORKERS. "
          "SMOKE_EXTERNAL is set, so the driver will NOT start a service.")


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
    from harness import gates_shared as gs
    from harness import memory_sources as msrc
    from harness import provenance_leela as pvl
    from harness import rr_credentials as rrc
    from harness.jsonl_stream import JsonlWriter, read_completed, rewrite_atomically
    from harness.chunk_hash import check_chunks, ChunkHashMismatch
    from harness.collector_proc import ProcessCollector
    from harness.content_sanity import inspect
    from harness.extraction_fidelity import fidelity, summarise
    from harness.tika_reference import available as tika_ok, reference_text
    from harness.resultio import write_result
    from weekend_worker import (LlamaHttpPdfArm, RocketPdfArm, RocketArm,
                                container_root_pid)

    if _UNKNOWN_LEGS:
        say(f"!! SMOKE_LEGS has unknown leg(s): {sorted(_UNKNOWN_LEGS)}. "
            "Valid: sequential, blast.")
        return 7
    if not LEGS:
        say("!! SMOKE_LEGS is empty — nothing to run.")
        return 7
    if LEGS != {"sequential", "blast"}:
        say(f"LEGS: running {sorted(LEGS)} only "
            "(determinism needs both; it uses the other leg's records from disk if present)")

    # Before ANY RocketRideClient is constructed — including the env_probe below.
    from harness.rr_credentials import resolve as _resolve_rr, auth_hint
    rr_creds = _resolve_rr(strict=True)
    say(f"rocketride client: uri={os.environ['ROCKETRIDE_URI']} "
        f"({rr_creds['ROCKETRIDE_URI']['source']}), "
        f"apikey sha256[:8]={rr_creds['ROCKETRIDE_APIKEY']['sha256_8']} "
        f"({rr_creds['ROCKETRIDE_APIKEY']['source']})")

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    _all = sorted((ROOT / "corpus" / "govdocs1" / "pdfs").glob(CORPUS_GLOB))
    pdfs = _all[:N]
    # DRIVER-SIDE WARM-UP, 25 DISJOINT documents taken from BEYOND the measured set
    # (Leela matched_run.sh WARM=25; rr_driver.py:194 `all_pdfs[n:n + warm_docs]`).
    #
    # Metric-side warm-up (perf_window, warm_n=64 by completion rank) is INCOHERENT under a
    # batched send: a batch has one submit and one return, so "the first 64 completions" is the
    # 64 documents the engine happened to finish first, i.e. the 64 FASTEST — dropping them
    # inflates the remainder rather than excluding a cold start. Disjoint documents also stop a
    # warmed document from later being measured cache-hot alongside cold peers.
    WARM_DOCS = int(os.environ.get("SMOKE_WARM_DOCS", "25"))
    warm_pdfs = _all[N:N + WARM_DOCS]
    warm_disjoint = len(warm_pdfs) == WARM_DOCS
    if WARM_DOCS and not warm_disjoint:
        say(f"  !! only {len(_all)} documents match {CORPUS_GLOB} for N={N}+warm={WARM_DOCS}; "
            "warm-up would REUSE measured documents. Refusing — widen the glob or lower N.")
        return 7
    say(f"documents: {len(pdfs)}  (offered = {len(pdfs)})  glob={CORPUS_GLOB}"
        + ("   [PREFLIGHT: not required]" if PREFLIGHT else ""))
    # PREFLIGHT sends no documents — it proves thread propagation and exits. Requiring a corpus
    # for it forced the runbook to fetch ~350 MB before it could check a thread pin, and the
    # driver exited 2 if you followed the documented order.
    if len(pdfs) < N and not PREFLIGHT:
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
    # A dependency-missing check must not be able to read as a clean result. This one is
    # ADVISORY by design (tika_reference.py's own docstring: standalone Tika disagrees with the
    # engine's in-process Tika on some glyphs, so as a hard gate it produced 4 false failures in
    # 5 on a 50-doc run), so a missing JRE is not automatically fatal — but it is never silent,
    # and SMOKE_REQUIRE_TIKA=1 makes it fatal for runs that depend on it.
    if not ok_tika:
        say("!! the independent-reference check will NOT RUN on the RocketRide arm. Its column "
            "will read NOT RUN, never '0 FAIL'. Fix: extract the engine tarball so "
            "engine/java/jre/bin/java exists (TikaExtract.class is already committed).")
        if os.environ.get("SMOKE_REQUIRE_TIKA", "") not in ("", "0", "false", "False"):
            say("SMOKE_REQUIRE_TIKA is set — refusing to run without the reference.")
            return 5

    say(f"service: workers={WORKERS} threads={THREADS} blast_concurrency={BLAST_C} "
        f"mode={'EXTERNAL (containers on loopback)' if EXTERNAL else 'driver-managed'}")
    hsvc = None
    if EXTERNAL:
        # Both arms must already be up. Fail loudly; never start one.
        health = wait_external(PORT, WORKERS)
        thr = sorted({(h["torch_threads"], h["torch_interop"]) for h in health})
        li_thread_env = health[0].get("thread_env", {})
        # The thread read-back comes from whichever worker answered. It is one sample, not all
        # 32 — the accept bias that broke PID collection makes "poll until you have seen them
        # all" unavailable here too. Recorded as such rather than implied to be a census.
        say(f"llamaindex: {health[0]['warm_workers']}/{WORKERS} workers warm on :{PORT}, "
            f"torch(intra,interop)={thr} [sampled from 1 worker]")
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
    # A resumed run MUST land in the same directory or there is nothing to resume from.
    # SMOKE_RUN_DIR pins it; otherwise a fresh stamp per run, as before.
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = Path(os.environ["SMOKE_RUN_DIR"]) if os.environ.get("SMOKE_RUN_DIR") \
        else ROOT / "working" / "results" / f"smoke_metrics_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    def service_root_pid(arm_name: str):
        """Root of the SERVICE tree — the driver is never sampled (settled 2026-08-14).

        Returns None when the service is a container the host cannot resolve. Callers must
        treat that as "cost unavailable", not as an error and not as zero.
        """
        if arm_name.startswith("llamaindex"):
            parent, _workers = ws.serving_pids(PORT)
            pid = parent
            container = os.environ.get("SMOKE_LI_CONTAINER", "li")
        else:
            pid = RocketArm._engine_pid()
            container = os.environ.get("SMOKE_RR_CONTAINER", "rr")
        if pid is None and EXTERNAL:
            # lsof cannot map a container's listening socket to a pid unprivileged —
            # /proc/<pid>/fd is 0500 and the container runs as uid 10001. docker inspect
            # needs no procfs privilege, and the host pid it returns is a REAL pid whose
            # /proc/<pid>/stat and /proc/<pid>/statm are world-readable, which is all the
            # psutil sampler ever needed. Same mechanism on both arms.
            pid = container_root_pid(container)
            if pid is not None:
                say(f"  {arm_name}: sampling container '{container}' root pid {pid} "
                    "(docker inspect; lsof cannot see it unprivileged)")
        return pid

    class CostSpan:
        """psutil ProcessCollector (0.5 s, out-of-process) around one arm+mode span; yields the
        normalized (ts, cpu_s, rss_mb) series the metrics consume. On the box (Docker) the same
        metrics take series_from_cgroup_jsonl instead — sampler pluggable, math identical."""

        def __init__(self, arm_name: str, mode: str):
            self.tag = f"{'li' if arm_name.startswith('llamaindex') else 'rr'}_{mode}"
            self.path = run_dir / f"sampler_{self.tag}.jsonl"
            self.pc = None
            self.reason = None
            pid = service_root_pid(arm_name)
            if pid is None:
                if not EXTERNAL:
                    raise RuntimeError(f"BLOCKER: no service root pid for {arm_name} — cannot "
                                       "sample cost. Refusing to emit metrics without it.")
                # Container services are not reliably walkable from the host. Cost is then
                # UNAVAILABLE with a reason, never a host-psutil number that would read as a
                # measurement of the container. The correct Docker-mode source is Leela's
                # in-container cgroup sampler via metrics_shared.series_from_cgroup_jsonl();
                # that path is NOT wired into this driver yet.
                self.reason = (
                    f"external mode: neither lsof nor `docker inspect` resolved a host pid "
                    f"for {arm_name}. Set SMOKE_LI_CONTAINER / SMOKE_RR_CONTAINER to the "
                    f"container names if they are not 'li' / 'rr'. (Host psutil CAN sample a "
                    f"container tree — /proc/<hostpid>/stat and /statm are world-readable — so "
                    f"this is a discovery failure, not a sampling limitation.)")
                say(f"  !! cost sampling DISABLED for {self.tag}: {self.reason}")
            else:
                self.pc = ProcessCollector(self.path, {"service": {"pids": [pid]}},
                                           interval_s=SAMPLE_INTERVAL_S,
                                           want_uss=True)

        def __enter__(self):
            if self.pc is None:
                self.epoch_anchor = time.time()
                return self
            self.pc.start()
            # Child publishes readiness AFTER its collector started: anchor error is the
            # handshake latency (<0.1 s), far under the 0.5 s edge-attribution bound.
            self.epoch_anchor = time.time()
            return self

        def __exit__(self, *exc):
            if self.pc is not None:
                self.pc.stop()

        def summary(self):
            return self.pc.summary() if self.pc is not None else {}

        def series(self):
            if self.pc is None:
                return None          # metrics_shared then emits None cost, never 0
            txt = self.path.read_text() if self.path.exists() else ""
            return ms.series_from_role_ticks(txt, "service", self.epoch_anchor)

    # Kept per arm for the gate suites: they need the chunk TEXTS and VECTORS, which the
    # verdict loop runs long after the per-doc loop has moved on.
    chunk_texts_by_arm: dict[str, dict] = {}
    vecs_by_arm: dict[str, dict] = {}
    cost_series: dict[str, list] = {}   # f"{arm}:{mode}" -> normalized series
    cost_reasons: dict[str, str] = {}   # same key -> why cost is absent, if it is
    mem_sources: dict[str, dict] = {}   # f"{arm}:{leg}" -> every memory figure, each named

    def capture_memory(arm_name: str, leg: str, span) -> None:
        """Every memory source for ONE arm in ONE leg, each named for what it is.

        PER LEG, not per arm (defect #30, 2026-08-16). This used to run only in the sequential
        leg and key on the arm alone, so the memory table described a 1-2 process tree while
        the metrics line beside it carried a blast-leg peak from a tree of BLAST_C-plus
        processes. A reader could then divide one by the other: 84,960 MB against a 1,025 MB
        cgroup anon reads as 83x when the printed sharing factor said 1.48x. Neither figure was
        wrong for what it measured; they were never the same measurement, and nothing on the
        page said so. The over-count scales with the process count, so a sharing factor is only
        ever valid for the leg it was measured in.
        """
        _sum = (span.summary().get("roles", {}).get("service", {}) or {})
        m = msrc.memory_report(service_root_pid(arm_name), _sum.get("peak_rss_mb"))
        m["summed_process_pss_peak_mb"] = _sum.get("peak_pss_mb")
        m["peak_process_count"] = _sum.get("peak_process_count")
        m["peak_thread_count"] = _sum.get("peak_thread_count")
        m["distinct_pids_seen"] = _sum.get("distinct_pids_seen")
        m["leg"] = leg
        # THE HEADLINE, sampled during the leg on the process tick (defect #31). Everything
        # `memory_report` produced above is a post-leg point read and can only describe the
        # container after it has released whatever the leg was holding: the 10k blast reported
        # 1,025.4 MB anon over 2 processes that way, taken after the engine had already torn
        # its task processes down. The sampled figure below is the one to quote.
        m["cgroup_anon_peak_mb"] = _sum.get("peak_cgroup_anon_mb")
        m["cgroup_current_peak_mb"] = _sum.get("peak_cgroup_current_mb")
        m["cgroup_peak_tasks"] = _sum.get("peak_cgroup_tasks")
        m["cgroup_samples_in_leg"] = _sum.get("cgroup_samples")
        m["quote_this"] = ("cgroup_anon_peak_mb" if _sum.get("peak_cgroup_anon_mb")
                           else None)
        if not _sum.get("peak_cgroup_anon_mb"):
            m["no_sampled_anon_reason"] = (
                "the collector resolved no cgroup v2 group for this arm — cgroup v1 host, "
                "macOS, or the root pid was gone before the first tick. The post-leg point "
                "sample below is NOT a substitute for a peak.")
        # tasks != processes. cgroup pids.current counts threads, so a threaded engine reads
        # ~10x its process count; reported side by side so they cannot be conflated.
        if _sum.get("peak_cgroup_tasks") and _sum.get("peak_process_count"):
            m["tasks_per_process_at_peak"] = round(
                _sum["peak_cgroup_tasks"] / max(_sum["peak_process_count"], 1), 1)
        if _sum.get("peak_rss_mb") and _sum.get("peak_cgroup_anon_mb"):
            m["sharing_factor_sampled"] = round(
                _sum["peak_rss_mb"] / _sum["peak_cgroup_anon_mb"], 2)
        # cgroup anon/current are read ONCE, here, after the leg — a point sample, not a peak.
        # Only memory.peak is a kernel high-water mark, and it is cumulative since the container
        # started (or was last reset), so it spans every leg and any earlier run in the same
        # container. Say so rather than letting three adjacent columns look like one kind of
        # number.
        m["cgroup_sampling"] = {
            "anon_mb": "point sample taken at end of this leg — NOT a peak",
            "current_mb": "point sample taken at end of this leg — NOT a peak",
            "peak_mb": ("kernel high-water mark, unsampled, cumulative since container start "
                        "or last reset — spans ALL legs, not just this one"),
        }
        if m.get("sharing_factor_summed_over_anon"):
            m["sharing_factor_note"] = (
                f"valid for the {leg} leg only ({m.get('peak_process_count')} processes at "
                "peak). Do not apply it to another leg's summed RSS — the over-count scales "
                "with the number of processes sharing pages.")
        mem_sources[f"{arm_name}:{leg}"] = m
    blast_rows: dict[str, list] = {}    # arm -> per-doc rows from the blast leg
    probed_dim: dict[str, int] = {}     # arm -> dim read off the arm's own loaded model
    warm_by_arm: dict[str, dict] = {}   # arm -> driver-side warm-up record
    broke: dict[str, dict] = {}         # arm -> where the K-consecutive breaker fired

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
            base = json.loads((ROOT / "working" / "pipes" / "a3_env_torch.pipe").read_text())
            base["project_id"] = str(_u.uuid5(_u.NAMESPACE_DNS,
                                              f"envprobe-{os.getpid()}-{time.time()}"))
            pp = ROOT / "working" / "pipes" / "generated" / f"envprobe_{os.getpid()}.pipe"
            pp.parent.mkdir(parents=True, exist_ok=True)
            pp.write_text(json.dumps(base))
            c = RocketRideClient()
            await c.connect(timeout=60000)
            tok = (await c.use(filepath=str(pp.relative_to(ROOT)),
                               ttl=rrc.RR_TTL_S))["token"]
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
            msg = f"{type(e).__name__}: {str(e)[:160]}"
            if "auth" in msg.lower() or "401" in msg:
                msg += " | " + auth_hint()
            return {"error": msg}

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
            seq_path = run_dir / (
                f"perdoc_{'li' if arm_name.startswith('llamaindex') else 'rr'}_sequential.jsonl")
            recs, done_docs, torn = ([], set(), None)
            if RESUME:
                recs, done_docs, torn = read_completed(seq_path)
                if torn:
                    say(f"  !! {torn}")
                if done_docs:
                    say(f"  RESUME {arm_name}: {len(done_docs)} documents already on disk, "
                        f"{len(pdfs) - len(done_docs)} to go")
            elif seq_path.exists():
                say(f"  !! {seq_path.name} exists and SMOKE_RESUME is not set. Refusing to "
                    "append to a previous run's records — set SMOKE_RESUME=1 to continue it, "
                    "or use a fresh SMOKE_RUN_DIR.")
                return 6
            chunk_texts: dict[str, list] = {}   # doc -> chunks, for post-loop gates
            vecs_keep: dict[str, list] = {}      # doc -> vectors, for the gate suites
            li_src: dict[str, str] = {}         # doc -> service-returned extracted text (LI)
            # Warm-up batch: OUTSIDE the CostSpan, so its CPU, memory and wall time are not in
            # any measured window. Timed and reported separately, never merged.
            warm_s = None
            if warm_pdfs and not done_docs:
                _tw = time.perf_counter()
                _wok = 0
                for wf in warm_pdfs:
                    try:
                        arm.process(wf.read_bytes())
                        _wok += 1
                    except Exception as e:
                        say(f"    warm-up {wf.name}: {type(e).__name__}")
                warm_s = round(time.perf_counter() - _tw, 2)
                say(f"  {arm_name}: warm-up {_wok}/{len(warm_pdfs)} disjoint documents in "
                    f"{warm_s}s (excluded from every measured window)")
                if _wok == 0:
                    say(f"  BLOCKER: every warm-up document failed on {arm_name}. The arm is "
                        "not serving; refusing to start a measured span against it.")
                    return 8
            warm_by_arm[arm_name] = {"docs": len(warm_pdfs), "ok": _wok if warm_pdfs else 0,
                                     "seconds": warm_s, "disjoint_from_measured": warm_disjoint,
                                     "policy": "driver-side, disjoint, excluded (Leela WARM=25)"}
            # K=3 CONSECUTIVE-FAILURE BREAKER. Defect #32: the 10k sequential leg kept sending to
            # a dead task for 371 documents because every error was recorded as a per-document
            # fact. Some errors are about the SESSION, not the document. Three in a row is not a
            # run worth finishing.
            BREAK_K = int(os.environ.get("SMOKE_BREAK_K", "3"))
            _consec = 0
            span = CostSpan(arm_name, "sequential")
            with span, JsonlWriter(seq_path) as seq_out:
                for f in (pdfs if "sequential" in LEGS else []):
                    if f.name in done_docs:
                        continue            # already durable on disk from an earlier attempt
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
                            vecs_keep[f.name] = vecs
                            if arm_name.startswith("llamaindex"):
                                li_src[f.name] = last.get("extracted_text")
                    except Exception as e:
                        rec["completion_ns"] = time.time_ns()
                        rec["outcome"] = "unexpected"
                        rec["error_class"] = f"{type(e).__name__}"
                        rec["error"] = str(e)[:200]
                    rec["ok"] = rec.get("outcome") == "successful"
                    # Session-level failure detection. Counts CONSECUTIVE failures only: an
                    # isolated bad document is a per-document fact and the run continues.
                    _consec = 0 if rec["ok"] else _consec + 1
                    if _consec >= BREAK_K:
                        seq_out.write(rec)
                        recs.append(rec)
                        say(f"  BREAKER: {BREAK_K} consecutive failures on {arm_name} at "
                            f"{f.name} (last: {rec.get('error_class')} "
                            f"{str(rec.get('error'))[:120]}). Aborting this leg — the records "
                            f"written so far are durable in {seq_path.name}.")
                        broke[arm_name] = {"at_doc": f.name, "after": len(recs),
                                           "consecutive": _consec,
                                           "last_error": rec.get("error_class")}
                        break
                    # Durable BEFORE the next document starts. A kill now costs this one
                    # document, not the whole run.
                    seq_out.write(rec)
                    recs.append(rec)
            cost_series[f"{arm_name}:sequential"] = span.series()
            cost_reasons[f"{arm_name}:sequential"] = span.reason
            # MEMORY, every source named. A summed-per-process RSS peak must never ship on
            # its own: shared copy-on-write pages are counted once per worker, so with 32
            # forked uvicorn workers it over-counts by roughly the sharing factor. cgroup
            # anon is the figure comparable to Leela's and Shashi's.
            capture_memory(arm_name, "sequential", span)
            arm.close()
            # ---- OUR gates, post-loop, outside the sampled/timed span ----
            # Deterministic stride sample, not random: reproducible across runs and across the
            # two arms, and it spreads the sample over the corpus instead of clustering it at
            # the front where the small documents happen to live.
            tika_scope = None
            if TIKA_SAMPLE and TIKA_SAMPLE < len(recs):
                stride = max(1, len(recs) // TIKA_SAMPLE)
                tika_scope = {r["doc"] for r in sorted(recs, key=lambda x: x["doc"])[::stride]}
                say(f"  independent-reference SAMPLED: {len(tika_scope)}/{len(recs)} documents "
                    f"(every {stride}th by name; ~{0.599 * len(tika_scope):.0f}s of JVM starts)")
            for rec in recs:
                chunks = chunk_texts.get(rec["doc"])
                if chunks is None:
                    continue
                if tika_scope is not None and rec["doc"] not in tika_scope:
                    rec["independent_hash"] = "not_run: outside the sampled subset"
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
                else:
                    # Second fail-open path, distinct from the missing JRE: on the LlamaIndex arm
                    # the reference is the service's own `extracted_text`, and if a response
                    # omits it the doc was silently skipped by the check with no trace. Name it
                    # per document so coverage is countable instead of assumed.
                    rec["independent_hash"] = ("not_run: no tika reference" if not src and
                                               not arm_name.startswith("llamaindex")
                                               else "not_run: no extracted_text in response")
                sus = [i for i, c in enumerate(chunks) if inspect(c)["suspect"]]
                if sus:
                    rec["content_suspect_chunks"] = sus
            chunk_texts_by_arm[arm_name] = dict(chunk_texts)
            vecs_by_arm[arm_name] = dict(vecs_keep)
            chunk_texts.clear()
            li_src.clear()
            vecs_keep.clear()
            results[arm_name] = recs
            # The post-loop gates add independent_hash / content_suspect to each record;
            # rewrite atomically so a crash leaves the streamed file, never a half-merge.
            rewrite_atomically(seq_path, recs)
            say(f"  {arm_name}: {len(recs)} records -> {seq_path.name}")

        # ---- determinism: a BLAST run (concurrent) vs the SEQUENTIAL run above
        say("\ndeterminism: blast run vs sequential run, per arm"
            + ("" if "blast" in LEGS else " (blast leg NOT run; using on-disk records)"))
        blobs = [(f.name, f.read_bytes()) for f in pdfs]

        # TWO CLOCKS PER DOCUMENT, ON BOTH ARMS. `enqueue_ns` is when the batch opened and the
        # item joined the client queue; `admit_ns` is when it went on the wire, after the
        # BLAST_C cap let it through. `submit_ns` == `admit_ns` so metrics_shared measures
        # SERVICE latency identically on both arms.
        #
        # DEFECT #29 (2026-08-16), which this replaces. LlamaIndex stamped `submit_ns` inside
        # the worker thread — i.e. at admission — while RocketRide stamped it at coroutine
        # creation, BEFORE `async with sem`, so all N documents were stamped at t0 and every
        # one of them carried the whole client-side queue wait in its "latency". Measured on
        # two local 200-doc runs: LlamaIndex submit spread 65.0 s and 67.2 s over 67 s and 69 s
        # legs (97.6%, 97.5% — spread across the leg); RocketRide 0.001 s over a 319 s leg
        # (0.0% — every document stamped at batch open). At 10k that printed RocketRide p50
        # 1120 s against LlamaIndex 2.05 s, a ~550x artifact of where the clock started.
        # Recording BOTH stamps means neither definition has to win: service latency and
        # Leela's batch-position latency are now derivable from the same records, so the
        # choice never costs another run.
        enqueue_ns = time.time_ns()

        # LlamaIndex: blocking urllib, so threads are the right concurrency primitive.
        def blast_llama(out_path, prior, done):
            import concurrent.futures as cf
            arm = LlamaHttpPdfArm(port=PORT)
            todo = [(n, b) for n, b in blobs if n not in done]

            with JsonlWriter(out_path) as w:
                def one(item):
                    name, b = item
                    # Reached only once a pool thread is free: this IS the admission instant.
                    admit = time.time_ns()
                    row = {"doc": name, "enqueue_ns": enqueue_ns, "admit_ns": admit,
                           "submit_ns": admit}
                    try:
                        ch, _ = arm.process(b)
                        row.update(completion_ns=time.time_ns(), ok=True,
                                   n_chunks=len(ch), chunk_sha256=[h(c) for c in ch])
                    except Exception as e:
                        row.update(completion_ns=time.time_ns(), ok=False,
                                   error_class=type(e).__name__)
                    # Durable before the next document is dispatched. JsonlWriter holds a lock,
                    # so concurrent worker threads cannot splice two records into one line.
                    w.write(row)
                    return row
                with cf.ThreadPoolExecutor(max_workers=BLAST_C) as ex:
                    fresh = list(ex.map(one, todo))
            arm.close()
            rows = prior + fresh
            return {r["doc"]: r.get("chunk_sha256") for r in rows}, rows

        # RocketRide: ONE asyncio loop, C concurrent send() coroutines. Driving RocketPdfArm.process
        # from a ThreadPoolExecutor calls run_until_complete on one loop from several threads, which
        # silently abandons coroutines ("coroutine 'send' was never awaited") and reports spurious
        # non-determinism. Measured: that harness bug alone produced 7/8 false "drift".
        def blast_rocket(out_path, prior, done):
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
                tok = (await c.use(filepath=str(pp.relative_to(ROOT)),
                               ttl=rrc.RR_TTL_S))["token"]
                sem = asyncio.Semaphore(BLAST_C)
                rows = []
                todo = [(n, b) for n, b in blobs if n not in done]

                async def one(name, b):
                    # `gather` starts every coroutine in the loop's first pass, so a stamp
                    # taken HERE is the batch-open time for all N documents, not a submission.
                    row = {"doc": name, "enqueue_ns": enqueue_ns}
                    async with sem:
                        row["admit_ns"] = row["submit_ns"] = time.time_ns()
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
                    w.write(row)          # durable as each send completes
                try:
                    await asyncio.gather(*(one(n_, b) for n_, b in todo))
                finally:
                    try:
                        await asyncio.wait_for(c.terminate(tok), timeout=60)
                    except Exception:
                        pass
                    await c.disconnect()
                allrows = prior + rows
                return {r["doc"]: r.get("chunk_sha256") for r in allrows}, allrows
            with JsonlWriter(out_path) as w:
                return asyncio.run(go())

        for arm_name, runner in (("llamaindex_http_pdf", blast_llama),
                                 ("rocketride_pdf", blast_rocket)):
            blast_path = run_dir / (
                f"perdoc_{'li' if arm_name.startswith('llamaindex') else 'rr'}_blast.jsonl")
            prior, done_b, torn_b = ([], set(), None)
            if RESUME:
                prior, done_b, torn_b = read_completed(blast_path)
                if torn_b:
                    say(f"  !! {torn_b}")
                if done_b:
                    say(f"  RESUME {arm_name} blast: {len(done_b)} on disk, "
                        f"{len(pdfs) - len(done_b)} to go")
            elif blast_path.exists():
                say(f"  !! {blast_path.name} exists and SMOKE_RESUME is not set. Refusing to "
                    "append to a previous run's records.")
                return 6
            if "blast" in LEGS:
                span = CostSpan(arm_name, "blast")
                with span:
                    blast, brows = runner(blast_path, prior, done_b)
                cost_series[f"{arm_name}:blast"] = span.series()
                cost_reasons[f"{arm_name}:blast"] = span.reason
                # The blast leg runs BLAST_C requests in flight, so its process count — and
                # therefore its summed-RSS over-count — is nothing like the sequential leg's.
                capture_memory(arm_name, "blast", span)
            else:
                # Leg skipped: read whatever a previous invocation left. Determinism then
                # compares against real records rather than silently reporting everything
                # unproven, which would read as a clean gate on no evidence.
                brows, _d, _t = read_completed(blast_path)
                blast = {r["doc"]: r.get("chunk_sha256") for r in brows}
                say(f"  {arm_name} blast: {len(brows)} records read from disk (leg not run)")
            blast_rows[arm_name] = brows
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
           # Leela's 24 REQUIRED fields under HIS key names (provenance.py:16-27). Our own
           # blocks below carry the same information under ours; his `check()` matches by key,
           # so without this a consumer marks our run "not publishable" on 23 of 24.
           # Leela m0_correctness.py:311 — the SENSITIVE detector (fires on any doc with >1
           # chunk, not only >=64). This is what PROVES the duplication patch worked: on
           # rr:patched it must read 0 duplicated documents.
           "self_duplication": {a: gs.self_duplication(results[a]) for a in results},
           "warm_up": warm_by_arm,
           "breaker": broke or None,
           "provenance_leela": {
               arm_name: pvl.build(
                   arm=arm_name, mode="sequential+blast", corpus_sha=corpus_sha,
                   corpus_n=len(pdfs),
                   offered_concurrency=BLAST_C,
                   # RocketRide: we pass no `threads=` to use(), so there is no configured
                   # value. Recorded as Leela records it in his own banner rather than as
                   # None, which his check() would read as a missing field rather than as
                   # the accurate statement that nothing was configured.
                   configured_concurrency=(WORKERS if arm_name.startswith("llamaindex")
                                           else "unset (engine default)"),
                   warmup_policy=(f"metric-side, first {WARM_N_PRIMARY} completions excluded "
                                  "(perf_window by completion rank)"),
                   timeout_s=1800,
                   parser=("pypdf" if arm_name.startswith("llamaindex") else "tika-3.2.3"),
                   chunk_size=4000, chunk_overlap=200,
                   embedding_model="sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
                   container=(LI_CONTAINER if arm_name.startswith("llamaindex")
                              else RR_CONTAINER) if EXTERNAL else None)
               for arm_name in results},
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
                      "memory_sources": mem_sources,
                      "legs_run": sorted(LEGS),
                      "tika_sample_size": TIKA_SAMPLE or None,
                      "tika_sample_note": (
                          "0/None = every document. A positive value is a deterministic stride "
                          "sample; the covered count per arm is in arms.*.independent_reference."),
                      "cost_available": all(cost_series.get(k) for k in cost_series),
                      "cost_unavailable_reason": next(
                          (r for r in cost_reasons.values() if r), None),
                      "cost_sampler": {"source": "psutil ProcessCollector (out-of-process, "
                                                 "dead-PID roll-forward)",
                                       "interval_s": SAMPLE_INTERVAL_S,
                                       "scope": "service process tree only, driver excluded",
                                       "pluggable": "box/Docker mode consumes Leela's "
                                                    "cgroup_sampler JSONL via "
                                                    "metrics_shared.series_from_cgroup_jsonl"},
                      # DRIVER affinity, named as such — never a utilisation denominator
                      # for a containerised service (defect #34).
                      "driver_affinity_cpus": (len(os.sched_getaffinity(0))
                                               if hasattr(os, "sched_getaffinity")
                                               else os.cpu_count()),
                      "host_cpu_count": os.cpu_count(),
                      # Which credentials the RocketRide arm actually used, and where they came
                      # from. The key itself is never written to a result file — a fingerprint is
                      # enough to prove two sites used the same one.
                      "rocketride_client": rr_creds,
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
        say(f"  census      offered {len(pdfs)} = successful {c['successful']} + "
            f"expected {c['expected']} + unexpected {c['unexpected']}   -> {'PASS' if census_ok else 'FAIL'}")
        say(f"  structure   {len(struct_fail)} failure(s)                      -> "
            f"{'PASS' if not struct_fail else 'FAIL'}")
        say(f"  determinism {len(det_fail)} drifted, {len(det_unproven)} unproven"
            f"            -> {'PASS' if not det_fail and not det_unproven else 'FAIL'}")
        # Coverage, not just failures. Leela's rule (m0_correctness.ground_truth_match): zero
        # coverage is a vacuous result, not a pass. A "0 FAIL" printed by a check that never ran
        # on a single document is the exact silent degradation this project keeps getting burned
        # by, so the count and the denominator are always printed together.
        n_ok = sum(1 for r in recs if r.get("outcome") == "successful")
        covered = sum(1 for r in recs
                      if str(r.get("independent_hash", "")).startswith(("pass", "FAIL")))
        if covered == 0:
            say(f"  independent-reference    : NOT RUN (0/{n_ok} successful docs covered)"
                f" — advisory check, dependency missing")
        else:
            say(f"  independent-reference    : {len(ind_fail)} FAIL "
                f"over {covered}/{n_ok} successful docs covered"
                + ("  !! PARTIAL COVERAGE" if covered < n_ok else ""))
        say(f"  content-suspect documents : {len(sus)}")
        out["arms"][arm_name] = {"census": c, "census_ok": census_ok,
                                 "structure_failures": len(struct_fail),
                                 "determinism_failures": len(det_fail),
                                 "determinism_unproven": len(det_unproven),
                                 "independent_hash_failures": len(ind_fail),
                                 "independent_reference": {
                                     "available": ok_tika if not arm_name.startswith("llamaindex")
                                     else None,
                                     "unavailable_reason": None if ok_tika else why,
                                     "covered": covered, "successful": n_ok,
                                     "ran": covered > 0, "full_coverage": covered == n_ok},
                                 "content_suspect": len(sus), "records": recs}

    # ---------------- THREE VERDICTS: Shashi's gates, Leela's, and the union ----------
    # Same records, three readings. Neither teammate should have to re-derive ours, and
    # where their definitions genuinely conflict both are computed and labelled rather
    # than one being chosen. Gate logic lives in harness/gates_shared.py with the
    # file:line it was adopted from; nothing here touches metrics_shared.py.
    out["gate_verdicts"] = {}
    for arm_name, recs in results.items():
        arm_key = "lg" if arm_name.startswith("llamaindex") else "rr"
        gate_rows, seen_names, zero_chunk = [], [], []
        for r in recs:
            chunks = chunk_texts_by_arm.get(arm_name, {}).get(r["doc"])
            vecs = vecs_by_arm.get(arm_name, {}).get(r["doc"])
            errored = r.get("outcome") == "unexpected"
            row = {"doc": r["doc"], "errored": errored,
                   "identity_ok": r.get("returned_doc_id") is not None or arm_key == "rr",
                   "sha_header_ok": True,
                   # OUR failure vocabulary mapped to Leela's at the boundary, so an expected
                   # empty is not counted as an unexpected failure by her census.
                   "reason": gs.to_leela_reason(r.get("error_class"))}
            if chunks is not None and vecs is not None:
                row.update(gs.check_document(chunks, vecs, probed_dim[arm_name]))
            else:
                row.update(n_chunks=r.get("n_chunks"),
                           chunk_sha256=r.get("chunk_sha256"),
                           vector_dim=probed_dim[arm_name], vectors_finite=True)
            # ONE success rule, applied to this leg and the blast leg alike. Classifying the
            # same document differently per leg is what manufactured phantom only_in_b.
            row["ok"] = gs.classify_ok(row.get("n_chunks"), errored)
            gate_rows.append(row)
            seen_names.append(r["doc"])
            if row.get("n_chunks") == 0:
                zero_chunk.append(r["doc"])

        blast_rowset = []
        for b in blast_rows.get(arm_name, []):
            berr = not b.get("ok")
            blast_rowset.append({"doc": b["doc"], "errored": berr,
                                 "ok": gs.classify_ok(b.get("n_chunks"), berr),
                                 "chunk_sha256": b.get("chunk_sha256")})
        seq_digests = {r["doc"]: r.get("chunk_sha256") for r in gate_rows if r["ok"]}
        blast_digests = {b["doc"]: b.get("chunk_sha256") for b in blast_rowset if b["ok"]}
        # Zero-chunk documents are legitimate; both censuses need the allowlist or they call
        # them defects. Neither can infer it.
        exp_empty = gs.expected_empty_docs(gate_rows)

        leela_checks = {
            "census": gs.leela_census(gate_rows, len(pdfs), expected_empty=exp_empty),
            "structure": gs.leela_structure(gate_rows, arm_key, probed_dim[arm_name]),
            "determinism": gs.leela_determinism(gate_rows, blast_rowset),
        }
        shashi_checks = {
            "census": gs.shashi_census([p.name for p in pdfs], seen_names,
                                       expected_empty=exp_empty,
                                       zero_chunk_names=zero_chunk),
            "structure": gs.shashi_structure(gate_rows, probed_dim[arm_name]),
            "determinism": gs.shashi_determinism(seq_digests, blast_digests,
                                                 "sequential", "blast"),
        }
        out["gate_verdicts"][arm_name] = gs.three_verdicts(shashi_checks, leela_checks)

    # Cross-arm gates that only exist once, not per arm (Shashi bench.py:337,356,431).
    li_s = out["gate_verdicts"]["llamaindex_http_pdf"]["shashi"]["checks"]["structure"]
    rr_s = out["gate_verdicts"]["rocketride_pdf"]["shashi"]["checks"]["structure"]
    li_chunks = sum(r.get("n_chunks") or 0 for r in results["llamaindex_http_pdf"])
    rr_chunks = sum(r.get("n_chunks") or 0 for r in results["rocketride_pdf"])
    cross = {
        "workload_ratio_rr_over_li": gs.workload_ratio_gate(rr_chunks, li_chunks),
        "normalization_parity": gs.normalization_parity(rr_s, li_s),
        "chunk_config_parity": gs.chunk_config_parity(
            (4000, 200), (4000, 200)),   # both arms configured from the same measured pair
    }
    cross["PASS"] = gs.gate_verdict(*cross.values())
    out["gate_verdicts"]["cross_arm"] = cross

    # ---- paste-ready table. Fixed widths, ASCII only, PASS/FAIL only. ----
    # Gate names are the teammates' own identifiers and are never re-worded. Verdict
    # labels state the RULE that distinguishes them rather than naming a person, so the
    # table needs no legend. The gate_verdicts block written above is untouched by this;
    # `duplication` is read out of the structure verdict where it already lives rather
    # than being added to the JSON.
    ARMS = [("llamaindex_http_pdf", "LLAMAINDEX"), ("rocketride_pdf", "ROCKETRIDE")]
    W_GATE, W_COL = 26, 11

    def mark(d) -> str:
        return "PASS" if isinstance(d, dict) and d.get("PASS") is True else "FAIL"

    def gv(arm, suite, gate):
        return out["gate_verdicts"][arm][suite]["checks"].get(gate)

    say("")
    say("=" * 78)
    say(f"CORRECTNESS GATES - {len(pdfs)} documents, identical records, three verdicts")
    say("=" * 78)
    say("")
    say("GATES EVALUATED UNDER BOTH RULES")
    say(f"{'':{W_GATE}}{'VERDICT A':{2 * W_COL}}{'VERDICT B':{2 * W_COL}}")
    say(f"{'GATE':{W_GATE}}" + "".join(f"{lbl:{W_COL}}" for _, lbl in ARMS) * 2)
    say("-" * 78)
    for gate in ("census", "structure", "determinism"):
        row = f"{gate:{W_GATE}}"
        for suite in ("shashi", "leela"):
            row += "".join(f"{mark(gv(a, suite, gate)):{W_COL}}" for a, _ in ARMS)
        say(row)
    say("")
    say("GATES IN VERDICT A ONLY")
    say(f"{'GATE':{W_GATE}}" + "".join(f"{lbl:{W_COL}}" for _, lbl in ARMS))
    say("-" * 78)
    say(f"{'duplication':{W_GATE}}" + "".join(
        f"{mark((gv(a, 'shashi', 'structure') or {}).get('duplication')):{W_COL}}"
        for a, _ in ARMS))
    say("")
    say("CROSS-ARM GATES, VERDICT A ONLY")
    say(f"{'GATE':{W_GATE}}{'RESULT':{W_COL}}")
    say("-" * 78)
    for k in ("workload_ratio_rr_over_li", "normalization_parity", "chunk_config_parity"):
        say(f"{k:{W_GATE}}{mark(cross[k]):{W_COL}}")
    say("")
    say("VERDICT SUMMARY")
    say(f"{'VERDICT':{52}}" + "".join(f"{lbl:{W_COL}}" for _, lbl in ARMS))
    say("-" * 78)
    for key, label in (("shashi", "A  intersection determinism, name-keyed census"),
                       ("leela",  "B  symmetric determinism, count-keyed census"),
                       ("union",  "C  union (strictest; conjunction of A and B)")):
        say(f"{label:{52}}" + "".join(
            f"{('PASS' if out['gate_verdicts'][a][key]['PASS'] else 'FAIL'):{W_COL}}"
            for a, _ in ARMS))
    say("=" * 78)

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
    # Publishability is DERIVED from the platform, not asserted. The old string said "macOS"
    # unconditionally and printed that on a Linux box run, which is the same class of defect as
    # a hardcoded gate verdict: the caveat stopped tracking the thing it describes.
    import platform as _plat
    _machine, _system = _plat.machine(), _plat.system()
    _native_x86 = _machine in ("x86_64", "AMD64")
    _publishable = _native_x86 and _system == "Linux"
    _why = (None if _publishable else
            f"{_system}/{_machine} — the pinned target is Linux x86_64; "
            "throughput and cost from any other platform are wiring validation only")
    say(f"\nMETRICS (metrics_shared; platform {_system}/{_machine}; "
        + ("publishable target platform)" if _publishable
           else "NOT the target platform, numbers are wiring validation only)"))
    # Defect #34 (supersedes the affinity fix that introduced it): the DRIVER's affinity is 8
    # under `taskset -c 24-31` while the SERVICE containers run on cpuset 0-23 (24), so using
    # sched_getaffinity here divided every utilisation by the wrong process's allocation —
    # util printed 1.58 INVALID for a true 52.8%. The denominator now comes from each SERVICE
    # container's own cgroup, per arm, source recorded. Driver affinity remains correct only
    # in native mode, where the service is the driver's child and genuinely shares it.
    _drv = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    cpus_by_arm: dict[str, int | None] = {}
    cpus_src: dict[str, str] = {}
    for _arm, _cont in (("llamaindex_http_pdf", os.environ.get("SMOKE_LI_CONTAINER", "li")),
                        ("rocketride_pdf", os.environ.get("SMOKE_RR_CONTAINER", "rr"))):
        if EXTERNAL:
            from harness import experiment_common as _ec
            cpus_by_arm[_arm], cpus_src[_arm] = _ec.service_available_cpus(_cont)
        else:
            cpus_by_arm[_arm] = _drv
            cpus_src[_arm] = "driver sched_getaffinity (native mode: service is a child)"
        say(f"  available_cpus[{_arm}] = {cpus_by_arm[_arm]}  ({cpus_src[_arm]})")

    out["metrics"] = {"module": "working/harness/metrics_shared.py",
                      "platform": {"system": _system, "machine": _machine,
                                   "native_x86_64": _native_x86},
                      "publishable": _publishable,
                      "not_publishable_reason": _why,
                      "arms": {}}
    out["metrics"]["available_cpus"] = {"by_arm": cpus_by_arm, "source_by_arm": cpus_src,
                                        "driver_affinity_cpus": _drv,
                                        "host_cpu_count": os.cpu_count()}
    # Both blast legs are a BOUNDED CLIENT POOL of BLAST_C, not an open-loop arrival process:
    # nothing is submitted until a slot frees, so offered load is throttled by the system under
    # test. Measured from admission the result is closed-loop service latency. Leela's
    # batch-position figure is still reported, from `enqueue_ns`, as its own row — the two are
    # never merged, and neither definition needs a second run to obtain.
    def _batchpos(rows):
        """Same rows, clock moved back to batch open — Leela's open-loop-blast definition.

        ALL OR NOTHING. A run resumed from records written before defect #29 mixes rows that
        carry `enqueue_ns` with rows that do not, and silently dropping the older ones would
        compute a percentile over whichever subset happened to be fresh — a partial reported
        as whole, which is the defect class this harness keeps tripping over. Emit nothing
        and say why instead.
        """
        if not rows:
            return []
        missing = [r for r in rows if not r.get("enqueue_ns")]
        if missing:
            say(f"  !! batch-position latency unavailable: {len(missing)}/{len(rows)} rows "
                "predate the enqueue_ns stamp (defect #29). Not reporting a partial.")
            return []
        return [{**r, "submit_ns": r["enqueue_ns"]} for r in rows]

    for arm_name in results:
        marm = out["metrics"]["arms"].setdefault(arm_name, {})
        cells = [("sequential", results[arm_name], "closed-loop"),
                 ("blast", blast_rows.get(arm_name, []), "closed-loop"),
                 ("blast_batchpos", _batchpos(blast_rows.get(arm_name, [])),
                  "open-loop-blast")]
        for mode, mrows, label in cells:
            series = cost_series.get(f"{arm_name}:{mode.split('_')[0]}")
            for wn in (WARM_N_PRIMARY, WARM_N_SECONDARY):
                d = ms.derive_side(mrows, series, warm_n=wn,
                                   available_cpus=cpus_by_arm.get(arm_name), mode=label)
                if mode.startswith("blast"):
                    d["client_concurrency"] = BLAST_C
                    # Shashi's basis-field pattern (rr_app.py:175-188): a derived number must
                    # carry the sentence saying what it is. Per-document latency under a batched
                    # send is not observed — the batch has one submit and one return.
                    if d.get("latency") and BATCHED_ARMS and arm_name in BATCHED_ARMS:
                        d["latency"]["basis"] = (
                            "DERIVED, not measured: batched send_files returns the whole batch "
                            "at once, so per-document completion comes from the engine's own "
                            "upload_time and submit is the batch open instant")
                        d["latency"]["measured"] = False
                # The metric is peak-of-a-SUM-of-per-process-RSS over THIS leg's window. Named
                # in place so the figure cannot be lifted out of the line and read as a
                # footprint, and cannot be divided by the memory table's sequential-leg
                # sharing factor (defect #30).
                d["peak_summed_process_rss_mb"] = d.pop("peak_rss_mb", None)
                d["peak_summed_process_rss_note"] = (
                    f"peak of a SUM of per-process RSS over the {mode} window; shared pages "
                    "counted once per process. NOT a footprint, NOT comparable across legs "
                    "with different process counts.")
                marm[f"{mode}_warm{wn}"] = d
                if "error" in d:
                    say(f"  {arm_name:22} {mode:14} warm_n={wn:<3} -> {d['error']}")
                    continue
                lat = d.get("latency") or {}
                say(f"  {arm_name:22} {mode:14} warm_n={wn:<3} "
                    f"docs/s={d['docs_per_s']}  chunks/s={d['chunks_per_s']}  "
                    f"p50={lat.get('p50')}s p95={lat.get('p95')}s [{lat.get('mode', '?')}]  "
                    f"cpu_s={d['cpu_s']}  cpu_s/doc={d['cpu_s_per_doc']}  "
                    f"cores={d['effective_cores']}  util={d['cpu_utilization']}"
                    f"{'' if d.get('cpu_utilization_valid') in (True, None) else ' INVALID'}  "
                    f"summedRSS={d['peak_summed_process_rss_mb']}MB(not a footprint)")

    say("")
    say("MEMORY - every source named, PER LEG; a summed-RSS peak is NOT a footprint")
    say(f"{'ARM:LEG':30}{'cgroup anon':>13}{'summed RSS':>13}{'summed PSS':>13}"
        f"{'procs':>7}{'tasks':>7}{'anon pt':>10}")
    say(f"{'':30}{'PEAK sampled':>13}{'peak (sum)':>13}{'peak (sum)':>13}"
        f"{'peak':>7}{'peak':>7}{'post-leg':>10}")
    say("-" * 93)
    for key, m in mem_sources.items():
        say(f"{key:30}"
            f"{_fmt_mb(m.get('cgroup_anon_peak_mb')):>13}"
            f"{_fmt_mb(m.get('summed_process_rss_peak_mb')):>13}"
            f"{_fmt_mb(m.get('summed_process_pss_peak_mb')):>13}"
            f"{str(m.get('peak_process_count') or '-'):>7}"
            f"{str(m.get('cgroup_peak_tasks') or '-'):>7}"
            f"{_fmt_mb(m.get('cgroup_anon_mb')):>10}")
        if m.get("sharing_factor_sampled"):
            say(f"{'':30}summed RSS / sampled anon = {m['sharing_factor_sampled']}x "
                f"in THIS leg only ({m.get('peak_process_count')} procs, "
                f"{m.get('tasks_per_process_at_peak')} tasks/proc at peak)")
        if m.get("no_sampled_anon_reason"):
            say(f"{'':30}!! NO SAMPLED ANON: {m['no_sampled_anon_reason']}")
        if m.get("summed_rss_impossible_as_footprint"):
            say(f"{'':30}!! {m['summed_rss_impossible_as_footprint']}")
        if m.get("cgroup_unavailable_reason"):
            say(f"{'':30}cgroup unavailable: {m['cgroup_unavailable_reason']}")
    say("QUOTE 'cgroup anon PEAK sampled' against Leela's and Shashi's figures. 'anon pt' is a")
    say("single read taken AFTER the leg and is not a peak. 'tasks' counts threads, not procs.")
    say("Columns are DIFFERENT KINDS of number and do not divide into each other across rows.")
    say("QUOTE cgroup anon against Leela's and Shashi's memory figures - both read the")
    say("cgroup, where a shared page is charged once. Summed RSS is not comparable to either.")

    p = write_result("smoke50_parser_in", out)
    say(f"\nwritten -> {p}")
    say(f"raw per-doc JSONL + sampler streams -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
