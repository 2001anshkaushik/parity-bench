#!/usr/bin/env python3
"""READ-ONLY query: what chunk size did Phase 1's RocketRide arm ACTUALLY produce?

Adjudicates the register candidate found 2026-08-20: engine 3.3.1 source says a
product_pdf.pipe-shaped config chunks at RecursiveCharacterTextSplitter
(chunk_size=strlen=512, chunk_overlap=0 hardcoded — preprocessor_langchain
langchain.py:167-168,314-315), while Phase 1 exports assert chunk_size=4000 /
chunk_overlap=200 (smoke50_parser_in.py:989-990) and the cross_arm gate fed
chunk_config_parity((4000,200),(4000,200)) as a config assertion (:1190-1191).
The LlamaIndex arm ran WS1_CHUNK_SIZE=4000. If the box RR records show ~512,
Phase 1's exported RR chunk_config was wrong and the workload ratio between
arms was ~8x by configuration.

WHAT THE RECORDS CAN AND CANNOT SAY. Phase 1 records carry, per document:
n_chunks, chars (SUM of chunk lengths), chunk_sha256 (hashes). Per-chunk
lengths were not exported, so this reports the PER-RECORD MEAN (chars /
n_chunks) and its distribution. That is decisive anyway: a mean chunk length
can never exceed the splitter's chunk_size, so any concentration of
per-record means well above 512 disproves 512, and means capped at <=512
disprove 4000. Records with n_chunks == 1 give one exact chunk length each
and are reported separately.

Discipline:
  - Opens everything read-only; writes ONLY its own --out file (default
    ./query_phase1_chunks_<UTC>.json in the current directory).
  - Touches no Phase 1 artifact, no STATE.md, no RUN_INVENTORY.md.
  - Exits non-zero if no RocketRide-arm records are found, naming exactly
    what it looked for and where.

Run on the box from the repo root:
    python3 working/video/query_phase1_chunks.py
    python3 working/video/query_phase1_chunks.py --roots working/results /data/results --glob '*.json' --glob '*.jsonl'
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

RR_ARM_MARKERS = ('rocketride', 'rr_')  # arm keys / filenames that mean the RocketRide arm
RECORD_FIELDS = ('n_chunks', 'chars')   # what a usable record must carry


def is_rr_name(name: str) -> bool:
    n = name.lower()
    return 'rocketride' in n or n.startswith('rr') or '_rr' in n


def iter_record_sets(path: Path):
    """Yield (label, records) for every RR-arm record list found in one file."""
    try:
        if path.suffix == '.jsonl':
            records = []
            with path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # torn last line tolerated, same rule as jsonl_stream
                    if isinstance(rec, dict) and all(k in rec for k in RECORD_FIELDS):
                        records.append(rec)
            if records and (is_rr_name(path.name) or any(is_rr_name(str(r.get('arm', ''))) for r in records[:5])):
                yield (path.name, records)
            return
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return

    def walk(obj, trail):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from walk(v, trail + (str(k),))
        elif (isinstance(obj, list) and obj and isinstance(obj[0], dict)
              and all(f in obj[0] for f in RECORD_FIELDS)):
            arm = next((t for t in reversed(trail) if is_rr_name(t)), None)
            if arm:
                yield ('/'.join(trail), obj)

    yield from walk(data, (path.name,))


def summarize(records: list[dict]) -> dict:
    usable = [r for r in records if (r.get('n_chunks') or 0) > 0 and (r.get('chars') or 0) > 0]
    means = [r['chars'] / r['n_chunks'] for r in usable]
    singles = [r['chars'] for r in usable if r['n_chunks'] == 1]
    n_chunks = [r['n_chunks'] for r in usable]
    hist = Counter()
    for m in means:
        lo = int(m // 256) * 256
        hist[f'{lo}-{lo + 255}'] += 1
    means_sorted = sorted(means)

    def pct(p):  # nearest-rank on the per-record means, rank stated by the caller's table
        return round(means_sorted[max(0, int(p * len(means_sorted)) - 1)], 1) if means_sorted else None

    return {
        'records_total': len(records),
        'records_usable': len(usable),
        'records_zero_or_missing': len(records) - len(usable),
        'mean_chunk_chars': {
            'min': round(min(means), 1) if means else None,
            'median': pct(0.5),
            'mean_of_means': round(sum(means) / len(means), 1) if means else None,
            'max': round(max(means), 1) if means else None,
            'histogram_256char_bins': dict(sorted(hist.items(), key=lambda kv: int(kv[0].split('-')[0]))),
        },
        'exact_single_chunk_lengths': sorted(singles)[:50],
        'n_single_chunk_records': len(singles),
        'chunks_per_document': {
            'min': min(n_chunks) if n_chunks else None,
            'median': sorted(n_chunks)[len(n_chunks) // 2] if n_chunks else None,
            'max': max(n_chunks) if n_chunks else None,
            'total_chunks': sum(n_chunks),
        },
        'verdict_hint': (
            None if not means else
            'consistent with chunk_size<=512 (no per-record mean exceeds 512)'
            if max(means) <= 512 else
            'INCONSISTENT with chunk_size=512 (means exceed 512 — consistent with a larger chunk_size, e.g. 4000)'
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--roots', nargs='*', default=['working/results'],
                    help='directories to search (read-only)')
    ap.add_argument('--glob', action='append', default=None,
                    help="filename patterns (default: '*.json' and '*.jsonl')")
    ap.add_argument('--out', default=f'query_phase1_chunks_{time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}.json')
    args = ap.parse_args()
    patterns = args.glob or ['*.json', '*.jsonl']

    searched, found = [], {}
    for root in args.roots:
        rootp = Path(root)
        for pat in patterns:
            searched.append(f'{rootp}/{pat} (recursive)')
            if not rootp.exists():
                continue
            for path in sorted(rootp.rglob(pat)):
                for label, records in iter_record_sets(path) or []:
                    found[f'{path}::{label}'] = summarize(records)

    report = {
        'question': 'Phase 1 RocketRide-arm actual chunk size (512 vs 4000)',
        'searched': searched,
        'record_fields_required': list(RECORD_FIELDS),
        'rr_arm_markers': list(RR_ARM_MARKERS),
        'legs_found': len(found),
        'results': found,
        'caveat': ('local laptop results are macOS wiring validation and include a driver-side '
                   'RR stand-in chunked at 4000/200 — only records produced against the EXTERNAL '
                   'engine container adjudicate the register question. Run this on the box.'),
    }
    Path(args.out).write_text(json.dumps(report, indent=1))

    if not found:
        print('NOT FOUND — no RocketRide-arm record lists with fields '
              f'{RECORD_FIELDS} under: ' + '; '.join(searched))
        print(f'(search report still written to {args.out})')
        return 1

    print(f'{len(found)} RR-arm record set(s):')
    for label, s in found.items():
        mm = s['mean_chunk_chars']
        print(f'  {label}\n    records={s["records_usable"]}/{s["records_total"]} '
              f'mean-chunk-chars min/med/max = {mm["min"]}/{mm["median"]}/{mm["max"]} '
              f'chunks/doc med={s["chunks_per_document"]["median"]} -> {s["verdict_hint"]}')
    print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
