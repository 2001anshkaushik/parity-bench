# Pre-500 review — her access model + her runbook vs our practice (2026-09-03)

Object reads at our pins only (aa817d9a / 313430f3 / 3967d9f4); no
fetch, no contact. One naming divergence first: **no file named
`ARCHIVE_FILMS_S3_AND_RUNBOOK.md` exists at our pins or in
`team_docs_received/`** — every item attributed to it lives in her
`aws_videobench/ARCHIVE_FILMS.md` ("the archive_films corpus: complete
data plan"), `run/films_v2.sh`, and `METRICS.md`, all cited below. A
post-pin rename is the likely explanation (HYPOTHESIS).

## 1. Their box access — no permission we lack, no mechanism outside SSM

Searched her whole tree at the head pin for endpoints, agents,
SendCommand, systemd, cron, webhooks, runners, listeners. The finding
is the opposite of the premise:

- **Her own docs state OUR constraint verbatim.**
  `aws_run/CHECKLIST.md:10-11`: "Access model: interactive SSM shell
  only… **No scp, no SendCommand, no port forwarding.**"
  `aws_run/COMMS.md:12`: "Explicitly impossible (don't burn time
  trying): scp, SSH, SSH-over-SSM…". Her role is even MORE constrained
  in one respect: `terminate-session is denied to this role`
  (`aws_bench/local/box.sh:42`).
- **The "automation" is a laptop-side wrapper over the SAME
  interactive channel.** `aws_bench/local/box.sh` — "Mac-side EC2/SSM
  control": `pipe_run()` (:46-56) pipes the command plus an
  `echo "__RC=$?"` marker into `aws ssm start-session` stdin under a
  pseudo-TTY (`script -q /dev/null`), scrapes the exit code back out,
  strips the pty's `\r`. The pty is load-bearing: since the box SSM
  agent's 3.3.4793.0 auto-update, no-TTY piped sessions "die instantly
  … and ALSO stay Connected server-side, so 25 of them hit the
  per-instance session cap and lock the box out entirely" (:38-44,
  their measured incident). `./box.sh launch <name> '<cmd>'` (:98)
  runs long jobs as `nohup … > ~/logs/<name>.log &` through that same
  pipe; `aws_bench/README.md:59-60` states the rule ("Long runs must
  not sit in an SSM session").
- **Shashi**: we hold NO clone of his repo (`team-repos/` contains
  only hers). Cannot be searched; nothing asserted about his tooling.

**What this means for us**: they have neither a permission we lack nor
an out-of-SSM mechanism — they scripted the paste. Adopting the same
pattern needs **no IAM change**: our existing `ssm:StartSession` is
the whole surface, and their comments pre-pay two lessons (pty
required; leaked sessions can cap-lock the box, and terminate-session
may be denied). If Ansh wants true `ssm:SendCommand` instead, that is
an IAM policy grant (`ssm:SendCommand` + `ssm:GetCommandInvocation`
on the instance and document resources) that, on this evidence, even
her role does not have. Whether to build the wrapper is an operator
ruling, not a permissions problem.

## 2. Her runbook items vs our practice

| her item (cite) | verdict for us |
|---|---|
| `archive10` .mp4 shakedown as the corpus smoke (`ARCHIVE_FILMS.md:68,205,229`; `run/archive10.sh`; codec sanity per `LONG_VIDEO_SOURCES.md:115`) | **Equivalent, different shape**: our staging (arming run + smoke_video + preflights) plus the 9-film heads batch and the 11-point full-corpus sweep covered the same ground for the 35. For the 500: her 10-set is the first 10 of every subset (nesting below) — a ready-made shakedown set if we want one; our heads batch is the in-house equivalent. |
| `RR_PIPE_TTL_S` must exceed `BENCH_TIMEOUT_S`, fail-closed FATAL (`films_v2.sh:45-48`) | **We do better**: measured legs run ttl=0, which removes the idle-reaping class outright rather than out-racing it — and our resume machinery was hardened by the ttl-0 corpse incident. No gap. |
| SUBSET nesting 10 ⊂ 50 ⊂ 100 ⊂ 500 (`corpus/sets/archive_films_{10,50,100,500}.txt`) | **VERIFIED at pin**: exact containment, headers aside (each file's one non-nested line is its own header, which states the rule — "first N accepted in queue order" — and pins manifest sha `bd0c915e…`, the same sha our DEFINITIVE cites). Ours is a 35-film strata sample, deliberately not nested (representativeness over scale-curve reuse). Conditional gap only: if we ever run intermediate scales, her nested sets are available at pin. |
| Results mirrored live to `s3://…/leela/videobench/films<SUBSET>-<stamp>/` (`films_v2.sh:43`) | **Partial gap, worth adopting for the 500**: we archive post-run and land with hashes (stronger provenance than her mirror), but nothing syncs DURING a run — a mid-run box death preserves only disk (the 24-Aug AMI death survived on disk alone). At 500-scale (~day-long campaign) a live sync loop is cheap insurance. |
| `report.py` gates-first (`METRICS.md:4` "gates first, numbers second") | **Equivalent-or-better**: fail-closed preflights, per-leg gates blocks in every export, summarizers that refuse, and the report's sourcing rule. No gap. |
| Single repetition labelled SIZING (`films_v2.sh:19,253`; her films500 README) | **Equivalent**: our n= column plus superseded / never-quote labels carry the same information; her one-word evidence-grade is a tidy convention, nothing more. |
| **$/1k footage-hour as a published metric** (`METRICS.md` V5) | **Belief corrected: computed, never published.** Every films export already carries `usd_per_1k_footage_hours` (the AMI-era driver work, inherited; basis in-export: $1.428/h ÷ x_realtime × 1000 on the 49.33 h footage). Values, from the landed exports: **RR 16×2 $10.12 / $9.91 · LI 16×2 $9.39 / $9.41 · RR default $40.35 / $40.65** (sequential legs $55.8–61.3 — latency mode, not comparable). What it takes to publish: one row in the DEFINITIVE's §2 table and one line in the summary; zero computation. One cautious echo, not a join: her films500 SIZING run reads RR-default $40.79 and LG-c32 $9.24 on a DIFFERENT corpus — remarkably near our $40.35–40.65 and $9.39–9.41. |

## 3. Her films500 runs — what to read before our 500

Three stamps (her `runs/films500-sizing/README.md` at pin):
`films500-20260824T073256Z/rr` (RR default, 498/498, 35.0×, $40.79/1k fh,
span 19.27 h), `films500-20260825T061529Z/lg` (LG c32, 498/498, 154.6×,
$9.24, span 4.36 h), and the first LG attempt
(`films500-20260824T073256Z/lg`) which **OOM-died at 97/498 — post-mortem
in her commit `2d7533b`**. The committed mirror at pin
(`runs/films500-sizing/{rr,lg}/`) carries per_doc.jsonl, driver.log,
cgroup CSVs, preflight hashes and provenance. Worth reading before our
500, concretely:

1. **Scale truth**: 498 measured + 2 warm, **674.75 h footage probed** —
   13.7× our films corpus. At our measured films 16×2 rates (~9.5 f/s)
   that is ~4.7 h per pass per arm; a films-shaped 9-leg campaign
   extrapolates to roughly a day of wall — SIZING-grade arithmetic,
   labelled as such.
2. **The LG OOM post-mortem (2d7533b)** — a corpus-scale failure mode.
   Our LI arm is a different build (streaming reader), likely immune,
   but the post-mortem names which content and what pressure killed it;
   read before betting a day of wall on "likely".
3. **Per-film walls in per_doc.jsonl** → timeout sizing. Her envelope is
   `BENCH_TIMEOUT_S=86400`; our LI client's **7200 s urlopen ceiling
   (handoff item 8) becomes acute at 500-scale** — a ~1.35 h mean film
   at a slow posture can breach it. Fix before the 500, not during.
4. **Her cross-arm films data** (workload_ratio 1.026; frame_parity
   VFR-band with 46 exact) — joins remain subject to §9's cautions (her
   frame counts carry the 416-counter artifact; >560px content carries
   the §6 caveat).
5. **Her committed 500-census is EMPTY at the pin** (0 bytes) — checked;
   so the DEFINITIVE's "corpus-wide >560px fraction not derivable from
   any artifact we hold" is re-verified, not overturned.
