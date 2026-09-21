#!/usr/bin/env bash
# batchsize_stage4_envelope.sh — the Stage 4 batch envelope, legs 7-11, after the six primaries.
#
#   bash working/scripts/batchsize_stage4_envelope.sh <campaign_dir> <docs_slice> <expect_head>
#
# REFUSES TO START unless all six primary legs have produced their leg files in this campaign —
# the ruling orders the envelope strictly after the primaries have landed.
#
# THE HYPOTHESIS, stated before the data (Stage 4 ruling): batch wall time was measured to equal
# the slowest document's solo service time at every K, so throughput should asymptote to the
# continuous value as the barrier count falls. The expected finding is therefore the MEMORY and
# BLAST-RADIUS cost of large send_files batches, not a throughput win — stated either way.
#
#    7-8  K=256 on both arms          9-10  K=1024 on both arms
#    11   K=512, CONDITIONAL, per arm, decided by batchsize_envelope_decide.py against floors
#         pre-registered in <campaign_dir>/envelope_floors.json before any K=256 leg existed.
#         A skip is recorded with the delta and the floor that caused it.
#
# Same discipline as the primaries: one leg per container lifetime, every leg prewarmed to the
# same cache state, unconstrained across every vCPU (Ruling A), one workload (Ruling C).
set -uo pipefail
echo "batchsize_stage4_envelope.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <docs_slice> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"

missing=()
for pat in "p1_rr_cont32/leg_rr_refc32_*" "p2_li_cont/leg_li_refc32_*" "p3_rr_k128/leg_rr_k128_*" "p4_li_k128/leg_li_k128_*"; do
  compgen -G "$D/$pat.json" >/dev/null || missing+=("$pat")
done
for v in p5_li_video/li_k16 p6_rr_video/rr_k16; do
  compgen -G "$D/$v/export_*.json" >/dev/null || missing+=("$v")
done
[ "${#missing[@]}" -eq 0 ] || { echo "REFUSED: primary legs not all landed: ${missing[*]}" >&2; exit 5; }
[ -f "$D/envelope_floors.json" ] || { echo "REFUSED: no pre-registered floors at $D/envelope_floors.json" >&2; exit 5; }

export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

step e7_rr_k256  bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e7_rr_k256" 256 0 env
step e8_li_k256  BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e8_li_k256" 256 0 env
step e9_rr_k1024 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e9_rr_k1024" 1024 0 env
step e10_li_k1024 BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e10_li_k1024" 1024 0 env

# 11 — mechanical, per arm. The K=128 legs are the primaries (p3/p4); the K=256 legs are 7/8.
"$PY" working/scripts/batchsize_envelope_decide.py "$D" "$D/envelope_floors.json" "$D/envelope_k512_decision.json" | tee "$D/envelope_k512_decision.txt"
if grep -q "^RUN_512 rr yes" "$D/envelope_k512_decision.txt"; then
  step e11_rr_k512 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e11_rr_k512" 512 0 env
else R+=("e11_rr_k512:SKIPPED_BY_RULE"); fi
if grep -q "^RUN_512 li yes" "$D/envelope_k512_decision.txt"; then
  step e11_li_k512 BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e11_li_k512" 512 0 env
else R+=("e11_li_k512:SKIPPED_BY_RULE"); fi

aws s3 cp "$D/envelope_k512_decision.json" "s3://rocketride-benchmark-data/ansh/batch-size-optimization/${D##*/working/results/}/envelope_k512_decision.json" --only-show-errors || true
aws s3 cp "$D/envelope_k512_decision.txt"  "s3://rocketride-benchmark-data/ansh/batch-size-optimization/${D##*/working/results/}/envelope_k512_decision.txt" --only-show-errors || true
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
