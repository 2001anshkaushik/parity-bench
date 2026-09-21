#!/usr/bin/env bash
# batchsize_stage5d_funnel.sh — S5-D, the admission funnel inside one RocketRide token.
#
#   bash working/scripts/batchsize_stage5d_funnel.sh <campaign_dir> <slice_9975.json> <expect_head>
#
# HYPOTHESIS (Ansh, 2026-09-21): one token exposes a fixed lane count; large documents occupy the
# lanes and small ones queue behind them. EVIDENCE: in leg 1, 1-page PDFs were held 548-720 s while
# 1,000-1,700-page documents were in flight; p50 2.8 s against p99 88.8 s.
#
# SOURCE, a map of what to measure (register 1), never the answer: each send opens a pipe under
# asyncio.Semaphore(threadCount) — 64 when threads= is unset (data_conn.py:138), so at C=32 it
# cannot bind; pipe work runs on asyncio.to_thread, Python's default executor, 32 workers here;
# the embedding encode path holds NO lock. So if small documents wait, it is not an explicit lane
# cap — the stamps say whether the wait is before admission or inside a stage (Tika, splitter,
# embedding), and in which.
#
# THE LEG: an INSTRUMENTED REPLAY of leg 1 — RocketRide, 1 token, continuous C=32, the full 9,975
# documents, prewarmed, unconstrained (Ruling A) — with three pass-through stamp_probe nodes at
# the parse, split and embed boundaries. Pass-through proven before use: chunk hashes identical
# with and without the nodes (laptop engine, 2026-09-21). Every send carries its document name so
# engine stamps join client records. The perturbation is measured against leg 1, not assumed.
#
# Strictly after the envelope: refuses unless BSZ_STAGE4_DIR holds envelope_done.json.
set -uo pipefail
echo "batchsize_stage5d_funnel.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 3 ] || { echo "usage: $0 <campaign_dir> <slice_9975.json> <expect_head>" >&2; exit 2; }
D="$1"; SLICE="$2"; H="$3"
cd "$(dirname "$0")/../.." || exit 2
S4="${BSZ_STAGE4_DIR:-}"
[ -n "$S4" ] && [ -f "$S4/envelope_done.json" ] || { echo "REFUSED: Stage 5 runs strictly after the envelope — set BSZ_STAGE4_DIR to a campaign dir holding envelope_done.json" >&2; exit 5; }
[ -f working/nodes/stamp_probe/IInstance.py ] || { echo "REFUSED: the stamp_probe node is absent from this tree" >&2; exit 5; }
echo "stamp_probe md5: $(md5sum working/nodes/stamp_probe/IInstance.py | cut -d' ' -f1)"
export BSZ_EXPECT_HEAD="$H" BSZ_PREWARM=1 BSZ_STAMP=1
R=()
step() { local l="$1"; shift; echo "===== STEP $l $(date -u +%H:%M:%SZ) ====="; ( env "$@" ); local rc=$?; R+=("$l:rc=$rc"); echo "===== STEP $l rc=$rc $(date -u +%H:%M:%SZ) ====="; }
step s5d_rr_stamped BSZ_CONTINUOUS=32 bash working/scripts/batchsize_docs_run.sh rr "$SLICE" "$D/rr_stamped" "" 0 s5d
echo "CHAIN RESULTS: ${R[*]}"
echo "CHAIN_DONE"
