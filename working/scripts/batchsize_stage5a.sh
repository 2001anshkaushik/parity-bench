#!/usr/bin/env bash
# batchsize_stage5a.sh — S5-A, the intra-op thread sweep on ONE RocketRide token, video.
#
#   bash working/scripts/batchsize_stage5a.sh <out_dir_abs> <expect_head>
#
# STRICTLY AFTER STAGE 4 (ruling): refuses unless the Stage 4 campaign's six primary legs AND the
# envelope's decision file exist — pass their directory as BSZ_STAGE4_DIR.
#
# HYPOTHESIS, stated before any leg: at one token the engine serialises detection behind a
# process-local device lock, so intra-op width T is the one knob that can widen a single
# instance without adding tokens. Sweep T in {1,2,4,8,16}; report the knee and the saturation
# point with utilisation, idle cores and CPU-s/frame.
#
# T IS NOT threads=. The SDK's use(threads=) adds item concurrency that queues at the device
# lock and was measured not to parallelise detection; it stays UNSET for every leg here.
#
# BUILT-IN CONTROL: the out-of-the-box posture (six variables UNSET) reads torch=16 in-process,
# so T=16 should reproduce the default-posture K=16 cell (2.623 / 2.379 f/s, 9.76% apart). A T=16
# far outside that range means "unset" and "16" differ in some variable — reported, not assumed.
#
# Comparator: the G4 matched-unit anchor (one LlamaIndex instance, K=16), never the tuned 8x4
# cell. Every figure here is TUNED POSTURE — the image is unchanged, the configuration is not —
# and is segregated from Stage 4 baseline figures in every table.
set -uo pipefail
echo "batchsize_stage5a.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <out_dir_abs> <expect_head>" >&2; exit 2; }
OUT="$1"; H="$2"
cd "$(dirname "$0")/../.." || exit 2
S4="${BSZ_STAGE4_DIR:-}"
[ -n "$S4" ] && [ -d "$S4" ] || { echo "REFUSED: set BSZ_STAGE4_DIR to the Stage 4 campaign dir — Stage 5 runs strictly after Stage 4 is banked" >&2; exit 5; }
for need in p1_rr_cont32 p2_li_cont p3_rr_k128 p4_li_k128 p5_li_video p6_rr_video envelope_k512_decision.json; do
  [ -e "$S4/$need" ] || { echo "REFUSED: Stage 4 not banked — $S4/$need is absent" >&2; exit 5; }
done
export BSZ_EXPECT_HEAD="$H"
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }

for T in 1 2 4 8 16; do
  step "s5a_T$T" BSZ_RR_T="$T" BSZ_LEG_SUFFIX="_T$T" bash working/scripts/batchsize_video_run.sh rr 16 16 "$OUT"
done

echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
