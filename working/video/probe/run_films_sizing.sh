#!/usr/bin/env bash
# =============================================================================
# Films sizing run — ONE film through the three postures (Ansh's ruling
# 2026-08-28: N comes from measurement, not AMI arithmetic). Committed script
# + self-printed sha256 per register entry 25.
#
# Cells (posture values MEASURED from the banked ami_full exports — see
# probe_films_sizing.py docstring): rr-default (1 token, env unset),
# rr-8x4 (8 tokens, six vars=4, threads kwarg NOT passed), li-8x4
# (8 single-worker li:video instances, env 4). Bring-up lines mirror
# overnight_apples.sh start_rr_set/start_li_set (reconstructed, corroborated
# by the banked exports' read-backs); the probe REFUSES any cell whose
# containers' declared env mismatches the posture.
#
# Per cell: probe_films_sizing.py measures wall/frames/CPU; mem_watch (the
# FIXED one — /proc scan, explicit vmhwm states) runs beside it and owns
# peak anon / memory.peak / VmHWM / spool df, including the ENGINE'S /tmp
# spool high-water on the rr container (reader.py:425 spools each video).
#
# FILM_DOC defaults to the strata rule's expected pick (globally largest
# bytes after title-dedup). Run films_strata_report.py FIRST; if it names a
# different film, pass FILM_DOC=<doc> to this script.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_films_sizing.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PY="${PY:-$HOME/.venv-floor/bin/python3}"
FILM_DOC="${FILM_DOC:-the-grapes-of-wrath-1940.mp4}"
FILM="$HOME/films_probe/$FILM_DOC"
MANIFEST="${MANIFEST:-$HOME/films_manifest/corpus_manifest.json}"
S3_CORPUS="s3://rocketride-benchmark-data/leela/corpus/archive_films_v2"
OUT_DIR="${OUT_DIR:-$HOME/films_probe/sizing_out}"
mkdir -p "$OUT_DIR"

# --- film: fetch if absent, then sha+bytes verify against her frozen manifest
if [ ! -f "$FILM" ]; then
  echo "fetching $FILM_DOC from $S3_CORPUS ..."
  aws s3 cp "$S3_CORPUS/$FILM_DOC" "$FILM" --quiet
fi
FILM_SHA="$("$PY" - "$MANIFEST" "$FILM_DOC" "$FILM" <<'PYV'
import hashlib, json, sys
man, doc, path = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
want = man['sha256'][doc]
h = hashlib.sha256()
with open(path, 'rb') as fh:
    for b in iter(lambda: fh.read(1 << 20), b''):
        h.update(b)
import os
ok = h.hexdigest() == want['sha256'] and os.path.getsize(path) == want['bytes']
print(h.hexdigest() if ok else 'MISMATCH')
PYV
)"
[ "$FILM_SHA" != "MISMATCH" ] || { echo "NOT DONE — $FILM_DOC sha/bytes mismatch vs manifest"; exit 1; }
echo "film verified: $FILM_DOC sha $FILM_SHA"

ENVARGS4="-e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 \
-e VECLIB_MAXIMUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TORCH_NUM_THREADS=4"

teardown() {
  docker rm -f rr >/dev/null 2>&1 || true
  local i; for i in 0 1 2 3 4 5 6 7; do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done
  touch "$OUT_DIR/memwatch.stop" 2>/dev/null || true
}
trap teardown EXIT

run_cell() { # $1=cell $2=containers-csv
  local cell="$1" containers="$2"
  rm -f "$OUT_DIR/memwatch.stop"
  "$PY" working/video/probe/mem_watch.py --containers "$containers" \
      --spool-path /tmp --duration-s 14400 \
      --stop-file "$OUT_DIR/memwatch.stop" \
      --out "$OUT_DIR/memwatch_$cell" &
  local mw=$!
  local rc=0
  "$PY" working/video/probe/probe_films_sizing.py --cell "$cell" \
      --film "$FILM" --film-sha-expected "$FILM_SHA" \
      --manifest "$MANIFEST" --containers "$containers" \
      --out "$OUT_DIR/sizing_$cell.json" || rc=$?
  touch "$OUT_DIR/memwatch.stop"
  wait "$mw" || true
  return "$rc"
}

echo "== cell 1: rr-default (1 token, env UNSET) =="
docker rm -f rr >/dev/null 2>&1 || true
docker run -d --name rr --memory 58g --log-opt max-size=200m --network host \
    rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
run_cell rr-default rr
docker rm -f rr >/dev/null 2>&1 || true

echo "== cell 2: rr-8x4 (8 tokens, six vars=4) =="
# shellcheck disable=SC2086
docker run -d --name rr --memory 58g $ENVARGS4 --log-opt max-size=200m \
    --network host rr:patched-video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm rr --port 5565 --deadline 1800 --container rr
run_cell rr-8x4 rr
docker rm -f rr >/dev/null 2>&1 || true

echo "== cell 3: li-8x4 (8 single-worker li:video instances, env 4) =="
NAMES=""
for i in 0 1 2 3 4 5 6 7; do
  docker rm -f "li_bal_$i" >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker run -d --name "li_bal_$i" --memory 7g $ENVARGS4 -e WS1V_WORKERS=1 \
      --log-opt max-size=200m --network host --entrypoint sh li:video -c \
      "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $((8802+i)) --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  NAMES="$NAMES,li_bal_$i"
done
NAMES="${NAMES#,}"
for i in 0 1 2 3 4 5 6 7; do
  "$PY" working/video/probe/wait_ready.py --arm li --port $((8802+i)) \
      --workers 1 --container "li_bal_$i" --deadline 1200
done
run_cell li-8x4 "$NAMES"
for i in 0 1 2 3 4 5 6 7; do docker rm -f "li_bal_$i" >/dev/null 2>&1 || true; done

echo "== summary =="
"$PY" - "$OUT_DIR" <<'PYS'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
for cell in ('rr-default', 'rr-8x4', 'li-8x4'):
    s = out / f'sizing_{cell}.json'
    if not s.exists():
        print(f'{cell}: NO ARTIFACT — cell did not complete')
        continue
    d = json.loads(s.read_text())
    mw = out / f'memwatch_{cell}.json'
    mem = json.loads(mw.read_text())['containers'] if mw.exists() else {}
    anon = {c: v.get('max_anon_bytes') for c, v in mem.items()}
    peak = {c: v.get('max_memory_peak_bytes') for c, v in mem.items()}
    spool = {c: v.get('max_spool_used_bytes') for c, v in mem.items()}
    print(f"{cell}: wall {d['result']['wall_s']}s | {d['frames_per_s']} f/s | "
          f"realtime x{d['realtime_factor']} | CPU {d['service_cpu']['cores']} "
          f"cores ({d['service_cpu']['util_pct']}%) | probe rss "
          f"{d['probe_ru_maxrss_kb']} kB")
    print(f'   max anon/instance: {anon}')
    print(f'   memory.peak/instance: {peak}')
    print(f'   spool df max: {spool}')
    for line in d['projection'].values():
        print(f'   projection: {line}')
PYS
echo "DONE — artifacts in $OUT_DIR (bundle them; entry 26: not landed until fetched + ls-remote confirmed)"
