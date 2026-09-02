# Cross-team comparison — RocketRide on ami_full (168 meetings, 23,049 frames, 96.06 h)

Basis, shared: footage 96.06 h (hers; ours reads ~96.1 h, consistent);
instance $1.428/h (c7i.8xlarge); $/1k footage-h = $/h ÷ x_realtime × 1000
— the formula reproduces all four of their published $/1k figures to the
cent, and Ansh's exports carry the same formula verbatim
(`usd_per_hour_basis: "… her V5 definition"`), which confirms the basis
on both sides. Their four columns are transcribed verbatim from Leela's
transmitted table (DATA). Ansh's cells show both passes (n=2,
pass1 / pass2), **measured values read from the landed run exports**
(identification and hashes: `results/AMI_LANDING.md`); the single
CPU-s/frame value is the mean of the two exported per-pass values.

| | Leela 32 × OMP 1 | Shashi 32×1 | Leela 16 × OMP 2 | Shashi 16×2 | Ansh 16 × OMP 2 | Ansh 8 × OMP 4 | Ansh default (1 token, env unset) |
|---|---|---|---|---|---|---|---|
| frames/s | 16.213 | 16.17 | 15.314 | 15.39 | 12.729 / 12.753 | 11.694 / 11.571 | 2.443 / 2.446 |
| x realtime | 243.24 | 242.6 | 229.76 | 230.9 | 190.97 / 191.33 | 175.45 / 173.6 | 36.65 / 36.70 |
| eff cores /32 | 28.74 (90%) | 28.56 | 29.62 (93%) | 29.14 | 29.328 / 29.482 (91.7 / 92.1%) | 30.411 / 29.843 (95.0 / 93.3%) | 6.029 / 6.046 (18.8 / 18.9%) |
| CPU-s/frame | 1.773 | 1.766 | 1.934 | 1.893 | 2.308 (2.304 / 2.312) | 2.590 (2.601 / 2.579) | 2.470 (2.468 / 2.472) |
| span | 1,421.7 s | 1,447 s | 1,505.1 s | 1,520 s | 1,810.8 / 1,807.4 s | 1,971.0 / 1,992.0 s | 9,435.9 / 9,422.4 s |
| $/1k footage-h | $5.87 | $5.89 | $6.22 | $6.18 | $7.48 / $7.46 | $8.14 / $8.23 | $38.97 / $38.91 |
| idle burden | 8.91 cores | — | 5.69 cores | — | 4.66 / 4.71 cores | 2.84 / 2.84 cores | 1.24 / 1.23 cores |
| peak memory ᵐ | 61.1 GB (cgroup, incl cache) | 44.4 GB (RSS) | 45.7 GB | 32.3 GB | 35.4 cgroup-cache · 32.9 anon · 40.5 RSS-sum GiB | 27.6 cgroup-cache · 24.9 anon · 28.9 RSS-sum GiB | 19.0 cgroup-cache · 16.3 anon · 17.0 RSS-sum GiB |
| gates | PASS, census 32/32 | — | PASS, census 16/16 | — | PASS, census 16/16 ᵉ | PASS, census 8/8 | PASS, census 1/1 ᵉ |

All Ansh figures above are the exports' own recorded values. The spans
are **measured** `total_span_s`; deltas from the previously published
derived values were +0.1 / +0.1 s (16×2), 0.0 / +0.1 s (8×4) and
+1.4 / −0.5 s (default) — every one inside the stated ½-ulp bound, and
the measured values now stand. The exports also confirm every banked
cores/util figure exactly (no disagreement with the DEFINITIVE) and the
banked window f/s (12.755/12.796 · 11.258/11.438 · 2.337/2.340).

ᵐ **Peak memory** (filled from the landed exports; per-cell value = max
of the two passes, per-pass detail in `results/AMI_LANDING.md`'s files):
three bases per cell, GiB. **cgroup-cache** = `peak_cgroup_current_mb`
(cgroup incl. page cache — the same KIND as Leela's 61.1 GB figure);
**anon** = `peak_cgroup_anon_mb` (anonymous only); **RSS-sum** =
`peak_rss_mb`, the SUM of per-process RSS across the engine's task
processes — it double-counts pages shared between the 16/8/1 processes
(it exceeds cgroup-cache at 16 tokens for exactly that reason) and is
NOT the same animal as a single-process or container RSS. Their row
already mixes bases (Leela cgroup-incl-cache vs Shashi RSS in one row);
no memory figure in this table is comparable across bases, and each of
Ansh's cells carries all three labels rather than one number.

ᵉ **The pass-1 errors-gate artifact, classified**: the 16×2 and default
pass-1 exports report `gates.errors PASS=false, n_errors=16`
(n_records 184 = 168+16). The 16 rows are corpses of the campaign
launch that died at its first 16 blast sends and was resumed
(`resume_console_20260824T074227Z.log`, landed): enqueued hours before
the leg's first completed row, instant connection errors, and all 16
videos completed OK in the same leg. `frames_census` passes with
exactly 168 records; spans and CPU brackets are computed on the
completed set. Full classification with records-file hashes:
`results/AMI_LANDING.md`. Pass-2 legs read 168/0 clean.

Row cautions:
- **Shashi's span column is not frames ÷ f/s**: his printed spans run
  +21.6 s / +22.3 s (~1.5%) above 23,049 ÷ his f/s, while his
  x_realtime and $/1k cohere with his f/s, not with his printed span.
  His "span" is therefore a different quantity (wall-clock including
  ramp is the natural candidate — HYPOTHESIS). Leela's columns cohere
  exactly. Do not join on his span cells.
- **Idle burden windows differ**: theirs is a 30 s idle window after
  warm-up; Ansh's is a 6 s cgroup-rate sample with instances live
  (`idle_burden.sample_s: 6.0` in all six landed exports; the films-era
  driver later shortened it to 4 s). Same kind (cgroup rate while
  idle), different window; the ~1 core difference at 16 tasks
  (5.69 vs 4.66/4.71) is unresolved.
- Ansh's utilization percentages are printed beside cores; theirs as
  published (32×1: 28.74/32 = 89.8%, printed 90%).

**The finding this table carries**: at matched utilization (~90–93%) on
the same corpus and the same pipe composition, Ansh's harness spends
**~19–20% more CPU per frame** than both of theirs (2.308 vs
1.934/1.893 at 16×2; 2.590 vs their 32×1 basis), stable across both
matched postures — and their two independently built harnesses agree
with each other to 0.3–0.5%, so Ansh's side is the outlier and the
burden of explanation sits there. Candidate causes are all HYPOTHESIS
(the patched-vs-stock engine build — the one named code delta, which
our own provenance marks not-comparable; CPU-bracket edges; client
topology); what would settle it is a per-stage CPU split of one
identical file through both harnesses at the same posture, or an
exchanged cgroup sampler stream for one leg
(`AMI_CROSS_TEAM_RECONCILIATION.md` §3).

**Traceability — LANDED**: every Ansh figure above now traces to a
committed artifact. The six per-leg exports, four collector summaries,
the campaign `run_manifest.json` and the resume console log are landed
under `working/video/results/` (`mainrun_20260824T025550Z/`,
`apples_20260826T041510Z/`, `apples_20260826T052915Z/`), byte-for-byte
from `s3://rocketride-benchmark-data/ansh/video-ami-20260826/`, with
per-file sha256 and the cell→file identification (by f/s contents, not
directory name) in `results/AMI_LANDING.md`. Known warts, stated there
in full: the landed run_manifest reads `completed: false` (the resume
tool never flipped it; the exports and resume log carry completion),
its `ruled_values` self-check is a stale 44-scale snapshot (the run's
ten env numbers match the recorded full-corpus launch line,
SESSION_STATE.md:294, exactly), and no apples directory carries a
run_manifest at all — the 8×4 configuration identity rides on the
exports' embedded provenance blocks (posture read-backs, task census
8→8, image digest shared with the mainrun). The two pass-1 records
files stay on S3 with verified-fetch hashes recorded.
