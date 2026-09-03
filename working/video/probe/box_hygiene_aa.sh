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
#     ws1-llamaindex:x86_64 (Phase 1 arm, no pin-locked Dockerfile —
#     Crossroad 19)
#   * dirs ~/films_corpus/subset, corpus/ami/full, corpus/ami/video
# ALSO ON THE BOX, IN NEITHER LIST, KEPT DELIBERATELY (stated in output so
# they read as considered, not overlooked): rr-engine:3.3.1, rr:patched,
# rr:stock — small (~1G each) Phase-1 artifacts, untouched by Ruling AA.
# Prints every deletion target and its size BEFORE deleting.
#
# RUN-1 NOTE (2026-09-03): the first issue of this script REFUSED, as
# designed, on its own guard bug — it checked bare `ws1-llamaindex`,
# which docker resolves to :latest (absent); the image is
# `ws1-llamaindex:x86_64`. This issue pins every KEEP/DELETE name AND
# its expected image ID against the box's actual `docker images` output
# (2026-09-03): a name that is missing OR that resolves to a different
# ID than was inventoried and ruled on refuses before any delete.
# Committed script + self-printed sha256 (entry 25). Idempotent: an
# already-absent DELETE target is noted and skipped, never an error.
# =============================================================================
set -euo pipefail
echo "box_hygiene_aa.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
AMI="$HOME/parity-bench-video/corpus/ami"

echo "== sequencing guard: Ruling Y ran? =="
[ -d "$HOME/films_probe/detector_parity_y" ] || { echo "REFUSE: ~/films_probe/detector_parity_y absent — Ruling AA runs AFTER Ruling Y's probe"; exit 3; }
echo "  OK: detector_parity_y present"

check_image() {  # $1 name  $2 expected short id  $3 label — top-level call
  if ! docker image inspect "$1" >/dev/null 2>&1; then
    echo "REFUSE: $3 image missing: $1"; exit 3
  fi
  local got
  got="$(docker image inspect -f '{{.Id}}' "$1" | sed 's/^sha256://; s/\(............\).*/\1/')"
  if [ "$got" != "$2" ]; then
    echo "REFUSE: $1 resolves to ID $got, expected $2 — the name no longer points at the ruled image"; exit 3
  fi
  echo "  $3 image OK: $1 (ID $got)"
}

echo "== KEEP guards (name AND image ID, refuse before any delete) =="
check_image rr:patched-video        b7f51acc9533 keep
check_image li:video                0a52afcbe9d4 keep
check_image li:video-anchor         b64454366c78 keep
check_image ws1-llamaindex:x86_64   3d2f1f436a46 keep
for d in "$HOME/films_corpus/subset" "$AMI/full" "$AMI/video"; do
  [ -d "$d" ] || { echo "REFUSE: KEEP dir missing: $d"; exit 3; }
  echo "  keep dir OK: $d"
done
echo "== in NEITHER list — considered and kept, not overlooked =="
for img in rr-engine:3.3.1 rr:patched rr:stock; do
  if docker image inspect "$img" >/dev/null 2>&1; then
    echo "  kept (Phase-1 artifact, small, outside Ruling AA): $img"
  else
    echo "  note: $img not present on this box"
  fi
done

echo "== DELETE-target identity (refuse on mismatch; absent = skip later) =="
if docker image inspect rr:patched-video.pre-node-fix >/dev/null 2>&1; then
  check_image rr:patched-video.pre-node-fix ed77767a43bf delete-target
else
  echo "  delete target already absent — will skip"
fi

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
