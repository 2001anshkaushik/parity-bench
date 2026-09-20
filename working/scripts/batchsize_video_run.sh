#!/usr/bin/env bash
# batchsize_video_run.sh — one arm of the AMI "batch size" sweep, on the box.
#
#   bash working/scripts/batchsize_video_run.sh <rr|li> <n> <k-list> <out_dir_abs>
#
# WHAT "BATCH SIZE" CAN MEAN ON VIDEO, stated before any number: there is NO batch knob on the
# video path on either arm. The detector is called one frame at a time on both
# (engine/nodes/detect/IInstance.py:107; working/video/li_video/pipeline.py:251-260, the k=1
# bounded-residency loop adopted after a measured 42.7 GB OOM), the pipe exposes only
# threshold/prompt/profile, and the driver submits one video per call. A frame batch would mean
# patching the detect node inside rr:patched-video — not out of the box, and a different image
# from the one every banked number rides. So K here is the ONLY lever that exists without
# changing an arm: the number of videos IN FLIGHT (driver_video.py --blast-concurrency K).
#
# THE DRIVER IS NOT OURS TO EDIT HERE. It runs unmodified from the video worktree
# (~/parity-bench-video, the tree that holds the box-only AMI manifest), through the same entry
# points the banked legs used, with its own fail-closed preflight. Every K is `--leg blast`,
# K=1 included, so K is the only thing that changes between legs.
#
#   rr   default posture exactly as run_plan.sh start_rr unset: rr:patched-video, --network
#        host, --memory 58g, six thread variables ABSENT, one token, use(threads=) not passed.
#   li   the banked headline posture (overnight_apples.sh start_li_set 8 4): eight single-worker
#        instances, thread variables at 4, driver round-robin.
#
# Idle cores come from a per-core sidecar (harness/percore_sampler.py) running beside each leg
# on all 32 cores — the video posture has no cpuset, so the driver's own cores are in the
# picture and its share is reported by the driver itself (driver_cpu.share_of_box).
#
# A fresh container lifetime PER LEG, both arms, so no leg inherits the previous leg's state.
set -uo pipefail

echo "batchsize_video_run.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 4 ] || { echo "usage: $0 <rr|li> <n> <k-list> <out_dir_abs>" >&2; exit 2; }
ARM="$1"; N="$2"; KLIST="$3"; OUT="$4"
PY="$HOME/.venv/bin/python"
BATCH_TREE="$(cd "$(dirname "$0")/../.." && pwd)"
VIDEO_TREE="${BSZ_VIDEO_TREE:-$HOME/parity-bench-video}"
case "$OUT" in /*) ;; *) echo "out_dir must be absolute" >&2; exit 2;; esac
"$PY" -c 'import psutil' || { echo "REFUSED: $PY cannot import psutil" >&2; exit 2; }
cd "$VIDEO_TREE" || { echo "REFUSED: no video worktree at $VIDEO_TREE" >&2; exit 2; }
echo "video tree: $(pwd) head $(git rev-parse --short HEAD) ; batch tree: $BATCH_TREE head $(git -C "$BATCH_TREE" rev-parse --short HEAD)"
MAN="working/video/ami_video_manifest.jsonl"
[ -f "$MAN" ] || { echo "REFUSED: $MAN is not on this box" >&2; exit 2; }

# FAIL CLOSED ON A STALE WORKTREE (2026-09-20). A `git pull --ff-only` that aborts leaves the
# box on an OLDER commit, and the chain then runs an older script under a posture nobody
# declared — which is how a Stage 3b launch briefly ran the Stage 3 cpuset. The caller states
# the commit it means to measure; anything else refuses here rather than producing data.
if [ -n "${BSZ_EXPECT_HEAD:-}" ]; then
  HAVE="$(git rev-parse HEAD 2>/dev/null | cut -c1-12)"
  WANT="$(echo "$BSZ_EXPECT_HEAD" | cut -c1-12)"
  [ "$HAVE" = "$WANT" ] || { echo "REFUSED: worktree is at $HAVE, caller expects $WANT — the pull did not land; refusing to measure with an undeclared tree" >&2; exit 2; }
  echo "worktree head matches the declared commit: $HAVE"
fi
mkdir -p "$OUT"

ours=()
cleanup() { for c in "${ours[@]:-}"; do [ -n "$c" ] && { docker stop "$c" >/dev/null 2>&1; docker rm "$c" >/dev/null 2>&1; }; done; }
trap cleanup EXIT

refuse_existing() { for c in "$@"; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' exists — not ours to remove" >&2; exit 3; }; done; }

envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }

LI_N=8; LI_T=4
PORTS=""; NAMES=""
for i in $(seq 0 $((LI_N-1))); do PORTS="$PORTS,$((8802+i))"; NAMES="$NAMES,li_bal_$i"; done
PORTS="${PORTS#,}"; NAMES="${NAMES#,}"

start_arm() {
  if [ "$ARM" = "rr" ]; then
    refuse_existing rr
    ours+=("$(docker run -d --name rr --memory 58g --log-opt max-size=200m --network host rr:patched-video)") || return 1
    "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
  else
    local i
    for i in $(seq 0 $((LI_N-1))); do refuse_existing "li_bal_$i"; done
    for i in $(seq 0 $((LI_N-1))); do
      # shellcheck disable=SC2046
      ours+=("$(docker run -d --name "li_bal_$i" --memory 7g $(envargs "$LI_T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30")") || return 1
    done
    for i in $(seq 0 $((LI_N-1))); do
      "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) --workers 1 --container "li_bal_$i" --deadline 1200 || return 1
    done
  fi
}

RCS=()
for K in ${KLIST//,/ }; do
  LEG="$OUT/${ARM}_k$K"
  [ -e "$LEG" ] && { echo "REFUSED: $LEG exists — append-only"; RCS+=("k$K:exists"); continue; }
  mkdir -p "$LEG"
  echo "=== $ARM K=$K n=$N — fresh lifetime ==="
  start_arm || { echo "NOT READY"; RCS+=("k$K:not_ready"); cleanup; ours=(); continue; }
  PYTHONPATH="$BATCH_TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$LEG/percore.jsonl" --duration 21600 --until "$LEG/.leg_done" > "$LEG/percore_summary.txt" 2>&1 &
  SPID=$!
  if [ "$ARM" = "rr" ]; then
    "$PY" working/video/driver_video.py --arm rocketride --posture default --leg blast --n "$N" --blast-concurrency "$K" --rr-threads-env unset --manifest "$MAN" --image-lineage "rr:patched-video sha256:b7f51acc (batch-size sweep, default posture)" --out-dir "$LEG" 2>&1 | tee "$LEG/driver.log"
  else
    "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$N" --blast-concurrency "$K" --li-ports "$PORTS" --li-containers "$NAMES" --manifest "$MAN" --image-lineage "li:video sha256:0a52afcb (batch-size sweep, LI-balanced 8x4)" --out-dir "$LEG" 2>&1 | tee "$LEG/driver.log"
  fi
  RC=${PIPESTATUS[0]}
  touch "$LEG/.leg_done"; wait "$SPID" 2>/dev/null
  RCS+=("k$K:rc=$RC")
  for c in "${ours[@]:-}"; do [ -n "$c" ] && docker logs "$c" > "$LEG/dockerlog_${c:0:12}.txt" 2>&1; done
  cleanup; ours=()
done
echo "LEGS: ${RCS[*]}"

STAMP="$(basename "$(dirname "$OUT")")/$(basename "$OUT")"
for K in ${KLIST//,/ }; do
  LEG="$OUT/${ARM}_k$K"; [ -d "$LEG" ] || continue
  DEST="s3://rocketride-benchmark-data/ansh/batch-size-optimization/$STAMP/${ARM}_k$K/"
  if aws s3 ls "$DEST" >/dev/null 2>&1; then echo "!! $DEST exists — not uploading over it"; continue; fi
  aws s3 cp "$LEG" "$DEST" --recursive --only-show-errors && echo "uploaded $DEST"
done
echo "DONE arm=$ARM ${RCS[*]}"
