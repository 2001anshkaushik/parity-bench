#!/usr/bin/env bash
# =============================================================================
# RULING M C sweep (2026-08-30): run_films_curve.sh at the RULED posture
# winners, pinned IN GIT rather than in a pasted env line (entry 25 — the
# --network-host-lost-to-line-wrap lesson applies to env assignments too).
#
# RULING M, recorded: RR = M16xT2 (leads its grid, 8.65 f/s). LI = N16xT2 —
# N8xT4 (10.105 f/s) and N16xT2 (10.071 f/s) sit 0.34% apart at n=1 and the
# only reproducibility evidence is 0.09% from a DIFFERENT corpus, so the two
# are not separable at this evidence level; among tied options N16xT2 uses
# 12% less CPU (23.55 vs 26.76 cores) and matches RR's winning shape — the
# headline becomes a matched 16x2-vs-16x2 comparison. Revisitable if this
# sweep separates them. The full matrix publishes both, tie stated.
#
# FLAGGED FOR ANSH (not silently changed): Ruling I fixed C in {1,2,4,8}
# when the assumed winners had 8 lanes. At the ruled 16-lane postures C=8
# under-saturates (every point will print the Ruling-K C<lanes warning) and
# the knee cannot appear below C=16; the posture sweep's C=32 points are
# the only saturated anchors. The grid below stays AS RULED; if Ansh
# extends it, run with C_GRID="1 2 4 8 16 32" — one variable, no re-commit.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
echo "run_films_curve_ruling_m.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
export RR_TOKENS=16 RR_TENV=2 LI_INSTANCES=16 LI_TENV=2
# run_films_curve.sh self-prints ITS sha and the repo HEAD next — the STOP
# reads all three lines before the sweep proceeds.
exec "$HERE/run_films_curve.sh"
