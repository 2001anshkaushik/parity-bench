#!/usr/bin/env bash
# =============================================================================
# Proof layer 2 for the LI streaming refactor (Rulings A-D, 2026-08-27/28):
# li:video-anchor (pre-refactor code, freeze-pinned deps) vs li:video
# (refactored) side by side, same env, host network, one item at a time —
# ES2005a.avi (AMI) FIRST, then ARomanceOfTheRedwoods.mp4.
#
# WHY A SCRIPT FILE: the anchor round's first attempt lost `--network host`
# to SSM line-wrapping in a long pasted block; the Crossroad-22 preflight
# refused (NetworkMode=''). Long box blocks are now a committed file plus a
# sha the operator verifies (register entry 25). This script prints its own
# sha256 at start.
#
# Verdicts:
#   * ES2005a must compare EQUAL on every field or the script exits 2
#     ("STOP (Ruling B)") — the film is not attempted after an AMI failure.
#   * If the FILM fails on the ANCHOR (buffered) image and passes on the new
#     one, that is RECORDED AS BLOCKER-3 EVIDENCE (OOMKilled read from
#     docker), not a failed proof — exit stays 0, the evidence is printed
#     and written to the artifact.
#   * Any divergence on a completed pair: exit 2. Machinery failure: exit 1.
# Fields compared: n_frames, frame_labels, frame_scores, chunks,
# embedding_norms, n_detections, total_chars. Each side's reader_semantics
# is printed (old: absent/buffered era; new: spooled_file_frames_on_disk).
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
echo "run_proof_layer2.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
echo "repo HEAD: $(git rev-parse HEAD)"

OLD_IMG="${OLD_IMG:-li:video-anchor}"
NEW_IMG="${NEW_IMG:-li:video}"
OLD_PORT=8802
NEW_PORT=8803
AMI_ITEM="${AMI_ITEM:-$ROOT/corpus/ami/full/ES2005a.avi}"
FILM_ITEM="${FILM_ITEM:-$HOME/films_probe/ARomanceOfTheRedwoods.mp4}"
OUT_DIR="${OUT_DIR:-$HOME/films_probe/proof_layer2}"
mkdir -p "$OUT_DIR"
[ -f "$AMI_ITEM" ] || { echo "NOT DONE — AMI item not found: $AMI_ITEM"; exit 1; }
[ -f "$FILM_ITEM" ] || { echo "NOT DONE — film not found: $FILM_ITEM"; exit 1; }

teardown() { docker rm -f li_eqv_old li_eqv_new >/dev/null 2>&1 || true; }
trap teardown EXIT

start_one() { # $1=name $2=image $3=port — the overnight_apples bring-up shape
  docker rm -f "$1" >/dev/null 2>&1 || true
  docker run -d --name "$1" --memory 8g \
    -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 \
    -e VECLIB_MAXIMUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TORCH_NUM_THREADS=4 \
    -e WS1V_WORKERS=1 --log-opt max-size=200m --network host --entrypoint sh "$2" -c \
    "rm -rf /tmp/ws1v_warm; exec python -m uvicorn li_video.service:app --host 0.0.0.0 --port $3 --workers 1 --loop uvloop --http httptools --no-access-log --log-level warning --timeout-keep-alive 30" >/dev/null
  echo "$1 <- $2 (image id $(docker inspect --format '{{.Image}}' "$1")), port $3"
}

wait_warm() { # $1=port $2=name — fail-closed readiness with a deadline
  local waited=0
  until curl -s "localhost:$1/health" | grep -q '"warm":true'; do
    sleep 5; waited=$((waited + 5))
    if [ "$waited" -ge 1200 ]; then
      echo "NOT DONE — $2 (port $1) not warm after ${waited}s"; exit 1
    fi
  done
  echo "$2 warm after ~${waited}s"
}

start_one li_eqv_old "$OLD_IMG" "$OLD_PORT"
start_one li_eqv_new "$NEW_IMG" "$NEW_PORT"
wait_warm "$OLD_PORT" li_eqv_old
wait_warm "$NEW_PORT" li_eqv_new

compare_item() { # $1=item path $2=allow_old_failure(0|1) $3=out json
  ~/.venv-floor/bin/python3 - "$1" "$2" "$3" "$OLD_PORT" "$NEW_PORT" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

item, allow_old_fail, out_path = Path(sys.argv[1]), sys.argv[2] == '1', sys.argv[3]
old_port, new_port = int(sys.argv[4]), int(sys.argv[5])
FIELDS = ('n_frames', 'frame_labels', 'frame_scores', 'chunks',
          'embedding_norms', 'n_detections', 'total_chars')


def exc_chain(e, limit=6):
    out, seen = [], set()
    while e is not None and id(e) not in seen and len(out) < limit:
        seen.add(id(e))
        out.append(f'{type(e).__name__}: {e}')
        e = e.__cause__ or e.__context__
    return out


def post(port):
    size = item.stat().st_size
    with open(item, 'rb') as fh:
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/process_video', data=fh, method='POST',
            headers={'Content-Type': 'application/octet-stream',
                     'Content-Length': str(size)})
        with urllib.request.urlopen(req, timeout=3600) as resp:
            return json.load(resp)


result = {'item': item.name, 'bytes': item.stat().st_size}
old_body = new_body = None
try:
    old_body = post(old_port)
    result['old'] = {'reader_semantics': old_body.get('reader_semantics'),
                     'n_frames': old_body.get('n_frames'),
                     'n_chunks': old_body.get('n_chunks')}
    print(f"  old_{old_port}: reader_semantics={old_body.get('reader_semantics')!r} "
          f"n_frames={old_body.get('n_frames')} n_chunks={old_body.get('n_chunks')}")
except Exception as exc:  # noqa: BLE001 — classified below, chain kept
    result['old'] = {'FAILED': exc_chain(exc)}
    print(f'  old_{old_port}: FAILED — {exc_chain(exc)}')

try:
    new_body = post(new_port)
    result['new'] = {'reader_semantics': new_body.get('reader_semantics'),
                     'n_frames': new_body.get('n_frames'),
                     'n_chunks': new_body.get('n_chunks')}
    print(f"  new_{new_port}: reader_semantics={new_body.get('reader_semantics')!r} "
          f"n_frames={new_body.get('n_frames')} n_chunks={new_body.get('n_chunks')}")
except Exception as exc:  # noqa: BLE001
    result['new'] = {'FAILED': exc_chain(exc)}
    print(f'  new_{new_port}: FAILED — {exc_chain(exc)}')

rc = None
if new_body is None:
    result['verdict'] = 'MACHINERY — the refactored side failed; nothing proven'
    rc = 4
elif old_body is None:
    if allow_old_fail:
        result['verdict'] = ('OLD-SIDE FAILURE, new side succeeded — candidate '
                             'BLOCKER-3 EVIDENCE (caller reads OOMKilled)')
        rc = 3
    else:
        result['verdict'] = 'MACHINERY — old side failed on the AMI item'
        rc = 4
else:
    same = {k: old_body.get(k) == new_body.get(k) for k in FIELDS}
    result['fields_equal'] = same
    if all(same.values()):
        result['verdict'] = 'EQUAL on every compared field'
        rc = 0
    else:
        bad = [k for k, v in same.items() if not v]
        result['verdict'] = f'DIVERGENT fields: {bad} — STOP (Ruling B)'
        rc = 2
print(f'  {item.name}: {result["verdict"]}')
Path(out_path).write_text(json.dumps(result, indent=1))
sys.exit(rc)
PY
}

echo "== item 1 (AMI, must be EQUAL): $(basename "$AMI_ITEM")"
if ! compare_item "$AMI_ITEM" 0 "$OUT_DIR/proof2_ES2005a.json"; then
  echo "STOP (Ruling B) — the AMI item diverged or failed; the film is not attempted."
  exit 2
fi

echo "== item 2 (film): $(basename "$FILM_ITEM")"
set +e
compare_item "$FILM_ITEM" 1 "$OUT_DIR/proof2_film.json"
film_rc=$?
set -e
if [ "$film_rc" -eq 3 ]; then
  oom_old="$(docker inspect --format '{{.State.OOMKilled}}' li_eqv_old 2>/dev/null || echo uninspectable)"
  echo "BLOCKER-3 EVIDENCE: the buffered (anchor) image failed on the film" \
       "(OOMKilled=$oom_old); the streaming image succeeded. Recorded in" \
       "$OUT_DIR/proof2_film.json — this is evidence, not a failed proof;" \
       "proof layer 2 rests on the AMI item's EQUAL above."
  echo "$oom_old" > "$OUT_DIR/proof2_film_old_oomkilled.txt"
elif [ "$film_rc" -eq 2 ]; then
  echo "STOP (Ruling B) — the film diverged between images."
  exit 2
elif [ "$film_rc" -ne 0 ]; then
  echo "NOT DONE — machinery failure on the film item (rc=$film_rc)."
  exit 1
fi

echo "PROOF LAYER 2 COMPLETE — artifacts in $OUT_DIR (containers torn down by trap)"
