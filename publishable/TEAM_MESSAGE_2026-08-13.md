# Team message — Leela, Shashi

**Draft for Slack. Ansh · 2026-08-13.** Everything here is measured on engine `3.3.1.35` unless
labelled otherwise. Four items: two confirmations of Leela's work, one warm-up number, and one open
question I do not have an answer to.

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

**4. Open question — the determinism gate has a blind spot, and I do not have a fix.**

Comparing each arm against itself across two runs catches **non-determinism**, which is real and
worth gating. It cannot catch **deterministic data loss**, because a deterministic defect reproduces
identically in both runs and the comparison agrees with itself.

Concretely, on our NUL-truncation defect (engine truncates returned `page_content` at the first NUL
byte, same place every time): a self-comparison gate passes **3/3** on a document that lost **84 %**
of its text. 100 % agreement on 100 % data loss.

**What I do not have is a working independent reference for the RocketRide arm.** I tried running the
engine's own Tika 3.2.3 standalone — same jars, same `tika-config.xml`, separate process — and it
does **not** reproduce the engine's in-process output byte-for-byte. Glyph mapping differs: engine
`long term` where standalone gives `long‑term` (soft hyphen), engine ` ` where standalone gives
` `. Same version, same config, JVM defaults already matching (UTF-8 / en / US). Root cause not
found. Used as a gate on 50 documents it produced 5 failures, **4 of which were this mapping
difference rather than an engine defect** — so it is worse than useless as a gate right now.

So: **has either of you got a better idea for an independent RocketRide parse reference?** Options I
can see, none verified:

* reconcile the standalone/in-process Tika difference (I could not, in the time I gave it)
* a structural check that does not need byte equality — e.g. assert chunk boundaries and counts
  against the arm's own parse output, catching loss without requiring exact text
* accept that no independent reference exists for this arm and rely on the LlamaIndex arm plus
  content-sanity checks (NUL presence, printable ratio) to catch the same defect classes

One candidate that looked better and is **not yet verified**: build the reference from the engine's
own `parse` output, tapped off the `text` lane with a second `response_text` node, instead of from
standalone Tika. On 98 documents that matched **97/98 exactly** — against 4-in-5 false failures from
the standalone route. It only checks everything *downstream* of parse, which is a real limitation.

**I could not confirm it catches the NUL case**, and the reason is worth knowing if either of you
tries it: our NUL reproducer is `text/plain`, and `parse` consumes the `tags` lane, so plain text
bypasses parse and the tap comes back **empty**. The gate then "fails" by comparing chunks against an
empty reference — a false positive, not a detection. Testing it properly needs a PDF with a NUL in
its extracted text, which I have not built.

I am not proposing the standalone-Tika route. It is advisory in our repo and explicitly marked
does-not-travel to AWS.

---

Everything above is in `publishable/PRE_AWS_READINESS.md` with the raw numbers.
