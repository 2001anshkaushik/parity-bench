#!/usr/bin/env bash
# working/harness/autoland_selftest.sh — null controls for every autoland.sh gate, run in a
# throwaway sandbox repo with a LOCAL bare "origin". Nothing here touches the real repo,
# the real origin, or the network. Invoked as `autoland.sh --self-test`.
#
# A gate never seen to refuse is not known to work (register entry 2; AUTOMATION_CONTRACT
# §3). So each gate is driven in BOTH directions: a case built to be refused must be
# refused (naming the reason), and its clean twin must pass. The real autoland.sh runs
# against the sandbox unmodified — the sandbox supplies the same relative paths autoland
# reads (working/scripts/regression_selftest.py as a FAKE runner driven by env,
# working/harness/suite_baseline.json, working/harness/{static_names,figure_guard}.py
# copied from this tree) — so the code under test is the code that lands.
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOLAND="$SELF/autoland.sh"
REAL_TOP="$(git -C "$SELF" rev-parse --show-toplevel)"

# The interpreter, proven the same way autoland proves it.
PY=""
for cand in "${PYBIN:-}" "$REAL_TOP/../.venv/bin/python" "$HOME/.venv/bin/python"; do
  [[ -n "$cand" && -x "$cand" ]] && "$cand" -c 'import psutil' >/dev/null 2>&1 && { PY="$cand"; break; }
done
[[ -n "$PY" ]] || { echo "self-test: no interpreter with psutil (set PYBIN)"; exit 2; }
echo "self-test interpreter: $PY"

TMP="$(mktemp -d -t autoland_selftest.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
ORIGIN="$TMP/origin.git"; REPO="$TMP/repo"
OK=0; BAD=0
chk() {  # $1 label, $2 condition (0/1 as command rc), $3 detail (optional)
  if [[ "$2" -eq 0 ]]; then echo "  PASS  $1"; OK=$((OK+1)); else echo "  FAIL  $1  ${3:-}"; BAD=$((BAD+1)); fi
}
G() { git -C "$REPO" "$@"; }
# run autoland in the sandbox; output -> $OUT, rc -> $RC. Extra env via leading VAR=... args.
OUT=""; RC=0
run_al() {
  local envs=()
  while [[ "${1:-}" == *=* ]]; do envs+=("$1"); shift; done
  OUT="$(cd "$REPO" && env AUTOLAND_NO_LOG=1 PYBIN="$PY" ${envs[@]+"${envs[@]}"} bash "$AUTOLAND" "$@" 2>&1)"; RC=$?
}
has() { printf '%s' "$OUT" | grep -qE -- "$1"; }
clean_tree() { G reset -q --hard >/dev/null; G clean -qfd >/dev/null; }

# ------------------------------------------------------------------ sandbox
git init -q --bare "$ORIGIN"; git -C "$ORIGIN" symbolic-ref HEAD refs/heads/video-bench
git init -q -b video-bench "$REPO"
G config user.email selftest@local; G config user.name selftest; G config commit.gpgsign false
mkdir -p "$REPO/working/results" "$REPO/working/harness" "$REPO/working/scripts" "$REPO/working/docs"
cp "$SELF/static_names.py" "$SELF/figure_guard.py" "$REPO/working/harness/"
echo '{"measured": 1}' > "$REPO/working/results/existing.json"
echo "# readme" > "$REPO/README.md"
echo "prose lives here" > "$REPO/working/docs/README.md"   # keeps the dir through git clean -d
cat > "$REPO/working/scripts/regression_selftest.py" <<'PYEOF'
# FAKE runner for the autoland self-test: same output SHAPE as the real one, driven by env.
import os, sys
fails = [f for f in os.environ.get("FAKE_FAILS", "").split() if f]
if os.environ.get("FAKE_CRASH") == "1":
    raise RuntimeError("runner crashed before its summary")
print("  PASS  content_sanity                      ok")
for f in fails: print(f"  FAIL  {f:36s} injected")
print(f"  {1} passed, {len(fails)} failed, 0 skipped, 0 xfail (known open upstream), 0 xpass")
for f in fails: print(f"    FAILED {f}: injected failure")
sys.exit(1 if fails else 0)
PYEOF
cat > "$REPO/working/harness/suite_baseline.json" <<'JEOF'
{"runner": "working/scripts/regression_selftest.py", "baselined_at_commit": "sandbox",
 "failing": {"thread_settings_matched": {"since_commit": "sandbox", "reason": "baselined in the sandbox"}}}
JEOF
G add -A >/dev/null; G commit -q -m "sandbox init"
G remote add origin "$ORIGIN"; G push -q -u origin video-bench
BASE_OK="FAKE_FAILS=thread_settings_matched"   # the runner state under which gate 3 must pass

echo "=== A1: interpreter is PROVEN by importing psutil"
mkdir -p "$TMP/nohome"
echo "x" > "$REPO/a1.txt"
run_al "PYBIN=/usr/bin/false" "HOME=$TMP/nohome" "$BASE_OK" --dry-run "m" a1.txt
chk "A1 refuses when no candidate imports psutil (rc 2)" $([[ $RC -eq 2 ]]; echo $?) "rc=$RC"
chk "A1 refusal lists what it tried"           $(has 'Tried, in order'; echo $?) "$OUT"
chk "A1 refusal names /usr/bin/false"           $(has '/usr/bin/false'; echo $?)
run_al "$BASE_OK" --dry-run "m" a1.txt
chk "A1 prints the proven interpreter"          $(has "interpreter: $PY"; echo $?) "$OUT"
chk "A1 clean twin: dry run passes (rc 0)"     $([[ $RC -eq 0 ]]; echo $?) "rc=$RC $OUT"
clean_tree

echo "=== A3: explicit paths required"
run_al "$BASE_OK" "m"
chk "A3 refuses with no paths"                  $([[ $RC -ne 0 ]] && has 'no paths given'; echo $?) "rc=$RC $OUT"
chk "A3 refusal happens before any add (index clean)" $([[ -z "$(G diff --cached --name-only)" ]]; echo $?)

echo "=== A5: a dirty index is refused up front and never discarded"
echo "theirs" >> "$REPO/README.md"; G add README.md
echo "mine" > "$REPO/a5.txt"
run_al "$BASE_OK" --dry-run "m" a5.txt
chk "A5 refuses on a dirty index"               $([[ $RC -ne 0 ]] && has 'index is dirty'; echo $?) "rc=$RC $OUT"
chk "A5 the pre-staged change is STILL staged"  $([[ "$(G diff --cached --name-only)" == "README.md" ]]; echo $?) "$(G diff --cached --name-only)"
chk "A5 a5.txt was not staged by the refused run" $(! G diff --cached --name-only | grep -q a5.txt; echo $?)
clean_tree

echo "=== gate 1: append-only under working/results/"
echo '{"measured": 2}' > "$REPO/working/results/existing.json"
run_al "$BASE_OK" --dry-run "m" working/results/existing.json
chk "gate 1 REFUSES a modification of an existing artifact" $([[ $RC -ne 0 ]] && has 'append-only violation'; echo $?) "rc=$RC $OUT"
chk "gate 1 refusal restores a clean index"     $([[ -z "$(G diff --cached --name-only)" ]]; echo $?)
chk "gate 1 refusal leaves the working-tree edit alone (not ours to discard)" $(grep -q '"measured": 2' "$REPO/working/results/existing.json"; echo $?)
clean_tree
git -C "$REPO" mv working/results/existing.json working/results/renamed.json >/dev/null 2>&1; G reset -q
run_al "$BASE_OK" --dry-run "m" working/results/existing.json working/results/renamed.json
chk "gate 1 REFUSES a rename/delete of an artifact" $([[ $RC -ne 0 ]] && has 'append-only violation'; echo $?) "rc=$RC"
clean_tree
echo '{"new": true}' > "$REPO/working/results/new_artifact.json"
run_al "$BASE_OK" --dry-run "m" working/results/new_artifact.json
chk "gate 1 clean twin: a NEW artifact passes (rc 0)" $([[ $RC -eq 0 ]] && has 'DRY RUN'; echo $?) "rc=$RC $OUT"
clean_tree

echo "=== gate 2: static undefined-name gate"
printf 'import os\n\ndef main():\n    if os.environ.get("X"):\n        return MISSING_NAME\n    return 0\n' > "$REPO/bad.py"
run_al "$BASE_OK" --dry-run "m" bad.py
chk "gate 2 REFUSES an undefined name in an untaken branch" $([[ $RC -ne 0 ]] && has 'static_names refused' && has 'MISSING_NAME'; echo $?) "rc=$RC $OUT"
clean_tree
printf 'import os\n\ndef main():\n    return os.getcwd()\n' > "$REPO/good.py"
run_al "$BASE_OK" --dry-run "m" good.py
chk "gate 2 clean twin passes"                  $([[ $RC -eq 0 ]] && has 'clean over 1 changed python'; echo $?) "rc=$RC $OUT"
clean_tree
G rm -q good.py 2>/dev/null || true; clean_tree
# a staged DELETION of a .py must not crash the gate into a false refusal
printf 'x = 1\n' > "$REPO/gone.py"; G add gone.py; G commit -q -m "add gone.py"; rm "$REPO/gone.py"
run_al "$BASE_OK" --dry-run "m" gone.py
chk "gate 2 a staged .py deletion is skipped, not crashed on" $([[ $RC -eq 0 ]] && has 'no python changed'; echo $?) "rc=$RC $OUT"
clean_tree

echo "=== gate 3: suite against the baseline"
echo "x" > "$REPO/g3.txt"
run_al "FAKE_FAILS=thread_settings_matched" --dry-run "m" g3.txt
chk "gate 3 a baselined failure ALONE does not refuse" $([[ $RC -eq 0 ]]; echo $?) "rc=$RC $OUT"
chk "gate 3 prints the baselined set every run" $(has 'baselined failures' && has 'thread_settings_matched  \[since'; echo $?) "$OUT"
run_al "FAKE_FAILS=thread_settings_matched injected_new_failure" --dry-run "m" g3.txt
chk "gate 3 REFUSES an injected new failure, naming it" $([[ $RC -ne 0 ]] && has 'NEW failure' && has 'injected_new_failure'; echo $?) "rc=$RC $OUT"
run_al "FAKE_FAILS=" --dry-run "m" g3.txt
chk "gate 3 REFUSES when a baselined test starts PASSING" $([[ $RC -ne 0 ]] && has 'now PASS'; echo $?) "rc=$RC $OUT"
run_al "FAKE_CRASH=1" --dry-run "m" g3.txt
chk "gate 3 REFUSES a runner that crashed before its summary" $([[ $RC -ne 0 ]] && has 'did not print its summary'; echo $?) "rc=$RC $OUT"
mv "$REPO/working/harness/suite_baseline.json" "$TMP/bl.bak"
run_al "$BASE_OK" --dry-run "m" g3.txt
chk "gate 3 REFUSES when the baseline file is absent" $([[ $RC -ne 0 ]] && has 'suite_baseline.json is absent'; echo $?) "rc=$RC"
mv "$TMP/bl.bak" "$REPO/working/harness/suite_baseline.json"
clean_tree

echo "=== gate 4: figure guard over prose"
echo "RocketRide peakRSS was 84,960.6 MB on the 10k run." > "$REPO/working/docs/bare.md"
run_al "$BASE_OK" --dry-run "m" working/docs/bare.md
chk "gate 4 REFUSES a bare never-quote figure" $([[ $RC -ne 0 ]] && has 'figure_guard refused' && has 'summed-rss-85g'; echo $?) "rc=$RC $OUT"
chk "gate 4 ran its own null control first"    $(has 'NULL CONTROL PASSED'; echo $?)
clean_tree
printf 'RocketRide peakRSS read 84,960.6 MB — a summing artifact against a 58 GB cap; never quote it.\n' > "$REPO/working/docs/caveated.md"
run_al "$BASE_OK" --dry-run "m" working/docs/caveated.md
chk "gate 4 clean twin: the caveated figure passes" $([[ $RC -eq 0 ]] && has 'FIGURE GUARD: clean'; echo $?) "rc=$RC $OUT"
chk "gate 4 base is origin/<branch> when it exists" $(has 'base: .*\(origin/video-bench\)'; echo $?) "$OUT"
clean_tree
printf 'Its provenance block says "duplication_patch_applied": false on the 18-Aug run.\n' > "$REPO/working/docs/dup.md"
run_al "$BASE_OK" --dry-run "m" working/docs/dup.md
chk "gate 4 REFUSES the false patch assertion (field paired with False)" $([[ $RC -ne 0 ]] && has 'dup-patch-false'; echo $?) "rc=$RC $OUT"
clean_tree
printf 'The export records duplication_patch_applied = True, read from the image label.\n' > "$REPO/working/docs/dup_ok.md"
run_al "$BASE_OK" --dry-run "m" working/docs/dup_ok.md
chk "gate 4 the field name alone (True, label-read) is quotable" $([[ $RC -eq 0 ]]; echo $?) "rc=$RC $OUT"
clean_tree

echo "=== A4: base fallback when origin/<branch> does not exist"
G checkout -q -b docs-bench-sim
echo "x" > "$REPO/a4.txt"
run_al "$BASE_OK" --dry-run "m" a4.txt
chk "A4 no origin/<branch>: base is merge-base with origin/video-bench" $([[ $RC -eq 0 ]] && has 'merge-base\(HEAD, origin/video-bench\)'; echo $?) "rc=$RC $OUT"
chk "A4 gate 0 announces the first push"       $(has 'first push'; echo $?)
clean_tree
# a repo whose origin has none of the known branches at all -> HEAD
REPO2="$TMP/repo2"; ORIGIN2="$TMP/origin2.git"; git init -q --bare "$ORIGIN2"; git init -q -b trunk "$REPO2"
git -C "$REPO2" config user.email s@l; git -C "$REPO2" config user.name s
mkdir -p "$REPO2/working/harness" "$REPO2/working/scripts"; cp "$SELF/static_names.py" "$SELF/figure_guard.py" "$REPO2/working/harness/"
cp "$REPO/working/scripts/regression_selftest.py" "$REPO2/working/scripts/"; cp "$REPO/working/harness/suite_baseline.json" "$REPO2/working/harness/"
git -C "$REPO2" add -A >/dev/null; git -C "$REPO2" commit -q -m init; git -C "$REPO2" remote add origin "$ORIGIN2"; git -C "$REPO2" push -q -u origin trunk
git -C "$REPO2" checkout -q -b feature; echo x > "$REPO2/f.txt"
OUT="$(cd "$REPO2" && env AUTOLAND_NO_LOG=1 PYBIN="$PY" FAKE_FAILS=thread_settings_matched bash "$AUTOLAND" --dry-run "m" f.txt 2>&1)"; RC=$?
chk "A4 no known origin branch at all: base falls back to HEAD" $([[ $RC -eq 0 ]] && has 'base: .*\(HEAD'; echo $?) "rc=$RC $OUT"

echo "=== gates 5/6/7 for real, against the local bare origin"
G checkout -q video-bench; clean_tree
echo "landed" > "$REPO/land.txt"
run_al "$BASE_OK" "land it" land.txt
chk "landing on an existing upstream: rc 0 and LANDED" $([[ $RC -eq 0 ]] && has 'AUTOLAND: LANDED'; echo $?) "rc=$RC $OUT"
chk "origin's branch head equals local HEAD"    $([[ "$(git -C "$ORIGIN" rev-parse video-bench)" == "$(G rev-parse HEAD)" ]]; echo $?)
chk "the commit carries the given message"      $([[ "$(G log -1 --format=%s)" == "land it" ]]; echo $?)
# A6: first push of a branch sets upstream
G checkout -q -b docs-bench-sim2; echo "first" > "$REPO/first.txt"
run_al "$BASE_OK" "first landing of docs-bench-sim2" first.txt
chk "A6 first push of a new branch lands (rc 0)" $([[ $RC -eq 0 ]] && has 'AUTOLAND: LANDED' && has 'setting upstream'; echo $?) "rc=$RC $OUT"
chk "A6 upstream is set to origin/docs-bench-sim2" $([[ "$(G rev-parse --abbrev-ref 'docs-bench-sim2@{u}' 2>/dev/null)" == "origin/docs-bench-sim2" ]]; echo $?) "$(G rev-parse --abbrev-ref 'docs-bench-sim2@{u}' 2>&1)"
chk "A6 origin reports the new branch at HEAD"  $([[ "$(git -C "$ORIGIN" rev-parse docs-bench-sim2)" == "$(G rev-parse HEAD)" ]]; echo $?)
# --verify on a landed HEAD, and on an unlanded one
run_al --verify
chk "--verify reports LANDED on a landed HEAD"  $([[ $RC -eq 0 ]] && has 'AUTOLAND: LANDED'; echo $?) "rc=$RC $OUT"
echo "local only" > "$REPO/unlanded.txt"; G add unlanded.txt; G commit -q -m "unlanded"
run_al --verify
chk "--verify REFUSES an unlanded HEAD"         $([[ $RC -ne 0 ]] && has 'Not landed'; echo $?) "rc=$RC $OUT"
G reset -q --hard HEAD~1

echo "=== entry 26: a claimed base is never pushed onto"
CLONE="$TMP/clone"; git clone -q "$ORIGIN" "$CLONE"; git -C "$CLONE" config user.email c@l; git -C "$CLONE" config user.name c
git -C "$CLONE" checkout -q video-bench; echo "elsewhere" > "$CLONE/elsewhere.txt"; git -C "$CLONE" add elsewhere.txt; git -C "$CLONE" commit -q -m "landed from elsewhere"; git -C "$CLONE" push -q origin video-bench
G checkout -q video-bench; echo "mine" > "$REPO/mine.txt"; G add mine.txt; G commit -q -m "mine, on a stale base"; echo "y" > "$REPO/y.txt"
run_al "$BASE_OK" "m" y.txt
chk "entry 26: REFUSES when origin/<branch> is not an ancestor of HEAD" $([[ $RC -ne 0 ]] && has 'CLAIMED'; echo $?) "rc=$RC $OUT"
chk "entry 26: refusal happens before any commit (HEAD unchanged)" $([[ "$(G log -1 --format=%s)" == "mine, on a stale base" ]]; echo $?)
chk "entry 26: refusal leaves the index clean"  $([[ -z "$(G diff --cached --name-only)" ]]; echo $?)
G merge -q --no-edit origin/video-bench >/dev/null 2>&1   # the sanctioned repair: an as-is merge
run_al "$BASE_OK" "after the merge" y.txt
chk "entry 26: after an as-is merge the landing proceeds" $([[ $RC -eq 0 ]] && has 'AUTOLAND: LANDED'; echo $?) "rc=$RC $OUT"

echo "=== gate 7: a push that origin does not agree with"
# post-receive on the bare origin reverts every ref it just accepted: the push
# reports success, ls-remote reports the OLD sha. Exactly the divergence entry 26 names.
cat > "$ORIGIN/hooks/post-receive" <<'HEOF'
#!/bin/sh
while read old new ref; do git update-ref "$ref" "$old"; done
HEOF
chmod +x "$ORIGIN/hooks/post-receive"
echo "z" > "$REPO/z.txt"
run_al "$BASE_OK" "should not be proven" z.txt
chk "gate 7 REFUSES when ls-remote disagrees with the pushed sha (rc non-zero)" $([[ $RC -ne 0 ]] && has 'landing not proven'; echo $?) "rc=$RC $OUT"
chk "gate 7 printed both shas"                   $(has 'local : ' && has 'origin: '; echo $?)
rm -f "$ORIGIN/hooks/post-receive"

echo
echo "self-test: $OK pass, $BAD fail"
[[ "$BAD" -eq 0 ]]
