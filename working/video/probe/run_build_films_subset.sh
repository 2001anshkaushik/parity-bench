#!/usr/bin/env bash
# =============================================================================
# Build + pin the films subset manifest (Rulings E/F, 2026-08-28). Committed
# script + self-printed sha256 per register entry 25.
#
# What it runs: fetch_films_subset.py — selection imported one-copy from
# films_strata_report (ratified splits in-rule; [waterfront] flagged, left
# merged), fetch-if-absent from her v2 prefix (sequential; resumable),
# sha256+bytes verified against her sealed manifest PER FILM on arrival
# (fail-closed), expected_frames_measured cut through OUR arms' own binary
# at fps=1/15 with BOTH PNG splitters agreeing — never her frames_counted.
#
# Disk: selection ~16-20 GB at the ~500 MB median (grapes 2.2 GB included);
# films already under ~/films_probe are NOT reused — the corpus dir is the
# single stamped home (entry 15), so expect refetches of the probe films.
# NOTE printed by the report and carried here: the ruled rule at k=4 yields
# N=35 (8 cells x 4 + the 3-title cell), not the ruling's stated 32 — read
# the printed N and STOP if Ansh wants the discrepancy reconciled first.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_build_films_subset.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PY:-$HOME/.venv-floor/bin/python3}"
CORPUS_DIR="${CORPUS_DIR:-$HOME/films_corpus/subset}"
AWS_BIN="${AWS_BIN:-$(command -v aws)}"

df -h "$HOME" | tail -1
"$PY" working/video/fetch_films_subset.py \
    --corpus-dir "$CORPUS_DIR" \
    --her-manifest "$HOME/films_manifest/corpus_manifest.json" \
    --k "${K:-4}" \
    --aws "$AWS_BIN" \
    --out working/video/films_video_manifest.jsonl

echo "manifest committed-to-disk at working/video/films_video_manifest.jsonl"
echo "NEXT (entry 26): commit the manifest on the box, bundle to S3 — that"
echo "bundle is a STOP-AND-LAND step; nothing else pushes until it is"
echo "fetched on the laptop and ls-remote confirms."
