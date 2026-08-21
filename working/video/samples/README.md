# Reading the Phase 2 video export — reviewer's guide

**Audience:** Shashi, Leela — reviewing `sample_export_blast.json` and
`sample_cross_gates.json` without having followed the build. The samples carry
**synthetic numbers in the real shape**: they are generated through the same
driver functions the box uses (`make_sample_export.py`), so the structure you
approve here is byte-shaped like what the real run emits. `_SAMPLE` at the top
of each file says so. Ten minutes, three sections: metrics, gates, what's
deliberately absent.

The workload: AMI meeting videos (44 measured, Corner view only) through a
six-node pipeline — frame extraction at 1 frame/15 s → RF-DETR object
detection per frame → detections-as-JSON → text split → MiniLM embedding —
on RocketRide (engine 3.3.1, patched) and LlamaIndex (FastAPI service),
identical weights (rf-detr-base, md5-verified in-container per run), identical
ffmpeg binary, identical sampling.

---

## 1. Metrics — what each block is, and the alternative it beat

**`throughput.total_frames_per_s` — the primary. Not videos/hour.** The
corpus spans **470.6 s to 2905.4 s per meeting (6.2×)**. Videos/hour rewards
whichever leg drew short meetings; frames are the unit of model work and their
count per video is fixed by duration, so frames/s is composition-independent.
Each arm's frame count is **read back, not assumed**: LlamaIndex counts at its
extractor; RocketRide's is recovered from the returned chunks themselves
(overlap-stripped bracket count, cross-checked by a second independent
decoder — the per-record `frames_observed_method` names the method).

**`total_realtime_factor` — the practitioner figure.** Video-seconds
processed per wall-second ("the system sustains N× realtime"). Derived from
manifest durations of completed videos; reported for both the window and the
span, like throughput.

**`steady_window` vs `total_span_s` — both, labelled, always.** At C
concurrent slots and a 6× duration spread, one 48-minute video holds the
total span open long after the queue drains — span throughput measures the
drain tail as much as the system. The steady window is
[first instant in-flight == C, last instant in-flight ≥ C], reconstructed
from per-item admit/done stamps; completions inside it are `window_n`, which
is structurally required to appear (an export without it cannot be written).
When the window is undefined (sequential legs, never-saturated runs) the
block says `defined: false` with the reason — it is never silently absent.
Neither number alone is honest; the pair plus `window_n` is.

**`latency_normalized` — wall-seconds per video-minute.** Raw per-video
latency is dominated by duration; normalizing by video-minutes makes videos
comparable while the raw `wall_s` and `video_s_manifest` stay in every record
so the confound remains visible rather than hidden. **Percentile policy:
p50, max, and n only.** No p95 below n=50 — nearest-rank p95 over 44 records
is the 42nd value, two from max, a percentile costume on a handful of samples.

**`submission_order`** is recorded in the export with its reason: manifest
order, deterministic by meeting id, identical on both arms — *not*
longest-first, because sorting to shorten the drain tail would benchmark our
scheduler rather than the frameworks.

**`preleg_load1` / `preleg_container_idle_cores` / `preleg_foreign_excess`** —
the quiet-box record. Values, not booleans: a background CPU hog contaminated
one day of Phase 1 runs and was caught **two days later** only because the
collector had recorded load numbers; a pass/fail bit could not have answered
that question. The gate refuses to start a leg when foreign load (load1 minus
what our own containers account for — the engine idles at ~1 core by itself)
exceeds 2.0. `driver_cpu` shows the driver's own share stayed negligible.

---

## 2. Gates — what each proves, its null control, and NOT RUN vs FAIL

**NOT RUN is a first-class verdict, distinct from both PASS and FAIL:** the
condition that arms the detector never occurred, so nothing was proven in
either direction. A NOT RUN never counts as a pass in any suite conjunction.
FAIL means the detector armed and fired. Every detector below ships with a
null control — an input that MUST make it fire; a control that cannot fail is
not a control.

| Gate | Proves | Null control | NOT RUN when |
|---|---|---|---|
| `frames_census` | frames extracted == the manifest's MEASURED expectation (counted through the arms' own ffmpeg at manifest build, not derived from duration), per video, both arms — the silent-frame-loss detector | observed N−1 vs measured N fires | leg never ran (a leg that ran and produced zero records is a FAIL) |
| `errors` | every offered video produced a record without error | an error row fires | — |
| `chunkid_monotone` | the engine's accumulate-then-split emitted one ordered split per video | out-of-order ids fire | — |
| `self_duplication_any` + `duplication_trigger` | the chunk-duplication engine defect (whole list emitted twice) did not occur. Tri-state: uniform-content records read *indeterminate*, never PASS or FAIL, because a static scene can produce identical chunks organically | doubled list fires; uniform list reads indeterminate | `duplication_trigger`: no record reached the 64-chunk flush threshold organically. Per-video eligibility is declared in the manifest in advance (`est_chunks_from_measured`, an estimate built from probe-measured detection density — 26.0 detections/frame, 230.4 chars/detection; a 21-min meeting estimates ~131 chunks, so most of the corpus clears 64 and only the shortest meetings may not). Measured `n_chunks` decides at run time; the estimate only plans |
| `detection_liveness` | a minimum fraction of frames produced ≥1 detection (a model serving garbage detects nothing) | a generated black video MUST fail this gate | threshold not yet supplied — it is probe-measured, and the code refuses to invent it |
| `embed_integrity` | every vector is 384-d and unit-norm within 1e-3, both arms | a 0.9 norm fires | — |
| `determinism_repeat` | the same video sent twice yields identical chunk hashes — nothing in this pipeline samples | one perturbed hash fires | blast legs (sequential legs produce the repeat) |
| `frame_count_methods_agree` | two independent frame-count recoveries agree on the RocketRide arm | forced disagreement fires | non-RR arms |
| `dropped_frame_attribution` | **not a gate — attribution.** The count census detects loss; this scrapes the engine log for its own drop warning to say *why*. Fail-closed on its own channel: if the log's liveness marker is absent, the result is UNKNOWN — a scrape that can only find nothing never reads as "no drops" | a fixture log line fires; a dead log reads UNKNOWN | — |

**Cross-arm file** (`sample_cross_gates.json`), in priority order:

- **`cross_detection_agreement` — strict, zero tolerance.** Identical
  per-frame label multisets across arms. Everything upstream is pinned and
  verified per run — same weights (checkpoint md5 read back inside both
  containers), byte-identical frames (probe-verified), same threshold, same
  package versions — so fp32 CPU inference should agree exactly, and any
  tolerance wide enough to absorb real divergence would also absorb a silent
  model swap, which is what this gate exists to catch. **Measured, it does
  agree: the staged one-video confirmation found EXACT per-frame
  label-multiset agreement on all 83 frames, reproduced in a second
  independent container the same day — zero tolerance is
  measured-achievable, not argued.** The gate arms via the recorded probe
  run id (`probe_20260821_195214`); unarmed it reports NOT RUN naming what
  arms it. `score_triage` accompanies
  failures as diagnostics — it deliberately **has no PASS key**, so it cannot
  become a verdict; only a human downgrades this gate, in writing.
- **`char_conservation` (±2%)** — measured workload parity: per-video sum of
  chunk characters, RR/LI. Same detections in, same text out; conservation
  within tolerance proves both arms processed the same workload. This
  *replaced* a config-equality check — configuration turned out to be exactly
  what could not be trusted (see §3).
- **`chunk_count_ratio` — reported, not gated.** The arms use different
  native splitters by design; the count ratio measures splitter semantics,
  not loss. A gated band may follow once real spread is observed.

---

## 3. The two postures, and what is deliberately absent

**RocketRide appears twice, side by side: `default` and `parity`.** Out of
the box, one pipeline token gives the engine a single detector instance
behind a process-local lock — with the engine's default 64 task threads, that
is a serial detection queue with 63 waiters. The `parity` posture runs M
independent tokens, giving RocketRide the same number of serving instances as
LlamaIndex has workers. **Neither alone is publishable:** default-only
measures a queue; parity-only conceals the out-of-box behaviour. Both, with
the posture labelled in every export, is the same controlled-experiment move
as Phase 1's per-document-vs-batch result — it isolates a configuration
effect from an architecture effect. Each arm otherwise runs at its **own
measured optimum** (workers, thread values — swept with the same method on
both arms, chosen per-arm from the curves, full matrix published, and every
export carries declared *and* in-process-measured thread values per arm;
undeclared asymmetry is the historical defect, not asymmetry itself).

**Not in the export, on purpose:**

- **Cross-arm chunk-hash equality** — declined, as in Phase 1: the arms split
  with different native splitters, so hash equality would fail for a
  non-defect reason. Conservation (chars) and detection agreement (labels)
  are the cross-arm truths that survive that difference.
- **p95** at these n (policy above).
- **docs/s and chunks-per-document as workload proxies** — document-shaped
  metrics that don't transfer; frames/s and char-conservation replace them.
- **Per-record PNG hashing** — frame byte-identity across arms is proven at
  probe scope (it is a gate there); doing it per record at leg scale would
  add I/O inside the measured span, distorting the measurement it protects.
- **Engine-internal stage timings on the RR arm** — the engine does not
  expose them client-side; LlamaIndex records carry `stage_s`, RR stage
  evidence lives in the probe. The export never fabricates a field one arm
  cannot measure.
- **Configured chunk sizes as provenance.** During bring-up we proved the
  engine's chunk-size configuration is silently ignored end-to-end (a
  constructor-kwargs filter drops it; the LangChain library defaults 4000/200
  are what actually run — engine ticket filed). Provenance therefore reports
  chunk configuration **measured from the records**, never the config
  literal. The same principle runs through the whole export: thread values,
  worker counts, weights, and interpreter are all read back from running
  processes, and where a value cannot be measured it appears as NOT RUN or
  `null` with a reason — never as an echo of what a config file intended.
