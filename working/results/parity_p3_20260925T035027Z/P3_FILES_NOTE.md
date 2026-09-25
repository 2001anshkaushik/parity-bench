# P3 leg files: what is compressed, what stays in S3, what stays on the box

- In the full-corpus legs landed with the deliverable (p3c_t4_full, p3d_hyb_full, p3d_pure_full), the per-document file
  (`perdoc_*.jsonl`), the stamps (`stamp_probe.jsonl`), the percore and the D0 samples are landed as lossless gzip copies
  (`gzip -n`). The uncompressed originals are in S3 under
  `s3://rocketride-benchmark-data/ansh/parity-p3/parity_p3_20260925T035027Z/<leg>/`. The P3 analysis computed from the
  compressed copies was checked equal to the one from the originals (byte-identical analysis JSON and per-document
  correctness file). p3a_rr_full and p3a_li_full were landed earlier, uncompressed.
- In S3 only: every `texts.jsonl.gz` (the chunk texts: the 384-slice P3-D legs, about 8 MB each; the full runs p3a_rr_full,
  p3d_hyb_full and p3d_pure_full, about 213-216 MB each) and every `vecs.jsonl.gz` (P3-C's embedding vectors, about 12 MB
  each). Pass their local copies to `p3_analyse_docs.py --texts-dir / --vecs-dir`.
- On the box only: the P3-B frame set (695 PNG frames under ~/p3b_frames_parity_p3_20260925T035027Z). Its per-frame sha256
  manifest is committed (p3b_frames_manifest.json), and every bare leg's bench.json carries each frame's sha256.
