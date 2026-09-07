# DOCS HANDOFF — WS-1 document-workload re-run

**Repo path:** `working/docs/DOCS_HANDOFF.md`
**Branch:** `video-bench` (travels to `docs-bench` unchanged when that branch is cut — see §5)
**Written:** 2026-09-07
**Supersedes pasted context.** Read this file instead of asking for a summary.

This document has two readers.

* **The Advisor** reads §0–§9 for context and rulings.
* **Claude Code** reads §0, §1, §2, §5, §8 and §10 for what to build, verify and refuse.

Everything below carries an evidence label. Nothing is asserted from memory.

| Label | Meaning |
|---|---|
| `[VERIFIED 2026-09-07]` | Re-derived this session from the committed artifact named. Trust it. |
| `[REPO]` | Stated in a committed file at the path given. Trust the file, not this summary. |
| `[PRIOR-RECORD]` | Carried from a previous session's context. **Not** confirmed against an artifact. Confirm before quoting. |
| `[HYPOTHESIS]` | Not measured. Reasoning only. |

---

## §0. Status board

### The load-bearing fact — read this before anything else

> **EVERY DOCS NUMBER WE HOLD WAS MEASURED WITH ROCKETRIDE AT ONE TOKEN.**

The banked docs comparison is **a tuned LlamaIndex against RocketRide's default posture.** It is not a framework comparison. Full verification in §1.

### Settled

1. All three docs legs ran at M=1 token. Verified from source, not inferred. (§1)
2. The 18-Aug 10k runs **were** on the patched engine, despite their own exports saying otherwise. The exports carry a hardcoded false provenance field that is still live on both branches today. (§2.4)
3. Our duplication patch works, proven three ways: artifact grep, exactly-halved fixture, and exactly-halved corpus maximum at 10k scale. (§2.2)
4. Only ~6% of the GovDocs corpus is eligible for the duplication bug at all. (§2.3)
5. Every 18-Aug docs run carries ~8 cores of background load. The 16-Aug pair is clean. Both were equally pinned. (§3.2)
6. The engine's splitter config is inert; LangChain defaults 4000/200 run instead. (§4)
7. The docs driver is already on `video-bench`. Branch from it; do not merge. (§5)

### Open

1. Whether the **current stock engine** fixes duplication natively. This is the re-run's question, and no test of it exists. (§2.5)
2. Where RocketRide's posture optimum sits for a parse-bound workload. Unknown; the video 5.21× does not transfer. (§6.1)
3. Whether GovDocs1 is still on the box, and at what SHA. (§5.4)
4. Whether the docs metric set survives contact with a multi-token posture. (§6.3)

### The first decision

**Do not run anything yet.** The first decision is §10.1 — fix `provenance_leela.py` before any leg runs, because every run made against it produces a false comparability record. It is a ten-line fix and it gates the campaign.

---

## §1. The load-bearing fact, verified

### 1.1 What the claim is

The video campaign measured RocketRide's throughput ceiling as **per-token, not architectural**: default posture (1 token, thread env unset) at 2.443 f/s and ~18.8% box utilisation, against parity posture (16 tokens, six BLAS/OMP vars = 2) at 12.729 f/s and 91.7% — **5.21× on span, pass-to-pass spread 0.19%**. `[PRIOR-RECORD — the campaign figures live in working/video/WS1_Phase2_Video_Benchmark_DEFINITIVE.md; confirm there before quoting]`

That finding is dated **24 August**. The docs runs are dated **16–18 August**. It was never applied to documents.

### 1.2 Verification from the docs-era code — all three legs

I checked every `use()` call site that a measured docs leg passes through. `[VERIFIED 2026-09-07]`

**Sequential leg** — `weekend_worker.py`, `RocketArm.__init__` (the base class `RocketPdfArm` inherits):

```python
self.c = RocketRideClient()
self.loop.run_until_complete(self.c.connect(timeout=60000))
r = self.loop.run_until_complete(
    self.c.use(filepath=str(p.relative_to(ROOT)), ttl=RR_TTL_S))
self.tok = r["token"]
```

One `use()`. **No `threads=`.** `RocketPdfArm.process()` sends every document through that single `self.tok`.

**Per-document blast leg** — `working/scripts/smoke50_parser_in.py:862`:

```python
tok = (await c.use(filepath=str(pp.relative_to(ROOT)),
               ttl=rrc.RR_TTL_S))["token"]
sem = asyncio.Semaphore(BLAST_C)
...
o = await asyncio.wait_for(c.send(tok, b, mimetype="application/pdf"), timeout=300)
```

One `use()`. **No `threads=`.** All N documents fan out across a client-side semaphore onto **that one token**.

**Batched leg** — `working/scripts/exp_batched_blast.py:216`:

```python
used = await c.use(filepath=str(pipe_path.relative_to(ROOT)), ttl=RR_TTL_S,
                   threads=RR_THREADS)
```

One `use()`, with `threads=RR_THREADS`. `RR_THREADS = int(os.environ.get("SMOKE_RR_THREADS", "24"))` at `:68`.

### 1.3 The recorded provenance agrees

All four `exp_batched_blast__20260818T*.json` exports record `threads_requested = 24` and `threads_observed = None`. `[VERIFIED 2026-09-07]` The `None` is deliberate and correct — requested ≠ activated ≠ effective, and only the last is measurable. `[REPO — the reasoning is in exp_batched_blast.py's own comments]`

### 1.4 The ruling

**No docs leg ran multi-token. The claim stands as stated, and is now source-verified rather than assumed.**

One nuance Claude Code must not lose. `threads=24` on the batched arm is **not** a second token. The engine's token topology is one `use()` = one token = one Task = one OS subprocess, with one model set per subprocess serialised by a process-local `threading.Lock`; `threads=` adds *item* concurrency that queues at that lock and does not parallelise the model stage. `[PRIOR-RECORD — proven from 3.3.1 source in the video phase; the source trace is summarised in working/video/PHASE1_CARRYOVER.md and REPRO_PARITY_POSTURE.md. Re-verify against the engine source before the re-run designs its posture sweep.]`

So the batched leg is *also* default posture. All three legs sit at M=1.

### 1.5 What this does to the banked comparison

The LlamaIndex arm was tuned — 24 workers, thread-pinned, warm-started. The RocketRide arm was at its out-of-box default. Both facts are true and neither was a mistake at the time; the token dimension had not been discovered.

**Consequence for the re-run:** the banked docs headline is a *default-posture* result. It remains publishable as exactly that, and it is a genuine product finding (out of the box, on a document workload, this is what a developer gets). It is **not** a statement about the two frameworks at their best, and it must never be presented as one.

---

## §2. The duplication question, made precise

### 2.1 The mechanism, from the filed bug

`nodes/embedding_transformer/IInstance.py` — `writeDocuments()` returns `preventDefault()` on the buffer path but **not** on the flush path. Once the buffer reaches `maxDocuments = 64`, the node writes the batch downstream *and* the engine forwards the original event, so the complete chunk list is emitted exactly twice. `[REPO — filed as BUG_CHUNK_DUPLICATION.md; root-caused in source by Shashi]`

**The predicate is ≥64 chunks, not a character count.** An earlier ~239,800-character threshold was a proxy (64 × ~3,750) and is superseded. `[PRIOR-RECORD]`

### 2.2 Evidence our patch works — three independent methods

**(a) The artifact grep.** `grep -c preventDefault` on the engine's own `IInstance.py` inside the built image returns **1 in stock, 2 in patched**. The patch is present in the artifact, not merely in metadata. `[PRIOR-RECORD — confirm by re-running the grep inside both images; it is cheap]`

**(b) The halved-count fixture.** Five duplication-fixture documents, stock vs patched, same day, same box:

| Document | stock chunks | patched chunks | ratio |
|---|---|---|---|
| `000_000159` | 164 | 82 | 2.000 |
| `000_000595` | 276 | 138 | 2.000 |
| `000_000674` | 1872 | 936 | 2.000 |
| `000_000762` | 132 | 66 | 2.000 |
| `000_000887` | 344 | 172 | 2.000 |

`repeat_factor` 2 → 1, `self_duplication` 5/5 → 0/5. `[VERIFIED 2026-09-07 — both artifacts committed: smoke_phase2__20260818T035137Z__4a2b2bb35b79.json records expect_patch=False, label_raw=0, all five records repeat_factor=2; smoke_phase2__20260818T035559Z__5131e250d300.json records expect_patch=True, label_raw=1, all five repeat_factor=1]`

**Exact halving is the strongest available proof** — the patch removes precisely the phantom copy and nothing else. A patch that changed chunking would not land on 2.000 five times.

**(c) The corpus maximum at 10k scale.** New this session, and it corroborates (b) by a completely different route — output shape rather than metadata: `[VERIFIED 2026-09-07 from the committed per-document records]`

| Run | dir | max chunks/doc | mean | median |
|---|---|---|---|---|
| 16-Aug (stock) | `working/results/run10k/perdoc_rr_blast.jsonl` | **2754** | 29.9 | 8 |
| 18-Aug (patched) | `working/results/run10k_p2_blast_v2/perdoc_rr_blast.jsonl` | **1377** | 20.7 | 8 |

2754 / 1377 = **2.000**, on the same corpus family. The patch's fingerprint is visible in the banked records.

**(d) `self_duplication` at 10k.** 0/9,872 LlamaIndex and 0/9,847 RocketRide. `[PRIOR-RECORD — from rederive_gates__20260818T140635Z__ef789985f863.json, which IS committed; read the file rather than quoting this line.]` Note the caveat in §2.3 before using it.

### 2.3 The ≥64-chunk predicate — and why the denominator matters

Measured on the committed records: `[VERIFIED 2026-09-07]`

| Run | successful docs | docs ≥64 chunks | share |
|---|---|---|---|
| 16-Aug stock `run10k` | 9,985 | **601** | 6.02% |
| 18-Aug patched `run10k_p2_blast_v2` | 9,936 | **595** | 5.99% |

Median chunks/doc is **8**. At LangChain's 4000-character default (§4) the typical GovDocs document produces nowhere near 64 chunks, so **94% of the corpus cannot trip the bug at all.**

**Ruling for the re-run:** `self_duplication` must report against the **eligible denominator** (documents ≥64 chunks), not the corpus. "0 duplicated out of 9,847" is nearly vacuous — 9,250 of those documents were never at risk. The honest figure is "0 of ~595 eligible". A gate that cannot state its own denominator is not evidence.

This also sizes the re-run: any duplication test needs a corpus slice that actually contains ≥64-chunk documents, and the five-document fixture exists precisely because it does.

### 2.4 🚩 The exports lie about patch status — and it is still live

`working/harness/provenance_leela.py` hardcodes the field as a literal: `[VERIFIED 2026-09-07]`

```python
"rocketride_engine_version": "3.3.1",
# STOCK. Leela builds patched by default (RR_DUP_PATCH=1). Measured exposure on our
# corpus: 5/199 documents at repeat_factor 2. A patched result is not comparable
# with this one, and this field is the only thing in the file that says so.
"duplication_patch_applied": False,
"duplication_patch_id": None,
```

`main` line 132, `video-bench` line 140. **Unconditional. Never fixed. Live on both branches today.**

The tell that it carries no information: it reports `False` on the **LlamaIndex arm too**, which has no RocketRide engine to patch. A field that fires identically on an arm that cannot have the property is a harness defect, not a measurement — the same signature the campaign already learned to read from the gate-contradiction root cause.

**What actually ran, established two ways:** `[VERIFIED 2026-09-07]`

| Digest | Identity | Evidence |
|---|---|---|
| `sha256:5e83c803…` | `rr:stock` | appears only in `smoke_phase2__20260818T035137Z` — `label_raw=0`, fixture `repeat_factor=2` |
| `sha256:073b43d8…` | `rr:patched` | in `smoke_phase2__20260818T035559Z` and `…074453Z` — `label_raw=1`, fixture `repeat_factor=1` |
| `sha256:3d2f1f43…` | `ws1-llamaindex:x86_64` | in every 18-Aug artifact |

`smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json` records `provenance_leela/rocketride_pdf/image_digest = sha256:073b43d8…` — **the patched digest** — while the same file's `duplication_patch_applied` reads `False`. The same holds for `…155557Z` and all four `exp_batched_blast__20260818T*` exports.

Corroborated independently by §2.2(c): the halved corpus maximum. Metadata and output shape agree.

**Ruling.** The 18-Aug measured docs runs were on `rr:patched`. Their exports' `duplication_patch_applied: False` is false. This matters beyond bookkeeping: Leela's `check()` treats that field as load-bearing for comparability, so anyone applying his rule to our exports concludes our headline run is not comparable with his patched runs — when in fact both are patched. **We owe him a correction, and the fix gates the re-run (§10.1).**

### 2.5 What a test of the CURRENT stock engine would have to show

The re-run's question is not "does our patch work" — that is answered (§2.2). It is **"does the engine now fix it natively."** Four things, in order, and the fourth is not optional.

1. **Source check.** `grep -c preventDefault` on the *current* shipping engine's `nodes/embedding_transformer/IInstance.py`. Stock 3.3.1 returns 1. A return of 2, or any equivalent guard on the flush path, is the source-level fix. Read the flush path, do not trust the count alone — a different fix shape would not change the count.
2. **Artifact check.** Build the current engine with **no patch of ours applied** and run the five-document fixture. Fixed ⟺ all five return `repeat_factor=1` *without* `RR_DUP_PATCH`.
3. **Scale check.** `self_duplication` = 0 over the eligible ≥64-chunk denominator (§2.3), not over the corpus.
4. **Null control — mandatory.** The identical test run against a known-stock 3.3.1 image must report `repeat_factor=2` on the same five documents. Without it, step 2 is a check that can only pass: a broken fixture, a mis-wired lane, or a document set with nothing eligible all produce "no duplication found". `rr:stock` at `sha256:5e83c803…` is the null-control image if it still exists on the box; if not, rebuild it with `RR_DUP_PATCH=0`.

**Precedent:** this is register entry 2 ("self-consistency is not evidence — the check must cross an independence boundary"), `working/video/METHODOLOGY_REGISTER.md:24`.

### 2.6 Which images exist

| Image | Digest | What it is |
|---|---|---|
| `rr:stock` | `sha256:5e83c803…` | 3.3.1, `RR_DUP_PATCH=0`, `label_raw=0`, grep 1. The null control. `[VERIFIED]` |
| `rr:patched` | `sha256:073b43d8…` | 3.3.1 + `preventDefault-after-embedding-flush`, `label_raw=1`, grep 2. Every 18-Aug docs number rides this. `[VERIFIED]` |
| `ws1-llamaindex:x86_64` | `sha256:3d2f1f43…` | The docs LlamaIndex arm. No pin-locked Dockerfile — a rebuild resolves differently and cannot reproduce it. **Do not delete.** `[VERIFIED digest; PRIOR-RECORD on the no-rebuild ruling — Crossroad 19]` |
| two 17-Aug images | `sha256:500c5d77…`, `sha256:6699e9d4…` | Pre-Phase-2. Carry the fault-isolation and data-isolation runs. `[VERIFIED digests; arm attribution unchecked]` |
| `rr:patched-video` | — | The baked video image. **Not bit-reproducible**, and on `box.sh`'s hard refusal list. Every RocketRide number in both video campaigns rides it. Never remove. `[PRIOR-RECORD]` |

Box residency of all of these is **UNVERIFIED** — see §5.4.

---

## §3. The banked docs figures

### 3.1 Posture and provenance common to the 18-Aug set

`[VERIFIED 2026-09-07 from smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json]`

* Corpus `22177c33c3651fceceef99ba5c5c2d89f9bbe270dddc23e9943c6e20b421508c`, **n = 9,975** (not 10,000 — see below)
* Instance `c7i.8xlarge`; engine 3.3.1; SDK 1.3.0; embedding `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`
* Parsers **differ by arm**: RocketRide Tika, LlamaIndex `pypdf`
* `offered_concurrency` 32, `configured_concurrency` 24, `timeout_s` 1800, ttl 7200
* Both arms pinned: `OMP_NUM_THREADS=1` measured **inside the engine task process**, torch intra=1 / interop=16, LlamaIndex per-worker `[[1, 16]]`
* Engine image `rr:patched` (§2.4) — **regardless of what the export's patch field says**
* `git_commit = 9b7c654…-dirty` — ⚠️ **the tree was dirty at run time.** The commit does not fully describe the code that ran.

**N=9,975, not 10,000:** the corpus holds exactly 10,000 documents and the warm-up guard requires 25 disjoint documents beyond N, so it refused (exit 7) rather than silently reusing measured documents. 9,975 measured + 25 warm = 10,000. This is the guard working as designed and must be **stated**, since Shashi runs a true 10,000. `[PRIOR-RECORD — confirm against the run's own warm-up block]`

### 3.2 🚩 The load qualifier — measured, not asserted

Background load, read from `load1` in the committed sampler streams: `[VERIFIED 2026-09-07]`

| Run dir | stream | n | load1 min | median | max |
|---|---|---|---|---|---|
| `run10k` | `sampler_rr_blast` | 500 | **3.84** | 34.55 | 37.80 |
| `run10k` | `sampler_li_blast` | 313 | **4.14** | 32.88 | 33.51 |
| `run10k_blast_v1` | `sampler_rr_blast` | 496 | **3.74** | 34.51 | 38.33 |
| `run10k_p2_blast` | `sampler_rr_blast` | 802 | **21.93** | 66.88 | 90.24 |
| `run10k_p2_blast_v2` | `sampler_rr_blast` | 718 | **15.37** | 36.69 | 44.46 |
| `run10k_p2_blast_v2` | `sampler_li_blast` | 476 | **12.05** | 33.05 | 33.60 |
| `run10k_p2_blast_v2` | `sampler_rr_sequential` | 185 | **10.18** | 10.35 | 11.35 |
| `run10k_p2_blast_v2` | `sampler_li_sequential` | 81 | **9.84** | 10.02 | 10.09 |
| `batched_20260818T133821Z` | `sampler_rr_batched` | 1046 | **9.15** | 31.50 | 35.86 |

The 16-Aug floor is ~4. Every 18-Aug floor is ~9–22. The sequential legs are flat at min≈med≈max≈10 while their arms used ~1–2 cores — **the steady-hog signature**, not workload.

Cause: an unbounded self-respawning `md5sum /dev/zero` keep-alive whose parent shell started **18-Aug 02:15:20** and ran until it was killed 21-Aug 01:18. `[PRIOR-RECORD — the kill and the load-average collapse from 17 to 1 were observed live]` The load1 floors above are the independent artifact-side confirmation, and they are new this session.

**This resolves the tension the record left open.** All three runs were equally pinned (§3.1). So:

| | pins | duplication patch | cpuset | load |
|---|---|---|---|---|
| 16-Aug `run10k` | ✅ | ❌ stock | ❌ full 32 | ✅ **clean** |
| 17-Aug re-run | ✅ | ❌ stock | ❌ full 32 | ✅ **clean** |
| 18-Aug `run10k_p2_blast_v2` | ✅ | ✅ patched | ✅ 0-23 / driver 24-31 | ❌ **~8 cores** |

**Neither pair is clean on all four axes.** Do not let a fresh session "reach for the 16-Aug numbers because they're load-clean" — they are stock and un-cpuset. State the trade explicitly wherever either is quoted.

**Direction of the load bias, and what survives it.** The hog was common-mode: it ran across both arms and across both submission shapes on the same days. So **within-18-Aug comparisons are far more robust than any 18-Aug absolute figure.** The batch-vs-per-document delta (§3.5) was measured under contamination on both sides and the ratio very likely survives; the absolute docs/s figures do not. `[HYPOTHESIS on the magnitude — the contamination is measured, its effect on the ratio is reasoned, not measured. A lifetime-controlled re-take is the way to settle it, as the films campaign did.]`

### 3.3 Quotable

With the §3.2 qualifier attached, every time.

**18-Aug 10k per-document blast** (`smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json`, records in `run10k_p2_blast_v2`) `[PRIOR-RECORD on the metric values — the artifact is committed; read it rather than quoting this table]`

| | LlamaIndex | RocketRide |
|---|---|---|
| docs/s | 4.1887 | 2.7762 |
| chunks/s | 81.84 | 57.39 |
| p50 / p95 | 3.058s / 28.21s | 4.785s / 31.21s |
| cpu_s/doc | 4.5127 | 5.9829 |
| effective cores | 18.90 | 16.61 |
| utilisation | 78.8% | **69.2%** |
| cgroup anon peak | 17,594.4 MB | 14,018.8 MB |

**18-Aug 10k batched** (`exp_batched_blast__20260818T150551Z__373adce246fc.json`): 1.9098 docs/s, 40.5112 chunks/s, wall 5,176.5s, `cpu_utilization` 0.5038, effective cores 12.09 of 24, ok 9,886/9,975.

**Fault isolation** (`exp_fault_isolation__20260817T064530Z__9497165fe2a1.json`, VERDICT PASS): both arms `collateral_failures = 0`, `batch_survived`, `service_alive_after`, `recovery_ok`. The real finding is **surfacing** — LlamaIndex returned `service_error`; RocketRide returned `no_documents`, a **success-shaped empty response** operationally indistinguishable from the ~88–102 legitimately empty PDFs in the same corpus.

**Data isolation** (`exp_data_isolation__20260817T065922Z` null control + `…072129Z` disjoint): cross-tenant chunks / docs / vectors all **0** on both arms, with the null control at overlap 1.0 proving the detector can see shared content.

**Lines of code, as-built**: 3.1× (557 vs 179) by LOC, 2.7× by semantic units, 4.9× by canonical bytes. COSMIC functional size **4 CFP on both arms**. `[PRIOR-RECORD]`

⚠️ Both isolation runs are **17-Aug, pre-Phase-2** — different images (`500c5d77`/`6699e9d4`), stock engine, no cpuset. Do not table them beside 18-Aug throughput without saying so.

### 3.4 Superseded

* **16-Aug 10k blast** (LI 6.4007 / RR 4.0271) — superseded on the clock defect by the 17-Aug clean-clock re-run (LI 6.3586 / RR 3.9930), and on config by 18-Aug. Retains value as the **load-clean** reference point.
* **All 200-document throughput figures** — structurally biased low. At n=200/C=32 there are only ~6 waves and the span is set by the slowest document in each; at 10k there are ~312 and it converges. A 200-doc and a 10k figure **cannot go in the same table in either direction.**
* **The N=1,000 batched probes** — invalidated by the unpinned-engine defects, then re-taken pinned at 49.7%.
* **The 52.8% / 52.9% Shashi corroboration** — VOID as an exact match; measured with the engine unpinned at torch=16. The honest version is 49.7% pinned vs his 52.9%, on different corpora: same regime, not the same number.
* **Every macOS number**, including the 314.5s stalled document, which did not reproduce on Linux.

### 3.5 The batch-API finding — the docs phase's strongest result

Same corpus, same box, same pins, same patched engine, one harness:

| RocketRide submission shape | docs/s | chunks/s | utilisation | effective cores |
|---|---|---|---|---|
| **Per-document** at C=32 | **2.776** | 57.39 | **69.2%** | 16.61 / 24 |
| **Native atomic `send_files`** | **1.910** | 40.51 | **50.4%** | 12.09 / 24 |

**Per-document is ~45% faster and uses far more of the machine. The batch API is the bottleneck, not the engine.**

Why this is the strongest thing the docs phase produced:

1. **It is a controlled experiment, not an inference.** Nobody else ran both submission shapes under one harness, one box, one corpus. Shashi measured 52.9% on the batched arm and hypothesised head-of-line blocking; we have the control that his run lacked.
2. **It converts a loss into a fixable defect.** His 2.07× GovDocs deficit becomes a named API/scheduler issue rather than an engine-speed verdict.
3. **It survives the scale objection.** Batched utilisation is ~50% at *both* n=1,000 (49.7%) and n=9,975 (50.4%), so it is not the finite-wave effect our own queueing analysis would otherwise predict.
4. **Both sides carry the same load contamination** (§3.2), so the ratio is the robust part.

⚠️ One withdrawal to keep straight: a mid-run reading of instantaneous `docker stats` (1788%, 1767%) was used to argue the starvation finding should be withdrawn. That was wrong — those were steady-state samples, and the **measured windowed average is 50.38%**, with the tail drain at ~237% pulling it down. The tail drain *is* the head-of-line blocking. The withdrawal was withdrawn. `[PRIOR-RECORD — the 0.5038 figure is in the committed export; the narrative is not]`

### 3.6 Never quote

* Any `peakRSS` from before commit `e1167121` — summed per-process RSS, over-counted, and the bias **scales with process count**, so even the LI/RR ratio is unsalvageable.
* **84,960.6 MB** for RocketRide — a summing artifact against a 58 GB cap. The number surviving *is* the proof it is not a footprint.
* **"RocketRide ~6.9× lighter"** — both sides were post-leg point samples taken after the leg closed. RocketRide's post-leg reading was 135.3 MB against a true sampled peak of 16,397.0 MB. Quote 1.42× from the 10k blast.
* **RocketRide `blast_batchpos` latency from `run10k_p2_blast_v2`** — corrupted at *every* `warm_n`. `enqueue_ns` was stamped once before both runners, so RocketRide's batch-open stamp predates its own leg by the whole LlamaIndex leg. Measured stale gap: **2,388.6s** on RocketRide, 0.3s on LlamaIndex. The `warm_n=64` closed-loop figures are the valid ones.
* **The 371 `PipeException` failures** as a RocketRide reliability result. Self-inflicted: the submission-gap check returned exactly **1800.0s** at index 9,629 — precisely our own client deadline — against the engine's 900s default idle ttl. The engine did what it documents. This is a harness footnote, never a product finding.
* **The gate FAIL verdicts on the 18-Aug per-document blast** — census printed "offered 9975 = successful 0" on both arms despite 9,975 records existing on disk. The gate path evaluated the empty sequential record set. Use `rederive_gates__20260818T140635Z__ef789985f863.json` instead.
* **`duplication_patch_applied` from any measured docs export** — §2.4. Read the `image_digest` instead.

---

## §4. The engine's inert splitter config

### 4.1 What it is

`preprocessor_langchain`'s `_filter_kwargs_for` (3.3.1 `langchain.py:96-99`) keeps only kwargs **named in the splitter constructor's explicit signature**. `RecursiveCharacterTextSplitter.__init__` names only `separators`, `keep_separator`, `is_separator_regex` — while `chunk_size`, `chunk_overlap` and `length_function` ride in `**kwargs`.

The engine's own settings therefore filter to `{}` and the splitter runs at **LangChain library defaults, 4000/200.** `[REPO — filed as Ticket 3 BUG_CHUNK_CONFIG_IGNORED in working/upstream/RocketRide_Engine_Tickets.md; reproduces on langchain-text-splitters 0.3.8 and 1.1.2, so the finding is version-robust]`

`strlen`, the profile values, `mode`, and the node's own `chunk_size`/`chunk_overlap` lines are **all dead config**. Only `separators` survives the filter.

This vindicated Phase 1 rather than damaging it: the docs arm's exported 4000/200 and its `chunk_config_parity` gate matched deployed reality. The measured records agree — mean chunk chars ~3326–3468, max ~3993, the 4000 ceiling showing through. `[PRIOR-RECORD from query_phase1_chunks_20260820T223826Z.json; the median-8-chunks/doc figure is VERIFIED 2026-09-07 from the committed per-document records]`

### 4.2 What it does to a chunk-conservation gate on documents

**Size is clean. Overlap is not.**

`_merge_splits` retains only **whole split units**. The engine's effective overlap is therefore **0 whenever a split unit exceeds the 200-character overlap window**, while LlamaIndex realises the full ~200.

On video this was crisp and constant: each per-frame detection line was ~1,726 characters, always over 200, so RocketRide's effective overlap was **always 0** and `char_conservation` failed at a systematic **4.86%** across every cell. Correcting each LlamaIndex video for `200 × (n_chunks − 1)` moved the ratio median from 0.9528 to 1.0021, with no video below 1.0. `[PRIOR-RECORD from the AMI campaign]`

**Documents are different, and worse — the bias is not a constant.** Prose splits on paragraph and sentence boundaries, so split units vary from a few characters to several hundred. Some units fall under 200 and RocketRide realises overlap on those seams; others exceed it and realise none. So:

> On documents, a chunk-conservation gate's expected value is neither 1.0 nor a fixed offset. It is a **corpus-dependent function of the split-unit length distribution.** `[HYPOTHESIS — the mechanism is source-verified, the document-side magnitude has never been measured]`

**Ruling.** A `char_conservation` or `chunk_ratio` gate must be **characterised before it gates**. Run it advisory on the banked records first, measure the distribution, and only then set a band. A hard band adopted from the video regime would be wrong by an unknown amount in an unknown direction.

**The fix to adopt regardless:** set the **LlamaIndex comparison arm's splitter to 4000/0**, matching what the engine actually realises rather than what it declares. Leela did exactly this and her `chunk_ratio` came into band. `[PRIOR-RECORD — her setting is pinned at 313430f3 per team_docs_received/README.md]`

**The lesson in one line, and it belongs in the report:** *configuration parity is not realisation parity.*

---

## §5. Branch strategy

### 5.1 What actually transfers — verified, and it changes the answer

I expected to have to move the docs driver across. **I do not.** `[VERIFIED 2026-09-07 — `git checkout video-bench` then file-by-file existence check]`

Already present on `video-bench`, unchanged and ready:

| Path | Role |
|---|---|
| `weekend_worker.py` | the arms — `RocketPdfArm`, `LlamaHttpPdfArm` |
| `working/scripts/smoke50_parser_in.py` | **the docs driver** — sequential + per-document blast legs |
| `working/scripts/exp_batched_blast.py` | the batched arm |
| `working/scripts/smoke_phase2.py` | the docs pre-run smoke, incl. the duplication fixture |
| `working/scripts/rederive_gates.py` | post-hoc gate re-derivation, no service contact |
| `working/harness/{gates_shared,metrics_shared,provenance_leela}.py` | gates, metrics, provenance |

`video-bench` forked from `17f77aa`, which already carried the whole docs tree.

**Video-bench-only, and load-bearing:** `working/harness/box.sh` exists on `video-bench` and **not on main** (the `video-bench`→`main` diff reports `D working/harness/box.sh`). Same for `docker/Dockerfile.llamaindex-video` and the entire `working/video/` tree — the register, the figure checker (`working/video/probe/end_to_end_figures_check.py`), the gate suite and the landing discipline.

**Main-only:** **128 files under `working/results/`** — the 18-Aug docs artifacts (`run10k_p2_blast*`, `batched_20260818T*`, the `smoke50_parser_in__20260818T*` and `exp_batched_blast__20260818T*` exports). These arrived via `88eeef7` → `c06673a` and never reached `video-bench`.

### 5.2 What is video-shaped and needs adapting

* **`box.sh`** — transfers unchanged. Its refusal list is image- and command-shaped, not workload-shaped. Add `rr:patched` / `rr:stock` to the refusal list if they are not already there, on the same grounds `rr:patched-video` is: every 18-Aug docs number rides `073b43d8`, and it is not bit-reproducible.
* **The gate suite** — split. `index_completeness`, `embed_integrity`, `determinism_repeat`, `thread_pins_by_arm` and `log_attribution` transfer as-is. `label_multiset_agreement` and `score_triage` are detection-specific and have **no docs analogue** (§6.2). `char_conservation` transfers in *form* but its band must be re-derived (§4.2).
* **The posture sweep and the C chain** — the *method* transfers, the *values* do not (§6.1).
* **The figure checker** — transfers as a mechanism; its checks are written against video report sections and need docs equivalents authored. See §7.3 — this goes in **first**, not last.
* **The landing discipline** (register entry 26) — transfers unchanged.

### 5.3 The recommendation

**The Current Decision.** Whether the docs re-run merges `main` into `video-bench`, cherry-picks the docs work forward, or branches from `video-bench`.

**The Trade-offs.** A merge looks natural and is the trap. `main` is **older** on five shared harness files — `gates_shared.py`, `provenance_leela.py`, `collector_proc.py`, `static_names.py`, `nodes/env_probe/IInstance.py` — because `video-bench` has developed them since the fork. I verified one instance concretely: `video-bench`'s `provenance_leela.build()` takes a `splitter` parameter added for the video arm, and `main`'s does not. A merge that resolves the wrong way on any of those five silently regresses the harness, and an as-is merge is the only repair sanctioned for a forked base. Cherry-picking is worse: the docs driver has three weeks of Phase-1 history behind it and there is no clean commit range. Branching from `video-bench` costs one path-scoped import — and since §5.1 shows the driver is already there, that import is **artifacts only, no code.**

**The Final Call. Branch `docs-bench` from `origin/video-bench` (`7152de7`), then import the 128 main-only result artifacts in one path-scoped commit that enumerates the paths. No merge, no rebase, no cherry-pick.**

```bash
git fetch origin
git checkout -b docs-bench origin/video-bench          # 7152de7
git checkout origin/main -- working/results/run10k_p2_blast \
                            working/results/run10k_p2_blast_v2 \
                            working/results/batched_20260818T040800Z \
                            working/results/batched_20260818T050304Z \
                            working/results/batched_20260818T074549Z \
                            working/results/batched_20260818T133821Z
# plus the 18-Aug top-level exports — enumerate them, do not glob blindly
git commit -m "docs: import 18-Aug run artifacts from main (paths enumerated); no code taken"
```

Rationale in one sentence: **`video-bench` carries operational discipline that cannot be re-derived, `main` carries artifacts that can be copied — so move the artifacts, not the discipline.**

Cut `docs-bench` on the box as a **third worktree** (`~/parity-bench-docs`), matching the two-worktree layout that already works. No branch-switching in an existing worktree.

### 5.4 Corpus status — GovDocs1

`[VERIFIED 2026-09-07]`

* Manifest committed at `working/results/corpus_manifest.jsonl`.
* Fetcher committed at `working/scripts/fetch_govdocs.py` — manifest-driven, verifies against recorded size and sha256, prints `DONE` only on a match, exits 1 and names the files otherwise.
* The 18-Aug measured slice records `corpus_manifest_sha256 = 22177c33c3651fceceef99ba5c5c2d89f9bbe270dddc23e9943c6e20b421508c`, `corpus_n_docs = 9975`.
* The full 10,000-document corpus sha from the 16-Aug era is recorded as `03692bf6a4d5d549` `[PRIOR-RECORD]`.

⚠️ **Whether GovDocs1 is still on the box is UNVERIFIED and cannot be checked from a laptop.** The box has since taken a 1 TB volume and run a 262 GiB films corpus. First box command of the campaign, before anything else:

```bash
./working/harness/box.sh 'ls ~/parity-bench/corpus/govdocs1/pdfs | wc -l; \
  df -h /; \
  cd ~/parity-bench && ~/.venv/bin/python working/scripts/verify_corpus_manifest.py'
```

⚠️ **Flag contract, verified — do not add `--full`.** `verify_corpus_manifest.py` takes **only** `--subset`; full verification is the **default with no flag** (`main()` does `subset = "--subset" in sys.argv[1:]`, `:41`). It resolves its own paths: manifest `working/results/corpus_manifest.jsonl`, corpus `corpus/govdocs1/pdfs` (`:35-37`). `--subset` verifies only files present on disk and does **not** gate on missing — it is the same gate, scoped, and it is the wrong one here. `[VERIFIED 2026-09-07]`

Expect `10000 on disk / 0 missing / 0 extra / 0 changed / VERDICT MATCH`. Anything else, re-fetch with `--verify` before a single leg runs. Do **not** trust a fetcher log line that reports its own arithmetic — that exact defect once truncated zip 040 at 48 of 248 members while printing `DONE total_pdfs=10000`.

---

## §6. Re-scoping for documents

The films campaign had to re-scope gate 3 for variable frame timing before anything could run. Documents need the same treatment, and in more places.

### 6.1 Documents are parse-bound, not inference-bound

The video pipeline's cost centre was RF-DETR — one model instance per task subprocess behind a process-local device lock. Tokens multiplied model instances, so tokens bought 5.21×.

The document pipeline's cost centre is **Tika parse** (JVM, in the engine) plus the splitter plus MiniLM embed. Tokens still multiply task subprocesses, so more tokens should still help — **but the magnitude is unknown and the mechanism differs.** BLAS/OMP thread counts matter far less when the dominant stage is not matmul.

> **The posture optimum for documents may sit somewhere else entirely, and the video 5.21× must not be assumed to transfer.** `[HYPOTHESIS]`

**Ruling.** The posture sweep must be run **fresh on documents**, over M tokens × the six BLAS/OMP vars, each point at C ≥ M so lanes actually saturate. Symmetric method, per-arm optimum, full matrix published beside the chosen values — the same shape settled for video (Crossroad 17). Do not carry a video value across.

⚠️ **Watch the idle burden.** The engine burns **1.004 cores doing nothing** (measured, `/proc/<pid>/stat` delta over 5s on an idle box). If that spin is per-token rather than per-server, M=16 costs 16 of 32 cores before any work starts — and on documents, where the box is not inference-saturated, that overhead is proportionally far more expensive than it was on video. **Measure whether the spin is per-server or per-token in the first sweep point.** `[PRIOR-RECORD on the 1.004 figure; the per-token question is open in both campaigns]`

### 6.2 There is no docs analogue for cross-arm detection agreement

Gate 3 compared label multisets between arms at zero tolerance — possible only because **both video arms shared the same detector and the same pinned `imageio-ffmpeg 0.6.0`.**

**The docs arms have never shared a parser.** RocketRide uses Tika; LlamaIndex uses `pypdf` (§3.1). There is no output on which byte-equality is even meaningful.

What can be gated instead, in descending strength:

1. **Determinism** — each arm against itself across blast and sequential legs. Strict, full chunk-hash-list equality. Transfers unchanged and is the strongest docs gate available.
2. **Census / structure / embed integrity** — transfer unchanged.
3. **Char conservation** — transfers in form only; band must be re-derived (§4.2).
4. **Independent reference (Tika)** — the only gate that catches a *deterministic* defect, since census, structure and determinism all pass on a doubled document. Priced at 0.599 s/doc, so sample it (`SMOKE_TIKA_SAMPLE=200`, deterministic stride) and **print the denominator**.

**Do not invent a cross-arm content gate to fill gate 3's slot.** Different parsers legitimately extract different text; a gate on that measures the parsers, not the frameworks, and would fire constantly.

### 6.3 The metric set needs its own review

Carry over: docs/s (primary), chunks/s (bridge, with the §4.2 overlap caveat and the §2.3 duplication caveat), cpu_s/doc, effective cores, utilisation, cgroup anon peak, both latency definitions.

Needs re-derivation:

* **Any per-core figure.** The films campaign found the product-reader sentence was the *effective-core* one, and that the whole visible gap was idle burden. Compute per-measured-core and per-effective-core **both ways** on documents, and expect them to disagree.
* **`chunks/s` as a headline.** It was contaminated by duplication pre-patch and is contaminated by the overlap asymmetry post-patch. It is a bridge metric, not a headline.
* **Latency under batching.** A batch has one submit and one return; per-document latency genuinely does not exist there. Label it derived, never measured.
* **n.** The wave analysis says a 1,000-document run reports only ~29% of converged throughput while its run-to-run spread is ±2.5% — **precision without accuracy.** Three reps at n=1,000 would agree closely and all three would be wrong by the same ~3.4×. 10k is the floor.
* **Warm-up.** Metric-side exclusion by completion rank drops the *fastest* documents under a batched leg, not the first processed. Driver-side warm-up on disjoint documents is the only coherent policy once batching is in scope — adopt both together or neither.

---

## §7. Instrument lessons — the costly rounds

Three lessons, each bought with real time. They are not general advice; each names a specific failure and its specific cure.

### 7.1 Staging must span the workload's variance axes

**Films cost:** the corpus was staged and sized before anyone measured how much resolution varied across archival prints, and resolution turned out to be the axis that mattered — it drove the 560px mechanism (§7.2).

**The docs axes are page count and extraction difficulty.** Both are already known to be brutal in GovDocs1: `[VERIFIED 2026-09-07]` chunks/doc runs median 8, p95 74, **max 1377** — a p95-to-max ratio of 18×. And the slowest 1% of documents carry **58.6% of all service seconds** `[PRIOR-RECORD]`.

**Cure:** stratify the staging set over page-count and extraction-difficulty terciles before sizing anything, exactly as the films subset was stratified over duration × bytes. A smoke set drawn from zip 000 alone is **not** representative of all 40 zips — this already bit once: the 200-doc runs used `SMOKE_CORPUS_GLOB='000_*.pdf'` while the 10k runs used all 40, so docs/s differences between them are partly corpus mix, not scale.

### 7.2 A cross-arm probe must exercise both arms' REAL paths

**Films cost: three rounds.** The 560px divergence was probed by calling the *backend's* `predict` — which is LlamaIndex's own path. The probe measured one arm twice and reported agreement. The real mechanism was one level up: the engine's `Detector` facade LANCZOS-downscales any frame whose long edge exceeds `infer_edge=560` before the backend sees it, while the LlamaIndex arm hands the raw frame over. Two resampling pipelines above the edge, one below.

**Register entry 33** — "Two methods with one name — the probe isolated the leaf, the node calls the facade", `working/video/METHODOLOGY_REGISTER.md:1242`.

This is the **third** occurrence of the one-armed-check class in this campaign (defects #24, #25, #37).

**Cure, and it is mechanical:** every cross-arm probe must enter through the **same entry point the measured leg uses** — the engine through its pipe, the service through its HTTP endpoint — never through an inner function either arm happens to share. If a probe cannot be driven through the real entry point, that is a finding about the probe, not a licence to use the inner one.

**Docs-specific instance to watch:** any probe comparing extraction must call Tika **through the engine's parse node**, not the Tika jar directly. Calling the jar directly measures Tika; the leg measures the engine's use of Tika. Those are different, and the difference is exactly where a defect would hide.

### 7.3 The figure checker goes in at the START

**Cost:** it went in at the end of the films campaign, so every figure written before it existed had to be re-verified against artifacts by hand.

The checker (`working/video/probe/end_to_end_figures_check.py`) mechanically verifies every number in a report against its source artifact and exits non-zero on a mismatch — 263 checks at rc=0 on the films end-to-end report.

**Cure:** author the docs figure checker **in the campaign's first week**, before the first measured leg, and add a check the moment a figure enters any document. A figure that has never been checked is a figure that has never been checked, whether it was written on day 1 or day 30.

This session is itself an argument for it: the `duplication_patch_applied` field (§2.4) has read `False` in every measured docs export since 17 August, and it took a targeted cross-reference against image digests to catch it.

---

## §8. Standing rules for fresh sessions

Inherited, non-negotiable, and all of them were bought with a lost round.

**1. The box wrapper.** All box commands go through `working/harness/box.sh` (laptop-side). It starts a stopped box, polls to SSM Online, opens the session, runs the command, scrapes `__RC=`, exits cleanly and writes a UTC transcript. Three things it adds over the version it adopts: a **hard refusal list** checked before anything is sent, the transcript as the evidence surface, and session-count hygiene against the 25-session cap. `--start` is opt-in. **Never bypass it to paste a command by hand.**

**2. Entry-26 landing.** A box commit is landed **only when the laptop has read it back from origin.** The box has no git credentials, so box-side work reaches origin via `git bundle` → S3 → laptop fetch → **`ls-remote` comparison**. A cut bundle *claims* the branch base, so no laptop work may push onto that base until the box side lands. The only repair for a fork is an **as-is merge after a mechanical path-overlap check — never a rebase.** `working/video/METHODOLOGY_REGISTER.md:901`

**3. Script files with SHAs.** Long box blocks are **committed script files that print their own sha256**, never pasted one-liners. A pasted anchor block once lost `--network host` to SSM line-wrapping and the preflight refused all 8 containers.

**4. The box/laptop split.** On the box: **never** `export AWS_PROFILE`, never `aws sso login`, `start-instances` or `start-session` — those are laptop-only. The box authenticates by instance role. On the box use `~/.venv/bin/python`, never bare `python3` (no psutil). `docker cp` writes to the writable layer and is destroyed by `docker rm` — re-copy custom nodes after every fresh container. Use `${PIPESTATUS[0]}`, never `$?` after a pipe. Use `command -v` to test for a tool — invoking a missing binary fires Ubuntu's `command_not_found_handle` and hangs the terminal.

**5. The evidence rule.** Believe a figure only if it comes from a run artifact, from Claude Code's source-verified analysis, or from something pasted out of the box. Everything else is labelled **HYPOTHESIS**. Never state a measurement not actually seen. When unsure, ask Claude Code rather than assume. **Anything not explicitly reported as done is PENDING** — never assume a command ran.

**6. The register.** `working/video/METHODOLOGY_REGISTER.md`, **35 entries**, `## N. Title` heading style. `[VERIFIED 2026-09-07]` **Consult it before designing anything.** It is not a log; it is the list of ways this campaign has already been wrong.

**7. Public actions.** Anything that will be publicly visible — issues, PRs, pushes to public repos, published copy — must be verified and shown for **manual approval** before it goes out. Never authorise an executor to publish inside an autonomous block. ⚠️ **`2001anshkaushik/parity-bench` is a PUBLIC repository.** Every push to it is a public action.

---

## §9. Open items from the video campaigns — DO NOT ACT

Listed so a docs session recognises them if they surface, and does not adopt them.

> **These are not docs work. Do not open, investigate or "quickly fix" any of them. If one appears to block docs work, say so and stop — do not decide it yourself.**

1. **Four upstream engine tickets**, unfiled or unresolved: `dap_client.py:229` discarding the true exception behind a generic `ConnectionError`; `CONST_DATA_PIPE_TIMEOUT = 60.0` reaping pipes as zombies during long uploads; the ttl idle-timer semantics; and Ticket 3 `BUG_CHUNK_CONFIG_IGNORED` (§4). Plus a Ticket 4 candidate on the 1-core idle spin.
2. **Crossroad-38 band re-centre** for the AMI regime.
3. **Leela's and Shashi's handoff docs still carry the withdrawn "RocketRide ahead" number.** They need updating. Not by this session.
4. **LOC + COSMIC comparison of the two services only**, excluding harness, instrumentation and engine source.
5. **The 16×2 ceiling legs** — dropped for time, so the queue-depth asymmetry at C=16 is stated qualitatively and never quantified.
6. **`boundary_eps` is 0.001 yet `n_boundary_excluded` reported 0** — an open instrument question on the video cross gates.
7. **The films500 p1 anomaly** — excluded from every mean as environmental, cause never established.
8. **Next-campaign candidate:** have the LlamaIndex arm apply the same 560px pre-downscale for like-for-like preprocessing.
9. **`[waterfront]`** — an unratified duplicate cluster in the films corpus.
10. **`working/results/probe_ws_ceiling__20260819T002626Z__8e18a5c2b643.json`** — still untracked on the box.

---

## §10. First actions

### 10.1 THE FIRST DECISION — fix the provenance field before any leg runs

**The Current Decision.** Whether to fix `provenance_leela.py`'s hardcoded `duplication_patch_applied: False` now, or to run first and correct the exports afterwards.

**The Trade-offs.** Fixing first costs perhaps an hour and delays nothing else, since the corpus check (§5.4) and the branch cut (§5.3) run in parallel. Running first means every leg of the re-run emits a **false comparability record** — and this field is precisely the one Leela's `check()` uses to decide whether two runs may share a table. We would generate a fresh set of exports asserting our patched engine is stock, then have to correct them by hand and explain the correction to two teammates. The defect has already survived from 17 August to today, on both branches, unnoticed.

**The Final Call. Fix it before the first leg.** The field must read the image label — the same mechanism `smoke_phase2.py` already uses successfully via `provenance/engine/label_raw` — and an **unreadable label must record `None`, never `False`.** `None` fails Leela's check as missing, which is the correct outcome for an unknown; `False` asserts a fact we did not measure. Then re-emit corrected `provenance_leela` blocks for the 18-Aug exports as a separate, clearly-labelled correction artifact, leaving the original files untouched.

**Prompt for Claude Code — carries hypothesis and evidence, per the standing rule:**

> **Hypothesis:** `working/harness/provenance_leela.py` hardcodes `duplication_patch_applied: False` and `duplication_patch_id: None` as literals in `build()`, so every measured docs export since 17 Aug carries a false patch record — including on the LlamaIndex arm, which has no engine to patch.
>
> **Evidence:** the literals are at `main:132-133` and `video-bench:140-141`, unconditional. `smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json` records `provenance_leela/rocketride_pdf/image_digest = sha256:073b43d8…`, which is the same digest carried by `smoke_phase2__20260818T074453Z__ca62d2e2ee9d.json` where `provenance/engine/label_raw = 1` and all five fixture records report `repeat_factor = 1`. Corroborated by output shape: max chunks/doc is 2754 in `run10k/perdoc_rr_blast.jsonl` (stock) and 1377 in `run10k_p2_blast_v2/perdoc_rr_blast.jsonl` (patched) — exactly halved.
>
> **Task:** make `build()` read the image label the way `smoke_phase2.py` already does, recording `None` (never `False`) when the label is unreadable. Add a regression test over a committed export asserting the field is never `False` on an arm whose `image_digest` matches a patched image. Then produce a correction artifact re-emitting corrected `provenance_leela` blocks for every 18-Aug export, originals untouched. Report which exports changed and which did not — I expect all four `exp_batched_blast__20260818T*` and both `smoke50_parser_in__20260818T*` to change, and any export that does not change is a finding I want to hear about before you proceed.

### 10.2 Then, in order

1. Cut `docs-bench` per §5.3; import the 128 artifacts; `ls-remote` to verify. **Public repo — show the push for approval first.**
2. Verify the corpus on the box per §5.4. Nothing runs until `VERDICT MATCH`.
3. Author the docs figure checker (§7.3) **before** the first measured leg.
4. Build the stock-engine duplication test with its null control (§2.5). This is re-run goal 1 and it is cheap — it needs a fixture, not a 10k leg.
5. Only then design the posture sweep (§6.1). This is re-run goal 2 and it is the expensive half.

---

## The flush — what this document adds that no committed file held

Stated plainly, because the next session cannot tell the difference between something I verified and something I remembered.

**Newly measured in this session, in no committed file:**

* The ≥64-chunk eligible denominator: **595 / 601 documents, ~6%** (§2.3). Nobody had computed it. It changes how `self_duplication` must be reported.
* The **load1 floors per docs run dir** (§3.2) — 3.74–4.14 clean versus 9.15–21.93 contaminated. The contamination was known as a general Phase-1 caveat; it had never been tied to specific docs artifacts or quantified against them.
* The **image-digest attribution** of the 18-Aug runs to `rr:patched` (§2.4), and the **halved-corpus-maximum corroboration** (§2.2c). The digests were in the exports; nobody had cross-referenced them.
* That **`provenance_leela.py`'s hardcoded `False` is still live on both branches** (§2.4, §10.1).
* The **pins × patch × cpuset × load table** (§3.2) resolving the open "neither pair is unconditionally quotable" tension.

**Held in prior context and now written down for the first time:**

* **The one-token fact applied to documents.** Every committed file that discusses multi-token posture lives in `working/video/` — `REPRO_PARITY_POSTURE.md`, `AMI_CROSS_TEAM_TABLE.md`, the three DEFINITIVE reports, `METHODOLOGY_REGISTER.md`, `FILMS_HANDOFF.md`. **Nothing in the docs-facing tree connects it to the docs numbers.** `[VERIFIED 2026-09-07 by grep]` This is the single most important thing this document adds.
* The batch-vs-per-document result framed as *the docs phase's strongest finding*, and the reasons it is (§3.5). The numbers are in the artifacts; the framing was not written down.
* The withdrawal-of-the-withdrawal on starvation (§3.5), which exists only as a conversational correction.
* The document-side reasoning about overlap realisation (§4.2) — the video mechanism is filed, the docs consequence is not.

**Everything else** in this document is either `[VERIFIED]` against a named artifact or points at a committed file. Where a figure is `[PRIOR-RECORD]`, the artifact is named — read it rather than quoting this file.
