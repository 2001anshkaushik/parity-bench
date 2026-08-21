# RocketRide-arm cross-check — three harnesses, one product (2026-08-21)

The competitor arms (LlamaIndex / LangGraph / Haystack) are not comparable
across harnesses. **The RocketRide arm is the same product in all three** —
this table compares only that axis. Sources: `team_docs_received/` — Leela's
`METRICS.md` (L-M) and `DATA_FLOW_PLAN.md` (L-D), Shashi's
`VIDEO-FULL50-RESULTS-2026-08-21.md` (S-R) — quoted as DATA per the hard
rule in `team_docs_received/README.md`. **Divergences are REPORTED, never
resolved here; Ansh asks the teams. UNKNOWN is a valid verdict.**

| # | dimension | ours | theirs | source | verdict |
|---|---|---|---|---|---|
| 1 | engine version + patch | 3.3.1 sha-pinned tarball, duplication patch, labels read back per run | Leela: "3.3.1 SHA-pinned + boot fix + duplication patch … never stock" | L-D:219 | **comparable** |
| 2 | pipe | `benchmark_video_detect.pipe`: grabber@15s → rfdetr thr 0.3 → langchain → miniLM → documents | same named pipe, same stages, both teams | L-D:44, S-R:6-7 | **comparable** (but see #6) |
| 3 | sampling rate | 1 frame / 15 s | 1 frame / 15 s | L-D:36, S-R:6 | **comparable** |
| 4 | embedder | multi-qa-MiniLM-L6-cos-v1, 384-d; identity read back per run | same string; Leela's trap 7 warns against the all-MiniLM lookalike | L-D:240-242 | **comparable** |
| 5 | corpus | 60 AMI ES-only, **Corner** view, video-only as shipped, no mux, 470–2905 s | Leela: full AMI, **Closeup1 + muxed audio**, 171 meetings; Shashi: 50 full-length, p50 43 min, view **unstated** | L-D:59-66, S-R:3-5 | **incomparable** (declared; different bytes enter the engine — view AND audio track differ) |
| 6 | **detections/frame on the same product** | **25.95 measured** (ES2002a.Corner, probe, exact recovery) | Leela: "ES ~3 … IB ~16"; Shashi: 29,451 det / ~9.3k frames ≈ **3.2** | L-M:116-117, S-R:14 | **DIVERGENT ×8 — the headline question.** Two candidate explanations, both UNKNOWN: (a) view composition (Corner sees the room; Closeup1 sees a face); (b) threshold routing — the engine's explicit-profile branch DISCARDS top-level config keys, so a threshold not nested under the `rfdetr` sub-object silently reverts to the library default. Ours is nested for exactly that reason. **Ask: where does their pipe carry the threshold, and what does one same-view video measure on each harness?** |
| 7 | thread config swept | six BLAS/OMP vars swept {1,8,32}, task threads default; **measured 2.3 → 8.5 cores as BLAS 1→8** on one video; knee 8; t32 pathological (Ticket 5) | Leela: BLAS pinned 1, task `threads=32` swept → "~6 cores regardless of configuration"; Shashi: OMP=1, RR_THREADS=32 → "flat 2.4 … architectural property, not a tuning issue" | L-D:198-203, L-M:75, S-R:43-64 | **DIVERGENT conclusions.** All three datasets are mutually consistent under the device-lock + intra-op mechanism (our Ticket 5): task threads add waiters, BLAS threads add workers. But both teams swept task threads **with BLAS pinned at 1** — the knob our curve moves was held constant in theirs. Their "regardless of configuration" is contradicted by our measured 1→8 BLAS curve. **Ask: has either team run a BLAS=8 point?** |
| 8 | RR effective cores | 2.3 (BLAS=1) / 8.5 (BLAS=8) during processing, single video | Leela ~5.85–5.59; Shashi ~2.42 — **they already diverge from each other** (Shashi flags it: "different pipe composition can move the constant") | L-M:75, S-R:66-68 | **DIVERGENT between all three**; config-correlated (see #7). Note our BLAS=1 point (2.3) ≈ Shashi's 2.42 |
| 9 | RR realtime factor | ~75× single-video at t8 (1248 s / 16.5 s) | Shashi 21–22× aggregate; Leela refs 36.2–40.7× blast | S-R:22,48-51, L-M:55 | **incomparable as published** — BLAS config, corpus density, and submission shape all differ; alignment on #7 + #10 is the path to one number |
| 10 | submission shape (RR blast) | per-video sends, C=BLAST_C, per-video records | Leela: native ingestion per arm — "ONE batched send_files"; Shashi: batch API (TTFR = whole span) | L-D:131-137,206-207, S-R:27 | **incomparable by design and DECLARED philosophy split**: they measure the arm's native batch path (Ticket 2 behavior included); we submit per-video on both arms (Ticket 2 behavior excluded). Both defensible; never mix the numbers |
| 11 | frame-count gate | expectation **measured per row** through the arms' own ffmpeg at manifest build (Crossroad 23); exact, no tolerance | both teams: `⌊dur/15⌋+1 ±1` formula, tolerance ±1 | L-M:34, S-R:13 | **comparable with caveat**: their ±1 absorbs the boundary off-by-one we measured (ffmpeg emits 83 where the formula says 84 on a 1248.3 s stream) — and therefore also absorbs any genuine single-frame drop. Report, don't push |
| 12 | storage amplification (RR writable layer) | **not measured by us — UNKNOWN** | Leela: ~1.0× retained for container lifetime, survives `terminate()`, caused an ENOSPC; Shashi: "does not reproduce … net 0.0" | L-M:85, L-D:161-168, S-R:77-80 | **the teammates contradict each other on our shared product**; we hold no data. Ask: what differs (engine build? scratch config? measurement point)? |
| 13 | weights identity | rf-detr-base.pth md5 vs registry constant, read inside both containers per run | Leela: shared `rr-model-cache` volume across arms (identity by shared artifact, no hash stated); Shashi: method unstated | L-D:224 | **UNKNOWN** (methods differ; no md5 published by either) |
| 14 | determinism / duplication gates | ordered chunk-hash repeat + tri-state whole-list-doubled + organic 64-trigger | Leela V0: `self_duplication` repeat_factor==1, `determinism` across reps; same defect class targeted | L-M:35-36 | **comparable** (same philosophy, independently arrived at) |
| 15 | corpus staging | EBS corpus, sha-manifest, page-cache eviction proven per leg | Leela: S3 → /dev/shm (RAM) staging, no disk in the read path | L-D:91-118 | **declared difference**: our cold-read numbers include disk; theirs cannot. Affects any I/O-sensitive comparison |
| 16 | `c<N>` mode | BLAST_C fixed-concurrency is our standard blast | Shashi: "not yet run (pending alignment with Leela)" | S-R:91-92 | **alignment opportunity** — three-way c<N> agreement would make one mode directly comparable |

## The three questions worth asking first (Ansh's call)

1. **#6 — detection density ×8**: one same-view video (an ES Corner file),
   run through each harness's RR arm, detections counted the same way —
   plus "is your threshold nested under the `rfdetr` profile sub-object?"
2. **#7 — the BLAS point**: one video at BLAS=8 on their configs. If their
   ~2.4/~5.9 moves the way our curve moved, the "architectural ceiling"
   conclusion in both their docs needs a caveat — and Ticket 5 already
   carries the mechanism.
3. **#12 — storage retention**: they contradict each other on the same
   engine; whichever reproduces, we should know before a 44-video leg runs
   on a container we keep up across postures.
