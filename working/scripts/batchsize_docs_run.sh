#!/usr/bin/env bash
# batchsize_docs_run.sh — one arm of the docs batch-size sweep, on the box, start to finish.
#
#   bash working/scripts/batchsize_docs_run.sh <rr|li> <slice.json> <run_dir> <k-list> [ref_c] [label] [thread_env]
#
# Launched through `working/harness/box.sh launch` (nohup, log in ~/logs). Never pasted.
#
# WHAT IT DOES, in order, refusing at the first thing that is not as declared:
#   1. refuses if a container named rr or li already exists — it will not remove one it did not
#      create (arms run ONE AT A TIME: PHASE1_CARRYOVER "never concurrently");
#   2. starts the arm UNCONSTRAINED (Ruling A, 2026-09-20): --memory 58g, the six thread
#      variables, -p, and NO --cpuset-cpus and NO --cpus. This deliberately departs from the
#      canonical docs posture (PHASE1_CARRYOVER.md:261-279 pins 0-23), because that cpuset is
#      exactly what made the Stage 3 docs table incomparable with the video and cross-team
#      numbers; the driver REFUSES if any cpuset or quota still binds.
#      thread_env=unset omits the six variables (engine default);
#   3. waits for a real answer from the service, not a TCP accept (register entry 3);
#   4. runs the sweep with the driver on the complementary cores (taskset -c 24-31). The driver
#      reads the posture back from the running container and refuses on any mismatch;
#   5. removes ONLY the container it created, by id;
#   6. ships the run dir and the export to S3 as NEW objects (exfil_s3.sh, instance role).
#
# No keep-alive here: forbidden during a measured leg (AUTOMATION_CONTRACT §4.4).
set -uo pipefail

echo "batchsize_docs_run.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -ge 4 ] || { echo "usage: $0 <rr|li> <slice.json> <run_dir> <k-list> [ref_c] [label] [thread_env]" >&2; exit 2; }
ARM="$1"; SLICE="$2"; RUN_DIR="$3"; KLIST="$4"; REFC="${5:-}"; LABEL="${6:-}"; TENV="${7:-1}"
CONT="${BSZ_CONTINUOUS:-}"          # G3a: continuous-submission C sweep, comma list
LI_WORKERS="${BSZ_LI_WORKERS:-24}"  # G3b/G4: the service arm's worker count is a swept knob
PY="$HOME/.venv/bin/python"
CORPUS="${BSZ_CORPUS_DIR:-$HOME/parity-bench/corpus/govdocs1/pdfs}"
cd "$(dirname "$0")/../.." || exit 2
echo "worktree: $(pwd)  branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)  dirty: $(git status --porcelain | wc -l)"
"$PY" -c 'import psutil' || { echo "REFUSED: $PY cannot import psutil — wrong interpreter" >&2; exit 2; }
[ -d "$CORPUS" ] || { echo "REFUSED: corpus dir $CORPUS missing" >&2; exit 2; }

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

for c in rr li; do
  if docker inspect "$c" >/dev/null 2>&1; then
    echo "REFUSED: a container named '$c' already exists — not ours to remove" >&2; exit 3
  fi
done

TARGS=()
if [ "$TENV" != "unset" ]; then
  for v in OMP_NUM_THREADS MKL_NUM_THREADS OPENBLAS_NUM_THREADS VECLIB_MAXIMUM_THREADS NUMEXPR_NUM_THREADS TORCH_NUM_THREADS; do
    TARGS+=(-e "$v=$TENV")
  done
fi

if [ "$ARM" = "rr" ]; then
  CID=$(docker run -d --name rr --memory 58g "${TARGS[@]}" -p 5565:5565 rr:patched) || exit 4
  READY='curl -sf http://127.0.0.1:5565/version'
elif [ "$ARM" = "li" ]; then
  CID=$(docker run -d --name li --memory 58g -e WS1_WORKERS="$LI_WORKERS" "${TARGS[@]}" -p 8801:8801 ws1-llamaindex:x86_64) || exit 4
  READY='curl -sf http://127.0.0.1:8801/health'
else
  echo "arm must be rr or li" >&2; exit 2
fi
echo "started $ARM container $CID"
cleanup() { echo "removing our container $CID"; docker stop "$CID" >/dev/null 2>&1; docker rm "$CID" >/dev/null 2>&1; }
trap cleanup EXIT

ok=0
for i in $(seq 1 180); do
  if out=$($READY 2>/dev/null); then ok=1; echo "service answered after ~$((i*5))s: ${out:0:160}"; break; fi
  sleep 5
done
[ "$ok" = 1 ] || { echo "REFUSED: $ARM service did not answer in 900s"; docker logs --tail 40 "$CID"; exit 5; }
if [ "$ARM" = "li" ]; then
  # Workers warm one by one; a leg against a half-warm pool measures the warm-up, not the arm.
  for i in $(seq 1 180); do
    w=$(curl -sf http://127.0.0.1:8801/health | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("warm_workers"))' 2>/dev/null)
    echo "warm_workers=$w/$LI_WORKERS"; [ "$w" = "$LI_WORKERS" ] && break; sleep 5
  done
  [ "$w" = "$LI_WORKERS" ] || { echo "REFUSED: only $w of $LI_WORKERS workers warm after 900s"; exit 6; }
else
  # G2 needs env_probe INSIDE the task process. The image should carry it (Dockerfile.rocketride
  # COPYs it); if it does not, copy it into the writable layer and restart — docker cp is undone
  # by docker rm, so this is per-container, every time (DOCS_HANDOFF §8.4).
  if ! docker exec "$CID" test -f /opt/rocketride/engine/nodes/env_probe/IInstance.py 2>/dev/null; then
    echo "env_probe absent in the image — copying the repo node in and restarting"
    docker cp working/nodes/env_probe "$CID":/opt/rocketride/engine/nodes/ || exit 6
    docker restart "$CID" >/dev/null || exit 6
    for i in $(seq 1 180); do curl -sf http://127.0.0.1:5565/version >/dev/null 2>&1 && break; sleep 5; done
  fi
  echo "env_probe md5 in container: $(docker exec "$CID" md5sum /opt/rocketride/engine/nodes/env_probe/IInstance.py 2>/dev/null | cut -d" " -f1)  repo: $(md5sum working/nodes/env_probe/IInstance.py | cut -d" " -f1)"
fi

ARGS=(--arm "$ARM" --slice "$SLICE" --run-dir "$RUN_DIR" --k "$KLIST" --corpus-dir "$CORPUS" --thread-env "$TENV")
[ -n "$REFC" ] && [ "$REFC" != "0" ] && ARGS+=(--reference-c "$REFC")
[ -n "$CONT" ] && ARGS+=(--continuous "$CONT")
[ -n "$LABEL" ] && [ "$LABEL" != "-" ] && ARGS+=(--label "$LABEL")
# NO taskset on the driver either (Ruling A). Pinning it to 24-31 was the complement of the
# arm's 0-23 cpuset; with the arm unconstrained across every vCPU, a pinned driver would both
# contradict the ruling and hide its own cost in 8 cores it does not own. The driver's CPU is
# now a reported number (cost.driver_cores), not a hidden one.
SMOKE_PORT=8801 "$PY" working/scripts/exp_batchsize_sweep.py "${ARGS[@]}"
RC=$?
echo "sweep rc=$RC"

# RUN_DIR is <campaign dir>/<arm>_<label>: one S3 prefix per launch, so a later launch can never
# re-upload (overwrite) an earlier launch's objects — S3 under ansh/ is append-only too.
STAMP="$(basename "$(dirname "$RUN_DIR")")"
if aws s3 ls "s3://rocketride-benchmark-data/ansh/batch-size-optimization/$STAMP/$(basename "$RUN_DIR")/" >/dev/null 2>&1; then
  echo "!! S3 prefix for this launch already exists — NOT uploading over it; results remain in $RUN_DIR"; exit "$RC"
fi
BENCH_S3="s3://rocketride-benchmark-data/ansh/batch-size-optimization" RUN_STAMP="$STAMP" \
  bash working/scripts/exfil_s3.sh "$RUN_DIR" $(ls -t working/results/exp_batchsize_sweep_"$ARM"__*.json 2>/dev/null | head -1) \
  || echo "!! exfil failed — results remain in $RUN_DIR on the box"
echo "DONE arm=$ARM rc=$RC"
exit "$RC"
