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

## 2. Diagnosis artifacts — NOT ON S3; archive script committed, landing BLOCKED on one box paste

Checked 2026-09-02: `s3://…/ansh/parity-failing-20260902/` and
`s3://…/ansh/detector-parity-20260902/` are **EMPTY**, and no
`*-20260902` prefix exists under `ansh/` — the archive step for
`~/films_probe/parity_failing/` and `~/films_probe/detector_parity/`
never ran (the campaign archive at `films-mainrun-20260901/` was cut
2026-09-01 23:44Z, before the diagnosis probes ran). The dirs remain
box-only. `probe/archive_films_diagnosis.sh` (committed, self-printing
sha256, box instance role, refuses if either dir is missing) creates
the two prefixes and prints per-file sha256 first; after that paste,
the JSON verdicts land here AMI_LANDING-style (frames/PNGs may stay on
S3 with pointers if bulky). What those artifacts back until then —
relayed verbatim into the record, not yet committed:

- `parity_failing/`: A==C EXACT byte-level frame parity on the three
  failing films + manifest-sha same-input proof (§6 exclusion 1; the
  committed Leagues A==B==C artifact covers the fourth film).
- `detector_parity/`: the 35-film PNG mode/size census (§6 exclusion 2
  and the 560px partition's size data), the Layer-1 build-identity
  reads (§6 exclusion 4: torch/pillow/torchvision/numpy versions, torch
  git/wheel identity, detr.py sha both containers), and the two
  extracted side-test frames (v1, reusable).

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
