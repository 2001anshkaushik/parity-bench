#!/usr/bin/env bash
# p1_tikafix_build.sh — build rr:p1-tikafix FROM rr:patched (P1-B). rr:patched is only read.
#
#   bash working/scripts/p1_tikafix_build.sh <campaign_dir_abs>
#
# Two changes, from the wrapper's bytecode (preregistration.json P1_B source step):
#  PATCH  engine/java/lib/tika.jar: com/rocketride/tika_api/TikaApi.getPdfConfig() code byte 9,
#         iconst_1 -> iconst_0 = setExtractInlineImages(false). No setting reaches it: getPdfConfig
#         takes no argument and reads no field, and extractInformation (offsets 564-571) puts that
#         PDFParserConfig into the ParseContext, which overrides tika-config.xml's PDFParser params.
#  CONFIG engine/java/tika-config.xml: <parser-exclude> for CompositeExternalParser and ExternalParser
#         under DefaultParser. ConfigBuilder.excludeExternalParserIfUnavailable returns at once for an
#         excluded parser (offsets 0-8) and never calls externalMediaToolsAvailable, which spawns
#         env / ffmpeg / exiftool / sox. ffmpeg, exiftool and sox are absent from rr:patched, so the
#         probe always removes both parsers today: the parser set is unchanged by construction.
set -uo pipefail
echo "p1_tikafix_build.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
D="$1"; cd "$(dirname "$0")/../.." || exit 2
PY="$HOME/.venv/bin/python"
docker image inspect rr:p1-tikafix >/dev/null 2>&1 && { echo "REFUSED: rr:p1-tikafix exists (never overwritten)"; exit 3; }
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
ids() { for i in rr:patched rr:patched-video; do echo "$i $(docker image inspect -f '{{.Id}}' "$i")"; done; }
BEFORE="$(ids)"; echo "protected before:"; echo "$BEFORE"
c=$(docker create rr:patched) || exit 4
docker cp -q "$c:/opt/rocketride/engine/java/lib/tika.jar" "$B/tika.orig.jar" && docker cp -q "$c:/opt/rocketride/engine/java/tika-config.xml" "$B/tika-config.orig.xml"
docker rm "$c" >/dev/null
"$PY" working/tools/p1_patch_tikaapi.py "$B/tika.orig.jar" "$B/tika.jar" || exit 5
"$PY" - "$B/tika-config.orig.xml" "$B/tika-config.xml" <<'PYCFG' || exit 5
import sys
s = open(sys.argv[1]).read()
anchor = '\t\t\t<parser-exclude class="org.apache.tika.parser.gdal.GDALParser"/>\n'
assert s.count(anchor) == 1, "anchor"
add = ('\t\t\t<!-- P1-B CONFIG: never probe external media tools (absent from this image) -->\n'
       '\t\t\t<parser-exclude class="org.apache.tika.parser.external.CompositeExternalParser"/>\n'
       '\t\t\t<parser-exclude class="org.apache.tika.parser.external.ExternalParser"/>\n')
open(sys.argv[2], "w").write(s.replace(anchor, anchor + add))
print("config: two parser-exclude lines added under DefaultParser")
PYCFG
diff "$B/tika-config.orig.xml" "$B/tika-config.xml"
printf 'FROM rr:patched\nCOPY tika.jar /opt/rocketride/engine/java/lib/tika.jar\nCOPY tika-config.xml /opt/rocketride/engine/java/tika-config.xml\n' > "$B/Dockerfile"
docker build -q -t rr:p1-tikafix "$B" || exit 6
AFTER="$(ids)"; echo "protected after:"; echo "$AFTER"
[ "$BEFORE" = "$AFTER" ] || { echo "!! PROTECTED IMAGE ID CHANGED"; exit 7; }
NEW="$(docker image inspect -f '{{.Id}}' rr:p1-tikafix)"
c=$(docker create rr:p1-tikafix) && docker cp -q "$c:/opt/rocketride/engine/java/lib/tika.jar" "$B/in_image.jar" && docker cp -q "$c:/opt/rocketride/engine/java/tika-config.xml" "$B/in_image.xml"; docker rm "$c" >/dev/null
cmp "$B/in_image.jar" "$B/tika.jar" && cmp "$B/in_image.xml" "$B/tika-config.xml" && echo "read-back: the image carries exactly the patched jar and config"
"$PY" - "$D/p1b_build.json" "$B" "$NEW" "$BEFORE" <<'PYREC'
import hashlib, json, sys, time, zipfile
out, B, new, before = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
cls = "com/rocketride/tika_api/TikaApi.class"
rec = {"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "image": "rr:p1-tikafix", "image_id": new,
       "from": "rr:patched", "protected_ids_before_and_after": before.splitlines(),
       "tika_jar_sha256": {"orig": h(f"{B}/tika.orig.jar"), "patched": h(f"{B}/tika.jar")},
       "TikaApi_class_sha256": {"orig": hashlib.sha256(zipfile.ZipFile(f"{B}/tika.orig.jar").read(cls)).hexdigest(),
                                "patched": hashlib.sha256(zipfile.ZipFile(f"{B}/tika.jar").read(cls)).hexdigest()},
       "tika_config_sha256": {"orig": h(f"{B}/tika-config.orig.xml"), "patched": h(f"{B}/tika-config.xml")},
       "scope": {"inline_image_extraction": "PATCH (TikaApi.getPdfConfig code byte 9: iconst_1 -> iconst_0)",
                 "external_tool_probes": "CONFIG (tika-config.xml parser-exclude x2; ConfigBuilder.excludeExternalParserIfUnavailable offsets 0-8)"}}
json.dump(rec, open(out, "x"), indent=1)
print(json.dumps(rec, indent=1))
PYREC
echo "CHAIN_DONE tikafix_build"
