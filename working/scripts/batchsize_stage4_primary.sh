#!/usr/bin/env bash
# batchsize_stage4_primary.sh — the six PRIMARY Stage 4 legs at full scale, in the ruled order.
#
#   bash working/scripts/batchsize_stage4_primary.sh <campaign_dir> <docs_slice> <expect_head>
#
# ONE LEG PER CONTAINER LIFETIME, one workload on the box (Ruling C), every leg prewarmed to the
# same page-cache state (a cold read cost the service arm 20.9% at K=128, so leg ORDER would
# otherwise decide part of the answer), every arm unconstrained across every vCPU (Ruling A).
#
# The settings are the ones Stage 3b MEASURED, not inherited:
#   RocketRide  continuous at C=32 (its knee, resolved against a 0.82% replicate floor), and
#               K=128 as the barrier comparator.
#   LlamaIndex  continuous at C=32 AND at C=16, because its 9.87% floor cannot separate them and
#               register entry 12 is explicit that the competitor arm is never run below its own
#               measured optimum on a judgement call — so both are run and both are reported.
#               24 workers: the best point measured, with 16 and 32 inside its own noise.
#   Video       K=16 on both arms. RocketRide ONE PASS, per the ruling.
set -uo pipefail
echo "batchsize_stage4_primary.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <docs_slice> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

# 1-2. the two continuous legs: each arm at its own measured optimum.
step p1_rr_cont BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/p1_rr_cont32" "" 0 main
step p2_li_cont BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32,16 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/p2_li_cont" "" 0 main

# 3-4. the barrier comparators at the grid's best K.
step p3_rr_k128 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/p3_rr_k128" 128 0 main
step p4_li_k128 BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/p4_li_k128" 128 0 main

# 5-6. video. The AMI manifest decides n; 168 measured + 2 warm are its own roles.
step p5_li_video bash working/scripts/batchsize_video_run.sh li 168 16 "/home/ssm-user/parity-bench-batch/$D/p5_li_video"
step p6_rr_video bash working/scripts/batchsize_video_run.sh rr 168 16 "/home/ssm-user/parity-bench-batch/$D/p6_rr_video"

echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
