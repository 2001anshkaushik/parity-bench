# BUG: pipeline emits every chunk twice for text payloads above ~239.8k characters

> ## ✅ ROOT-CAUSED IN SOURCE 2026-08-15 — the trigger is CHUNK COUNT, not character count
>
> Shashi found the mechanism (`ENGINE-ISSUE-3.3.1-chunk-duplication-2026-08-15.md`, his
> `c8b4b2b3`), crediting the empirical finding below. `nodes/embedding_transformer/IInstance.py`:
> `writeDocuments()` returns `preventDefault()` on the buffer path but **not** on the flush path,
> so once the buffer reaches `maxDocuments = 64` the node writes the batch downstream itself AND
> the engine also forwards the original event — the same embedded `Doc` objects land twice.
>
> **The predicate is `>= 64 chunks`.** Our "~239,800 characters" was a proxy for it: 64 chunks ×
> ~3,750 chars ≈ 240k. **Every character-based figure below, including the "5.34 % of the corpus"
> census, is therefore a proxy measurement and understates or overstates depending on a document's
> chunk-length distribution.** Re-derive any corpus census on chunk count. The reproducer and the
> observed behaviour are unaffected — only the stated trigger changes.
>
> Our `gates_shared.duplication_verdict()` now reports both `over_chunk_trigger` (>= 64 chunks, the
> real predicate) and `over_char_proxy` (>= 239,800 chars, kept for continuity with earlier runs).



**Engine `3.3.1.35` (hash `a0817cc6`) · SDK `rocketride` 1.3.0 · found 2026-08-13 · Ansh (WS-1)**

**Severity: silent data duplication.** Every affected document's complete chunk list is returned
**twice, concatenated**. All vectors are individually valid, the response looks healthy, and every
correctness gate that compares the output against itself passes. In a RAG deployment the affected
documents are embedded and indexed **double-weighted**, and consume 2× the vector-store rows,
silently.

---

## 1. Minimal reproducer [VERIFIED — deterministic, n=3 both sides of the threshold]

No PDF required. Send plain repeated text through the canonical 5-node pipeline
(`webhook → parse → preprocessor_langchain → embedding_transformer → response_documents`; the
`parse` node is bypassed for `text/plain`, and the same doubling occurs with it in the path):

```python
unit = "alpha beta gamma delta epsilon zeta. "         # any text works
send(token, (unit * 7000)[:239_062], mimetype="text/plain")   # -> 63 chunks  (correct)
send(token, (unit * 7000)[:239_843], mimetype="text/plain")   # -> 128 chunks (= 2 x 64)
```

| payload chars | reference chunks | engine returns | verdict |
| ---: | ---: | ---: | --- |
| 200,000 | 53 | 53 | clean |
| 239,062 | 63 | **63 · 63 · 63** (n=3) | clean |
| 239,843 | 64 | **128 · 128 · 128** (n=3) | **DOUBLE** |
| 500,000 | 132 | 264 | double (still exactly 2×) |
| 750,000 | 198 | 396 | double (still exactly 2×) |

**Threshold: between 239,062 and 239,843 characters** (bisected; deterministic 3/3 on each side).
**The factor is exactly 2 at every size tested up to 750k** — one duplication above a threshold,
not per-fragment emission.

## 2. Structure of the duplication [VERIFIED]

On real corpus documents (`000_000159.pdf`, 283,521 extracted chars):

* engine returns 164 chunks; reference from the engine's **own parse output** is 82
* 82 unique chunk hashes among the 164
* `returned == reference + reference` — **True**; first half == second half == reference
* NOT interleaved (`c1,c1,c2,c2,…` is False) — it is the full list, twice, in order

## 3. What was ruled out [VERIFIED, each by direct test]

| rival explanation | test | result |
| --- | --- | --- |
| harness: 5-node `parse` differs from extract-only `parse` | tapped both in one run | byte-identical, same sha256 |
| harness: preprocessor has two `text`-lane inputs (parse + webhook) | single-input variant pipe | still doubles, same 164 chunks |
| harness: the tap node causes it | plain 5-node pipe, no tap | still doubles |
| document-specific (fonts, structure, Tika metadata) | **synthetic repeated ASCII doubles too** | property of PAYLOAD LENGTH, not content |
| PDF-specific / parse-related | same text as `text/plain`, parse bypassed | still doubles |
| file size correlation | size ladder 0.38–26 MB | duplicators at 2.25/3.75/7.52/10.12 MB; clean at 3.0/4.0/5.0/14.1/26.3 MB. **Extracted-text length** is the variable, not file size |
| SDK send-side chunking constant | grep of SDK source | file-read chunk is 1 MB, not ~240k; fragmentation is transport- or server-side |

## 4. Mechanism — partially localised [PROVISIONAL]

Known: the trigger is **total text-payload length crossing ~239.8k chars**, the effect is **one
extra emission of the complete document set**, and it is **downstream of parse** (parse output is
correct and single). The constant factor of 2 at 750k chars argues against per-frame re-emission and
for a single duplicated hand-off — e.g. a payload delivered via a fallback path for large messages
*and* the primary path, or a lane flushed twice when a size limit forces a split.

Not established: which component performs the second emission. That requires engine-side visibility
we do not have. The reproducer above should let the engine team find it quickly.

## 5. Prevalence [PROVISIONAL — two samples, one host]

* Arbitrary 100-document sample: **1/98** usable documents affected (1.0 %)
* Size-ladder sample (weighted to large documents): **4/17** affected
* Combined: **5 distinct affected documents** — `000_000159` (283,521 extracted chars),
  `009_009442` (246,694), `003_003316`, `004_004513`, `011_011411` — every one with extracted text
  above the ~239.8k threshold, every clean document below it or textless (verified against
  `dup_size_ladder__20260813T221423Z`: zero violations of the threshold rule in either direction)

**Prevalence is therefore a function of the corpus's text-length distribution — and the full-corpus
census supersedes the sample estimates above [VERIFIED — per-file manifest, all 10,000 documents]:**

> **534 of 9,992 parseable documents (5.34 %) exceed the 239,843-char threshold** and would have
> their chunks doubled in a full Parser IN run (`working/results/corpus_manifest.jsonl`, chars
> pypdf-derived, Tika/pypdf median ratio 1.007 so ±~1 % on the count; only 2 documents sit inside
> the 781-char uncertainty band).
>
> The earlier "~1 %" figure came from a 100-document sample drawn from the small-document head of
> the corpus and is **superseded** — it under-counted 5×. A contracts or reports corpus would be hit
> harder still. **At 5.34 % this is not a tail anomaly; it inflates any full-corpus RocketRide chunk
> count by ~10 % on its own.**

## 6. Why every self-referential gate passes [VERIFIED]

`000_000159.pdf` through the team's gate set, three runs:

| gate | result |
| --- | --- |
| census (offered = successful + expected + unexpected) | PASS |
| structure (384-d, finite, L2 = 1.0 ± 0.001) | PASS — all 164 vectors valid |
| determinism (chunk-hash lists identical across runs) | PASS — 164 every time |
| **independent reference (engine's own parse output, chunked offline)** | **FAIL — 164 ≠ 82** |

The duplication is perfectly deterministic, so every comparison of the output against itself agrees.
Only a reference derived *outside* the duplicating path can see it.

## 7. Impact

* **Vector store:** 2× rows for affected documents; retrieval double-weights them.
* **Any chunk-count metric** (goodput, throughput-per-chunk, cost-per-document) is inflated 2× on
  affected documents.
* **Cross-framework benchmarks:** an affected document inflates RocketRide's chunk and character
  counts against any other framework — our cross-arm char-ratio outliers at 1.32–1.98 in the
  50-document smoke run are exactly this.

## 8. Hostile-reviewer questions, answered

* *"Is this your harness again?"* — Three harness explanations tested and refuted (§3), and the
  reproducer is 4 lines against a stock pipeline with a synthetic string.
* *"Maybe the reference splitter disagrees with the engine's."* — On 97/98 documents below the
  threshold they agree exactly; above the threshold the engine returns the reference **twice**, not
  a different chunking.
* *"Threshold could be flaky."* — n=3 on both sides, 781 chars apart: 63/63/63 vs 128/128/128.
* *"Does it depend on the tap or the extra node?"* — the plain 5-node pipe reproduces it.
* *"Could the SDK be sending twice?"* — not ruled out end-to-end; the SDK's visible chunking constant
  is 1 MB, not ~240k, and the factor stays 2 (not N) at 3× the threshold. Engine-side logging would
  settle it; flagged for the engine team rather than guessed.
