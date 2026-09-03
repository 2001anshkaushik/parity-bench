# AMI vs Archive Films — the data-type difference, characterized (2026-09-03)

For Shashi's question (relayed): why the two corpora produce different
benchmark results on the same setup. Held artifacts only; every cell
cited; derived values marked ᵈ.

## 1. Corpus comparison

| item | AMI (ami_full) | Films (35-subset) | source |
|---|---|---|---|
| items | 168 measured + 2 warm | 35 measured + 2 warm | both manifests |
| resolution | **352×288, uniform** | **320×240 – 1424×1072; 27/35 above 560px** | SESSION_STATE.md:1945 + her setup doc:210; films DEFINITIVE §6 table |
| duration/item | 2,058 s mean ᵈ (96.06 h ÷ 168) | 5,074 s mean, max 9,954 s (165.9 min) | her table basis; films manifest |
| frames/item @1/15 | 137.2 | 338 mean | exports (23,049/168; 11,841/35) |
| bytes/item | 0.142 GB mean, max 0.303 | 0.81 GB mean, max 2.19 | her landed AMI manifest; films manifest |
| bitrate | ~0.31 Mb/s | 1.27 Mb/s mean ᵈ | her setup doc:226; films manifest ᵈ |
| container/codec | mpeg4 AVI, audio stream on 170/170 | MP4, moov placement split front/end, old MPEG-derivative codecs present | her setup doc:210; SESSION_STATE:235; parity cell-B finding; her LONG_VIDEO_SOURCES:115 |
| detections/frame @0.3 | **8.50** (identical both arms) | **4.89 LI / 4.93 RR** (the cross-arm divergence visible in the pair) | exports: 195,999/23,049; 57,856 & 58,370/11,841 |
| chunks/item | 68.6 LI / 78.1 RR | 92.5 LI / 123.2 RR (4000/0 era; RR stock) | exports |
| gate 3 | 168/168 PASS, byte-identical scores | 27/35 FAIL on the 560px partition (Ruling U) | AMI DEFINITIVE:202; films DEFINITIVE §6 |
| total footage | 96.06 h | 49.33 h | both reports |

## 2. Where the time goes — held, with two named confounds

**Films LI 16×2 (clean, ruled cell, streaming build):** extract 22.5% /
detect 74.9% / split 0.02% / embed 2.6% — re-derived this round from the
landed records with the same code (reproduces the published figures
exactly; null control).

**AMI LI records DO carry `stage_s`** (the 24-Aug leg's 168 records,
fetched): extract 3.4% / detect 54.3% / split 0.03% / embed 42.3%.
**NOT like-for-like with the films shares, for two source-confirmed
reasons**: (1) BUILD — the AMI-era LI predates the streaming refactor
(`b295dea`, 08-27) and the 4000/0 splitter (Ruling L, 08-30; AMI ran
4000/200 with true ~200 overlap → more embed text), and critically
predates `cc91729` (08-25), which moved stage stamps INSIDE the lock —
on the 24-Aug build a stage bucket absorbs lock/contention wait;
(2) POSTURE — that leg is the 8-worker kernel-accept cell (contended,
~40% util), not the balanced headline (whose records file on S3 holds
only 18 send-side rows from the aborted attempt — no stage data
survives for it). The 42% "embed" is therefore largely wait
accounting, not embed compute. **Direction that survives the
confounds**: per-frame EXTRACT cost — AMI 55 ms vs films 228 ms
(~4×) — decode tracks pixels × bitrate, and contention could only have
inflated the AMI side.

**The clean same-build comparison costs one probe**: 1–2 AMI meetings
through the CURRENT li:video build on the box (~10–15 min) gives AMI
stage shares at films semantics, directly comparable to
22.5/74.9/0.02/2.6. **RR records carry no stage timings in either era**
(films DEFINITIVE §10.6) — every stage statement here is LI-side.

**The decomposition we DO hold clean — CPU per frame vs utilization,
same arm across corpora** (exports; cores ÷ pass-mean f/s ᵈ):

| | AMI | films | Δ |
|---|---|---|---|
| RR 16×2 CPU-s/frame | 2.308 | 2.683 ᵈ | **+16%** |
| LI (balanced) CPU-s/frame | 2.212 ᵈ | 2.117 ᵈ | **−4%** |
| RR util | 91.9% | 79.8% | −12 pts |
| LI util | 88.0% | 67.0% | −21 pts |
| span f/s | 12.74 / 12.74 | 9.51 / 10.13 | −25% / −20% |

Per-frame CPU cost barely moves (LI ~flat; RR +16%); **utilization
collapses** — the films throughput drop is mostly scheduling geometry,
not per-frame work.

## 3. The answer (three sentences + ranking)

The two corpora differ in three ways that matter and several that
don't: films are **long** (85 min vs 34 min mean — so 35 big items at
C=16 spend a large fraction of each leg ramping and draining, and
utilization drops 12–21 points, which is most of the −20–25%
throughput difference), films are **big-framed** (27/35 above the
detector's 560px input edge — which is the entire reason the two arms'
detections agree byte-for-byte on AMI and diverge on 27 films, and
which roughly quadruples per-frame decode cost and plausibly RR's +16%
per-frame CPU), and AMI meetings are **denser in detections** (8.5 vs
4.9 per frame) — which sounds important but is nearly cosmetic for
compute, since detector cost is per-inference, not per-detection.
Ranking by what moves the numbers: **(1) item length/count geometry
(throughput), (2) resolution vs the 560px edge (detection agreement +
per-frame cost), (3) detections-per-frame and chunk volume (small,
rides 2.6–3% of wall), (4) container/codec/audio/bitrate-as-such
(cosmetic — moov placement only ever affected a dead probe cell).**
