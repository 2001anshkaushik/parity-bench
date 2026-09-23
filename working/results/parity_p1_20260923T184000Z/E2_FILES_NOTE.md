# E2 leg files: what is compressed

Each tracer-ON leg's `threadstate_<leg>.jsonl` (the 5 Hz /proc sampler, ~84 MB) and `pyspy_gil_<leg>.txt`
(py-spy's raw GIL samples) are landed as lossless gzip copies (`gzip -n`, `.gz` suffix). The uncompressed
originals are in S3 under `s3://rocketride-benchmark-data/ansh/parity-p1/parity_p1_20260923T184000Z/<leg>/`,
uploaded by the chain at the end of each leg. `working/scripts/p1_analyse_e2.py` reads either form; the
readings computed from the gzip copies are identical to those computed from the originals. Every other file is
as the chain wrote it.
