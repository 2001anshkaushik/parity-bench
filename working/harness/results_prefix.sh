# results_prefix.sh — SOURCED, never run. The one definition of "an S3 key mirrors the path
# under working/results/".
#
# Why one definition: six hand-written copies used ${X##*/working/results/}, which needs a "/"
# BEFORE "working". A RELATIVE path (working/results/<campaign>) never matched, so the whole
# path, "working/results/" included, became the key, one level outside the campaign's prefix.
# Found 2026-09-21 before the first Stage 5 launch; the only files it moved were the Stage 4
# envelope's end-of-chain files, whose chain was already running. A seventh derivation, the docs
# runner's basename(dirname(run_dir)), kept only the last component, so a leg two levels deep
# (<campaign>/s5c/rr_b) would have landed under a top-level "s5c/" prefix.
#
#   results_rel <path>         the path under working/results/. Relative, ./-relative or absolute
#                              input; a trailing slash is ignored. rc 1 and NOTHING printed when
#                              the path is not under working/results/: a caller refuses, never guesses.
#   results_parent_rel <dir>   the same for the directory that CONTAINS <dir>: a leg's campaign
#                              prefix. rc 1 unless <dir> is at least one level below a campaign.
#
# Tested by working/harness/test_results_prefix.py, whose null control runs the same cases
# against the old expression and must see it fail.
results_rel() {
  local p="${1%/}"
  case "$p" in
    working/results/?*)   printf '%s\n' "${p#working/results/}" ;;
    ./working/results/?*) printf '%s\n' "${p#./working/results/}" ;;
    */working/results/?*) printf '%s\n' "${p#*/working/results/}" ;;
    *) return 1 ;;
  esac
}

results_parent_rel() {
  local r
  r="$(results_rel "$1")" || return 1
  case "$r" in
    ?*/?*) printf '%s\n' "${r%/*}" ;;
    *) return 1 ;;
  esac
}
