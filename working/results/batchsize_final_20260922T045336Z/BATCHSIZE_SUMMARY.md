# Batch-size optimisation — RocketRide at one token and LlamaIndex, GovDocs PDFs and AMI video

Generated 2026-09-22T05:05:13Z by `working/scripts/batchsize_final_report.py` from committed analysis artifacts; every table names its source, and `batchsize_final_summary.json` records each input's sha256. Box: one c7i.8xlarge, 32 vCPUs, one workload at a time.

Supersedes `working/results/batchsize_final_20260922T023454Z` — every figure identical: **False**; the figure groups that differ, computed from the two JSON twins: `fd_note`, `provenance_s3b`, `stage4_docs_headline`, `stage4_envelope`, `stage5`, `straggler_order`.

## 0. Answers

**Optimal batch size, GovDocs PDFs.** No batch size beats continuous submission on either arm: sending each document as soon as a slot frees was faster than every batch size at full scale. Within batch mode, throughput rises with K on both arms (RocketRide K=128: 0.9643 †, K=256: 1.1952 †, K=512: 1.392 †, K=1024: 1.5142 †; LlamaIndex K=128: 1.9264, K=256: 2.4591, K=512: 3.0463, K=1024: 3.8639) — consistent with the pre-registered hypothesis that each batch barrier costs a wait for that batch's slowest document, so fewer barriers approach the continuous rate. Even the best batch reaches only 0.647 of RocketRide's continuous rate † and 0.758 of LlamaIndex's.

**The cost of large batches.** The batch holding `039_039660.pdf` had this many seconds to spare against the 1,800 s batch deadline, by K — RocketRide: K=128: 93.2, K=256: 51.9, K=512: 45.6, K=1024: died at the deadline †; LlamaIndex: K=128: 1761.2, K=256: 1694.7, K=512: 1698.8, K=1024: 1558.7. **RocketRide K=1024 lost 1 batch(es) to the deadline — 759 documents — reported as blast radius, never re-run.** Engine anon memory at each leg's close, across K: RocketRide 10.2 GiB to 11.7 GiB; LlamaIndex 15.8 GiB to 16.0 GiB; total high-water `memory.peak`: RocketRide 21.6 GiB to 23.0 GiB; LlamaIndex 16.9 GiB to 17.2 GiB — peak anon lies between the two (§2).

**Optimal "batch", AMI video.** Neither arm has a frame-batch knob. The only lever, videos in flight, was set to K=16 for both arms from the 16-video smoke slice (§5); RocketRide at one token moved 9.17% from K=1 to K=16, inside its own K=16 replicate spread of 9.76%.

**Best to best, full scale, each arm at its own optimum** (§1, §3). Not a per-unit comparison — one RocketRide token against 24 LlamaIndex workers (docs) or 8 LlamaIndex instances (video):

| Full scale | RocketRide — 1 token | LlamaIndex |
|---|---|---|
| Docs: span docs/s (PRIMARY) | 2.3395 † | 5.096 |
| Docs: CPU utilisation, engine / 32 | 56.16% † | 72.59% |
| Docs: idle core-equivalents of 32 | 13.802 † | 8.714 |
| Docs: idle spin (burned, not idle) | 1.224 † | 0.034 |
| Video: frames/s | RANKING ONLY (leg-6 rule) | 13.524 |
| Video: CPU utilisation, engine / 32 | 18.29% | 89.27% |
| Video: idle core-equivalents of 32 | 26.015 | 3.132 |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

**Per unit** (§4, the only basis for a per-unit claim): from one to eight documents in flight, one RocketRide token's throughput grows 5.00x; one LlamaIndex worker's grows 1.01x.

**Stage 5, segregated** (§6; no Stage 5 figure appears beside a baseline one):

- S5-A (TUNED POSTURE): intra-op width stops adding throughput at T=2; beyond it only CPU cost rises, and every T other than 16 changes the detection scores. Unset vs 16: ESTABLISHED.
- S5-B (PATCHED-ENGINE): STOPPED — batched detection failed the end-to-end correctness control; B>1 is a different measurement, not an optimisation.
- S5-C (DIAGNOSTIC): null control FAILED; beyond its spread, BOX PROPERTY.
- S5-D (INSTRUMENTED): no admission queue — the time is inside the pipeline, the long holds in parse; the parse-concurrency read of the same stamps finds those holds are the documents' own Tika cost, not a parse bound (§6).
- S5-E (thread variables unset vs = 1, docs): unset is slower and costs more CPU per document — READABLE beyond every noise measure; the banked docs posture, not the out-of-the-box one, is the faster RocketRide docs posture (§6).
- S5-F (SDK default-5 equivalent, C=5): 0.518 of this session's C=32 rate † (§6).

## 1. Headline — each arm at its own measured optimum, 9,975 GovDocs PDFs (Stage 4)

Both arms run the **banked docs posture: 1 token, six vars = 1, both arms** — RocketRide one token (`use()` with no `threads=`), LlamaIndex 24 service workers (its own measured optimum), and the six BLAS/OpenMP/torch thread variables = 1 on both, read back from inside the running processes (first row). The six variables at 1 are the campaign's banked docs posture, not RocketRide's out-of-the-box default (which leaves them unset; S5-E measures the difference). This row pair answers "how fast does each stack go at its best on this box"; it is **not** a per-unit comparison — one token against 24 workers — and carries no parity claim. The per-unit comparison is the G4 anchor, §4. Both arms unconstrained across all 32 vCPUs (Ruling A); one leg on the box at a time (Ruling C); caches prewarmed.

| Stage 4 docs, 9,975 PDFs + 25 warm-up | RocketRide — 1 token | LlamaIndex — 24 workers |
|---|---|---|
| Posture — banked docs posture: 1 token, six vars = 1, both arms (read back in-process) | 1 token, threads= not passed; six thread variables at 1, and torch threads 1, both read in the task process; cpuset 0-31 of 32 † | 24 workers; six thread variables at 1 in every service process read, all agreeing; torch threads 1, from one worker's /health answer; cpuset 0-31 of 32 |
| Submission at the arm's own optimum | continuous, C=32 (the knee) † | continuous, C=32 — a TIE with C=16 inside its 9.87% floor; C=32 kept per register 12, not as a winner |
| **Span throughput, docs/s — PRIMARY** | **2.3395** † | **5.096** |
| Span with 039_039660.pdf dropped from BOTH arms | 3.6956 † | 5.0955 |
| docs/s to the 99th-percentile completion — POST-HOC DIAGNOSTIC | 3.9344 † | 5.2865 |
| Document that set the span (held) | 039_039660.pdf (1722 s) † | 011_011575.pdf (149.8 s) |
| Engine container CPU, cores (cgroup) | 17.97 † | 23.228 |
| Driver CPU, cores (getrusage) | 0.036 † | 0.039 |
| Host busy cores (per-core /proc/stat) | 18.198 † | 23.286 |
| CPU utilisation, engine / 32 vCPUs | 56.16% † | 72.59% |
| **Idle core-equivalents (32 − host busy)** | **13.802** † | **8.714** |
| Idle spin — CPU BURNED while idle, not idle capacity | 1.224 † | 0.034 |
| CPU-seconds per document (engine) | 7.681 † | 4.558 |
| Engine memory (cgroup): anon at window close / total high-water memory.peak | 12.0 GiB / 21.9 GiB † | 15.9 GiB / 17.1 GiB |
| Documents: completed / content outcome (no text, parse failed) / lost to the deadline / other failure | 9,885 / 89 / 1 / 0 † | 9,873 / 102 / 0 / 0 |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

Source: `working/results/batchsize_s4_20260921T013303Z/analysis_docs.json` (ranking, check_E_tail) and the two `leg_*_refc32_main.json` (cost, memory, documents).

The RocketRide leg lost 1 document(s) to the driver's own 1,800 s deadline — a harness loss, not an engine error: `011_011464.pdf` (held 1800 s).

**Why span and the diagnostics disagree on RocketRide.** `039_039660.pdf` (39 pages, per the corpus manifest) finished 1738 s after the 99th-percentile completion and set the span (register 40). Dropping it from both arms is the symmetric view; the p99 figure was defined after this leg was seen (register 34) and is never the headline.

### Empty-content documents, both arms (C5)

RocketRide 89†, LlamaIndex 102; 89 are empty on both. Empty on LlamaIndex only (13): `002_002400.pdf`, `004_004306.pdf`, `008_008724.pdf`, `009_009802.pdf`, `014_014222.pdf`, `018_018542.pdf`, `020_020747.pdf`, `020_020806.pdf`, `022_022819.pdf`, `027_027613.pdf`, `033_033689.pdf`, `037_037919.pdf`, `040_040669.pdf`. Empty on RocketRide only (0): none.
An empty extraction is a parser outcome (Tika vs pypdf), reported as content, never as lost work.
Source: `working/results/batchsize_s4_20260921T013303Z/analysis_docs.json` → check_C5_empty_content.

## 2. Batch size at full scale — the envelope, 9,975 PDFs (Stage 4)

**Batch K** is the only lever that exists without modifying an arm: RocketRide `send_files(K files)` on one token; LlamaIndex K concurrent single-document POSTs behind a barrier (its service has no multi-document endpoint). The next batch starts only when every document of the current one has returned. Batch deadline pre-registered at 1,800 s for every K and both arms before the first envelope leg; a batch lost to it is blast radius, never re-run.

**What K means inside each arm — SOURCE, not measurement.** RocketRide: the installed SDK (rocketride 1.3.0) opens all K pipes at once, with no client-side bound (`rocketride/mixins/data.py:719-725`); the engine admits at most 64 pipes per token (`engine/ai/modules/data/data_conn.py:138,477`; threadCount 64 when `threads=` is not passed, `engine/ai/constants.py:48`, `task_engine.py:247,382`) and runs each document's pipeline on asyncio's default executor (`data_conn.py:737`), which is 32 threads on this 32-vCPU box. So K is documents per barrier, and at K of 32 or more at most 32 are processed at once. LlamaIndex: K concurrent POSTs (`working/scripts/exp_batchsize_sweep.py:702`) to 24 single-concurrency workers, so at most 24 are processed at once. The SDK and engine files cited were hashed on the box and match the copies read here.

### RocketRide — 1 token

| K | Span docs/s | Batches | Batch wall median / max, s | Batch holding 039_039660.pdf: wall (spare to 1,800 s) | That batch's share of the span | Batches died | Documents returned / lost / numerator of docs/s § | Peak engine anon, bracketed ¶ | Idle core-equiv. |
|---|---|---|---|---|---|---|---|---|---|
| K=128 | 0.9643 † | 78 | 75.0 / 1706.8 | #77: 1706.8 s (93.2 s spare) | 16.65% | 0 | 9,975 / 0 / 9,886 | 10.2 GiB – 21.6 GiB | 24.771 † |
| K=256 | 1.1952 † | 39 | 128.6 / 1748.1 | #38: 1748.1 s (51.9 s spare) | 21.14% | 0 | 9,975 / 0 / 9,886 | 11.7 GiB – 22.8 GiB | 22.848 † |
| K=512 | 1.392 † | 20 | 244.7 / 1754.4 | #19: 1754.4 s (45.6 s spare) | 24.70% | 0 | 9,975 / 0 / 9,886 | 11.7 GiB – 22.6 GiB | 21.099 † |
| K=1024 | 1.5142 † | 10 | 458.0 / 1800.1 | #9: DIED at the deadline (1800.1 s) | 29.86% | 1 — batch 9, blast radius | 9,216 / 759 / 9,129 | 11.5 GiB – 23.0 GiB | 19.084 † |
| continuous C=32 (reference) | 2.3395 † | — | — | — | — | — | — | — | 13.802 † |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

¶ cgroup v2 keeps no anon high-water mark, so peak anon RSS is bracketed, not read: at least the anon at the window's close, at most the container's total high-water `memory.peak`. No memory was sampled during a leg, so no statement about how memory moved with K is made.
§ Returned = documents with content + content outcomes (no text, parse failed); lost = deadline losses + other failures. docs/s divides the documents WITH CONTENT (the third number) by the span.

<details><summary>Per-batch wall times, s (batch index: wall)</summary>

- K=128 (p3_rr_k128/k128_main): 0:47.1, 1:115.9, 2:41.4, 3:85.7, 4:78.4, 5:55.7, 6:71.5, 7:61.3, 8:105.5, 9:174.1, 10:46.2, 11:64.0, 12:49.7, 13:72.2, 14:38.3, 15:60.9, 16:43.5, 17:64.9, 18:106.9, 19:84.4, 20:67.5, 21:58.7, 22:48.2, 23:48.2, 24:173.8, 25:72.9, 26:104.3, 27:242.2, 28:98.3, 29:753.2, 30:94.6, 31:75.7, 32:60.8, 33:255.2, 34:65.9, 35:46.9, 36:51.0, 37:142.8, 38:359.0, 39:192.9, 40:107.3, 41:133.2, 42:79.4, 43:41.9, 44:274.5, 45:41.3, 46:39.4, 47:108.4, 48:171.5, 49:211.2, 50:45.7, 51:22.0, 52:442.6, 53:288.1, 54:27.0, 55:124.6, 56:27.3, 57:125.2, 58:156.4, 59:81.7, 60:103.2, 61:51.8, 62:74.4, 63:64.3, 64:152.9, 65:69.3, 66:52.6, 67:48.0, 68:56.6, 69:68.5, 70:245.8, 71:151.6, 72:50.1, 73:43.7, 74:102.8, 75:99.7, 76:80.0, 77:1706.8
- K=256 (e7_rr_k256/k256_env): 0:140.5, 1:103.4, 2:93.6, 3:85.5, 4:205.9, 5:89.2, 6:94.4, 7:86.2, 8:89.2, 9:126.1, 10:88.1, 11:70.9, 12:198.3, 13:274.6, 14:779.5, 15:109.8, 16:282.3, 17:83.2, 18:168.0, 19:390.4, 20:165.0, 21:92.4, 22:293.5, 23:129.1, 24:244.7, 25:55.8, 26:478.7, 27:145.6, 28:147.3, 29:184.3, 30:121.5, 31:90.1, 32:172.2, 33:71.5, 34:95.2, 35:279.2, 36:68.2, 37:128.6, 38:1748.1
- K=512 (e9_rr_k512/k512_env): 0:169.8, 1:144.9, 2:253.3, 3:139.3, 4:174.6, 5:126.1, 6:351.9, 7:815.1, 8:322.1, 9:439.8, 10:190.0, 11:330.9, 12:273.3, 13:514.8, 14:236.0, 15:150.6, 16:200.2, 17:334.1, 18:179.8, 19:1754.4
- K=1024 (e11_rr_k1024/k1024_env): 0:262.9, 1:325.5, 2:249.7, 3:972.3, 4:574.4, 5:448.7, 6:617.4, 7:309.6, 8:467.2, 9:1800.1

</details>

### LlamaIndex — 24 workers

| K | Span docs/s | Batches | Batch wall median / max, s | Batch holding 039_039660.pdf: wall (spare to 1,800 s) | That batch's share of the span | Batches died | Documents returned / lost / numerator of docs/s § | Peak engine anon, bracketed ¶ | Idle core-equiv. |
|---|---|---|---|---|---|---|---|---|---|
| K=128 | 1.9264 | 78 | 54.5 / 236.0 | #77: 38.8 s (1761.2 s spare) | 0.76% | 0 | 9,975 / 0 / 9,873 | 15.8 GiB – 16.9 GiB | 25.181 |
| K=256 | 2.4591 | 39 | 98.2 / 251.3 | #38: 105.3 s (1694.7 s spare) | 2.62% | 0 | 9,975 / 0 / 9,873 | 15.9 GiB – 17.0 GiB | 22.47 |
| K=512 | 3.0463 | 20 | 143.3 / 308.2 | #19: 101.2 s (1698.8 s spare) | 3.12% | 0 | 9,975 / 0 / 9,873 | 16.0 GiB – 17.2 GiB | 19.422 |
| K=1024 (re-run, register 44) | 3.8639 | 10 | 240.3 / 380.8 | #9: 241.3 s (1558.7 s spare) | 9.44% | 0 | 9,975 / 0 / 9,873 | 15.9 GiB – 17.1 GiB | 14.995 |
| continuous C=32 (reference) | 5.096 | — | — | — | — | — | — | — | 8.714 |

¶ cgroup v2 keeps no anon high-water mark, so peak anon RSS is bracketed, not read: at least the anon at the window's close, at most the container's total high-water `memory.peak`. No memory was sampled during a leg, so no statement about how memory moved with K is made.
§ Returned = documents with content + content outcomes (no text, parse failed); lost = deadline losses + other failures. docs/s divides the documents WITH CONTENT (the third number) by the span.

<details><summary>Per-batch wall times, s (batch index: wall)</summary>

- K=128 (p4_li_k128/k128_main): 0:34.7, 1:94.1, 2:39.8, 3:90.5, 4:93.6, 5:47.7, 6:54.0, 7:55.6, 8:98.7, 9:73.5, 10:64.4, 11:46.3, 12:34.9, 13:42.9, 14:46.7, 15:55.1, 16:47.8, 17:52.3, 18:67.8, 19:69.1, 20:40.1, 21:55.4, 22:37.8, 23:42.8, 24:96.6, 25:38.9, 26:89.8, 27:32.1, 28:79.9, 29:87.7, 30:87.5, 31:34.6, 32:73.5, 33:236.0, 34:57.8, 35:57.5, 36:49.9, 37:134.6, 38:79.6, 39:178.7, 40:68.2, 41:106.5, 42:80.9, 43:47.6, 44:74.1, 45:41.2, 46:36.8, 47:49.7, 48:42.2, 49:31.4, 50:51.2, 51:25.1, 52:99.1, 53:36.8, 54:31.3, 55:91.6, 56:32.2, 57:78.0, 58:59.1, 59:54.9, 60:106.5, 61:44.4, 62:44.6, 63:47.2, 64:134.3, 65:62.0, 66:48.1, 67:49.8, 68:41.6, 69:45.9, 70:62.9, 71:46.0, 72:31.8, 73:40.8, 74:101.2, 75:171.6, 76:68.9, 77:38.8
- K=256 (e8_li_k256/k256_env): 0:108.7, 1:100.3, 2:99.3, 3:76.7, 4:118.2, 5:100.3, 6:64.7, 7:81.3, 8:76.9, 9:84.7, 10:65.3, 11:65.5, 12:113.8, 13:105.1, 14:88.8, 15:112.7, 16:251.3, 17:85.9, 18:125.1, 19:212.0, 20:122.1, 21:94.6, 22:81.9, 23:94.3, 24:66.1, 25:61.2, 26:126.2, 27:124.1, 28:98.2, 29:102.7, 30:127.8, 31:62.0, 32:165.2, 33:70.2, 34:68.6, 35:85.9, 36:54.0, 37:167.7, 38:105.3
- K=512 (e10_li_k512/k512_env): 0:141.2, 1:147.7, 2:164.6, 3:112.6, 4:129.9, 5:114.7, 6:170.2, 7:145.4, 8:296.6, 9:308.2, 10:147.9, 11:116.0, 12:112.6, 13:180.9, 14:132.5, 15:136.9, 16:164.4, 17:121.9, 18:295.2, 19:101.2
- K=1024 (e12b_li_k1024/k1024_env): 0:227.2, 1:241.7, 2:232.1, 3:271.6, 4:380.8, 5:212.0, 6:273.5, 7:235.6, 8:239.4, 9:241.3

</details>

**K=1,024, stated plainly.** RocketRide returned 9,216 documents (9,129 with content, 87 content outcomes) and lost 759 to the deadline †; LlamaIndex returned 9,975 (9,873 with content, 102 content outcomes) and lost 0. Each arm's docs/s divides its documents with content — 9,129 and 9,873 — by its span.

**The two K=1,024 legs ran under different open-file limits.** RocketRide's e11 ran before the fix (register 44), at the box's default soft limit of 1,024 descriptors; LlamaIndex's e12b ran at 65,536 (recorded in its export). No descriptor count was sampled during e11, so its peak is not measured. Its records carry 0 open-file errors — every loss is `batch_error:TimeoutError`. SOURCE, not measurement: the SDK opens a file only after the engine grants its pipe (`rocketride/mixins/data.py:651`), and the engine grants at most 64 per token (`data_conn.py:138,477`), so RocketRide's open files stay near 64 plus its one websocket, whatever K.

**Where `039_039660.pdf` sat in each leg's submission order** (R3). Every leg sends the slice in one fixed order, the slice file's, where the document is at position 9,957 of 9,975. Its rank by submit stamp differs by leg, for two reasons that do not change that order: a continuous leg stamps each document when a worker actually sends it, so near-simultaneous sends interleave; and a RocketRide batch stamps all its rows at once, so the rank inside a batch is only alphabetical (ties are broken by name).

| Leg | Slice position (the send order) | Rank by submit stamp | Batch | Held, s | Set the span? |
|---|---|---|---|---|---|
| p1_rr_cont32 | 9,957 of 9,975 | 9,957 † | — | 1722 † | yes |
| p2_li_cont | 9,957 of 9,975 | 9,957 | — | 31 | no — `011_011575.pdf` (held 149.8 s) |
| p3_rr_k128 | 9,957 of 9,975 | 9,973 † | #77 | 1706.8 † | its batch #77 did — the last to return; its 119 rows share one return stamp |
| p4_li_k128 | 9,957 of 9,975 | 9,960 | #77 | 38.8 | yes |
| e7_rr_k256 | 9,957 of 9,975 | 9,967 † | #38 | 1748.1 † | its batch #38 did — the last to return; its 247 rows share one return stamp |
| e8_li_k256 | 9,957 of 9,975 | 9,960 | #38 | 61.1 | no — `033_033175.pdf` (held 105.3 s) |
| e9_rr_k512 | 9,957 of 9,975 | 9,967 † | #19 | 1754.4 † | its batch #19 did — the last to return; its 247 rows share one return stamp |
| e10_li_k512 | 9,957 of 9,975 | 9,957 | #19 | 47.8 | no — `009_009076.pdf` (held 101.2 s) |
| e11_rr_k1024 | 9,957 of 9,975 | 9,949 † | #9 | 1800.1 † | its batch #9 did — the last to return; its 759 rows share one return stamp |
| e12b_li_k1024 | 9,957 of 9,975 | 9,955 | #9 | 170.5 | no — `018_018497.pdf` (held 241.1 s) |

**The span is order-dependent.** `039_039660.pdf` is the 19th document from the end of the order (position 9,957 of 9,975); on RocketRide it is then held 1722 s †, so it outlasts the rest of the run and sets the span of the continuous leg, and on batched legs it is in the last batch at every K. Sent early, that hold would overlap the bulk of the run and the span would be set by the bulk. The span with it dropped from both arms (§1) and the p99 diagnostic are the order-robust views; the span itself is a property of this order as much as of the arm.

**The pre-registered K=512 rule, for audit only** (every K ran on both arms by ruling): . Source: `working/results/batchsize_s4_20260921T013303Z/envelope_k512_decision.json`.

**Batch size never changed the output.** Chunk hashes are identical across every K and the continuous legs within each arm (check C: RocketRide PASS, LlamaIndex PASS); across arms they differ, the null control that shows the comparator can see a difference.

Source: `working/results/batchsize_s4_20260921T013303Z/analysis_docs.json` → ranking.by_k, envelope_batch_report, check_C_content.

## 3. AMI video at full scale, 168 videos + 2 warm-up (Stage 4)

There is **no batch knob on the video path of either arm** (one frame per detector call by design). K is the number of videos in flight (`driver_video.py --blast-concurrency K`, unmodified).

| Stage 4 video, 168 AMI videos | LlamaIndex | RocketRide |
|---|---|---|
| Posture, read back in-process | workers[declared_workers=8]: 8 process(es) read back: six thread variables at 4; torch threads [4] | out of the box — default[tokens=1,threads=unset(engine-default-64)]: 1 process(es) read back: six thread variables unset; torch threads [16] |
| Videos in flight, K | 16 | 16 |
| Throughput, frames/s | 13.524 | **RANKING ONLY** — see rule below |
| Engine CPU, cores (cgroup) | 28.566 | 5.853 |
| CPU utilisation, engine / 32 vCPUs | 89.27% | 18.29% |
| **Idle core-equivalents (32 − host busy)** | **3.132** | **26.015** |
| Idle spin — burned, not idle | 0.034 | 1.226 |
| Videos / errors | 168 / 0 | 168 / 0 |

**Ranking: LlamaIndex ahead of RocketRide.** **The leg-6 rule fired.** RocketRide's K=16 replicate spread on the 16-video slice is 9.76% (G5(b)), above the pre-set 2% threshold, so this leg's absolute frames/s is not quotable beside banked figures; it is reported as a ranking plus idle cores only. One pass was authorised because G5(b) supplies a spread at this scale. LlamaIndex's own K=8 replicate spread was 12.25%.

Sources: `working/results/batchsize_s4_20260921T013303Z/p5_li_video/analysis_video.json`, `working/results/batchsize_s4_20260921T013303Z/p6_rr_video/analysis_video.json`; spreads from `working/results/batchsize_smoke_20260920T113000Z/analysis_video.json` and `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_rep.json`.

## 4. The per-unit anchor — the only basis for a per-unit claim (G4)

One RocketRide token against ONE LlamaIndex worker, same documents, same in-flight C. This is a 96-document stratified sub-slice: **smoke-scale absolutes, not comparable with the 10k tables above.**

| Docs, 96-PDF sub-slice | C=1 docs/s | C=8 docs/s | C=8 / C=1 | C=8 engine cores | C=8 idle core-equiv. |
|---|---|---|---|---|---|
| RocketRide — 1 token | 0.3209 † | 1.6058 † | 5.00x | 7.57 † | 24.348 † |
| LlamaIndex — 1 worker | 0.448 | 0.4503 | 1.01x | 1 | 30.995 |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

One token scales with documents in flight; one LlamaIndex worker does not — its `/process_pdf` handles one document per request and is effectively single-concurrency per worker, so LlamaIndex's headline throughput comes from its worker count.

Video, 16-video slice, K=16: one LlamaIndex instance 3.068 frames/s at 2.924 cores; one RocketRide token 2.623 and 2.379 frames/s in two runs (9.76% apart) at 5.293 / 5.507 cores.

Sources: `working/results/batchsize_s3b_20260920T203139Z/analysis_docs_anchor96.json`, `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_anchor.json`, `working/results/batchsize_smoke_20260920T113000Z/analysis_video.json`, `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_rep.json`.

## 5. How the operating points were chosen — smoke slice, 384 stratified PDFs (Stage 3b)

**Smoke-scale absolutes. Never compare these with the 10k figures above.** The 384-document slice is stratified by page count × characters per page; one long PDF can set a short leg's span.

| Arm | Continuous C curve, docs/s | Knee | Batch K, docs/s (mean of runs) | Warm replicate floor |
|---|---|---|---|---|
| RocketRide — 1 token | C=4: 1.0764, C=8: 1.8886, C=16: 2.3417, C=32: 2.4836, C=64: 2.4744 † | knee at C=32 (TIE between C=[32, 64]) | K=1: 0.2942, K=8: 0.5254, K=16: 0.6461, K=32: 0.8448, K=64: 1.1371, K=128: 1.833, K=256: 2.0593, K=384: 2.4798 † | 0.82% |
| LlamaIndex — 24 workers | C=4: 1.5444, C=8: 2.7016, C=16: 3.3481, C=32: 3.5358, C=64: 3.3858 | knee at C=16 (TIE between C=[16, 32, 64]) | K=1: 0.4138, K=8: 0.8101, K=16: 1.0593, K=32: 1.3889, K=64: 1.9108, K=128: 2.1654, K=256: 2.217, K=384: 3.307 | 9.87% |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

The in-grid best K was the grid edge (K=128) on both arms and continuous submission beat every K on both arms, so K=256/512/1024 were characterised at 10k scale (Ruling B, §2). K values at or above the slice size collapse to one batch here and are not rankable at this scale.

**LlamaIndex worker count at C=32 (G3b).** Not resolved above its floor; 24 kept.

| Service workers | docs/s, each run | mean |
|---|---|---|
| 16 workers | 3.2123 | 3.2123 |
| 24 workers | 3.66, 3.4117 | 3.5358 |
| 32 workers | 3.331 | 3.331 |

**Cold vs warm page cache (G5a)**, each cold leg against warm legs of the same arm shape. Caches dropped before the cold leg; every Stage 4 leg is prewarmed.

| Arm | Cell | Warm runs, docs/s | Cold run, docs/s | Cold vs warm mean |
|---|---|---|---|---|
| RocketRide | C=32, 1 token | 2.487, 2.4802 † | 2.4575 † | -1.1% |
| RocketRide | K=128, 1 token | 1.8273, 1.8387 † | 1.8447 † | +0.6% |
| LlamaIndex | C=32, 24 workers | 3.66, 3.4117 | 3.2835 | -7.1% |
| LlamaIndex | K=128, 24 workers | 2.2723, 2.0586 | 1.7135 | -20.9% |

Source: `working/results/batchsize_s3b_20260920T203139Z/analysis_docs_384.json` (ranking, noise_floor, check_G3b_unit_sweep, check_G5a_cache_effect).

**Provenance of these analyses** (R7): PASS — both Stage 3b analyses contain only Stage 3b launches; the misfiled copy matches no launch. The misfiled `shake_rr` export names `working/results/batchsize_smoke_20260920T113000Z/shake_rr` and matched no launch; the check's null control (a planted export naming another campaign) was rejected. Source: `working/results/batchsize_s3b_20260920T203139Z/provenance_check.json`.

**Video, 16-video smoke slice — how K=16 was chosen.** Smoke-scale absolutes; never beside the 168-video figures.

| Arm | Videos in flight | Run | frames/s | engine cores | idle core-equiv. |
|---|---|---|---|---|---|
| LlamaIndex — 8x4 | K=1 | first run | 3.13 | 2.693 | 29.317 |
| LlamaIndex — 8x4 | K=8 | first run | 13.876 | 24.114 | 7.067 |
| LlamaIndex — 8x4 | K=16 | first run | 14.117 | 25.711 | 4.807 |
| RocketRide — 1 token | K=1 | first run | 2.392 | 5.123 | 26.868 |
| RocketRide — 1 token | K=8 | first run | 2.54 | 5.382 | 26.599 |
| RocketRide — 1 token | K=16 | first run | 2.623 | 5.293 | 26.68 |
| LlamaIndex — 8x4 | K=8 | replicate | 12.274 | 24.182 | 7.055 |
| RocketRide — 1 token | K=16 | replicate | 2.379 | 5.507 | 26.329 |

RocketRide at one token barely moves with K (one detector instance serves every frame); the stock video pipeline was chunk-identical across runs and across K on every video, and differed from the other arm on every video (the null control).

Sources: `working/results/batchsize_smoke_20260920T113000Z/analysis_video.json`, `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_rep.json`.

## Checks behind the full-scale figures

| Check | Verdict | Null control |
|---|---|---|
| A. Clock: docs/s from per-document wall stamps vs the export's monotonic span | 11 legs: PASS 11 | — |
| B. CPU source: engine cgroup cores vs host per-core busy on the same CPUs | 11 legs: PASS 11 | — |
| C. Content: chunk hashes identical across every K and C within an arm | RocketRide PASS, LlamaIndex PASS | cross-arm comparison FIRED: 9,081 of 9,116 documents differ (different parsers) |
| E. The K ranking is the same by span and by time-to-p90 | li: PASS — K ranking identical under both metrics, rr: PASS — K ranking identical under both metrics | — |
| Ruling C: no other container, no stray process above 0.5 cores, before each leg | 11 legs: all clean | — |

Source: `working/results/batchsize_s4_20260921T013303Z/analysis_docs.json` → check_A_clock, check_B_cpu_source, check_C_content, check_E_tail, box_hygiene_per_leg.

## 6. Stage 5 — optimisation investigation (SEGREGATED from every baseline table above)

All of Stage 5 runs at ONE RocketRide token. Nothing here is out-of-the-box RocketRide: S5-A is a TUNED POSTURE (image unchanged, thread configuration set), S5-B is a PATCHED ENGINE (new image), S5-C binds cpusets on purpose (diagnostic, outside Ruling A), S5-D is an INSTRUMENTED replay. The comparator for per-unit statements is the G4 anchor (§4), never the tuned 8x4 cell.

### S5-A — intra-op thread width T at one token (TUNED POSTURE)

| T (TUNED POSTURE) | frames/s | engine cores | util / 32 | idle core-equiv. | CPU-s/frame | torch threads read in-process |
|---|---|---|---|---|---|---|
| T=1 | 1.262 | 2.39 | 7.47% | 29.579 | 1.895 | 1 |
| T=2 | 2.286 | 3.508 | 10.96% | 28.436 | 1.534 | 2 |
| T=4 | 2.233 | 3.665 | 11.45% | 28.229 | 1.642 | 4 |
| T=8 | 2.462 | 4.372 | 13.66% | 27.457 | 1.776 | 8 |
| T=16 | 2.331 | 5.637 | 17.61% | 26.122 | 2.418 | 16 |

Knee T=2 (smallest T within G5(b)'s 9.76% spread of the best T); saturation T=8. Excluded legs: [].
T=16 against the out-of-the-box default cell: ESTABLISHED — T=16 reproduces the default cell within the spread AND produces chunk-identical output (relative -0.068, chunk-identical videos 16/16).
Output against the out-of-the-box default cell — a DIAGNOSTIC, not a pre-registered gate for S5-A (intra-op width changes the floating-point path, as batching does in S5-B):

| Leg | chunk-identical videos | frames with identical labels | frames with identical counts | largest score change (at least) |
|---|---|---|---|---|
| default vs its own replicate (null control) | 16/16 | 3,203/3,203 | 3,203/3,203 | 0.00e+00 |
| T=1 | 0/16 | 3,203/3,203 | 3,203/3,203 | 2.18e-03 |
| T=2 | 0/16 | 3,203/3,203 | 3,203/3,203 | 1.96e-03 |
| T=4 | 0/16 | 3,203/3,203 | 3,203/3,203 | 1.96e-03 |
| T=8 | 0/16 | 3,203/3,203 | 3,203/3,203 | 2.10e-03 |
| T=16 | 16/16 | 3,203/3,203 | 3,203/3,203 | 0.00e+00 |

Comparator, the G4 anchor (one LlamaIndex instance, K=16, same videos): 3.068 frames/s at 2.924 cores.

Source: `working/results/batchsize_s5_20260921T205917Z/analysis_s5a_threads.json`.

### S5-B — detector frame micro-batching (PATCHED-ENGINE, NOT OUT-OF-THE-BOX)

Pre-check, read-only, in a throwaway container of the unmodified `rr:patched-video` on 24 frames, criterion pre-registered in the artifact: **PASS labelled NUMERICALLY EQUIVALENT (TIER 2) — within the pre-registered tolerances at every B, but NOT bit-identical; the emitted text and its chunk hashes will differ from B=1**

Null controls: one frame at a time is bit-reproducible — True; the comparator sees two different frames as different — True.

| Batch | bit-identical frames | max score change | max box change, output px | detection counts equal | Tier |
|---|---|---|---|---|---|
| B=2 | 0/24 | 9.54e-07 (limit 1e-05) | 6.10e-05 (limit 1e-03) | True | TIER 2 — NUMERICALLY EQUIVALENT |
| B=4 | 0/24 | 1.28e-06 (limit 1e-05) | 1.37e-04 (limit 1e-03) | True | TIER 2 — NUMERICALLY EQUIVALENT |
| B=8 | 0/24 | 1.28e-06 (limit 1e-05) | 1.37e-04 (limit 1e-03) | True | TIER 2 — NUMERICALLY EQUIVALENT |

**Null control** (patched B=1, through the new batched code path, against stock by chunk hash): 16/16 videos identical — PASS.

| Batch | Tier 1: every video chunk-identical | Tier 2: frames failing | max score change | max box change, output px | Result |
|---|---|---|---|---|---|
| B=2 | False | 132/3,526 | 7.49e-03 (limit 1e-05) | 1.04e-01 (limit 1e-03) | NEITHER — a different measurement, not an optimisation |
| B=4 | False | 131/3,526 | 1.96e-03 (limit 1e-05) | 1.05e-01 (limit 1e-03) | NEITHER — a different measurement, not an optimisation |
| B=8 | False | 131/3,526 | 1.96e-03 (limit 1e-05) | 1.05e-01 (limit 1e-03) | NEITHER — a different measurement, not an optimisation |

**S5-B STOPPED by its end-to-end correctness control: B=[2, 4, 8] is a different measurement, not an optimisation (the ruling), and carries no timing.** The pre-check passed Tier 2 on 24 frames of one video; end to end, over every frame of the 16 videos, the same criterion failed — the pre-check licensed the build and the legs, never the claim.

**The stop, read as a measurement** (item 4). One comparator for every knob — per-frame label multisets and scores from the driver's own records, 16 measured videos; scores paired in sorted order, so each figure is a lower bound:

| Leg | chunk-identical videos | frames with every label kept | score shift, at least |
|---|---|---|---|
| null: default vs its own replicate | 16/16 | 3,203/3,203 | 0.00e+00 |
| null: patched B=1 vs default | 16/16 | 3,203/3,203 | 0.00e+00 |
| S5-A T=1 vs default (TUNED POSTURE) | 0/16 | 3,203/3,203 | 2.18e-03 |
| S5-A T=2 vs default (TUNED POSTURE) | 0/16 | 3,203/3,203 | 1.96e-03 |
| S5-A T=4 vs default (TUNED POSTURE) | 0/16 | 3,203/3,203 | 1.96e-03 |
| S5-A T=8 vs default (TUNED POSTURE) | 0/16 | 3,203/3,203 | 2.10e-03 |
| S5-A T=16 vs default (TUNED POSTURE) | 16/16 | 3,203/3,203 | 0.00e+00 |
| S5-B B=2 vs patched B=1 (PATCHED-ENGINE) | 0/16 | 3,203/3,203 | 7.49e-03 |
| S5-B B=4 vs patched B=1 (PATCHED-ENGINE) | 0/16 | 3,203/3,203 | 1.96e-03 |
| S5-B B=8 vs patched B=1 (PATCHED-ENGINE) | 0/16 | 3,203/3,203 | 1.96e-03 |

A thread-width change alone (S5-A) moves scores by at least 2.0e-03 with every label kept; batching (S5-B) moves them by up to 7.5e-03, also with every label kept on the measured frames. The pre-registered Tier 2 tolerance (1e-05 score, 1e-03 px) sits below both; the stop is that criterion's, and it stands.
Tier 2 failing frames on the 16 measured videos: B=2: 120, B=4: 120, B=8: 120; on the two warm-up videos the taps also cover: B=2: 12, B=4: 11, B=8: 11. The taps' 3 "label set or count differs" failure(s) changed no label and no count: B=2 `EN2001a.avi` frame 97, tv 0.3011 → 0.3008; B=4 `EN2001a.avi` frame 97, tv 0.3011 → 0.3008; B=8 `EN2001a.avi` frame 97, tv 0.3011 → 0.3008 — a score crossing the edge of the ±0.001 band around the 0.3 threshold, which the rule filters on each side by that side's own scores.

Source: `working/results/batchsize_s5_20260921T205917Z/analysis_output_shift.json`.

| B | Label | frames/s | engine cores | util / 32 | idle core-equiv. | engine memory: total high-water (peak) and anon at leg end — peak anon lies between |
|---|---|---|---|---|---|---|
| B=1 | PATCHED-ENGINE | 2.336 | 5.646 | 17.64% | 26.109 | peak 7.2 GiB, anon 0.1 GiB |

Verdict: B=[2, 4, 8] failed correctness and carry no timing. Source: `working/results/batchsize_s5_20260921T205917Z/analysis_s5b.json`.

### S5-C — is RocketRide's 32-vCPU cost hyperthreading? (DIAGNOSTIC — cpusets bound on purpose)

**Null control, pre-registered** (two unconstrained RocketRide runs, span docs/s): 2.4273 and 2.4673, spread 1.63% against the 0.82% floor — **FAILED**. No between-cell difference below 1.63% is interpretable.

POST-HOC DIAGNOSTIC (defined after the pre-registered control failed; does not change the verdict): the same pair agrees within 0.22% on CPU-s/doc — the metric the hypothesis turns on — and 0.63% on docs/s to p90; both spans were set by `029_029958.pdf` (held 124.9 s), `029_029958.pdf` (held 122.3 s), so the span gap is one document's finishing time.

| Arm | Cell against (a), unconstrained 32 vCPU | CPU-s/doc | docs/s | CPUs |
|---|---|---|---|---|
| RocketRide | (b) cpuset 0-23 | -11.7% | -2.5% | 24 |
| RocketRide | (c) one vCPU per physical core | -29.1% | -7.2% | 16 |
| LlamaIndex | (b) cpuset 0-23 | -1.0% | -13.7% | 24 |
| LlamaIndex | (c) one vCPU per physical core | -24.4% | -12.2% | 16 |

**The caveat is this row.** RocketRide at cpuset 0-23 against 32 vCPU, same harness: -2.5% docs/s, -11.7% CPU-s/doc — the † caveat on every RocketRide docs figure. It replaces an earlier caveat that compared Stage 3 (24-core cpuset, an earlier harness session) with Stage 3b (32 vCPU, a later one); that cross-session figure is WITHDRAWN (register 46).

| Cell (384 slice, continuous C=32) | cpuset | docs/s | CPU-s/doc | engine cores | task-process threads | JVM threads |
|---|---|---|---|---|---|---|
| rr_a1 | none (32 vCPU) | 2.4273 † | 6.553 † | 15.906 † | 283 | 0 |
| rr_a2 | none (32 vCPU) | 2.4673 † | 6.539 † | 16.133 † | 289 | 1 |
| rr_b | 0-23 | 2.3854 ‡ | 5.78 ‡ | 13.788 ‡ | 280 | 0 |
| rr_c | 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 | 2.2702 ‡ | 4.639 ‡ | 10.53 ‡ | 271 | 1 |
| li_a | none (32 vCPU) | 3.5893 | 4.012 | 14.399 | 0 | 0 |
| li_b | 0-23 | 3.0986 | 3.97 | 12.302 | 0 | 0 |
| li_c | 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 | 3.1508 | 3.032 | 9.552 | 0 | 0 |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)
‡ RocketRide under a declared cpuset — an S5-C diagnostic outside Ruling A, never a baseline figure.

Hypothesis reading, at the tolerance the failed control leaves (1.63%): **BOX PROPERTY — both arms get cheaper without siblings; not RocketRide-specific**. Analyser verdict: NULL CONTROL FAILED — two runs of the same unconstrained cell differ by more than the floor; no between-cell difference below that spread is interpretable.

In every RocketRide cell's snapshot the only JVM process is `jspawnhelper` (1 thread), the JVM's spawn helper: there is no standalone `java` process, so the JVM runs inside the task process and its threads are in the task-process column. Processes seen: `engine`, `jspawnhelper`, `scanner-0`.

Source: `working/results/batchsize_s5_20260921T205917Z/analysis_s5c_smt.json`.

### S5-D — the admission funnel inside one token (INSTRUMENTED replay of leg 1)

| Documents (share of end-to-end latency; p50) | n | admission wait | parse (Tika, incl. contention) | split | embed | return |
|---|---|---|---|---|---|---|
| all documents | 9,885 | 0.10% (p50 0 s) | 41.02% (p50 0.27 s) | 0.06% (p50 0 s) | 57.46% (p50 1.83 s) | 1.36% (p50 0.05 s) |
| tercile_0 (< 7 pages) | 3,250 | 0.45% (p50 0 s) | 57.95% (p50 0.09 s) | 0.12% (p50 0 s) | 39.08% (p50 0.63 s) | 2.40% (p50 0.02 s) |
| tercile_1 (7-21 pages) | 3,243 | 0.18% (p50 0 s) | 47.56% (p50 0.22 s) | 0.07% (p50 0 s) | 50.56% (p50 1.87 s) | 1.62% (p50 0.04 s) |
| tercile_2 (>= 22 pages) | 3,392 | 0.05% (p50 0 s) | 37.65% (p50 0.83 s) | 0.05% (p50 0 s) | 61.07% (p50 6.22 s) | 1.19% (p50 0.12 s) |

**The lane hypothesis, at admission: not supported.** Waiting for admission is at most 0.45% of end-to-end latency in any page tercile (p99 at most 0.09 s): documents enter the pipeline as they are sent. The time is spent INSIDE it. Of the 15 documents held over 300 s, 13 were held in parse, 2 in embed.
Joined 9,885 documents; 90 unjoined (content outcomes and the deadline loss, which never reach every stage). Cannot separate: a stage's own work from contention INSIDE that stage (a JVM pool, the GIL): that needs each document's solo stage time, which a C=32 run does not contain.

**Instrument perturbation, pre-registered** (span docs/s against leg 1, floor 0.82%): 2.2912 against 2.3395, -2.06% — OUTSIDE the floor — the instrument perturbed the measurement; decomposition shares stand, absolute times carry the offset.

POST-HOC DIAGNOSTIC (defined after the pre-registered comparison fell outside the floor; does not change the verdict): docs/s to p90 -1.54%, to p99 -1.48%; both spans set by `039_039660.pdf` (held 1722 s in leg 1, 1773.4 s instrumented); the same deadline loss in both (`011_011464.pdf`).

Source: `working/results/batchsize_s5_20260921T205917Z/analysis_s5d_funnel.json`.

**Parse concurrency inside one token** (item 5 — POST-HOC on the S5-D stamps; laptop only):

| Measured, time-weighted over the leg | max | p50 | p95 |
|---|---|---|---|
| documents in parse (waiting or parsing) | 32 | 10 | 17 |
| documents in the pipeline | 32 | 31 | 32 |

- One process carries every stamp, on 32 threads per stage; 9,911 of 10,000 documents ran parse and embed on the same thread (the rest are the content outcomes, which have no embed stamp). Up to 26 threads held a document in parse at a sampled instant (every 25th admission; a lower bound on the maximum).
- The 6 documents of 1,000+ pages spent at most 7.3 s in parse and 113.7-450.8 s in embed; some such document was in parse for 29 s of the leg (0.67%).
- Of 3,289 documents under 7 pages, 45 were in parse while a 1,000+ page document was — 1.25% of their parse time; median parse 0.1 s with overlap, 0.09 s without.
- The 11 documents held in parse over 300 s reproduce: each one's parse time here is within 4.86% of its end-to-end time in Stage 4 leg 1, and each took at most 31 s end to end on LlamaIndex. While each sat in parse, between 18 and 6,171 other documents entered and left parse; the fewest during `039_039660.pdf`'s, which is sent near the end of the order.

**The hypothesis — parse effectively bounded per token, small documents waiting behind large ones inside parse — is not supported on these stamps.** Thousands of documents pass through parse while a slow one sits there, so no lock holds parse for a whole document at a time; the large documents are in embed, not parse; and the long parse holds are the documents' own Tika cost, repeated run to run and absent on pypdf. What the stamps cannot say: whether a document in parse was WAITING for a slot or BEING parsed: Tika emits its text as one event, so the stamp marks only when parsing ended; that split needs the engine's own parse start, which no stamp records.

**SOURCE, not measurement — what bounds concurrency inside one task process:** engine/ai/modules/data/data_conn.py:737 runs each pipe's close — where the document's pipeline executes (pipe.close(), data_conn.py:711) — via asyncio.to_thread, i.e. asyncio's DEFAULT executor; engine/ai sets no other executor, so CPython's default applies: min(32, os.cpu_count() + 4) = 32 on this 32-vCPU box. Pipes are admitted under asyncio.Semaphore(threadCount=64) (data_conn.py:138,477). So one token processes at most 32 documents at once, whatever K or C above 32. the parse provider is a native node (engine/nodes/core/services.parse.json:3, protocol parse://) running Tika 3.2.3 (engine/java/lib/tika-*-3.2.3.jar) in a JVM hosted inside the engine process (no standalone java process in S5-C's snapshots; engine/java/jre ships with the bundle). The C++ binding is compiled into the engine binary and is NOT in this bundle, so a lock inside it cannot be read here — the stamps below bound it instead. engine/java/tika-config.xml:12 excludes OCR; :29 sets PDFParser sortByPosition=true and :30-32 turn on AcroForm, annotation and bookmark extraction — a candidate for the document-intrinsic slow parses (HYPOTHESIS from source, not measured).

Source: `working/results/batchsize_s5_20260921T205917Z/analysis_s5d_parse_concurrency.json`.

### S5-E — the six thread variables unset against = 1, at one token, docs (384-document slice)

RocketRide, continuous C=32, two runs per posture, interleaved; torch intra-op threads read INSIDE the task process: = 1 → [1], unset → [16]. Excluded legs: []. Pre-registered in `preregistration.json` before any leg ran.

| Metric | = 1: runs (spread) | unset: runs (spread) | unset vs = 1 | tolerance ‖ | Reading |
|---|---|---|---|---|---|
| span docs/s — PRIMARY | 2.8287, 2.8182 (spread 0.37%) † | 2.4319, 2.4396 (spread 0.32%) † | -13.73% † | 1.63% | **readable**; beyond the 0.82% floor |
| docs/s to p90 — pre-registered diagnostic | 5.9114, 5.9103 (spread 0.02%) † | 5.0947, 5.0741 (spread 0.41%) † | -13.98% † | 1.63% | **readable**; beyond the 0.82% floor |
| CPU-s per document | 5.7227, 5.7341 (spread 0.20%) † | 7.1489, 7.1548 (spread 0.08%) † | +24.85% † | 1.63% | **readable**; beyond the 0.82% floor |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)
‖ the largest of the 0.82% Stage 3b floor, each posture pair's own spread, and S5-C's null-control spread (same slice) — an effect is read only beyond all of them.

**Cross-session, labelled so.** S5-C ran the same cell — RocketRide, C=32, = 1, unconstrained, this slice — in an earlier session: 2.4273 and 2.4673 docs/s †. This session's = 1 runs average 2.8235 †: +15.4%, after a box restart and with every leg prewarmed. A difference between sessions this large is why a posture cost measured ACROSS sessions was withdrawn from the caveat (register 46), and why S5-E compares postures only inside one session.

### S5-F — SDK default-5 equivalent (PR #1895 / TypeScript maxConcurrent)

RocketRide, continuous C=5, the banked docs posture (= 1), two runs, same session as S5-E. Before it ran, the source it rests on was read and recorded (SOURCE, not measurement): the installed Python SDK's `send_files` gathers one coroutine per file with no client bound (`rocketride/mixins/data.py:719-725`), each waiting in `pipe.open()` for the engine (`data.py:635-638`); our continuous driver sends each document with `client.send()` under `asyncio.Semaphore(C)` (`working/scripts/exp_batchsize_sweep.py:651,656,661`). So C=5 is the client-side bound the TypeScript SDK's default applies, reproduced with the Python primitive; the batch-K labels are restated in §2 for the engine's own bound.

|  | docs/s |
|---|---|
| C=5, runs (spread) | 1.4658, 1.459 (0.46%) † |
| C=5, mean | 1.4624 † |
| C=32 at = 1, this session (S5-E), mean | 2.8235 † |
| C=5 / C=32, same session | 0.518 † |
| Stage 3b, C=4 / C=8 / C=32 — CROSS-SESSION, ranking context only | 1.0764 / 1.8886 / 2.4836 † |

† 32 vCPU unconstrained per Ruling A; same-harness cpuset 0-23 measured -2.5% throughput, -11.7% CPU-s/doc (S5-C; its null control failed at 1.63%, so differences under 1.63% are unreadable)

docs/s to p90 at C=5 (pre-registered diagnostic): 1.4364, 1.432.

Source: `working/results/batchsize_s5ef_20260922T040204Z/analysis_s5ef.json`.

## Not verified / pending

- S5-A: T=1, 2, 4, 8 changed the detector's output against the default cell (see its table) — a tuned thread width is not output-neutral, and its throughput is not a like-for-like speed-up of the same computation.
- S5-C's pre-registered null control failed (spread 1.63%); only differences beyond that spread are read, and the post-hoc view beside it is labelled as such.
- S5-D's instrument moved the leg beyond the floor: its stage SHARES stand; its absolute stage times carry the offset.
- No 10k-scale replicate exists for any K or C: the full-scale K ranking borrows the smoke-slice floors (pre-registered in `envelope_floors.json`) and is therefore an ordering, not a resolved ranking.
- The 168-video RocketRide leg ran once; its absolute frames/s is not quotable (leg-6 rule).
- WITHDRAWN: the earlier RocketRide docs caveat, a posture cost computed ACROSS harness sessions (Stage 3's 24-core cpuset against Stage 3b's 32 vCPU); the caveat now carries S5-C's same-harness figures (register 46).
- WITHDRAWN: an in-session statement that engine memory was flat with K. No memory was sampled during a leg; the cgroup gives a bracket only (§2).
- CORRECTED: an earlier statement (in-session and register 45) that one S5-B frame changed its label set. No label or count changed: one detection's score crossed the edge of Tier 2's threshold band (§6, register 47).
- WITHDRAWN interim Stage 3b figures, reported in-session from scratch analyses that pooled unlike legs: the K=128 means (pooled the cold-cache leg with the warm runs) and LlamaIndex's C=32 cold-vs-warm delta (pooled three worker counts against a 24-worker cold leg). §5 carries the partitioned values from the committed analysis (registers 39, 42).
- Every figure in this summary is read from the analysis file named beside it; the inputs and their sha256s are listed at the end.

## SELF-AUDIT

- **HYPOTHESIS.** Pre-registered, per stage: batch barriers cost a wait for each batch's slowest document (§2); intra-op width can widen one token (S5-A); batched detection is not bit-identical (S5-B); RocketRide pays an SMT tax the other arm does not (S5-C); one token queues small documents at admission behind large ones (S5-D).
- **EVIDENCE.** Every figure above is read from the committed analysis named beside it; the inputs and their sha256s close this document.
- **NULL CONTROLS**, each as it came out:
  - content check across arms (Stage 4): FIRED
  - S5-A output comparator, default cell against its own replicate: 16/16 chunk-identical, score change 0.0
  - S5-B pre-check N1 (single frame reproducible) True, N2 (comparator sees a different frame) True
  - S5-B patched B=1 against stock: {"videos": 16, "chunk_identical": 16, "PASS": true}
  - S5-C two unconstrained RocketRide runs: spread 1.63% against 0.82% — FAILED
  - S5-D instrument against leg 1: -2.06% — OUTSIDE the floor — the instrument perturbed the measurement; decomposition shares stand, absolute times carry the offset
  - output-shift comparator, default vs its replicate: 16/16 chunk-identical, score shift 0.0
  - output-shift comparator, patched B=1 vs default: 16/16 chunk-identical, score shift 0.0
  - Stage 3b provenance: a planted export naming another campaign rejected — True
  - S5-E/S5-F posture read-back: legs excluded for a read-back that contradicts their posture — []
- **REGISTER.** Entries 37-48 were added during this campaign, dated 2026-09-20 or later (working/video/METHODOLOGY_REGISTER.md).
- **NOT VERIFIED.** Listed in the section above; nothing absent from these tables is claimed.
- **GATES.** Every landing passed autoland's gates with an ls-remote read-back; the commits are on `feat/batch-size-optimization`.

## Inputs

- corpus_manifest: `working/results/corpus_manifest.jsonl  sha256:309749a593dd4467`
- envelope_k512_decision: `working/results/batchsize_s4_20260921T013303Z/envelope_k512_decision.json  sha256:b95af235e14a4dda`
- s3b_anchor_docs: `working/results/batchsize_s3b_20260920T203139Z/analysis_docs_anchor96.json  sha256:fa748df66d3f6ad9`
- s3b_anchor_video: `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_anchor.json  sha256:010732c523ba2e17`
- s3b_docs_384: `working/results/batchsize_s3b_20260920T203139Z/analysis_docs_384.json  sha256:790923cee88fa601`
- s3b_provenance: `working/results/batchsize_s3b_20260920T203139Z/provenance_check.json  sha256:9ae2829f8342da90`
- s3b_video_rep: `working/results/batchsize_s3b_20260920T203139Z/video/analysis_video_rep.json  sha256:41096a9002e98164`
- s4_docs: `working/results/batchsize_s4_20260921T013303Z/analysis_docs.json  sha256:3960e78b7b6da56f`
- s4_export_li_p2: `working/results/exp_batchsize_sweep_li__20260921T035607Z__f5a53f343098.json  sha256:fe99b37d36f79809`
- s4_export_rr_p1: `working/results/exp_batchsize_sweep_rr__20260921T024645Z__eebea66604c5.json  sha256:7f69c33de4bd3d81`
- s4_leg_li_refc32: `working/results/batchsize_s4_20260921T013303Z/p2_li_cont/leg_li_refc32_main.json  sha256:8553195e7b793093`
- s4_leg_rr_refc32: `working/results/batchsize_s4_20260921T013303Z/p1_rr_cont32/leg_rr_refc32_main.json  sha256:b7253437c58d14f7`
- s4_perdoc_li_k1024_env: `working/results/batchsize_s4_20260921T013303Z/e12b_li_k1024/perdoc_li_k1024_env.jsonl  sha256:e099a7db6be0bd2b`
- s4_perdoc_li_k128_main: `working/results/batchsize_s4_20260921T013303Z/p4_li_k128/perdoc_li_k128_main.jsonl  sha256:e6073e29963a6a79`
- s4_perdoc_li_k256_env: `working/results/batchsize_s4_20260921T013303Z/e8_li_k256/perdoc_li_k256_env.jsonl  sha256:2f8af95948221557`
- s4_perdoc_li_k512_env: `working/results/batchsize_s4_20260921T013303Z/e10_li_k512/perdoc_li_k512_env.jsonl  sha256:74602bd8e6457c44`
- s4_perdoc_li_refc32: `working/results/batchsize_s4_20260921T013303Z/p2_li_cont/perdoc_li_refc32_main.jsonl  sha256:4576efcff5a782dc`
- s4_perdoc_rr_k1024_env: `working/results/batchsize_s4_20260921T013303Z/e11_rr_k1024/perdoc_rr_k1024_env.jsonl  sha256:17c4cbe7a770bdef`
- s4_perdoc_rr_k128_main: `working/results/batchsize_s4_20260921T013303Z/p3_rr_k128/perdoc_rr_k128_main.jsonl  sha256:fffd53c2e0e34c30`
- s4_perdoc_rr_k256_env: `working/results/batchsize_s4_20260921T013303Z/e7_rr_k256/perdoc_rr_k256_env.jsonl  sha256:f5ceb0de857bc5b4`
- s4_perdoc_rr_k512_env: `working/results/batchsize_s4_20260921T013303Z/e9_rr_k512/perdoc_rr_k512_env.jsonl  sha256:191d8654f1beadd4`
- s4_perdoc_rr_refc32: `working/results/batchsize_s4_20260921T013303Z/p1_rr_cont32/perdoc_rr_refc32_main.jsonl  sha256:18f547b0ec8ab546`
- s4_video_li: `working/results/batchsize_s4_20260921T013303Z/p5_li_video/analysis_video.json  sha256:4a5774041091adde`
- s4_video_li_preflight: `working/results/batchsize_s4_20260921T013303Z/p5_li_video/li_k16/preflight_llamaindex_video_workers_blast.json  sha256:1af0f2e113f0e774`
- s4_video_rr: `working/results/batchsize_s4_20260921T013303Z/p6_rr_video/analysis_video.json  sha256:964b44b5f5d34bf0`
- s4_video_rr_preflight: `working/results/batchsize_s4_20260921T013303Z/p6_rr_video/rr_k16/preflight_rocketride_video_default_blast.json  sha256:3971cea7916a43fe`
- s5_output_shift: `working/results/batchsize_s5_20260921T205917Z/analysis_output_shift.json  sha256:ed74c32b7ee6ddcf`
- s5a: `working/results/batchsize_s5_20260921T205917Z/analysis_s5a_threads.json  sha256:84ad3245c6f7209f`
- s5b: `working/results/batchsize_s5_20260921T205917Z/analysis_s5b.json  sha256:502e7adf9f21a61a`
- s5b_precheck: `working/results/batchsize_s5_20260921T205917Z/s5b_precheck/s5b_precheck.json  sha256:8fe9de23959fe64d`
- s5c: `working/results/batchsize_s5_20260921T205917Z/analysis_s5c_smt.json  sha256:ae16dd791d43088e`
- s5c_for_caveat: `working/results/batchsize_s5_20260921T205917Z/analysis_s5c_smt.json  sha256:ae16dd791d43088e`
- s5d: `working/results/batchsize_s5_20260921T205917Z/analysis_s5d_funnel.json  sha256:d31aceadfc13d961`
- s5d_parse_concurrency: `working/results/batchsize_s5_20260921T205917Z/analysis_s5d_parse_concurrency.json  sha256:f82c978315980ab8`
- s5ef: `working/results/batchsize_s5ef_20260922T040204Z/analysis_s5ef.json  sha256:105074af77166d80`
- slice_9975: `working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json  sha256:607936acc8330d78`
- smoke_video: `working/results/batchsize_smoke_20260920T113000Z/analysis_video.json  sha256:3e50c0d1451fdc06`
- superseded_summary: `working/results/batchsize_final_20260922T023454Z/batchsize_final_summary.json  sha256:412097327e14ffaa`

