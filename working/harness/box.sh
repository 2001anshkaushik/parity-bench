#!/usr/bin/env bash
# box.sh — laptop-side entrypoint for the WS-1 benchmark box (i-0775f33f3dc16f6af).
#
# FORM CREDIT: adopted from Leela's aws_bench/local/box.sh @ her pin 3967d9f4
# (Ansh's ruling 2026-09-03: adopt her proven form; contest nothing about it
# without a measurement). Her team already paid for the traps this file
# inherits unchanged:
#   * The pty is LOAD-BEARING: `script -q /dev/null` allocates one. Since the
#     SSM agent 3.3.4793.0 auto-update, no-TTY piped sessions die instantly
#     ("Cannot perform start session: EOF") AND stay Connected server-side —
#     25 leaked sessions hit the per-instance cap and LOCK THE BOX OUT
#     (terminate-session may be DENIED to the role; only stop/start or the
#     idle timeout clears them).
#   * The remote exit code travels as an `__RC=<n>` marker echoed after the
#     command, scraped locally, re-raised; the pty's \r are stripped.
#   * Long jobs never sit in a session: `launch` fires
#     `nohup … > ~/logs/<name>.log &` through the same pipe.
#   * Her experimental `runx` (AWS-StartInteractiveCommand) is NOT adopted —
#     her own file marks it "test first"; untested on our role.
#
# OUR ADDITIONS (not in her form):
#   1. HARD REFUSAL LIST — every command is checked BEFORE anything is sent;
#      a match refuses, printing the matched pattern. Ansh's standing rule:
#      anything destructive or publicly visible stops for HIS manual approval
#      — this wrapper refuses and reports; it never asks itself for
#      permission. The highest-value irreplaceable object on the box is the
#      rr:patched-video image: it is NOT bit-reproducible (its deferred
#      rebuild would re-resolve a floating base and unpinned libs), and every
#      RocketRide number in BOTH campaigns (AMI + Films) was measured on it.
#      Nothing that could delete or overwrite images, corpora, or results
#      goes through this wrapper.
#   2. TRANSCRIPT — every command, its exit code and its full output are
#      appended with a UTC stamp to ~/.rocketride_box/transcript_<day>.log.
#      The transcript is the evidence surface: figures are quoted from it,
#      never from recollection.
#   3. SESSION HYGIENE — the active SSM session count is reported against the
#      per-instance cap before every run and REFUSES above SAFE_SESSIONS
#      (20 of 25). If DescribeSessions is denied to our role the count prints
#      UNKNOWN and the run proceeds with that stated (refusing on an
#      unknowable would brick the wrapper); our own sessions always end with
#      an explicit `exit`.
#
# STANDING RULES carried into enforcement:
#   * never export AWS_PROFILE on the box (refused pattern);
#   * sso login / start-instances / start-session are LAPTOP-side — this file
#     is that laptop side;
#   * long blocks go to the box as committed scripts with a self-printed sha
#     (entry 25) — `run` and `launch` REFUSE multi-line commands.
#
# Usage:
#   box.sh login                     SSO login (opens browser, human approves)
#   box.sh status                    instance state + SSM ping + session count
#   box.sh start                     start instance, wait until SSM Online
#   box.sh stop                      stop instance (disk survives)
#   box.sh shell                     interactive SSM shell (for humans)
#   box.sh run  [--start] '<cmd>'    one-shot command (single-line only)
#   box.sh launch [--start] <name> '<cmd>'  long run: nohup, log ~/logs/<name>.log
#     --start (opt-in, NEVER default): if the box is stopped, start it, wait
#     for instance-running, then poll DescribeInstanceInformation until the
#     SSM agent reads Online before opening the session. Default OFF so a
#     stopped box stays a visible fact unless the caller asked.
#   box.sh tail <name> [lines]       tail that log (default 50)
#   box.sh ps                        running launched jobs on the box
#   box.sh sessions                  active SSM session count vs the cap
#   box.sh self-test                 laptop-only checks; touches no box
set -euo pipefail

echo "box.sh sha256: $( (shasum -a 256 "$0" 2>/dev/null || sha256sum "$0") | cut -d' ' -f1 )" >&2

PROFILE="${BOX_PROFILE:-rocketride}"
INSTANCE="${BOX_INSTANCE:-i-0775f33f3dc16f6af}"
A=(aws --profile "$PROFILE")
[ -n "${BOX_REGION:-}" ] && A+=(--region "$BOX_REGION")
SAFE_SESSIONS="${BOX_SAFE_SESSIONS:-20}"   # cap is 25; refuse before we can contribute to a lockout
TRANSCRIPT_DIR="${BOX_TRANSCRIPT_DIR:-$HOME/.rocketride_box}"

die() { echo "box.sh: $*" >&2; exit 1; }

state() {
  "${A[@]}" ec2 describe-instances --instance-ids "$INSTANCE" \
    --query 'Reservations[0].Instances[0].State.Name' --output text
}

ssm_online() {
  "${A[@]}" ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || echo none
}

sessions_count() {
  "${A[@]}" ssm describe-sessions --state Active \
    --filters "key=Target,value=$INSTANCE" \
    --query 'length(Sessions)' --output text 2>/dev/null || echo UNKNOWN
}

# ---------- addition 1: the hard refusal list ----------------------------
REFUSE_LABELS=(
  'rm -rf'
  'rm -r/-f split flags'
  'docker rmi'
  'docker image rm'
  'docker system prune'
  'docker builder prune'
  'aws s3 rm'
  'aws s3 mv'
  'git push --force'
  'git reset --hard'
  'dd'
  'mkfs'
  'shutdown'
  'reboot'
  'truncate'
  'export AWS_PROFILE on the box'
  'redirect into a corpus/results path'
  'redirect into a corpus/results path'
)
REFUSE_PATS=(
  'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*f|rm[[:space:]]+-[a-zA-Z]*f[a-zA-Z]*[rR]'
  'rm[[:space:]]+-[rR][[:space:]]+-f|rm[[:space:]]+-f[[:space:]]+-[rR]'
  'docker[[:space:]]+rmi'
  'docker[[:space:]]+image[[:space:]]+rm'
  'docker[[:space:]]+system[[:space:]]+prune'
  'docker[[:space:]]+builder[[:space:]]+prune'
  'aws[[:space:]]+s3[[:space:]]+rm'
  'aws[[:space:]]+s3[[:space:]]+mv'
  'git[[:space:]]+push[[:space:]]+.*(--force|-f([[:space:]]|$))'
  'git[[:space:]]+reset[[:space:]]+.*--hard'
  '(^|[;&|[:space:](])dd([[:space:]]|$)'
  '(^|[;&|[:space:](])mkfs'
  '(^|[;&|[:space:](])shutdown([[:space:]]|$)'
  '(^|[;&|[:space:](])reboot([[:space:]]|$)'
  '(^|[;&|[:space:](])truncate([[:space:]]|$)'
  'export[[:space:]]+AWS_PROFILE'
  '>[[:space:]]*((films_)?corpus|results)/'
  '>[^|;&]*[/~[:space:]]((films_)?corpus|results)(/|[[:space:]]|$)'
)

refuse_check() {  # $1 = command string; 0 = clean, 1 = refused (reason printed)
  local cmd="$1" i
  case "$cmd" in
    *$'\n'*)
      echo "REFUSED (long block): multi-line command — long blocks go to the box as committed scripts with a self-printed sha (entry 25), never inline."
      return 1;;
  esac
  for i in "${!REFUSE_PATS[@]}"; do
    if printf '%s' "$cmd" | grep -qE "${REFUSE_PATS[$i]}"; then
      echo "REFUSED (${REFUSE_LABELS[$i]}): matches refusal pattern '${REFUSE_PATS[$i]}'"
      echo "Standing rule: destructive or publicly-visible actions stop for Ansh's manual approval — this wrapper never asks itself for permission."
      return 1
    fi
  done
  return 0
}

# ---------- addition 2: the transcript ----------------------------------
transcript() {  # $1 cmd  $2 rc  $3 output
  mkdir -p "$TRANSCRIPT_DIR"
  local f="$TRANSCRIPT_DIR/transcript_$(date -u +%Y%m%d).log"
  {
    printf '=== %s ===\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '$ %s\n' "$1"
    printf '%s\n' "$3"
    printf '__rc=%s\n\n' "$2"
  } >> "$f"
  echo "transcript: $f" >&2
}

# ---------- addition 3: session hygiene ---------------------------------
session_guard() {
  local n
  n=$(sessions_count)
  if [ "$n" = "UNKNOWN" ]; then
    echo "sessions: UNKNOWN (DescribeSessions denied or unavailable) — proceeding; hygiene rests on our own explicit exits" >&2
    return 0
  fi
  echo "sessions: $n active (cap 25, refuse threshold $SAFE_SESSIONS)" >&2
  if [ "$n" -ge "$SAFE_SESSIONS" ] 2>/dev/null; then
    die "REFUSED (session hygiene): $n active sessions >= $SAFE_SESSIONS — leaked sessions cap-lock the box (Leela's measured incident); clear them (stop/start or idle timeout) before running"
  fi
}

# ---------- her form: the piped one-shot --------------------------------
parse_rc() {  # $1 = session output; prints rc or returns 1
  local rc
  rc=$(printf '%s\n' "$1" | grep -o '__RC=[0-9]*' | tail -1 | cut -d= -f2)
  [ -n "${rc:-}" ] || return 1
  printf '%s' "$rc"
}

# Three different failures must never read as one (2026-09-03 ruling: a
# wrapper an agent drives unattended never reports a diagnosable condition
# as an unknown one). Detected from the captured session output.
diagnose_failure() {  # $1 = session output; prints one actionable line
  local o="$1"
  if printf '%s' "$o" | grep -qiE 'token.*(expired|invalid)|error when retrieving token|sso session.*expired'; then
    echo "SSO token expired — run: aws sso login --profile $PROFILE   (or: box.sh login)"
  elif printf '%s' "$o" | grep -qiE 'TargetNotConnected|is not connected'; then
    echo "the box is stopped or unreachable (TargetNotConnected) — run: box.sh start   (or rerun with --start)"
  else
    echo "no exit marker in session output and no known failure signature matched — session may not have opened; read the output above"
  fi
}

pipe_run() {
  local cmd="$1" out rc
  refuse_check "$cmd" || exit 3
  session_guard
  out=$({ sleep 3; printf '%s\n' "$cmd" 'echo "__RC=$?"' 'exit'; } \
        | script -q /dev/null "${A[@]}" ssm start-session --target "$INSTANCE" 2>&1 \
        | tr -d '\r') || true
  printf '%s\n' "$out"
  if ! rc=$(parse_rc "$out"); then
    transcript "$cmd" "NO_MARKER" "$out"
    die "$(diagnose_failure "$out")"
  fi
  transcript "$cmd" "$rc" "$out"
  return "$rc"
}

# --start support (opt-in, never default: a stopped box stays a VISIBLE
# fact unless the caller asked). The PingStatus poll is the step that
# matters — instance-running lands well before the SSM agent registers.
start_flag() { [ "${1:-}" = "--start" ] && echo 1 || echo 0; }

ensure_online() {
  local s tries="${BOX_POLL_TRIES:-30}" slp="${BOX_POLL_SLEEP:-5}" i
  s=$(state)
  if [ "$s" != "running" ]; then
    echo "starting instance ($s)..." >&2
    "${A[@]}" ec2 start-instances --instance-ids "$INSTANCE" >/dev/null
    "${A[@]}" ec2 wait instance-running --instance-ids "$INSTANCE"
  fi
  echo -n "waiting for SSM agent" >&2
  for i in $(seq 1 "$tries"); do
    if [ "$(ssm_online)" = "Online" ]; then echo " — Online" >&2; return 0; fi
    echo -n "." >&2; sleep "$slp"
  done
  echo "" >&2
  die "SSM agent not Online after $((tries * slp))s — refusing to open a session (the agent registers well after instance-running; box.sh status, then retry)"
}

# ---------- laptop-only self-test (touches no box) ----------------------
self_test() {
  local ok=0 fail=0
  chk() { if eval "$2"; then echo "  PASS  $1"; ok=$((ok+1)); else echo "  FAIL  $1"; fail=$((fail+1)); fi; }

  local refusals=(
    'rm -rf /home/ssm-user/films_probe'
    'sudo rm -fR ~/x'
    'rm -r -f ~/x'
    'docker rmi rr:patched-video'
    'docker image rm li:video'
    'docker system prune -f'
    'docker builder prune -f'
    'aws s3 rm s3://rocketride-benchmark-data/x'
    'aws s3 mv s3://a s3://b'
    'git push --force origin video-bench'
    'git push -f'
    'git reset --hard HEAD~3'
    'dd if=/dev/zero of=/dev/nvme0n1'
    'mkfs.ext4 /dev/nvme1n1'
    'shutdown -h now'
    'sudo reboot'
    'truncate -s 0 big.log'
    'export AWS_PROFILE=rocketride'
    'echo x > results/notes.txt'
    'cat a >> ~/parity-bench-video/working/video/results/x.json'
    'cmd > ~/films_corpus/subset/f.mp4'
    'echo hi > corpus/ami/full/EN2001a.avi'
  )
  names_pattern() {  # pipefail-safe: capture, then grep
    local o; o=$(refuse_check "$1" || true)
    printf '%s' "$o" | grep -q 'refusal pattern'
  }
  local r
  for r in "${refusals[@]}"; do
    chk "refuses: $r" "! refuse_check \"\$r\" >/dev/null"
    chk "names the pattern: $r" "names_pattern \"\$r\""
  done

  local nulls=(
    'git -C ~/parity-bench-video rev-parse HEAD'
    'ls -la ~/films_probe'
    'docker images'
    'docker ps -a'
    'aws s3 ls s3://rocketride-benchmark-data/ansh/'
    'echo hi > /tmp/scratch.txt'
    'grep -c results/foo notes.md'
    'ls added_files reddish'
    'tail -n 50 ~/logs/run.log'
    'df -h'
  )
  local n
  for n in "${nulls[@]}"; do
    chk "passes null control: $n" "refuse_check \"\$n\" >/dev/null"
  done

  chk "refuses multi-line" "! refuse_check \$'echo a\necho b' >/dev/null"
  chk "marker parse: extracts last __RC" "[ \"\$(parse_rc \$'noise\n__RC=0\nmore\n__RC=7')\" = 7 ]"
  chk "marker parse: missing marker fails" "! parse_rc 'no marker here' >/dev/null"

  chk "diagnose: expired token -> sso login remedy" \
    "diagnose_failure 'Error when retrieving token from sso: Token has expired and refresh failed' | grep -q 'aws sso login'"
  chk "diagnose: TargetNotConnected -> box.sh start remedy" \
    "diagnose_failure 'An error occurred (TargetNotConnected) when calling the StartSession operation: i-0775f33f3dc16f6af is not connected.' | grep -q 'box.sh start'"
  chk "diagnose: unknown output -> no-marker message" \
    "diagnose_failure 'some pty noise with no signatures' | grep -q 'no exit marker'"
  chk "diagnose: unknown output does NOT claim a remedy" \
    "! diagnose_failure 'some pty noise' | grep -qE 'sso login|box.sh start'"

  chk "start_flag: --start -> 1" "[ \"\$(start_flag --start)\" = 1 ]"
  chk "start_flag: command -> 0" "[ \"\$(start_flag 'git status')\" = 0 ]"
  chk "start_flag: empty -> 0" "[ \"\$(start_flag '')\" = 0 ]"

  chk "ensure_online: refuses on poll timeout (stubbed)" \
    "! ( state(){ echo running; }; ssm_online(){ echo none; }; BOX_POLL_TRIES=2 BOX_POLL_SLEEP=0 ensure_online ) >/dev/null 2>&1"
  chk "ensure_online: timeout message says not Online (stubbed)" \
    "o=\$( ( state(){ echo running; }; ssm_online(){ echo none; }; BOX_POLL_TRIES=2 BOX_POLL_SLEEP=0 ensure_online ) 2>&1 || true ); printf '%s' \"\$o\" | grep -q 'not Online'"
  chk "ensure_online: succeeds when agent Online (stubbed, no aws call)" \
    "( state(){ echo running; }; ssm_online(){ echo Online; }; BOX_POLL_TRIES=2 BOX_POLL_SLEEP=0 ensure_online ) >/dev/null 2>&1"

  local td; td=$(mktemp -d)
  TRANSCRIPT_DIR="$td" transcript 'echo demo' 0 'demo-output' 2>/dev/null
  chk "transcript file written" "ls \"$td\"/transcript_*.log >/dev/null 2>&1"
  chk "transcript carries stamp+cmd+rc" "grep -q 'echo demo' \"$td\"/transcript_*.log && grep -q '__rc=0' \"$td\"/transcript_*.log && grep -qE '=== [0-9]{4}-' \"$td\"/transcript_*.log"
  rm -r "$td"

  echo "self-test: $ok pass, $fail fail"
  [ "$fail" -eq 0 ]
}

# ---------- dispatch (her shape) ----------------------------------------
case "${1:-}" in
  login)
    exec aws sso login --profile "$PROFILE"
    ;;
  status)
    echo "instance: $INSTANCE  state: $(state)  ssm: $(ssm_online)  sessions: $(sessions_count)"
    ;;
  start)
    ensure_online
    ;;
  stop)
    "${A[@]}" ec2 stop-instances --instance-ids "$INSTANCE" >/dev/null
    echo "stop requested (disk survives; box.sh start to resume)"
    ;;
  shell)
    exec "${A[@]}" ssm start-session --target "$INSTANCE"
    ;;
  run)
    shift
    START=$(start_flag "${1:-}"); [ "$START" = 1 ] && shift
    [ $# -ge 1 ] || die "usage: box.sh run [--start] '<cmd>'"
    [ "$START" = 1 ] && ensure_online
    pipe_run "$1"
    ;;
  launch)
    shift
    START=$(start_flag "${1:-}"); [ "$START" = 1 ] && shift
    [ $# -ge 2 ] || die "usage: box.sh launch [--start] <name> '<cmd>'"
    name="$1"; cmd="$2"
    refuse_check "$cmd" || exit 3
    [ "$START" = 1 ] && ensure_online
    q=$(printf '%q' "$cmd")
    pipe_run "mkdir -p ~/logs && nohup bash -c $q > ~/logs/$name.log 2>&1 & echo launched $name pid \$!"
    ;;
  tail)
    [ $# -ge 2 ] || die "usage: box.sh tail <name> [lines]"
    pipe_run "tail -n ${3:-50} ~/logs/$2.log"
    ;;
  ps)
    pipe_run "pgrep -af 'bash -c' || echo '(no launched jobs)'"
    ;;
  sessions)
    echo "sessions: $(sessions_count) active (cap 25, refuse threshold $SAFE_SESSIONS)"
    ;;
  self-test)
    self_test
    ;;
  *)
    sed -n '/^# Usage:/,/^set -euo/p' "$0" | sed '$d;s/^# \{0,1\}//'; exit 1
    ;;
esac
