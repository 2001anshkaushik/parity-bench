#!/usr/bin/env bash
# p7_chain.sh — P7 on the box (preregistration.json), one workload at a time. Leg mechanics are P6's (p6_chain.sh): stamped
# detect copies, the percore and 1 Hz memory samplers per leg, session facts, append-only S3 uploads. rr:p5-infer is USED,
# never rebuilt; no image is built.
#
#   bash working/scripts/p7_chain.sh <campaign_dir_abs> <expect_head> control
#       the gate-control target (not a measured leg): p7ctl_cap (rr:patched-video, T=4, K=1, the control manifest's one
#       video, --keep-detections)
#   bash working/scripts/p7_chain.sh <campaign_dir_abs> <expect_head> run
#       refuses unless the latest gate_controls record says all_pass. Budget P7_DEADLINE_EPOCH = the first leg + 10,800 s.
#       P7-B TIER 1: two ABAB rounds, each after the canary: p7b_can_<r> p7b_stock_<r> p7b_p5_<r> (K=3, T=4, the Tier 1
#             manifest: IN1002.avi, TS3010a.avi, IN1009.avi; --keep-detections); then G_tier2
#       P7-B TIER 2 (only if G_tier2 fires): two ABAB rounds, each after the canary: p7t2_stock_b<NN> p7t2_p5_b<NN> for the
#             P6-B blocks 06 and 10 — each a fresh container, its one-time start warm (the P6-B start manifest, 16 warm
#             sends at concurrency 16, excluded) then the block (the P6-B block manifest, 2 warm sends at 2, K=16,
#             --keep-detections)
#       P7-C: p7c_can_c2 p7c_p5t16_2 [G_correct_C2, HARD for P7-C] p7c_lit16_2 (P6-C's cells, round 2)
#       after every leg: G_d0 (exit 9), G_cell (exit 11), G_warm where a warm set is declared (exit 11), G_detcap where
#       detections are kept (exit 11); G_memstat after the first leg (exit 10); G_canary after every canary (exit 11).
set -uo pipefail
echo "p7_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir_abs> <expect_head> control|run" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"
case "$D" in /*) ;; *) echo "campaign dir must be absolute" >&2; exit 2;; esac
TREE="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$TREE" || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: worktree at $HAVE, caller expects $H" >&2; exit 2; }
PY="$HOME/.venv/bin/python"
"$PY" -c 'import psutil' || { echo "REFUSED: $PY cannot import psutil" >&2; exit 2; }
VMAN="$HOME/parity-bench-video/working/video/ami_video_manifest.jsonl"
[ -f "$VMAN" ] || { echo "REFUSED: AMI manifest $VMAN absent" >&2; exit 2; }
MAN="$D/p7_manifests"; P6M="$TREE/working/results/parity_p6_20260925T175225Z/p6b_manifests"
for f in "$MAN/tier1.jsonl" "$MAN/control.jsonl" "$P6M/start.jsonl" "$P6M/block_06.jsonl" "$P6M/block_10.jsonl"; do [ -f "$f" ] || { echo "REFUSED: manifest $f absent" >&2; exit 2; }; done
P5ID=sha256:b42c03b69f1749049d3a2e6334890347a22621e8d1adb0a8984780eab866d6bd
[ "$(docker image inspect -f '{{.Id}}' rr:p5-infer 2>/dev/null)" = "$P5ID" ] || { echo "REFUSED: rr:p5-infer is not P5's image $P5ID (never rebuilt)" >&2; exit 2; }
FR="$HOME/p3b_frames_parity_p3_20260925T035027Z"; FMAN="$TREE/working/results/parity_p3_20260925T035027Z/p3b_frames_manifest.json"
CANV=v00_EN2001a; RRW=/opt/rocketride/engine/cache/models/rfdetr
S3="s3://rocketride-benchmark-data/ansh/parity-p7/$REL"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE  manifest $(sha256sum "$VMAN" | cut -c1-16)"
for img in rr:patched rr:patched-video li:video rr:p5-infer; do echo "image $img $(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null)"; done
R=(); LAST=""; FIRSTDONE=0
envargs() { echo "-e OMP_NUM_THREADS=$1 -e MKL_NUM_THREADS=$1 -e OPENBLAS_NUM_THREADS=$1 -e VECLIB_MAXIMUM_THREADS=$1 -e NUMEXPR_NUM_THREADS=$1 -e TORCH_NUM_THREADS=$1"; }
up() { local dest="$S3/$1/"; aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists — not uploading over it"; return 1; }; aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"; }
up1() { aws s3 ls "$S3/$1" >/dev/null 2>&1 || aws s3 cp "$D/$1" "$S3/$1" --only-show-errors; }
upgates() { for f in "$D"/gates/*.json; do [ -f "$f" ] && up1 "gates/$(basename "$f")"; done; }
past() { [ -n "${P7_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge "$P7_DEADLINE_EPOCH" ]; }
g() { "$PY" working/scripts/p7_gates.py "$@"; }
imgid() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null; }
sess_open() { cat /proc/stat | head -1 > "$1/procstat_open.txt"; cat /proc/sys/kernel/random/boot_id > "$1/boot_id.txt"; grep -m1 "model name" /proc/cpuinfo > "$1/cpu_model.txt"; grep -m1 microcode /proc/cpuinfo > "$1/microcode.txt"; grep MHz /proc/cpuinfo > "$1/mhz_open.txt"; }
sess_close() { cat /proc/stat | head -1 > "$1/procstat_close.txt"; grep MHz /proc/cpuinfo > "$1/mhz_close.txt"; }
stop_all() { docker rm -f rr li_bal_0 >/dev/null 2>&1; }

if [ "$STAGE" = run ]; then
  CTL="$(ls "$D"/gate_controls.json "$D"/gate_controls_run*.json 2>/dev/null | sort -V | tail -1)"
  [ -n "$CTL" ] || { echo "REFUSED: no gate_controls record in $D (the GATE CONTROLS rule)"; exit 12; }
  "$PY" -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("all_pass") is True else 1)' "$CTL" || { echo "REFUSED: $CTL does not say all_pass"; exit 12; }
  echo "gate controls: $(basename "$CTL") all_pass"
fi
"$PY" - "$D/chain_p7_${STAGE}_start.json" "$HAVE" <<'PYSTART' || { echo "REFUSED: chain_p7_${STAGE}_start.json exists (one run per stage)"; exit 3; }
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video", "rr:p5-infer")}
json.dump({"stage_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "head": sys.argv[2],
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(), "image_ids_at_start": ids},
          open(sys.argv[1], "x"), indent=1)
PYSTART
up1 "chain_p7_${STAGE}_start.json"

finish() {
  for img in rr:patched rr:patched-video li:video rr:p5-infer; do echo "image $img $(imgid "$img")"; done
  "$PY" - "$D/chain_p7_${STAGE}_done.json" "$1" "${R[*]}" "${P7_DEADLINE_EPOCH:-}" <<'PYDONE'
import json, subprocess, sys, time
ids = {i: subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", i], capture_output=True, text=True).stdout.strip()
       for i in ("rr:patched", "rr:patched-video", "li:video", "rr:p5-infer")}
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
           "outcome": sys.argv[2], "legs": sys.argv[3].split(), "deadline_epoch": sys.argv[4] or None,
           "image_ids_at_end": ids}, open(sys.argv[1], "x"), indent=1)
PYDONE
  up1 "chain_p7_${STAGE}_done.json"; upgates
  echo "CHAIN RESULTS: ${R[*]}"; echo "CHAIN_DONE p7 $STAGE $1"
}
subdone() {  # subdone <file>: the legs so far, for the analyser
  "$PY" -c 'import json,sys; json.dump({"legs": sys.argv[2].split()}, open(sys.argv[1], "x"), indent=1)' "$D/$1" "${R[*]}"; up1 "$1"
}

# ---------------------------------------------------------------- the canary (P3-B bare microbenchmark, rr:patched-video)
canary() {  # canary <name>
  local name="$1" try L C=p7_canary MPID rc
  past && { echo "!! $name NOT RUN: budget"; R+=("${name}:NOT_RUN_budget"); return 1; }
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"; [ -e "$L" ] && continue
    g alone || { R+=("${name}${try}:NOT_ALONE"); return 1; }
    mkdir -p "$L"; chmod 0777 "$L"
    echo "===== CANARY ${name}${try} $(date -u +%H:%M:%SZ) ====="
    docker ps -a --format '{{.Names}} {{.Status}}' > "$L/containers_at_start.txt"
    sess_open "$L"
    docker run -d --name "$C" --network none --memory 16g $(envargs 4) -v "$FR/$CANV:/frames/$CANV:ro" -v "$TREE/working/video/p3b:/x:ro" -v "$L:/out" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine rr:patched-video /x/p3b_bench.py --frames /frames --weights-dir "$RRW" --out /out/bench.json >/dev/null || { R+=("${name}${try}:rc=4"); continue; }
    "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
    MPID=$!
    rc="$(docker wait "$C")"
    touch "$L/.leg_done"; wait "$MPID" 2>/dev/null
    docker logs "$C" > "$L/container_log.txt" 2>&1; docker rm "$C" >/dev/null 2>&1
    sess_close "$L"
    grep '^P3B_BENCH ' "$L/container_log.txt" | tail -1
    up "${name}${try}"
    if [ "$rc" = 0 ] && [ -f "$L/bench.json" ]; then
      g canary "$D" "${name}${try}" "$FMAN" "$CANV"; local cg=$?; upgates
      [ "$cg" = 0 ] || { R+=("G_canary_${name}${try}:FAIL"); stop_all; finish "STOPPED: the canary did not run on the manifest's frames"; exit 11; }
      R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0
    fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times"; return 1
}

# ---------------------------------------------------------------- container start / stop (fresh per leg)
start_c() {  # start_c <stock|p5|li> <T> <set|unset> -> sets C, IMG; rc 0 ready
  local fl="$1" TT="$2" em="$3" ENV rc=0
  ENV=$([ "$em" = unset ] && echo "" || envargs "$TT")
  if [ "$fl" = li ]; then
    C=li_bal_0; IMG=li:video
    docker run -d --name li_bal_0 --memory 7g $ENV -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh li:video -c "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port 8802 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null || rc=4
    [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh li install li_bal_0 || rc=6; }
    [ "$rc" = 0 ] && { docker restart li_bal_0 >/dev/null || rc=6; }
    [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm li --port 8802 --workers 1 --container li_bal_0 --deadline 1200 || rc=5; }
  else
    C=rr; IMG=$([ "$fl" = p5 ] && echo rr:p5-infer || echo rr:patched-video)
    docker run -d --name rr --memory 58g $ENV --log-opt max-size=200m --network host "$IMG" >/dev/null || rc=4
    [ "$rc" = 0 ] && { docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/ || rc=6; }
    if [ "$fl" = p5 ]; then [ "$rc" = 0 ] && { bash working/scripts/p5_stamp.sh install rr || rc=6; }
    else [ "$rc" = 0 ] && { bash working/scripts/p1_stamp.sh rr install rr || rc=6; }; fi
    [ "$rc" = 0 ] && { docker restart rr >/dev/null || rc=6; }
    [ "$rc" = 0 ] && { "$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr || rc=5; }
  fi
  return $rc
}

# drive <L> <fl> <K> <n> <T> <set|unset> <warm "S,C"|-> <manifest> <cap 0|1> <label>: one driver run into $L on the running $C
drive() {
  local L="$1" fl="$2" K="$3" n="$4" TT="$5" em="$6" wf="$7" man="$8" cap="$9" lab="${10}" SPID MPID rc WARG="" CAPARG="" RTE
  [ "$wf" != "-" ] && WARG="--warm-sends ${wf%,*} --warm-concurrency ${wf#*,}"
  [ "$cap" = 1 ] && CAPARG="--keep-detections"
  RTE=$([ "$em" = unset ] && echo unset || echo "$TT")
  docker inspect -f '{{.Image}}' "$C" > "$L/container_image_id.txt"; cp "$man" "$L/leg_manifest.jsonl"
  sess_open "$L"
  PYTHONPATH="$TREE/working" "$PY" -m harness.percore_sampler --cpus 0-31 --out "$L/percore.jsonl" --duration 21600 --until "$L/.leg_done" > "$L/percore_summary.txt" 2>&1 &
  SPID=$!
  "$PY" working/harness/memstat_sampler.py --container "$C" --out "$L/memstat.jsonl" --until "$L/.leg_done" > "$L/memstat_stdout.txt" 2>&1 &
  MPID=$!
  unset P1_SYNC_DIR
  if [ "$fl" = li ]; then
    "$PY" working/video/driver_video.py --arm llamaindex --leg blast --n "$n" --blast-concurrency "$K" --li-ports 8802 --li-containers li_bal_0 --manifest "$man" $WARG --image-lineage "li:video sha256:0a52afcb ($lab, ONE instance, K=$K, T=$TT)" --out-dir "$L" > "$L/driver.log" 2>&1
  else
    P0_ONTOKEN=1 "$PY" working/video/driver_video.py --arm rocketride --posture parity --tokens 1 --leg blast --n "$n" --blast-concurrency "$K" --rr-threads-env "$RTE" --manifest "$man" $WARG $CAPARG --image-lineage "$IMG $(imgid "$IMG" | cut -c1-19) ($lab, 1 token, K=$K, T=$TT env $em)" --out-dir "$L" > "$L/driver.log" 2>&1
  fi
  rc=$?
  sess_close "$L"
  touch "$L/.leg_done"; wait "$SPID" 2>/dev/null; wait "$MPID" 2>/dev/null
  if [ "$fl" = p5 ]; then bash working/scripts/p5_stamp.sh collect "$C" "$L"; else bash working/scripts/p1_stamp.sh "$([ "$fl" = li ] && echo li || echo rr)" collect "$C" "$L"; fi
  tail -3 "$L/driver.log" 2>/dev/null
  if [ "$rc" != 0 ]; then
    local nrec
    nrec="$("$PY" -c 'import json,glob,sys; f=sorted(glob.glob(sys.argv[1]+"/records_*.jsonl")); e=glob.glob(sys.argv[1]+"/export_*.json"); print(len({json.loads(x)["video"] for x in open(f[0]) if x.strip() and json.loads(x).get("role")=="measured"}) if f and e else 0)' "$L" 2>/dev/null || echo 0)"
    [ "$nrec" = "$n" ] && { echo "$(basename "$L"): driver rc=$rc but all $n videos recorded -> DEGRADED-with-all-rows, KEPT"; return 99; }
  fi
  return $rc
}

# ---------------------------------------------------------------- a leg in a fresh container
# leg <name> <stock|p5|li> <K> <n> <T> <set|unset> <warm "S,C"|-> <manifest> <cap 0|1>
leg() {
  local name="$1" fl="$2" K="$3" n="$4" TT="$5" em="$6" wf="$7" man="$8" cap="$9" try L rc
  LAST=""
  if past; then echo "!! $name NOT RUN: the P7 budget has passed"; R+=("${name}:NOT_RUN_budget"); return 1; fi
  for try in "" _r1 _r2; do
    L="$D/${name}${try}"
    [ -e "$L" ] && { echo "REFUSED: $L exists (append-only)"; continue; }
    g alone || { R+=("${name}${try}:NOT_ALONE"); docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'; return 1; }
    mkdir -p "$L"
    echo "===== LEG ${name}${try} ($fl K=$K n=$n T=$TT env=$em warm=$wf cap=$cap manifest=$(basename "$man")) $(date -u +%H:%M:%SZ) ====="
    start_c "$fl" "$TT" "$em"; rc=$?
    [ "$rc" = 0 ] && { drive "$L" "$fl" "$K" "$n" "$TT" "$em" "$wf" "$man" "$cap" "P7 $name"; rc=$?; docker logs "$C" > "$L/dockerlog_$C.txt" 2>&1; }
    docker stop rr li_bal_0 >/dev/null 2>&1; docker rm rr li_bal_0 >/dev/null 2>&1
    up "${name}${try}"
    if [ -f "$L/MANDATE_VIOLATION.json" ]; then R+=("${name}${try}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in ${name}${try}"; exit 9; fi
    if [ "$rc" = 99 ]; then R+=("${name}${try}:DEGRADED_all_rows"); LAST="${name}${try}"; return 0; fi
    if [ "$rc" = 0 ]; then R+=("${name}${try}:rc=0"); LAST="${name}${try}"; return 0; fi
    R+=("${name}${try}:rc=$rc")
  done
  echo "!! $name failed three times — recorded FAILED, chain continues"; return 1
}

after() {  # after <leg> <stock|p5|li> <K> <n> <T> <set|unset> <warm "S,C"|-> <cap 0|1>
  local L="$1" fl="$2" K="$3" n="$4" TT="$5" em="$6" wf="$7" cap="$8" IMG
  IMG=$(imgid "$([ "$fl" = p5 ] && echo rr:p5-infer || ([ "$fl" = li ] && echo li:video || echo rr:patched-video))")
  g d0 "$D" "$L" "$([ "$fl" = li ] && echo li || echo rr)"; local d=$?
  g cell "$D" "$L" "$fl" "$K" "$TT" "$n" "$IMG" "$([ "$em" = unset ] && echo unset || echo set)"; local c=$?
  local w=0; [ "$wf" != "-" ] && { g warm "$D" "$L" "${wf%,*}" "${wf#*,}"; w=$?; }
  local k=0; [ "$cap" = 1 ] && { g detcap "$D" "$L"; k=$?; }
  upgates
  [ "$d" = 0 ] || { R+=("G_d0_${L}:FAIL(rc=$d)"); stop_all; finish "STOPPED: G_d0 failed on $L"; exit 9; }
  [ "$c" = 0 ] || { R+=("G_cell_${L}:FAIL(rc=$c)"); stop_all; finish "STOPPED: G_cell failed on $L"; exit 11; }
  [ "$w" = 0 ] || { R+=("G_warm_${L}:FAIL(rc=$w)"); stop_all; finish "STOPPED: G_warm failed on $L"; exit 11; }
  [ "$k" = 0 ] || { R+=("G_detcap_${L}:FAIL(rc=$k)"); stop_all; finish "STOPPED: G_detcap failed on $L"; exit 11; }
  if [ "$FIRSTDONE" = 0 ]; then
    FIRSTDONE=1
    g memstat "$D" "$L" || { upgates; R+=("G_memstat:FAIL"); finish "STOPPED: G_memstat (the first leg's memory sampler wrote nothing)"; exit 10; }
    upgates
  fi
}
cellrun() { leg "$@" && after "$LAST" "$2" "$3" "$4" "$5" "$6" "$7" "$9"; }   # cellrun <name> <fl> <K> <n> <T> <set|unset> <warm> <manifest> <cap>

# ---------------------------------------------------------------- P7-B Tier 2: one P6-B block in a fresh container
t2leg() {  # t2leg <name> <stock|p5> <block NN> <n>
  local name="$1" fl="$2" b="$3" n="$4" L W rc
  LAST=""
  if past; then echo "!! $name NOT RUN: the P7 budget has passed"; R+=("${name}:NOT_RUN_budget"); return 1; fi
  L="$D/$name"; W="$D/${name}_startwarm"
  { [ -e "$L" ] || [ -e "$W" ]; } && { echo "REFUSED: $L exists"; return 1; }
  g alone || { R+=("${name}:NOT_ALONE"); return 1; }
  mkdir -p "$L" "$W"
  echo "===== TIER 2 $name ($fl, P6-B block $b, K=16, T=4) $(date -u +%H:%M:%SZ) ====="
  start_c "$fl" 4 set; rc=$?
  if [ "$rc" = 0 ]; then
    drive "$W" "$fl" 16 1 4 set 16,16 "$P6M/start.jsonl" 0 "P7 $name start warm"; rc=$?
    if [ "$rc" = 0 ]; then drive "$L" "$fl" 16 "$n" 4 set 2,2 "$P6M/block_$b.jsonl" 1 "P7 $name"; rc=$?; else echo "!! $name: start warm failed (rc=$rc)"; fi
    docker logs "$C" > "$L/dockerlog_$C.txt" 2>&1
  fi
  docker stop rr >/dev/null 2>&1; docker rm rr >/dev/null 2>&1
  up "${name}_startwarm"; up "$name"
  if [ -f "$L/MANDATE_VIOLATION.json" ] || [ -f "$W/MANDATE_VIOLATION.json" ]; then R+=("${name}:MANDATE_VIOLATION"); finish "STOPPED: mandate violation in $name"; exit 9; fi
  g d0 "$D" "${name}_startwarm" rr; local dw=$?
  g warm "$D" "${name}_startwarm" 16 16; local ww=$?
  upgates
  [ "$dw" = 0 ] || { R+=("G_d0_${name}_startwarm:FAIL"); finish "STOPPED: G_d0 failed on ${name}_startwarm"; exit 9; }
  [ "$ww" = 0 ] || { R+=("G_warm_${name}_startwarm:FAIL"); finish "STOPPED: G_warm failed on ${name}_startwarm"; exit 11; }
  if [ "$rc" = 0 ] || [ "$rc" = 99 ]; then
    R+=("${name}:$([ "$rc" = 0 ] && echo rc=0 || echo DEGRADED_all_rows)"); LAST="$name"
    after "$name" "$fl" 16 "$n" 4 set 2,2 1
    return 0
  fi
  R+=("${name}:rc=$rc"); return 1
}

case "$STAGE" in
  control)
    leg p7ctl_cap stock 1 1 4 set - "$MAN/control.jsonl" 1 || { finish "control leg p7ctl_cap FAILED"; exit 4; }
    finish "control target complete (a gate-control target, not a measured leg)"
    ;;
  run)
    export P7_DEADLINE_EPOCH="$(( $(date +%s) + 10800 ))"
    echo "first leg starts $(date -u +%H:%M:%SZ); deadline $(date -u -d "@$P7_DEADLINE_EPOCH" +%H:%M:%SZ) (epoch $P7_DEADLINE_EPOCH)"
    # ---------------- P7-B Tier 1
    for r in 1 2; do
      canary "p7b_can_$r"
      cellrun "p7b_stock_$r" stock 3 3 4 set - "$MAN/tier1.jsonl" 1
      cellrun "p7b_p5_$r" p5 3 3 4 set - "$MAN/tier1.jsonl" 1
    done
    subdone chain_p7_t1_done.json
    g tier "$D"; tg=$?; upgates; R+=("G_tier2:rc=$tg")
    # ---------------- P7-B Tier 2 (only if Tier 1 reads CONDITION-DEPENDENT)
    if [ "$tg" = 0 ]; then
      r=1
      for b in 06 10; do
        nb="$("$PY" -c 'import json,sys; print(sum(1 for l in open(sys.argv[1]) if l.strip() and json.loads(l).get("role")=="measured"))' "$P6M/block_$b.jsonl")"
        canary "p7t2_can_$r"
        t2leg "p7t2_stock_b$b" stock "$b" "$nb"
        t2leg "p7t2_p5_b$b" p5 "$b" "$nb"
        r=$((r + 1))
      done
    else echo "P7-B TIER 2 NOT RUN: G_tier2 did not fire (rc=$tg)"; R+=("P7B_T2:NOT_RUN_gate"); fi
    subdone chain_p7_b_done.json
    # ---------------- P7-C (P6-C round 2)
    canary p7c_can_c2
    cellrun p7c_p5t16_2 p5 16 16 16 unset - "$VMAN" 0
    P16T="$(ls -d "$D"/p7c_p5t16_2* 2>/dev/null | head -1)"
    cc=1
    if [ -n "$P16T" ]; then
      g correct "$D" G_correct_C2 "$(basename "$P16T")" "$TREE/working/results/parity_p0_20260923T083031Z/v1_rr_def_a"; cc=$?; upgates
      [ "$cc" = 0 ] && R+=("G_correct_C2:PASS") || R+=("G_correct_C2:FAIL(rc=$cc)")
    fi
    if [ "$cc" = 0 ]; then cellrun p7c_lit16_2 li 16 16 16 set - "$VMAN" 0
    else echo "P7-C: the T=16 leg absent or OUTPUT-CHANGING against the out-of-box reference — the LlamaIndex leg NOT RUN (no speed reading)"; R+=("p7c_lit16_2:NOT_RUN_correctness"); fi
    subdone chain_p7_c_done.json
    finish "complete"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
