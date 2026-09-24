#!/usr/bin/env bash
# p2_master.sh — everything P2 runs on the box, in the pre-registered order, at ONE head, one workload at a time,
# with the HARD DEPENDENCY GATES of preregistration.json (register 55: P1's master ran P1-C on an image whose
# build check had failed). Every gate's exit status is checked explicitly and recorded as one JSON line in
# master_gates.jsonl (a snapshot is uploaded as a NEW object after every gate).
#
#   bash working/scripts/p2_master.sh <campaign_dir_abs> <expect_head>
#
#   1 P2-A smoke (p2_docs_chain a_smoke)          -> G_memstat (exit 10 stops ALL), G_mandate (exit 9 stops ALL), G_smoke_A
#   2 rr:p2-pdfium build (p2_pdfium_build.sh)      -> G_build_C: non-zero = P2-C smoke AND full NOT RUN
#     P2-C smoke (p2_docs_chain c_smoke)          -> G_node_C (exit 8 = P2-C stops), G_smoke_C (fired variants)
#   3 P2-B video (p2_video_chain b)                -> G_manip_B (exit 11 = P2-B stops; independent stages continue)
#   4 P2-A full, only if G_smoke_A fired
#   5 P2-C full, only for fired variants (comparator: p2a_rr_full if it ran, else p2c_fix_full first)
# Budget: 8 hours from the start of the first leg (P2_DEADLINE_EPOCH, recorded before leg 1). The chains check it
# before every leg; the master checks it before every stage. A stage not started past it is NOT_RUN_budget.
set -uo pipefail
echo "p2_master.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head>" >&2; exit 2; }
D="$1"; H="$2"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || exit 2
S3="s3://rocketride-benchmark-data/ansh/parity-p2/$REL"
PY="$HOME/.venv/bin/python"
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
[ -e "$D/master_gates.jsonl" ] && { echo "REFUSED: $D/master_gates.jsonl exists (append-only; one master per campaign)" >&2; exit 3; }
SNAP=0
# rec <gate> <status> <exit_code> <detail>
rec() {
  "$PY" - "$D/master_gates.jsonl" "$1" "$2" "$3" "$4" <<'PYREC'
import json, sys, time
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gate": sys.argv[2],
                        "status": sys.argv[3], "exit_code": sys.argv[4], "detail": sys.argv[5]}) + "\n")
PYREC
  SNAP=$((SNAP + 1))
  aws s3 cp "$D/master_gates.jsonl" "$S3/master_gates_snap$(printf %02d "$SNAP").jsonl" --only-show-errors || echo "!! gate snapshot upload failed"
  echo "GATE $1: $2 (exit $3) $4"
}
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix rr:p2-pdfium; do echo "$i $(docker image inspect -f '{{.Id}}' "$i" 2>/dev/null)"; done; }
PROT0="$(docker image inspect -f '{{.Id}}' rr:patched rr:patched-video 2>/dev/null | tr '\n' ' ')"
echo "master start $(date -u +%FT%TZ) head $HAVE boot $(cat /proc/sys/kernel/random/boot_id)"; ids
past() { [ "$(date +%s)" -ge "$P2_DEADLINE_EPOCH" ]; }
stop_all() { rec MASTER STOPPED "$1" "$2"; finish "STOPPED: $2"; exit "$1"; }
finish() {
  PROT1="$(docker image inspect -f '{{.Id}}' rr:patched rr:patched-video 2>/dev/null | tr '\n' ' ')"
  rec PROTECTED_IDS "$([ "$PROT0" = "$PROT1" ] && echo UNCHANGED || echo CHANGED)" 0 "start: $PROT0 end: $PROT1"
  ids
  "$PY" - "$D/master_done.json" "$1" "$PROT0" "$PROT1" <<'PYD'
import json, sys, time
json.dump({"master_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(), "outcome": sys.argv[2],
           "protected_ids_start": sys.argv[3].split(), "protected_ids_end": sys.argv[4].split(),
           "gates": [json.loads(x) for x in open(sys.argv[1].replace("master_done.json", "master_gates.jsonl"))]},
          open(sys.argv[1], "x"), indent=1)
PYD
  aws s3 cp "$D/master_done.json" "$S3/master_done.json" --only-show-errors
  echo "CHAIN_DONE master $1 $(date -u +%FT%TZ)"
}

export P2_DEADLINE_EPOCH=$(( $(date +%s) + 28800 ))
rec BUDGET SET 0 "8 h from the first leg: deadline $(date -u -d @"$P2_DEADLINE_EPOCH" +%FT%TZ) (epoch $P2_DEADLINE_EPOCH)"

# ---- 1 P2-A smoke
bash working/scripts/p2_docs_chain.sh "$D" "$H" a_smoke; RC=$?
rec A_SMOKE_CHAIN "$([ $RC = 0 ] && echo complete || echo "rc $RC")" "$RC" "p2_docs_chain a_smoke"
[ "$RC" = 9 ] && stop_all 9 "G_mandate: a D0 violation in P2-A smoke"
[ "$RC" = 10 ] && stop_all 10 "G_memstat: the first leg's memory sampler wrote nothing"
"$PY" working/scripts/p2_gates.py a_smoke "$D"; GA=$?
aws s3 cp "$D/gates/G_smoke_A.json" "$S3/gates/G_smoke_A.json" --only-show-errors 2>/dev/null
rec G_smoke_A "$(case $GA in 0) echo FIRED;; 1) echo "NOT FIRED";; *) echo "NOT EVALUABLE";; esac)" "$GA" "gates/G_smoke_A.json"

# ---- 2 P2-C build + smoke
CB=1; CS=1; FIRED=""
if past; then rec G_build_C NOT_RUN_budget 0 "budget passed before the build"
else
  bash working/scripts/p2_pdfium_build.sh "$D"; CB=$?
  [ -f "$D/p2c_build.json" ] && aws s3 cp "$D/p2c_build.json" "$S3/p2c_build.json" --only-show-errors
  rec G_build_C "$([ $CB = 0 ] && echo PASS || echo "FAIL — P2-C smoke and full NOT RUN")" "$CB" "p2_pdfium_build.sh; p2c_build.json"
  if [ "$CB" = 0 ]; then
    bash working/scripts/p2_docs_chain.sh "$D" "$H" c_smoke; CS=$?
    rec C_SMOKE_CHAIN "$([ $CS = 0 ] && echo complete || echo "rc $CS")" "$CS" "p2_docs_chain c_smoke"
    [ "$CS" = 9 ] && stop_all 9 "G_mandate: a D0 violation in P2-C smoke"
    if [ "$CS" = 8 ]; then
      rec G_node_C FAIL 8 "the prototype node produced no text — P2-C stops (smoke gate and full runs NOT RUN)"
    else
      rec G_node_C PASS 0 "gates/G_node_C_hybrid.json, gates/G_node_C_pure.json"
      "$PY" working/scripts/p2_gates.py c_smoke "$D"; GC=$?
      aws s3 cp "$D/gates/G_smoke_C.json" "$S3/gates/G_smoke_C.json" --only-show-errors 2>/dev/null
      if [ "$GC" = 0 ]; then
        FIRED="$("$PY" -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["fired_variants"]))' "$D/gates/G_smoke_C.json")"
        rec G_smoke_C EVALUATED 0 "fired variants: [${FIRED}]"
      else
        rec G_smoke_C "NOT EVALUABLE" "$GC" "no variant's full run is queued"
      fi
    fi
  fi
fi

# ---- 3 P2-B video (independent of P2-A and P2-C)
if past; then rec P2_B NOT_RUN_budget 0 "budget passed before P2-B"
else
  bash working/scripts/p2_video_chain.sh "$D" "$H" b; VB=$?
  rec B_CHAIN "$([ $VB = 0 ] && echo complete || echo "rc $VB")" "$VB" "p2_video_chain b"
  [ "$VB" = 9 ] && stop_all 9 "G_mandate: a D0 violation in P2-B"
  [ "$VB" = 10 ] && stop_all 10 "G_memstat: the first video leg's memory sampler wrote nothing"
  [ "$VB" = 11 ] && rec G_manip_B FAIL 11 "P2-B stopped: a read-back was not the cell described (gates/G_manip_B_*.json)"
fi

# ---- 4 P2-A full
if [ "$GA" != 0 ]; then rec A_FULL "NOT RUN (G_smoke_A not fired)" 0 "gates/G_smoke_A.json"
elif past; then rec A_FULL NOT_RUN_budget 0 "budget passed before the P2-A full run"
else
  bash working/scripts/p2_docs_chain.sh "$D" "$H" a_full; AF=$?
  rec A_FULL_CHAIN "$([ $AF = 0 ] && echo complete || echo "rc $AF")" "$AF" "p2_docs_chain a_full"
  [ "$AF" = 9 ] && stop_all 9 "G_mandate: a D0 violation in the P2-A full run"
fi

# ---- 5 P2-C full
if [ "$CB" != 0 ]; then rec C_FULL "NOT RUN (G_build_C failed)" 0 ""
elif [ "$CS" = 8 ]; then rec C_FULL "NOT RUN (G_node_C failed)" 0 ""
elif [ -z "$FIRED" ]; then rec C_FULL "NOT RUN (no variant's smoke gate fired)" 0 "gates/G_smoke_C.json"
elif past; then rec C_FULL NOT_RUN_budget 0 "budget passed before the P2-C full runs"
else
  COMP=""
  for c in "$D"/p2a_rr_full "$D"/p2a_rr_full_r1 "$D"/p2a_rr_full_r2; do
    if [ -f "$c/texts.jsonl.gz" ] && ls "$c"/leg_*.json >/dev/null 2>&1; then COMP="$(basename "$c")"; break; fi
  done
  rec C_FULL_COMPARATOR "${COMP:-none}" 0 "$([ -n "$COMP" ] && echo "P2-A's RR full leg" || echo "p2c_fix_full runs first")"
  P2C_VARIANTS="$FIRED" P2C_COMPARATOR="$COMP" bash working/scripts/p2_docs_chain.sh "$D" "$H" c_full; CF=$?
  rec C_FULL_CHAIN "$([ $CF = 0 ] && echo complete || echo "rc $CF")" "$CF" "p2_docs_chain c_full, variants [$FIRED]"
  [ "$CF" = 9 ] && stop_all 9 "G_mandate: a D0 violation in the P2-C full runs"
fi
finish "complete"
