#!/usr/bin/env python3
"""Detect-text tap probe — the upgrade after the 1009 refusal (2026-08-27).

Why it exists: probe_frame_identity uses client.send(), which writes the whole
film as ONE DAP message (mixins/data.py:456-468); the engine's websocket
refuses any message over 250 MiB — server 1009 'message too big',
429,700,563 bytes (= the 429,700,405-byte film + 158 bytes of DAP envelope)
vs limit 262,144,000 (CONST_WEB_WS_MAX_SIZE, ai/constants.py:74, applied at
ai/web/server.py:458; the client pins the same 250 MiB for what IT receives,
transport_websocket.py:384). This probe uploads the way the measured driver
does — 1 MiB chunked writes (driver_video.py:436,449-450; each write its own
DAP request, data.py:208-244), streamed from disk so the film is never whole
in memory — and taps the pipeline for ground truth.

Pipe variant (measured pipe untouched; a3/envprobe pattern,
driver_video.py:596-608 + probe_frame_identity.py:45-55):
  * response_text on DETECT's text lane (laneName 'detections') — the
    engine-delivered per-frame JSON lines, upstream of the splitter. The
    response node COALESCES writeText calls into one string joined by
    '\\n\\n' (nodes/response/IInstance.py:145-147, appended once at close,
    :105-114) — whitespace to the array parser, and recorded so nobody
    reads the tap's bytes as the splitter's input.
  * response_documents on frame_grabber's documents lane (laneName
    'frames') — per-frame chunkId for the index-completeness count.
    OPTIONAL (--no-frames-tap): its response carries every frame PNG
    base64 and both sides cap messages at 250 MiB, so it is for films
    whose PNG total stays well under ~180 MB (20000Leagues: frames
    <= ~0.1 MB each, measured by probe_frame_parity's parser_max_buffer).
  * the measured pipe's own response_documents still returns the CHUNK
    texts — the exact bytes a leg's record derivation sees.

FOUR NUMBERS, side by side — never averaged, never reconciled; a
disagreement IS the result:
  1. engine_frames_tap   — index-completeness count over chunkId
                           (gs.index_completeness; gapless, duplicate-free,
                           starts at 0), NOT RUN under --no-frames-tap.
  2. detect_text_count   — arrays raw-decoded from the detect-lane text
                           (frame_arrays_from_chunks on a ONE-element list:
                           no seam logic runs; pure decode).
  3. stripper_count      — frames_from_chunks (the driver's real seam
                           stripper, IMPORTED, one copy) over the chunk
                           texts as received.
  4. naive_count         — full.count("[{") + full.count("[]") over the
                           plain concatenation: Leela's RR counter,
                           bench_video.py:106 at 313430f3 (the sha her
                           films500 RR run executed), reproduced here as
                           the instrument under test.

Stripper forensics (the inverse failure mode, driver_video.py:303-307 —
"runs of byte-identical short frames straddling a boundary are
indistinguishable from overlap-copies"): per chunk boundary the probe
reports k stripped, the stripped span, and its pattern class
(empty-frame-lines / short-detection-lines / partial-line). Text alone
cannot adjudicate copy-vs-real — but THIS probe holds the detect-lane
ground truth, so it compares the stripper's reassembled arrays against the
engine's own text elementwise and, if the stripper deleted a real frame or
retained a duplicate, SAYS SO with indices. The forensic k-scan is a local
mirror of the imported stripper; the probe asserts the two agree on every
boundary and refuses (INSTRUMENT MISMATCH) if they ever diverge.

Fail-closed: any engine/SDK error (recorded with its FULL exception chain —
dap_client.py:229 strips causes, so the probe keeps them), a missing
response lane, or a detect text that does not raw-decode (truncated stream)
exits 1 with the failure in the artifact. Index gaps, count disagreements,
and stripper deletions are FINDINGS: recorded, exit 0.

Binds: film sha256 (--film-sha-expected refuses a mismatch), rr image id,
git HEAD, measured-pipe sha256, the generated variant's appended components
and project_id. Artifacts move aside as .prev_ (entry 7).

Exit codes: 0 completed (findings in artifact) / 1 machinery, guard, or
truncation / 4 --self-test failure.

Run (box; rr container up; floor venv has the SDK):
  ~/.venv-floor/bin/python3 working/video/probe/probe_detect_text.py \
      --film ~/films_probe/20000LeaguesUndertheSea.mp4 \
      --film-sha-expected <sha256 from corpus_manifest.json>
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # working
from argtypes import positive_int          # noqa: E402 — register entry 8
from harness import gates_shared as gs     # noqa: E402 — one copy: index_completeness
# ONE COPY (entries 6/14): the counts under test are the driver's own
# functions, imported — never re-implemented here.
from driver_video import frames_from_chunks, frame_arrays_from_chunks  # noqa: E402
from probe_rr import fresh_project_pipe    # noqa: E402

PIPE_SRC = Path(__file__).resolve().parents[1] / 'benchmark_video_detect.pipe'
WRITE_CHUNK = 1024 * 1024      # the driver's shape: driver_video.py:436
UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())


# ------------------------------------------------------------------- helpers

def sha256_file(path: Path, chunk: int = 1 << 20):
    h, n = hashlib.sha256(), 0
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def exc_chain(e: BaseException, limit: int = 6) -> list:
    """The full cause chain — dap_client.py:229 discards it; this probe
    records it (entry 20, second occurrence 2026-08-27)."""
    out, seen = [], set()
    while e is not None and id(e) not in seen and len(out) < limit:
        seen.add(id(e))
        out.append(f'{type(e).__name__}: {e}')
        e = e.__cause__ or e.__context__
    return out


def preserve(path: Path):
    """Entry 7: a re-run must not destroy prior evidence."""
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


def run_text(argv, timeout=60):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# ------------------------------------------------- stripper forensics (TASK 3)

def forensic_k(prev: str, cur: str, max_k: int = 400) -> int:
    """Mirror of the imported stripper's k-scan (driver_video.py:234-240),
    kept ONLY for reporting; consistency with the imported functions is
    asserted by the caller on every boundary."""
    for k in range(min(max_k, len(prev), len(cur)), 0, -1):
        if prev.endswith(cur[:k]):
            return k
    return 0


_EMPTY_RUN = re.compile(r'^(?:\s*\[\]\s*)+$')


def classify_span(span: str) -> str:
    if not span:
        return 'none'
    if _EMPTY_RUN.fullmatch(span):
        return 'empty-frame-lines'
    dec, i, n, arrays, ok = json.JSONDecoder(), 0, len(span), 0, True
    try:
        while i < n:
            while i < n and span[i] in ' \t\r\n':
                i += 1
            if i >= n:
                break
            obj, i = dec.raw_decode(span, i)
            if not isinstance(obj, list):
                ok = False
                break
            arrays += 1
    except json.JSONDecodeError:
        ok = False
    if ok and arrays:
        return 'short-detection-lines' if any(c == '{' for c in span) \
            else 'empty-frame-lines'
    return 'partial-line'


def stripper_forensics(contents: list) -> dict:
    """Per-boundary strip report + reassembly consistent with the imported
    stripper (asserted). Returns the report and the reassembled text."""
    if not contents:
        return {'n_boundaries': 0, 'boundaries': [], 'reassembled': ''}
    parts, boundaries = [contents[0]], []
    for i, (prev, cur) in enumerate(zip(contents, contents[1:])):
        k = forensic_k(prev, cur)
        span = cur[:k]
        boundaries.append({'boundary': i, 'k_stripped': k,
                           'stripped_span': span if k else None,
                           'class': classify_span(span) if k else 'none'})
        parts.append(cur[k:])
    stripped = [b for b in boundaries if b['k_stripped']]
    return {
        'n_boundaries': len(boundaries),
        'n_stripped_boundaries': len(stripped),
        'total_stripped_chars': sum(b['k_stripped'] for b in stripped),
        'stripped_span_lengths': [b['k_stripped'] for b in stripped] or None,
        'stripped_classes': sorted({b['class'] for b in stripped}) or None,
        'boundaries': boundaries,
        'reassembled': ''.join(parts),
    }


def compare_arrays(stripped, truth) -> dict:
    """Stripper output vs the engine's own detect-lane arrays, elementwise.
    If the stripper deleted a real frame or retained a duplicate, this is
    where the run says so."""
    if stripped is None or truth is None:
        return {'verdict': 'CANNOT COMPARE — a side failed to decode',
                'n_stripped': None if stripped is None else len(stripped),
                'n_truth': None if truth is None else len(truth)}
    first = next((i for i, (a, b) in enumerate(zip(stripped, truth))
                  if a != b), None)
    if len(stripped) == len(truth) and first is None:
        verdict = ('MATCH — stripper output equals the engine text: no real '
                   'frame deleted, no duplicate retained')
    elif len(stripped) < len(truth):
        verdict = (f'STRIPPER DELETED {len(truth) - len(stripped)} real '
                   f'frame(s) — first divergence at index {first}')
    elif len(stripped) > len(truth):
        verdict = (f'stripper RETAINED {len(stripped) - len(truth)} '
                   f'duplicate/extra frame(s) — first divergence at index {first}')
    else:
        verdict = f'content mismatch at index {first} (equal counts)'
    return {'verdict': verdict, 'n_stripped': len(stripped),
            'n_truth': len(truth), 'first_divergence_index': first}


# ------------------------------------------------------------- pipe + upload

def generate_pipe(frames_tap: bool):
    base = fresh_project_pipe(PIPE_SRC, 'detect-text')
    added = [{'id': 'resp_dettext', 'provider': 'response_text',
              'config': {'laneName': 'detections'},
              'input': [{'lane': 'text', 'from': 'detect_1'}]}]
    if frames_tap:
        added.append({'id': 'resp_frames', 'provider': 'response_documents',
                      'config': {'laneName': 'frames'},
                      'input': [{'lane': 'documents', 'from': 'frame_grabber_1'}]})
    base['components'].extend(added)
    out = PIPE_SRC.parent / 'probe' / f'generated_detect_text_{os.getpid()}.pipe'
    out.write_text(json.dumps(base, indent=1))
    return out, base['project_id'], added


async def upload_chunked(client, token, film: Path, film_bytes: int) -> dict:
    """The driver's write path (driver_video.py:438-463), streamed from
    disk: 1 MiB per DAP request — the only admissible shape above the
    250 MiB message ceiling. mime video/mp4 routes by prefix to the video
    lane (data_conn._determine_lane)."""
    pipe = await client.pipe(token, {'name': film.name, 'size': film_bytes},
                             'video/mp4')
    await pipe.open()
    n_writes = 0
    t0 = time.monotonic()
    try:
        with open(film, 'rb') as fh:
            while True:
                chunk = fh.read(WRITE_CHUNK)
                if not chunk:
                    break
                await pipe.write(chunk)
                n_writes += 1
        t_close = time.monotonic()
        result = await pipe.close()
    except Exception:
        if pipe.is_opened:
            try:
                await pipe.close()
            except Exception:   # noqa: BLE001 — cleanup mirrors send()'s
                pass
        raise
    return {'result': result, 'n_writes': n_writes,
            'upload_wall_s': round(t_close - t0, 2),
            'close_wall_s': round(time.monotonic() - t_close, 2)}


# ------------------------------------------------------------------ selftest

def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    L = ['[{"label": "a", "score": 0.5}]', '[{"label": "b", "score": 0.7}]']
    E = '[]'

    # Case 1 — HER over-count mode: LangChain retained the short trailing
    # unit, duplicating it at the boundary. Truth: 3 frames.
    c1, c2 = f'{L[0]}\n{E}', f'{E}\n{L[1]}'
    truth3 = [json.loads(x) for x in (L[0], E, L[1])]
    naive = (c1 + c2).count('[{') + (c1 + c2).count('[]')
    check('naive counter over-counts the duplicated boundary (4 vs 3)',
          naive == 4)
    check('imported stripper counts 3', frames_from_chunks([c1, c2]) == 3)
    arr = frame_arrays_from_chunks([c1, c2])
    check('stripper arrays == truth (duplicate removed)', arr == truth3)
    cmp1 = compare_arrays(arr, truth3)
    check('ground-truth compare: MATCH', cmp1['verdict'].startswith('MATCH'))

    # Case 2 — OUR inverse mode: the SAME two texts, but the empties are
    # REAL distinct frames (truth: 4). Text-identical to case 1 — the
    # documented indistinguishability — and the ground-truth compare must
    # say the stripper deleted a frame.
    truth4 = [json.loads(x) for x in (L[0], E, E, L[1])]
    cmp2 = compare_arrays(frame_arrays_from_chunks([c1, c2]), truth4)
    check('deletion detector fires: STRIPPER DELETED 1 real frame',
          cmp2['verdict'].startswith('STRIPPER DELETED 1'))
    check('naive count equals truth here by coincidence (4) — why no single '
          'number adjudicates', naive == 4)

    # Case 3 — clean boundary, nothing stripped, everything agrees.
    d1, d2 = L[0], L[1]
    fx = stripper_forensics([d1, d2])
    check('clean boundary strips nothing',
          fx['n_stripped_boundaries'] == 0 and
          frames_from_chunks([d1, d2]) == 2)

    # Forensic mirror consistency (asserted the same way main() asserts it).
    fx1 = stripper_forensics([c1, c2])
    check('forensic reassembly decodes to the imported stripper arrays',
          frame_arrays_from_chunks([c1, c2]) ==
          frame_arrays_from_chunks([fx1['reassembled']]))
    check('forensic k reports the duplicated span as empty-frame-lines',
          fx1['boundaries'][0]['class'] == 'empty-frame-lines' and
          fx1['boundaries'][0]['k_stripped'] == 2)

    # Classification: a complete short detection line vs a partial slice.
    check("classify short detection line", classify_span(L[0]) ==
          'short-detection-lines')
    check("classify partial line", classify_span(L[0][:-3]) == 'partial-line')
    check("classify empty run", classify_span('[]\n[]') == 'empty-frame-lines')

    # Single-element list = pure rawdecode (no seam logic can run).
    blob = '\n\n'.join([L[0], E, L[1]]) + '\n\n'
    check('detect-lane text decodes to 3 arrays via the imported parser',
          frame_arrays_from_chunks([blob]) == truth3)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

async def amain(args) -> int:
    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        raise SystemExit(f'NOT DONE — film not found: {film}')
    print(f'film sha256: hashing {film.name} ...')
    film_sha, film_bytes = sha256_file(film)
    if args.film_sha_expected and film_sha != args.film_sha_expected:
        raise SystemExit(f'NOT DONE — film sha mismatch: measured {film_sha}, '
                         f'expected {args.film_sha_expected}. Refusing to '
                         'measure an unverified input.')

    rc, image_id, err = run_text(['docker', 'inspect', '--format',
                                  '{{.Image}}', args.container])
    if rc != 0:
        raise SystemExit(f'NOT DONE — docker inspect {args.container!r} failed '
                         f'({err[-200:]}); the rr container must already be up '
                         '(this probe never starts one).')

    repo = Path(__file__).resolve().parents[3]
    rc, head, _ = run_text(['git', '-C', str(repo), 'rev-parse', 'HEAD'])

    pipe_path, project_id, added = generate_pipe(frames_tap=not args.no_frames_tap)
    artifact = {
        'probe': 'detect_text', 'created_utc': UTC,
        'git_head': head if rc == 0 else 'UNAVAILABLE',
        'film': {'path': str(film), 'name': film.name, 'bytes': film_bytes,
                 'sha256': film_sha, 'sha_expected': args.film_sha_expected},
        'rr_image_id': image_id, 'container': args.container,
        'measured_pipe_sha256': hashlib.sha256(PIPE_SRC.read_bytes()).hexdigest(),
        'generated_pipe': str(pipe_path), 'project_id': project_id,
        'appended_components': added, 'mime': 'video/mp4', 'ttl': args.ttl,
        'write_chunk_bytes': WRITE_CHUNK,
        'ceiling_note': ('whole-message sends >= 262,144,000 bytes are refused '
                         'by the server (1009; ai/constants.py:74, '
                         'server.py:458) — this probe uploads 1 MiB writes'),
    }
    out = Path(args.out) if args.out else \
        Path(__file__).parent / f'probe_detect_text_{film.stem}.json'

    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{args.port}'
    os.environ.setdefault('ROCKETRIDE_APIKEY', 'local-dev')
    from rocketride import RocketRideClient
    client = RocketRideClient()
    await client.connect(timeout=60000)
    token = None
    try:
        started = await client.use(filepath=str(pipe_path), ttl=args.ttl)
        token = started['token']
        up = await upload_chunked(client, token, film, film_bytes)
        artifact.update({k: up[k] for k in
                         ('n_writes', 'upload_wall_s', 'close_wall_s')})
        result = up['result'] or {}
    except Exception as exc:   # noqa: BLE001 — recorded with its full chain
        artifact['FAILED'] = {'stage': 'upload/close',
                              'exception_chain': exc_chain(exc)}
        preserve(out)
        out.write_text(json.dumps(artifact, indent=1))
        print(f'NOT DONE — upload/close failed; chain: '
              f'{artifact["FAILED"]["exception_chain"]}; artifact {out}')
        return 1
    finally:
        if token:
            try:   # terminate BEFORE disconnect (Ticket 4)
                await asyncio.wait_for(client.terminate(token), timeout=60)
            except Exception as exc:   # noqa: BLE001
                print(f'terminate: {exc!r} (recorded; ttl={args.ttl} reaps)')
        await client.disconnect()

    failures = []

    # --- detect-lane ground truth ------------------------------------------
    texts = result.get('detections')
    if not texts:
        failures.append(f"response lane 'detections' absent/empty "
                        f"(keys: {sorted(result.keys())})")
        detect_text, arrays_detect = None, None
    else:
        detect_text = ''.join(texts)
        arrays_detect = frame_arrays_from_chunks([detect_text])
        if arrays_detect is None:
            failures.append('detect-lane text did not raw-decode — truncated '
                            'stream; fail-closed')
    artifact['detect_tap'] = {
        'n_text_entries': len(texts) if texts else 0,
        'coalescing_note': ("response_text joins writeText calls with '\\n\\n' "
                            '(nodes/response/IInstance.py:145-147,105-114) — '
                            "whitespace to the array parser; NOT the "
                            "splitter's input bytes"),
        'chars': len(detect_text) if detect_text else 0,
        'text': detect_text,
    }

    # --- chunk texts as a leg receives them --------------------------------
    docs = result.get('documents')
    if not docs:
        failures.append("response lane 'documents' absent/empty — the measured "
                        'pipe should always return chunk documents')
        contents = []
    else:
        contents = [d.get('page_content') or '' for d in docs]
    artifact['chunks'] = {'n_chunks': len(contents),
                          'chunk_chars': [len(c) for c in contents],
                          'texts': contents}

    # --- frames tap (index completeness) -----------------------------------
    if args.no_frames_tap:
        artifact['frames_tap'] = {'status': 'NOT RUN — --no-frames-tap '
                                            '(response size bound)'}
        engine_frames = None
    else:
        fdocs = result.get('frames')
        if not fdocs:
            failures.append("response lane 'frames' absent/empty with the "
                            'frames tap enabled')
            engine_frames = None
        else:
            rows = []
            for d in fdocs:
                md = d.get('metadata') or {}
                try:
                    png_len = len(base64.b64decode(d.get('page_content') or ''))
                except Exception:   # noqa: BLE001
                    png_len = None
                rows.append({'chunkId': md.get('chunkId'),
                             'time_stamp': md.get('time_stamp'),
                             'png_bytes': png_len})
            idx = [r['chunkId'] for r in rows]
            comp = gs.index_completeness(idx)
            engine_frames = len(rows)
            artifact['frames_tap'] = {'n_frames': engine_frames,
                                      'index_completeness': comp,
                                      'frames': rows}

    # --- the four numbers ---------------------------------------------------
    stripper_count = frames_from_chunks(contents) if contents else None
    full = ''.join(contents)
    naive_count = (full.count('[{') + full.count('[]')) if contents else None
    detect_count = len(arrays_detect) if arrays_detect is not None else None
    artifact['four_numbers'] = {
        '1_engine_frames_tap': engine_frames,
        '2_detect_text_count': detect_count,
        '3_stripper_count': stripper_count,
        '4_naive_count': naive_count,
        'rule': 'never averaged, never reconciled — a disagreement is the result',
        'naive_basis': 'full.count("[{")+full.count("[]") over "".join(texts) '
                       '— bench_video.py:106 @ 313430f3 (the instrument under test)',
    }

    # --- stripper forensics + ground-truth adjudication --------------------
    if contents:
        fx = stripper_forensics(contents)
        arrays_stripped = frame_arrays_from_chunks(contents)
        mirror_ok = (arrays_stripped == frame_arrays_from_chunks(
            [fx['reassembled']]))
        if not mirror_ok:
            failures.append('INSTRUMENT MISMATCH — forensic k-scan diverged '
                            'from the imported stripper; forensics unusable')
        naive_arrays = frame_arrays_from_chunks([full])
        artifact['stripper_forensics'] = {
            k: fx[k] for k in ('n_boundaries', 'n_stripped_boundaries',
                               'total_stripped_chars', 'stripped_span_lengths',
                               'stripped_classes', 'boundaries')}
        artifact['stripper_forensics']['mirror_consistent'] = mirror_ok
        artifact['adjudication'] = {
            'stripped_vs_detect_text': compare_arrays(arrays_stripped,
                                                      arrays_detect),
            'naive_vs_detect_text': compare_arrays(naive_arrays, arrays_detect),
        }

    if failures:
        artifact['FAILED'] = {'stage': 'response-parse', 'reasons': failures}
    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back, then report
    four = rb['four_numbers']
    print(f'wrote {out}')
    print(f'FOUR NUMBERS — {rb["film"]["name"]}: '
          f'frames_tap={four["1_engine_frames_tap"]} | '
          f'detect_text={four["2_detect_text_count"]} | '
          f'stripper={four["3_stripper_count"]} | '
          f'naive={four["4_naive_count"]}')
    if 'adjudication' in rb:
        print(f'stripper vs engine text: '
              f'{rb["adjudication"]["stripped_vs_detect_text"]["verdict"]}')
        print(f'naive    vs engine text: '
              f'{rb["adjudication"]["naive_vs_detect_text"]["verdict"]}')
    if 'FAILED' in rb:
        print(f'NOT DONE — {rb["FAILED"]}')
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--film')
    ap.add_argument('--film-sha-expected', default=None)
    ap.add_argument('--port', type=positive_int('port', 65535), default=5565)
    ap.add_argument('--container', default='rr')
    ap.add_argument('--ttl', type=positive_int('ttl', 86400), default=3600,
                    help='instrument token keeps a FINITE ttl deliberately '
                         '(Crossroad 43: short-lived, terminated in finally)')
    ap.add_argument('--no-frames-tap', action='store_true',
                    help='skip the response_documents frames tap (use for '
                         'films whose PNG total approaches the 250 MiB '
                         'response ceiling); index-completeness reports NOT RUN')
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true',
                    help='stripper forensics + deletion detector + counters on '
                         'synthetic frames; no engine, no docker')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.film:
        ap.error('--film is required (unless --self-test)')
    if args.film_sha_expected and not re.fullmatch(r'[0-9a-f]{64}',
                                                   args.film_sha_expected):
        ap.error('--film-sha-expected must be 64 lowercase hex chars')
    return asyncio.run(amain(args))


if __name__ == '__main__':
    sys.exit(main())
