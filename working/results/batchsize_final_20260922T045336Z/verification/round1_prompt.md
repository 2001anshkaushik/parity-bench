You are an independent verifier with no context about this project beyond this message. Your job: recompute every figure in named sections of a Markdown report from raw measurement files, and report every figure that does not match. Trust no number in the report.

RULES
- Read ONLY the files listed below. Do NOT open any file whose name starts with `analysis_`, any `*summary*.json`, anything under `working/scripts/`, or any other file in the repository. Recompute; do not look up.
- Do not modify, move or delete any file. Use Python (the interpreter at /Users/ansh/RocketRide/Benchmarking/.venv/bin/python) for the arithmetic.
- A figure MATCHES when your recomputed value, rounded exactly as the report displays it (same decimals, same percent formatting, thousands separators ignored), equals the report's value. Anything else is a MISMATCH — report it with both values.
- Write your findings as JSON to /private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify/verifier_findings.json and finish with a short plain-text summary: how many figures you checked, and every mismatch.

THE REPORT: /private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify/REPORT_UNDER_TEST.md
Verify every figure in these sections: "## 0. Answers" (except the "Stage 5, segregated" bullet list), "## 1. Headline …", "### Empty-content documents, both arms (C5)", "## 2. Batch size at full scale …" (both arm tables — skip the "Peak engine anon" column and the collapsed per-batch lists — plus the "K=1,024, stated plainly" paragraph and the "Where 039_039660.pdf sat" table), and "## 3. AMI video at full scale …". Skip memory figures everywhere.

FILES (paths relative to /Users/ansh/RocketRide/Benchmarking/benchmark-A)
Docs legs, 9,975 PDFs each. Each directory holds, for its leg name L: leg_<arm>_L.json (the driver's export for the leg: blocks cost, documents, throughput, percore_host) and perdoc_<arm>_L.jsonl (one row per document: doc, ok, reason, submit_ns, completion_ns, batch) and percore_<arm>_L.jsonl (host per-core samples over the leg's measured window: t = wall-clock seconds, busy = a mapping from core id to that core's busy fraction).
- working/results/batchsize_s4_20260921T013303Z/p1_rr_cont32/ — RocketRide, continuous C=32, L = refc32_main
- working/results/batchsize_s4_20260921T013303Z/p2_li_cont/ — LlamaIndex, continuous C=32 (L = refc32_main) and C=16 (L = refc16_main)
- working/results/batchsize_s4_20260921T013303Z/p3_rr_k128/ (L = k128_main), p4_li_k128/ (k128_main)
- working/results/batchsize_s4_20260921T013303Z/e7_rr_k256/ (k256_env), e8_li_k256/ (k256_env), e9_rr_k512/ (k512_env), e10_li_k512/ (k512_env), e11_rr_k1024/ (k1024_env), e12b_li_k1024/ (k1024_env)
Video legs, 168 AMI videos. Each directory holds records_*.jsonl (one row per video: role, frames_observed, and an `error` key if it failed) and export_*.json (the driver's export: throughput.total_frames, throughput.total_span_s, throughput.total_frames_per_s; efficiency.effective_cores, efficiency.cpu_util_of_box) and percore.jsonl.
- working/results/batchsize_s4_20260921T013303Z/p5_li_video/li_k16/ — LlamaIndex
- working/results/batchsize_s4_20260921T013303Z/p6_rr_video/rr_k16/ — RocketRide (the report gives its frames/s as a ranking only; verify the ranking)
Per-unit anchor, 96 PDFs: working/results/batchsize_s3b_20260920T203139Z/anchor_rr/ and anchor_li/ (L = refc1_anchor and refc8_anchor).

DEFINITIONS (the report's methodology)
- Span docs/s = (rows with ok true) / ((max completion_ns − min submit_ns) / 1e9), over all rows of the leg.
- "Span with 039_039660.pdf dropped from BOTH arms" = the same computed with that document's row removed.
- docs/s to the 99th-percentile completion = sort the ok rows by completion_ns; k = int(0.99 × number of ok rows); k / ((completion_ns of the k-th ok row, 1-based − min submit_ns over all rows) / 1e9).
- "Document that set the span (held)" = the row with the largest completion_ns; held = its completion_ns − submit_ns, in seconds.
- Host busy cores = the mean, over every sample in the leg's percore file (the sampler runs over the measured window only), of the sum of the busy mapping's values; idle core-equivalents = 32 − host busy cores. Cross-check against the leg JSON's percore_host block, and report both if they differ.
- Engine container cores, driver cores, CPU utilisation (engine cores / 32), idle spin and CPU-seconds per document are the driver's own measurements in the leg JSON's cost block (idle spin: cost.idle_spin_measured.cores). Verify the report quotes each field correctly.
- Documents: completed = ok true; content outcome = reason in {no_documents, empty_extraction, parse_failed}; lost to the deadline = reason ending in TimeoutError; other failure = anything else not ok. Returned = completed + content outcome; lost = deadline + other; the docs/s numerator = completed.
- Empty-content counts (C5) = per arm, the documents with a content outcome in that arm's continuous C=32 leg; "empty on LlamaIndex only" = in LlamaIndex's set and not RocketRide's (and the reverse).
- Batched legs: batches = the number of distinct batch values; a batch's wall = max completion_ns − min submit_ns over that batch's rows; median / max over batches; the batch holding 039_039660.pdf, its wall, and "spare" = 1800 − that wall; "That batch's share of the span" = that wall / the leg's span (max completion − min submit over all rows); a batch died if its rows carry reason batch_error:TimeoutError.
- "Sent at" = the 1-based rank of 039_039660.pdf when the leg's rows are sorted by (submit_ns, doc).
- Answers section: "Even the best batch reaches only X of the continuous rate" = (best batched span docs/s) / (continuous C=32 span docs/s), per arm; "seconds to spare … by K" = 1800 − the wall of the batch holding 039_039660.pdf; per unit, "grows N x" = (anchor C=8 span docs/s) / (anchor C=1 span docs/s), per arm.
- Video: recompute total frames as the sum of frames_observed over records with role "measured" and no `error` key, confirm it equals throughput.total_frames, and recompute frames/s = total_frames / throughput.total_span_s. Idle core-equivalents for video = 32 − the mean of sum(busy values) over the percore samples whose t lies inside the leg's measured window (the video sampler also runs before and after the leg; keep only samples whose mono_ns lies in [min admit_ns, max done_ns] taken over the records with role "measured" — both clocks are CLOCK_MONOTONIC). Videos/errors from the records.

OUTPUT (JSON at /private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify/verifier_findings.json): {"figures_checked": N, "results": [{"section", "figure", "reported", "recomputed", "match", "note"}], "mismatches": [...]}.
