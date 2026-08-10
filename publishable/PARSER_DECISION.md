# PDF Parser — Decision Brief

**For Shashi. You own the call.** Ansh · 2026-08-07.
Evidence: `PARSER_PREMISES.md`, `TWO_TIER_PARSER_DESIGN.md`, `working/dossiers/`, `working/nodes/pdf_probe/`,
`working/results/pdf_parser_diff.json`.

---

## What this brief is

We were about to build the PDF comparison on two assumptions. I tested both before writing any
architecture. **Both turned out to be false**, and that changes what the sensible plan is. Nothing
has been decided or changed — this lays out what was claimed, what was measured, and what I would
recommend.

## Premise 1 — "RocketRide doesn't allow custom parsing nodes, so Tika is forced"

**Claimed:** the engine parses PDFs with its built-in Tika/JNI path, and there is no way to
substitute a different parser, so any PDF comparison is necessarily Tika-vs-something-else.

**Measured:** built `working/nodes/pdf_probe`, a node that parses with **pypdf** instead, installed it,
restarted the engine, and sent it a PDF:

```json
{"node": "pdf_probe", "pid": 1313, "python": "3.12.13",
 "lib": "pypdf 6.15.0", "pages": 3, "chars": 15065}
```

**15,065 characters — byte-identical to standalone pypdf on the same file.** The engine loaded a
node with a third-party dependency, ran it in its embedded CPython 3.12.13, and returned the result
through the normal response lane. **[VERIFIED by execution]**

**Verdict: REFUTED. Tika is the default, not a constraint.** Both sides can be pinned to the same
parser, which means parser choice can stop being a confound instead of being argued about.

**The cost, which is real and belongs in the toil ledger [VERIFIED]:** pypdf is not in the engine's
embedded interpreter and there is **no documented way to add it**. I installed it by copying the
package directory into `engine/lib/python3.12/site-packages/`. That works but is not a supported
deployment story — not reproducible from a manifest, will not survive an engine upgrade, and has to
be redone in any container image.

## Premise 2 — "PyMuPDF is the best-in-class production choice"

**Claimed:** PyMuPDF is the fast, obvious parser to standardise on.

**Measured** (`verify_frameworks.py`, package metadata):

| package | version | licence | permissive? | released | status |
| --- | --- | --- | --- | --- | --- |
| **pymupdf** | 1.28.2 | **Dual: GNU AFFERO GPL 3.0 or Artifex commercial** | **REVIEW_REQUIRED** | 2026-08-06 | ACTIVE |
| **pypdf** | 6.15.0 | **BSD-3-Clause** | **YES** | 2026-08-06 | ACTIVE |
| **pdfplumber** | 0.11.10 | **MIT** | **YES** | 2026-06-15 | ACTIVE |
| pdfminer.six | 20260107 | MIT | YES | 2026-01-07 | **STALE** |

**Verdict: REFUTED on licensing.** AGPL-3.0's network clause extends copyleft to software offered
*over a network*, which is exactly what an embedding service is. On the AGPL branch we would owe
the service's corresponding source under AGPL; the alternative is Artifex's **paid commercial
licence**, which is a procurement decision with a cost attached, not a default.

This does not stop us *measuring* PyMuPDF. It stops us *recommending* it, and it means "PyMuPDF is
faster" is not by itself an argument for shipping it.

## Recommendation

### 1. Framework comparison (Tier 1) — pin BOTH sides to pypdf

**pypdf 6.15.0, BSD-3-Clause.** Three reasons, and the third is the one that matters for fairness:

* **permissive** — no licence constraint on an enterprise deployment
* **actively maintained** — released the same day as PyMuPDF
* **it is already LlamaIndex's own default** — `llama-index-readers-file` 0.6.0 requires
  `pypdf<7,>=6.1.3`, with `pymupdf` only as an opt-in extra

That last point removes the usual objection. Pinning both sides to pypdf is not us picking a parser
that suits us; it is adopting one side's shipped default and proving (premise 1) that the other side
can run it too.

With the parser identical, Tier 1 measures **frameworks**, which is what WS-1 is for.

### 2. Product comparison (Tier 2) — Tika vs pypdf as shipped defaults, WITH quality

Keep a second tier where each side uses what it ships: Tika/JNI for the engine, pypdf for
LlamaIndex. That is a genuine product difference and worth measuring.

**Speed alone must not decide it.** A parser that is faster and extracts worse text has shifted
cost downstream into worse chunks and worse retrieval — and a parser that returns *nothing* is
infinitely fast. `TWO_TIER_PARSER_DESIGN.md` specifies the quality axis: character-level fidelity
against a 2-of-3 consensus reference, reported as a distribution rather than a mean, plus token
ratio, reading order, table recall, and an explicit empty-extraction check.

**Tiers never share a table.** A framework could lose Tier 1 and win Tier 2 purely on parser
choice, and a blended number would hide which.

### 3. PyMuPDF as an optional third arm

If someone wants the speed number, measure it — labelled with the AGPL constraint every time it
appears. Adopting it needs a procurement decision, not a benchmark result.

## Toil, both directions — for `TOIL_INSTRUMENT.md`

| side | cost |
| --- | --- |
| **RocketRide** | No supported path to add a Python dependency to the engine's interpreter. Hand-copied into `engine/lib/python3.12/site-packages/`. Not manifest-reproducible, will not survive an engine upgrade, must be redone per container image |
| **RocketRide** | Custom parse node must be copied into `engine/nodes/` and the engine restarted |
| **LlamaIndex** | Shipped with **no PDF capability at all** — `llama-index-readers-file`, pypdf, PyMuPDF all absent. Core maps `.pdf → PDFReader` and, when the package is missing, **warns and returns `{}`** — PDFs are **silently skipped, not errored**. A pipeline would appear to succeed while processing nothing |
| **LlamaIndex** | pypdf installed this session; `llama-index-readers-file` still absent, so the framework's native reader path is not yet exercised |

The silent-skip behaviour is the more dangerous of the two: RocketRide's gap fails loudly at
install time, ours fails quietly at run time.

## What I have measured, and what I have not

| claim | label |
| --- | --- |
| Custom Python parse node runs in the engine, output byte-identical to standalone pypdf | **VERIFIED** (executed) |
| Tika is the engine's default PDF path, loaded in-process via JNI | **VERIFIED** (`engine --tika` → `com.rocketride.tika_api.TikaApi`; no separate `java` process ever appears) |
| No supported path to add a dependency to the engine's interpreter | **VERIFIED** (hand-copy; no manifest mechanism found) |
| PyMuPDF is AGPL-3.0 / Artifex dual-licensed | **VERIFIED** (package metadata) |
| pypdf is LlamaIndex's default PDF parser | **VERIFIED** (dependency metadata) |
| LlamaIndex silently returns `{}` for PDFs when the reader package is absent | **VERIFIED** (source) |
| Tika and pypdf agree to 99.10 % on a simple text PDF | **PROVISIONAL** — one generated, single-column, text-only PDF. Says nothing about scanned or multi-column documents, which is where parsers actually differ |
| Relative extraction **quality** on hard documents | **UNVERIFIED** — that is what Tier 2 exists to measure; no corpus selected yet |
| Relative **speed** of Tika vs pypdf | **UNVERIFIED** — not measured. Tika's JVM startup cost (per-request vs per-process) is also unmeasured and would dominate a per-document figure |

## The call is yours

I would pin both to pypdf for Tier 1 and keep Tika-vs-pypdf as Tier 2 with the quality axis. If you
disagree — particularly if you think the engine's Tika path is enough of a product differentiator
that Tier 1 should also use it — that is a reasonable position and it changes only which tier is
the headline, not the measurement design.

**Open before either tier runs:** whether Tika's JVM initialises once per engine, per task process,
or per request. It is loaded in-process via JNI, which suggests once per process, but that is an
inference and it would dominate any Tier 2 speed number if wrong. **~20 min to settle.**
