#!/usr/bin/env python3
"""AMI video-corpus fetcher + sha-pinned manifest builder (Phase 2, video signal).

Discipline carried from fetch_govdocs.py (defect #28's fix): the corpus is
defined by the MANIFEST, not by a counter. DONE means verified-against-manifest
— every file present, every byte hashed; anything else exits non-zero and
names the files. Fetch-as-shipped: NO mux (audio is out this phase; the AMI
AVIs are video-only), so corpus bytes are upstream bytes and the sha pins are
the mirror's own artifacts.

Two modes:

BUILD MODE (--build-manifest): constructs the manifest ONCE. Walks the
scenario-meeting id space in sorted order (ES2002a..ES2016d, IS1000a..IS1009d,
TS3003a..TS3012d), tries views in the recorded preference order
(Corner, then Overhead), downloads the first hit, sha256s it, parses the AVI
header for duration/fps/frame count (the census input that makes
expected-frame-count manifest-derivable), and assigns roles: first N_MEASURED
usable meetings -> measured, next N_WARM -> warm (driver-side warm-up,
disjoint from the measured set). Meetings with no available view are recorded
as skipped, with the reason, and later ids fill the quota. Run on the box.

MANIFEST MODE (default, manifest present): downloads only what is missing,
then verifies EVERYTHING against the manifest (size always, sha256 with
--verify) before printing DONE. Never uses a counter as evidence.

Layout: corpus/ami/video/<MEETING>.<View>.avi ; manifest at
working/video/ami_video_manifest.jsonl (one JSON object per line; first line
is a _meta header).
"""

import argparse
import hashlib
import json
import struct
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'working' / 'video' / 'ami_video_manifest.jsonl'
CORPUS = ROOT / 'corpus' / 'ami' / 'video'
MIRROR = 'https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus'

VIEW_PREFERENCE = ['Corner', 'Overhead']  # selection rule; fallback recorded per row
N_MEASURED = 48
N_WARM = 16

# Planning-column assumptions (approved 2026-08-20, ruling 5). The engine's
# splitter runs at LangChain LIBRARY DEFAULTS 4000/200 (its own size config is
# inert — see the 2026-08-20 adjudication), so net new chars per chunk ~= 3800.
# Chars/frame from detect JSON: ~185 chars/detection, assumed 5/10/15
# detections per frame for low/mid/high. These are PLANNING ESTIMATES ONLY:
# the duplication gate uses MEASURED n_chunks, and the run plan should
# re-derive eligibility from the probe's measured chars/frame + these
# durations rather than refetching.
INTERVAL_S = 15
CHUNK_STRIDE = 4000 - 200
CHARS_PER_FRAME = {'low': 900, 'mid': 1850, 'high': 2800}
DUP_TRIGGER_CHUNKS = 64


def derived_columns(video_s: float) -> dict:
    """Planning columns from duration alone. expected_frames_15s is EXACT
    (frames at t = 0, 15, ... strictly below duration — same formula as
    driver_video.expected_frames, pinned by the probe at 84 on ES2002a);
    chunk counts are banded estimates under the module-level assumptions."""
    frames = int(video_s // INTERVAL_S) + (1 if video_s % INTERVAL_S else 0)
    est = {band: -(-frames * cpf // CHUNK_STRIDE)  # ceil
           for band, cpf in CHARS_PER_FRAME.items()}
    return {
        'expected_frames_15s': frames,
        'est_chunks_low': est['low'],
        'est_chunks_mid': est['mid'],
        'est_chunks_high': est['high'],
        'dup_trigger_eligible_est': est['mid'] >= DUP_TRIGGER_CHUNKS,
    }


def scenario_meeting_ids() -> list[str]:
    """The deterministic candidate order: scenario series, sorted."""
    ids = []
    for s in range(2002, 2017):        # ES2002..ES2016
        ids += [f'ES{s}{x}' for x in 'abcd']
    for s in range(1000, 1010):        # IS1000..IS1009
        ids += [f'IS{s}{x}' for x in 'abcd']
    for s in range(3003, 3013):        # TS3003..TS3012
        ids += [f'TS{s}{x}' for x in 'abcd']
    return sorted(ids)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def parse_avi_header(p: Path) -> dict:
    """Duration/fps/frames/streams from the RIFF header. Raises on non-AVI."""
    data = p.open('rb').read(2_000_000)
    if data[:4] != b'RIFF' or data[8:12] != b'AVI ':
        raise ValueError('not an AVI (RIFF header mismatch)')
    info = {'streams': []}

    def walk(i, end):
        while i < end - 8:
            fcc = data[i:i + 4]
            size = struct.unpack('<I', data[i + 4:i + 8])[0]
            if fcc == b'LIST' and data[i + 8:i + 12] in (b'hdrl', b'strl'):
                walk(i + 12, i + 8 + size)
            elif fcc == b'avih':
                us, = struct.unpack('<I', data[i + 8:i + 12])
                tf, = struct.unpack('<I', data[i + 24:i + 28])
                w, h = struct.unpack('<II', data[i + 40:i + 48])
                info.update(width=w, height=h, total_frames=tf,
                            fps=round(1e6 / us, 3) if us else None,
                            video_s=round(tf * us / 1e6, 1) if us else None)
            elif fcc == b'strh':
                stype = data[i + 8:i + 12].decode(errors='replace')
                info['streams'].append(stype)
            i += 8 + size + (size & 1)

    walk(12, len(data))
    return info


def fetch_url(url: str, dest: Path, timeout: int = 120) -> bool:
    """Download url -> dest. False on 404, raises on other errors."""
    tmp = dest.with_suffix('.part')
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, tmp.open('wb') as out:
            while True:
                block = resp.read(1 << 20)
                if not block:
                    break
                out.write(block)
        tmp.rename(dest)
        return True
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        if e.code == 404:
            return False
        raise
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def load_manifest():
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    meta = rows[0] if rows and '_meta' in rows[0] else {}
    return meta, [r for r in rows if '_meta' not in r]


def build_mode(n_measured: int, n_warm: int) -> int:
    print(f'BUILD MODE: constructing {MANIFEST.name} for {n_measured} measured + {n_warm} warm '
          f'(views tried in order {VIEW_PREFERENCE}). This downloads everything once.', flush=True)
    CORPUS.mkdir(parents=True, exist_ok=True)
    rows, skips = [], []
    reused = fetched = 0
    need = n_measured + n_warm
    for mid in scenario_meeting_ids():
        if len(rows) >= need:
            break
        picked = None
        for view in VIEW_PREFERENCE:
            fname = f'{mid}.{view}.avi'
            url = f'{MIRROR}/{mid}/video/{fname}'
            dest = CORPUS / fname
            if dest.exists():
                reused += 1
                picked = (view, fname, url, dest)
                break
            if fetch_url(url, dest):
                fetched += 1
                picked = (view, fname, url, dest)
                break
        if picked is None:
            skips.append({'meeting': mid, 'reason': f'no view in {VIEW_PREFERENCE} on mirror'})
            print(f'  skip {mid}: no available view', flush=True)
            continue
        view, fname, url, dest = picked
        try:
            hdr = parse_avi_header(dest)
        except ValueError as e:
            skips.append({'meeting': mid, 'reason': f'{fname}: {e}'})
            print(f'  skip {mid}: {e}', flush=True)
            continue
        row = {
            'seq': len(rows),
            'meeting': mid,
            'view': view,
            'view_fallback': view != VIEW_PREFERENCE[0],
            'file': fname,
            'url': url,
            'bytes': dest.stat().st_size,
            'sha256': sha256_file(dest),
            'video_s': hdr.get('video_s'),
            'total_frames': hdr.get('total_frames'),
            'fps': hdr.get('fps'),
            'width': hdr.get('width'),
            'height': hdr.get('height'),
            'streams': hdr.get('streams'),
            'role': 'measured' if len(rows) < n_measured else 'warm',
        }
        row.update(derived_columns(hdr.get('video_s') or 0.0))
        rows.append(row)
        print(f'  [{len(rows)}/{need}] {fname} {row["bytes"]/1e6:.1f}MB '
              f'{row["video_s"]}s {row["role"]}' + (' (fallback view)' if row['view_fallback'] else ''),
              flush=True)

    if len(rows) < need:
        print(f'NOT DONE — only {len(rows)}/{need} meetings available; skips: {len(skips)}', flush=True)
        return 1

    meta = {'_meta': {
        'built_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'mirror': MIRROR,
        'selection_rule': ('scenario meetings (ES2002-16, IS1000-09, TS3003-12) x abcd, sorted by id; '
                           f'views tried in order {VIEW_PREFERENCE}; first {n_measured} usable = measured, '
                           f'next {n_warm} = warm (disjoint); unavailable meetings skipped and recorded'),
        'n_measured': n_measured, 'n_warm': n_warm,
        'mux': 'none — fetched as shipped (video-only AVIs; audio out of scope this phase)',
        'planning_columns': {
            'interval_s': INTERVAL_S,
            'chunk_stride': CHUNK_STRIDE,
            'chars_per_frame_assumed': CHARS_PER_FRAME,
            'dup_trigger_chunks': DUP_TRIGGER_CHUNKS,
            'note': ('est_chunks_* and dup_trigger_eligible_est are PLANNING '
                     'estimates from duration under the stated assumptions; the '
                     'duplication gate uses MEASURED n_chunks (NOT-RUN below 64, '
                     'approved rule), and eligibility should be re-derived from '
                     'the probe\'s measured chars/frame before the run plan '
                     'fixes leg composition.'),
        },
        'skipped': skips,
    }}
    with MANIFEST.open('w') as fh:
        fh.write(json.dumps(meta) + '\n')
        for r in rows:
            fh.write(json.dumps(r) + '\n')
    total_gb = sum(r['bytes'] for r in rows) / 1e9
    print(f'manifest written: {MANIFEST} ({len(rows)} rows, {total_gb:.2f} GB, {len(skips)} skips)', flush=True)
    print(f'REUSE PROOF: {reused} files reused from disk, {fetched} downloaded '
          f'(a re-cut over an existing corpus must show fetched=0)', flush=True)
    print('Re-run without --build-manifest to verify; DONE only comes from manifest mode.', flush=True)
    return 0


def manifest_mode(verify_sha: bool) -> int:
    if not MANIFEST.exists():
        print(f'NOT DONE — no manifest at {MANIFEST}. Build one on the box with --build-manifest.')
        return 1
    meta, rows = load_manifest()
    CORPUS.mkdir(parents=True, exist_ok=True)
    print(f'MANIFEST MODE: {len(rows)} files defined by {MANIFEST.name} '
          f'(built {meta.get("_meta", {}).get("built_utc", "?")})', flush=True)

    missing = [r for r in rows if not (CORPUS / r['file']).exists()]
    for i, r in enumerate(missing, 1):
        print(f'  fetch [{i}/{len(missing)}] {r["file"]}', flush=True)
        if not fetch_url(r['url'], CORPUS / r['file']):
            print(f'NOT DONE — {r["url"]} returned 404; the mirror no longer matches the manifest.')
            return 1

    print('verifying against the manifest ...', flush=True)
    bad = []
    for r in rows:
        p = CORPUS / r['file']
        if not p.exists():
            bad.append((r['file'], 'missing'))
        elif p.stat().st_size != r['bytes']:
            bad.append((r['file'], f'size {p.stat().st_size} != {r["bytes"]}'))
        elif verify_sha and sha256_file(p) != r['sha256']:
            bad.append((r['file'], 'sha256 mismatch'))
    if bad:
        print('NOT DONE — the corpus does not match the manifest:')
        for f, why in bad:
            print(f'  {f}: {why}')
        return 1
    print(f'DONE verified={len(rows)}/{len(rows)} against {MANIFEST.name} '
          f'({"sha256" if verify_sha else "size only — pass --verify for sha256"}); '
          f'roles: {sum(1 for r in rows if r["role"] == "measured")} measured, '
          f'{sum(1 for r in rows if r["role"] == "warm")} warm', flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-manifest', action='store_true',
                    help='discovery: construct the manifest (run ONCE, on the box)')
    ap.add_argument('--verify', action='store_true', help='manifest mode: sha256 every file')
    ap.add_argument('--n-measured', type=int, default=N_MEASURED)
    ap.add_argument('--n-warm', type=int, default=N_WARM)
    ap.add_argument('--manifest', default=None, help='override manifest path (wiring tests)')
    ap.add_argument('--corpus-dir', default=None, help='override corpus dir (wiring tests)')
    args = ap.parse_args()
    global MANIFEST, CORPUS
    if args.manifest:
        MANIFEST = Path(args.manifest)
    if args.corpus_dir:
        CORPUS = Path(args.corpus_dir)
    if args.build_manifest:
        return build_mode(args.n_measured, args.n_warm)
    return manifest_mode(args.verify)


if __name__ == '__main__':
    sys.exit(main())
