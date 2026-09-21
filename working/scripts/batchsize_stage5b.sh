#!/usr/bin/env bash
# batchsize_stage5b.sh — S5-B proper: detector frame micro-batching on a NEW tagged image.
#
#   bash working/scripts/batchsize_stage5b.sh <out_dir_abs> <precheck.json> <expect_head>
#
# PATCHED-ENGINE, NOT OUT-OF-THE-BOX. Runs only if the read-only pre-check passed Tier 1 or Tier 2.
#
#   1. BASE CHECK — the patch was written against the 3.3.1 detect node and detection module; their
#      md5s are pinned below and read INSIDE rr:patched-video. Any difference refuses: a patch
#      applied to a different base would measure the difference, not the batching.
#   2. BUILD rr:s5b-microbatch FROM rr:patched-video with ONLY the patched detect node (context =
#      a directory holding that one file). rr:patched-video is READ, never modified, retagged or
#      removed — its image id is read before and after the build and must not change. The built
#      image's detect node is read back and must equal the patched file.
#   3. LEGS on the 16-video slice, one token, default posture, K=16, the tap on: B = 1, 2, 4, 8.
#      B=1 goes through the NEW batched code path (a list of one frame), so "patched B=1 == stock"
#      tests this patch's reimplementation, not merely the rebuild.
#   4. The analyser decides correctness FIRST (null control: patched B=1 chunk hashes == stock;
#      then each B>1 against B=1, Tier 1 by chunk hash, Tier 2 by the per-frame tap) and reports
#      timing and peak anon ONLY for a B that passed — every figure labelled PATCHED-ENGINE.
set -uo pipefail
echo "batchsize_stage5b.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <out_dir_abs> <precheck.json> <expect_head>" >&2; exit 2; }
OUT="$1"; PRE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
S4="${BSZ_STAGE4_DIR:-}"
[ -n "$S4" ] && [ -f "$S4/envelope_done.json" ] || { echo "REFUSED: Stage 5 runs strictly after the envelope" >&2; exit 5; }
[ -f "$PRE" ] || { echo "REFUSED: no pre-check result at $PRE" >&2; exit 5; }
VERDICT="$(~/.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("verdict",""))' "$PRE")"
case "$VERDICT" in PASS*) echo "pre-check: $VERDICT";; *) echo "REFUSED: the pre-check did not pass (${VERDICT:-no verdict}) — per the ruling S5-B stops" >&2; exit 5;; esac
RUNNING="$(docker ps --format '{{.Names}}')"
[ -z "$RUNNING" ] || { echo "REFUSED (Ruling C): containers running: $RUNNING" >&2; exit 3; }

# 1. BASE CHECK — md5s of the 3.3.1 files the patch was written against (laptop bundle, 2026-09-21).
WANT_NODE=984d80e45e885b5ae21e987664850b4c
WANT_DET=9757fb00129d59ecb8e43fbdaac71595
BASE="$(docker run --rm --network none --entrypoint sh rr:patched-video -c 'md5sum /opt/rocketride/engine/nodes/detect/IInstance.py /opt/rocketride/engine/ai/common/models/vision/detection.py')"
echo "$BASE"
HAVE_NODE="$(awk 'NR==1{print $1}' <<< "$BASE")"; HAVE_DET="$(awk 'NR==2{print $1}' <<< "$BASE")"
[ "$HAVE_NODE" = "$WANT_NODE" ] && [ "$HAVE_DET" = "$WANT_DET" ] || { echo "REFUSED: rr:patched-video's detect node or detection module differs from the base the patch was written against" >&2; exit 5; }

# 2. BUILD — a new tag only; rr:patched-video's id must not move.
if docker image inspect rr:s5b-microbatch >/dev/null 2>&1; then
  echo "REFUSED: rr:s5b-microbatch already exists — not rebuilt over; inspect it by hand" >&2; exit 3
fi
BEFORE="$(docker image inspect -f '{{.Id}}' rr:patched-video)"
CTX="$(mktemp -d /tmp/s5b_ctx.XXXXXX)"
cp working/nodes/detect_s5b/IInstance.py "$CTX/IInstance.py"
docker build -q -f docker/Dockerfile.s5b -t rr:s5b-microbatch "$CTX" || { echo "REFUSED: build failed" >&2; exit 6; }
AFTER="$(docker image inspect -f '{{.Id}}' rr:patched-video)"
[ "$BEFORE" = "$AFTER" ] || { echo "REFUSED: rr:patched-video's id CHANGED during the build ($BEFORE -> $AFTER)" >&2; exit 7; }
PATCHED="$(md5sum working/nodes/detect_s5b/IInstance.py | cut -d' ' -f1)"
INIMG="$(docker run --rm --network none --entrypoint sh rr:s5b-microbatch -c 'md5sum /opt/rocketride/engine/nodes/detect/IInstance.py' | cut -d' ' -f1)"
[ "$PATCHED" = "$INIMG" ] || { echo "REFUSED: the built image's detect node ($INIMG) is not the patched file ($PATCHED)" >&2; exit 7; }
mkdir -p "$OUT"
printf '{"base_image_id": "%s", "s5b_image_id": "%s", "patched_node_md5": "%s", "base_node_md5": "%s", "base_detection_md5": "%s", "label": "PATCHED-ENGINE, NOT OUT-OF-THE-BOX"}\n' \
  "$BEFORE" "$(docker image inspect -f '{{.Id}}' rr:s5b-microbatch)" "$PATCHED" "$HAVE_NODE" "$HAVE_DET" > "$OUT/s5b_image.json"
cat "$OUT/s5b_image.json"

# 3. LEGS
export BSZ_EXPECT_HEAD="$H"
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }
for B in 1 2 4 8; do
  step "s5b_B$B" BSZ_RR_IMAGE=rr:s5b-microbatch BSZ_S5B_BATCH="$B" BSZ_S5B_TAP=1 BSZ_LEG_SUFFIX="_B$B" bash working/scripts/batchsize_video_run.sh rr 16 16 "$OUT"
done
aws s3 cp "$OUT/s5b_image.json" "s3://rocketride-benchmark-data/ansh/batch-size-optimization/${OUT##*/working/results/}/s5b_image.json" --only-show-errors || true
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
