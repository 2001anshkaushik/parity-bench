#!/usr/bin/env bash
# fetch_films500.sh — BOX-SIDE. Stage the full frozen archive_films_v2 500
# into ~/films_corpus/full500, REUSING our verified 35-film subset by
# hardlink, verifying EVERY file's sha256 against Leela's canonical
# corpus_manifest.json (itself verified against the frozen manifest sha
# bd0c915e… our DEFINITIVE §1 cites). Fail-closed: a manifest-sha mismatch
# or any per-film sha mismatch refuses; nothing is deleted, ever.
# Idempotent + resumable: verified files are skipped on re-run.
# ~252 GB of fetch (281.4 GB corpus minus our 29 GB subset) — run it
# detached:  box.sh launch fetch500 'bash ~/parity-bench-video/working/video/probe/fetch_films500.sh'
# Committed script + self-printed sha256 (entry 25).
set -euo pipefail
echo "fetch_films500.sh sha256: $(sha256sum "$0" | awk '{print $1}')"
echo "repo HEAD: $(git -C ~/parity-bench-video rev-parse --short HEAD 2>/dev/null || echo n/a)"

SRC="s3://rocketride-benchmark-data/leela/corpus/archive_films_v2"
DEST="$HOME/films_corpus/full500"
SUBSET="$HOME/films_corpus/subset"
MANIFEST_SHA_EXPECT="bd0c915e28710322bace0549d7372dddea5578895333f143c67e04252e4e02a1"
mkdir -p "$DEST"

echo "== canonical manifest (verified against the frozen sha) =="
aws s3 cp "$SRC/corpus_manifest.json" "$DEST/corpus_manifest.json" --quiet
GOT=$(sha256sum "$DEST/corpus_manifest.json" | awk '{print $1}')
[ "$GOT" = "$MANIFEST_SHA_EXPECT" ] || {
  echo "REFUSE: corpus_manifest.json sha $GOT != frozen $MANIFEST_SHA_EXPECT — the canonical object is not the frozen manifest; nothing fetched"; exit 3; }
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
    print(f'{sha}  {name}')
PYM
N=$(wc -l < "$DEST/.filelist" | tr -d ' ')
echo "  manifest lists $N files"

echo "== stage (reuse subset by hardlink where sha matches; else fetch; verify all) =="
OK=0; LINKED=0; FETCHED=0; BAD=0
while read -r SHA NAME; do
  T="$DEST/$NAME"
  if [ -s "$T" ] && [ "$(sha256sum "$T" | awk '{print $1}')" = "$SHA" ]; then
    OK=$((OK+1)); continue
  fi
  if [ -s "$SUBSET/$NAME" ] && [ "$(sha256sum "$SUBSET/$NAME" | awk '{print $1}')" = "$SHA" ]; then
    ln -f "$SUBSET/$NAME" "$T"; LINKED=$((LINKED+1)); OK=$((OK+1)); continue
  fi
  aws s3 cp "$SRC/$NAME" "$T" --quiet
  if [ "$(sha256sum "$T" | awk '{print $1}')" = "$SHA" ]; then
    FETCHED=$((FETCHED+1)); OK=$((OK+1))
  else
    echo "SHA MISMATCH after fetch: $NAME"; BAD=$((BAD+1))
  fi
done < "$DEST/.filelist"

echo "== census =="
echo "verified=$OK/$N  hardlinked_from_subset=$LINKED  fetched=$FETCHED  MISMATCHED=$BAD"
du -sh "$DEST"; df -h /home/ssm-user | tail -1
[ "$BAD" -eq 0 ] && [ "$OK" -eq "$N" ] || { echo "NOT DONE — census above says why"; exit 3; }
echo "DONE — $N/$N byte-verified against the frozen manifest."
