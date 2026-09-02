# Cross-team comparison — RocketRide on ami_full (168 meetings, 23,049 frames, 96.06 h)

Basis, shared: footage 96.06 h (hers; ours reads ~96.1 h, consistent);
instance $1.428/h (c7i.8xlarge); $/1k footage-h = $/h ÷ x_realtime × 1000
— the formula reproduces all four of their published $/1k figures to the
cent, which confirms the basis. Their four columns are transcribed
verbatim from Leela's transmitted table (DATA). Ansh's cells show both
passes (n=2, pass1 / pass2); single derived values are computed on the
mean of the two passes.

| | Leela 32 × OMP 1 | Shashi 32×1 | Leela 16 × OMP 2 | Shashi 16×2 | Ansh 16 × OMP 2 | Ansh 8 × OMP 4 | Ansh default (1 token, env unset) |
|---|---|---|---|---|---|---|---|
| frames/s | 16.213 | 16.17 | 15.314 | 15.39 | 12.729 / 12.753 | 11.694 / 11.571 | 2.443 / 2.446 |
| x realtime | 243.24 | 242.6 | 229.76 | 230.9 | 190.98 / 191.34 | 175.45 / 173.61 | 36.65 / 36.70 |
| eff cores /32 | 28.74 (90%) | 28.56 | 29.62 (93%) | 29.14 | 29.328 / 29.482 (91.7 / 92.1%) | 30.411 / 29.843 (95.0 / 93.3%) | 6.029 / 6.046 (18.8 / 18.9%) |
| CPU-s/frame | 1.773 | 1.766 | 1.934 | 1.893 | 2.308 (2.304 / 2.312) | 2.590 (2.601 / 2.579) | 2.470 (2.468 / 2.472) |
| span | 1,421.7 s | 1,447 s | 1,505.1 s | 1,520 s | 1,810.7 / 1,807.3 s ᵈ | 1,971.0 / 1,992.0 s ᵈ | 9,434.7 / 9,423.1 s ᵈ |
| $/1k footage-h | $5.87 | $5.89 | $6.22 | $6.18 | $7.47 | $8.18 | $38.94 |
| idle burden | 8.91 cores | — | 5.69 cores | — | 4.66–4.71 cores | 2.83–2.84 cores | 1.23–1.24 cores |
| peak memory | 61.1 GB (cgroup, incl cache) | 44.4 GB (RSS) | 45.7 GB | 32.3 GB | in exports, not yet read ᵐ | in exports, not yet read ᵐ | in exports, not yet read ᵐ |
| gates | PASS, census 32/32 | — | PASS, census 16/16 | — | PASS, census 16/16 | PASS, 8/8 tasks concurrently busy | PASS, census 1/1 |

ᵈ **Derived, not measured**: Ansh's span cells are 23,049 ÷ banked f/s.
The banked f/s were themselves computed from the measured spans, so the
derived value can differ from the export's measured `span_s` only within
½ ulp of the 3-dp f/s: ±0.1 s on the parity cells, ±2 s on default. The
measured values replace these when the exports are read (see below);
measured wins on any disagreement.

ᵐ **Peak memory**: no memory figure is banked in-repo for the AMI cells.
The collector at the AMI campaign already recorded three bases per leg —
`peak_cgroup_current_mb` (incl. cache — Leela's basis),
`peak_cgroup_anon_mb`, and `peak_rss_mb` (Shashi's basis) — so the
exports can fill this row on either basis, labelled per cell. Their own
row already mixes bases (Leela 61.1 GB cgroup-incl-cache vs Shashi
44.4 GB RSS in the same cell); no figure in this row is comparable
across bases and Ansh's cells will carry their basis label when filled.

Row cautions:
- **Shashi's span column is not frames ÷ f/s**: his printed spans run
  +21.6 s / +22.3 s (~1.5%) above 23,049 ÷ his f/s, while his
  x_realtime and $/1k cohere with his f/s, not with his printed span.
  His "span" is therefore a different quantity (wall-clock including
  ramp is the natural candidate — HYPOTHESIS). Leela's columns cohere
  exactly. Do not join on his span cells.
- **Idle burden windows differ**: theirs is a 30 s idle window after
  warm-up; Ansh's is a 4 s cgroup-rate sample with instances live.
  Same kind (cgroup rate while idle), different window; the ~1 core
  difference at 16 tasks (5.69 vs 4.66–4.71) is unresolved.
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

**Traceability**: the AMI export files behind Ansh's cells are NOT
in-repo — the only committed artifact under
`working/video/results/mainrun_20260823T034358Z/` is a **dry-pass**
run_manifest (`dry_pass: true, completed: false`; not the ruled
campaign's manifest) plus its log. Every Ansh figure above traces today
to `WS1_Phase2_Video_Benchmark_DEFINITIVE.md` §3.1/§4.1, whose exports
live at `s3://rocketride-benchmark-data/ansh/video-ami-20260826/`. For
this table to travel with every figure traceable to a committed
artifact, land from that archive (entry-26 discipline: fetch, verify,
commit): the ruled run's run_manifest, the per-leg export JSONs for the
three cells (measured `span_s`, cores, gates), and the collector
`.summary.json` files (fills the memory row on both bases). S3 access
from this machine is currently blocked — the `rocketride` profile's SSO
token has expired (`aws sso login --profile rocketride` restores it); a
box-side bundle is the alternative.
