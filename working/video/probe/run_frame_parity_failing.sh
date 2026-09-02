#!/usr/bin/env bash
# =============================================================================
# CROSS-GATE DISCRIMINATOR (2026-09-01): probe_frame_parity on THREE FAILING
# films from the measured set — decode-only, re-runs nothing, changes no gate.
#
# The campaign's cross_detection_agreement failed 34/35; the one passing film
# is the only one ever proven byte-identical A==B==C. Hypothesis: the arms
# decoded DIFFERENT frames on unverified films (same count — gate 1 passed
# both arms — different content, VFR selection) -> entry 14 CANNOT COMPARE,
# not FAIL. This runs the EXISTING committed probe (A = engine argv via
# docker exec, B = LI pipe, C = LI file; per-frame PNG sha comparison, null
# controls built in) on:
#   ABucketofBlood.mp4      — worst reported divergence (134/262 = 51%),
#                             and the largest of the three (1.71 GB)
#   HouseOnBareMountain.mp4 — 113/248 (46%); ALSO the golden film, so an
#                             A==B verdict here additionally anchors the
#                             committed golden's chunk hashes
#   A_Study_In_Scarlet.mp4  — 113/285 (40%); third operator-named failure,
#                             smallest bytes (446 MB) — n=3 with size spread
# (Resolution is unrecorded in any manifest — severity + anchors + bytes are
# the selection axes available; all three are operator-named failures.)
#
# Each film's sha256 is read from the manifest and passed as
# --film-sha-expected: the probe proves it decoded the manifest's bytes
# (entry 14: same-input proof travels with the comparison).
#
# VERDICT KEY: A==B==C EXACT on a failing film -> frames identical, the
# divergence is DOWNSTREAM (detector/service at leg scale) — more serious.
# A!=B -> the arms decoded different frames -> entry 14: those films'
# gate-3 verdict is CANNOT COMPARE. Either way, Ansh rules next.
#
# Cost: decode+hash only, ~2-4 min/film (20000Leagues cell A measured
# 24.7 s on 429 MB; 3 cells + hashing + overhead), ~6-12 min total.
# Needs the rr container for cell A: uses the running one; brings one up
# (default lifetime) if absent and removes it after ONLY if created here.
# Committed script + self-printed sha256 per register entry 25.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_frame_parity_failing.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

PYF="${PYF:-$HOME/.venv-floor/bin/python3}"
MANIFEST="working/video/films_video_manifest.jsonl"
CORPUS="${CORPUS:-$HOME/films_corpus/subset}"
OUT="${OUT:-$HOME/films_probe/parity_failing}"
mkdir -p "$OUT"
[ -f "$MANIFEST" ] || { echo "NOT DONE — manifest missing: $MANIFEST"; exit 1; }

CREATED_RR=0
if [ "$(docker inspect -f '{{.State.Running}}' rr 2>/dev/null)" != "true" ]; then
  echo "rr not running — bringing up a default lifetime for cell A (decode only)"
  docker rm -f rr >/dev/null 2>&1 || true
  docker run -d --name rr --memory 58g --log-opt max-size=200m --network host \
      rr:patched-video >/dev/null
  "$HOME/.venv/bin/python" working/video/probe/wait_ready.py --arm rr --port 5565 \
      --deadline 1800 --container rr
  CREATED_RR=1
fi
cleanup() {
  [ "$CREATED_RR" = "1" ] && docker rm -f rr >/dev/null 2>&1 || true
}
trap cleanup EXIT

sha_of() {  # manifest sha for --film-sha-expected (same-input proof)
  "$PYF" - "$MANIFEST" "$1" <<'PYSHA'
import json, sys
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get('file') == sys.argv[2]:
        print(r['sha256']); break
else:
    raise SystemExit(f'NOT DONE — {sys.argv[2]} not in manifest')
PYSHA
}

for f in ABucketofBlood.mp4 HouseOnBareMountain.mp4 A_Study_In_Scarlet.mp4; do
  echo "==== $f ===="
  [ -f "$CORPUS/$f" ] || { echo "NOT DONE — $CORPUS/$f missing"; exit 1; }
  SHA="$(sha_of "$f")"
  "$PYF" working/video/probe/probe_frame_parity.py \
      --film "$CORPUS/$f" --film-sha-expected "$SHA" --container rr \
      --out "$OUT/probe_frame_parity_${f%.mp4}.json"
done
echo "DONE — three verdicts above; artifacts in $OUT. Bring the comparison"
echo "blocks back verbatim. No gate changed, nothing re-run, nothing published."
