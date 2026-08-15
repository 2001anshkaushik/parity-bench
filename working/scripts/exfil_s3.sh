#!/usr/bin/env bash
# Ship a run off the box. Matches Leela's exfil contract (RUN_LOG_20260814 §6): raw records go
# up, not just the report, because every metric must stay re-derivable from raw forever and a
# report alone cannot be recomputed or re-gated.
#
#   bash working/scripts/exfil_s3.sh <dir-or-file> [...]
#
# Destination: s3://rocketride-benchmark-data/ansh/<stamp>/ — the ansh/ prefix is ours, matching
# leela/ and shashi/. Override with BENCH_S3.
#
# The box uses its INSTANCE ROLE. Do not set AWS_PROFILE here — that is a laptop-side concept and
# setting it makes the CLI look for a profile that does not exist on the box.
set -euo pipefail

STAMP="${RUN_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
DEST="${BENCH_S3:-s3://rocketride-benchmark-data/ansh}/$STAMP/"
[ "$#" -ge 1 ] || { echo "usage: $0 <dir-or-file> [...]" >&2; exit 2; }

command -v aws >/dev/null 2>&1 || {
  echo "FATAL: no aws CLI. Install it first:" >&2
  echo "  sudo apt-get install -y awscli          # box has passwordless sudo" >&2
  echo "  # or, no-sudo fallback: bash working/scripts/install_awscli_userdir.sh" >&2
  exit 127; }

# Prove the role works BEFORE spending time on a copy that will 403 at the end.
aws sts get-caller-identity >/dev/null || {
  echo "FATAL: no usable credentials. On the box this should be the instance role." >&2
  echo "       If AWS_PROFILE is set, unset it — the box has no profile config." >&2
  exit 1; }

n=0
for src in "$@"; do
  [ -e "$src" ] || { echo "!! skipping missing $src" >&2; continue; }
  if [ -d "$src" ]; then
    aws s3 cp "$src" "$DEST$(basename "$src")/" --recursive --only-show-errors
  else
    aws s3 cp "$src" "$DEST" --only-show-errors
  fi
  n=$((n + 1))
done

echo "uploaded $n path(s) -> $DEST"
# Round-trip proof, not a file listing: object count and total bytes as S3 sees them. Leela's
# checklist 4.2 is that the exfil was COMPLETE, not merely that something arrived.
aws s3 ls "$DEST" --recursive --summarize | tail -3
echo "verify from the laptop with:  aws s3 cp $DEST ./run --recursive --profile <yours>"
