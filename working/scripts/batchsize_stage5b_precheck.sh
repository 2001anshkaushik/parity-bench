#!/usr/bin/env bash
# batchsize_stage5b_precheck.sh — S5-B's correctness gate, run BEFORE any patch or image build.
#
#   bash working/scripts/batchsize_stage5b_precheck.sh <out_dir> <expect_head>
#
# Runs working/scripts/s5b_batch_identity_probe.py inside a THROWAWAY container of the UNMODIFIED
# rr:patched-video (docker run --rm, --network none, every mount read-only), under the engine's
# own embedded interpreter, on 24 frames of one AMI video sampled at the campaign's 15 s interval.
# rr:patched-video is only READ — never modified, retagged or removed (it is not bit-reproducible
# and every banked RocketRide number rides it).
#
# The probe's verdict decides S5-B mechanically:
#   PASS  batched inference is bit-identical at B=2,4,8 -> the node patch + new image + the
#         end-to-end control through the pipe may proceed
#   FAIL  it is not -> per the Stage 5 ruling, B>1 is a different measurement, not an
#         optimisation; the sweep stops here and the finding is the magnitude and where it arose
#
# Posture: the out-of-the-box default (six thread variables UNSET), because that is the posture
# a patched node would be compared against. Strictly after Stage 4 (same guard as S5-A).
set -uo pipefail
echo "batchsize_stage5b_precheck.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <out_dir> <expect_head>" >&2; exit 2; }
OUT="$1"; H="$2"
cd "$(dirname "$0")/../.." || exit 2
[ "$(git rev-parse HEAD | cut -c1-12)" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: worktree is not at the declared commit $H" >&2; exit 2; }
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh is absent from this tree" >&2; exit 2; }
REL="$(results_rel "$OUT")" || { echo "REFUSED: out_dir $OUT is not under working/results/ — its S3 prefix mirrors that path" >&2; exit 2; }
S4="${BSZ_STAGE4_DIR:-}"
[ -n "$S4" ] && [ -d "$S4" ] || { echo "REFUSED: set BSZ_STAGE4_DIR — Stage 5 runs strictly after Stage 4 is banked" >&2; exit 5; }
for need in p1_rr_cont32 p2_li_cont p3_rr_k128 p4_li_k128 p5_li_video p6_rr_video envelope_done.json; do
  [ -e "$S4/$need" ] || { echo "REFUSED: Stage 4 not banked — $S4/$need is absent" >&2; exit 5; }
done
RUNNING="$(docker ps --format '{{.Names}}')"          # captured: no pipe into grep -q (register 38)
if [ -n "$RUNNING" ]; then
  echo "REFUSED (Ruling C): containers are running: $(tr '\n' ' ' <<< "$RUNNING")" >&2; exit 3
fi
VDIR="$HOME/parity-bench-video/corpus/ami/full"
VIDS=("$VDIR"/*)                                      # glob expansion is sorted; no pipe into head
[ -e "${VIDS[0]}" ] || { echo "REFUSED: no AMI video under $VDIR" >&2; exit 2; }
VID="$(basename "${VIDS[0]}")"
mkdir -p "$OUT"
[ -e "$OUT/s5b_precheck.json" ] && { echo "REFUSED: $OUT/s5b_precheck.json exists — append-only" >&2; exit 3; }
echo "video: $VID  image: $(docker image inspect -f '{{.Id}}' rr:patched-video)"
# stdout is kept WHOLE and the verdict extracted from it: the engine's imports may log to stdout,
# and one such line in a file read as JSON would refuse S5-B for a reason unrelated to the verdict.
docker run --rm --network none \
  -v "$VDIR:/v:ro" -v "$(pwd)/working/scripts:/probe:ro" \
  -w /opt/rocketride/engine rr:patched-video \
  /opt/rocketride/engine/engine /probe/s5b_batch_identity_probe.py "/v/$VID" 24 \
  > "$OUT/s5b_precheck.stdout" 2> "$OUT/s5b_precheck.stderr"
RC=$?
echo "probe rc=$RC"
"$HOME/.venv/bin/python" working/scripts/extract_probe_json.py "$OUT/s5b_precheck.stdout" "$OUT/s5b_precheck.json"
[ -f "$OUT/s5b_precheck.json" ] && cat "$OUT/s5b_precheck.json" || { echo "!! no verdict — stdout tail:"; tail -n 20 "$OUT/s5b_precheck.stdout"; echo "!! stderr tail:"; tail -n 20 "$OUT/s5b_precheck.stderr"; }
aws s3 cp "$OUT" "s3://rocketride-benchmark-data/ansh/batch-size-optimization/$REL/" --recursive --only-show-errors || echo "!! upload failed — results remain in $OUT"
echo "DONE rc=$RC"
exit "$RC"
