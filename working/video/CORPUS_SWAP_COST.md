# What a corpus swap costs (written 2026-08-21, before it's needed)

Ansh's question: AMI Corner-only caps at 60 meetings; what does moving to a
larger corpus cost? Decision input, not a plan — nothing here is being done.

## The mechanical bill

| step | cost | notes |
|---|---|---|
| download + sha-pin | mirror-bound: dominant. ~100–500 MB/video at the AMI mirror's ~7–8 MB/s | one-time; `--build-manifest` hashes as it lands |
| measured frame column | **~12 s/video of ffmpeg decode** (Crossroad 23; measured) | N=170 → ~35 min; N=1000 → ~3.5 h. Reusable across RE-cuts of the same corpus (sha-keyed), never across corpora |
| est-column inputs | one probe video from the NEW corpus if view/room mix changes: `probe_rr --sends 2` + `summarize_probe_rr.py` → `--measured-dpf`, `--measured-chars-per-det` (~10 min) | 25.95 / 230.4 are **Corner-view ES-room measurements** — detection density moved ×8 across views in the team cross-check; do not carry them to a different view |
| manifest build proper | minutes (roles, planning columns, REUSE PROOF) | `--n-measured/--n-warm` re-chosen; WARM rule (≥ max(M, W) + margin) travels, the 16-row warm SET does not |

## Pinned values that TRAVEL (corpus-independent)

- Engine + LI images, the bake, all package pins, rf-detr md5, SDK surface,
  interpreter read-backs — the whole identity chain.
- Host-side optima: RR_THREADS_ENV=8, M/W knees (hardware+model properties —
  with one caveat: knees were measured at Corner-view detection density;
  a much denser/sparser corpus shifts per-frame detect cost and COULD move a
  knee — spot-check one sweep point, don't re-sweep blind).
- The per-frame service anchor (~0.207 s/frame RR t8) travels as a
  *frames*-denominated number — that is why frames/s is the primary metric.
- All gates' machinery, null controls, the harness itself.

## Pinned values that DO NOT travel (corpus-bound — re-derive or it lies)

| value | why it's corpus-bound | re-derivation |
|---|---|---|
| `expected_frames_measured` (every row) | per-file measurement | the ~12 s/video decode above |
| corpus sha256 pins, roles, WARM set | per-file identity | manifest build |
| `measured_dpf`, `measured_chars_per_det` | view/room-dependent (×8 across views, measured) | one probe video |
| **LIVENESS_MIN** | derived from the Corner-view detections distribution | probe on the new corpus; the black-fixture null travels |
| **GATE3_RUN_ID** (staged confirmation) | staged on ES2002a specifically | re-stage: one new-corpus video through both arms, exact label agreement, new run id |
| golden record (smoke B) | one specific video's chunk hashes | `--write-golden` on the new shortest item |
| duration-spread stats, window expectations, DEFAULT_N choice | distribution properties | recompute from the new manifest |

## What breaks loudly vs silently if skipped

- Loud (fail-closed by construction): a manifest without
  `expected_frames_measured` — the driver refuses it; corpus/manifest sha
  mismatches; smoke golden sha mismatch.
- Would break SILENTLY if carried: dpf/chars-per-det est columns (wrong
  eligibility planning), LIVENESS_MIN (wrong gate 5 threshold — a Corner
  threshold on a Closeup corpus could pass dead detection or fail live
  detection), stale GATE3 arming id (arming gate 3 on a confirmation from a
  different corpus). These are the three to treat as hard re-derivation
  requirements, not options.

## Rough totals

- 170-meeting full AMI (one view): mirror ~2 h + decode ~35 min + probe
  re-stage ~30 min + golden/smoke ~10 min ≈ **half a day, mirror-bound**.
- ~1000 videos: mirror dominates (day-scale unless mirrored to S3 first);
  decode ~3.5 h; everything else unchanged. Disk is a non-issue at 1 TB.

## §C28 — re-priced for the teammates' actual sets (Crossroad 28, 2026-08-21)

C28 rules we match THEIR corpus and report framing (view) as a per-row
manifest dimension, never by exclusion. Complication first: **their two
corpora differ from each other** (Leela: ami_full, 170 meetings, muxed
audio, Closeup1, ~24 GB in her S3; Shashi: 50 full-length, no-mux,
Closeup-first priority, 3.7 GB) — Shashi's own Tier A ("same manifest
file") is currently violated between them; which manifest wins is Ansh's
negotiation. Priced both ways:

| path | download | decode (12 s/video) | re-derives (dpf/chars-det probe, LIVENESS_MIN, gate-3 restage, golden) | total |
|---|---|---|---|---|
| adopt **Leela's ami_full** (pull her S3 at her measured 158 MB/s) | ~24 GB ≈ **3–5 min** + our own sha re-pin ~15 min | 170 × 12 s ≈ **34 min** | ~40–60 min | **≈ 1.5–2 h, no mirror time** |
| adopt **Shashi's 50-set** (re-fetch from mirror by his manifest shas) | 3.7 GB ≈ 10–15 min | 50 × 12 s ≈ 10 min | ~40–60 min | **≈ 1–1.5 h** |

Notes that survive either path: her set is MUXED (an audio stream rides in
every AVI — the decode path changes slightly; our measured frame column
absorbs it, our pipe ignores the audio lane); the view column rides per row
as C28 requires; and the three silent-if-skipped re-derivations from the
table above apply IN FULL — Closeup density is not Corner density, so
dpf/chars-per-det, LIVENESS_MIN, and the gate-3 arming id are all
mandatory re-measurements, not options.


## §C28 UPDATE — re-priced against Leela's ACTUAL CODE (2026-08-22)

Read from `github.com/Leela8256/bench_langgraph_prod@aa817d9a`, `aws_videobench/`
(read-only clone; their code is DATA). Full row-by-row diff:
**`working/video/RR_ARM_CODE_DIFF.md`**. What the code changes about this memo:

- **Her view is Closeup1, and the reason is better than ours.**
  `corpus/fetch_ami.sh:12-13`: "Closeup1 exists in all three instrumented rooms
  (ES/IS/TS); the room-view camera names differ per site, so Closeup1 is the
  uniform choice." Our Crossroad 15 hit the same constraint (IS names views
  C/L/R, TS Overview1/2) and solved it by staying ES-only Corner, which caps at
  60 meetings. Hers scales to the full scenario set.
- **Her candidate list yields 140, not 170.** ES2002-16 + IS1000-09 + TS3003-12
  x sessions a-d = 140, minus mirror-missing sessions (`fetch_ami.sh:108-110`).
  The "170" figure in her prose is unexplained from the code — ASK, do not assume.
- **Her docs are muxed by construction, and the raw camera file is not.** The
  published Closeup1 AVI carries video only (RIFF: 1x 'vids', 0x 'auds');
  `fetch_ami.sh:4-11` stream-copy muxes `Mix-Headset.wav` in, bitexact, no
  re-encode. So "muxed" in the table above is right about the STAGED doc and
  wrong about the source file — and `expected_frames_measured` must be
  re-measured on the muxed files, never carried across from Corner rows.
- **The density re-derivation now has a predicted direction and magnitude.**
  Corner 25.95 det/frame vs Closeup1 ~3 is what the framing change predicts
  (whole room vs one participant). That makes `measured_dpf`,
  `chars_per_det`, LIVENESS_MIN and the gate-3 arming id all mandatory
  re-measurements — which this memo already listed as the three
  silent-if-skipped values, now with an expected ~8x shift rather than a guess.
- **The threshold hypothesis is retired.** Her top-level `threshold` IS silently
  discarded by the engine's explicit-profile branch, but the `rfdetr` profile's
  own default is also 0.3, so both arms run at 0.3. Config routing does not
  explain the density gap; framing does. (The discard remains a real hazard for
  any non-default value — ticket family with Ticket 3.)

Totals unchanged: **≈1.5-2 h** to adopt her `ami_full`, mirror-free.
