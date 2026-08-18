#!/usr/bin/env python3
"""Weekend worker — one phase, one arm, continuous processing with checkpoints.

Invoked by weekend_runner.sh. Never run by hand during the weekend run.

DESIGN NOTES THAT MATTER
------------------------
CONTINUOUS, NOT RUNGS. Rungs reprocess documents 0..N every time N grows, which wastes hours
re-embedding the same PDFs. This walks the corpus once and checkpoints every CHECKPOINT_EVERY
documents, so the record at any moment is "we processed the first k documents", not "we processed
100, then the same 100 plus 400 more".

IDEMPOTENT. On start it reads the phase checkpoint and resumes from the next unprocessed index.
Relaunching after a kill never restarts a phase from zero.

OOM IS A VALID RESULT. A memory ceiling breach is caught, the full RSS curve up to it and the
document that triggered it are written, and the process exits with a distinct code so the runner
advances instead of dying. Losing the pre-crash curve would waste the whole phase.

HEARTBEAT. Written every HEARTBEAT_EVERY seconds so a human can tell "slow" from "silently dead".
A fetch was assumed alive for two hours in this project when it had exited immediately.

GOODPUT. Every document is asserted through harness.goodput. A PDF path with no reader registered
returns {} silently and would otherwise produce a flawless-looking run that embedded nothing.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import resource
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))

from harness.goodput import check_document, GoodputFailure   # noqa: E402
from harness.resultio import write_result                     # noqa: E402

CHECKPOINT_EVERY = 100
HEARTBEAT_EVERY = 60.0
RSS_SAMPLE_EVERY = 5
STATE_DIR = ROOT / "weekend_state"
STATUS = ROOT / "status.txt"

EXIT_OK, EXIT_CAP, EXIT_OOM, EXIT_ERR = 0, 10, 11, 1


def container_root_pid(name: str) -> int | None:
    """HOST pid of a container's main process, via `docker inspect`.

    WHY THIS EXISTS — the sampler was never the problem, discovery was.

    Docker on Linux does not hide container processes from the host: they appear in the
    host PID table under host numbering, so `/proc/<hostpid>/stat` exists and is readable.
    psutil reads exactly that for CPU (`_pslinux.py:1828` cpu_times -> _parse_stat_file ->
    /proc/<pid>/stat) and `/proc/<pid>/statm` for RSS (`:1878`). **Both are world-readable
    (0444), so an unprivileged host process CAN sample a container's tree.**

    What an unprivileged host process CANNOT do is *find* those pids with lsof. lsof maps a
    listening socket to a pid by reading `/proc/<pid>/fd/*`, which is 0500 owner-only. Our
    containers run as uid 10001 (`Dockerfile.llamaindex`: useradd -u 10001 ws1) and the
    driver runs as ssm-user, so `lsof -iTCP:8801` returns nothing for it — while the same
    command under sudo lists the pids and emits "no pwd entry for UID 10001" for every one,
    because root can read the fds but there is no host passwd entry for that uid.

    `docker inspect` needs no procfs privilege at all, so it is the discovery mechanism in
    external mode — for BOTH arms, so neither is sampled by a different source.
    """
    import subprocess
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Pid}}", name],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    pid = (r.stdout or "").strip()
    if r.returncode != 0 or not pid.isdigit() or int(pid) == 0:
        return None            # 0 means the container exists but is not running
    return int(pid)


def external_services() -> bool:
    """True when the services under test are CONTAINERS, not host processes.

    Every host-side discovery path in this file — `lsof` by listening socket, psutil tree
    walks, process-name matching — was written for services this driver started itself.
    None of them is a reliable precondition once the service is in a container: the
    listener may belong to a PID the host cannot resolve, and name matching would happily
    match some other `engine` (it already cost this project a 104 MB accounting error, see
    engine_tree_rss_mb).

    So in external mode discovery becomes OPTIONAL and NON-FATAL. Readiness is proven by
    the driver's HTTP/`/version` gates instead, which work across the boundary. Anything
    that genuinely needs a host PID (RSS, CPU sampling) reports unavailable with a reason
    rather than guessing or dying.

    Single source of truth: the same SMOKE_EXTERNAL the driver already sets.
    """
    return os.environ.get("SMOKE_EXTERNAL", "") not in ("", "0", "false", "False")


def rss_mb() -> float:
    """Current RSS. macOS ru_maxrss is BYTES; Linux reports kB. Measured, not assumed."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 1e6 if sys.platform == "darwin" else r / 1024.0


def engine_tree_rss_mb(root_pid: int | None = None) -> float:
    """RSS of the engine process tree — the RocketRide arm does its work out of process.

    MATCH BY PID, NOT BY NAME. The name-matching version counted EVERY process called "engine",
    including a five-day-old unrelated installation under ~/Library/Application Support that
    contributed 104 MB (~5.8 % of the RocketRide median) to the weekend run's numbers.
    See publishable/WEEKEND_FORENSICS.md section 2.
    """
    try:
        import psutil
    except Exception:
        return 0.0
    tot, seen = 0.0, set()
    if root_pid is not None:
        try:
            roots = [psutil.Process(root_pid)]
        except Exception:
            roots = []
    else:
        roots = [r for r in psutil.process_iter(["pid", "name"])
                 if (r.info["name"] or "").lower() == "engine"]
    for r in roots:
        try:
            for p in [r] + r.children(recursive=True):
                if p.pid in seen:
                    continue
                seen.add(p.pid)
                tot += p.memory_info().rss / 1e6
        except Exception:
            pass
    return tot


def system_used_mb() -> float:
    """System-wide resident memory — a cross-check the tree walk cannot falsify on its own.

    A task process that lives less than one sample interval is invisible to a tree walk. This is
    not, so recording both makes the tree walk checkable instead of merely trusted.
    """
    try:
        import psutil
        return psutil.virtual_memory().used / 1e6
    except Exception:
        return 0.0


class Phase:
    def __init__(self, name: str, arm: str, cap_s: float, limit_mb: float, target: int):
        self.name, self.arm, self.cap_s = name, arm, cap_s
        self.limit_mb, self.target = limit_mb, target
        self.ckpt = STATE_DIR / f"{name}_{arm}.json"
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        if self.ckpt.exists():
            try:
                s = json.loads(self.ckpt.read_text())
                print(f"[resume] {self.name}/{self.arm} from index {s.get('next_index', 0)}",
                      flush=True)
                return s
            except Exception:
                print(f"[resume] checkpoint unreadable, starting fresh", flush=True)
        return {"next_index": 0, "goodput": 0, "faults": {}, "rss_series": [],
                "peak_rss_mb": 0.0, "chunks": 0, "elapsed_s": 0.0, "status": "new"}

    def save(self, **extra):
        self.state.update(extra)
        tmp = self.ckpt.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        tmp.replace(self.ckpt)          # atomic: a torn checkpoint is worse than none


def heartbeat(phase: str, arm: str, idx: int, total: int, t0: float, rss: float, extra=""):
    STATUS.write_text(
        f"phase={phase} arm={arm} doc={idx}/{total} elapsed={time.time()-t0:.0f}s "
        f"rss={rss:.0f}MB pid={os.getpid()} updated={time.strftime('%Y-%m-%dT%H:%M:%S')} {extra}\n")


# ------------------------------------------------------------------ arms
class LlamaArm:
    name = "llamaindex"

    def __init__(self):
        from ws1.pipeline import LlamaIndexPipeline
        self.p = LlamaIndexPipeline(
            model_name="sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
            chunk_size=4000, chunk_overlap=200, device="cpu")
        self.p.warm()

    def process(self, text):
        r = self.p.process(text)
        return r.chunks, r.embeddings

    def rss(self):
        return rss_mb()

    def close(self):
        pass


from harness.rr_credentials import RR_TTL_S  # noqa: E402


class RocketArm:
    """RocketRide over the canonical 4-node pipeline, driven synchronously."""
    name = "rocketride"

    @staticmethod
    def _engine_pid() -> int | None:
        """The engine actually serving 5565 — identified by LISTENING SOCKET, not by name.

        Name matching counted an unrelated five-day-old engine installation in the weekend run.
        The process holding the port is the one we are driving, by definition.
        """
        # psutil.net_connections() needs root on macOS and returns None silently without it —
        # which is exactly how the first version of this fix appeared to work while falling back
        # to name matching. lsof does not need root, and the pidfile is the declared value.
        import subprocess
        try:
            out = subprocess.run(["lsof", "-nP", "-l", "-iTCP:5565", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, timeout=15).stdout
            for ln in out.splitlines()[1:]:
                f = ln.split()
                if len(f) > 1 and f[1].isdigit():
                    return int(f[1])
        except Exception:
            pass
        try:                                   # fallback: the pidfile start_engine.sh writes
            return int((ROOT / "logs" / "engine.pid").read_text().strip())
        except Exception:
            return None

    def __init__(self, tag: str = "rr", pipe: str = "embed_probe.pipe"):
        import asyncio, uuid
        from rocketride import RocketRideClient
        self.loop = asyncio.new_event_loop()
        self.engine_pid = self._engine_pid()
        if self.engine_pid is None and external_services():
            self.engine_pid = container_root_pid(
                os.environ.get("SMOKE_RR_CONTAINER", "rr"))
        if self.engine_pid is None and external_services():
            print("[engine] no host-visible listener on 5565 — external/container mode; "
                  "readiness came from /version. RSS by process tree unavailable.", flush=True)
        else:
            print(f"[engine] driving pid={self.engine_pid} "
                  "(matched by listening socket, not name)", flush=True)
        base = json.loads((ROOT / "working" / "pipes" / pipe).read_text())
        # ONE LIVE TASK PER project_id (STATE.md section 9). A fixed id made p0, p3 and p4 collide
        # with each other — the first RocketRide phase claimed the id and every later phase died
        # with "Pipeline is already running". The id must be unique per phase AND per process, or
        # phase 4 (both arms at once) collides with phase 3's leftover task.
        uniq = f"weekend-rr-{tag}-{os.getpid()}-{int(time.time())}"
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, uniq))
        p = ROOT / "working" / "pipes" / "generated" / f"weekend_rr_{tag}_{os.getpid()}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(base))
        self.c = RocketRideClient()
        self.loop.run_until_complete(self.c.connect(timeout=60000))
        r = self.loop.run_until_complete(
            self.c.use(filepath=str(p.relative_to(ROOT)), ttl=RR_TTL_S))
        self.tok = r["token"]

    def process(self, text):
        import asyncio
        out = self.loop.run_until_complete(
            asyncio.wait_for(self.c.send(self.tok, text, mimetype="text/plain"), timeout=1800))
        docs = out.get("documents") or []
        # field names verified empirically: the 4-node pipeline returns page_content/embedding,
        # NOT text/embeddings. The goodput gate caught this mismatch on the first attempt.
        return [d.get("page_content", "") for d in docs], [d.get("embedding") or [] for d in docs]

    def rss(self):
        # engine_tree_rss_mb(None) falls back to matching processes NAMED "engine" — the
        # exact mistake that counted an unrelated five-day-old install in the weekend run.
        # In external mode there is no host PID to walk, so return the driver's own RSS and
        # let the caller see that the service side is missing, rather than silently
        # attributing some other process's memory to RocketRide.
        if self.engine_pid is None:
            return float("nan") if external_services() else engine_tree_rss_mb(None) + rss_mb()
        return engine_tree_rss_mb(self.engine_pid) + rss_mb()

    def close(self):
        try:
            import asyncio
            self.loop.run_until_complete(asyncio.wait_for(self.c.terminate(self.tok), timeout=120))
            self.loop.run_until_complete(self.c.disconnect())
        except Exception:
            pass


class LlamaHttpArm:
    """LlamaIndex driven over HTTP through ws1/service.py — the MATCHED-LAYER arm.

    `LlamaArm` calls the pipeline in-process: no transport, no serialization, one OS process. The
    RocketRide arm has always gone client -> WebSocket+DAP -> engine -> task process. Comparing them
    measures the topology as much as the frameworks (publishable/MATCHED_LAYERS.md). This arm gives
    LlamaIndex the same shape: separate driver, serialization boundary, server parent, out-of-process
    worker.

    The SERVICE LIFECYCLE IS THE CALLER'S, not this arm's — worker count is an experimental variable
    and the service must be restarted when it changes.

    rss() mirrors RocketArm exactly: server tree (uvicorn parent + every worker, resolved by
    LISTENING SOCKET) + this driver. Never by process name.
    """
    name = "llamaindex_http"

    def __init__(self, port: int = 8801, timeout: float = 1800.0):
        import urllib.request
        self.port, self.timeout = port, timeout
        self.base = f"http://127.0.0.1:{port}"
        self._n = 0
        sys.path.insert(0, str(ROOT / "working"))
        from harness import ws1_service as ws
        self._ws = ws
        parent, workers = ws.serving_pids(port)
        if parent is None and external_services():
            # lsof cannot see a container's fds unprivileged; docker inspect can.
            parent = container_root_pid(os.environ.get("SMOKE_LI_CONTAINER", "li"))
            if parent is not None:
                try:
                    import psutil
                    workers = [k.pid for k in psutil.Process(parent).children(recursive=True)]
                except Exception:
                    workers = []
        self.parent_pid, self.worker_pids = parent, workers
        if parent is None:
            if not external_services():
                raise RuntimeError(f"no service listening on {port} — the caller must start and "
                                   f"warm-gate it before constructing this arm")
            # External mode: the listener belongs to a container, so a host-side lsof finding
            # nothing proves nothing. Readiness was already established over HTTP by the
            # driver's warm_workers gate — two detection methods disagreeing about one port
            # in one process is what this branch exists to stop.
            print(f"[ws1] port {port}: no host-visible listener — external/container mode, "
                  "readiness came from /health warm_workers. RSS by process tree unavailable.",
                  flush=True)
        else:
            print(f"[ws1] driving parent pid={parent} with {len(workers)} worker(s) "
                  f"(matched by listening socket, not name)", flush=True)

    def process(self, text):
        import urllib.request
        self._n += 1
        body = json.dumps({"doc_id": f"d{os.getpid()}-{self._n}", "text": text}).encode()
        req = urllib.request.Request(f"{self.base}/process", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode())
        if not out.get("ok"):
            # same contract as the other arms: a fault is a result, not an exception
            return [], []
        ch = [c.get("text", "") for c in out.get("chunks", [])]
        em = [c.get("embedding") or [] for c in out.get("chunks", [])]
        return ch, em

    def rss(self):
        # Same rule as RocketArm.rss(): a container's tree is not walkable from the host, so
        # report NaN rather than a driver-only number that would read as a real measurement.
        if self.parent_pid is None:
            return float("nan") if external_services() else self._ws.tree_rss_mb(self.port)[0]
        if external_services():
            # Walk the resolved container tree directly; tree_rss_mb re-runs lsof, which
            # is the thing that cannot see it.
            return engine_tree_rss_mb(self.parent_pid) + rss_mb()
        tree, _n = self._ws.tree_rss_mb(self.port)
        return tree + rss_mb()

    def close(self):
        pass


class RocketPdfArm(RocketArm):
    """RocketRide under PARSER IN — the stock 5-node product pipeline, fed raw PDF bytes.

        webhook -> parse -> preprocessor_langchain -> embedding_transformer -> response_documents

    All five providers are STOCK. We already carry six custom nodes, which is the larger deviation
    from what a customer runs; solving Parser IN with a seventh would make that worse. Lane wiring
    (`parse` consumes `tags`, not the `data` its README documents) is copied from Leela's verified
    pipeline rather than guessed.

    Extraction happens in the engine via Tika 3.2.3 (jars in engine/java/lib, confirmed present;
    parser identity confirmed by execution — see extract_text()).
    """
    name = "rocketride_pdf"
    PIPE = "product_pdf.pipe"

    def __init__(self, tag: str = "rrpdf"):
        super().__init__(tag=tag, pipe=self.PIPE)

    def process(self, pdf_bytes: bytes):
        """Raw PDF bytes in, (chunks, embeddings) out. No driver-side extraction."""
        import asyncio
        out = self.loop.run_until_complete(
            asyncio.wait_for(self.c.send(self.tok, pdf_bytes, mimetype="application/pdf"),
                             timeout=1800))
        docs = out.get("documents") or []
        return ([d.get("page_content", "") for d in docs],
                [d.get("embedding") or [] for d in docs])


class LlamaHttpPdfArm(LlamaHttpArm):
    """LlamaIndex under PARSER IN — POSTs raw PDF bytes to /process_pdf.

    The service parses with pypdf inside the worker. Parse faults come back as `parse_failed` /
    `empty_extraction` error classes; the driver no longer classifies them, so if the service did
    not surface them the fault counts would read zero rather than move.
    """
    name = "llamaindex_http_pdf"

    def process(self, pdf_bytes: bytes):
        import urllib.request
        self._n += 1
        req = urllib.request.Request(
            f"{self.base}/process_pdf", data=pdf_bytes,
            headers={"Content-Type": "application/pdf", "X-Doc-Id": f"d{os.getpid()}-{self._n}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode())
        self.last = out
        if not out.get("ok"):
            return [], []
        return ([c.get("text", "") for c in out.get("chunks", [])],
                [c.get("embedding") or [] for c in out.get("chunks", [])])


ARMS = {"llamaindex": LlamaArm, "rocketride": RocketArm, "llamaindex_http": LlamaHttpArm,
        "rocketride_pdf": RocketPdfArm, "llamaindex_http_pdf": LlamaHttpPdfArm}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--arm", required=True, choices=list(ARMS))
    ap.add_argument("--cap-seconds", type=float, required=True)
    ap.add_argument("--limit-mb", type=float, default=12000.0)
    ap.add_argument("--target", type=int, default=10000)
    ap.add_argument("--corpus", default=str(ROOT / "corpus" / "govdocs1" / "pdfs"))
    a = ap.parse_args()

    import pypdf
    pdfs = sorted(Path(a.corpus).glob("*.pdf"))
    target = min(a.target, len(pdfs))
    ph = Phase(a.phase, a.arm, a.cap_seconds, a.limit_mb, target)
    t0 = time.time()
    prior = ph.state.get("elapsed_s", 0.0)

    print(f"[start] phase={a.phase} arm={a.arm} cap={a.cap_seconds:.0f}s "
          f"limit={a.limit_mb:.0f}MB target={target} resume_at={ph.state['next_index']}", flush=True)

    try:
        arm = ARMS[a.arm](a.phase) if a.arm == "rocketride" else ARMS[a.arm]()
    except Exception:
        traceback.print_exc()
        ph.save(status="arm_init_failed")
        return EXIT_ERR
    print(f"[warm] {a.arm} ready rss={arm.rss():.0f}MB", flush=True)

    last_hb = 0.0
    consecutive_gp = 0
    i = ph.state["next_index"]
    status = "completed"
    try:
        while i < target:
            if time.time() - t0 >= a.cap_seconds:
                status = "cap_reached"
                print(f"[cap] wall-clock cap {a.cap_seconds:.0f}s reached at doc {i}", flush=True)
                break
            f = pdfs[i]
            if time.time() - last_hb >= HEARTBEAT_EVERY:
                heartbeat(a.phase, a.arm, i, target, t0, arm.rss(),
                          f"goodput={ph.state['goodput']} STARTING {f.name}")
                last_hb = time.time()
            try:
                rd = pypdf.PdfReader(str(f))
                text = "\n".join((pg.extract_text() or "") for pg in rd.pages)
            except Exception as e:
                k = f"parse:{type(e).__name__}"
                ph.state["faults"][k] = ph.state["faults"].get(k, 0) + 1
                i += 1
                continue
            if not text.strip():
                ph.state["faults"]["empty_extraction"] = \
                    ph.state["faults"].get("empty_extraction", 0) + 1
                i += 1
                continue
            try:
                chunks, vecs = arm.process(text)
                check_document(f.name, chunks, vecs)
                ph.state["goodput"] += 1
                ph.state["chunks"] += len(chunks)
                consecutive_gp = 0
            except GoodputFailure as e:
                # A single pathological document must not end a 16-hour phase. The weekend run
                # stopped at 2.7 % of the corpus because one NUL-containing PDF tripped a fatal
                # gate. Classify and continue; abort only if failures are SYSTEMIC, which is the
                # case the gate actually exists to catch (e.g. no reader registered at all).
                ph.state["faults"][f"goodput:{str(e).split(':')[-1].strip()[:40]}"] = \
                    ph.state["faults"].get(f"goodput:{str(e).split(':')[-1].strip()[:40]}", 0) + 1
                ph.state.setdefault("goodput_failures", []).append(
                    {"index": i, "doc": f.name, "error": str(e)[:200]})
                consecutive_gp += 1
                print(f"[goodput fault] {f.name}: {str(e)[:110]}", flush=True)
                if consecutive_gp >= 25:
                    print(f"[SYSTEMIC GOODPUT FAILURE] {consecutive_gp} consecutive — aborting",
                          flush=True)
                    ph.save(status="goodput_failure_systemic", failure=str(e), next_index=i,
                            elapsed_s=prior + time.time() - t0)
                    return EXIT_ERR
                i += 1
                continue
            except Exception as e:
                k = f"{a.arm}:{type(e).__name__}"
                ph.state["faults"][k] = ph.state["faults"].get(k, 0) + 1
            i += 1

            r = arm.rss()
            ph.state["peak_rss_mb"] = max(ph.state["peak_rss_mb"], r)
            if i % RSS_SAMPLE_EVERY == 0:
                ph.state["rss_series"].append(
                    {"n": i, "t": round(time.time() - t0, 1), "rss_mb": round(r, 1)})
            # A ceiling breach is a RESULT. Record the curve and the triggering document, then
            # exit with a distinct code so the runner advances rather than dying here.
            if r > a.limit_mb:
                # always record the breaching sample: an OOM before the first periodic sample
                # would otherwise leave an empty curve, which is the data we most need.
                ph.state["rss_series"].append(
                    {"n": i, "t": round(time.time() - t0, 1), "rss_mb": round(r, 1),
                     "breach": True})
                print(f"[OOM] rss {r:.0f}MB exceeded limit {a.limit_mb:.0f}MB at doc {i} "
                      f"({f.name})", flush=True)
                ph.save(status="memory_limit_exceeded", oom_at_index=i, oom_doc=f.name,
                        oom_rss_mb=round(r, 1), next_index=i,
                        elapsed_s=prior + time.time() - t0)
                write_result(f"weekend_{a.phase}_{a.arm}_OOM", ph.state)
                return EXIT_OOM
            if i % CHECKPOINT_EVERY == 0:
                ph.save(next_index=i, elapsed_s=prior + time.time() - t0, status="running")
                gc.collect()
                print(f"[ckpt] n={i} goodput={ph.state['goodput']} rss={r:.0f}MB "
                      f"peak={ph.state['peak_rss_mb']:.0f}MB "
                      f"faults={sum(ph.state['faults'].values())}", flush=True)
            if time.time() - last_hb >= HEARTBEAT_EVERY:
                heartbeat(a.phase, a.arm, i, target, t0, r,
                          f"goodput={ph.state['goodput']} peak={ph.state['peak_rss_mb']:.0f}MB")
                last_hb = time.time()
    except MemoryError:
        print("[OOM] MemoryError", flush=True)
        ph.save(status="memory_error", next_index=i, elapsed_s=prior + time.time() - t0)
        write_result(f"weekend_{a.phase}_{a.arm}_OOM", ph.state)
        return EXIT_OOM
    except KeyboardInterrupt:
        ph.save(next_index=i, elapsed_s=prior + time.time() - t0, status="interrupted")
        return EXIT_CAP
    finally:
        try:
            arm.close()
        except Exception:
            pass

    ph.save(next_index=i, elapsed_s=prior + time.time() - t0, status=status)
    p = write_result(f"weekend_{a.phase}_{a.arm}", ph.state)
    print(f"[done] {status} n={i} goodput={ph.state['goodput']} "
          f"peak={ph.state['peak_rss_mb']:.0f}MB -> {p.name}", flush=True)
    return EXIT_CAP if status == "cap_reached" else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
