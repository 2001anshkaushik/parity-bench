#!/usr/bin/env bash
# p0_docs_chain.sh — P0 docs legs on the box, one launch per stage, one workload at a time.
#
#   bash working/scripts/p0_docs_chain.sh <campaign_dir> <expect_head> <stage>
#     stage d1    tooling leg, then D1 (overhead ABAB on the 384 slice; the single-instance anchor
#                 block on the 96 slice, both arms interleaved)
#     stage h2h1  H2 (null control C=1 first, then C=32 twice) and H1 (C=32 / C=64 ABAB)
#     stage h2full  the 9,975-document H2 profile — ONLY if the H2 smoke gate fired (the caller
#                 decides from the committed threshold; this script refuses without the gate file)
#
# Launched through working/harness/box.sh launch. Every leg is one fresh container via
# batchsize_docs_run.sh (Ruling A: unconstrained; Ruling C: nothing else on the box), with P0 on:
# D0/G2 read on the measured token, the leg's session record, and — where named — PROFILE stamps
# or the DIAGNOSTIC py-spy profiler. Pre-registration: <campaign_dir>/preregistration.json, landed
# before the first leg; this script refuses without it.
#
# A failed leg is retried at most twice under a new directory (<leg>_r1, <leg>_r2 — results are
# append-only), then recorded as failed and the chain moves on. A leg whose record shows a MANDATE
# VIOLATION (more than one task process or model instance) STOPS the chain: that is the one outcome
# the operating rules say is never worked around.
set -uo pipefail
echo "p0_docs_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <expect_head> <d1|h2h1|h2full>" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent — landed before any leg" >&2; exit 5; }
S384=working/results/batchsize_smoke_20260920T113000Z/slice_docs_n384_w25.json
S96=working/results/batchsize_main_20260920T160920Z/slice_docs_n96_w25.json
S9975=working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json
for s in "$S384" "$S96" "$S9975"; do [ -f "$s" ] || { echo "REFUSED: slice $s absent" >&2; exit 2; }; done
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1 BSZ_P0=1 BSZ_S3_ROOT=parity-p0
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $H"
R=()

violation() {  # $1 = run dir: 0 if any leg json in it records a mandate violation
  "$HOME/.venv/bin/python" - "$1" <<'PYV'
import json, sys, pathlib
for f in pathlib.Path(sys.argv[1]).glob("leg_*.json"):
    m = ((json.loads(f.read_text()).get("p0") or {}).get("mandate") or {})
    if m.get("mandate_violation"):
        print(f"MANDATE VIOLATION in {f}: {m.get('violations')}"); sys.exit(0)
sys.exit(1)
PYV
}

# leg <name> <env...> -- <docs_run args...>
leg() {
  local name="$1"; shift
  local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
  local try dir rc
  for try in "" _r1 _r2; do
    dir="$D/${name}${try}"
    echo "===== LEG ${name}${try} $(date -u +%H:%M:%SZ) ====="
    ( env "${envs[@]}" bash working/scripts/batchsize_docs_run.sh "$1" "$2" "$dir" "" 0 "${name}${try}" "$3" )
    rc=$?
    echo "===== LEG ${name}${try} rc=$rc $(date -u +%H:%M:%SZ) ====="
    if violation "$dir"; then
      R+=("${name}${try}:MANDATE_VIOLATION")
      finish "STOPPED: mandate violation in ${name}${try}"; exit 9
    fi
    [ "$rc" -eq 0 ] && { R+=("${name}${try}:rc=0"); return 0; }
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! ${name} failed three times — recorded as FAILED, chain continues"
  return 1
}

finish() {
  "$HOME/.venv/bin/python" - "$D/chain_${STAGE}_done.json" "$1" "${R[*]}" <<'PYDONE'
import json, sys, time
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split()}, open(sys.argv[1], "x"), indent=1)
PYDONE
  aws s3 cp "$D/chain_${STAGE}_done.json" "s3://rocketride-benchmark-data/ansh/parity-p0/$REL/chain_${STAGE}_done.json" --only-show-errors || echo "!! upload of chain_${STAGE}_done.json failed"
  echo "CHAIN RESULTS: ${R[*]}"
  echo "CHAIN_DONE $1"
}

C32=(BSZ_CONTINUOUS=32); C8=(BSZ_CONTINUOUS=8); C1=(BSZ_CONTINUOUS=1); C64=(BSZ_CONTINUOUS=64)
case "$STAGE" in
  d1)
    # tooling: py-spy + stamps on a short leg, so H2's instrument is proven before H2 relies on it
    leg tool_pyspy "${C32[@]}" BSZ_STAMP=1 BSZ_PYSPY=1 -- rr "$S96" 1
    # D1 overhead, RocketRide, 384 slice, C=32: stamped / unstamped, ABAB, two each
    leg d1_rr_s1 "${C32[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    leg d1_rr_u1 "${C32[@]}"             -- rr "$S384" 1
    leg d1_rr_s2 "${C32[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    leg d1_rr_u2 "${C32[@]}"             -- rr "$S384" 1
    # single-instance anchor block, 96 slice, C=8, both arms interleaved: unstamped/untimed parity
    # legs and PROFILE legs (RocketRide stamps, LlamaIndex timed service), each arm ABAB
    leg an_rr_u1 "${C8[@]}"                              -- rr "$S96" 1
    leg an_li_u1 "${C8[@]}" BSZ_LI_WORKERS=1             -- li "$S96" 1
    leg an_rr_s1 "${C8[@]}" BSZ_STAMP=1                  -- rr "$S96" 1
    leg an_li_t1 "${C8[@]}" BSZ_LI_WORKERS=1 BSZ_LI_TIMED=1 -- li "$S96" 1
    leg an_rr_u2 "${C8[@]}"                              -- rr "$S96" 1
    leg an_li_u2 "${C8[@]}" BSZ_LI_WORKERS=1             -- li "$S96" 1
    leg an_rr_s2 "${C8[@]}" BSZ_STAMP=1                  -- rr "$S96" 1
    leg an_li_t2 "${C8[@]}" BSZ_LI_WORKERS=1 BSZ_LI_TIMED=1 -- li "$S96" 1
    ;;
  h2h1)
    # H2 null control FIRST: one document in flight must show near-zero GIL waiting
    leg h2_null_c1 "${C1[@]}"  BSZ_PYSPY=1 -- rr "$S96" 1
    leg h2_c32_a   "${C32[@]}" BSZ_PYSPY=1 -- rr "$S384" 1
    leg h2_c32_b   "${C32[@]}" BSZ_PYSPY=1 -- rr "$S384" 1
    # H1: C=32 against C=64, stamped (PROFILE), interleaved ABAB
    leg h1_c32_a "${C32[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    leg h1_c64_a "${C64[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    leg h1_c32_b "${C32[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    leg h1_c64_b "${C64[@]}" BSZ_STAMP=1 -- rr "$S384" 1
    ;;
  h2full)
    [ -f "$D/h2_gate_fired.json" ] || { echo "REFUSED: the H2 full run needs $D/h2_gate_fired.json (the smoke gate's committed outcome)" >&2; exit 5; }
    leg h2_full_c32 "${C32[@]}" BSZ_PYSPY=1 -- rr "$S9975" 1
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
finish "complete"
