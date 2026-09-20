#!/usr/bin/env bash
# batchsize_stage3b_video.sh — the Stage 3b video gates, one workload at a time.
#
#   bash working/scripts/batchsize_stage3b_video.sh <out_dir_abs> <expect_head>
#
#   G5(b)  replicates. The RocketRide video trend across K was 2.392 -> 2.623 f/s on n=1 legs,
#          a 9.6% span, while this campaign's banked pass-to-pass spreads run 0.19%-5.7%. A
#          trend inside the instrument's own noise is not a trend, and only a replicate can say
#          which it is. One RocketRide K=16 and one LlamaIndex K=8, both on the 16-video slice.
#   G4     the matched-unit anchor: ONE LlamaIndex instance against ONE RocketRide token at the
#          same in-flight K, so per-unit cross-arm claims rest on a measured cell instead of on
#          1 token against 8 tuned instances. Each arm keeps its own default thread posture and
#          both are read back in-process by the driver's own preflight; the asymmetry
#          (RocketRide unset -> torch 16, LlamaIndex at 4) is disclosed, never averaged away.
set -uo pipefail
echo "batchsize_stage3b_video.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <out_dir_abs> <expect_head>" >&2; exit 2; }
OUT="$1"; H="$2"
cd "$(dirname "$0")/../.." || exit 2
export BSZ_EXPECT_HEAD="$H"
R=()
step() { local l="$1"; shift; echo "===== STEP $l ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc ====="; }

# G5(b) — replicates of the two cells the ranking rests on.
step rr_k16_rep BSZ_LEG_SUFFIX=_rep bash working/scripts/batchsize_video_run.sh rr 16 16 "$OUT/rep"
step li_k8_rep  BSZ_LEG_SUFFIX=_rep bash working/scripts/batchsize_video_run.sh li 16 8  "$OUT/rep"

# G4 — one instance against one token, same K.
step li_1inst BSZ_LI_INSTANCES=1 BSZ_LEG_SUFFIX=_1inst bash working/scripts/batchsize_video_run.sh li 16 16 "$OUT/anchor"

echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
