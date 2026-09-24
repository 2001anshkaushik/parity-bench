#!/usr/bin/env bash
# p2_docs_chain.sh — P2 docs legs (P2-A, P2-C) on the box, one launch per stage, one workload at a time.
#
#   bash working/scripts/p2_docs_chain.sh <campaign_dir> <expect_head> a_smoke|c_smoke|a_full|c_full
#
#   a_smoke  P2-A smoke (1): 384 slice C=32, ABAB two runs each: p2a_rr_a (rr:p1-tikafix, ONE token) p2a_li_a
#            (LlamaIndex 24 workers) p2a_rr_b p2a_li_b; then (2) the 96 anchor at C=8: p2a_an_rr_a p2a_an_li_a
#            (ONE worker) p2a_an_rr_b p2a_an_li_b. After the FIRST leg: G_memstat (exit 10 if it fails).
#   c_smoke  P2-C smoke (i): the eleven at C=1, ABAB: p2c_s_fix_a p2c_s_hyb_a p2c_s_pure_a p2c_s_fix_b p2c_s_hyb_b
#            p2c_s_pure_b (G_node_C after the first HYBRID and PURE legs: exit 8 if either fails); then (ii) the
#            384 slice C=32 with texts: p2c_fix_a p2c_hyb_a p2c_pure_a p2c_fix_b p2c_hyb_b p2c_pure_b.
#   a_full   P2-A full: p2a_rr_full (rr:p1-tikafix, texts — P2-C's comparator) then p2a_li_full (24 workers), C=32.
#   c_full   P2-C full: P2C_VARIANTS="hybrid pure" (the fired ones) and P2C_COMPARATOR (p2a_rr_full, or empty
#            -> p2c_fix_full runs first); each variant full run with texts.
#
# Every leg: one fresh container via batchsize_docs_run.sh (Ruling A unconstrained, Ruling C), P0's D0 on the
# measured token (BSZ_P0), the 1 Hz memory sampler started after the run dir exists (BSZ_MEMSTAT), RocketRide
# legs stamped (BSZ_STAMP). A mandate violation stops the chain (exit 9). A leg that did not complete is retried
# at most twice; a DEGRADED leg with every row present is a result and is not retried (register 55). Before every leg the P2 budget (P2_DEADLINE_EPOCH) is checked: a leg not started past it is
# recorded NOT_RUN_budget.
set -uo pipefail
echo "p2_docs_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <expect_head> <a_smoke|c_smoke|a_full|c_full>" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
S384=working/results/batchsize_smoke_20260920T113000Z/slice_docs_n384_w25.json
S96=working/results/batchsize_main_20260920T160920Z/slice_docs_n96_w25.json
S9975=working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json
S11="$D/slice_docs_n11_stragglers_w25.json"
for s in "$S384" "$S96" "$S9975" "$S11"; do [ -f "$s" ] || { echo "REFUSED: slice $s absent" >&2; exit 2; }; done
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1 BSZ_P0=1 BSZ_S3_ROOT=parity-p2 BSZ_MEMSTAT=1
PY="$HOME/.venv/bin/python"
S3="s3://rocketride-benchmark-data/ansh/parity-p2/$REL"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  deadline ${P2_DEADLINE_EPOCH:-unset}"
P2C_IMAGE="${P2C_IMAGE:-rr:p2-pdfium}"   # amendment 2: rr:p2-pdfium-b
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix "$P2C_IMAGE"; do echo "image $i $(docker image inspect -f '{{.Id}}' "$i" 2>/dev/null)"; done; }
ids
R=()
LAST=""
violation() {
  "$PY" - "$1" <<'PYV'
import json, sys, pathlib
for f in pathlib.Path(sys.argv[1]).glob("leg_*.json"):
    m = ((json.loads(f.read_text()).get("p0") or {}).get("mandate") or {})
    if m.get("mandate_violation"):
        print(f"MANDATE VIOLATION in {f}: {m.get('violations')}"); sys.exit(0)
sys.exit(1)
PYV
}
# 0 iff the leg completed every row and its driver marked it DEGRADED (a document lost to a timeout): a RESULT,
# never retried (register 55); any other non-zero rc is a run that did not complete and is retried.
measured_loss() {
  "$PY" - "$1" <<'PYL'
import json, sys, pathlib
for f in pathlib.Path(sys.argv[1]).glob("leg_*.json"):
    g = json.loads(f.read_text()); d = g.get("documents") or {}
    if g.get("verdict") == "DEGRADED" and d.get("submitted") and d.get("recorded") == d.get("submitted"):
        print(f"DEGRADED with every row present: {d}"); sys.exit(0)
sys.exit(1)
PYL
}
up_gate() { [ -f "$D/gates/$1.json" ] && aws s3 cp "$D/gates/$1.json" "$S3/gates/$1.json" --only-show-errors; }
# leg <name> <arm rr|li> <slice> [VAR=value ...]   (RR legs: BSZ_RR_IMAGE, P1C_VARIANT, TEXTS=1 in the list)
leg() {
  local name="$1" arm="$2" slice="$3"; shift 3
  local envs=("$@") try dir rc texts=0 e
  for e in "${envs[@]}"; do [ "$e" = "TEXTS=1" ] && texts=1; done
  if [ -n "${P2_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P2_DEADLINE_EPOCH" ]; then
    echo "!! $name NOT RUN: the P2 8-hour budget (preregistration.json budget_and_order) has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1
  fi
  for try in "" _r1 _r2; do
    dir="$D/${name}${try}"
    echo "===== LEG ${name}${try} ($arm, $(basename "$slice"), ${envs[*]}) $(date -u +%H:%M:%SZ) ====="
    ( for e in "${envs[@]}"; do [ "$e" = "TEXTS=1" ] || export "$e"; done
      [ "$texts" = 1 ] && export P1_TEXT_DUMP="$dir/texts.jsonl.gz"
      bash working/scripts/batchsize_docs_run.sh "$arm" "$slice" "$dir" "" 0 "${name}${try}" 1 )
    rc=$?
    echo "===== LEG ${name}${try} rc=$rc $(date -u +%H:%M:%SZ) ====="
    if violation "$dir"; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    [ "$rc" -eq 0 ] && { R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0; }
    if measured_loss "$dir"; then
      echo "   ${name}${try}: every row present, a document lost to its timeout — a result, not retried (register 55)"
      R+=("${name}${try}:DEGRADED_result"); LAST="${name}${try}"; return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! ${name} failed three times — recorded FAILED"; LAST=""; return 1
}
finish() {
  ids
  "$PY" - "$D/chain_${STAGE}_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "rr:p1-tikafix", __import__("os").environ.get("P2C_IMAGE", "rr:p2-pdfium"))}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_${STAGE}_done.json" "$S3/chain_${STAGE}_done.json" --only-show-errors
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE $1"
}
for c in rr li li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' present" >&2; exit 3; }; done
RRT=(BSZ_RR_IMAGE=rr:p1-tikafix BSZ_STAMP=1)
case "$STAGE" in
  a_smoke)
    docker image inspect rr:p1-tikafix >/dev/null 2>&1 || { echo "REFUSED: rr:p1-tikafix absent" >&2; exit 5; }
    leg p2a_rr_a rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32
    FIRST="$LAST"
    if [ -z "$FIRST" ] || ! "$PY" working/scripts/p2_gates.py memstat "$D" "${FIRST:-p2a_rr_a}"; then
      up_gate "G_memstat_${FIRST:-p2a_rr_a}"; R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10
    fi
    up_gate "G_memstat_$FIRST"
    leg p2a_li_a li "$S384" BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32
    leg p2a_rr_b rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32
    leg p2a_li_b li "$S384" BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32
    leg p2a_an_rr_a rr "$S96" "${RRT[@]}" BSZ_CONTINUOUS=8
    leg p2a_an_li_a li "$S96" BSZ_LI_WORKERS=1 BSZ_CONTINUOUS=8
    leg p2a_an_rr_b rr "$S96" "${RRT[@]}" BSZ_CONTINUOUS=8
    leg p2a_an_li_b li "$S96" BSZ_LI_WORKERS=1 BSZ_CONTINUOUS=8
    ;;
  c_smoke)
    docker image inspect "$P2C_IMAGE" >/dev/null 2>&1 || { echo "REFUSED: $P2C_IMAGE absent" >&2; exit 5; }
    PDF=(BSZ_RR_IMAGE="$P2C_IMAGE" BSZ_STAMP=1)
    leg p2c_s_fix_a rr "$S11" "${RRT[@]}" BSZ_CONTINUOUS=1
    leg p2c_s_hyb_a rr "$S11" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=1
    "$PY" working/scripts/p2_gates.py node_c "$D" "${LAST:-p2c_s_hyb_a}" hybrid; NH=$?; up_gate G_node_C_hybrid
    leg p2c_s_pure_a rr "$S11" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=1
    "$PY" working/scripts/p2_gates.py node_c "$D" "${LAST:-p2c_s_pure_a}" pure; NP=$?; up_gate G_node_C_pure
    if [ "$NH" != 0 ] || [ "$NP" != 0 ]; then
      R+=("G_node_C:FAIL(hybrid=$NH,pure=$NP)"); finish "STOPPED: G_node_C (the prototype node did not produce text)"; exit 8
    fi
    leg p2c_s_fix_b rr "$S11" "${RRT[@]}" BSZ_CONTINUOUS=1
    leg p2c_s_hyb_b rr "$S11" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=1
    leg p2c_s_pure_b rr "$S11" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=1
    leg p2c_fix_a rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p2c_hyb_a rr "$S384" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=32 TEXTS=1
    leg p2c_pure_a rr "$S384" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=32 TEXTS=1
    leg p2c_fix_b rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p2c_hyb_b rr "$S384" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=32 TEXTS=1
    leg p2c_pure_b rr "$S384" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=32 TEXTS=1
    ;;
  a_full)
    leg p2a_rr_full rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p2a_li_full li "$S9975" BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32
    ;;
  c_full)
    docker image inspect "$P2C_IMAGE" >/dev/null 2>&1 || { echo "REFUSED: $P2C_IMAGE absent" >&2; exit 5; }
    [ -n "${P2C_VARIANTS:-}" ] || { echo "REFUSED: P2C_VARIANTS empty — no variant's gate fired" >&2; exit 5; }
    if [ -z "${P2C_COMPARATOR:-}" ]; then
      echo "comparator: P2-A's RR full leg did not run -> p2c_fix_full first (preregistration P2_C full_run)"
      leg p2c_fix_full rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    else
      echo "comparator: $P2C_COMPARATOR (P2-A's RR full leg)"
    fi
    for v in $P2C_VARIANTS; do
      case "$v" in hybrid) n=p2c_hyb_full ;; pure) n=p2c_pure_full ;; *) echo "unknown variant $v"; continue ;; esac
      leg "$n" rr "$S9975" BSZ_RR_IMAGE="$P2C_IMAGE" BSZ_STAMP=1 P1C_VARIANT="$v" BSZ_CONTINUOUS=32 TEXTS=1
    done
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
