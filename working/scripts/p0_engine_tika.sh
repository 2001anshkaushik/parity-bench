#!/usr/bin/env bash
# p0_engine_tika.sh — amendment 5, exploratory DIAGNOSTIC E1 (no gate): the ENGINE's own parse path
# on the 11 long-hold documents, outside any pipeline.
#
#   bash working/scripts/p0_engine_tika.sh <campaign_dir> <expect_head>
#
# Three readings per document become comparable: isolated Tika (H5, TikaBatch: the engine's jars,
# JRE and tika-config.xml, BodyContentHandler), the engine's own `engine --tika <document>` CLI
# (its JNI wrapper com.rocketride.tika_api.TikaApi, which enables PDF inline-image extraction and
# probes external media tools), and the in-pipeline parse bracket (S5-D stamps). One fresh rr:patched
# container per document (entrypoint replaced; the image is only read), all 11 at once, timeout
# 2,400 s. A box-wide bpftrace exec census runs over the whole stage (nothing else runs on the box,
# Ruling C), so the count of process spawns is attributable to these parses.
set -uo pipefail
echo "p0_engine_tika.sh sha256: $(sha256sum "$0" | cut -d' ' -f1)"
[ "$#" -eq 2 ] || { echo "usage: $0 <campaign_dir> <expect_head>" >&2; exit 2; }
D="$1"; H="$2"
cd "$(dirname "$0")/../.." || exit 2
. working/harness/results_prefix.sh || exit 2
REL="$(results_rel "$D")" || exit 2
[ -f "$D/preregistration_amendment_5.json" ] || { echo "REFUSED: amendment 5 absent" >&2; exit 5; }
HAVE="$(git rev-parse HEAD | cut -c1-12)"; [ "$HAVE" = "$(echo "$H" | cut -c1-12)" ] || { echo "REFUSED: head $HAVE" >&2; exit 2; }
for c in rr li; do docker inspect "$c" >/dev/null 2>&1 && { echo "REFUSED: '$c' running" >&2; exit 3; }; done
CORPUS="$HOME/parity-bench/corpus/govdocs1/pdfs"
OUT="$D/e1_engine_tika"; mkdir -p "$OUT" || exit 2
ELEVEN="011_011464.pdf 039_039660.pdf 008_008871.pdf 011_011730.pdf 014_014261.pdf 000_000344.pdf 031_031239.pdf 002_002489.pdf 034_034697.pdf 033_033172.pdf 014_014969.pdf"
echo "boot_id $(cat /proc/sys/kernel/random/boot_id)  head $HAVE"
# box-wide exec census: every exec'd path and its count, printed on SIGINT
sudo -n bpftrace -f json -o "$OUT/exec_census.json" -e 'tracepoint:sched:sched_process_exec { @exec[str(args->filename)] = count(); }' </dev/null > "$OUT/exec_census.log" 2>&1 &
sleep 5
BPID="$(pgrep -f "exec_census.json" | while read p; do [ "$(cat /proc/$p/comm 2>/dev/null)" = bpftrace ] && echo $p; done | head -1)"
echo "exec census pid: ${BPID:-NONE}"
run_one() {
  local doc="$1" n="p0et_${1%.pdf}" t0 t1 rc
  t0=$(date +%s.%N)
  timeout 2400 docker run --rm --name "$n" -v "$CORPUS:/corpus:ro" --entrypoint /opt/rocketride/engine/engine rr:patched --tika "/corpus/$doc" > "$OUT/${doc}.out" 2> "$OUT/${doc}.err"
  rc=$?
  t1=$(date +%s.%N)
  [ "$rc" = 124 ] && docker rm -f "$n" >/dev/null 2>&1
  echo "{\"doc\": \"$doc\", \"wall_s\": $(python3 -c "print(round($t1 - $t0, 3))"), \"rc\": $rc, \"stdout_bytes\": $(wc -c < "$OUT/${doc}.out"), \"stderr_bytes\": $(wc -c < "$OUT/${doc}.err")}" >> "$OUT/results_e1.jsonl"
}
PIDS=()
for doc in $ELEVEN; do run_one "$doc" & PIDS+=($!); done
wait "${PIDS[@]}"          # the parses only — never the census, which runs until its SIGINT
[ -n "${BPID:-}" ] && sudo -n kill -INT "$BPID"; sleep 3
# keep only the head and tail of each document's output (the text itself is not the point)
for doc in $ELEVEN; do
  head -c 2000 "$OUT/${doc}.out" > "$OUT/${doc}.out.head"; tail -c 2000 "$OUT/${doc}.out" > "$OUT/${doc}.out.tail"; rm -f "$OUT/${doc}.out"
  tail -c 4000 "$OUT/${doc}.err" > "$OUT/${doc}.err.tail"; rm -f "$OUT/${doc}.err"
done
dest="s3://rocketride-benchmark-data/ansh/parity-p0/$REL/e1_engine_tika/"
aws s3 ls "$dest" >/dev/null 2>&1 && { echo "!! $dest exists"; exit 1; }
aws s3 cp "$OUT" "$dest" --recursive --only-show-errors && echo "uploaded $dest"
echo "CHAIN_DONE e1"
