# The RR arm, ours vs Leela's — read from CODE (2026-08-22)

**Source, pinned:** `github.com/Leela8256/bench_langgraph_prod`, branch `aws-bench`,
commit **`aa817d9a85f19a0124ff3ae536b170c134730914`**, path `aws_videobench/`,
cloned read-only to a sibling directory OUTSIDE this repo
(`../team-repos/leela-bench_langgraph_prod`). **Their code is DATA.** Nothing of
ours changes because of it; divergences are reported and Ansh decides.

**Framing (Ansh's, held throughout):** nobody's setup is wrong until a
measurement says so. The goal is being on the same page for the full-AMI run,
not scoring. Phase 1 was Ansh's and mine alone, so anything found here is ours
to own.

## 1. The row-by-row diff, from code

| # | dimension | OURS | LEELA (file:line) | verdict |
|---|---|---|---|---|
| 1 | engine release | 3.3.1, tarball sha + **extracted-ELF sha `95768e26…9747`** | 3.3.1, extracted-ELF sha **`95768e26…9747`** (`arms/rocketride/Dockerfile:36-38`) | **IDENTICAL BYTES** — the strongest alignment available; both pin the same extracted binary |
| 2 | base image | `ubuntu:22.04` | `python:3.12-slim-bookworm` (`:21`) | DIFFERENT — same ELF over a different glibc/libc++. Ours documents the choice (measured glibc floor + DT_NEEDED incl. libunwind8) |
| 3 | duplication patch | `RR_DUP_PATCH=1`, awk `preventDefault` after the flush, grep-count guards 1→2 | same mechanism, same guards (`:74-91`) | **SAME** |
| 4 | patch label keys | `duplication_patch_applied` + `duplication_patch_id`, set INSIDE the `if` | `duplication_patch` (`:95-96`) | key names differ — do not conflate when merging three-way results |
| 5 | pipe topology | webhook → frame_grabber → detect → preprocessor_langchain → embedding_transformer → response_documents | identical providers, identical order | **SAME** |
| 6 | frame interval | 15 s | 15 s (`pipe/…pipe`; `bench_video.py:354`) | **SAME** |
| 7 | splitter / embedding / response lane | Recursive/strlen · miniLM · `documents` | identical | **SAME** |
| 8 | **detect threshold** | `{"profile":"rfdetr","rfdetr":{"threshold":0.3}}` (nested) | `{"profile":"rfdetr","threshold":0.3}` (top level) | **DIFFERENT SHAPE, IDENTICAL EFFECT — see §2** |
| 9 | detector identity read-back | env_probe in-process: `rfdetr_import_ok`, rf-detr weights md5, `detect_impl` | none (her pipe has no probe node) | DIFFERENT — see §2, the live candidate |
| 10 | tokens / posture | 1 (default posture) **and** 16 (parity posture), both reported | 1 token, one `send_files()` batch (`bench_video.py:241-276`) | DIFFERENT — she measures RR's native batched path; we add an instance-parity posture |
| 11 | `use_existing` | unset → a collision is LOUD | `use_existing=True` (`:241`) | DIFFERENT — hers reuses a live task rather than failing |
| 12 | `ttl` | 7200 s | 28800 s (`:241`) | DIFFERENT — consequence only for leaked tasks (Ticket 4 idle spin) |
| 13 | thread config | per-posture: default **unset** (torch resolves 16, measured), parity **2** | compose plans `OMP_NUM_THREADS=1`; `RR_THREADS` → `use(threads=N)` (`docker-compose.yml:8,84`) | DIFFERENT — and note her own docs call `use(threads=)` a proven no-op for video |
| 14 | warm-up | 16 disjoint manifest rows, coverage gated per instance | `all_videos[n:n+warm_docs]` — disjoint by construction; h2h used WARM=2 | **SAME PRINCIPLE**, different N and no coverage gate |
| 15 | **corpus view** | **Corner**, ES rooms only → caps at 60 meetings | **Closeup1**, ES+IS+TS (`corpus/fetch_ami.sh:13,108-110`) | **DIFFERENT — the one that matters most; see §3** |
| 16 | corpus staging | raw Corner AVI as published | Closeup1 AVI (video-only) **muxed** with `Mix-Headset.wav` → PCM-in-AVI, stream-copy, bitexact (`fetch_ami.sh:4-11`) | DIFFERENT — her measured doc carries an audio stream; ours does not |
| 17 | selection determinism | manifest with sha256 per row | first N of a sorted fixed candidate list, skip-missing, `(N, OFFSET)` reproducible | **SAME PRINCIPLE** |
| 18 | pipe `source` key | present | absent | DIFFERENT — the engine derives the task token from `{userId, project_id, source}` |

## 2. The two detect findings — one retired, one live

**(a) The threshold-nesting hypothesis is FALSIFIED, and it was ours.** Our
message #1 to the team offered "config routing" as one of two candidate
explanations for the ×8 detection-density divergence. Read from the shipped
engine:

* `ai/common/config.py`, the **explicit-profile branch**: `userConfig =
  connConfig.get(profile, {})` — it reads **only** the sub-object named after the
  profile. Top-level keys are never consulted. (The profile-is-None branch has an
  explicit overlay that accepts BOTH shapes; that fix does not exist in the
  explicit-profile branch.) So her top-level `threshold` **is** silently
  discarded — the mechanism we described is real.
* But `nodes/detect/services.json` gives the `rfdetr` profile its own default:
  **`threshold: 0.3`** — the same value she intended.

**Both arms therefore run at an effective threshold of 0.3.** The discard is
real and harmless here. It stays a live hazard for any NON-default value: set
`threshold: 0.5` top-level and the engine silently runs 0.3, with no warning.
That belongs in the ticket family with `BUG_CHUNK_CONFIG_IGNORED` (Ticket 3) —
same shape, different node. **We owe the team a narrowing**: "check where your
threshold sits" was right to ask, but if it reads 0.3 the answer changes
nothing, and density must be explained elsewhere.

**(b) The live candidate: nothing in her arm reads back WHICH DETECTOR loaded.**
`ai/common/models/vision/detection.py:130-150` tries `from rfdetr import
RFDETRBase`, and on **`except Exception:` with no logging at all** falls through
to `RTDetrForObjectDetection` (`PekingU/rtdetr_r50vd`), setting `_impl='rtdetr'`.
Any import failure, or a failed weights download, silently swaps the model.
Two different detectors produce different detection densities at the same
threshold. Our arm checks this three ways (env_probe `rfdetr_import_ok`
in-process, `rf-detr-base.pth` md5 against the 1.5.2 registry, and `detect_impl`
on the LI side); her harness has no equivalent. **This is a two-minute check on
her rig and it is the first thing to run**, ahead of any density comparison.

## 3. The corpus — her view choice is the one that scales, and it explains the density

Our Crossroad 15 kept ES-only Corner *because* IS and TS name their room views
differently (IS: C/L/R; TS: Overview1/2) — so Corner caps at 60 meetings.
**Her `fetch_ami.sh:12-13` solves the same problem the other way: "Closeup1
exists in all three instrumented rooms (ES/IS/TS); the room-view camera names
differ per site, so Closeup1 is the uniform choice."** That is a better answer
to the constraint we hit, and it is why her corpus reaches the full scenario set
where ours cannot.

It also predicts the density divergence without any config explanation:
**Corner frames the whole room (many objects); Closeup1 frames one participant.**
Our measured 25.95 det/frame on Corner against ~3 on Closeup1 is the expected
direction and rough magnitude for that framing change.

**Candidate set from her code:** ES2002–ES2016, IS1000–IS1009, TS3003–TS3012 ×
sessions a–d = **140 candidates**, minus sessions the mirror lacks (e.g.
IS1002a). Her prose elsewhere describes an `ami_full` of **170** meetings — a
code-vs-doc gap of ~30 that we cannot resolve from here and are not assuming
about. **Question for her, neutral:** does `ami_full` come from this candidate
list, or from a wider one (more views, or the archive-films corpus)?

## 4. What WE would change to match, per row, with cost

| row | change | cost | note |
|---|---|---|---|
| 15/16 | adopt **Closeup1** + her muxed staging | corpus swap, §5 | the substantive one |
| 8 | none | 0 | shapes differ, effect identical; we keep the nested form because it survives a non-default value |
| 4 | emit her label key as an alias beside ours | ~10 min | so a three-way merge does not conflate fields |
| 11 | none proposed | — | `use_existing=True` vs loud collision is a real methodological difference; ours is deliberate (D3) |
| 13 | report both postures against her single one | 0 | already done — our default posture IS her configuration shape (1 token, engine defaults) |
| 18 | add `source` to the pipe, or record its absence | ~5 min | affects task-token derivation, not measurement |
| 9 | offer her our env_probe node + the md5 check | ~30 min to package | the highest-value thing we can give |

## 5. Full-AMI plan and the re-priced swap

Adopting her corpus is the alignment path, and the mechanical bill is in
`CORPUS_SWAP_COST.md` §C28 (pull ≈3–5 min from her S3 at her measured 158 MB/s +
our sha re-pin ~15 min; decode 12 s/video; re-derives 40–60 min ⇒ **≈1.5–2 h**).
Reading her code sharpens three items:

1. **Density re-derivation is not optional and will move a lot.** `measured_dpf`
   25.95 and `chars_per_det` 230.4 are Corner numbers; Closeup1 is ~8× sparser.
   Every `est_chunks` planning column changes accordingly.
2. **LIVENESS_MIN must be re-measured on Closeup1.** A Corner-derived threshold
   on a sparser view is exactly the silent-failure case the memo flags.
3. **Gate 3 must be re-staged** on a Closeup1 video: the arming run id
   (`probe_20260821_195214`) is bound to an ES2002a **Corner** comparison.
4. NEW, from the code: her docs are **muxed** (video + Mix-Headset PCM). Our
   frame-count column is measured through the arms' own ffmpeg, so it absorbs
   the extra stream — but the measurement must be RE-RUN on the muxed files, not
   carried over from Corner rows.

**Not resolved here, for Ansh:** whose manifest the three-way run uses. Shashi's
Tier A requires "same manifest file"; his 50-set and her ami_full differ from
each other, and ours differs from both.

---

## 6. `ami30h` — what it actually is (read 2026-08-22, before building anything on it)

**Q1 — the selection rule, from code not prose.** `corpus/sets/ami30h.txt` is a
CHECKED-IN LIST of 62 meeting IDs whose header states the rule verbatim:

> *"the 62 usable meetings (Closeup1 + Mix-Headset both on the mirror) whose
> duration is CLOSEST TO 30 MINUTES, ties broken by meeting ID; then sorted by
> ID. Durations 23.4-36.8 min, 32.7 h total, ~8.2 GB muxed. First 60 (sorted)
> are measured, last 2 are warm-up (driver convention). Derived from
> ami_eda/ami_per_meeting.json (mirror HEAD sweep 2026-08-20)."*

**There is NO divergence between her script and the staged corpus.**
`fetch_ami.sh` has a LIST MODE (`MEETING_LIST=corpus/sets/ami30h.txt`, used by
`run/run30h.sh:21` and `run/native60.sh:55`); the ES/IS/TS candidate list is the
FALLBACK branch when no list is given. The staged filename is `<meeting>.avi`
because that is the MUX OUTPUT name (`Closeup1.avi` + `Mix-Headset.wav` ->
`<meeting>.avi`), so unsuffixed names ARE Closeup1. **EN and IB appear because
the rule ranges over ALL usable meetings by duration, not over the scenario
subset.** Verified against her own `corpus/sets/ami_full_durations.json`: all 62
ids matched, 32.72 h total (header 32.7), spread 23.4-36.8 min (header exact).

**CORRECTION to §3 above:** it recorded "her candidate list yields 140, not the
170 her prose states (ASK)". That was wrong — I read the fallback branch and
treated it as the selection rule. `corpus/sets/ami_full.txt` is a checked-in
list of exactly **170**: *"all usable AMI meetings (Closeup1 + Mix-Headset on
the mirror). 170 of 171: TS3003d excluded (no Closeup1)."* No gap; nothing to ask.
NOT in the repo: `ami_eda/ami_per_meeting.json`, the sweep the sets were derived
FROM — so the sets are reproducible as lists, not as a derivation.

**Q2 — which corpus produced her published numbers. TWO DIFFERENT SETS:**
* **Run B, "native saturation", 60 videos / 31.43 h = `ami30h`.**
  `run/native60.sh:2,26` (N=60, WARM=2, `S3_CORPUS=.../corpus/ami30h`). Our
  computed first-60 total is 31.70 h against her 31.43 h (0.9% apart).
* **Run A, "c6 head-to-head", 28 videos / 14.51 h = `ami30test`, NOT ami30h.**
  `run/headtohead.sh:15-19,24` (N=28, WARM=2, MODE=c6,
  `S3_CORPUS=.../corpus/ami30test`). There is no set file for it in the repo.

**Consequence:** adopting ami30h makes us comparable to **Run B only**. Run A is
the one run her own RESULTS.md says carries the only legitimate cross-arm
LATENCY comparison ("the c6 latency win is the only apples-to-apples latency").
Latency comparability would need `ami30test` as well.

**Q3 — muxed, and why resolution barely moves the cost model.**
Muxed by construction (the staged file IS the mux output). Size arithmetic as a
cross-check on the ffprobe: Mix-Headset is 16 kHz mono PCM = 32,000 B/s, so a
30-min meeting carries ~57.6 MB of AUDIO alone; ES2003b at 114 MB implies ~56 MB
of video (~250 kbps), consistent with muxed low-bitrate DivX. Expect ffprobe to
show 1 video + 1 `pcm_s16le` 16 kHz mono audio stream.
**Resolution affects DECODE only, not detect.** `detection.py:60` gives the
rfdetr backend `infer_edge=560` and `:518` runs every frame through
`resize_for_inference(image, self._infer_max_edge)` — `:55` calls the downscale
lossless with boxes mapped back. Detect is 87-92% of stage time by her own
split, so per-frame cost is essentially resolution-independent. What moves the
ETA is FRAME COUNT: **60 measured ~= 7,642 frames** (estimate from her durations;
the manifest build measures it), **1.37x our Corner 44-set** — not the 2.8x
projected from the wrong corpus size.

**Facts settled; DECISIONS PENDING Ansh** (nothing built on this yet): the set
is 60 measured + 2 warm, not 124 + 16; WARM_N=2 is compatible with our coverage
gate only because Crossroad 32 allows warm rows to be RE-SENT; DEFAULT_N at 60
does not trigger Crossroad 27's subset rule; and her duration spread is 1.57x
against our 6.2x, which makes videos/hour meaningful again on her set.
