#!/usr/bin/env bash
# batchsize_stage4_envelope.sh — the Stage 4 batch envelope: K=256, 512, 1024 on BOTH arms.
#
#   bash working/scripts/batchsize_stage4_envelope.sh <campaign_dir> <docs_slice> <expect_head>
#
# RULING, 2026-09-21: every K runs on both arms UNCONDITIONALLY. The K=512 rule pre-registered in
# envelope_floors.json is still evaluated, after the K=256 legs, and recorded FOR AUDIT ONLY — it
# gates nothing. (Before this ruling the rule decided whether K=512 ran.)
#
# REFUSES TO START unless, in <campaign_dir>:
#   - all six primary legs have landed (the envelope is strictly after the primaries);
#   - envelope_floors.json exists (the audit rule's pre-registered floors);
#   - envelope_deadline_preregistration.json exists — written and landed on origin BEFORE the
#     first envelope leg, fixing the batch deadline at 1800 s for every K and both arms, the
#     blast-radius reporting, and the BLAST-RADIUS-DOMINATED rule. The chain re-asserts the
#     deadline it will run under matches that file, and refuses otherwise.
#
# A batch lost to the deadline is BLAST RADIUS: recorded, never re-run. A leg in which more than
# one batch dies is reported BLAST-RADIUS-DOMINATED, not failed (the analyser applies the label).
#
# HYPOTHESIS, stated before the data: batch wall time was measured to equal the slowest
# document's solo service time at every K, so throughput should approach the continuous value
# as the barrier count falls; the expected finding is the memory and blast-radius cost of large
# send_files batches, not a throughput win. At K=128 the batch holding 039_039660.pdf took
# 1,707 s against the 1,800 s deadline — 93 s of margin — so a larger batch holding it may die.
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
PRE="$D/envelope_deadline_preregistration.json"
[ -f "$PRE" ] || { echo "REFUSED: no deadline pre-registration at $PRE — it must exist before leg 7" >&2; exit 5; }
WANT="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["batch_deadline_s"])' "$PRE")"
export BSZ_BATCH_TIMEOUT_S="${BSZ_BATCH_TIMEOUT_S:-1800}"
[ "$BSZ_BATCH_TIMEOUT_S" = "$WANT" ] || { echo "REFUSED: batch deadline $BSZ_BATCH_TIMEOUT_S differs from the pre-registered $WANT" >&2; exit 5; }
echo "deadline pre-registration honoured: batch deadline ${BSZ_BATCH_TIMEOUT_S}s at every K, both arms"

export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

step e7_rr_k256   bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e7_rr_k256" 256 0 env
step e8_li_k256   BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e8_li_k256" 256 0 env

# AUDIT ONLY: what the pre-registered K=512 rule would have decided. It gates nothing.
"$PY" working/scripts/batchsize_envelope_decide.py "$D" "$D/envelope_floors.json" "$D/envelope_k512_decision.json" | tee "$D/envelope_k512_decision.txt"
echo "(the K=512 rule above is AUDIT ONLY — K=512 runs on both arms regardless, by ruling)"

step e9_rr_k512   bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e9_rr_k512" 512 0 env
step e10_li_k512  BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e10_li_k512" 512 0 env
step e11_rr_k1024 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/e11_rr_k1024" 1024 0 env
step e12_li_k1024 BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/e12_li_k1024" 1024 0 env

DEST="s3://rocketride-benchmark-data/ansh/batch-size-optimization/${D##*/working/results/}"
for f in envelope_k512_decision.json envelope_k512_decision.txt; do
  aws s3 cp "$D/$f" "$DEST/$f" --only-show-errors || echo "!! upload of $f failed — it remains in $D"
done
# THE COMPLETION MARKER. Stage 5 requires THIS file, written last — never the K=512 audit file,
# which under the unconditional ruling appears mid-envelope, after the K=256 legs only.
"$PY" - "$D/envelope_done.json" "${R[*]}" <<'PYDONE'
import json, sys, time
json.dump({"envelope_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "steps": sys.argv[2].split()}, open(sys.argv[1], "x"), indent=1)
PYDONE
aws s3 cp "$D/envelope_done.json" "$DEST/envelope_done.json" --only-show-errors || echo "!! upload of envelope_done.json failed"
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
