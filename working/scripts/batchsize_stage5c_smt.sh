#!/usr/bin/env bash
# batchsize_stage5c_smt.sh — S5-C, the SMT probe: is RocketRide's 32-vCPU penalty hyperthreading?
#
#   bash working/scripts/batchsize_stage5c_smt.sh <campaign_dir> <slice_384.json> <expect_head>
#
# HYPOTHESIS (Ansh, 2026-09-21): the engine sizes a pool from the visible CPU count, so on 32 vCPUs
# it activates both hyperthread siblings of each of 16 physical cores and pays more CPU-s per
# document for less work. EVIDENCE: continuous C=32 on the 384 slice went 2.68 -> 2.487 docs/s and
# 5.05 -> 6.47 CPU-s/doc from the 24-core cpuset to 32 unconstrained vCPUs, against a 0.82% floor.
#
# SOURCE, read first and held as a map of what to measure, never the answer (register 1): the task
# pool is threadCount = 64 when use(threads=) is unset (task_engine.py:247, data_conn.py:138) —
# NOT sized from CPUs; pipe work runs on asyncio.to_thread, Python's default executor,
# min(32, os.cpu_count() + 4), and os.cpu_count() IGNORES cpusets on 3.12; Tika runs in a JVM,
# which sizes from availableProcessors() and DOES honour them. So which pool (if any) follows the
# visible CPUs is measured here — every leg snapshots each process's thread count and allowed CPUs.
#
# CELLS, one container lifetime each, continuous C=32 on the 384 slice:
#   (a) unconstrained, all 32 vCPUs — Ruling A's posture         (RocketRide: TWICE, the null control)
#   (b) cpuset 0-23                                               (the Stage 3 posture)
#   (c) one vCPU per physical core, read from lscpu's sibling map (no hyperthread sibling in use)
# and the SAME three cells on LlamaIndex, so an effect shown only on RocketRide is RocketRide's and
# not a property of the box. The discriminating metric is CPU-s/doc: fewer CPUs slow any arm; only a
# sibling effect makes the same work cheaper when siblings are removed.
#
# NULL CONTROL: the two RocketRide cell-(a) runs must agree within the arm's 0.82% floor, or no
# difference between cells means anything and the probe says so.
#
# Cells (b) and (c) bind a cpuset ON PURPOSE: they are S5-C diagnostics outside Ruling A, labelled
# so in every leg (cpuset_declared_for_s5c), and never enter a Stage 4 table.
# Strictly after the envelope: refuses unless <campaign_dir>/envelope_done.json exists.
set -uo pipefail
echo "batchsize_stage5c_smt.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <slice_384.json> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: working/harness/results_prefix.sh is absent from this tree" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: campaign dir $D is not under working/results/ — its S3 prefix mirrors that path" >&2; exit 2; }
S4="${BSZ_STAGE4_DIR:-}"
[ -n "$S4" ] && [ -f "$S4/envelope_done.json" ] || { echo "REFUSED: Stage 5 runs strictly after the envelope — set BSZ_STAGE4_DIR to a campaign dir holding envelope_done.json" >&2; exit 5; }
command -v lscpu >/dev/null 2>&1 || { echo "REFUSED: lscpu is not installed — the sibling map must be READ, never assumed" >&2; exit 5; }
mkdir -p "$D"
[ -e "$D/lscpu_siblings.txt" ] && { echo "REFUSED: $D/lscpu_siblings.txt exists — append-only" >&2; exit 3; }
lscpu -p=CPU,CORE,SOCKET,NODE > "$D/lscpu_siblings.txt"
lscpu > "$D/lscpu_full.txt"
# cell (c): the lowest-numbered CPU of every (socket, core) pair — one hardware thread per core.
ONE_PER_CORE="$(awk -F, '!/^#/ { key=$3","$2; if (!(key in seen) || $1 < seen[key]) seen[key]=$1 } END { for (k in seen) print seen[k] }' "$D/lscpu_siblings.txt" | sort -n | paste -sd, -)"
N_PHYS="$(awk -F, '!/^#/ { print $3","$2 }' "$D/lscpu_siblings.txt" | sort -u | wc -l)"
N_CPU="$(grep -vc '^#' "$D/lscpu_siblings.txt")"
echo "sibling map read: $N_CPU logical CPUs on $N_PHYS physical cores; cell (c) cpuset = $ONE_PER_CORE"
[ "$N_PHYS" -lt "$N_CPU" ] || echo "NOTE: every logical CPU is its own core here — there are no siblings to remove, so cell (c) equals cell (a) and the SMT hypothesis cannot be tested on this box"
printf '{"logical_cpus": %s, "physical_cores": %s, "cell_c_cpuset": "%s"}\n' "$N_CPU" "$N_PHYS" "$ONE_PER_CORE" > "$D/cells.json"

export BSZ_EXPECT_HEAD="$H"
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

step rr_a1 BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_a1" "" 0 smt_a1
step rr_a2 BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_a2" "" 0 smt_a2
step rr_b  BSZ_CONTINUOUS=32 BSZ_CPUSET=0-23 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_b" "" 0 smt_b
step rr_c  BSZ_CONTINUOUS=32 BSZ_CPUSET="$ONE_PER_CORE" bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_c" "" 0 smt_c
step li_a  BSZ_CONTINUOUS=32 BSZ_LI_WORKERS=24 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_a" "" 0 smt_a
step li_b  BSZ_CONTINUOUS=32 BSZ_LI_WORKERS=24 BSZ_CPUSET=0-23 bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_b" "" 0 smt_b
step li_c  BSZ_CONTINUOUS=32 BSZ_LI_WORKERS=24 BSZ_CPUSET="$ONE_PER_CORE" bash working/scripts/batchsize_docs_run.sh li "$SLICE" "$D/li_c" "" 0 smt_c

DEST="s3://rocketride-benchmark-data/ansh/batch-size-optimization/$REL"
for f in lscpu_siblings.txt lscpu_full.txt cells.json; do aws s3 cp "$D/$f" "$DEST/$f" --only-show-errors || true; done
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
