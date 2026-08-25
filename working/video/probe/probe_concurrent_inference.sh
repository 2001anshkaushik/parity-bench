#!/usr/bin/env bash
# CONCURRENT-INFERENCE PROBE (2026-08-24) — Leela's gap: M task PROCESSES were
# proven (census, distinct pids); M concurrent INFERENCES were not. This
# measures the latter directly: sample /proc/<pid>/stat for every task process
# at ~1 s ticks during a small blast and report the distribution of "how many
# task processes were simultaneously burning CPU" (busy = >=0.3 cores in the
# tick). Detection dominates task CPU (Leela's split: detect ~92%), so
# simultaneous busy processes ~= simultaneous inferences.
#
#   bash probe_concurrent_inference.sh <container> <out.tsv> &   # start sampler
#   ... run the small blast ...
#   kill %1; python3 probe_concurrent_inference_summary.py <out.tsv> <M>
set -euo pipefail
C="${1:?container}"; OUT="${2:?out.tsv}"
: > "$OUT"
while :; do
  PIDS=$(docker exec "$C" ps -eo pid,args 2>/dev/null | awk '/node\.py/ {printf "%s ", $1}')
  [ -n "$PIDS" ] || { sleep 1; continue; }
  TICK=$(date +%s)
  # one exec per tick: pid utime stime (fields 14,15 of /proc/<pid>/stat)
  docker exec "$C" sh -c "for p in $PIDS; do awk '{print \"$TICK\", FILENAME, \$14+\$15}' /proc/\$p/stat 2>/dev/null; done" >> "$OUT" || true
  sleep 1
done
