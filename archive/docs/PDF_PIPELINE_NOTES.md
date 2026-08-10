# PDF Pipeline — Design Notes (no build, no benchmark)

**Design only.** Ansh · 2026-08-06. The corpus is shifting to heavy PDFs; these are the two things
that must be settled before any PDF number is produced.

---

> ## ⚠️ CORRECTIONS 2026-08-06 (session 8) — three claims in this document were wrong or imprecise
>
> **1. "java is present on PATH" was WRONG EVIDENCE.** `which java` returns `/usr/bin/java` on macOS
> even with no JDK installed — it is a stub. `java -version` reports *"Unable to locate a Java
> Runtime."* There is no system Java on this machine.
> **The conclusion survives on better evidence:** the engine **bundles its own private JRE** at
> `engine/java/jre/bin/java` — OpenJDK **17.0.19 Temurin, aarch64** (native arm64, no Rosetta).
>
> **2. Tika is now VERIFIED by execution, not just by source strings.** `engine --tika <file>`
> extracts text and identifies itself as `com.rocketride.tika_api.TikaApi`. The engine binary loads
> the JVM **in-process via JNI** (`engLib/store/filters/parse/tika/`, `JNI_CreateJavaVM`,
> `Jni.hpp`) — so **no separate `java` process ever appears**, and its absence does NOT disprove
> Tika. The check proposed in §1 of this document would have produced a false negative.
>
> **3. The LlamaIndex side has NO PDF capability installed at all.** `llama-index-readers-file`,
> `pypdf`, `PyMuPDF`, `pdfminer` and `pdfplumber` are all absent. `llama_index.core` maps
> `.pdf → PDFReader` from that missing package and, when it is absent, **warns and returns `{}`** —
> so PDFs would be **silently skipped, not error**. That is a trap worth its own note.
> The default parser, once installed, is **`pypdf`** (`llama-index-readers-file` 0.6.0 requires
> `pypdf<7,>=6.1.3`); **PyMuPDF is an optional extra**, not the default. The earlier text implying
> PyMuPDF was the likely default is corrected.
>
> **Empirical parser diff [VERIFIED, one simple PDF]:** on a 3-page generated text PDF, Tika and
> pypdf agree to **99.10 %**. Against ground truth, **pypdf 100.00 %**, **Tika 99.10 %**. Both
> preserve ligatures (`fi fl ffi`), unicode (`café`), formatted numbers (`1,234.56`) and table
> tokens. Operational note: Tika writes JVM log lines to stdout mixed with extracted text, which
> must be filtered.
> **Scope limit:** this was the easiest possible PDF. It shows the two parsers do not diverge on
> simple text, and that the harness works. It says nothing about scanned, multi-column, or
> font-embedded documents, which is where parsers actually differ. `results/pdf_parser_diff.json`.



## 1. The parser asymmetry is real, and it would invalidate the comparison

**If the engine parses PDFs with Tika (JVM) and our service parses with PyMuPDF, we would be
benchmarking two PDF parsers, not two orchestration frameworks.** Parser choice dominates: extraction
speed on a heavy PDF can differ by an order of magnitude between implementations, and it is
entirely unrelated to what WS-1 is trying to measure.

### What the engine actually ships [VERIFIED — source inspection]

The engine bundle contains a **complete Apache Tika 3.2.3 JVM stack**:

```
engine/java/lib/tika-core-3.2.3.jar
engine/java/lib/tika-parser-pdf-module-3.2.3.jar      <- PDF handled by Tika (PDFBox)
engine/java/lib/tika-parser-ocr-module-3.2.3.jar
engine/java/lib/tika-parser-image-module-3.2.3.jar    (+ ~15 further parser modules)
engine/java/tika-config.xml
```

`java` is present on `PATH`, and `tika-config.xml` configures a `DefaultParser` with explicit
exclusions (Tesseract OCR, OOXML, Office, GDAL are excluded from the default parser and OOXML is
re-registered with `extractMacros=true`).

**No `PyMuPDF`, `fitz`, `pdfminer`, or `pypdf` exists anywhere in the engine's Python
environment** — searched to depth 6. So the engine has no Python PDF path; PDF extraction goes
through the JVM.

Relevant nodes: `extract_data` (the general extractor) and `llamaparse` (a **hosted API** — network
dependency and per-page cost; must be excluded from any local $0 benchmark, and its presence should
not be mistaken for a local parser).

### What LlamaIndex would use by default

LlamaIndex's default `SimpleDirectoryReader` PDF path uses a **Python** reader (`pypdf` family) and
its ecosystem commonly reaches for `PyMuPDF` for speed. **[PROVISIONAL — not yet verified in our
installed version.]** This must be pinned down by inspecting the installed `llama-index-readers-file`
before any PDF run; it is a 10-minute check I have not done.

### Verdict

**[VERIFIED] The two sides would use different PDF parsers by default — Tika/PDFBox on a JVM versus
a Python reader in-process.** That is not a framework difference. It is also not only a speed
difference: the two produce **different text**, so chunk counts, token counts, and embedding costs
would all differ downstream, and every number after extraction would inherit the discrepancy.

### How to pin the same parser on both sides

Three options, in order of preference:

| option | how | trade-off |
| --- | --- | --- |
| **A. Parse once, outside both** *(recommended)* | Extract text from the PDF corpus in a separate, single pass with one pinned parser. Feed **identical text** to both services. Both arms then run the pipeline we actually want to compare | measures split+embed only — PDF parsing is excluded from the comparison rather than made fair. Report it as a separate, single-arm number |
| **B. Force both to Tika** | Run a Tika server container; have the LlamaIndex arm call it via `TikaReader` | both pay the same parser cost, including JVM startup and an extra network hop for one side only — a new asymmetry |
| **C. Force both to the Python parser** | Write a RocketRide node that parses with the same Python library instead of routing to Tika | most faithful to "same work," but it means benchmarking a non-default engine configuration, which needs disclosure |

**Recommendation: A for the headline comparison, with parser performance reported separately as its
own finding.** It keeps the WS-1 question ("how do these frameworks serve a pipeline?") separable
from "which PDF parser is faster," which is a genuinely interesting but different question.

If we do want the end-to-end number, **B** is the honest way to get it, and the JVM startup cost and
extra hop must be measured and disclosed rather than amortised away.

### Empirical confirmation still owed

Source inspection says Tika. **[UNVERIFIED empirically]** — the run that proves it has not been
done. The check: send one PDF through the engine's extract path and confirm a JVM process appears
in the process tree, and diff the extracted text against a PyMuPDF extraction of the same file.
Different text confirms different parsers, and the diff itself sizes the downstream distortion.
**~20 min, not run** — deferred because the corpus is not selected yet and the environment is about
to change to Docker.

## 2. Candidate corpora — legally redistributable

A benchmark nobody can reproduce is not publishable. Requirements: redistributable without
per-recipient licensing, stable identifiers, and genuinely heavy PDFs.

| corpus | what | size | license / terms | fit |
| --- | --- | --- | --- | --- |
| **SEC EDGAR full-text filings** | 10-K/10-Q annual and quarterly reports | tens of GB available; a 500-doc sample is easy to define | **US government work — public domain.** EDGAR requires a declared `User-Agent` and has published rate limits | **best fit.** Heavy (10-Ks run 100–300 pages), text-dense, real-world, stable accession numbers make the sample exactly reproducible |
| **arXiv** | scientific papers | 2M+ papers; bulk access via S3 requester-pays | **mixed and per-paper** — many are CC-BY/CC-BY-SA, but a substantial fraction are arXiv's non-exclusive licence only, which does **not** permit redistribution | usable **only** if filtered to CC-licensed papers; the filter must be part of the manifest. Requester-pays conflicts with the $0 constraint unless using the OAI metadata + individual fetches |
| **US federal government filings/reports** (GPO govinfo, agency reports) | budget documents, congressional reports | large | **public domain** as US government works | good secondary source; heavier layout variety than EDGAR |
| **Common Crawl PDF subset** | scraped PDFs | very large | CC's terms permit use, but **individual documents carry their own copyright** | **avoid** — redistribution of the documents themselves is not clean |

**Recommendation: SEC EDGAR 10-K filings as the primary heavy-PDF corpus.** Public domain, heavy,
text-dense, and — most important for this project — a sample is fully specified by a list of
accession numbers, so the manifest can be a few kilobytes and anyone can rebuild the exact corpus.
That is the same property that made mt10k verifiable (10,000/10,000 sha256 match against Leela's
manifest).

**Corpus manifest requirements**, mirroring what already works for mt10k:

* accession numbers (or stable URLs) + **sha256 per document**
* page count, byte size, and extracted-token count per document, so corpus shape is known before
  any benchmark (mt10k taught us that corpus shape drives the result more than the frameworks do)
* the fetch script, with the declared `User-Agent` and rate limiting EDGAR requires
* the **parser and version used to produce the token counts**, since §1 shows those counts are
  parser-dependent

**Labels:** licence characterisations above are **PROVISIONAL** — from general knowledge of these
sources, not from re-reading each site's current terms this session. Before publication, each
must be confirmed against the source's terms page and the confirmation dated. arXiv's per-paper
licence mix in particular is a trap: "arXiv is open" is not the same as "redistributable."

## 3. What must happen before any PDF number

1. Confirm empirically that the engine's PDF path is Tika (§1) — ~20 min.
2. Pin LlamaIndex's installed PDF reader by inspection — ~10 min.
3. Choose option A / B / C and get it agreed — this is a **comparison-validity** decision, not an
   implementation detail.
4. Select the corpus, write the manifest with sha256s, and characterise its shape **before**
   measuring anything.
5. Confirm licences against current terms pages and date the confirmation.
