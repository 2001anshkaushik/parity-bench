#!/usr/bin/env bash
# p5_infer_build.sh — build rr:p5-infer FROM rr:patched-video (P5-A, preregistration.json P5_A.build). The base is
# never modified; the new image adds exactly three files to engine/nodes/detect: IGlobal.py and IInstance.py
# (working/nodes/p5_infer_src, derived from the base's own files) and infer_worker.py (the single inference thread).
#
#   bash working/scripts/p5_infer_build.sh <campaign_dir_abs>
#
# Exit 0 ONLY when everything below holds (gate G_build_A; the chain stops P5 on any other status):
#   * the base image's detect node carries the md5s the P5 files were derived from (IInstance 984d80e4…, IGlobal 9edc29c9…);
#   * the files copied carry the md5s of working/nodes/p5_infer_src, owned and moded like the base's node files;
#   * rr:patched and rr:patched-video read back identical before and after the build;
#   * the in-image check (the engine's own Python, check_p5_in_image.py) exits 0 with "ok": true on rr:p5-infer.
# The record p5a_build.json is written in every case that reaches the check (pass or fail).
set -uo pipefail
echo "p5_infer_build.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 1 ] || { echo "usage: $0 <campaign_dir_abs>" >&2; exit 2; }
D="$1"; TAG=rr:p5-infer; RECF=p5a_build.json; cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"; SRC=working/nodes/p5_infer_src; NODE=/opt/rocketride/engine/nodes/detect
FRAME="$HOME/p3b_frames_parity_p3_20260925T035027Z/v00_EN2001a/f_000001.png"
docker image inspect "$TAG" >/dev/null 2>&1 && { echo "REFUSED: $TAG exists (never overwritten)"; exit 3; }
[ -e "$D/$RECF" ] && { echo "REFUSED: $D/$RECF exists (append-only)"; exit 3; }
[ -f "$FRAME" ] || { echo "REFUSED: check frame $FRAME absent"; exit 3; }
ids() { for i in rr:patched rr:patched-video; do echo "$i $(docker image inspect -f '{{.Id}}' "$i")"; done; }
BEFORE="$(ids)"; echo "images before:"; echo "$BEFORE"
BASEMD5="$(docker run --rm --entrypoint sh rr:patched-video -c "cd $NODE && md5sum IInstance.py IGlobal.py && stat -c '%U:%G %a %n' IInstance.py IGlobal.py")" || exit 4
echo "$BASEMD5"
echo "$BASEMD5" | grep -q '^984d80e45e885b5ae21e987664850b4c  IInstance.py$' || { echo "REFUSED: base IInstance.py is not 984d80e4… (the P5 file's origin)"; exit 4; }
echo "$BASEMD5" | grep -q '^9edc29c94a5a34ba366d938d048e89fd  IGlobal.py$' || { echo "REFUSED: base IGlobal.py is not 9edc29c9… (the P5 file's origin)"; exit 4; }
OWN="$(echo "$BASEMD5" | awk '/ IInstance.py$/ && NF==3 {print $1}')"; MODE="$(echo "$BASEMD5" | awk '/ IInstance.py$/ && NF==3 {print $2}')"
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
cp "$SRC/IGlobal.py" "$SRC/IInstance.py" "$SRC/infer_worker.py" "$B/" || exit 5
chmod "$MODE" "$B"/*.py
printf 'FROM rr:patched-video\nCOPY --chown=%s IGlobal.py IInstance.py infer_worker.py %s/\n' "$OWN" "$NODE" > "$B/Dockerfile"
cat "$B/Dockerfile"
docker build -q -t "$TAG" "$B" || exit 6
AFTER="$(ids)"; echo "images after:"; echo "$AFTER"
[ "$BEFORE" = "$AFTER" ] || { echo "!! A PROTECTED IMAGE ID CHANGED"; exit 7; }
EXPECT="$("$PY" -c 'import hashlib,json,sys; print(json.dumps({f: hashlib.md5(open(sys.argv[1]+"/"+f,"rb").read()).hexdigest() for f in ("IGlobal.py","IInstance.py","infer_worker.py")}))' "$SRC")"
INIMG="$(docker run --rm --entrypoint sh "$TAG" -c "cd $NODE && md5sum IGlobal.py IInstance.py infer_worker.py; stat -c '%U:%G %a %n' IGlobal.py IInstance.py infer_worker.py")"
echo "$INIMG"
OUT="$(docker run --rm --network none -v "$FRAME:/x/frame.png:ro" -v "$PWD/$SRC/check_p5_in_image.py:/x/check.py:ro" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine "$TAG" /x/check.py "$EXPECT" 2>&1)"
CRC=$?
echo "$OUT" | tail -8
CHECK="$(echo "$OUT" | grep '^P5_CHECK ' | tail -1)"
"$PY" - "$D/$RECF" "$(docker image inspect -f '{{.Id}}' "$TAG")" "$BEFORE" "${CHECK:-}" "$CRC" "$EXPECT" "$BASEMD5" "$INIMG" <<'PYREC'
import json, sys, time
chk = sys.argv[4]
parsed = json.loads(chk.split("P5_CHECK ", 1)[1]) if chk.startswith("P5_CHECK ") else None
ok = bool(parsed and parsed.get("ok") is True and sys.argv[5] == "0")
json.dump({"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "image": "rr:p5-infer", "image_id": sys.argv[2],
           "from": "rr:patched-video", "protected_ids_before_and_after": sys.argv[3].splitlines(),
           "base_node": sys.argv[7].splitlines(), "expected_p5_md5": json.loads(sys.argv[6]), "in_image_node": sys.argv[8].splitlines(),
           "in_image_check": parsed, "in_image_check_rc": int(sys.argv[5]), "gate_G_build_A_pass": ok},
          open(sys.argv[1], "x"), indent=1)
print(open(sys.argv[1]).read())
sys.exit(0 if ok else 1)
PYREC
[ $? -eq 0 ] || { echo "!! IN-IMAGE CHECK FAILED (G_build_A) — P5 must not run on this image"; exit 8; }
echo "CHAIN_DONE p5_infer_build (G_build_A PASS)"
exit 0
