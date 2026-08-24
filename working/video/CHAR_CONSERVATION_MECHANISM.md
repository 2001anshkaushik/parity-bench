# char_conservation 0.953 on ami_full — mechanism, from source (2026-08-24)

Verdict up front: **overlap-realization asymmetry, not lost content.** Both
splitters are configured 4000/200; the engine's realizes **overlap=0 on this
corpus**, LlamaIndex realizes ~200. RR therefore embeds ~4.75% fewer
characters. Every detected character appears in RR's chunks (loss = 1 dropped
separator per boundary ≈ 0.04%); LI's sum is inflated by ~200-char duplicated
tails per boundary. Correctness of content: unaffected. Work volume: RR does
measurably less embed-stage work — disclose as an artifact WITH a work-volume
consequence, direction flattering RR, bounded by the embed stage's share.

## The chain, cited

1. **Config parity is TRUE and misleading (Ticket 3 reconfirmed).** The
   measured pipe's chunker is `preprocessor_langchain` (pipe components:
   webhook → frame_grabber → detect → preprocessor_langchain →
   embedding_transformer → response_documents). Its `_filter_kwargs_for`
   keeps only kwargs in `cls.__init__`'s signature
   [engine/nodes/preprocessor_langchain/langchain.py:90-102,202];
   `RecursiveCharacterTextSplitter.__init__` names only
   separators/keep_separator/is_separator_regex (+ **kwargs), so
   chunk_size/chunk_overlap are DISCARDED and the **library defaults 4000/200**
   run [pinned langchain_text_splitters/base.py:49-50]. Our LI:
   `SentenceSplitter(chunk_size=4000, chunk_overlap=200)`
   [li_video/pipeline.py:83-84,116-119]. Same numbers both sides.
2. **LangChain realizes overlap in WHOLE SPLIT UNITS.** `_merge_splits`:
   `while total > self._chunk_overlap: pop` — a unit is retained into the next
   chunk only if the retained total stays ≤200 chars [pinned base.py,
   _merge_splits]. The atomic unit on ami is a per-frame detection JSON line ≈
   **1,726 chars** (7.77 det/frame × 222.2 chars/det, B1) — every unit > 200,
   so **nothing is ever retained: effective overlap 0**.
   `keep_separator=False` default [base.py:52] additionally drops ~1
   separator char per boundary (~0.04% — negligible, and the only true loss).
3. **The arithmetic closes.** LI packs to its cap (measured median 3993, max
   4000 [RELAYED]) and realizes ~200/boundary:
   sum_li ≈ source × (1 + 200/3993) = source × 1.0501 → predicted ratio
   **0.9523** vs measured median **0.9529** [RELAYED] — 0.06% apart. RR chunk
   median 3349 ≈ two whole frame-lines (2 × 1,726 = 3,452), the no-fill
   signature of whole-unit splitting. Detection agreement 168/168 PASS
   [RELAYED] pins the upstream text as identical.
4. **The regime flip explains Corner vs ami.** Corner's frame line ≈ 25.95 ×
   230.4 = **5,979 chars > 4000** → the splitter recurses to finer separators
   (words ≪ 200) → overlap PARTIALLY realized on RR too → Corner's measured
   centre 0.9817 (Crossroad 38 band). ami's frame line 1,726 < 4000 → whole
   lines → overlap 0 → 0.953. One mechanism, two corpus regimes, both
   quantitatively matched.

## What it is NOT
Not dropped detections (gate 3 exact ×168), not serialization (Corner-era
byte-identical `_to_detection`), not the chunked write path (wire only), not
per-boundary content loss at scale (0.04%).

## Consequences
- **Crossroad 38's band was calibrated on the Corner REGIME** (centre 0.9817);
  ami sits in the other regime (≈0.953). Re-centring for ami is Ansh's ruling
  per the band's own centred-on-measured-median rule — not a widening.
- Disclosure sentence (draft): "Both arms are configured 4000/200; on this
  corpus the engine's LangChain splitter realizes zero overlap (whole-unit
  retention vs 1.7k-char units) while LlamaIndex realizes ~200, so RocketRide
  embeds ~4.75% fewer characters. Identical detected content; the asymmetry
  is overlap realization, corpus-regime-dependent (Corner: ~1.8%)."
- [INFERRED] LlamaIndex SentenceSplitter's ~200 realization is inferred from
  our config + measured packing + the 0.06% arithmetic fit; its source is
  container-installed (unpinned) and not in this repo.
- Box reconstruction (later, not while the 8-token leg runs): per-video
  sum(chunk_chars) both arms + n_chunks both arms from the two records files;
  expect ratio ≈ 1/(1 + 200×(n_li−1)/sum_li) per video, RR n_chunks > LI, and
  RR sum ≈ frame-line total + newlines.
