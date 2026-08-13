# Pre-AWS local readiness — Parser IN end-to-end

**Ansh · 2026-08-13.** Engine `3.3.1.35`, SDK 1.3.0, threads unpinned (measured 10 intra-op / 14
interop on both arms), Parser IN. AWS bills from power-on, so this states plainly what travels and
what does not.

---

## 1. The newline question — RESOLVED, and it was two layers, not a contradiction

**Verdict: `'\n\n'` is added at the parse-node output; the `'\n'` is the splitter-input contract.
Different layers, no contradiction — and neither changes any chunk.**

Traced at all three boundaries on real documents:

| boundary | measured |
| --- | --- |
| 0 — standalone Tika | 650 chars, tail `'40\n\n\n'` |
| 1 — after the `parse` node | 652 chars, tail `'\n\n\n\n\n'` — **exactly +2** |
| 2 — after `preprocessor_langchain` | chunk 0 = 646 chars, tail `'78240'` — **no trailing whitespace** |

**Why it does not matter for chunks:** `RecursiveCharacterTextSplitter` has
**`strip_whitespace=True`** by default, so trailing whitespace never survives into a chunk.

Verified three ways [VERIFIED]:

* On 5 real **multi-chunk** documents, `split(T)`, `split(T+'\n')`, `split(T+'\n\n')` and
  `split(T+'\n\n\n')` all reproduce the engine's chunk hashes — **5/5 for all four variants**.
* A synthetic boundary sweep at lengths 3798–8000 (including exactly 4000): the trailing newline
  changes the chunk count in **0 of 11** cases.
* Same sweep on natural text with spaces available as split points: **0 of 4**.

**Effect on the last chunk of every document: none.** It is stripped either way.

**Whether the preprocessor adds a third newline is unobservable and irrelevant** — it cannot be seen
downstream of a stripping splitter, and the sweep shows it could not change chunking if it did.
[UNVERIFIED but bounded: unobservable *and* demonstrably inert.]

**Consequence for reference generation: unblocked at chunk level.** Any variant works for a
chunk-hash gate. It still matters for *text-level* comparison — see §3, where it turned out to
matter more than expected.

## 2. 50-document smoke test — both gate structures, side by side

Same 50 GovDocs PDFs, both arms, sequential then blast.

| | LlamaIndex-pdf | RocketRide-pdf |
| --- | --- | --- |
| **Leela — census** | 50 = 49 successful + 1 expected + 0 unexpected · **PASS** | 50 = 49 + 1 + 0 · **PASS** |
| **Leela — structure** (384-d, finite, L2 = 1.0 ± 0.001) | 0 failures · **PASS** | 0 failures · **PASS** |
| **Leela — determinism** (blast vs sequential) | 50/50 identical · **PASS** | 50/50 identical · **PASS** |
| **Ours — independent-reference chunk hash** | 0 fail | **5 fail** |
| **Ours — content sanity** | 0 suspect | 0 suspect |

**Cross-arm, reported not gated:** chunk-count delta (RR − LI) median **+0**, range −7 to +89,
identical on **33/50**. Char ratio (RR / LI) median **0.9963**, range 0.9404–1.9773.

### The 5 RocketRide failures are MY reference, not the engine — mostly

This is the part that would have gone to AWS as a false finding. Investigated at the parse boundary:

| document | what the gate said | what it actually is |
| --- | --- | --- |
| `000_000142` | chunk 0 shorter by 1 | engine `long term` vs my reference `long\xadterm` (**soft hyphen**) |
| `000_000163` | same length, different bytes | engine ` ` (em space) vs my ` ` (em quad) |
| `000_000152`, `000_000168` | same length, different bytes | same class — Unicode mapping |
| `000_000159` | chunk COUNT 164 vs 82 | **parse output matches my reference exactly**; the product pipeline still returned 2× the chunks and 2.05× the characters. **UNEXPLAINED.** |

**Four of five are a defect in my reference.** Standalone Tika — same version, same jars, same
`tika-config.xml` — maps certain glyphs differently from the engine's in-process Tika. Root cause not
established: JVM defaults already match (`file.encoding=UTF-8`, `user.language=en`, `user.country=US`)
and explicit overrides did not reproduce the engine's mapping. **Stopped per the stopping rule** —
>30 min, and the load-bearing conclusion does not need it.

**Correction to a claim I made yesterday:** I reported the reference rule
`engine_parse == standalone_tika + '\n\n'` as **byte-exact 8/8**. That was measured on the **first 8
sorted documents**, which is not a representative sample. On a wider draw it holds **2 of 6**.
**The rule is not universal and the earlier 8/8 overstated it.** Lengths still differ by exactly 2
everywhere measured, but the bytes in between do not always agree.

**`000_000159` is the one that is not explained away**, and it is the more interesting one: the
engine's own parse output matched my reference byte-for-byte, yet the 5-node pipeline produced 164
chunks against 82, and 580,104 characters of chunk text from 283,521 characters of extracted text.
That is consistent with Leela's §4.5 finding that the engine's parser duplicates content, but at 2×
rather than her ~4.7 % of lines. **PROVISIONAL — one document, one run, not isolated.** Rival
explanation I cannot exclude: the `parse` node inside the 5-node pipeline may not produce the same
text as the `parse` node in the extract-only pipeline. I have not verified that they agree, and it is
the first thing to check.

## 3. What Leela's gates cannot catch — demonstrated twice

**On a synthetic NUL document** (13,816 chars, NUL at offset 2,115), engine 3.3.1:

| gate | result |
| --- | --- |
| self-capture / determinism style (compare the arm against itself) | **3/3 PASS** |
| independent reference | **FAIL** — `chunk 0/4, len 2115 vs reference 3998 — truncation at the NUL` |

100 % agreement on 100 % data loss: the document lost 84 % of its text and the gate reported health.

**And in the 50-document run above**, RocketRide passed all three of her gates — census, structure,
determinism 50/50 — while an independent reference flagged 5 documents. Even after subtracting the
4 that are my reference's fault, **one real anomaly survived a gate set that reported everything
clean.**

**Her gates are not wrong.** Determinism is a real property, and a self-comparison is the correct
instrument for it — our own harness bug (below) is exactly what it would catch. But a deterministic
defect reproduces identically by definition, so self-comparison cannot see it. **Both are needed.**

## 4. Warm-up, and the expected-failure list

**Warm-up [PROVISIONAL — one fixture, one host].** 25 documents is enough for RocketRide, not for
LlamaIndex. One document repeated 200×, size held constant:

| reps | LlamaIndex | RocketRide |
| --- | ---: | ---: |
| 0 | 1.61× steady | **4.04× steady** |
| 10–25 | 1.14× | 1.06× |
| **25–50** | **1.08×** | 1.05× |
| 100–200 | 1.00× | 1.00× |

RocketRide is within 5 % by rep 25; LlamaIndex is still **8 % inflated at reps 25–50** and reaches
steady near rep 100. **Recommend 100, set by the slower arm** — 25 leaves an 8 % bias on one arm and
not the other, which is the shape of a false finding.

(A first attempt at this measured 400 consecutive corpus documents and was discarded: GovDocs1 sizes
span **2018×**, so it measured document size, not warm-up.)

**Expected-failure list.** `pdf500/census.py:14` hardcodes `EXPECTED_FAIL = {"000164.pdf",
"000357.pdf"}` — two filenames, not one. Two problems:

1. **It matches zero documents in our corpus.** Ours are named `000_000164.pdf`; the set silently
   selects nothing, and the expected-fail check passes vacuously.
2. It cannot discover new expected-failures as the corpus grows.

**But the underlying finding is solid and now cross-confirmed:** both documents exist in our corpus
under the `000_` prefix, and both return **0 documents on our engine 3.3.1** — reproducing her
failure on a **different engine version**. [VERIFIED — 2/2, two teams, two engine versions.]

**Proposal:** derive the expected-failure set from the corpus manifest rather than hardcoding it —
a one-time characterisation pass records per-document expected outcome alongside the per-file
sha256, versioned with the corpus. It then scales with the corpus and is portable across naming
schemes.

## 5. Readiness verdict

**Travels to AWS:**

| item | evidence |
| --- | --- |
| Parser IN, both arms | 50/50 documents both arms, census closes, structure clean |
| Leela's census + structure + determinism gates | implemented, PASS on both arms |
| Determinism under concurrency | 50/50 blast vs sequential, both arms |
| Thread parity, measured in-process, refuses to run on mismatch | 10/14 on both arms every run |
| Content sanity | 0 false positives on 50 documents |
| Setup probe + environment manifest incl. engine binary sha256 | built, runs |
| Cross-arm fidelity as a reported metric | median char ratio 0.9963 |

**Does NOT travel:**

| item | why |
| --- | --- |
| **The independent Tika reference gate** | produces **false failures** — 4/5 flagged documents are Unicode-mapping differences between standalone and in-process Tika. **Do not run it as a gate on AWS.** Keep it advisory until the mapping is reconciled. |
| **The `+'\n\n'` reference rule as stated** | holds 2/6 on a wider draw, not 8/8. Needs re-deriving, and re-deriving on **3.2.1** regardless. |
| **`000_000159` 2× duplication** | unexplained; check first whether the 5-node `parse` and the extract-only `parse` agree. |
| **Census identity as a hard gate** | closes on both arms, but the fault taxonomies are asymmetric: LlamaIndex returns typed error classes, RocketRide signals failure with an empty document list. It closes while meaning different things. |
| **Per-file corpus sha256 manifest** | still missing on our side; both other teams have one. |

**One harness bug caught during this run, worth recording:** the first determinism implementation
drove `RocketPdfArm.process()` from a `ThreadPoolExecutor`. That calls `run_until_complete` on one
asyncio loop from several threads, silently abandoning coroutines
(`coroutine 'send' was never awaited`) and reporting **7/8 false non-determinism** against
RocketRide. Fixed to one loop with `asyncio.gather` and a semaphore; 50/50 clean afterwards. It is
the twelfth instrument defect in this project versus the systems under test, and it would have
travelled as a RocketRide finding.
