# AMI export landing — traceability for AMI_CROSS_TEAM_TABLE.md

Source: `s3://rocketride-benchmark-data/ansh/video-ami-20260826/` (fetched
from the laptop, SSO profile `rocketride`). Every file below was landed
byte-for-byte under its original run-directory name; sha256 computed at
landing. **Identification is by contents, not by directory name** — the
in-repo `mainrun_20260823T034358Z/run_manifest.json` had already shown a
name can carry a dry pass. Each banked cell was located by matching the
export's recorded `total_frames_per_s` to the banked value across all 43
exports in the archive (25 RocketRide exports scanned; six matches, no
ambiguity — no other export in the archive carries any of the six banked
f/s values).

## Cell → export identification

| cell | pass | f/s (export=banked) | file |
|---|---|---|---|
| RR 16×2 | 1 | 12.729 | `mainrun_20260824T025550Z/export_rocketride_video_parity_blast.json` |
| RR 16×2 | 2 | 12.753 | `mainrun_20260824T025550Z/export_rocketride_video_parity_blast_p2.json` |
| RR 8×4 | 1 | 11.694 | `apples_20260826T041510Z/export_rocketride_video_parity_blast.json` |
| RR 8×4 | 2 | 11.571 | `apples_20260826T052915Z/export_rocketride_video_parity_blast_p2.json` |
| RR default | 1 | 2.443 | `mainrun_20260824T025550Z/export_rocketride_video_default_blast.json` |
| RR default | 2 | 2.446 | `mainrun_20260824T025550Z/export_rocketride_video_default_blast_p2.json` |

The 16×2 and default pairs come from the resumed 24-Aug campaign run; the
8×4 pair comes from the apples session, whose two passes sit in two
directories (the session restarted between passes). The superseded 8×4
single (12.048) is `equalconfig_20260824T213655Z/` — located, not landed.

## Landed files (sha256 at landing)

```
176bbb1621c5b789bd6433179530622e89a1788e0539192753f1f4b2e64e64cd  mainrun_20260824T025550Z/run_manifest.json
003b38b860343f914edb04f025fb21c36a306c3833211b57cf8f3cf3bb7a19f4  mainrun_20260824T025550Z/export_rocketride_video_parity_blast.json
a28645a5583418c1039d5f11f2d9582612de162803ecb98624112f49f804cc2b  mainrun_20260824T025550Z/export_rocketride_video_parity_blast_p2.json
050f0e9069428977b745e62754ec0f1acf9e929ca18616e69a38f0c5eb2c3054  mainrun_20260824T025550Z/export_rocketride_video_default_blast.json
d0586714ed2e72e333d245f003da63c8abd35794746d812497ab6cc183915c0b  mainrun_20260824T025550Z/export_rocketride_video_default_blast_p2.json
8a9bdb8fe82e3cc037379a26c87069ce56ba8159a2a66e78bb383cdf228fd9ad  mainrun_20260824T025550Z/collector_rocketride_video_parity_blast.summary.json
fb4af75d366a22b3fbd9d7d16b3c51c4461f86e4fa91302811c3c3f83e6f64f3  mainrun_20260824T025550Z/collector_rocketride_video_parity_blast_p2.summary.json
4edbca65bf5e1843dde98e3c532092bd8061f9e9ef26f94fbd76d255bafbcb2f  mainrun_20260824T025550Z/collector_rocketride_video_default_blast.summary.json
3700b01bfea61e43674c7a5d2376378c1f0ec15eb8f198bb42c12f6fc339a7ab  mainrun_20260824T025550Z/collector_rocketride_video_default_blast_p2.summary.json
889e0f5adb6c7912b6eb1a73b84ea7d7e27fd4e198b3424feccf3bae6df14e01  apples_20260826T041510Z/export_rocketride_video_parity_blast.json
4b92d2914a00810cab75ab5ed805391131e1de593963c71f6d98e0181d2bc430  apples_20260826T041510Z/collector_rocketride_video_parity_blast.summary.json
a34457c066e4868ecc7a196f91d5b17de1517eb0f415163e2f76005a128778eb  apples_20260826T052915Z/export_rocketride_video_parity_blast_p2.json
f969f485a89528b8fd9f2cb27e62fb640d92e0cf815ad0ca482c269002cb8395  apples_20260826T052915Z/collector_rocketride_video_parity_blast_p2.summary.json
2c85a5f576133844638940dadb752abaeb7a709f038246d046dca647fe467fe0  resume_console_20260824T074227Z.log
```

`resume_console_20260824T074227Z.log` sits at the archive's top level on
S3 (key `ansh/video-ami-20260826/resume_console_20260824T074227Z.log`);
it is landed here beside the run directories.

## The pass-1 errors gate reads FAIL — and no measured figure is affected

**Verdict first**: both pass-1 exports in `mainrun_20260824T025550Z`
report `gates.errors: PASS=false, n_errors=16`, and all 16 are corpse
rows of an aborted launch, not failures of the measured run — every
throughput, CPU and memory figure quoted from these exports is computed
on the 168-record completed set and is unaffected. The basis for that
verdict, classified from the full records files (fetched, not landed —
hashes below): `n_records=184` (= 168 + 16), while both pass-2 exports
read 168/0. All 16 error rows are `role=measured` rows for 16 distinct
videos, enqueued **~1.9 h (parity) / ~3.3 h (default) BEFORE the leg's
first completed row**, each dying instantly at send
(`ConnectionError('Could not send request')` /
`AttributeError("'NoneType' object has no attribute 'is_connected'")`),
and **every one of the 16 videos also completed OK later in the same
file**. These are corpse rows from the campaign launch that died at its
first 16 blast sends (BLAST_C=16) — the incident our session record
already documents (SESSION_STATE.md:99 "LAUNCH 5 (RESUME) DIED
IDENTICALLY AT THE FIRST BLAST SENDS with ttl=0"; the Crossroad-42
resume fix at :126). The landed `resume_console_20260824T074227Z.log`
shows the resume: fresh `rr` container created 07:42:27Z, driver
re-invoked into the same out-dir (which is why the corpse rows share the
record files), full preflight PASSED, 168/168 completions. The measured
quantities are computed on the completed set: `frames_census` PASS with
exactly 168 records and no missing videos, and the measured spans match
23,049 frames at the banked rates. The export's `n_errors` counter
naively includes the corpses; the throughput and CPU brackets do not.

Records files (verified fetches, left on S3):

```
e4a8a08b3ccb0e3073152a6169e52470132c68f27cf702f6ffe7e1ca2efcb886  mainrun_20260824T025550Z/records_rocketride_video_parity_blast.jsonl
2f38c528d9d0bb4b88d1387198fee5324c017303a4702238e6015a4e2897300d  mainrun_20260824T025550Z/records_rocketride_video_default_blast.jsonl
```

## Manifest warts, stated

1. `mainrun_20260824T025550Z/run_manifest.json` reads
   `completed: false` — the resume path (`resume_rr_legs.sh`) never
   flipped the flag. Completion evidence is the per-leg exports (all
   gates except the corpse-counting errors gate PASS; n_records=168 per
   completed set) plus the resume console log.
2. Its embedded `ruled_values` self-check string is a **stale snapshot
   of the 44-scale ruling** (Crossroads 31/32: WARM_N=16,
   LI_THREADS_ENV=1, DEFAULT_N=44); the run's actual numbers
   (M_TOKENS=16, RR_THREADS_ENV=2, LI_WORKERS=8, LI_THREADS_ENV=4,
   WARM_N=2, BLAST_C=16, DEFAULT_N=168, PASSES=2, LIVENESS_MIN=0.5,
   GATE3_RUN_ID=probe_20260823_122005) match the recorded full-corpus
   launch line at SESSION_STATE.md:294 on **all ten values**. The cell
   identification stands on the f/s match and that launch-line match,
   not on the manifest's self-check string.
3. **No apples directory carries a run_manifest** (checked on S3, all
   four). The 8×4 cells' configuration identity traces to the exports'
   embedded provenance blocks: `provenance_video.posture`
   (tokens=8, threads_env_expected=4, in-process torch reads 4),
   `task_census` (declared 8 → census_after 8), image digest
   `sha256:b7f51acc…` (same `rr:patched-video` as the mainrun), and
   `provenance_leela` (engine 3.3.1, duplication_patch_applied: False).
