# `archive/` — superseded material, retained deliberately

**Nothing in this folder is current. Do not quote from it.**
Current statements live in [`../publishable/README.md`](../publishable/README.md); the authoritative
record of what still stands and what was withdrawn is
[`../publishable/STATE.md`](../publishable/STATE.md) **§5**.

---

## What is here

| | |
| --- | --- |
| `docs/` | 21 superseded documents — earlier findings, earlier framings, and the full narrative progress log |
| `results/` | result files whose findings were later withdrawn |
| `scripts/` | 9 deprecated harnesses. Each **exits non-zero if executed**, with an explanation of why it was retired. A quarantined script that still runs will eventually get run. |

## Why it is kept rather than deleted

This project withdrew more findings than it kept. Several were withdrawn twice — a correction that
was itself wrong, then corrected again. That history is the most reliable thing here: it is the
evidence that the numbers which survived were actually tested, and it is how a reader can tell a
verified result from a plausible one.

Deleting it would leave a repo that looks more confident than the work justifies.

**Every withdrawal is listed with its reason in `STATE.md` §5.** If a number in this folder
contradicts one in `publishable/`, `publishable/` is correct and §5 explains why.

## ⚠️ Phrasing here predates a review pass

These documents were written when the only reader was me. Before sharing, `publishable/` and
`docs/progress.md` were reviewed so that observations about colleagues' environments state the
technical fact without an attached verdict — for example, *"a combination the release manifests do
not pair"* rather than *"already mismatched"*, and *"reconstructing that environment needs the
commit rather than a published artifact"* rather than *"not reproducible"*.

**The rest of this folder was deliberately left unedited.** Rewriting an archive retroactively
would defeat the purpose of keeping one: the point of a correction history is that it is not
groomed. So some documents here — `docs/FINDINGS_FOR_WS1.md` most directly — still carry the
blunter original wording about version pairings in teammates' repositories.

**Read those as first-draft engineering notes, not as considered assessments of anyone's work.**
Where the same observation appears in `publishable/`, the `publishable/` wording is the one that
was reviewed and is the one that stands.

**One inconsistency, disclosed rather than hidden:** `docs/progress.md` *was* edited in that review
pass, before the decision to leave the archive untouched. So this folder is not uniformly
pre-review — one file in it reflects the reviewed phrasing and the others do not. The edits to
that file changed wording only; no finding, number, or date in its body was altered except two
session headings whose day and number were transcription errors, which the file itself records.

## What is *not* wrong with this folder

The material here is superseded, not false. Most of it was correct when written and was replaced
because a better measurement came along — a longer run, a second method, a controlled test that
separated two explanations. A few entries were genuinely mistaken, and those say so at the point of
the claim.

Attributions to colleagues' work throughout are overwhelmingly confirmations: *"Leela's 'MiniLM CPU
embedding' is correct"*, *"confirming Leela's Stage 0 #9 finding"*, and grounded facts sourced to
her findings documents. Those needed no revision and received none.

## If you only want the current picture

1. [`../publishable/README.md`](../publishable/README.md) — headline results with their labels
2. [`../publishable/BENCHMARK_SETUP.md`](../publishable/BENCHMARK_SETUP.md) — how to build and run it
3. [`../publishable/STATE.md`](../publishable/STATE.md) §5 — every number that did not survive, and why

Then ignore this folder entirely.
