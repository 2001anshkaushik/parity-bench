# Team message — Leela, Shashi

**Draft for Slack. Ansh · 2026-08-13.** Everything here is measured on engine `3.3.1.35` unless
labelled otherwise. Four items: two confirmations of Leela's work, a warm-up number, and a working parse reference
with a real-data demonstration of what the determinism gate cannot see.

---

**1. Both your expected-fail documents reproduce on 3.3.1 — cross-version confirmation.** [VERIFIED,
2/2]

`000164.pdf` and `000357.pdf` both return **0 documents** on our engine, the same "no documents
returned" failure you recorded on 3.2.1. Two teams, two engine versions, two harnesses, same two
documents. That moves it from "a thing Leela's setup does" to a product behaviour worth filing.

**2. Heads-up on `EXPECTED_FAIL` — it will pass vacuously on our corpus.** [VERIFIED]

`pdf500/census.py:14` hardcodes `{"000164.pdf", "000357.pdf"}`. Our GovDocs1 files are named
`000_000164.pdf`, so on our corpus the set matches **zero** documents and the expected-fail check
silently succeeds without checking anything. The documents *are* there — just under a different
prefix.

Suggestion: derive the expected-fail set from the corpus manifest rather than hardcoding filenames —
a one-time characterisation pass that records each document's expected outcome next to its sha256,
versioned with the corpus. It then survives corpus growth and different naming schemes. Happy to
build it if you want it; the finding underneath is yours and it is solid.

**3. Warm-up: 100 documents, not 25.** [PROVISIONAL — one fixture document, one host, n=1 per rep]

Measured by repeating a single document 200× with size held constant, so any trend is warm-up rather
than document-size variance:

| reps | LlamaIndex | RocketRide |
| --- | ---: | ---: |
| 0 (first request) | 1.61× steady | **4.04× steady** |
| 10–25 | 1.14× | 1.06× |
| **25–50** | **1.08×** | 1.05× |
| 50–100 | 1.07× | 0.99× |
| 100–200 | 1.00× | 1.00× |

**RocketRide is within 5 % by rep 25 — 25 is fine for that arm.** LlamaIndex is still **8 % inflated
at reps 25–50** and only reaches steady near rep 100. A shared warm-up has to satisfy the slower arm,
otherwise we bake an 8 % bias into one arm and not the other, which is exactly the shape of a false
finding.

(First attempt at this measured 400 consecutive corpus documents and was thrown away: GovDocs1 sizes
span **2018×**, so it measured document size, not warm-up. Worth knowing if either of you measures
it the same way.)

**4. We have a working parse reference now — and a real-data demonstration of the gate gap.**

Replacing the open question I was going to send you. Build the chunk reference from **the engine's
own `parse` output**, tapped off the `text` lane with a second `response_text` node, rather than from
standalone Tika. Both sides then come from the same in-process Tika, so the glyph-mapping problem
that broke my earlier attempt disappears: **97/98 documents match exactly**, against 4-in-5 false
failures the other way.

**The demonstration, on a real corpus document — no synthetic fixture needed.** `000_000159.pdf`,
three runs through the full pipeline:

| gate | result |
| --- | --- |
| determinism (n=3) | **PASS** — 164 chunks every run |
| structure (384-d, finite, L2 1.0 ± 0.001) | **PASS** — all 164 vectors valid |
| census (1 offered = 1 successful) | **PASS** |
| parse-tap reference | **FAIL** — `chunk COUNT 164 != reference 82` |

The engine returns that document's chunk list **twice, concatenated** — 82 unique chunks, emitted
164 times, first half == second half == reference. Every vector is individually valid and the
response looks healthy, so all three gates pass while the content is silently stored double-weighted.
That is the concrete version of the blind spot I was going to describe in the abstract.

**Scope, measured rather than assumed.** It catches defects **downstream of** `parse`; it cannot
catch defects **inside** parse, because it trusts parse by construction. Worth having anyway.

**It did NOT catch our NUL case, and the reason is worth your time:** on `038_038716.pdf` — the
document we recorded as losing 98.9 % of its text under the old topology — the engine's **own parse
output contains no NUL at all**. Tika does not emit the NUL that pypdf did. So there was nothing
downstream to lose. **Our ~0.30 % NUL prevalence was measured parser-out with pypdf and should not
be quoted for a Parser IN run until re-derived from Tika extractions.** The defect itself is
unchanged and still reproduces (`'AAAA\x00BBBB'` → `'AAAA'` on 3.3.1.35, re-verified today).

**Duplication prevalence so far [PROVISIONAL]:** 1/98 on an arbitrary 100-document sample, plus a
second instance found on a size ladder — `009_009442.pdf` at **2.25 MB**, also exact doubling. But
documents at 3.00, 3.01 and 4.00 MB are clean, so it is **not a simple size threshold**. Two
instances, exact `[ref+ref]` doubling both times, mechanism unknown. If either of you sees a
chunk-count ratio near 2.0 against your own reference, that is this.

**Since drafting the above, both open threads closed [VERIFIED]:**

* **Duplication is now a filed bug with a 4-line synthetic reproducer** — any text payload over
  ~239.8k chars gets its full chunk list emitted **twice** (threshold bisected to 781 chars,
  deterministic n=3 both sides, factor exactly 2 up to 750k). Not the document, not the PDF, not our
  harness: pure repeated ASCII triggers it. `BUG_CHUNK_DUPLICATION.md`. Check any long-document
  results you have for chunk counts at exactly 2× expectations.
* **NUL truncation has no observed path under Parser IN**: 0/303 documents show NUL — or any control
  character — in Tika output, including the three that produce NULs under pypdf. The defect is still
  live on text-lane paths; the 0.30 % figure was pypdf-specific and is re-scoped in the bug report.

If you want the tap pipe and the reference builder, they are in our repo and portable —
`working/pipes/product_pdf_tap.pipe` plus `harness/chunk_hash.py`.

