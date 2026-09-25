#!/usr/bin/env bash
# p3_master.sh — everything P3 runs on the box, in the pre-registered order, at ONE head, one workload at a time, with
# hard dependency gates (register 55: a failed build, in-image check or correctness gate STOPS what depends on it;
# independent stages continue). Every gate's exit status is recorded in master_gates.jsonl; a snapshot is uploaded as
# a NEW object after every gate.
#
#   bash working/scripts/p3_master.sh <campaign_dir_abs> <expect_head>
#
#   0 G_controls: gate_controls.json must exist with all_pass true (the GATE CONTROLS rule), else REFUSE
#   1 P3-B video discriminator (p3_video_chain.sh)             exit 9 (D0) / 10 (memstat) stop ALL
#   2 P3-C thread-shape smoke (p3_docs_chain c_smoke) -> G_smoke_C (winner shape or none)
#   3 P3-A health smoke (a_health) -> G_health_A; fired -> P3-A full (a_full)
#   4 P3-D: build rr:p3-pdfium (G_build_D; fail = P3-D NOT RUN) -> smoke (d_smoke; G_node_D exit 8 = P3-D stops) -> G_smoke_D
#   5 full runs, only for fired gates, P3-C first (c_full), then P3-D (d_full)
# Budget: 7 hours from the start of the first leg (P3_DEADLINE_EPOCH, recorded before leg 1); chains check it before
# every leg, the master before every stage.
set -uo pipefail
echo "p3_master.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head>" >&2; exit 2; }
D="$1"; H="$2"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || exit 2
S3="s3://rocketride-benchmark-data/ansh/parity-p3/$REL"
PY="$HOME/.venv/bin/python"
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: preregistration.json absent" >&2; exit 5; }
[ -e "$D/master_gates.jsonl" ] && { echo "REFUSED: master_gates.jsonl exists (one master per campaign)" >&2; exit 3; }
CTLF="$(ls "$D"/gate_controls_run*.json 2>/dev/null | sort -V | tail -1)"; [ -n "$CTLF" ] || CTLF="$D/gate_controls.json"
"$PY" -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r.get("all_pass") is True else 1)' "$CTLF" 2>/dev/null \
  || { echo "REFUSED: the latest gate-controls record ($CTLF) is absent or not all_pass — no gate goes on the box without both controls passing" >&2; exit 5; }
export P3B_RR_WEIGHTS=/opt/rocketride/engine/cache/models/rfdetr P3B_LI_WEIGHTS=/opt/rfdetr-cache
SNAP=0
rec() {
  "$PY" - "$D/master_gates.jsonl" "$1" "$2" "$3" "$4" <<'PYREC'
import json, sys, time
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gate": sys.argv[2],
                        "status": sys.argv[3], "exit_code": sys.argv[4], "detail": sys.argv[5]}) + "\n")
PYREC
  SNAP=$((SNAP + 1))
  aws s3 cp "$D/master_gates.jsonl" "$S3/master_gates_snap$(printf %02d "$SNAP").jsonl" --only-show-errors || echo "!! snapshot upload failed"
  echo "GATE $1: $2 (exit $3) $4"
}
upg() { [ -f "$D/gates/$1.json" ] && { aws s3 ls "$S3/gates/$1.json" >/dev/null 2>&1 || aws s3 cp "$D/gates/$1.json" "$S3/gates/$1.json" --only-show-errors; }; }
PROT0="$(docker image inspect -f '{{.Id}}' rr:patched rr:patched-video 2>/dev/null | tr '\n' ' ')"
echo "master start $(date -u +%FT%TZ) head $HAVE boot $(cat /proc/sys/kernel/random/boot_id) protected $PROT0"
past() { [ "$(date +%s)" -ge "$P3_DEADLINE_EPOCH" ]; }
finish() {
  local PROT1; PROT1="$(docker image inspect -f '{{.Id}}' rr:patched rr:patched-video 2>/dev/null | tr '\n' ' ')"
  rec PROTECTED_IDS "$([ "$PROT0" = "$PROT1" ] && echo UNCHANGED || echo CHANGED)" 0 "start: $PROT0 end: $PROT1"
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
stop_all() { rec MASTER STOPPED "$1" "$2"; finish "STOPPED: $2"; exit "$1"; }
chain_rc() { case "$1" in 9) stop_all 9 "G_mandate: a D0 violation in $2";; 10) stop_all 10 "G_memstat: the first leg's sampler wrote nothing in $2";; esac; }

rec G_controls PASS 0 "$(basename "$CTLF") all_pass (the GATE CONTROLS rule)"
export P3_DEADLINE_EPOCH=$(( $(date +%s) + 25200 ))
rec BUDGET SET 0 "7 h from the first leg: deadline $(date -u -d @"$P3_DEADLINE_EPOCH" +%FT%TZ) (epoch $P3_DEADLINE_EPOCH)"

# ---- 1 P3-B
bash working/scripts/p3_video_chain.sh "$D" "$H"; RB=$?
rec B_CHAIN "$([ $RB = 0 ] && echo complete || echo "rc $RB")" "$RB" "p3_video_chain (P3-B)"
chain_rc "$RB" "P3-B"

# ---- 2 P3-C smoke
WIN=""
if past; then rec C_SMOKE NOT_RUN_budget 0 ""
else
  bash working/scripts/p3_docs_chain.sh "$D" "$H" c_smoke; RC=$?
  rec C_SMOKE_CHAIN "$([ $RC = 0 ] && echo complete || echo "rc $RC")" "$RC" "p3_docs_chain c_smoke"
  chain_rc "$RC" "P3-C smoke"
  "$PY" working/scripts/p3_gates.py smoke_c "$D"; GC=$?; upg G_smoke_C
  [ "$GC" = 0 ] && WIN="$("$PY" -c 'import json,sys; w=json.load(open(sys.argv[1])).get("winner"); print(w or "")' "$D/gates/G_smoke_C.json")"
  rec G_smoke_C "$([ "$GC" = 0 ] && { [ -n "$WIN" ] && echo "FIRED (winner vars=$WIN)" || echo "NOT FIRED"; } || echo "NOT EVALUABLE")" "$GC" "gates/G_smoke_C.json"
fi

# ---- 3 P3-A health smoke, then its full runs
GA=1
if past; then rec A_HEALTH NOT_RUN_budget 0 ""
else
  bash working/scripts/p3_docs_chain.sh "$D" "$H" a_health; RA=$?
  rec A_HEALTH_CHAIN "$([ $RA = 0 ] && echo complete || echo "rc $RA")" "$RA" "p3_docs_chain a_health"
  chain_rc "$RA" "P3-A health"
  "$PY" working/scripts/p3_gates.py health_a "$D" working/results/parity_p2_20260924T160106Z/p2a_rr_a working/results/parity_p2_20260924T160106Z/p2a_rr_b; GA=$?; upg G_health_A
  rec G_health_A "$(case $GA in 0) echo FIRED;; 1) echo "NOT FIRED";; *) echo "NOT EVALUABLE";; esac)" "$GA" "gates/G_health_A.json"
  if [ "$GA" = 0 ]; then
    if past; then rec A_FULL NOT_RUN_budget 0 ""
    else
      bash working/scripts/p3_docs_chain.sh "$D" "$H" a_full; RF=$?
      rec A_FULL_CHAIN "$([ $RF = 0 ] && echo complete || echo "rc $RF")" "$RF" "p3_docs_chain a_full"
      chain_rc "$RF" "P3-A full"
    fi
  else
    rec A_FULL "NOT RUN (G_health_A not fired)" 0 "gates/G_health_A.json"
  fi
fi

# ---- 4 P3-D build, smoke
DB=1; DS=1; FIRED=""
if past; then rec G_build_D NOT_RUN_budget 0 ""
else
  bash working/scripts/p2_pdfium_build.sh "$D" rr:p3-pdfium p3d_build.json; DB=$?
  [ -f "$D/p3d_build.json" ] && { aws s3 ls "$S3/p3d_build.json" >/dev/null 2>&1 || aws s3 cp "$D/p3d_build.json" "$S3/p3d_build.json" --only-show-errors; }
  rec G_build_D "$([ $DB = 0 ] && echo PASS || echo "FAIL — P3-D NOT RUN")" "$DB" "p2_pdfium_build.sh rr:p3-pdfium -> p3d_build.json"
  if [ "$DB" = 0 ] && ! past; then
    bash working/scripts/p3_docs_chain.sh "$D" "$H" d_smoke; DS=$?
    rec D_SMOKE_CHAIN "$([ $DS = 0 ] && echo complete || echo "rc $DS")" "$DS" "p3_docs_chain d_smoke"
    chain_rc "$DS" "P3-D smoke"
    if [ "$DS" = 8 ]; then rec G_node_D FAIL 8 "the prototype node produced no text — P3-D stops"
    else
      rec G_node_D PASS 0 "gates/G_node_D_hybrid.json, gates/G_node_D_pure.json"
      "$PY" working/scripts/p3_gates.py smoke_d "$D"; GD=$?; upg G_smoke_D
      [ "$GD" = 0 ] && FIRED="$("$PY" -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["fired_variants"]))' "$D/gates/G_smoke_D.json")"
      rec G_smoke_D "$([ "$GD" = 0 ] && echo EVALUATED || echo "NOT EVALUABLE")" "$GD" "fired variants: [${FIRED}]"
    fi
  elif [ "$DB" = 0 ]; then rec D_SMOKE NOT_RUN_budget 0 ""
  fi
fi

# ---- 5 full runs for fired gates, P3-C first
if [ -z "$WIN" ]; then rec C_FULL "NOT RUN (G_smoke_C: no shape fired)" 0 ""
elif past; then rec C_FULL NOT_RUN_budget 0 ""
else
  P3C_WINNER="$WIN" bash working/scripts/p3_docs_chain.sh "$D" "$H" c_full; CF=$?
  rec C_FULL_CHAIN "$([ $CF = 0 ] && echo complete || echo "rc $CF")" "$CF" "vars=$WIN"
  chain_rc "$CF" "P3-C full"
fi
if [ "$DB" != 0 ]; then rec D_FULL "NOT RUN (G_build_D failed or not run)" 0 ""
elif [ "$DS" = 8 ]; then rec D_FULL "NOT RUN (G_node_D failed)" 0 ""
elif [ -z "$FIRED" ]; then rec D_FULL "NOT RUN (no variant's smoke gate fired)" 0 ""
elif past; then rec D_FULL NOT_RUN_budget 0 ""
else
  P3D_VARIANTS="$FIRED" bash working/scripts/p3_docs_chain.sh "$D" "$H" d_full; DF=$?
  rec D_FULL_CHAIN "$([ $DF = 0 ] && echo complete || echo "rc $DF")" "$DF" "variants [$FIRED]"
  chain_rc "$DF" "P3-D full"
fi
finish complete
