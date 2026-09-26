# P6 files note

- Every leg, block and canary directory is committed as the chain wrote it, EXCEPT the stamp files of the P6-B block legs (`p6b_*/p5_stamps.jsonl`, `p6b_*/p1_stamps.jsonl`). One container per arm served all of P6-B, so each block's stamp file holds every earlier block's rows too (23 MB by block 11). No P6 analysis reads them: P6-B is read from the records and exports; G_cell read them on the box when each block ended. They are in S3 at the paths listed, with sizes and sha256, in `p6b_stamps_s3_only.json`.
- `p6b_manifests/` holds the per-block manifests (the meta row, the warm rows, that block's measured rows) and the start-warm manifest.
- The control legs (`p6ctl_*`) are gate-control targets, not measured legs.
