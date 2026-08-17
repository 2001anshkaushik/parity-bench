# M6 lines-of-code: the counting rule

**The rule is the finding. The number is downstream of it.** A reviewer should be able to reject
one cut without rejecting the whole measurement, so every removed line is listed in
`REMOVED.md` with its reason.

## 1. The counter (unchanged, Leela's)

`aws_bench/metrics/m6_loc.py::count_loc` at Leela `a5c3b5d`, imported and called — not
reimplemented, not tweaked:

* non-blank lines only
* lines whose first non-space character starts a `#` comment are excluded
* Python docstrings are excluded (tracked by a `"""` state machine)
* no `cloc`, no external dependency

## 2. The four layers (unchanged, Leela's)

| layer | what belongs in it |
| --- | --- |
| `pipeline_definition` | the description of the stages and their wiring |
| `compute_transforms` | the per-stage work a developer writes |
| `serving_integration` | how it is deployed and exposed |
| `client_harness` | the minimum code to send a document and read the result back |

**The load-bearing entry is Leela's `"compute_transforms": []` for RocketRide — "engine-internal:
product code, not user code".** The engine's stages are product; a developer does not write them.
Symmetrically, LlamaIndex's, LangChain's and pypdf's internals are not counted either. The rule
is symmetric; the *result* is asymmetric, and that asymmetry is the product difference the metric
exists to measure.

## 3. What "minimal" means — the knife, stated before it is used

A line is **benchmark-only** and is cut if and only if it exists to *measure, verify or compare*
rather than to *make the pipeline work*. Concretely, cut:

1. **Measurement instrumentation** — timing fields, per-stage traces, worker-count reporting.
2. **Readiness/observability apparatus a caller only needs because a harness polls it** — warm
   marker files, aggregate warm counts, census-validity flags, supervisor-identity keys.
3. **Declared-vs-measured audit machinery** — thread env read-back, resolved-device assertions,
   `concurrency_source` provenance strings, library-version manifests.
4. **Fault injection** — code whose only caller is a poison run.
5. **Cross-arm parity scaffolding** — returning the arm's own extracted text so a hash gate can
   build a reference; schema-version and manifest endpoints that exist for comparison.
6. **Alternate modes kept for experiments** — a second splitter mode, a second PDF parser, a
   second device path, when the parity configuration only ever uses one.
7. **Probe nodes and their dependencies** — code copied into an image solely so a gate can read
   something back.

A line is **kept** if removing it changes what the pipeline produces or stops it running:
the five stages, the model, the chunk configuration, the `text + "\n"` transform, HTTP serving,
error responses a caller must distinguish, and the pins that make the image reproducible.

**Both arms get the same knife.** Cutting only the arm that is losing is a thumb on the scale.
Here the scale tips *against* us — our LlamaIndex arm carries far more scaffolding than our
RocketRide arm does — which is exactly why the cut must be symmetric and exactly why the
as-built ratio is not the publishable number.

## 4. What is reported

Not one number. Two extremes and the range between them:

* **as-built** — what is in the repo today, scaffolding included. An *upper* bound on the
  LlamaIndex side and therefore on the ratio.
* **minimal** — the smallest functionally-equivalent implementation of the same five stages,
  same model, same chunk config, still served over HTTP. A *lower* bound.

The publishable claim is the **range**. A single number invites the argument about which cut was
fair; the range makes that argument bounded and explicit.

## 5. Correction to the previously reported figure

The as-built `client_harness` numbers reported on 2026-08-16 (llamaindex 140, rocketride 13) were
**wrong**. The slicer took each arm class from its `class` line to the next `class` line;
`LlamaHttpPdfArm` is the last class in `weekend_worker.py`, so the slice ran to end-of-file and
swept in ~130 unrelated lines. Both arms also excluded their base classes, where the connect /
token / transport work actually lives. Corrected here: each arm's client is counted as
**subclass + base class**, and the ratio is restated. The error inflated the LlamaIndex side,
i.e. it ran in our favour.
