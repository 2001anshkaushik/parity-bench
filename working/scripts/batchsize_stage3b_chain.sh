#!/usr/bin/env bash
# batchsize_stage3b_chain.sh — the remaining Stage 3b document gates, one workload at a time.
#
#   bash working/scripts/batchsize_stage3b_chain.sh <campaign_dir> <slice.json> <expect_head>
#
# Sequential by construction (Ruling C: the box carries one leg and nothing else). Each step is
# its own container lifetime, so no step inherits the previous step's warm workers or loaded
# pipelines. A step that refuses does NOT stop the chain — a gate that cannot run is recorded as
# not run, and the steps after it are still independent measurements.
#
#   G3(b)  the service arm's worker count swept at its knee C: 16 and 32 beside the 24 already
#          measured. 24 was inherited from a 24-core cpuset that no longer exists (Ruling A), so
#          "each arm at its own optimum" has to be measured rather than carried.
#   G3(c)  K=256 replicated on both arms, plus a second continuous C=32 on each, which is what
#          gives the knee a noise floor to be judged against.
#   G5(a)  one cold-cache leg per arm at the winning batch size and at the winning continuous C.
#          The 384-document slice is ~267 MB on a 61 GiB box, so an ascending K grid re-reads a
#          corpus the page cache already holds; these legs pay the cold read a first leg pays.
set -uo pipefail
echo "batchsize_stage3b_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <slice.json> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
export BSZ_EXPECT_HEAD="$H"
R=()

step() {  # $1 label for the log; rest: env=val ... then the runner args
  local label="$1"; shift
  echo "===== STEP $label ====="
  ( env "$@" ) ; local rc=$?
  R+=("$label:rc=$rc")
  echo "===== STEP $label rc=$rc ====="
}

# G3(b) — the service arm at 16 and at 32 workers, both at C=32.
step li_w16 BSZ_LI_WORKERS=16 BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_w16" "" 0 w16
step li_w32 BSZ_LI_WORKERS=32 BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_w32" "" 0 w32

# G3(c) — replicates that give K=256 and the continuous knee a spread on both arms.
step li_u32b BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_u32b" 256,128 0 u32b
step rr_u32b BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_u32b" 256,128 0 u32b

# G5(a) — cold cache at each arm's winning configurations.
step li_cold BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32 BSZ_DROP_CACHES=1 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_cold" 128 0 cold
step rr_cold BSZ_CONTINUOUS=32 BSZ_DROP_CACHES=1 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_cold" 128 0 cold

echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
