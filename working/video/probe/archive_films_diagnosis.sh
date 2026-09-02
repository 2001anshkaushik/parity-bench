#!/usr/bin/env bash
# archive_films_diagnosis.sh — archive the films diagnosis evidence to S3.
# BOX-SIDE (instance role; never export AWS_PROFILE on the box — handoff §6).
# Read-only on the box dirs; writes only the two S3 prefixes below.
# Prints per-file sha256 BEFORE uploading so the laptop landing can verify
# byte identity after fetch (entry-25/26 discipline). Idempotent: sync
# re-uploads only changed files; re-running after success is harmless.
set -euo pipefail
echo "script sha256: $(sha256sum "$0" | awk '{print $1}')"
echo "repo HEAD: $(git -C ~/parity-bench-video rev-parse --short HEAD 2>/dev/null || echo 'n/a')"

SRC_PF="$HOME/films_probe/parity_failing"
SRC_DP="$HOME/films_probe/detector_parity"
DST_PF="s3://rocketride-benchmark-data/ansh/parity-failing-20260902/"
DST_DP="s3://rocketride-benchmark-data/ansh/detector-parity-20260902/"

for d in "$SRC_PF" "$SRC_DP"; do
  [ -d "$d" ] || { echo "MISSING: $d — refusing (nothing archived)"; exit 3; }
done

echo "== sha256 of every file to be archived =="
( cd "$HOME/films_probe" && find parity_failing detector_parity -type f -exec sha256sum {} + | sort -k2 )

echo "== sizes =="
du -sh "$SRC_PF" "$SRC_DP"

aws s3 sync "$SRC_PF" "$DST_PF"
aws s3 sync "$SRC_DP" "$DST_DP"

echo "== archived listings =="
aws s3 ls "$DST_PF" --recursive
aws s3 ls "$DST_DP" --recursive
echo "DONE — paste everything above back for the laptop landing."
