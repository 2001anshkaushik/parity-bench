#!/usr/bin/env bash
# batchsize_stage5ef.sh — S5-E and S5-F, one box launch, RocketRide only, the 384-document slice.
#
#   bash working/scripts/batchsize_stage5ef.sh <campaign_dir> <slice_384.json> <expect_head>
#
# S5-E  THREAD VARIABLES AT ONE TOKEN, DOCS. Continuous C=32, the six thread variables UNSET (the
#       engine's out-of-the-box posture) against =1 (the banked docs posture), two runs each,
#       interleaved A B A B so drift cannot masquerade as the effect. The driver reads torch's
#       intra-op count back INSIDE the task process for every leg. The delta between postures is
#       read against the 0.82% Stage 3b floor, and beside it S5-C's measured null-control spread.
# S5-F  SDK DEFAULT-5 EQUIVALENT (PR #1895 / TypeScript maxConcurrent). Continuous C=5, banked
#       docs posture, two runs; reported against Stage 3b's C=4, C=8 and C=32 on the same slice
#       and posture (an earlier session, so labelled cross-session) and against this launch's own
#       C=32 legs (same session).
#
# PRE-REGISTERED (working/results/<campaign>/preregistration.json, written by the laptop and landed
# before this launch): the primary metric is span docs/s; docs/s to p90 is reported beside it as a
# diagnostic defined BEFORE these legs ran, because on this slice one 791-page document sets the span.
#
# Ruling C: one leg on the box at a time, each in its own container lifetime; the runner refuses if
# any rr/li container exists. Every leg prewarms the corpus so every leg starts from one cache state.
set -uo pipefail
echo "batchsize_stage5ef.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <slice_384.json> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh is absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json is absent — it must be landed before the legs" >&2; exit 5; }
[ -f "$SLICE" ] || { echo "REFUSED: slice $SLICE absent" >&2; exit 2; }
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

step s5e_env1_a  BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_env1_a"  "" 0 s5e_env1_a  1
step s5e_unset_a BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_unset_a" "" 0 s5e_unset_a unset
step s5e_env1_b  BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_env1_b"  "" 0 s5e_env1_b  1
step s5e_unset_b BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_unset_b" "" 0 s5e_unset_b unset
step s5f_c5_a    BSZ_CONTINUOUS=5  bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_c5_a"    "" 0 s5f_c5_a    1
step s5f_c5_b    BSZ_CONTINUOUS=5  bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_c5_b"    "" 0 s5f_c5_b    1

"$HOME/.venv/bin/python" - "$D/s5ef_done.json" "${R[*]}" <<'PYDONE'
import json, sys, time
json.dump({"s5ef_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "steps": sys.argv[2].split()}, open(sys.argv[1], "x"), indent=1)
PYDONE
aws s3 cp "$D/s5ef_done.json" "s3://rocketride-benchmark-data/ansh/batch-size-optimization/$REL/s5ef_done.json" --only-show-errors || echo "!! upload of s5ef_done.json failed"
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
