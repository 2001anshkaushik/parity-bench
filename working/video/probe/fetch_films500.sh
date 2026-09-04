#!/usr/bin/env bash
# fetch_films500.sh v2 — BOX-SIDE. Stage the frozen archive_films_v2 500 into
# ~/films_corpus/full500: subset reuse by hardlink, EVERY file sha256-verified
# against Leela's canonical corpus_manifest.json (itself verified against the
# frozen sha bd0c915e). Fail-closed; nothing deleted, ever. RESUMABLE: a
# present file with a matching sha is SKIPPED (the first branch); a partial
# (size/sha mismatch) is re-fetched and overwritten.
#
# v2 (2026-09-04) after run 1 died to the box's IDLE WATCHDOG — the failure
# Leela's runbook names ("every runner starts its own keepalive") and v1
# omitted; owned:
#   * KEEPALIVE, bounded and SELF-TERMINATING (the standing rule — the
#     unbounded respawning form contaminated the 18-Aug runs): N background
#     `timeout <s> md5sum /dev/zero` burners, NO respawn parent — they die
#     on their own even if this script is killed; killed early on success.
#     Sized 7200 s (>=4x the projected parallel wall). The script prints
#     that a keepalive is running and when it expires.
#   * PARALLEL fetch: run-1 measured ~11-20 MB/s effective single-stream
#     (54.9 GB in <=85 min before the watchdog) => ~3-5 h sequential for
#     the remaining ~197 GB. 12 parallel per-file workers keep the
#     per-file correctness surface IDENTICAL (skip-if-verified /
#     hardlink-if-subset / cp + sha verify) and should land NIC/EBS-bound
#     (~150-400 MB/s aggregate, ~10-25 min projected; per-file walls are
#     PRINTED because aws cp stamps mtimes with S3 LastModified — run 1's
#     timing had to be bracketed from the transcript and boot record).
# Detach it:
#   box.sh launch fetch500 'bash ~/parity-bench-video/working/video/probe/fetch_films500.sh'
# Committed script + self-printed sha256 (entry 25).
set -euo pipefail
echo "fetch_films500.sh sha256: $(sha256sum "$0" | awk '{print $1}')"
echo "repo HEAD: $(git -C ~/parity-bench-video rev-parse --short HEAD 2>/dev/null || echo n/a)"

SRC="s3://rocketride-benchmark-data/leela/corpus/archive_films_v2"
DEST="$HOME/films_corpus/full500"
SUBSET="$HOME/films_corpus/subset"
MANIFEST_SHA_EXPECT="bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1"
FETCH_P="${FETCH_P:-12}"
KEEPALIVE_S="${KEEPALIVE_S:-7200}"
mkdir -p "$DEST"

echo "== canonical manifest (verified against the frozen sha) =="
aws s3 cp "$SRC/corpus_manifest.json" "$DEST/corpus_manifest.json" --quiet
GOT=$(sha256sum "$DEST/corpus_manifest.json" | awk '{print $1}')
[ "$GOT" = "$MANIFEST_SHA_EXPECT" ] || {
  echo "REFUSE: corpus_manifest.json sha $GOT != frozen $MANIFEST_SHA_EXPECT"; exit 3; }
echo "  manifest sha OK: $GOT"

python3 - "$DEST/corpus_manifest.json" > "$DEST/.filelist" <<'PYM'
import json, sys
m = json.load(open(sys.argv[1]))
sh = m.get('sha256') or m.get('files') or {}
if not isinstance(sh, dict) or not sh:
    print(f'REFUSE: unexpected manifest shape — top keys {sorted(m.keys())}', file=sys.stderr)
    raise SystemExit(3)
for name, rec in sorted(sh.items()):
    sha = rec['sha256'] if isinstance(rec, dict) else rec
    print(f'{sha} {name}')
PYM
N=$(wc -l < "$DEST/.filelist" | tr -d ' ')
echo "  manifest lists $N files"

echo "== KEEPALIVE: 2 bounded burners (timeout ${KEEPALIVE_S}s md5sum /dev/zero), NO respawn =="
echo "   running now; self-expire at $(date -u -d "+${KEEPALIVE_S} seconds" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
for _ in 1 2; do ( timeout "$KEEPALIVE_S" md5sum /dev/zero >/dev/null 2>&1 ) & done

fetch_one() {  # $1 = sha  $2 = name — the v1 per-file surface, unchanged
  local SHA="$1" NAME="$2" T t0 t1 sz
  [ $# -eq 2 ] || { echo "BAD-ARGS $*" >> "$DEST/.results"; return 0; }
  T="$DEST/$NAME"
  if [ -s "$T" ] && [ "$(sha256sum "$T" | awk '{print $1}')" = "$SHA" ]; then
    echo "OK $NAME" >> "$DEST/.results"; return 0
  fi
  if [ -s "$SUBSET/$NAME" ] && [ "$(sha256sum "$SUBSET/$NAME" | awk '{print $1}')" = "$SHA" ]; then
    ln -f "$SUBSET/$NAME" "$T"
    echo "LINKED $NAME" >> "$DEST/.results"; return 0
  fi
  t0=$(date +%s)
  aws s3 cp "$SRC/$NAME" "$T" --quiet || { echo "BAD $NAME (cp failed)" >> "$DEST/.results"; return 0; }
  if [ "$(sha256sum "$T" | awk '{print $1}')" = "$SHA" ]; then
    t1=$(date +%s); sz=$(stat -c %s "$T")
    echo "  FETCHED $NAME $(awk -v b="$sz" 'BEGIN{printf "%.2fGB", b/1e9}') in $((t1-t0))s ($(awk -v b="$sz" -v s=$((t1-t0)) 'BEGIN{printf "%.0f", b/1e6/(s?s:1)}') MB/s)"
    echo "FETCHED $NAME" >> "$DEST/.results"
  else
    echo "BAD $NAME (sha mismatch after fetch)" >> "$DEST/.results"
  fi
}
export -f fetch_one
export SRC DEST SUBSET

: > "$DEST/.results"
echo "== stage: $FETCH_P parallel workers (per-file surface identical to v1) =="
T_START=$(date +%s)
xargs -a "$DEST/.filelist" -L1 -P "$FETCH_P" bash -c 'fetch_one "$@"' _
T_END=$(date +%s)

pkill -f "md5sum /dev/zero" 2>/dev/null || true
echo "keepalive burners stopped (or already self-expired)"

echo "== census =="
OK=$(grep -c '^OK ' "$DEST/.results" || true)
LINKED=$(grep -c '^LINKED ' "$DEST/.results" || true)
FETCHED=$(grep -c '^FETCHED ' "$DEST/.results" || true)
BAD=$(grep -c '^BAD' "$DEST/.results" || true)
TOTAL=$((OK + LINKED + FETCHED))
echo "verified=$TOTAL/$N (pre-verified=$OK hardlinked=$LINKED fetched=$FETCHED)  MISMATCHED_OR_FAILED=$BAD  wall=$((T_END-T_START))s"
grep '^BAD' "$DEST/.results" || true
MISSING=0
while read -r _SHA NAME; do
  [ -s "$DEST/$NAME" ] || { echo "MISSING: $NAME"; MISSING=$((MISSING+1)); }
done < "$DEST/.filelist"
du -sh "$DEST"; df -h /home/ssm-user | tail -1
[ "$BAD" -eq 0 ] && [ "$MISSING" -eq 0 ] && [ "$TOTAL" -eq "$N" ] || { echo "NOT DONE — census above says why (re-run resumes; verified files skip)"; exit 3; }
echo "DONE — $N/$N byte-verified against the frozen manifest in $((T_END-T_START))s."
