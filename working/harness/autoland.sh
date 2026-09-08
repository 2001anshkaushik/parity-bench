#!/usr/bin/env bash
# working/harness/autoland.sh — commit, gate, push, and PROVE the landing.
#
# WHY THIS EXISTS
# ---------------
# Register entry 26: a commit is landed only when the laptop has read it back from
# origin. That rule was previously satisfied by Ansh running ls-remote by hand and
# reading the sha. This makes the read-back part of the command, so "pushed" and
# "landed" cannot diverge — the script exits non-zero unless origin actually reports
# the sha we just built.
#
# It also replaces the retired manual approval on pushes. The repo is PUBLIC and two
# teammates clone it, so the gate is content-level, not attention-level.
#
# GATES, in order, all fail-closed:
#   0  shape: on a branch, origin reachable (fetched), index CLEAN, explicit paths,
#      HEAD not behind origin/<branch> (a claimed base is never pushed onto — entry 26);
#      then the paths are staged and the SINGLE-SOURCE files are checked against the
#      other campaign branch (AUTOMATION_CONTRACT.md identical or only-behind in the
#      merge direction video-bench -> docs-bench; DOCS_HANDOFF.md canonical on docs-bench,
#      a marked stub anywhere else)
#   1  APPEND-ONLY: refuse any modification/deletion/rename under working/results/
#   2  static undefined-name gate over changed python (imports static_names, never
#      runs it as a script — it has no __main__ and would exit 0 doing nothing)
#   3  the test suite, against a BASELINE: refuse a failure not baselined, refuse a
#      baselined failure that now passes (update the baseline deliberately), refuse a
#      runner that did not complete, refuse MORE SKIPS than the baseline allows (a
#      skipped test is a path the suite did not run — entry 27). rc alone is
#      insufficient: the runner returns 1 for a baselined failure.
#   4  figure_guard over the prose that will go public (its own null control first)
#   5  figure_guard over the COMMIT MESSAGE, then commit — a message is public and
#      permanent, so a never-quote figure in it is refused before the commit exists
#   6  push — never --force; first push of a branch sets upstream explicitly
#   7  ls-remote read-back  <-- the landing proof
#
# WHAT IT WILL NOT DO, ever: --force, branch delete, history rewrite, or touch an
# existing measurement artifact. Those are the red list; they stop for a human.
#
# REPAIRS 2026-09-08 (six defects in the Advisor's draft, each null-controlled in
# autoland_selftest.sh — `autoland.sh --self-test`):
#   A1 interpreter PROVEN by importing psutil, not by a path existing; ~/.venv is the
#      BOX path, the laptop's venv is ../.venv.
#   A2 gate 3 had no baseline and could never pass on this repo (thread_settings_matched
#      fails at 87b957d); now parses FAILED lines against suite_baseline.json.
#   A3 `git add -A` with no paths swept untracked files once (~170 run records);
#      explicit paths are required.
#   A4 gate 4 assumed origin/<branch> exists; a first-landing branch has none. Base
#      falls back to the merge-base with origin/video-bench, then origin/main, then HEAD.
#   A5 `git reset -q` on refusal discarded whatever was staged beforehand; now a dirty
#      index is refused up front, so a reset only ever undoes this script's own staging.
#   A6 push on a branch with no upstream; now `push -u` on the first push.
#   Plus, found in audit: staged DELETIONS of .py files were handed to the static gate
#   (a missing file would have crashed it into a false refusal); gate 1 now refuses
#   every non-A status (T/C too), and the read-back names refs/heads/<branch> exactly.
#
# Usage:
#   autoland.sh "commit message" path [path ...]
#   autoland.sh --dry-run "commit message" path [path ...]   # every gate, no commit/push
#   autoland.sh --verify                                     # is HEAD landed on origin?
#   autoland.sh --self-test                                  # sandboxed null controls
# Env: PYBIN=/path/to/python overrides interpreter discovery.
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RED_LIST_NOTE="RED LIST — this stops for a human. See working/docs/AUTOMATION_CONTRACT.md."
RUNNER="working/scripts/regression_selftest.py"
BASELINE="working/harness/suite_baseline.json"
GUARD="working/harness/figure_guard.py"

MODE="land"
case "${1:-}" in
  --self-test) exec bash "$SELF/autoland_selftest.sh" ;;
  --dry-run)   MODE="dry"; shift ;;
  --verify)    MODE="verify"; shift ;;
esac

say() { printf '\n=== %s\n' "$*"; }
die() { printf '\nAUTOLAND: REFUSED — %s\n' "$*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "autoland: not in a git repo" >&2; exit 2; }
TOP="$(pwd)"

# Transcript: every run appended, UTC-stamped, so gate output is quotable later.
if [[ "${AUTOLAND_NO_LOG:-0}" != "1" ]]; then
  LOGDIR="${AUTOLAND_LOG_DIR:-$HOME/.rocketride_box}"; mkdir -p "$LOGDIR"
  LOG="$LOGDIR/autoland_$(date -u +%Y%m%d).log"
  exec > >(tee -a "$LOG") 2>&1
  printf '\n##### autoland %s  mode=%s  cwd=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE" "$TOP"
fi

# ------------------------------------------------------------ A1: the interpreter
# PROVEN, not assumed: a candidate counts only if it can import psutil, which the
# harness needs. A path that exists is not evidence it is the interpreter we need.
PY=""; TRIED=()
for cand in "${PYBIN:-}" "$TOP/../.venv/bin/python" "$HOME/.venv/bin/python"; do
  [[ -n "$cand" ]] || continue
  TRIED+=("$cand")
  if [[ -x "$cand" ]] && "$cand" -c 'import psutil' >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [[ -z "$PY" ]]; then
  echo "autoland: no interpreter that can import psutil. Tried, in order:" >&2
  for t in ${TRIED[@]+"${TRIED[@]}"}; do echo "    $t" >&2; done
  echo "  (\$PYBIN, then <repo>/../.venv/bin/python — the laptop venv — then ~/.venv/bin/python — the box venv)" >&2
  echo "  Set PYBIN=/path/to/python that has psutil and re-run." >&2
  exit 2
fi
echo "interpreter: $PY  ($("$PY" --version 2>&1); psutil import proven)"

remote_sha() { git ls-remote --heads origin "refs/heads/$1" | awk '{print $1}'; }

# ------------------------------------------------------------------- --verify
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$MODE" == "verify" ]]; then
  say "verify — is HEAD landed on origin/$BRANCH? (entry 26)"
  [[ "$BRANCH" != "HEAD" ]] || die "detached HEAD"
  git fetch -q origin || die "cannot fetch origin — a landing cannot be verified without a read-back"
  LOCAL="$(git rev-parse HEAD)"; REMOTE="$(remote_sha "$BRANCH")"
  echo "  local : $LOCAL"; echo "  origin: ${REMOTE:-<none>}"
  [[ -n "$REMOTE" && "$LOCAL" == "$REMOTE" ]] && { printf '\nAUTOLAND: LANDED  %s  on %s\n' "$LOCAL" "$BRANCH"; exit 0; }
  die "HEAD $LOCAL is not what origin reports for $BRANCH (${REMOTE:-nothing}). Not landed."
fi

MSG="${1:-}"; shift || true
[[ -n "$MSG" ]] || die "usage: autoland.sh [--dry-run] \"commit message\" path [path ...]"
PATHS=("$@")

# ---------------------------------------------------------------- gate 0: shape
say "gate 0 — branch shape"
[[ "$BRANCH" != "HEAD" ]] || die "detached HEAD. Check out a branch first."
echo "  branch: $BRANCH"
git fetch -q origin || die "cannot fetch origin — no read-back is possible, so no landing is possible"
# A5: never discard someone else's staged work. If the index is dirty we refuse BEFORE
# touching it, and every later `git reset -q` in this script undoes only our own add.
PRESTAGED="$(git diff --cached --name-only)"
if [[ -n "$PRESTAGED" ]]; then
  echo "  the index already holds staged changes:" >&2
  echo "$PRESTAGED" | sed 's/^/    /' >&2
  die "index is dirty. Commit or unstage them yourself first — this script will not fold them into its commit and will not discard them."
fi
# A3: explicit paths, always. `git add -A` once swept ~170 local run records (and this
# repo carries untracked .claude/ .github/ and scratch files) into a PUBLIC repo.
if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "  untracked files present right now:" >&2
  git ls-files --others --exclude-standard | sed 's/^/    /' >&2
  die "no paths given. Name every path to land: autoland.sh \"msg\" path/one path/two — there is no all-files mode."
fi
# entry 26: HEAD must contain origin/<branch>; otherwise the base is CLAIMED by work we
# have not read back, and the only repair is a merge, never a rebase, never --force.
if git rev-parse --verify -q "refs/remotes/origin/$BRANCH" >/dev/null; then
  if ! git merge-base --is-ancestor "refs/remotes/origin/$BRANCH" HEAD; then
    echo "  origin/$BRANCH = $(git rev-parse --short "refs/remotes/origin/$BRANCH") is NOT an ancestor of HEAD = $(git rev-parse --short HEAD)" >&2
    die "the branch base is CLAIMED by commits on origin that HEAD does not contain (entry 26). Land the origin side first: git merge --ff-only origin/$BRANCH, or an as-is merge after a path-overlap check. Never rebase, never --force."
  fi
  echo "  origin/$BRANCH $(git rev-parse --short "refs/remotes/origin/$BRANCH") is an ancestor of HEAD — not pushing onto a claimed base"
else
  echo "  origin/$BRANCH does not exist yet — this will be the branch's first push (upstream will be set)"
fi

if ! git add -- ${PATHS[@]+"${PATHS[@]}"}; then
  git reset -q
  die "git add failed on the given paths (missing, or ignored — an ignored path needs a deliberate decision, not a silent add)"
fi

# ---- single-source files (2026-09-08). Two campaign branches carry the same operating
# documents; a stale copy on one of them is a session reading the wrong document. The
# merge direction is video-bench -> docs-bench ONLY (as-is merge), so:
#   IDENTICAL paths: on the SOURCE branch the other side may only be BEHIND (its copy is a
#     version already in this branch's history); on the DESTINATION or any other branch
#     the copy must equal origin/video-bench's exactly — edit it there and merge forward.
#   CANONICAL-OR-STUB paths: docs-bench carries the document; every other branch carries
#     a marked stub, so no prose on the wrong branch can be mistaken for the briefing.
CAMPAIGN_SRC="video-bench"; CAMPAIGN_DST="docs-bench"
SINGLE_SOURCE_IDENTICAL=("working/docs/AUTOMATION_CONTRACT.md")
SINGLE_SOURCE_CANONICAL_OR_STUB=("working/docs/DOCS_HANDOFF.md")
STUB_MARKER="<!-- DOCS_HANDOFF_STUB: the document lives on docs-bench -->"
blob_at() {  # $1 = INDEX | HEAD | any ref, $2 = path -> blob id or empty
  if [[ "$1" == "INDEX" ]]; then git rev-parse -q --verify ":$2" 2>/dev/null || true
  else git rev-parse -q --verify "$1:$2" 2>/dev/null || true; fi
}
blob_is_stub() { git cat-file -p "$1" | head -1 | grep -qF "$STUB_MARKER"; }
blob_in_history() {  # $1 blob, $2 path: is this blob any committed version of $path on HEAD?
  local c
  for c in $(git log --format=%H HEAD -- "$2"); do
    [[ "$(blob_at "$c" "$2")" == "$1" ]] && return 0
  done
  return 1
}
say "gate 0b — single-source files against the other campaign branch"
if [[ "$BRANCH" == "$CAMPAIGN_SRC" ]]; then OTHER="$CAMPAIGN_DST"; ROLE="source"; else OTHER="$CAMPAIGN_SRC"; ROLE="destination"; fi
[[ "$BRANCH" == "$CAMPAIGN_SRC" || "$BRANCH" == "$CAMPAIGN_DST" ]] || echo "  $BRANCH is not a campaign branch — held to the destination rule against origin/$CAMPAIGN_SRC"
if git rev-parse -q --verify "refs/remotes/origin/$OTHER" >/dev/null; then
  for sp in "${SINGLE_SOURCE_IDENTICAL[@]}"; do
    mine="$(blob_at INDEX "$sp")"; head_="$(blob_at HEAD "$sp")"; theirs="$(blob_at "refs/remotes/origin/$OTHER" "$sp")"
    if [[ -z "$mine" && -n "$head_" ]]; then git reset -q; die "$sp is being DELETED on $BRANCH — it is a single-source file carried by both campaign branches"; fi
    if [[ -z "$mine" && -z "$theirs" ]]; then echo "  $sp: absent on both $BRANCH and origin/$OTHER"; continue; fi
    if [[ -z "$mine" ]]; then echo "  $sp: absent on $BRANCH, present on origin/$OTHER — not yet carried here"; continue; fi
    if [[ "$mine" == "$theirs" ]]; then echo "  $sp: identical to origin/$OTHER"; continue; fi
    if [[ "$ROLE" == "source" && -n "$theirs" ]] && blob_in_history "$theirs" "$sp"; then
      echo "  $sp: origin/$OTHER is BEHIND (its copy is an earlier version in this branch's history) — merge $CAMPAIGN_SRC -> $CAMPAIGN_DST as-is to converge"; continue
    fi
    git reset -q
    if [[ "$ROLE" == "source" ]]; then
      die "$sp on origin/$OTHER carries a version that is NOT in $BRANCH's history — a foreign edit on the destination branch. The merge direction is $CAMPAIGN_SRC -> $CAMPAIGN_DST only; the other copy must be reconciled by hand (never merged back)."
    else
      die "$sp differs from origin/$CAMPAIGN_SRC. Single-source rule: edit it on $CAMPAIGN_SRC and merge it forward (as-is); it is never edited on $BRANCH."
    fi
  done
  for sp in "${SINGLE_SOURCE_CANONICAL_OR_STUB[@]}"; do
    mine="$(blob_at INDEX "$sp")"; head_="$(blob_at HEAD "$sp")"
    if [[ -z "$mine" && -n "$head_" ]]; then git reset -q; die "$sp is being DELETED on $BRANCH"; fi
    if [[ -z "$mine" ]]; then echo "  $sp: absent on $BRANCH"; continue; fi
    if [[ "$BRANCH" == "$CAMPAIGN_DST" ]]; then
      if blob_is_stub "$mine"; then git reset -q; die "$sp on $CAMPAIGN_DST is a STUB — $CAMPAIGN_DST is the canonical home; a stub here leaves no document anywhere"; fi
      echo "  $sp: canonical on $CAMPAIGN_DST"
    else
      if ! blob_is_stub "$mine"; then git reset -q; die "$sp on $BRANCH is not the stub — only $CAMPAIGN_DST carries the document; every other branch carries a stub whose first line is: $STUB_MARKER"; fi
      echo "  $sp: stub on $BRANCH (canonical copy is on $CAMPAIGN_DST)"
    fi
  done
else
  echo "  origin/$OTHER does not exist — nothing to compare against"
fi

# ------------------------------------------------------- gate 1: append-only artifacts
say "gate 1 — measurement artifacts are append-only"
# Anything but A (added) under working/results/ is a change to evidence: M, D, R, T, C.
VIOLATIONS="$(git diff --cached --name-status -- working/results/ | awk '$1 !~ /^A/ {print $0}' || true)"
if [[ -n "$VIOLATIONS" ]]; then
  echo "$VIOLATIONS" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  Existing artifacts under working/results/ are the evidence behind every claim" >&2
  echo "  and are not reproducible. New files are fine; changing, renaming or deleting" >&2
  echo "  one is not.  $RED_LIST_NOTE" >&2
  git reset -q
  die "append-only violation under working/results/"
fi
STAGED="$(git diff --cached --name-only)"
if [[ -z "$STAGED" ]]; then
  git reset -q
  die "the given paths produced no staged change — nothing to land. (To check whether HEAD is landed: autoland.sh --verify)"
fi
echo "  staged, no artifact modified:"
echo "$STAGED" | sed 's/^/    /'

# ------------------------------------------------------------- gate 2: static names
say "gate 2 — static undefined-name gate"
# Deletions excluded: a deleted .py has no file to scan and would crash the checker
# into a refusal that names nothing.
PYFILES=()
while IFS= read -r _f; do [[ -n "$_f" ]] && PYFILES+=("$_f"); done \
  < <(git diff --cached --name-only --diff-filter=d -- '*.py')
if [[ ${#PYFILES[@]} -gt 0 ]]; then
  # static_names.py is a LIBRARY (no __main__): run as a script it defines its functions
  # and exits 0 — a gate that can only pass. Import it.
  if ! "$PY" - "${PYFILES[@]}" <<'PYEOF'
import sys
sys.path.insert(0, "working/harness")
from static_names import check_files
res = check_files(sys.argv[1:])
bad = {k: v for k, v in res.items() if v}
for path, findings in bad.items():
    for f in findings:
        print(f"  {path}: {f}", file=sys.stderr)
sys.exit(1 if bad else 0)
PYEOF
  then git reset -q; die "static_names refused. An undefined name inside an unexecuted branch is a live defect (entries 4, 27)."; fi
  echo "  clean over ${#PYFILES[@]} changed python file(s)"
else
  echo "  no python changed — skipped"
fi

# ------------------------------------------------------------------ gate 3: suite
say "gate 3 — test suite against the baseline"
[[ -f "$RUNNER" ]]   || { git reset -q; die "$RUNNER is absent. A missing gate is not a passing gate."; }
[[ -f "$BASELINE" ]] || { git reset -q; die "$BASELINE is absent. Gate 3 cannot tell a known failure from a new one without it."; }
echo "  baselined failures (from $BASELINE — a listed test that starts passing is also refused):"
if ! "$PY" - "$BASELINE" <<'PYEOF'
import json, sys
try:
    b = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"    {sys.argv[1]} is not valid JSON: {e}"); sys.exit(1)
for k, v in (b.get("failing") or {}).items():
    print(f"    {k}  [since {v.get('since_commit','?')}, baselined at {b.get('baselined_at_commit','?')}] {v.get('reason','')[:120]}")
if not b.get("failing"): print("    (none)")
print(f"    max_skipped: {b.get('max_skipped', 'ABSENT')}")
PYEOF
then git reset -q; die "$BASELINE is not valid JSON — a gate whose baseline cannot be read cannot tell a known failure from a new one"; fi
SUITE_OUT="$(mktemp -t autoland_suite.XXXXXX)"
echo "  running: $PY $RUNNER"
T0=$(date +%s); set +e; "$PY" "$RUNNER" >"$SUITE_OUT" 2>&1; SUITE_RC=$?; set -e
echo "  runner rc=$SUITE_RC in $(( $(date +%s) - T0 ))s; tail of output:"
tail -n 12 "$SUITE_OUT" | sed 's/^/    | /'
if ! "$PY" - "$BASELINE" "$SUITE_OUT" "$SUITE_RC" <<'PYEOF'
import json, re, sys
bl = json.load(open(sys.argv[1]))
base = set((bl.get("failing") or {}).keys())
out = open(sys.argv[2], errors="replace").read(); rc = int(sys.argv[3])
summ = re.search(r"^\s*(\d+) passed, (\d+) failed, (\d+) skipped", out, re.M)
completed = summ is not None
skipped = int(summ.group(3)) if summ else None
failing = set(re.findall(r"^\s*FAILED (\S+?):", out, re.M))
new = sorted(failing - base); fixed = sorted(base - failing)
print(f"  parsed: completed={completed} rc={rc} failing={sorted(failing)} baseline={sorted(base)} skipped={skipped} max_skipped={bl.get('max_skipped')!r}")
bad = []
if not completed:
    bad.append("the runner did not print its summary line — it crashed or was cut off; a suite that did not complete proves nothing (entry 35)")
if "max_skipped" not in bl:
    bad.append(f"{sys.argv[1]} has no max_skipped — a suite with an unbounded skip count is a suite whose coverage is unknown (entry 27); record today's skip count")
elif skipped is not None and skipped > int(bl["max_skipped"]):
    bad.append(f"{skipped} test(s) SKIPPED, baseline allows {bl['max_skipped']} — the suite ran fewer live paths than it did when baselined (engine down on :5565? engine/ absent?). A green run on fewer paths is a narrower claim, not a pass (entry 27)")
if new:
    bad.append(f"NEW failure(s) not in the baseline: {new}")
if fixed:
    bad.append(f"baselined test(s) now PASS: {fixed} — good news, but update {sys.argv[1]} deliberately (remove them) before landing, so the baseline never silently rots")
if rc != 0 and completed and not failing:
    bad.append(f"runner exited {rc} without naming a FAILED test — read the output")
if rc == 0 and base and completed and not fixed:
    bad.append("runner exited 0 while the baseline lists failures the output did not report — the runner and the baseline disagree")
for b in bad: print("  REFUSE: " + b)
sys.exit(1 if bad else 0)
PYEOF
then
  echo "  full runner output: $SUITE_OUT" >&2
  git reset -q; die "suite gate refused. Read the runner output — do not re-run hoping."
fi
rm -f "$SUITE_OUT"
echo "  suite: only baselined failures present, skips within budget, runner completed"

# ------------------------------------------------------------ gate 4: figure guard
say "gate 4 — figure guard (never-quote figures) over everything this push makes public"
# A4: the base is what origin already has. A first-landing branch has no origin/<branch>;
# fall back to the merge-base with origin/video-bench, then origin/main, then HEAD.
if git rev-parse --verify -q "refs/remotes/origin/$BRANCH" >/dev/null; then
  BASE="$(git rev-parse "refs/remotes/origin/$BRANCH")"; BASE_WHY="origin/$BRANCH"
elif git rev-parse --verify -q refs/remotes/origin/video-bench >/dev/null; then
  BASE="$(git merge-base HEAD refs/remotes/origin/video-bench)"; BASE_WHY="merge-base(HEAD, origin/video-bench) — origin/$BRANCH does not exist"
elif git rev-parse --verify -q refs/remotes/origin/main >/dev/null; then
  BASE="$(git merge-base HEAD refs/remotes/origin/main)"; BASE_WHY="merge-base(HEAD, origin/main) — neither origin/$BRANCH nor origin/video-bench exists"
else
  BASE="HEAD"; BASE_WHY="HEAD — origin has no branch to compare against; only the staged prose is scanned"
fi
echo "  base: $(git rev-parse --short "$BASE")  ($BASE_WHY)"
[[ -f "$GUARD" ]] || { git reset -q; die "$GUARD is absent. A missing gate is not a passing gate."; }
"$PY" "$GUARD" --null-control \
  || { git reset -q; die "figure_guard null control did not fire. The gate is broken; a clean run proves nothing."; }
"$PY" "$GUARD" --base "$BASE" \
  || { git reset -q; die "figure_guard refused. A withdrawn figure would have gone public uncaveated."; }

# ------------------------------------------------------------------- 5/6: land it
if [[ "$MODE" == "dry" ]]; then
  say "DRY RUN — all gates passed; commit and push skipped (index restored)"
  git reset -q
  exit 0
fi

say "gate 5 — commit message through figure_guard, then commit"
MSG_FILE="$(mktemp -t autoland_msg.XXXXXX)"; printf '%s\n' "$MSG" > "$MSG_FILE"
if ! "$PY" "$GUARD" --message-file "$MSG_FILE"; then
  rm -f "$MSG_FILE"; git reset -q
  die "the COMMIT MESSAGE carries an uncaveated never-quote figure. A message is public and permanent (no rewrite, ever), so it is refused BEFORE the commit is created. Caveat the figure in the message or drop it."
fi
rm -f "$MSG_FILE"
git commit -q -m "$MSG"
LOCAL="$(git rev-parse HEAD)"
echo "  $LOCAL  $(git log -1 --format=%s)"

say "gate 6 — push (never --force)"
if git rev-parse --verify -q "refs/remotes/origin/$BRANCH" >/dev/null && git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push origin "$BRANCH"
else
  echo "  first push of $BRANCH — setting upstream (git push -u origin $BRANCH)"
  git push -u origin "$BRANCH"
fi

# --------------------------------------------------------- gate 7: landing proof
say "gate 7 — ls-remote read-back (entry 26)"
REMOTE="$(remote_sha "$BRANCH")"
echo "  local : $LOCAL"
echo "  origin: ${REMOTE:-<none>}"
if [[ -z "$REMOTE" || "$LOCAL" != "$REMOTE" ]]; then
  echo "" >&2
  echo "  The push reported success and origin does not agree. Do NOT build on this" >&2
  echo "  base — a claimed base that has not landed is exactly the fork entry 26" >&2
  echo "  exists to prevent." >&2
  die "landing not proven"
fi
printf '\nAUTOLAND: LANDED  %s  on %s\n' "$LOCAL" "$BRANCH"
