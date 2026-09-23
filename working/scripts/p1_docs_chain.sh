#!/usr/bin/env bash
# p1_docs_chain.sh — P1 docs legs (P1-B, P1-C) on the box, one launch per stage, one workload at a time.
#
#   bash working/scripts/p1_docs_chain.sh <campaign_dir> <expect_head> p1b|p1c
#
#   p1b  P1-B (preregistration.json P1_B): 384 slice C=32 stamped PROFILE p1b_base_a (rr:patched),
#        p1b_fix_a (rr:p1-tikafix) -> correctness gate; E1 engine path on the eleven, baseline then
#        fixed, with the exec census -> smoke gate; p1b_base_b, p1b_fix_b; then ONLY if both gates
#        passed: one full 9,975 run each (p1b_base_full, p1b_fix_full), chunk texts captured.
#   p1c  P1-C (preregistration.json P1_C): full 9,975 runs of HYBRID and PURE (rr:p1-pdfium, texts
#        captured) first; then the 384 ABAB: p1c_fix_a p1c_hyb_a p1c_pure_a p1c_fix_b p1c_hyb_b p1c_pure_b.
#
# Every leg: one fresh container via batchsize_docs_run.sh (Ruling A unconstrained, Ruling C), P0's
# D0 on the measured token (BSZ_P0), stamp_probe PROFILE stamps (BSZ_STAMP), the 1 Hz memory sampler
# (BSZ_MEMSTAT). A mandate violation stops the chain. A failed leg is retried at most twice.
set -uo pipefail
echo "p1_docs_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <expect_head> <p1b|p1c>" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
S384=working/results/batchsize_smoke_20260920T113000Z/slice_docs_n384_w25.json
S9975=working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1 BSZ_P0=1 BSZ_S3_ROOT=parity-p1 BSZ_STAMP=1 BSZ_MEMSTAT=1 BSZ_CONTINUOUS=32
PY="$HOME/.venv/bin/python"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE"
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix rr:p1-pdfium; do echo "$i $(docker image inspect -f '{{.Id}}' "$i" 2>/dev/null)"; done; }
ids
R=()
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
# leg <name> <image> <slice> [texts|-] [pure|hybrid]
leg() {
  local name="$1" img="$2" slice="$3" texts="${4:-}" variant="${5:-}" try dir rc
  [ "$texts" = "-" ] && texts=""
  for try in "" _r1 _r2; do
    dir="$D/${name}${try}"
    echo "===== LEG ${name}${try} ($img, $(basename "$slice")${texts:+, texts}${variant:+, $variant}) $(date -u +%H:%M:%SZ) ====="
    ( export BSZ_RR_IMAGE="$img"; [ -n "$texts" ] && export P1_TEXT_DUMP="$dir/texts.jsonl.gz"
      [ -n "$variant" ] && export P1C_VARIANT="$variant"
      bash working/scripts/batchsize_docs_run.sh rr "$slice" "$dir" "" 0 "${name}${try}" 1 )
    rc=$?
    echo "===== LEG ${name}${try} rc=$rc $(date -u +%H:%M:%SZ) ====="
    if violation "$dir"; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    [ "$rc" -eq 0 ] && { R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0; }
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! ${name} failed three times — recorded FAILED"; LAST=""; return 1
}
finish() {
  ids
  "$PY" - "$D/chain_${STAGE}_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "rr:p1-tikafix", "rr:p1-pdfium")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_${STAGE}_done.json" "s3://rocketride-benchmark-data/ansh/parity-p1/$REL/chain_${STAGE}_done.json" --only-show-errors
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE $1"
}
up() { aws s3 cp "$D/$1" "s3://rocketride-benchmark-data/ansh/parity-p1/$REL/$1" --only-show-errors; }
for c in rr li li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' present" >&2; exit 3; }; done
case "$STAGE" in
  p1b)
    docker image inspect rr:p1-tikafix >/dev/null 2>&1 || { echo "REFUSED: rr:p1-tikafix absent" >&2; exit 5; }
    leg p1b_base_a rr:patched "$S384"; BA="$LAST"
    leg p1b_fix_a rr:p1-tikafix "$S384"; FA="$LAST"
    CORR=1
    if [ -n "$BA" ] && [ -n "$FA" ]; then "$PY" working/scripts/p1_gates.py correctness "$D" "$BA" "$FA"; CORR=$?; up p1b_correctness.json; fi
    bash working/scripts/p1_engine_tika.sh "$D" "$H" rr:patched p1b_smoke_base
    bash working/scripts/p1_engine_tika.sh "$D" "$H" rr:p1-tikafix p1b_smoke_fix
    "$PY" working/scripts/p1_gates.py smoke "$D" p1b_smoke_base p1b_smoke_fix; SMOKE=$?; up p1b_smoke_gate.json
    leg p1b_base_b rr:patched "$S384"
    leg p1b_fix_b rr:p1-tikafix "$S384"
    if [ "$CORR" = 0 ] && [ "$SMOKE" = 0 ]; then
      leg p1b_base_full rr:patched "$S9975" texts
      leg p1b_fix_full rr:p1-tikafix "$S9975" texts
    else
      echo "FULL RUNS NOT RUN: correctness rc=$CORR smoke rc=$SMOKE (both gates must pass)"; R+=("p1b_full:NOT_RUN_gates")
    fi
    ;;
  p1c)
    docker image inspect rr:p1-pdfium >/dev/null 2>&1 || { echo "REFUSED: rr:p1-pdfium absent" >&2; exit 5; }
    # correctness first: the full runs decide adoptability (texts captured); they double as the full runs
    leg p1c_hyb_full rr:p1-pdfium "$S9975" texts hybrid
    leg p1c_pure_full rr:p1-pdfium "$S9975" texts pure
    # then the 384 ABAB: P1-B fixed Tika vs HYBRID vs PURE, two runs each
    leg p1c_fix_a rr:p1-tikafix "$S384"
    leg p1c_hyb_a rr:p1-pdfium "$S384" - hybrid
    leg p1c_pure_a rr:p1-pdfium "$S384" - pure
    leg p1c_fix_b rr:p1-tikafix "$S384"
    leg p1c_hyb_b rr:p1-pdfium "$S384" - hybrid
    leg p1c_pure_b rr:p1-pdfium "$S384" - pure
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
