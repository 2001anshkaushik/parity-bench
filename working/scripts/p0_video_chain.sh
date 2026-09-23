#!/usr/bin/env bash
# p0_video_chain.sh — P0 video legs (V1 matched single instance; V2 duty cycle), on the box, one
# launch per stage, one workload at a time, a fresh container lifetime per leg.
#
#   bash working/scripts/p0_video_chain.sh <campaign_dir_abs> <expect_head> v1|v1full|v2
#
# Single instance on BOTH arms (the mandate): RocketRide = one token on rr:patched-video (the
# image is only run — never modified, retagged or removed); LlamaIndex = ONE li_video instance,
# one worker. No pooling, no frame batching. The driver is THIS tree's working/video/driver_video.py
# with P0_ONTOKEN=1 (env_probe read on the measured token — no second token), fed the box-only
# AMI manifest from the video worktree. Pre-registration: preregistration.json V1/V2.
#
#   v1      16 videos, K=16: rr_t4_a li_t4_a rr_def_a rr_t4_b li_t4_b rr_def_b (ABAB)
#   v1full  168 videos, K=16: rr_t4 then li_t4 — only with v1_gate.json (the fired gate) present
#   v2      16 videos, K=16, T=4: stamped/unstamped RocketRide ABAB + stamped LlamaIndex twice
set -uo pipefail
echo "p0_video_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head> <v1|v1full|v2>" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
TREE="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$TREE" || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; WANT="$(echo "$H" | cut -c1-12)"
[ "$HAVE" = "$WANT" ] || { echo "REFUSED: worktree at $HAVE, caller expects $WANT" >&2; exit 2; }
PY="$HOME/.venv/bin/python"
VMAN="${P0_VIDEO_MANIFEST:-$HOME/parity-bench-video/working/video/ami_video_manifest.jsonl}"
[ -f "$VMAN" ] || { echo "REFUSED: AMI manifest $VMAN absent" >&2; exit 2; }
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  manifest $(sha256sum "$VMAN" | cut -c1-16)"
R=()
ours=()
cleanup() { for c in "${ours[@]:-}"; do [ -n "$c" ] && { docker stop "$c" >/dev/null 2>&1; docker rm "$c" >/dev/null 2>&1; }; done; ours=(); }
trap cleanup EXIT
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
refuse_existing() { for c in "$@"; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' exists — not ours" >&2; return 1; }; done; return 0; }

# leg <name> <arm rr|li> <T|unset> <n> [stamped]
leg() {
  local name="$1" arm="$2" T="$3" n="$4" stamped="${5:-}" try L rc
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"
    [ -e "$L" ] && { echo "REFUSED: $L exists (append-only)"; continue; }
    mkdir -p "$L"
    echo "===== LEG ${name}${try} ($arm T=$T n=$n ${stamped:+STAMPED}) $(date -u +%H:%M:%SZ) ====="
    rc=0
    if [ "$arm" = "rr" ]; then
      refuse_existing rr || return 1
      ours+=("$(docker run -d --name rr --memory 58g $( [ "$T" != "unset" ] && envargs "$T") --log-opt max-size=200m --network host rr:patched-video)") || { rc=4; }
      # env_probe schema 3 (D0 on the measured token): the image bakes an older node; the repo's
      # copy goes into THIS container's writable layer, as the docs runner does
      [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
      if [ "$rc" = 0 ] && [ -n "$stamped" ]; then
        bash working/scripts/p0_v2_stamp.sh rr install rr || rc=6
      fi
      [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
    else
      refuse_existing li_bal_0 || return 1
      ours+=("$(docker run -d --name li_bal_0 --memory 16g $(envargs "$T") -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30")") || rc=4
      if [ "$rc" = 0 ] && [ -n "$stamped" ]; then
        bash working/scripts/p0_v2_stamp.sh li install li_bal_0 || rc=6
        [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
      fi
      [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
    fi
    if [ "$rc" = 0 ]; then
      PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
      local SPID=$!
      cat /proc/stat | head -1 > "$L/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$L/boot_id.txt"
      grep -m1 "model name" /proc/cpuinfo > "$L/cpu_model.txt"; grep MHz /proc/cpuinfo > "$L/mhz_open.txt"
      if [ "$arm" = "rr" ]; then
        if [ "$T" = "unset" ]; then
          P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture default --leg blast --n "$n" --blast-concurrency 16 --rr-threads-env unset --manifest "$VMAN" --image-lineage "rr:patched-video sha256:b7f51acc (P0 $name, default posture)" --out-dir "$L" > "$L/driver.log" 2>&1
        else
          P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency 16 --rr-threads-env "$T" --manifest "$VMAN" --image-lineage "rr:patched-video sha256:b7f51acc (P0 $name, 1 token, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
        fi
      else
        "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency 16 --li-ports 8802 --li-containers li_bal_0 --manifest "$VMAN" --image-lineage "li:video sha256:0a52afcb (P0 $name, ONE instance, six vars=$T)" --out-dir "$L" > "$L/driver.log" 2>&1
      fi
      rc=$?
      cat /proc/stat | head -1 > "$L/procstat_close.txt"; grep MHz /proc/cpuinfo > "$L/mhz_close.txt"
      touch "$L/.leg_done"; wait "$SPID" 2>/dev/null
      if [ -n "$stamped" ]; then
        if [ "$arm" = "rr" ]; then bash working/scripts/p0_v2_stamp.sh rr collect rr "$L"; else bash working/scripts/p0_v2_stamp.sh li collect li_bal_0 "$L"; fi
      fi
      for c in "${ours[@]:-}"; do [ -n "$c" ] && docker logs "$c" > "$L/dockerlog_${c:0:12}.txt" 2>&1; done
      [ "$arm" = "rr" ] && docker image inspect -f '{{.Id}}' rr:patched-video > "$L/engine_image_id.txt" 2>/dev/null
    fi
    tail -3 "$L/driver.log" 2>/dev/null
    cleanup
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then
      R+=("${name}${try}:MANDATE_VIOLATION"); upload "${name}${try}"; finish "STOPPED: mandate violation in ${name}${try}"; exit 9
    fi
    upload "${name}${try}"
    [ "$rc" -eq 0 ] && { R+=("${name}${try}:rc=0"); return 0; }
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED, chain continues"; return 1
}

upload() {
  local dest="s3://rocketride-benchmark-data/ansh/parity-p0/$REL/$1/"
  if aws s3 ls "$dest" >/dev/null 2>&1; then echo "!! $dest exists — not uploading over it"; return 1; fi
  aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"
}

finish() {
  "$PY" - "$D/chain_video_${STAGE}_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, sys, time
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split()}, open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_video_${STAGE}_done.json" "s3://rocketride-benchmark-data/ansh/parity-p0/$REL/chain_video_${STAGE}_done.json" --only-show-errors
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE $1"
}

for c in rr li; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' running — one workload at a time" >&2; exit 3; }; done
case "$STAGE" in
  v1)
    leg v1_rr_t4_a  rr 4 16
    leg v1_li_t4_a  li 4 16
    leg v1_rr_def_a rr unset 16
    leg v1_rr_t4_b  rr 4 16
    leg v1_li_t4_b  li 4 16
    leg v1_rr_def_b rr unset 16
    ;;
  v1full)
    [ -f "$D/v1_gate.json" ] || { echo "REFUSED: v1_gate.json (the committed fired gate) absent" >&2; exit 5; }
    leg v1full_rr_t4 rr 4 168
    leg v1full_li_t4 li 4 168
    ;;
  v2)
    [ -f working/scripts/p0_v2_stamp.sh ] || { echo "REFUSED: p0_v2_stamp.sh absent" >&2; exit 5; }
    leg v2_rr_s_a rr 4 16 stamped
    leg v2_rr_u_a rr 4 16
    leg v2_li_s_a li 4 16 stamped
    leg v2_rr_s_b rr 4 16 stamped
    leg v2_rr_u_b rr 4 16
    leg v2_li_s_b li 4 16 stamped
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
