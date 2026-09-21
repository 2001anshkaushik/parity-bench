#!/usr/bin/env bash
# box_sync_worktree.sh — fast-forward a box worktree whose untracked RESULT files have since been
# landed on origin, without deleting anything and without trusting a file it has not compared.
#
#   bash working/scripts/box_sync_worktree.sh <branch> <expect_head>
#
# WHY. The box writes results under working/results/ as untracked files; the laptop later lands
# the same files on origin. The next `git pull --ff-only` then aborts ("untracked working tree
# files would be overwritten") and a chain started after it runs an OLDER script — which is how a
# Stage 3b launch briefly ran the Stage 3 cpuset (2026-09-20, recovered by hand). This is that
# recovery, made mechanical:
#   1. fetch; for every untracked file that origin now tracks, compare its blob hash with origin's
#      — ANY difference refuses (a box file that differs from the landed one is evidence, not a
#      duplicate, and is never moved or overwritten);
#   2. move the byte-identical duplicates to ~/prepull_<stamp>/ (moved, never deleted);
#   3. git pull --ff-only; refuse unless HEAD is now <expect_head>;
#   4. verify every moved file came back from git byte-identical; print the count.
set -uo pipefail
echo "box_sync_worktree.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <branch> <expect_head>" >&2; exit 2; }
BR="$1"; WANT="$(echo "$2" | cut -c1-12)"
cd "$(dirname "$0")/../.." || exit 2
git fetch -q origin "$BR" || { echo "REFUSED: fetch failed" >&2; exit 2; }
R="origin/$BR"
UNTRACKED="$(git status --porcelain --untracked-files=all)"
same=(); diff=()
while IFS= read -r line; do
  [ "${line:0:2}" = "??" ] || continue
  f="${line:3}"
  b="$(git rev-parse -q --verify "$R:$f" 2>/dev/null)" || continue      # origin does not track it: leave it
  a="$(git hash-object "$f")"
  if [ "$a" = "$b" ]; then same+=("$f"); else diff+=("$f"); fi
done <<< "$UNTRACKED"
echo "untracked files origin now tracks: identical=${#same[@]} differing=${#diff[@]}"
if [ "${#diff[@]}" -gt 0 ]; then
  printf 'DIFFERS (never moved): %s\n' "${diff[@]:0:20}" >&2
  echo "REFUSED: box files differ from the landed ones — resolve by hand; nothing was touched" >&2; exit 3
fi
B="$HOME/prepull_$(date -u +%Y%m%dT%H%M%SZ)"
for f in "${same[@]:-}"; do
  [ -n "$f" ] || continue
  mkdir -p "$B/$(dirname "$f")" && mv "$f" "$B/$f" || { echo "REFUSED: could not move $f aside" >&2; exit 4; }
done
[ "${#same[@]}" -gt 0 ] && echo "moved ${#same[@]} identical duplicates to $B (nothing deleted)"
git pull -q --ff-only origin "$BR" || { echo "REFUSED: fast-forward failed after moving duplicates aside; they remain in $B" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"
[ "$HAVE" = "$WANT" ] || { echo "REFUSED: HEAD is $HAVE after the pull, caller expects $WANT" >&2; exit 6; }
bad=0
for f in "${same[@]:-}"; do
  [ -n "$f" ] || continue
  cmp -s "$f" "$B/$f" || { echo "MISMATCH after pull: $f" >&2; bad=$((bad+1)); }
done
[ "$bad" -eq 0 ] || { echo "REFUSED: $bad restored files differ from the moved originals" >&2; exit 7; }
echo "worktree at $HAVE; ${#same[@]} files restored byte-identical from git"
