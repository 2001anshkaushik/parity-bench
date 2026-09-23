#!/usr/bin/env bash
# p0_runtime_versions.sh — V2's pre-registered reading: an unequal forward-pass time at equal T is a
# model-runtime configuration difference, "to be named from both images (torch, oneDNN/MKL, dtype,
# input size)". Read-only: each image is only RUN with its entrypoint replaced to list files; nothing
# is imported into a measured process, nothing is written to an image. Run with the box quiet (after
# the last measured leg).
#
#   bash working/scripts/p0_runtime_versions.sh <campaign_dir>
set -uo pipefail
D="$1"; OUT="$D/runtime_versions"; mkdir -p "$OUT"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || exit 2
for c in rr li li_bal_0; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: '$c' running" >&2; exit 3; }; done
read_image() {  # $1 image  $2 label
  docker run --rm --entrypoint sh "$1" -c '
    for v in $(find / -path "*/torch/version.py" -not -path "/proc/*" 2>/dev/null); do echo "== $v"; cat "$v"; done
    for d in $(find / -maxdepth 8 -type d \( -name "torch-*.dist-info" -o -name "torchvision-*.dist-info" -o -name "rfdetr-*.dist-info" -o -name "transformers-*.dist-info" -o -name "numpy-*.dist-info" -o -name "onnxruntime*.dist-info" \) -not -path "/proc/*" 2>/dev/null); do echo "== dist-info: $d"; done
    for f in $(find / -path "*/torch/lib/*" \( -name "libmkl*" -o -name "libgomp*" -o -name "libiomp*" -o -name "libdnnl*" -o -name "libmkldnn*" \) -not -path "/proc/*" 2>/dev/null); do echo "== lib: $f"; done
    echo "== cpu flags seen by the image:"; grep -m1 -o "avx512[a-z_]*\|amx[a-z_]*" /proc/cpuinfo | sort -u | tr "\n" " "; echo
  ' > "$OUT/$2.txt" 2>&1
  echo "$2: $(grep -c '' "$OUT/$2.txt") lines"
}
read_image rr:patched-video rr_patched_video
read_image li:video li_video
read_image rr:patched rr_patched_docs
read_image ws1-llamaindex:x86_64 li_docs
dest="s3://rocketride-benchmark-data/ansh/parity-p0/$REL/runtime_versions/"
aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists"; exit 1; }
aws s3 cp "$OUT" "$dest" --recursive --only-show-errors && echo "uploaded $dest"
echo "CHAIN_DONE runtime_versions"
