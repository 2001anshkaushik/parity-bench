# WS-1 Metrics & Correctness Readiness — pre-Phase-2 sync

**Ansh · 2026-08-13 · for the three-team call.** One page of what we measure, how each number is
gated, and where we stand against Leela's spec and Shashi's asks. Everything labelled; every gate has
been shown to *fail* at least once, because a gate that cannot fail is worse than no gate.

---

## 1. The metric set — three layers, every number carries its gate

### Performance (per run, per arm, per concurrency level)

| metric | definition | gate before it is quotable |
| --- | --- | --- |
| **memory (median)** | median RSS over the block, sampled 5-doc intervals, continuous 0.25 s in sweeps | 10 % spread, n≥3, refuses n=1; swap/compressor gate (a cell where the host evicted or compressed is marked unquotable) |
| **memory (peak)** | max of the same series | same; peak and median never share a cell unlabelled |
| **memory decomposition** | engine parent / task tree / workers / driver, separately | counts sampled in the same snapshot as totals |
| **wall clock per block** | fixed document count, barrier-synchronised | 10 % gate **plus block-level warm-up exclusion** (block 0 is 12–38 % slower on both arms) |
| **latency per document** | per-doc, with **run-position recorded** | first-100-request warm-up excluded (measured: LlamaIndex still 1.08× at rep 25–50) |
| **throughput** | — | **never quoted from a laptop** (2.2× order effect); on AWS: descending or pre-warmed only, n≥3 |
| **concurrency** | offered AND **achieved** (in-flight counter, continuous) | cell where achieved < offered is marked SHORT, ratio not quoted |
| **census** | offered = successful + expected + unexpected, unique ids, zero silent | asserted per run (Leela's identity — adopted) |

### Correctness (per document — this is the levelled-up part)

| # | check | catches | provenance |
| --- | --- | --- | --- |
| C1 | structure: ≥1 chunk, one vector/chunk, 384-d, finite, **L2 = 1.0 ± 0.001** | zero vectors, dim drift, NaN | Leela's spec (tightened from our ±0.01) |
| C2 | vectors not identical across chunks | broadcast/stuck embedder | ours |
| C3 | content sanity: NUL presence + printable ratio < 0.90 (threshold **derived** from 991-doc sample) | garbage extraction, control-char content | ours |
| C4 | **determinism**: chunk-hash lists identical, blast vs sequential run | non-deterministic pipelines, race effects | Leela's, extended to concurrent-vs-sequential |
| C5 | **per-arm chunk hash vs independent reference** — LlamaIndex: its own returned extracted text; RocketRide: **engine parse-tap** (2nd response node on the text lane) | **deterministic data loss/duplication that C1–C4 provably pass** | ours; the tap idea validated at 97/98 exact |
| C6 | cross-arm extraction fidelity: char ratio + order-insensitive word-Jaccard + order-sensitive seqmatch | parser divergence, reading-order effects | ours; **reported, never gated** (parsers differ by construction) |
| C7 | expected-failure set **derived from corpus manifest**, not hardcoded filenames | vacuous pass when naming schemes differ (measured: Leela's hardcoded set matches 0 of our files) | proposed to team |

**Proof the stack works — each of C4/C5's blind spots demonstrated on real data:**
`000_000159.pdf` passes census + structure + determinism (n=3) while its content is silently
**doubled**; only C5 catches it (164 ≠ 82). And C5's own limits are stated: it trusts parse, and it
is per-arm — cross-parser differences go to C6.

### Provenance (per run — the part I was missing last time)

| item | status |
| --- | --- |
| engine version + **binary sha256** (a tag is mutable, a hash is not) | adopted from Shashi, in setup probe |
| SDK version, all library versions **read from the live venv** | in setup probe |
| thread counts **measured in-process on both arms**, run refuses on mismatch | ours — added after a 1-vs-10-thread run went undetected |
| splitter config **read back off the live object** (4000/200) | Leela's read-back discipline, adopted |
| per-file corpus sha256 manifest | **being added — the one gap**; both other teams have one |
| result files: `name__UTC__payload-hash`, O_EXCL, cannot collide | ours |
| setup probe (10 docs) + determinism re-run, gates with non-zero exit | per spec, built |

## 2. What the metric set has already caught (why this is the answer to "not enough metrics")

The levelled-up stack is not aspirational — this week it produced **two filed product findings**:

1. **`BUG_CHUNK_DUPLICATION.md`** — text payloads over **~239.8k chars** get their full chunk list
   emitted **exactly twice**. 4-line synthetic reproducer, threshold bisected to 781 chars,
   deterministic n=3, factor exactly 2 up to 750k. Found **by C5**; passes census, structure and
   determinism. Prevalence is a function of the corpus's text-length distribution (~1 % on GovDocs1;
   would be far higher on a long-document corpus).
2. **`BUG_NUL_TRUNCATION.md`, re-scoped with data** — the truncation defect is live
   (`'AAAA\x00BBBB'` → `'AAAA'`, re-verified) but has **no observed path under Parser IN**: 0/303
   documents show NUL or any control character in Tika output, including all 3 that produce NULs
   under pypdf. Honest one-liner for Joe: *"real defect, no observed instance under Parser IN on
   this corpus; affects text-lane paths."*

Plus cross-team confirmations: Leela's two expected-fail documents reproduce on 3.3.1 (2/2), and the
dropped-splitter-kwargs defect was found independently by all three teams.

## 3. Sync status with Leela and Shashi

**Aligned (no action):** engine 3.3.1 + SDK 1.3.0 · Parser IN, stock 5-node pipeline, `tags` lane ·
model/device/normalisation (verified, not declared) · 4000/200 effective chunking · census identity ·
structure gate at her tolerance · determinism gate · closed-loop driving.

**We adopt from them:** Shashi's engine-binary sha256 and runtime chunk read-back · Leela's L2
tolerance, census, ground-truth-hash discipline · per-file corpus manifest (both have one).

**They may want from us:** the parse-tap reference (C5 — only gate that catches the duplication) ·
achieved-vs-offered concurrency · in-process thread verification · block-level warm-up exclusion ·
swap/compressor gating on memory cells · content sanity.

**Open for the call — needs a decision, with our position:**

| item | positions | our position |
| --- | --- | --- |
| warm-up count | Shashi 25 | **100** — measured: RR converges by 25, LlamaIndex still 1.08× at 25–50, steady ~100; 25 bakes an 8 % bias into one arm |
| thread config | Leela pin-1, Shashi SDK-8, us unpinned-10 | any — but **measured in-process on both arms**, whatever we pick; and note `use(threads=)` vs env vars may not control the same pool (unverified) |
| RocketRide parse reference | spec §4.3 self-capture | **parse-tap** (2nd response node) — self-capture provably passes on 100 % data loss; standalone Tika fails on glyph mapping (4/5 false); tap matched 97/98 |
| driving modes | Leela closed-loop, Shashi blast+sequential | run **all three, never in one table** — burst percentiles include queueing by her own annotation |
| memory boundary | tree+driver / cgroup / driver-only | **cgroup on AWS** (Leela's) — cleanest boundary; ours inflates RR by the driver, Shashi's misses the engine |
| ladder ceiling | 32 | run to 32, but **re-measure pool width first** (17.24 was macOS); label cells above it past-saturation |

## 4. If asked "what would you cut"

The metric set is large because each item caught a real defect. If forced to rank: census +
structure + C5 + provenance manifest are the floor; C6 and the fidelity metrics are reporting, not
gating, and cost nothing at run time; the expensive item is n≥3 with warm-up exclusion — and that is
the one that turned 12–38 % phantom instability into a 0.24 % measurement, so it pays for itself.
