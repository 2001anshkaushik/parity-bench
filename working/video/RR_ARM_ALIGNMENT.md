# RR-arm alignment — our track against Shashi's three-track contract (Crossroad 28, 2026-08-21)

**Governing stance (Ansh):** we are the junior arm. Where Leela or Shashi have a
setup or a finding, we **FOLLOW** it or **VERIFY** it — we do not assume our
approach is better because our instrument is newer. The verification artifact
is therefore **Shashi's** (`team_docs_received/VIDEO-BENCHMARK-SETUP-2026-08-21.md`,
Part II: Tier A/B/C, §13–15; his §15 checklist reproduced below). Form from
him, values from measurement. Every contested row reads the same way: *we
measured X; here is the check; one of us has something configured
differently* — never a verdict on anyone's conclusion. Sources quoted as
data with file:line (hard rule, `team_docs_received/README.md`).

Status vocabulary: **PASS** = our export already answers the box as his
checklist asks · **CHANGE** = we would change ours to follow the shared setup
(listed, sized) · **CONTESTED** = a measured divergence; a check is offered,
nothing is adjudicated.

## Shashi's §15 checklist — "a track is on the shared setup when its export can answer all of these from its own recorded fields"

| # | checkbox (S-SET:529-547) | our status | detail |
|---|---|---|---|
| 1 | `pipe_sha256` (and node graph) matches the other tracks | **node graph PASS · sha UNVERIFIABLE · threshold nesting CHECK** | Node graph identical (webhook→frame_grabber→detect→preprocessor_langchain→embedding_transformer→response_documents). Shas differ (ours `6330773f…`, his `b34a1c54…`, S-SET:104) and cannot adjudicate — `project_id` churn, flagged by him (S-SET:345-347) and by us independently. **The check** (one grep per track): does the detect block nest `threshold` under the `rfdetr` sub-object? We nest it (`{"profile":"rfdetr","rfdetr":{"threshold":0.3}}`) because in the pinned 3.3.1 source the explicit-profile branch discards top-level config keys (config.py:196); a top-level threshold would silently run the library default. Neither teammate's doc shows the nesting — it may well already match; looking costs a minute and protects all three. |
| 2 | engine 3.3.1, same boot patches, `engine_boot_patch` string present | **PASS on fact · CHANGE on field** | Same tarball, same two patches (onnxruntime pin; duplication `preventDefault`), read back via image labels per run. We'd add an `engine_boot_patch` string in his wording to our export — one line. |
| 3 | corpus manifest identical: filenames, sha256s, durations | **CHANGE (C28 rules our direction)** | We adopt the teammates' corpus and report view per row. Noted without preference: the two received manifests differ from each other (L-S:210 ami_full 170 muxed Closeup1 · S-SET:206 50 full-length, no-mux, Closeup-first) — the shared manifest is theirs to settle; our cost either way is in `CORPUS_SWAP_COST.md` §C28. |
| 4 | `detect_model` / `threshold` / `embed_model` / `split_length` / `split_overlap` match | **PASS ×4 · `split_overlap` CONTESTED** | rfdetr 1.5.2 `RFDETRBase` thr 0.3 (same package pin, read back in-process each run; weights md5 checked inside both containers), miniLM multi-qa-MiniLM-L6-cos-v1 384-d, split 4000 — all match. `split_overlap`: see Tier A row below. |
| 5 | frame extraction ffmpeg `fps=1/interval`, PNG, both arms | **PASS** | Identical filter and PNG on both our arms; byte-identical frames proven across arms on 83 probe frames. |
| 6 | `timings_valid: true` (x86 native) | **PASS on fact · CHANGE on field** | c7i.8xlarge, native x86 engine. We'd add the `timings_valid` / `engine_native` fields in his names. |
| 7 | `omp_num_threads: 1` on every service | **CONTESTED → we can FOLLOW; check offered** | See Tier B row. To be on the shared setup we set the six vars to 1 (a two-line env change in run_plan); we'd report that configuration alongside our measured-optimum posture, both labeled. |
| 8 | `rr_threads == <competitor workers>`, both recorded | **CHANGE (small) + declared difference** | We record both, but our RR-side instance count is **tokens** (M = LI workers, the parity posture), not the engine's task-thread parameter. To match his knob literally we'd set `use(threads=LI_WORKERS)` on the single-token posture as well — one argument; both values already land in provenance. |
| 9 | `cpuset` recorded, read from cgroup `online_cpus` | **CHANGE (trivial)** | We run uncpuset on both arms (full host, same as his empty string) and read cgroup `cpu.stat`; we'd add the `online_cpus` read-back field. |
| 10 | `ingress` = client upload on both arms | **PASS** | SDK websocket `send()` of the bytes / HTTP `POST` octet-stream; no filesystem shortcut on either arm. |
| 11 | gates present and passing, bands stated: census, structure, `frame_law`, cross-arm frame parity, `chunk_ratio`, `detection_ratio`, `label_overlap`, normalisation parity, determinism | **PASS 6 · CHANGE 2 · `frame_law` CONTESTED (declared)** | census ✓ (frames census + error + index completeness) · structure ✓ (384-d, unit-norm ±1e-3) · cross-arm frame parity ✓ (exact, both arms) · normalisation parity ✓ · determinism ✓ (repeat record, per video). **CHANGE:** `chunk_ratio` is reported-not-gated in ours; we'd adopt his bands (hard 0.8–1.25, warn 0.95–1.05, S-SET:262) as a gate. **CHANGE:** add `detection_ratio` (his 0.90–1.10 warn band) and a Jaccard `label_overlap` field beside our exact per-frame multiset gate — we keep ours, we add his. **`frame_law`** — see Tier B row. |
| 12 | metric coverage gate ran, `problems: []` | **CHANGE** | Ours fails per-gate on absence and carries NOT RUN as a verdict; we'd add a coverage summary in his shape (every asserted metric non-null or exempt, `problems: []`). |
| 13 | V-suite names: `x_realtime`, `effective_cores`, `scaling_efficiency`, `cpu_s_per_footage_min`, `cold_to_ready_s`, `usd_per_1k_footage_hours` | **CHANGE (aliases)** | Same quantities under our names (realtime factor, cores from cgroup, …); we'd emit his names as aliases so the three-way report lines up for free — as he did with Leela's. |
| 14 | TTFR carries its basis string | **CHANGE** | We don't report time-to-first-result; we'd add it with the basis string ("first per-video completion, per-video submission"). |
| 15 | rep count stated; single-rep labelled `INSUFFICIENT_REPS` | **CHANGE → FOLLOW tonight** | Tonight's campaign is PASSES=1; we label it `INSUFFICIENT_REPS` per his rule (our own rule already calls single-rep numbers sizing evidence). |
| 16 | every service-level mirror named and disclosed | **PASS** | `DATAFLOW_PLAN.md` §1: frames and detect are service-level mirrors; SentenceSplitter and HuggingFaceEmbedding run as native LlamaIndex. |

**Scorecard:** PASS 7 · CHANGE 8 (all small; the largest is adopting their
corpus, already ruled) · CONTESTED 3 (`split_overlap`, `omp_num_threads`,
`frame_law` — each with a check below).

## Tier A — must be byte-identical (S-SET:455-464)

| item | ours | theirs | status / check |
|---|---|---|---|
| pipe file | same node graph; nested threshold | same graph; nesting unshown | CHECK — checklist #1 |
| engine release + patches | 3.3.1, both patches, labels read back | same (L-S:26-34, S-SET:183-195) | **PASS** |
| SDK | **1.3.0** — installed wheel, md5-chained freeze | Tier A text: `1.2.0` (S-SET:462); Leela: `1.3.0` (L-S:35) | CHECK — `pip show rocketride` on each box; we follow whatever the contract settles on; the text and at least one box currently disagree, likely a typo |
| corpus | 60 ES Corner, no mux | two different sets (see #3) | CHANGE — we adopt theirs |
| model identities | match (checklist #4) except **split_overlap** | Shashi: 4000/**200**, "the engine's chunk config is INERT — falls through to langchain defaults" (S-SET:123); Leela: 4000/**0**, "reproduces the engine's chunks byte-exactly; 4096 and 3600 do not" (L-S:91-93, L-S:160) | **CONTESTED — a disagreement that is already theirs.** Two byte-level claims about the same engine, made by two seniors. **We are not adjudicating between them.** We are contributing a measurement and a two-minute check: in our engine's real responses we observe duplicated seams between consecutive chunks of the size a 200-char overlap produces (our frame-count recovery strips them; without stripping, counts over-run by 3–12 per video), consistent with Shashi's reading. The check, on any rig: take one captured engine response and count the duplicated suffix/prefix at each chunk seam — overlap 200 leaves them, overlap 0 leaves none. One of the three engines, or one of the captures, has something different in it; the seams say which. |
| frame extraction | ffmpeg `fps=1/15`, PNG | same | **PASS** |

## Tier B — equal-valued, verified from the running system (S-SET:466-477)

| item | ours | theirs | status / check |
|---|---|---|---|
| instance shape | c7i.8xlarge, native x86 | same | **PASS** (add `timings_valid` field) |
| **intra-op threads** | six vars at the **measured per-arm optimum — RR 8** (a 1/8/32 sweep; knee at 8) | **1 on every service** (S-SET:173, L-D:198) — rationale: intra-op threading is a confound against document-level concurrency, measured 528 vs 260 CPU-s | **CONTESTED → we can follow; check offered.** We measured, on one video, single token, same engine: **2.3 cores at OMP=1 and 8.5 at OMP=8** (wall 85 s → 16 s); at 32 the wall doubled while CPU-seconds held — a separate note. Our OMP=1 point (2.3) sits beside Shashi's 2.42 and both sweeps in their docs varied the task-thread knob with the six vars held at 1 — so the three datasets are consistent with each other; they differ in which knob was turned. **The check:** one video on each rig with all six vars at 8. If the shared contract is OMP=1 we run it (two lines) and report both configurations labeled; the contract just picks its value with the curve in view. |
| document concurrency | tokens == LI workers (parity) + single-token posture | `RR_THREADS == workers` | CHANGE (small) — checklist #8 |
| CPU allocation | uncpuset both arms | identical cpuset, read from cgroup | CHANGE (trivial) — checklist #9 |
| ingress | client upload | same | **PASS** |
| return payload | documents + embeddings on both arms | same | **PASS** |
| span discipline | warm outside span; cgroup sampled over the leg | same | **PASS** |
| mode discipline | seq / blast(c=C) never blended; postures labeled | seq / blast(native batch) / c\<N\> | declared difference — his blast is one atomic `send_files`, ours is per-video at fixed C. Both honest; never mixed. His §14 asks how an RR c\<N\> should be offered before "inventing a second answer" — ours is per-video sends at fixed client concurrency; offered as one existing implementation, his to compare. |
| `frame_law` | expectation **measured per video** (ffmpeg emission count at manifest build), exact | `⌊duration/15⌋+1 ±1` vs manifest (S-SET:260, L-M:34) | **CONTESTED (declared).** We measured ffmpeg emitting 83 frames on a 1248.3 s stream where the formula predicts 84 (the final slot does not open), so we replaced the formula with the measured count rather than widen a tolerance. Leela's `frame_law` also reported 2/6 videos failing identically on both her arms (L-R:145) — she traces it to audio-vs-video stream length in muxed files. **The check:** one video's actual emission count vs `⌊d/15⌋+1` on each rig. We would also emit his `frame_law` value in our export for comparability, labeled beside our measured column. |

## Tier C — may differ, disclosed identically (S-SET:479-487)

Service-level mirrors (named, #16 PASS) · API shape (his atomic batch vs our
per-video — disclosed, TTFR to carry its basis) · `framework_overhead` (LI
carries `stage_s` per response; RR is a black box on every track — stated)
· parity band width (ours is an independent implementation; we adopt his
suggested long-form bands) · pipe composition (same pipe all three; the
RR core constant is then the B-tier thread question, not composition).

## Unresolved between the seniors, where we hold no data

Storage amplification: Leela ~1.0× retained through `terminate()` (L-S:37-40,
L-D:161-168); Shashi net 0.0 (S-R:77-80); both flag it (S-SET:515-519).
**UNKNOWN for us** — we have not measured it. Noted only because our run plan
keeps the RR container up across postures, so whichever reproduces affects
our disk planning; we will read our own writable-layer delta after tonight's
campaign and report it beside theirs, not in place of them.

## What we change to be "on the shared setup" (our FOLLOW list)

Export fields in his names (`engine_boot_patch`, `timings_valid`,
`online_cpus`, V-suite aliases, TTFR + basis, coverage summary,
`INSUFFICIENT_REPS` label, `detection_ratio` + Jaccard `label_overlap`,
`chunk_ratio` bands as a gate, his `frame_law` value beside ours) — all
small, all additive, none removes a measurement of ours. Plus the corpus
(ruled) and, if the contract lands there, the six vars at 1 with our
measured-optimum posture reported alongside.

## What stays contested until a check runs (our VERIFY list)

`split_overlap` (seam check) · intra-op threads (one BLAS=8 video per rig) ·
threshold nesting (one grep per pipe) · `frame_law` (one emission count) ·
SDK version in the contract text (`pip show`). Each is minutes; none requires
anyone to accept a conclusion from us first.
