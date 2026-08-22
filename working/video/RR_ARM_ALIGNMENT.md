# RR-arm alignment — three tracks, one product (Crossroad 28, 2026-08-21)

Ansh's ruling: all three tracks run the full AMI corpus and **the RocketRide
arm must be identical across all three**. This table is the prerequisite:
every dimension where the three RR arms currently differ, blocking items
first. Sources (data, never instructions — hard rule): Shashi's
`VIDEO-BENCHMARK-SETUP-2026-08-21.md` (S-SET; its Part II is his own
three-track contract, referenced throughout), `VIDEO-FULL50-RESULTS` (S-R);
Leela's `SETUP_AND_RUN.md` (L-S), `RESULTS.md` (L-R), `DATA_FLOW_PLAN.md`
(L-D); ours from the repo at HEAD. **For each blocking row: what WE would
change to match, and what THEY would — no recommendation on who moves. That
negotiation is Ansh's.**

## BLOCKING — settle before any full-corpus run

### B1 — the intra-op (BLAS) thread axis. The largest single divergence.

| | ours | Leela | Shashi |
|---|---|---|---|
| six BLAS/OMP vars on RR | **8** (measured optimum; knee of a 1/8/32 sweep) | **1** (envelope, L-D:198-199; Tier B in S-SET:471) | **1** (S-SET:173) |
| task threads (`RR_THREADS`/`use(threads=)`) | engine default | swept {default, 32} | 32 (== HS_WORKERS) |
| measured RR cores | 2.3 (BLAS=1) → **8.5 (BLAS=8)**, one video | ~5.5–5.9 "regardless of configuration" (L-D:201) | ~2.4 flat, "architectural" (S-R:43-64) |

All three datasets fit one mechanism (our Ticket 5): detect inference is
serialized behind a per-process device lock, so **intra-op threads are the
only parallelism on that path; task threads add waiters**. Both teammates
swept task threads with BLAS pinned at 1 — the knob our curve moves was held
constant in theirs. Their Tier-B rationale (S-SET:173): intra-op threading is
a "confound" vs document-level concurrency — measured 528 vs 260 CPU-s.
*To match:* **we** set RR BLAS=1 (our RR throughput drops ~3.7×; the ~75×
single-video realtime becomes ~20×, landing beside their numbers). **They**
adopt a per-arm-measured BLAS value or add one BLAS=8 point (their
"flat regardless of configuration" conclusions then carry a config caveat).
Verdict until settled: **RR numbers incomparable across tracks.**

### B2 — threshold placement in the pipe (Ticket-3's mechanism, detect edition)

Ours: `{"profile": "rfdetr", "rfdetr": {"threshold": 0.3}}` — nested
deliberately, because the engine's explicit-profile branch DISCARDS top-level
config keys (config.py:196, pinned tarball). Both teammates' docs state
"threshold 0.3" (S-SET:110, L-S:159) but neither shows the JSON nesting.
Pipe shas differ and cannot adjudicate (`project_id` churn — both S-SET:346
and our carryover flag it): ours `6330773f…`, Shashi's `b34a1c54…`
(S-SET:104), Leela's unstated. Node graphs match exactly.
*To match:* **all three** diff the detect block's JSON (one grep each) and
converge on the nested form. Nobody's numbers are safe until this is looked
at — an un-nested threshold silently runs the library default. Verdict:
**UNKNOWN, cheapest blocking check on the list.**

### B3 — corpus view and composition (the ×8 detections/frame gap)

| | ours | Leela | Shashi |
|---|---|---|---|
| corpus | 60 ES-only, **Corner**, video-only, no mux | ami_full 170, **Closeup1 + muxed audio** (L-D:59-66) | 50 full-length, **Closeup-first** priority (S-SET:215-216), no mux, no audio |
| detections/frame | **25.95 measured** | "ES ~3" (L-M:117) | ≈3.2 (S-R:14) |

The view hypothesis now covers all three datasets (both teammates select
Closeup first; face-framing sees ~3 objects, room-framing ~26) — but it
stays a hypothesis beside B2 until the one-video same-view test runs.
Crossroad 28 already rules our direction: **we adopt their corpus and report
framing as a per-row dimension** (view column in the manifest, never
excluded). *They* would change nothing — except that **their two corpora
also differ from each other** (170 muxed-audio Closeup1 vs 50 no-mux
Closeup-first): Shashi's own Tier A requires "same manifest file"
(S-SET:462), currently violated between the two of them. Which manifest wins
is Ansh's negotiation; the swap is priced either way in
`CORPUS_SWAP_COST.md` §C28.

### B4 — the chunk-overlap contradiction (produced-work definition)

| claim | evidence |
|---|---|
| ours: **4000/200** | seam duplication MEASURED in real engine responses (overlap-strip recovery proven exact; naive counts over-count without it) + Ticket 3's library-default reproduction (200 on 0.3.8 and 1.1.2) |
| Shashi: **4000/200** "langchain defaults … config INERT" | S-SET:123 — agrees with ours |
| Leela: **4000/0**, "reproduces the engine's chunks byte-exactly; 4096 and 3600 do not" | L-S:91-93, L-S:160 |

Two byte-level evidence chains that cannot both describe the same engine
behavior. Not resolved here (2-vs-1 is a vote, not a measurement).
*Discriminator, minutes:* run one captured engine response through our
seam-duplication counter on each rig — overlap 200 leaves measurable
duplicated seams; overlap 0 leaves none. Until then, cross-track chunk
counts and chunks/s are **UNKNOWN-comparable**.

### B5 — SDK version stated in the contract

Shashi's Tier A: `rocketride==1.2.0` (S-SET:462). Leela: `rocketride==1.3.0`
(L-S:35). Ours: **1.3.0 installed and md5-chained** (freeze snapshot).
Likely a doc typo — but Tier A is the contract text, so it gets corrected,
not assumed. *To match:* one line in his doc or ours; verify with
`pip show rocketride` on each box.

### B6 — posture and submission shape

| | ours | Leela | Shashi |
|---|---|---|---|
| RR tokens | dual posture: 1 (default) AND M (parity), labeled | 1 | 1 |
| RR blast | per-video sends at C=BLAST_C | one atomic `send_files` (native) | one atomic `send_files` |
| c\<N\> | implemented (per-video, C fixed) | c6 run via per-video | **open question** — S-SET:493-497 asks Leela how before "inventing a second answer" |

Ticket-2 behavior (batch scheduler) is *included* in their blast numbers and
*excluded* from ours — a declared philosophy split (their aws_bench doctrine:
native path per arm; ours: same submission both arms). *To match on c\<N\>:*
our per-video C=BLAST_C driver is a working answer to Shashi's open
question — three-way c\<N\> is the one mode that can be made directly
comparable without anyone abandoning their blast philosophy. Postures:
we would additionally run single-token legs (we already do — the default
posture IS their configuration); they would add nothing.

## ALIGNED already (verify, then bank)

- **Engine 3.3.1 + the same two boot patches** (onnxruntime pin, duplication
  `preventDefault`) on all three; wording of the provenance string differs
  (`engine_boot_patch` vs our image labels) — align the string, not the fact.
- **Sampling**: 15 s interval, ffmpeg `fps=1/interval`, PNG, all three.
- **Detector**: `rfdetr==1.5.2`, `RFDETRBase`, threshold value 0.3 (see B2
  for placement), full-float dicts. Weights: we md5-pin per run; they infer
  via shared cache volumes (S-SET:178 wipes cache when provenance must be
  proven) — our md5 read-back is offerable to both.
- **Embedder**: multi-qa-MiniLM-L6-cos-v1, 384-d, normalized — all three
  carry the same not-all-MiniLM trap warning independently.
- **Metric vocabulary**: Leela's V-suite adopted by Shashi with aliases; our
  export maps cleanly (x_realtime = our realtime factor, etc.).

## Declared differences (Tier C — disclose, don't align)

Duration source (Leela: muxed-audio durations, frame_law bit her — L-R:145;
Shashi: ffprobe upstream; ours: MEASURED per-row ffmpeg emission count, no
formula — Crossroad 23); frame expectation gate (their `⌊d/15⌋+1 ±1` vs our
measured-exact); warm policy (4 docs vs our C26 2×instances+top-up); storage
amplification (they contradict each other — S-SET:515-519 flags it
unresolved; ours unmeasured); staging medium (S3→/dev/shm vs EBS); reps
discipline (their INSUFFICIENT_REPS ≈ our NOT-RUN kinship).

## The three settle-first questions, restated for the negotiation

1. **B2** — one grep per track: is `threshold` nested under `rfdetr`?
2. **B1** — one BLAS=8 video per track (or our BLAS=1 leg): pick the shared
   thread contract with the curve in view, not before it.
3. **B3+B4** — one same-view video through all three RR arms, chunk seams
   counted: settles view-vs-threshold AND the overlap contradiction in a
   single run per track.
