# RULING L — LI splitter 4000/0, the equivalence note (2026-08-30)

**What changed.** The LlamaIndex comparison arm's splitter overlap moved
200 → **0** (chunk_size stays 4000, split_unit stays chars). Three copies of
the value, changed together so no stale twin survives (entry 6/21):
`docker/Dockerfile.llamaindex-video:118` ENV (the operative copy the sweep
containers inherit), `li_video/service.py:58` env default,
`li_video/pipeline.py:112` constructor default. **The engine is untouched**:
its chunk config is inert (kwargs-filter, Ticket 3 / register entry 1) and
its splitter keeps running at LangChain library defaults 4000/200.
`li:video-anchor` is deliberately untouched — it exists to reproduce banked
AMI-era numbers and stays a 4000/200-era instrument.

**Why (the ruling chain).** LangChain realizes overlap in WHOLE split units
(`_merge_splits`: retain only while total ≤ 200), so the engine realized ~0
overlap on AMI's 1.7k-char lines; LlamaIndex's SentenceSplitter at 200
realized a true ~200 chars/boundary. That asymmetry IS the AMI
char_conservation 4.86% failure (ratio ≈ 0.9523 predicted vs 0.9529 measured
— CHAR_CONSERVATION_MECHANISM.md). The DEFINITIVE §2.4 ruled the adoption:
Leela's comparison arm ran 4000/0, her chunk_ratio sat in band
(workload_ratio 1.024) — "Credit to Leela; adopt 4000/0 on the comparison
arm in the next campaign." Ruling C deferred it out of the streaming
refactor (one variable at a time); Ruling L lands it BEFORE the posture
sweep, never between passes — chunk config changes the embed-stage workload,
so every posture number must be measured on the config the legs will use.

## What legitimately changes (LI arm only, forward runs only)

- **Chunk texts** — no more ~200-char duplicated tail re-appearing at the
  next chunk's head at pack boundaries. Any chunk-hash or chunk-text
  comparison against a 4000/200-era run WILL differ; that is the config, not
  a defect.
- **n_chunks** — effective new content per packed chunk goes ~3800 → ~4000,
  so ~5% fewer chunks on pack-limited content.
- **sum(chunk_chars) / total embedded chars** — drops by ~200×(n_chunks−1)
  per document on packed content; embed-stage work volume drops with it, so
  LI wall/throughput moves (bounded by the embed stage's share). This is why
  the ruling precedes the sweep.
- **char_conservation ratio (rr_chars/li_chars)** — the LI inflation term is
  gone; the ratio moves from the ~0.95 regime toward and slightly ABOVE 1.0.
  Residual asymmetry on films is now the ENGINE side: LangChain retains
  SHORT lines at boundaries on films-regime content (measured: 21 duplicate
  frame-starts on 20000Leagues, 395 real frames — probe artifacts at
  `7204a28`/`677bdda`), which our stripper strips for counting but which
  stays inside rr_chars. Direction rr/li ≥ 1.0; magnitude on films is
  HYPOTHESIS until films records exist. The films band is cut from films
  records at 4000/0 per the band's centred-on-measured-median rule
  (`probe/char_band_from_records.py`) — no AMI (≈0.953) or Corner (≈0.9817)
  centre carries over.

## What does NOT change

- **Frames, both arms** — extraction is upstream of both splitters;
  `expected_frames_measured` and the subset manifest (sha `54186c24…`) are
  untouched; gate 3 and frames_census unaffected.
- **Detections, embeddings semantics, models** — identical.
- **The RR stripper** (`driver_video.frames_from_chunks`) — still required:
  the engine still retains short lines on films (the 395-vs-416 counter
  finding stands).
- **RR-side goldens and fixtures** — the smoke's golden record is the
  ENGINE pipe (`record_from_rr`, bound to the RR image), and the PDF fixture
  stock counts are the engine's; neither is invalidated. No LI golden
  exists; films gate-8/chunk baselines are not yet cut (landing this first
  is the point).
- **Committed probe artifacts** — reader-equivalence/frame-parity/
  detect-text artifacts compare frames and detect fields, not chunk config;
  they remain valid records of what they measured.

## Era discipline

Chunk-level fields (n_chunks, chunk_chars, char sums, chunk hashes, embed
work, and any throughput that includes the embed stage) are CROSS-ERA
between pre- and post-Ruling-L LI runs — never compare silently (the
standing reader_semantics/stage_s_semantics discipline). The era marker is
the LI service's own `/health` `chunk_overlap` field; sweep artifacts now
carry `chunk_config_readback` (absence of that field in an artifact ⇒
4000/200 era). AMI-era banked numbers are NOT invalidated — they are
records of the 4000/200 era and the DEFINITIVE discloses that config and
its 4.86% consequence (§5.2, §2.4).

## Read-backs (the proof is layered, never asserted)

1. **Image env** — `docker inspect li:video` Config.Env carries
   `WS1V_CHUNK_OVERLAP=0` (run_ruling_l_box.sh, read-back 1).
2. **Parse + realization + null control** —
   `probe/verify_li_chunk_config.py` inside the image: the env var is
   PRESENT and parses to 0; the pipeline's own warm()-built splitter splits
   films-regime text with zero seam retention; a 200-overlap control on the
   same text MUST show retention or the check declares itself void
   (entry 1's boundary: config accepted ≠ config realized).
3. **Per-point, fail-closed** — `probe_films_curve.py` refuses any LI point
   whose `/health` does not read back `{4000, 0, chars}` on every instance
   (entry 12: the read-back is half of the measurement), and records the
   read-back in every point artifact. RR has no equivalent surface (inert
   config, no /health twin) — recorded as the honest asymmetry; its
   evidence is the detect-text/frame-parity probes.

## Flagged, not fixed here

- `driver_video.py:2326` hardcodes `chunk_overlap=0` in the provenance
  `chunk_config` block. For AMI-era LI exports that literal understated the
  realized ~200 (the DEFINITIVE's §2.4/§5.2 disclosure carries the truth at
  report level). Post-Ruling-L it is correct for LI. Whether the field
  should be populated from the arm's read-back instead of a literal is an
  export-schema question — Ansh's surface, not silently rewritten here.
- The driver's LI preflight (`li_readbacks`) records thread env, versions,
  weights — not chunk config. Before the first films LEG (not the sweep;
  the sweep probe covers itself), the preflight should gain the same
  fail-closed chunk read-back. Carried as a films-leg to-do.
