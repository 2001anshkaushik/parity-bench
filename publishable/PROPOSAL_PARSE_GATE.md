# Proposal: change the reference source for the RocketRide parse gate

**For Leela.** Ansh · 2026-08-13. Re: §4.3 of the LangGraph vs RocketRide Benchmark Specification.

**Your design reasoning is right and I am not proposing to change it.** A parse gate needs a
reference, the reference must not be the other arm's parser (pypdf-as-truth would make every Tika
difference look like a defect), and it must be cheap to produce. All three constraints stand.

**Only the reference *source* needs changing.** §4.3 takes a sequential capture of the engine's own
output as ground truth. That makes the gate self-referential, and I can demonstrate concretely what
it misses rather than argue about it.

> **Note:** I am working from the specification as relayed to me, not from the document itself — it
> is not in `bench_langgraph_prod@b9b4736`. If I have misread what §4.3 captures, the demonstration
> below still stands on its own but the recommendation may not apply. Please correct me.

---

## 1. The demonstration

Our NUL-truncation defect is **deterministic**: the engine truncates returned `page_content` at the
first NUL byte, in the same place, every time. That is exactly the property a self-capture reference
cannot see.

Document: 13,816 characters, a single NUL at offset 2,115. Engine `3.3.1.35`.

| gate | reference | result |
| --- | --- | --- |
| **A — §4.3 style** | sequential capture of the engine's own output | **3/3 PASS** |
| **B — independent** | `harness/chunk_hash.py`, built outside the engine | **FAIL** — `chunk 0/4 content differs (len 2115 vs reference 3998) — reference contains NUL, returned does not: truncation at the NUL` |

Gate A passes because the defect reproduces perfectly. Every re-run truncates at offset 2,115, the
capture also truncated at 2,115, so they agree — **100 % agreement on 100 % data loss.** The document
lost 84 % of its text and the gate reported health.

**This is not specific to NUL.** Any deterministic defect is invisible to a self-capture reference:
a parser that always drops the last page, always mangles a ligature, always flattens a table the
same way. The gate detects only *non-determinism* — real, but a different property from correctness.
[VERIFIED — n=3 re-runs, single defect class. The generalisation to other deterministic defects is
reasoning, not measurement.]


> ### ⚠️ CORRECTION 2026-08-13 — the byte-exact claim below was overstated
> `engine_parse == standalone_tika + '\n\n'` was measured **byte-exact 8/8** on the *first 8 sorted*
> documents. On a wider draw it holds **2 of 6**. Lengths still differ by exactly 2 everywhere
> measured, but the bytes between do not always agree: standalone Tika maps some glyphs differently
> from the engine's in-process Tika — e.g. engine `long term` vs standalone `long\xadterm` (soft
> hyphen), engine `\u2003` vs standalone `\u2001`. Same version, same jars, same `tika-config.xml`;
> JVM defaults already match (UTF-8 / en / US) and explicit overrides did not reproduce it. **Root
> cause not established.**
>
> **The §1 demonstration is unaffected** — it does not depend on this rule. But the proposed gate is
> **not ready to run as a hard gate**: on 50 documents it produced 5 failures, 4 of which were this
> mapping difference rather than an engine defect. Keep it **advisory** until reconciled.
> See `PRE_AWS_READINESS.md` §2.

## 2. The fix: standalone Tika, the engine's own parser, outside the engine

The engine bundles Tika 3.2.3 and a JRE. Run that same Tika **outside** the engine process and use
its output as the reference. Independent of the thing under test, but still RocketRide's own parser —
so it does not reintroduce pypdf-as-truth.

**Verified end to end, on this host:**

| check | result |
| --- | --- |
| bundled runtime | OpenJDK **17.0.19** Temurin — runs |
| Tika jars | `tika-core-3.2.3`, `tika-parsers-standard-package-3.2.3`, `tika-parser-pdf-module-3.2.3`, `pdfbox-3.0.5` (134 jars total) |
| engine's own parser config | `engine/java/tika-config.xml` — **excludes** TesseractOCR, OOXMLParser, OfficeParser, GDALParser from `DefaultParser`. A reference built without this config is a different parser. |
| standalone extraction runs on the bundled JRE | **yes** |
| **matches the engine byte-for-byte** | **8/8 documents**, via one exact rule (below) |

**The rule, measured not assumed:** the engine's parse output is standalone Tika's output plus
exactly two trailing newlines.

```
engine_parse_text  ==  standalone_tika(pdf, engine/java/tika-config.xml) + "\n\n"
```

Verified byte-exact (sha256 equality) on 8/8 documents. Before finding the rule, the two differed by
exactly 2 characters on every document, matched after `.strip()` 6/6 and on normalised whitespace
6/6 — the constant offset is what led to the exact rule. **This matters because it keeps the gate
exact:** no whitespace normalisation, and normalisation is precisely what would hide a truncation
defect.

[VERIFIED — 8 documents, byte-exact. Two methods agree: full-string equality and sha256.]

**One constraint worth knowing before you plan the work:** the bundle ships a **JRE, not a JDK** —
there is no `javac`, and `java`'s single-file source mode fails with `Module jdk.compiler not in
boot Layer`. So the extractor must be compiled once elsewhere (any JDK 17; I used an
`eclipse-temurin:17-jdk` container against the engine's own jars) and the resulting class shipped.
It then **runs** on the bundled JRE with no JDK at runtime. On the Phase 2 Linux boxes this is a
non-issue.

## 3. Second layer: content sanity, independent of any reference

Cheap, and it catches a class the hash gate cannot — content that is *structurally* fine but
*semantically* garbage:

* **`has_nul`** — exact. Catches the truncation defect at the source.
* **printable ratio < 0.90** — catches garbage extraction.

**The threshold was derived, not chosen.** On a 991-document sample, legitimate documents sit at
p1 = 0.9944 with a second-lowest of 0.9757; the two known-garbage extractions sit at 0.679 and
0.700. 0.90 is the midpoint of an empty band and flags 0 of 40 legitimate documents.

The two checks do not substitute for each other: two of three NUL-bearing documents had printable
ratios of 0.9923 and 0.9884 — indistinguishable from clean — and one of them lost 98.9 % of its text.

## 4. What I am proposing, concretely

1. **Keep §4.3's structure.** Per-document parse gate, sequential, cheap.
2. **Replace the reference source** with standalone Tika using the engine's own jars and
   `tika-config.xml`, plus the `+ "\n\n"` rule.
3. **Add content sanity** as a second, reference-free layer.
4. **Keep the determinism re-run you already have** — it is still the right check for
   non-determinism, which the new reference does *not* test. The two are complementary, not
   alternatives.

**What this costs:** one ~40-line Java class compiled once, and one subprocess call per document at
reference-build time. The reference is built once per corpus, not per run.

**What it buys:** the gate can fail. Right now, on our engine, it cannot fail on our worst known
data-loss defect.

## 5. What a hostile reviewer would say, answered

* *"You are proposing your own gate over hers."* — No. Her structure, her constraints, her rejection
  of pypdf-as-truth. One field changes: where the reference text comes from.
* *"Standalone Tika might not match the engine, making the reference wrong."* — That was the risk, so
  it was the first thing measured: 8/8 byte-exact under an explicit rule. If it had not matched, the
  proposal would have died here.
* *"Two newlines is a fragile rule to hang a gate on."* — Agreed, which is why it is asserted rather
  than assumed: if the engine stops appending them, the gate fails loudly on every document and the
  rule gets re-derived. That is the correct failure mode.
* *"This only proves the NUL case."* — Correct. The measurement covers one deterministic defect
  class; the extension to others is argument. But one is enough to show the gate cannot fail on it.
* *"Does this depend on engine 3.3.1?"* — The `+ "\n\n"` rule is measured on 3.3.1 only. It must be
  re-derived on 3.2.1 before anyone relies on it, and the assertion above is what will catch it if it
  differs.
