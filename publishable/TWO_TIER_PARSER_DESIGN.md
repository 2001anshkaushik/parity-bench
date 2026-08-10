# Two-Tier Parser Comparison — design

**Design only, nothing run.** Ansh · 2026-08-07. Depends on `PARSER_PREMISES.md`, which settled
that the parser is a free choice on both sides.

---

## Why two tiers, and why they must never share a table

The question "which is faster on PDFs" hides two different questions with different answers:

| tier | question | parser |
| --- | --- | --- |
| **Tier 1 — same-text** | *Which framework serves a pipeline better?* | **identical on both sides** (pypdf), parsing done once, outside both |
| **Tier 2 — end-to-end native** | *Which product ingests a PDF better?* | **each side's own default** — Tika/JNI for the engine, pypdf for LlamaIndex |

Tier 1 isolates the framework. Tier 2 measures the product a customer actually gets. A number from
one answers nothing about the other, and **blending them in one table is the single easiest way to
produce a misleading result** — a framework could lose Tier 1 and win Tier 2 purely on parser
choice, and a combined figure would hide which.

**Rule: no table, chart, or summary sentence may contain both tiers.** Separate sections, separate
headline numbers, tier named every time.

## Tier 1 — same-text (measures frameworks)

**Method.** Parse the PDF corpus **once**, outside both services, with pinned `pypdf 6.15.0`.
Persist the extracted text plus a **sha256 per document**. Both services then receive
byte-identical text and run the split+embed pipeline already characterised.

**Why parse outside rather than pin the same parser inside both:** it removes parser CPU from both
arms entirely, so the measurement is purely the serving path, and it makes the input verifiable —
the same sha256 manifest discipline that proved mt10k was the real corpus (10,000/10,000 match).

**What it reports:** throughput, P50/P95/P99/P99.9, peak RSS, error rate — at the concurrency
levels the isolated profiles say are meaningful (`isolated_profile.py`), **not** at arbitrary ones.

**What it explicitly does not report:** anything about PDF handling. Tier 1 has no parser in it.

## Tier 2 — end-to-end native (measures products)

**Method.** Each service ingests the PDF file itself using its own default path: the engine through
Tika/JNI, the LlamaIndex service through pypdf. Both measured on the same corpus, same host, one
interleaved session.

**Speed alone is not the result.** A parser that is faster and extracts worse text must not score
as a win — it has shifted cost downstream into worse chunks, worse embeddings, and worse retrieval.
So Tier 2 reports **two axes and refuses to collapse them**.

### The quality metric

**Ground truth.** For each document, a reference extraction produced by a third, independent
method, so neither arm's parser is its own referee. Two sources, in preference order:

1. **Born-digital documents with a text source** — for generated or HTML-origin PDFs, the original
   text is the ground truth. Exact, no judgement.
2. **Consensus reference** — for real PDFs with no source text: extract with pypdf, pdfplumber and
   Tika, and take agreement of **≥2 of 3** at each position as reference. Positions where all three
   disagree are excluded from scoring and **counted** — a high exclusion rate is itself a finding
   about document difficulty.

**Primary metric — character-level fidelity:**

```
fidelity(arm, doc) = SequenceMatcher(reference_norm, extracted_norm).ratio()
```

on whitespace-normalised text, which is the same statistic already used to get pypdf 100.00 % and
Tika 99.10 % on the test document. Reported as a distribution (median, p10, worst case), never a
mean — a parser that is perfect on 95 % of documents and catastrophic on 5 % must not average into
"very good".

**Secondary metrics, because fidelity alone misses structured failures:**

| metric | catches |
| --- | --- |
| **token count ratio** vs reference | silent truncation — the failure that most distorts downstream embedding cost |
| **reading-order correctness** on multi-column pages (Kendall tau of paragraph order vs reference) | interleaved columns, which read as fluent text but are semantically scrambled |
| **table cell recall** on documents with tables | tables flattened into unusable word soup |
| **empty/near-empty rate** (< 100 chars from a page with visible text) | scanned pages silently returning nothing |

**The empty-extraction check is the one that matters most for a benchmark**, because a parser that
returns nothing is *infinitely fast* and would otherwise win on speed outright. Any document where
an arm returns near-empty text is **excluded from the speed comparison and reported separately as
an extraction failure**.

### Reporting format for Tier 2

Both axes, side by side, never multiplied into one score:

| arm | throughput | P99 | median fidelity | p10 fidelity | empty rate | token ratio |
| --- | --- | --- | --- | --- | --- | --- |

with an explicit verdict line of the form: *"Arm A is X× faster and extracts Y% fidelity against
Arm B's Z%"* — the trade stated, not resolved. Resolving it is a product decision that depends on
what the text is for.

## Corpus and reproducibility

Per `PDF_PIPELINE_NOTES.md` §2: **SEC EDGAR 10-K filings** — public domain, heavy, text-dense, and
specified exactly by accession number so the manifest is small and the corpus is rebuildable. The
manifest carries sha256, page count, byte size, and extracted-token count **plus the parser and
version that produced those counts**, since §1 shows token counts are parser-dependent.

Deliberately include a **hard subset** — at least some scanned or multi-column documents — because
a corpus of clean born-digital PDFs would show the parsers agreeing (as our easy test did) and
would prove nothing about the axis Tier 2 exists to measure.

## Sequencing and gates

1. Corpus selected, manifest written, shape characterised **before** any measurement.
2. Ground-truth references built and the exclusion rate reported.
3. **Tier 1** — needs only the same-text pipeline, already built and characterised.
4. **Tier 2** — needs the engine's Tika path (verified working) and pypdf on the LlamaIndex side
   (installed this session).
5. Neither tier is reported until the isolated saturation profiles exist for **both** arms, so the
   concurrency levels are chosen from evidence rather than picked.

**Open, and not to be guessed [UNVERIFIED]:** whether Tika's JVM startup is per-request,
per-task-process, or once per engine. It is loaded in-process via JNI, which suggests once per
engine process, but that has not been measured and it would dominate a per-document Tier 2 number
if it were per-request. **~20 min to settle; must be settled before any Tier 2 speed figure.**
