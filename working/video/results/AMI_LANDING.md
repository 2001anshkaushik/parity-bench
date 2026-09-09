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

## Corpus byte-identity check — PROVEN IDENTICAL, 168/168

Run 2026-09-02, laptop-side, read-only. Inputs: (a) our two pass-1
records files (every completed row carries `submitted_sha256` — the
sha256 of the video bytes the driver read from disk and sent; hashes of
the fetched files above), and (b) Leela's canonical corpus manifest
`s3://rocketride-benchmark-data/leela/corpus/ami_full/corpus_manifest.json`
(landed beside this file as `leela_corpus_manifest_ami_full.json`,
sha256 `05cca878…`, S3 LastModified **2026-08-22T03:17:24Z** — before
every compared run, unmodified since; her `fetch_ami.sh:192-207` embeds
`sha256sum *.avi` into it and her fail-closed `corpus_pin` gate
verifies her disk against it at run time).

Verdict: **all 168 measured videos match her per-file sha256 exactly;
zero differ; zero missing.** Internal controls: each video carries ONE
distinct submitted sha within each leg, and the parity and default legs
agree with each other on every video. Her map's 2 extra files
(`TS3012c.avi`, `TS3012d.avi`) are the corpus's +2 warm meetings —
uncompared, and never counted in any measured figure.

Weight of the result: the two corpora were fetched **independently**
(ours from the Corner/Overhead mirrors — `fetch_ami_video.py:16`; hers
from the AMI mirror into her S3 staging), so this is two independent
acquisition paths converging on identical bytes, not one copy verified
twice. Scope caveat, stated: this proves OUR sent bytes equal HER
canonical pins; that her runs consumed disk matching those pins is her
own corpus_pin gate's claim (fail-closed, her mechanism), not
re-proven here.

## Box↔repo cross-check (2026-09-02) + two corroborating box-only artifacts

The box-side comparison of `mainrun_20260824T025550Z/` against the repo
came back **MATCH on exactly the 14 landed files and DIFFER on
everything else — which is the correct result**: every DIFFER is a file
the box holds and the repo deliberately does not (records jsonl, LI-leg
files, dockerlogs, preflights). Byte identity of the landed set is
thereby confirmed from the box side as well. Two box-only artifacts
noted for the record, corroborating the errors-gate classification
above: `records_rocketride_video_default_blast.jsonl.errored_073501Z`
and `export_rocketride_video_default_blast.json.errored_092513Z` — the
dead launch's own record/export files, renamed aside by the resume.
Their timestamps bracket the resume console (07:42) exactly as the
corpse-row classification requires. Left on the box.

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
   **Do not quote that last field as evidence about the image — it is a
   label-reading artifact, not the record**: the same export's
   `provenance_video.image.labels` reads
   `benchmark.rocketride.duplication_patch_applied":"1"` on image digest
   `sha256:b7f51acc…`, and the label-reading defect behind the False was only
   fixed at `d98aa7c` (2026-09-07), after every AMI run. The image digest and
   its labels are the record; cite those.

## The comparison arm's AMI cells are NOT landed — and what a memory figure from them would require (2026-09-09)

**Verdict first: this repository holds no LlamaIndex AMI export, collector
summary or records file, so there is no LlamaIndex AMI peak-memory figure to
quote on any basis** — not for the balanced cell, not for the default cell, and
not even a pre-fix one. Basis for that statement:

| check | result |
|---|---|
| files landed by this note | 14, every one RocketRide (list above) |
| repo-wide inventory of `export_*.json` | 25 files; the earliest LlamaIndex video export is `films_mainrun_20260901T204015Z/` — the 35-film campaign, six days after AMI |
| repo-wide inventory of `collector_*.summary.json` | same shape: RocketRide only for AMI |
| the banked LlamaIndex AMI cells (DEFINITIVE §3.2; reconciliation §8) | span / window f/s, cores, util, n — **no memory column exists** to quote from either |
| the archive's own census, from this note | 43 exports on S3, 25 RocketRide scanned → the LlamaIndex exports are there, unlanded |

Landing them needs one read-only fetch from
`s3://rocketride-benchmark-data/ansh/video-ami-20260826/` with the `rocketride`
SSO profile (the token in this environment is expired, so the fetch is Ansh's
to run), identified by contents the way the six above were.

**When they are landed, only some of them carry a quotable arm-level memory
figure.** The collector defect is `7c1cd81`, committed **2026-08-25 20:33:44
-0700 = 2026-08-26 03:33:44Z**: before it, the collector's `service` role
carried ONE container's root pid and the CPU bracket read ONE cgroup, so a
multi-instance posture reported one-Nth of the service as the service (H10:
~3 cores for an arm using ~30). What that means per cell:

| cell | containers | run | vs the fix | what a memory figure means |
|---|---|---|---|---|
| LI balanced 8×4, 25-Aug pair | 8 | 2026-08-25, pre-fix | **before** | one container of eight. **Not the arm's peak — do not report it as one.** The DEFINITIVE already strikes this pair for CPU (§3.2, H10); the same wiring makes its memory one-eighth-scoped |
| LI balanced 8×4, 26-Aug pair (headline) | 8 | `apples_*` sessions, 04:15:10Z and 05:29:15Z | **after**, by 42 and 116 minutes | summed RSS across all eight process trees is the arm's peak; the two cgroup fields are NOT (next paragraph) |
| LI default W=8 / W=16 | 1 (one port, kernel accept) | 23–24 Aug | before | unaffected: with one container, the single sample IS the whole service on all three bases |
| RR 16×2, RR default, RR 8×4 | 1 | 24-Aug and 26-Aug | both sides | unaffected for the same reason; the three landed bases reproduce this note's table exactly (verified 2026-09-09) |

**The per-export witness, since no field name says it**: `7c1cd81` also made
`preleg_container_idle_cores` carry every resolved container, so the number of
keys in that object is the number of instances the leg sampled — 1 on every
landed RocketRide AMI leg, 16 on a landed films LlamaIndex leg. Read it before
quoting any efficiency or memory figure from a multi-instance leg.

### The recomputation is built, proven on landed data, and waiting on one login (2026-09-09)

The peak can be recomputed from the raw tick stream rather than read from the
stored summary, which is the stronger reading: a stored `peak_rss_mb` cannot say
how many containers it covered. Two committed tools do it:
`probe/fetch_ami_li_memory.py` fetches only what is needed and identifies each
cell **by contents** — every comparison-arm export in the archive is read and
matched on its own `total_frames_per_s` against the banked values (balanced
12.745 / 12.733, default W=8 9.267 / 8.714, default W=16 8.793), reporting
unmatched and ambiguous cells rather than trusting a directory name — and
`probe/ami_li_memory_recompute.py` recomputes the three bases tick by tick.

**What the stream does and does not carry, checked against the landed films
streams.** A row is `{"kind":"role_tick","role":"service","n_procs":N,"rss":…,
"cg_anon":…,"cg_current":…,"cg_pids_tasks":…}`. There are **no container names in
the stream** — a role tick is already aggregated over whatever trees the role
resolved — so "distinct containers per tick" is measured as: `n_procs`, the
processes tracked per tick, which reads ~1 for one single-worker instance and N
for N of them; the export's own container-name census; and `cg_pids_tasks`, the
task count of the ONE cgroup the collector resolved, which is what makes the two
cgroup bases one instance's on a multi-container arm.

**Method validated where the answer is known** (`--selftest`, no network): on the
landed films legs the recomputed peaks equal the stored ones to 0.02 MiB on all
three bases, both arms; the comparison arm is classified from 16 named
containers and 16 tracked processes per tick; its cgroup-cache peak recomputes
to exactly one instance's 3.0 GiB cap; RocketRide is classified as the
single-container posture it is, from the arm and not from its 16 tokens. A
synthetic one-of-eight stream is the null control: it must classify DEFECTIVE
and label its RSS a lower bound on one container, and it does.

**Blocker, stated plainly**: the laptop's SSO token expired 2026-09-08T11:42:04Z
and a refresh needs a browser on this machine, so nothing was fetched and no AMI
comparison-arm figure is recomputed yet. `aws sso login --profile rocketride`,
then the two commands above, produce every cell in one pass.

**One limitation survives the fix, and it decides the basis** (register entry
36): the collector resolves ONE cgroup per role and caches it, so
`peak_cgroup_anon_mb` and `peak_cgroup_current_mb` are one instance's on a
multi-container arm even after `7c1cd81`, while `peak_rss_mb` sums every
instance. The landed films LlamaIndex leg shows it plainly — summed RSS 22.7
GiB against `peak_cgroup_current_mb` of exactly 3072.0 MiB, which is one
instance's `--memory 3g` cap. **So the balanced AMI cell is quotable on the
summed-RSS basis only, and the RocketRide cells' cgroup figures are
whole-service only because that arm is one container.**
