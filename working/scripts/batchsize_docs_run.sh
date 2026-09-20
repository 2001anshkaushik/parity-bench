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
#   2. starts the arm in the canonical docs posture (PHASE1_CARRYOVER.md:261-279; the form
#      probe_idle_spin_docs.py:247 executes): --cpuset-cpus 0-23, --memory 58g, the six thread
#      variables, -p, and NO --cpus. thread_env=unset omits the six variables (engine default);
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
PY="$HOME/.venv/bin/python"
CORPUS="${BSZ_CORPUS_DIR:-$HOME/parity-bench/corpus/govdocs1/pdfs}"
cd "$(dirname "$0")/../.." || exit 2
echo "worktree: $(pwd)  branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)  dirty: $(git status --porcelain | wc -l)"
"$PY" -c 'import psutil' || { echo "REFUSED: $PY cannot import psutil — wrong interpreter" >&2; exit 2; }
[ -d "$CORPUS" ] || { echo "REFUSED: corpus dir $CORPUS missing" >&2; exit 2; }

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
  CID=$(docker run -d --name rr --cpuset-cpus 0-23 --memory 58g "${TARGS[@]}" -p 5565:5565 rr:patched) || exit 4
  READY='curl -sf http://127.0.0.1:5565/version'
elif [ "$ARM" = "li" ]; then
  CID=$(docker run -d --name li --cpuset-cpus 0-23 --memory 58g -e WS1_WORKERS=24 "${TARGS[@]}" -p 8801:8801 ws1-llamaindex:x86_64) || exit 4
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
  # 24 workers warm one by one; a leg against a half-warm pool measures the warm-up.
  for i in $(seq 1 120); do
    w=$(curl -sf http://127.0.0.1:8801/health | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("warm_workers"))' 2>/dev/null)
    echo "warm_workers=$w"; [ "$w" = "24" ] && break; sleep 5
  done
fi

ARGS=(--arm "$ARM" --slice "$SLICE" --run-dir "$RUN_DIR" --k "$KLIST" --corpus-dir "$CORPUS" --thread-env "$TENV")
[ -n "$REFC" ] && [ "$REFC" != "0" ] && ARGS+=(--reference-c "$REFC")
[ -n "$LABEL" ] && [ "$LABEL" != "-" ] && ARGS+=(--label "$LABEL")
SMOKE_PORT=8801 taskset -c 24-31 "$PY" working/scripts/exp_batchsize_sweep.py "${ARGS[@]}"
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
