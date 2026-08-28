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

MANIFEST MODE — four operations, each named, none wearing another's flag
(2026-08-23: the campaign died at step 0 because --verify, pointed at the wrong
directory, found every file "missing" and FETCHED — urlopen('') on a staged row):
  (no flag)            verify, size only, NEVER fetches   (the smoke's fast check)
  --verify             verify, sha256,    NEVER fetches   (run_plan step 0)
  --fetch-missing      provisioning: download rows that are absent AND carry a
                       url; a staged row (url '') is never fetched — it is named
                       and the run refuses. Then size-checks everything.
  --stamp-corpus-dir   full sha256 verify against --corpus-dir, and on N/N PASS
                       record that directory in _meta.corpus_dir (meta line only;
                       data rows byte-identical, asserted). Run ONCE per corpus.
A verify is read-only: it checks what is on disk against the manifest and
reports. A missing file is a finding, not a reason to go and get one.

WHERE THE CORPUS IS is never a default in this file (corpus_locator.py): the
manifest records the directory it was built or stamped against, every consumer
derives from it, and an explicit --corpus-dir must agree with it. Build mode
REQUIRES --corpus-dir (no manifest exists yet to derive from) and records it.

Layout: <corpus_dir>/<MEETING>.<View>.avi (or <MEETING>.avi when --staged);
manifest at working/video/ami_video_manifest.jsonl (one JSON object per line;
first line is a _meta header).
Box corpus layout note (measured 2026-08-28): corpus/ami/full = the staged
ami_full corpus (Closeup1 video + Mix-Headset PCM muxed per file; 170/170
carry an auds stream); corpus/ami/closeup1 is a DUPLICATE SUBSET of full/
(62/62 byte-identical to their full/ counterparts, all with audio), NOT a
separate raw-view directory; corpus/ami/video is the Corner-era location
(raw camera files, no audio).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argtypes import bounded_float, positive_int  # noqa: E402 — register entry 8
from corpus_locator import (CorpusDirError, META_KEY, STAMP_CMD,  # noqa: E402
                            manifest_corpus_dir, resolve_corpus_dir)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'working' / 'video' / 'ami_video_manifest.jsonl'
CORPUS: Path | None = None   # NEVER defaulted (2026-08-23): resolved from --corpus-dir
                             # or the manifest meta, see corpus_locator.py
MIRROR = 'https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus'

STAGED_NAMES = False   # --staged: files are '<meeting>.avi', pre-muxed, never fetched
MEETING_IDS: list = []      # --meeting-list: ids in FILE ORDER, overriding the generator
MEETING_LIST_PATH = None    # recorded in manifest meta with its sha256
VIEW_PREFERENCE = ['Corner', 'Overhead']  # selection rule; fallback recorded per row
# Crossroad 34 (2026-08-22): the corpus moves to Closeup1. Corner exists only in
# the ES rooms — IS names its room views C/L/R and TS names them Overview1/2 —
# so a Corner rule caps at ~60 meetings, which is why Crossroad 15 stayed
# ES-only. Closeup1 exists in ALL THREE instrumented room types, so it is the
# view that reaches the full scenario set. --view overrides the rule; --staged
# accepts files already muxed and named "<meeting>.avi" (the shape a staged
# corpus arrives in) and NEVER downloads: an absent file is a hard failure,
# because silently fetching a raw camera file in place of a staged one would
# put different bytes on our arm than on theirs.
N_MEASURED = 48
N_WARM = 16

# Crossroad 23 (2026-08-21): the expected-frame column is MEASURED, never
# derived. floor(d/15)+1 predicted 84 on ES2002a; the arms' ffmpeg emitted 83
# (the t=1245 slot never fires on a 1248.3 s stream). NO corrected formula —
# a replacement fitted to one observation on one file would reverse-engineer
# the check from the result, which is what gate 1 exists to prevent. Instead
# --build-manifest runs fps=1/15 through the SAME imageio-ffmpeg binary both
# arms use and counts emissions per row (~10-12 s/video). Register entry 5.
INTERVAL_S = 15
CHUNK_STRIDE = 4000 - 200      # LangChain library defaults 4000/200 (engine config inert)
DUP_TRIGGER_CHUNKS = 64
PNG_SIG = b'\x89PNG\r\n\x1a\n'


def measure_frames_ffmpeg(path: Path, interval_s: int = INTERVAL_S) -> int:
    """Count fps=1/interval emissions through the arms' own ffmpeg. The
    command AND the pipe:0 input mirror li_video/pipeline._extract_frames
    byte for byte (the measured exemplar — a file input is seekable where the
    arms' pipe is not, and conditions travel with measurements)."""
    import subprocess
    try:
        import imageio_ffmpeg
    except ImportError:
        raise SystemExit("NOT DONE — --build-manifest measures frames through the arms' "
                         'ffmpeg and needs imageio-ffmpeg: run under ~/.venv-floor '
                         '(the probe venv with the engine pins).')
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [exe, '-nostdin', '-loglevel', 'error', '-i', 'pipe:0',
           '-vf', f'fps=1/{interval_s}', '-f', 'image2pipe',
           '-fps_mode', 'passthrough', '-vcodec', 'png', '-']
    raw = subprocess.run(cmd, input=path.read_bytes(), check=True,
                         capture_output=True).stdout
    return raw.count(PNG_SIG)


def _ffmpeg_provenance() -> dict:
    """The measuring instrument, recorded into the manifest meta."""
    import imageio_ffmpeg
    return {'imageio_ffmpeg_version': getattr(imageio_ffmpeg, '__version__', '?'),
            'exe': imageio_ffmpeg.get_ffmpeg_exe()}


def est_columns_from_measured(frames: int, dpf: float, chars_per_det: float) -> dict:
    """Planning estimate from three MEASURED inputs: the per-row frame count
    above, plus detections/frame and chars/detection from the probe
    (summarize_probe_rr.py prints both). Still an ESTIMATE and labeled so —
    the duplication gate uses measured n_chunks at run time."""
    est = -(-int(frames * dpf * chars_per_det) // CHUNK_STRIDE)  # ceil
    return {'est_chunks_from_measured': est,
            'dup_trigger_eligible_from_measured': est >= DUP_TRIGGER_CHUNKS}


def meeting_ids_from_list(path: Path) -> list[str]:
    """Meeting ids in FILE ORDER from a checked-in set file (Crossroad 36).

    Adopting a teammate's corpus means adopting their ROW ORDER too: their
    convention is "first N by id measured, last M warm", and role assignment
    here is positional, so re-deriving the order from our own generator would
    silently produce a different measured/warm split over the same files. The
    set file IS the selection; we read it, we do not reconstruct it. Blank
    lines and #-comments are stripped; everything else is taken verbatim, in
    order, including families our own generator never emits (EN, IB)."""
    ids = []
    for line in path.read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            ids.append(line)
    return ids


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
    if not url:
        # A staged row carries url '' by design. Reaching here means a caller
        # decided to fetch without looking — refuse BEFORE the network, naming it.
        raise ValueError(f'fetch_url: empty url for {dest.name} — a staged row is never fetched')
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


def build_mode(n_measured: int, n_warm: int,
               dpf: float | None, chars_per_det: float | None) -> int:
    if dpf is None or chars_per_det is None:
        print('NOT DONE — --build-manifest needs --measured-dpf and --measured-chars-per-det '
              '(probe-measured; probe/summarize_probe_rr.py prints both from the probe '
              'outputs). Refusing to invent planning inputs.')
        return 1
    print(f'BUILD MODE: constructing {MANIFEST.name} for {n_measured} measured + {n_warm} warm '
          f'(views tried in order {VIEW_PREFERENCE}). This downloads everything once, and '
          f'MEASURES fps=1/{INTERVAL_S} per row through the arms\' ffmpeg (~10-12 s/video).',
          flush=True)
    CORPUS.mkdir(parents=True, exist_ok=True)
    rows, skips = [], []
    reused = fetched = 0
    need = n_measured + n_warm
    for mid in (MEETING_IDS if MEETING_IDS else scenario_meeting_ids()):
        if len(rows) >= need:
            break
        picked = None
        # STAGED (Crossroad 34): the file is "<meeting>.avi", already muxed by
        # whoever staged it, and we NEVER fetch a substitute — identical bytes
        # across all three arms is the whole point of adopting one corpus.
        for view in (['staged'] if STAGED_NAMES else VIEW_PREFERENCE):
            fname = f'{mid}.avi' if STAGED_NAMES else f'{mid}.{view}.avi'
            url = '' if STAGED_NAMES else f'{MIRROR}/{mid}/video/{fname}'
            dest = CORPUS / fname
            if dest.exists():
                reused += 1
                picked = (view, fname, url, dest)
                break
            if STAGED_NAMES:
                continue          # absent staged file -> recorded as a skip, never fetched
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
        t_measure = time.monotonic()
        row['expected_frames_measured'] = measure_frames_ffmpeg(dest)
        row.update(est_columns_from_measured(row['expected_frames_measured'],
                                             dpf, chars_per_det))
        rows.append(row)
        print(f'  [{len(rows)}/{need}] {fname} {row["bytes"]/1e6:.1f}MB '
              f'{row["video_s"]}s frames_measured={row["expected_frames_measured"]} '
              f'({time.monotonic()-t_measure:.0f}s) {row["role"]}'
              + (' (fallback view)' if row['view_fallback'] else ''),
              flush=True)

    if len(rows) < need:
        print(f'NOT DONE — only {len(rows)}/{need} meetings available; skips: {len(skips)}', flush=True)
        return 1

    meta = {'_meta': {
        'built_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'mirror': MIRROR,
        'selection_rule': (
            (f'meeting list {MEETING_LIST_PATH.name} taken in FILE ORDER '
             f'(sha256 {sha256_file(MEETING_LIST_PATH)[:16]}, {len(MEETING_IDS)} ids); '
             f'first {n_measured} = measured, next {n_warm} = warm (positional, matching the '
             f'list owner\'s convention); files are pre-staged and never fetched'
             if MEETING_IDS else
             'scenario meetings (ES2002-16, IS1000-09, TS3003-12) x abcd, sorted by id; '
             f'views tried in order {VIEW_PREFERENCE}; first {n_measured} usable = measured, '
             f'next {n_warm} = warm (disjoint); unavailable meetings skipped and recorded')),
        META_KEY: str(CORPUS.resolve()),   # the directory every consumer derives from
        'meeting_list': (str(MEETING_LIST_PATH) if MEETING_LIST_PATH else None),
        'meeting_list_sha256': (sha256_file(MEETING_LIST_PATH) if MEETING_LIST_PATH else None),
        'n_measured': n_measured, 'n_warm': n_warm,
        # Conditional since 2026-08-28: the old unconditional 'video-only,
        # mux none' sentence was FALSE on every staged ami_full row (the
        # corpus changed under the sentence — register entry 19's class).
        # The banked 170-row manifest artifact stays byte-frozen (its sha is
        # run provenance); the correction lives here and in the DEFINITIVE.
        'mux': (("pre-staged corpus accepted as-is (--staged): muxing was done by the "
                 "staging owner, not this tool. For ami_full: each file is the meeting's "
                 "Closeup1 camera video stream-copy-muxed with its Mix-Headset audio "
                 "(16 kHz mono PCM-in-AVI) by Leela's corpus/fetch_ami.sh; box-measured "
                 "2026-08-28: 170/170 files carry an auds stream, zero without")
                if STAGED_NAMES else
                'none — fetched as shipped (video-only AVIs; audio out of scope this phase)'),
        'measured_columns': {
            'interval_s': INTERVAL_S,
            'expected_frames_method': ('MEASURED at build (Crossroad 23): fps=1/15 through '
                                       "the arms' own imageio-ffmpeg binary via pipe:0, PNG "
                                       'emissions counted. No formula — arithmetic from a '
                                       'measured duration is still an assertion.'),
            'ffmpeg': _ffmpeg_provenance(),
            'measured_dpf': dpf,
            'measured_chars_per_det': chars_per_det,
            'chunk_stride': CHUNK_STRIDE,
            'dup_trigger_chunks': DUP_TRIGGER_CHUNKS,
            'note': ('est_chunks_from_measured derives from three measured inputs '
                     '(per-row frames, probe dpf, probe chars/det) and is STILL an '
                     'estimate, planning only; the duplication gate uses MEASURED '
                     'n_chunks at run time (NOT-RUN below 64, approved rule).'),
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


def _check_rows(rows, corpus: Path, sha: bool):
    bad = []
    for r in rows:
        pth = corpus / r['file']
        if not pth.exists():
            bad.append((r['file'], f'missing from {corpus}'))
        elif pth.stat().st_size != r['bytes']:
            bad.append((r['file'], f'size {pth.stat().st_size} != {r["bytes"]}'))
        elif sha and sha256_file(pth) != r['sha256']:
            bad.append((r['file'], 'sha256 mismatch'))
    return bad


def manifest_mode(op: str, corpus_arg: str | None) -> int:
    """op: 'verify-size' | 'verify' | 'fetch-missing' | 'stamp'. See the docstring."""
    if not MANIFEST.exists():
        print(f'NOT DONE — no manifest at {MANIFEST}. Build one on the box with --build-manifest.')
        return 1
    meta_doc, rows = load_manifest()
    meta = meta_doc.get('_meta', {})

    # WHERE the corpus is — one resolver, never a default (corpus_locator.py).
    # A stamp may name a directory that DISAGREES with the meta (the corpus
    # moved); everything else must agree or refuse.
    if op == 'stamp':
        if not corpus_arg:
            print(f'NOT DONE — --stamp-corpus-dir needs an explicit --corpus-dir: {STAMP_CMD}')
            return 1
        corpus, source = Path(corpus_arg).expanduser(), 'explicit (stamping)'
        if not corpus.is_dir():
            print(f'NOT DONE — --corpus-dir {corpus} is not a directory'); return 1
    else:
        try:
            corpus, source = resolve_corpus_dir(corpus_arg, meta, MANIFEST, 'fetch_ami_video')
        except CorpusDirError as e:
            print(str(e)); return 1

    label = {'verify-size': 'VERIFY (size only; read-only, never fetches)',
             'verify': 'VERIFY (sha256; read-only, never fetches)',
             'fetch-missing': 'FETCH MISSING (network), then size-check',
             'stamp': f'STAMP {META_KEY} after a full sha256 verify'}[op]
    print(f'MANIFEST MODE — {label}: {len(rows)} files defined by {MANIFEST.name} '
          f'(built {meta.get("built_utc", "?")}); corpus_dir={corpus} [{source}]', flush=True)

    if op == 'fetch-missing':
        corpus.mkdir(parents=True, exist_ok=True)
        missing = [r for r in rows if not (corpus / r['file']).exists()]
        staged = [r['file'] for r in missing if not r.get('url')]
        if staged:
            print(f'NOT DONE — {len(staged)} missing row(s) carry no url (staged corpus: files '
                  f'are placed by whoever staged them and NEVER fetched). Missing from {corpus}: '
                  f'{staged[:10]}{" ..." if len(staged) > 10 else ""}')
            return 1
        for i, r in enumerate(missing, 1):
            print(f'  fetch [{i}/{len(missing)}] {r["file"]}', flush=True)
            if not fetch_url(r['url'], corpus / r['file']):
                print(f'NOT DONE — {r["url"]} returned 404; the mirror no longer matches the manifest.')
                return 1

    sha = op in ('verify', 'stamp')
    print(f'verifying against the manifest ({"sha256" if sha else "size only"}) ...', flush=True)
    bad = _check_rows(rows, corpus, sha)
    if bad:
        print(f'NOT DONE — the corpus at {corpus} does not match the manifest '
              f'({len(bad)} of {len(rows)} rows):')
        for f, why in bad[:40]:
            print(f'  {f}: {why}')
        if len(bad) > 40:
            print(f'  ... and {len(bad) - 40} more')
        if op != 'fetch-missing' and any(why.startswith('missing') for _, why in bad):
            print('A verify never fetches. If these files are meant to be downloaded, that is '
                  '--fetch-missing; if the corpus is elsewhere, that is --corpus-dir.')
        return 1

    if op == 'stamp':
        previous = manifest_corpus_dir(meta)
        before = sha256_file(MANIFEST)
        raw = MANIFEST.read_text().splitlines()
        data_lines = [l for l in raw if l.strip() and '_meta' not in json.loads(l)]
        new_meta = dict(meta)
        new_meta[META_KEY] = str(corpus.resolve())
        new_meta['corpus_dir_stamped'] = {
            'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'proof': f'sha256 verify {len(rows)}/{len(rows)} against this directory',
            'previous': str(previous) if previous else None}
        MANIFEST.write_text(json.dumps({'_meta': new_meta}) + '\n'
                            + ''.join(l + '\n' for l in data_lines))
        # Data rows byte-identical, PROVEN not assumed.
        after_data = [l for l in MANIFEST.read_text().splitlines()
                      if l.strip() and '_meta' not in json.loads(l)]
        if after_data != data_lines:
            print('NOT DONE — data rows changed while stamping; restore the manifest from backup')
            return 1
        print(f'STAMPED {META_KEY}={corpus.resolve()} into {MANIFEST.name} '
              f'(meta line only; {len(data_lines)} data rows byte-identical). '
              f'manifest sha256 {before[:16]} -> {sha256_file(MANIFEST)[:16]}'
              + (f'; previous {META_KEY}={previous}' if previous else ''), flush=True)

    print(f'DONE verified={len(rows)}/{len(rows)} against {MANIFEST.name} '
          f'({"sha256" if sha else "size only — pass --verify for sha256"}) at {corpus}; '
          f'roles: {sum(1 for r in rows if r["role"] == "measured")} measured, '
          f'{sum(1 for r in rows if r["role"] == "warm")} warm', flush=True)
    return 0


def main() -> int:
    # allow_abbrev=False: an abbreviated flag is an unmeasured identity claim
    # (register entry 8 — `--measured-chars` silently matched the full name).
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--build-manifest', action='store_true',
                    help='discovery: construct the manifest (run ONCE, on the box)')
    ap.add_argument('--verify', action='store_true',
                    help='manifest mode: sha256 every file. READ-ONLY — never fetches')
    ap.add_argument('--fetch-missing', action='store_true',
                    help='manifest mode: download absent rows that carry a url (staged rows '
                         'are never fetched), then size-check. The only operation that '
                         'touches the network')
    ap.add_argument('--stamp-corpus-dir', action='store_true',
                    help=f'manifest mode: full sha256 verify against --corpus-dir, then record '
                         f'it as _meta.{META_KEY} so run_plan and every tool derive it. Meta '
                         'line only; data rows asserted byte-identical. Run once per corpus')
    ap.add_argument('--n-measured', type=positive_int('n-measured', 500), default=N_MEASURED)
    ap.add_argument('--n-warm', type=positive_int('n-warm', 500), default=N_WARM)
    ap.add_argument('--manifest', default=None, help='override manifest path (wiring tests)')
    ap.add_argument('--corpus-dir', default=None,
                    help='REQUIRED for --build-manifest and --stamp-corpus-dir; otherwise '
                         'optional and must agree with the manifest meta (corpus_locator.py)')
    ap.add_argument('--view', default=None,
                    help='comma-separated view preference, e.g. Closeup1 (default: '
                         'Corner,Overhead). Closeup1 is the only view present in ES, IS '
                         'AND TS rooms, so it is the one that reaches the full set.')
    ap.add_argument('--meeting-list', default=None,
                    help="a checked-in set file of meeting ids, one per line, taken in "
                         "FILE ORDER (Crossroad 36: adopting a corpus means adopting its "
                         "row order, because roles are assigned positionally). Overrides "
                         "the built-in scenario generator, including families it never "
                         "emits (EN, IB).")
    ap.add_argument('--staged', action='store_true',
                    help='corpus files are already staged/muxed and named <meeting>.avi; '
                         'never download — an absent file fails loudly rather than '
                         'silently substituting a raw camera file')
    ap.add_argument('--measured-dpf', type=bounded_float('measured-dpf', 0.1, 500.0),
                    default=None,
                    help='build: probe-measured detections/frame (summarize_probe_rr.py '
                         'prints it; 25.95 measured 2026-08-21) — REQUIRED for '
                         '--build-manifest, never defaulted; value validated, not just present')
    ap.add_argument('--measured-chars-per-det',
                    type=bounded_float('measured-chars-per-det', 0.1, 10000.0),
                    default=None,
                    help='build: probe-measured chars/detection (230.4 measured 2026-08-21) '
                         '— REQUIRED for --build-manifest, never defaulted; value validated')
    args = ap.parse_args()
    global MANIFEST, CORPUS
    if args.manifest:
        MANIFEST = Path(args.manifest)
    CORPUS = Path(args.corpus_dir).expanduser() if args.corpus_dir else None  # never carried over
    if args.view:
        globals()['VIEW_PREFERENCE'] = [v.strip() for v in args.view.split(',') if v.strip()]
        if not VIEW_PREFERENCE:
            print('NOT DONE — --view given but empty'); return 1
    if args.meeting_list:
        mlp = Path(args.meeting_list)
        if not mlp.is_file():
            print(f'NOT DONE — --meeting-list {mlp} is not a file'); return 1
        globals()['MEETING_LIST_PATH'] = mlp
        globals()['MEETING_IDS'] = meeting_ids_from_list(mlp)
        if not MEETING_IDS:
            print(f'NOT DONE — --meeting-list {mlp} yielded no ids'); return 1
    if args.staged:
        globals()['STAGED_NAMES'] = True
    ops = [n for n, on in (('verify', args.verify), ('fetch-missing', args.fetch_missing),
                           ('stamp', args.stamp_corpus_dir), ('build', args.build_manifest)) if on]
    if len(ops) > 1:
        print(f'NOT DONE — one operation at a time, got {ops}'); return 1
    if args.build_manifest:
        if CORPUS is None:
            print('NOT DONE — --build-manifest needs --corpus-dir (no manifest exists yet to '
                  'derive it from, and this file carries no default that names a corpus)')
            return 1
        return build_mode(args.n_measured, args.n_warm,
                          args.measured_dpf, args.measured_chars_per_det)
    return manifest_mode(ops[0] if ops else 'verify-size', args.corpus_dir)


if __name__ == '__main__':
    sys.exit(main())
