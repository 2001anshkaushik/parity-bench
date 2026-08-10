# Two Premises, Tested Before They Became Architecture

**Both settled empirically. Both were wrong.** Ansh · 2026-08-07.
Evidence: `pdftest/`, `working/dossiers/`, `working/nodes/pdf_probe/`, `working/results/pdf_parser_diff.json`.

---

## Summary

| premise | verdict |
| --- | --- |
| "RocketRide doesn't allow custom parsing nodes, so Tika is architecturally forced" | **REFUTED** — a custom Python parse node loads and runs and produces byte-identical output to standalone pypdf |
| "PyMuPDF is the best-in-class production parser choice" | **REFUTED on licensing** — PyMuPDF is **AGPL-3.0** (or paid Artifex commercial). Permissive alternatives exist and one of them is already LlamaIndex's default |

Neither premise survives, and together they change the parser plan: **the parser is a free choice on
both sides**, so it can be made identical rather than worked around.

## 1. Custom parse nodes work — Tika is a default, not a constraint [VERIFIED by execution]

Built `working/nodes/pdf_probe`, a node that takes a filesystem path and extracts with **pypdf** instead of
the engine's built-in Tika/JNI path. Installed it, restarted the engine, sent it the test PDF:

```json
{"node": "pdf_probe", "pid": 1313, "python": "3.12.13",
 "lib": "pypdf 6.15.0", "pages": 3, "chars": 15065,
 "head": "PARSER DIFFERENTIAL TEST DOCUMENT"}
```

**15,065 characters — byte-identical to the standalone pypdf extraction of the same file.** The
engine loaded a third-party-dependency parse node, ran it in its embedded CPython 3.12.13, and
returned the result through the normal response lane.

**Consequence:** the claim that comparing Tika-vs-pypdf is unavoidable is false. Option **C** in
`PDF_PIPELINE_NOTES.md` (force both sides onto the same Python parser) is viable and is now the
cheapest way to make the framework comparison clean.

**Cost, and it is a real one [VERIFIED]:** pypdf is not in the engine's embedded interpreter, and
there is no documented package-management path for adding it. I installed it by **copying the
package directory into `engine/lib/python3.12/site-packages/`**. That works, but it is not a
supported deployment story — it is not reproducible from a manifest, it will not survive an engine
upgrade, and it has to be redone in any container image. **This belongs in
`TOIL_INSTRUMENT.md` §4 as a RocketRide configuration/deployment entry.**

> *Hostile reviewer: "You proved a node can import a library you hand-copied into the runtime. That
> is not a supported extension mechanism."*

Correct, and both halves are reported: the engine **does** execute custom parse logic (so Tika is
not forced), **and** getting a dependency in front of it has no supported path (so it costs
something). Those are separate findings and neither cancels the other.

## 2. PyMuPDF is AGPL — the licence disqualifies it before performance matters [VERIFIED]

Run through `verify_frameworks.py`:

| package | version | licence | permissive? | last release | status |
| --- | --- | --- | --- | --- | --- |
| **pymupdf** | 1.28.2 | **Dual: GNU AFFERO GPL 3.0 or Artifex commercial** | **REVIEW_REQUIRED** | 2026-08-06 | ACTIVE |
| **pypdf** | 6.15.0 | **BSD-3-Clause** | **YES** | 2026-08-06 | ACTIVE |
| **pdfplumber** | 0.11.10 | **MIT** | **YES** | 2026-06-15 | ACTIVE |
| pdfminer.six | 20260107 | MIT | YES | 2026-01-07 | **STALE** |

**Why AGPL is disqualifying here specifically.** AGPL-3.0's network clause extends copyleft to
software offered *over a network* — not just distributed software. An embedding service is exactly
that shape. Using PyMuPDF in it would, on the AGPL branch, oblige us to offer the service's
corresponding source under AGPL. The escape is Artifex's **paid commercial licence**, which is a
procurement decision with a cost, not a default.

**This is an enterprise-adoption constraint, not a benchmark constraint.** It does not stop us
measuring PyMuPDF; it stops us *recommending* it, and it means "PyMuPDF is faster" is not by itself
an argument for shipping it.

**Recommendation: pypdf (BSD-3-Clause).** It is permissive, actively maintained, and — decisively —
**already what LlamaIndex ships**: `llama-index-readers-file` 0.6.0 requires `pypdf<7,>=6.1.3`,
with `pymupdf` only as an opt-in extra. Choosing pypdf is therefore *both* the permissive choice
*and* the framework-default choice, so it needs no special justification in a fairness argument.

**pdfplumber (MIT)** is the reserve option if table extraction quality turns out to matter; it is
built on pdfminer.six and is slower but layout-aware. **pdfminer.six** is MIT but flagged STALE —
last release 2026-01-07 — so it is not a primary choice.

**Not established [UNVERIFIED]:** the *quality* ranking of these parsers on hard documents. The
one measured comparison (§3) used an easy PDF. Extraction quality is measured in
`TWO_TIER_PARSER_DESIGN.md`, not assumed from popularity.

## 3. What the measured parser diff actually showed [PROVISIONAL — one easy document]

3-page generated text PDF, Tika (engine's own path) vs pypdf:

| | vs ground truth | chars |
| --- | ---: | ---: |
| pypdf | **100.00 %** | 15,065 |
| Tika | 99.10 % | 12,432 |
| Tika vs pypdf agreement | 99.10 % | |

Both preserved ligatures (`fi fl ffi`), unicode (`café`), formatted numbers (`1,234.56`) and
table-column tokens. Tika's shortfall is partly my own incomplete stripping of the JVM log lines it
interleaves into stdout — an operational note in its own right.

**Scope limit, stated plainly:** this is the easiest possible PDF — generated, text-only, single
column, no embedded fonts, no scan. It shows the harness works and that the two do not diverge on
trivial input. **It is not evidence about real documents**, which is exactly where parsers differ,
and it must not be quoted as though it were.

## 4. What follows for the plan

1. **Use pypdf on both sides** for the framework comparison (Tier 1). Same parser, same version,
   same output — parser choice stops being a confound instead of being argued about.
2. **Keep Tika in the product comparison** (Tier 2), because it is what the engine ships by default
   and that is a genuine product difference worth measuring — on both speed *and* extraction
   quality.
3. **Do not adopt PyMuPDF** without a procurement decision on the Artifex licence. If someone wants
   its speed, that is a business conversation, not a technical default.
4. **Record the engine-dependency-install gap** as toil.

## 5. Labels

| claim | label |
| --- | --- |
| Custom Python parse node loads and runs in the engine | **VERIFIED** (executed; output byte-identical to standalone pypdf) |
| Tika is the default, not architecturally forced | **VERIFIED** (follows directly) |
| No supported path to add a dependency to the engine's interpreter | **VERIFIED** (hand-copied into site-packages; no manifest mechanism found) |
| PyMuPDF is AGPL-3.0 / Artifex commercial dual-licensed | **VERIFIED** (package metadata) |
| pypdf BSD-3, pdfplumber MIT, pdfminer.six MIT-but-stale | **VERIFIED** (package metadata) |
| pypdf is LlamaIndex's default PDF parser | **VERIFIED** (`llama-index-readers-file` 0.6.0 requires `pypdf<7,>=6.1.3`) |
| Tika and pypdf agree to 99.10 % on a simple text PDF | **PROVISIONAL** (one easy document) |
| Relative extraction quality on hard documents | **UNVERIFIED** — measured in `TWO_TIER_PARSER_DESIGN.md`, not before |
