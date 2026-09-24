#!/usr/bin/env bash
# p2_pdfium_build.sh — build rr:p2-pdfium FROM rr:p1-tikafix (P2-C, preregistration.json P2_C build). Neither
# base is modified; rr:p1-pdfium (P1's broken build) is left as it is.
#
#   bash working/scripts/p2_pdfium_build.sh <campaign_dir_abs>
#
# Exit 0 ONLY when everything below holds (gate G_build_C; the master stops P2-C on any other status):
#   * pypdfium2 5.13.0 is installed from ~/p0venv (the wheel H6 used; no download) by its dist-info RECORD:
#     every top-level entry the wheel installed — pypdfium2, pypdfium2_raw, pypdfium2_cfg (the module P1's
#     hand-picked copy left out, register 54), pypdfium2_cli — plus the dist-info itself;
#   * the prototype nodes come from working/nodes/p2_pdfium_src (pdfium_pure, pdfium_hybrid);
#   * the base and protected image ids read back identical before and after the build;
#   * the in-image check (the engine's own Python) exits 0 and prints P2_PDFIUM_CHECK with "ok": true.
# The record p2c_build.json is written in every case that reaches the check (pass or fail).
set -uo pipefail
echo "p2_pdfium_build.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 1 ] || { echo "usage: $0 <campaign_dir_abs>" >&2; exit 2; }
D="$1"; cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"; PV="$HOME/p0venv/lib/python3.12/site-packages"
DI="$PV/pypdfium2-5.13.0.dist-info"
docker image inspect rr:p2-pdfium >/dev/null 2>&1 && { echo "REFUSED: rr:p2-pdfium exists (never overwritten)"; exit 3; }
docker image inspect rr:p1-tikafix >/dev/null 2>&1 || { echo "REFUSED: rr:p1-tikafix absent"; exit 3; }
[ -f "$DI/RECORD" ] || { echo "REFUSED: $DI/RECORD absent"; exit 3; }
ids() { for i in rr:patched rr:patched-video rr:p1-tikafix; do echo "$i $(docker image inspect -f '{{.Id}}' "$i")"; done; }
BEFORE="$(ids)"; echo "images before:"; echo "$BEFORE"
SITE="$(docker run --rm --entrypoint sh rr:p1-tikafix -c 'ls -d /opt/rocketride/engine/lib/python3.12/site-packages')" || exit 4
echo "engine site-packages: $SITE"
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
mkdir -p "$B/nodes" "$B/site"
"$PY" working/nodes/p2_pdfium_src/gen.py "$B/nodes" || exit 5
# every top-level entry the wheel's RECORD lists inside site-packages (paths starting '../' are console scripts)
TOPS="$("$PY" - "$DI/RECORD" <<'PYREC'
import csv, sys
tops = sorted({row[0].split("/")[0] for row in csv.reader(open(sys.argv[1])) if row and not row[0].startswith("../")})
print("\n".join(tops))
PYREC
)" || exit 5
echo "RECORD top-level entries:"; echo "$TOPS" | sed 's/^/  /'
echo "$TOPS" | grep -qx pypdfium2_cfg || { echo "REFUSED: RECORD does not list pypdfium2_cfg — not the wheel this build expects"; exit 5; }
while IFS= read -r t; do
  [ -n "$t" ] || continue
  if [ -d "$PV/$t" ]; then cp -R "$PV/$t" "$B/site/" || exit 5
  elif [ -f "$PV/$t" ]; then cp "$PV/$t" "$B/site/" || exit 5
  else echo "REFUSED: RECORD lists $t but $PV/$t is absent"; exit 5; fi
done <<< "$TOPS"
cp working/nodes/p2_pdfium_src/check_in_image.py "$B/"
printf 'FROM rr:p1-tikafix\nCOPY nodes/pdfium_pure /opt/rocketride/engine/nodes/pdfium_pure\nCOPY nodes/pdfium_hybrid /opt/rocketride/engine/nodes/pdfium_hybrid\nCOPY site/ %s/\nCOPY check_in_image.py /opt/rocketride/p2_check_in_image.py\n' "$SITE" > "$B/Dockerfile"
docker build -q -t rr:p2-pdfium "$B" || exit 6
AFTER="$(ids)"; echo "images after:"; echo "$AFTER"
[ "$BEFORE" = "$AFTER" ] || { echo "!! A BASE OR PROTECTED IMAGE ID CHANGED"; exit 7; }
CORPUS="$HOME/parity-bench/corpus/govdocs1/pdfs"
OUT="$(docker run --rm -v "$CORPUS:/corpus:ro" --workdir /opt/rocketride/engine --entrypoint /opt/rocketride/engine/engine rr:p2-pdfium /opt/rocketride/p2_check_in_image.py /corpus/002_002489.pdf 2>&1)"
CRC=$?
echo "$OUT" | tail -20
CHECK="$(echo "$OUT" | grep '^P2_PDFIUM_CHECK ' | tail -1)"
"$PY" - "$D/p2c_build.json" "$(docker image inspect -f '{{.Id}}' rr:p2-pdfium)" "$BEFORE" "${CHECK:-}" "$SITE" "$CRC" "$TOPS" <<'PYREC'
import json, sys, time
chk = sys.argv[4]
parsed = json.loads(chk.split("P2_PDFIUM_CHECK ", 1)[1]) if chk.startswith("P2_PDFIUM_CHECK ") else None
ok = bool(parsed and parsed.get("ok") is True and sys.argv[6] == "0")
json.dump({"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "image": "rr:p2-pdfium",
           "image_id": sys.argv[2], "from": "rr:p1-tikafix", "base_ids_before_and_after": sys.argv[3].splitlines(),
           "engine_site_packages": sys.argv[5], "wheel_record_top_level": sys.argv[7].splitlines(),
           "in_image_check": parsed, "in_image_check_rc": int(sys.argv[6]), "gate_G_build_C_pass": ok},
          open(sys.argv[1], "x"), indent=1)
print(open(sys.argv[1]).read())
sys.exit(0 if ok else 1)
PYREC
[ $? -eq 0 ] || { echo "!! IN-IMAGE CHECK FAILED (G_build_C) — P2-C must not run on this image"; exit 8; }
echo "CHAIN_DONE p2_pdfium_build (G_build_C PASS)"
exit 0
