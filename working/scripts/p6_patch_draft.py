#!/usr/bin/env python3
"""P6-D (2) UPSTREAM PATCH DESCRIPTION DRAFT for the single inference thread. Every figure is read from committed files
(analysis_p6.json, the P5 analysis and build record, the node sources); the diff summary is computed from the files.
Draft only: not filed, posted or sent.

    p6_patch_draft.py <p6_campaign_dir>  -> P6_UPSTREAM_PATCH_DRAFT.md
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "working" / "nodes" / "p5_infer_src"
BASE = ROOT / "engine" / "nodes" / "detect"          # the local 3.3.1.35 bundle (gitignored); md5s checked against the image
P5 = ROOT / "working" / "results" / "parity_p5_20260925T141647Z"


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def diffstat(a: Path, b: Path):
    x, y = a.read_text().splitlines(), b.read_text().splitlines()
    plus = minus = 0
    for ln in difflib.unified_diff(x, y, lineterm=""):
        if ln.startswith("+") and not ln.startswith("+++"):
            plus += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            minus += 1
    return plus, minus


def main() -> int:
    camp = Path(sys.argv[1])
    A6 = json.loads((camp / "analysis_p6.json").read_text())
    a, b = A6["P6_A"], A6.get("P6_B")
    p5a = json.loads((P5 / "analysis_p5a.json").read_text())
    build = json.loads((P5 / "p5a_build.json").read_text())
    C = a["cells"]
    d = a.get("descriptive_forward_degradation") or {}
    stats = {f: diffstat(BASE / f, SRC / f) for f in ("IGlobal.py", "IInstance.py")} if BASE.exists() else {}
    worker_lines = len((SRC / "infer_worker.py").read_text().splitlines())
    base_img = {x.split()[1]: x.split()[0] for x in build["base_node"] if not x.startswith("UNKNOWN")}
    m = lambda cell, k: C[cell][k]["mean"]  # noqa: E731
    L = ["# DRAFT — upstream patch description: a single inference thread for the detect node (not filed, posted or sent)", "",
         "## What changed", "",
         f"- `nodes/detect/IGlobal.py` (+{stats.get('IGlobal.py', ('?', '?'))[0]} / -{stats.get('IGlobal.py', ('?', '?'))[1]} lines): after building the one "
         "`Detector`, it starts an `InferenceWorker` (one daemon thread, one bounded FIFO queue, `RR_DETECT_QUEUE_MAX`, default 64) instead of "
         "`make_device_lock()`; `endGlobal` stops the worker before disconnecting the detector.",
         f"- `nodes/detect/IInstance.py` (+{stats.get('IInstance.py', ('?', '?'))[0]} / -{stats.get('IInstance.py', ('?', '?'))[1]} lines): "
         "`with self.IGlobal.device_lock: detections = self.IGlobal.detector.detect(image)` becomes "
         "`detections = self.IGlobal.infer.detect(image, timeout=600)`; decode and emit stay on the caller.",
         f"- `nodes/detect/infer_worker.py` (new, {worker_lines} lines): `InferenceWorker.submit/detect/close`. Each caller has at most one frame "
         "outstanding and blocks on its own `Future`, so a video's frames stay in order and each result returns to its caller without a "
         "routing table; a detect exception reaches its own caller's existing `except` branch; a full queue blocks the submitter.",
         f"- Base files: IInstance.py md5 {md5(BASE / 'IInstance.py') if BASE.exists() else '—'}, IGlobal.py md5 "
         f"{md5(BASE / 'IGlobal.py') if BASE.exists() else '—'} — "
         + ("equal to the image's own node files [parity_p5_20260925T141647Z/p5a_build.json base_node]" if BASE.exists() and base_img == {f: md5(BASE / f) for f in base_img} else "NOT checked against the image's node files")
         + " (the local engine bundle, 3.3.1.35 per parity_p5_20260925T141647Z/PROGRESS_LOG.md:5; the line counts above are against that bundle, which is not in the repository). Patched: "
         + ", ".join(f"{k} {v}" for k, v in build["expected_p5_md5"].items()) + ".",
         "", "## Output identity", "",
         f"- P5 (parity_p5_20260925T141647Z): identical to stock (per-video chunk sha256 AND frame scores) on 16/16 videos in every comparison, "
         f"at K=16 and K=1, both rounds, and against an earlier session's stock K=1 leg [analysis_p5a.json correctness.gate_pass = {p5a['correctness']['gate_pass']}].",
         f"- P6: identical to stock on 16/16 in both rounds [analysis_p6.json P6_A.correctness.gate_pass = {a['correctness']['gate_pass']}]"
         + (f"; on the 168-video slice, {b['correctness_vs_p1d']['identical']} of {b['correctness_vs_p1d']['videos_compared']} videos identical to a banked stock run "
            "from another session [P6_B.correctness_vs_p1d]" + (": " + ", ".join(x["video"] for x in b["correctness_vs_p1d"]["differ"])
            + " differ (chunk hashes and frame scores); whether the patch or run-to-run variation in stock causes it is NOT established — "
              "stock was never replicated on those videos (register 65)." if b["correctness_vs_p1d"]["differ"] else ".") if b else
            "; the 168-video confirmation did not run (see the P6 report)."),
         "", "## Mandate compliance", "",
         "- One engine process, one pipeline, ONE model instance: the worker calls the same `IGlobal.detector` object; the on-token D0 read "
         "exactly one LWDETR before and after every measured leg (P5, P6 gate records G_d0).",
         "- Threads only: one extra thread (`detect-infer`) per task process.",
         "", "## Measured effect (16 AMI videos, 16 in flight, T=4, one session, ABAB)", "",
         f"- Frames/s: {m('p5_k16', 'frames_per_s'):.3f} vs stock {m('stock_k16', 'frames_per_s'):.3f} "
         f"({m('p5_k16', 'frames_per_s') / m('stock_k16', 'frames_per_s') - 1:+.1%}) [P6_A.cells.*.frames_per_s.mean]; one LlamaIndex instance "
         f"{m('li_k16', 'frames_per_s'):.3f}.",
         f"- CPU-s per frame: {m('p5_k16', 'cpu_s_per_frame'):.3f} vs stock {m('stock_k16', 'cpu_s_per_frame'):.3f} "
         f"({m('p5_k16', 'cpu_s_per_frame') / m('stock_k16', 'cpu_s_per_frame') - 1:+.1%}) [P6_A.cells.*.cpu_s_per_frame.mean].",
         f"- Sampled memory peak: {m('p5_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB vs stock {m('stock_k16', 'memory_peak_total_bytes') / 1e6:,.0f} MB "
         "[P6_A.cells.*.memory_peak_total_bytes.mean].",
         f"- The inference thread is busy {m('p5_k16', 'duty'):.2%} of the window [P6_A.cells.p5_k16.duty.mean]: it is now the bottleneck.",
         "", "## Known residual", "",
         (f"- With 16 videos in flight the forward pass is {d['F_over_ref_minus_1']:+.1%} longer than with one (mean; median "
          f"{d['p50_over_ref_minus_1']:+.1%}, p99 {d['p99_over_ref_minus_1']:+.1%}) [P6_A.descriptive_forward_degradation; the one-video reference is P5's "
          "session] — a tail of slow forwards while the other callers decode; its cause was not measured." if d else "- Not measured in P6."),
         "", "## What a reviewer should test", "",
         "- Output identity against the current node on your own video set at the same thread count, at 1 and at many videos in flight — "
         "and, first, the current node against ITSELF on the same set (two runs), so a mismatch can be attributed"
         + (f"; start with {', '.join(x['video'] for x in b['correctness_vs_p1d']['differ'])}, which differed here." if b and b["correctness_vs_p1d"]["differ"] else "."),
         "- Teardown: a pipeline stopped with frames queued ends cleanly (the worker fails pending frames and `endGlobal` returns).",
         "- Errors: a frame whose detect raises is dropped with the existing warning and the next frame is served.",
         "- Model-server (proxy) mode: `make_device_lock()` returned a no-op there; the worker still serialises calls — check throughput in that mode.",
         "- Very high concurrency: the queue bound (`RR_DETECT_QUEUE_MAX`) and memory (one decoded frame per waiting caller).",
         "- Other nodes or code that used `IGlobal.device_lock` (none in the detect node itself)."]
    (camp / "P6_UPSTREAM_PATCH_DRAFT.md").write_text("\n".join(L) + "\n")
    print(f"wrote P6_UPSTREAM_PATCH_DRAFT.md ({len(L)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
