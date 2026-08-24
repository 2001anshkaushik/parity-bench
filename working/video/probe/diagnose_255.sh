#!/usr/bin/env bash
# Q1 DISCRIMINATOR — is the "returncode 255" line the cause, or normal noise?
#
# The line is verbatim CPython asyncio/unix_events.py, _ThreadedChildWatcher /
# _PidfdChildWatcher, whose own comment reads "(may happen if waitpid() is
# called elsewhere)". 255 is a SENTINEL the watcher substitutes when the exit
# status was already reaped by someone else — NOT the task's exit code. So the
# first question is whether it also appears in legs that finished clean.
#
# Usage:  ./diagnose_255.sh <run_dir>        e.g. working/video/results/mainrun_...
set -euo pipefail
RUN="${1:?usage: diagnose_255.sh <run_dir>}"
echo "=== 1. Does the 255 line appear in legs that PASSED? (if yes: red herring) ==="
for f in "$RUN"/dockerlog_rr_*.txt; do
  [ -f "$f" ] || continue
  printf '%-52s 255-lines=%s\n' "$(basename "$f")" "$(grep -c 'returncode 255' "$f" || true)"
done
echo
echo "=== 2. The LIVE container's full log, everything BEFORE the first 255 ==="
echo "    (this is the part that was never read; the cause is here if anywhere)"
docker logs rr > /tmp/rr_full.log 2>&1 || true
echo "    total lines: $(wc -l < /tmp/rr_full.log)"
FIRST=$(grep -n 'returncode 255' /tmp/rr_full.log | head -1 | cut -d: -f1 || true)
if [ -n "${FIRST:-}" ]; then
  echo "    first 255 at line $FIRST — 120 lines of context before it:"
  sed -n "$(( FIRST > 120 ? FIRST-120 : 1 )),${FIRST}p" /tmp/rr_full.log
else
  echo "    no 255 line in the live container log"
fi
echo
echo "=== 3. The four things that would each be a DIFFERENT cause ==="
for pat in Traceback 'MemoryError' 'Killed' 'SIGKILL' 'SIGSEGV' 'OOM' 'ttl' 'expire' 'timeout' \
           'Too many open files' 'EMFILE' 'Connection reset' 'BrokenPipe' 'already running'; do
  n=$(grep -ic "$pat" /tmp/rr_full.log || true)
  [ "$n" = "0" ] || printf '  %-22s %s hit(s)\n' "$pat" "$n"
done
echo
echo "=== 4. Every traceback in full (the actual exception, if there is one) ==="
grep -n -A 25 'Traceback (most recent call last)' /tmp/rr_full.log | head -120 || echo "  none"
echo
echo "=== 5. Did the task process die, or is it still there? ==="
docker exec rr sh -c 'ls -1 /proc | grep -E "^[0-9]+$" | while read p; do
  printf "%s %s\n" "$p" "$(tr "\0" " " < /proc/$p/cmdline 2>/dev/null | cut -c1-90)"; done' 2>/dev/null \
  || echo "  (container not running or exec refused)"
echo
echo "=== 6. TTL SEMANTICS — idle timeout or absolute lifetime? (decides Q2) ==="
docker exec rr sh -c 'grep -rn "ttl" --include=task_server.py / 2>/dev/null | head -20' \
  || echo "  (could not read task_server.py in the container)"
