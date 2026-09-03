#!/usr/bin/env bash
# =============================================================================
# box_hygiene_aa.sh — RULING AA (2026-09-02). BOX-SIDE. Runs AFTER Ruling Y's
# probe (fail-closed sequencing guard below).
#
# DELETES (ruled AA):
#   * image rr:patched-video.pre-node-fix   (15G, superseded)
#   * reclaimable docker build cache        (~13.92G at inventory)
#   * corpus/ami/closeup1                   (7.7G — ruled a duplicate subset
#     of full/, 62/62 byte-identical; this script re-checks name+size
#     containment before removing)
#   * ~/anchor_7204                          (17M — trivially recreated from
#     commit 7204a28)
# KEEPS — refuses BEFORE deleting anything if any is missing:
#   * images rr:patched-video (NOT bit-reproducible; every RR number rides
#     it), li:video, li:video-anchor (pre-refactor comparable),
#     ws1-llamaindex (Phase 1 arm, no pin-locked Dockerfile — Crossroad 19)
#   * dirs ~/films_corpus/subset, corpus/ami/full, corpus/ami/video
# Prints every deletion target and its size BEFORE deleting.
# Committed script + self-printed sha256 (entry 25). Idempotent: an
# already-absent DELETE target is noted and skipped, never an error.
# =============================================================================
set -euo pipefail
echo "box_hygiene_aa.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
AMI="$HOME/parity-bench-video/corpus/ami"

echo "== sequencing guard: Ruling Y ran? =="
[ -d "$HOME/films_probe/detector_parity_y" ] || { echo "REFUSE: ~/films_probe/detector_parity_y absent — Ruling AA runs AFTER Ruling Y's probe"; exit 3; }
echo "  OK: detector_parity_y present"

echo "== KEEP guards (refuse before any delete) =="
for img in rr:patched-video li:video li:video-anchor ws1-llamaindex; do
  docker image inspect "$img" >/dev/null 2>&1 || { echo "REFUSE: KEEP image missing: $img"; exit 3; }
  echo "  keep image OK: $img"
done
for d in "$HOME/films_corpus/subset" "$AMI/full" "$AMI/video"; do
  [ -d "$d" ] || { echo "REFUSE: KEEP dir missing: $d"; exit 3; }
  echo "  keep dir OK: $d"
done

echo "== closeup1 containment re-check (name+size within full/) =="
if [ -d "$AMI/closeup1" ]; then
python3 - "$AMI" <<'PYC'
import os, sys
ami = sys.argv[1]
cl = {f: os.path.getsize(os.path.join(ami, 'closeup1', f))
      for f in os.listdir(os.path.join(ami, 'closeup1'))
      if not f.startswith('.')}
fu = {f: os.path.getsize(os.path.join(ami, 'full', f))
      for f in os.listdir(os.path.join(ami, 'full'))
      if not f.startswith('.')}
bad = [f for f, s in cl.items() if fu.get(f) != s]
print(f'  closeup1: {len(cl)} files; name+size contained in full/: '
      f'{len(cl) - len(bad)}/{len(cl)}')
if bad:
    print('  REFUSE: not contained:', bad[:5]); raise SystemExit(3)
print('  (byte-level 62/62 identity is the AA ruling evidence; '
      'this re-check is name+size)')
PYC
else
  echo "  closeup1 already absent — nothing to check"
fi

echo "== WHAT WILL BE DELETED (sizes; nothing deleted yet) =="
docker images rr:patched-video.pre-node-fix 2>/dev/null || echo "  image already absent"
du -sh "$AMI/closeup1" 2>/dev/null || echo "  closeup1 already absent"
du -sh "$HOME/anchor_7204" 2>/dev/null || echo "  anchor_7204 already absent"
echo "-- docker space before --"
docker system df
df -h "$HOME" | tail -1

echo "== DELETING =="
if docker image inspect rr:patched-video.pre-node-fix >/dev/null 2>&1; then
  docker rmi rr:patched-video.pre-node-fix
else
  echo "  skip: image already absent"
fi
docker builder prune -f
rm -rf "$AMI/closeup1"
rm -rf "$HOME/anchor_7204"

echo "== AFTER =="
docker system df
df -h "$HOME" | tail -1
echo "DONE — paste everything above back."
