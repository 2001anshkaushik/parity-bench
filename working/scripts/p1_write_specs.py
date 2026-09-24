import json, sys
from pathlib import Path
D = Path(sys.argv[1])
roi = {"items": [
  {"bottleneck": "the docs parse tail: the engine's Tika wrapper extracted every PDF inline image and probed external tools per image",
   "fix": "DONE in P1-B (rr:p1-tikafix): TikaApi.getPdfConfig code byte 9 iconst_1 -> iconst_0 (setExtractInlineImages off; PATCH) and two parser-exclude lines in tika-config.xml (CONFIG); output-neutral on the 384 slice (the gate) and chunk-identical over the full corpus (context). Ready to ship as a wrapper change",
   "scope": "PATCH", "share_key": "docs_base:parse_bracket", "evidence": "P1-B correctness, smoke, 384 ABAB and full runs"},
  {"bottleneck": "per-document embedding (MiniLM) — after the wrapper fix, nearly all of document time",
   "fix": "encode the chunks of several in-flight documents in one call inside the one model instance; output effect to be verified (batch composition can move floats)",
   "scope": "PYTHON", "share_key": "docs_fixed:embed", "evidence": "P1-B fixed legs' D1 stage shares"},
  {"bottleneck": "response path: vectors serialised as JSON text on the websocket", "fix": "binary vector encoding on the response lane",
   "scope": "PYTHON", "share_key": "docs_fixed:return", "evidence": "P1-B fixed legs' D1 stage shares"},
  {"bottleneck": "video: RocketRide's T=4 forward pass is slower than LlamaIndex's at identical libraries and pool settings; its calling thread is on-CPU for less of it",
   "fix": "not yet named: E2's pre-registered readings are unreadable (the tracer failed its null control). Candidates for P2, from E2's read-backs: the attached debugger (pydevd as sys.monitoring tool 0, RocketRide only), the per-frame device lock rotating forward calls across 16 pipe threads each with its own OpenMP pool, MALLOC_ARENA_MAX=2 (LlamaIndex only), the task process's thread count. Scope THREADING is provisional",
   "scope": "THREADING", "evidence": "E2 OFF legs (forward times, caller CPU ratio) and read-backs"}],
 "out_of_bounds": ["a second token, more task processes, model or engine pools, the model-server mode (unchanged from P0)"],
 "not_run": [
  "P1-C's native-parser question: the prototype's pypdfium2 never ran (the image lacked pypdfium2's top-level pypdfium2_cfg module; the build's own check failed with rc 8 and my master did not gate on it). Needs: the module added (install the wheel into the engine's site-packages), the counters checked after the first leg, then the pre-registered P1-C design (about 1.5 h of box time)",
  "P1-D's LlamaIndex 168-video leg: the chain's per-leg budget check found the 11-hour budget passed; the gap is not computed. Needs about 2 h of box time plus a RocketRide leg in the same session",
  "E2's tracer-ON readings (GIL wait in forward, run-queue wait, busy OpenMP workers): unreadable because the tracer itself cost about 6% on both arms (null control failed). Needs a lighter instrument (for example bpftrace off-CPU accounting only for the forward-calling threads) and its own null control",
  "memory samples for p1b_base_a and p1b_fix_a: the runner's sampler never ran on them (register 55); later docs legs are covered by the outside watcher",
  "rr:p1-pdfium's build record (p1c_build.json): the build script stopped at its failed in-image check before writing it; the image id is in chain_p1c_done.json"],
 "register": ["53 — the tracer that could not stop (per-CPU preallocated maps), and a repeat of entry 50 (sudo in a one-shot run)",
              "54 — the build check that failed and the orchestration that did not listen (P1-C)",
              "55 — the sampler with nowhere to write, and the DEGRADED leg retried twice"]}
(D / "p1_roi_spec.json").write_text(json.dumps(roi, indent=1) + "\n")
summ = {"readings": {
  "E2": "UNREADABLE by the pre-registered null control (the tracer's own cost); untraced, RocketRide's forward pass is slower at identical pool settings and its calling thread is on-CPU for less of it",
  "E2_detail": "The tracer-ON figures below are DIAGNOSTIC context only: they carry no reading.",
  "E2_cause": "Not established. The pre-registered readings (GIL contention, pool or affinity configuration, CPU contention) needed the traced legs, and the tracer's own cost failed the null control on both arms, so none is supported or refuted. What the untraced legs establish: at T=4 with identical torch, OpenMP and MKL settings and identical affinity, RocketRide's forward pass is slower per frame, and its calling thread is on-CPU for a smaller share of that pass (see P1-A). The read-backs differ only outside the pool fields: the debugger is attached in RocketRide's task process, LlamaIndex sets MALLOC_ARENA_MAX=2, and RocketRide's process runs many more threads. Those are P2's candidates.",
  "P1B": "the pathological holds are the wrapper's inline-image extraction and per-image tool probing; turning both off leaves the text lane unchanged and removes the tail",
  "P1C": "the question was not answered: the prototype's parser never ran; the hybrid's replay path gave fixed Tika's output, chunk-identical over the full corpus",
  "P1D": "only the RocketRide arm ran (deterministic against P0 on the shared videos); the gap needs the LlamaIndex leg"},
 "recommendation": "Ship P1-B's wrapper fix: it is output-neutral on the gate slice and chunk-identical over the full corpus, and it more than doubles full-corpus docs/s at lower CPU per document. P1-C cannot be recommended or rejected: its prototype never parsed a document. Its wiring is proven: with the node producing no text, every document still came out through the fixed Tika, chunk-identical over the full corpus, at no readable cost. P2 can therefore test pypdfium2 with only the missing module added.",
 "self_audit": {
  "1. HYPOTHESIS": "stated before the first leg in preregistration.json (P1-A E2, P1-B, P1-C, P1-D) and amendment 1 (the tracer's maps and GIL buckets, before any measured leg).",
  "2. EVIDENCE": "every figure in this report is computed by working/scripts/p1_report.py from analysis_e2.json, analysis_p1docs.json and analysis_v1full168.json, produced by committed analysers from the raw leg directories beside them (large files as lossless gzip copies, originals in S3 — E2_FILES_NOTE.md, P1_FILES_NOTE.md); the build and gate records are p1b_build.json, p1b_correctness.json and p1b_smoke_gate.json; the chain logs are in box_logs/.",
  "3. NULL CONTROL": "E2: tracer ON vs OFF, per arm, had to agree within the floor with identical output — it FAILED on both arms (output identical, throughput not), and the ON-leg readings are withdrawn as readings. P1-B: the 384-slice chunk identity had to hold (it did). The blind recomputation's planted figures had to be caught (see P1_BLIND_VERIFICATION.json).",
  "4. REGISTER": "2 (self-consistency: E2's null control crosses the tracer boundary and failed); 3 (conditions: one box session, boot e293381c, for every P1 leg); 34 (a pre-registration refuted or left unreadable on its own terms: E2); 48 (blind recomputation); 49 (a read-back must not become part of the measurement: the E2 read-back runs once per process); 50, 53 (sudo in a one-shot run, again); 54 (the build check nobody listened to); 55 (the sampler with nowhere to write; the DEGRADED leg retried).",
  "5. NOT VERIFIED": "why RocketRide's forward pass waits (E2 unreadable); pypdfium2 inside the engine (P1-C never ran it); the 168-video gap (LlamaIndex leg not run); memory on P1-B's first pair; that the full-corpus chunk identity would hold for other corpora; the texts of the full runs are in S3 only and were not re-read for this report (P1-B's full-corpus identity is by chunk hash).",
  "6. GATES": "every P1 landing went through working/harness/autoland.sh with its gates and the ls-remote read-back; box commands through box.sh; the box was stopped by the operator at 08:18Z, started by me at about 15:18Z for two minutes to upload the watcher's files and logs, and stopped again with box.sh stop, read back as stopped at 15:20:49Z. This session was idle from about 00:00Z to 15:16Z (no monitoring in that time); the chains ran by themselves as designed."}}
(D / "p1_summary_spec.json").write_text(json.dumps(summ, indent=1) + "\n")
print("specs written")
