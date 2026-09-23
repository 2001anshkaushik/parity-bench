#!/usr/bin/env python3
"""P0 H5/H6: run ONE parser over a document list with W line-protocol workers, timing each parse.

    p0_parse_bench.py --parser tika --config <cfg.xml> --docs <slice.json|names.txt|a,b,c>
                      --label <phase> --out <results_dir> [--workers W] [--timeout S] [--fresh]
                      [--warmup-doc NAME] [--reps N]
    p0_parse_bench.py --parser pypdf|pypdfium2 ... (same)

One parser per invocation = one PHASE (the pre-registration's "one parser phase at a time, the
same worker count for every parser"). Workers:
  tika       the engine's own JRE and Tika jars INSIDE rr:patched (entrypoint replaced by the
             bundled java; the image is only read), running working/tika/TikaBatch compiled
             against those jars. --fresh starts one JVM per document and parses --warmup-doc
             first, so a cold JIT is never what a document is timed against (H5).
  pypdf / pypdfium2   working/scripts/p0_parse_worker.py under ~/p0venv.
A document still unanswered after --timeout seconds is recorded as a TIMEOUT, its worker is
killed and a fresh one takes the next document. Per document the record holds the parse's own
wall and CPU seconds (measured inside the worker), and the text's length in Unicode code points
and after stripping whitespace, read back from the text file by THIS script for every parser.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
P0VENV_PY = Path(os.environ.get("P0_PARSE_PY", str(Path.home() / "p0venv" / "bin" / "python")))
BUILD = Path(os.environ.get("P0_TIKA_BUILD", str(Path.home() / "p0_build")))
TEXTS = Path(os.environ.get("P0_TEXTS", str(Path.home() / "p0_texts")))
JAVA = "/opt/rocketride/engine/java/jre/bin/java"
JARS = "/opt/rocketride/engine/java/lib/*"
IMAGE = os.environ.get("P0_TIKA_IMAGE", "rr:patched")


def doc_names(spec: str) -> List[str]:
    p = Path(spec)
    if p.suffix == ".json" and p.is_file():
        return list(json.loads(p.read_text())["measured"])
    if p.is_file():
        return [x.strip() for x in p.read_text().splitlines() if x.strip()]
    return [x.strip() for x in spec.split(",") if x.strip()]


class Worker:
    def __init__(self, parser: str, corpus: Path, text_dir: Path, config: Optional[Path],
                 label: str, wid: int, jvm_heap: str):
        self.parser, self.corpus, self.text_dir, self.config = parser, corpus, text_dir, config
        self.label, self.wid, self.heap = label, wid, jvm_heap
        self.proc: Optional[subprocess.Popen] = None
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.name: Optional[str] = None
        self.ready: Dict[str, Any] = {}

    def _reader(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            self.lines.put(line)
        self.lines.put("")                                 # EOF marker

    def start(self) -> None:
        self.lines = queue.Queue()
        if self.parser == "tika":
            self.name = f"p0parse_{self.label}_{self.wid}_{uuid.uuid4().hex[:6]}"
            cmd = ["docker", "run", "-i", "--rm", "--name", self.name, "--memory", "16g",
                   "-v", f"{self.corpus}:/corpus:ro", "-v", f"{BUILD}:/work:ro",
                   "-v", f"{self.text_dir}:/out", "--entrypoint", JAVA, IMAGE,
                   f"-Xmx{self.heap}", "-cp", f"/work:{JARS}", "TikaBatch",
                   f"/work/cfg/{self.config.name}", "/out"]
        else:
            cmd = [str(P0VENV_PY), str(ROOT / "working" / "scripts" / "p0_parse_worker.py"),
                   self.parser, str(self.text_dir)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        first = self._next(300)
        if not first or '"ready"' not in first:
            self.kill()
            raise RuntimeError(f"worker {self.wid} did not become ready: {first!r}")
        self.ready = json.loads(first)

    def _next(self, timeout: float) -> Optional[str]:
        try:
            return self.lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def path_for(self, name: str) -> str:
        return f"/corpus/{name}" if self.parser == "tika" else str(self.corpus / name)

    def run(self, name: str, timeout: float) -> Dict[str, Any]:
        t_start = time.time()
        self.proc.stdin.write(self.path_for(name) + "\n")
        self.proc.stdin.flush()
        noise = []
        while True:
            line = self._next(max(1.0, timeout - (time.time() - t_start)))
            if line is None:
                self.kill()
                return {"doc": name, "timeout": True, "timeout_s": timeout, "t_start": t_start,
                        "t_end": time.time(), "stdout_noise": noise[:5]}
            if line == "":
                self.kill()
                return {"doc": name, "error": "worker died (EOF)", "t_start": t_start,
                        "t_end": time.time(), "stdout_noise": noise[:5]}
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                noise.append(line[:200])              # not the protocol: recorded, skipped
                continue
            if isinstance(rec, dict) and rec.get("doc") == name:
                break
            noise.append(line[:200])
        rec.update(t_start=t_start, t_end=time.time())
        if noise:
            rec["stdout_noise"] = noise[:5]
        return rec

    def kill(self) -> None:
        if self.parser == "tika" and self.name:
            subprocess.run(["docker", "kill", self.name], capture_output=True)
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=60)
            except Exception:
                self.kill()
        self.proc = None


def text_facts(text_dir: Path, name: str) -> Dict[str, Any]:
    f = text_dir / f"{name}.txt"
    if not f.exists():
        return {"chars": None, "stripped_chars": None}
    t = f.read_text(encoding="utf-8", errors="replace")
    return {"chars": len(t), "stripped_chars": len(t.strip())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", required=True, choices=("tika", "pypdf", "pypdfium2"))
    ap.add_argument("--config", type=Path, help="tika: a config file under $P0_TIKA_BUILD/cfg/")
    ap.add_argument("--docs", required=True)
    ap.add_argument("--corpus", type=Path, default=Path(os.environ.get(
        "BSZ_CORPUS_DIR", str(Path.home() / "parity-bench" / "corpus" / "govdocs1" / "pdfs"))))
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--warmup-doc", default=None)
    ap.add_argument("--jvm-heap", default="4g")   # 12 workers x 4g stays under the 61 GiB box
    ap.add_argument("--jobs", type=Path, default=None,
                    help="H5: a JSONL of {doc, config, label} jobs run in ONE pool (requires "
                         "--fresh); each job's text goes to $P0_TEXTS/<its label>/")
    a = ap.parse_args()
    if a.jobs:
        if not a.fresh or a.parser != "tika":
            raise SystemExit("REFUSED: --jobs is the H5 mixed-config mode: tika with --fresh only")
        job_list = [json.loads(x) for x in a.jobs.read_text().splitlines() if x.strip()]
    else:
        if a.parser == "tika" and (a.config is None or not (BUILD / "cfg" / a.config.name).is_file()):
            raise SystemExit(f"REFUSED: tika needs --config naming a file in {BUILD}/cfg/")
        job_list = [{"doc": n, "config": a.config.name if a.config else None, "label": a.label}
                    for n in doc_names(a.docs)]
    for j in job_list:
        if a.parser == "tika" and not (BUILD / "cfg" / j["config"]).is_file():
            raise SystemExit(f"REFUSED: config {j['config']} is not in {BUILD}/cfg/")
    names = [j["doc"] for j in job_list]
    missing = [n for n in names if not (a.corpus / n).is_file()]
    if missing:
        raise SystemExit(f"REFUSED: {len(missing)} documents missing from {a.corpus}: {missing[:5]}")
    a.out.mkdir(parents=True, exist_ok=True)
    res_f = a.out / f"results_{a.label}.jsonl"
    if res_f.exists():
        raise SystemExit(f"REFUSED: {res_f} exists (append-only)")
    for lab in sorted({j["label"] for j in job_list}):
        td = TEXTS / lab
        if td.exists() and any(td.iterdir()):
            raise SystemExit(f"REFUSED: text dir {td} is not empty")
        td.mkdir(parents=True, exist_ok=True)
        os.chmod(td, 0o777)                       # the engine image's user writes here
    text_dir = TEXTS / a.label
    jobs: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    for j in job_list:                            # in the order given: the caller decides it
        jobs.put(j)
    lock = threading.Lock()
    meta: Dict[str, Any] = {"versions": {}}
    t_phase0 = time.time()

    def loop(wid: int) -> None:
        w = Worker(a.parser, a.corpus, text_dir, a.config, a.label, wid, a.jvm_heap)
        started = False
        while True:
            try:
                job = jobs.get_nowait()
            except queue.Empty:
                break
            name = job["doc"]
            if a.fresh:                               # one JVM per job, with the job's own config
                w = Worker(a.parser, a.corpus, TEXTS / job["label"],
                           (BUILD / "cfg" / job["config"]) if job.get("config") else None,
                           job["label"], wid, a.jvm_heap)
            rec = None
            for attempt in range(3):                 # a worker that cannot start is retried
                try:
                    if not started or w.proc is None:
                        w.start()
                        started = True
                        meta["versions"][str(wid)] = w.ready
                        if a.warmup_doc:              # every worker start, restarts included
                            wu = w.run(a.warmup_doc, a.timeout)
                            with lock:
                                meta.setdefault("warmups", []).append({**wu, "worker": wid})
                    break
                except Exception as e:
                    rec = {"doc": name, "error": f"worker start (attempt {attempt + 1}): {type(e).__name__}: {e}"}
                    w.kill()
                    started = False
            else:
                pass
            if w.proc is not None:
                try:
                    rec = w.run(name, a.timeout)
                except Exception as e:
                    rec = {"doc": name, "error": f"parse call: {type(e).__name__}: {e}"}
                    w.kill()
            rec.update(parser=a.parser, label=job["label"], worker=wid, config=job.get("config"),
                       rep=job.get("rep"),
                       **(text_facts(TEXTS / job["label"], name)
                          if not rec.get("timeout") and not rec.get("error")
                          else {"chars": None, "stripped_chars": None}))
            with lock:
                with open(res_f, "a") as f:
                    f.write(json.dumps(rec) + "\n")
            if a.fresh:
                w.stop()
                started = False
        w.stop()

    ths = [threading.Thread(target=loop, args=(i,), daemon=True) for i in range(a.workers)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    rows = [json.loads(x) for x in res_f.read_text().splitlines() if x.strip()]
    summary = {"parser": a.parser, "label": a.label, "config": a.config.name if a.config else None,
               "jobs_file": str(a.jobs) if a.jobs else None,
               "docs": len(names), "records": len(rows), "workers": a.workers,
               "timeout_s": a.timeout, "fresh_jvm_per_doc": a.fresh, "warmup_doc": a.warmup_doc,
               "timeouts": sorted(r["doc"] for r in rows if r.get("timeout")),
               "errors": {r["doc"]: r["error"] for r in rows if r.get("error")},
               "empty": sorted(r["doc"] for r in rows
                               if r.get("timeout") or r.get("error") or not r.get("stripped_chars")),
               "phase_wall_s": round(time.time() - t_phase0, 3),
               "worker_versions": meta["versions"], "warmups": meta.get("warmups"),
               "host_cpus": os.cpu_count(), "image": IMAGE if a.parser == "tika" else None}
    (a.out / f"summary_{a.label}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("parser", "label", "docs", "records", "phase_wall_s")}
                     | {"timeouts": len(summary["timeouts"]), "errors": len(summary["errors"]),
                        "empty": len(summary["empty"])}))
    return 0 if len(rows) == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
