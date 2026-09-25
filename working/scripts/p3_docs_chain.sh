#!/usr/bin/env bash
# p3_docs_chain.sh — P3 docs legs (P3-A, P3-C, P3-D) on the box, one launch per stage, one workload at a time.
#
#   bash working/scripts/p3_docs_chain.sh <campaign_dir> <expect_head> <stage>
#
#   c_smoke   P3-C: 384 slice, rr:p1-tikafix, ONE token, C=32, stamped, six thread vars in {1,2,4}, ABAB two runs each,
#             embedding vectors captured: p3c_t1_a p3c_t2_a p3c_t4_a p3c_t1_b p3c_t2_b p3c_t4_b
#   a_health  P3-A health smoke: p3a_rr_h (rr:p1-tikafix, one token, C=32, stamped), p3a_li_h (LlamaIndex 24 workers, C=32)
#   a_full    P3-A full 9,975: p3a_rr_full (texts; the fixed-Tika full comparator for P3-C and P3-D), p3a_li_full
#   d_smoke   P3-D = P2-C's smoke on rr:p3-pdfium: the eleven at C=1 ABAB (p3d_s_{fix,hyb,pure}_{a,b}; G_node_D after the
#             first HYBRID and PURE legs: exit 8 on failure), then the 384 slice ABAB with texts (p3d_{fix,hyb,pure}_{a,b})
#   c_full    P3-C full: P3C_WINNER=<2|4> -> p3c_t<W>_full (comparator p3a_rr_full; if absent, p3c_t1_full first)
#   d_full    P3-D full: P3D_VARIANTS="hybrid pure" (fired) -> p3d_<v>_full with texts (comparator p3a_rr_full; if absent,
#             p3d_fix_full first)
#
# Every leg: one fresh container via batchsize_docs_run.sh (Ruling A unconstrained, Ruling C), P0's D0 on the measured
# token (BSZ_P0; a violation stops the chain: exit 9), the 1 Hz memory sampler started after the run dir exists
# (BSZ_MEMSTAT; the FIRST leg of the stage is gated on it: exit 10), RocketRide legs stamped. A leg that did not
# complete is retried at most twice; a DEGRADED leg with every row is a result and is not retried (register 55).
# Before every leg the P3 budget (P3_DEADLINE_EPOCH) is checked: a leg not started past it is NOT_RUN_budget.
set -uo pipefail
echo "p3_docs_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <expect_head> <c_smoke|a_health|a_full|d_smoke|c_full|d_full>" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
S384=working/results/batchsize_smoke_20260920T113000Z/slice_docs_n384_w25.json
S9975=working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json
S11=working/results/parity_p2_20260924T160106Z/slice_docs_n11_stragglers_w25.json
for s in "$S384" "$S9975" "$S11"; do [ -f "$s" ] || { echo "REFUSED: slice $s absent" >&2; exit 2; }; done
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1 BSZ_P0=1 BSZ_S3_ROOT=parity-p3 BSZ_MEMSTAT=1
PY="$HOME/.venv/bin/python"
S3="s3://rocketride-benchmark-data/ansh/parity-p3/$REL"
PDFIMG=rr:p3-pdfium
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  deadline ${P3_DEADLINE_EPOCH:-unset}"
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix "$PDFIMG"; do echo "image $i $(docker image inspect -f '{{.Id}}' "$i" 2>/dev/null)"; done; }
ids
R=(); LAST=""; FIRSTDONE=0
up_gate() { [ -f "$D/gates/$1.json" ] && { aws s3 ls "$S3/gates/$1.json" >/dev/null 2>&1 || aws s3 cp "$D/gates/$1.json" "$S3/gates/$1.json" --only-show-errors; }; }
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
# leg <name> <arm rr|li> <slice> [VAR=value ...]   (TEXTS=1, VECS=1, TENV=<n> are chain flags, not exported)
leg() {
  local name="$1" arm="$2" slice="$3"; shift 3
  local envs=("$@") try dir rc texts=0 vecs=0 tenv=1 e
  for e in "${envs[@]}"; do case "$e" in TEXTS=1) texts=1 ;; VECS=1) vecs=1 ;; TENV=*) tenv="${e#TENV=}" ;; esac; done
  if [ -n "${P3_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P3_DEADLINE_EPOCH" ]; then
    echo "!! $name NOT RUN: the P3 7-hour budget has passed"; R+=("${name}:NOT_RUN_budget"); LAST=""; return 1
  fi
  for try in "" _r1 _r2; do
    dir="$D/${name}${try}"
    echo "===== LEG ${name}${try} ($arm, $(basename "$slice"), threads=$tenv, ${envs[*]}) $(date -u +%H:%M:%SZ) ====="
    ( for e in "${envs[@]}"; do case "$e" in TEXTS=1|VECS=1|TENV=*) ;; *) export "$e" ;; esac; done
      [ "$texts" = 1 ] && export P1_TEXT_DUMP="$dir/texts.jsonl.gz"
      [ "$vecs" = 1 ] && export P3_VEC_DUMP="$dir/vecs.jsonl.gz"
      bash working/scripts/batchsize_docs_run.sh "$arm" "$slice" "$dir" "" 0 "${name}${try}" "$tenv" )
    rc=$?
    echo "===== LEG ${name}${try} rc=$rc $(date -u +%H:%M:%SZ) ====="
    if ! "$PY" working/scripts/p3_gates.py mandate "$dir" >/dev/null; then
      [ -d "$dir" ] && ls "$dir"/leg_*.json >/dev/null 2>&1 && { R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; }
    fi
    if [ "$rc" -eq 0 ] || measured_loss "$dir"; then
      [ "$rc" -eq 0 ] && R+=("${name}${try}:rc=0") || R+=("${name}${try}:DEGRADED_result")
      LAST="${name}${try}"
      if [ "$FIRSTDONE" = 0 ]; then
        FIRSTDONE=1
        "$PY" working/scripts/p3_gates.py memstat "$D" "$LAST"; local g=$?; up_gate "G_memstat_$LAST"
        [ "$g" = 0 ] || { R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10; }
      fi
      return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! ${name} failed three times — recorded FAILED"; LAST=""; return 1
}
finish() {
  ids
  "$PY" - "$D/chain_${STAGE}_done.json" "$1" "${R[*]}" "$PDFIMG" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "rr:p1-tikafix", sys.argv[4])}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_${STAGE}_done.json" "$S3/chain_${STAGE}_done.json" --only-show-errors
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE $1"
}
for c in rr li li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' present" >&2; exit 3; }; done
RRT=(BSZ_RR_IMAGE=rr:p1-tikafix BSZ_STAMP=1)
comparator() { local c; for c in "$D"/p3a_rr_full "$D"/p3a_rr_full_r1 "$D"/p3a_rr_full_r2; do [ -f "$c/texts.jsonl.gz" ] && ls "$c"/leg_*.json >/dev/null 2>&1 && { basename "$c"; return 0; }; done; return 1; }
case "$STAGE" in
  c_smoke)
    for r in a b; do for t in 1 2 4; do leg "p3c_t${t}_$r" rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32 TENV="$t" VECS=1; done; done
    ;;
  a_health)
    leg p3a_rr_h rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32
    leg p3a_li_h li "$S384" BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32
    ;;
  a_full)
    leg p3a_rr_full rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p3a_li_full li "$S9975" BSZ_LI_WORKERS=24 BSZ_CONTINUOUS=32
    ;;
  d_smoke)
    docker image inspect "$PDFIMG" >/dev/null 2>&1 || { echo "REFUSED: $PDFIMG absent" >&2; exit 5; }
    PDF=(BSZ_RR_IMAGE="$PDFIMG" BSZ_STAMP=1)
    leg p3d_s_fix_a rr "$S11" "${RRT[@]}" BSZ_CONTINUOUS=1
    leg p3d_s_hyb_a rr "$S11" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=1
    "$PY" working/scripts/p3_gates.py node_d "$D" "${LAST:-p3d_s_hyb_a}" hybrid; NH=$?; up_gate G_node_D_hybrid
    leg p3d_s_pure_a rr "$S11" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=1
    "$PY" working/scripts/p3_gates.py node_d "$D" "${LAST:-p3d_s_pure_a}" pure; NP=$?; up_gate G_node_D_pure
    if [ "$NH" != 0 ] || [ "$NP" != 0 ]; then R+=("G_node_D:FAIL(hybrid=$NH,pure=$NP)"); finish "STOPPED: G_node_D (the prototype node did not produce text)"; exit 8; fi
    leg p3d_s_fix_b rr "$S11" "${RRT[@]}" BSZ_CONTINUOUS=1
    leg p3d_s_hyb_b rr "$S11" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=1
    leg p3d_s_pure_b rr "$S11" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=1
    leg p3d_fix_a rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p3d_hyb_a rr "$S384" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=32 TEXTS=1
    leg p3d_pure_a rr "$S384" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=32 TEXTS=1
    leg p3d_fix_b rr "$S384" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1
    leg p3d_hyb_b rr "$S384" "${PDF[@]}" P1C_VARIANT=hybrid BSZ_CONTINUOUS=32 TEXTS=1
    leg p3d_pure_b rr "$S384" "${PDF[@]}" P1C_VARIANT=pure BSZ_CONTINUOUS=32 TEXTS=1
    ;;
  c_full)
    case "${P3C_WINNER:-}" in 2|4) ;; *) echo "REFUSED: P3C_WINNER must be 2 or 4" >&2; exit 5 ;; esac
    if ! comparator >/dev/null; then echo "comparator: P3-A's RR full leg absent -> p3c_t1_full first"; leg p3c_t1_full rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TENV=1; fi
    leg "p3c_t${P3C_WINNER}_full" rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TENV="$P3C_WINNER"
    ;;
  d_full)
    docker image inspect "$PDFIMG" >/dev/null 2>&1 || { echo "REFUSED: $PDFIMG absent" >&2; exit 5; }
    [ -n "${P3D_VARIANTS:-}" ] || { echo "REFUSED: P3D_VARIANTS empty" >&2; exit 5; }
    if ! comparator >/dev/null; then echo "comparator: P3-A's RR full leg absent -> p3d_fix_full first"; leg p3d_fix_full rr "$S9975" "${RRT[@]}" BSZ_CONTINUOUS=32 TEXTS=1; fi
    for v in $P3D_VARIANTS; do
      case "$v" in hybrid) n=p3d_hyb_full ;; pure) n=p3d_pure_full ;; *) echo "unknown variant $v"; continue ;; esac
      leg "$n" rr "$S9975" BSZ_RR_IMAGE="$PDFIMG" BSZ_STAMP=1 P1C_VARIANT="$v" BSZ_CONTINUOUS=32 TEXTS=1
    done
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
