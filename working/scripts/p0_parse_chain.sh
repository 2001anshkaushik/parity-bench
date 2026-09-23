#!/usr/bin/env bash
# p0_parse_chain.sh — P0 H5 (Tika config tail) and H6 (parser bake-off), on the box, one launch
# per stage, one workload at a time (Ruling C: no container of the docs or video legs runs).
#
#   bash working/scripts/p0_parse_chain.sh <campaign_dir> <expect_head> h5
#   bash working/scripts/p0_parse_chain.sh <campaign_dir> <expect_head> h6smoke [best_cfg]
#   bash working/scripts/p0_parse_chain.sh <campaign_dir> <expect_head> h6full  [best_cfg]
#   bash working/scripts/p0_parse_chain.sh <campaign_dir> <expect_head> h6hybrid <candidate>
#
# READ-ONLY with respect to both arms: Tika runs from rr:patched's own JRE and jars with the
# entrypoint replaced (the image is read, never rebuilt, retagged or removed); pypdf and
# pypdfium2 run from ~/p0venv. NO node and NO pipeline changes. Pre-registration:
# <campaign_dir>/preregistration.json (H5, H6), refused without it. h6full / h6hybrid refuse
# without the committed gate outcome file h6_gate.json naming the fired branch.
set -uo pipefail
echo "p0_parse_chain.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -ge 3 ] || { echo "usage: $0 <campaign_dir> <expect_head> <h5|h6smoke|h6best|h6full|h6hybrid> [cfg|candidate]" >&2; exit 2; }
D="$1"; H="$2"; STAGE="$3"; ARG4="${4:-}"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || { echo "REFUSED: results_prefix.sh absent" >&2; exit 2; }
REL="$(results_rel "$D")" || { echo "REFUSED: $D is not under working/results/" >&2; exit 2; }
[ -f "$D/preregistration.json" ] || { echo "REFUSED: $D/preregistration.json absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; WANT="$(echo "$H" | cut -c1-12)"
[ "$HAVE" = "$WANT" ] || { echo "REFUSED: worktree at $HAVE, caller expects $WANT" >&2; exit 2; }
for c in rr li; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: container '$c' is running — one workload at a time (Ruling C)" >&2; exit 3; }; done
PY="$HOME/.venv/bin/python"
BUILD="$HOME/p0_build"; export P0_TIKA_BUILD="$BUILD" P0_TEXTS="$HOME/p0_texts"
S384=working/results/batchsize_smoke_20260920T113000Z/slice_docs_n384_w25.json
S9975=working/results/batchsize_main_20260920T160920Z/slice_docs_n9975_w25.json
ELEVEN="011_011464.pdf,039_039660.pdf,008_008871.pdf,011_011730.pdf,014_014261.pdf,000_000344.pdf,031_031239.pdf,002_002489.pdf,034_034697.pdf,033_033172.pdf,014_014969.pdf"
WARMUP=028_028070.pdf          # a warm-up document of the 9,975 slice: in no measured list
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  stage $STAGE  head $HAVE"

build() {
  # TikaBatch compiled against the ENGINE's jars (copied out of rr:patched, read-only) on the
  # bundled JRE's major version, 17; the configs extracted from the same image.
  mkdir -p "$BUILD/cfg" "$HOME/p0_texts"
  SRC_SHA="$(sha256sum working/tika/TikaBatch.java | cut -d' ' -f1)"
  if [ ! -f "$BUILD/TikaBatch.class" ] || [ "$(cat "$BUILD/.source_sha" 2>/dev/null)" != "$SRC_SHA" ]; then
    rm -f "$BUILD/TikaBatch.class"
    rm -rf "$HOME/p0_build_jars"; docker rm -f p0jars >/dev/null 2>&1
    docker create --name p0jars rr:patched >/dev/null && docker cp p0jars:/opt/rocketride/engine/java/lib "$HOME/p0_build_jars" && docker rm p0jars >/dev/null || return 1
    docker run --rm -v "$HOME/p0_build_jars:/jars:ro" -v "$(pwd)/working/tika:/src:ro" -v "$BUILD:/out" eclipse-temurin:17-jdk \
      javac --release 17 -cp "/jars/*" -d /out /src/TikaBatch.java || return 1
    echo "$SRC_SHA" > "$BUILD/.source_sha"
  fi
  echo "TikaBatch.class sha256 $(sha256sum "$BUILD/TikaBatch.class" | cut -d' ' -f1)  source sha256 $(sha256sum working/tika/TikaBatch.java | cut -d' ' -f1)"
  docker run --rm --entrypoint cat rr:patched /opt/rocketride/engine/java/tika-config.xml > "$BUILD/cfg/shipped.xml" || return 1
  "$PY" - "$BUILD/cfg" <<'PYCFG' || return 1
import hashlib, sys, pathlib
d = pathlib.Path(sys.argv[1]); base = (d / "shipped.xml").read_text()
for label, param in (("no_sortByPosition", "sortByPosition"), ("no_acroform", "extractAcroFormContent"),
                     ("no_annotations", "extractAnnotationText"), ("no_bookmarks", "extractBookmarksText")):
    old = f'<param name="{param}" type="bool">true</param>'
    assert base.count(old) == 1, f"{param}: expected exactly one enabled occurrence"
    (d / f"{label}.xml").write_text(base.replace(old, old.replace(">true<", ">false<")))
for f in sorted(d.glob("*.xml")):
    print(f"config {f.name} sha256 {hashlib.sha256(f.read_bytes()).hexdigest()}")
PYCFG
  "$HOME/p0venv/bin/pip" install -q "pypdf==6.15.0" 2>&1 | grep -v "notice" || true
  "$HOME/p0venv/bin/python" -c 'import sys, pypdf, pypdfium2; from importlib.metadata import version as v; print("p0venv python", sys.version.split()[0], "pypdf", pypdf.__version__, "pypdfium2", v("pypdfium2"), "pdfium", getattr(pypdfium2, "PDFIUM_INFO", "?"))'
}

upload() {  # $1 = sub dir of $D
  local dest="s3://rocketride-benchmark-data/ansh/parity-p0/$REL/$1/"
  if aws s3 ls "$dest" >/dev/null 2>&1; then echo "!! $dest exists — not uploading over it"; return 1; fi
  aws s3 cp "$D/$1" "$dest" --recursive --only-show-errors && echo "uploaded $dest"
}

phase() {  # <outsub> <label> <parser> <docs> <workers> [--config cfg]
  local sub="$1" label="$2" parser="$3" docs="$4" w="$5"; shift 5
  echo "===== PHASE $label ($parser, $w workers) $(date -u +%H:%M:%SZ) ====="
  "$PY" working/scripts/p0_parse_bench.py --parser "$parser" --docs "$docs" --label "$label" \
    --out "$D/$sub" --workers "$w" --timeout 1800 --warmup-doc "$WARMUP" "$@"
  echo "===== PHASE $label rc=$? $(date -u +%H:%M:%SZ) ====="
}

case "$STAGE" in
  h5)
    build || { echo "BUILD FAILED"; exit 4; }
    mkdir -p "$D/h5"
    # 11 documents x (shipped twice + four single-feature variants), longest in-engine hold
    # first, each document's six jobs adjacent so they run under the same load.
    "$PY" - "$D/h5/jobs.jsonl" "$ELEVEN" <<'PYJOBS'
import json, sys
order = ["011_011464.pdf", "039_039660.pdf", "008_008871.pdf", "011_011730.pdf", "014_014261.pdf",
         "000_000344.pdf", "031_031239.pdf", "002_002489.pdf", "034_034697.pdf", "033_033172.pdf",
         "014_014969.pdf"]
assert sorted(order) == sorted(sys.argv[2].split(","))
with open(sys.argv[1], "x") as f:
    for d in order:
        for cfg, lab, rep in (("shipped.xml", "h5_shipped_r1", 1), ("shipped.xml", "h5_shipped_r2", 2),
                              ("no_sortByPosition.xml", "h5_no_sortByPosition", 1),
                              ("no_acroform.xml", "h5_no_acroform", 1),
                              ("no_annotations.xml", "h5_no_annotations", 1),
                              ("no_bookmarks.xml", "h5_no_bookmarks", 1)):
            f.write(json.dumps({"doc": d, "config": cfg, "label": lab, "rep": rep}) + "\n")
PYJOBS
    cp "$BUILD"/cfg/*.xml "$D/h5/" 2>/dev/null
    echo "===== H5 $(date -u +%H:%M:%SZ) ====="
    "$PY" working/scripts/p0_parse_bench.py --parser tika --jobs "$D/h5/jobs.jsonl" --fresh \
      --warmup-doc "$WARMUP" --label h5 --docs "$ELEVEN" --out "$D/h5" --workers 12 --timeout 2400
    echo "===== H5 rc=$? $(date -u +%H:%M:%SZ) ====="
    upload h5
    ;;
  h6smoke)
    build || { echo "BUILD FAILED"; exit 4; }
    cp "$BUILD"/cfg/*.xml "$D/" 2>/dev/null; mkdir -p "$D/h6smoke"
    # (i) the 11, every parser, 11 workers (one per document); (ii) the 384 slice, 12 workers (12 x 4g heap fits the box)
    phase h6smoke h6_tail_tika_shipped tika "$ELEVEN" 11 --config "$BUILD/cfg/shipped.xml"
    [ -n "$ARG4" ] && phase h6smoke h6_tail_tika_best tika "$ELEVEN" 11 --config "$BUILD/cfg/$ARG4"
    phase h6smoke h6_tail_pypdf pypdf "$ELEVEN" 11
    phase h6smoke h6_tail_pypdfium2 pypdfium2 "$ELEVEN" 11
    phase h6smoke h6_384_tika_shipped tika "$S384" 12 --config "$BUILD/cfg/shipped.xml"
    [ -n "$ARG4" ] && phase h6smoke h6_384_tika_best tika "$S384" 12 --config "$BUILD/cfg/$ARG4"
    phase h6smoke h6_384_pypdf pypdf "$S384" 12
    phase h6smoke h6_384_pypdfium2 pypdfium2 "$S384" 12
    CANDS="h6_384_pypdf,h6_384_pypdfium2${ARG4:+,h6_384_tika_best}"
    "$PY" working/scripts/p0_parse_fidelity.py --texts "$HOME/p0_texts" --ref h6_384_tika_shipped --cands "$CANDS" --docs "$S384" --out "$D/h6smoke/fidelity_384.jsonl"
    upload h6smoke
    ;;
  h6best)
    # H5's gate fired AFTER h6smoke ran: the best-config Tika phases alone, same workers/timeouts,
    # in their own directory (the analyser merges them into the smoke analysis)
    [ -n "$ARG4" ] || { echo "REFUSED: h6best needs the best config name" >&2; exit 2; }
    build || { echo "BUILD FAILED"; exit 4; }
    mkdir -p "$D/h6best"
    phase h6best h6_tail_tika_best tika "$ELEVEN" 11 --config "$BUILD/cfg/$ARG4"
    phase h6best h6_384_tika_best tika "$S384" 12 --config "$BUILD/cfg/$ARG4"
    "$PY" working/scripts/p0_parse_fidelity.py --texts "$HOME/p0_texts" --ref h6_384_tika_shipped --cands h6_384_tika_best --docs "$S384" --out "$D/h6best/fidelity_384_best.jsonl"
    upload h6best
    ;;
  h6full|h6hybrid)
    [ -f "$D/h6_gate.json" ] || { echo "REFUSED: $D/h6_gate.json (the committed smoke-gate outcome) is absent" >&2; exit 5; }
    build || { echo "BUILD FAILED"; exit 4; }
    mkdir -p "$D/$STAGE"
    phase "$STAGE" "${STAGE}_tika_shipped" tika "$S9975" 12 --config "$BUILD/cfg/shipped.xml"
    if [ "$STAGE" = "h6full" ]; then
      [ -n "$ARG4" ] && phase h6full h6full_tika_best tika "$S9975" 12 --config "$BUILD/cfg/$ARG4"
      phase h6full h6full_pypdf pypdf "$S9975" 12
      phase h6full h6full_pypdfium2 pypdfium2 "$S9975" 12
      CANDS="h6full_pypdf,h6full_pypdfium2${ARG4:+,h6full_tika_best}"
      "$PY" working/scripts/p0_parse_fidelity.py --texts "$HOME/p0_texts" --ref h6full_tika_shipped --cands "$CANDS" --docs "$S9975" --out "$D/h6full/fidelity_9975.jsonl"
    else
      phase h6hybrid "h6hybrid_$ARG4" "$ARG4" "$S9975" 12
    fi
    upload "$STAGE"
    ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
"$PY" - "$D/chain_parse_${STAGE}_done.json" <<'PYDONE'
import json, sys, time
json.dump({"stage_complete_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip()},
          open(sys.argv[1], "x"), indent=1)
PYDONE
aws s3 cp "$D/chain_parse_${STAGE}_done.json" "s3://rocketride-benchmark-data/ansh/parity-p0/$REL/chain_parse_${STAGE}_done.json" --only-show-errors
echo "CHAIN_DONE parse $STAGE"
