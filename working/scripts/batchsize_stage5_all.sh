#!/usr/bin/env bash
# batchsize_stage5_all.sh — Stage 5, every probe, sequentially, as ONE box launch.
#
#   bash working/scripts/batchsize_stage5_all.sh <stage4_dir> <s5_dir> <slice_384> <slice_9975> <expect_head>
#
# Every path is RELATIVE to the repo root and <s5_dir> must not exist yet (working/results/ is
# append-only; a child that re-ran into an old directory would write over its files).
#
# Strictly after the envelope: every child refuses unless <stage4_dir>/envelope_done.json exists,
# and this launch is made only after the envelope has been landed on origin and read back.
# One workload at a time (Ruling C): each child starts and removes its own containers.
#
# ORDER, and why: the S5-B pre-check first (read-only, minutes) because its verdict decides
# whether S5-B builds anything; then S5-A, S5-C and S5-D, which never touch a patched image;
# then S5-B proper LAST, whose chain REFUSES unless the pre-check's verdict is a PASS — so "else
# STOP S5-B" is enforced by code, not by a judgement made mid-run. A child that refuses does not
# stop the others; each is an independent experiment and its refusal is recorded by name.
set -uo pipefail
echo "batchsize_stage5_all.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 5 ] || { echo "usage: $0 <stage4_dir> <s5_dir> <slice_384> <slice_9975> <expect_head>" >&2; exit 2; }
S4="$1"; S5="$2"; SL384="$3"; SL9975="$4"; H="$5"
cd "$(dirname "$0")/../.." || exit 2
ROOT="$(pwd)"
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh is absent from this tree" >&2; exit 2; }
case "$S5" in /*) echo "REFUSED: pass <s5_dir> relative to the repo root" >&2; exit 2;; esac
REL="$(results_rel "$S5")" || { echo "REFUSED: $S5 is not under working/results/" >&2; exit 2; }
[ -e "$S5" ] && { echo "REFUSED: $S5 exists — append-only; choose a new Stage 5 directory" >&2; exit 3; }
[ -f "$S4/envelope_done.json" ] || { echo "REFUSED: $S4/envelope_done.json absent — the envelope has not finished" >&2; exit 5; }
for f in "$SL384" "$SL9975"; do [ -f "$f" ] || { echo "REFUSED: slice $f absent" >&2; exit 2; }; done
export BSZ_STAGE4_DIR="$S4"
mkdir -p "$S5"
R=()
step() { local l="$1"; shift; echo "======= STAGE5 $l $(date -u +%H:%M:%SZ) ======="; ( "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "======= STAGE5 $l rc=$rc $(date -u +%H:%M:%SZ) ======="; }

# The two video chains take ABSOLUTE output dirs (their runner works from the video worktree).
step s5b_precheck bash working/scripts/batchsize_stage5b_precheck.sh "$S5/s5b_precheck" "$H"
step s5a_threads  bash working/scripts/batchsize_stage5a.sh "$ROOT/$S5/s5a" "$H"
step s5c_smt      bash working/scripts/batchsize_stage5c_smt.sh "$S5/s5c" "$SL384" "$H"
step s5d_funnel   bash working/scripts/batchsize_stage5d_funnel.sh "$S5/s5d" "$SL9975" "$H"
step s5b_proper   bash working/scripts/batchsize_stage5b.sh "$ROOT/$S5/s5b" "$S5/s5b_precheck/s5b_precheck.json" "$H"

"$HOME/.venv/bin/python" - "$S5/stage5_done.json" "${R[*]}" <<'PYDONE'
import json, sys, time
json.dump({"stage5_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "steps": sys.argv[2].split()}, open(sys.argv[1], "x"), indent=1)
PYDONE
aws s3 cp "$S5/stage5_done.json" "s3://rocketride-benchmark-data/ansh/batch-size-optimization/$REL/stage5_done.json" --only-show-errors || echo "!! upload of stage5_done.json failed"
echo "STAGE5 RESULTS: ${R[*]}"
echo "CHAIN_DONE"
