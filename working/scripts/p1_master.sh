#!/usr/bin/env bash
# p1_master.sh — everything after P1-A, in the pre-registered order, at ONE head, one workload at a time:
#   P1-B (p1_docs_chain p1b) -> rr:p1-pdfium build -> P1-C (p1_docs_chain p1c) -> P1-D (p1_video_chain v1full)
#   bash working/scripts/p1_master.sh <campaign_dir_abs> <expect_head> <deadline_epoch>
# The deadline (the 11-hour budget) is checked before every leg by the chains: a leg in flight finishes,
# a leg not yet started is recorded NOT_RUN_budget.
set -uo pipefail
echo "p1_master.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
D="$1"; H="$2"; export P1_DEADLINE_EPOCH="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || exit 2
echo "master start $(date -u +%FT%TZ) head $(git rev-parse HEAD | cut -c1-12) deadline $(date -u -d @"$P1_DEADLINE_EPOCH" +%FT%TZ)"
bash working/scripts/p1_docs_chain.sh "$D" "$H" p1b; echo "p1b rc=$?"
if [ "$(date +%s)" -lt "$P1_DEADLINE_EPOCH" ]; then
  bash working/scripts/p1_pdfium_build.sh "$D"; echo "pdfium_build rc=$?"
  [ -f "$D/p1c_build.json" ] && aws s3 cp "$D/p1c_build.json" "s3://rocketride-benchmark-data/ansh/parity-p1/$REL/p1c_build.json" --only-show-errors
  bash working/scripts/p1_docs_chain.sh "$D" "$H" p1c; echo "p1c rc=$?"
else
  echo "P1-C NOT RUN: budget"
fi
if [ "$(date +%s)" -lt "$P1_DEADLINE_EPOCH" ]; then
  bash working/scripts/p1_video_chain.sh "$D" "$H" v1full; echo "v1full rc=$?"
else
  echo "P1-D NOT RUN: budget"
fi
echo "CHAIN_DONE master $(date -u +%FT%TZ)"
