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
#   4. runs the sweep with the driver unpinned (no taskset, Ruling A; its CPU is a reported
#      number). The driver reads the posture back from the running container and refuses on any
#      mismatch;
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
# S5-C ONLY: a DECLARED cpuset, the experimental variable of the SMT probe. Every other leg runs
# unconstrained (Ruling A); the driver asserts the container matches this exactly and labels the
# leg a diagnostic outside Ruling A.
CPUSET="${BSZ_CPUSET:-}"
CPUSET_ARGS=(); [ -n "$CPUSET" ] && CPUSET_ARGS=(--cpuset-cpus "$CPUSET")
PY="$HOME/.venv/bin/python"
CORPUS="${BSZ_CORPUS_DIR:-$HOME/parity-bench/corpus/govdocs1/pdfs}"
cd "$(dirname "$0")/../.." || exit 2
echo "worktree: $(pwd)  branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)  dirty: $(git status --porcelain | wc -l)"
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh is absent from this tree" >&2; exit 2; }
# The launch's S3 prefix mirrors its campaign's path under working/results/, however deep (a
# Stage 5 leg is <campaign>/s5c/rr_b). Decided HERE, before a container starts, so a run_dir
# that cannot be uploaded refuses instead of measuring and then stranding its results.
STAMP="$(results_parent_rel "$RUN_DIR")" || { echo "REFUSED: run_dir $RUN_DIR is not <campaign under working/results/>/<leg>" >&2; exit 2; }
# A launch never writes into another launch's directory (working/results/ is append-only), which
# also guarantees that the export_path.txt read after the sweep was written by THIS launch.
if [ -d "$RUN_DIR" ] && [ -n "$(ls -A "$RUN_DIR" 2>/dev/null)" ]; then
  echo "REFUSED: run_dir $RUN_DIR exists and is not empty — choose a new launch directory" >&2; exit 2
fi
# Open files (2026-09-21): the service arm's batch mode holds K requests open at once, and the box's
# default soft limit of 1,024 killed the first LlamaIndex K=1024 leg with EMFILE. Raised for this
# runner and the driver only (never the arm's container); the driver records the limit in its export
# and refuses a leg the limit cannot hold.
NOFILE_WANT=65536; NOFILE_HARD="$(ulimit -Hn)"
if [ "$NOFILE_HARD" != "unlimited" ] && [ "$NOFILE_HARD" -lt "$NOFILE_WANT" ]; then NOFILE_WANT="$NOFILE_HARD"; fi
ulimit -n "$NOFILE_WANT" || echo "!! could not raise the open-file limit"
echo "driver open-file limit: soft $(ulimit -Sn) hard $(ulimit -Hn)"
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
  CID=$(docker run -d --name rr --memory 58g "${CPUSET_ARGS[@]}" "${TARGS[@]}" -p 5565:5565 rr:patched) || exit 4
  READY='curl -sf http://127.0.0.1:5565/version'
elif [ "$ARM" = "li" ]; then
  CID=$(docker run -d --name li --memory 58g "${CPUSET_ARGS[@]}" -e WS1_WORKERS="$LI_WORKERS" "${TARGS[@]}" -p 8801:8801 ws1-llamaindex:x86_64) || exit 4
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
  # G2 needs env_probe INSIDE the task process. ABSENT IS NOT THE ONLY FAILURE: rr:patched bakes
  # an OLDER copy of the node (md5 cba71b35 against the repo's, 2026-09-20) which returns an
  # empty response, and an instrument that answers nothing is worse than one that is missing —
  # it reads as "no pins declared". So the container's copy is compared with the repo's and
  # REPLACED when it differs, not merely when it is absent. docker cp writes to the writable
  # layer and is undone by docker rm, so this runs per container, every time (DOCS_HANDOFF §8.4).
  # The image itself is never rebuilt or retagged; product_pdf.pipe does not load this node, so
  # the measured legs are unaffected by its presence.
  # S5-D: the stamp node is not in any image; copy it in the same way, per container.
  if [ "${BSZ_STAMP:-}" = "1" ]; then
    docker cp working/nodes/stamp_probe "$CID":/opt/rocketride/engine/nodes/ || exit 6
    echo "stamp_probe copied in (S5-D instrumented leg); restart follows with env_probe's"
    NEED_RESTART=1
  fi
  REPO_MD5="$(md5sum working/nodes/env_probe/IInstance.py | cut -d" " -f1)"
  CON_MD5="$(docker exec "$CID" md5sum /opt/rocketride/engine/nodes/env_probe/IInstance.py 2>/dev/null | cut -d" " -f1)"
  echo "env_probe md5 container=${CON_MD5:-ABSENT} repo=$REPO_MD5"
  if [ "$CON_MD5" != "$REPO_MD5" ] || [ "${NEED_RESTART:-0}" = "1" ]; then
    echo "env_probe in the container is ${CON_MD5:+STALE}${CON_MD5:-ABSENT} — copying the repo node in and restarting"
    docker cp working/nodes/env_probe "$CID":/opt/rocketride/engine/nodes/ || exit 6
    docker restart "$CID" >/dev/null || exit 6
    for i in $(seq 1 180); do curl -sf http://127.0.0.1:5565/version >/dev/null 2>&1 && break; sleep 5; done
    CON_MD5="$(docker exec "$CID" md5sum /opt/rocketride/engine/nodes/env_probe/IInstance.py 2>/dev/null | cut -d" " -f1)"
    echo "env_probe md5 after copy: ${CON_MD5:-ABSENT} (repo $REPO_MD5)"
    [ "$CON_MD5" = "$REPO_MD5" ] || { echo "REFUSED: env_probe still does not match the repo after the copy" >&2; exit 6; }
  fi
fi

ARGS=(--arm "$ARM" --slice "$SLICE" --run-dir "$RUN_DIR" --k "$KLIST" --corpus-dir "$CORPUS" --thread-env "$TENV")
[ -n "$REFC" ] && [ "$REFC" != "0" ] && ARGS+=(--reference-c "$REFC")
[ -n "$CONT" ] && ARGS+=(--continuous "$CONT")
[ -n "$CPUSET" ] && ARGS+=(--declared-cpuset "$CPUSET")
[ -n "$LABEL" ] && [ "$LABEL" != "-" ] && ARGS+=(--label "$LABEL")
# NO taskset on the driver either (Ruling A). Pinning it to 24-31 was the complement of the
# arm's 0-23 cpuset; with the arm unconstrained across every vCPU, a pinned driver would both
# contradict the ruling and hide its own cost in 8 cores it does not own. The driver's CPU is
# now a reported number (cost.driver_cores), not a hidden one.
SMOKE_PORT=8801 "$PY" working/scripts/exp_batchsize_sweep.py "${ARGS[@]}"
RC=$?
if [ "${BSZ_STAMP:-}" = "1" ] && [ "$ARM" = "rr" ]; then
  docker cp "$CID":/tmp/stamp_probe.jsonl "$RUN_DIR/stamp_probe.jsonl" && echo "stamps copied out: $(wc -l < "$RUN_DIR/stamp_probe.jsonl") records" || echo "!! no stamp file came out of the container"
fi
echo "sweep rc=$RC"

# RUN_DIR is <campaign dir>/<arm>_<label>: one S3 prefix per launch, so a later launch can never
# re-upload (overwrite) an earlier launch's objects — S3 under ansh/ is append-only too. STAMP was
# fixed at the top; for a leg one level under its campaign it equals the old
# basename(dirname(RUN_DIR)), so every banked launch's key is unchanged.
if aws s3 ls "s3://rocketride-benchmark-data/ansh/batch-size-optimization/$STAMP/$(basename "$RUN_DIR")/" >/dev/null 2>&1; then
  echo "!! S3 prefix for this launch already exists — NOT uploading over it; results remain in $RUN_DIR"; exit "$RC"
fi
# THIS launch's export, as its driver named it — never "the newest export on disk". A driver that
# crashed before writing one had the previous launch's export re-sent under that export's own key
# (e12, 2026-09-21: identical bytes, but a re-put of an existing object; register 44).
LATEST_EXPORT="$(cat "$RUN_DIR/export_path.txt" 2>/dev/null)"
if [ -n "$LATEST_EXPORT" ] && [ -f "$LATEST_EXPORT" ]; then
  echo "export written by this launch: $LATEST_EXPORT"
else
  LATEST_EXPORT=""; echo "!! the driver wrote no export (rc=$RC) — only the run dir is uploaded; no older export is re-sent"
fi
BENCH_S3="s3://rocketride-benchmark-data/ansh/batch-size-optimization" RUN_STAMP="$STAMP" \
  bash working/scripts/exfil_s3.sh "$RUN_DIR" "${LATEST_EXPORT:-}" \
  || echo "!! exfil failed — results remain in $RUN_DIR on the box"
echo "DONE arm=$ARM rc=$RC"
exit "$RC"
