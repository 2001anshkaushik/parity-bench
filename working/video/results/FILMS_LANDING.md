# Films evidence landing — traceability for WS1_Phase2_Films_Benchmark_DEFINITIVE.md

Companion to `AMI_LANDING.md` (same discipline: byte-for-byte from S3,
per-file sha256 at landing, identification by contents). The films
campaign run itself was landed earlier by entry-26 bundle at `646eaea`
(`films_mainrun_20260901T204015Z/`, 95 files); this note covers the
evidence that was still outside the repo.

## 1. Sweep point artifacts — LANDED (31 files, three prefixes)

| landed dir | files | backs (DEFINITIVE) |
|---|---|---|
| `posture-sweep-20260830/` | 11 `curve_*.json` | §5 posture matrix — all 11 f/s+cores cells verbatim; §4's sweep basis; Ruling M |
| `c-sweep-20260831/` | 14 `curve_*.json` | §5 heads C-chain (n=9 batch; the unrealized C=16/32 points carry `inflight_max: 9` — the refusal's evidence); §5 batch-composition (heads ~34% slower); Rulings N context |
| `c-sweep-highc-20260831/` | 6 `curve_*.json` | §5 measured-batch C chain (RR 8.21→9.059→9.127, LI 9.569→10.221→9.788; inflight == requested at every point); Ruling O (knee C=16) |

Every landed point's `metrics.frames_per_s` was verified against the
DEFINITIVE's §5 tables at landing: all 31 match verbatim; the heads
points additionally carry the inflight-9 realization facts §5 states.
Source prefixes: `s3://rocketride-benchmark-data/ansh/<same name>/`.

**Deliberately NOT landed (S3 pointers, large sample streams)**: the
`memwatch_*.jsonl` per-second memory sample streams in the same three
prefixes (~0.05–2.3 MB each). §4's absolute memory figures (RR anon
17.26→18.19 GB across C, anon sums 22.3/23.9/24.6 GB, memory.peak
30/38/38 GB, LI flat 14.7–15.1 GB, the 0.92 GB/token fit) trace to
those streams; the landed point artifacts carry the beside-note naming
them (`memory_note`). They stay on S3 until ruled otherwise.

## 2. Diagnosis artifacts — LANDED 2026-09-02 (13 files, both prefixes)

History: the stated prefixes were checked EMPTY earlier the same day
(the campaign archive was cut 2026-09-01 23:44Z, before the diagnosis
probes ran); `probe/archive_films_diagnosis.sh` was committed, the
operator pasted it, and the box printed per-file sha256 before upload.
The laptop fetch **matches all 13 box-printed hashes exactly** (hashes
in §3a below). What each file proves:

- `parity_failing/probe_frame_parity_{ABucketofBlood,
  A_Study_In_Scarlet,HouseOnBareMountain}.json` — the A==C EXACT
  byte-level frame parity on the three failing films with the
  manifest-sha same-input proof (§6 exclusion 1; the committed Leagues
  A==B==C artifact covers the fourth film).
- `detector_parity/census_20260902T074527Z.json` (mode census) and
  `census_20260902T080135Z.json` (extended size/dtype census) — the
  all-RGB result (§6 exclusion 2) and the 560px size partition's data
  (§6's 35/35 table).
- `detector_parity/detr_engine.py` + `detr_li.py` — the two containers'
  installed `rfdetr/detr.py`, and the landed pair hashes IDENTICALLY
  (`d0cf8916…` both) — §6 exclusion 4's byte-identity claim is now a
  committed byte-identity.
- `detector_parity/side_{engine,li}.json` + `.err` — **the side test's
  two side documents, READ 2026-09-02 (§4 below)** — each carrying the
  full libs identity block (torch 2.10.0+cu128 git `449b1768…`, pillow
  10.4.0, torchvision 0.25.0+cu128, numpy 2.5.2, detr sha `d0cf8916…`,
  per-container site-packages paths) — the §6 exclusion-4 Layer-1
  reads, now committed.
- `detector_parity/{small,large}.png` — the two probe frames
  (20000Leagues midpoint 320×240; HouseOnBareMountain midpoint
  714×480), landed (172K+580K total made everything landable — nothing
  left on S3 as pointer from these prefixes).

## 2a. THE SIDE TEST, READ — verdict first

**Ruling U is CONFIRMED in its verdict and REFINED in its mechanism;
nothing is overturned.** The committed comparator
(`probe_detector_parity.py --compare`) run over the two side documents
(log-prefix lines mechanically stripped — rf-detr logs to stdout ahead
of the JSON; the stripped lines are quoted in the run record):

- **P1 (small, 20000Leagues 320×240): MET, stronger than predicted** —
  arrays equal, raw scores **BIT-EQUAL at 9 dp** (max sorted delta
  0.0), 300/300 raw detections, self-determinism nulls PASS both sides.
- **P2 (large, HouseOnBareMountain 714×480): arrays equal and raw
  scores BIT-EQUAL at 9 dp** — no divergence of any size, not even the
  predicted %-scale. But the P2 instance turns out to be
  **non-discriminating**: the frame was extracted at the film's
  midpoint (`run_side_prediction.sh`, `-ss video_s/2` → sampled-frame
  index 123), and the landed campaign records show the arms **AGREED
  at that frame** (both `['person']` — matching the probe's own n=1
  @0.3 three ways), while 113/248 of the film's frames diverged,
  including indices 120 and 124 beside it. The arming-film selection
  lesson (§10.4 of the DEFINITIVE), repeated at frame granularity:
  the large frame was chosen by convenience (midpoint), not against
  the records. (Caveat kept: a single `-ss` extract is not
  byte-guaranteed to equal the campaign's fps-sampled frame 123; the
  timestamp mapping and the three-way @0.3 agreement are the
  correspondence evidence.)
- **The falsifier as written does not cleanly fire** — it presupposed
  the large frame would be a diverging instance; on an agreeing frame,
  0.0 is what every candidate mechanism predicts.

**What the test DID establish (new, real):** on identical bytes, in a
single-inference context, the two containers' full
load→resize→predict path is **bit-reproducible across containers** —
300 raw scores to 9 dp on BOTH size classes, through the >560px
downscale, with libs identical and weights MD5-matched. This
**excludes any static, always-on stack difference** (a "the two
containers' resize produces different pixels as a standing property"
variant is dead): the campaign divergence requires something the probe
context did not have — campaign execution context (thread state,
allocator, load, serving path) and/or diverging-frame content. The
probe cannot separate those two, because its frame is an agreeing one.
**The decisive next instrument is the same probe pointed at a
campaign-diverging frame** (House index 124, or the §6 anatomy frame
10) — one box run, harness resumable.

**Run warts, stated (neither voids the result):** (1) the engine-side
run DOWNLOADED fresh weights (its `.err` shows the 355M fetch; rf-detr
validated the canonical MD5) while the LI side used its cached file
(MD5-correct) — same canonical weights by rf-detr's own gate, but the
offline/`-w` cache mechanism did not hold on the engine side; (2) the
side documents do NOT record `torch.get_num_threads()` — the design
called for it, v2 did not write it; an instrument gap to close before
the diverging-frame run, since thread state is a live candidate.

## 3. Landed-file hashes (sha256 at landing)

```
053fae63a0de1ad6e8cbdadfb4f62bb857b9e7498fe46788be6151ac9253aec0  posture-sweep-20260830/curve_li_N16xT2_C32.json
8b9a35591340e590c9e41070faca0c07b32361ff2071a6bdc5847b75ae1437a7  posture-sweep-20260830/curve_li_N4xT8_C8.json
77c1dfdab18137c75643d05cb6efa0786618e7dd8d823afbe880e7a343a2218e  posture-sweep-20260830/curve_li_N8xT2_C16.json
646539652b8dd3a88ce8f98420697883b79c686333478f8f5b755c002c50a3d0  posture-sweep-20260830/curve_li_N8xT4_C16.json
d44ea20cdd28851ae7b29c1a38d5b0412abd0ed905b8c06f7c846c324f14d3fd  posture-sweep-20260830/curve_li_N8xT8_C16.json
9e8c1e734f9a20554dbe1e336c07a2822ae19b033f3f497d902d3a80e9bdf92e  posture-sweep-20260830/curve_rr_M16xT2_C32.json
a0485ff54e3dc034138c579641263ac3994f97c06836d0a51e6373212e45a041  posture-sweep-20260830/curve_rr_M16xT4_C32.json
a019310051ac5a2924260a5e0dd0d515112dd61f20f0d8f954ffc17d8b859fcc  posture-sweep-20260830/curve_rr_M32xT1_C35.json
75d7df7b12270896b5d4fdbbeb9839468d0814287bda92df6935a209ef60ebd5  posture-sweep-20260830/curve_rr_M4xT8_C8.json
df659f3610ca45e70622983a3a4b4c957abbeb3705413634ddf10f4cfe117e2c  posture-sweep-20260830/curve_rr_M8xT2_C16.json
549c01df6eae0686fece7a9ed72428ff79da487c18cb6666067a385c6a8bd4bf  posture-sweep-20260830/curve_rr_M8xT4_C16.json
71e8f078c273c1396d2e31fd76892b712dd03ab7c21e315e6f6a9e47c09a3f1e  c-sweep-20260831/curve_li_N16xT2_C1.json
bf43c3c8bfc660bacb5bd1820a513b79b29ad88ae77ad44b78646b9ca7e61316  c-sweep-20260831/curve_li_N16xT2_C16.json
ba1dac6596341cdb6fc5c0728c6145e73684405343b2ccc9f7faf0bf872cdeb1  c-sweep-20260831/curve_li_N16xT2_C2.json
b2da8071ddbedb28d614c720d3b72394225edb20a83240f11ee3a55aa15adf9e  c-sweep-20260831/curve_li_N16xT2_C32.json
bfd2a297f1788a00210de5faee81bdc5f492dea23c2737d8e51ee0cb97c14af5  c-sweep-20260831/curve_li_N16xT2_C4.json
c28cfedd56b8d40626b82264bde805cc2726c1a09454a5d7927963b5d2ad69b4  c-sweep-20260831/curve_li_N16xT2_C8.json
8d4d6ee65d9be26d1fb741c0fec4af314f45f43a54ec05fa9e88bcadb3d0cb8b  c-sweep-20260831/curve_rr-default_C1.json
24e0a363256d72a456675e3e40bae015d7eb4bf7ccf7136243eee847755f8e5f  c-sweep-20260831/curve_rr-default_C2.json
367a258b6faac2d738f6da3a6fdd8ba606583c7ea5f3040d860d5387eddae2d9  c-sweep-20260831/curve_rr_M16xT2_C1.json
fce96d05f6701131a56d6e202a1f57940fe585da44d89ae8be4ea89c37f4af79  c-sweep-20260831/curve_rr_M16xT2_C16.json
f9aa236a53bf62239dbd16304b422a2687f42fc318ea02a4c507d57b379e5eb9  c-sweep-20260831/curve_rr_M16xT2_C2.json
f9e85e1db1d61baaff065040a678230ac6b548e656f099e13a440e40a26740bb  c-sweep-20260831/curve_rr_M16xT2_C32.json
c55c973c1c15523ecd3dd601585eb2ee5ab04e3bd942d569ed973522f2eaff33  c-sweep-20260831/curve_rr_M16xT2_C4.json
6501e7c6caf337185a12729bd6e8322b40c9d721f343610b6d44e3b3d0cba2a1  c-sweep-20260831/curve_rr_M16xT2_C8.json
f5365d6bf26a40ba41ebb465e19357da1d0875a046293d1bfdc1347ce7ce1239  c-sweep-highc-20260831/curve_li_N16xT2_C16.json
285b01958d7a3fc69d008552235d1c075419879fe1e23e8dcd96439d47c28a7f  c-sweep-highc-20260831/curve_li_N16xT2_C32.json
7f0942d58e53f42177e332b0a2551bcee6a60a26382f0facc76345b2d26d8d7f  c-sweep-highc-20260831/curve_li_N16xT2_C8.json
6ff19cbfb31033cf8f32954890ef8544bf90c62e30f9b48da675f594c953a47b  c-sweep-highc-20260831/curve_rr_M16xT2_C16.json
a53067d92621a60c341f547129f0d3507c344a636720a228d8a9c97fd6a51819  c-sweep-highc-20260831/curve_rr_M16xT2_C32.json
8f1f95733c3a99822e7e975249357ca25595061b534cb029f57e033f647a3b38  c-sweep-highc-20260831/curve_rr_M16xT2_C8.json
```

## 3a. Diagnosis-archive hashes (box-printed pre-upload; laptop fetch MATCHED all 13)

```
0b1a110bca0941ae41552aaace3a611c638cd078972eaed7fc59629036ad6b88  detector-parity-20260902/census_20260902T074527Z.json
9b0dc302360b07fa0b4dd6ddd5a3af1e6cf1c14ab9337068e491d2d75900f5f7  detector-parity-20260902/census_20260902T080135Z.json
d0cf8916b8109bed319a8f458ffcd3c01a55421d43f2a1f66e8b6a9c95560c84  detector-parity-20260902/detr_engine.py
d0cf8916b8109bed319a8f458ffcd3c01a55421d43f2a1f66e8b6a9c95560c84  detector-parity-20260902/detr_li.py
11f2c99e12ee46ade7ca0b1ae9916add6eb9c4e89d7f8c1514a49cf53a2cbed5  detector-parity-20260902/large.png
b7b9dff2f9351d3dce22657afbd3052157e0764b3e0d4e766d00675430389a99  detector-parity-20260902/side_engine.err
02105062e39efe57660a88b1d8b7059b3b622fd2ab6227737565515412c52aaa  detector-parity-20260902/side_engine.json
7811fb993524b13809188bd3cd7e3734e521e5071162958977748ed0f87644e2  detector-parity-20260902/side_li.err
0cb2459ae7394e66c928103da70559267b5d9a497087741e7a2f8014e35add56  detector-parity-20260902/side_li.json
a82a6b2f32eb57cbf44b1626f5010015743ee2bbd19110a7a17e80d4fbd9a2e8  detector-parity-20260902/small.png
d9a673de875f59bba4927e49ae5e8baea307961e453bc4b89a00589966d8bf93  parity-failing-20260902/probe_frame_parity_ABucketofBlood.json
b818f144f4a436b217a3e2bd5a2936aaa980a75e6b72c9741ff8aa4ad2c8802f  parity-failing-20260902/probe_frame_parity_A_Study_In_Scarlet.json
e6b1585a132828e824ed7e907122e7e38003efcc78c8eaca070088d64a8a879b  parity-failing-20260902/probe_frame_parity_HouseOnBareMountain.json
```
