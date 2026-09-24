# P1 docs and P1-D leg files: what is compressed, what stays in S3

In the full-corpus legs (p1b_base_full, _r1, _r2, p1b_fix_full, p1c_hyb_full, p1c_pure_full) the per-document
file (`perdoc_*.jsonl`), the stamps (`stamp_probe.jsonl`), the percore and D0 samples are landed as lossless
gzip copies (`gzip -n`); in v1full_rr_t4 the collector, percore, filesystem-stream and memory samples are. The
uncompressed originals are in S3 under `s3://rocketride-benchmark-data/ansh/parity-p1/parity_p1_20260923T184000Z/<leg>/`.
Every full run's `texts.jsonl.gz` (the returned chunk texts, about 216 MB each) is in S3 only. The analysers
read either form of every landed file; the analysis computed from the compressed copies was checked equal to
the one from the originals for E2 (E2_FILES_NOTE.md).
