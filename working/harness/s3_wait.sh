#!/usr/bin/env bash
# s3_wait.sh — wait, from the laptop, for an object to appear under an S3 prefix.
#
#   working/harness/s3_wait.sh <s3-prefix> <grep-pattern> <max-minutes> [poll-seconds]
#
# Exit codes are DISTINCT, because three different conditions must never read as one:
#   0  the pattern appeared
#   3  AUTH EXPIRED — the laptop's SSO session died; every later check would be blind
#   4  timeout with credentials that still worked — the object genuinely did not appear
#
# WHY IT EXISTS (2026-09-21). A bare `until aws s3 ls … | grep -q …; do sleep; done` treats a
# failing `aws` exactly like "not there yet": when the SSO token expired mid-wait, the loop kept
# polling blind until its timeout and then reported "did not land", which was never observed —
# the leg's state was simply unknown. Credentials are now proven on every iteration, before the
# listing is believed.
set -uo pipefail
[ "$#" -ge 3 ] || { echo "usage: $0 <s3-prefix> <grep-pattern> <max-minutes> [poll-seconds]" >&2; exit 2; }
PREFIX="$1"; PAT="$2"; MAXMIN="$3"; SLP="${4:-120}"
PROFILE="${BOX_PROFILE:-rocketride}"
end=$(( $(date +%s) + MAXMIN * 60 ))
while :; do
  if ! aws --profile "$PROFILE" sts get-caller-identity >/dev/null 2>&1; then
    echo "AUTH EXPIRED at $(date -u +%H:%M:%SZ) — run: aws sso login --profile $PROFILE. The state of $PREFIX is UNKNOWN, not absent."
    exit 3
  fi
  if aws --profile "$PROFILE" s3 ls "$PREFIX" 2>/dev/null | grep -q -- "$PAT"; then
    echo "APPEARED at $(date -u +%H:%M:%SZ): $PAT under $PREFIX"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$end" ]; then
    echo "TIMEOUT after ${MAXMIN} min with working credentials: $PAT never appeared under $PREFIX"
    exit 4
  fi
  sleep "$SLP"
done
